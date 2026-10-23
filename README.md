# Parallel

Parallel is a persistent project workspace for humans and AI agents. Its direction is **Project Continuity Intelligence**: keeping decisions, context, ownership, and verified outcomes useful across sessions.

## Current functionality

Phase 1A provides cookie authentication, private workspaces, owner-managed membership for existing accounts, shared workspace messages, scoped activity, optional AI replies, and database migrations. The React application restores sessions after reload. Human messaging works without provider credentials.

Tasks, decision records, invitation delivery, semantic memory, durable agent workflows, voice/SMS, and external tool execution are not released features. Historical integration code is retained as disabled reference material. Live AI-provider behavior has not been verified in this phase.

## Stack

React 19 / Vite frontend; modular FastAPI backend; SQLAlchemy with Alembic; SQLite for local development and PostgreSQL 16 CI coverage. Python 3.12–3.13 and Node 22.12+ are the supported development targets.

## Local setup

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python migrate.py
uvicorn main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
cd parallel-frontend
npm ci
npm run dev
```

Open http://localhost:5174. Register an account; its initial workspace is private. Create another workspace and add a collaborator's existing account by email. Adding membership grants access to that workspace's history.

Development generates a process-local signing secret when none is supplied; set a generated `SECRET_KEY` in `backend/.env` to retain sessions across backend restarts. Production requires an explicit secret and HTTPS origins. Never use a sample password or provider credential.

**Before migrating an existing database, stop the application and create a verified backup.** Legacy records are assigned to private workspaces by original `user_id`; no global sharing is inferred. Do not run historical seed instructions. See [development](docs/DEVELOPMENT.md) for the migration and recovery procedure.

## Verification

```bash
cd backend
ruff check . ../scripts
ruff format --check . ../scripts
pytest -q
cd ../parallel-frontend
npm run lint
npm run build
npx playwright install chromium
PARALLEL_TEST_PYTHON=../backend/.venv/bin/python npm test
```

Browser tests use disposable databases and local servers; no provider calls. Run `python scripts/check_secrets.py` from the repository root before commits. GitHub Actions verifies Python 3.12/3.13, PostgreSQL migrations, frontend build/lint, and the browser workflow.

## Documentation and roadmap

- [Product vision](docs/PRODUCT_VISION.md)
- [Architecture and authorization](docs/ARCHITECTURE.md)
- [Development, migrations and Docker](docs/DEVELOPMENT.md)
- [Security and credential rotation](docs/SECURITY.md)
- [Audit baseline and remediation](docs/REPOSITORY_AUDIT.md)
- [Development roadmap](docs/DEVELOPMENT_ROADMAP.md)
- [Engineering instructions](AGENTS.md)

Phase 1B adds complete collaboration flows, tasks, invitations, and membership lifecycle. Later phases add source-linked decisions and evaluated continuity, durable coordination, approved integrations, and release operations.

## History and licensing

This repository preserves the original Parallel hackathon project's history and human contributions. Historical feature descriptions are not evidence of current functionality. No license granting redistribution has been added; existing rights remain unchanged.
