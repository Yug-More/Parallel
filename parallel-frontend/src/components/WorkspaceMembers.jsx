import { useState } from "react";
import { api } from "../api";

export default function WorkspaceMembers({
  workspace,
  members,
  invitations,
  user,
  onRefresh,
  onConfirm,
  onAccessLost,
}) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const base = `/workspaces/${workspace.id}`;
  const owner = workspace.role === "owner";
  async function invite(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api(`${base}/invitations`, { method: "POST", body: { email } });
      setEmail("");
      setNotice("In-app invitation created. No email was sent.");
      onRefresh();
    } catch (err) {
      setError(err.message);
      if (err.status === 404 && err.message === "Workspace not found")
        onAccessLost(workspace.id);
    } finally {
      setBusy(false);
    }
  }
  function remove(member) {
    onConfirm({
      title: "Remove workspace member?",
      message: `${member.name} will lose workspace access. Their tasks will be unassigned; existing work remains.`,
      action: () => api(`${base}/members/${member.id}`, { method: "DELETE" }),
    });
  }
  function transfer(member) {
    onConfirm({
      title: "Transfer workspace ownership?",
      message: `${member.name} will become owner. You will become a member and lose owner controls. Pending invitations will be revoked.`,
      action: () =>
        api(`${base}/transfer-ownership`, {
          method: "POST",
          body: { user_id: member.id },
        }),
    });
  }
  return (
    <section aria-label="Workspace members">
      <div className="section-heading">
        <div>
          <h2>Members</h2>
          <p>
            Owners manage access. All members can collaborate on messages and
            tasks.
          </p>
        </div>
        {!owner && (
          <button
            className="danger"
            onClick={() =>
              onConfirm({
                title: "Leave workspace?",
                message:
                  "You will lose workspace access. Your assigned tasks will be unassigned; existing work remains.",
                action: () => api(`${base}/leave`, { method: "POST" }),
              })
            }
          >
            Leave workspace
          </button>
        )}
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
      {owner && (
        <form className="invite-form surface" onSubmit={invite}>
          <label>
            Invite registered user by email
            <input
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              maxLength={254}
            />
          </label>
          <button className="primary" disabled={busy}>
            {busy ? "Inviting…" : "Invite collaborator"}
          </button>
          <small>
            Invitations appear in the recipient’s app, expire after 7 days, and
            grant access only after acceptance.
          </small>
        </form>
      )}
      <div className="member-list">
        {members.map((member) => (
          <div className="member-row" key={member.id}>
            <div className="avatar" aria-hidden="true">
              {member.name.slice(0, 1).toUpperCase()}
            </div>
            <div className="member-name">
              <strong>
                {member.name}
                {member.id === user.id ? " (you)" : ""}
              </strong>
              <small>{member.role}</small>
            </div>
            {owner && member.id !== user.id && (
              <div className="button-row">
                <button onClick={() => transfer(member)}>Make owner</button>
                <button className="danger" onClick={() => remove(member)}>
                  Remove
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
      {owner && (
        <>
          <h3>Invitation history</h3>
          {!invitations.length ? (
            <p className="empty-state">No invitations have been created.</p>
          ) : (
            invitations.map((invitation) => (
              <div className="invitation-row" key={invitation.id}>
                <div>
                  <strong>{invitation.recipient_name}</strong>
                  <p>
                    {invitation.status} · Expires{" "}
                    {new Date(invitation.expires_at).toLocaleDateString()}
                  </p>
                </div>
                {invitation.status === "pending" && (
                  <button
                    onClick={() =>
                      onConfirm({
                        title: "Revoke invitation?",
                        message: `${invitation.recipient_name} will no longer be able to accept this invitation.`,
                        action: () =>
                          api(`${base}/invitations/${invitation.id}/revoke`, {
                            method: "POST",
                          }),
                      })
                    }
                  >
                    Revoke
                  </button>
                )}
              </div>
            ))
          )}
        </>
      )}
    </section>
  );
}
