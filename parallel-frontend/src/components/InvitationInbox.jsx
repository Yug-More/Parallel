export default function InvitationInbox({ invitations, busy, onRespond }) {
  return (
    <section aria-label="Your invitations">
      <div className="section-heading">
        <div>
          <h2>Your invitations</h2>
          <p>
            Accept to join a project. Invitations are delivered here, without
            email.
          </p>
        </div>
      </div>
      {!invitations.length ? (
        <div className="empty-state">
          No pending invitations. Ask a workspace owner to invite your
          registered email.
        </div>
      ) : (
        invitations.map((invitation) => (
          <article className="invitation-row surface" key={invitation.id}>
            <div>
              <h3>{invitation.workspace_name}</h3>
              <p>Invited by {invitation.inviter_name}</p>
              <small>
                Expires {new Date(invitation.expires_at).toLocaleString()}
              </small>
            </div>
            <div className="button-row">
              <button
                disabled={busy}
                onClick={() => onRespond(invitation, "decline")}
              >
                Decline
              </button>
              <button
                className="primary"
                disabled={busy}
                onClick={() => onRespond(invitation, "accept")}
              >
                Accept invitation
              </button>
            </div>
          </article>
        ))
      )}
    </section>
  );
}
