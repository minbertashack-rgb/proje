import { appConfig } from '../config/appConfig';
import type { AuthSession } from '../types/api';

function canUseStorage() {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

export function getStoredAuthSession(): AuthSession | null {
  if (!canUseStorage()) {
    return null;
  }

  const rawValue = window.localStorage.getItem(appConfig.authStorageKey);
  if (!rawValue) {
    return null;
  }

  try {
    const parsed = JSON.parse(rawValue) as Partial<AuthSession>;
    if (!parsed.accessToken || typeof parsed.accessToken !== 'string') {
      window.localStorage.removeItem(appConfig.authStorageKey);
      return null;
    }

    return {
      accessToken: parsed.accessToken,
      refreshToken: typeof parsed.refreshToken === 'string' ? parsed.refreshToken : undefined,
      username: typeof parsed.username === 'string' ? parsed.username : undefined,
    };
  } catch {
    window.localStorage.removeItem(appConfig.authStorageKey);
    return null;
  }
}

export function setStoredAuthSession(session: AuthSession | null) {
  if (!canUseStorage()) {
    return;
  }

  if (!session) {
    window.localStorage.removeItem(appConfig.authStorageKey);
    return;
  }

  window.localStorage.setItem(appConfig.authStorageKey, JSON.stringify(session));
}

export function getStoredAccessToken() {
  return getStoredAuthSession()?.accessToken ?? null;
}

export function clearStoredAuthSession() {
  if (!canUseStorage()) {
    return;
  }

  window.localStorage.removeItem(appConfig.authStorageKey);
}
