import { FeedbackPanel, StatusBadge } from '../common/StateViews';
import {
  DOCVERSE_UPLOAD_EXTENSIONS,
  getFileCategoryLabel,
  getFileExtension,
  getFileTypeWarning,
  isParseSupportedExtension,
  isUploadSelectionDisabled,
} from '../../constants/fileTypes';
import { overviewCards, overviewStats } from '../../data/mockDashboard';
import type { BackendHealth, UploadedDocument } from '../../types/api';
import type { LoadableState } from '../../types/ui';

type HeroSectionProps = {
  backendState: LoadableState<BackendHealth>;
  isAuthenticated: boolean;
  username?: string;
  onAuthOpen: (mode: 'login' | 'register') => void;
  selectedFile: File | null;
  onFileSelect: (file: File | null) => void;
  onUploadSubmit: () => void;
  uploadState: LoadableState<UploadedDocument>;
  currentDocument: UploadedDocument | null;
  partsCount: number;
  liveSectionCount: number;
  mockSectionCount: number;
};

function formatFileSize(size: number) {
  if (size < 1024) {
    return `${size} B`;
  }

  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }

  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function HeroSection({
  backendState,
  isAuthenticated,
  username,
  onAuthOpen,
  selectedFile,
  onFileSelect,
  onUploadSubmit,
  uploadState,
  currentDocument,
  partsCount,
  liveSectionCount,
  mockSectionCount,
}: HeroSectionProps) {
  const visibleSelectedFile = isAuthenticated ? selectedFile : null;
  const visibleCurrentDocument = isAuthenticated ? currentDocument : null;
  const selectedExtension = visibleSelectedFile ? getFileExtension(visibleSelectedFile.name) : '';
  const selectedCategory = selectedExtension ? getFileCategoryLabel(selectedExtension) : null;
  const selectedFileWarning = visibleSelectedFile ? getFileTypeWarning(selectedExtension) : null;
  const selectedFileCanUpload = selectedExtension ? !isUploadSelectionDisabled(selectedExtension) : false;
  const selectedFileParserSupported = selectedExtension ? isParseSupportedExtension(selectedExtension) : false;
  const uploadDisabled = !selectedFile || uploadState.status === 'loading' || !selectedFileCanUpload;
  const liveStats = [
    {
      label: overviewStats[0].label,
      value: visibleCurrentDocument ? `${visibleCurrentDocument.title} / ${partsCount || 0} parça` : overviewStats[0].value,
    },
    {
      label: 'Canlı akış',
      value: `${liveSectionCount} canlı / ${mockSectionCount} demo section`,
    },
    {
      label: 'Sistem',
      value:
        backendState.status === 'success'
          ? 'Bağlantı hazır'
          : backendState.status === 'error'
            ? 'Bağlantı kontrol edilmeli'
            : 'Bağlantı kontrol ediliyor',
    },
  ];

  return (
    <section id="overview" className="glass-panel overflow-hidden p-4 sm:p-6">
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr),minmax(320px,420px)]">
        <div className="space-y-4">
          <span className="chip bg-white/90">Ana Sayfa</span>
          <div className="space-y-3">
            <h1 className="display-font max-w-2xl text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">
              Doküman çalışma alanı
            </h1>
            <p className="max-w-2xl text-sm leading-7 text-slate-600 sm:text-base">
              Yüklediğin dokümanı oku, zorlandığın parçaları açıkla ve kanıtlı cevaplar al.
            </p>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            {liveStats.map((item) => (
              <div key={item.label} className="rounded-2xl border border-slate-200/80 bg-white/75 p-3">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{item.label}</p>
                <p className="mt-2 text-sm font-semibold leading-6 text-slate-950">{item.value}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="grid gap-4">
          <div className="surface-muted p-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-semibold text-slate-900">{isAuthenticated ? 'Profil' : 'Oturum'}</p>
                <p className="mt-1 text-sm leading-6 text-slate-600">
                  {isAuthenticated ? 'Çalışma alanı hazır.' : 'Doküman yüklemek ve cevap almak için giriş yap.'}
                </p>
              </div>
              <StatusBadge
                label={
                  backendState.status === 'success'
                    ? 'Hazır'
                    : backendState.status === 'error'
                      ? 'Kontrol gerekli'
                      : 'Kontrol'
                }
                tone={
                  backendState.status === 'success'
                    ? 'success'
                    : backendState.status === 'error'
                      ? 'error'
                      : 'info'
                }
              />
            </div>

            <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
              {isAuthenticated ? (
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-slate-900">Oturum açık</p>
                    <p className="mt-1 text-sm text-slate-500">
                      Kullanıcı: <span className="font-semibold text-slate-900">{username || 'aktif kullanıcı'}</span>
                    </p>
                  </div>
                  <StatusBadge label="Hazır" tone="success" />
                </div>
              ) : (
                <div className="space-y-4">
                  <p className="text-sm leading-6 text-slate-600">
                    Hesabına giriş yaptığında belge yükleme, açıklama ve kanıtlı cevap akışları açılır.
                  </p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <button
                      type="button"
                      onClick={() => onAuthOpen('login')}
                      className="rounded-xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white"
                    >
                      Giriş Yap
                    </button>
                    <button
                      type="button"
                      onClick={() => onAuthOpen('register')}
                      className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700"
                    >
                      Kayıt Ol
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            {!isAuthenticated ? (
              <div className="space-y-4">
                <div>
                  <p className="text-sm font-semibold text-slate-900">Doküman yükleme</p>
                  <p className="mt-1 text-sm leading-6 text-slate-600">
                    Doküman yüklemek ve parçalarla çalışmak için giriş yap.
                  </p>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <button
                    type="button"
                    onClick={() => onAuthOpen('login')}
                    className="rounded-xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white"
                  >
                    Giriş Yap
                  </button>
                  <button
                    type="button"
                    onClick={() => onAuthOpen('register')}
                    className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700"
                  >
                    Kayıt Ol
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-sm font-semibold text-slate-900">Belge yükleme</p>
                    <p className="mt-1 text-sm leading-6 text-slate-600">
                      Belgeni seç, parçalar hazır olunca çalışma alanında devam et.
                    </p>
                  </div>
                  <StatusBadge label="Canlı" tone="info" />
                </div>

                <div className="mt-5 space-y-4">
                  <label className="block rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-4 py-4 text-sm text-slate-600">
                    <span className="font-semibold text-slate-900">Dosya seç</span>
                    <span className="mt-2 block">
                      {visibleSelectedFile ? visibleSelectedFile.name : 'Henüz dosya seçilmedi'}
                    </span>
                    {visibleSelectedFile ? (
                      <div className="mt-2 flex flex-wrap gap-2 text-xs font-semibold text-slate-500">
                        <span>{visibleSelectedFile.type || 'Tür bilgisi yok'}</span>
                        <span>{formatFileSize(visibleSelectedFile.size)}</span>
                        <span className="rounded-full border border-slate-200 bg-white px-2 py-1 text-slate-700">
                          Uzantı: {selectedExtension || 'yok'}
                        </span>
                        <span className="rounded-full border border-teal-100 bg-teal-50 px-2 py-1 text-teal-700">
                          Kategori: {selectedCategory}
                        </span>
                        {selectedFileParserSupported ? (
                          <span className="rounded-full border border-emerald-100 bg-emerald-50 px-2 py-1 text-emerald-700">
                            İçerik çıkarma hazır
                          </span>
                        ) : null}
                      </div>
                    ) : null}
                    <input
                      type="file"
                      accept={DOCVERSE_UPLOAD_EXTENSIONS.join(',')}
                      onChange={(event) => onFileSelect(event.target.files?.[0] ?? null)}
                      className="mt-3 block w-full text-sm text-slate-500 file:mr-4 file:rounded-full file:border-0 file:bg-slate-900 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white"
                    />
                  </label>

                  {selectedFileWarning ? (
                    <div
                      className={`rounded-2xl border px-4 py-3 text-sm leading-6 ${
                        selectedFileCanUpload
                          ? 'border-amber-200 bg-amber-50 text-amber-800'
                          : 'border-rose-200 bg-rose-50 text-rose-700'
                      }`}
                    >
                      {selectedFileWarning}
                    </div>
                  ) : null}

                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                    <button
                      type="button"
                      onClick={onUploadSubmit}
                      disabled={uploadDisabled}
                      className="rounded-xl bg-teal-600 px-4 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {uploadState.status === 'loading' ? 'Yükleniyor...' : 'Dokümanı Yükle'}
                    </button>
                    {visibleCurrentDocument ? (
                      <p className="text-sm text-slate-500">Aktif doküman: {visibleCurrentDocument.title}</p>
                    ) : null}
                  </div>

                  {uploadState.status === 'error' ? (
                    <FeedbackPanel
                      title="Yükleme hatası"
                      message={uploadState.message ?? 'Doküman yüklenemedi.'}
                      tone="error"
                      actions={
                        visibleSelectedFile ? (
                          <button
                            type="button"
                            onClick={onUploadSubmit}
                            className="rounded-[16px] border border-rose-200 bg-white px-3 py-2 text-sm font-semibold text-rose-700"
                          >
                            Yeniden Dene
                          </button>
                        ) : null
                      }
                    />
                  ) : null}

                  {uploadState.status === 'success' && visibleCurrentDocument ? (
                    <FeedbackPanel
                      title="Doküman hazır"
                      message={uploadState.message ?? `${visibleCurrentDocument.title} yüklendi. ${partsCount} parça getirildi.`}
                      tone="success"
                    />
                  ) : null}

                  {uploadState.status === 'empty' && visibleCurrentDocument ? (
                    <FeedbackPanel
                      title="İçerik çıkarma sınırlı"
                      message={uploadState.message ?? 'Bu dosya yüklendi ancak şu anda içerik çıkarma desteği yok.'}
                      tone="info"
                    />
                  ) : null}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
        {overviewCards.map((card) => (
          <article key={card.title} className={`rounded-2xl border p-4 ${card.toneClass}`}>
            <p className="text-sm font-semibold text-slate-950">{card.title}</p>
            <p className="mt-3 text-sm leading-7 text-slate-700">{card.description}</p>
            <p className="mt-4 text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">{card.meta}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
