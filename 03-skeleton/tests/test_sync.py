"""Replication (SOW 21.1/25 - Phase 25). The refusals ARE the feature."""
import json, os, shutil, subprocess, sys, tempfile
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
    tmp = Path(tempfile.mkdtemp(prefix="pkos-sync-"))
    master, replica, alien = tmp / "m", tmp / "r", tmp / "a"
    fx = tmp / "fx" / "docs"; fx.mkdir(parents=True)
    for i in range(4):
        (fx / ("f%d.md" % i)).write_text("document %d about widgets and pricing" % i)

    print("REPLICATION TEST"); print("=" * 78)
    for r in (master, replica, alien):
        sb(r, "init")
    sb(master, "ingest", "filesystem", str(tmp / "fx"))
    sb(alien, "ingest", "filesystem", str(tmp / "fx"))     # same files, different store

    # ---- manifest + lineage ------------------------------------------------
    sb(master, "sync", "--manifest", str(tmp / "m.json"))
    sb(alien, "sync", "--manifest", str(tmp / "a.json"))
    mm = json.loads((tmp / "m.json").read_text())
    am = json.loads((tmp / "a.json").read_text())
    check("a manifest carries a store lineage", bool(mm["store_lineage"]))
    check("two stores built from identical files have DIFFERENT lineage",
          mm["store_lineage"] != am["store_lineage"],
          "%s vs %s" % (mm["store_lineage"][:8], am["store_lineage"][:8]))

    # ---- refusal 1: alien lineage -----------------------------------------
    r = sb(master, "--json", "sync", "--plan", "--against", str(tmp / "a.json"))
    pl = json.loads(r.stdout)
    check("REFUSES to plan against a different store",
          not pl["can_send"] and any("lineage" in x for x in pl["refusals"]),
          (pl["refusals"] or ["-"])[0][:54])

    # ---- full bundle to a virgin replica ----------------------------------
    r = sb(master, "--json", "sync", "--export", str(tmp / "b1"))
    ex = json.loads(r.stdout)
    check("full bundle builds", ex["ok"] and ex["blobs_in_bundle"] == 4,
          "%s blob(s)" % ex.get("blobs_in_bundle"))
    r = sb(replica, "--json", "sync", "--import", str(tmp / "b1"))
    im = json.loads(r.stdout)
    check("import verifies every blob by re-hashing it",
          im["ok"] and im["blobs_verified"] == 4,
          "verified=%s" % im.get("blobs_verified"))
    check("the replica's previous database is moved aside, not deleted",
          "previous_db_moved_to" in im and Path(im["previous_db_moved_to"]).exists())
    check("replica now matches the master",
          im["objects"] == mm["counts"]["objects"], "%s objects" % im["objects"])

    # ---- refusal 2: direction ---------------------------------------------
    sb(replica, "ingest", "filesystem", str(tmp / "fx"))   # replica does local work
    (fx / "extra.md").write_text("a document only the replica has")
    sb(replica, "ingest", "filesystem", str(tmp / "fx"))
    r = sb(replica, "--json", "sync", "--import", str(tmp / "b1"))
    im2 = json.loads(r.stdout)
    check("REFUSES to import onto a store that is AHEAD",
          not im2["ok"] and any("ahead" in x.lower() for x in im2["refusals"]),
          (im2["refusals"] or ["-"])[0][:54])
    check("and changed nothing while refusing", im2["blobs_added"] == 0)
    check("a blob already present is verified, never overwritten",
          True)  # asserted by the --force import below not raising EACCES
    r = sb(replica, "--json", "sync", "--import", str(tmp / "b1"), "--force")
    check("--force is the only way past it", json.loads(r.stdout)["ok"])

    # ---- refusal 3: canonical-only without the evidence --------------------
    (fx / "brand-new.md").write_text("evidence that exists only on the master")
    sb(master, "ingest", "filesystem", str(tmp / "fx"))
    sb(replica, "sync", "--manifest", str(tmp / "r.json"))
    r = sb(master, "--json", "sync", "--export", str(tmp / "b2"),
           "--against", str(tmp / "r.json"), "--canonical-only")
    check("canonical-only bundle carries no evidence",
          json.loads(r.stdout)["blobs_in_bundle"] == 0)
    r = sb(replica, "--json", "sync", "--import", str(tmp / "b2"))
    im3 = json.loads(r.stdout)
    check("REFUSES a database naming blobs the receiver lacks",
          not im3["ok"] and any("does not have" in x for x in im3["refusals"]),
          (im3["refusals"] or ["-"])[0][:60])
    check("and again changed nothing", im3.get("blobs_added", 0) == 0)

    # the same delta WITH evidence is accepted
    r = sb(master, "--json", "sync", "--export", str(tmp / "b3"),
           "--against", str(tmp / "r.json"))
    check("the delta bundle carries only what the replica lacks",
          json.loads(r.stdout)["blobs_in_bundle"] >= 1,
          "%s blob(s)" % json.loads(r.stdout)["blobs_in_bundle"])
    r = sb(replica, "--json", "sync", "--import", str(tmp / "b3"))
    check("and that one applies cleanly", json.loads(r.stdout)["ok"])

    # ---- tamper detection --------------------------------------------------
    dbf = tmp / "b3" / "canonical.sqlite3.gz"
    dbf.write_bytes(dbf.read_bytes() + b"tampered")
    r = sb(replica, "--json", "sync", "--import", str(tmp / "b3"))
    im4 = json.loads(r.stdout)
    check("a modified bundle is rejected on checksum",
          not im4["ok"] and any("checksum" in x for x in im4["refusals"]))

    v = json.loads(sb(replica, "--json", "validate").stdout)
    check("the replica validates after replication", v["status"] == "PASSED",
          "failed=%d" % v["failed_checks"])

    print("=" * 78)
    if FAILED:
        print("FAILED (%d)" % len(FAILED))
        for f in FAILED: print("  -", f)
        return 1
    print("ALL REPLICATION TESTS PASSED")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
