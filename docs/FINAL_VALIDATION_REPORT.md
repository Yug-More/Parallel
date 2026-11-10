# Final engineering validation

9 November 2026, America/Los_Angeles. Baseline: `fb3b3fb`, verified clean and synchronized with `origin/main` at `https://github.com/Yug-More/Parallel.git`. Branch: `codex/final-engineering-validation`. No open PRs existed at intake. Work preserves the modular monolith, user data, disabled historical integrations and contributor history.

## Prioritized audit and resulting changes

1. **High: current PDF dependency advisories.** `pip-audit` found seven CVEs affecting pypdf 6.21.2: CVE-2026-119203 through CVE-2026-119209. Both requirements and constraints now pin 6.21.4, the reported fixed patch for all seven. The repeated audit reports no known vulnerabilities in the requirements-ai resolution. Existing subprocess limits remain unchanged. This is dependency advisory checking, not a formal security assessment.
2. **High for demo functionality: missing Compose worker.** API/database startup previously left document and agent queues unprocessed. Compose now starts a separate nonroot worker with the exact shared database/configuration after migration-aware API readiness. A new real HTTP smoke exercises ingestion, delegated computation, idempotency and cross-workspace denial; CI runs it. No migration/backfill is introduced.
3. **Medium: misleading API specification.** The disabled legacy catch-all appeared as five operations with duplicate operation IDs. It is now excluded from OpenAPI while retaining 410/404 denial behavior. A regression verifies unique supported operation IDs and unchanged legacy denial. The supported schema has 61 paths and 75 method/path operations, excluding framework docs and disabled legacy/WebSocket routes.
4. **Medium: unsupported application claims.** Public evidence supports three historical events, but Scoop is second place, not first. Two continual-learning tracks are one event. Exact sources and uncertainty are recorded in [history](PROJECT_HISTORY.md); no unverified aggregate cash/adoption number is published. Current evaluation was rerun with unchanged labels/rankings.
5. **Preserved boundaries and open gaps.** Existing local contracts already implement leases, bounded delegation, explicit retries/cancellation, context rechecks and exact native/publication approvals. Workspace locks, live sessions, source epochs and per-resource membership remain in force. Tests cover these rather than introducing unrestricted execution. Slack/Notion/Drive/Composio/email sending/voice/SMS are historical or disabled; no mock is promoted to live support. Private GitHub and model adapters retain explicit opt-in and unverified live gaps.

## Review coverage

Inspected repository inventory/history/remotes/CI, runtime entry points, configuration, schema lifecycle, worker queues, agent contracts, action approval paths, source ingestion/revocation, connector documentation, frontend panels and browser journeys, Docker setup, existing audits/handoffs/evaluation fixtures and award sources. Current UI uses polling, not SSE; invitations and workspace activity provide actual in-app collaboration rather than a fabricated notification service. The existing design system, keyboard/modal behavior and responsive panels were preserved and re-exercised. No cosmetic rewrite or new arbitrary agents were needed to resolve the observed defects.

This is a scoped source review plus automated verification, not proof that every line is defect-free. Existing documentation describes earlier milestones; this report supersedes their current outcome counts, not their historical records.

## Commands and evidence

- `ruff check backend scripts`; `ruff format --check backend scripts`: passed, 100 Python files formatted.
- `pytest -q backend/tests`: **215 passed**, four warnings, **90.27s** after the stable dependency run. Baseline was 214 passed; one supported-schema regression was added.
- `pytest -q backend/tests/test_pdf.py backend/tests/test_operations.py`: 14 passed after the pypdf patch.
- Fresh exclusive temporary SQLite: `python migrate.py` twice and `alembic check`: passed, no new upgrade operations.
- Isolated PostgreSQL 16: repeated migrations, metadata check, `postgres_smoke.py`, `postgres_upgrade.py`, `postgres_intelligence.py`, `postgres_connected.py`: passed. PostgreSQL recovery/embedding-adapter/retention suites: 22 passed, one warning, 13.51s. These synthetic checks include populated upgrades and competing operations; no live database was touched.
- `npm ci`: 167 packages installed; 168 audited, zero vulnerabilities. `npm run lint` and `npm run build`: passed. Vite JS 292.79kB / 85.31kB gzip; CSS 22.06kB / 4.87kB gzip. This is bundle size, not user-perceived load-time measurement.
- `PARALLEL_TEST_PYTHON=/tmp/parallel-final-venv/bin/python npm test`: **16 passed (3.3m)** in the final stable environment. No assertion or resource limit was relaxed.
- All four retrieval commands in [retrieval evaluation](RETRIEVAL_EVALUATION.md): passed, raw outputs committed under `docs/final-evaluation/`. No ranking change or paid/trained-model run occurred.
- `pip-audit -r backend/requirements-ai.txt --progress-spinner off`: no known vulnerabilities after patch. Optional full trained ML runtime excluded.
- `python scripts/check_secrets.py`: passed; limited current-source pattern scanning, not complete historical/entropy scanning.
- Docker Desktop 28.5.1, real `docker compose ... up --build -d --wait`: passed on the exclusive `parallel-final-validation` project. `python scripts/compose_smoke.py`: ingestion ready, delegated handoff completed, replay deduplicated and three cross-workspace reads denied. [Synthetic receipt IDs](final-evaluation/compose-smoke.json). Full service restart preserved run `completed` and revision `ready`; services returned ready/running. Existing volumes were preserved.

## Failures investigated

The first browser attempt had no Chromium binary; installed it as documented. A subsequent run had 15/16 passing, with one PDF subprocess failure while the environment's pypdf package was being replaced. The fixed PDF/operations tests passed; the full suite was rerun in a stable environment without weakening the resource limits or assertions. Docker's first build lacked the bundled credential helper on PATH; adding Docker Desktop's own binary directory resolved it without changing credential storage.

The initial vulnerability gate failed legitimately and was fixed with a patch upgrade, not an exclusion. Starlette test-client deprecation, intentionally short-key JWT negative-test and historical SQLite datetime warnings remain visible. No test was removed or skipped to obtain passing outcomes.

## Release gates and limitations

No production deployment, paid APIs, credential rotation, external messages/documents, private provider authentication or repository write integration was executed. Historical Plivo exposure still requires owner revocation; source changes cannot perform that. Live model quality, independent relevance/usability/accessibility, production recovery, throughput, task/SSE latency and verified adoption remain unavailable. No production-readiness certification is implied by merge.

The PR must pass every configured check, including the new Compose job. Branch protection/rules and exact head are checked before an authorized normal merge; no bypass is permitted. Post-merge main and CI are verified separately. Frozen technical facts are in [metrics](FINAL_PROJECT_METRICS.md); release URLs/outcomes are appended only after observed.

## Verified implementation commit

Runtime/security changes: `e1a1a1f44d4e4bbba172c60bcbc0c5dbb4e6850f`. Both author and committer verified as Yug-More <yugmore20@gmail.com>; no co-author trailers. Documentation and evidence are committed separately. All README screenshot references and historical contributors remain preserved. Local Markdown links, the exact private/exclusive configuration-generation command, source secret guard and diff whitespace checks passed.

## Release gate and immutable evidence

[PR #12](https://github.com/Yug-More/Parallel/pull/12) contains the final design, exact commits, six CI jobs, review and merge outcome. [Main verification runs](https://github.com/Yug-More/Parallel/actions?query=branch%3Amain) provide the post-merge gate; their results must be inspected, not inferred from this source file. Runtime/security implementation: `e1a1a1f44d4e4bbba172c60bcbc0c5dbb4e6850f`; initial evidence freeze: `ed962112140cb7fb41a07f0ebfa5b23b9620bb63`. No CI/merge result is predeclared before observation. Numerical fixture results above are frozen; repository release state remains observable through these linked records.
