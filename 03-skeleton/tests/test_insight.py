"""Knowledge gaps and meta-knowledge (SOW 73/74 - Phase 27).

The whole value of this phase is that absence gets counted. So the tests are
about absence: a gap that exists must be reported, a gap that does not must
not be invented, and a ratio must never be arithmetically impossible.
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


BOOKMARKS = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<DL><p>
    <DT><A HREF="https://example.com/a" ADD_DATE="1600000100">A</A>
    <DT><A HREF="https://example.org/b" ADD_DATE="1600000200">B</A>
</DL><p>"""


def main():
    tmp = Path(tempfile.mkdtemp(prefix="pkos-insight-"))
    root = tmp / "store"
    fx = tmp / "fx" / "docs"; fx.mkdir(parents=True)
    for i in range(3):
        (fx / ("f%d.md" % i)).write_text("note %d about widgets and pricing" % i)
    bm = tmp / "bm.html"; bm.write_text(BOOKMARKS)

    print("KNOWLEDGE GAPS / META TEST"); print("=" * 78)
    sb(root, "init")
    sb(root, "ingest", "filesystem", str(tmp / "fx"))
    sb(root, "ingest", "bookmarks", str(bm))
    sb(root, "rebuild-index", "--quiet")
    sb(root, "graph", "--rebuild")

    g = json.loads(sb(root, "--json", "gaps").stdout)
    by = {x["gap"]: x for x in g["gaps"]}

    check("unfetched URLs are counted as a gap",
          by.get("urls_never_fetched", {}).get("count") == 2,
          str(by.get("urls_never_fetched", {}).get("count")))
    check("every gap names the action that closes it",
          all(x["action"] for x in g["gaps"]))
    check("every gap is COUNTED, never vague",
          all(isinstance(x["count"], int) and x["count"] > 0 for x in g["gaps"]))
    check("gaps with zero instances are not invented",
          "open_conflicts" not in by and "items_in_dead_letter" not in by,
          str(sorted(by)))
    check("uningested sources are named, not just counted",
          isinstance(by["sources_never_ingested"]["detail"], dict)
          and len(by["sources_never_ingested"]["detail"]) > 5)
    check("high severity sorts above info",
          [x["severity"] for x in g["gaps"]] == sorted(
              [x["severity"] for x in g["gaps"]],
              key=lambda s: {"high": 0, "medium": 1, "info": 2}[s]))

    # empty-body gap must EXCLUDE the classes that are empty by design
    m = json.loads(sb(root, "--json", "meta").stdout)
    check("meta reports scale, states, authority and decay",
          all(k in m for k in ("scale", "by_knowledge_state", "by_authority", "by_decay")))

    pr = m["provenance"]
    check("traceability is a real percentage, never over 100",
          0 <= pr["traceable_pct_of_acquired"] <= 100,
          "%.2f%%" % pr["traceable_pct_of_acquired"])
    check("numerator and denominator cover the SAME population",
          pr["acquired_tracing_to_bytes"] + pr["acquired_untraceable"]
          == pr["acquired_objects"],
          "%d + %d == %d" % (pr["acquired_tracing_to_bytes"],
                             pr["acquired_untraceable"], pr["acquired_objects"]))
    check("derived objects are counted separately, not as failures",
          pr["derived_objects"] > 0, "%d derived" % pr["derived_objects"])

    v = m["voice"]
    check("first-hand vs machine-generated is reported as a ratio",
          0 <= v["first_hand_pct"] <= 100 and 0 <= v["machine_pct"] <= 100)

    # read vs write: honest about its own blind spot
    rw = m["read_vs_write"]
    check("read/write starts at zero and says so",
          rw["distinct_objects_ever_surfaced"] == 0 and rw["inquiries_recorded"] == 0,
          "%d inquiries" % rw["inquiries_recorded"])
    sb(root, "--json", "ask", "widgets", "--limit", "3")
    m2 = json.loads(sb(root, "--json", "meta").stdout)
    rw2 = m2["read_vs_write"]
    check("asking a question makes objects count as READ",
          rw2["distinct_objects_ever_surfaced"] > 0
          and rw2["inquiries_with_ids_logged"] == 1,
          "%d surfaced" % rw2["distinct_objects_ever_surfaced"])
    check("and the percentage is of the whole store",
          0 < rw2["pct_of_store_ever_surfaced"] < 100,
          "%.3f%%" % rw2["pct_of_store_ever_surfaced"])

    # an unanswered agent answer must show up as a gap
    r = sb(root, "--json", "ask", "widgets", "--limit", "2")
    pack = json.loads(r.stdout)
    ids = [e["object_id"] for e in pack["evidence"]]
    sb(root, "--json", "answer", "--model", "m1", "--inquiry", pack["inquiry_id"],
       "--question", "q", "--body", "an answer", "--cite", *ids)
    g2 = {x["gap"]: x for x in json.loads(sb(root, "--json", "gaps").stdout)["gaps"]}
    check("an un-reviewed agent answer is reported as a gap",
          g2.get("answers_awaiting_human_review", {}).get("count") == 1)

    print("=" * 78)
    if FAILED:
        print("FAILED (%d)" % len(FAILED))
        for f in FAILED: print("  -", f)
        return 1
    print("ALL INSIGHT TESTS PASSED")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
