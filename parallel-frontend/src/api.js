export const apiBase = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export async function api(path, { body, ...options } = {}) {
  const response = await fetch(`${apiBase}${path}`, {
    credentials: "include",
    ...options,
    ...(body !== undefined
      ? {
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : {}),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail =
      typeof data.detail === "string"
        ? data.detail
        : "Please check the entered values.";
    const error = new Error(detail);
    error.status = response.status;
    if (response.status === 401 && !["/auth/login", "/me"].includes(path))
      window.dispatchEvent(new Event("parallel:session-expired"));
    throw error;
  }
  return data;
}
