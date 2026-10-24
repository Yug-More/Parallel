# Security

Runtime configuration, hardening and external limits: [trained intelligence and operational hardening](INTELLIGENCE_HARDENING.md). Earlier milestone sections below describe their original scope.

## Historical credential exposure: owner action required

The original backend/check_plivo.py contained Plivo authentication material. It has been removed from current source and the diagnostic is disabled. The credential remains in historical commits. **The owner must rotate/revoke the exposed credential and review provider access logs.** No credential was tested, rotated, revoked or reproduced in reports. No history rewriting was performed. Source cleanup is not credential revocation.

## Trust boundaries

The browser supplies untrusted input. Authentication establishes a user; membership establishes access to a workspace. Every message/activity/member/context operation checks membership before access. Owner-only membership addition grants historical workspace access; use a new workspace when history should remain private. Display names and profile roles grant no authority.

PyJWT replaces the advisory-affected legacy JWT dependency. JWTs require subject, expiry, a session identifier and the configured HS256 signature, plus a matching unrevoked database session. Cookies are HttpOnly and SameSite=Lax, Secure in production; unsafe browser requests reject foreign origins/cross-site fetch metadata. Production settings require an explicit signing key and HTTPS origins. Never log passwords, JWTs, provider keys, transcript bodies or raw provider exceptions. Validation responses omit input values.

SQLite foreign keys are enabled. Migrations preserve historical ownership in individual private workspaces and refuse orphaned records. Backups and restore verification precede existing-data migration. Unsupported downgrade cannot remove workspace boundaries.

## Providers and external actions

Optional OpenAI text replies and separately enabled grounded model answers are available; local source excerpts need no provider. Retrieval is workspace-scoped and bounded; provider clients are constructed lazily, close after use, have a deadline, and do not retry automatically. Messages persist independently of provider success. No live-provider verification is claimed.

Voice, SMS, Composio, telephony configuration, arbitrary browsing and external summary/email/document writes are unavailable, including direct HTTP and WebSocket requests. Archived code is non-executable reference material and must not be reactivated as-is. This deliberately removes unauthenticated callbacks, editable-name integration identities, provider-account fallback, and misleading completion reporting from the active service.

Before re-enabling integrations require signed/replay-resistant webhooks, authenticated caller identity, immutable connection ownership, capability checks, least privilege, explicit approval for consequential writes, durable execution states, idempotency and independently validated provider outcomes. The model must never decide authorization.

## Guardrails and tests

`scripts/check_secrets.py` scans current tracked/unignored source for supported provider credentials, literal auth tuples and private keys, printing locations only. It runs in CI and has a detection regression test. This limited pattern guard is not a full entropy/history scan or proof of no secrets; enable GitHub secret scanning/push protection where available through an owner-reviewed settings change.

Tests cover anonymous access, cross-workspace reads/writes/context, membership permissions, signatures/expiry, password byte limits, origin enforcement, migration preservation, disabled integrations and sanitized provider failures. Tests prohibit paid network calls.

## Remaining release risks

No production deployment is authorized or validated. Before release establish installed operational monitoring, production/key/offsite restoration drills, a reviewed production verification/recovery delivery adapter, trusted ingress/account abuse controls, continued dependency review and organization spend controls. Private development/test recovery/verification, signed retention and synthetic SQLite/PostgreSQL restoration are implemented; they do not meet those production gates. Frontend advisory checks run in CI; the initial lockfile advisories were resolved through compatible updates. Revoked sessions, including copied cookies, cannot authenticate. The frontend uses recipient-approved in-app invitations. The Phase 1A direct member-add API remains owner-only for compatibility; owners are trusted to grant access. AI-generated text remains untrusted and may be inaccurate. Model output remains untrusted. Conversation uses a bounded escaped text-only Markdown subset; source/answer records remain safely rendered and raw HTML is never interpreted.

Development's ephemeral secret invalidates sessions on process restart; set an explicit generated local secret if continuity is needed. Grounded answers use an explicit untrusted-evidence boundary and citation validation; this does not prove prompt-injection immunity. External writes remain disabled; local deterministic execution is described below. No paid provider actions or production resources were used for this phase.


## Phase 1B guarantees and remaining limits

Every workspace write is serialized before membership/ownership validation. Read endpoints, task details, dependency references and AI context are workspace-scoped. Member removal revokes future requests and unassigns tasks atomically; ownership transfer leaves exactly one owner and revokes pending invitations. All new activity is persisted in the same transaction as its operation. Stale task edits and repeated invitation transitions fail without duplicate activity. Creation requests are not automatically retried; repeating a fresh task-creation request can still create a second task.

Invitation IDs do not grant access: only the authenticated recipient can accept/decline; only owners can create/revoke. Pending invites expire after 7 days by default (1–30 days through API). No email is sent. Existing users are required; at this historical Phase 1B checkpoint account verification was future work; current private development/test verification exists, while real delivery remains unimplemented. Expired/terminal IDs cannot be reactivated. Member removal revokes outstanding invitations for that account, and transfer revokes all pending workspace invitations.

Session records store a random identifier digest, not raw cookies. Logout and logout-all revoke server-side sessions. Existing Phase 1A stateless cookies are invalid after migration. Expired operational session/recovery records now have bounded cleanup; human project records require explicit applicable owner retention and an operational backup policy. The original process-local limiter remains a unit-tested utility; HTTP authentication now uses atomic shared database fixed-minute counters keyed by HMAC. It is not a substitute for trusted production ingress protection.

The browser clears removed/revoked content after a failed authorization refresh (two-second polling interval); network interruptions cannot revoke information already read. No promise of erasing screenshots or human knowledge is made. In-flight reads authorized before removal may complete; subsequent requests are denied. Client state is not a security boundary.

## Project intelligence and worker boundaries

Decision sources are resolved by immutable kind/ID in the decision's workspace before revision creation. Snapshots preserve cited previews; current source navigation checks membership again. Default retrieval excludes terminal decisions and archived tasks. Including historical sources does not bypass membership. Text remains untrusted and is rendered without raw HTML. Retrieved assertions are not executable instructions or proof of truth.

Every new decision/run/approval mutation acquires the workspace lock before authorization. Task/decision versions protect competing edits; composite FKs prevent cross-workspace successor, parent, retry and task links. Polymorphic source targets are service-validated rather than protected by target-table FKs. Direct database modifications are outside API guarantees.

Workers execute six code-defined deterministic contracts. Objectives and input text cannot create capabilities. No shell, model, external tools or outbound operations are part of those contracts. The worker checks initiating membership at claim and finalization, verifies task dependencies and context fingerprints, and discards late results after cancellation or lease recovery. Revoking a session denies subsequent API access; already queued authorized work survives logout unless cancelled or its membership becomes invalid.

A publication request stores a fixed action, exact payload and SHA-256. Only the current owner may approve/reject the pending unexpired request. The worker independently checks payload equality/hash, initiator membership, approver's current ownership, expiry and context before atomically saving one assistant message and receipt. An approval is not an execution success. Replay, altered payloads, competing responses, post-approval ownership changes, cancellation and expiry are tested. External writes remain unavailable.

Run contexts and evidence snapshots contain workspace data and require the same retention/backup protections as messages. They are not encrypted at rest by this application, signed, or tamper-proof against database administrators. Bound outstanding jobs, input sizes, graph scope and execution deadlines limit local abuse; broader public deployment needs installed supervision, ingress controls and provider spend limits; shared database quotas are implemented. No new production resources or real credentials were used.

## Connected sources, answers and native task plans

Document upload requires membership, bounded JSON/decoded bytes, safe metadata-only filenames and UTF-8 extraction. No parser executes Markdown/HTML; PDF parsing has separate process resource/deadline bounds. Stable revision passages remain private to their workspace. Archiving blocks every passage including history, cancels extraction and discards late results. Public repository reads remain unauthenticated fixed-host GETs with verified TLS. Private mode requires the explicit GitHub App device flow, selected read-only installation access and encrypted expiring user grants; there is no token/CLI fallback. Repository data remains GET-only, with no redirects/client URLs and bounded responses/requests. Revocation cancels syncs and blocks imported records; worker finalization rechecks current ownership and connection version.

Saved answers re-resolve all evidence/fingerprints on every read. Generated reports/messages bind a workspace knowledge epoch; document/import change or revocation hides their old text/context from reads, search and conversation model context. This is conservative invalidation, not deletion/encryption. Decision-source snapshots redact unavailable generated-message evidence; manual human quotations in native fields cannot be automatically erased. Already delivered information and administrative database/backups are outside retrieval revocation.

Optional grounded model mode requires a separate server opt-in plus key and explicit UI choice. Evidence is bounded and treated as data, tools are absent, citation IDs must come from the allowlist, and post-call membership/evidence are rechecked. Structured output/citation validity does not prove factual entailment. Fake-adapter tests do not prove live model quality, provider compatibility or prompt-injection immunity.

Native proposals permit only `create_task_plan` (one to five To do/unassigned tasks with only the exact displayed prerequisites). They do not accept client-authored action bodies. Current owner approval binds the exact server payload/hash; worker execution recomputes the plan and verifies current context, initiating membership, owner, expiry and action. All tasks/edges and the unique proposal receipt commit atomically. No status is automatically Done, no external write occurs and no arbitrary code/tool command is dispatched. Shared quotas, retention, encryption and production supervision remain [operational requirements](OPERATIONS.md).

## Phase 7–9 targeted review

Review covered authentication/session regression, PDF parser process isolation, encrypted private grants, selected/read-only App permissions, fixed endpoint construction, refresh rotation, permission expiry, workspace source/index/answer/report invalidation, owner transfer, cancellation, exact action replay and concurrent workers/counters. Regressions cover resource/time failures, private access loss during network reads, stale index results, tampered credentials and model output attempting an extra action field. A rotated refresh grant is committed under current authority before later sync reads can fail. Source preview dialogs now explicitly restore keyboard focus after closing.

Residual boundaries: the PDF subprocess is not a complete OS filesystem/network sandbox; macOS has no enforced address-space cap. Remote permission revocation is discovered on sync or within a ten-minute local authorization window, not via webhooks. Stored user tokens can access the intersection of App/user grants, while application requests remain limited to the mapped repository; only read permissions are accepted. Secrets require privately managed encryption/signing keys and encrypted backups/volumes. Model schemas do not establish factual entailment or complete prompt-injection resistance. A fake-transport test is not live authorization, a penetration test or production certification. The historical Plivo credential still needs owner-side rotation/revocation.

## Product refinement regression

Phase 15 retained the backend security suite and added real browser checks for escaped script/image/unsafe-link text, 503 draft preservation/explicit retry, workspace cache clearing, current citation focus, exact proposal rejection/denied replay and dialog containment. UI selection never replaces membership/freshness checks. [QA report](PRODUCT_REGRESSION_QA.md) states results and [external validation](EXTERNAL_VALIDATION_CHECKLIST.md) states limits. No penetration test or blanket accessibility/production certification is implied.
