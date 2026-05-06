import { useEffect, useMemo, useState } from 'react';
import { AuthPage } from './pages/AuthPage';
import { DocVerseDashboardPage } from './pages/DocVerseDashboardPage';

function App() {
  const [hash, setHash] = useState(() => window.location.hash);
  const route = useMemo(() => hash.replace(/^#/, '') || '/', [hash]);

  useEffect(() => {
    const handleHashChange = () => setHash(window.location.hash);
    window.addEventListener('hashchange', handleHashChange);

    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  if (route === '/auth/login') {
    return <AuthPage initialMode="login" />;
  }

  if (route === '/auth/register') {
    return <AuthPage initialMode="register" />;
  }

  return <DocVerseDashboardPage />;
}

export default App;
