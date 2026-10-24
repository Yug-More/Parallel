import { useState } from "react";
import { api } from "../api";
import { useWorkspaceQuery } from "./projectHooks";

export default function RetentionPanel({
  workspaceId,
  onAccessLost,
  onClosed,
}) {
  const [scope, setScope] = useState("derived");
  const [target, setTarget] = useState("");
  const [plan, setPlan] = useState(null);
  const [confirmation, setConfirmation] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const targets = useWorkspaceQuery(
    scope === "document"
      ? `/workspaces/${workspaceId}/documents`
      : scope === "connection"
        ? `/workspaces/${workspaceId}/connections`
        : null,
    workspaceId,
    onAccessLost,
  );
  async function act(execute = false) {
    setBusy(true);
    setNotice("");
    try {
      if (execute) {
        const { scope, target_id, expected_revision, expires, plan_hash } =
          plan;
        const result = await api(
          `/workspaces/${workspaceId}/retention/execute`,
          {
            method: "POST",
            body: {
              scope,
              target_id,
              expected_revision,
              expires,
              plan_hash,
              confirmation,
            },
          },
        );
        setNotice(
          `Content erasure completed. Retained audit receipt: ${result.id}.`,
        );
        setPlan(null);
        setConfirmation("");
        if (scope === "close") onClosed?.(result);
      } else {
        setPlan(
          await api(`/workspaces/${workspaceId}/retention/preview`, {
            method: "POST",
            body: {
              scope,
              target_id: ["document", "connection"].includes(scope)
                ? target
                : null,
            },
          }),
        );
      }
    } catch (error) {
      setNotice(error.message);
      setPlan(null);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="surface">
      <summary>Retention and workspace closure · owner only</summary>
      <p>
        Content erasure is irreversible. Review the scope and retained
        exceptions before confirming. Backups and external provider copies
        require separate operator handling.
      </p>
      <label>
        Retention scope
        <select
          value={scope}
          onChange={(event) => {
            setScope(event.target.value);
            setTarget("");
            setPlan(null);
          }}
        >
          <option value="derived">Erase all derived workspace content</option>
          <option value="document">
            Erase one document and all derived workspace content
          </option>
          <option value="connection">
            Erase one imported repository cache and all derived workspace
            content
          </option>
          <option value="close">
            Close workspace and erase document/import/derived content
          </option>
        </select>
      </label>
      {["document", "connection"].includes(scope) && (
        <label>
          Retention target
          <select
            value={target}
            onChange={(event) => {
              setTarget(event.target.value);
              setPlan(null);
            }}
          >
            <option value="">Select a source</option>
            {targets.data?.items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title || item.repository} · {item.id}
              </option>
            ))}
          </select>
        </label>
      )}
      <button
        disabled={
          busy || (["document", "connection"].includes(scope) && !target)
        }
        onClick={() => act()}
      >
        Preview erasure
      </button>
      {plan && (
        <article>
          <h3>Review exact erasure scope</h3>
          <p>{plan.effects}</p>
          <p>Retained exceptions: {plan.exceptions}</p>
          <ul>
            {Object.entries(plan.workspace_counts).map(([name, count]) => (
              <li key={name}>
                {name}: {count} workspace records (source erasure applies to the
                selected target)
              </li>
            ))}
          </ul>
          <p>
            Review expires in five minutes. Changes to the workspace require a
            new review.
          </p>
          <label>
            Type ERASE REVIEWED CONTENT
            <input
              value={confirmation}
              autoComplete="off"
              onChange={(event) => setConfirmation(event.target.value)}
            />
          </label>
          <button
            disabled={busy || confirmation !== "ERASE REVIEWED CONTENT"}
            onClick={() => act(true)}
          >
            Erase reviewed content
          </button>
        </article>
      )}
      {notice && <p role="status">{notice}</p>}
    </details>
  );
}
