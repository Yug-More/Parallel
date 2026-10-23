# Engineering decisions

These records describe implementation choices in this repository. They are distinct from the user-created decision records stored in each workspace.

## ADR 001 — Keep a modular monolith

**Accepted.** React/Vite calls FastAPI domain routers. SQLAlchemy and Alembic support SQLite and PostgreSQL. `collaboration.lock_workspace` serializes mutations before authorization checks. New decision and agent services reuse this boundary. Separate queues, graph databases, and service-to-service authorization would add failure modes without a demonstrated workload.

## ADR 002 — Store facts before summaries

**Accepted.** Decisions have immutable application-level revisions and per-revision evidence snapshots. Source IDs are validated in the decision's workspace; snapshots retain cited text and version while live previews reveal corrections or archival. Accepted decisions are structured human records, not proof that their statements are true. Conflicting messages remain separate raw records. Supersession preserves the prior statement and links to a new accepted decision.

Rejected alternatives: silently editing accepted records; treating every conversation assertion as a fact; indexing only lossy summaries. Database administrators can still change records; there are no append-only database triggers or cryptographic signatures.

## ADR 003 — Evaluate lexical retrieval before buying embeddings

**Accepted.** SQL retrieval provides deterministic title/body scoring with workspace, status, archive, and time filters. It works without keys and is portable. Eleven synthetic scenarios expose both ambiguity and vocabulary failures. There is no measured semantic-search implementation or vector store. Consider embeddings only after adding a broader relevance set and measuring improvement, including lifecycle and privacy correctness.

## ADR 004 — Leased local jobs, explicit retries

**Accepted.** A small database worker claims a run, computes outside the transaction, then revalidates its lease, membership, task graph and source fingerprint. Interrupted leases become visible failures. A human can request up to three attempts; each attempt is a new record. This avoids hidden re-execution and separates computation from publication. It requires a running worker; HTTP requests never imply execution.

## ADR 005 — Coordinate distinct computational contracts

**Accepted.** The handoff coordinator delegates a task/decision status computation and a graph traversal, then composes their persisted outcomes. These are deterministic local agents, not LLM personas or autonomous software implementers. Children must complete against the same relevant state as the coordinator. A changed context fails the composition rather than silently mixing snapshots.

## ADR 006 — Approve exact local publication

**Accepted.** An owner approves a server-generated report payload and its SHA-256. The worker verifies that payload, the requesting member, current owner authority, expiry, and project state before publishing one assistant message in the same transaction as the execution receipt. Rejected/expired/cancelled approvals cannot be replayed. No approval authorizes shell commands, external documents, or another payload.

## ADR 007 — Poll and restore navigation without storing credentials

**Accepted.** The interface polls bounded lists, preserves draft edits, and restores workspace/section from URL parameters. The backend checks membership independently of those parameters. HttpOnly cookies remain the session mechanism; no token is stored in browser localStorage. Already-read data cannot be recalled, and an in-flight authorized read may finish during removal.

## ADR 006 — Bounded stored sources before a vector service

**Accepted.** Text/Markdown extraction and public GitHub imports use SQL tables and the existing worker. Stable passages and explicit source kinds preserve provenance; archive/revocation gates live joins. Coverage-based lexical retrieval improves measured fixture precision without introducing embeddings, model downloads or another index lifecycle. PDF/private authentication were separate follow-ups at that checkpoint; ADRs below record current support.

## ADR 007 — Conservative invalidation for derived knowledge

**Accepted.** Answers revalidate evidence fingerprints; generated run/report/publication text binds a workspace knowledge epoch. Revocable source change hides entire older reports rather than trying to redact individual paraphrases. This reduces availability after unrelated edits, but avoids claiming a model summary is safe merely because one citation was removed. Manual native quotations remain authored data; administrative storage/backup retention is an operational boundary.

## ADR 008 — Small exact native action surface

**Accepted.** A deterministic planner preserves explicit user steps, with at most five To do/unassigned tasks and sequential prerequisites. A separate proposal record protects the legacy publication action constraint. Owner review binds exact payload/hash/context, and task creation plus receipt is atomic. General coding tools, unconstrained model actions and external writes were rejected for this cycle because their execution and independent outcome verification require a broader authorization design.

## ADR 009 — Resource-bounded PDF subprocess

**Accepted.** Reuse the document lease/revision/archive boundary, with pinned pypdf parsing only stdin bytes in a separate isolated interpreter. Bound file/pages/text/CPU/time, add Linux memory limits and nullable page provenance. Do not claim OCR or a complete OS sandbox. Avoid running an untrusted parser in the HTTP/worker interpreter.

## ADR 010 — Selected GitHub App user grants

**Accepted.** Choose fine-grained App user authorization/device flow over broad OAuth-app repo scope. Require selected installations with metadata/issues/pulls read only; map verified repository IDs to owner-authorized workspaces. Store expiring grants under a separate Fernet key, renew explicitly and persist rotation before further I/O. Poll bounded snapshots with incremental upserts; ten-minute freshness fails closed. Webhooks, live authorization and cursor-based deltas remain future verification/work.

## ADR 011 — Honest optional similarity and measured ranking

**Accepted.** SQL durable index jobs expose a replaceable provider interface without another database or silent model calls. The shipped adapter is deterministic character similarity, not trained semantics. Revalidate epoch/fingerprints and fall back to lexical filtering. A frozen 40-query developer holdout measured one current-decision ranking improvement (MRR 0.818 to 0.839), unchanged precision/recall and remaining vocabulary misses. Coverage stays default. Independent human evaluation is still required.

## ADR 012 — Exact issue triage, separate optional interpretation

**Accepted.** Improve existing planner/research/delivery contracts rather than add personas. The explicit triage objective proposes up to five internal issue-review tasks with source IDs/URLs/versions; independent issues receive no inferred dependencies. Existing exact approval/recompute/receipt logic remains authoritative. Optional model interpretation saves a cited answer and cannot edit plans or grant capabilities.

## ADR 013 — Shared counters and new-path recovery

**Accepted.** Atomic SQL upserts share fixed-minute HMAC counters across processes without raw IP storage. Bound model requests in addition to workspace quotas; this is not an organization spend cap. Rotate worker queues locally and provide an operator supervision template. Restore backups only to exclusively new private paths, migrate the copy and check integrity/FKs; never reset live data. PostgreSQL production recovery, ingress controls and account recovery remain deployment gates.
