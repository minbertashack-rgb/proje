import type { AuthSession, LoginCredentials, RegisterPayload } from '../types/api';
import { apiRequest, ApiError } from './client';
import { asArray, asRecord, isLikelyHtml, pickString, unwrapRecord } from './normalize';

function normalizeSession(raw: unknown, username?: string): AuthSession {
  const record = unwrapRecord(raw, ['data', 'payload', 'result', 'results', 'user', 'session']);
  const accessToken = pickString(record, ['access', 'access_token', 'token']);

  if (!accessToken) {
    throw new ApiError('Giriş yanıtında access token bulunamadı.', 500, raw);
  }

  return {
    accessToken,
    refreshToken: pickString(record, ['refresh', 'refresh_token']),
    username: pickString(record, ['username', 'user']) ?? username,
  };
}

function payloadIncludesUsernameConflict(payload: unknown) {
  const record = asRecord(payload);
  const usernameValue =
    record?.username ??
    record?.kullanici_adi ??
    record?.user ??
    record?.errors;

  const candidates = [
    typeof usernameValue === 'string' ? usernameValue : '',
    ...asArray(usernameValue).filter((item): item is string => typeof item === 'string'),
  ]
    .join(' ')
    .toLowerCase();

  return (
    candidates.includes('already') ||
    candidates.includes('exists') ||
    candidates.includes('taken') ||
    candidates.includes('kullan') ||
    candidates.includes('mevcut') ||
    candidates.includes('benzersiz') ||
    candidates.includes('unique')
  );
}

function payloadLooksLikeHtml(payload: unknown) {
  if (typeof payload === 'string') {
    return isLikelyHtml(payload);
  }

  const record = asRecord(payload);
  if (!record) {
    return false;
  }

  const raw = record.raw;
  return typeof raw === 'string' && isLikelyHtml(raw);
}

function toFriendlyAuthError(error: unknown, intent: 'login' | 'register') {
  if (error instanceof ApiError) {
    if (payloadLooksLikeHtml(error.payload)) {
      return intent === 'register'
        ? 'Kayıt başarısız oldu. Sunucudan beklenmeyen yanıt geldi.'
        : 'Giriş yapılamadı. Sunucudan beklenmeyen yanıt geldi.';
    }

    if (intent === 'register') {
      if (error.status === 0) {
        return 'Bağlantı kurulamadı. Lütfen daha sonra tekrar deneyin.';
      }

      if (error.status === 400 && payloadIncludesUsernameConflict(error.payload)) {
        return 'Bu kullanıcı adı zaten kullanılıyor olabilir.';
      }

      if (error.status === 400) {
        return 'Girilen bilgiler doğrulanamadı.';
      }

      if (error.status >= 500) {
        return 'Kayıt başarısız oldu. Sunucu tarafında bir hata oluştu.';
      }
    }

    if (intent === 'login') {
      if (error.status === 0) {
        return 'Bağlantı kurulamadı. Lütfen daha sonra tekrar deneyin.';
      }

      if (error.status === 400 || error.status === 401) {
        return 'Kullanıcı adı veya şifre doğrulanamadı.';
      }

      if (error.status >= 500) {
        return 'Giriş yapılamadı. Sunucu tarafında bir hata oluştu.';
      }
    }

    return error.message;
  }

  return intent === 'register' ? 'Kayıt başarısız oldu.' : 'Giriş yapılamadı.';
}

export async function login(credentials: LoginCredentials) {
  try {
    const raw = await apiRequest<unknown>('/api/kimlik/token/', {
      method: 'POST',
      body: credentials,
      skipAuthHandling: true,
    });

    return normalizeSession(raw, credentials.username);
  } catch (error) {
    if (error instanceof ApiError) {
      throw new ApiError(toFriendlyAuthError(error, 'login'), error.status, error.payload);
    }

    throw error;
  }
}

export async function register(payload: RegisterPayload) {
  try {
    await apiRequest<unknown>('/api/kimlik/kayit/', {
      method: 'POST',
      body: payload,
      skipAuthHandling: true,
    });
  } catch (error) {
    if (error instanceof ApiError) {
      throw new ApiError(toFriendlyAuthError(error, 'register'), error.status, error.payload);
    }

    throw error;
  }
}
