# PKOS — Personal Knowledge Operating System

Wave 1: discovery, architecture, and a working canonical layer. Built 2026-09-07.

```
pkos/
  00-discovery/     what the discovery workers found (evidence-backed reports)
  01-architecture/  the 15 required first deliverables (SOW §127)
  02-canonical/     pkos-store/ — the live canonical store, 45 MB, 1,529 objects
  03-skeleton/      secondbrain — working code, stdlib only, 34 passing tests
  90-evidence/      raw discovery evidence (JSON/JSONL) + servers/ (awaiting audits)
  99-runbooks/      pkos-server-audit.sh + runbook + schema — RUN THIS FIRST
```

## Start here

1. **`99-runbooks/RUNBOOK-server-audit.md`** — the one action that unblocks the most. Phases 1 and 2 are blocked without it.
2. **`01-architecture/01-current-state-architecture.md`** — what is actually true right now.
3. **`01-architecture/15-implementation-roadmap.md`** — what to do next and in what order.

## The three findings worth knowing before reading anything else

**The 20,000-URL file does not exist.** Downloads was walked completely — 57,145 files. The real corpus is 1,448 unique URLs over 8.1 years, from a bookmarks HTML export. The missing ~18,500 are almost certainly in the live Chrome/Edge profiles under `AppData`, which is not mounted.

**The servers are unreachable from this session.** SSH blocked, proxy 403, `Network is unreachable` from the laptop VM, no Tailscale inside it. Measured, not assumed. The audit script exists so you can close that gap in about five minutes per server.

**The "2,000 existing files" were not where they were expected.** The connected folder holds ~150 non-dependency files. The real corpus is probably in the ~90 home folders that were never mounted.

## The canonical layer works

1,529 objects · 1,576 versions with 1:1 provenance and events · 1,448 canonicalized URLs across 928 domains · 74 evidence blobs verified by re-hash, 0 corrupt · all 9 invariants passing.

```bash
cd 03-skeleton
export PKOS_ROOT="../02-canonical/pkos-store"
PYTHONPATH=. python3 -m secondbrain status
PYTHONPATH=. python3 -m secondbrain history
PYTHONPATH=. python3 -m secondbrain search "voice agent"
PYTHONPATH=. python3 -m secondbrain validate --deep
```

Nothing here calls an LLM. The canonical layer is deterministic on purpose (§3), so it never depends on a model being available or behaving the same way twice.
