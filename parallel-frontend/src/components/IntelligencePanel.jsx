import { useState } from "react";
import { api } from "../api";
import { SourceLink, SourceViewer } from "./ProjectSources";
import { useProjectAction, useWorkspaceQuery } from "./projectHooks";

export default function IntelligencePanel({
  workspaceId,
  onAccessLost,
  onAgents,
}) {
  const base = `/workspaces/${workspaceId}`;
  const [mode, setMode] = useState("briefing");
  const [source, setSource] = useState(null);
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("");
  const [historical, setHistorical] = useState(false);
  const [archived, setArchived] = useState(false);
  const [searchParams, setSearchParams] = useState("");
  const [offset, setOffset] = useState(0);
  const [since, setSince] = useState("");
  const [appliedSince, setAppliedSince] = useState("");
  const [briefOffset, setBriefOffset] = useState(0);
  const actions = useProjectAction(workspaceId, onAccessLost);
  const briefing = useWorkspaceQuery(
    `${base}/continuity?limit=20&offset=${briefOffset}${appliedSince ? `&since=${encodeURIComponent(appliedSince)}` : ""}`,
    workspaceId,
    onAccessLost,
    2000,
  );
  const results = useWorkspaceQuery(
    `${base}/knowledge?limit=20&offset=${offset}${searchParams}`,
    workspaceId,
    onAccessLost,
  );
  const data = briefing.data;
  async function markSeen() {
    const result = await actions.act(
      () =>
        api(`${base}/continuity/visit`, {
          method: "POST",
          body: { through: data.generated_at },
        }),
      "Visit saved. Later changes will appear in your next briefing.",
    );
    if (result) {
      setAppliedSince("");
      setSince("");
      setBriefOffset(0);
      briefing.reload();
    }
  }
  return (
    <section className="project-section" aria-label="Project intelligence">
      <div className="section-heading">
        <div>
          <h2>Project intelligence</h2>
          <p>
            Find the source. Understand what changed. Keep current decisions
            separate from history.
          </p>
        </div>
      </div>
      <div className="button-row section-switch">
        <button
          aria-pressed={mode === "briefing"}
          onClick={() => setMode("briefing")}
        >
          Continuity briefing
        </button>
        <button
          aria-pressed={mode === "search"}
          onClick={() => setMode("search")}
        >
          Search project knowledge
        </button>
      </div>
      {actions.error && <p role="alert">{actions.error}</p>}
      {actions.notice && (
        <p role="status" className="feedback">
          {actions.notice}
        </p>
      )}
      {mode === "briefing" ? (
        <>
          <form
            className="briefing-filter surface"
            onSubmit={(e) => {
              e.preventDefault();
              setAppliedSince(since ? new Date(since).toISOString() : "");
              setBriefOffset(0);
            }}
          >
            <label>
              Changes since
              <input
                type="datetime-local"
                value={since}
                onChange={(e) => setSince(e.target.value)}
              />
            </label>
            <button>Apply time filter</button>
            <button
              type="button"
              onClick={() => {
                setSince("");
                setAppliedSince("");
                setBriefOffset(0);
                briefing.reload();
              }}
            >
              Use previous visit
            </button>
          </form>
          {briefing.error ? (
            <p role="alert">{briefing.error}</p>
          ) : !data ? (
            <p role="status">Loading briefing…</p>
          ) : (
            <>
              <div className="section-heading">
                <p className="muted">
                  {data.since
                    ? `Changes after ${new Date(data.since).toLocaleString()}`
                    : "First visit: all available project history"}
                  <br />
                  Retrieved {new Date(data.generated_at).toLocaleString()}
                </p>
                <button disabled={actions.busy} onClick={markSeen}>
                  Mark caught up
                </button>
              </div>
              <div className="state-summary surface">
                <div>
                  <h3>Current task state</h3>
                  <dl>
                    {["todo", "in_progress", "blocked", "done"].map((x) => (
                      <div key={x}>
                        <dt>{x.replace("_", " ")}</dt>
                        <dd>{data.task_counts[x] || 0}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
                <div>
                  <h3>Decision state</h3>
                  <dl>
                    {["proposed", "accepted", "superseded", "rejected"].map(
                      (x) => (
                        <div key={x}>
                          <dt>{x}</dt>
                          <dd>{data.decision_counts[x] || 0}</dd>
                        </div>
                      ),
                    )}
                  </dl>
                </div>
                <div>
                  <h3>Human attention</h3>
                  <p>{data.pending_approvals} pending approval requests</p>
                  <button onClick={onAgents}>
                    Review agents and approvals
                  </button>
                </div>
              </div>
              <p className="muted">{data.note}</p>
              <section className="surface">
                <h3>
                  Tasks needing prerequisites or attention (
                  {data.blocked_task_total})
                </h3>
                {!data.blocked_tasks.length ? (
                  <p>No blocked tasks in this page.</p>
                ) : (
                  data.blocked_tasks.map((item) => (
                    <div key={item.id}>
                      <SourceLink source={item} onOpen={setSource} />
                      <small> · {item.status.replaceAll("_", " ")}</small>
                    </div>
                  ))
                )}
              </section>
              <div className="briefing-columns">
                <section className="surface">
                  <h3>Decision changes</h3>
                  {!data.decision_changes.length && (
                    <p>No decision changes in this interval.</p>
                  )}
                  {data.decision_changes.map((item) => (
                    <article
                      className="briefing-event"
                      key={`${item.id}:${item.version}`}
                    >
                      <SourceLink
                        source={{
                          kind: "decision",
                          id: item.id,
                          title: item.snapshot.title,
                          version: item.version,
                        }}
                        onOpen={setSource}
                      />
                      <p>
                        {item.snapshot.status} · {item.reason}
                      </p>
                      <small>
                        Event: {new Date(item.event_at).toLocaleString()}
                      </small>
                    </article>
                  ))}
                  <small>
                    {data.decision_change_total} decision revision events
                  </small>
                </section>
                <section className="surface">
                  <h3>Project changes</h3>
                  {!data.changes.items.length && (
                    <p>No changes in this interval.</p>
                  )}
                  {data.changes.items.map((item) => (
                    <article className="briefing-event" key={item.ref}>
                      <SourceLink source={item} onOpen={setSource} />
                      <p>
                        {item.status}
                        {item.archived ? " · archived" : ""}
                      </p>
                      <small>
                        Event: {new Date(item.event_at).toLocaleString()}
                      </small>
                    </article>
                  ))}
                  <small>{data.changes.total} changed source records</small>
                </section>
              </div>
              <section className="surface">
                <h3>Activity and attribution</h3>
                {!data.events.length && <p>No activity in this interval.</p>}
                <ol className="activity-timeline">
                  {data.events.map((item) => (
                    <li key={item.id}>
                      <strong>{item.actor_name}</strong>
                      <p>{item.summary}</p>
                      <small>{new Date(item.event_at).toLocaleString()}</small>
                    </li>
                  ))}
                </ol>
                <small>{data.event_total} persisted events</small>
              </section>
              <div className="pagination">
                <button
                  disabled={!briefOffset}
                  onClick={() => setBriefOffset(briefOffset - 20)}
                >
                  Newer briefing items
                </button>
                <span>Page {briefOffset / 20 + 1}</span>
                <button
                  disabled={
                    briefOffset + 20 >=
                    Math.max(
                      data.event_total,
                      data.changes.total,
                      data.decision_change_total,
                      data.blocked_task_total,
                    )
                  }
                  onClick={() => setBriefOffset(briefOffset + 20)}
                >
                  Older briefing items
                </button>
              </div>
            </>
          )}
        </>
      ) : (
        <>
          <form
            className="project-form surface"
            onSubmit={(e) => {
              e.preventDefault();
              const p = new URLSearchParams({
                q: query,
                include_historical: historical,
                include_archived: archived,
              });
              if (kind) p.set("kind", kind);
              setSearchParams(`&${p}`);
              setOffset(0);
              results.reload();
            }}
          >
            <label>
              Search terms
              <input
                maxLength={200}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="authentication, milestone, handoff…"
              />
            </label>
            <label>
              Record type
              <select
                aria-label="Record type"
                value={kind}
                onChange={(e) => setKind(e.target.value)}
              >
                <option value="">All sources</option>
                {["decision", "task", "message", "activity"].map((x) => (
                  <option key={x} value={x}>
                    {x}
                  </option>
                ))}
              </select>
            </label>
            <div className="button-row">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={historical}
                  onChange={(e) => setHistorical(e.target.checked)}
                />
                Include superseded / rejected decisions
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={archived}
                  onChange={(e) => setArchived(e.target.checked)}
                />
                Include archived tasks
              </label>
            </div>
            <button className="primary">Search sources</button>
          </form>
          <p className="muted">
            Deterministic lexical search ranks matching titles and text. Results
            are evidence records, not a generated answer or semantic search.
          </p>
          {results.error ? (
            <p role="alert">{results.error}</p>
          ) : !results.data ? (
            <p role="status">Loading sources…</p>
          ) : (
            <>
              <p>{results.data.total} matching sources</p>
              {!results.data.total && (
                <p className="empty-state">
                  No matching evidence. Try different terms or record filters.
                </p>
              )}
              <div className="search-results">
                {results.data.items.map((item) => (
                  <article className="surface search-result" key={item.ref}>
                    <SourceLink source={item} onOpen={setSource} />
                    <p className="source-body">{item.excerpt}</p>
                    <small>
                      {item.status} · {item.authority.replaceAll("_", " ")} ·{" "}
                      {new Date(item.event_at).toLocaleString()}
                      {item.archived ? " · archived" : ""}
                    </small>
                  </article>
                ))}
              </div>
              <div className="pagination">
                <button
                  disabled={!offset}
                  onClick={() => setOffset(offset - 20)}
                >
                  Previous sources
                </button>
                <span>
                  {offset + 1}–{offset + results.data.items.length} of{" "}
                  {results.data.total}
                </span>
                <button
                  disabled={offset + 20 >= results.data.total}
                  onClick={() => setOffset(offset + 20)}
                >
                  Next sources
                </button>
              </div>
            </>
          )}
        </>
      )}
      <SourceViewer
        source={source}
        workspaceId={workspaceId}
        onAccessLost={onAccessLost}
        onClose={() => setSource(null)}
        onNavigate={setSource}
      />
    </section>
  );
}
