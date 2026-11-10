# Parallel — final project metrics

Freeze date: 9 November 2026 (America/Los_Angeles). Technical values refer to the finalization tree based on `fb3b3fb`; release gate outcomes are recorded in [final validation](FINAL_VALIDATION_REPORT.md) and the linked PR. Future claims must retain dataset/scope qualifiers; do not silently substitute historical counts. This freeze does not certify production readiness.

## Project and attribution

**Official name:** Parallel. **Description:** A persistent collaborative project workspace with source-linked decisions, permission-aware retrieval and human-approved, bounded local agent coordination.

Primary areas: full-stack systems, authorization, persistent orchestration, concurrency, information retrieval, provenance, reliable ingestion and reproducibility. React/Vite, FastAPI, SQLAlchemy/Alembic, SQLite/PostgreSQL and a separate database-leased worker form a modular monolith.

Repository history records commits under Yug-More <yugmore20@gmail.com> and legitimate historical contributors Sean Aminov, Nayab and severin-spagnola. Public event accounts name Yug More, Sean Aminov, Severin Spagnola and Nayab Hossain; Yug and Sean represented the continual-learning event. The current repository records substantial engineering under the required Yug-More identity. Commit attribution alone does not establish the individual division of design/implementation or unaided personal authorship. Confirm personal responsibility before using first-person implementation claims. No team member's work is attributed exclusively to the applicant here.

## Competition evidence

Three events, four award results:

- Scoop AI Hackathon Silicon Valley Bowl: **second place**, per [published results](https://neonewstoday.com/ai/neo-and-spoonos-announce-winners-of-scoop-ai-hackathon-silicon-valley-bowl/). Secondary reporting; linked organizer post was not directly fetchable. This corrects the first-place recollection.
- Meet the Vibes with TRAE Friends @ Silicon Valley: **first place / grand winner**, per [organizer](https://www.linkedin.com/company/ainovoco/) and [team announcement](https://www.linkedin.com/posts/paralleldev_ai-startup-parallel-activity-7405709912682463232-4XuK). Pitch/demo event.
- Continual Learning Hackathon: **Composio Best of Use** and **Best Voice agent using Plivo**, per the [Devpost record](https://devpost.com/software/parallel), also supplied by the owner. Two tracks at one event.

[History and discrepancy resolution](PROJECT_HISTORY.md). Do not claim three first-place hackathon wins, four separate competitions.

## Architecture and capabilities

Six code-defined local contracts: status, dependencies, handoff coordinator, explicit task planner, context researcher and delivery coordinator (`backend/orchestration.py`). Coordinators persist child plans, wait for outcomes and recheck common context fingerprints. They do not execute shell/tools/models or external writes. Explicit optional cited model reasoning is separate.

Runs have durable attempts, lease tokens, bounded scope, cancellation/failure history and idempotency keys. Current owners approve exact native task/publication payloads; worker revalidation and atomic receipts establish effects. Native tasks begin To do; a report never proves software work completed.

Implemented knowledge inputs: bounded local text/Markdown/PDF uploads and opt-in read-only GitHub imports. Private GitHub App selected-repository flow is implemented but not live-verified here. Slack, Notion, Google Drive, Composio, email sending and voice/SMS are historical/disabled. Optional model/trained adapters are not live quality evidence. UI updates use polling; no current SSE latency claim.

## Engineering measurements

- Supported OpenAPI: **61 paths, 75 HTTP method/path operations**. Generated from `create_app().openapi()`, excluding docs routes, the disabled legacy catch-all and disabled voice WebSocket. Baseline schema exposed 80 including five misleading legacy operations.
- Backend regression suite: **215 passed**, four warnings, 90.27s after one added supported-schema regression. Baseline rerun: 214 passed, 88.90s, four warnings. Test quantity is not coverage percentage.
- Browser suite: **16 passed real Chromium journeys (3.3m)**, not 16 frontend unit tests. Covers persisted authentication/collaboration, evidence, native approvals, recovery/retention and six-width/two-theme UI checks. No separate frontend component/unit suite is configured.
- PostgreSQL recovery/adapter/retention suite: **22 passed**, 13.51s; counted separately, not added to unique backend test inventory. Fresh/repeated/populated migrations and concurrency scripts passed.
- Ruff lint/format: passed, **100 Python files** formatted. Frontend lint/build: passed. JS **292.79kB / 85.31kB gzip**; CSS **22.06kB / 4.87kB gzip** on Node 24.11.1. No frontend speed gain inferred.
- Dependency audit after pypdf **6.21.4** patch: **no known vulnerabilities** in requirements-ai resolution; npm audit reported zero across **168 packages**. Seven pypdf advisories were found and resolved in this cycle. Optional full ML runtime excluded; advisories are time-sensitive.
- Real Docker Compose: nonroot API/worker plus PostgreSQL 16; initial migration, ingestion, delegated run, duplicate suppression and cross-workspace denial passed. Restart preserved completed/ready records. No production deployment, restore objective or volume deletion.
- Security boundaries tested: live session revocation, immutable membership, workspace locking/isolation, optimistic versions/dependencies, source invalidation, exact approval/replay/context rechecks, bounded PDF subprocess and provider failure sanitation. Historical credential rotation remains owner work.

## Retrieval and performance

Dataset: `backend/evaluation/pilot_holdout.json`, **40 frozen developer-created queries**, cutoff 5; no independent judgments. Default deterministic lexical coverage: **recall@5 0.900**, **MRR 0.817708**, **returned-set precision 0.772917**, **strict precision@5 0.170**. Holdout coverage mean **11.536ms**, maximum **60.143ms** for this local run. Lexical vocabulary/ambiguity/multilingual limits remain. No trained model was run.

The separate 16-query connected workload made 160 sequential requests per ranking: coverage p50 **4.446ms**, p95 **8.649ms**, recall **0.875**, MRR **0.833333**. Workload and exact reproduction commands are in [evaluation](RETRIEVAL_EVALUATION.md); full outputs in `docs/final-evaluation/`. These are local SQLite API/session measurements, not general API latency or production benchmarks. Task routing/execution latency, memory, production throughput and SSE latency were not separately measured. No fabricated values fill those gaps.

## Adoption and evidence

No verified user/organization count is frozen. A teammate portfolio reports historical users/SpoonOS pilots, but no independent organization confirmation or telemetry was inspected. Do not state approximately 15 production developers as verified adoption.

Primary sources: `backend/{orchestration,actions,worker,security,documents,pdf_extract,pdf_parser}.py`, `backend/api/`, migrations through `0018_sync_checkpoints`, `backend/tests/`, `parallel-frontend/tests/`, `backend/docker-compose.yml`, `scripts/compose_smoke.py`, `.github/workflows/verify.yml`, evaluation JSON and the validation report. Historical baseline/merge references remain in `docs/FINAL_PRODUCT_HANDOFF.md`. Release commit/PR/main facts are recorded after observation, without self-referential invented hashes.

## Application wording

**One sentence:** Parallel is a collaborative project workspace that combines source-linked decisions, permission-aware lexical retrieval and durable, human-supervised local agent workflows.

**Three evidence-based project bullets** (use first person only after confirming your contribution):

- Built a React/FastAPI workspace architecture with database-backed sessions, workspace authorization, versioned tasks and revision-preserving decision provenance.
- Implemented six bounded local agent contracts with persistent delegation, lease recovery, idempotent requests and exact owner-approved native actions with atomic receipts.
- Evaluated default lexical retrieval on 40 developer-created holdout queries: 90.0% recall@5 and 0.818 MRR; validated the repository with backend/browser, PostgreSQL and real Docker workflows.

**SOP description (100 words):**

Parallel explores how collaborative software can preserve project context without giving automated systems unrestricted authority. The project combines conversations, versioned tasks, source-linked decisions and permission-aware retrieval in a React and FastAPI workspace. Six deterministic local agent contracts analyze status, dependencies, explicit plans and evidence through a durable database worker. Consequential native actions require exact owner approval and revalidation before an atomic receipt records their effects. Evaluation on forty developer-created holdout queries yielded ninety percent recall and 0.818 MRR. The engineering emphasis is reproducible behavior, authorization, recovery and honest evidence boundaries rather than unsupported claims of autonomous execution or production adoption.

**Technical description:** See the 200-word description in [application summary](GRADUATE_APPLICATION_SUMMARY.md). **Faculty explanation:** “The agents compute bounded reports and proposed task plans. A separate worker rechecks the approval and context before committing an allowed native effect. A successful computation does not prove the proposed work happened. Retrieval numbers are synthetic lexical results, and historical awards do not validate current live integrations.”
