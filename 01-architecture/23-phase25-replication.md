# Phase 25 — Replication

**Status: COMPLETE.** 18 dedicated tests, all seven suites green.

---

## Not a sync. Replication.

Two-way sync between two copies of one brain means conflict resolution, and
conflict resolution over 39,000 objects means silently picking a winner. The
SOW already settled this in §21.1: **the server is the authority.** So this is
one-directional — master to replica — and every safety property follows from
that single decision.

It also **owns no transport.** No sockets, no SSH library, no credentials. It
builds a bundle and applies a bundle; `scp`, rsync, a USB stick or a courier
moves it. A store that stops working when a network library changes its API is
not one that survives twenty years, and transport is the layer most likely to
change underneath it.

---

## Three refusals, which are the entire feature

**Lineage.** A bundle from a different store never applies. Two stores built
from the *same files* still share no history — the test proves it: identical
inputs, lineages `ac2a2bc0` and `83dccc99`. Lineage is the uuid of
`KB-00000001`, allocated once and never reallocated.

**Direction.** Importing onto a store that is *ahead* is refused. This is the
accident that nearly happened by hand today: Perceptor held an 11:00 copy while
the laptop had a day of work on it, and one careless push would have erased
Phases 22–24. `--force` exists, says exactly what it discards, and is the only
way past.

**Integrity.** Every blob is re-hashed **after extraction**, not merely
checksummed in transit. An archive that unpacked cleanly is not evidence that
the bytes inside are the bytes that were sent.

---

## The canonical-only bundle, and why it is safe

When the evidence plane has not changed, shipping 5.7 GB of blobs to move a
day's canonical work is absurd. So a bundle can carry the database alone — but
that claim is **not taken on trust**. Before touching anything, the importer
decompresses the incoming database to scratch and checks that it holds every
blob that database references. If even one is missing it refuses and changes
nothing.

An assertion the far end can verify is a fact. One it cannot is a hope.

Today's real bundle: **72.6 MB**, zero blobs, against 5.7 GB for a full one.

---

## Four defects found by testing

**The virgin replica crashed.** A store that has never allocated an id has no
`id_sequence` row, and `manifest()` subscripted `None`. The single most
important case for this code — the first ever import — was the one that
failed.

**Blob immutability broke re-import.** Blobs are stored mode `444` on purpose,
so extracting over an existing one fails with `EACCES`. That failure is the
immutability guarantee *working*. Fixed by the correct semantics rather than by
loosening permissions: a blob already present is never overwritten, only
verified.

**The vacuum scratch file was written to the output directory** — which is
normally the mounted or removable medium the bundle is going onto. 2m52s and
still unfinished, versus 7s on local scratch. The bundle medium carries the
finished artefact, not the workings.

**A stale test.** `test_smoke` still asserted `sync` declares
`NOT_IMPLEMENTED`. Same rule as `graph` before it: a test asserting a
limitation that no longer exists is a lie that reports success.

---

## Commands

```
secondbrain sync --manifest FILE            what this store holds (+ lineage)
secondbrain sync --plan --against FILE      what would move, and what is refused
secondbrain sync --export DIR [--against FILE] [--canonical-only]
secondbrain sync --import DIR [--force]
```

Typical cycle: replica emits a manifest → master plans against it → master
exports a delta → move it → replica imports → `validate --deep` →
`rebuild-index`.

---

## What Phase 26 now inherits

Backup/DR is substantially closer than it was. `backup` and
`restore --verify` already exist, and Phase 25 adds the missing primitive: a
**verifiable, self-describing bundle**. What 26 still needs is the layered
policy (primary / secondary / off-site / versioned), a scheduled restore drill
that proves a backup rather than assuming it, and retention. The bundle format
is the unit all of that will operate on.
