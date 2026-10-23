import { useEffect, useRef } from "react";

export default function ConfirmDialog({
  confirmation,
  busy,
  error,
  onCancel,
  onConfirm,
}) {
  const dialog = useRef(null);
  useEffect(() => {
    if (confirmation && !dialog.current.open) dialog.current.showModal();
    if (!confirmation && dialog.current.open) dialog.current.close();
  }, [confirmation]);
  return (
    <dialog
      ref={dialog}
      className="confirm-dialog"
      aria-labelledby="confirm-title"
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onCancel();
      }}
    >
      <h2 id="confirm-title">{confirmation?.title}</h2>
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
