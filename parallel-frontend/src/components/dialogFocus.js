// Keep Tab/Shift+Tab within visible controls while a native modal is open.
// Native showModal also makes background content inert.
export function containDialogFocus(event) {
  if (event.key !== "Tab") return;
  const controls = [
    ...event.currentTarget.querySelectorAll(
      'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
    ),
  ].filter(
    (node) =>
      node.getClientRects().length &&
      getComputedStyle(node).visibility !== "hidden",
  );
  const first = controls[0];
  const last = controls.at(-1);
  if (!first) {
    event.preventDefault();
    return;
  }
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
