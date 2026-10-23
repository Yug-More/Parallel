# Durable local agent coordination

Current Phase 10–12 behavior: [trained intelligence, selected evidence and operational hardening](INTELLIGENCE_HARDENING.md). Earlier milestone sections retain their historical scope.

The supported agents perform real deterministic computation over persisted workspace data. They do not execute code, browse, call models, modify external systems, or implement a task on a user's behalf.

## Contracts

`GET /agent-contracts` describes six versioned identities. The original three are:

- **`local.status.v1`** counts active task states, records task facts and accepted decisions with source IDs, and saves a status report.
- **`local.dependencies.v1`** traverses prerequisite chains, identifies unfinished prerequisites and explicit Blocked states, and lists work ready by dependency state. It can analyze a blocked task.
- **`local.handoff.v1`** is a coordinator: its persisted plan delegates to the status and dependency contracts, waits for both child outcomes, verifies context fingerprints and composes a handoff. The child runs have distinct computation and inspectable outcomes.

Status/dependency objectives are human labels. Planner objectives preserve explicit task-title steps; neither form is executable instructions. Explicit input references are resolved in the same workspace and retained in the context snapshot. Their text cannot expand capabilities or grant permissions. Publication is a separate local action.

## Run lifecycle

```mermaid
stateDiagram-v2
    [*] --> queued
    queued --> running: worker claims lease
    queued --> failed: membership, dependency or delegate failure
    running --> completed: save read-only outcome
    running --> waiting_for_approval: save outcome and exact publication request
    running --> failed: timeout, context change or computation failure
    queued --> cancelled: human cancels
    running --> cancelled: human cancels and discards late result
    waiting_for_approval --> cancelled: rejection or cancellation
    waiting_for_approval --> failed: expiry or invalid execution authority
    waiting_for_approval --> completed: approved publication committed
    failed --> [*]
    completed --> [*]
    cancelled --> [*]
```

### Queue and delegation

`POST /workspaces/{w}/runs` accepts a known `agent_type`, objective (up to 1,000 characters), optional task, up to 30 `input_refs`, a `publish` flag, and `idempotency_key` (8–100 characters). Repeating the same key and payload returns the same run; changing the payload with that key returns 409. Keys are unique per workspace and initiator. The UI preserves a request key across a failed response retry.

The coordinator creates two queued children and records its plan atomically. Children run before composition; completion is never inferred from queue insertion. Child failures/cancellation fail the coordinator. Delegation is fixed and bounded, with no user-defined graph or recursive agent chain.

```mermaid
flowchart LR
    Human[Human objective and optional task] --> Gate[Check task and prerequisites]
    Gate --> Plan[Persist handoff plan]
    Plan --> Status[Status child]
    Plan --> Graph[Dependency child]
    Status --> Compose[Verify consistent context]
    Graph --> Compose
    Compose --> Outcome[Persist handoff outcome]
    Outcome --> Review[Human inspects evidence]
```

A task-associated status/handoff run requires an active unfinished task that is not explicitly blocked and whose prerequisites are Done. Dependency analysis may inspect blocked work. The worker checks again before computing and before committing. A task change during computation invalidates the result. Reports never change task status, assignment, or decision acceptance.

### Worker operation and recovery

Start a third development terminal with the same database configuration as the HTTP backend:

```bash
cd backend
source .venv/bin/activate
python worker.py
# For one job, recovery or approval only:
python worker.py --once
```

The worker checks the schema; it does not migrate automatically. No queue service is required. Multiple processes may share PostgreSQL/SQLite; workspace locks and lease tokens prevent duplicate claims and late commits. No deployment scheduler is bundled. A stopped worker leaves durable queued work visible until a worker starts.

Each claim stores a random lease token, context and 60-second lease in a short transaction. Computation runs outside it. Completion rechecks membership, task validity, source/task/decision fingerprint, and token. Dependency traversal has a 30-second computation budget, a 100-node path bound and bounded output. Finalization refuses an expired lease even if computation returned.

A restarted worker marks expired Running jobs Failed (`lease_expired`). It never guesses that they succeeded. Waiting approvals expire after 24 hours and are materialized by the worker or an attempted response. There are no automatic retries. The original initiator may explicitly retry a failed root/standalone run at most twice (three total attempts); each retry is a new durable run, and each failed record permits only one successor retry. Cancelled/completed runs are not retried.

Cancellation is available to the initiator/current owner and cancels pending children and approvals. Completed child reports remain historical records. A late worker discards its result when cancellation/recovery has already won.

### Bounds and staleness

A workspace may have at most 100 outstanding run records (including children; a handoff needs three available slots). The worker snapshots at most 500 total tasks, 200 accepted decisions, 2,500 dependency edges and the explicit source references. It fails with `scope_limit_exceeded` rather than claiming a complete report over a truncated graph. The UI's task/prerequisite selectors offer bounded recent candidates; APIs accept any authorized eligible task.

Fingerprints include task versions, status, assignment, archival, accepted decisions, dependency edges and explicit source text. Related changes require a new run/retry. Child and parent fingerprints must match; ongoing editing can intentionally cause `context_changed`. Outcomes are historical as-of snapshots, not perpetually current truth. Unlinked conversation text is outside these contracts' computation scope.

## Approval and exact publication

```mermaid
sequenceDiagram
    participant Member
    participant API
    participant DB
    participant Worker
    participant Owner
    Member->>API: Queue report with publication requested
    API->>DB: Persist run and bounded delegation plan
    Worker->>DB: Claim, compute, save outcome and exact payload hash
    Owner->>API: Inspect preview, approve payload hash
    API->>DB: Verify current owner, pending state and expiry
    Worker->>DB: Recheck authority, payload, context and expiry
    Worker->>DB: Insert one assistant message and execution receipt atomically
```

A successful computation with `publish=true` enters Waiting for approval. It does not publish yet. The server constructs a preview containing the objective, report time/summary, up to 20 facts with bounded citations, and the full run reference. The owner must submit its SHA-256 to approve/reject; the frontend asks for confirmation. Approval records bind `publish_report`, workspace, run, agent identity and exact content. No client-provided replacement action is accepted.

Approval alone is not an execution receipt. A worker revalidates the requester is still a member, the approver is still owner, expiry, payload hash/equality and project fingerprint. It writes one assistant message plus Executed state/message ID and run completion in one transaction. Competing workers cannot duplicate publication. Ownership transfer or membership removal can invalidate an earlier approval. Rejection cancels publication while preserving the computed report. Expired or mismatched approvals fail with visible error codes.

The requesting user's logout does not cancel already authorized durable work; membership revocation and explicit cancellation do. Session revocation still denies all subsequent protected API access. No approval can authorize external writes.

## Observability and limits

`GET /runs`, `/runs/{id}`, and `/approvals` are workspace-authorized and bounded. Run detail includes the objective, initiating ID, source snapshot/scope, plan/children, timeline, outcome, error code, attempt chain and approval. Worker exceptions become safe public codes; raw provider/exception payloads are not stored or exposed. Events are append-only through application APIs, not tamper-proof against administrators.

Not implemented: unrestricted LLM agent execution, arbitrary tools, dynamic delegation graphs, distributed queue infrastructure, automatic compensation, durable streaming, or production monitoring. These need separate capability and approval designs.

## Connected research and exact native task plans

Three additional identities preserve the original contracts:

- **`local.plan.v1`** analyzes the existing dependency graph/blockers and accepted decisions, splits up to five explicit semicolon/newline-separated objective steps into task titles, skips existing active titles and proposes a sequential task plan with evidence references. It does not invent a software implementation or claim general-language planning.
- **`local.research.v1`** retrieves up to eight authorized native/document/import sources and prior decision/document revisions using objective terms, returns cited excerpts with current/historical labels and abstains without matches. It excludes self-generated activity/assistant messages from automatic research to avoid self-referential context changes. Explicit original source references retain the original native source types.
- **`local.delivery.v1`** persists a fixed plan with planner/research children and composes their reports only when fingerprints match. Its root creates one native proposal; child runs do not independently create duplicate proposals.

These contracts remain deterministic and have no model/tools/external calls. The separate public connector fills imported records; local agents read only the authorized stored snapshot. Optional model answers are a separate API, not a hidden model-agent capability.

`GET /workspaces/{w}/action-proposals` exposes recent exact plans and receipts. An owner approves/rejects with the displayed payload hash. Before execution, `actions.py` checks initiating membership, current owner, expiry, run state, context/epoch and exact recomputed plan/hash. It creates one to five To do/unassigned/medium tasks and their sequential prerequisites in the same transaction as the unique resource receipt and activity. The legacy `publish_report` action/constraint remains separate.

```mermaid
stateDiagram-v2
    [*] --> pending: root saves exact task plan
    pending --> approved: current owner approves hash
    pending --> rejected: current owner rejects
    pending --> expired: deadline passes
    approved --> executed: revalidate and commit resources plus receipt
    approved --> failed: changed context or authority
    executed --> [*]
    rejected --> [*]
    expired --> [*]
    failed --> [*]
```

A Completed planner/coordinator means its computation completed. Pending proposals and Approved proposals have not created tasks; only Executed carries actual task IDs. Created tasks are unfinished work. Any task/decision/context change before execution can fail the entire proposal without partial resources. After execution, another proposal must be computed from the new context.

Document/import changes advance a conservative knowledge epoch. Stale run contexts/outcomes and publication content/messages become unavailable across APIs/search/model context. Native task-plan payloads are also hidden after knowledge change, and execution rejects them. Existing human-authored native text and resource receipts remain. See [Integrations](INTEGRATIONS.md) for the privacy boundary and [Operations](OPERATIONS.md) for health, recovery and scheduling limits.

## GitHub issue triage and optional reasoning

The exact objective `triage github issues` on planner or delivery coordinator selects bounded authorized open imported issues and proposes up to five `Review issue: …` tasks, retaining original URL, source ID and version in the description. Existing active titles are skipped. Issues stay untrusted imported records; no dependency is inferred between separate issues. The owner sees exact To do/unassigned payloads and citations; execution recomputes the same plan and verifies the source/context epoch before atomically creating tasks and one receipt. Public and private imports use the same stored-source boundary. Revocation/expiry hides the derived run and fails stale proposals. The deterministic researcher also retains historical labels and explicit uncertainty.

When separately configured, an explicit Request cited model interpretation action re-retrieves current evidence for a short run objective and saves a cited model answer. It uses the same one-call/20-second/1,600-token/no-tools schema and citation gate as Ask workspace, plus shared model request budget. It does not change the durable run, deterministic plan, approval payload or task status. This is bounded optional reasoning alongside agents, not general model planning or autonomous implementation. Fake-provider tests reject extra action fields and prove no native state change; no live model-quality claim follows.

## Selected connected evidence

New requests may include up to eight `knowledge_refs` of kind `document`, `external` or `decision_revision`, distinct from native `input_refs`. They bind idempotency only when nonempty, preserving existing empty-reference request hashes. Child/retry runs preserve selection; capture resolves it in the authorized workspace, adds it to the context fingerprint and prioritizes it before lexical research candidates. Changed or revoked evidence cannot pass exact approval recomputation. The optional picker performs explicitly requested trained retrieval before queuing; local contract execution itself remains deterministic and does not call models or embeddings.
