import { useWorkspaceQuery } from "./projectHooks";

export default function OverviewPanel({
  workspaceId,
  onAccessLost,
  onNavigate,
}) {
  const query = useWorkspaceQuery(
    `/workspaces/${workspaceId}/overview`,
    workspaceId,
    onAccessLost,
    3000,
  );
  if (query.error) return <p role="alert">{query.error}</p>;
  if (!query.data) return <p role="status">Loading project overview…</p>;
  const data = query.data;
  return (
    <section className="project-section" aria-label="Project overview">
      <div className="section-heading">
        <div>
          <h2>Project overview</h2>
          <p>
            Live project state and the next useful steps. Reports never mark
            tasks complete automatically.
          </p>
        </div>
      </div>
      <details className="surface">
        <summary>First project: setup and return checklist</summary>
        <ol>
          <li>
            Choose or create a workspace, then invite a registered teammate in
            Members.
          </li>
          <li>
            Upload text, Markdown or an extractable PDF in Documents. Wait for
            Ready.
          </li>
          <li>
            Optionally connect a public repository or authorize a configured
            GitHub App in Connections.
          </li>
          <li>
            Search sources in Intelligence and inspect citations in Ask
            workspace.
          </li>
          <li>
            Run Delivery coordinator with explicit task titles, or use the exact
            objective “triage github issues”.
          </li>
          <li>
            Review the exact native plan in Agents. An owner approves it; only
            an executed receipt means tasks were created.
          </li>
          <li>
            Return to Intelligence for changes since your last visit. Tasks stay
            unfinished until a person updates them.
          </li>
        </ol>
      </details>
      <div className="form-grid">
        <article className="surface">
          <h3>Tasks</h3>
          <p>
            {Object.values(data.task_counts).reduce((a, b) => a + b, 0)} active
            · {data.task_counts.done || 0} done · {data.blocked_task_total}{" "}
            blocked
          </p>
          <button onClick={() => onNavigate("tasks")}>Open task board</button>
        </article>
        <article className="surface">
          <h3>Decisions</h3>
          <p>
            {data.decision_counts.accepted || 0} accepted ·{" "}
            {data.decision_counts.proposed || 0} proposed
          </p>
          {!!data.current_decisions.length && (
            <ul>
              {data.current_decisions.map((decision) => (
                <li key={decision.id}>
                  {decision.title} · v{decision.version}
                </li>
              ))}
            </ul>
          )}
          <button onClick={() => onNavigate("decisions")}>
            Review decisions
          </button>
        </article>
        <article className="surface">
          <h3>Human approvals</h3>
          <p>
            {data.pending_approvals} pending report publications ·{" "}
            {data.pending_native_actions} native task plans
          </p>
          <button onClick={() => onNavigate("agents")}>
            Review runs and approvals
          </button>
        </article>
        <article className="surface">
          <h3>Connected knowledge</h3>
          <p>
            {data.documents} {data.documents === 1 ? "document" : "documents"} ·{" "}
            {data.connections} repository{" "}
            {data.connections === 1 ? "connection" : "connections"}
          </p>
          <div className="button-row">
            <button onClick={() => onNavigate("documents")}>
              Manage documents
            </button>
            <button onClick={() => onNavigate("connections")}>
              Manage connections
            </button>
          </div>
        </article>
      </div>
      <article className="surface">
        <h3>Worker health</h3>
        <p>
          {data.worker.active_workers
            ? "Worker recently polling"
            : "No recent worker heartbeat"}
          . {data.worker.note}
        </p>
        {!data.worker.active_workers && (
          <p>
            Start the backend worker to process document uploads, syncs, runs
            and approved task plans.
          </p>
        )}
      </article>
      <article className="surface">
        <h3>Next steps</h3>
        <div className="button-row">
          {Object.keys(data.task_counts).length === 0 && (
            <button onClick={() => onNavigate("tasks")}>
              Create your first task
            </button>
          )}
          {!data.documents && (
            <button onClick={() => onNavigate("documents")}>
              Add project context
            </button>
          )}
          {!!data.blocked_task_total && (
            <button onClick={() => onNavigate("tasks")}>
              Resolve task blockers
            </button>
          )}
          <button onClick={() => onNavigate("answers")}>
            Ask a project question
          </button>
          <button onClick={() => onNavigate("intelligence")}>
            Read continuity briefing
          </button>
          <button onClick={() => onNavigate("members")}>
            Invite a collaborator
          </button>
        </div>
      </article>
      <article className="surface">
        <h3>Recent changes</h3>
        {!data.events.length ? (
          <p>No changes yet.</p>
        ) : (
          <ul>
            {data.events.map((event) => (
              <li key={event.id}>
                {event.actor_name}: {event.summary}
              </li>
            ))}
          </ul>
        )}
      </article>
      <article className="surface">
        <h3>Recent delegated work</h3>
        {!data.recent_runs.length ? (
          <p>
            No agent runs yet. Start with a local status or dependency report.
          </p>
        ) : (
          <ul>
            {data.recent_runs.map((run) => (
              <li key={run.id}>
                {run.objective} · {run.state.replaceAll("_", " ")}
              </li>
            ))}
          </ul>
        )}
        <button onClick={() => onNavigate("agents")}>
          Open agent workspace
        </button>
      </article>
    </section>
  );
}
