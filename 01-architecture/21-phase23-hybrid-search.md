# Phase 23 — Hybrid retrieval

**Status: COMPLETE.** 7 of the 9 §72 ranking signals now active, 2 still
honestly `NOT_IMPLEMENTED`. 11 dedicated tests. Query latency ~1.5 s over
31,206 indexed objects.

---

## The constraint that shaped it

The SOW mandates stdlib-only, zero dependencies. That rules out a sentence
transformer, a vector store, and therefore "semantic search" in the sense
people usually mean.

Two honest options: declare semantic relevance permanently blocked, or find a
technique that delivers real recall gains inside the constraint. This is the
second — **pseudo-relevance feedback** — and the naming matters. It is
described everywhere in the code and the CLI as *distributional, not neural*,
because the difference is real: it learns that "n8n" relates to "workflow"
because they co-occur in **your** documents, not because a model was
pre-trained on the web. Smaller claim, and true.

---

## How a query is answered

1. **Lexical** — FTS5 bm25 over canonical bodies.
2. **Expansion** — read the 8 strongest results, find terms far more common in
   them than in the corpus (`tf · log(N/df)`), take the top 6, search again at
   0.35 weight. This is what lets a document containing **none of the query's
   words** be found.
3. **Graph** — entities whose *name* the query mentions, matched as whole
   words; every object wired to them enters the pool.
4. **Priors** — authority tier, recency, validation status.

Signals are max-normalised and weighted, and `--explain` prints each one's
contribution per result. `--no-expand` and `--no-graph` turn the new signals
off, which is how the tests prove they are doing the work rather than
decorating it.

---

## Four defects the tests caught

**The graph could only re-rank, never retrieve.** It scored objects the lexical
search had already found — useless in precisely the case it should be
strongest. Ask for a folder by name, and if no document text contains that
word, the graph knows exactly which objects belong to it and never gets asked.
A retrieval signal must be able to put a document *into* the result set.

**Substring entity matching put junk at rank 1.** "automation" matched a Folder
entity called `screencapture-polsia-dashboard-…-automation-services.png`, and
every file wired to it took the full graph boost. Whole-word matching only,
exact hits first.

**Rarity was being mistaken for significance.** The first live run expanded a
query with `31f07c94a4a7803dba80c85e630ea866` — a Notion page id. Perfect by
the arithmetic (vanishingly rare, so enormous IDF) and meaningless. Identifier-
shaped tokens are now rejected: long hex strings, and anything more than 30%
digits.

**Extraction artefacts were being filed as folders.** Path segments ending
`.zip`, `.png`, `.mp4` are unzipped archives, not filing systems. Excluded, and
the 88 entities the old rule had created were retired — `decay_status =
SUPERSEDED`, excluded from lookup and ranking, **never deleted**: they carry
`KB-` ids that may already appear in an answer, and history is append-only
(SOW 10/11). They revive automatically if a future rule produces them again.

---

## Proof it works

The test builds three documents. Two mention `kubernetes` and `helm` together.
The third mentions **only** `helm` — none of the query's words.

```
query: "kubernetes"
  chart-repo.md   lexical=0.0  expansion=0.3219  →  retrieved
```

Retrieved with a lexical score of exactly zero, by a term the corpus itself
taught the system. `--no-expand` drops it from the results, which is the
control.

---

## Still not implemented, and why

| Signal | Why not |
|---|---|
| `personal_relevance` | needs a labelled benchmark of queries with known-good answers. Without one, any weighting would be invented and unfalsifiable. |
| `historical_importance` | needs Phase 7 temporal clustering over the full URL corpus — 1,448 of ~20,000 URLs are ingested. |

Both are reported by `secondbrain search` on every query, with the reason. A
system that hides what it cannot do is worse than one that does less.
