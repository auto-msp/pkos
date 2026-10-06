# Security and DPDP review

Scope: every tracked file on branch `claude/domain-migration-and-security` (base `main`, commit `dec65d4`). The repository `auto-msp/pkos` is **public** (confirmed through the GitHub API). No secret value appears in this report; secrets are identified by file path and type only.

Method: pattern scans for known key formats (AWS, GitHub, OpenAI/Anthropic, Slack, Google, Stripe, Airtable, JWT, PEM/private-key blocks, URLs with embedded credentials), generic `password/secret/token=` assignments, long hex strings, a structural walk of the JSON evidence files, IPv4 and e-mail extraction, and a read of the Python source and shell/PowerShell runbooks for unsafe input handling.

## Summary

| Severity | Count | Fixed in this PR |
|---|---:|---:|
| Critical | 1 | partly (removed from HEAD, still in history) |
| High | 3 | 0 |
| Medium | 4 | 2 |
| Low | 5 | 1 |

Secret findings: 2 (type: gateway access tokens), plus 2 unverified synthetic-looking test strings.

## Critical

**C1. Live access tokens committed in a public repo (2 secrets).**
- File: `90-evidence/airtable/base-appkFemlPJYiaY72e.json`, `Notes` field of two records in the "AI coding agents" table (the OpenClaw / Jarvis web gateways).
- Type: URL-embedded gateway access token (32+ character hex string), one per record.
- The runbook `99-runbooks/pkos-part2.ps1` (lines 170-172) already confirms these are real access tokens.
- Fixed: both values replaced with `[REDACTED - access token removed, rotate]` in the working tree; the JSON still parses.
- Not fixed, needs you: the original values remain in git history and in any clone or fork made while the repo was public. **Rotate both tokens now.** Consider purging history (`git filter-repo`) or making the repo private.

## High

**H1. The repository is public and contains a full infrastructure map.**
- Public IPv4 addresses of production servers appear in 20 files (distinct addresses per file in brackets): `90-evidence/airtable/base-appkFemlPJYiaY72e.json` [7], `90-evidence/airtable/base-appSmkEFE8UCSwjag.json` [6], `PKOS-HANDOFF.md` [6], `NEXT-STEPS.md` [6], `90-evidence/putty-sessions.csv` [6], `FLEET.md` [9], `START-HERE.md` [1], `99-runbooks/RUNBOOK-server-audit.md` [2], `99-runbooks/pkos-part2.ps1` [7], `01-architecture/17-security-incident-credentials.md` [6], `01-architecture/04b-fleet-audit-summary.md` [5], `96-perceptor-scripts/vault-sync-to-staging.sh` [2], `01-architecture/01-current-state-architecture.md` [2], `01-architecture/19-megatron-to-perceptor-migration.md` [3], `01-architecture/04-07-infrastructure-audits-BLOCKED.md` [2], `01-architecture/15-implementation-roadmap.md` [2], `01-architecture/04-server-rdp02-findings.md` [1], `90-evidence/w1-downloads-inventory.jsonl` [1], `90-evidence/airtable/airtable-estate.json` [1], `99-runbooks/push-to-github.ps1` [1]. Tailnet addresses (100.x) were not counted.
- Combined with SSH user names, container and stack names, certificate expiry dates, open-port tables and the incident write-up, this gives an attacker a ready target list.
- Not fixed (changing it would gut the documents). Recommended: make the repo private, or move `FLEET.md`, `01-architecture/04*`, `01-architecture/17*`, `90-evidence/` and `99-runbooks/` into a private repo.

**H2. SSH session registry with key-file locations.** `90-evidence/putty-sessions.csv` lists 12 PuTTY sessions: host IP, port, `ubuntu` login and the local path of each private key (`.ppk`). No key material is present, but it names the exact key files and hosts. Not fixed; move to the private repo.

**H3. Map of where plaintext credentials live on the laptop and Drive.** `01-architecture/17-security-incident-credentials.md` and `90-evidence/w1-downloads-inventory.jsonl` name the folders and files that hold credentials (`Credentials & Keys`, `01 - API Keys & Credentials`; 101 key-file names such as `.pem`/`.ppk`/`.env`; entries named like "CloudFlare Tunnel API Token"). Only names, no values. The incident document itself states that every credential in those folders must be treated as compromised and rotated. Confirm that the rotation was completed. Not fixed.

## Medium

**M1. Personal identity documents named in the public inventory (DPDP Act).** `90-evidence/w1-downloads-inventory.jsonl` (lines 46377, 46378, 46392, 46396-46400, 46403, 46404, 46780, 49114-49116, 55528, 56441) lists files named after Aadhaar, PAN, passport and voter ID documents, a passport update letter, and an SBI video-KYC note. Contents are not in the repo, but their existence and location are. For a data fiduciary under the DPDP Act this is unnecessary disclosure of personal-data locations. Not fixed (evidence file); recommended: remove those lines or move the inventory to a private store.

**M2. Local Windows account name and absolute paths published.** `C:\Users\<account>\Downloads\...` appears in `90-evidence/putty-sessions.csv`, `99-runbooks/Clean-Downloads.ps1` (93 lines), `99-runbooks/pkos-part2.ps1`, `NEXT-STEPS.md`, `PKOS-HANDOFF.md`, `START-HERE.md`, `00-discovery/W1-laptop-corpus-report.md` and others. Minor on its own, useful for targeted phishing and for guessing key locations. Not fixed.

**M3. Tar extraction path traversal in bundle restore.** `03-skeleton/secondbrain/sync.py` (apply path) called `tarfile.extractall()` on members selected only by `isfile()`; a crafted bundle with absolute or `..` member names could write outside the evidence directory. Bundles are checksummed against a manifest shipped inside the same bundle, so an attacker who can tamper with the bundle can also fix the checksums. **Fixed:** the restore now refuses any bundle with an absolute path or `..` in a member name, returning a refusal. All 13 test scripts still pass. Remaining hardening idea: pass `filter="data"` to `extractall` (Python 3.12+).

**M4. `.gitignore` did not work for its first rule, and had no credential patterns.** The file began with a UTF-8 byte-order mark, so the `__pycache__/` rule never matched. There were also no ignore rules for `.env`, `*.pem`, `*.ppk`, `*.key` or service-account JSON. **Fixed:** BOM removed and credential patterns added.

## Low

**L1. Possibly real key in a test fixture.** `03-skeleton/tests/test_adapters_graph.py` (around line 351) contains a Notion-style `ntn_...` key in a test string, and line 313/315 contain fake-looking API key strings. They look synthetic (patterned tails) but the Notion one has a realistic shape. Confirm it is not a real key; replace it with an obviously fake string. Not changed.

**L2. Bearer / JWT-looking string in a test fixture.** `03-skeleton/tests/test_adapters_graph.py:88` holds `Bearer eyJ...` used to test redaction. Confirm it is synthetic. Not changed.

**L3. Personal e-mail address of the owner in 9 files** (`00-discovery/W2-github-report.md`, `W3-google-drive-report.md`, `01-architecture/02-digital-trace-inventory.md`, `03-account-inventory.md`, `18-phase14-claude-history.md`, `90-evidence/w3-gdrive-inventory.json`, `99-runbooks/pkos-part2.ps1`, `NEXT-STEPS.md`, `90-evidence/airtable/base-appSmkEFE8UCSwjag.json`), plus work addresses at the company domains in `03-account-inventory.md`, `99-runbooks/push-to-github.ps1` and the Airtable snapshot. They are the founder's own accounts, so this is a disclosure choice, not a leak of third-party data. No third-party personal data (customer names, phone numbers, government IDs) was found in docs, logs or sample data; test e-mails use reserved example/`.test` domains.

**L4. Zip extraction has no size limit.** `03-skeleton/secondbrain/adapters/_archive.py` and `adapters/claude_export.py` correctly reject absolute and `..` entry names, but do not cap uncompressed size or entry count (zip-bomb risk on an untrusted export). Operator-supplied input only. Not fixed.

**L5. Minor input-handling notes (no action required).** SQL built with string formatting in `export.py` (`SELECT * FROM %s`) and `search.py` uses constant, code-defined table and column lists, not user input. `VACUUM INTO '%s'` in `dr.py` and `sync.py` escapes single quotes. `bin/measure-vault-cost.py:115` prints a copy-paste shell hint containing the database path inside a quoted string; it is output only and is not executed. `99-runbooks/pkos-part2.ps1` uses `StrictHostKeyChecking=accept-new` (trust on first use) and `ExecutionPolicy Bypass` in usage text; acceptable for a one-off operator script. No `eval`, `exec`, `shell=True`, `os.system`, `pickle` or unsafe YAML loading exists in the code.

## What was changed in this PR for security

1. Redacted the two gateway tokens in `90-evidence/airtable/base-appkFemlPJYiaY72e.json` (C1, partial).
2. Added the unsafe-path guard to bundle restore in `03-skeleton/secondbrain/sync.py` (M3).
3. Removed the BOM and added credential ignore patterns in `.gitignore` (M4).

## Recommended next steps, in order

1. Rotate the two OpenClaw / Jarvis gateway tokens.
2. Make `auto-msp/pkos` private, or purge history and move the infrastructure and evidence material to a private repo.
3. Confirm that the credentials named in `17-security-incident-credentials.md` were rotated.
4. Decide whether the identity-document file names and the SSH session list stay in any shared repo.
5. Add pre-commit secret scanning (gitleaks or similar) before the repo is public again.
