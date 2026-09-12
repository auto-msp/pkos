"""End-to-end smoke test. Runs the real CLI against real fixtures and asserts
on measured numbers, not on the absence of exceptions (SOW 43)."""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
FAILURES = []


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

def sb(root, *args, expect=0):
    r = subprocess.run([sys.executable, "-m", "secondbrain", "--root", str(root)] + list(args),
                       cwd=str(PKG), capture_output=True, text=True,
                       env=_env(root))
    if r.returncode != expect:
        FAILURES.append("exit %d (expected %d) for %s\n%s\n%s"
                        % (r.returncode, expect, " ".join(args), r.stdout[-1500:], r.stderr[-1500:]))
    return r


def check(name, cond, detail=""):
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))
    if not cond:
        FAILURES.append("%s %s" % (name, detail))


def make_fixtures(d):
    docs = d / "docs"; (docs / "sub").mkdir(parents=True)
    (docs / "notes.md").write_text("# Kubernetes notes\nWe chose Postgres over MySQL for the ledger.\n")
    (docs / "plan.txt").write_text("Second brain plan: preserve provenance and evidence.\n")
    (docs / "data.csv").write_text("a,b\n1,2\n")
    (docs / "sub" / "dup.md").write_text("# Kubernetes notes\nWe chose Postgres over MySQL for the ledger.\n")  # exact dup
    (docs / "app.py").write_text("print('code - SOW 75 excludes this')\n")
    (docs / "bundle.min.js").write_text("var x=1\n")
    nm = docs / "node_modules" / "pkg"; nm.mkdir(parents=True)
    (nm / "index.js").write_text("module.exports=1\n")

    bm = d / "bookmarks.html"
    bm.write_text("""<!DOCTYPE NETSCAPE-Bookmark-file-1>
<DL><p>
    <DT><H3 ADD_DATE="1500000000">Research</H3>
    <DL><p>
        <DT><A HREF="https://www.example.com/index.html?utm_source=news&b=2" ADD_DATE="1500000100">Example Article</A>
        <DT><A HREF="https://github.com/anthropics/anthropic-sdk-python" ADD_DATE="1600000000">Anthropic SDK</A>
        <DT><A HREF="http://EXAMPLE.com/?b=2" ADD_DATE="1700000000">Same resource, different form</A>
    </DL><p>
    <DT><H3 ADD_DATE="1650000000">Infra</H3>
    <DL><p>
        <DT><A HREF="https://qdrant.tech/documentation/" ADD_DATE="1650000100">Qdrant docs</A>
        <DT><A HREF="not a url at all" ADD_DATE="1650000200">Broken</A>
    </DL><p>
</DL><p>""")
    srv = d / "servers"; srv.mkdir()
    # Ship the audit fixture with the tests. A test that depends on a file
    # someone left in /tmp is not a test - it passes or fails by accident.
    here = Path(__file__).resolve().parent / "fixtures" / "server-audit.json"
    if here.exists():
        shutil.copy(str(here), str(srv / "container-audit.json"))
    return docs, bm, srv


def main():
    tmp = Path(tempfile.mkdtemp(prefix="pkos-test-"))
    root = tmp / "store"; fx = tmp / "fx"; fx.mkdir()
    docs, bm, srv = make_fixtures(fx)
    print("PKOS SMOKE TEST"); print("=" * 62)

    print("\n1. init")
    sb(root, "init")
    check("three planes created",
          all((root / p).exists() for p in ("evidence/blobs", "canonical", "derived")))
    check("derived plane self-documents as rebuildable",
          (root / "derived/REBUILDABLE.txt").exists())
    check("evidence plane self-documents as immutable",
          (root / "evidence/IMMUTABLE.txt").exists())

    print("\n2. ingest filesystem (SOW 75 include/exclude)")
    r = sb(root, "--json", "ingest", "filesystem", str(docs))
    j = json.loads(r.stdout)
    check("discovered all files incl. excluded", j["discovered"] >= 6, "n=%d" % j["discovered"])
    check("created 4 knowledge objects", j["created"] == 4, "created=%d" % j["created"])
    check("code excluded but COUNTED, not dropped",
          j["adapter_stats"]["excluded_files"] >= 2,
          "excluded=%d" % j["adapter_stats"]["excluded_files"])
    check("node_modules pruned", "node_modules" not in r.stdout)

    print("\n3. idempotency (SOW 39) - re-run must create nothing")
    r2 = sb(root, "--json", "ingest", "filesystem", str(docs))
    j2 = json.loads(r2.stdout)
    check("re-ingest creates 0 new objects", j2["created"] == 0, "created=%d" % j2["created"])
    check("re-ingest reports unchanged", j2["unchanged"] >= 4, "unchanged=%d" % j2["unchanged"])

    print("\n4. versioning (SOW 9) - changed content -> new version, SAME object id")
    (docs / "plan.txt").write_text("Second brain plan: REVISED. Evidence first.\n")
    time.sleep(0.01)
    r3 = sb(root, "--json", "ingest", "filesystem", str(docs))
    j3 = json.loads(r3.stdout)
    check("changed file versioned not recreated",
          j3["versioned"] == 1 and j3["created"] == 0,
          "versioned=%d created=%d" % (j3["versioned"], j3["created"]))

    print("\n5. ingest bookmarks (SOW 53-64)")
    r = sb(root, "--json", "ingest", "bookmarks", str(bm), "--browser", "chrome", expect=1)
    j = json.loads(r.stdout)
    check("4 valid bookmarks acquired", j["acquired"] == 4, "acquired=%d" % j["acquired"])
    check("1 unparseable url isolated, batch survived", j["failed"] == 1, "failed=%d" % j["failed"])
    check("http/https variants kept distinct (SOW 55, not over-normalized)",
          j["adapter_stats"]["new_urls"] == 4,
          "new=%d repeat=%d" % (j["adapter_stats"]["new_urls"], j["adapter_stats"]["repeat_urls"]))
    check("ADD_DATE preserved on every valid bookmark",
          j["adapter_stats"]["with_add_date"] == 4,
          "with_add_date=%d" % j["adapter_stats"]["with_add_date"])

    print("\n6. dead-letter queue (SOW 40)")
    r = sb(root, "--json", "audit", "--dead-letter")
    check("failure captured, not lost", len(json.loads(r.stdout)) == 1)

    print("\n7. ingest server audit (real output of pkos-server-audit.sh)")
    if (srv / "container-audit.json").exists():
        r = sb(root, "--json", "ingest", "server-audit", str(srv))
        check("server audit ingested", json.loads(r.stdout)["created"] == 1)
        r = sb(root, "--json", "servers")
        s = json.loads(r.stdout)[0]
        check("server matrix has real host + error count",
              s["host"] and s["error_count"] is not None,
              "host=%s errors=%s" % (s["host"], s["error_count"]))
    else:
        check("server audit fixture present", False,
              "(tests/fixtures/server-audit.json missing)")

    print("\n8. validate (SOW 43/125 invariants)")
    r = sb(root, "--json", "validate", "--deep")
    v = json.loads(r.stdout)
    check("all invariants pass", v["status"] == "PASSED",
          "failed=%d" % v["failed_checks"])
    check("evidence blobs verified by re-hash",
          v["integrity"]["corrupt"] == 0 and v["integrity"]["missing"] == 0,
          "ok=%d" % v["integrity"]["ok"])
    check("provenance row per version", v["counts"]["provenance"] == v["counts"]["versions"],
          "%d prov / %d ver" % (v["counts"]["provenance"], v["counts"]["versions"]))

    print("\n9. duplicates (SOW 19) - link, never delete")
    r = sb(root, "--json", "duplicates", "--link")
    d = json.loads(r.stdout)
    check("exact duplicate detected", d["exact_groups"] >= 1, "groups=%d" % d["exact_groups"])
    check("url scheme-variants linked, not merged", d["url_variant_groups"] == 1,
          "variant_groups=%d" % d["url_variant_groups"])
    r = sb(root, "--json", "validate")
    check("aliases still exist after linking",
          json.loads(r.stdout)["status"] == "PASSED")

    print("\n10. derived plane is rebuildable (SOW 25/88)")
    sb(root, "rebuild-index")
    r = sb(root, "--json", "search", "Postgres ledger")
    check("search finds content", len(json.loads(r.stdout)["results"]) >= 1)
    shutil.rmtree(root / "derived")           # destroy the whole derived plane
    sb(root, "rebuild-index")
    r = sb(root, "--json", "search", "Postgres ledger")
    check("full recovery after deleting derived/",
          len(json.loads(r.stdout)["results"]) >= 1)

    # An index rebuild must survive being killed. It commits in batches and
    # records its own progress, and it builds into doc_new so the PREVIOUS
    # index stays queryable the whole time - rebuilding is not a reason for
    # search to go dark.
    import sqlite3 as _sq
    fts = root / "derived" / "fts.sqlite3"
    st = dict(_sq.connect(str(fts)).execute("SELECT k,v FROM build_state"))
    check("rebuild records a finished state",
          st.get("status") == "FRESH" and int(st.get("done", 0)) > 0,
          "status=%s done=%s" % (st.get("status"), st.get("done")))

    f = _sq.connect(str(fts))                 # simulate a killed rebuild
    f.execute("CREATE VIRTUAL TABLE IF NOT EXISTS doc_new USING fts5(object_id)")
    f.executemany("INSERT OR REPLACE INTO build_state(k,v) VALUES(?,?)",
                  [("status", "BUILDING"), ("total", "999999"), ("last", "KB-99999999")])
    f.commit(); f.close()
    r = sb(root, "--json", "search", "Postgres ledger")
    check("previous index still answers during an unfinished rebuild",
          len(json.loads(r.stdout)["results"]) >= 1)
    sb(root, "rebuild-index")
    r = sb(root, "--json", "search", "Postgres ledger")
    check("stale build state is discarded, not resumed against wrong data",
          len(json.loads(r.stdout)["results"]) >= 1)

    # FTS5 has its own grammar: a hyphen is an operator and a colon means
    # "column". Someone searching their own notes types words, not a query
    # language, and "sign-in x_y" must not come back as `no such column: in`.
    r = sb(root, "--json", "search", "Postgres-ledger")
    check("punctuation in a plain-language query does not error",
          r.returncode == 0 and r.stdout.strip().startswith("{"),
          (r.stderr or "").strip()[:70])
    r = sb(root, "--json", "search", "Postgres AND ledger")
    check("deliberate FTS operators still work", r.returncode == 0)

    print("\n11. history (SOW 60-62)")
    r = sb(root, "--json", "history")
    h = json.loads(r.stdout)
    check("temporal span computed", h["first_seen"] and h["last_seen"],
          "%s -> %s" % (h["first_seen"], h["last_seen"]))
    check("year buckets built", len(h["by_year"]) >= 2, str(h["by_year"]))

    print("\n12. portability mirror (SOW 7/91/124)")
    r = sb(root, "--json", "export")
    m = json.loads(r.stdout)
    check("every canonical table mirrored to JSONL", len(m["tables"]) == 26)
    check("mirror is non-empty", m["tables"]["object"]["rows"] > 0)

    print("\n13. backup + restore drill (SOW 93)")
    r = sb(root, "--json", "backup", "--dest", str(tmp / "bk"), "--include-evidence")
    bk = json.loads(r.stdout)
    check("backup written", bk["ok"])
    check("a fresh backup is a hypothesis, not a backup",
          bk["manifest"]["proven"] is False)
    r = sb(root, "--json", "backup", "--drill", bk["path"])
    d = json.loads(r.stdout)
    check("a restore drill PROVES it", d["ok"],
          "%d step(s)" % len(d["steps"]))
    r = sb(root, "--json", "backup", "--status", "--dest", str(tmp / "bk"))
    st = json.loads(r.stdout)
    check("recovery position reports last PROVEN, not last written",
          st["tiers"]["primary"]["last_proven"] is not None)

    print("\n14. destructive gate (SOW 97) - refuses without --dry-run")
    r = sb(root, "cleanup", expect=2)
    check("cleanup refuses to delete", "REFUSED" in r.stdout)

    # Fragments from processes killed mid-write. One is provably redundant
    # (the blob it was becoming exists and re-hashes); one is not (its final
    # blob never landed, so it may be the only copy of something acquired).
    # The gate must remove the first and keep the second.
    import secondbrain.evidence as _ev
    conn2 = __import__("sqlite3").connect(str(root / "canonical" / "canonical.sqlite3"))
    h = conn2.execute("SELECT content_hash FROM evidence_blob LIMIT 1").fetchone()[0]
    conn2.close()
    good = _ev.blob_path(root / "evidence" / "blobs", h).with_suffix(".tmp-999")
    good.write_bytes(b"partial")
    lone = _ev.blob_path(root / "evidence" / "blobs", "b" * 64).with_suffix(".tmp-1000")
    lone.parent.mkdir(parents=True, exist_ok=True)
    lone.write_bytes(b"only copy")
    r = sb(root, "--json", "prune-writes")
    d = json.loads(r.stdout)
    check("interrupted writes are found and triaged",
          d["found"] == 2 and d["prunable"] == 1 and d["needs_review"] == 1,
          "found=%d prunable=%d review=%d" % (d["found"], d["prunable"], d["needs_review"]))
    check("dry run is the default - nothing deleted",
          good.exists() and lone.exists())
    sb(root, "prune-writes", "--execute")
    check("only the provably redundant fragment is removed", not good.exists())
    check("a fragment that may be the only copy is KEPT", lone.exists())
    lone.unlink()

    print("\n15. honest NOT_IMPLEMENTED (SOW 107) - non-zero exit, no fake success")
    # `graph` used to be on this list. Phase 22 implemented it, so the honest
    # thing is to move it OUT rather than leave a test asserting a limitation
    # that no longer exists - a stale test is a lie with a passing status.
    # `sync` left this list when Phase 25 implemented it. Same rule as `graph`
    # before it: a test asserting a limitation that no longer exists is a lie
    # that reports success.
    for c in ("storage", "discover"):
        r = sb(root, c, expect=3)
        check("%s declares NOT_IMPLEMENTED" % c, "NOT_IMPLEMENTED" in r.stdout)
    r = sb(root, "--json", "graph", "--rebuild")
    check("graph is implemented and builds", r.returncode == 0,
          (r.stderr or "")[:70])
    g = json.loads(r.stdout)
    check("graph derives entities from structured data",
          g["domains"] + g["folders"] > 0,
          "domains=%d folders=%d" % (g["domains"], g["folders"]))
    r = sb(root, "--json", "sync", "--manifest", str(root / "m.json"))
    check("sync is implemented and emits a manifest with a lineage",
          r.returncode == 0 and json.loads(r.stdout).get("lineage"),
          (r.stderr or "")[:60])

    print("\n16. status dashboard (SOW 114)")
    r = sb(root, "--json", "status")
    st = json.loads(r.stdout)
    check("dashboard reports real counts",
          st["knowledge_objects"] > 0 and st["urls"] == 4 and st["evidence_blobs"] > 0,
          "objects=%d urls=%d blobs=%d" % (st["knowledge_objects"], st["urls"], st["evidence_blobs"]))

    print("\n" + "=" * 62)
    if FAILURES:
        print("FAILED (%d)" % len(FAILURES))
        for f in FAILURES[:12]: print("  - %s" % f)
        return 1
    print("ALL SMOKE TESTS PASSED")
    print("store: %s" % root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
