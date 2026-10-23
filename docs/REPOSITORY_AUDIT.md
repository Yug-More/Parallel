# Repository audit and remediation

## Original verified baseline

Audit baseline: 4700bf0ff764a0e18e47bebf0bf2b60579165f69, main, clean working tree, origin https://github.com/Yug-More/Parallel-AI.git. Local history had 50 commits: severin-spagnola 20, Sean Aminov 19, Yug-More 9, Nayab 2. Historical contributions remain intact.

The original active application used React 19/Vite, a monolithic FastAPI backend, SQLAlchemy, SQLite/PostgreSQL configuration and four models: User, UserCredential, Message, Activity. README room/task/memory/SSE claims did not match active APIs. Authentication and SQLite persistence worked in isolated checks. Build passed, lint failed with 11 errors. Backend import required missing packages and two provider credentials. No tests, migrations or CI were tracked.

Confirmed or source-identified defects included tracked Plivo credentials; unsigned voice/SMS entry points; dev-secret JWT fallback; global activity/context/summary queries; display-name integration identity collisions; false email-success claims; destructive seed; inconsistent dependencies and configuration loading; oldest-message context and unbounded retrieval. The audit made no repository changes or external provider calls.

## Phase 1A remediation

- Replaced credential-bearing diagnostics; owner-side rotation remains required.
- Disabled legacy external/global APIs and voice WebSocket; retained non-executable historical references.
- Removed known signing defaults; validated production settings and password byte bounds.
- Added workspace/membership entities, owner-only membership creation and scoped APIs/context.
- Added Alembic with private legacy backfill and orphan rejection; replaced destructive seeding.
- Reconciled runtime dependencies, lazy optional AI and environment loading.
- Connected the dashboard to workspace APIs with session restoration and stale-read cancellation.
- Corrected frontend lint defects without disabling rules.
- Added backend regression tests, browser workflow, CI and current-source secret guard.

## Verification scope

Backend tests use real isolated SQLite storage; migration tests adopt unversioned legacy records and verify preservation and private ownership. Provider tests use mocks solely for error and authorization behavior. Browser tests use real localhost HTTP with separate account contexts. CI includes Python 3.12/3.13, PostgreSQL 16 and Chromium checks. Exact results and remote CI status are recorded in the implementation PR; do not infer a passing run from workflow existence.

No model calls, telephony, emails, external document edits, production deployment, secret rotation or history rewriting are part of this implementation. Phase 1A does not restore tasks, semantic memory or full agent orchestration.
