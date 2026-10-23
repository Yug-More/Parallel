# Phase 10–12 pre-delivery execution checkpoint

Baseline: clean local/remote main `8bf2c22339131604d3dc5afb7fbd2d1d51e6aac1`.
Branch: `feat/semantic-intelligence-pilot-hardening`.

Integrated plan:

1. Add real opt-in trained embedding adapters (operator-provisioned local weights or explicitly consented external provider), bounded versioned indexing across authorized sources, filtered hybrid retrieval, grounded evidence selection and reproducible evaluation with honest live-model status.
2. Tighten private GitHub permission freshness, provide explicit revalidation/live verification harness, and connect issues/PRs/native tasks with source navigation and exact human action review.
3. Add hashed one-use account recovery/verification tokens with private local delivery, strengthen worker health/recovery, provide an isolated PostgreSQL backup/restore drill, and implement explicit previewed retention/redaction controls without migration-time data deletion.
4. Retain existing tests/journeys, add focused security/concurrency/provider/lifecycle/browser coverage, run comprehensive checks, update diagrams/screenshots/setup, commit with mandatory identity, open PR, verify CI and merge normally when permitted.

Checkpoint status: implementation spans all three phases and local verification passed. This is a pre-delivery snapshot; subsequent PR/CI/merge evidence is recorded in the delivery report and GitHub checks.

Implemented: real optional offline/local and opt-in OpenAI embedding adapters; bounded versioned multi-source indexes and semantic/hybrid modes with fresh lexical fallback; complete source-set invalidation; explicit evidence selection for agents/answers and bounded blocker/change scopes; GitHub owner permission revalidation, sensitive 30-second freshness and atomic reconciliation checkpoints; private local account recovery/verification with one-use hashes and serialized reset/login; independent worker liveness/backoff; exact signed retention previews, scoped content redaction and workspace closure; isolated PostgreSQL restore drill and PostgreSQL boundary tests; two additional browser journeys and actual synthetic screenshots.

Observed checks: original baseline 183 backend tests passed; final full local run 212 passed, followed by 22 affected answer/embedding/retention checks after the idempotency/budget correction, 58 private/auth/workspace checks after extending freshness to chat, and 11 embedding checks after the native-rebuild correction. The rebuild correction also passed on PostgreSQL. All eleven Chromium journeys passed (the original nine plus two new desktop/mobile journeys). PostgreSQL boundary tests: 21 passed; existing PostgreSQL smoke, populated-upgrade, intelligence/approval and connected-source scripts passed. Real pg_dump/pg_restore passed (32 tables, 24 rows, receipts preserved, source unchanged). SQLite repeated migration and metadata drift check passed. Nineteen Mermaid diagrams rendered and local documentation links passed. Shipped Python/npm audits and a direct-package-only optional Sentence Transformers advisory query found no known vulnerabilities; optional transitive ML runtime is not installed/fully audited.

Frozen forty-query evaluation records character-hybrid recall 0.8/MRR 0.709375 versus coverage 0.9/0.817708. Default remains coverage. Trained comparisons remain unexecuted; fabricated-vector tests are protocol/security evidence only. No real model weights, paid model call, private repository access, App registration, email send, deployment or original-data migration/deletion was performed. Local PostgreSQL used a cached image and a disposable container with new synthetic databases/schemas only.

Next delivery steps at this snapshot: commit tested checkpoints with exact required author/committer, push PR, inspect/fix CI, authorized normal merge, synchronize and verify clean main. Current expected head is `0018_sync_checkpoints`. The disposable Docker test container is stopped during delivery cleanup.
