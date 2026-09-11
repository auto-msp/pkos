# Phase 14 — Claude conversation history

**Status: COMPLETE.** 18,856 items acquired, **0 failures**, 0 dead-letter rows.
Job `JOB-a443fe346cfc4a42`.

---

## What went in

| Object class | Count | What it is |
|---|---:|---|
| `Message` | 15,908 | the retrievable unit — what search returns and what a citation points at |
| `Attachment` | 797 | a document pasted *into* a conversation; its own origin, its own authority tier |
| `FileReference` | 1,916 | an uploaded file the export names but does **not** carry the bytes for |
| `Conversation` | 184 | the container: title, summary, dates, opening request |
| `AssistantMemory` | 15 | what the assistant had synthesised about you |
| `Project` | 6 | registered as workspaces, and as objects |
| `ProjectDocument` | 4 | files attached to a Claude Project |

Span: **2025‑03‑30 → 2026‑07‑20**. Human 7,987 / assistant 7,921 messages.

Relationships written — **structural, present in the export, never inferred**:

| Type | Count |
|---|---:|
| `PART_OF` (message → conversation, doc → project) | 15,912 |
| `REPLIES_TO` (message → parent message) | 15,733 |
| `ATTACHED_TO` (attachment / file ref → message) | 2,739 |

`REPLIES_TO` is the branch structure of every conversation. It is the first
real graph in the store, and Phase 22 traversal will run on it.

---

## Design decisions

### Five classes, not one blob per conversation
A conversation is what a person *remembers* ("that chat where we built the
voice agent"); a message is what search should *return*. Collapsing them gives
you either a search that returns 100‑message walls, or a corpus with no
conversational identity. Both are kept, linked by `PART_OF`.

Attachments are separated for a different reason: a document pasted into a
chat has a **different origin** from the chat around it. Smearing it into the
message body would give a third‑party document the same authority tier as
something you wrote.

### The assistant's memory is labelled as synthesised
The 15 `AssistantMemory` objects carry `knowledge_state = SYNTHESIZED`,
`decay_status = UNVERIFIED`, `authority = AI-GENERATED`. They are useful, and
they are **not** things you said. The store must never let a model's summary of
you be retrieved as if it were your own statement.

### Authority is assigned by who spoke
`PRIMARY SOURCE` for your messages, `AI-GENERATED` for the assistant's.
This flows straight into ranking: `AUTHORITY_BOOST` is 1.0 vs 0.1. Your own
words outrank a model's paraphrase of them by an order of magnitude, by
construction rather than by hope.

### Credentials never reach the canonical layer
16 objects contained credential material and were redacted **at ingest**, in
the same transaction that created them — the value never existed in a
searchable body, not even briefly. The raw bytes stay in the evidence plane,
content-addressed, retrievable deliberately. `validate` passes
`no_secret_values_in_bodies` because there is nothing to find, not because the
check is lenient.

---

## What the export does NOT contain (SOW 107)

Recorded as fact, not worked around:

1. **Uploaded file bytes are absent.** `files[]` carries a uuid and a name
   only. 1,916 `FileReference` objects record the gap with
   `bytes_available: false` so it is countable, instead of 1,916 files
   silently never existing.
2. **Conversations carry no project id.** Project membership *cannot* be
   reconstructed from this archive. No such relationship was invented.
   Projects are registered as workspaces; their docs are ingested.
3. **`tool_result` payloads are summarised**, not inlined — name, error flag,
   character count. The full JSON is in the evidence blob.

---

## The older snapshot: proven redundant, not assumed

`Downloads/Brain/Claude-Obsidian/conversations.json` (68 MB, April 2026) was
compared conversation-by-conversation against the July generation:

- 106 of 106 of its conversations are present in the newer export
- **0 conversations and 0 messages exist only in the older one**
- 11 conversations grew; **0 shrank**

So it contains nothing the newer export lacks. It is retained in the evidence
plane as a dated snapshot and **not** ingested — ingesting it would have
inflated the corpus without adding knowledge. `raw_export/` proved
byte-identical (`sha256 e6a19fdb…`) and collapsed to the same blob for free.

Both facts are in the audit log, with the proof, not just the conclusion.

---

## Two engineering fixes this phase forced

**1. `rebuild-index` was not survivable — now it is.**
The old rebuild committed once, at the end. On this corpus it accumulated a
196 MB uncommitted WAL, ran past three minutes, and lost **everything** to a
single interruption. It now commits in 2,000-row batches, records progress in
the derived file itself, and resumes. Side effect of batching: the rebuild went
from *over 180 s and never finishing* to **13.1 s** for 29,312 objects.

It also builds into `doc_new` and swaps at the end, so the previous index stays
queryable throughout. Rebuilding an index is not a reason for search to go dark.

**2. Manifests no longer claim states nobody verified.**
28 jobs killed by shell wall-clock limits sat in `ACQUIRING` forever, so the
manifest table implied work still in flight that had stopped days ago. They are
now `INTERRUPTED`, with the reason recorded and the resuming job identified.
§43 cuts both ways: never declare success without proof, and never leave a
record asserting a state you never confirmed.

---

## Store after Phase 14

```
objects      36,797        versions  37,144       provenance rows  37,144
evidence     9,035 blobs / 5.7 GB    FTS indexed  29,312 (duplicates aliased, not re-indexed)
validate     10 / 10 PASS            dead letter  11 (all Phase-8 unparseable URLs)
```

By source: Claude 18,830 · laptop filesystem 16,516 · bookmarks 1,448 · servers 3.

Accounts stay separate (SOW 45/46): `mcontractor@coreitx.com` is registered as
its own account under `SRC-claude-ai`, verified from `users.json`, and is not
merged with anything.

---

# Addendum — 2026-09-08: the "second account" that wasn't, and a changed export format

## It is the same account

A second export was pulled from what was believed to be a different Claude
account. It is not. `users.json` reports account
`9004a7af-08eb-40cb-a249-4472048b282d`, `mcontractor@coreitx.com` — identical
to the July export — and it carries the same six project uuids and the same two
design-chat uuids.

This was checked before ingesting, not after, and that ordering is the point.
Had the adapter simply trusted the label on the folder, the store would now
contain a second "account" that is the same person, and every count in it would
be wrong in a way that is very hard to unpick later.

What the newer export actually is: **a later generation of the same account.**

| | |
|---|---:|
| Conversations only in the new export | 15 (72 messages) |
| Conversations only in the old export | **0** — nothing was deleted |
| Existing conversations that grew | 9 (+125 messages) |
| Total messages | 16,105 (was 15,908) |
| New span | 2025‑03‑30 → **2026‑09‑08** |

Ingest result: **338 created, 18 versioned, 18,853 unchanged, 0 failures.**
Those 18 versions are the §9/§10 versioning path proving itself on real data —
9 assistant-memory documents and 9 conversations changed since July, and each
got a new version under its existing `KB-` id rather than a duplicate object.

## The export format changed

July delivered one folder. September delivers a **manifest plus five zips**
(`conversations`, `light_metadata`, `memories`, `projects`, `design_chats`),
each behind a **single-use download URL**. The adapter now handles both, treats
the manifest as the authority on completeness, and refuses to run when a part
named in the manifest is absent — because a failed download cannot be retried
from the same manifest, and the alternative is a successful-looking run that is
quietly short a whole category.

Three things the new shape broke, all found before they could do damage:

1. **`memories.json` became `memories/<account-uuid>.json`.** The old glob did
   not match it. Nothing would have errored; all 15 memory documents and 4
   project memories would simply have been missing. The lookup now targets the
   account's own file by name, and *counts* any memory file belonging to a
   different account rather than passing over it silently.
2. **`login_history.json` is new** — 61 sign-ins spanning 2025‑03‑17 →
   2026‑09‑08, 46 distinct IPs, 58 from IN and 3 from US. This is the only
   first-party record of when and from where the account was accessed, so it is
   now ingested as `LoginEvent` objects, classified `SENSITIVE`. It is what a
   "was that actually me?" question needs, and it is answerable only if kept.
3. **Export download URLs are credential material.** A manifest sitting in
   Downloads gets ingested like any other file, and each URL is a bearer token
   for an entire account's history until claimed. Added to the secret patterns;
   they are stripped from canonical bodies automatically.

Zip handling refuses `../` and absolute paths, and only ever opens archives the
manifest names — a Downloads folder holding 116 unrelated zips must not become
an ingestion target.

## One more fix: search stopped rejecting ordinary words

FTS5 has its own grammar. A hyphen is an operator; a colon means "column". So
`sign-in magic_link` came back as `no such column: in`. Someone searching their
own notes types words, not a query language. The query now retries with each
token quoted as a literal, while deliberate operator syntax (`traefik AND
certbot`) still works untouched.

## Store after the addendum

```
objects  37,135     versions  37,500     relationships  34,838
FTS      29,650 indexed in 8.1s          validate  11 / 11 PASS
```

---

# Addendum 2 — 2026-09-08: the real second account, and the bug that nearly hid it

## Both accounts are now in, and they are separate

| Account | uuid | Conversations | Messages | Span |
|---|---|---:|---:|---|
| `mcontractor@coreitx.com` | `9004a7af…` | 199 | 16,105 | 2025‑03‑30 → 2026‑09‑08 |
| `openmynewopportunities@gmail.com` | `a34f2c68…` | 90 | 1,102 | **2024‑06‑25** → 2026‑09‑01 |

Second account ingest: **1,556 created, 0 versioned, 0 unchanged, 0 failures** —
0 unchanged is itself the proof that nothing was matched onto the first
account's objects. Plus 80 sign-in records and 19 assistant-memory documents of
its own.

Worth noting against expectation: this account was described as the larger,
more exhaustive one. It is not — it holds about a fifteenth of the messages.
What it does hold is **nine months of earlier history** (June 2024 onward) that
the other account has no record of at all.

## The bug: two accounts, one folder, no error

The first attempt to read this export reported `mcontractor@coreitx.com`. It
was wrong, and the reason is worth writing down.

The landing directory was keyed on the export's **filenames**:

```python
tag = hash("|".join(sorted(z.name for z in zips)))     # WRONG
```

Every Claude export ships the same five names — `conversations-000.zip`,
`memories-000.zip`, and so on. So both accounts' exports mapped to the *same*
landing directory, `claude-export-4e75f96e378c`. The `.unpacked-*` markers from
the first extraction were already sitting there, so the second export **was
never extracted at all**, and the first account's `users.json` was read in its
place.

Everything downstream would then have been correct-looking and false: an ingest
that confidently attributed one account's history to the other, with the
account-boundary invariants all passing, because from the store's point of view
only one account was ever involved.

The fix keys the directory on the **content** of the parts — each zip is hashed
into the evidence plane first, and the directory tag is derived from those
digests. The `.unpacked` marker carries its part's hash too, so a re-download
with changed content re-extracts instead of being skipped.

There is now a regression test that builds two exports with **identical
filenames and different contents** and asserts they unpack to different
directories and register two accounts. It fails against the old code.

The lesson is the same one as the memories-folder rename earlier today: the
dangerous failures in an ingestion pipeline are not the ones that raise. They
are the ones that produce a clean, plausible, complete-looking result from the
wrong bytes. Content addressing is not just for the evidence plane; anywhere a
name is used as an identity, two different things will eventually share it.

## Store after both accounts

```
objects  38,691    versions  39,056    relationships  37,220
blobs    9,055 / 5.7 GB      FTS  31,206 indexed in 11.1s
validate 11 / 11 PASS        accounts  2, strictly separate
```
