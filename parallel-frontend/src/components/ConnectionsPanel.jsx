import GitHubAuthorization from "./GitHubAuthorization";
import { useState } from "react";
import { api } from "../api";
import { useProjectAction, useWorkspaceQuery } from "./projectHooks";

export default function ConnectionsPanel({
  workspaceId,
  owner,
  onAccessLost,
  onConfirm,
}) {
  const base = `/workspaces/${workspaceId}/connections`;
  const [repository, setRepository] = useState("");
  const query = useWorkspaceQuery(base, workspaceId, onAccessLost, 2000);
  const actions = useProjectAction(workspaceId, onAccessLost);
  async function connect(event) {
    event.preventDefault();
    if (
      await actions.act(
        () => api(base, { method: "POST", body: { repository } }),
        "Connection authorized. Read-only sync queued.",
      )
    ) {
      setRepository("");
      query.reload();
    }
  }
  return (
    <section className="project-section" aria-label="Connections">
      <div className="section-heading">
        <div>
          <h2>Connected repositories</h2>
          <p>
            Public GitHub metadata, 25 recent issues and 25 pull requests.
            Imported context stays distinct from native decisions and tasks.
          </p>
        </div>
      </div>
      {(actions.error || query.error) && (
        <p role="alert">{actions.error || query.error}</p>
      )}
      {actions.notice && <p role="status">{actions.notice}</p>}
      {!query.data && !query.error && <p role="status">Loading connections…</p>}
      {query.data && !query.data.enabled && (
        <p className="feedback">
          The public GitHub connector is disabled. The server operator can
          enable GITHUB_CONNECTOR_ENABLED. No credentials are needed for public
          repositories.
        </p>
      )}
      {owner && query.data?.enabled && (
        <form className="surface project-form" onSubmit={connect}>
          <label>
            GitHub repository
            <input
              required
              maxLength={200}
              placeholder="owner/repository"
              value={repository}
              onChange={(e) => setRepository(e.target.value)}
            />
          </label>
          <p>
            Authorize read-only public imports into this workspace. No GitHub
            writes or account tokens. Private access uses the separate GitHub
            App flow below.
          </p>
          <button disabled={actions.busy}>Connect public repository</button>
        </form>
      )}
      {owner && query.data?.private_enabled && (
        <GitHubAuthorization
          workspaceId={workspaceId}
          onAccessLost={onAccessLost}
          onConnected={query.reload}
        />
      )}
      {owner && query.data && !query.data.private_enabled && (
        <p>
          Private access requires operator-configured GitHub App authorization.
          It is disabled on this server.
        </p>
      )}
      {query.data?.items.length === 0 && <p>No repositories connected.</p>}
      {query.data?.items.map((connection) => (
        <article className="surface" key={connection.id}>
          <h3>{connection.repository}</h3>
          <p>
            {connection.active
              ? connection.auth_mode === "github_app_user"
                ? "Read-only selected GitHub App connection · revalidated every sync"
                : "Read-only public connection"
              : "Revoked; imported sources unavailable"}
          </p>
          <ul>
            {connection.syncs.map((sync) => (
              <li key={sync.id}>
                {sync.state} · attempt {sync.attempt}/3 · {sync.record_count}{" "}
                imported records{sync.error_code ? ` · ${sync.error_code}` : ""}
              </li>
            ))}
          </ul>
          {owner && connection.active && (
            <div className="button-row">
              {connection.auth_mode === "github_app_user" && (
                <button
                  disabled={actions.busy}
                  onClick={async () => {
                    await actions.act(
                      () =>
                        api(`${base}/${connection.id}/verify`, {
                          method: "POST",
                          body: { version: connection.version },
                        }),
                      "Private permissions revalidated. Model transmission is available for 30 seconds.",
                    );
                    query.reload();
                  }}
                >
                  Revalidate private access
                </button>
              )}

              <button
                disabled={actions.busy || !query.data.enabled}
                onClick={async () => {
                  if (
                    await actions.act(
                      () =>
                        api(`${base}/${connection.id}/sync`, {
                          method: "POST",
                          body: { version: connection.version },
                        }),
                      "Sync queued. Five-minute minimum between syncs.",
                    )
                  )
                    query.reload();
                }}
              >
                Sync repository
              </button>
              <button
                disabled={actions.busy}
                onClick={() =>
                  onConfirm({
                    title: "Revoke repository connection?",
                    message:
                      "Queued syncs will be cancelled and all imported sources will become unavailable. Existing native project records stay in the workspace.",
                    action: async () => {
                      await api(`${base}/${connection.id}/revoke`, {
                        method: "POST",
                        body: { version: connection.version },
                      });
                      query.reload();
                    },
                  })
                }
              >
                Revoke connection
              </button>
            </div>
          )}
        </article>
      ))}
    </section>
  );
}
