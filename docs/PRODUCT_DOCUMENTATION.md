# Product documentation — Phase 16

The README presents the current application rather than accumulated milestone descriptions: concise positioning, actual workspace hero, core workflows, authentic conversation/evidence/agent/approval/membership/context views, one maintainable architecture diagram, verified stack/setup/configuration/verification, privacy boundaries, evaluation limits and repository guidance. No new badge, generated mockup, license, award ranking, deployment or production-readiness claim was added.

## Screenshot provenance

`parallel-frontend/tests/showcase.spec.js` creates synthetic Casey/Riley `.test` accounts, a shared Release workspace, actual messages and assigned task, an authenticated source-linked accepted decision, uploaded Markdown, saved local evidence/citation inspection, a completed delivery coordinator, exact owner task-plan review and executed receipt. It verifies three active tasks after execution and mobile conversation containment. No model call or private GitHub access is needed. The initial run found an ambiguous selector matching Riley in membership and invitation history; scoping it to the member list fixes the test without weakening the workflow. Visual review also caught a briefing capture before data finished loading; the capture now waits for actual task-state content.

Explicit `PARALLEL_CAPTURE_PRODUCT=true` writes curated docs PNGs; ordinary CI keeps them in ignored results. Nine images are bounded to 1440×1000 or a 390px-wide full mobile page, about 1.2MiB combined, and are never shipped in the app bundle. [Manifest](screenshots/product/manifest.json) records dimensions, bytes and hashes. Actual workspace, evidence modal, approval, conversation, agent, memory and member views were inspected. They are synthetic engineering evidence, not independent usability findings or live model output. Historical before/after/milestone captures remain intact.

## Documentation consistency

Development now gives one active setup/migration/test/capture procedure and head `0018_sync_checkpoints`. Architecture/data/operations/security/integrations/vision/roadmap/audit distinguish current trained adapters, private App access, local recovery/verification, signed retention, synthetic PostgreSQL restoration and shared limits from historical scope. Real email, trained quality/private live authorization and production operational readiness remain unverified. External checks link to the explicit owner checklist. Evaluation retains original/frozen developer labels and raw results; default lexical ranking was not changed.

Owner-supplied hackathon recognition moved to [project history](PROJECT_HISTORY.md), with its lack of independent verification explicit. Historical contributors and Git records remain preserved. No project license was established or implied.

## Verification

The real populated capture journey passed (14.7s; 17.1s including service setup). Frontend lint passed. Final full suite, build, diagram/link and secret checks are appended below before delivery; CI is required before merge. No backend or database migration was needed for this documentation phase.

Frontend lint/build and backend Ruff lint/format passed (99 Python files). The current-source secret guard passes unchanged; its literal-assignment warning on the generated-secret documentation recipe was addressed by the existing separated-key/value generation form, not by changing detection rules. Documentation validation parsed/rendered **16 Mermaid diagrams** and resolved local links/images. Production build remains 291.88kB JS / 85.03kB gzip and 21.47kB CSS / 4.78kB gzip; documentation PNGs are outside that bundle.

Final full Chromium suite: **15 passed in 3.3 minutes**. The settled explicit capture rerun passed **1/1 in 17.4s** after adding the real briefing-content wait/full mobile capture; refreshed images and manifest were reviewed. No ordinary suite run modified historical tracked screenshots. No backend behavior changed; the prior 214-test/22-PostgreSQL results and green Phase 15 main CI remain applicable, and remote CI repeats them for this PR.
