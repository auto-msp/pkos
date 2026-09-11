# The fleet — one table, three naming systems reconciled

Updated 2026-09-11, when BumbleBee joined.

There are **three** independent names for most of these machines and they do not
agree. The PKOS handoff uses Transformers names, the Airtable *AutoMSP
Infrastructure* table uses function names, and the tailnet uses its own
hostnames. Nobody is wrong; they just grew separately. Until they are
reconciled, "audit Ratchet" and "audit AutoMSP" sound like two jobs and are one
machine — so this table is the mapping.

| Transformers (PKOS) | Airtable name | Tailnet node | IP | Role | Audited? |
|---|---|---|---|---|---|
| **Perceptor** | RDP01 | — | 132.145.133.39 | ⭐ **MASTER** — the Second Brain lives here | ✅ |
| **Optimus Prime** | RDP02 | — | 150.136.95.118 | secondary backup tier | ✅ |
| **Megatron** | — | `moiz7tsvr01v` | 100.80.47.37 | ❌ **outside the trust boundary**; cold backup only, do not delete | ✅ |
| **Ironhide** | Adguard Server | `adguard` | 129.158.236.50 | Adguard / DNS blocker | ❌ |
| **Ratchet** | AutoMSP | `automsp` | 141.148.58.44 | Production 1 — Ruflo, Hermes, Claude Code, ECC | ❌ |
| **Prowl** | CloudPanel | — | 129.213.93.2 | CloudPanel — sites, web apps | ❌ |
| **WheelJack** | My-RDP | — | 150.136.67.246 | Production 2 — ERPNext, Structurizr, analytics | ❌ |
| **BumbleBee** | *(not yet listed)* | — | **150.136.35.253** | **NEW** — serving Dify at dify.coreitx.us.kg | ❌ |
| *(unnamed)* | Core - Oracle - Server | — | 158.101.117.121 | Airtable says "SSH Key not working" | ❌ |

## BumbleBee — what is known, and what is not

**Known, measured 2026-09-11:**
- `150.136.35.253` — ports **80 and 443 open**, port 22 blocked *from the cloud
  container* (which blocks 22 to every host on the internet, so this says
  nothing about the server itself).
- Same `150.136.0.0/16` OCI block as Optimus Prime and WheelJack, so almost
  certainly the same OCI region and tenancy.
- It already appears in your Airtable *AutoMSP Infrastructure* table — not by
  name, but as the Server IP of the **Dify** record (`dify.coreitx.us.kg`,
  status "Fully Working"), created today at 11:27.

**Not known, and not guessed:**
- Which SSH key it takes. The four unaudited servers each have their own; there
  is no `bumblebee_key`. Say which, and the audit step is ready.
- Whether the login user is `ubuntu` (as on Ironhide/Ratchet/Prowl/WheelJack)
  or `root`.
- Disk, memory, containers, what else it runs. That needs the audit script,
  which needs your machine — it is Step 2 of `pkos-part2.ps1`.
- It is **not on the tailnet**. The tailnet currently has six nodes:
  `adguard`, `automsp`, `moiz7tsvr01v`, `lenovo-laptop` and two phones.

## The two loose ends worth closing

1. **The Core-Oracle box at 158.101.117.121 has no Transformers name** and its
   SSH key is recorded as not working. It is the only machine in your own
   registry that is nameless.
2. **The naming systems should converge.** The PKOS knowledge graph already
   derives `Server` entities; once the audits land it can carry all three names
   as aliases of one entity, and "which machine is `automsp`?" stops being a
   question you answer from memory.
