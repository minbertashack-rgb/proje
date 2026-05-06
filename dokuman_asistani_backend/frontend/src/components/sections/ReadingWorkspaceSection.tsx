import { SectionShell } from '../layout/SectionShell';
import { FeedbackPanel, StatusBadge } from '../common/StateViews';
import type { QuickAction } from '../../data/mockDashboard';
import type { DocumentPart, EvidenceAnswerResult, ExplainResult, UploadedDocument } from '../../types/api';
import type { LoadableState } from '../../types/ui';

type ReadingWorkspaceSectionProps = {
  activeAction: QuickAction;
  currentDocument: UploadedDocument | null;
  partsState: LoadableState<DocumentPart[]>;
  selectedPart: DocumentPart | null;
  onPartSelect: (partId: string) => void;
  onRunExplain: () => void;
  explainState: LoadableState<ExplainResult>;
  evidenceQuestion: string;
  onEvidenceQuestionChange: (value: string) => void;
  onAskEvidence: () => void;
  onClearEvidence: () => void;
  evidenceState: LoadableState<EvidenceAnswerResult>;
  isAuthenticated: boolean;
};

function hasExplainContent(result: ExplainResult | undefined) {
  if (!result) {
    return false;
  }

  return Boolean(
    result.oneLiner ||
      result.verySimple ||
      result.glossary.length ||
      result.steps.length ||
      result.examples.length ||
      result.miniQuiz.length,
  );
}

function renderExplainResult(explainState: LoadableState<ExplainResult>) {
  if (explainState.status === 'loading') {
    return (
      <FeedbackPanel
        title="Açıklama hazırlanıyor"
        message="Seçili parça için sadeleştirilmiş açıklama getiriliyor."
        tone="info"
      />
    );
  }

  if (explainState.status === 'error') {
    return (
      <FeedbackPanel
        title="Açıklama alınamadı"
        message={explainState.message ?? 'Yanıt işlenemedi.'}
        tone="error"
      />
    );
  }

  if (explainState.status === 'empty') {
    return (
      <FeedbackPanel
        title="Boş yanıt"
        message={explainState.message ?? 'Bu parça için gösterilebilir açıklama dönmedi.'}
        tone="warning"
      />
    );
  }

  if (explainState.status !== 'success' || !explainState.data) {
    return null;
  }

  const result = explainState.data;

  return (
    <div className="space-y-4">
      {result.oneLiner ? (
        <div className="rounded-[22px] border border-white/70 bg-white/80 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">One Liner</p>
          <p className="mt-2 text-sm font-semibold leading-7 text-slate-900">{result.oneLiner}</p>
        </div>
      ) : null}

      {result.verySimple ? (
        <div className="rounded-[22px] border border-white/70 bg-white/80 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Very Simple</p>
          <p className="mt-2 text-sm leading-7 text-slate-700">{result.verySimple}</p>
        </div>
      ) : null}

      {result.glossary.length ? (
        <div className="rounded-[22px] border border-white/70 bg-white/80 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Glossary</p>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {result.glossary.map((item) => (
              <div key={`${item.term}-${item.definition ?? ''}`} className="rounded-[18px] bg-white px-4 py-3">
                <p className="text-sm font-semibold text-slate-900">{item.term}</p>
                {item.definition ? <p className="mt-1 text-sm leading-7 text-slate-600">{item.definition}</p> : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {result.steps.length ? (
        <div className="rounded-[22px] border border-white/70 bg-white/80 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Steps</p>
          <ol className="mt-3 space-y-3">
            {result.steps.map((step, index) => (
              <li key={`${index + 1}-${step}`} className="flex gap-3 rounded-[18px] bg-white px-4 py-3">
                <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white">
                  {index + 1}
                </span>
                <span className="text-sm leading-7 text-slate-700">{step}</span>
              </li>
            ))}
          </ol>
        </div>
      ) : null}

      {result.examples.length ? (
        <div className="rounded-[22px] border border-white/70 bg-white/80 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Examples</p>
          <div className="mt-3 space-y-2">
            {result.examples.map((example, index) => (
              <div key={`${index + 1}-${example}`} className="rounded-[18px] bg-white px-4 py-3 text-sm leading-7 text-slate-700">
                <span className="mr-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
                  Ornek {index + 1}
                </span>
                {example}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {result.miniQuiz.length ? (
        <div className="rounded-[22px] border border-white/70 bg-white/80 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Mini Quiz</p>
          <div className="mt-3 space-y-3">
            {result.miniQuiz.map((quizItem, index) => (
              <div key={`${quizItem.question}-${quizItem.answer ?? ''}`} className="rounded-[18px] bg-white px-4 py-3">
                <p className="text-sm font-semibold text-slate-900">Soru {index + 1}</p>
                <p className="mt-2 text-sm leading-7 text-slate-700">{quizItem.question}</p>
                {quizItem.answer ? (
                  <p className="mt-3 rounded-[16px] bg-slate-50 px-3 py-3 text-sm leading-7 text-slate-600">
                    <span className="font-semibold text-slate-900">Cevap:</span> {quizItem.answer}
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function renderEvidenceResult(
  evidenceState: LoadableState<EvidenceAnswerResult>,
  onClearEvidence: () => void,
) {
  if (evidenceState.status === 'loading') {
    return (
      <FeedbackPanel
        title="Kanıtlı cevap hazırlanıyor"
        message="Soru belge içeriğiyle birlikte işleniyor."
        tone="info"
      />
    );
  }

  if (evidenceState.status === 'error') {
    return (
      <FeedbackPanel
        title="Soru gönderilemedi"
        message={evidenceState.message ?? 'Kanıtlı cevap alınamadı.'}
        tone="error"
      />
    );
  }

  if (evidenceState.status === 'empty') {
    return (
      <FeedbackPanel
        title="Yanıt boş döndü"
        message={evidenceState.message ?? 'Bu soru için cevap veya kanıt bulunamadı.'}
        tone="warning"
        actions={
          <button
            type="button"
            onClick={onClearEvidence}
            className="rounded-[16px] border border-amber-200 bg-white px-3 py-2 text-sm font-semibold text-amber-700"
          >
            Yeni Soru
          </button>
        }
      />
    );
  }

  if (evidenceState.status !== 'success' || !evidenceState.data) {
    return null;
  }

  return (
    <div className="space-y-4">
      {evidenceState.data.answer ? (
        <div className="rounded-[22px] border border-white/70 bg-white/80 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Ana Cevap</p>
          <p className="mt-2 text-sm leading-7 text-slate-700">{evidenceState.data.answer}</p>
        </div>
      ) : null}

      {evidenceState.data.path ? (
        <div className="rounded-[22px] border border-white/70 bg-white/80 p-4 text-sm leading-7 text-slate-700">
          <span className="font-semibold text-slate-900">Adres:</span> {evidenceState.data.path}
        </div>
      ) : null}

      {evidenceState.data.snippets.length ? (
        <div className="rounded-[22px] border border-white/70 bg-white/80 p-4">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Kanıt Kartları</p>
            <button
              type="button"
              onClick={onClearEvidence}
              className="rounded-[16px] border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700"
            >
              Temizle
            </button>
          </div>
          <div className="mt-3 space-y-3">
            {evidenceState.data.snippets.map((snippet, index) => (
              <div key={`${snippet.text}-${snippet.path ?? ''}-${index}`} className="rounded-[18px] bg-white px-4 py-3">
                <p className="text-sm leading-7 text-slate-700">{snippet.text}</p>
                <div className="mt-2 flex flex-wrap gap-2 text-xs font-semibold text-slate-500">
                  {snippet.source ? <span>Kaynak: {snippet.source}</span> : null}
                  {snippet.path ? <span>Adres: {snippet.path}</span> : null}
                  {snippet.score ? <span>Skor: {snippet.score}</span> : null}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function ReadingWorkspaceSection({
  activeAction,
  currentDocument,
  partsState,
  selectedPart,
  onPartSelect,
  onRunExplain,
  explainState,
  evidenceQuestion,
  onEvidenceQuestionChange,
  onAskEvidence,
  onClearEvidence,
  evidenceState,
  isAuthenticated,
}: ReadingWorkspaceSectionProps) {
  const parts = partsState.data ?? [];
  const partCount = parts.length;
  const selectedPartIndex = selectedPart ? parts.findIndex((part) => part.id === selectedPart.id) + 1 : null;

  return (
    <SectionShell
      id="workspace"
      eyebrow="Orta İçerik Alanı"
      title="Belge çalışma alanı ve canlı aksiyon paneli"
      description="Seçili aksiyon burada içerikle birlikte görünür. Sağdaki yorum paneli masaüstünde daha rahat, mobilde ise alta akacak şekilde tasarlandı."
      aside={
        <div className="rounded-full border border-slate-200 bg-slate-50 px-4 py-2 text-sm font-medium text-slate-600">
          Aktif mod: {activeAction.title}
        </div>
      }
    >
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.18fr),minmax(300px,0.82fr)]">
        <article className="surface-muted p-5">
          <div className="flex flex-col gap-3 border-b border-slate-200 pb-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-semibold text-slate-900">Belge görünümü</p>
              <p className="mt-1 text-sm text-slate-500">
                {currentDocument ? currentDocument.title : 'Henüz aktif doküman yok'}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <span className="chip bg-white">{partCount} parça</span>
              <span className="chip bg-white">
                {selectedPartIndex ? `Secili #${selectedPartIndex}` : 'Parça seçilmedi'}
              </span>
              <span className="chip bg-white">{isAuthenticated ? 'Oturum hazır' : 'Giriş gerekli'}</span>
            </div>
          </div>

          {!currentDocument ? (
            <FeedbackPanel
              title="Belge bekleniyor"
              message="Önce giriş yapıp bir doküman yüklediğinizde parça listesi burada görünecek."
              tone="warning"
              className="mt-5"
            />
          ) : null}

          {partsState.status === 'loading' ? (
            <FeedbackPanel
              title="Parçalar getiriliyor"
              message="Yüklenen dokümanın bölümleri okunabilir kartlara ayrılıyor."
              tone="info"
              className="mt-5"
            />
          ) : null}

          {partsState.status === 'error' ? (
            <FeedbackPanel
              title="Parça listesi alınamadı"
              message={partsState.message ?? 'Doküman parçaları getirilemedi.'}
              tone="error"
              className="mt-5"
            />
          ) : null}

          {currentDocument && partsState.status === 'empty' ? (
            <FeedbackPanel
              title="Parça bulunamadı"
              message={partsState.message ?? 'Bu doküman için görünür parça bulunamadı.'}
              tone="warning"
              className="mt-5"
            />
          ) : null}

          {partsState.status === 'success' ? (
            <div className="mt-5 grid gap-4 xl:grid-cols-[260px,minmax(0,1fr)]">
              <div className="space-y-3">
                {parts.map((part) => {
                  const active = selectedPart?.id === part.id;
                  return (
                    <button
                      key={part.id}
                      type="button"
                      onClick={() => onPartSelect(part.id)}
                      className={`w-full rounded-[20px] border px-4 py-4 text-left transition ${
                        active
                          ? 'border-slate-900 bg-slate-900 text-white shadow-soft'
                          : 'border-slate-200 bg-white text-slate-700'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-sm font-semibold">{part.title}</p>
                        <span className={`text-xs ${active ? 'text-slate-200' : 'text-slate-400'}`}>#{part.order}</span>
                      </div>
                      {part.pageLabel ? (
                        <p className={`mt-2 text-xs ${active ? 'text-slate-200' : 'text-slate-500'}`}>{part.pageLabel}</p>
                      ) : null}
                    </button>
                  );
                })}
              </div>

              <div className="space-y-4">
                {selectedPart ? (
                  <>
                    <div className="rounded-[22px] border border-slate-200 bg-white p-5">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-slate-900">{selectedPart.title}</p>
                          <p className="mt-1 text-sm text-slate-500">
                            {selectedPart.pageLabel || `Parça sırası ${selectedPart.order}`}
                          </p>
                        </div>
                        <StatusBadge label={`ID ${selectedPart.id}`} tone="neutral" />
                      </div>
                      <div className="mt-4 max-h-[28rem] overflow-y-auto rounded-[18px] bg-slate-50 px-4 py-4">
                        <p className="whitespace-pre-wrap break-words text-sm leading-7 text-slate-700">
                          {selectedPart.content || 'Bu parça için içerik metni dönmedi.'}
                        </p>
                      </div>
                    </div>

                    <div className="grid gap-4 lg:grid-cols-2">
                      <div className="rounded-[22px] border border-amber-200 bg-amber-50/80 p-4">
                        <p className="text-sm font-semibold text-slate-900">Zor Kısımlar</p>
                        <p className="mt-2 text-sm leading-7 text-slate-700">
                          Seçili parçayı aktif aksiyonlardan “Zor Kısım” veya “Bunu Anlamadım” ile tekrar işleyebilirsiniz.
                        </p>
                      </div>
                      <div className="rounded-[22px] border border-violet-200 bg-violet-50/80 p-4">
                        <p className="text-sm font-semibold text-slate-900">Terim Yoğun Alanlar</p>
                        <p className="mt-2 text-sm leading-7 text-slate-700">
                          Açıklama sonucunda terimler gelirse burada ve sağ panelde otomatik görünür.
                        </p>
                      </div>
                    </div>
                  </>
                ) : (
                  <FeedbackPanel
                    title="Parça seçin"
                    message="Açıklama ve kanıt akışlarını başlatmak için soldaki listeden bir parça seçin."
                    tone="warning"
                  />
                )}
              </div>
            </div>
          ) : null}
        </article>

        <article className={`rounded-[26px] border p-5 ${activeAction.toneClass}`}>
          <div className="flex items-start gap-4">
            <div className={`inline-flex h-12 w-12 items-center justify-center rounded-2xl text-sm font-semibold ${activeAction.iconClass}`}>
              {activeAction.title.slice(0, 1)}
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-900">Canlı aksiyon paneli</p>
              <h3 className="display-font mt-1 text-2xl font-semibold text-slate-950">{activeAction.title}</h3>
            </div>
          </div>

          <p className="mt-5 text-sm leading-7 text-slate-700">{activeAction.detail}</p>

          <div className="mt-5 rounded-[24px] border border-white/70 bg-white/70 p-4">
            <p className="text-sm font-semibold text-slate-900">Sistem isteği</p>
            <p className="mt-2 text-sm leading-7 text-slate-700">{activeAction.prompt}</p>
          </div>

          {activeAction.id === 'confused' ? (
            <div className="mt-5 space-y-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <button
                  type="button"
                  onClick={onRunExplain}
                  disabled={!selectedPart || !isAuthenticated || explainState.status === 'loading'}
                  className="rounded-[20px] bg-slate-900 px-4 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {explainState.status === 'loading' ? 'İşleniyor...' : 'Bunu Anlamadım Çalıştır'}
                </button>
                <p className="text-sm text-slate-600">
                  {selectedPart ? `${selectedPart.title} için` : 'Önce bir parça seçin'}
                </p>
              </div>
              {renderExplainResult(explainState)}
              {!hasExplainContent(explainState.data) && explainState.status === 'idle' ? (
                <div className="space-y-3">
                  {activeAction.bullets.map((bullet) => (
                    <div key={bullet} className="rounded-[20px] border border-white/70 bg-white/75 px-4 py-3 text-sm text-slate-700">
                      {bullet}
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {activeAction.id === 'evidence' ? (
            <div className="mt-5 space-y-4">
              <textarea
                value={evidenceQuestion}
                onChange={(event) => onEvidenceQuestionChange(event.target.value)}
                placeholder="Sorunu yaz: örn. geri yayılım neden önemlidir?"
                className="min-h-[120px] w-full rounded-[22px] border border-white/70 bg-white/75 p-4 text-sm leading-7 text-slate-700 outline-none transition focus:border-slate-400"
              />
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <button
                  type="button"
                  onClick={onAskEvidence}
                  disabled={!isAuthenticated || evidenceState.status === 'loading' || !evidenceQuestion.trim()}
                  className="rounded-[20px] bg-slate-900 px-4 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {evidenceState.status === 'loading' ? 'Soruluyor...' : 'Kanıtlı Cevap Getir'}
                </button>
                <button
                  type="button"
                  onClick={onClearEvidence}
                  className="rounded-[20px] border border-white/70 bg-white/75 px-4 py-3 text-sm font-semibold text-slate-700"
                >
                  Temizle
                </button>
              </div>
              {renderEvidenceResult(evidenceState, onClearEvidence)}
              {evidenceState.status === 'idle' ? (
                <div className="space-y-3">
                  {activeAction.bullets.map((bullet) => (
                    <div key={bullet} className="rounded-[20px] border border-white/70 bg-white/75 px-4 py-3 text-sm text-slate-700">
                      {bullet}
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {activeAction.id === 'terms' ? (
            <div className="mt-5 space-y-3">
              {explainState.data?.glossary.length ? (
                explainState.data.glossary.map((item) => (
                  <div key={item.term} className="rounded-[20px] border border-white/70 bg-white/75 px-4 py-3">
                    <p className="text-sm font-semibold text-slate-900">{item.term}</p>
                    {item.definition ? <p className="mt-2 text-sm leading-7 text-slate-700">{item.definition}</p> : null}
                  </div>
                ))
              ) : (
                <>
                  {activeAction.bullets.map((bullet) => (
                    <div key={bullet} className="rounded-[20px] border border-white/70 bg-white/75 px-4 py-3 text-sm text-slate-700">
                      {bullet}
                    </div>
                  ))}
                  <FeedbackPanel
                    title="Demo + canlı geçiş"
                    message="Gerçek glossary verisi, Bunu Anlamadım yanıtında dönmeye başladığında bu panel otomatik canlı veriyi kullanır."
                    tone="info"
                  />
                </>
              )}
            </div>
          ) : null}

          {activeAction.id === 'hard-parts' ? (
            <div className="mt-5 space-y-3">
              {selectedPart ? (
                <FeedbackPanel
                  title="Seçili zor pasaj adayı"
                  message={`${selectedPart.title} aktif inceleme parçası olarak seçildi. İsterseniz önce “Bunu Anlamadım” çalıştırıp ardından bu pasajı tekrar değerlendirebilirsiniz.`}
                  tone="warning"
                />
              ) : null}
              {activeAction.bullets.map((bullet) => (
                <div key={bullet} className="rounded-[20px] border border-white/70 bg-white/75 px-4 py-3 text-sm text-slate-700">
                  {bullet}
                </div>
              ))}
            </div>
          ) : null}
        </article>
      </div>
    </SectionShell>
  );
}
