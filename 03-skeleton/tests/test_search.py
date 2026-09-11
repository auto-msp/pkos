"""Hybrid retrieval (SOW 71/72, Phase 23).

The claim being tested is deliberately small: this is pseudo-relevance
feedback, not an embedding model. The test proves the thing that actually
matters about it - a document containing NONE of the query's words can still be
found, because the corpus itself says those words travel together.
"""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKEL = HERE.parent
FAILED = []


def check(name, ok, detail=""):
    print("  [%s] %-56s %s" % ("PASS" if ok else "FAIL", name, detail))
    if not ok:
        FAILED.append(name)


def sb(root, *args):
    env = dict(os.environ, PKOS_ROOT=str(root), PKOS_DERIVED=str(root / "derived"),
               PYTHONPATH=str(SKEL))
    return subprocess.run([sys.executable, "-m", "secondbrain"] + list(args),
                          cwd=str(SKEL), env=env, capture_output=True, text=True)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="pkos-search-"))
    root = tmp / "store"
    d = tmp / "fx" / "Infra"; d.mkdir(parents=True)
    # two documents where the query term and a companion term co-occur
    (d / "cluster-notes.md").write_text(
        "kubernetes cluster setup. We install helm charts for every deployment "
        "and keep the helm values under version control.")
    (d / "ingress-notes.md").write_text(
        "kubernetes ingress configuration. The helm release owns the ingress "
        "and helm handles the certificate.")
    # the payload: mentions the companion term ONLY - no query term anywhere
    (d / "chart-repo.md").write_text(
        "Maintaining our helm chart repository. Publishing a new helm chart "
        "requires bumping the chart version and signing the package.")
    # filler, so document frequencies mean something
    other = tmp / "fx" / "Misc"; other.mkdir(parents=True)
    for i in range(16):
        (other / ("note%02d.md" % i)).write_text(
            "Meeting notes number %d about invoicing, scheduling and travel "
            "arrangements for the quarter." % i)

    print("HYBRID SEARCH TEST"); print("=" * 74)
    sb(root, "init")
    sb(root, "ingest", "filesystem", str(tmp / "fx"))
    sb(root, "rebuild-index", "--quiet")
    sb(root, "graph", "--rebuild")

    r = sb(root, "--json", "search", "kubernetes", "--limit", "10")
    d1 = json.loads(r.stdout)
    titles = [x["title"] for x in d1["results"]]
    check("query terms still win on lexical match",
          any("cluster-notes" in t for t in titles), str(titles[:3]))
    check("expansion learned a companion term from the corpus",
          "helm" in d1["expansion_terms"], str(d1["expansion_terms"]))
    check("a document with NONE of the query's words is retrieved",
          any("chart-repo" in t for t in titles), str(titles))
    hit = [x for x in d1["results"] if "chart-repo" in x["title"]]
    check("and it is retrieved BY the expansion signal, not by luck",
          bool(hit) and hit[0]["score_components"]["expansion"] > 0,
          str(hit[0]["score_components"]) if hit else "not found")

    r = sb(root, "--json", "search", "kubernetes", "--limit", "10", "--no-expand")
    d2 = json.loads(r.stdout)
    t2 = [x["title"] for x in d2["results"]]
    check("--no-expand really disables it (lexical only)",
          not any("chart-repo" in t for t in t2) and d2["expansion_terms"] == [],
          str(t2))

    # graph signal
    r = sb(root, "--json", "search", "Infra", "--limit", "10")
    d3 = json.loads(r.stdout)
    check("graph signal matches a real entity by whole word",
          "Infra" in d3["graph_entities"], str(d3["graph_entities"]))
    boosted = [x for x in d3["results"] if x["score_components"]["graph"] > 0]
    check("objects wired to that entity are boosted",
          len(boosted) > 0, "%d boosted" % len(boosted))
    r = sb(root, "--json", "search", "Infra", "--limit", "10", "--no-graph")
    d4 = json.loads(r.stdout)
    check("--no-graph really disables it",
          all(x["score_components"]["graph"] == 0 for x in d4["results"]))

    # honesty of the ranking table
    rc = d1["ranking"]
    ni = [k for k, v in rc.items() if v.startswith("NOT")]
    check("still declares what is NOT implemented, and why",
          set(ni) == {"personal_relevance", "historical_importance"}
          and all(len(rc[k]) > 40 for k in ni), str(ni))
    check("semantic signal does not claim to be an embedding model",
          "not neural" in rc["semantic_relevance"].lower()
          or "distributional" in rc["semantic_relevance"].lower(),
          rc["semantic_relevance"][:60])

    r = sb(root, "search", "kubernetes", "--explain", "--limit", "2")
    check("--explain shows per-signal contributions",
          "signals:" in r.stdout and "lexical=" in r.stdout)

    print("=" * 74)
    if FAILED:
        print("FAILED (%d)" % len(FAILED))
        for f in FAILED: print("  -", f)
        return 1
    print("ALL SEARCH TESTS PASSED")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
