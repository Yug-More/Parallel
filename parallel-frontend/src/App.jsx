import { useEffect, useState } from 'react';
import { ThemeProvider } from './context/ThemeContext';
import Landing from './pages/Landing';
import Dashboard from './pages/Dashboard';
import Login from './pages/Login';
import Signup from './pages/Signup';
import { api } from './api';

export default function App() {
  const [page, setPage] = useState('landing');
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    api('/me', { signal: controller.signal }).then(setUser).catch(() => {}).finally(() => {
      if (!controller.signal.aborted) setChecking(false);
    });
    return () => controller.abort();
  }, []);

  async function signedIn() {
    try { setUser(await api('/me')); setError(''); }
    catch (err) { setError(err.message); }
  }

  async function logout() {
    try { await api('/auth/logout', { method: 'POST' }); setUser(null); setPage('login'); setError(''); }
    catch (err) { setError(err.message); }
  }

  return <ThemeProvider>
    {error && <p role="alert">{error}</p>}
    {checking ? <p role="status">Restoring your session…</p> : user ? <Dashboard user={user} onLogout={logout} /> : <>
      {page === 'landing' && <Landing goLogin={() => setPage('login')} />}
      {page === 'login' && <Login goDashboard={signedIn} goSignup={() => setPage('signup')} />}
      {page === 'signup' && <Signup goLogin={() => setPage('login')} goDashboard={signedIn} />}
    </>}
  </ThemeProvider>;
}
