# Operations and recovery

Runtime configuration, hardening and external limits: [trained intelligence and operational hardening](INTELLIGENCE_HARDENING.md). Earlier milestone sections below describe their original scope.

This is a local/team foundation, not a public deployment recipe. Keep the HTTP process, worker and migrations on the same configured database. No user database was reset or migrated during implementation verification.

## Readiness and worker health

`GET /health` is process liveness. `GET /ready` checks database connectivity and the expected Alembic head (`0018_sync_checkpoints`), returning 503 on failure. Startup refuses a missing/outdated schema. Neither endpoint exposes credentials, workspace data or provider errors.

Run `python worker.py` from backend with the intended environment. The worker processes native approvals, local runs, document extraction and explicitly enabled public GitHub syncs. `--once` handles at most one operation, so a coordinator needs several iterations. Worker heartbeat records update approximately every ten seconds and become stale after 60 seconds. Overview distinguishes recent polling from actual job success; inspect each durable state/receipt to establish success.

Ctrl-C closes the worker engine and records a stopped heartbeat. HTTP lifespan disposes its engine. A forced termination can leave processing leases, which a later worker marks failed; it never guesses completion. Leases are 60 seconds for agents, 30 for document extraction and 45 for public repository sync and 120 for private sync; optional indexing uses 20 seconds. Run retries are explicit and bounded to three attempts; extraction retries require a new uploaded revision; transient/rate-limited repository syncs have at most three attempts with backoff.

The sequential worker rotates fairly between native approvals, runs, ingestion, enabled sync and indexing queues. This prevents one queue from always winning; there is no distributed scheduler, installed supervisor, fleet monitor or complete process sandbox. Deployments need supervised restarts, queue/latency alerting and resource limits. Polling does not prove execution or production scalability.

## Safe request logs

HTTP middleware emits JSON containing a server-generated request ID, method, **route template**, status and duration. Query strings, path values, account identifiers, bodies, cookies, authorization headers, provider credentials and raw exceptions are omitted. `X-Request-ID` is returned; unexpected errors expose only a generic failure and that ID. Configure log collection/retention at deployment. Uvicorn access logs are separate: disable them if request-path privacy requires it, for example `uvicorn main:app --no-access-log`.

## Back up before upgrades

Stop HTTP/worker writers, verify DATABASE_URL, and use a new private backup path. From backend:

```bash
python backup.py --output /absolute/private/path/parallel-before-upgrade.db
```

The SQLite utility uses the native backup API, opens the source read-only, creates the output exclusively with mode 0600, refuses overwrite/source equality, and checks integrity. It does not remove failed outputs. It accepts file-backed SQLite only. Keep backups out of the repository and off public/shared paths. Copying a live `.db` file without WAL handling is insufficient.

For PostgreSQL use an operator-reviewed `pg_dump`/restore procedure with credentials supplied privately. Test restoration in a disposable database; do not replace production data merely to verify a backup. The SQLite backup/restore path is covered by isolated tests. The isolated PostgreSQL dump/restore drill verifies synthetic data and receipts into exclusive new databases. No live production restore, offsite-key recovery or production recovery objective is claimed.

Test migrations and application checks against the restored disposable copy first. Then follow [Development](DEVELOPMENT.md) before updating the intended database. Migrations 0005–0018 add connected knowledge, actions, heartbeats, indexes/private grants, trained adapters, recovery/retention and checkpoints; existing records and live session data remain intact. Populated Phase 1B/Phase 3 preservation and foreign keys are tested; downgrade is intentionally blocked.

## Retention and deployment gaps

Raw document uploads are discarded after terminal extraction/cancellation; document revisions/passages, imported history, answers, runs, approvals, receipts and activity are retained until their applicable explicit retention operation. Expired operational authentication/recovery records have bounded cleanup as described in the hardening guide. Archiving/revocation restricts application retrieval without deleting the audit record. Heartbeats older than seven days are operational telemetry and are pruned. Application storage is not encrypted at rest; protect database files, volumes, backups and logs.

Before public deployment establish TLS/trusted ingress, broader account/organization abuse controls, a reviewed production recovery/delivery channel, database/backup encryption, production restore drills and an operational retention policy and monitored worker supervision. Authentication uses shared atomic fixed-minute database counters (20 attempts per peer/minute), keyed by HMAC rather than raw IP. Boundary bursts can cross adjacent windows; trusted ingress controls remain necessary. Answer/sync quotas are workspace/database serialized, not a complete global or distributed abuse-control service. Model calls have no global organization spend cap; configure provider-side limits before enabling them. Historical exposed Plivo credentials still require owner-side revocation/rotation.

## Restore and supervision drill

`python restore.py --source /private/backup.db --output /private/NEW-restored.db` creates a new 0600 database exclusively, never overwrites an existing file, migrates the copy, and checks integrity/foreign keys. Tests verify the original source bytes stay unchanged and a populated Phase 6 database preserves every original field on repeated upgrades. This is an isolated SQLite recovery drill, not a production/PostgreSQL restore certification. Back up the separate GitHub credential encryption key as well; otherwise restored grants cannot decrypt.

[Worker systemd example](../deploy/parallel-worker.service) is an operator-reviewed Linux template. It uses a dedicated unprivileged user, private environment file, restart-on-failure and SIGINT shutdown; it has not been installed or used to deploy this repository. Replace paths and configure the database privately. Ensure the HTTP service uses the same migrated database and stable SECRET_KEY. Monitor job latency/failures rather than treating a recent heartbeat as success. Private syncs may occupy a worker longer than the heartbeat threshold; concurrency/throughput remain unmeasured.

Shared counters expire after one day and contain only HMAC keys/window/count; raw IPs are not retained. Durable project records still use archive/revocation rather than hard deletion. Pending device grants are cleared when completed/expired/failed (expiry is materialized on owner inspection); an operator retention process for abandoned historical rows is still required. No existing user database or deployment was changed.

## Phase 12 restoration and retained data

[The executed synthetic PostgreSQL drill](postgres-restore-phase12.json) compared 32 tables/24 rows including exact native execution receipts, preserved the source and verified repeat migration. The same exclusive-new-database drill runs in CI. It is not a production backup or RTO/RPO claim. See [the reproducible command and retention exceptions](INTELLIGENCE_HARDENING.md).

`RECOVERY_OUTBOX_PATH` is development/test only, absolute and private; production rejects it. Keep outbox files out of web roots and backups intended for sharing. Database token expiry does not clean the private delivery files; the operator must remove expired outbox files. Worker operational retention expires abandoned recovery jobs at thirty minutes, retains recovery metadata seven days and retains expired sessions seven days after expiry. It never expires native project history or retention receipts automatically.

Heartbeat status means recently alive, including while a job waits on I/O. Inspect durable job state/checkpoints and receipts for actual progress. Queue exceptions back off for thirty seconds; persistent failures need operator investigation. Existing systemd/Compose templates remain operator-installed examples, not a managed deployment.

## Current operator boundaries

Private local account recovery/verification, signed owner erasure/closure previews, operational metadata cleanup, independent worker heartbeat/backoff and isolated PostgreSQL restoration are implemented. They do not provide real email, production service installation, backup erasure or deployment readiness. [External validation checklist](EXTERNAL_VALIDATION_CHECKLIST.md) specifies the remaining owner steps. The current head is shared by HTTP and worker; settings mismatch must fail closed.
