import { useEffect, useState } from 'react';
import ChatBubble from '../components/ChatBubble';
import ThemeToggle from '../components/ThemeToggle';
import { api } from '../api';
import './Dashboard.css';
import '../components/ChatPanel.css';

export default function Dashboard({ user, onLogout }) {
  const [workspaces, setWorkspaces] = useState([]);
  const [workspaceId, setWorkspaceId] = useState('');
  const [snapshot, setSnapshot] = useState({ id: '', messages: [], activity: [], members: [] });
  const [draft, setDraft] = useState('');
  const [workspaceName, setWorkspaceName] = useState('');
  const [memberEmail, setMemberEmail] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [older, setOlder] = useState([]);

  useEffect(() => {
    const controller = new AbortController();
    api('/workspaces', { signal: controller.signal }).then((rows) => {
      setWorkspaces(rows);
      setWorkspaceId((current) => current || rows[0]?.id || '');
    }).catch((err) => { if (err.name !== 'AbortError') setError(err.message); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!workspaceId) return;
    const controller = new AbortController();
    let pending = false;
    const update = async () => {
      if (pending) return;
      pending = true;
      try {
        const [messages, activity, members] = await Promise.all(
          ['messages', 'activity', 'members'].map((resource) => api(`/workspaces/${workspaceId}/${resource}`, { signal: controller.signal }))
        );
        if (!controller.signal.aborted) setSnapshot({ id: workspaceId, messages, activity, members });
      } catch (err) {
        if (err.name !== 'AbortError') setError(err.message);
      } finally { pending = false; }
    };
    update();
    const timer = setInterval(update, 3000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [workspaceId, refresh]);

  const current = workspaces.find((workspace) => workspace.id === workspaceId);
  const view = snapshot.id === workspaceId ? snapshot : null;

  async function createWorkspace(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const workspace = await api('/workspaces', { method: 'POST', body: { name: workspaceName } });
      setWorkspaces((rows) => [...rows, workspace]);
      setWorkspaceId(workspace.id); setWorkspaceName(''); setOlder([]); setDraft('');
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function addMember(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      await api(`/workspaces/${workspaceId}/members`, { method: 'POST', body: { email: memberEmail } });
      setMemberEmail(''); setRefresh((value) => value + 1);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function send(event) {
    event.preventDefault();
    if (!draft.trim() || !workspaceId || busy) return;
    setBusy(true); setError('');
    try {
      await api(`/workspaces/${workspaceId}/messages`, { method: 'POST', body: { content: draft } });
      setDraft(''); setRefresh((value) => value + 1);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function askAgent() {
    const source = [...(view?.messages || [])].reverse().find((message) => message.role === 'user');
    if (!source) return;
    setBusy(true); setError('');
    try {
      await api(`/workspaces/${workspaceId}/agent-replies`, { method: 'POST', body: { message_id: source.id } });
      setRefresh((value) => value + 1);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function loadOlder() {
    const first = older[0] || view?.messages[0];
    if (!first) return;
    setBusy(true);
    try {
      const rows = await api(`/workspaces/${workspaceId}/messages?before=${encodeURIComponent(first.id)}`);
      setOlder((previous) => [...rows, ...previous]);
      if (!rows.length) setError('You have reached the beginning of this conversation.');
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="dashboard-simple">
      <header className="dashboard-header">
        <strong>Parallel / {user.name}</strong>
        <div className="dashboard-actions"><ThemeToggle /><button disabled={busy} onClick={onLogout}>Log out</button></div>
      </header>
      <div className="workspace-toolbar">
        <label>Workspace <select aria-label="Workspace" value={workspaceId} disabled={busy} onChange={(event) => {
          setWorkspaceId(event.target.value); setOlder([]); setDraft(''); setMemberEmail(''); setError('');
        }}>{workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}</select></label>
        <form onSubmit={createWorkspace}><label>New workspace <input value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} required maxLength={120} /></label><button disabled={busy || !workspaceName.trim()}>Create</button></form>
      </div>
      {error && <p role="alert" className="workspace-error">{error}</p>}
      <div className="dashboard-panels">
        <section aria-label="Workspace conversation" className="chat-wrapper glass chat-panel">
          <h2>{current?.name || 'Loading workspaces…'}</h2>
          <p>Messages are shared with this workspace’s members. AI replies are optional.</p>
          <div className="chat-scroll" aria-live="polite">
            {!view ? <p>Loading conversation…</p> : <>
              {view.messages.length > 0 && <button disabled={busy} onClick={loadOlder}>Load older messages</button>}
              {!view.messages.length && <p>No messages yet. Start the conversation.</p>}
              {[...older, ...view.messages].filter((message, index, rows) => rows.findIndex((row) => row.id === message.id) === index).map((message) => (
                <div key={message.id}><small>{message.sender_name} · {new Date(message.created_at).toLocaleString()}</small><ChatBubble sender={message.role === 'user' ? 'user' : 'ai'} text={message.content} /></div>
              ))}
            </>}
          </div>
          <form className="input-container" onSubmit={send}>
            <label className="workspace-compose">Message<input className="chat-input" value={draft} onChange={(event) => setDraft(event.target.value)} maxLength={16000} disabled={busy || !view} /></label>
            <button className="chat-send" disabled={busy || !view || !draft.trim()}>Send</button>
          </form>
          <button className="workspace-ai" disabled={busy || !view?.messages.some((message) => message.role === 'user')} onClick={askAgent}>{busy ? 'Working…' : 'Ask AI about recent conversation'}</button>
        </section>
        <aside className="activity-panel glass">
          <h2>Members</h2>
          {view?.members.map((member) => <p key={member.id}>{member.name} · {member.role}</p>)}
          {current?.role === 'owner' && <form className="workspace-member-form" onSubmit={addMember}><label>Add an existing account by email<input type="email" value={memberEmail} onChange={(event) => setMemberEmail(event.target.value)} required /></label><button disabled={busy || !view}>Add member</button><small>Adding a member grants access to this workspace’s history.</small></form>}
          <h2>Activity</h2>
          {view && !view.activity.length && <p>No activity yet.</p>}
          {view?.activity.map((item) => <p key={item.id}>{item.user_name}: {item.summary}</p>)}
          <p className="workspace-limits">Tasks, decisions, invitations, voice, SMS and external actions are not available in this phase.</p>
        </aside>
      </div>
    </div>
  );
}
