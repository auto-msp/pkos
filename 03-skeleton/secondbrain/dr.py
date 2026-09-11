"""Backup and disaster recovery (SOW 26, 93 - Phase 26).

THE QUESTION THIS MODULE ANSWERS
================================
Not "did a backup run?" - every backup system on earth answers that, and it is
nearly worthless. The question is:

    HOW LONG AGO DID WE LAST PROVE WE COULD RESTORE?

A backup that has never been restored is a hypothesis. SOW 93 says so, and
today gave three separate demonstrations of why: a vault sync dead since June
that logged "STARTED" every morning, a 2am chain whose cleanup had not run
since August, and a tarball taken mid-rsync that was 6.5 MB short and looked
completely normal.

So `drill` is the centre of this module, not `create`. A drill restores a
backup into a scratch store, runs the deep validation, re-hashes every blob,
compares the result against the live store, and records the outcome in the
audit log. `status` then reports how stale that proof is - because "last
backup 2 hours ago, last PROVEN restore 41 days ago" is the honest position,
and it is the one that gets acted on.

TIERS (SOW 26)
    primary    same machine, fast to make, useless against machine loss
    secondary  another machine in the fleet
    offsite    outside the tenancy entirely
Each is reported separately. A store with three copies in one blast radius has
one backup, not three, and status says so.
"""
import json, shutil, sqlite3, tempfile
from pathlib import Path

from . import evidence, validate as validate_mod
from .config import Paths
from .events import audit
from .util import now_iso, human

MANIFEST = "BACKUP.json"
TIERS = ("primary", "secondary", "offsite")


def _counts(conn):
    q = lambda s: conn.execute(s).fetchone()[0]
    return {"objects": q("SELECT COUNT(*) FROM object"),
            "versions": q("SELECT COUNT(*) FROM object_version"),
            "relationships": q("SELECT COUNT(*) FROM relationship"),
            "blobs": q("SELECT COUNT(*) FROM evidence_blob"),
            "evidence_bytes": q("SELECT COALESCE(SUM(byte_size),0) FROM evidence_blob")}


def create(conn, paths, dest, tier="primary", include_evidence=False, label=None):
    """Write a backup. The database is VACUUMed, never copied while live.

    The previous implementation used shutil.copytree on the canonical
    directory. Copying a live SQLite file gives you a torn snapshot that has
    the right name, a plausible size and a clean exit code - the exact failure
    that produced a 6.5 MB-short vault archive today. VACUUM INTO produces a
    consistent database by construction.
    """
    if tier not in TIERS:
        raise ValueError("tier must be one of %s" % (TIERS,))
    dest = Path(dest).expanduser().resolve()
    stamp = now_iso().replace(":", "").replace("-", "")

    # The stamp is whole seconds, so two backups started within the same second
    # want the same directory. The old code took it with exist_ok=True, which
    # is the most dangerous possible answer: the JSONL mirror is rewritten into
    # the FIRST backup's folder before VACUUM INTO refuses the existing
    # database file, so the run fails AND leaves a good backup half-overwritten.
    # That is post-mortem 12.5 with a different trigger. A backup directory is
    # therefore never reused: claim a fresh one atomically, or say why not.
    target, n = dest / ("pkos-backup-%s-%s" % (tier, stamp)), 1
    while True:
        try:
            target.mkdir(parents=True, exist_ok=False)
            break
        except FileExistsError:
            n += 1
            if n > 99:
                return {"ok": False, "error":
                        "refusing to write into an existing backup directory; "
                        "99 variants of %s already exist" % target.name}
            target = dest / ("pkos-backup-%s-%s-%02d" % (tier, stamp, n))
    (target / "canonical").mkdir(parents=True, exist_ok=True)

    db_out = target / "canonical" / "canonical.sqlite3"
    try:
        conn.execute("VACUUM INTO '%s'" % str(db_out).replace("'", "''"))
    except sqlite3.Error as exc:
        shutil.rmtree(target, ignore_errors=True)
        return {"ok": False, "error": "VACUUM INTO failed (%s); the partial "
                "backup directory was removed and no existing backup was "
                "touched" % exc}
    c = sqlite3.connect(str(db_out))
    integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
    fk = len(c.execute("PRAGMA foreign_key_check").fetchall())
    counts = _counts(c)
    lineage = (c.execute("SELECT uuid FROM object ORDER BY object_id LIMIT 1")
                .fetchone() or [None])[0]
    c.close()
    if integrity != "ok" or fk:
        shutil.rmtree(target, ignore_errors=True)
        return {"ok": False, "error": "the vacuumed copy failed its own integrity "
                "check (%s, %d fk violation(s)); nothing was written" % (integrity, fk)}

    from . import export as export_mod
    export_mod.export_all(conn, target / "canonical" / "mirror")

    ev_bytes = 0
    if include_evidence:
        shutil.copytree(str(paths.blobs), str(target / "evidence" / "blobs"))
        for f in (target / "evidence" / "blobs").rglob("*"):
            if f.is_file():
                ev_bytes += f.stat().st_size

    man = {"created_at": now_iso(), "tier": tier, "label": label,
           "store_lineage": lineage, "counts": counts,
           "includes_evidence": bool(include_evidence),
           "evidence_bytes_copied": ev_bytes,
           "integrity_check": integrity, "foreign_key_violations": fk,
           "proven": False,
           "note": "SOW 93: this is a hypothesis until a restore drill passes."}
    (target / MANIFEST).write_text(json.dumps(man, indent=1), encoding="utf-8")
    audit(conn, "backup", "backup_created", "OK", target=str(target),
          detail={"tier": tier, "counts": counts, "evidence": include_evidence})
    conn.commit()
    return {"ok": True, "path": str(target), "manifest": man}


def list_backups(dest):
    dest = Path(dest).expanduser().resolve()
    out = []
    if not dest.exists():
        return out
    for d in sorted(dest.iterdir()):
        m = d / MANIFEST
        if d.is_dir() and m.exists():
            try:
                man = json.loads(m.read_text(encoding="utf-8"))
            except ValueError:
                continue
            man["path"] = str(d)
            out.append(man)
    return out


def drill(backup_dir, live_conn=None):
    """Restore into scratch and PROVE it. This is what makes a backup real."""
    b = Path(backup_dir).expanduser().resolve()
    rep = {"backup": str(b), "ok": False, "steps": []}

    def step(name, ok, detail=""):
        rep["steps"].append({"step": name, "ok": bool(ok), "detail": detail})
        return ok

    man_p = b / MANIFEST
    if not step("manifest present", man_p.exists()):
        return rep
    man = json.loads(man_p.read_text(encoding="utf-8"))
    rep["manifest"] = man

    src_db = b / "canonical" / "canonical.sqlite3"
    if not step("canonical database present", src_db.exists()):
        return rep

    scratch = Path(tempfile.mkdtemp(prefix="pkos-drill-"))
    try:
        # Restore into a REAL store layout, not just a loose file. A drill that
        # only opens the database proves the database; it does not prove that
        # a store can be stood up from this backup, which is the actual claim.
        p = Paths(scratch).ensure()
        shutil.copy2(str(src_db), str(p.db))
        if (b / "evidence" / "blobs").exists():
            shutil.rmtree(str(p.blobs), ignore_errors=True)
            shutil.copytree(str(b / "evidence" / "blobs"), str(p.blobs))
        # Every probe below runs inside `attempt`. A corrupted database raises
        # sqlite3.DatabaseError on the very first PRAGMA - and the first
        # version of this code let that exception escape, so the routine whose
        # entire purpose is detecting corruption CRASHED when it found some.
        # "Your backup is unusable" must arrive as a verdict, not a traceback.
        def attempt(name, fn, detail_ok=""):
            try:
                ok, det = fn()
                return step(name, ok, det or detail_ok)
            except Exception as e:                       # noqa: BLE001 - deliberate
                return step(name, False, "%s: %s" % (type(e).__name__, e))

        try:
            c = sqlite3.connect(str(p.db)); c.row_factory = sqlite3.Row
        except Exception as e:                           # noqa: BLE001
            step("open the restored database", False, "%s: %s" % (type(e).__name__, e))
            rep["ok"] = False
            return rep

        healthy = attempt("integrity_check", lambda: (
            c.execute("PRAGMA integrity_check").fetchone()[0] == "ok", ""))
        attempt("foreign keys", lambda: (
            len(c.execute("PRAGMA foreign_key_check").fetchall()) == 0, ""))

        if not healthy:
            # Nothing after this means anything: counts and invariants read
            # from a malformed file are noise, and running them would only
            # produce more confident-looking output about a dead backup.
            rep["steps"].append({"step": "remaining checks", "ok": None,
                                 "detail": "skipped - the database is malformed, "
                                           "so nothing read from it is meaningful"})
            try:
                c.close()
            except Exception:
                pass
            rep["ok"] = False
            return rep

        got = _counts(c)
        rep["counts_restored"] = got
        step("counts match the backup manifest",
             got["objects"] == man["counts"]["objects"],
             "restored %d vs manifest %d" % (got["objects"], man["counts"]["objects"]))

        deep = bool((b / "evidence" / "blobs").exists())
        r = validate_mod.run(c, p, deep=deep)
        rep["validation"] = {"status": r["status"], "failed": r["failed_checks"],
                             "deep": deep}
        step("invariants hold", r["status"] == "PASSED",
             "%d failed check(s)" % r["failed_checks"])
        if deep:
            step("every blob re-hashed",
                 r["integrity"]["corrupt"] == 0 and r["integrity"]["missing"] == 0,
                 "ok=%d missing=%d corrupt=%d" % (r["integrity"]["ok"],
                                                  r["integrity"]["missing"],
                                                  r["integrity"]["corrupt"]))
        else:
            rep["steps"].append({"step": "every blob re-hashed", "ok": None,
                                 "detail": "backup carries no evidence - the "
                                           "database restored, the BYTES it "
                                           "points at are unproven"})
        mirror = b / "canonical" / "mirror" / "MANIFEST.json"
        step("jsonl mirror present (vendor-neutral copy)", mirror.exists())

        if live_conn is not None:
            live = _counts(live_conn)
            rep["counts_live"] = live
            behind = {k: live[k] - got[k] for k in live}
            rep["behind_live_by"] = behind
            rep["steps"].append({
                "step": "recovery point", "ok": None,
                "detail": "restoring this backup would lose %d object(s) and "
                          "%d version(s) of work" % (max(behind["objects"], 0),
                                                     max(behind["versions"], 0))})
        c.close()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    rep["ok"] = bool(rep["steps"]) and all(
        s["ok"] for s in rep["steps"] if s["ok"] is not None)
    if rep["ok"]:
        man["proven"] = True
        man["last_proven_at"] = now_iso()
        man_p.write_text(json.dumps(man, indent=1), encoding="utf-8")
    return rep


def status(conn, dests):
    """The honest recovery position, per tier."""
    out = {"checked_at": now_iso(), "tiers": {}, "live": _counts(conn), "warnings": []}
    seen_any = False
    for tier in TIERS:
        out["tiers"][tier] = {"backups": 0, "newest": None, "last_proven": None,
                              "with_evidence": 0}
    for d in dests:
        for b in list_backups(d):
            seen_any = True
            t = out["tiers"].setdefault(b.get("tier", "primary"),
                                        {"backups": 0, "newest": None,
                                         "last_proven": None, "with_evidence": 0})
            t["backups"] += 1
            if b.get("includes_evidence"):
                t["with_evidence"] += 1
            if not t["newest"] or b["created_at"] > t["newest"]:
                t["newest"] = b["created_at"]
            lp = b.get("last_proven_at")
            if lp and (not t["last_proven"] or lp > t["last_proven"]):
                t["last_proven"] = lp
    if not seen_any:
        out["warnings"].append("no backups found in any of the given locations")
    for tier, t in out["tiers"].items():
        if t["backups"] and not t["last_proven"]:
            out["warnings"].append(
                "%s: %d backup(s) exist and NONE has ever been restore-tested. "
                "SOW 93: that is a hypothesis, not a backup." % (tier, t["backups"]))
        if t["backups"] and not t["with_evidence"]:
            out["warnings"].append(
                "%s: no backup here carries the evidence plane. The database "
                "would restore; the bytes it cites would not." % tier)
    empty = [t for t in TIERS if not out["tiers"][t]["backups"]]
    if empty:
        out["warnings"].append(
            "no backup at all in tier(s): %s. Copies inside one blast radius "
            "are one backup, not several." % ", ".join(empty))
    return out
