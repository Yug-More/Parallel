# Functional and security regression — Phase 15

This report covers the refined product on synthetic accounts and isolated databases. It does not certify a public deployment, live private GitHub, trained-model quality or email delivery.

## Browser coverage

All eleven existing journeys remain in place. They exercise UI registration, personal/shared workspaces, invitations and terminal IDs, tasks/prerequisites/current versions/archive, persisted messages, decision revisions/supersession/citations, lexical continuity, uploaded PDF passages, optional fabricated index adapters, selected-source local agents, exact approved task plans/report publication, revocation invalidation, member removal/ownership transfer, session revocation, private local recovery and signed retention execution. No assertion was removed to make the redesign pass.

Three additional journeys in `parallel-frontend/tests/product.spec.js` cover:

- Eleven sections at six widths (1440, 1280, 1024, 768, 390, 360), **both light and dark themes: 132 section/theme/width cases**. Check accessible input labels and selection state, page overflow, unbroken long message content, Shift+Enter/Enter, account/security availability, initial dialog focus, Tab containment, Escape and focus return. Attach actual viewport measurements to the Playwright result. Contrast calculations read current CSS tokens rather than duplicated expected colors; normal text targets 4.5:1 and input boundaries 3:1.
- A synthetic 503 message failure followed by explicit retry. The draft remains intact, no success message is fabricated, retry persists one message across reload, HTML/image/script/unsafe-link text cannot become executable markup, Markdown/code is readable, source citations open current evidence with keyboard focus/return, and changing workspace clears conversation/draft state. Only this failure is transport-injected; the successful retry and citation retrieval use real HTTP/database persistence.
- A local planner's exact native proposal rejected through the mobile UI. No tasks or execution receipt appear; history persists across reload; a later approve replay returns HTTP 409. Existing connected journeys independently cover successful exact approval and resulting To do task receipts.

The first focused run exposed a modal Shift+Tab gap. Shared `dialogFocus.js` now contains Tab within visible controls for confirmation/source dialogs, while native showModal keeps the background inert. Confirmations explicitly return focus to a connected opener. The focused rerun passed **3/3** in 13.2s; the complete final suite result is recorded below. Conversation uses a named polite log limited to additions rather than announcing the entire workspace polling snapshot.

Hardening screenshots now go to isolated Playwright output instead of rewriting tracked historical Phase 12 captures. This preserves reproducibility and keeps ordinary tests from dirtying the repository; the prior assertions and retention workflow are unchanged.

## Security and reliability boundaries

Backend code, schema, ranking, credential handling and approvals remain unchanged. Current tests retain immutable-ID membership checks, cross-workspace denial, serialized mutations, current-version/task dependency conflicts, decision-source isolation, private grant renewal/expiry, fresh transmission consent, epoch/fingerprint invalidation, worker lease interruption/competition/cancellation, tamper/replay rejection, recovery one-use/session invalidation and retention race protection. Fixtures cannot grant model or external execution powers.

No original database was migrated or erased. PostgreSQL runs use a new no-mount container and guarded exclusive schemas/databases. Ordinary tests prohibit paid network calls. Real provider exceptions/credentials are not rendered or logged. The source secret guard is a limited supported-pattern scan, not proof of clean historical Git or complete penetration testing. Historical Plivo revocation remains an owner action.

## Performance inspection

The same-toolchain production build changed from baseline 397.55kB JS / 120.51kB gzip to approximately 291kB / 85kB gzip after active decorative motion imports were removed. CSS is approximately 21.5kB / 4.8kB gzip. No remote fonts, images or animation were added to the shell. These are actual bundle measurements, not time-to-interactive, throughput or production latency claims.

Source inspection confirms the owner shell still polls seven resources per two-second update, with additional selected-panel polls. No WebSocket, cache coordination, batching or background-tab suspension is claimed. Those are follow-ups requiring authorization-freshness-aware design; polling was preserved in this UI cycle rather than silently weakening membership/source refresh. Screenshots are documentation assets, not loaded into the application bundle.

## Accessibility limits

Automated label/contrast/layout/keyboard tests supplement actual synthetic browser inspections. No independent screen-reader/human usability study, OS high-contrast review or exhaustive rendered-state contrast audit occurred. Bounded Markdown is a documented subset. Long forms remain scrollable rather than hiding consequential controls; mobile section navigation uses a horizontal local scroll region. No blanket WCAG certification is claimed.

## External validation

[Owner checklist](EXTERNAL_VALIDATION_CHECKLIST.md) gives exact prerequisites and steps for optional ML dependency/model quality, live selected private GitHub, real delivery implementation, independent usability/accessibility and production disaster recovery. Production delivery is not an available SMTP switch: only the private development/test outbox exists. No paid services, deployment, external document/repository writes or real grants were used.

## Verification record

Commands use the documented temporary environment and isolated services. Completed results are appended after the final full run; PR CI must pass before merge.

- `python -m pytest -q backend/tests`: **214 passed**, four existing warnings, 92.01s.
- PostgreSQL `test_recovery.py test_embedding_providers.py test_retention.py` with `PARALLEL_TEST_POSTGRES=true`: **22 passed**, one existing warning, 18.16s.
- `ruff check backend scripts` and `ruff format --check backend scripts`: **passed**, 99 files formatted.
- `npm run lint` and `npm run build`: **passed**; final JS 291.88kB / 85.03kB gzip; CSS 21.47kB / 4.78kB gzip.
- `python scripts/check_secrets.py`: **passed**.
- `scripts/check_docs.cjs`: **19 Mermaid diagrams** parsed/rendered, local links resolved.
- Earlier isolated PostgreSQL smoke/populated upgrade/intelligence/connected scripts passed after migrating only the newly created container; the first smoke invocation correctly refused its unmigrated schema. Restoration compared 32 tables/24 rows, preserved receipts and source state. Fresh/repeated SQLite migration and metadata drift checks passed. Retrieval baseline/coverage/connected/pilot harnesses passed without ranking changes. Python and npm advisory audits reported no known vulnerabilities in the shipped dependency sets. These checks are repeated in remote CI; optional full ML runtime remains outside them.
- Final complete Chromium suite: `PARALLEL_TEST_PYTHON=/tmp/parallel-phase1a-venv/bin/python npm test` — **14 passed in 3.0 minutes**, including source-dialog focus return and all original workflows. No tracked screenshots were changed by the run.
