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

No provider credentials are required. For optional AI replies install `pip install -r requirements-ai.txt` and set OPENAI_API_KEY explicitly. This is a server-owned model credential, not another user's account fallback. Real requests can incur cost; do not exercise them without authorization. Model selection is OPENAI_MODEL. Voice/SMS/research/tool execution cannot be enabled in Phase 1A.

## Migrating existing databases

1. Stop all writers. Verify DATABASE_URL points to the intended database.
2. Make a database-native backup and verify it can be restored. For SQLite use Python's sqlite3 backup API while the application is stopped; preserve WAL state through the backup API rather than copying a live main file. Use pg_dump/restore procedures for PostgreSQL.
3. Test `python migrate.py` against a disposable copy first.
4. Inspect account/message/activity counts and ownership. Only then run against the intended database.
5. Run `alembic current` and `alembic check`; expect 0002_workspaces and no new upgrade operations.

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

Backend tests migrate isolated SQLite files and block outbound sockets. Provider unit tests use mocks and do not prove live compatibility. Requirements-dev and requirements-ai are installed in CI so adapter tests can import the optional SDK.

Frontend:

```bash
npm run lint
npm run build
npx playwright install chromium
PARALLEL_TEST_PYTHON=../backend/.venv/bin/python npm test
```

Browser tests create a temporary database/server on 127.0.0.1:18001 and frontend on 15175. Use an executable Python with the backend dependencies installed. Test accounts and databases are disposable; no paid keys are passed. CI also verifies PostgreSQL migration and registration/message persistence.

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
