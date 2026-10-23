import { useState } from "react";
import { api } from "../api";
import { SourceLink, SourceViewer } from "./ProjectSources";
import ConfirmDialog from "./ConfirmDialog";
import { useProjectAction, useWorkspaceQuery } from "./projectHooks";

export default function NativeActions({ workspaceId, owner, onAccessLost }) {
  const base = `/workspaces/${workspaceId}/action-proposals`;
  const query = useWorkspaceQuery(base, workspaceId, onAccessLost, 1500);
  const actions = useProjectAction(workspaceId, onAccessLost);
  const [confirmation, setConfirmation] = useState(null);
  const [source, setSource] = useState(null);
  async function decide() {
    const { proposal, choice } = confirmation;
    if (
      await actions.act(
        () =>
          api(`${base}/${proposal.id}/${choice}`, {
            method: "POST",
            body: { payload_hash: proposal.payload_hash },
          }),
        choice === "approve"
          ? "Exact task plan approved. The worker will revalidate context before creating tasks."
          : "Task plan rejected.",
      )
    ) {
      setConfirmation(null);
      query.reload();
    }
  }
  return (
    <section
      className="surface native-action-section"
      aria-label="Native action proposals"
    >
      <h3>Native action proposals</h3>
      <p>
        Current owners can approve the exact task plan. Created tasks start To
        do, unassigned, with sequential prerequisites. Approval never means the
        work is done.
      </p>
      {(query.error || actions.error) && (
        <p role="alert">{query.error || actions.error}</p>
      )}
      {actions.notice && <p role="status">{actions.notice}</p>}
      {query.data?.items.length === 0 && (
        <p>
          No native proposals yet. Use Task planner or Delivery coordinator with
          up to five task titles separated by semicolons.
        </p>
      )}
      {query.data?.items.map((proposal) => (
        <article className="native-action-item" key={proposal.id}>
          <h4>Create task plan · {proposal.state}</h4>
          <p className="muted">Run {proposal.run_id}</p>
          {proposal.payload ? (
            <>
              <ol>
                {proposal.payload.proposal.tasks.map((task, index) => (
                  <li key={index}>
                    <strong>{task.title}</strong>
                    <p>{task.description}</p>
                    <p>
                      {task.status} · {task.priority} · unassigned
                      {index > 0 ? " · depends on previous step" : ""}
                    </p>
                  </li>
                ))}
              </ol>
              {!!proposal.payload.proposal.evidence?.length && (
                <div>
                  <h4>Plan evidence</h4>
                  <div className="button-row">
                    {proposal.payload.proposal.evidence.map((ref) => (
                      <SourceLink
                        key={`${ref.kind}:${ref.id}`}
                        source={ref}
                        onOpen={setSource}
                      />
                    ))}
                  </div>
                </div>
              )}
              <details>
                <summary>Exact approved payload</summary>
                <pre className="source-body">
                  {JSON.stringify(proposal.payload, null, 2)}
                </pre>
                <p className="source-body">SHA-256: {proposal.payload_hash}</p>
              </details>
            </>
          ) : (
            <p>
              Source knowledge changed or became unavailable. Request a new
              plan.
            </p>
          )}
          {proposal.error_code && (
            <p role="status">
              Execution stopped: {proposal.error_code.replaceAll("_", " ")}. No
              task plan was applied.
            </p>
          )}
          {proposal.receipt && (
            <div>
              <h4>Execution receipt</h4>
              <p>
                {proposal.receipt.resources.length} tasks created. Review them
                in Tasks.
              </p>
              <ul>
                {proposal.receipt.resources.map((resource) => (
                  <li key={resource.id}>
                    {resource.kind} {resource.id} · version {resource.version}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {owner && proposal.state === "pending" && (
            <div className="button-row">
              {["approve", "reject"].map((choice) => (
                <button
                  key={choice}
                  disabled={
                    actions.busy || (choice === "approve" && !proposal.payload)
                  }
                  onClick={() => setConfirmation({ proposal, choice })}
                >
                  {choice === "approve"
                    ? "Approve task plan"
                    : "Reject task plan"}
                </button>
              ))}
            </div>
          )}
        </article>
      ))}
      <SourceViewer
        source={source}
        workspaceId={workspaceId}
        onAccessLost={onAccessLost}
        onClose={() => setSource(null)}
        onNavigate={setSource}
      />
      <ConfirmDialog
        confirmation={
          confirmation
            ? {
                title:
                  confirmation.choice === "approve"
                    ? "Approve exact task plan?"
                    : "Reject task plan?",
                message:
                  confirmation.choice === "approve"
                    ? "The worker will create exactly the displayed tasks and prerequisites, only if the owner, initiating membership and captured context still match."
                    : "This proposal will remain in history and create no tasks.",
              }
            : null
        }
        error={actions.error}
        busy={actions.busy}
        onCancel={() => setConfirmation(null)}
        onConfirm={decide}
      />
    </section>
  );
}
