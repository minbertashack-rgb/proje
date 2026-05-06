import type { BackendHealth, DocumentPart, UploadedDocument } from '../types/api';
import { apiRequest, ApiError, getApiErrorCode } from './client';
import {
  asRecord,
  extractMessage,
  pickNumber,
  pickString,
  pickStringOrNumber,
  unwrapArray,
  unwrapRecord,
} from './normalize';

function normalizeDocument(raw: unknown, fallbackFileName: string): UploadedDocument {
  const candidate = unwrapRecord(raw, ['dokuman', 'document', 'payload', 'data', 'result', 'item']);

  const id = pickStringOrNumber(candidate, ['id', 'dokuman_id', 'document_id']) ?? fallbackFileName;
  const fileName =
    pickString(candidate, ['dosya_adi', 'file_name', 'filename', 'name']) ?? fallbackFileName;
  const title =
    pickString(candidate, ['baslik', 'title', 'ad', 'name']) ?? fileName;

  return {
    id,
    title,
    fileName,
    createdAt: pickString(candidate, ['created_at', 'olusturma_tarihi', 'uploaded_at']),
    raw,
  };
}

function normalizePart(raw: unknown, index: number): DocumentPart | null {
  const record = asRecord(raw);
  if (!record) {
    return null;
  }

  const id = pickStringOrNumber(record, ['id', 'parca_id']) ?? `part-${index + 1}`;
  const order = pickNumber(record, ['sira', 'order', 'index']) ?? index + 1;
  const title =
    pickString(record, ['baslik', 'title', 'heading']) ?? `Parça ${order}`;
  const content =
    pickString(record, ['icerik', 'content', 'metin', 'text', 'parca_metni']) ?? '';

  return {
    id,
    order,
    title,
    content,
    pageLabel: pickString(record, ['sayfa', 'page', 'section', 'bolum']),
    raw,
  };
}

export async function pingBackend() {
  const raw = await apiRequest<unknown>('/api/dokuman-asistani/ping/');
  const record = unwrapRecord(raw, ['payload', 'data', 'result', 'status']);

  return {
    ok: true,
    message:
      pickString(record, ['message', 'mesaj', 'detail', 'status']) ??
      'Bağlantı hazır.',
    checkedAt: new Date().toISOString(),
  } satisfies BackendHealth;
}

export async function uploadDocument(file: File) {
  const fieldNames = ['dosya', 'file'];
  let lastError: unknown = null;

  for (const fieldName of fieldNames) {
    const formData = new FormData();
    formData.append(fieldName, file);

    try {
      const raw = await apiRequest<unknown>('/api/dokuman-asistani/dokumanlar/yukle/', {
        method: 'POST',
        body: formData,
      });
      return normalizeDocument(raw, file.name);
    } catch (error) {
      lastError = error;
      const errorCode = getApiErrorCode(error);
      const shouldRetryWithFileField =
        error instanceof ApiError &&
        error.status < 500 &&
        fieldName === 'dosya' &&
        !errorCode;

      if (!shouldRetryWithFileField) {
        throw error;
      }
    }
  }

  throw lastError instanceof Error ? lastError : new Error('Doküman yüklenemedi.');
}

export function getDocumentFromUploadError(error: unknown, fallbackFileName: string) {
  if (!(error instanceof ApiError) || getApiErrorCode(error) !== 'parser_not_available') {
    return null;
  }

  try {
    return normalizeDocument(error.payload, fallbackFileName);
  } catch {
    return null;
  }
}

export async function fetchDocumentParts(documentId: string) {
  const raw = await apiRequest<unknown>(`/api/dokuman-asistani/dokumanlar/${documentId}/parcalar/`);
  const list = unwrapArray(raw, ['parcalar', 'parts', 'items', 'results', 'data', 'payload']);

  return list
    .map((item, index) => normalizePart(item, index))
    .filter((item): item is DocumentPart => Boolean(item))
    .sort((left, right) => left.order - right.order);
}

export function getApiErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    return error.message;
  }

  return extractMessage(error) ?? 'Beklenmeyen bir hata oluştu.';
}
