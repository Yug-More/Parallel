# Architecture

## Runtime

Parallel remains a modular monolith. `backend/main.py` composes HTTP middleware and routers, validates migrated schema at startup, and owns application-specific engine/session construction. Startup does not migrate or seed the database. `config.py` loads backend/.env before constructing database settings and validates environment, signing secret, and CORS origins.

- `security.py`: request schemas, bcrypt boundaries, PyJWT cookies and membership checks.
- `api/auth.py`: account/session operations. Registration atomically creates credentials and a private workspace.
- `api/workspaces.py`: workspace creation/listing, membership listing and owner-only addition of existing accounts.
- `api/messages.py`: membership-scoped human messages, cursor pagination, activity and recent AI context.
- `providers.py`: optional lazy OpenAI adapter with deadline, no automatic retries, sanitized failures and no external tools.
- `database.py` / `models.py`: explicit engine creation, per-request transactions, foreign-key enforcement on SQLite, and ORM entities.
- `migrations/`: legacy adoption and private ownership backfill.
- `legacy/`: historical code renamed with `.disabled`, excluded from runtime and tooling; it is not a supported integration implementation.

The frontend preserves React/Vite, theme and message components. `App.jsx` restores the cookie session. `Dashboard.jsx` selects/creates workspaces, adds existing accounts, and polls scoped conversation/activity/membership data. Switching workspaces cancels old reads and hides stale data. Human message submission is separate from optional AI generation. `api.js` provides consistent credentialed requests.

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

Sessions expire after 24 hours. Logout deletes the browser cookie; server-side token revocation and session management remain follow-up work. Development secrets may be ephemeral. Production transport settings are stricter, but deployment hardening remains required before release.
