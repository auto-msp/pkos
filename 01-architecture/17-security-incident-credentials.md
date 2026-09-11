# 17. Security Incident — Credential Material in Canonical Content

**SOW §28, §31, §32, §34, §125.14 · Detected and remediated 2026-09-08**

## What happened

A scan of object bodies found **300 canonical objects containing live secret material**. They had been ingested during Phase 6 along with everything else, and were sitting in searchable content.

| Secret type | Objects |
|---|---:|
| OpenAI-style keys (`sk-…`) | 164 |
| Bearer tokens | 59 |
| PEM blocks (certificates / RSA / OPENSSH) | 35 |
| Private keys (`BEGIN … PRIVATE KEY`) | 28 |
| Anthropic keys (`sk-ant-…`) | 24 |
| Google API keys (`AIza…`) | 24 |
| GitHub tokens (`ghp_/gho_/ghs_…`) | 9 |
| GCP service-account JSON | 7 |
| Telegram bot tokens | 6 |
| Slack tokens | 6 |
| AWS access key IDs (`AKIA…`) | 5 |

Concentrated in three places:

| Location | Objects |
|---|---:|
| `06 - Documents/GDrive Word Files/Credentials & Keys` | 94 |
| `Text Files/01 - API Keys & Credentials` (264 files ingested) | 63 |
| `Claude Chat/chat_archive` | 20 |

The second and third matter beyond this system: those are folders where credentials were being *stored as plain text files*, and a chat archive that captured keys pasted during past debugging sessions.

## The validation gap that let it through

`validate` had a check called `no_secret_values_stored`. **It only inspected the `credential_registry` table.** It passed — reporting "0 credential rows look like they contain a secret VALUE" — while 300 object bodies held live keys.

A check that passes for the wrong reason is worse than no check: it produces false assurance. This is the most serious defect found in the system so far, and it was mine.

**Fixed.** `validate` now carries `no_secret_values_in_bodies`, which scans every current-version body against 12 credential patterns. It runs on every validate, and it fails loudly.

## Remediation performed

`secondbrain secrets --redact` — a new command, deliberately two-step (scan, then redact only when asked).

For each of the 300 objects:

1. **Body replaced** with a marker naming which secret types were present.
2. **New version created** — `change_type='corrected'`, with the reason recorded. The prior version and its content hash remain in the version chain.
3. **Event logged** (`MODIFIED`, previous → new classification), so the change is auditable.
4. **Reclassified** `RESTRICTED`, retention `PERMANENT`.
5. **Evidence plane untouched.** The original bytes remain content-addressed under their original hash.

Nothing was destroyed and nothing was silent — the §125.10 rule holds. Versions went 18,014 → 18,314; the 300 new versions *are* the redactions.

**Verified after:** secret scan returns 0. Search index rebuilt from the redacted content — 10,482 objects, no credentials. All 10 validate checks pass.

## This does not make the credentials safe

Redaction removed them from the *searchable knowledge layer*. It did nothing about the underlying exposure:

- The plaintext files still sit in `Downloads` and in **Google Drive**.
- They exist in Claude chat archives.
- Several were pasted into terminals and chat during this and earlier sessions.

**Every credential in those folders should be treated as compromised and rotated.** This is the third credential incident recorded on this project — NVIDIA/OpenRouter keys in an earlier session, the hardcoded Telegram bot token in `bos_health_monitor.py`, and now this. Three occurrences is a process gap, not bad luck.

Minimum controls worth adding:
1. Rotate everything in `Text Files/01 - API Keys & Credentials` and `GDrive Word Files/Credentials & Keys`.
2. Move secrets out of files and into a secret manager or per-project `.env` with `chmod 600`, never in a synced folder.
3. Pre-commit secret scanning on every repo.
4. `secondbrain secrets` on a schedule (**not enabled — requires explicit approval**).

## Related discovery: private keys stored in Downloads

`Downloads\10 - Tools & Software\Putty Keys New\` holds **45 key files** — 20 private keys across PuTTY, OpenSSH and PEM formats, for infrastructure well beyond the known fleet: 3CX/Hetzner, a PBX, CloudPanel, Core, and a Stalwart recovery key.

Only one was ingestible by extension — `stalwart_recovery_key.txt`, an OpenSSH private key saved as `.txt`. It was caught and redacted. The `.ppk`, `.pem` and extensionless keys were never ingested because they are not in the §75 include list.

That is luck, not design. A private key with a `.txt` extension defeated the extension-based classifier, and the only thing that caught it was the body scan built in response to this incident.

## Fleet correction — six Autobots, not five

The PuTTY session registry resolved the server inventory the SOW could not:

| PuTTY session | Name | Host | User |
|---|---|---|---|
| Adguard Server | **Ironhide** | 129.158.236.50 | `ubuntu` |
| AutoMSP | **Ratchet** | 141.148.58.44 | `ubuntu` |
| CloudPanel | **Prowl** | 129.213.93.2 | `ubuntu` |
| My-RDP | **WheelJack** | 150.136.67.246 | `ubuntu` |
| RDP01 | **Perceptor** | 132.145.133.39 | `ubuntu` |
| RDP02 | **Optimus Prime** | 150.136.95.118 | `ubuntu` |
| — | *Megatron* (MOIZ7TSVR01V) | 100.80.47.37 | excluded from trust boundary |

**Two servers were never in scope at all**: Prowl (CloudPanel) and WheelJack (My-RDP). Neither appears on the tailnet. The SOW said five; the real count is six trusted hosts plus Megatron, and the key folder implies more infrastructure again.

**Why the earlier logins failed:** every session uses `ubuntu@`, not `root@`, and the keys are in **PuTTY `.ppk` format**, which OpenSSH cannot read. Nine key/user combinations were tried and all nine were the wrong format.

Keys for the two blocked hosts:
- `Putty Keys New\newputtykeys\AdguardPvt.ppk.ppk` → Ironhide
- `Putty Keys New\newputtykeys\automsppvt.ppk` → Ratchet
