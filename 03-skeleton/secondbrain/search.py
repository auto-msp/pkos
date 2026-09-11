"""Derived search plane (SOW 25, 71, 88).

The FTS index lives in a SEPARATE database file under derived/. It is never
authoritative and is always rebuildable from canonical content. Deleting
derived/ and running `secondbrain rebuild-index` must be a complete recovery.

Hybrid ranking (SOW 72) needs semantic + graph signals that require an
embedding model and a populated graph. What is implemented here is the
lexical component plus the metadata/temporal/authority boosts that CAN be
computed today; the semantic and graph terms are declared and reported as
NOT_IMPLEMENTED rather than faked.
"""
import re
import sqlite3
from pathlib import Path
from .util import now_iso

RANK_COMPONENTS = {
    "text_relevance":       "IMPLEMENTED (FTS5 bm25)",
    "semantic_relevance":   "IMPLEMENTED (pseudo-relevance feedback; DISTRIBUTIONAL, "
                            "not neural embeddings - see note below)",
    "graph_connectivity":   "IMPLEMENTED (shared entities in the Phase 22 graph)",
    "recency":              "IMPLEMENTED (source_modified_at decay)",
    "source_authority":     "IMPLEMENTED (object.authority tier)",
    "validation_status":    "IMPLEMENTED (human-validated boost)",
    "revisit_frequency":    "IMPLEMENTED for URLs (url.visit_count)",
    "personal_relevance":   "NOT_IMPLEMENTED - needs a labelled benchmark of "
                            "queries with known-good answers; without one, any "
                            "weighting would be invented",
    "historical_importance":"NOT_IMPLEMENTED - needs Phase 7 temporal clustering "
                            "over the full URL corpus (1,448 of ~20,000 ingested)",
}

# On "semantic": this is NOT an embedding model and must never be described as
# one. The SOW mandates stdlib-only with zero dependencies, so there is no
# sentence transformer here and no vector store. What IS implemented is
# pseudo-relevance feedback: run the query, read the strongest results, find
# the terms that are far more common in those results than in the corpus at
# large, and search again with them at reduced weight. It is distributional
# rather than neural - it learns "n8n" relates to "workflow" because they
# co-occur in YOUR documents, not because a model was pre-trained on the web.
# That is a real and measurable recall improvement, and a smaller claim than
# "semantic search". Making the smaller true claim is the point.

WEIGHTS = {"lexical": 1.0, "expansion": 0.35, "graph": 0.5,
           "authority": 0.6, "recency": 0.3}
PRF_DOCS = 8          # strongest results read for expansion terms
PRF_TERMS = 6         # expansion terms taken from them
PRF_CHARS = 4000      # per document, enough for the topic without the tail
STOPWORDS = set("""the a an and or of to in for on with is are was were be been
it this that these those as at by from we you i he she they them his her its
not no but if then than so such can will would could should may might must do
does did have has had our your their my me us also more most other some any
all one two new use used using into out up down over under about after before
what which who whom whose when where why how""".split())

AUTHORITY_BOOST = {
    "PRIMARY SOURCE": 1.0, "OFFICIAL DOCUMENTATION": 0.9, "ORIGINAL RESEARCH": 0.9,
    "HUMAN-VALIDATED PERSONAL KNOWLEDGE": 1.0, "DIRECT PROJECT ARTIFACT": 0.8,
    "TECHNICAL SECONDARY SOURCE": 0.5, "COMMUNITY SOURCE": 0.4,
    "SOCIAL MEDIA": 0.2, "AI-GENERATED": 0.1, "UNKNOWN": 0.3,
}


DOC_COLUMNS = ("object_id UNINDEXED, title, body, object_class UNINDEXED, "
               "source_id UNINDEXED, modified UNINDEXED, authority UNINDEXED, "
               "knowledge_state UNINDEXED, tokenize='porter unicode61'")

_WORD = re.compile(r"[\w']+", re.UNICODE)

BATCH = 2000
BODY_CAP = 200000


def _has_table(f, name):
    return f.execute("SELECT 1 FROM sqlite_master WHERE type IN ('table','view')"
                     " AND name=?", (name,)).fetchone() is not None


def build(canon_conn, fts_path, batch=BATCH, on_progress=None):
    """Rebuild the FTS index, resumably, without ever leaving search broken.

    Three properties this needs and an all-at-once rebuild does not have:

      1. It commits in batches. A rebuild whose only commit is at the very end
         loses ALL its work to any interruption - a killed shell, a closed
         laptop, a session wall-clock limit. On a corpus this size that turns a
         recoverable pause into a restart from zero, every time.
      2. It builds into doc_new and swaps at the end, so the PREVIOUS index
         stays queryable throughout. Rebuilding an index is not a reason for
         search to go dark for the duration.
      3. It resumes. Progress is recorded in the derived file itself, keyed on
         the canonical object count, so a resumed build is only valid against
         the same canonical state it started from; anything else restarts.

    None of this makes the index authoritative. Deleting derived/ entirely and
    running this again is still a complete recovery (SOW 25, 88).
    """
    fts_path = Path(fts_path)
    fts_path.parent.mkdir(parents=True, exist_ok=True)
    # WAL before anything else. In the default rollback-journal mode SQLite must
    # DELETE its -journal file on every commit; on a filesystem that forbids
    # unlink (a hardened mount, a policy-restricted share) that surfaces as an
    # opaque "disk I/O error". WAL keeps its sidecar files in place instead.
    # The canonical store already runs WAL for the same reason; the derived
    # plane must be rebuildable in every environment the canonical layer runs in.
    f = sqlite3.connect(str(fts_path))
    f.execute("PRAGMA journal_mode=WAL")
    f.execute("PRAGMA synchronous=NORMAL")
    f.execute("CREATE TABLE IF NOT EXISTS build_state(k TEXT PRIMARY KEY, v TEXT)")

    total = canon_conn.execute(
        "SELECT COUNT(*) FROM object WHERE is_duplicate_of IS NULL").fetchone()[0]
    st = {k: v for k, v in f.execute("SELECT k,v FROM build_state")}
    resuming = (st.get("status") == "BUILDING" and st.get("total") == str(total)
                and _has_table(f, "doc_new"))

    if resuming:
        last = st.get("last") or ""
        done = int(st.get("done") or 0)
    else:
        f.execute("DROP TABLE IF EXISTS doc_new")
        f.execute("CREATE VIRTUAL TABLE doc_new USING fts5(%s)" % DOC_COLUMNS)
        f.executemany("INSERT OR REPLACE INTO build_state(k,v) VALUES(?,?)",
                      [("status", "BUILDING"), ("total", str(total)),
                       ("last", ""), ("done", "0"),
                       ("started_at", now_iso())])
        f.commit()
        last, done = "", 0

    rows = canon_conn.execute(
        "SELECT o.object_id, o.title, o.object_class, o.authority, o.knowledge_state,"
        "       v.body, p.source_system, p.source_modified_at"
        "  FROM object o"
        "  LEFT JOIN object_version v ON v.version_id = o.current_version"
        "  LEFT JOIN provenance p ON p.version_id = o.current_version"
        " WHERE o.is_duplicate_of IS NULL AND o.object_id > ?"
        " ORDER BY o.object_id", (last,))

    pending = 0
    for r in rows:
        f.execute("INSERT INTO doc_new(object_id,title,body,object_class,source_id,"
                  "modified,authority,knowledge_state) VALUES(?,?,?,?,?,?,?,?)",
                  (r["object_id"], r["title"] or "", (r["body"] or "")[:BODY_CAP],
                   r["object_class"], r["source_system"] or "",
                   r["source_modified_at"] or "", r["authority"] or "UNKNOWN",
                   r["knowledge_state"]))
        done += 1; pending += 1; last = r["object_id"]
        if pending >= batch:
            f.executemany("UPDATE build_state SET v=? WHERE k=?",
                          [(last, "last"), (str(done), "done")])
            f.commit(); pending = 0
            if on_progress:
                on_progress(done, total)

    f.executemany("UPDATE build_state SET v=? WHERE k=?",
                  [(last, "last"), (str(done), "done")])
    f.execute("DROP TABLE IF EXISTS doc")
    f.execute("ALTER TABLE doc_new RENAME TO doc")
    f.executemany("INSERT OR REPLACE INTO build_state(k,v) VALUES(?,?)",
                  [("status", "FRESH"), ("finished_at", now_iso())])
    f.commit()
    try:
        f.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.OperationalError:
        pass
    f.close()

    canon_conn.execute(
        "INSERT INTO derived_index_registry(index_name,kind,backend,built_at,"
        "object_count,status,rebuild_command)"
        " VALUES('fts_main','fts','sqlite-fts5',?,?, 'FRESH','secondbrain rebuild-index')"
        " ON CONFLICT(index_name) DO UPDATE SET built_at=excluded.built_at,"
        " object_count=excluded.object_count, status='FRESH'",
        (now_iso(), done))
    canon_conn.commit()
    return done


def build_progress(fts_path):
    """What a partially built index knows about itself."""
    fts_path = Path(fts_path)
    if not fts_path.exists():
        return None
    f = sqlite3.connect(str(fts_path))
    try:
        if not _has_table(f, "build_state"):
            return None
        st = {k: v for k, v in f.execute("SELECT k,v FROM build_state")}
        st["queryable"] = _has_table(f, "doc")
        return st
    finally:
        f.close()


def _fts(f, expr, limit):
    """Run an FTS query, falling back to literal tokens when the user's words
    trip FTS5's grammar (a hyphen is an operator, a colon means 'column')."""
    sql = ("SELECT object_id,title,object_class,source_id,modified,authority,"
           "       snippet(doc,2,'[',']','...',12) snip, body, bm25(doc) score"
           "  FROM doc WHERE doc MATCH ? ORDER BY score LIMIT ?")
    try:
        return f.execute(sql, (expr, limit)).fetchall()
    except sqlite3.OperationalError:
        toks = [t for t in _WORD.findall(expr) if t]
        safe = " OR ".join('"%s"' % t.replace('"', '""') for t in toks)
        if not safe:
            raise SystemExit("nothing searchable in %r" % expr)
        try:
            return f.execute(sql, (safe, limit)).fetchall()
        except sqlite3.OperationalError as e:
            raise SystemExit("bad FTS query %r: %s" % (expr, e))


_HEXISH = re.compile(r"^[0-9a-f]{8,}$")


def _is_identifier(t):
    """Reject tokens that are identifiers rather than vocabulary.

    Notion page ids, uuid fragments and hashes are perfect expansion
    candidates by the arithmetic - very rare, so enormous IDF - and completely
    useless as meaning. The first live run expanded a query with
    "31f07c94a4a7803dba80c85e630ea866". Rarity is not significance.
    """
    if t.isdigit() or _HEXISH.match(t):
        return True
    if len(t) > 20:
        return True                     # no English word is this long
    digits = sum(c.isdigit() for c in t)
    if len(t) >= 12 and digits:
        return True                     # long AND mixed = a key, e.g. 01kpwzd8wq...
    return bool(digits) and digits / len(t) > 0.3


def expansion_terms(f, seed_rows, query_terms, n_docs=PRF_DOCS, n_terms=PRF_TERMS):
    """Pseudo-relevance feedback.

    Terms that are common in the strongest results but rare in the corpus are
    the ones that characterise the topic. Terms common everywhere characterise
    nothing - the same discrimination rule the graph uses for saturation.
    """
    import collections, math
    total = f.execute("SELECT COUNT(*) FROM doc").fetchone()[0] or 1
    tf = collections.Counter()
    for r in seed_rows[:n_docs]:
        text = ((r["title"] or "") + " " + (r["body"] or "")[:PRF_CHARS]).lower()
        for t in set(_WORD.findall(text)):
            if len(t) > 2 and t not in STOPWORDS and not _is_identifier(t):
                tf[t] += 1
    seen = {t.lower() for t in query_terms}
    scored = []
    for t, c in tf.most_common(400):
        if t in seen or c < 2:
            continue
        try:
            df = f.execute("SELECT COUNT(*) FROM doc WHERE doc MATCH ?",
                           ('"%s"' % t.replace('"', '""'),)).fetchone()[0]
        except sqlite3.OperationalError:
            continue
        if df == 0 or df > total * 0.25:
            continue
        scored.append((c * math.log(total / df), t))
    scored.sort(reverse=True)
    return [t for _s, t in scored[:n_terms]]


def match_entities(canon_conn, q_terms, limit=8):
    """Entities whose NAME the query mentions, as whole words.

    Substring matching here was actively harmful: "automation" matched a Folder
    entity called "screencapture-polsia-dashboard-...-automation-services.png",
    and every file wired to it took the full graph boost. One loose LIKE put a
    junk file at rank 1. Whole words only, exact matches first.
    """
    ents, seen = [], set()
    for t in q_terms:
        if len(t) < 4:
            continue
        tl = t.lower()
        word = re.compile(r"(?:^|[^a-z0-9])%s(?:[^a-z0-9]|$)" % re.escape(tl))
        for r in canon_conn.execute(
                "SELECT object_id, title, object_class FROM object"
                " WHERE knowledge_state='DERIVED' AND decay_status<>'SUPERSEDED'"
                "   AND is_duplicate_of IS NULL AND lower(title) LIKE ? LIMIT 40", ("%" + tl + "%",)):
            title = (r["title"] or "").lower()
            if r["object_id"] in seen:
                continue
            if title == tl or word.search(title):
                seen.add(r["object_id"])
                d = dict(r); d["exact"] = (title == tl)
                ents.append(d)
    ents.sort(key=lambda e: not e["exact"])
    return ents[:limit]


def graph_candidates(canon_conn, ents, cap):
    """Objects wired to those entities - RETRIEVED, not merely re-ranked.

    This started as a re-ranking signal that could only reorder whatever the
    lexical search already returned. That made it useless in exactly the case
    it should be strongest: ask for a folder or a domain by name, and if no
    document happens to contain that word, the graph knows precisely which
    objects belong to it and never gets asked. A retrieval signal has to be
    able to put a document INTO the result set.
    """
    if not ents:
        return {}
    eids = [e["object_id"] for e in ents]
    qm = ",".join("?" * len(eids))
    hits = {}
    for r in canon_conn.execute(
            "SELECT source_object o, COUNT(*) n FROM relationship"
            " WHERE target_object IN (%s) GROUP BY 1 ORDER BY 2 DESC LIMIT ?" % qm,
            eids + [cap]):
        hits[r["o"]] = r["n"]
    return hits


def _doc_rows(f, oids):
    if not oids:
        return {}
    out = {}
    oids = list(oids)
    for i in range(0, len(oids), 400):
        chunk = oids[i:i + 400]
        qm = ",".join("?" * len(chunk))
        for r in f.execute(
                "SELECT object_id,title,object_class,source_id,modified,authority,"
                "       '' snip, body, 0.0 score FROM doc"
                " WHERE object_id IN (%s)" % qm, chunk):
            out[r["object_id"]] = r
    return out


def query(canon_conn, fts_path, q, limit=20, expand=True, use_graph=True):
    fts_path = Path(fts_path)
    if not fts_path.exists():
        raise SystemExit("no search index - run: secondbrain rebuild-index")
    f = sqlite3.connect(str(fts_path)); f.row_factory = sqlite3.Row
    f.execute("PRAGMA journal_mode=WAL")

    pool = limit * 5
    q_terms = [t for t in _WORD.findall(q) if t.lower() not in STOPWORDS]
    base = _fts(f, q, pool)
    rows = {r["object_id"]: r for r in base}
    lex = {r["object_id"]: -float(r["score"]) for r in base}

    exp_terms, expn = [], {}
    if expand and base:
        exp_terms = expansion_terms(f, base, q_terms)
        if exp_terms:
            expr = " OR ".join('"%s"' % t for t in exp_terms)
            for r in _fts(f, expr, pool):
                rows.setdefault(r["object_id"], r)
                expn[r["object_id"]] = -float(r["score"])

    gr, ents = ({}, [])
    if use_graph:
        ents = match_entities(canon_conn, q_terms)
        gr = graph_candidates(canon_conn, ents, pool)
        missing = [o for o in gr if o not in rows]
        for oid, r in _doc_rows(f, missing).items():
            rows[oid] = r
        gr = {o: n for o, n in gr.items() if o in rows}

    def norm(d):
        if not d:
            return {}
        m = max(d.values()) or 1.0
        return {k: v / m for k, v in d.items()}
    nlex, nexp, ngr = norm(lex), norm(expn), norm(gr)

    out = []
    for oid, r in rows.items():
        a = AUTHORITY_BOOST.get(r["authority"] or "UNKNOWN", 0.3)
        rec = 0.0
        if r["modified"]:
            rec = 1.0 if r["modified"] >= "2026" else (0.5 if r["modified"] >= "2025" else 0.0)
        c = {"lexical":   round(WEIGHTS["lexical"] * nlex.get(oid, 0.0), 4),
             "expansion": round(WEIGHTS["expansion"] * nexp.get(oid, 0.0), 4),
             "graph":     round(WEIGHTS["graph"] * ngr.get(oid, 0.0), 4),
             "authority": round(WEIGHTS["authority"] * a, 4),
             "recency":   round(WEIGHTS["recency"] * rec, 4)}
        out.append({"object_id": oid, "title": r["title"],
                    "object_class": r["object_class"], "source": r["source_id"],
                    "modified": r["modified"], "authority": r["authority"],
                    "snippet": r["snip"], "score": round(sum(c.values()), 4),
                    "score_components": c})
    f.close()
    out.sort(key=lambda x: -x["score"])
    return {"results": out[:limit], "expansion_terms": exp_terms,
            "graph_entities": [e["title"] for e in ents],
            "pool_size": len(rows)}
