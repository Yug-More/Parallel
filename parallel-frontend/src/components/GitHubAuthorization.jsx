import { useState } from "react";
import { api } from "../api";
import { useWorkspaceQuery, useProjectAction } from "./projectHooks";

export default function GitHubAuthorization({
  workspaceId,
  onAccessLost,
  onConnected,
}) {
  const base = `/workspaces/${workspaceId}/github-authorizations`;
  const [repository, setRepository] = useState("");
  const [installation, setInstallation] = useState("");
  const [started, setStarted] = useState(null);
  const [lastState, setLastState] = useState("");
  const query = useWorkspaceQuery(base, workspaceId, onAccessLost, 5000);
  const actions = useProjectAction(workspaceId, onAccessLost);
  const pending = started || query.data?.items[0];
  return (
    <section className="surface" aria-label="Private GitHub authorization">
      <h3>Connect a selected private repository</h3>
      <p>
        Install the operator-configured read-only GitHub App on selected
        repositories first. Device authorization grants time-limited, read-only
        access to this workspace. Tokens stay encrypted on the server.
      </p>
      {(actions.error || query.error) && (
        <p role="alert">{actions.error || query.error}</p>
      )}
      {lastState && <p role="status">{lastState}</p>}
      {actions.notice && <p role="status">{actions.notice}</p>}
      <form
        className="project-form"
        onSubmit={async (e) => {
          e.preventDefault();
          const value = await actions.act(
            () =>
              api(base, {
                method: "POST",
                body: { repository, installation_id: Number(installation) },
              }),
            "Authorization started. Complete the code in GitHub, then check authorization.",
          );
          if (value) setStarted(value);
        }}
      >
        <label>
          Selected private repository
          <input
            required
            maxLength={150}
            placeholder="owner/repository"
            value={repository}
            onChange={(e) => setRepository(e.target.value)}
          />
        </label>
        <label>
          GitHub installation ID
          <input
            required
            type="number"
            min="1"
            step="1"
            value={installation}
            onChange={(e) => setInstallation(e.target.value)}
          />
        </label>
        <button disabled={actions.busy}>Start GitHub authorization</button>
      </form>
      {pending && (
        <div>
          <p>
            Enter code <strong>{pending.user_code}</strong> at{" "}
            <a
              href="https://github.com/login/device"
              target="_blank"
              rel="noreferrer"
            >
              GitHub device authorization
            </a>
            . Only enter this code if you requested this connection.
          </p>
          <p>
            Wait at least {pending.interval} seconds between checks.
            Authorization expires after 15 minutes or earlier.
          </p>
          <button
            disabled={actions.busy}
            onClick={async () => {
              const value = await actions.act(() =>
                api(`${base}/${pending.id}/complete`, { method: "POST" }),
              );
              if (value)
                setLastState(
                  `Authorization ${value.state}${value.error_code ? `: ${value.error_code.replaceAll("_", " ")}` : ""}.`,
                );
              if (value?.state === "completed") {
                setStarted(null);
                query.reload();
                onConnected();
              } else if (value && value.state !== "pending") {
                setStarted(null);
                query.reload();
              }
            }}
          >
            Check GitHub authorization
          </button>
        </div>
      )}
    </section>
  );
}
