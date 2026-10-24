# Repository audit and remediation

Runtime configuration, hardening and external limits: [trained intelligence and operational hardening](INTELLIGENCE_HARDENING.md). Earlier milestone sections below describe their original scope.

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


## Phase 1B evolution

Baseline 426306235cfc127287e58d6efb989555a8d5491a was clean, including models.py; the apparent UI edit did not represent an uncommitted change. Phase 1B adds real invitations, member removal/ownership transfer, tasks and dependencies, revocable sessions, local auth throttling and a complete collaboration UI. Phase 1A tests remain regression coverage. New tests exercise races, populated-schema upgrades, task/version invariants and real browser removal/cache clearing. No paid providers, email delivery, production deployment or original user databases are used.


## Phases 2 + 3 evolution

The verified starting main was d3bd47543da51a147cdfb7f4f6e171fbdd1ecac2 with a clean working tree. New modules add revisioned decisions/provenance, authorized lexical retrieval, explicit visit markers, current-state/change briefings, deterministic status/dependency agents, a fixed handoff coordinator and exact owner-approved local publication. Migration 0004 adds seven tables without rewriting existing records. Backend tests include competing revisions/workers/approvals and interrupted execution. Retrieval fixtures deliberately expose ambiguity and vocabulary gaps. Real browser workflows produce the documentation screenshots. Optional model replies remain separate and live-unverified; no external execution or production claims are added.

## Phases 4–6 evolution

The verified baseline was clean local/remote main at `fe49e06f183cde8ae914771e481ad83315cc3ce6` (Phase 2/3 PR #3). This cycle adds durable text/Markdown ingestion, revocable public GitHub imports, grounded answer persistence/citation checks, explicit historical revision search, measured lexical coverage filtering, three additional local contracts, exact native task-plan proposals/receipts and an integrated overview/knowledge UI.

Revocation was reviewed across direct sources, retrieval, answers, run context/outcomes, publication previews, generated messages and decision-source snapshots. Conservative epochs hide older derived reports; human-authored native text remains authored data. Existing collaboration APIs and the legacy publication approval constraint are retained. Migration tests now populate historical schemas through their actual columns rather than using newer ORM columns against older schemas; they still compare every original field and record.

Verification includes isolated backend storage/worker races, real desktop/mobile workflows and screenshots, frozen author-curated retrieval labels, SQLite backup restoration and PostgreSQL CI checks. Public GitHub reads were live exercised without credentials; model behavior uses fake adapters and no paid calls. No real user database, production deployment, external write, credential rotation or historical commit was changed. Exact final counts/remote status belong to the delivery PR.

## Phases 7–9 evolution

Started from verified clean local/remote main `6c5008419a2c57cee7bceb00811f1d2442ca34ad` (PR #4). Baseline verification ran 153 backend tests and retained seven browser journeys. This cycle adds bounded PDF parsing/page citations, optional local index/provider lifecycle, measured phrase ranking, private GitHub App device grants/renewal/revocation, approved issue triage, shared counters, fairer worker queue rotation and a new-path restore drill. Additive migrations 0010–0013 preserve populated Phase 6 records.

Targeted review fixed rotated refresh-grant loss on a subsequent network outage, incorrect inferred dependencies between separate issues, and explicit source-dialog focus restoration. Tests cover malicious model action fields, private permission expiry/owner transfer, late sync results, resource-bounded parser failures and competing shared counters. All data used for verification is synthetic. No paid calls, live private authorization, external App registration, production deployment, original user-data reset or historical rewriting occurred. Delivery evidence and limitations are recorded in the implementation PR and [pilot readiness](PILOT_READINESS.md).

## Phases 13–16 product finalization

Started from the verified Phase 12 merge `d54b91973d7fd97bda96ef090a6b88b195e86e4b`. The [screen audit](PRODUCT_UI_AUDIT.md) and [design system](PRODUCT_DESIGN_SYSTEM.md) precede the [interface refinement](PRODUCT_UI_IMPLEMENTATION.md). [Regression QA](PRODUCT_REGRESSION_QA.md) retains historical workflows and adds six-width/both-theme, keyboard, failure/retry, safe formatting and rejection/replay evidence. The README now uses reproducible actual synthetic screenshots, current schema/setup and explicit optional/external boundaries. Earlier audit entries remain historical; they are not current capability inventories.

## Phase 17 final QA

Final inspection corrected pending/rejected payload terminology, added an exact native task preview to confirmation and retained closure-success receipt feedback while clearing inaccessible workspace state. A new 360px closure journey verifies preview/typed execution/replay/owner audit. Unused active-import-free visual dependencies, obsolete styles and stock assets were removed; original branding/history/audit fixtures remain. [Final handoff](FINAL_PRODUCT_HANDOFF.md) contains the actual final gate and explicit external/production limitations. No backend schema/ranking or external execution boundary changed.
