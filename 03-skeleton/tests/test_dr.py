"""Backup and DR (SOW 26/93 - Phase 26).

The property under test is not "a backup was written". It is that the system
refuses to call a backup good until a restore has proved it, and that it says
out loud what it has NOT proved.
"""
import json, os, shutil, sqlite3, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKEL = HERE.parent
FAILED = []


def _env(root):
    """A hermetic child environment.

    The suite used to pass env={**os.environ, ...}, which inherits whatever
    PKOS_ROOT / PKOS_DERIVED the operator has exported - and the runbook tells
    you to export both. The result: every test store's derived plane was
    silently redirected to the REAL store's derived directory, so tests that
    assert on root/derived failed for reasons that had nothing to do with the
    code. A test suite that only passes in a shell you have not configured is
    not a test suite. Scrub the ambient PKOS_* and pin derived to this store.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("PKOS_")}
    env["PYTHONPATH"] = str(PKG if "PKG" in globals() else SKEL)
    env["PKOS_ROOT"] = str(root)
    env["PKOS_DERIVED"] = str(Path(root) / "derived")
    return env

def check(name, ok, detail=""):
    print("  [%s] %-58s %s" % ("PASS" if ok else "FAIL", name, detail))
    if not ok:
        FAILED.append(name)


def sb(root, *args):
    env = _env(root)
    return subprocess.run([sys.executable, "-m", "secondbrain"] + list(args),
                          cwd=str(SKEL), env=env, capture_output=True, text=True)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="pkos-dr-"))
    root, bk = tmp / "store", tmp / "backups"
    fx = tmp / "fx" / "docs"; fx.mkdir(parents=True)
    for i in range(4):
        (fx / ("f%d.md" % i)).write_text("document %d about widgets and pricing" % i)

    print("BACKUP / DR TEST"); print("=" * 78)
    sb(root, "init")
    sb(root, "ingest", "filesystem", str(tmp / "fx"))

    # ---- create -----------------------------------------------------------
    r = sb(root, "--json", "backup", "--dest", str(bk))
    c1 = json.loads(r.stdout)
    check("backup written", c1["ok"], c1.get("error", ""))
    man = c1["manifest"]
    check("a fresh backup is NOT claimed to be good", man["proven"] is False,
          "proven=%s" % man["proven"])
    check("it says so in the manifest itself", "hypothesis" in man["note"].lower())

    bdir = Path(c1["path"])
    check("the database is vacuumed, not copied live "
          "(no -wal/-shm alongside it)",
          not (bdir / "canonical" / "canonical.sqlite3-wal").exists()
          and not (bdir / "canonical" / "canonical.sqlite3-shm").exists())
    dbc = sqlite3.connect(str(bdir / "canonical" / "canonical.sqlite3"))
    check("and it is internally consistent",
          dbc.execute("PRAGMA integrity_check").fetchone()[0] == "ok")
    dbc.close()

    # ---- drill: the evidence-less case must NOT claim the blobs are fine ---
    r = sb(root, "--json", "backup", "--drill", str(bdir))
    d1 = json.loads(r.stdout)
    check("drill on a database-only backup passes", d1["ok"])
    blob_step = [s for s in d1["steps"] if "re-hashed" in s["step"]][0]
    check("but the blob step is UNPROVEN, not a false pass",
          blob_step["ok"] is None and "unproven" in blob_step["detail"],
          str(blob_step["ok"]))
    man2 = json.loads((bdir / "BACKUP.json").read_text())
    check("a passed drill marks the manifest proven, with a date",
          man2["proven"] is True and man2.get("last_proven_at"))

    # ---- drill with evidence ----------------------------------------------
    r = sb(root, "--json", "backup", "--dest", str(bk), "--tier", "secondary",
           "--include-evidence")
    b2 = Path(json.loads(r.stdout)["path"])
    r = sb(root, "--json", "backup", "--drill", str(b2))
    d2 = json.loads(r.stdout)
    bs = [s for s in d2["steps"] if "re-hashed" in s["step"]][0]
    check("with evidence, every blob is actually re-hashed",
          d2["ok"] and bs["ok"] is True and "corrupt=0" in bs["detail"],
          bs["detail"])

    # ---- two backups in the same second must not collide -------------------
    # This was a real bug found by running the suite twice on a fast machine:
    # the directory name is stamped to whole seconds, the old code took an
    # existing directory with exist_ok=True, and the second run rewrote the
    # first backup's JSONL mirror before failing on the database file. A
    # backup that damages the previous backup is the worst failure this
    # subsystem has (12.5), so it is pinned here rather than left to timing.
    burst = [json.loads(sb(root, "--json", "backup", "--dest", str(bk)).stdout or "{}")
             for _ in range(3)]
    check("three backups fired back-to-back all succeed",
          all(b.get("ok") for b in burst),
          "; ".join(str(b.get("error"))[:60] for b in burst if not b.get("ok")))
    paths = [b.get("path") for b in burst if b.get("ok")]
    check("each got its own directory", len(set(paths)) == len(paths),
          "%d dirs for %d backups" % (len(set(paths)), len(paths)))
    check("every one of them still has its own manifest and database",
          all((Path(x) / "canonical" / "canonical.sqlite3").exists()
              and (Path(x) / "BACKUP.json").exists() for x in paths))

    # ---- a damaged backup must fail the drill ------------------------------
    b3 = Path(json.loads(sb(root, "--json", "backup", "--dest", str(bk)).stdout)["path"])
    dbf = b3 / "canonical" / "canonical.sqlite3"
    raw = bytearray(dbf.read_bytes())
    for i in range(4096, min(len(raw), 65536)):      # corrupt the page data
        raw[i] ^= 0xFF
    dbf.write_bytes(bytes(raw))
    r = sb(root, "--json", "backup", "--drill", str(b3))
    d3 = json.loads(r.stdout)
    check("a corrupted backup FAILS its drill", not d3["ok"],
          "verdict ok=%s" % d3["ok"])
    check("and is never marked proven",
          json.loads((b3 / "BACKUP.json").read_text())["proven"] is False)
    shutil.rmtree(b3)

    # ---- recovery point ----------------------------------------------------
    (fx / "new-work.md").write_text("work done after the backup was taken")
    sb(root, "ingest", "filesystem", str(tmp / "fx"))
    r = sb(root, "--json", "backup", "--drill", str(b2))
    d4 = json.loads(r.stdout)
    rp = [s for s in d4["steps"] if s["step"] == "recovery point"][0]
    check("the drill states what restoring would LOSE",
          "lose 1 object" in rp["detail"], rp["detail"])

    # ---- status ------------------------------------------------------------
    r = sb(root, "--json", "backup", "--status", "--dest", str(bk))
    st = json.loads(r.stdout)
    check("status reports per tier", set(st["tiers"]) >= {"primary", "secondary", "offsite"})
    check("status warns that there is no off-site copy",
          any("offsite" in w for w in st["warnings"]),
          "; ".join(st["warnings"])[:70])
    check("status warns when a tier holds no evidence",
          any("bytes it cites would not" in w for w in st["warnings"]))
    check("last_proven is reported, not just last_created",
          st["tiers"]["secondary"]["last_proven"] is not None)

    # a store with backups none of which are proven must say so
    fresh = tmp / "s2"; fbk = tmp / "b2"
    sb(fresh, "init"); sb(fresh, "ingest", "filesystem", str(tmp / "fx"))
    sb(fresh, "backup", "--dest", str(fbk))
    st2 = json.loads(sb(fresh, "--json", "backup", "--status", "--dest", str(fbk)).stdout)
    check("an untested backup is called a hypothesis, loudly",
          any("hypothesis" in w for w in st2["warnings"]),
          "; ".join(st2["warnings"])[:70])

    print("=" * 78)
    if FAILED:
        print("FAILED (%d)" % len(FAILED))
        for f in FAILED: print("  -", f)
        return 1
    print("ALL BACKUP/DR TESTS PASSED")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
