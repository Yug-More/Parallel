import { useEffect, useRef, useId } from "react";
import { containDialogFocus } from "./dialogFocus";

export default function ConfirmDialog({
  confirmation,
  busy,
  error,
  onCancel,
  onConfirm,
}) {
  const dialog = useRef(null);
  const titleId = useId();
  const opener = useRef(null);
  const cancelButton = useRef(null);
  useEffect(() => {
    if (confirmation && !dialog.current.open) {
      opener.current = document.activeElement;
      dialog.current.showModal();
      cancelButton.current?.focus();
    }
    if (!confirmation && dialog.current.open) {
      dialog.current.close();
      if (opener.current?.isConnected) opener.current.focus();
    }
  }, [confirmation]);
  return (
    <dialog
      ref={dialog}
      className="confirm-dialog"
      aria-labelledby={titleId}
      onKeyDown={containDialogFocus}
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onCancel();
      }}
    >
      <h2 id={titleId}>{confirmation?.title}</h2>
      <p>{confirmation?.message}</p>
      {confirmation?.preview && (
        <div className="confirmation-preview">
          <h3>Exact task effect</h3>
          <pre tabIndex={0} aria-label="Exact task effect">
            {confirmation.preview}
          </pre>
        </div>
      )}
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        <button ref={cancelButton} autoFocus disabled={busy} onClick={onCancel}>
          Cancel
        </button>
        <button className="primary" disabled={busy} onClick={onConfirm}>
          {busy ? "Saving…" : "Confirm"}
        </button>
      </div>
    </dialog>
  );
}
