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
  useEffect(() => {
    if (confirmation && !dialog.current.open) {
      opener.current = document.activeElement;
      dialog.current.showModal();
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
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        <button autoFocus disabled={busy} onClick={onCancel}>
          Cancel
        </button>
        <button className="primary" disabled={busy} onClick={onConfirm}>
          {busy ? "Saving…" : "Confirm"}
        </button>
      </div>
    </dialog>
  );
}
