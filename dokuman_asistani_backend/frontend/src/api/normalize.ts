export function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }

  return value as Record<string, unknown>;
}

export function asArray(value: unknown) {
  return Array.isArray(value) ? value : [];
}

export function isLikelyHtml(value: string) {
  const normalized = value.trim().toLowerCase();
  if (!normalized) {
    return false;
  }

  return (
    normalized.startsWith('<!doctype html') ||
    normalized.startsWith('<html') ||
    normalized.includes('<body') ||
    normalized.includes('<title') ||
    /<\/?[a-z][\s\S]*>/i.test(normalized.slice(0, 240))
  );
}

export function ensureTrimmedString(value: unknown) {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

export function pickString(record: Record<string, unknown> | null, keys: string[]) {
  if (!record) {
    return undefined;
  }

  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }

  return undefined;
}

export function pickStringOrNumber(record: Record<string, unknown> | null, keys: string[]) {
  if (!record) {
    return undefined;
  }

  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
    if (typeof value === 'number' && Number.isFinite(value)) {
      return String(value);
    }
  }

  return undefined;
}

export function pickNumber(record: Record<string, unknown> | null, keys: string[]) {
  if (!record) {
    return undefined;
  }

  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value;
    }
    if (typeof value === 'string') {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
  }

  return undefined;
}

export function pickNestedRecord(record: Record<string, unknown> | null, keys: string[]) {
  if (!record) {
    return null;
  }

  for (const key of keys) {
    const nested = asRecord(record[key]);
    if (nested) {
      return nested;
    }
  }

  return null;
}

export function pickArray(record: Record<string, unknown> | null, keys: string[]) {
  if (!record) {
    return [];
  }

  for (const key of keys) {
    const value = record[key];
    if (Array.isArray(value)) {
      return value;
    }
  }

  return [];
}

export function pickNestedArray(record: Record<string, unknown> | null, keys: string[]) {
  if (!record) {
    return [];
  }

  const direct = pickArray(record, keys);
  if (direct.length > 0) {
    return direct;
  }

  for (const key of keys) {
    const nested = asRecord(record[key]);
    const nestedDirect = pickArray(nested, keys);
    if (nestedDirect.length > 0) {
      return nestedDirect;
    }
  }

  return [];
}

export function unwrapRecord(raw: unknown, keys: string[]) {
  const topLevel = asRecord(raw);
  if (!topLevel) {
    return null;
  }

  const nested = pickNestedRecord(topLevel, keys);
  if (nested) {
    return nested;
  }

  for (const key of keys) {
    const rawList = asArray(topLevel[key]);
    const firstRecord = rawList.map((item) => asRecord(item)).find(Boolean);
    if (firstRecord) {
      return firstRecord;
    }
  }

  return topLevel;
}

export function unwrapArray(raw: unknown, keys: string[]) {
  if (Array.isArray(raw)) {
    return raw;
  }

  const topLevel = asRecord(raw);
  if (!topLevel) {
    return [];
  }

  return pickNestedArray(topLevel, keys);
}

export function toTextList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        const directString = ensureTrimmedString(item);
        if (directString) {
          return directString;
        }
        const itemRecord = asRecord(item);
        return (
          pickString(itemRecord, ['text', 'icerik', 'content', 'description', 'aciklama', 'madde']) ?? ''
        );
      })
      .filter(Boolean);
  }

  if (typeof value === 'string' && value.trim()) {
    return [value.trim()];
  }

  return [];
}

export function extractMessage(value: unknown) {
  const directString = ensureTrimmedString(value);
  if (directString && !isLikelyHtml(directString)) {
    return directString;
  }

  const record = asRecord(value);
  if (!record) {
    return undefined;
  }

  const direct =
    pickString(record, ['detail', 'message', 'mesaj', 'error', 'non_field_errors']) ??
    pickString(asRecord(record.errors), ['detail', 'message']);

  if (direct) {
    return direct;
  }

  const entries = Object.entries(record)
    .map(([key, rawValue]) => {
      if (typeof rawValue === 'string' && rawValue.trim() && !isLikelyHtml(rawValue)) {
        return `${key}: ${rawValue.trim()}`;
      }
      if (Array.isArray(rawValue)) {
        const text = rawValue
          .filter((item): item is string => typeof item === 'string')
          .filter((item) => !isLikelyHtml(item))
          .join(', ');
        return text ? `${key}: ${text}` : '';
      }
      return '';
    })
    .filter(Boolean);

  return entries[0];
}
