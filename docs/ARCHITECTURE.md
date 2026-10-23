# Architecture

## Runtime

Parallel remains a modular monolith. `backend/main.py` composes HTTP middleware and routers, validates migrated schema at startup, and owns application-specific engine/session construction. Startup does not migrate or seed the database. `config.py` loads backend/.env before constructing database settings and validates environment, signing secret, and CORS origins.

- `security.py`: request schemas, bcrypt boundaries, PyJWT cookies and membership checks.
- `api/auth.py`: account/session operations. Registration atomically creates credentials and a private workspace.
- `api/workspaces.py`: workspace creation/listing, owner-managed membership and ownership transfer.
- `api/invitations.py` / `api/tasks.py`: account-bound invitations and versioned task/dependency operations.
- `collaboration.py` / `rate_limit.py`: workspace serialization and bounded authentication throttling.
- `api/messages.py`: membership-scoped human messages, cursor pagination, activity and recent AI context.
- `providers.py`: optional lazy OpenAI adapter with deadline, no automatic retries, sanitized failures and no external tools.
- `database.py` / `models.py`: explicit engine creation, per-request transactions, foreign-key enforcement on SQLite, and ORM entities.
- `migrations/`: legacy adoption and private ownership backfill.
- `legacy/`: historical code renamed with `.disabled`, excluded from runtime and tooling; it is not a supported integration implementation.

The frontend preserves React/Vite, theme and message components. `App.jsx` restores the cookie session. `Dashboard.jsx` selects/creates workspaces, presents invitation/task/member workflows, and polls scoped conversation/activity/membership data. Switching workspaces cancels old reads and hides stale data. Human message submission is separate from optional AI generation. `api.js` provides consistent credentialed requests.

## Data ownership

User -> UserCredential. Workspace -> owner User. Membership has composite key (workspace_id, user_id) and constrained role owner/member. Message and Activity require workspace_id and preserve user_id as actor/legacy ownership. Workspace+time indexes support scoped queries.

Each authenticated request checks membership before resource queries, writes or provider calls. Missing membership returns 404, including guessed IDs; member-management writes require owner role. Roles from signup are descriptive profile fields and grant no permissions. There is no global roster, context, message, activity or summary endpoint.

Private legacy workspaces derive stable UUIDs from original user IDs. No membership is inferred from display names. New workspace IDs and actor IDs are immutable. Integration connections are not enabled; future connections must use IDs, never editable names or another user's provider fallback.

## API

Auth: POST /auth/register, /auth/login, /auth/logout; GET /me.
Workspaces: GET/POST /workspaces; GET /workspaces/{id}; GET/POST /workspaces/{id}/members.
Conversation: GET/POST /workspaces/{id}/messages; POST /workspaces/{id}/agent-replies; GET /workspaces/{id}/activity.
Messages return the latest 50, chronological within each page, with a maximum limit of 100 and an optional `before` message-ID cursor. AI context is the most recent 30 messages in that workspace, bounded per message. AI replies require an existing human message ID from the authorized workspace. Requests are synchronous; durable runs and idempotent regeneration belong in later phases.

Legacy integration/global APIs return 410. Voice WebSocket closes with policy violation before execution. No runtime enable switch exists for voice, SMS or external actions.

## Tradeoffs

Polling is adequate for this foundation; SSE comes after collaboration semantics stabilize. SQLite supports easy local use; PostgreSQL verification runs in CI. Alembic adopts known legacy tables and refuses orphan ownership. Migration backups are required because SQLite DDL is not fully transactional. Downgrades that remove isolation or data are deliberately rejected.

Sessions expire after 24 hours and now require a revocable database record; logout invalidates the server-side session. Development secrets may be ephemeral. Production transport settings are stricter, but deployment hardening remains required before release.


## Phase 1B collaboration architecture

Alembic revision `0003_collaboration` adds revocable sessions, invitations, tasks/dependencies, a workspace revision counter and a partial unique owner index. All Phase 1A records remain intact. Old stateless cookies deliberately require a fresh login after upgrade; no account or project data is reset.

`collaboration.py` acquires a workspace UPDATE lock before checking write permissions. PostgreSQL row locks and SQLite writer serialization prevent membership removal, assignment, invitations, dependency edits and ownership transfer from violating each other's invariants. Read APIs still enforce current membership. Provider calls run outside this lock and recheck membership before persisting a result.

`api/invitations.py` provides owner invitation creation/history/revocation, a recipient inbox, and recipient-only acceptance/decline. Invitations target existing immutable account IDs; UUIDs are identifiers, not bearer credentials. States are pending/accepted/declined/revoked/expired. Expiry is evaluated on reads and checked again during transitions; expired pending rows are materialized before re-inviting. A partial unique index permits only one pending invitation per workspace/recipient. Re-inviting creates a new ID. Membership acceptance and activity commit atomically.

Only owners manage membership. Members may leave; owners must transfer first. Transfer atomically demotes the old owner, promotes an existing member and updates workspace.owner_id. Pending invitations are revoked on transfer. Removal unassigns all tasks attributed to the removed assignee, increments their task versions and preserves messages, tasks and creator attribution. The Phase 1A owner-only POST /members API remains a compatibility/admin operation; the frontend uses recipient-approved invitations. It closes pending invitations when direct access is granted. No arbitrary admin role or role-update API exists.

`api/tasks.py` supports workspace-scoped listing/details/create/PATCH/archive. All current members can edit tasks. Tasks have title, description, creator, optional current-member assignee, status, priority, optional date, version, archived flag and UTC creation/update times. Composite foreign keys enforce assignee membership and same-workspace dependency edges. Task updates require a matching version; conflicts return 409 and no-op edits emit no activity. Active lists paginate 50 per page, bounded to 100 per request.

Dependencies form an application-validated DAG, serialized under the workspace lock. Self/cross-workspace/archived prerequisites and cycles are rejected. Done requires all prerequisites done; reopening a prerequisite is blocked while an active dependent is done. Archiving a prerequisite with active dependents is rejected; archiving a dependent removes its own outgoing dependency links without deleting task records.

AuthSession stores a SHA-256 digest of a random JWT jti, user ID, expiry and optional revocation time. Every authenticated request verifies JWT signature/expiry and the live database session. Logout revokes one session; logout-all revokes all existing account sessions. A bounded, thread-safe per-process IP limiter allows 20 registration/login attempts per 60 seconds, uses the ASGI client address, and does not parse forwarding headers itself. Configure server-side trusted-proxy handling explicitly. Distributed deployment requires a shared limiter at a trusted ingress.

The frontend now has Conversation, Tasks, Members, Activity and an invitation inbox. Confirmations protect removal, transfer, leave, archive, revoke and logout-all. Separate components own task drafts and member/inbox flows. Polling refreshes authorization every two seconds; 401 unmounts protected UI, and missing membership clears cached content and task drafts. Already-read information cannot be withdrawn; the server denies future requests immediately. Task forms retain unsaved edits during polling and provide explicit reload after version conflicts.

New routes: GET /invitations; POST /invitations/{id}/{accept|decline}; GET/POST /workspaces/{id}/invitations; POST /workspaces/{id}/invitations/{invitation_id}/revoke; DELETE /workspaces/{id}/members/{member_id}; POST /workspaces/{id}/leave; POST /workspaces/{id}/transfer-ownership; GET/POST /workspaces/{id}/tasks; GET/PATCH /workspaces/{id}/tasks/{task_id}; POST /workspaces/{id}/tasks/{task_id}/archive; POST /auth/logout-all. OpenAPI documents input contracts. Task PATCH/archive must include version. Tasks use `todo`, `in_progress`, `blocked`, `done`; priorities `low`, `medium`, `high`, `urgent`.
