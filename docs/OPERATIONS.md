# Operations and recovery

This is a local/team foundation, not a public deployment recipe. Keep the HTTP process, worker and migrations on the same configured database. No user database was reset or migrated during implementation verification.

## Readiness and worker health

`GET /health` is process liveness. `GET /ready` checks database connectivity and the expected Alembic head (`0009_worker_health`), returning 503 on failure. Startup refuses a missing/outdated schema. Neither endpoint exposes credentials, workspace data or provider errors.

Run `python worker.py` from backend with the intended environment. The worker processes native approvals, local runs, document extraction and explicitly enabled public GitHub syncs. `--once` handles at most one operation, so a coordinator needs several iterations. Worker heartbeat records update approximately every ten seconds and become stale after 60 seconds. Overview distinguishes recent polling from actual job success; inspect each durable state/receipt to establish success.

Ctrl-C closes the worker engine and records a stopped heartbeat. HTTP lifespan disposes its engine. A forced termination can leave processing leases, which a later worker marks failed; it never guesses completion. Leases are 60 seconds for agents, 30 for document extraction and 45 for repository sync. Run retries are explicit and bounded to three attempts; extraction retries require a new uploaded revision; transient/rate-limited repository syncs have at most three attempts with backoff.

The sequential worker prioritizes approvals/runs before ingestion/sync. Sustained run arrivals can delay other queues. There is no fair/distributed scheduler, job supervisor, fleet monitor or hard process sandbox bundled. Deployments need supervised restarts, queue/latency alerting and resource limits. Polling does not prove execution or production scalability.

## Safe request logs

HTTP middleware emits JSON containing a server-generated request ID, method, **route template**, status and duration. Query strings, path values, account identifiers, bodies, cookies, authorization headers, provider credentials and raw exceptions are omitted. `X-Request-ID` is returned; unexpected errors expose only a generic failure and that ID. Configure log collection/retention at deployment. Uvicorn access logs are separate: disable them if request-path privacy requires it, for example `uvicorn main:app --no-access-log`.

## Back up before upgrades

Stop HTTP/worker writers, verify DATABASE_URL, and use a new private backup path. From backend:

```bash
python backup.py --output /absolute/private/path/parallel-before-upgrade.db
```

The SQLite utility uses the native backup API, opens the source read-only, creates the output exclusively with mode 0600, refuses overwrite/source equality, and checks integrity. It does not remove failed outputs. It accepts file-backed SQLite only. Keep backups out of the repository and off public/shared paths. Copying a live `.db` file without WAL handling is insufficient.

For PostgreSQL use an operator-reviewed `pg_dump`/restore procedure with credentials supplied privately. Test restoration in a disposable database; do not replace production data merely to verify a backup. The SQLite backup/restore path is covered by isolated tests. No live production restore or PostgreSQL operational backup drill is claimed.

Test migrations and application checks against the restored disposable copy first. Then follow [Development](DEVELOPMENT.md) before updating the intended database. Migrations 0005–0009 add connected-knowledge/action/heartbeat tables and nullable/defaulted revocation metadata; existing records and live session data remain intact. Populated Phase 1B/Phase 3 preservation and foreign keys are tested; downgrade is intentionally blocked.

## Retention and deployment gaps

Raw document uploads are discarded after terminal extraction/cancellation; document revisions/passages, imported history, answers, runs, approvals, receipts, sessions and activity are retained. Archiving/revocation restricts application retrieval without deleting the audit record. Heartbeats older than seven days are operational telemetry and are pruned. Application storage is not encrypted at rest; protect database files, volumes, backups and logs.

Before public deployment establish TLS/trusted ingress, shared abuse/cost throttling, account verification/recovery, database/backup encryption, restore drills, retention policies and monitored worker supervision. Login throttling is process-local. Answer/sync quotas are workspace/database serialized, not a complete global or distributed abuse-control service. Model calls have no global organization spend cap; configure provider-side limits before enabling them. Historical exposed Plivo credentials still require owner-side revocation/rotation.
