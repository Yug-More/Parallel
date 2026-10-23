# Security

## Historical credential exposure: owner action required

The original backend/check_plivo.py contained Plivo authentication material. It has been removed from current source and the diagnostic is disabled. The credential remains in historical commits. **The owner must rotate/revoke the exposed credential and review provider access logs.** No credential was tested, rotated, revoked or reproduced in reports. No history rewriting was performed. Source cleanup is not credential revocation.

## Trust boundaries

The browser supplies untrusted input. Authentication establishes a user; membership establishes access to a workspace. Every message/activity/member/context operation checks membership before access. Owner-only membership addition grants historical workspace access; use a new workspace when history should remain private. Display names and profile roles grant no authority.

PyJWT replaces the advisory-affected legacy JWT dependency. JWTs require subject, expiry, a session identifier and the configured HS256 signature, plus a matching unrevoked database session. Cookies are HttpOnly and SameSite=Lax, Secure in production; unsafe browser requests reject foreign origins/cross-site fetch metadata. Production settings require an explicit signing key and HTTPS origins. Never log passwords, JWTs, provider keys, transcript bodies or raw provider exceptions. Validation responses omit input values.

SQLite foreign keys are enabled. Migrations preserve historical ownership in individual private workspaces and refuse orphaned records. Backups and restore verification precede existing-data migration. Unsupported downgrade cannot remove workspace boundaries.

## Providers and external actions

Only optional OpenAI text replies are available. Retrieval is workspace-scoped and bounded; provider clients are constructed lazily, close after use, have a deadline, and do not retry automatically. Messages persist independently of provider success. No live-provider verification is claimed.

Voice, SMS, research, Composio, telephony configuration and summary/email/document execution are unavailable, including direct HTTP and WebSocket requests. Archived code is non-executable reference material and must not be reactivated as-is. This deliberately removes unauthenticated callbacks, editable-name integration identities, provider-account fallback, and misleading completion reporting from the active service.

Before re-enabling integrations require signed/replay-resistant webhooks, authenticated caller identity, immutable connection ownership, capability checks, least privilege, explicit approval for consequential writes, durable execution states, idempotency and independently validated provider outcomes. The model must never decide authorization.

## Guardrails and tests

`scripts/check_secrets.py` scans current tracked/unignored source for supported provider credentials, literal auth tuples and private keys, printing locations only. It runs in CI and has a detection regression test. This limited pattern guard is not a full entropy/history scan or proof of no secrets; enable GitHub secret scanning/push protection where available through an owner-reviewed settings change.

Tests cover anonymous access, cross-workspace reads/writes/context, membership permissions, signatures/expiry, password byte limits, origin enforcement, migration preservation, disabled integrations and sanitized provider failures. Tests prohibit paid network calls.

## Remaining release risks

No production deployment is authorized or validated. Before release add operational monitoring, backup/restore drills, email verification, password recovery, shared rate limiting for distributed deployments, dependency vulnerability review, and abuse/cost quotas. Frontend advisory checks run in CI; the initial lockfile advisories were resolved through compatible updates. Revoked sessions, including copied cookies, cannot authenticate. The frontend uses recipient-approved in-app invitations. The Phase 1A direct member-add API remains owner-only for compatibility; owners are trusted to grant access. AI-generated text remains untrusted and may be inaccurate. Model output is rendered as text; do not introduce raw HTML rendering.

Development's ephemeral secret invalidates sessions on process restart; set an explicit generated local secret if continuity is needed. Full prompt-injection mitigation and durable agent execution remain later work. No paid provider actions or production resources were used for this phase.


## Phase 1B guarantees and remaining limits

Every workspace write is serialized before membership/ownership validation. Read endpoints, task details, dependency references and AI context are workspace-scoped. Member removal revokes future requests and unassigns tasks atomically; ownership transfer leaves exactly one owner and revokes pending invitations. All new activity is persisted in the same transaction as its operation. Stale task edits and repeated invitation transitions fail without duplicate activity. Creation requests are not automatically retried; repeating a fresh task-creation request can still create a second task.

Invitation IDs do not grant access: only the authenticated recipient can accept/decline; only owners can create/revoke. Pending invites expire after 7 days by default (1–30 days through API). No email is sent. Existing users are required; account-email verification remains future work. Expired/terminal IDs cannot be reactivated. Member removal revokes outstanding invitations for that account, and transfer revokes all pending workspace invitations.

Session records store a random identifier digest, not raw cookies. Logout and logout-all revoke server-side sessions. Existing Phase 1A stateless cookies are invalid after migration. Session history currently needs an operational retention policy; no user records are deleted automatically. The local IP limiter is bounded and testable, but is per process, resets on restart and is not a substitute for production ingress protection.

The browser clears removed/revoked content after a failed authorization refresh (two-second polling interval); network interruptions cannot revoke information already read. No promise of erasing screenshots or human knowledge is made. In-flight reads authorized before removal may complete; subsequent requests are denied. Client state is not a security boundary.
