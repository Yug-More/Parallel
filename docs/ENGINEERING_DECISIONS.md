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
