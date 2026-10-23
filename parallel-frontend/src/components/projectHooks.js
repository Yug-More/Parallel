import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

export function useWorkspaceQuery(path, workspaceId, onAccessLost, poll = 0) {
  const [result, setResult] = useState({ path: null, data: null, error: "" });
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => setRevision((n) => n + 1), []);
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    let pending = false;
    async function update() {
      if (pending) return;
      pending = true;
      try {
        const data = await api(path, { signal: controller.signal });
        if (!controller.signal.aborted) setResult({ path, data, error: "" });
      } catch (error) {
        if (!controller.signal.aborted) {
          setResult({ path, data: null, error: error.message });
          if (error.status === 404 && error.message === "Workspace not found")
            onAccessLost(workspaceId);
        }
      } finally {
        pending = false;
      }
    }
    update();
    const timer = poll ? setInterval(update, poll) : null;
    return () => {
      controller.abort();
      if (timer) clearInterval(timer);
    };
  }, [path, workspaceId, onAccessLost, poll, revision]);
  return {
    data: result.path === path ? result.data : null,
    error: result.path === path ? result.error : "",
    reload,
  };
}

export function useProjectAction(workspaceId, onAccessLost) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  async function act(action, message) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const value = await action();
      setNotice(message || "Change saved.");
      return value;
    } catch (error) {
      setError(error.message);
      if (error.status === 404 && error.message === "Workspace not found")
        onAccessLost(workspaceId);
      return null;
    } finally {
      setBusy(false);
    }
  }
  return { act, busy, error, notice };
}
