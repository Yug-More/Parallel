import { useState } from "react";
import ThemeToggle from "../components/ThemeToggle";
import { api } from "../api";
import "./Auth.css";

export default function Signup({ goLogin, goDashboard }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setStatus("");
    try {
      await api("/auth/register", {
        method: "POST",
        body: { name, email, password },
      });
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
        <h1 className="auth-title">Create Account</h1>
        <p className="auth-subtitle">Start with a private workspace</p>
        <form onSubmit={submit}>
          <label>
            Full name
            <input
              className="auth-input"
              autoComplete="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={100}
              required
            />
          </label>
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
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              minLength={8}
              maxLength={72}
              required
            />
          </label>
          <p>Use at least 8 characters and at most 72 UTF-8 bytes.</p>
          {status && (
            <p role="alert" className="auth-status">
              {status}
            </p>
          )}
          <button className="auth-button" disabled={loading}>
            {loading ? "Creating…" : "Sign Up"}
          </button>
        </form>
        <p className="auth-footer">
          Already registered?{" "}
          <button type="button" onClick={goLogin}>
            Sign in
          </button>
        </p>
      </div>
    </div>
  );
}
