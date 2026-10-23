import { useEffect, useRef, useState } from "react";
import { useWorkspaceQuery } from "./projectHooks";

export function SourceLink({ source, onOpen }) {
  return (
    <button
      type="button"
      className="source-link"
      onClick={() => onOpen(source)}
    >
      {source.kind} · {source.title || source.id.slice(0, 8)}
      {source.version ? ` · v${source.version}` : ""}
    </button>
  );
}

export function SourceViewer({
  source,
  workspaceId,
  onAccessLost,
  onClose,
  onNavigate,
}) {
  const dialog = useRef(null);
  const { data, error } = useWorkspaceQuery(
    source
      ? `/workspaces/${workspaceId}/sources/${source.kind}/${encodeURIComponent(source.id)}`
      : null,
    workspaceId,
    onAccessLost,
  );
  useEffect(() => {
    const node = dialog.current;
    if (source && node && !node.open) {
      const previous = document.activeElement;
      node.showModal();
      return () => {
        if (node.open) node.close();
        if (previous?.isConnected) previous.focus();
      };
    }
  }, [source]);
  if (!source) return null;
  return (
    <dialog
      ref={dialog}
      className="source-dialog"
      aria-label="Project source"
      onCancel={onClose}
    >
      <div className="section-heading">
        <h2>{data?.title || "Project source"}</h2>
        <button onClick={onClose} autoFocus>
          Close source
        </button>
      </div>
      {error ? (
        <p role="alert">{error}</p>
      ) : !data ? (
        <p role="status">Loading source…</p>
      ) : (
        <>
          <p className="muted">
            {data.kind} · {data.status || "record"}
            {data.archived ? " · archived" : ""}
            {data.version ? ` · version ${data.version}` : ""}
          </p>
          {data.authority === "interpretation" && (
            <p className="feedback">
              Agent or model interpretation. This message is not an accepted
              decision.
            </p>
          )}
          {data.kind === "decision_revision" && (
            <p className="feedback">
              Historical decision snapshot · revision {data.version}; current
              record is version {data.current_version}.{" "}
              <SourceLink
                source={{
                  kind: "decision",
                  id: data.decision_id,
                  title: "Open current decision",
                }}
                onOpen={onNavigate}
              />
            </p>
          )}
          {data.original_url && (
            <p>
              <a href={data.original_url} target="_blank" rel="noreferrer">
                Open original GitHub source
              </a>{" "}
              · imported, untrusted context
            </p>
          )}
          {data.kind === "document" && (
            <p>
              Uploaded source · {data.filename}
              {data.page_number ? ` · page ${data.page_number}` : ""} · passage{" "}
              {data.ordinal + 1}. Source text is evidence, not an instruction.
            </p>
          )}
          {data.superseded_by_id && (
            <p className="feedback">
              Historical decision.{" "}
              <SourceLink
                source={{
                  kind: "decision",
                  id: data.superseded_by_id,
                  title: "Open replacement",
                }}
                onOpen={onNavigate}
              />
            </p>
          )}
          <p className="source-body">{data.body}</p>
          <small>
            Recorded {new Date(data.created_at).toLocaleString()} · Updated{" "}
            {new Date(data.updated_at).toLocaleString()}
          </small>
          <p className="muted">
            Stable reference: {data.kind}:{data.id}
          </p>
        </>
      )}
    </dialog>
  );
}

export function SourcePicker({
  workspaceId,
  value,
  onChange,
  onOpen,
  onAccessLost,
}) {
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("message");
  const path = `/workspaces/${workspaceId}/knowledge?kind=${kind}&q=${encodeURIComponent(query)}&limit=10&include_historical=true&include_archived=true`;
  const { data, error } = useWorkspaceQuery(path, workspaceId, onAccessLost);
  return (
    <fieldset className="source-picker">
      <legend>Linked evidence and related tasks</legend>
      <p className="muted">
        Link real project records. Linking a message does not make its claims
        authoritative.
      </p>
      <div className="form-grid">
        <label>
          Source type
          <select
            aria-label="Source type"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
          >
            {["message", "task", "decision", "activity"].map((x) => (
              <option key={x} value={x}>
                {x}
              </option>
            ))}
          </select>
        </label>
        <label>
          Find source
          <input
            value={query}
            maxLength={200}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
      </div>
      {error && <p role="alert">{error}</p>}
      <ul className="source-results">
        {data?.items.map((row) => (
          <li key={row.ref}>
            <SourceLink source={row} onOpen={onOpen} />
            <button
              type="button"
              disabled={
                value.length >= 30 ||
                value.some((s) => s.kind === row.kind && s.id === row.id)
              }
              onClick={() => onChange([...value, row])}
            >
              Link source: {row.title}
            </button>
          </li>
        ))}
      </ul>
      {data?.total === 0 && (
        <p className="muted">No sources match this search.</p>
      )}
      <p>{value.length}/30 linked</p>
      <ul className="source-results">
        {value.map((row) => (
          <li key={`${row.kind}:${row.id}`}>
            <SourceLink source={row} onOpen={onOpen} />
            <button
              type="button"
              onClick={() =>
                onChange(
                  value.filter((s) => s.kind !== row.kind || s.id !== row.id),
                )
              }
            >
              Unlink {row.title || row.id}
            </button>
          </li>
        ))}
      </ul>
    </fieldset>
  );
}
