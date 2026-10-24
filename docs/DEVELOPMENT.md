# Development

React/Vite and FastAPI/SQLAlchemy form a modular monolith; the separate worker shares the same database. Use Python 3.12/3.13 and Node 22.12+ (the lockfile also permits compatible Node 20.19+). The ordinary local suite requires no paid provider, private grant, model weights or email service.

## First local setup

From a new checkout's `backend` directory:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python -c 'import secrets; print("SECRET_KEY", secrets.token_urlsafe(48), sep="=")' >> .env
python migrate.py
uvicorn main:app --host 127.0.0.1 --port 8000
```

Do not overwrite an existing `.env`. Windows PowerShell activation is `.venv\Scripts\Activate.ps1`; use an installed supported Python executable. Development can generate a process-local secret, but an explicit generated secret gives HTTP/worker consistent configuration and stable sessions across restarts. Never commit it.

In separate terminals run `npm ci && npm run dev` from `parallel-frontend`, and `source .venv/bin/activate && python worker.py` from `backend`. Open http://localhost:5174 and register. HTTP and worker must use the same migrated database and private configuration. Queued uploads/runs/approved actions await the worker; a heartbeat proves polling, not success.

Vite defaults to 5174 and can choose another free port. Match the actual browser origin in `CORS_ORIGINS`. `VITE_API_BASE` defaults to http://localhost:8000; keep localhost/127.0.0.1 consistent for cookies. Provider keys are never frontend environment variables. SQLite relative URLs resolve from the process working directory; use an absolute URL when running commands elsewhere.

## Configuration and optional features

`APP_ENV` is development, test or production. Production requires a sufficiently long signing key and explicit HTTPS origins; invalid settings fail closed. Cookies are HttpOnly/SameSite=Lax and Secure in production. Sessions additionally require live unrevoked database records; never restore stateless JWT acceptance or browser localStorage tokens.

See [example settings](../backend/.env.example). Default collaboration/lexical retrieval/local contracts need no provider key. `requirements-dev.txt` includes the optional AI SDK for isolated mocked adapter regressions; minimal application runtime can install `requirements.txt` only. Actual model requests require explicit server opt-in, key and UI request and may incur cost. Optional trained local runtime is separately installed, trusted-artifact-bound and unverified here. Public GitHub GET imports and selected private App authorization are separate opt-ins; no CLI credential/token fallback. Voice/SMS/arbitrary tools/external writes remain disabled.

[Integrations](INTEGRATIONS.md) describes PDF/private access/index/grounded-answer bounds. [Intelligence hardening](INTELLIGENCE_HARDENING.md) describes trained adapters, fresh transmission checks, local recovery/verification, exact retention and quotas. Recovery's absolute `RECOVERY_OUTBOX_PATH` is private development/test delivery only; it sends no email and production rejects it. [External validation](EXTERNAL_VALIDATION_CHECKLIST.md) lists owner prerequisites without requiring secrets for ordinary tests.

## Migrating existing data

The current head is **`0018_sync_checkpoints`**. Never reset a database or run create_all/drop_all/historical destructive seeds to make an upgrade pass.

1. Stop all HTTP/worker writers and verify the intended `DATABASE_URL`.
2. Make a database-native backup to an exclusive private path and prove it restores into a **new disposable** destination. SQLite uses `python backup.py --output /absolute/private/new-backup.db`; use PostgreSQL-native procedures for PostgreSQL. Do not copy a live SQLite main file without WAL handling.
3. Run `python migrate.py` against the restored disposable copy first. Check owners, memberships, original messages, decisions, session validity and receipts.
4. Only after that review, migrate the intended database. Run `python migrate.py` again, `alembic current` and `alembic check`; expect head 0018 and no new upgrade operations.

Known legacy schemas are adopted explicitly, not blindly stamped. Historical messages remain in their original owners' private workspaces; fields/IDs/timestamps are preserved. Unknown/orphaned schemas stop for review. SQLite DDL failure can leave partial operations: preserve backups, investigate and restore only a disposable/approved destination. Destructive downgrades are intentionally blocked. Additive migrations 0010–0018 cover PDF provenance, indexes/private grants, shared limits, trained adapters, recovery, retention, answer modes and sync checkpoints.

Register through the UI. Optional `python seed.py --confirm-development --email developer@example.test --name Developer` prompts privately and leaves existing data intact; it is development-only.

## Verification

From the root with the backend environment active:

```bash
ruff check backend scripts
ruff format --check backend scripts
pytest -q backend/tests
python backend/evaluation/run.py --ranking legacy
python backend/evaluation/run.py --ranking coverage
python backend/evaluation/connected.py
python backend/evaluation/pilot.py
python scripts/check_secrets.py
pip install pip-audit==2.10.0
pip-audit -r backend/requirements-ai.txt --progress-spinner off
```

Backend tests migrate isolated SQLite files and block outbound sockets. Fake provider adapters prove local failure/authorization contracts, not live compatibility or quality. Evaluations use synthetic author/developer judgments; do not mix development and frozen holdout labels.

From `parallel-frontend`:

```bash
npm ci
npm audit --audit-level=high
npm run lint
npm run build
npx playwright install chromium
PARALLEL_TEST_PYTHON=../backend/.venv/bin/python npm test
```

Browser tests start a temporary migrated FastAPI/worker on 127.0.0.1:18001 and Vite on 15175, with separate synthetic account contexts. Their private outbox has bounded-prefix ownership-checked teardown. Keep these ports free; ordinary tests write screenshots/traces only to ignored Playwright output. Six widths/both themes, keyboard/dialog/citations, failures/retry, isolation, member removal, approval/rejection/replay, recovery and retention complement populated collaboration journeys. [Regression evidence](PRODUCT_REGRESSION_QA.md) records dated commands/results; CI repeats its five-job gate.

For PostgreSQL use a new disposable PostgreSQL 16 service with database name `parallel_test`, `APP_ENV=test` and a test-only URL. Migrate it twice and run `alembic check`; then run `backend/tests/postgres_{smoke,upgrade,intelligence,connected}.py` individually from the root. The latter scripts create guarded exclusive schemas. `PARALLEL_TEST_POSTGRES=true pytest -q backend/tests/test_recovery.py backend/tests/test_embedding_providers.py backend/tests/test_retention.py` uses exclusive schemas too. Never target a user database. `postgres_restore.py --container DISPOSABLE_CONTAINER_ID` creates exclusive source/destination databases and verifies all rows/receipts without overwriting the configured database; [operations](OPERATIONS.md) explains scope and cleanup.

## Product screenshots

```bash
PARALLEL_CAPTURE_PRODUCT=true PARALLEL_TEST_PYTHON=../backend/.venv/bin/python npm test -- showcase.spec.js
```

Run from `parallel-frontend`. This explicit command refreshes curated `docs/screenshots/product/` PNGs through real synthetic account, conversation, document, source, local-agent and exact-approval workflows. Ordinary CI runs the same assertions but writes captures only to Playwright results. The accepted decision is seeded through the authenticated API against the same isolated storage; other displayed state is created through actual UI flows. No generated mockups, live model claims or private user data. Review images before committing; preserve historical baseline captures.

## Documentation verification

From the root after frontend/Chromium installation:

```bash
npm install --prefix /tmp/parallel-doc-tools --no-save --package-lock=false mermaid@11.12.0
MERMAID_BUNDLE=/tmp/parallel-doc-tools/node_modules/mermaid/dist/mermaid.min.js node scripts/check_docs.cjs
```

The checker resolves actual local Markdown/image targets and parses/renders every Mermaid diagram. Mermaid is an isolated documentation tool, not a runtime dependency. The architecture sources must track implemented modules and states.

## Troubleshooting and operations

- Startup migration error: verify URL/working directory; back up and migrate the intended disposable copy first.
- Missing/failed provider: human messages persist; optional replies fail explicitly. Retry only by a new deliberate action.
- 404 workspace/source: missing membership, closure or unavailable evidence; UI filtering cannot authorize access.
- Task conflict/prerequisite failure: reload the current version and review dependencies; never force Done.
- Queued/failed run: verify worker/database/configuration, then inspect durable context/event/error state. `context_changed` needs a fresh plan; lease failure is not completion. Approved waits for execution; receipt proves the native effect.
- Cookie/CORS issues: match browser/API hostname and allowed origin; use HTTPS in production.
- Recovery token missing: only a configured private test/development channel exists; no email was sent.

`GET /health` is liveness; `/ready` checks database/head. [Operations](OPERATIONS.md) covers private logs, backup/new-path restoration, queue fairness, bounded leases and operator-installed supervision. Docker Compose is an optional local profile: configure generated private keys/passwords, preserve existing volumes, run frontend separately, and never use `down -v` on needed data. No production deployment or public release is authorized by these instructions.
