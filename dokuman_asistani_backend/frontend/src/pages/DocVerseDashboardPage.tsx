import { useEffect, useState } from 'react';
import { Header } from '../components/layout/Header';
import { Sidebar } from '../components/layout/Sidebar';
import { Drawer } from '../components/layout/Drawer';
import { MobileBottomActions } from '../components/layout/MobileBottomActions';
import { RightRail } from '../components/layout/RightRail';
import { HeroSection } from '../components/sections/HeroSection';
import { ReadingWorkspaceSection } from '../components/sections/ReadingWorkspaceSection';
import { ThemeSurveySection } from '../components/sections/ThemeSurveySection';
import { RemixConsoleSection } from '../components/sections/RemixConsoleSection';
import { DirectorsCutSection } from '../components/sections/DirectorsCutSection';
import { ConceptGraphSection } from '../components/sections/ConceptGraphSection';
import { NotesSection } from '../components/sections/NotesSection';
import { ChallengesSection } from '../components/sections/ChallengesSection';
import { OwnSentenceSection } from '../components/sections/OwnSentenceSection';
import { ProgressFlowSection } from '../components/sections/ProgressFlowSection';
import { InsightAccessSection } from '../components/sections/InsightAccessSection';
import { navItems } from '../constants/navigation';
import { liveSectionLabels, mockSectionLabels } from '../constants/sectionModes';
import { quickActions } from '../data/mockDashboard';
import { requestEvidenceAnswer, requestExplain } from '../api/aiApi';
import {
  fetchDocumentParts,
  getApiErrorMessage,
  getDocumentFromUploadError,
  pingBackend,
  uploadDocument,
} from '../api/documentApi';
import { getApiErrorCode } from '../api/client';
import { getFileExtension, getFileTypeWarning, isUploadSelectionDisabled } from '../constants/fileTypes';
import { useAuthSession } from '../hooks/useAuthSession';
import type {
  BackendHealth,
  DocumentPart,
  EvidenceAnswerResult,
  ExplainResult,
  UploadedDocument,
} from '../types/api';
import type { LoadableState } from '../types/ui';

function createState<T>(
  status: LoadableState<T>['status'],
  data?: T,
  message?: string,
): LoadableState<T> {
  return {
    status,
    data,
    message,
    updatedAt: new Date().toISOString(),
  };
}

export function DocVerseDashboardPage() {
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [activeActionId, setActiveActionId] = useState<(typeof quickActions)[number]['id']>('confused');
  const {
    session,
    clearSession,
    isAuthenticated,
    authNotice,
    clearAuthNotice,
  } = useAuthSession();
  const [backendState, setBackendState] = useState<LoadableState<BackendHealth>>(createState('idle'));
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadState, setUploadState] = useState<LoadableState<UploadedDocument>>(createState('idle'));
  const [currentDocument, setCurrentDocument] = useState<UploadedDocument | null>(null);
  const [partsState, setPartsState] = useState<LoadableState<DocumentPart[]>>(createState('idle'));
  const [selectedPartId, setSelectedPartId] = useState<string | null>(null);
  const [explainState, setExplainState] = useState<LoadableState<ExplainResult>>(createState('idle'));
  const [evidenceQuestion, setEvidenceQuestion] = useState('');
  const [evidenceState, setEvidenceState] = useState<LoadableState<EvidenceAnswerResult>>(createState('idle'));
  const activeAction = quickActions.find((action) => action.id === activeActionId) ?? quickActions[0];
  const parts = partsState.data ?? [];
  const selectedPart = parts.find((part) => part.id === selectedPartId) ?? null;

  const resetLearningFlow = () => {
    setCurrentDocument(null);
    setSelectedFile(null);
    setSelectedPartId(null);
    setPartsState(createState<DocumentPart[]>('idle'));
    setExplainState(createState<ExplainResult>('idle'));
    setEvidenceState(createState<EvidenceAnswerResult>('idle'));
    setEvidenceQuestion('');
    setUploadState(createState<UploadedDocument>('idle'));
  };

  useEffect(() => {
    let active = true;

    const runPing = async () => {
      setBackendState(createState<BackendHealth>('loading'));
      try {
        const health = await pingBackend();
        if (!active) {
          return;
        }
        setBackendState(createState('success', health, health.message));
      } catch (error) {
        if (!active) {
          return;
        }
        setBackendState(createState<BackendHealth>('error', undefined, getApiErrorMessage(error)));
      }
    };

    void runPing();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!authNotice) {
      return;
    }

    resetLearningFlow();
  }, [authNotice]);

  useEffect(() => {
    if (isAuthenticated) {
      return;
    }

    resetLearningFlow();
  }, [isAuthenticated]);

  useEffect(() => {
    if (!parts.length) {
      setSelectedPartId(null);
      return;
    }

    if (!selectedPartId || !parts.some((part) => part.id === selectedPartId)) {
      setSelectedPartId(parts[0].id);
    }
  }, [parts, selectedPartId]);

  const handleActionSelect = (id: (typeof quickActions)[number]['id']) => {
    setActiveActionId(id);
    setIsDrawerOpen(false);
    document.getElementById('workspace')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const handleAuthOpen = (mode: 'login' | 'register') => {
    setIsDrawerOpen(false);
    window.location.hash = `#/auth/${mode}`;
  };

  const handleLogout = () => {
    clearSession();
    clearAuthNotice();
    resetLearningFlow();
  };

  const loadParts = async (documentId: string) => {
    setPartsState(createState<DocumentPart[]>('loading'));
    try {
      const nextParts = await fetchDocumentParts(documentId);
      if (nextParts.length === 0) {
        setPartsState(createState('empty', [], 'Bu doküman için görünür parça bulunamadı.'));
        return;
      }

      setPartsState(createState('success', nextParts, `${nextParts.length} parça getirildi.`));
    } catch (error) {
      setPartsState(createState<DocumentPart[]>('error', undefined, getApiErrorMessage(error)));
    }
  };

  const handleUploadSubmit = async () => {
    if (!isAuthenticated) {
      setUploadState(createState<UploadedDocument>('error', undefined, 'Önce giriş yapmalısınız.'));
      return;
    }

    if (!selectedFile) {
      setUploadState(createState<UploadedDocument>('error', undefined, 'Lütfen bir dosya seçin.'));
      return;
    }

    const selectedExtension = getFileExtension(selectedFile.name);
    if (isUploadSelectionDisabled(selectedExtension)) {
      setUploadState(
        createState<UploadedDocument>(
          'error',
          undefined,
          getFileTypeWarning(selectedExtension) ?? 'Bu dosya yüklenemez.',
        ),
      );
      return;
    }

    setUploadState(createState<UploadedDocument>('loading'));
    setExplainState(createState<ExplainResult>('idle'));
    setEvidenceState(createState<EvidenceAnswerResult>('idle'));
    setPartsState(createState<DocumentPart[]>('idle'));
    setSelectedPartId(null);

    try {
      const document = await uploadDocument(selectedFile);
      setCurrentDocument(document);
      setUploadState(createState('success', document, 'Doküman yüklendi.'));
      await loadParts(document.id);
    } catch (error) {
      const partialDocument = getDocumentFromUploadError(error, selectedFile.name);
      if (partialDocument && getApiErrorCode(error) === 'parser_not_available') {
        const message = 'Bu dosya yüklendi ancak şu anda içerik çıkarma desteği yok.';
        setCurrentDocument(partialDocument);
        setUploadState(createState('empty', partialDocument, message));
        setPartsState(createState('empty', [], message));
        return;
      }

      setUploadState(createState<UploadedDocument>('error', undefined, getApiErrorMessage(error)));
    }
  };

  const handlePartSelect = (partId: string) => {
    setSelectedPartId(partId);
    setExplainState(createState<ExplainResult>('idle'));
    setEvidenceState(createState<EvidenceAnswerResult>('idle'));
  };

  const handleRunExplain = async () => {
    if (!isAuthenticated) {
      setExplainState(createState<ExplainResult>('error', undefined, 'Önce giriş yapmalısınız.'));
      return;
    }

    if (!selectedPart) {
      setExplainState(createState<ExplainResult>('error', undefined, 'Önce bir parça seçin.'));
      return;
    }

    setExplainState(createState<ExplainResult>('loading'));
    try {
      const result = await requestExplain(selectedPart.id);
      const hasContent = Boolean(
        result.oneLiner ||
          result.verySimple ||
          result.glossary.length ||
          result.steps.length ||
          result.examples.length ||
          result.miniQuiz.length,
      );

      setExplainState(
        hasContent
          ? createState('success', result)
          : createState('empty', result, 'Bu parça için gösterilebilir açıklama dönmedi.'),
      );
    } catch (error) {
      setExplainState(createState<ExplainResult>('error', undefined, getApiErrorMessage(error)));
    }
  };

  const handleAskEvidence = async () => {
    if (!isAuthenticated) {
      setEvidenceState(createState<EvidenceAnswerResult>('error', undefined, 'Önce giriş yapmalısınız.'));
      return;
    }

    if (!evidenceQuestion.trim()) {
      setEvidenceState(createState<EvidenceAnswerResult>('error', undefined, 'Önce bir soru yazın.'));
      return;
    }

    setEvidenceState(createState<EvidenceAnswerResult>('loading'));
    try {
      const result = await requestEvidenceAnswer({
        question: evidenceQuestion.trim(),
        documentId: currentDocument?.id,
        partId: selectedPart?.id,
      });

      const hasContent = Boolean(result.answer || result.snippets.length || result.path);
      setEvidenceState(
        hasContent
          ? createState('success', result)
          : createState('empty', result, 'Bu soru için cevap veya kanıt bulunamadı.'),
      );
    } catch (error) {
      setEvidenceState(createState<EvidenceAnswerResult>('error', undefined, getApiErrorMessage(error)));
    }
  };

  return (
    <div className="min-h-screen text-slate-900">
      <Header
        navItems={navItems}
        quickActions={quickActions}
        activeActionId={activeActionId}
        onActionSelect={handleActionSelect}
        onMenuOpen={() => setIsDrawerOpen(true)}
        session={session}
        onAuthOpen={handleAuthOpen}
        onLogout={handleLogout}
      />

      <Drawer
        open={isDrawerOpen}
        navItems={navItems}
        quickActions={quickActions}
        activeActionId={activeActionId}
        onActionSelect={handleActionSelect}
        onClose={() => setIsDrawerOpen(false)}
      />

      <main className="mx-auto max-w-[1600px] px-4 pb-32 pt-6 sm:px-6 lg:px-8">
        <div className="grid gap-6 xl:grid-cols-[250px,minmax(0,1fr),320px]">
          <aside className="hidden xl:block">
            <Sidebar
              navItems={navItems}
              currentDocument={currentDocument}
              partsCount={parts.length}
              isAuthenticated={isAuthenticated}
              backendState={backendState}
              liveSectionCount={liveSectionLabels.length}
              mockSectionCount={mockSectionLabels.length}
            />
          </aside>

          <div className="space-y-6">
            <HeroSection
              backendState={backendState}
              isAuthenticated={isAuthenticated}
              username={session?.username}
              onAuthOpen={handleAuthOpen}
              selectedFile={selectedFile}
              onFileSelect={(file) => {
                if (!isAuthenticated) {
                  setSelectedFile(null);
                  setUploadState(createState('idle'));
                  return;
                }

                setSelectedFile(file);
                setUploadState(createState('idle'));
              }}
              onUploadSubmit={handleUploadSubmit}
              uploadState={uploadState}
              currentDocument={currentDocument}
              partsCount={parts.length}
              liveSectionCount={liveSectionLabels.length}
              mockSectionCount={mockSectionLabels.length}
            />
            <ReadingWorkspaceSection
              activeAction={activeAction}
              currentDocument={currentDocument}
              partsState={partsState}
              selectedPart={selectedPart}
              onPartSelect={handlePartSelect}
              onRunExplain={handleRunExplain}
              explainState={explainState}
              evidenceQuestion={evidenceQuestion}
              onEvidenceQuestionChange={(value) => {
                setEvidenceQuestion(value);
                setEvidenceState(createState('idle'));
              }}
              onAskEvidence={handleAskEvidence}
              onClearEvidence={() => {
                setEvidenceQuestion('');
                setEvidenceState(createState('idle'));
              }}
              evidenceState={evidenceState}
              isAuthenticated={isAuthenticated}
            />
            <ThemeSurveySection />
            <RemixConsoleSection />
            <DirectorsCutSection />
            <ConceptGraphSection />
            <NotesSection />
            <ChallengesSection />
            <OwnSentenceSection />
            <ProgressFlowSection />
            <InsightAccessSection
              quickActions={quickActions}
              activeActionId={activeActionId}
              onActionSelect={handleActionSelect}
            />
          </div>

          <aside className="hidden xl:block">
            <RightRail
              activeAction={activeAction}
              quickActions={quickActions}
              onActionSelect={handleActionSelect}
              backendState={backendState}
              session={session}
              currentDocument={currentDocument}
              selectedPart={selectedPart}
              liveSectionCount={liveSectionLabels.length}
              mockSectionCount={mockSectionLabels.length}
            />
          </aside>
        </div>
      </main>

      <MobileBottomActions
        quickActions={quickActions}
        activeActionId={activeActionId}
        onActionSelect={handleActionSelect}
      />
    </div>
  );
}
