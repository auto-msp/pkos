# Phase 24 — The agent boundary

**Status: COMPLETE.** 21 dedicated tests, all six suites green, 12/12 validate.

Per the §3 decision: **hybrid, deterministic core, agents used only for
interpretation.** This phase makes that a mechanism rather than an intention.

---

## The line, and where it is drawn

```
  DETERMINISTIC CORE                      |   AGENT
  ------------------------------------    |   -----------------------
  ask     retrieve, trace, state gaps     |   read the pack, interpret
                                          |
  answer  record, attribute, quarantine   <---  the interpretation
  cite    walk back to the bytes          |
  validate-answer  human accepts/rejects  |
```

`ask` **produces no prose.** It gathers evidence, traces each item back to the
bytes it came from, states plainly what the store cannot answer from, and
stops. There is a test asserting the returned pack contains no `answer`,
`summary`, `conclusion` or `response` key — because the moment retrieval starts
writing sentences, the line between what the store *knows* and what a model
*said* is gone, and no amount of documentation gets it back.

---

## What `ask` returns

Evidence, plus the part most systems leave out:

```
WHAT THIS STORE CANNOT ANSWER FROM
  ingested    : Claude conversations, browser bookmarks, laptop files, server audits
  NOT ingested: airtable, chatgpt, facebook, github-stars, gmail/outlook/zoho,
                google-takeout, gumroad, instagram, linkedin, notion
  corpus spans: 2018-07-02 .. 2026-09-08
  ranking signals off: personal_relevance, historical_importance
  696 object(s) redacted for credentials; 11 item(s) in the dead-letter queue
```

An answer built on a corpus with known holes is not wrong. Presenting it
without the holes is. Every item also carries `traceable_to_bytes`, and the
instruction to the agent says explicitly: do not fill a gap from general
knowledge, and never cite an untraceable item as fact.

---

## What happens to a model's answer

It enters the store **quarantined and attributed**:

| Field | Value |
|---|---|
| `knowledge_state` | `SYNTHESIZED` — never `ORIGINAL` |
| `authority` | `AI-GENERATED` (ranking weight 0.1 vs 1.0 for primary source) |
| `validation_status` | `REQUIRES_HUMAN_REVIEW` |
| `decay_status` | `UNVERIFIED` |
| provenance | names the model and the inquiry id |
| relationships | `DERIVED_FROM` every source it cited |

A model's paraphrase of Moiz must never come back as something Moiz said. Only
`validate-answer --accept` promotes it to `HUMAN_VALIDATED`, and that promotion
is **a new version**, not an edit in place — the model's original text stays
readable forever alongside the human verdict.

---

## `cite` — SOW 17 made executable

```
ANSWER -> object -> object_version -> provenance -> evidence_blob -> bytes
```

Live example:

```
KB-00002936  [File]  160.md
  version        : KB-00002936:v01 (imported by job:JOB-c994e655e3a8)
  provenance     : source=SRC-laptop-filesystem
                   path=.../Downloads/Claude Chat/chat_archive/160.md
  evidence blob  : a991b15e4b970ae5…  25,005 bytes at evidence/blobs/a9/91/…
CHAIN COMPLETE - this traces to raw bytes on disk.
```

**One correction worth recording.** The first version reported a synthesised
answer as `CHAIN INCOMPLETE - do not cite this as fact`, because the answer has
no blob of its own. That is what synthesis *means*, not a defect. Crying wolf
on a well-sourced answer trains you to ignore the warning, and then it is worth
nothing the day a chain is genuinely broken. It now walks the parents and
reports `CHAIN COMPLETE VIA 4 PARENT(S)` — and still fails loudly when a parent
really doesn't trace.

---

## Entity merging: the first real use of the boundary

Moiz said "everything means the same" about AutoMSP. The graph held **13**
entities matching *automsp*, and they were not all the same thing:
`automsp_pitch_chunks_part1of3` is a chunked-file directory, not a company, and
`01 - AutoMSP & CoreIT` is a folder spanning **two** companies. Executing the
instruction as stated would have made the graph worse.

So the merge was proposed as a specific set and confirmed: AutoMSP AI
Automation Services absorbs AutoMSP Official Website and automsp.store — 261 →
360 edges. Core Technology Services was deliberately left separate; it is a
different company.

`--merge` **refuses without `--confirmed-by`**:

> Merging two entities is a judgement, not a computation.
> The store records WHO decided it, so it can be questioned later.

The alias keeps its id, its history and its own edges (SOW 19: linked, never
deleted). Anything that already cited it stays valid.

**And a bug this caught.** The orphan-retirement pass revives any superseded
entity that has edges — and a merged alias keeps its edges by design. The next
`graph --rebuild` would have silently undone a merge a human confirmed. A
rebuild must never overturn a human decision; there is now a test that fails if
it does.

---

## Commands

```
secondbrain ask "..."                     evidence + gaps, no answer
secondbrain answer --model M --inquiry INQ-x --text f --cite KB-1 KB-2
secondbrain cite KB-x                     walk back to the bytes
secondbrain validate-answer KB-x --accept --note "..."
secondbrain graph --merge CANON ALIAS --confirmed-by WHO --reason "..."
```

---

## What is deliberately absent

The core does not call a model. The SOW forbids dependencies, and a knowledge
store that cannot function without a live API is not one that survives twenty
years. The agent is whatever reads the pack — Claude here, GLM in Moiz's
two-LLM design — and the contract between them is a JSON document, not a
library.
