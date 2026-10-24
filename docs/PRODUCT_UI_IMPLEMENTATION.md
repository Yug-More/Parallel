# Interface implementation — Phase 14

This phase implements the [design system](PRODUCT_DESIGN_SYSTEM.md) over the existing React/FastAPI contracts. The [baseline audit](PRODUCT_UI_AUDIT.md) remains historical evidence.

## What changed

- Persistent desktop workspace-section sidebar; compact, horizontally scrollable mobile section row. Native button focus scrolls sections into view. This deliberately preserves direct navigation rather than introducing a closed menu prerequisite. Workspace creation/switching, invitation inbox and query-parameter reload behavior remain intact.
- Account & security disclosure groups account identity, verification, logout and global session revocation. Members retains ownership/invitations; owner retention/closure follows membership rather than appearing above navigation. Role and actual member count are visible.
- Shared neutral light/dark tokens, system typography, 6/8px radii, solid surfaces, consistent forms and feedback, contrast-conscious input boundaries, content skip link and reduced-motion rules. Authentication/recovery uses the same vocabulary; short mobile pages scroll naturally.
- Multiline conversation composer: Enter sends, Shift+Enter adds a newline, IME composition does not submit. Failed requests preserve the draft. Explicit Member/AI interpretation labels supplement color. Messages support paragraphs, heading-like emphasis, unordered lists, bold, inline code, fenced code and HTTP(S) links. This is a bounded Markdown subset, not full CommonMark. React escapes text; raw HTML, images and embedded content are not interpreted. Code scrolls within its own container.
- Agent capability explanation appears beside the chosen contract; local computation, exact owner review and external-execution boundaries remain explicit. Empty run details no longer add another bordered card. Source dialogs and exact approval payload/hash/expiry/receipt flows are preserved.
- Intelligence explains retained workspace sources and actual archive/revocation/retention controls. No cosmetic personal memory editor or arbitrary agent configuration was added.
- Connections displays committed sync and cached private grant expiry from existing API metadata, with bounded-snapshot delta counts and the separate 30-second model-transmission requirement. A timestamp is historical metadata, not a frontend authorization decision.

## Browser evidence

Real synthetic captures: [phase14 screenshots](screenshots/phase14); compare [phase13 baselines](screenshots/phase13). `inspection.json` records all eleven sections at 1440, 1280, 1024, 768, 390 and 360px: **66 section/viewport inspections**, no document overflow or JavaScript page errors. Each width exercised persisted multiline submission, escaped script text, account verification visibility, modal initial cancellation focus/Escape, and theme switching. Desktop/mobile light and dark images were visually inspected. These are automated engineering inspections, not independent human usability or screen-reader certification.

The first review identified that a wrapping textarea label was unstable after multiline filling; an explicit matching accessible name fixes repeated keyboard access. Input control borders were strengthened after contrast review. Decorative Framer Motion imports were removed from the active three consumers; no package range was added or removed in this phase.

## Compatibility and verification

No backend API, schema, ranking, authorization, session, approval, retention or worker contract changes. Existing browser assertions remain; only account disclosure opening was added where controls moved. Native dialogs retain focus containment and safe cancellation. All six-width account/security actions remain accessible; no critical action is hidden with a mobile CSS rule.

Verification commands and completed results are recorded below before delivery. CI remains required before merge. Live trained-model quality, real private GitHub authorization, actual email delivery, independent usability and production operations remain unverified; see [intelligence hardening](INTELLIGENCE_HARDENING.md).

Completed local verification: `python -m pytest -q backend/tests` **214 passed** (four existing warnings); Ruff lint/format **passed** (99 files); frontend lint/build **passed**; current-source secret guard **passed**. The first complete browser pass was **11/11**; a final pass follows the last label/border/empty-state adjustments. Representative calculated contrast ratios: light muted/canvas 5.99:1, light accent/white 6.57:1, dark muted/surface 8.29:1, dark accent/surface 9.61:1; input border/surface 3.21:1 light and 4.47:1 dark. These token calculations do not certify every rendered combination or assistive-technology interaction.

Build comparison on the same local toolchain: baseline JS 397.55kB / 120.51kB gzip; refined JS 291.20kB / 84.78kB gzip after removing active motion imports. CSS grew from 16.02kB / 3.83kB gzip to approximately 21kB / 4.7kB gzip. This is a bundle-size measurement, not a runtime latency or scale benchmark. Dashboard and selected panel polling remain unchanged and are an explicit performance limitation for later transport work.

Final settled browser run: `PARALLEL_TEST_PYTHON=/tmp/parallel-phase1a-venv/bin/python npm test` — **11 passed in 2.7 minutes**. The refreshed six-width inspection also completed successfully after the final styling changes; all 66 entries have document width equal to viewport and zero page errors. Documentation verification passed all 19 diagrams and local links. `npm audit --audit-level=high` reported zero vulnerabilities.
