import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import AgentsPanel from "../components/AgentsPanel";
import DecisionsPanel from "../components/DecisionsPanel";
import OverviewPanel from "../components/OverviewPanel";
import AnswersPanel from "../components/AnswersPanel";
import ConnectionsPanel from "../components/ConnectionsPanel";
import DocumentsPanel from "../components/DocumentsPanel";
import IntelligencePanel from "../components/IntelligencePanel";
import ChatBubble from "../components/ChatBubble";
import ConfirmDialog from "../components/ConfirmDialog";
import InvitationInbox from "../components/InvitationInbox";
import TaskBoard from "../components/TaskBoard";
import ThemeToggle from "../components/ThemeToggle";
import WorkspaceMembers from "../components/WorkspaceMembers";
import "./Collaboration.css";

export default function Dashboard({ user, onLogout }) {
  const [workspaces, setWorkspaces] = useState([]);
  const [workspaceId, setWorkspaceId] = useState(
    () => new URLSearchParams(window.location.search).get("workspace") || "",
  );
  const [snapshot, setSnapshot] = useState(null);
  const [invitations, setInvitations] = useState([]);
  const [tab, setTab] = useState(() => {
    const section = new URLSearchParams(window.location.search).get("section");
    return [
      "conversation",
      "tasks",
      "decisions",
      "intelligence",
      "documents",
      "connections",
      "overview",
      "answers",
      "agents",
      "members",
      "activity",
      "inbox",
    ].includes(section)
      ? section
      : "conversation";
  });
  const [draft, setDraft] = useState("");
  const [older, setOlder] = useState([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [confirmation, setConfirmation] = useState(null);
  const bump = useCallback(() => setRefresh((value) => value + 1), []);
  const lostAccess = useCallback((id) => {
    setSnapshot(null);
    setOlder([]);
    setDraft("");
    setWorkspaceId((current) => (current === id ? "" : current));
    setNotice("Workspace access changed. Its cached content has been cleared.");
    setRefresh((value) => value + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let pending = false;
    async function update() {
      if (pending) return;
      pending = true;
      try {
        const [rows, inbox] = await Promise.all([
          api("/workspaces", { signal: controller.signal }),
          api("/invitations", { signal: controller.signal }),
        ]);
        if (controller.signal.aborted) return;
        setWorkspaces(rows);
        setInvitations(inbox);
        if (!workspaceId) {
          setWorkspaceId(rows[0]?.id || "");
          return;
        }
        if (!rows.some((row) => row.id === workspaceId)) {
          lostAccess(workspaceId);
          return;
        }
        const workspace = await api(`/workspaces/${workspaceId}`, {
          signal: controller.signal,
        });
        const [messages, members, activity, sent] = await Promise.all([
          ...["messages", "members", "activity"].map((resource) =>
            api(`/workspaces/${workspaceId}/${resource}`, {
              signal: controller.signal,
            }),
          ),
          workspace.role === "owner"
            ? api(`/workspaces/${workspaceId}/invitations`, {
                signal: controller.signal,
              }).catch((err) => {
                if (err.status === 403) return [];
                throw err;
              })
            : [],
        ]);
        if (!controller.signal.aborted)
          setSnapshot({
            id: workspaceId,
            workspace,
            messages,
            members,
            activity,
            sent,
          });
      } catch (err) {
        if (err.name !== "AbortError" && !controller.signal.aborted) {
          setError(err.message);
          if (err.status === 404 || err.status === 401) lostAccess(workspaceId);
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
  }, [workspaceId, refresh, lostAccess]);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (workspaceId) url.searchParams.set("workspace", workspaceId);
    else url.searchParams.delete("workspace");
    url.searchParams.set("section", tab);
    window.history.replaceState(null, "", url);
  }, [workspaceId, tab]);

  const view = snapshot?.id === workspaceId ? snapshot : null;
  async function act(action, success = "") {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await action();
      if (success) setNotice(success);
      bump();
      return result;
    } catch (err) {
      setError(err.message);
      if (err.status === 404 && err.message === "Workspace not found")
        lostAccess(workspaceId);
      return null;
    } finally {
      setBusy(false);
    }
  }
  async function createWorkspace(event) {
    event.preventDefault();
    const workspace = await act(
      () => api("/workspaces", { method: "POST", body: { name } }),
      "Workspace created.",
    );
    if (workspace) {
      setWorkspaces((rows) => [...rows, workspace]);
      setWorkspaceId(workspace.id);
      setSnapshot(null);
      setName("");
      setDraft("");
      setOlder([]);
      setTab("conversation");
    }
  }
  async function send(event) {
    event.preventDefault();
    if (!draft.trim()) return;
    const result = await act(() =>
      api(`/workspaces/${workspaceId}/messages`, {
        method: "POST",
        body: { content: draft },
      }),
    );
    if (result) setDraft("");
  }
  async function askAgent() {
    const source = [...(view?.messages || [])]
      .reverse()
      .find((message) => message.role === "user");
    if (source)
      await act(() =>
        api(`/workspaces/${workspaceId}/agent-replies`, {
          method: "POST",
          body: { message_id: source.id },
        }),
      );
  }
  async function loadOlder() {
    const first = older[0] || view?.messages[0];
    if (!first) return;
    const rows = await act(() =>
      api(
        `/workspaces/${workspaceId}/messages?before=${encodeURIComponent(first.id)}`,
      ),
    );
    if (rows) {
      setOlder((previous) => [...rows, ...previous]);
      if (!rows.length) setNotice("Beginning of conversation.");
    }
  }
  async function respond(invitation, action) {
    const result = await act(
      () => api(`/invitations/${invitation.id}/${action}`, { method: "POST" }),
      action === "accept" ? "Invitation accepted." : "Invitation declined.",
    );
    if (result && action === "accept") {
      setWorkspaceId(result.workspace_id);
      setSnapshot(null);
      setOlder([]);
      setDraft("");
      setTab("conversation");
    }
  }
  async function confirm() {
    const selected = confirmation;
    const result = await act(async () => {
      await selected.action();
      return true;
    }, "Change saved.");
    if (result) {
      setSnapshot(null);
      setConfirmation(null);
    }
  }
  function chooseWorkspace(id) {
    setWorkspaceId(id);
    setSnapshot(null);
    setOlder([]);
    setDraft("");
    setTab("conversation");
    setError("");
    setNotice("");
  }

  return (
    <div className="collab-app">
      <header className="collab-header">
        <div className="brand">
          Parallel <span>Project workspace</span>
        </div>
        <div className="header-actions">
          <span className="account-name">{user.name}</span>
          <ThemeToggle />
          <button disabled={busy} onClick={() => onLogout(false)}>
            Log out
          </button>
          <button
            disabled={busy}
            onClick={() =>
              setConfirmation({
                title: "Log out all sessions?",
                message:
                  "Every browser session for this account will be revoked, including this one.",
                action: async () => {
                  if (!(await onLogout(true)))
                    throw new Error(
                      "Logout failed. Your sessions were not revoked.",
                    );
                },
              })
            }
          >
            Log out all sessions
          </button>
        </div>
      </header>
      <div className="collab-shell">
        <aside className="workspace-sidebar">
          <label>
            Workspace
            <select
              aria-label="Workspace"
              value={workspaceId}
              disabled={busy || !!confirmation}
              onChange={(event) => chooseWorkspace(event.target.value)}
            >
              {!workspaces.length && <option value="">No workspaces</option>}
              {workspaces.map((workspace) => (
                <option key={workspace.id} value={workspace.id}>
                  {workspace.name}
                </option>
              ))}
            </select>
          </label>
          <form onSubmit={createWorkspace} className="create-workspace">
            <label>
              New workspace
              <input
                required
                maxLength={120}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <button disabled={busy || !name.trim()}>Create workspace</button>
          </form>
          <button
            className={`inbox-button ${tab === "inbox" ? "active" : ""}`}
            onClick={() => {
              setTab("inbox");
              setNotice("");
              setError("");
            }}
          >
            Invitations ({invitations.length})
          </button>
          <p className="sidebar-note">
            Shared project state. Explicit access. Work you can return to.
          </p>
        </aside>
        <main className="workspace-main">
          {error && !confirmation && (
            <p role="alert" className="feedback error">
              {error}
            </p>
          )}
          {notice && (
            <p role="status" className="feedback">
              {notice}
            </p>
          )}
          {tab === "inbox" ? (
            <InvitationInbox
              invitations={invitations}
              busy={busy}
              onRespond={respond}
            />
          ) : (
            <>
              <div className="workspace-heading">
                <div>
                  <p className="eyebrow">WORKSPACE</p>
                  <h1>
                    {view?.workspace.name ||
                      workspaces.find((row) => row.id === workspaceId)?.name ||
                      "Your projects"}
                  </h1>
                </div>
                {view && (
                  <span className="role-label">{view.workspace.role}</span>
                )}
              </div>
              <nav className="workspace-nav" aria-label="Workspace sections">
                {[
                  ["overview", "Overview"],
                  ["conversation", "Conversation"],
                  ["tasks", "Tasks"],
                  ["decisions", "Decisions"],
                  ["intelligence", "Intelligence"],
                  ["documents", "Documents"],
                  ["connections", "Connections"],
                  ["answers", "Ask workspace"],
                  ["agents", "Agents & approvals"],
                  ["members", "Members"],
                  ["activity", "Activity"],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    aria-pressed={tab === value}
                    disabled={busy}
                    className={tab === value ? "active" : ""}
                    onClick={() => {
                      setTab(value);
                      setNotice("");
                      setError("");
                    }}
                  >
                    {label}
                  </button>
                ))}
              </nav>
              {!view ? (
                <div role="status" className="empty-state">
                  {workspaces.length
                    ? "Loading workspace…"
                    : "Create a workspace or accept an invitation to get started."}
                </div>
              ) : (
                <>
                  {tab === "conversation" && (
                    <section
                      className="conversation surface"
                      aria-label="Workspace conversation"
                    >
                      <div className="section-heading">
                        <div>
                          <h2>Conversation</h2>
                          <p>Visible only to current workspace members.</p>
                        </div>
                      </div>
                      <div className="conversation-log" aria-live="polite">
                        {view.messages.length > 0 && (
                          <button disabled={busy} onClick={loadOlder}>
                            Load older messages
                          </button>
                        )}
                        {!view.messages.length && (
                          <p className="empty-state">
                            No messages yet. Start the conversation.
                          </p>
                        )}
                        {[...older, ...view.messages]
                          .filter(
                            (message, index, rows) =>
                              rows.findIndex((row) => row.id === message.id) ===
                              index,
                          )
                          .map((message) => (
                            <article
                              className="conversation-entry"
                              key={message.id}
                            >
                              <small>
                                {message.sender_name} ·{" "}
                                {new Date(message.created_at).toLocaleString()}
                              </small>
                              <ChatBubble
                                sender={message.role === "user" ? "user" : "ai"}
                                text={message.content}
                              />
                            </article>
                          ))}
                      </div>
                      <form className="message-form" onSubmit={send}>
                        <label>
                          Message
                          <input
                            value={draft}
                            maxLength={16000}
                            onChange={(event) => setDraft(event.target.value)}
                            disabled={busy}
                          />
                        </label>
                        <button
                          className="primary"
                          disabled={busy || !draft.trim()}
                        >
                          Send
                        </button>
                      </form>
                      <button
                        className="ai-button"
                        disabled={
                          busy ||
                          !view.messages.some(
                            (message) => message.role === "user",
                          )
                        }
                        onClick={askAgent}
                      >
                        Ask AI about recent conversation
                      </button>
                      <small className="muted">
                        Optional AI requires a configured provider. Human
                        messages are saved independently.
                      </small>
                    </section>
                  )}
                  {tab === "tasks" && (
                    <TaskBoard
                      key={workspaceId}
                      workspaceId={workspaceId}
                      members={view.members}
                      refresh={refresh}
                      onConfirm={setConfirmation}
                      onAccessLost={lostAccess}
                    />
                  )}
                  {tab === "decisions" && (
                    <DecisionsPanel
                      key={workspaceId}
                      workspaceId={workspaceId}
                      onAccessLost={lostAccess}
                    />
                  )}
                  {tab === "overview" && (
                    <OverviewPanel
                      key={workspaceId}
                      workspaceId={workspaceId}
                      onAccessLost={lostAccess}
                      onNavigate={setTab}
                    />
                  )}
                  {tab === "answers" && (
                    <AnswersPanel
                      key={workspaceId}
                      workspaceId={workspaceId}
                      onAccessLost={lostAccess}
                    />
                  )}
                  {tab === "connections" && (
                    <ConnectionsPanel
                      key={workspaceId}
                      workspaceId={workspaceId}
                      owner={view.workspace.role === "owner"}
                      onAccessLost={lostAccess}
                      onConfirm={setConfirmation}
                    />
                  )}
                  {tab === "documents" && (
                    <DocumentsPanel
                      key={workspaceId}
                      workspaceId={workspaceId}
                      onAccessLost={lostAccess}
                      onConfirm={setConfirmation}
                    />
                  )}
                  {tab === "intelligence" && (
                    <IntelligencePanel
                      key={workspaceId}
                      workspaceId={workspaceId}
                      onAccessLost={lostAccess}
                      onAgents={() => setTab("agents")}
                    />
                  )}
                  {tab === "agents" && (
                    <AgentsPanel
                      key={workspaceId}
                      workspaceId={workspaceId}
                      user={user}
                      workspace={view.workspace}
                      onAccessLost={lostAccess}
                    />
                  )}
                  {tab === "members" && (
                    <WorkspaceMembers
                      key={workspaceId}
                      workspace={view.workspace}
                      members={view.members}
                      invitations={view.sent}
                      user={user}
                      onRefresh={bump}
                      onConfirm={setConfirmation}
                      onAccessLost={lostAccess}
                    />
                  )}
                  {tab === "activity" && (
                    <section aria-label="Workspace activity">
                      <div className="section-heading">
                        <div>
                          <h2>Activity</h2>
                          <p>
                            Persisted changes, attributed to the person who made
                            them.
                          </p>
                        </div>
                      </div>
                      {!view.activity.length ? (
                        <p className="empty-state">No activity yet.</p>
                      ) : (
                        <ol className="activity-timeline">
                          {view.activity.map((item) => (
                            <li key={item.id}>
                              <strong>{item.user_name}</strong>
                              <p>{item.summary}</p>
                              <small>
                                {new Date(item.created_at).toLocaleString()}
                              </small>
                            </li>
                          ))}
                        </ol>
                      )}
                    </section>
                  )}
                </>
              )}
            </>
          )}
        </main>
      </div>
      <ConfirmDialog
        confirmation={confirmation}
        busy={busy}
        error={error}
        onCancel={() => setConfirmation(null)}
        onConfirm={confirm}
      />
    </div>
  );
}
