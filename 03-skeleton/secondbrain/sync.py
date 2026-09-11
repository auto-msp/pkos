"""Laptop <-> server replication (SOW 21.1, 22, 25 - Phase 25).

WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT
=============================================
It is not a two-way sync. Two-way sync between two copies of one brain means
conflict resolution, and conflict resolution on 39,000 objects means silently
picking a winner. The SOW already decided this: the server is the authority
(21.1). So this is REPLICATION - one direction, master to replica, verified.

It owns no transport. No sockets, no SSH library, no credentials. It builds a
bundle and it applies a bundle; scp, rsync, a USB stick or a courier moves it.
A knowledge store that stops working when a network library changes its API is
not one that survives twenty years, and the transport is the part most likely
to change.

THREE REFUSALS, WHICH ARE THE WHOLE POINT
  lineage   a bundle from a DIFFERENT store never applies. Two stores can look
            identical in shape and share no history; overwriting one with the
            other is unrecoverable. Lineage is the uuid of KB-00000001, which
            is allocated once and never changes.
  direction importing onto a store that is AHEAD is refused. This is the exact
            accident that nearly happened by hand today: the server held an
            11:00 copy while the laptop had a day of work on it, and pushing
            the wrong way would have erased it.
  integrity every blob is re-hashed after extraction, not merely checksummed
            in transit. An archive that unpacked cleanly is not evidence that
            the bytes inside it are the bytes that were sent.
"""
import gzip, json, os, shutil, sqlite3, tarfile, tempfile
from pathlib import Path

from . import evidence
from .events import audit
from .util import now_iso, human

BUNDLE_DB = "canonical.sqlite3.gz"
BUNDLE_BLOBS = "blobs-delta.tar.gz"
BUNDLE_MANIFEST = "MANIFEST.json"
BUNDLE_SUMS = "SHA256SUMS"


def lineage(conn):
    r = conn.execute("SELECT uuid FROM object ORDER BY object_id LIMIT 1").fetchone()
    return r["uuid"] if r else None


def manifest(conn, with_blobs=True):
    q = lambda s: conn.execute(s).fetchone()[0]
    m = {
        "store_lineage": lineage(conn),
        "schema_version": (conn.execute(
            "SELECT schema_version FROM schema_meta LIMIT 1").fetchone()
            or ["unknown"])[0],
        "generated_at": now_iso(),
        "counts": {
            "objects": q("SELECT COUNT(*) FROM object"),
            "versions": q("SELECT COUNT(*) FROM object_version"),
            "relationships": q("SELECT COUNT(*) FROM relationship"),
            "blobs": q("SELECT COUNT(*) FROM evidence_blob"),
            "evidence_bytes": q("SELECT COALESCE(SUM(byte_size),0) FROM evidence_blob"),
        },
        # A store that has never allocated an id has no id_sequence row at all.
        # That is the VIRGIN REPLICA - the single most important case for this
        # code - and the first version crashed on it. Treat absent as 1.
        "id_high_water": (conn.execute(
            "SELECT next_val FROM id_sequence WHERE prefix='KB'").fetchone()
            or [1])[0],
    }
    if with_blobs:
        m["blobs"] = {r["content_hash"]: r["byte_size"] for r in
                      conn.execute("SELECT content_hash, byte_size FROM evidence_blob")}
    return m


def plan(local, remote):
    """What would have to move for `remote` to match `local`."""
    out = {"can_send": True, "refusals": [], "warnings": []}
    if remote is None:
        out["blobs_to_send"] = sorted(local.get("blobs", {}))
        out["bytes_to_send"] = sum(local.get("blobs", {}).values())
        out["warnings"].append("no remote manifest supplied - planning a FULL bundle")
        return out
    if local["store_lineage"] != remote["store_lineage"]:
        out["can_send"] = False
        out["refusals"].append(
            "different store lineage (%s vs %s). These are not two copies of one "
            "store; applying one over the other would be unrecoverable."
            % ((local["store_lineage"] or "?")[:8], (remote["store_lineage"] or "?")[:8]))
    if remote["id_high_water"] > local["id_high_water"]:
        out["can_send"] = False
        out["refusals"].append(
            "the REMOTE is ahead (ids to %d, local only %d). Sending would erase "
            "work that exists only there. Pull from it instead."
            % (remote["id_high_water"], local["id_high_water"]))
    lb, rb = local.get("blobs", {}), remote.get("blobs", {})
    send = sorted(set(lb) - set(rb))
    only_remote = sorted(set(rb) - set(lb))
    out["blobs_to_send"] = send
    out["bytes_to_send"] = sum(lb[h] for h in send)
    out["blobs_only_on_remote"] = only_remote
    if only_remote:
        out["warnings"].append(
            "%d blob(s) exist only on the remote. Replacing its database would "
            "leave them unreferenced - acquire them here first." % len(only_remote))
    out["db_delta"] = {k: local["counts"][k] - remote["counts"][k]
                       for k in local["counts"]}
    return out


def export_bundle(conn, paths, out_dir, against=None, compress=6,
                  canonical_only=False):
    out = Path(out_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    local = manifest(conn)
    p = plan(local, against)
    if canonical_only:
        # Ship the database and no evidence. Legitimate only when the evidence
        # plane has not changed - and this is NOT taken on trust: the manifest
        # says so, and the importer proves it by checking that every blob the
        # incoming database references already exists on the receiving side.
        # An assertion the far end can verify is a fact; one it cannot is a hope.
        p["blobs_to_send"] = []
        p["bytes_to_send"] = 0
        p["warnings"].append(
            "canonical-only bundle: no evidence included. The importer will "
            "refuse it unless it already holds every blob the database names.")
    if not p["can_send"]:
        return {"ok": False, "plan": p}

    # canonical: VACUUM INTO a scratch file, then compress. Never tar a live
    # SQLite database - a copy taken mid-write is a torn snapshot that looks
    # perfectly normal until you try to use it.
    # The vacuum scratch file goes to LOCAL temp, never to the output
    # directory. The output is usually a mounted or removable medium - that is
    # the whole point of a bundle - and writing a 365 MB database through it
    # twice took 3 minutes here versus 7 seconds locally. The bundle medium
    # should carry the finished artefact, not the workings.
    scratchdir = Path(tempfile.mkdtemp(prefix="pkos-sync-"))
    scratch = scratchdir / "vacuum.sqlite3"
    conn.execute("VACUUM INTO '%s'" % str(scratch).replace("'", "''"))
    chk = sqlite3.connect(str(scratch))
    integrity = chk.execute("PRAGMA integrity_check").fetchone()[0]
    fk = len(chk.execute("PRAGMA foreign_key_check").fetchall())
    chk.close()
    if integrity != "ok" or fk:
        shutil.rmtree(scratchdir, ignore_errors=True)
        return {"ok": False, "plan": p,
                "error": "vacuumed copy failed its own integrity check "
                         "(%s, %d fk violation(s)) - refusing to ship it" % (integrity, fk)}
    with open(scratch, "rb") as f, gzip.open(out / BUNDLE_DB, "wb", compress) as g:
        shutil.copyfileobj(f, g, 1 << 20)
    db_bytes = scratch.stat().st_size
    shutil.rmtree(scratchdir, ignore_errors=True)

    # evidence: only the blobs the far end lacks
    sent = 0
    with tarfile.open(out / BUNDLE_BLOBS, "w:gz", compresslevel=compress) as t:
        for h in p["blobs_to_send"]:
            bp = evidence.blob_path(paths.blobs, h)
            if not bp.exists():
                continue
            t.add(str(bp), arcname="evidence/blobs/%s/%s/%s" % (h[:2], h[2:4], h))
            sent += 1

    local["bundle"] = {"built_at": now_iso(), "canonical_only": canonical_only,
                       "delta_against":
                       (against or {}).get("generated_at"),
                       "blobs_in_bundle": sent,
                       "canonical_bytes_uncompressed": db_bytes,
                       "direction": "master -> replica"}
    (out / BUNDLE_MANIFEST).write_text(json.dumps(local, indent=1), encoding="utf-8")
    sums = []
    for name in (BUNDLE_DB, BUNDLE_BLOBS, BUNDLE_MANIFEST):
        fp = out / name
        sums.append("%s  %s" % (evidence.hash_file(fp), name))
    (out / BUNDLE_SUMS).write_text("\n".join(sums) + "\n", encoding="utf-8")
    audit(conn, "sync", "bundle_exported", "OK", target=str(out),
          detail={"blobs": sent, "bytes": p["bytes_to_send"]})
    conn.commit()
    return {"ok": True, "plan": p, "dir": str(out), "blobs_in_bundle": sent,
            "sizes": {n: (out / n).stat().st_size
                      for n in (BUNDLE_DB, BUNDLE_BLOBS, BUNDLE_MANIFEST)}}


def import_bundle(paths, bundle_dir, local_conn=None, force=False):
    """Apply a bundle. Verifies before it touches anything."""
    b = Path(bundle_dir).expanduser().resolve()
    rep = {"ok": False, "checked": [], "refusals": [], "blobs_added": 0,
           "blobs_verified": 0}
    for name in (BUNDLE_DB, BUNDLE_BLOBS, BUNDLE_MANIFEST, BUNDLE_SUMS):
        if not (b / name).exists():
            rep["refusals"].append("bundle is missing %s" % name)
    if rep["refusals"]:
        return rep

    for line in (b / BUNDLE_SUMS).read_text().split("\n"):
        if not line.strip():
            continue
        want, name = line.split("  ", 1)
        got = evidence.hash_file(b / name)
        rep["checked"].append({"file": name, "ok": got == want})
        if got != want:
            rep["refusals"].append("checksum mismatch on %s" % name)
    if rep["refusals"]:
        return rep

    incoming = json.loads((b / BUNDLE_MANIFEST).read_text(encoding="utf-8"))
    if local_conn is not None:
        here = manifest(local_conn, with_blobs=False)
        if here["store_lineage"] and incoming["store_lineage"] != here["store_lineage"]:
            rep["refusals"].append(
                "lineage mismatch: bundle is from store %s, this is store %s"
                % ((incoming["store_lineage"] or "?")[:8], (here["store_lineage"] or "?")[:8]))
        if here["id_high_water"] > incoming["id_high_water"] and not force:
            rep["refusals"].append(
                "THIS store is ahead (ids to %d) of the bundle (%d). Applying it "
                "would erase work that exists only here. Use --force only if you "
                "have decided to discard it."
                % (here["id_high_water"], incoming["id_high_water"]))
    if rep["refusals"]:
        return rep

    # evidence first: additive, content-addressed, safe to apply before the db
    with tarfile.open(b / BUNDLE_BLOBS, "r:gz") as t:
        members = [m for m in t.getmembers() if m.isfile()]
        # A blob already present is NEVER overwritten. Blobs are content
        # addressed and stored read-only (mode 444) precisely so that they
        # cannot be rewritten - extracting over one fails with EACCES, and
        # that failure is the immutability guarantee working, not a bug to
        # code around. An existing blob is verified instead.
        fresh = []
        for m in members:
            h = Path(m.name).name
            if evidence.blob_path(paths.blobs, h).exists():
                rep["blobs_already_present"] = rep.get("blobs_already_present", 0) + 1
            else:
                fresh.append(m)
        if fresh:
            t.extractall(str(Path(paths.evidence).parent), members=fresh)
    for m in members:
        h = Path(m.name).name
        bp = evidence.blob_path(paths.blobs, h)
        if not bp.exists():
            rep["refusals"].append("blob %s did not land" % h[:12]); continue
        if evidence.hash_file(bp) != h:
            rep["refusals"].append(
                "blob %s does not hash to its own name - the bytes on disk are "
                "not the bytes that were sent" % h[:12]); continue
        rep["blobs_verified"] += 1
    rep["blobs_added"] = len(fresh)
    if rep["refusals"]:
        return rep

    # BEFORE touching the live database: decompress the incoming one to a
    # scratch file and check that every blob it references actually exists on
    # this side. A database naming evidence the receiver does not hold is a
    # store that looks complete and cannot produce its own sources - which is
    # exactly the failure the whole provenance chain exists to prevent.
    canon = Path(paths.db)
    scratch = canon.parent / "_incoming.sqlite3"
    with gzip.open(b / BUNDLE_DB, "rb") as g, open(scratch, "wb") as f:
        shutil.copyfileobj(g, f, 1 << 20)
    ic = sqlite3.connect(str(scratch))
    missing = []
    for (h,) in ic.execute("SELECT content_hash FROM evidence_blob"):
        if not evidence.blob_path(paths.blobs, h).exists():
            missing.append(h)
            if len(missing) >= 25:
                break
    total_ref = ic.execute("SELECT COUNT(*) FROM evidence_blob").fetchone()[0]
    ic.close()
    rep["evidence_referenced"] = total_ref
    if missing:
        scratch.unlink()
        rep["refusals"].append(
            "the incoming database references %d+ blob(s) this store does not "
            "have (e.g. %s). Nothing was changed. Re-export WITHOUT "
            "--canonical-only so the evidence travels with it."
            % (len(missing), ", ".join(h[:12] for h in missing[:3])))
        return rep

    # the old database is moved aside, never removed

    aside = canon.parent / ("superseded-%s.sqlite3" % now_iso().replace(":", ""))
    if canon.exists():
        canon.replace(aside)
        for sfx in ("-wal", "-shm"):
            s = Path(str(canon) + sfx)
            if s.exists():
                s.replace(Path(str(aside) + sfx))
        rep["previous_db_moved_to"] = str(aside)
    scratch.replace(canon)
    c = sqlite3.connect(str(canon))
    rep["integrity_check"] = c.execute("PRAGMA integrity_check").fetchone()[0]
    rep["objects"] = c.execute("SELECT COUNT(*) FROM object").fetchone()[0]
    c.close()
    rep["ok"] = rep["integrity_check"] == "ok"
    return rep
