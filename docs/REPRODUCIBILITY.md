# Reproducibility

Validation date: 9 November 2026 (America/Los_Angeles). See [final validation](FINAL_VALIDATION_REPORT.md) for outcomes and limitations.

## Local installation

Follow the [README](../README.md#run-locally) with Python 3.12/3.13 and Node 22.12+. Install pinned requirements and `npm ci`; migrate before starting API/worker. Both processes must use the same database and signing configuration. A new checkout requires `npx playwright install chromium` before browser tests. No provider credentials are required for the core workflows.

## Docker

The [Compose file](../backend/docker-compose.yml) builds a nonroot Python image, starts PostgreSQL 16 with a named volume, starts the API only after database health, migrates before serving, and starts the worker only after API readiness confirms the schema. HTTP is bound to loopback; PostgreSQL is not published. API/worker share one environment mapping. The frontend runs separately. This is a local development profile, not production deployment.

Use the generated private environment file and commands in the README. Preserve that file and the named volume across stops. Never use `down -v` against needed data. Existing databases require backup, tested restoration and a disposable migration rehearsal before upgrade. No schema/backfill is introduced by this release.

Run `python3 scripts/compose_smoke.py` only against a disposable local stack at port 8000. It creates two synthetic accounts, a workspace, a task and a document; waits for actual extraction and a delegated handoff; replays the same run key; checks another account cannot read tasks, documents or the run. Polling is bounded to 60 seconds. Failures exit nonzero. It retains records for inspection and never calls a provider.

The validation project used the exclusive name `parallel-final-validation` and a generated temporary environment file. A real image build, fresh initialization, HTTP cookie authentication, ingestion and coordinator completion succeeded. A full service restart preserved the completed run and ready document in PostgreSQL. This confirms the measured synthetic scenario, not interrupted production recovery. CI now runs the real Compose smoke on each PR/main push in addition to existing PostgreSQL migration, lease/concurrency and restore drills.

`docker compose restart` does not reapply dependency startup ordering. For a stopped stack, use `up -d --wait`; verify `ps`, `/ready` and actual job outcomes after any database outage. A process being running does not prove successful work. Optional connectors/providers must be configured consistently on API/worker through an operator-reviewed override; this default profile deliberately enables none.

## Verification commands

From the root with the development environment active:

```bash
ruff check backend scripts
ruff format --check backend scripts
pytest -q backend/tests
python scripts/check_secrets.py
pip-audit -r backend/requirements-ai.txt --progress-spinner off
python backend/evaluation/run.py --ranking legacy
python backend/evaluation/run.py --ranking coverage
python backend/evaluation/connected.py
python backend/evaluation/pilot.py
```

In `parallel-frontend`: `npm ci`, `npm audit --audit-level=high`, `npm run lint`, `npm run build`, `npx playwright install chromium`, then `PARALLEL_TEST_PYTHON=/absolute/path/to/python npm test`. The browser suite creates disposable real API/database/worker services. Optional ML runtime/live private authorization/model quality remain outside these checks. [Development](DEVELOPMENT.md) and [operations](OPERATIONS.md) retain detailed backup, migration and supervisor procedures.
