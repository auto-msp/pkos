# Phase 22 — Knowledge graph

**Status: COMPLETE.** 1,074 entities, 65,693 relationships, rebuild in ~48 s,
12/12 validate checks pass, 13 dedicated tests.

---

## The decision that shaped everything

The obvious way to build this is to run 38,000 objects through a model, extract
things that look like names, and call them entities. That gives you a graph
that is roughly right, cannot be reproduced, and rots quietly — in three years
nobody can say why a node exists or whether it still should.

So **every entity here is derived from structured evidence the store already
holds and already trusts:**

| Entity | Derived from | Count |
|---|---|---:|
| `Domain` | `url.registrable_domain` — a parse, not a guess | 928 |
| `Folder` | the directory a file was actually acquired from | 133 |
| `Workspace` | `profile_workspace` (Claude projects) | 7 |
| `Server` | `profile_workspace` from real audits | 3 |
| `Account` | the export's own `users.json` | 3 |

Edges follow the same rule. `HOSTED_AT` exists because a URL's host **is** that
domain. `STORED_IN` exists because the file **was** in that directory. Nothing
is created from resemblance.

Each entity carries `knowledge_state='DERIVED'` and a provenance row naming the
exact rule (`graph:domain-from-url`, `graph:folder-from-path`, …), so the whole
layer is reproducible and a wrong rule is correctable rather than permanent.

---

## The one inexact pass, and its fence

`MENTIONS` is the only edge type built by matching text. It is a literal phrase
search over canonical bodies via the FTS index, and it is fenced:

**An entity appearing in more than 5% of objects produces no mention edges at
all.** A term in a third of your documents cannot tell you which document you
want; it is noise wearing a graph edge's clothes. The true match count is
recorded on the entity either way, as a new version explaining why the edges
were withheld — the decision is visible, not silently applied.

Result: 902 entities carry mentions, 10,282 edges, 36 entities matched nothing,
0 saturated on the current corpus.

---

## Edges now in the store

| Type | Count | Origin |
|---|---:|---|
| `PART_OF` | 17,212 | message → conversation (acquired) |
| `REPLIES_TO` | 16,931 | message → parent message (acquired) |
| `STORED_IN` | 16,402 | file → folder (derived) |
| `MENTIONS` | 10,282 | object → entity (derived, fenced) |
| `ATTACHED_TO` | 3,077 | attachment → message (acquired) |
| `HOSTED_AT` | 1,448 | bookmark → domain (derived) |
| `BELONGS_TO` | 341 | container → account / workspace (derived) |

The most connected entities are, correctly, his real working structure:
`03 - AI Tools & N8N` (7,596 files), `06 - Documents` (2,592),
`09 - Social & Comms` (1,939), then `google.com`, `github.com`, `n8n.io`,
`claude.ai`.

---

## Three defects caught by testing, not by running

**1. The folder rule was a coincidence, not a rule.** The first version
hardcoded `/mnt/` and took the segment after it. It produced a beautiful result
on this machine and collapsed every file into one meaningless entity anywhere
else — with no error. Replaced with: find the deepest directory all acquired
files share, take the first segment below it, and descend one level past any
segment holding >95% of files (a path component every file shares tells you
nothing about any of them — the same reasoning as mention saturation).

**2. An invariant satisfied by luck.** The saturation branch created a version
with no provenance row, which breaks `every_version_has_provenance`. It never
fired on this corpus, so the omission was invisible. The test now forces
saturation with `SATURATION = 0.0`, which is the only reason it was found.

**3. Rebuild added instead of replacing.** Changing the folder rule would have
left the old edges in place beside the new ones — a file "stored in" two
folders, one from a rule that no longer exists. `rebuild` now deletes edges
with `created_by LIKE 'rule:%'` first. Adapter edges (`created_by='job:…'`) are
acquired facts and are never touched.

---

## Commands

```
secondbrain graph --rebuild                    derive entities and edges
secondbrain graph                              counts by class and edge type
secondbrain graph --top [--entity-class Folder]  most connected entities
secondbrain graph --find automsp               entity lookup by name
secondbrain graph --object KB-00039666         one object's edges, in and out
```

---

## What this unblocks, and what it doesn't

`graph_connectivity` is one of the four §72 ranking signals still reported as
`NOT_IMPLEMENTED`. The graph it needed now exists, so wiring it into ranking is
Phase 23 work rather than a blocked dependency. It is **not** claimed as done:
search ranking is unchanged today and still says so.

Entity resolution across *surface forms* (that "AutoMSP", "automsp.us" and
"AutoMSP AI Automation Services" are one thing) is deliberately not attempted.
That requires judgement, and judgement belongs behind the §3 agent boundary
with a human confirming merges — not in a deterministic rebuild that runs
unattended.
