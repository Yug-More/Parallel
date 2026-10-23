# Security

## Historical credential exposure: owner action required

The original backend/check_plivo.py contained Plivo authentication material. It has been removed from current source and the diagnostic is disabled. The credential remains in historical commits. **The owner must rotate/revoke the exposed credential and review provider access logs.** No credential was tested, rotated, revoked or reproduced in reports. No history rewriting was performed. Source cleanup is not credential revocation.

## Trust boundaries

The browser supplies untrusted input. Authentication establishes a user; membership establishes access to a workspace. Every message/activity/member/context operation checks membership before access. Owner-only membership addition grants historical workspace access; use a new workspace when history should remain private. Display names and profile roles grant no authority.

PyJWT replaces the advisory-affected legacy JWT dependency. JWTs require subject, expiry and the configured HS256 signature. Cookies are HttpOnly and SameSite=Lax, Secure in production; unsafe browser requests reject foreign origins/cross-site fetch metadata. Production settings require an explicit signing key and HTTPS origins. Never log passwords, JWTs, provider keys, transcript bodies or raw provider exceptions. Validation responses omit input values.

SQLite foreign keys are enabled. Migrations preserve historical ownership in individual private workspaces and refuse orphaned records. Backups and restore verification precede existing-data migration. Unsupported downgrade cannot remove workspace boundaries.

## Providers and external actions

Only optional OpenAI text replies are available. Retrieval is workspace-scoped and bounded; provider clients are constructed lazily, close after use, have a deadline, and do not retry automatically. Messages persist independently of provider success. No live-provider verification is claimed.

Voice, SMS, research, Composio, telephony configuration and summary/email/document execution are unavailable, including direct HTTP and WebSocket requests. Archived code is non-executable reference material and must not be reactivated as-is. This deliberately removes unauthenticated callbacks, editable-name integration identities, provider-account fallback, and misleading completion reporting from the active service.

Before re-enabling integrations require signed/replay-resistant webhooks, authenticated caller identity, immutable connection ownership, capability checks, least privilege, explicit approval for consequential writes, durable execution states, idempotency and independently validated provider outcomes. The model must never decide authorization.

## Guardrails and tests

`scripts/check_secrets.py` scans current tracked/unignored source for supported provider credentials, literal auth tuples and private keys, printing locations only. It runs in CI and has a detection regression test. This limited pattern guard is not a full entropy/history scan or proof of no secrets; enable GitHub secret scanning/push protection where available through an owner-reviewed settings change.

Tests cover anonymous access, cross-workspace reads/writes/context, membership permissions, signatures/expiry, password byte limits, origin enforcement, migration preservation, disabled integrations and sanitized provider failures. Tests prohibit paid network calls.

## Remaining release risks

No production deployment is authorized or validated. Before release add rate limiting, operational monitoring, backup/restore drills, session revocation, email verification, password recovery, membership removal/ownership transfer, dependency vulnerability review, and abuse/cost quotas. Frontend advisory checks run in CI; the initial lockfile advisories were resolved through compatible updates. Cookie deletion does not revoke a copied JWT before expiry. Owner-added membership has no invitation acceptance flow yet. AI-generated text remains untrusted and may be inaccurate. Model output is rendered as text; do not introduce raw HTML rendering.

Development's ephemeral secret invalidates sessions on process restart; set an explicit generated local secret if continuity is needed. Full prompt-injection mitigation and durable agent execution remain later work. No paid provider actions or production resources were used for this phase.
