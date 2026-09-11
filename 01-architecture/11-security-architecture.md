# 11. Security Architecture

**SOW §26–§35, §98, §108 · Status: `PARTIALLY IMPLEMENTED`**

## 11.1 Trust zones (§27)

| Zone | Contains | Rule |
|---|---|---|
| 1 External | Google, GitHub, Airtable, Notion, Meta, LinkedIn, Anthropic, OpenAI, Oracle | untrusted; authorized access only |
| 2 Acquisition | connectors, API workers, importers, the audit script | **read-only by default** |
| 3 Processing | parsers, OCR, transcription, LLM enrichment | no write access to Zone 4 evidence |
| 4 Canonical | `canonical.sqlite3`, mirror, provenance | write only through `secondbrain` |
| 5 Derivation | FTS, vectors, graph | fully destroyable |
| 6 Administration | backup, monitoring, infra | separate credentials |

An agent does not cross a zone boundary without explicit authorization. The clearest current instance: the server audit script is Zone 2 and is **structurally incapable** of Zone 6 action — it contains no mutating command, verified by automated grep.

## 11.2 Agent permission model (§33) — what is actually enforced

**Default: READ ONLY.** This was enforced throughout Phase 0, not merely intended:

- every discovery worker ran read-only against source data
- `device_bash` cannot delete on the user's machine by design; no delete permission was requested
- the audit script forbids `rm` (outside its own mktemp dir), `mv`, `dd`, `docker prune|rm|stop`, `systemctl start|stop|restart`, package installs, `kill`, `crontab -r`, `sudo`, and **all network calls** — 11 automated checks, all passing
- `secondbrain cleanup` **refuses** without `--dry-run`, exit 2

§98: no autonomous agent gets unrestricted destructive authority. The audit script is the template — capability removed at the source rather than governed by policy.

## 11.3 Credential architecture (§28–§30)

`credential_registry` stores `storage_location` — *where* a secret lives — and **never the value**. A `validate` check greps for anything resembling a key and fails if found.

**Cookies are credentials** (§28). No browser session token was captured this session.

### Open incident — needs action

Prior context records that live API keys were **pasted in plaintext into a chat session** during debugging: 9 NVIDIA NIM keys, a "conduit" proxy key, and an OpenRouter key. They were flagged for rotation.

Per §34, the workflow is: DETECT → CONTAIN → PRESERVE EVIDENCE → **REVOKE** → ASSESS → RESTORE → VERIFY → ROTATE → DOCUMENT. Detection and documentation happened. **Revocation status is unconfirmed.** Until each is confirmed revoked or rotated, treat them as compromised — a key in a chat log is a key in an unknown number of places.

This is independent of the PKOS build and should not wait for it.

## 11.4 LLM data governance (§31, §32)

Classification: `PUBLIC` `INTERNAL` `PRIVATE` `SENSITIVE` `HIGHLY_SENSITIVE` `RESTRICTED`, applied per object, **more restrictive wins** on inheritance conflict. Default is `PRIVATE`; server audits are ingested as `SENSITIVE`.

Before content reaches a model: CLASSIFY → determine sensitivity → apply model policy → **redact** → send minimum necessary → record the processing. `SENSITIVE` and above defaults toward local/private processing.

The two-LLM split (§2) has a security dimension, not just a cost one: GLM 5.3 handles high-volume classification and tagging, Claude Opus 5 handles architecture and hard extraction. Routing decisions must be made on **classification**, not convenience — a bulk worker should never see `HIGHLY_SENSITIVE` content because the batch happened to include it.

Every AI-derived object carries `generated_by`, `model`, `model_version`, `generated_at`, `source_objects`, `prompt_reference`, `confidence`, `validation_status` (§106), and `knowledge_state` distinguishes `INFERRED` and `SYNTHESIZED` from `ORIGINAL`. **An AI inference is never presentable as source evidence** (§15).

## 11.5 Legal/access boundary (§108) — held

Only authorized APIs, permitted exports and legitimate account access were used. When GitHub returned 403, the response was to **document the block and stop** — not to scrape HTML, not to try an alternate host, not to request expanded proxy access. A blocked path is a finding, not an obstacle to route around.

## 11.6 Audit and incident response (§34, §35)

`audit_event` records category, action, actor, target, outcome, detail and job id for every system action, separately from `event`, which records how *knowledge* changed. Both are append-only.

Retention: `audit_event` and `event` are `PERMANENT` — they are what makes system history reconstructible; a truncated audit log defeats §35 entirely. Their volume is trivial (518 KB for 1,576 events).

Incident procedures needed but **not yet written**: credential leak (partially exercised, see 11.3), unauthorized access, compromised server, data corruption, ransomware, destructive agent behavior, accidental deletion, GitHub exposure. Deliverable #15 schedules these; they are cheap to write and expensive to lack.
