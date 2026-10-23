import { useState } from 'react';
import { motion as Motion } from 'framer-motion';
import { api } from '../api';
import './Auth.css';

export default function Login({ goSignup, goDashboard }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(false);
  async function submit(event) {
    event.preventDefault(); setLoading(true); setStatus('');
    try {
      await api('/auth/login', { method: 'POST', body: { email, password } });
      await goDashboard();
    } catch (err) { setStatus(err.message); }
    finally { setLoading(false); }
  }
  return <div className="auth-container"><Motion.div className="auth-card glass" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
    <h2 className="auth-title">Welcome Back</h2><p className="auth-subtitle">Sign in to your workspace</p>
    <form onSubmit={submit}>
      <label>Email<input className="auth-input" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
      <label>Password<input className="auth-input" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
      {status && <p role="alert" className="auth-status">{status}</p>}
      <button className="auth-button" disabled={loading}>{loading ? 'Signing in…' : 'Sign In'}</button>
    </form>
    <p className="auth-footer">New here? <button type="button" onClick={goSignup}>Create an account</button></p>
  </Motion.div></div>;
}
