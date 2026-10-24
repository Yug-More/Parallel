import { useState } from "react";
import { api } from "../api";

export default function AccountRecovery({ verification = false }) {
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  async function perform(path, body, success) {
    setBusy(true);
    setNotice("");
    try {
      const result = await api(path, { method: "POST", body });
      setNotice(success || result.message);
    } catch (error) {
      setNotice(error.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="account-recovery">
      <summary>
        {verification ? "Verify account email" : "Recover your account"}
      </summary>
      <p>
        Delivery requires an operator-configured channel. Local development uses
        a private outbox and sends no email. Tokens expire after 30 minutes and
        work once.
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          perform(
            verification
              ? "/auth/verification/request"
              : "/auth/recovery/request",
            verification ? undefined : { email },
          );
        }}
      >
        {!verification && (
          <label>
            Recovery email
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
        )}
        <button disabled={busy}>
          Request {verification ? "verification" : "recovery"} instructions
        </button>
      </form>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          await perform(
            verification
              ? "/auth/verification/complete"
              : "/auth/recovery/complete",
            { token, ...(verification ? {} : { password }) },
            verification
              ? "Verification completed. Local outbox delivery is a development simulation."
              : "Password updated. All sessions were revoked. Sign in with your new password.",
          );
          setToken("");
          setPassword("");
        }}
      >
        <label>
          {verification ? "Verification" : "Recovery"} token
          <input
            autoComplete="off"
            type="password"
            required
            minLength={40}
            maxLength={100}
            value={token}
            onChange={(event) => setToken(event.target.value)}
          />
        </label>
        {!verification && (
          <label>
            New password
            <input
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              maxLength={72}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
        )}
        <button disabled={busy}>
          Complete {verification ? "verification" : "password reset"}
        </button>
      </form>
      {notice && <p role="status">{notice}</p>}
    </details>
  );
}
