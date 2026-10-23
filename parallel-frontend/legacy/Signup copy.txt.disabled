import { useState } from "react";
import { motion } from "framer-motion";
import "./Auth.css";

export default function Signup({ goLogin, goDashboard }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);

  const apiBase = import.meta.env.VITE_API_BASE || "http://localhost:8000";
  const roleOptions =
    (import.meta.env.VITE_ROLE_OPTIONS || "Product,Engineering,Design,Data,Ops,Other")
      .split(",")
      .map((r) => r.trim())
      .filter(Boolean);

  const submit = async () => {
    if (!name || !email || !password || !role) {
      setStatus("Fill all fields (including role).");
      return;
    }
    setLoading(true);
    setStatus("");
    try {
      console.log("Signup: sending request", { apiBase, email });
      const res = await fetch(`${apiBase}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ name, email, password, role }),
      });
      if (!res.ok) {
        const text = await res.text();
        console.error("Signup failed", res.status, text);
        setStatus(`Signup failed (${res.status}).`);
      } else {
        setStatus("Account created.");
        goDashboard();
      }
    } catch (err) {
      console.error("Signup error", err);
      setStatus("Signup failed. See console.");
    } finally {
      setLoading(false);
    }
  };

  const onKey = (e) => {
    if (e.key === "Enter") submit();
  };

  return (
    <div className="auth-container">
      <motion.div
        className="auth-card glass"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h2 className="auth-title">Create Account</h2>
        <p className="auth-subtitle">Start your workspace</p>

        <input
          className="auth-input"
          placeholder="Full Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={onKey}
        />
        <select
          className="auth-input"
          value={role}
          onChange={(e) => setRole(e.target.value)}
        >
          <option value="">Select your role</option>
          {roleOptions.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
        <input
          className="auth-input"
          placeholder="Email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onKeyDown={onKey}
        />
        <input
          className="auth-input"
          placeholder="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={onKey}
        />

        {status && <div className="auth-status">{status}</div>}

        <button className="auth-button" onClick={submit} disabled={loading}>
          {loading ? "Signing up..." : "Sign Up"}
        </button>

        <p className="auth-footer">
          Already have an account? <span onClick={goLogin}>Sign in</span>
        </p>
      </motion.div>
    </div>
  );
}
