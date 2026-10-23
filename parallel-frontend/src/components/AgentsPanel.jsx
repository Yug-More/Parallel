import { useRef, useState } from "react";
import { api } from "../api";
import NativeActions from "./NativeActions";
import ConfirmDialog from "./ConfirmDialog";
import { SourceLink, SourcePicker, SourceViewer } from "./ProjectSources";
import { useProjectAction, useWorkspaceQuery } from "./projectHooks";

export default function AgentsPanel({
  workspaceId,
  user,
  workspace,
  onAccessLost,
  onNavigate,
}) {
  const base = `/workspaces/${workspaceId}`;
  const [contract, setContract] = useState("local.handoff.v1");
  const [objective, setObjective] = useState("");
  const [taskId, setTaskId] = useState("");
  const [publish, setPublish] = useState(false);
  const [refs, setRefs] = useState([]);
  const [selected, setSelected] = useState(null);
  const [source, setSource] = useState(null);
  const [offset, setOffset] = useState(0);
  const [approvalOffset, setApprovalOffset] = useState(0);
  const [factsLimit, setFactsLimit] = useState(50);
  const [confirmation, setConfirmation] = useState(null);
  const request = useRef(null);
  const retryKeys = useRef({});
  const actions = useProjectAction(workspaceId, onAccessLost);
  const contracts = useWorkspaceQuery(
    "/agent-contracts",
    workspaceId,
    onAccessLost,
  );
  const tasks = useWorkspaceQuery(
    `${base}/tasks?limit=100`,
    workspaceId,
    onAccessLost,
    2000,
  );
  const listing = useWorkspaceQuery(
    `${base}/runs?limit=20&offset=${offset}`,
    workspaceId,
    onAccessLost,
    1500,
  );
  const approvals = useWorkspaceQuery(
    `${base}/approvals?limit=20&offset=${approvalOffset}`,
    workspaceId,
    onAccessLost,
    1500,
  );
  const detail = useWorkspaceQuery(
    selected ? `${base}/runs/${selected}` : null,
    workspaceId,
    onAccessLost,
    1500,
  );
  const modelConfig = useWorkspaceQuery(
    selected ? `${base}/answers` : null,
    workspaceId,
    onAccessLost,
  );
  const reasoningKeys = useRef({});
  const run = detail.data;
  function refresh() {
    listing.reload();
    detail.reload();
    approvals.reload();
  }
  function openRun(id) {
    setSelected(id);
    setFactsLimit(50);
  }
  async function start(e) {
    e.preventDefault();
    const body = {
      agent_type: contract,
      objective,
      task_id: taskId || null,
      publish,
      input_refs: refs.map(({ kind, id }) => ({ kind, id })),
    };
    const signature = JSON.stringify(body);
    if (request.current?.signature !== signature)
      request.current = { signature, key: crypto.randomUUID() };
    const result = await actions.act(
      () =>
        api(`${base}/runs`, {
          method: "POST",
          body: { ...body, idempotency_key: request.current.key },
        }),
      "Run queued. Completion is shown only after the worker saves its result.",
    );
    if (result) {
      openRun(result.id);
      request.current = null;
      refresh();
    }
  }
  async function confirm() {
    const result = await actions.act(confirmation.action, confirmation.success);
    if (result) {
      setConfirmation(null);
      refresh();
    }
  }
  async function retry() {
    retryKeys.current[run.id] ||= crypto.randomUUID();
    const result = await actions.act(
      () =>
        api(`${base}/runs/${run.id}/retry`, {
          method: "POST",
          body: { idempotency_key: retryKeys.current[run.id] },
        }),
      "A new retry was queued; the failed record remains unchanged.",
    );
    if (result) {
      openRun(result.id);
      refresh();
    }
  }
  function approve(item, action) {
    setConfirmation({
      title:
        action === "approve"
          ? "Approve this exact publication?"
          : "Reject this publication?",
      message:
        action === "approve"
          ? "The local worker may publish the previewed content to this workspace conversation. Approval does not permit external actions or task completion."
          : "The publication will be cancelled. The computed report remains inspectable.",
      action: () =>
        api(`${base}/approvals/${item.id}/${action}`, {
          method: "POST",
          body: { payload_hash: item.payload_hash },
        }),
      success:
        action === "approve"
          ? "Approval saved. Execution is tracked below."
          : "Publication rejected.",
    });
  }
  return (
    <section
      className="project-section"
      aria-label="Local agents and approvals"
    >
      <div className="section-heading">
        <div>
          <h2>Agents & approvals</h2>
          <p>
            Bounded local computation, durable evidence, and explicit human
            control.
          </p>
        </div>
      </div>
      {actions.error && !confirmation && (
        <p role="alert" className="feedback error">
          {actions.error}
        </p>
      )}
      {actions.notice && (
        <p role="status" className="feedback">
          {actions.notice}
        </p>
      )}
      <details className="surface contract-explainer">
        <summary>Supported execution contracts</summary>
        {contracts.data?.map((item) => (
          <article key={item.id}>
            <h3>{item.name}</h3>
            <p>{item.description}</p>
            <small>
              {item.id} · {item.mode.replaceAll("_", " ")}
            </small>
            <p>
              Input: {item.input}
              <br />
              Output: {item.output}
            </p>
          </article>
        ))}
        {contracts.error && <p role="alert">{contracts.error}</p>}
        <p>
          No code, shell commands, paid providers, or external services are
          executed. Reports never mark tasks Done.
        </p>
      </details>
      <details className="surface new-run-form" open={!selected}>
        <summary>Start a local run</summary>
        <form className="project-form" onSubmit={start}>
          <h3>Start a local run</h3>
          <div className="form-grid">
            <label>
              Agent capability
              <select
                aria-label="Agent capability"
                value={contract}
                onChange={(e) => setContract(e.target.value)}
              >
                {contracts.data?.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Related task
              <select
                aria-label="Related task"
                value={taskId}
                onChange={(e) => setTaskId(e.target.value)}
              >
                <option value="">Workspace-wide report</option>
                {tasks.data?.items
                  .filter((t) => t.status !== "done")
                  .map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.title}
                    </option>
                  ))}
              </select>
            </label>
          </div>
          <label>
            Run objective
            <input
              required
              maxLength={1000}
              value={objective}
              onChange={(e) => setObjective(e.target.value)}
              placeholder="Prepare the implementation handoff"
            />
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={publish}
              onChange={(e) => setPublish(e.target.checked)}
            />
            Request owner approval to publish the exact report to Conversation
          </label>
          <details>
            <summary>Add explicit project sources</summary>
            <SourcePicker
              workspaceId={workspaceId}
              value={refs}
              onChange={setRefs}
              onOpen={setSource}
              onAccessLost={onAccessLost}
            />
          </details>
          <button
            className="primary"
            disabled={actions.busy || !contracts.data}
          >
            Queue run
          </button>
          <small className="muted">
            Queued runs wait for the local worker. Status and handoff work
            requires an unblocked active task; dependency analysis can inspect
            blocked work.
          </small>
        </form>
      </details>
      <div className="knowledge-layout">
        <aside className="surface record-list">
          <h3>Execution history</h3>
          {listing.error && <p role="alert">{listing.error}</p>}
          {!listing.data ? (
            <p>Loading runs…</p>
          ) : !listing.data.total ? (
            <p className="empty-state">No runs yet.</p>
          ) : (
            listing.data.items.map((item) => (
              <button
                key={item.id}
                className="record-choice"
                aria-pressed={selected === item.id}
                onClick={() => openRun(item.id)}
              >
                <strong>{item.objective}</strong>
                <small>
                  {item.state.replaceAll("_", " ")} · {item.agent_type}
                </small>
              </button>
            ))
          )}
          <div className="pagination">
            <button disabled={!offset} onClick={() => setOffset(offset - 20)}>
              Newer runs
            </button>
            <button
              disabled={offset + 20 >= (listing.data?.total || 0)}
              onClick={() => setOffset(offset + 20)}
            >
              Older runs
            </button>
          </div>
        </aside>
        <article className="surface record-detail" aria-label="Run details">
          {!selected ? (
            <p className="empty-state">
              Select a run to inspect its plan, evidence, events, and saved
              outcome.
            </p>
          ) : !run ? (
            <p role={detail.error ? "alert" : "status"}>
              {detail.error || "Loading run…"}
            </p>
          ) : (
            <>
              <div className="section-heading">
                <h3>{run.objective}</h3>
                <span className="status-badge">
                  {run.state.replaceAll("_", " ")}
                </span>
              </div>
              <p className="muted">
                {run.agent_type} · attempt {run.attempt}/3
              </p>
              <p>
                Created {new Date(run.created_at).toLocaleString()}
                {run.completed_at
                  ? ` · Finished ${new Date(run.completed_at).toLocaleString()}`
                  : ""}
              </p>
              {run.error_code && (
                <p className="feedback error">
                  Execution outcome: {run.error_code.replaceAll("_", " ")}. No
                  success is inferred.
                </p>
              )}
              {run.state === "queued" && (
                <p>Awaiting worker execution or delegated results.</p>
              )}
              {run.state === "waiting_for_approval" && (
                <p>
                  The report was computed. Publication is awaiting approval or
                  worker execution.
                </p>
              )}
              {run.parent_id && (
                <button onClick={() => openRun(run.parent_id)}>
                  Open coordinator run
                </button>
              )}
              {!run.parent_id &&
                !["completed", "failed", "cancelled"].includes(run.state) &&
                (run.initiator_id === user.id ||
                  workspace.role === "owner") && (
                  <button
                    onClick={() =>
                      setConfirmation({
                        title: "Cancel this run?",
                        message:
                          "Pending delegates and publication approvals will be cancelled. Any late computation will be discarded.",
                        action: () =>
                          api(`${base}/runs/${run.id}/cancel`, {
                            method: "POST",
                          }),
                        success: "Run cancelled.",
                      })
                    }
                  >
                    Cancel run
                  </button>
                )}
              {!run.parent_id &&
                run.state === "failed" &&
                run.attempt < 3 &&
                run.initiator_id === user.id && (
                  <button disabled={actions.busy} onClick={retry}>
                    Retry failed run
                  </button>
                )}
              {run.children.length > 0 && (
                <div>
                  <h4>Delegated plan</h4>
                  <ol>
                    {run.children.map((child) => (
                      <li key={child.id}>
                        <button
                          className="source-link"
                          onClick={() => openRun(child.id)}
                        >
                          {child.agent_type} ·{" "}
                          {child.state.replaceAll("_", " ")}
                        </button>
                      </li>
                    ))}
                  </ol>
                  <p>
                    Coordinator composes the child results only after both
                    complete against consistent project state.
                  </p>
                </div>
              )}
              {run.evidence_unavailable && (
                <p className="feedback">
                  Source knowledge changed or became unavailable. The saved
                  report and context are hidden. Start a fresh run.
                </p>
              )}
              {run.outcome && (
                <>
                  <h4>Saved result</h4>
                  <p className="source-body report-summary">
                    {run.outcome.summary}
                  </p>
                  <p className="muted">
                    As of {new Date(run.outcome.as_of).toLocaleString()}
                  </p>
                  <p>{run.outcome.interpretation}</p>
                  <ol className="report-facts">
                    {run.outcome.facts.slice(0, factsLimit).map((fact, i) => (
                      <li key={i}>
                        <p>{fact.text}</p>
                        <div className="source-links">
                          {fact.sources.map((s) => (
                            <SourceLink
                              key={`${s.kind}:${s.id}`}
                              source={s}
                              onOpen={setSource}
                            />
                          ))}
                        </div>
                      </li>
                    ))}
                  </ol>
                  {factsLimit < run.outcome.facts.length && (
                    <button onClick={() => setFactsLimit(factsLimit + 50)}>
                      Show more report facts
                    </button>
                  )}
                </>
              )}
              {run.context && (
                <details>
                  <summary>Authorized context and scope</summary>
                  <p>{run.context.scope}</p>
                  <p className="muted">
                    Snapshot {run.context.as_of} · {run.context.tasks.length}{" "}
                    tasks, {run.context.decisions.length} accepted decisions
                  </p>
                  {run.context.input_sources.map((s) => (
                    <SourceLink
                      key={`${s.kind}:${s.id}`}
                      source={s}
                      onOpen={setSource}
                    />
                  ))}
                  <small className="hash-label">
                    Context fingerprint: {run.context.fingerprint}
                  </small>
                </details>
              )}
              {modelConfig.data?.model_enabled &&
                !run.evidence_unavailable &&
                run.objective.length >= 3 &&
                run.objective.length <= 200 && (
                  <div>
                    <p>
                      Optional paid model interpretation retrieves current
                      evidence for this objective. It cannot change the run or
                      its approved plan.
                    </p>
                    <button
                      disabled={actions.busy}
                      onClick={async () => {
                        reasoningKeys.current[run.id] ||= crypto.randomUUID();
                        const result = await actions.act(
                          () =>
                            api(`${base}/runs/${run.id}/reasoning`, {
                              method: "POST",
                              body: {
                                idempotency_key: reasoningKeys.current[run.id],
                              },
                            }),
                          "Cited interpretation saved in Ask workspace.",
                        );
                        if (result) onNavigate?.("answers");
                      }}
                    >
                      Request cited model interpretation
                    </button>
                  </div>
                )}
              <h4>Execution timeline</h4>
              <ol className="activity-timeline">
                {run.events.map((item) => (
                  <li key={item.id}>
                    <strong>{item.event.replaceAll("_", " ")}</strong>
                    <br />
                    <small>{new Date(item.created_at).toLocaleString()}</small>
                    <details>
                      <summary>Event details</summary>
                      <pre>{JSON.stringify(item.detail, null, 2)}</pre>
                    </details>
                  </li>
                ))}
              </ol>
            </>
          )}
        </article>
      </div>
      <NativeActions
        workspaceId={workspaceId}
        owner={workspace.role === "owner"}
        onAccessLost={onAccessLost}
      />
      <section
        className="approval-section surface"
        aria-label="Publication approvals"
      >
        <h3>Publication approvals</h3>
        <p>
          Only the current owner can approve. Each approval is bound to the
          exact preview and expires after 24 hours.
        </p>
        {approvals.error && <p role="alert">{approvals.error}</p>}
        {approvals.data?.total === 0 && (
          <p className="empty-state">No approval requests.</p>
        )}
        {approvals.data?.items.map((item) => (
          <article className="approval-item" key={item.id}>
            <div className="section-heading">
              <h4>Publish local report</h4>
              <span className="status-badge">{item.state}</span>
            </div>
            <p>Expires {new Date(item.expires_at).toLocaleString()}</p>
            <button onClick={() => openRun(item.run_id)}>
              Inspect requesting run
            </button>
            <details open={item.state === "pending"}>
              <summary>Exact proposed content</summary>
              <p className="source-body approval-preview">
                {item.payload?.content ||
                  "Report hidden: source knowledge changed or became unavailable."}
              </p>
              <small className="hash-label">
                Payload SHA-256: {item.payload_hash}
              </small>
            </details>
            {item.state === "pending" &&
              (workspace.role === "owner" ? (
                <div className="button-row">
                  <button
                    className="primary"
                    disabled={actions.busy}
                    onClick={() => approve(item, "approve")}
                  >
                    Approve publication
                  </button>
                  <button
                    disabled={actions.busy}
                    onClick={() => approve(item, "reject")}
                  >
                    Reject publication
                  </button>
                </div>
              ) : (
                <p className="muted">Owner approval required.</p>
              ))}
            {item.state === "approved" && (
              <p>Approved; waiting for worker execution.</p>
            )}
            {item.message_id && (
              <SourceLink
                source={{
                  kind: "message",
                  id: item.message_id,
                  title: "Open published report",
                }}
                onOpen={setSource}
              />
            )}
            {item.error_code && (
              <p role="alert">{item.error_code.replaceAll("_", " ")}</p>
            )}
          </article>
        ))}
        <div className="pagination">
          <button
            disabled={!approvalOffset}
            onClick={() => setApprovalOffset(approvalOffset - 20)}
          >
            Newer approvals
          </button>
          <button
            disabled={approvalOffset + 20 >= (approvals.data?.total || 0)}
            onClick={() => setApprovalOffset(approvalOffset + 20)}
          >
            Older approvals
          </button>
        </div>
      </section>
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
