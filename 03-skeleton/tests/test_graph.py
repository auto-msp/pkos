"""Knowledge graph (SOW 22): entities are derived, not guessed, and re-derivable.

The saturation test matters more than it looks. That branch never fired on the
real corpus, so a missing provenance row in it was invisible - the invariant
passed by luck rather than by construction. This forces it.
"""
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
    print("  [%s] %-54s %s" % ("PASS" if ok else "FAIL", name, detail))
    if not ok:
        FAILED.append(name)


def sb(root, *args):
    env = _env(root)
    return subprocess.run([sys.executable, "-m", "secondbrain"] + list(args),
                          cwd=str(SKEL), env=env, capture_output=True, text=True)


BOOKMARKS = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<DL><p>
    <DT><H3 ADD_DATE="1600000000">Work</H3>
    <DL><p>
        <DT><A HREF="https://github.com/automspai/vault" ADD_DATE="1600000100">Vault repo</A>
        <DT><A HREF="https://github.com/automspai/other" ADD_DATE="1600000200">Other repo</A>
        <DT><A HREF="https://n8n.io/workflows" ADD_DATE="1600000300">n8n workflows</A>
    </DL><p>
</DL><p>"""


def main():
    tmp = Path(tempfile.mkdtemp(prefix="pkos-graph-"))
    root = tmp / "store"; fx = tmp / "fx"
    (fx / "Downloads" / "ProjectAlpha").mkdir(parents=True)
    (fx / "Downloads" / "ProjectBeta").mkdir(parents=True)
    (fx / "Downloads" / "ProjectAlpha" / "notes.md").write_text(
        "Deployment notes. We host the repo on github.com and run n8n.io flows.")
    (fx / "Downloads" / "ProjectAlpha" / "plan.md").write_text(
        "Plan: migrate everything to github.com this quarter.")
    (fx / "Downloads" / "ProjectBeta" / "readme.md").write_text("Unrelated project.")
    bm = fx / "bookmarks.html"; bm.write_text(BOOKMARKS)

    print("KNOWLEDGE GRAPH TEST"); print("=" * 70)
    sb(root, "init")
    sb(root, "ingest", "filesystem", str(fx / "Downloads"))
    sb(root, "ingest", "bookmarks", str(bm))
    sb(root, "rebuild-index", "--quiet")

    r = sb(root, "--json", "graph", "--rebuild")
    d = json.loads(r.stdout)
    check("rebuild succeeds", r.returncode == 0, (r.stderr or "")[:90])
    check("domains derived from parsed URLs, not from text",
          d["domains"] == 2, "domains=%s (github.com, n8n.io)" % d["domains"])
    check("every bookmark linked to its host domain",
          d["edges_hosted_at"] == 3, "edges=%s" % d["edges_hosted_at"])
    check("folders derived from the paths files came from",
          d["folders"] == 2, "folders=%s" % d["folders"])
    check("every file linked to its folder",
          d["edges_stored_in"] == 3, "edges=%s" % d["edges_stored_in"])

    import sqlite3
    c = sqlite3.connect(str(root / "canonical" / "canonical.sqlite3"))
    c.row_factory = sqlite3.Row
    ents = c.execute("SELECT object_id, object_class, title, knowledge_state"
                     " FROM object WHERE knowledge_state='DERIVED'").fetchall()
    check("entities are marked DERIVED, never ORIGINAL",
          len(ents) >= 4 and all(e["knowledge_state"] == "DERIVED" for e in ents),
          "%d entity object(s)" % len(ents))
    named = c.execute("SELECT COUNT(*) FROM provenance p JOIN object o"
                      " ON o.object_id=p.object_id WHERE o.knowledge_state='DERIVED'"
                      "   AND p.transformation_id LIKE 'graph:%'").fetchone()[0]
    check("each entity records the RULE that produced it",
          named >= len(ents), "%d provenance row(s) naming a graph rule" % named)

    # idempotency: rebuilding must not duplicate entities or edges
    before = c.execute("SELECT COUNT(*) FROM object WHERE knowledge_state='DERIVED'").fetchone()[0]
    rel_before = c.execute("SELECT COUNT(*) FROM relationship").fetchone()[0]
    sb(root, "graph", "--rebuild")
    after = c.execute("SELECT COUNT(*) FROM object WHERE knowledge_state='DERIVED'").fetchone()[0]
    rel_after = c.execute("SELECT COUNT(*) FROM relationship").fetchone()[0]
    check("rebuilding is idempotent", before == after and rel_before == rel_after,
          "entities %d->%d, edges %d->%d" % (before, after, rel_before, rel_after))

    # traversal
    r = sb(root, "--json", "graph", "--find", "github")
    d = json.loads(r.stdout)
    check("entity lookup by name works", len(d["entities"]) == 1,
          str([e["title"] for e in d["entities"]]))
    gid = d["entities"][0]["object_id"]
    r = sb(root, "--json", "graph", "--object", gid)
    d = json.loads(r.stdout)
    check("traversal returns the bookmarks pointing at that domain",
          len(d["neighbours"]) == 2, "%d neighbour(s)" % len(d["neighbours"]))

    # ---- forced saturation: the branch that never fires in production -------
    import importlib
    sys.path.insert(0, str(SKEL))
    from secondbrain import graph as g, db as gdb, config as gcfg
    importlib.reload(g)
    g.SATURATION = 0.0                       # every matched term is now "too common"
    env_root = os.environ.get("PKOS_ROOT"); env_der = os.environ.get("PKOS_DERIVED")
    os.environ["PKOS_ROOT"] = str(root); os.environ["PKOS_DERIVED"] = str(root / "derived")
    p = gcfg.Paths(); conn = gdb.connect(p.db)
    st = {k: 0 for k in ("domains", "workspaces", "accounts", "folders",
                         "edges_hosted_at", "edges_belongs_to", "edges_account",
                         "edges_stored_in", "edges_mentions", "entities_with_mentions",
                         "entities_saturated", "entities_no_match",
                         "entities_too_short", "entities_unqueryable")}
    g.build_mentions(conn, p.fts_db, st)
    conn.commit(); conn.close()
    if env_root: os.environ["PKOS_ROOT"] = env_root
    if env_der: os.environ["PKOS_DERIVED"] = env_der
    check("saturated terms produce NO mention edges",
          st["entities_saturated"] > 0 and st["edges_mentions"] == 0,
          "saturated=%d edges=%d" % (st["entities_saturated"], st["edges_mentions"]))

    r = sb(root, "--json", "validate")
    v = json.loads(r.stdout)
    names = {x["check"]: x["status"] for x in v["checks"]}
    check("saturation versions still carry provenance",
          names.get("every_version_has_provenance") == "PASS")
    check("validate passes after the graph build", v["status"] == "PASSED",
          "failed=%d" % v["failed_checks"])

    print("=" * 70)
    if FAILED:
        print("FAILED (%d)" % len(FAILED))
        for f in FAILED: print("  -", f)
        return 1
    print("ALL GRAPH TESTS PASSED")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
