# Product design system

Phase 13 specification · 24 October 2026. This is the implementation target for Phase 14, not a claim that the baseline already meets it.

## Principles

Make the workspace, actor, source and action legible. Prefer compact lists, clear headings and readable evidence over decorative cards. Preserve distinctions between human records, source quotations, model interpretation, local computation, queued work and committed receipts. Show unavailable capabilities honestly. Security controls must remain usable at narrow widths.

## Layout and navigation

Use a 224px desktop sidebar for workspace selection, creation, invitations and persistent section navigation. Keep the content region fluid with a 1240px maximum reading/work width; use smaller text measures inside conversations. At 768px and below, use a single horizontally scrollable section row with visible selection and native keyboard access. This preserves direct section access and avoids a hidden navigation prerequisite; the browser scrolls focused controls into view. Keep workspace switching available without opening a menu. Do not create a second routing framework: existing workspace/section query parameters remain reloadable.

The shell header identifies Parallel and the signed-in account; account verification and global session revocation belong together under an Account disclosure. Workspace membership and retention remain in Members, with a clear security/retention heading. Never move owner controls into a location members can use to bypass server authorization.

## Typography and spacing

System font stack: Inter when locally available, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif. No third-party font download. Body 14px/1.6, metadata 12px/1.5, form labels 13px/1.5, section headings 18px/1.35, page identity 24px/1.25. Use weights 400, 500 and 600. Code uses ui-monospace, SFMono-Regular, Consolas, monospace at 13px. Long prose should not span the full viewport.

Spacing scale: 4, 8, 12, 16, 20, 24, 32, 48px. Use 24px section gaps and 16px form gaps; 32px desktop page gutters, 16px mobile. Avoid repeated large nested padding.

## Semantic tokens

Light: canvas #f7f8fa, surface #ffffff, secondary surface #f0f3f5, text #19242e, muted #52616f, border #d3dbe2, accent #126678, accent-soft #e6f1f3. Dark: canvas #11171d, surface #182129, secondary surface #202d37, text #edf2f5, muted #acbbc7, border #3c4c59, accent #85d3df, accent-soft #213d45. Primary filled controls use #126678 with white text in both themes. Error light #a82d35/dark #ffabb1; success light #216b43/dark #9ddcb7. Selection must use both shape/border and text, not color alone.

Surface hierarchy is canvas → panel → selected item; no translucent glass or gradients. Border 1px solid semantic border; input boundaries use #81929e in light mode and #71899b in dark mode for stronger non-text contrast. Controls 6px radius, panels/dialogs 8px, small tags 4px. Shadows only where needed for an actual overlay; avoid ordinary card shadows.

## Controls and content

Use native button/input/textarea/select/details/dialog semantics. Reuse existing form, section-heading, feedback, source dialog and confirmation patterns rather than introducing a competing library. Primary actions use the primary class; destructive actions use danger text plus explicit wording and confirmation. Disabled controls remain legible and indicate pending state through text. All non-submit form buttons specify type=button.

Forms have visible labels, concise help and bounded input. Recovery forms use the same controls as the workspace. Async failures use role=alert; success/waiting uses role=status without making whole message histories repeatedly announce. Empty states say what is absent and name an available next action. Loading text reflects real requests, never fabricated streaming.

Conversation: multiline composer, Enter sends, Shift+Enter inserts a line break; do not submit during IME composition. Human and generated messages have explicit role labels, stable authorship/time, readable paragraphs, safely escaped Markdown/code and no raw HTML. Code may scroll within its own container. Evidence remains interactive SourceLink → current-authorized SourceViewer; rendering never creates citations.

Agent contracts are code-defined capabilities, not custom autonomous assistants. Keep contract explanation, selected capability, evidence, execution history and owner approvals visually distinct. Approval preview includes exact effect/hash/context, expiry, and resulting receipt; never reduce it to an unexplained accept button.

Memory is workspace records and retrieval, not a separate personal vector-memory editor. Describe Documents, Decisions and Intelligence as the retained context sources; link to actual retention controls. GitHub status must distinguish cached/synced from recently permission-verified access and show returned expiry/checkpoint metadata.

## Accessibility and responsive behavior

Targets: WCAG 2.2 AA where applicable, with limitations recorded from actual tests. Focus ring 3px with 3px offset; never remove it. Native modal dialogs contain keyboard focus, Escape cancels when safe, initial focus lands on cancellation/close, and closing returns focus to the opener. Use semantic landmarks, one page h1 and logical section headings. Include a skip link to workspace content. Disclosure and selection controls expose expanded/pressed states. Icons, when useful, use one existing icon family; text labels are preferred to ambiguous icons and emoji.

Controls target at least 36px height on desktop and 44px on narrow touch layouts. Inputs use 16px text on small screens. At 1100px task/evidence split views stack; at 768px shell navigation becomes a disclosure; at 480px forms and action rows stack as needed. Verify at 1440, 1280, 1024, 768, 390 and 360px, including long URLs/hashes and dialog content. Never hide session, retention or approval controls for mobile.

Avoid animation in ordinary content. Honor prefers-reduced-motion globally; remove decorative entry motion. Theme changes do not animate whole pages. Automated checks supplement keyboard/browser inspection and do not prove screen-reader usability or independent human usability.

## Implementation sequence

1. Centralize theme tokens and form/focus primitives; unify authentication/recovery.
2. Refine shell hierarchy and mobile section disclosure while preserving accessible button names and query parameters.
3. Improve multiline conversation, role labels and safe text/code formatting.
4. Refine agent, evidence, connection freshness and retention hierarchy with existing API metadata.
5. Verify all six viewport widths, both themes, dialogs and failures; add targeted regression journeys in Phase 15.
6. Capture final synthetic screenshots and align README/technical docs in Phase 16; repeat full verification in Phase 17.
