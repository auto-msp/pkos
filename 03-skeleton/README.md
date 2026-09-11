# `secondbrain` — PKOS canonical layer (working skeleton)

Python 3 **standard library only**. No pip install, no dependencies, no build
step. That is a design requirement, not laziness: the SOW asks for a 10–20 year
lifespan (§124, §125.45), and every dependency is a component that can rot.

```bash
export PKOS_ROOT=/path/to/pkos-store
python3 -m secondbrain init
python3 -m secondbrain ingest filesystem "/path/to/docs"
python3 -m secondbrain ingest bookmarks "/path/to/bookmarks.html" --browser chrome
python3 -m secondbrain rebuild-index
python3 -m secondbrain search "postgres"
python3 -m secondbrain validate --deep
python3 -m secondbrain status
```

`bin/secondbrain` is the same thing as an executable. Add `--json` to any
command for machine-readable output.

## Three planes, physically separated (§5)

```
$PKOS_ROOT/
  evidence/    EVIDENCE PLANE   immutable, content-addressed by sha256, append-only
    blobs/aa/bb/<sha256>        the path IS the hash
  canonical/   KNOWLEDGE PLANE  the authority
    canonical.sqlite3           operational store
    mirror/*.jsonl              portability guarantee — one file per table
  derived/     DERIVED PLANE    rebuildable; deleting it is a recoverable act
```

The separation is physical so that `rm -rf derived/` is safe **by construction**,
not by convention. The smoke test proves it: it deletes the entire derived plane
and recovers with one command.

## What actually works

| Command | State |
|---|---|
| `init` `status` `inventory` `accounts` `health` `export` | working |
| `ingest filesystem` | working — §75 include/exclude, idempotent, versioning |
| `ingest bookmarks` | working — Netscape parser, URL canonicalization, ADD_DATE |
| `ingest server-audit` | working — consumes `pkos-server-audit.sh` output |
| `validate` / `--deep` | working — 9 invariants + blob re-hash |
| `search` / `rebuild-index` | working — FTS5 + authority/recency boosts |
| `duplicates` / `--link` | working — exact + url-variant kinds |
| `history` | working — temporal + domain aggregation |
| `audit` / `--dead-letter` | working |
| `backup` / `restore --verify` | working — §93 restore verification |
| `servers` | working once audits are ingested; explains the block otherwise |
| `cleanup` | **refuses** without `--dry-run` (§97 gate) |
| `graph` `sync` `storage` `discover` | **NOT_IMPLEMENTED**, exit 3, names the blocking phase |

A stub that printed success would violate §43 and §107, so none of them do.
`NOT_IMPLEMENTED` exits non-zero and says which phase unblocks it.

## Invariants `validate` enforces

Every object has a current version · every version has provenance · version
chains are intact · every object has event history · account boundaries are
never collapsed (§125.11) · duplicates are linked and never deleted (§125.10) ·
conflicts are surfaced, never silently resolved (§125.12) · no secret *values*
in the canonical store (§125.14) · derived indexes are registered as rebuildable.
`--deep` re-hashes every evidence blob and reports drift.

## Two things this skeleton deliberately does not do

**It is not the canonical authority yet.** §21.1 puts that on the Ubuntu
server. Until the server audit lands, this local tree is a working replica.
`sync` refuses to guess an architecture for infrastructure nobody has measured.

**It does not call an LLM.** §2 splits Claude Opus 5 (architecture, hard
extraction, review) from GLM 5.3 (bulk classification, tagging, summarization).
That boundary belongs in the enrichment pipeline, which is Phase 4+. Everything
here is deterministic on purpose (§3: "use deterministic code for critical
operations"), so the canonical layer never depends on a model being available
or behaving the same way twice.

## Tests

```bash
python3 tests/test_smoke.py
```

34 assertions against real fixtures — including ingesting a genuine
`pkos-server-audit.sh` output, deleting the derived plane and rebuilding it, and
verifying a backup by restore (§93). They assert on measured numbers, never on
the absence of an exception.
