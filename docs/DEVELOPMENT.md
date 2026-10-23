# Development

## Requirements

Use Python 3.12 or 3.13 and Node 22.12+ (the lockfile also permits compatible Node 20.19+). CI tests Python 3.12/3.13 and Node 22. SQLite is bundled with Python. PostgreSQL 16 is the CI/Docker database target.

From backend:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python migrate.py
uvicorn main:app --host 127.0.0.1 --port 8000
```

From parallel-frontend:

```bash
npm ci
npm run dev
```

Vite uses port 5174; CORS must explicitly include the actual frontend origin. `VITE_API_BASE` defaults to http://localhost:8000. Keep localhost/127.0.0.1 consistent for cookies. Provider keys are never Vite variables.

## Settings

`APP_ENV` is development, test or production. `DATABASE_URL` is read after backend/.env loading. SQLite's relative path is relative to the process working directory: run backend commands from backend, or use an absolute SQLite URL.

Development can use a random process-local secret. For stable sessions generate a secret with `python -c 'import secrets; print(secrets.token_urlsafe(48))'` and set SECRET_KEY in backend/.env. Production requires at least 32 bytes and explicit HTTPS CORS_ORIGINS; cookies are Secure and HttpOnly. Local HTTP uses HttpOnly/SameSite=Lax cookies. A changed signing key invalidates old sessions.

No provider credentials are required. For optional AI replies install `pip install -r requirements-ai.txt` and set OPENAI_API_KEY explicitly. This is a server-owned model credential, not another user's account fallback. Real requests can incur cost; do not exercise them without authorization. Model selection is OPENAI_MODEL. Voice/SMS/research/external tool execution remains disabled.

## Migrating existing databases

1. Stop all writers. Verify DATABASE_URL points to the intended database.
2. Make a database-native backup and verify it can be restored. For SQLite use Python's sqlite3 backup API while the application is stopped; preserve WAL state through the backup API rather than copying a live main file. Use pg_dump/restore procedures for PostgreSQL.
3. Test `python migrate.py` against a disposable copy first.
4. Inspect account/message/activity counts and ownership. Only then run against the intended database.
5. Run `alembic current` and `alembic check`; expect 0004_intelligence and no new upgrade operations.

Revision 0001 adopts known legacy tables or creates an empty schema; it does not stamp a database blindly. Revision 0002 creates one private workspace per original user and assigns that user's message/activity rows there. Credentials, record IDs, existing timestamps and contents are preserved. Missing legacy creation timestamps are filled with the migration time so pagination remains ordered. No other user receives membership. Unknown schemas or orphan ownership stop migration for owner review; never delete records merely to make migration pass.

Re-running an already completed migration is safe. SQLite DDL failures can leave partial schema operations: retain the backup, investigate, and restore the disposable/approved backup before retrying. Destructive downgrade is intentionally blocked. Do not run create_all, drop_all or the historical seed script to repair migrations.

## Optional development account

Register through the UI. Alternatively, after migration:

```bash
python seed.py --confirm-development --email developer@example.test --name Developer
```

The script prompts privately for a password, is development-only, and leaves existing accounts/data intact. Importing it performs no work.

## Tests

```bash
ruff check . ../scripts
ruff format --check . ../scripts
pytest -q
python ../scripts/check_secrets.py
```

Backend tests migrate isolated SQLite files and block outbound sockets. Provider unit tests use mocks and do not prove live compatibility. Requirements-dev includes the optional AI SDK for mocked adapter regressions; the application runtime can still install only requirements.txt and run local intelligence without that SDK or provider keys.

Frontend:

```bash
npm run lint
npm run build
npx playwright install chromium
PARALLEL_TEST_PYTHON=../backend/.venv/bin/python npm test
```

Desktop/mobile browser tests create a temporary database/server on 127.0.0.1:18001 and frontend on 15175. Use an executable Python with the backend dependencies installed. Test accounts and databases are disposable; no paid keys are passed. CI also verifies PostgreSQL collaboration, optimistic task concurrency, session revocation, and upgrade from a populated Phase 1A schema.

## Docker (development)

In backend/.env set generated SECRET_KEY and POSTGRES_PASSWORD values. Use a URL-safe generated database password, or percent-encode it when composing DATABASE_URL. Then `docker compose up --build`. PostgreSQL must be healthy before the backend runs migrations and starts. Backend binds only localhost:8000; run the frontend separately. Existing volumes are preserved. Back up existing database volumes before upgrades. Never use `docker compose down -v` on data you need.

The image runs as an unprivileged user, includes application code, and excludes .env files/databases. Compose is a local development profile, not a production deployment recipe.

## Troubleshooting

- Migration-required startup error: verify the correct working directory/URL and run migrations after backup.
- Missing provider: human messages still save; optional AI returns 503.
- Provider failure: AI returns 502, creates no assistant success message, and preserves the human message.
- 404 workspace: the current account is not a member, or the workspace does not exist.
- 403 membership write: only the owner can add members.
- Invalid password input: registration requires 8+ characters and at most 72 UTF-8 bytes. Existing shorter legacy passwords can still authenticate.
- CORS/cookie failures: match hostnames, ports and allowed origins; production requires HTTPS.


## Phase 1B upgrade and collaboration usage

Run `python migrate.py` after the existing backup/disposable-copy procedure. Revision 0003 checks that each existing workspace has exactly one matching owner membership, then adds tables and constraints without resetting Phase 1A records. Inconsistent ownership stops before schema changes for owner review. Existing users must log in again: old stateless JWTs have no session record. The script refuses destructive downgrades. `alembic check` must show no model drift. CI tests both a populated SQLite Phase 1A file and an isolated PostgreSQL Phase 1A schema.

Use Members → Invite collaborator with a registered email. The recipient opens Invitations and accepts/declines. No email delivery is configured. Owners revoke pending invitations in Members; owners can remove members and transfer ownership to an existing member. A member may leave; an owner must transfer first. Adding a collaborator grants access to existing workspace history.

Use Tasks → New task. Choose an assignee from current members, a status, priority, optional due date, description and prerequisite tasks. Save commits real database state. API edits/archive require the current version; on conflict use Reload task and reconcile your draft. The UI offers up to 100 recent active prerequisite candidates; the API supports any active same-workspace task. Tasks are listed 50 per page and archived rather than deleted.

Mark prerequisites Done before completing dependents. Reopen completed dependents before reopening their prerequisite. Remove dependent links before archiving a prerequisite. Removing a member clears their assignments, including archived-task assignments, while preserving creator attribution and task contents.

Log out revokes the current session. Log out all sessions requires confirmation and invalidates all existing browser sessions. Other browsers return to sign-in on their next authenticated refresh. Auth throttling returns 429/Retry-After after 20 registration/login attempts per connection IP within 60 seconds; do not trust X-Forwarded-For without a controlled deployment design.

`postgres_smoke.py` and `postgres_upgrade.py` are CI-only scripts guarded by APP_ENV=test and the disposable parallel_test database name. The upgrade script creates an isolated schema in that test service; never point these scripts at user databases.


## Phase 2 + 3 development

After the backup and disposable-copy procedure, `python migrate.py` applies `0004_intelligence`. This adds decision/revision/source, visit, run/event and approval tables without changing existing Phase 1B records or invalidating its live sessions. Stop both HTTP and worker writers before upgrading a user database. `alembic current` and `alembic check` must agree with the new revision.

Start the backend, frontend and a separate worker using the same database URL:

```bash
cd backend
source .venv/bin/activate
python worker.py
```

`python worker.py --once` processes at most one queued job, expired lease or approval; a coordinator requires multiple iterations. For the optional development Docker profile, start the backend/database first, then `docker compose run --rm backend python worker.py`. Docker execution has not been verified in this phase. Never start a worker before the intended database is migrated. A missing worker leaves runs Queued, not Completed.

In Decisions, record a statement, rationale and linked source, revise it with a reason, or supersede an accepted decision with another accepted record. In Intelligence, inspect a visit-relative briefing, apply a timestamp, mark changes seen, or search current/historical source records. In Agents & approvals, request a local status/dependency/handoff report and inspect its child runs, context and events. Select publication only when you want an owner to review the exact report for posting to Conversation. Approval and publication are separate persisted states.

Additional verification from the repository root:

```bash
python backend/evaluation/run.py
python scripts/check_secrets.py
```

CI runs PostgreSQL collaboration plus `postgres_intelligence.py`: populated Phase 1B preservation, source-linked decisions, concurrent revisions, SQL retrieval, delegated handoffs and competing-worker approval publication. Those scripts require APP_ENV=test and the disposable parallel_test service; never target a user database. Browser scenarios use synthetic accounts, real localhost HTTP, SQLite and the same worker implementation. See [Evaluation](EVALUATION.md) and [Agent orchestration](AGENT_ORCHESTRATION.md) for metrics and recovery commands.

Troubleshooting: Queued means check the worker uses the same migrated DATABASE_URL; `task_blocked` means complete prerequisites or use dependency analysis; `context_changed` means project state changed during computation/approval and a fresh run is needed; `lease_expired` means interrupted execution failed visibly and can be explicitly retried. A pending approval can only be answered by the current owner. Approved means the worker still has to execute; Executed contains the publication message receipt.


## Documentation validation

Screenshots are captured by the real `intelligence.spec.js` desktop/mobile scenarios into Playwright test output; curated copies live in `docs/screenshots/` and contain synthetic accounts only. Do not substitute generated mockups. To validate Markdown links and parse/render every Mermaid diagram without adding a runtime dependency:

```bash
npm install --prefix /tmp/parallel-doc-tools --no-save --package-lock=false mermaid@11.12.0
MERMAID_BUNDLE=/tmp/parallel-doc-tools/node_modules/mermaid/dist/mermaid.min.js node scripts/check_docs.cjs
```

Run from the repository root after frontend dependency/Chromium installation. The script uses that Playwright browser and checks actual local link/image targets. This validation is optional locally and was executed for the documentation overhaul; the core CI has no Mermaid package dependency.
