# Domain migration notes

Branch `claude/domain-migration-and-security`. Hostnames under `automsp.us` / `automsp.store` were moved by this mapping, keeping the subdomain label:

- To `automsp.cloud`: portal, bos, bos-dev, crm, erp, mautic, nextcloud, pbx, analytics
- To `coreitx.us.kg`: coder, octogent, openclaw, paperclip, mission-control, qr, db, evolution, search-council, voicebox, voice, omniroute, structurizr, portainer, npm, cloudpanel, adguard, invoice, harness, jarvis, n8n, build

Everything else was left alone. `FLEET.md` contains no `automsp.us` / `automsp.store` hostnames (it already uses `*.coreitx.us.kg`), so it needed no change.

## Changed (22 occurrences)

| File:line | Old | New |
|---|---|---|
| 01-architecture/04-server-rdp02-findings.md:302 | `n8n.automsp.us` | `n8n.coreitx.us.kg` |
| 01-architecture/04-server-rdp02-findings.md:357 | `n8n.automsp.us` | `n8n.coreitx.us.kg` |
| 01-architecture/04-server-rdp02-findings.md:363 | `n8n.automsp.us` | `n8n.coreitx.us.kg` |
| 01-architecture/04-server-rdp02-findings.md:407 | `n8n.automsp.us` | `n8n.coreitx.us.kg` |
| 01-architecture/04-server-rdp02-findings.md:410 | `n8n.automsp.us` | `n8n.coreitx.us.kg` |
| 01-architecture/04b-fleet-audit-summary.md:53 | `n8n.automsp.us` | `n8n.coreitx.us.kg` |
| 03-skeleton/secondbrain/adapters/n8n.py:70 | `n8n.automsp.us` | `n8n.coreitx.us.kg` |
| 03-skeleton/tests/test_adapters_graph.py:202 | `n8n.automsp.us` | `n8n.coreitx.us.kg` |
| 03-skeleton/tests/test_adapters_graph.py:245 | `n8n.automsp.us` | `n8n.coreitx.us.kg` |
| 90-evidence/airtable/base-appSmkEFE8UCSwjag.json:1 (occurrence 1 on minified single-line JSON) | `erp.automsp.us` | `erp.automsp.cloud` |
| 90-evidence/airtable/base-appSmkEFE8UCSwjag.json:1 (occurrence 2 on minified single-line JSON) | `mautic.automsp.us` | `mautic.automsp.cloud` |
| 90-evidence/airtable/base-appSmkEFE8UCSwjag.json:1 (occurrence 3 on minified single-line JSON) | `structurizr.automsp.store` | `structurizr.coreitx.us.kg` |
| 90-evidence/airtable/base-appSmkEFE8UCSwjag.json:1 (occurrence 4 on minified single-line JSON) | `voice.automsp.us` | `voice.coreitx.us.kg` |
| 90-evidence/airtable/base-appSmkEFE8UCSwjag.json:1 (occurrence 5 on minified single-line JSON) | `search-council.automsp.us` | `search-council.coreitx.us.kg` |
| 90-evidence/airtable/base-appSmkEFE8UCSwjag.json:1 (occurrence 6 on minified single-line JSON) | `search-council.automsp.us` | `search-council.coreitx.us.kg` |
| 90-evidence/airtable/base-appSmkEFE8UCSwjag.json:1 (occurrence 7 on minified single-line JSON) | `voicebox.automsp.us` | `voicebox.coreitx.us.kg` |
| 90-evidence/airtable/base-appSmkEFE8UCSwjag.json:1 (occurrence 8 on minified single-line JSON) | `bos.automsp.us` | `bos.automsp.cloud` |
| 90-evidence/airtable/base-appSmkEFE8UCSwjag.json:1 (occurrence 10 on minified single-line JSON) | `omniroute.automsp.store` | `omniroute.coreitx.us.kg` |
| 90-evidence/airtable/base-appSmkEFE8UCSwjag.json:1 (occurrence 11 on minified single-line JSON) | `octogent.automsp.us` | `octogent.coreitx.us.kg` |
| 90-evidence/airtable/base-appSmkEFE8UCSwjag.json:1 (occurrence 12 on minified single-line JSON) | `n8n.automsp.us` | `n8n.coreitx.us.kg` |
| 90-evidence/airtable/base-appkFemlPJYiaY72e.json:1 (occurrence 1 on minified single-line JSON) | `jarvis.automsp.us` | `jarvis.coreitx.us.kg` |
| 90-evidence/airtable/base-appkFemlPJYiaY72e.json:1 (occurrence 2 on minified single-line JSON) | `openclaw.automsp.us` | `openclaw.coreitx.us.kg` |

## Intentionally NOT changed (36 occurrences)

| File:line | Value | Reason |
|---|---|---|
| 01-architecture/03-account-inventory.md:13 | `automsp.us` | email address at the domain (must not change) |
| 01-architecture/04-server-rdp02-findings.md:303 | `nemoclaw.automsp.us` | subdomain 'nemoclaw' not in the migration mapping |
| 01-architecture/04-server-rdp02-findings.md:309 | `automsp.us` | bare domain (explicitly out of scope) |
| 01-architecture/04-server-rdp02-findings.md:357 | `nemoclaw.automsp.us` | subdomain 'nemoclaw' not in the migration mapping |
| 01-architecture/04-server-rdp02-findings.md:359 | `automsp.us` | bare domain (explicitly out of scope) |
| 01-architecture/04-server-rdp02-findings.md:363 | `automsp.us` | bare domain (explicitly out of scope) |
| 01-architecture/04-server-rdp02-findings.md:394 | `automsp.store` | bare domain (explicitly out of scope) |
| 01-architecture/04-server-rdp02-findings.md:398 | `automsp.store` | bare domain (explicitly out of scope) |
| 01-architecture/04-server-rdp02-findings.md:407 | `automsp.us` | bare domain (explicitly out of scope) |
| 01-architecture/04-server-rdp02-findings.md:408 | `nemoclaw.automsp.us` | subdomain 'nemoclaw' not in the migration mapping |
| 01-architecture/04-server-rdp02-findings.md:408 | `automsp.us` | bare domain (explicitly out of scope) |
| 01-architecture/04-server-rdp02-findings.md:418 | `automsp.us` | bare domain (explicitly out of scope) |
| 01-architecture/04-server-rdp02-findings.md:418 | `automsp.store` | bare domain (explicitly out of scope) |
| 01-architecture/04b-fleet-audit-summary.md:41 | `automsp.store` | bare domain (explicitly out of scope) |
| 01-architecture/20-phase22-knowledge-graph.md:113 | `automsp.us` | bare domain (explicitly out of scope) |
| 01-architecture/22-phase24-agent-boundary.md:108 | `automsp.store` | bare domain (explicitly out of scope) |
| 03-skeleton/secondbrain/graph.py:442 | `automsp.us` | bare domain (explicitly out of scope) |
| 90-evidence/airtable/base-appSmkEFE8UCSwjag.json:1 (occurrence 9 on minified single-line JSON) | `automsp.us` | bare domain (explicitly out of scope) |
| 90-evidence/w1-downloads-inventory.jsonl:32090 | `automsp.us` | bare domain (explicitly out of scope) - part of a local file name in a path inventory |
| 90-evidence/w1-downloads-inventory.jsonl:46823 | `automsp.us` | bare domain (explicitly out of scope) - part of a local file name in a path inventory |
| 90-evidence/w1-downloads-inventory.jsonl:56171 | `AutoMSP.US` | bare domain (explicitly out of scope) - part of a local file name in a path inventory |
| 90-evidence/w1-downloads-inventory.jsonl:56200 | `automsp.store` | bare domain (explicitly out of scope) - part of a local file name in a path inventory |
| 90-evidence/w1-downloads-inventory.jsonl:56201 | `automsp.us` | bare domain (explicitly out of scope) - part of a local file name in a path inventory |
| 90-evidence/w1-downloads-inventory.jsonl:56202 | `automsp.us` | bare domain (explicitly out of scope) - part of a local file name in a path inventory |
| 90-evidence/w1-downloads-inventory.jsonl:56203 | `automsp.us` | bare domain (explicitly out of scope) - part of a local file name in a path inventory |
| 90-evidence/w1-downloads-inventory.jsonl:56204 | `automsp.us` | bare domain (explicitly out of scope) - part of a local file name in a path inventory |
| 90-evidence/w1-downloads-inventory.jsonl:56446 | `automsp.store` | bare domain (explicitly out of scope) - part of a local file name in a path inventory |
| 90-evidence/w1-downloads-inventory.jsonl:56447 | `automsp.us` | bare domain (explicitly out of scope) - part of a local file name in a path inventory |
| 90-evidence/w1-downloads-inventory.jsonl:56448 | `automsp.us` | bare domain (explicitly out of scope) - part of a local file name in a path inventory |
| 90-evidence/w1-downloads-inventory.jsonl:56533 | `automsp.store` | bare domain (explicitly out of scope) - part of a local file name in a path inventory |
| 90-evidence/w1-downloads-inventory.jsonl:56534 | `automsp.store` | bare domain (explicitly out of scope) - part of a local file name in a path inventory |
| 90-evidence/w1-downloads-inventory.jsonl:56535 | `automsp.us` | bare domain (explicitly out of scope) - part of a local file name in a path inventory |
| 99-runbooks/RUNBOOK-server-audit.md:21 | `automsp.us` | bare domain (explicitly out of scope) |
| 99-runbooks/push-to-github.ps1:63 | `automsp.us` | email address at the domain (must not change) |
| 90-evidence/w1-downloads-inventory.jsonl:56210 | `mail.automsp.store-zone` | subdomain 'mail' not in the migration mapping (also part of a local file name) |
| 90-evidence/w1-downloads-inventory.jsonl:56211 | `mail.automsp.store-zone` | subdomain 'mail' not in the migration mapping (also part of a local file name) |

## Ambiguous items needing a human decision

1. `nemoclaw.automsp.us` (3 mentions, `01-architecture/04-server-rdp02-findings.md` lines 303, 357, 408): the label `nemoclaw` is not in either mapping list, so it was left unchanged. Decide where it moves.
2. `mail.automsp.store` (2 mentions in `90-evidence/w1-downloads-inventory.jsonl`, lines 56210-56211): `mail` is not in either mapping list, so it was left unchanged. These are also real local file names.
3. Historical audit text: `01-architecture/04-server-rdp02-findings.md` and `04b-fleet-audit-summary.md` record a real certificate-renewal audit of the n8n host. The hostname was rewritten as instructed, but the "Zone needed" column and the surrounding prose still talk about the `automsp.us` Cloudflare zone and token scope, which is now inconsistent for a `coreitx.us.kg` name. Review those paragraphs.
4. Evidence snapshots under `90-evidence/airtable/` were rewritten by the mapping (11 hostnames in `base-appSmkEFE8UCSwjag.json`, 2 in `base-appkFemlPJYiaY72e.json`). These are meant to be point-in-time captures, so they no longer match what Airtable held on the capture date. Both files still parse as valid JSON. Revert these two files if you want the evidence kept verbatim.
5. Code and tests: `03-skeleton/secondbrain/adapters/n8n.py` (help text) and `03-skeleton/tests/test_adapters_graph.py` (lines 202, 245) used `n8n.automsp.us` as an example `--identity` value. They now say `n8n.coreitx.us.kg`. The identity is a free-form operator-supplied string, so behaviour is unchanged, but any already-ingested store that used the old identity string will treat the new string as a different n8n instance.

## Cloudflare tunnel mentions (listed only, not changed)

| File:line | What it mentions |
|---|---|
| 01-architecture/04-server-rdp02-findings.md:56 | `cloudflared` container, twice (n8n stack and a standalone one) |
| 01-architecture/04-server-rdp02-findings.md:111 | container name `cf-tunnel-bos` |
| 90-evidence/airtable/base-appkFemlPJYiaY72e.json:1 | container names `n8n-cloudflared` and `cloudflared` (minified single-line JSON) |
| 90-evidence/w1-downloads-inventory.jsonl:46914 | file name `CloudFlare Tunnel API Token(1).txt` |
| 90-evidence/w1-downloads-inventory.jsonl:46915 | file name `CloudFlare Tunnel API Token(2).txt` |
| 90-evidence/w1-downloads-inventory.jsonl:46916 | file name `CloudFlare Tunnel API Token.txt` |
| 90-evidence/w1-downloads-inventory.jsonl:55596 | file name `CloudFlare Tunnel API Token.txt` |

No `cfargotunnel` strings exist in the repo. Other hits for the word "tunnel" (TunnelBear installer, SSH reverse-tunnel checks in `pkos-session-forensics.sh`) are unrelated to Cloudflare and are not listed.

