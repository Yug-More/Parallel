# Parallel

Parallel is a persistent project workspace for humans and AI agents. Its direction is **Project Continuity Intelligence**: keeping decisions, context, ownership, and verified outcomes useful across sessions.

## Current functionality

Phase 1B adds in-app invitations, membership removal and ownership transfer, persistent collaborative tasks, task dependencies, and server-side session revocation to the Phase 1A workspace foundation. Users can invite a registered collaborator, accept access, exchange messages, assign and update tasks, leave, and return to the same database-backed state.

Task statuses are To Do, In Progress, Blocked and Done. Tasks include priority, due date, descriptions, creator/assignee attribution and safe archival. Dependencies reject cycles and prevent premature completion. Stale edits return a conflict rather than overwrite a teammate's changes.

Invitations appear in the app; **no email is sent**. Only the recipient can accept or decline. Owners can revoke pending invitations and transfer ownership to a current member. Removing a member immediately blocks future API access and unassigns their tasks. The UI clears cached workspace content on its next authorization refresh.

Human collaboration requires no provider credentials. Optional AI replies remain conversation-only and unverified against a live provider. Source-linked decisions, semantic memory, durable agent workflows, voice/SMS, and external tool execution remain future work.

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

Open http://localhost:5174. Register an account; its initial workspace is private. Create another workspace, open Members, and invite a collaborator's registered email. They accept through Invitations. Acceptance grants access to that workspace's history.

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

Desktop and mobile Chromium tests use disposable databases, separate account contexts, and real local servers; no provider calls. Run `python scripts/check_secrets.py` from the repository root before commits. GitHub Actions verifies Python 3.12/3.13, PostgreSQL migrations, frontend build/lint, and the browser workflow.

## Documentation and roadmap

- [Product vision](docs/PRODUCT_VISION.md)
- [Architecture and authorization](docs/ARCHITECTURE.md)
- [Development, migrations and Docker](docs/DEVELOPMENT.md)
- [Security and credential rotation](docs/SECURITY.md)
- [Audit baseline and remediation](docs/REPOSITORY_AUDIT.md)
- [Development roadmap](docs/DEVELOPMENT_ROADMAP.md)
- [Engineering instructions](AGENTS.md)

Phase 2 begins with source-linked decisions and permission-aware project continuity. Later phases add source-linked decisions and evaluated continuity, durable coordination, approved integrations, and release operations.

## History and licensing

This repository preserves the original Parallel hackathon project's history and human contributions. Historical feature descriptions are not evidence of current functionality. No license granting redistribution has been added; existing rights remain unchanged.
