import { useState } from "react";
import { api } from "../api";
import ConfirmDialog from "./ConfirmDialog";
import { SourceLink, SourcePicker, SourceViewer } from "./ProjectSources";
import { useProjectAction, useWorkspaceQuery } from "./projectHooks";

const blank = {
  title: "",
  context: "",
  statement: "",
  rationale: "",
  alternatives: "",
  tradeoffs: "",
  status: "proposed",
  sources: [],
  reason: "",
};
const fields = [
  ["context", "Problem / context"],
  ["statement", "Decision statement"],
  ["rationale", "Rationale"],
  ["alternatives", "Alternatives considered"],
  ["tradeoffs", "Tradeoffs"],
];

export default function DecisionsPanel({ workspaceId, onAccessLost }) {
  const base = `/workspaces/${workspaceId}/decisions`;
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(blank);
  const [source, setSource] = useState(null);
  const [historyOffset, setHistoryOffset] = useState(0);
  const [successor, setSuccessor] = useState("");
  const [reason, setReason] = useState("");
  const [confirmation, setConfirmation] = useState(null);
  const actions = useProjectAction(workspaceId, onAccessLost);
  const listing = useWorkspaceQuery(
    `${base}?limit=20&offset=${offset}${status ? `&status=${status}` : ""}`,
    workspaceId,
    onAccessLost,
    2000,
  );
  const detail = useWorkspaceQuery(
    selected ? `${base}/${selected}` : null,
    workspaceId,
    onAccessLost,
  );
  const history = useWorkspaceQuery(
    selected
      ? `${base}/${selected}/history?limit=20&offset=${historyOffset}`
      : null,
    workspaceId,
    onAccessLost,
  );
  const accepted = useWorkspaceQuery(
    `${base}?status=accepted&limit=100`,
    workspaceId,
    onAccessLost,
    2000,
  );
  const record = detail.data;
  function choose(id) {
    setSelected(id);
    setEditing(false);
    setHistoryOffset(0);
    setSuccessor("");
    setReason("");
  }
  function change(key, value) {
    setDraft((current) => ({ ...current, [key]: value }));
  }
  async function save(e) {
    e.preventDefault();
    const body = {
      title: draft.title,
      status: draft.status,
      ...Object.fromEntries(fields.map(([key]) => [key, draft[key]])),
      sources: draft.sources.map(({ kind, id }) => ({ kind, id })),
      ...(selected ? { version: draft.version, reason: draft.reason } : {}),
    };
    const result = await actions.act(
      () =>
        api(selected ? `${base}/${selected}` : base, {
          method: selected ? "PATCH" : "POST",
          body,
        }),
      "Decision saved with revision history.",
    );
    if (result) {
      setSelected(result.id);
      setEditing(false);
      listing.reload();
      accepted.reload();
      detail.reload();
      history.reload();
    }
  }
  async function confirm() {
    const replacement = accepted.data?.items.find(
      (item) => item.id === successor,
    );
    const result = await actions.act(
      () =>
        api(`${base}/${record.id}/supersede`, {
          method: "POST",
          body: {
            version: record.version,
            successor_id: successor,
            successor_version: replacement.version,
            reason,
          },
        }),
      "Decision superseded. Its original history is preserved.",
    );
    if (result) {
      setConfirmation(null);
      detail.reload();
      history.reload();
      listing.reload();
    }
  }
  return (
    <section className="project-section" aria-label="Decision records">
      <div className="section-heading">
        <div>
          <h2>Decisions</h2>
          <p>Keep the reasoning, evidence, and changes behind your project.</p>
        </div>
        <button
          className="primary"
          disabled={actions.busy}
          onClick={() => {
            setSelected(null);
            setDraft({ ...blank, sources: [] });
            setEditing(true);
          }}
        >
          New decision
        </button>
      </div>
      {actions.error && !confirmation && (
        <p role="alert" className="feedback error">
          {actions.error}{" "}
          {selected && (
            <button
              onClick={() => {
                detail.reload();
                setEditing(false);
              }}
            >
              Reload decision
            </button>
          )}
        </p>
      )}
      {actions.notice && (
        <p role="status" className="feedback">
          {actions.notice}
        </p>
      )}
      {listing.error && <p role="alert">{listing.error}</p>}
      <div className="knowledge-layout">
        <aside className="surface record-list">
          <label>
            Decision status
            <select
              aria-label="Decision status filter"
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">All states</option>
              {["proposed", "accepted", "superseded", "rejected"].map((x) => (
                <option key={x} value={x}>
                  {x}
                </option>
              ))}
            </select>
          </label>
          {!listing.data ? (
            <p>Loading decisions…</p>
          ) : !listing.data.total ? (
            <p className="empty-state">No decisions yet.</p>
          ) : (
            listing.data.items.map((item) => (
              <button
                key={item.id}
                aria-pressed={selected === item.id}
                className="record-choice"
                disabled={actions.busy}
                onClick={() => choose(item.id)}
              >
                <strong>{item.title}</strong>
                <small>
                  {item.status} · v{item.version}
                </small>
              </button>
            ))
          )}
          <div className="pagination">
            <button disabled={!offset} onClick={() => setOffset(offset - 20)}>
              Previous decisions
            </button>
            <span>
              {listing.data?.items.length
                ? `${offset + 1}–${offset + listing.data.items.length} of ${listing.data.total}`
                : `0 of ${listing.data?.total || 0}`}
            </span>
            <button
              disabled={offset + 20 >= (listing.data?.total || 0)}
              onClick={() => setOffset(offset + 20)}
            >
              Next decisions
            </button>
          </div>
        </aside>
        <div className="surface record-detail">
          {editing ? (
            <form className="project-form" onSubmit={save}>
              <h3>{selected ? "Revise decision" : "Record a decision"}</h3>
              <label>
                Decision title
                <input
                  required
                  maxLength={200}
                  value={draft.title}
                  onChange={(e) => change("title", e.target.value)}
                />
              </label>
              {fields.map(([key, label]) => (
                <label key={key}>
                  {label}
                  <textarea
                    aria-label={label}
                    required={key === "statement"}
                    maxLength={6000}
                    rows={key === "statement" ? 4 : 2}
                    value={draft[key]}
                    onChange={(e) => change(key, e.target.value)}
                  />
                </label>
              ))}
              <label>
                Decision state
                <select
                  aria-label="Decision state"
                  value={draft.status}
                  onChange={(e) => change("status", e.target.value)}
                >
                  {(draft.version && record?.status === "accepted"
                    ? ["accepted"]
                    : draft.version
                      ? ["proposed", "accepted", "rejected"]
                      : ["proposed", "accepted"]
                  ).map((x) => (
                    <option key={x} value={x}>
                      {x}
                    </option>
                  ))}
                </select>
              </label>
              {selected && (
                <label>
                  Revision reason
                  <input
                    required
                    maxLength={1000}
                    value={draft.reason}
                    onChange={(e) => change("reason", e.target.value)}
                  />
                </label>
              )}
              <SourcePicker
                workspaceId={workspaceId}
                value={draft.sources}
                onChange={(value) => change("sources", value)}
                onOpen={setSource}
                onAccessLost={onAccessLost}
              />
              <div className="button-row">
                <button className="primary" disabled={actions.busy}>
                  Save decision
                </button>
                <button
                  type="button"
                  disabled={actions.busy}
                  onClick={() => setEditing(false)}
                >
                  Discard draft
                </button>
              </div>
            </form>
          ) : !selected ? (
            <p className="empty-state">
              Select a decision to inspect its evidence and history, or record
              the team's reasoning.
            </p>
          ) : !record ? (
            <p role={detail.error ? "alert" : "status"}>
              {detail.error || "Loading decision…"}
            </p>
          ) : (
            <>
              <div className="section-heading">
                <h3>{record.title}</h3>
                <span className="status-badge">
                  {record.status} · v{record.version}
                </span>
              </div>
              <p className="muted">
                Recorded by {record.creator_name} ·{" "}
                {new Date(record.created_at).toLocaleString()}
              </p>
              {record.superseded_by_id && (
                <p className="feedback">
                  Historical decision.{" "}
                  <button onClick={() => choose(record.superseded_by_id)}>
                    Open replacement decision
                  </button>
                </p>
              )}
              {fields.map(([key, label]) => (
                <div key={key}>
                  <h4>{label}</h4>
                  <p className="source-body">
                    {record[key] || "Not recorded."}
                  </p>
                </div>
              ))}
              <h4>Linked sources and related tasks</h4>
              {!record.sources.length && (
                <p className="muted">
                  No evidence linked. This decision has no source citations.
                </p>
              )}
              {record.sources.map(({ cited, current }) => (
                <div className="evidence-row" key={`${cited.kind}:${cited.id}`}>
                  <SourceLink source={current} onOpen={setSource} />
                  {cited.version !== current.version && (
                    <small>
                      Originally cited v{cited.version}; current v
                      {current.version}
                    </small>
                  )}
                  {current.archived && <small>Archived source</small>}
                </div>
              ))}
              {!["superseded", "rejected"].includes(record.status) && (
                <button
                  onClick={() => {
                    setDraft({
                      ...record,
                      sources: record.sources.map((s) => s.current),
                      reason: "",
                    });
                    setEditing(true);
                  }}
                >
                  Revise decision
                </button>
              )}
              {record.status === "accepted" && (
                <form
                  className="supersede-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    setConfirmation({
                      title: "Supersede this decision?",
                      message:
                        "The selected accepted decision becomes its replacement. All previous revisions remain available.",
                    });
                  }}
                >
                  <h4>Replace this decision</h4>
                  <label>
                    Replacement decision
                    <select
                      required
                      aria-label="Replacement decision"
                      value={successor}
                      onChange={(e) => setSuccessor(e.target.value)}
                    >
                      <option value="">Select an accepted decision</option>
                      {accepted.data?.items
                        .filter((x) => x.id !== record.id)
                        .map((x) => (
                          <option key={x.id} value={x.id}>
                            {x.title}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    Supersession reason
                    <input
                      required
                      maxLength={1000}
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                    />
                  </label>
                  <button disabled={actions.busy || !successor}>
                    Supersede decision
                  </button>
                </form>
              )}
              <h4>Revision history</h4>
              {history.error && <p role="alert">{history.error}</p>}
              <ol className="revision-list">
                {history.data?.items.map((item) => (
                  <li key={item.version}>
                    <details>
                      <summary>
                        Version {item.version} · {item.snapshot.status} ·{" "}
                        {item.reason}
                      </summary>
                      <small>
                        {new Date(item.created_at).toLocaleString()} · actor{" "}
                        {item.actor_id.slice(0, 8)}
                      </small>
                      {fields.map(([key, label]) => (
                        <p className="source-body" key={key}>
                          <strong>{label}: </strong>
                          {item.snapshot[key] || "Not recorded."}
                        </p>
                      ))}
                      {item.sources.map((s) => (
                        <div key={`${s.kind}:${s.id}`}>
                          <SourceLink source={s} onOpen={setSource} />
                          <p className="source-body">
                            Cited snapshot: {s.body}
                          </p>
                        </div>
                      ))}
                    </details>
                  </li>
                ))}
              </ol>
              <div className="pagination">
                <button
                  disabled={!historyOffset}
                  onClick={() => setHistoryOffset(historyOffset - 20)}
                >
                  Newer revisions
                </button>
                <button
                  disabled={historyOffset + 20 >= (history.data?.total || 0)}
                  onClick={() => setHistoryOffset(historyOffset + 20)}
                >
                  Older revisions
                </button>
              </div>
            </>
          )}
        </div>
      </div>
      <SourceViewer
        source={source}
        workspaceId={workspaceId}
        onAccessLost={onAccessLost}
        onClose={() => setSource(null)}
        onNavigate={setSource}
      />
      <ConfirmDialog
        confirmation={confirmation}
        busy={actions.busy}
        error={actions.error}
        onCancel={() => setConfirmation(null)}
        onConfirm={confirm}
      />
    </section>
  );
}
