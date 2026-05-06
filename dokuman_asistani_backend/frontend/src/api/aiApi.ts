import type {
  EvidenceAnswerResult,
  EvidenceSnippet,
  ExplainGlossaryItem,
  ExplainQuizItem,
  ExplainResult,
} from '../types/api';
import { apiRequest } from './client';
import {
  asArray,
  asRecord,
  pickString,
  pickStringOrNumber,
  toTextList,
  unwrapArray,
  unwrapRecord,
} from './normalize';

function normalizeGlossary(raw: unknown): ExplainGlossaryItem[] {
  if (Array.isArray(raw)) {
    return raw
      .map((item) => {
        if (typeof item === 'string' && item.trim()) {
          return { term: item.trim() };
        }

        const record = asRecord(item);
        const term = pickString(record, ['term', 'kavram', 'title', 'baslik']);
        if (!term) {
          return null;
        }

        return {
          term,
          definition: pickString(record, ['definition', 'aciklama', 'description', 'anlam']),
        };
      })
      .filter((item): item is ExplainGlossaryItem => Boolean(item));
  }

  const record = asRecord(raw);
  if (!record) {
    return [];
  }

  return Object.entries(record)
    .reduce<ExplainGlossaryItem[]>((items, [term, definition]) => {
      if (!term.trim()) {
        return items;
      }

      items.push({
        term,
        definition: typeof definition === 'string' ? definition.trim() : undefined,
      });

      return items;
    }, []);
}

function normalizeMiniQuiz(raw: unknown): ExplainQuizItem[] {
  return asArray(raw)
    .map((item) => {
      if (typeof item === 'string' && item.trim()) {
        return { question: item.trim() };
      }

      const record = asRecord(item);
      const question = pickString(record, ['question', 'soru', 'title']);
      if (!question) {
        return null;
      }

      return {
        question,
        answer: pickString(record, ['answer', 'cevap']),
      };
    })
    .filter((item): item is ExplainQuizItem => Boolean(item));
}

function normalizeExplainResult(raw: unknown): ExplainResult {
  const candidate = unwrapRecord(raw, ['data', 'payload', 'result', 'results', 'anlamadim', 'response', 'item']);

  return {
    oneLiner: pickString(candidate, ['one_liner', 'tek_cumle', 'summary']),
    verySimple: pickString(candidate, ['very_simple', 'cok_basit', 'simple']),
    glossary: normalizeGlossary(
      candidate?.glossary ?? candidate?.terimler ?? candidate?.sozluk,
    ),
    steps: toTextList(candidate?.steps ?? candidate?.adimlar),
    examples: toTextList(candidate?.examples ?? candidate?.ornekler),
    miniQuiz: normalizeMiniQuiz(candidate?.mini_quiz ?? candidate?.miniQuiz ?? candidate?.quiz),
    raw,
  };
}

function normalizeSnippet(raw: unknown): EvidenceSnippet | null {
  const record = asRecord(raw);
  if (!record) {
    if (typeof raw === 'string' && raw.trim()) {
      return { text: raw.trim() };
    }
    return null;
  }

  const text = pickString(record, ['text', 'snippet', 'icerik', 'content', 'quote']);
  if (!text) {
    return null;
  }

  return {
    text,
    source: pickString(record, ['source', 'kaynak', 'document', 'belge']),
    path: pickString(record, ['path', 'adres', 'location']),
    score: pickStringOrNumber(record, ['score', 'confidence', 'guven']),
  };
}

function normalizeEvidenceResult(raw: unknown): EvidenceAnswerResult {
  const candidate = unwrapRecord(raw, ['data', 'payload', 'result', 'results', 'response', 'item']);

  const rawSnippets = unwrapArray(candidate?.snippets ?? candidate, [
    'snippets',
    'kanitlar',
    'evidence',
    'sources',
    'items',
    'results',
  ]);

  return {
    answer: pickString(candidate, ['answer', 'cevap', 'yanit', 'response']),
    snippets: rawSnippets
      .map((snippet) => normalizeSnippet(snippet))
      .filter((item): item is EvidenceSnippet => Boolean(item)),
    path: pickString(candidate, ['path', 'adres', 'source_path']),
    raw,
  };
}

export async function requestExplain(partId: string) {
  const raw = await apiRequest<unknown>(`/api/dokuman-asistani/parcalar/${partId}/anlamadim-v2/`, {
    method: 'POST',
  });

  return normalizeExplainResult(raw);
}

export async function requestEvidenceAnswer(input: {
  question: string;
  documentId?: string;
  partId?: string;
}) {
  const body: Record<string, unknown> = {
    soru: input.question,
  };

  if (input.documentId) {
    body.dokuman_id = input.documentId;
  }

  if (input.partId) {
    body.parca_id = input.partId;
  }

  const raw = await apiRequest<unknown>('/api/dokuman-asistani/ai2/kanitli-cevap/', {
    method: 'POST',
    body,
  });

  return normalizeEvidenceResult(raw);
}
