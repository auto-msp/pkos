# 3. Account Inventory

**SOW §45, §46 · "Do not assume one." An empty row is a discovery gap, not evidence of absence.**

| Vendor | Accounts found | Verified | How discovered | Isolation status |
|---|---|---|---|---|
| Google | **1** — `openmynewopportunities@gmail.com` | yes, via connector | live connector | others **UNDISCOVERED** |
| GitHub | **1 candidate** — `mynewopportunities` | **no** | `.git/config` remote + commit-author email on device | API-unverified |
| GitHub org | `auto-msp` | **no** | prior context only | no metadata obtainable |
| Airtable | unknown | — | not executed | deferred |
| Oracle Cloud | ≥1 tenancy | **no** | inferred from server IPs | registered as `oci-tenancy` |
| Notion / Gumroad / Instagram / Facebook / LinkedIn / Zoho / Outlook / OpenAI / Anthropic | unknown | — | not started | — |
| Corporate identity | `moiz.contractor@automsp.us` | from profile | prior context | distinct from the Google account above |

## What this table means

Two email identities are already in evidence — a personal Gmail and a corporate AutoMSP address — and prior context also references a part-time role at a separate managed-services firm. **That is three plausible identity domains before discovery has properly started.** Gmail/Outlook/Zoho (§44 items 20-22) will almost certainly span more than one account each.

§46 requires that `GMAIL/ACCOUNT-A` and `GMAIL/ACCOUNT-B` stay separately identifiable even when their messages land in one search index. The schema enforces this structurally: `source → account → profile_workspace → source_object → object`, with `UNIQUE(source_id, account_id, native_id)`. The `validate` command has a dedicated invariant — `account_boundaries_preserved` — that fails if one source object is ever attributed to two accounts. It currently passes on 1,576 source objects.

## Required before any email phase

For each of Gmail, Outlook and Zoho, the answer to "how many accounts?" must be **stated by you and recorded with `discovered_via`**, not inferred. Ingesting mail under a wrong or merged account identity is one of the few errors in this design that is genuinely expensive to undo, because provenance would be wrong at the root.
