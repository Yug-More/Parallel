# Development roadmap

## Phase 0 — Audit

Completed: repository/history verification, active-stack inventory, security findings and isolated baseline checks. Historical promotional claims were separated from active implementation. See REPOSITORY_AUDIT.md.

## Phase 1A — Secure foundation

Implemented: configuration and session hardening, disabled unsafe integrations, non-destructive seeding, workspace/membership ownership, scoped messages/activity/context, private legacy migrations, optional provider boundaries, frontend lint fixes, workspace/session UI, regression/browser tests, CI and documentation.

Completion requires executed tests, migration checks and CI; a workflow file alone is not evidence. Live provider compatibility, credential rotation and production readiness are not claimed.

## Phase 1B — Real collaboration

Implemented: account-bound in-app invitation lifecycle; owner-managed removal, ownership transfer and leaving; persistent versioned tasks with assignments/status/priority/due dates and safe archival; acyclic prerequisites; server-side session revocation/logout-all; local authentication rate limiting; a complete collaboration interface and desktop/mobile browser journeys. Existing owner-only direct addition remains a documented compatibility/admin endpoint. Human collaboration and activity require no AI credentials.

Verification includes Phase 1A regressions, transaction/concurrency invariants, copied-token revocation, populated-schema preservation, PostgreSQL integration and both browser layouts. Completion is established by executed local/remote results in the implementation PR. Remaining release hardening includes email verification/recovery, distributed quotas, session-retention policy, operational monitoring and backup drills.

## Phase 2 — Project Continuity Intelligence

Source-linked decisions, task/document context, correction and supersession, permission-aware retrieval, and reproducible continuity evaluations. Start with structured storage; add embeddings only when they improve measured relevance. Evaluate recall, resume effort and source correctness. No results exist yet.

## Phase 3 — Multi-agent coordination

Persist agent configurations, task delegation, handoffs, dependency tracking, run states, interruption recovery, cancellation and idempotency. Acceptance requires durable real work and evidence, not chat-only role simulation.

## Phase 4 — Integrations and approvals

Select integrations by user value. Introduce scoped immutable connection ownership, signed/replay-safe callbacks, approval records, verified execution receipts, bounded retries and recovery. Historical voice/Composio code remains disabled until these requirements are implemented and tested with explicit authorization.

## Phase 5 — Evaluation, deployment and release

Reproducible end-to-end scenarios, reliability and task-completion measurement, security/dependency review, backup/restore drills, release configuration, observability, onboarding and user evaluation. Release only after the intended workflows are verified. No production deployment or adoption is claimed.
