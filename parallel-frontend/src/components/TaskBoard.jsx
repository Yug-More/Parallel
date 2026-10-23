import { useEffect, useState } from "react";
import { api } from "../api";

const statuses = [
  ["todo", "To Do"],
  ["in_progress", "In Progress"],
  ["blocked", "Blocked"],
  ["done", "Done"],
];
const blank = {
  title: "",
  description: "",
  assignee_id: "",
  status: "todo",
  priority: "medium",
  due_date: "",
  dependencies: [],
};
function editable(task) {
  return {
    ...task,
    assignee_id: task.assignee_id || "",
    due_date: task.due_date || "",
  };
}

export default function TaskBoard({
  workspaceId,
  members,
  refresh,
  onConfirm,
  onAccessLost,
}) {
  const [page, setPage] = useState({ items: [], total: 0 });
  const [candidates, setCandidates] = useState([]);
  const [editor, setEditor] = useState(null);
  const [status, setStatus] = useState("");
  const [archived, setArchived] = useState(false);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [revision, setRevision] = useState(0);
  const base = `/workspaces/${workspaceId}/tasks`;

  useEffect(() => {
    const controller = new AbortController();
    let pending = false;
    async function update() {
      if (pending) return;
      pending = true;
      try {
        const [rows, options] = await Promise.all([
          api(
            `${base}?limit=50&offset=${offset}&archived=${archived}${status ? `&status=${status}` : ""}`,
            { signal: controller.signal },
          ),
          api(`${base}?limit=100`, { signal: controller.signal }),
        ]);
        if (!controller.signal.aborted) {
          setPage(rows);
          setCandidates(options.items);
          setLoading(false);
        }
      } catch (err) {
        if (err.name !== "AbortError" && !controller.signal.aborted) {
          setError(err.message);
          setLoading(false);
          if (err.status === 404 || err.status === 401)
            onAccessLost(workspaceId);
        }
      } finally {
        pending = false;
      }
    }
    update();
    const timer = setInterval(update, 2000);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [
    workspaceId,
    base,
    status,
    archived,
    offset,
    refresh,
    revision,
    onAccessLost,
  ]);

  async function open(item) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      setEditor(editable(await api(`${base}/${item.id}`)));
    } catch (err) {
      setError(err.message);
      if (err.status === 404) onAccessLost(workspaceId);
    } finally {
      setBusy(false);
    }
  }

  async function save(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    const body = {
      title: editor.title,
      description: editor.description,
      assignee_id: editor.assignee_id || null,
      status: editor.status,
      priority: editor.priority,
      due_date: editor.due_date || null,
      dependency_ids: editor.dependencies.map((item) => item.id),
      ...(editor.id ? { version: editor.version } : {}),
    };
    try {
      const saved = await api(editor.id ? `${base}/${editor.id}` : base, {
        method: editor.id ? "PATCH" : "POST",
        body,
      });
      setEditor(editable(saved));
      setNotice("Task saved.");
      setRevision((value) => value + 1);
    } catch (err) {
      setError(err.message);
      if (err.status === 404) onAccessLost(workspaceId);
    } finally {
      setBusy(false);
    }
  }

  function field(name, value) {
    setEditor((previous) => ({ ...previous, [name]: value }));
  }
  function archive() {
    onConfirm({
      title: "Archive task?",
      message: `“${editor.title}” will remain in history and leave the active task list.`,
      action: async () => {
        await api(`${base}/${editor.id}/archive`, {
          method: "POST",
          body: { version: editor.version },
        });
        setEditor(null);
        setRevision((value) => value + 1);
      },
    });
  }

  return (
    <section aria-label="Workspace tasks">
      <div className="section-heading">
        <div>
          <h2>Tasks</h2>
          <p>Clear ownership, shared progress, and persistent details.</p>
        </div>
        <button
          className="primary"
          disabled={busy}
          onClick={() => {
            setEditor({ ...blank });
            setNotice("");
            setError("");
          }}
        >
          New task
        </button>
      </div>
      <div className="task-filters">
        <label>
          Filter status
          <select
            aria-label="Filter status"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setOffset(0);
            }}
          >
            <option value="">All statuses</option>
            {statuses.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={archived}
            onChange={(event) => {
              setArchived(event.target.checked);
              setOffset(0);
            }}
          />
          Show archived
        </label>
      </div>
      {error && (
        <p role="alert" className="feedback error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="feedback">
          {notice}
        </p>
      )}
      <div className="task-layout">
        <div className="task-list">
          {loading ? (
            <p role="status">Loading tasks…</p>
          ) : !page.items.length ? (
            <div className="empty-state">
              No tasks match this view. Create a task to plan the next step.
            </div>
          ) : (
            page.items.map((task) => (
              <button
                className={`task-row ${editor?.id === task.id ? "selected" : ""}`}
                key={task.id}
                onClick={() => open(task)}
                disabled={busy}
              >
                <strong>{task.title}</strong>
                <span className="task-meta">
                  <span className={`status-tag status-${task.status}`}>
                    {statuses.find(([value]) => value === task.status)?.[1]}
                  </span>
                  <span>{task.priority} priority</span>
                </span>
                <small>
                  {task.assignee_name || "Unassigned"}
                  {task.due_date ? ` · Due ${task.due_date}` : ""}
                </small>
              </button>
            ))
          )}
          <div className="pagination">
            <button
              disabled={!offset || busy}
              onClick={() => setOffset((value) => Math.max(0, value - 50))}
            >
              Previous tasks
            </button>
            <small>
              {page.total} task{page.total === 1 ? "" : "s"}
            </small>
            <button
              disabled={offset + 50 >= page.total || busy}
              onClick={() => setOffset((value) => value + 50)}
            >
              Next tasks
            </button>
          </div>
        </div>
        {!editor ? (
          <div className="task-detail empty-state">
            Select a task to view its details, or create one.
          </div>
        ) : (
          <form
            className="task-detail"
            onSubmit={save}
            aria-label="Task details"
          >
            <div className="section-heading">
              <h3>{editor.id ? "Task details" : "New task"}</h3>
              <button
                type="button"
                disabled={busy}
                onClick={() => setEditor(null)}
              >
                Close task
              </button>
            </div>
            {editor.id && (
              <p className="muted">
                Created by {editor.creator_name} · Updated{" "}
                {new Date(editor.updated_at).toLocaleString()} · Version{" "}
                {editor.version}
                {editor.archived ? " · Archived" : ""}
              </p>
            )}
            <label>
              Task title
              <input
                aria-label="Task title"
                required
                maxLength={200}
                value={editor.title}
                disabled={busy || editor.archived}
                onChange={(event) => field("title", event.target.value)}
              />
            </label>
            <label>
              Description
              <textarea
                aria-label="Description"
                maxLength={12000}
                rows={5}
                value={editor.description}
                disabled={busy || editor.archived}
                onChange={(event) => field("description", event.target.value)}
              />
            </label>
            <div className="form-grid">
              <label>
                Assignee
                <select
                  aria-label="Assignee"
                  value={editor.assignee_id}
                  disabled={busy || editor.archived}
                  onChange={(event) => field("assignee_id", event.target.value)}
                >
                  <option value="">Unassigned</option>
                  {members.map((member) => (
                    <option value={member.id} key={member.id}>
                      {member.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Task status
                <select
                  aria-label="Task status"
                  value={editor.status}
                  disabled={busy || editor.archived}
                  onChange={(event) => field("status", event.target.value)}
                >
                  {statuses.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Priority
                <select
                  aria-label="Priority"
                  value={editor.priority}
                  disabled={busy || editor.archived}
                  onChange={(event) => field("priority", event.target.value)}
                >
                  {["low", "medium", "high", "urgent"].map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Due date
                <input
                  aria-label="Due date"
                  type="date"
                  value={editor.due_date}
                  disabled={busy || editor.archived}
                  onChange={(event) => field("due_date", event.target.value)}
                />
              </label>
            </div>
            <label>
              Prerequisite tasks
              <select
                aria-label="Prerequisite tasks"
                multiple
                size={4}
                value={editor.dependencies.map((item) => item.id)}
                disabled={busy || editor.archived}
                onChange={(event) =>
                  field(
                    "dependencies",
                    [...event.target.selectedOptions].map((option) => ({
                      id: option.value,
                    })),
                  )
                }
              >
                {[...candidates, ...editor.dependencies]
                  .filter(
                    (item, index, rows) =>
                      item.id !== editor.id &&
                      rows.findIndex((row) => row.id === item.id) === index,
                  )
                  .map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.title}
                    </option>
                  ))}
              </select>
            </label>
            <small className="muted">
              Select prerequisites with Ctrl/Command. Dependencies must be done
              before this task can be marked Done. Up to 100 recent active tasks
              are offered.
            </small>
            <div className="button-row">
              {!editor.archived && (
                <button className="primary" disabled={busy}>
                  {busy ? "Saving…" : "Save task"}
                </button>
              )}
              {editor.id && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => open(editor)}
                >
                  Reload task
                </button>
              )}
              {editor.id && !editor.archived && (
                <button
                  type="button"
                  className="danger"
                  disabled={busy}
                  onClick={archive}
                >
                  Archive task
                </button>
              )}
            </div>
          </form>
        )}
      </div>
    </section>
  );
}
