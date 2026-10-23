import { useEffect, useState } from "react";
import { ThemeProvider } from "./context/ThemeContext";
import Landing from "./pages/Landing";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import { api } from "./api";

export default function App() {
  const [page, setPage] = useState("landing");
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    api("/me", { signal: controller.signal })
      .then(setUser)
      .catch(() => {})
      .finally(() => {
        if (!controller.signal.aborted) setChecking(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const expired = () => {
      setUser(null);
      setPage("login");
      setError("Your session expired or was revoked. Sign in again.");
    };
    window.addEventListener("parallel:session-expired", expired);
    return () =>
      window.removeEventListener("parallel:session-expired", expired);
  }, []);

  async function signedIn() {
    try {
      setUser(await api("/me"));
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }

  async function logout(all = false) {
    try {
      await api(all ? "/auth/logout-all" : "/auth/logout", { method: "POST" });
      setUser(null);
      setPage("login");
      setError("");
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    }
  }

  return (
    <ThemeProvider>
      {error && <p role="alert">{error}</p>}
      {checking ? (
        <p role="status">Restoring your session…</p>
      ) : user ? (
        <Dashboard user={user} onLogout={logout} />
      ) : (
        <>
          {page === "landing" && <Landing goLogin={() => setPage("login")} />}
          {page === "login" && (
            <Login goDashboard={signedIn} goSignup={() => setPage("signup")} />
          )}
          {page === "signup" && (
            <Signup goLogin={() => setPage("login")} goDashboard={signedIn} />
          )}
        </>
      )}
    </ThemeProvider>
  );
}
