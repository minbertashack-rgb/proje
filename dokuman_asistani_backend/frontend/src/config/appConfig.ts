const fallbackApiBaseUrl = 'http://127.0.0.1:8001';

export const appConfig = {
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL || fallbackApiBaseUrl).replace(/\/+$/, ''),
  authStorageKey: 'docverse.auth.session',
  requestTimeoutMs: 20000,
};
