import { appConfig } from '../config/appConfig';
import { getStoredAccessToken } from '../utils/authStorage';
import { emitUnauthorized } from '../utils/authEvents';
import { extractMessage } from './normalize';

export class ApiError extends Error {
  status: number;
  payload: unknown;
  errorCode?: string;

  constructor(message: string, status: number, payload: unknown, errorCode?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
    this.errorCode = errorCode;
  }
}

type ApiRequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: FormData | Record<string, unknown>;
  headers?: HeadersInit;
  token?: string | null;
  signal?: AbortSignal;
  timeoutMs?: number;
  skipAuthHandling?: boolean;
};

async function parseResponsePayload(response: Response) {
  if (response.status === 204) {
    return null;
  }

  const responseText = await response.text();
  if (!responseText) {
    return null;
  }

  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.includes('application/json')) {
    return responseText;
  }

  try {
    return JSON.parse(responseText) as unknown;
  } catch {
    return { detail: 'Sunucudan gelen JSON çözümlenemedi.', raw: responseText };
  }
}

const ERROR_CODE_MESSAGES: Record<string, string> = {
  unsupported_extension: 'Bu dosya türü desteklenmiyor.',
  blocked_extension: 'Bu dosya türü güvenlik nedeniyle yüklenemez.',
  parser_not_available: 'Bu dosya türü yüklenebilir ancak şu anda içerik çıkarma desteği yok.',
  archive_not_supported: 'Arşiv dosyaları için içerik çıkarma desteği henüz hazır değil.',
  archive_unsafe_path: 'Arşiv içinde güvenli olmayan dosya yolu tespit edildi.',
  archive_too_large: 'Arşiv dosyası çok büyük.',
  archive_too_many_files: 'Arşiv içinde çok fazla dosya var.',
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function getPayloadErrorCode(payload: unknown): string | undefined {
  const record = asRecord(payload);
  const errorCode = record?.error_code;
  return typeof errorCode === 'string' && errorCode.trim() ? errorCode.trim() : undefined;
}

export function getApiErrorCode(error: unknown) {
  if (error instanceof ApiError) {
    return error.errorCode ?? getPayloadErrorCode(error.payload);
  }
  return getPayloadErrorCode(error);
}

export function getErrorCodeMessage(errorCode: string | undefined) {
  return errorCode ? ERROR_CODE_MESSAGES[errorCode] : undefined;
}

function buildErrorMessage(status: number, payload: unknown) {
  const mappedMessage = getErrorCodeMessage(getPayloadErrorCode(payload));
  if (mappedMessage) {
    return mappedMessage;
  }

  const payloadMessage = extractMessage(payload);
  if (payloadMessage) {
    return payloadMessage;
  }

  if (status === 401) {
    return 'Oturum doğrulanamadı. Tekrar giriş yapmayı deneyin.';
  }

  if (status === 403) {
    return 'Bu işlem için yetkiniz yok.';
  }

  if (status >= 500) {
    return 'Sunucu tarafında bir hata oluştu.';
  }

  if (status === 0) {
    return 'Bağlantı kurulamadı. Lütfen daha sonra tekrar deneyin.';
  }

  return 'İstek tamamlanamadı.';
}

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}) {
  const headers = new Headers(options.headers);
  const token = options.token ?? getStoredAccessToken();

  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  let body: BodyInit | undefined;
  if (options.body instanceof FormData) {
    body = options.body;
  } else if (options.body) {
    headers.set('Content-Type', 'application/json');
    body = JSON.stringify(options.body);
  }

  const controller = new AbortController();
  let didTimeout = false;
  const timeoutId = window.setTimeout(() => {
    didTimeout = true;
    controller.abort();
  }, options.timeoutMs ?? appConfig.requestTimeoutMs);

  const abortSignal = controller.signal;
  const externalSignal = options.signal;
  const abortExternal = () => controller.abort();
  if (externalSignal) {
    if (externalSignal.aborted) {
      controller.abort();
    } else {
      externalSignal.addEventListener('abort', abortExternal, { once: true });
    }
  }

  let response: Response;
  try {
    response = await fetch(`${appConfig.apiBaseUrl}${path}`, {
      method: options.method ?? 'GET',
      headers,
      body,
      signal: abortSignal,
    });
  } catch {
    if (externalSignal) {
      externalSignal.removeEventListener('abort', abortExternal);
    }
    window.clearTimeout(timeoutId);

    if (didTimeout) {
      throw new ApiError('İstek zaman aşımına uğradı. Lütfen daha sonra tekrar deneyin.', 0, null);
    }

    throw new ApiError('Ağ bağlantısı kurulamadı. Lütfen daha sonra tekrar deneyin.', 0, null);
  }

  if (externalSignal) {
    externalSignal.removeEventListener('abort', abortExternal);
  }
  window.clearTimeout(timeoutId);

  const payload = await parseResponsePayload(response);

  if (!response.ok) {
    const errorCode = getPayloadErrorCode(payload);
    const message = buildErrorMessage(response.status, payload);
    if (response.status === 401 && !options.skipAuthHandling) {
      emitUnauthorized(message);
    }
    throw new ApiError(message, response.status, payload, errorCode);
  }

  return payload as T;
}
