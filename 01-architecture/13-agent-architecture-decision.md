# 13. Agent Architecture Decision

**SOW §3 · "Do NOT assume that a swarm is required merely because the workload is large."**

This session ran a five-agent swarm and it partly failed. That failure is the most useful evidence in this document, so it goes first.

## 13.1 What actually happened

Five read-only discovery workers launched in parallel. Outcome:

| Worker | Result |
|---|---|
| W1 laptop corpus | **completed** — 33 tool calls, 141k tokens, ~22 min, excellent output |
| W2 GitHub | **completed** — correctly diagnosed a proxy block and stopped rather than routing around it |
| W3 Google Drive | **killed mid-flight** by a session rate limit — 47 calls, 180k tokens, **wrote nothing to disk** |
| W4 Airtable | **killed mid-flight** — **164 tool calls, 228k tokens, wrote nothing to disk** |
| W5 audit script | **killed mid-flight** — 18 calls, 161k tokens, wrote nothing |

Three of five died at a shared session limit. W3 was recoverable only because it still held its context and could be told to persist. **W4's 164 tool calls of structural Airtable data were lost.** W5's work was re-done directly by the supervisor in less wall-clock time than the agent had already spent.

## 13.2 What that proves, concretely

**1. Parallel agents share one budget.** Five workers did not multiply throughput; they multiplied a shared, invisible consumption rate until it hit a wall. The failure was correlated, not isolated — precisely what §40 failure isolation is supposed to prevent, and the swarm did not provide it.

**2. Agent context is not durable state.** An agent that has done real work but not written it down has produced nothing. W4 is the proof. Deterministic pipelines checkpoint to disk; agents checkpoint to a context window that dies with them.

**3. Deterministic work does not need an agent.** W5's task — author a bash script — was pure authoring. Done directly it took less time, produced a tested artifact, and could not be killed by a shared limit.

**4. Agents earn their cost on interpretation.** W1 and W2 both did things deterministic code could not: W1 recognised that a 114 MB CSV was an Instagram export rather than a URL corpus, and that a "stale backup" was not redundant. W2 recognised that a 403 with no rate-limit headers meant a proxy allowlist rather than a quota, and — importantly — declined to expand its own access. Those are judgement calls.

## 13.3 The four architectures, evaluated

| | A. Single orchestrator | B. Supervisor + workers | C. Full swarm | D. Hybrid |
|---|---|---|---|---|
| Failure isolation | poor — one context, one death | good | **poor in practice** (shared budget) | **best** — deterministic work survives |
| Checkpointing | context only | context only | context only | **disk, per item** |
| Cost predictability | moderate | moderate | **worst** — observed | **best** |
| Observability | good | moderate | **poor** — three workers died invisibly | **best** — manifests + dead-letter |
| Concurrency | none | real | real | real where safe |
| Fit for §125 non-negotiables | weak | moderate | weak | **strong** |
| Human approval gates | manual | manual | hard to enforce across agents | **enforced in code** |

Scale check: ~17,312 laptop INCLUDE files, ~1,448 URLs today (potentially ~20k), 5 servers, 3+ email accounts, ~26 sources. Large — but **large and repetitive**, which is the deterministic case, not the agentic one.

## 13.4 Decision

**Architecture D — hybrid, with a strong deterministic core.**

```
                    CLAUDE OPUS 5 — architect / supervisor
                     (design, hard extraction, review, conflict resolution)
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
        DETERMINISTIC PIPELINES              BOUNDED AGENT WORKERS
        (secondbrain, stdlib Python)         (interpretation only)
        acquisition · hashing · manifests    capability discovery
        idempotency · versioning             ambiguous classification
        provenance · dedup · validation      cross-source reasoning
        indexing · export · backup           anomaly investigation
                    │                               │
                    └───────────────┬───────────────┘
                                    ▼
                            GLM 5.3 BULK LAYER
                    (tagging, summarization, entity candidates,
                     URL categorization — high volume, low stakes)
                                    ▼
                            VALIDATION LAYER
                          (deterministic invariants)
                                    ▼
                       CLAUDE OPUS 5 — high-value review
```

### Binding rules

1. **Anything that touches evidence, identity, provenance, versioning or deletion is deterministic code.** No agent writes to the canonical plane directly. Already true: every write goes through `secondbrain`.
2. **Agents are read-mostly and must persist within their first few tool calls.** W4's lesson, written into the operating procedure: an agent that has not written to disk has produced nothing.
3. **Cap concurrency at two or three** interpretation workers, never five. The observed limit is a shared budget, so parallelism past that point buys correlated failure.
4. **Every agent output is data, not authority.** It lands with `knowledge_state=INFERRED` or `SYNTHESIZED`, `generated_by`, `model`, `confidence` (§106), and is never presentable as source evidence (§15).
5. **GLM 5.3 never touches architecture, schema, identity or deletion** (§2.3), and never sees content classified `SENSITIVE` or above (§32).
6. **Destructive operations have no agent path at all** (§98). `secondbrain cleanup` refuses without `--dry-run`; the audit script contains no mutating command. Capability is removed at the source rather than governed by policy.

### Where agents are genuinely worth it

Capability discovery (does this connector paginate? does it preserve formulas? — W3 answered exactly this) · ambiguous classification (the 4,447 extensionless files) · cross-source reasoning (§63 research→decision→implementation) · conflict adjudication (§20) · anomaly investigation (why does SAP dominate a corpus that should look like AutoMSP?).

### Where they are not

File walking · hashing · dedup · manifest writing · schema validation · index building · backup · anything with a deterministic answer and a large N.

## 13.5 Note on the two-LLM design

§2 specifies Claude Opus 5 + GLM 5.3. **GLM 5.3 is not available as a worker model in this session** — subagents here run on Claude models only. The split is therefore *designed and specified* but not *exercised*, and nothing in this session should be read as having tested it. Implementation belongs in the Phase 4+ enrichment pipeline, calling GLM via API from deterministic pipeline code — which is also the right architecture, since it puts the model behind a checkpointed, restartable job rather than inside an agent's context.
