import { useState } from "react";
import ThemeToggle from "../components/ThemeToggle";
import { api } from "../api";
import "./Auth.css";
import AccountRecovery from "../components/AccountRecovery";

export default function Login({ goSignup, goDashboard }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setStatus("");
    try {
      await api("/auth/login", { method: "POST", body: { email, password } });
      await goDashboard();
    } catch (err) {
      setStatus(err.message);
    } finally {
      setLoading(false);
    }
  }
  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="auth-header">
          <strong>Parallel</strong>
          <ThemeToggle />
        </div>
        <h1 className="auth-title">Welcome Back</h1>
        <p className="auth-subtitle">Sign in to your workspace</p>
        <form onSubmit={submit}>
          <label>
            Email
            <input
              className="auth-input"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <label>
            Password
            <input
              className="auth-input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          {status && (
            <p role="alert" className="auth-status">
              {status}
            </p>
          )}
          <button className="auth-button" disabled={loading}>
            {loading ? "Signing in…" : "Sign In"}
          </button>
        </form>
        <AccountRecovery />
        <p className="auth-footer">
          New here?{" "}
          <button type="button" onClick={goSignup}>
            Create an account
          </button>
        </p>
      </div>
    </div>
  );
}
