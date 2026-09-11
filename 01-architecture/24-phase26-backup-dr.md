# Phase 26 — Backup and disaster recovery

**Status: COMPLETE.** 16 dedicated tests, all eight suites green.

---

## The question it answers

Not *"did a backup run?"* — every backup system answers that, and it is nearly
worthless. The question is:

> **How long ago did we last PROVE we could restore?**

Today produced three separate demonstrations of why that distinction matters:
a staging sync that logged `STARTED` every morning and had been dead since
**2026‑06‑25**; a 2am chain whose cleanup had not run since August, quietly
piling 796 MB into `/tmp`; and a vault tarball taken mid‑rsync that was 6.5 MB
short and looked completely normal.

So `--drill` is the centre of this module, not `--dest`. A fresh backup is
written with `proven: false` and a note saying so in its own manifest. Only a
passed drill flips it.

---

## What a drill actually does

It restores into a scratch **store**, not just a loose file — a drill that only
opens the database proves the database, not that a store can be stood up from
this backup, which is the real claim.

```
[PASS] manifest present
[PASS] canonical database present
[PASS] integrity_check
[PASS] foreign keys
[PASS] counts match the backup manifest        restored 4 vs manifest 4
[PASS] invariants hold                         0 failed check(s)
[PASS] every blob re-hashed                    ok=4 missing=0 corrupt=0
[PASS] jsonl mirror present (vendor-neutral copy)
[----] recovery point                          restoring this backup would lose
                                               1 object(s) and 1 version(s) of work
VERDICT: RESTORE PROVEN
```

Two details worth pointing at:

**The blob step reports `[----] unproven`, not `[PASS]`, when a backup carries
no evidence.** A database-only backup restores the *index of your knowledge*
and none of the bytes it cites. Calling that a pass would be the same lie as an
`rclone copy` that returns 0 having uploaded nothing.

**"Recovery point" states what restoring would LOSE.** A backup is a position
in time, and the useful number is not its age but the work that dies if you use
it.

---

## Three defects fixed

**`backup` was doing `copytree` on a live SQLite database.** That is the
torn-snapshot problem exactly — the same one that produced your short vault
archive this morning. Right name, plausible size, clean exit, inconsistent
contents. Now `VACUUM INTO`, whose output is consistent by construction, and
the result is integrity-checked before the manifest is written.

**The drill crashed on a corrupted backup.** `PRAGMA integrity_check` raises
`DatabaseError` on a malformed file, and the first version let it escape — so
the routine whose entire purpose is detecting corruption fell over the moment
it found some. "Your backup is unusable" has to arrive as a verdict, not a
traceback. Every probe now runs inside a handler, and once the database is
known malformed the remaining checks are **skipped and marked skipped**, rather
than producing confident-looking output read from a dead file.

**A stale smoke test.** Section 13 still drove the old `backup <dest>` /
`restore --verify` interface. Same rule as `graph` and `sync` before it.

---

## Tiers, and the blast-radius warning

`primary` (same machine) · `secondary` (another machine) · `offsite` (outside
the tenancy). `--status` reports each separately and warns:

- a tier with backups but **none ever restore-tested** — *"that is a
  hypothesis, not a backup"*
- a tier carrying **no evidence plane** — *"the database would restore; the
  bytes it cites would not"*
- **an empty tier** — *"copies inside one blast radius are one backup, not
  several"*

---

## Commands

```
secondbrain backup --dest DIR [--tier secondary] [--include-evidence]
secondbrain backup --drill DIR        restore into scratch and PROVE it
secondbrain backup --status --dest-list DIR1 DIR2
```

---

## What is deliberately still absent

**Retention/pruning is not implemented.** Deleting old backups is a destructive
operation on the last copies of things, and it needs the §97 gate — discover,
dry run, impact report, human approval — done properly rather than bolted on.
It is not claimed as done.

**In-place restore over a live store is not implemented either**, for the same
reason. `--drill` restores to scratch, which is safe and is what §93 actually
requires. Overwriting a live canonical store is a separate, gated act.
