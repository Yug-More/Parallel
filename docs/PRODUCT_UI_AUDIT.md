# Product and interface audit — Phase 13

24 October 2026 · baseline `d54b91973d7fd97bda96ef090a6b88b195e86e4b`. This record precedes the redesign. Findings are implementation observations, not independent usability research.

## Method and architecture

Reviewed App/Dashboard, all active panels, shared CSS, API client, auth/recovery, source resolution, connections, agents/actions and retention APIs, persistence models, architecture and verification workflow. React 19/Vite is state-routed with workspace/section query parameters; plain CSS and native controls are the active UI system. Framer Motion is used for entry transitions, react-icons is installed, and Three.js remains a dependency to investigate before removal. No component library or router is required for this refinement.

FastAPI routers call workspace-authorized domain modules and SQLAlchemy. Alembic head is `0018_sync_checkpoints`. Database-backed sessions and immutable member IDs gate context; mutation locks serialize permission changes. Worker leases, context fingerprints/knowledge epochs and exact owner approvals remain server responsibilities. Frontend design changes must not substitute for any of these boundaries. Optional model responses and trained adapters are separately enabled; local agent contracts do not execute external work.

Browser audit used the existing documented isolated E2E environment: Vite on loopback 15175 and FastAPI on 18001 with a temporary migrated database and synthetic `.test` accounts. Registered an account through the UI, submitted a persisted message, opened every section, requested generic recovery instructions, opened/cancelled session revocation, inspected invitations and captured desktop/mobile states. Existing connected/intelligence/pilot/hardening journeys additionally exercise populated evidence, approvals, member removal, provider fixtures, retention and recovery. Those adapters do not prove live model, private GitHub or email behavior.

## Screen inventory

Each entry lists the real scope, components/API dependencies, and refinement needs. Baseline captures are in [screenshots/phase13](screenshots/phase13), named by section and width (1440/390). `inspection.json` records viewport/document widths and observed headings for all eleven workspace sections.

### Landing and authentication

Landing explains collaboration/provenance/local coordination and opens sign-in. Login/Signup use cookie-backed `/auth/login`, `/auth/register`, `/auth/me`; App restores live sessions. Actual account creation produces Personal workspace. Auth.css uses a 420px glass card, large heavy headings, inconsistent native footer buttons and entry motion. Centered 100vh containers risk tall recovery content being difficult to reach on short screens. Make responsive solid surfaces, visible aligned labels, unified button/focus/error styles and scrollable page height. Baseline auth capture waits for existing entry motion to settle.

AccountRecovery calls `/auth/recovery/{request,complete}` and `/auth/verification/{request,complete}`. Request responses are generic; private development outbox is not email delivery. The verification disclosure currently spans the shell immediately below the header with little internal styling. Group it with account controls and give forms the same label, pending, help and feedback hierarchy as authentication. There is no profile editor, notification-preference center or account-deletion API: do not invent them.

### Shell and workspace switching

Dashboard loads `/workspaces`, `/invitations`, selected workspace/messages/members/activity and owner invitation history, polling every two seconds. Switch/create clears cached content/drafts; lost access clears inaccessible state. Workspace creation and global logout actions are visually prominent on every screen. Eleven horizontal section buttons wrap into multiple rows; on mobile the shell consumes roughly half the first viewport before content. Move section navigation into a persistent desktop sidebar and mobile disclosure; preserve deep-link query parameters, selection semantics and visible workspace identity. Add a content skip link. Keep account security available at every width.

### Conversation

ChatBubble renders persisted `/messages` and optional explicit `/agent-replies`. Current roles are inferred mainly through bubble color; user text is unnecessarily bold, author/timestamp is small, long text has no Markdown/code structure, input is single-line, empty log reserves 250px. Older-message pagination and provider errors are real. Improve explicit role labeling, message reading width, multiline composer with documented keyboard behavior, safe formatting, pending feedback and draft-preserving retry. Do not claim streaming, thread navigation or configurable conversational agents: those do not exist. Evidence is inspected in Answers/Intelligence/Agents, not invented for uncited conversation text.

### Overview

OverviewPanel uses `/overview`: task/decision/approval/connected knowledge counts, worker health, next steps, changes and delegated runs. Counts are real; heartbeat means liveness rather than successful work. Repeated surfaces and equal-weight boxes obscure useful next actions. Reduce nesting and use compact count rows; keep freshness/time and worker caveats visible. Empty workspaces are supported and should guide users toward actual task/document creation.

### Tasks

TaskBoard uses `/tasks`, task detail, prerequisites and current member assignment. Supports filtering, paging, current-version edits, archival, prerequisites and conflict reload. Split list/detail stacks below 1100px. Styling is largely usable but form/radius/padding hierarchy differs from other panels. Keep selected task obvious, names and long values wrapping, sticky-free mobile actions and unsaved form state separate from polling. Preserve archive confirmation and unavailable prerequisite/completion failures.

### Decisions and history

DecisionsPanel uses `/decisions` with SourcePicker/SourceViewer. Human choices retain reasons, sources, revisions and supersession. Forms are long and nested; historical versus current source identity needs clear labels and consistent spacing. Keep mandatory correction reason/version and source snapshots, improve detail hierarchy and readable evidence. There is no automatic promotion of a model answer into an accepted decision.

### Intelligence / retained memory

IntelligencePanel exposes `/continuity`, `/continuity/visit` and `/search`. It offers changes since visit/time, source-linked task/decision/activity changes and deterministic lexical search with optional similarity modes. Source types, archived native scope and source dialogs are real. Repeated cards make empty briefings long; search and continuity need a stronger subnavigation hierarchy and concise retained-context explanation. There is no separate personal-memory editor or universal semantic understanding. Retained records belong to the selected workspace; removal/archive/revocation filters are server enforced.

### Documents and indexes

DocumentsPanel uses `/documents`, revisions/archive, `/retrieval-index`. Bounded text/Markdown/PDF uploads create leased extraction jobs and stable passages. Optional indexes expose provider/model/epoch/state and explicit external consent. The upload form and optional index control are large surfaces, while errors/passages compete for emphasis. Clarify supported limits, record states and source provenance; keep archive confirmation and index opt-in, label character similarity distinctly from trained modes. No OCR or remote URL importer exists.

### GitHub connections

ConnectionsPanel/GitHubAuthorization use `/connections` and `/github` device/installation/repository endpoints. Public imports and selected private App access are read-only and owner controlled. Current panel lists sync attempts but omits useful returned `access_verified_until`, checkpoint and last verified information. Present permission expiry separately from sync success; never imply a cached private repository has a current live grant. Keep disabled/operator configuration honest, recoverable revalidation/sync failures visible and revocation confirmation explicit. No repository writes exist.

### Ask workspace and evidence

AnswersPanel uses `/answers`; SourceViewer resolves `/sources/{kind}/{id}` under current authority. Users select local excerpts or configured model interpretation and lexical/optional trained retrieval. Saved claims/citations preserve evidence scope, abstention and unavailable evidence. Forms and result cards need clearer input-versus-history hierarchy and code/prose readability. Source dialogs already use native modal focus/return behavior; preserve that. Citations validate identity, not correctness. Do not equate retrieval scores with confidence.

### Agents, configuration and approvals

AgentsPanel/NativeActions use `/agents/contracts`, runs/context/events/reasoning/publication approvals and `/actions`. Real contracts include status, dependency, handoff, research and exact native task plans. Configuration is capability, objective, related task and explicit evidence; there is no arbitrary persona/tool editor. Current empty history/detail/approval regions produce many similar cards and a long mobile page. Emphasize the selected contract, permitted effect, run state and selected evidence; visually separate computation from approved native changes. Publication and task-plan owner reviews must retain payload/hash/context/expiry and receipt, approve/reject and failure states. Queue insertion is never completion.

### Members, invitations, retention and security

WorkspaceMembers and InvitationInbox use `/members`, ownership/leave and account-bound `/invitations` transitions. Owner/member is the entire privilege model. A personal-named workspace is still a workspace that an owner can share. Show actual member count and role, not an inferred privacy guarantee. Preserve terminal invitation history, remove/transfer/leave confirmation and safe unassignment.

RetentionPanel uses signed `/retention/preview`, exact typed execution and audit receipts. Owner-only closure/erasure controls currently appear above section navigation, disconnected from Members. Place them after membership controls under a clear retention heading; distinguish native human history from erased derived content and closure. Never make previews destructive. Log out all sessions uses a native ConfirmDialog and real revocation. No individual session list exists; explain global revocation accurately.

### Activity, notifications, empty and error states

Activity is persisted `/activity`, attributed and timestamped; invitations are the implemented inbox. No general push notification or fake activity feed exists. Most async panels have status/alert text; presentation varies and some empty details reserve large blank surfaces. Standardize feedback contrast, spacing and meaningful recovery wording. Loading must represent requests; no fake skeleton duration or simulated completion. Preserve unauthorized 404/expired-session transitions and UI cache clearing.

## Priorities and acceptance plan

1. High: reduce mobile navigation overhead; unify auth/recovery focus/forms; make conversation multiline and safely readable; preserve every security action and accessible name.
2. High: clarify workspace ownership/membership, local agent effects, exact approval review and GitHub permission freshness using existing metadata.
3. Medium: centralize light/dark neutral tokens, spacing, type, radius and status primitives; reduce repetitive empty/nested surfaces; remove unnecessary entry animation and emoji theme labels.
4. Medium: test six viewport widths, long content, keyboard and modal focus/return, both themes, provider and permission failures; expand regression coverage rather than replacing existing journeys.
5. Follow-through: replace historical README milestone accumulation with current behavior/screenshots and retain historical execution documents; final complete verification and precise handoff.

[Design specification](PRODUCT_DESIGN_SYSTEM.md) defines the implementation contract. Phase 14 implements it; Phase 15 adds targeted functional/accessibility/responsive evidence; Phase 16 updates presentation; Phase 17 repeats the quality gate. No critical security issue has been established by this interface audit; this is not a new formal security certification.

## Baseline verification

Fresh local checks on this baseline: backend `python -m pytest -q`: **214 passed**, four existing warnings, 86.54s; `ruff check backend scripts`: passed; `ruff format --check backend scripts`: 99 files unchanged; frontend `npm run lint`: passed; `npm run build`: passed (397.55kB JS / 120.51kB gzip, 16.02kB CSS / 3.83kB gzip). Browser and remote CI results are recorded after completion below. These synthetic fixture workloads do not establish production performance or external integration quality.

Unchanged Chromium suite: `PARALLEL_TEST_PYTHON=/tmp/parallel-phase1a-venv/bin/python npm test` — **11 passed in 2.9 minutes**. The additional audit visited all eleven sections at both widths; measured document width equaled viewport width in all 22 cases. This does not establish six-width coverage, contrast conformance or all populated failure states; those remain explicit next-phase gates.
