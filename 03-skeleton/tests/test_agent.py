"""The agent boundary (SOW 3, 17 - Phase 24).

The properties worth testing are the ones that are easy to lose:
  * `ask` must never answer. The moment retrieval starts writing prose, the
    line between what the store knows and what a model said is gone.
  * a model's answer must never be retrievable as though the user said it.
  * a graph rebuild must never quietly overturn a merge a human confirmed.
"""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKEL = HERE.parent
FAILED = []


def check(name, ok, detail=""):
    print("  [%s] %-58s %s" % ("PASS" if ok else "FAIL", name, detail))
    if not ok:
        FAILED.append(name)


def sb(root, *args):
    env = dict(os.environ, PKOS_ROOT=str(root), PKOS_DERIVED=str(root / "derived"),
               PYTHONPATH=str(SKEL))
    return subprocess.run([sys.executable, "-m", "secondbrain"] + list(args),
                          cwd=str(SKEL), env=env, capture_output=True, text=True)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="pkos-agent-"))
    root = tmp / "store"
    d = tmp / "fx" / "Acme" / "docs"; d.mkdir(parents=True)
    (d / "brief.md").write_text("Acme Corp sells widgets to hospitals in Ohio.")
    (d / "pricing.md").write_text("Acme widget pricing starts at 40 dollars per unit.")
    (d / "roadmap.md").write_text("Acme roadmap: expand widget distribution nationally.")
    e = tmp / "fx" / "Zeta" / "docs"; e.mkdir(parents=True)
    (e / "unrelated.md").write_text("Zeta handles catering logistics for events.")
    print("AGENT BOUNDARY TEST"); print("=" * 78)
    sb(root, "init")
    ing = sb(root, "--json", "ingest", "filesystem", str(tmp / "fx"))
    try:
        n = json.loads(ing.stdout)["created"]
    except Exception:
        n = -1
    check("fixture ingested", n == 4, "created=%s %s" % (n, (ing.stderr or "")[:60]))
    sb(root, "rebuild-index", "--quiet")
    sb(root, "graph", "--rebuild")

    # ---- ask assembles, and refuses to answer ---------------------------
    r = sb(root, "--json", "ask", "what does Acme sell", "--limit", "3")
    pack = json.loads(r.stdout)
    check("ask returns evidence", len(pack["evidence"]) > 0,
          "%d item(s)" % len(pack["evidence"]))
    check("ask produces NO answer field of any kind",
          not any(k in pack for k in ("answer", "summary", "conclusion", "response")),
          str(sorted(pack.keys())))
    check("every item says whether it traces to bytes",
          all("traceable_to_bytes" in e for e in pack["evidence"]))
    g = pack["coverage_gaps"]
    check("ask states what the store CANNOT answer from",
          bool(g["sources_declared_but_absent"]) and "ranking_signals_off" in g,
          "%d source(s) declared but absent" % len(g["sources_declared_but_absent"]))
    check("ask instructs the agent not to fill gaps from general knowledge",
          "do not fill the gap" in pack["instruction_to_agent"].lower())

    # ---- merge requires a human ----------------------------------------
    ents = json.loads(sb(root, "--json", "graph", "--find", "Acme").stdout)["entities"]
    check("an entity exists to merge", len(ents) >= 1, str([e["title"] for e in ents]))
    eid = ents[0]["object_id"]
    other = json.loads(sb(root, "--json", "graph", "--top", "--limit", "5").stdout)["top"]
    alias = next((o["object_id"] for o in other if o["object_id"] != eid), None)
    r = sb(root, "graph", "--merge", eid, alias)
    check("merge REFUSED without --confirmed-by",
          r.returncode == 2 and "judgement" in r.stdout.lower(), r.stdout.strip()[:60])
    r = sb(root, "--json", "graph", "--merge", eid, alias,
           "--confirmed-by", "human:tester", "--reason", "same thing")
    check("merge succeeds when a human is named", r.returncode == 0)

    import sqlite3
    c = sqlite3.connect(str(root / "canonical" / "canonical.sqlite3"))
    c.row_factory = sqlite3.Row
    dl = c.execute("SELECT detected_by, evidence FROM duplicate_link"
                   " WHERE dedup_kind='semantic'").fetchone()
    check("the decision records WHO made it", dl and dl["detected_by"] == "human:tester",
          dl["detected_by"] if dl else "none")
    a = c.execute("SELECT is_duplicate_of, decay_status FROM object WHERE object_id=?",
                  (alias,)).fetchone()
    check("the alias is linked and superseded, NOT deleted",
          a and a["is_duplicate_of"] == eid and a["decay_status"] == "SUPERSEDED",
          "%s/%s" % (a["is_duplicate_of"], a["decay_status"]) if a else "gone")

    # the bug: a rebuild used to revive merged aliases and undo the merge
    sb(root, "graph", "--rebuild")
    a2 = c.execute("SELECT is_duplicate_of, decay_status FROM object WHERE object_id=?",
                   (alias,)).fetchone()
    check("a graph rebuild does NOT overturn the human's merge",
          a2["is_duplicate_of"] == eid and a2["decay_status"] == "SUPERSEDED",
          "%s/%s" % (a2["is_duplicate_of"], a2["decay_status"]))

    # ---- an answer is attributed, quarantined, and promotable -----------
    ids = [e["object_id"] for e in pack["evidence"][:2]]
    r = sb(root, "--json", "answer", "--model", "test-model-1",
           "--inquiry", pack["inquiry_id"], "--question", "what does Acme sell",
           "--body", "Acme sells widgets to hospitals.", "--cite", *ids)
    ans = json.loads(r.stdout)["object_id"]
    o = c.execute("SELECT knowledge_state, authority, license FROM object"
                  " WHERE object_id=?", (ans,)).fetchone()
    check("a model's answer is SYNTHESIZED, never ORIGINAL",
          o["knowledge_state"] == "SYNTHESIZED", o["knowledge_state"])
    check("and attributed to the model, not the user",
          o["authority"] == "AI-GENERATED", o["authority"])
    v = c.execute("SELECT changed_by, validation_status FROM object_version"
                  " WHERE object_id=? ORDER BY version_num DESC LIMIT 1", (ans,)).fetchone()
    check("it arrives requiring human review",
          v["validation_status"] == "REQUIRES_HUMAN_REVIEW" and "test-model-1" in v["changed_by"],
          "%s by %s" % (v["validation_status"], v["changed_by"]))
    n = c.execute("SELECT COUNT(*) FROM relationship WHERE source_object=?"
                  "  AND relationship_type='DERIVED_FROM'", (ans,)).fetchone()[0]
    check("it is linked to every source it rests on", n == len(ids), "%d link(s)" % n)

    r = sb(root, "cite", ans)
    check("cite an answer: complete VIA PARENTS, not falsely 'incomplete'",
          r.returncode == 0 and "VIA" in r.stdout, r.stdout.strip().splitlines()[-1][:60])
    r = sb(root, "cite", ids[0])
    check("cite a source: complete, down to the blob",
          r.returncode == 0 and "raw bytes" in r.stdout)

    r = sb(root, "--json", "validate-answer", ans, "--accept", "--note", "checked")
    check("only a human promotes it to HUMAN_VALIDATED",
          json.loads(r.stdout)["knowledge_state"] == "HUMAN_VALIDATED")
    vs = c.execute("SELECT COUNT(*) FROM object_version WHERE object_id=?", (ans,)).fetchone()[0]
    check("the promotion is a new version, not an edit in place", vs == 2, "%d versions" % vs)

    v = json.loads(sb(root, "--json", "validate").stdout)
    check("validate passes with agent output in the store", v["status"] == "PASSED",
          "failed=%d" % v["failed_checks"])

    print("=" * 78)
    if FAILED:
        print("FAILED (%d)" % len(FAILED))
        for f in FAILED: print("  -", f)
        return 1
    print("ALL AGENT BOUNDARY TESTS PASSED")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
