import { useEffect, useState } from 'react';
import type { AuthSession } from '../types/api';
import { getStoredAuthSession, setStoredAuthSession } from '../utils/authStorage';
import { subscribeToUnauthorized } from '../utils/authEvents';

export function useAuthSession() {
  const [session, setSessionState] = useState<AuthSession | null>(null);
  const [isHydrated, setIsHydrated] = useState(false);
  const [authNotice, setAuthNotice] = useState<string | null>(null);

  useEffect(() => {
    setSessionState(getStoredAuthSession());
    setIsHydrated(true);
  }, []);

  useEffect(() => {
    const unsubscribe = subscribeToUnauthorized((message) => {
      setSessionState(null);
      setStoredAuthSession(null);
      setAuthNotice(message);
    });

    return unsubscribe;
  }, []);

  const setSession = (nextSession: AuthSession | null) => {
    setSessionState(nextSession);
    setStoredAuthSession(nextSession);
    if (nextSession) {
      setAuthNotice(null);
    }
  };

  return {
    session,
    setSession,
    clearSession: () => setSession(null),
    isAuthenticated: Boolean(session?.accessToken),
    isHydrated,
    authNotice,
    clearAuthNotice: () => setAuthNotice(null),
  };
}
