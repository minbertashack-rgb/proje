export type AuthSession = {
  accessToken: string;
  refreshToken?: string;
  username?: string;
};

export type LoginCredentials = {
  username: string;
  password: string;
};

export type RegisterPayload = {
  username: string;
  password: string;
  password2: string;
  email?: string;
};

export type RegisterFormValues = Omit<RegisterPayload, 'password2'> & {
  passwordConfirm: string;
};

export type BackendHealth = {
  ok: boolean;
  message: string;
  checkedAt: string;
};

export type UploadedDocument = {
  id: string;
  title: string;
  fileName: string;
  createdAt?: string;
  raw: unknown;
};

export type DocumentPart = {
  id: string;
  order: number;
  title: string;
  content: string;
  pageLabel?: string;
  raw: unknown;
};

export type ExplainGlossaryItem = {
  term: string;
  definition?: string;
};

export type ExplainQuizItem = {
  question: string;
  answer?: string;
};

export type ExplainResult = {
  oneLiner?: string;
  verySimple?: string;
  glossary: ExplainGlossaryItem[];
  steps: string[];
  examples: string[];
  miniQuiz: ExplainQuizItem[];
  raw: unknown;
};

export type EvidenceSnippet = {
  text: string;
  source?: string;
  path?: string;
  score?: string;
};

export type EvidenceAnswerResult = {
  answer?: string;
  snippets: EvidenceSnippet[];
  path?: string;
  raw: unknown;
};
