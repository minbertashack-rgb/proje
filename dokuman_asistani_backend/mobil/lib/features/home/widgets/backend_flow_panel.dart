import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/state/operation_status.dart';
import '../../../core/i18n/app_localizer.dart';
import '../../../core/files/file_type_config.dart';
import '../../../services/ai_service.dart';
import '../../../services/concept_service.dart';
import '../../../services/document_service.dart';
import '../../../services/preference_service.dart';
import '../../../shared/widgets/content_blocks.dart';
import '../../../shared/widgets/section_card.dart';
import '../../../shared/widgets/status_message.dart';
import '../../../shared/widgets/language_picker.dart';
import '../../documents/data/document_part.dart';
import '../../documents/data/uploaded_document.dart';
import '../../concepts/data/concept_models.dart';
import '../../explain/data/directors_cut_response.dart';
import '../../explain/data/explain_response.dart';
import '../../explain/data/remix_response.dart';
import '../../preferences/data/learning_preferences.dart';
import '../data/upload_stage.dart';
import '../../qa/data/evidence_answer.dart';

class BackendFlowPanel extends StatefulWidget {
  const BackendFlowPanel({
    super.key,
    this.isGuest = false,
    this.username,
    this.guestMessage,
    this.onLogin,
    this.onRegister,
    this.onLogout,
    this.onUnauthorized,
    this.documentService,
    this.aiService,
    this.conceptService,
    this.preferenceService,
  });

  final bool isGuest;
  final String? username;
  final String? guestMessage;
  final VoidCallback? onLogin;
  final VoidCallback? onRegister;
  final VoidCallback? onLogout;
  final ValueChanged<String>? onUnauthorized;
  final DocumentService? documentService;
  final AiService? aiService;
  final ConceptService? conceptService;
  final PreferenceService? preferenceService;

  @override
  State<BackendFlowPanel> createState() => BackendFlowPanelState();
}

class BackendFlowPanelState extends State<BackendFlowPanel> {
  final _qaKey = GlobalKey();
  final _explainKey = GlobalKey();
  DocumentService? _documentService;
  AiService? _aiService;
  ConceptService? _conceptService;
  PreferenceService? _preferenceService;
  TextEditingController? _questionController;

  DocumentService get _documents =>
      _documentService ??= widget.documentService ?? DocumentService();
  AiService get _ai => _aiService ??= widget.aiService ?? AiService();
  ConceptService get _concepts =>
      _conceptService ??= widget.conceptService ?? ConceptService();
  PreferenceService get _preferencesService =>
      _preferenceService ??= widget.preferenceService ?? PreferenceService();
  TextEditingController get _questionInput =>
      _questionController ??= TextEditingController();

  UploadedDocument? _document;
  List<DocumentPart> _parts = const [];
  DocumentPart? _selectedPart;
  ExplainResponse? _explain;
  DirectorsCutResponse? _directorsCutResult;
  RemixResponse? _remixResult;
  EvidenceAnswer? _answer;
  LearningPreferences? _learningPreferences;
  List<ConceptItem> _partConcepts = const [];
  List<ConceptRelation> _conceptRelations = const [];
  List<ConceptMention> _conceptMentions = const [];
  ConceptItem? _selectedConcept;

  String? _selectedFilePath;
  String? _selectedFileName;
  String? _selectedFileExtension;
  FileTypeInfo? _selectedFileType;
  String? _notice;
  String? _error;
  String? _explainError;
  String? _directorsCutError;
  String? _remixError;
  String? _answerError;
  String? _conceptError;
  String? _preferencesError;
  String _evidenceQuestion = '';
  String? _selectedDirectorsCutType;
  String? _selectedRemixStyle;
  UploadStage _uploadStage = UploadStage.idle;
  bool _showEvidenceComposer = false;

  OperationStatus _pingStatus = OperationStatus.idle;
  OperationStatus _uploadStatus = OperationStatus.idle;
  OperationStatus _partsStatus = OperationStatus.idle;
  OperationStatus _explainStatus = OperationStatus.idle;
  OperationStatus _directorsCutStatus = OperationStatus.idle;
  OperationStatus _remixStatus = OperationStatus.idle;
  OperationStatus _answerStatus = OperationStatus.idle;
  OperationStatus _conceptStatus = OperationStatus.idle;
  OperationStatus _preferencesStatus = OperationStatus.idle;
  bool _unauthorizedRedirectScheduled = false;

  bool get _busy =>
      _uploadStatus.isLoading ||
      _partsStatus.isLoading ||
      _explainStatus.isLoading ||
      _directorsCutStatus.isLoading ||
      _remixStatus.isLoading ||
      _answerStatus.isLoading ||
      _conceptStatus.isLoading ||
      _preferencesStatus.isLoading;

  bool get _hasExplainResult =>
      _explainStatus == OperationStatus.success && _explain?.isEmpty == false;

  List<DocumentPart> get _hardestParts {
    final ranked = [..._parts];
    ranked.sort((a, b) {
      final scoreCompare = (b.difficultyScore ?? 0.5).compareTo(
        a.difficultyScore ?? 0.5,
      );
      return scoreCompare != 0 ? scoreCompare : a.order.compareTo(b.order);
    });
    return ranked.take(3).toList(growable: false);
  }

  @visibleForTesting
  int? get selectedPartId => _selectedPart?.id;

  @override
  void initState() {
    super.initState();
    if (kDebugMode) {
      debugPrint(
        widget.isGuest
            ? 'BackendFlowPanel init guest'
            : 'BackendFlowPanel init authenticated',
      );
    }
    if (!widget.isGuest) {
      Future<void>.microtask(loadPreferences);
    }
  }

  @override
  void dispose() {
    _questionController?.dispose();
    super.dispose();
  }

  Future<void> ping() async {
    if (_pingStatus.isLoading) return;
    setState(() {
      _pingStatus = OperationStatus.loading;
      _error = null;
      _notice = 'Bağlantı kontrol ediliyor...';
    });

    try {
      await _documents.ping();
      if (!mounted) return;
      setState(() {
        _pingStatus = OperationStatus.success;
        _notice = 'Bağlantı hazır.';
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _pingStatus = OperationStatus.error;
        _error = 'Bağlantı kontrolü başarısız oldu.';
      });
    }
  }

  Future<void> pickFile() async {
    if (_busy) return;
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: uploadExtensions,
      withData: false,
    );
    if (result == null || result.files.single.path == null) return;

    var selectedExt = normalizeFileExtension(result.files.single.extension);
    if (selectedExt.isEmpty) {
      final name = result.files.single.name.toLowerCase();
      if (name.contains('.')) {
        selectedExt = normalizeFileExtension(name.split('.').last);
      }
    }
    final fileType = fileTypeInfoForExtension(selectedExt);
    setState(() {
      _selectedFilePath = result.files.single.path;
      _selectedFileName = result.files.single.name;
      _selectedFileExtension = selectedExt.toUpperCase();
      _selectedFileType = fileType;
      _uploadStatus = OperationStatus.idle;
      _uploadStage = UploadStage.selected;
      _document = null;
      _parts = const [];
      _selectedPart = null;
      _explain = null;
      _resetDirectorsCutState();
      _resetRemixState();
      _resetConceptState();
      _answer = null;
      _learningPreferences = null;
      _explainError = null;
      _answerError = null;
      _preferencesError = null;
      _explainStatus = OperationStatus.idle;
      _answerStatus = OperationStatus.idle;
      _preferencesStatus = OperationStatus.idle;
      _partsStatus = OperationStatus.idle;
      _questionController?.clear();
      _evidenceQuestion = '';
      _showEvidenceComposer = false;
      _error = fileType.blocked
          ? AppLocalizer.of(context).t('blocked_extension')
          : !fileType.uploadAllowed
          ? AppLocalizer.of(context).t('unsupported_extension')
          : null;
      _notice = fileType.uploadAllowed && !fileType.parseSupported
          ? AppLocalizer.of(context).t('parserLimitedHint')
          : 'Dosya seçildi.';
    });
  }

  Future<void> upload() async {
    final path = _selectedFilePath;
    final fileType = _selectedFileType;
    if (path == null) {
      setState(() {
        _uploadStatus = OperationStatus.error;
        _error = 'Önce bir doküman seçmelisin.';
      });
      return;
    }
    if (fileType == null || !fileType.uploadAllowed) {
      setState(() {
        _uploadStatus = OperationStatus.error;
        _uploadStage = UploadStage.error;
        _error = fileType?.blocked == true
            ? AppLocalizer.of(context).t('blocked_extension')
            : AppLocalizer.of(context).t('unsupported_extension');
      });
      return;
    }
    if (_uploadStatus.isLoading || _partsStatus.isLoading) return;

    setState(() {
      _uploadStatus = OperationStatus.loading;
      _uploadStage = UploadStage.uploading;
      _partsStatus = OperationStatus.idle;
      _parts = const [];
      _selectedPart = null;
      _explain = null;
      _resetDirectorsCutState();
      _resetRemixState();
      _resetConceptState();
      _answer = null;
      _explainError = null;
      _answerError = null;
      _explainStatus = OperationStatus.idle;
      _answerStatus = OperationStatus.idle;
      _error = null;
      _notice = 'Doküman yükleniyor...';
    });

    try {
      Future<void>.delayed(const Duration(milliseconds: 600), () {
        if (!mounted || !_uploadStatus.isLoading) return;
        setState(() {
          _uploadStage = UploadStage.waitingResponse;
          _notice = 'Dosya gönderildi, yanıt bekleniyor...';
        });
      });
      final document = await _documents.uploadDocument(path);
      if (!mounted) return;
      setState(() {
        _document = document;
        _parts = const [];
        _selectedPart = null;
        _explain = null;
        _resetDirectorsCutState();
        _resetRemixState();
        _resetConceptState();
        _explainError = null;
        _answer = null;
        _answerError = null;
        _showEvidenceComposer = false;
        _uploadStatus = OperationStatus.success;
        _uploadStage = UploadStage.success;
        _notice = 'Doküman yüklendi.';
      });
      if (document.id <= 0) {
        setState(() {
          _partsStatus = OperationStatus.empty;
          _notice = 'Doküman yüklendi ancak parçalar alınamadı.';
        });
        return;
      }
      await loadParts(document.id);
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_upload')) return;
      setState(() {
        _uploadStatus = OperationStatus.error;
        _uploadStage = UploadStage.error;
        _error = error.message;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _uploadStatus = OperationStatus.error;
        _uploadStage = UploadStage.error;
        _error = 'Doküman yüklenirken beklenmeyen hata oluştu.';
      });
    }
  }

  Future<void> loadParts(int documentId) async {
    if (_partsStatus.isLoading) return;
    setState(() {
      _partsStatus = OperationStatus.loading;
      _error = null;
      _notice = 'Parçalar getiriliyor...';
    });

    try {
      final parts = await _documents.getDocumentParts(documentId);
      if (!mounted) return;
      setState(() {
        _parts = parts;
        _selectedPart = parts.isNotEmpty ? parts.first : null;
        _explain = null;
        _explainError = null;
        _resetDirectorsCutState();
        _resetRemixState();
        _resetConceptState();
        _answer = null;
        _answerError = null;
        _questionController?.clear();
        _evidenceQuestion = '';
        _showEvidenceComposer = false;
        _explainStatus = OperationStatus.idle;
        _answerStatus = OperationStatus.idle;
        _partsStatus = parts.isEmpty
            ? OperationStatus.empty
            : OperationStatus.success;
        _notice = parts.isEmpty
            ? 'Doküman yüklendi ancak parça bulunamadı.'
            : '${parts.length} parça hazır.';
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_parts')) return;
      setState(() {
        _partsStatus = OperationStatus.error;
        _error = 'Doküman yüklendi fakat parçalar alınamadı. Tekrar deneyin.';
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _partsStatus = OperationStatus.error;
        _error = 'Doküman yüklendi fakat parçalar alınamadı. Tekrar deneyin.';
      });
    }
  }

  Future<void> loadPreferences() async {
    if (_preferencesStatus.isLoading) return;
    setState(() {
      _preferencesStatus = OperationStatus.loading;
      _preferencesError = null;
    });
    try {
      final prefs = await _preferencesService.fetchPreferences();
      if (!mounted) return;
      setState(() {
        _learningPreferences = prefs.enabled ? prefs : null;
        _preferencesStatus = prefs.enabled
            ? OperationStatus.success
            : OperationStatus.empty;
        _preferencesError = prefs.enabled
            ? null
            : AppLocalizer.of(context).t('personalizationDisabled');
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _preferencesStatus = OperationStatus.error;
        _preferencesError = AppLocalizer.of(
          context,
        ).t('preferencesUnavailable');
      });
    }
  }

  Future<void> savePreferences(LearningPreferences preferences) async {
    if (_preferencesStatus.isLoading) return;
    setState(() {
      _preferencesStatus = OperationStatus.loading;
      _preferencesError = null;
    });
    try {
      final saved = await _preferencesService.savePreferences(preferences);
      if (!mounted) return;
      setState(() {
        _learningPreferences = saved.enabled ? saved : null;
        _preferencesStatus = OperationStatus.success;
        _notice = AppLocalizer.of(context).t('preferencesSaved');
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _preferencesStatus = OperationStatus.error;
        _preferencesError = AppLocalizer.of(
          context,
        ).t('preferencesUnavailable');
      });
    }
  }

  Future<void> explainSelectedPart() async {
    final part = _selectedPart;
    if (part == null) {
      setState(() {
        _explainStatus = OperationStatus.empty;
        _explainError = null;
        _error = null;
      });
      return;
    }
    if (_explainStatus.isLoading) return;

    setState(() {
      _explainStatus = OperationStatus.loading;
      _error = null;
      _explainError = null;
      _explain = null;
      _resetDirectorsCutState();
      _resetRemixState();
      _resetEvidenceState();
      _resetConceptState();
      _notice = 'Seçili parça açıklanıyor...';
    });
    _scrollToExplain();

    try {
      final response = await _ai.askExplain(
        partId: part.id,
        preferences: _learningPreferences,
      );
      if (!mounted) return;
      setState(() {
        _explain = response;
        _resetDirectorsCutState();
        _resetRemixState();
        _partConcepts = response.concepts;
        _conceptRelations = response.conceptRelations;
        _conceptStatus = response.concepts.isEmpty
            ? OperationStatus.idle
            : OperationStatus.success;
        _conceptError = null;
        _showEvidenceComposer = false;
        _explainStatus = response.isEmpty
            ? OperationStatus.empty
            : OperationStatus.success;
        _notice = response.isEmpty
            ? 'Bu parça için açıklama üretilemedi.'
            : 'Açıklama hazır.';
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_anlamadim')) return;
      setState(() {
        _explainStatus = OperationStatus.error;
        _explainError = error.message;
        _error = null;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _explainStatus = OperationStatus.error;
        _explainError = 'Anlatım alınamadı. Lütfen tekrar deneyin.';
        _error = null;
      });
    } finally {
      if (mounted) _scrollToExplain();
    }
  }

  Future<void> remixExplanation(String style) async {
    final part = _selectedPart;
    final explain = _explain;
    if (part == null || explain == null || explain.isEmpty) return;
    if (_remixStatus.isLoading) return;

    setState(() {
      _selectedRemixStyle = style;
      _remixStatus = OperationStatus.loading;
      _remixError = null;
      _remixResult = null;
      _notice = AppLocalizer.of(context).t('remixLoading');
    });

    try {
      final response = await _ai.requestRemix(
        partId: part.id,
        style: style,
        source: explain.toRemixSource(),
        preferences: _learningPreferences,
      );
      if (!mounted) return;
      setState(() {
        _remixResult = response;
        _remixStatus = response.isEmpty
            ? OperationStatus.empty
            : OperationStatus.success;
        _notice = response.isEmpty
            ? AppLocalizer.of(context).t('remixFailed')
            : 'Remix hazır.';
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_remix')) return;
      setState(() {
        _remixStatus = OperationStatus.error;
        _remixError = error.message;
        _error = null;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _remixStatus = OperationStatus.error;
        _remixError = AppLocalizer.of(context).t('remixFailed');
        _error = null;
      });
    }
  }

  Future<void> requestDirectorsCut(String cutType) async {
    final part = _selectedPart;
    final explain = _explain;
    if (part == null || explain == null || explain.isEmpty) return;
    if (_directorsCutStatus.isLoading) return;

    setState(() {
      _selectedDirectorsCutType = cutType;
      _directorsCutStatus = OperationStatus.loading;
      _directorsCutError = null;
      _directorsCutResult = null;
      _notice = AppLocalizer.of(context).t('directorsCutLoading');
    });

    try {
      final response = await _ai.requestDirectorsCut(
        partId: part.id,
        cutType: cutType,
        source: explain.toRemixSource(),
        preferences: _learningPreferences,
      );
      if (!mounted) return;
      setState(() {
        _directorsCutResult = response;
        _directorsCutStatus = response.isEmpty
            ? OperationStatus.empty
            : OperationStatus.success;
        _notice = response.isEmpty
            ? AppLocalizer.of(context).t('directorsCutFailed')
            : 'Director’s Cut hazır.';
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_directors_cut')) return;
      setState(() {
        _directorsCutStatus = OperationStatus.error;
        _directorsCutError = error.message;
        _error = null;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _directorsCutStatus = OperationStatus.error;
        _directorsCutError = AppLocalizer.of(context).t('directorsCutFailed');
        _error = null;
      });
    }
  }

  Future<void> askQuestion() async {
    FocusScope.of(context).unfocus();
    if (!_hasExplainResult || !_showEvidenceComposer) return;
    final document = _document;
    final part = _selectedPart;
    final question = _questionInput.text.trim();
    if (document == null) {
      setState(() {
        _answerStatus = OperationStatus.empty;
        _answerError = AppLocalizer.of(context).t('documentRequired');
        _error = null;
      });
      return;
    }
    if (question.isEmpty) {
      setState(() {
        _answerStatus = OperationStatus.empty;
        _answerError = AppLocalizer.of(context).t('questionRequired');
        _error = null;
      });
      return;
    }
    if (_answerStatus.isLoading) return;

    setState(() {
      _answerStatus = OperationStatus.loading;
      _error = null;
      _answerError = null;
      _answer = null;
      _notice = 'Kanıtlı cevap hazırlanıyor...';
    });

    try {
      final response = await _ai.askEvidenceAnswer(
        documentId: document.id,
        partId: part?.id,
        question: question,
        preferences: _learningPreferences,
      );
      if (!mounted) return;
      final hasAnswer =
          response.answer?.trim().isNotEmpty == true ||
          response.evidence.isNotEmpty;
      setState(() {
        _answer = response;
        _answerStatus = hasAnswer
            ? OperationStatus.success
            : OperationStatus.empty;
        _notice = hasAnswer
            ? 'Kanıtlı cevap hazır.'
            : 'Bu soru için cevap bulunamadı.';
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_evidence')) return;
      setState(() {
        _answerStatus = OperationStatus.error;
        _answerError = error.message;
        _error = null;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _answerStatus = OperationStatus.error;
        _answerError = AppLocalizer.of(context).t('evidence_failed');
        _error = null;
      });
    }
  }

  void focusQuestion() {
    final context = _qaKey.currentContext;
    if (context == null) return;
    Scrollable.ensureVisible(
      context,
      duration: const Duration(milliseconds: 350),
      curve: Curves.easeOut,
    );
  }

  void showPlaceholderNotice(String label) {
    setState(() {
      _error = null;
      _notice = '$label yakında burada olacak.';
    });
  }

  void clearSessionState() {
    setState(() {
      _document = null;
      _parts = const [];
      _selectedPart = null;
      _explain = null;
      _resetDirectorsCutState();
      _resetRemixState();
      _resetConceptState();
      _answer = null;
      _selectedFilePath = null;
      _selectedFileName = null;
      _selectedFileExtension = null;
      _selectedFileType = null;
      _notice = null;
      _error = null;
      _explainError = null;
      _answerError = null;
      _uploadStage = UploadStage.idle;
      _pingStatus = OperationStatus.idle;
      _uploadStatus = OperationStatus.idle;
      _partsStatus = OperationStatus.idle;
      _explainStatus = OperationStatus.idle;
      _answerStatus = OperationStatus.idle;
      _questionController?.clear();
      _evidenceQuestion = '';
      _showEvidenceComposer = false;
      _unauthorizedRedirectScheduled = false;
    });
  }

  void clearAnswer() {
    setState(() {
      _answer = null;
      _answerStatus = OperationStatus.idle;
      _questionController?.clear();
      _evidenceQuestion = '';
      _answerError = null;
      _notice = 'Yeni soru için panel temizlendi.';
      _error = null;
    });
  }

  @visibleForTesting
  void setTestDocumentAndParts({
    required UploadedDocument document,
    required List<DocumentPart> parts,
  }) {
    setState(() {
      _document = document;
      _parts = parts;
      _selectedPart = parts.isNotEmpty ? parts.first : null;
      _partsStatus = parts.isEmpty
          ? OperationStatus.empty
          : OperationStatus.success;
      _explain = null;
      _resetDirectorsCutState();
      _resetRemixState();
      _resetConceptState();
      _explainError = null;
      _explainStatus = OperationStatus.idle;
      _resetEvidenceState();
      _resetConceptState();
    });
  }

  void _resetEvidenceState() {
    _answer = null;
    _answerError = null;
    _answerStatus = OperationStatus.idle;
    _questionController?.clear();
    _evidenceQuestion = '';
    _showEvidenceComposer = false;
  }

  void _resetConceptState() {
    _partConcepts = const [];
    _conceptRelations = const [];
    _conceptMentions = const [];
    _selectedConcept = null;
    _conceptError = null;
    _conceptStatus = OperationStatus.idle;
  }

  void _resetRemixState() {
    _selectedRemixStyle = null;
    _remixResult = null;
    _remixError = null;
    _remixStatus = OperationStatus.idle;
  }

  void _resetDirectorsCutState() {
    _selectedDirectorsCutType = null;
    _directorsCutResult = null;
    _directorsCutError = null;
    _directorsCutStatus = OperationStatus.idle;
  }

  void _toggleEvidenceComposer() {
    if (!_hasExplainResult) return;
    setState(() {
      _showEvidenceComposer = !_showEvidenceComposer;
    });
  }

  void selectConcept(ConceptItem concept) {
    setState(() {
      _selectedConcept = concept;
      _conceptMentions = const [];
      _conceptError = null;
    });
  }

  Future<void> loadConceptMentions(ConceptItem concept) async {
    final document = _document;
    if (document == null || concept.term.trim().isEmpty) return;
    setState(() {
      _selectedConcept = concept;
      _conceptStatus = OperationStatus.loading;
      _conceptError = null;
      _conceptMentions = const [];
    });
    try {
      final response = await _concepts.searchConceptMentions(
        document.id,
        concept.term,
      );
      if (!mounted) return;
      setState(() {
        _selectedConcept = response.concept ?? concept;
        _conceptMentions = response.mentions;
        _conceptStatus = response.mentions.isEmpty
            ? OperationStatus.empty
            : OperationStatus.success;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_concepts')) return;
      setState(() {
        _conceptStatus = OperationStatus.error;
        _conceptError = error.message;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _conceptStatus = OperationStatus.error;
        _conceptError = AppLocalizer.of(context).t('conceptsFailed');
      });
    }
  }

  void goToMention(ConceptMention mention) {
    DocumentPart? nextPart;
    for (final part in _parts) {
      if (part.id == mention.partId) {
        nextPart = part;
        break;
      }
    }
    if (nextPart == null) return;
    setState(() {
      _selectedPart = nextPart;
      _explain = null;
      _explainError = null;
      _explainStatus = OperationStatus.idle;
      _resetDirectorsCutState();
      _resetRemixState();
      _resetEvidenceState();
      _resetConceptState();
      _notice = 'Parça seçildi.';
    });
  }

  bool _handleUnauthorized(ApiException error, String reason) {
    if (!error.isUnauthorized) return false;
    setState(() {
      _error = AppLocalizer.of(context).t('sessionExpired');
      _notice = AppLocalizer.of(context).t('sessionExpired');
    });
    if (!_unauthorizedRedirectScheduled) {
      _unauthorizedRedirectScheduled = true;
      Future<void>.delayed(const Duration(milliseconds: 900), () {
        if (!mounted) return;
        widget.onUnauthorized?.call(reason);
      });
    }
    return true;
  }

  void _scrollToExplain() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final context = _explainKey.currentContext;
      if (!mounted || context == null) return;
      Scrollable.ensureVisible(
        context,
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeOut,
        alignment: 0.08,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    if (widget.isGuest) {
      return _GuestUploadSection(
        message: widget.guestMessage,
        onLogin: widget.onLogin,
        onRegister: widget.onRegister,
      );
    }

    return Column(
      children: [
        if (_notice != null) StatusMessage(message: _notice!),
        if (_error != null) ...[
          const SizedBox(height: 12),
          StatusMessage(message: _error!, isError: true),
        ],
        const SizedBox(height: 14),
        _StatusSection(
          username: widget.username,
          pingStatus: _pingStatus,
          document: _document,
          partsCount: _parts.length,
          onPing: ping,
          onLogout: widget.onLogout,
        ),
        if (_preferencesStatus != OperationStatus.empty ||
            _preferencesError != null ||
            _learningPreferences != null) ...[
          const SizedBox(height: 14),
          _LearningPreferencesSection(
            preferences: _learningPreferences ?? const LearningPreferences(),
            status: _preferencesStatus,
            errorMessage: _preferencesError,
            onSave: savePreferences,
          ),
        ],
        const SizedBox(height: 14),
        _UploadSection(
          fileName: _selectedFileName,
          extension: _selectedFileExtension,
          fileType: _selectedFileType,
          status: _uploadStatus,
          stage: _uploadStage,
          onPick: pickFile,
          onUpload: upload,
        ),
        const SizedBox(height: 14),
        _DocumentSection(
          document: _document,
          parts: _parts,
          hardestParts: _hardestParts,
          selectedPart: _selectedPart,
          status: _partsStatus,
          explainStatus: _explainStatus,
          onReload: _document == null ? null : () => loadParts(_document!.id),
          onSelect: (part) => setState(() {
            _selectedPart = part;
            _explain = null;
            _resetDirectorsCutState();
            _resetRemixState();
            _resetConceptState();
            _explainError = null;
            _explainStatus = OperationStatus.idle;
            _resetEvidenceState();
          }),
          onStartHardPart: (part) => setState(() {
            _selectedPart = part;
            _explain = null;
            _resetDirectorsCutState();
            _resetRemixState();
            _resetConceptState();
            _explainError = null;
            _explainStatus = OperationStatus.idle;
            _resetEvidenceState();
          }),
          onExplain: explainSelectedPart,
        ),
        const SizedBox(height: 14),
        _ExplainSection(
          key: _explainKey,
          response: _explain,
          status: _explainStatus,
          errorMessage: _explainError,
          hasSelectedPart: _selectedPart != null,
          evidenceKey: _qaKey,
          controller: _questionInput,
          question: _evidenceQuestion,
          answer: _answer,
          concepts: _partConcepts,
          conceptRelations: _conceptRelations,
          selectedConcept: _selectedConcept,
          conceptMentions: _conceptMentions,
          conceptStatus: _conceptStatus,
          conceptErrorMessage: _conceptError,
          directorsCutResult: _directorsCutResult,
          selectedDirectorsCutType: _selectedDirectorsCutType,
          directorsCutStatus: _directorsCutStatus,
          directorsCutErrorMessage: _directorsCutError,
          remixResult: _remixResult,
          selectedRemixStyle: _selectedRemixStyle,
          remixStatus: _remixStatus,
          remixErrorMessage: _remixError,
          answerStatus: _answerStatus,
          answerErrorMessage: _answerError,
          hasDocument: _document != null,
          showEvidenceComposer: _showEvidenceComposer,
          onQuestionChanged: (value) => setState(() {
            _evidenceQuestion = value;
          }),
          onToggleEvidenceComposer: _toggleEvidenceComposer,
          onSelectConcept: selectConcept,
          onShowConceptMentions: loadConceptMentions,
          onGoToMention: goToMention,
          onDirectorsCut: requestDirectorsCut,
          onRemix: remixExplanation,
          onAsk: askQuestion,
          onClear: clearAnswer,
        ),
      ],
    );
  }
}

class _StatusSection extends StatelessWidget {
  const _StatusSection({
    required this.username,
    required this.pingStatus,
    required this.document,
    required this.partsCount,
    required this.onPing,
    required this.onLogout,
  });

  final String? username;
  final OperationStatus pingStatus;
  final UploadedDocument? document;
  final int partsCount;
  final VoidCallback onPing;
  final VoidCallback? onLogout;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    final connectionLabel = switch (pingStatus) {
      OperationStatus.success => 'Bağlantı hazır',
      OperationStatus.loading => 'Kontrol ediliyor',
      OperationStatus.error => 'Bağlantı kontrol edilemedi',
      _ => 'Kontrol bekliyor',
    };

    return SectionCard(
      title: username?.isNotEmpty == true ? username! : 'Oturum açık',
      subtitle: 'Çalışma alanı',
      icon: Icons.person_outline_rounded,
      child: Column(
        children: [
          _InfoRow(
            icon: Icons.monitor_heart_outlined,
            label: 'Backend',
            value: connectionLabel,
          ),
          _InfoRow(
            icon: Icons.description_outlined,
            label: 'Aktif doküman',
            value: document?.title ?? 'Henüz doküman yok',
          ),
          _InfoRow(
            icon: Icons.segment_outlined,
            label: 'Parça sayısı',
            value: '$partsCount',
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: pingStatus.isLoading ? null : onPing,
                  icon: pingStatus.isLoading
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.refresh_rounded),
                  label: const Text('Bağlantıyı kontrol et'),
                ),
              ),
              const SizedBox(width: 10),
              IconButton.filledTonal(
                tooltip: localizer.t('signOut'),
                onPressed: onLogout,
                icon: const Icon(Icons.logout_rounded),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          Icon(icon, size: 18, color: const Color(0xFF667085)),
          const SizedBox(width: 8),
          Text(
            label,
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: const Color(0xFF667085)),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              value,
              textAlign: TextAlign.right,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
          ),
        ],
      ),
    );
  }
}

class _GuestUploadSection extends StatelessWidget {
  const _GuestUploadSection({
    required this.message,
    required this.onLogin,
    required this.onRegister,
  });

  final String? message;
  final VoidCallback? onLogin;
  final VoidCallback? onRegister;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    return SectionCard(
      title: localizer.t('uploadDocument'),
      subtitle: localizer.t('guestUploadDescription'),
      icon: Icons.upload_file_rounded,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const LanguagePicker(),
          const SizedBox(height: 12),
          if (message != null && message!.isNotEmpty) ...[
            StatusMessage(message: message!, isError: true),
            const SizedBox(height: 12),
          ],
          Row(
            children: [
              Expanded(
                child: FilledButton.icon(
                  onPressed: onLogin,
                  icon: const Icon(Icons.login_rounded),
                  label: Text(localizer.t('signIn')),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: onRegister,
                  icon: const Icon(Icons.person_add_alt_1_rounded),
                  label: Text(localizer.t('register')),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _LearningPreferencesSection extends StatefulWidget {
  const _LearningPreferencesSection({
    required this.preferences,
    required this.status,
    required this.errorMessage,
    required this.onSave,
  });

  final LearningPreferences preferences;
  final OperationStatus status;
  final String? errorMessage;
  final ValueChanged<LearningPreferences> onSave;

  @override
  State<_LearningPreferencesSection> createState() =>
      _LearningPreferencesSectionState();
}

class _LearningPreferencesSectionState
    extends State<_LearningPreferencesSection> {
  late LearningPreferences _draft;

  @override
  void initState() {
    super.initState();
    _draft = widget.preferences;
  }

  @override
  void didUpdateWidget(covariant _LearningPreferencesSection oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.preferences != widget.preferences) {
      _draft = widget.preferences;
    }
  }

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    return SectionCard(
      title: localizer.t('learningPreferences'),
      subtitle: localizer.t('learningPreferencesDescription'),
      icon: Icons.tune_rounded,
      child: Column(
        children: [
          _PreferenceDropdown(
            label: localizer.t('theme'),
            value: _draft.theme,
            values: const [
              'default',
              'spor',
              'yemek',
              'oyun',
              'teknoloji',
              'film_dizi',
              'muzik',
              'tarih',
              'bilim',
              'saglik',
              'is_dunyasi',
            ],
            labelFor: (value) => localizer.t(_themeKey(value)),
            onChanged: (value) => setState(() {
              _draft = _draft.copyWith(theme: value);
            }),
          ),
          const SizedBox(height: 10),
          _PreferenceDropdown(
            label: localizer.t('explanationStyle'),
            value: _draft.explanationStyle,
            values: const [
              'kisa',
              'adim_adim',
              'bol_ornek',
              'hafif_mizah',
              'ciddi',
              'sinav_odakli',
              'sohbet',
            ],
            labelFor: (value) => localizer.t(_styleKey(value)),
            onChanged: (value) => setState(() {
              _draft = _draft.copyWith(explanationStyle: value);
            }),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: _PreferenceDropdown(
                  label: localizer.t('level'),
                  value: _draft.level,
                  values: const ['baslangic', 'orta', 'ileri'],
                  labelFor: (value) => localizer.t(_levelKey(value)),
                  onChanged: (value) => setState(() {
                    _draft = _draft.copyWith(level: value);
                  }),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _PreferenceDropdown(
                  label: localizer.t('exampleDensity'),
                  value: _draft.exampleDensity,
                  values: const ['az', 'normal', 'cok'],
                  labelFor: (value) => localizer.t(_densityKey(value)),
                  onChanged: (value) => setState(() {
                    _draft = _draft.copyWith(exampleDensity: value);
                  }),
                ),
              ),
            ],
          ),
          if (widget.errorMessage != null) ...[
            const SizedBox(height: 10),
            StatusMessage(message: widget.errorMessage!, isError: true),
          ],
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: widget.status.isLoading
                  ? null
                  : () => widget.onSave(_draft),
              icon: widget.status.isLoading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.save_outlined),
              label: Text(localizer.t('savePreferences')),
            ),
          ),
        ],
      ),
    );
  }

  static String _themeKey(String value) => switch (value) {
    'spor' => 'themeSport',
    'yemek' => 'themeFood',
    'oyun' => 'themeGaming',
    'teknoloji' => 'themeTechnology',
    'film_dizi' => 'themeMovieSeries',
    'muzik' => 'themeMusic',
    'tarih' => 'themeHistory',
    'bilim' => 'themeScience',
    'saglik' => 'themeHealth',
    'is_dunyasi' => 'themeBusiness',
    _ => 'themeDefault',
  };

  static String _styleKey(String value) => switch (value) {
    'kisa' => 'styleShort',
    'bol_ornek' => 'styleManyExamples',
    'hafif_mizah' => 'styleLightHumor',
    'ciddi' => 'styleSerious',
    'sinav_odakli' => 'styleExamFocused',
    'sohbet' => 'styleConversation',
    _ => 'styleStepByStep',
  };

  static String _levelKey(String value) => switch (value) {
    'orta' => 'levelIntermediate',
    'ileri' => 'levelAdvanced',
    _ => 'levelBeginner',
  };

  static String _densityKey(String value) => switch (value) {
    'az' => 'densityLow',
    'cok' => 'densityHigh',
    _ => 'densityNormal',
  };
}

class _PreferenceDropdown extends StatelessWidget {
  const _PreferenceDropdown({
    required this.label,
    required this.value,
    required this.values,
    required this.labelFor,
    required this.onChanged,
  });

  final String label;
  final String value;
  final List<String> values;
  final String Function(String) labelFor;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return DropdownButtonFormField<String>(
      initialValue: values.contains(value) ? value : values.first,
      decoration: InputDecoration(labelText: label),
      items: [
        for (final item in values)
          DropdownMenuItem(value: item, child: Text(labelFor(item))),
      ],
      onChanged: (value) {
        if (value != null) onChanged(value);
      },
    );
  }
}

class _UploadSection extends StatelessWidget {
  const _UploadSection({
    required this.fileName,
    required this.extension,
    required this.fileType,
    required this.status,
    required this.stage,
    required this.onPick,
    required this.onUpload,
  });

  final String? fileName;
  final String? extension;
  final FileTypeInfo? fileType;
  final OperationStatus status;
  final UploadStage stage;
  final VoidCallback onPick;
  final VoidCallback onUpload;

  @override
  Widget build(BuildContext context) {
    final loading = status.isLoading;
    final localizer = AppLocalizer.of(context);
    return SectionCard(
      title: localizer.t('uploadDocument'),
      subtitle: fileName == null ? 'PDF, DOCX, DOC veya TXT seç' : null,
      icon: Icons.upload_file_rounded,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _UploadStageIndicator(stage: stage, loading: loading),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              const Chip(label: Text('PDF')),
              const Chip(label: Text('Word')),
              const Chip(label: Text('Excel')),
              const Chip(label: Text('Kod')),
              const Chip(label: Text('Görsel/OCR')),
              const Chip(label: Text('Arşiv')),
              if (extension != null) Chip(label: Text('Seçili: $extension')),
              if (fileType != null) Chip(label: Text(fileType!.category)),
            ],
          ),
          if (fileName != null) ...[
            const SizedBox(height: 12),
            _SelectedFileBox(fileName: fileName!, extension: extension),
          ],
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: loading ? null : onPick,
            icon: const Icon(Icons.folder_open_rounded),
            label: Text(
              fileName == null
                  ? localizer.t('selectFile')
                  : localizer.t('changeFile'),
            ),
          ),
          const SizedBox(height: 10),
          FilledButton.icon(
            onPressed:
                loading || fileName == null || fileType?.uploadAllowed == false
                ? null
                : onUpload,
            icon: loading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.cloud_upload_outlined),
            label: Text(
              loading
                  ? localizer.t('loading')
                  : stage == UploadStage.error
                  ? localizer.t('tryAgain')
                  : localizer.t('uploadAndFetchParts'),
            ),
          ),
          if (fileType != null &&
              fileType!.uploadAllowed &&
              !fileType!.parseSupported) ...[
            const SizedBox(height: 12),
            _InlineState(
              icon: Icons.info_outline_rounded,
              message: localizer.t('parserLimitedHint'),
            ),
          ],
          if (fileType != null && !fileType!.uploadAllowed) ...[
            const SizedBox(height: 12),
            _InlineState(
              icon: Icons.block_rounded,
              message: fileType!.blocked
                  ? localizer.t('blocked_extension')
                  : localizer.t('unsupported_extension'),
              error: true,
            ),
          ],
          if (status == OperationStatus.success) ...[
            const SizedBox(height: 12),
            const _InlineState(
              icon: Icons.check_circle_outline_rounded,
              message: 'Yükleme tamamlandı, parçalar hazırlandı.',
              success: true,
            ),
          ],
          if (status == OperationStatus.error) ...[
            const SizedBox(height: 12),
            const _InlineState(
              icon: Icons.error_outline_rounded,
              message: 'Yükleme tamamlanamadı. Tekrar deneyebilirsin.',
              error: true,
            ),
          ],
        ],
      ),
    );
  }
}

class _SelectedFileBox extends StatelessWidget {
  const _SelectedFileBox({required this.fileName, required this.extension});

  final String fileName;
  final String? extension;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFF8FAFC),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE5EAF1)),
      ),
      child: Row(
        children: [
          const Icon(Icons.insert_drive_file_outlined, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              fileName,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
          ),
          if (extension != null && extension!.isNotEmpty) ...[
            const SizedBox(width: 8),
            Chip(label: Text(extension!)),
          ],
        ],
      ),
    );
  }
}

class _InlineState extends StatelessWidget {
  const _InlineState({
    required this.icon,
    required this.message,
    this.success = false,
    this.error = false,
  });

  final IconData icon;
  final String message;
  final bool success;
  final bool error;

  @override
  Widget build(BuildContext context) {
    final color = error
        ? const Color(0xFFB42318)
        : success
        ? const Color(0xFF047857)
        : const Color(0xFF475467);
    final background = error
        ? const Color(0xFFFFF0F0)
        : success
        ? const Color(0xFFECFDF3)
        : const Color(0xFFF8FAFC);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withAlpha(55)),
      ),
      child: Row(
        children: [
          Icon(icon, size: 18, color: color),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              message,
              style: TextStyle(color: color, fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }
}

class _UploadStageIndicator extends StatelessWidget {
  const _UploadStageIndicator({required this.stage, required this.loading});

  final UploadStage stage;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFF8FAFC),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE5EAF1)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                stage == UploadStage.error
                    ? Icons.error_outline_rounded
                    : stage == UploadStage.success
                    ? Icons.check_circle_outline_rounded
                    : Icons.cloud_upload_outlined,
                size: 18,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  stage.label,
                  style: const TextStyle(fontWeight: FontWeight.w800),
                ),
              ),
            ],
          ),
          if (loading) ...[
            const SizedBox(height: 10),
            const LinearProgressIndicator(),
          ],
        ],
      ),
    );
  }
}

class _DocumentSection extends StatelessWidget {
  const _DocumentSection({
    required this.document,
    required this.parts,
    required this.hardestParts,
    required this.selectedPart,
    required this.status,
    required this.explainStatus,
    required this.onReload,
    required this.onSelect,
    required this.onStartHardPart,
    required this.onExplain,
  });

  final UploadedDocument? document;
  final List<DocumentPart> parts;
  final List<DocumentPart> hardestParts;
  final DocumentPart? selectedPart;
  final OperationStatus status;
  final OperationStatus explainStatus;
  final VoidCallback? onReload;
  final ValueChanged<DocumentPart> onSelect;
  final ValueChanged<DocumentPart> onStartHardPart;
  final VoidCallback onExplain;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    return SectionCard(
      title: 'Parça listesi',
      subtitle: document == null
          ? 'Yükleme sonrası parçalar burada görünür'
          : '${parts.length} parça',
      icon: Icons.article_outlined,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (status.isLoading) ...[
            const LinearProgressIndicator(),
            const SizedBox(height: 12),
            const Text('Parçalar hazırlanıyor...'),
          ] else if (status == OperationStatus.error) ...[
            const _InlineState(
              icon: Icons.error_outline_rounded,
              message: 'Parçalar alınamadı. Tekrar deneyebilirsin.',
              error: true,
            ),
          ] else if (parts.isEmpty) ...[
            const _InlineState(
              icon: Icons.info_outline_rounded,
              message: 'Henüz parça yok. Doküman yükleyince burada listelenir.',
            ),
          ],
          if (parts.isNotEmpty)
            _HardestSectionsCard(
              parts: hardestParts,
              selectedPart: selectedPart,
              onSelect: onStartHardPart,
            ),
          if (parts.isNotEmpty) const SizedBox(height: 10),
          if (parts.isNotEmpty)
            ...parts.asMap().entries.map((entry) {
              final index = entry.key;
              final part = entry.value;
              final selected = selectedPart?.id == part.id;
              return _PartCard(
                part: part,
                index: index,
                selected: selected,
                onTap: () => onSelect(part),
              );
            }),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: onReload,
                  icon: const Icon(Icons.refresh_rounded),
                  label: Text(localizer.t('refreshParts')),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: FilledButton.icon(
                  onPressed: selectedPart == null || explainStatus.isLoading
                      ? null
                      : onExplain,
                  icon: explainStatus.isLoading
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.lightbulb_outline_rounded),
                  label: Text(AppLocalizer.of(context).t('iDontUnderstand')),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _PartCard extends StatelessWidget {
  const _PartCard({
    required this.part,
    required this.index,
    required this.selected,
    required this.onTap,
  });

  final DocumentPart part;
  final int index;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    final label = part.order == 0 ? index + 1 : part.order;
    final preview = part.text.isEmpty
        ? 'Bu parça için metin dönmedi.'
        : part.text;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: selected ? const Color(0xFFEFF6FF) : const Color(0xFFF8FAFC),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: selected
                  ? const Color(0xFF276EF1)
                  : const Color(0xFFE5EAF1),
              width: selected ? 1.4 : 1,
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      part.title?.isNotEmpty == true
                          ? part.title!
                          : 'Parça $label',
                      style: const TextStyle(fontWeight: FontWeight.w800),
                    ),
                  ),
                  if (selected)
                    const Icon(
                      Icons.check_circle_rounded,
                      size: 18,
                      color: Color(0xFF276EF1),
                    ),
                  const SizedBox(width: 8),
                  _DifficultyBadge(part: part),
                ],
              ),
              if (part.difficultyReasons.isNotEmpty) ...[
                const SizedBox(height: 6),
                Text(
                  '${localizer.t('whyHard')} ${part.difficultyReasons.first}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: const Color(0xFF475569),
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
              if (selected) ...[
                const SizedBox(height: 4),
                Text(
                  localizer.t('selectedPart'),
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: const Color(0xFF276EF1),
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
              const SizedBox(height: 6),
              Text(
                preview,
                maxLines: selected ? 8 : 3,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(height: 1.35),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _HardestSectionsCard extends StatelessWidget {
  const _HardestSectionsCard({
    required this.parts,
    required this.selectedPart,
    required this.onSelect,
  });

  final List<DocumentPart> parts;
  final DocumentPart? selectedPart;
  final ValueChanged<DocumentPart> onSelect;

  @override
  Widget build(BuildContext context) {
    if (parts.isEmpty) return const SizedBox.shrink();
    final localizer = AppLocalizer.of(context);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: const Color(0xFFFFFBEB),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFFFDE68A)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                const Icon(
                  Icons.map_outlined,
                  size: 18,
                  color: Color(0xFF92400E),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    localizer.t('hardestSections'),
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              localizer.t('hardestSectionsDescription'),
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: const Color(0xFF713F12)),
            ),
            const SizedBox(height: 8),
            ...parts.map((part) {
              final selected = selectedPart?.id == part.id;
              final title = part.title?.isNotEmpty == true
                  ? part.title!
                  : 'Parça ${part.order}';
              return Padding(
                padding: const EdgeInsets.only(top: 6),
                child: OutlinedButton(
                  onPressed: () => onSelect(part),
                  style: OutlinedButton.styleFrom(
                    alignment: Alignment.centerLeft,
                    padding: const EdgeInsets.symmetric(
                      horizontal: 10,
                      vertical: 10,
                    ),
                    side: BorderSide(
                      color: selected
                          ? const Color(0xFF276EF1)
                          : const Color(0xFFFBBF24),
                    ),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              title,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                            if (part.difficultyReasons.isNotEmpty) ...[
                              const SizedBox(height: 2),
                              Text(
                                part.difficultyReasons.first,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: Theme.of(context).textTheme.labelSmall,
                              ),
                            ],
                          ],
                        ),
                      ),
                      const SizedBox(width: 8),
                      _DifficultyBadge(part: part),
                      const SizedBox(width: 8),
                      Text(
                        localizer.t('startWithThisPart'),
                        style: Theme.of(context).textTheme.labelSmall?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ),
              );
            }),
          ],
        ),
      ),
    );
  }
}

class _DifficultyBadge extends StatelessWidget {
  const _DifficultyBadge({required this.part});

  final DocumentPart part;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    final normalized = part.difficultyLabel.trim().toLowerCase();
    final (textKey, foreground, background) = switch (normalized) {
      'zor' || 'hard' => (
        'difficultyHard',
        const Color(0xFF991B1B),
        const Color(0xFFFEE2E2),
      ),
      'kolay' || 'easy' => (
        'difficultyEasy',
        const Color(0xFF166534),
        const Color(0xFFDCFCE7),
      ),
      _ => (
        'difficultyMedium',
        const Color(0xFF92400E),
        const Color(0xFFFEF3C7),
      ),
    };
    return DecoratedBox(
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        child: Text(
          localizer.t(textKey),
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
            color: foreground,
            fontWeight: FontWeight.w800,
          ),
        ),
      ),
    );
  }
}

class _ExplainSection extends StatelessWidget {
  const _ExplainSection({
    super.key,
    required this.response,
    required this.status,
    required this.errorMessage,
    required this.hasSelectedPart,
    required this.evidenceKey,
    required this.controller,
    required this.question,
    required this.answer,
    required this.concepts,
    required this.conceptRelations,
    required this.selectedConcept,
    required this.conceptMentions,
    required this.conceptStatus,
    required this.conceptErrorMessage,
    required this.directorsCutResult,
    required this.selectedDirectorsCutType,
    required this.directorsCutStatus,
    required this.directorsCutErrorMessage,
    required this.remixResult,
    required this.selectedRemixStyle,
    required this.remixStatus,
    required this.remixErrorMessage,
    required this.answerStatus,
    required this.answerErrorMessage,
    required this.hasDocument,
    required this.showEvidenceComposer,
    required this.onQuestionChanged,
    required this.onToggleEvidenceComposer,
    required this.onSelectConcept,
    required this.onShowConceptMentions,
    required this.onGoToMention,
    required this.onDirectorsCut,
    required this.onRemix,
    required this.onAsk,
    required this.onClear,
  });

  final ExplainResponse? response;
  final OperationStatus status;
  final String? errorMessage;
  final bool hasSelectedPart;
  final Key evidenceKey;
  final TextEditingController controller;
  final String question;
  final EvidenceAnswer? answer;
  final List<ConceptItem> concepts;
  final List<ConceptRelation> conceptRelations;
  final ConceptItem? selectedConcept;
  final List<ConceptMention> conceptMentions;
  final OperationStatus conceptStatus;
  final String? conceptErrorMessage;
  final DirectorsCutResponse? directorsCutResult;
  final String? selectedDirectorsCutType;
  final OperationStatus directorsCutStatus;
  final String? directorsCutErrorMessage;
  final RemixResponse? remixResult;
  final String? selectedRemixStyle;
  final OperationStatus remixStatus;
  final String? remixErrorMessage;
  final OperationStatus answerStatus;
  final String? answerErrorMessage;
  final bool hasDocument;
  final bool showEvidenceComposer;
  final ValueChanged<String> onQuestionChanged;
  final VoidCallback onToggleEvidenceComposer;
  final ValueChanged<ConceptItem> onSelectConcept;
  final ValueChanged<ConceptItem> onShowConceptMentions;
  final ValueChanged<ConceptMention> onGoToMention;
  final ValueChanged<String> onDirectorsCut;
  final ValueChanged<String> onRemix;
  final VoidCallback onAsk;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final data = response;
    final localizer = AppLocalizer.of(context);
    final visibleConcepts = concepts.isNotEmpty
        ? concepts
        : data?.terms
              .map(
                (term) => ConceptItem(
                  id: term.toLowerCase().replaceAll(RegExp(r'\s+'), '-'),
                  term: term,
                  definition: localizer.t('conceptNotFound'),
                ),
              )
              .toList(growable: false) ??
              const <ConceptItem>[];
    return SectionCard(
      title: localizer.t('iDontUnderstand'),
      subtitle: 'Seçili parçayı daha sade bir dille açıkla',
      icon: Icons.psychology_alt_outlined,
      child: status.isLoading
          ? const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                LinearProgressIndicator(),
                SizedBox(height: 12),
                Text('Açıklama hazırlanıyor...'),
              ],
            )
          : status == OperationStatus.error
          ? StatusMessage(
              message:
                  errorMessage ?? 'Anlatım alınamadı. Lütfen tekrar deneyin.',
              isError: true,
            )
          : status == OperationStatus.empty
          ? const _InlineState(
              icon: Icons.info_outline_rounded,
              message:
                  'Bu parça için açıklama üretilemedi. Lütfen tekrar deneyin veya başka bir parça seçin.',
            )
          : data == null
          ? _InlineState(
              icon: Icons.touch_app_outlined,
              message: hasSelectedPart
                  ? 'Seçili parça için açıklama isteyebilirsin.'
                  : 'Önce listeden bir parça seç.',
            )
          : data.isEmpty
          ? const _InlineState(
              icon: Icons.info_outline_rounded,
              message:
                  'Bu parça için açıklama üretilemedi. Lütfen tekrar deneyin veya başka bir parça seçin.',
            )
          : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (data.oneSentence != null)
                  TextBlock(title: 'Kısa özet', text: data.oneSentence!),
                if (data.simpleExplanation != null)
                  TextBlock(
                    title: 'Basit anlatım',
                    text: data.simpleExplanation!,
                  ),
                if (data.rawExplanation != null)
                  TextBlock(title: 'Açıklama', text: data.rawExplanation!),
                _TermBubbleBlock(
                  concepts: visibleConcepts,
                  onSelect: onSelectConcept,
                  selectedConcept: selectedConcept,
                ),
                NumberedListBlock(
                  title: localizer.t('stepByStep'),
                  items: data.steps,
                ),
                CardListBlock(
                  title: localizer.t('examples'),
                  items: data.examples,
                ),
                CardListBlock(title: localizer.t('miniQuiz'), items: data.quiz),
                CardListBlock(
                  title: localizer.t('evidence'),
                  items: data.evidence,
                ),
                CardListBlock(
                  title: localizer.t('personalExamples'),
                  items: data.themedExamples,
                ),
                const SizedBox(height: 14),
                _ConceptMapPanel(
                  concepts: visibleConcepts,
                  relations: conceptRelations,
                  selectedConcept: selectedConcept,
                  mentions: conceptMentions,
                  status: conceptStatus,
                  errorMessage: conceptErrorMessage,
                  onSelectConcept: onSelectConcept,
                  onShowMentions: onShowConceptMentions,
                  onGoToMention: onGoToMention,
                ),
                const SizedBox(height: 14),
                _DirectorsCutPanel(
                  selectedCutType: selectedDirectorsCutType,
                  status: directorsCutStatus,
                  result: directorsCutResult,
                  errorMessage: directorsCutErrorMessage,
                  onDirectorsCut: onDirectorsCut,
                ),
                const SizedBox(height: 14),
                _RemixConsolePanel(
                  selectedStyle: selectedRemixStyle,
                  status: remixStatus,
                  result: remixResult,
                  errorMessage: remixErrorMessage,
                  onRemix: onRemix,
                ),
                const SizedBox(height: 14),
                _EvidenceFollowupPanel(
                  key: evidenceKey,
                  controller: controller,
                  question: question,
                  answer: answer,
                  status: answerStatus,
                  errorMessage: answerErrorMessage,
                  hasDocument: hasDocument,
                  showComposer: showEvidenceComposer,
                  onQuestionChanged: onQuestionChanged,
                  onToggleComposer: onToggleEvidenceComposer,
                  onAsk: onAsk,
                  onClear: onClear,
                ),
              ],
            ),
    );
  }
}

class _TermBubbleBlock extends StatelessWidget {
  const _TermBubbleBlock({
    required this.concepts,
    required this.selectedConcept,
    required this.onSelect,
  });

  final List<ConceptItem> concepts;
  final ConceptItem? selectedConcept;
  final ValueChanged<ConceptItem> onSelect;

  @override
  Widget build(BuildContext context) {
    if (concepts.isEmpty) return const SizedBox.shrink();
    final localizer = AppLocalizer.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            localizer.t('terms'),
            style: Theme.of(
              context,
            ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final concept in concepts)
                ActionChip(
                  label: Text(concept.term),
                  avatar: const Icon(Icons.bubble_chart_outlined, size: 18),
                  onPressed: () => onSelect(concept),
                ),
            ],
          ),
          if (selectedConcept != null) ...[
            const SizedBox(height: 10),
            _ConceptDetailCard(concept: selectedConcept!),
          ],
        ],
      ),
    );
  }
}

class _ConceptDetailCard extends StatelessWidget {
  const _ConceptDetailCard({required this.concept});

  final ConceptItem concept;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    final definition = concept.definition.trim().isNotEmpty
        ? concept.definition
        : 'Bu terim seçili parçada geçen önemli bir kavramdır.';
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              concept.term,
              style: Theme.of(
                context,
              ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 6),
            Text('${localizer.t('conceptDefinition')}: $definition'),
            if (concept.example.trim().isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(concept.example),
            ],
            if (concept.path.trim().isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(concept.path, style: Theme.of(context).textTheme.bodySmall),
            ],
          ],
        ),
      ),
    );
  }
}

class _ConceptMapPanel extends StatelessWidget {
  const _ConceptMapPanel({
    required this.concepts,
    required this.relations,
    required this.selectedConcept,
    required this.mentions,
    required this.status,
    required this.errorMessage,
    required this.onSelectConcept,
    required this.onShowMentions,
    required this.onGoToMention,
  });

  final List<ConceptItem> concepts;
  final List<ConceptRelation> relations;
  final ConceptItem? selectedConcept;
  final List<ConceptMention> mentions;
  final OperationStatus status;
  final String? errorMessage;
  final ValueChanged<ConceptItem> onSelectConcept;
  final ValueChanged<ConceptItem> onShowMentions;
  final ValueChanged<ConceptMention> onGoToMention;

  @override
  Widget build(BuildContext context) {
    if (concepts.isEmpty && relations.isEmpty) return const SizedBox.shrink();
    final localizer = AppLocalizer.of(context);
    final selected = selectedConcept ?? concepts.first;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(
          context,
        ).colorScheme.surfaceContainerHighest.withValues(alpha: 0.35),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Icon(
                  Icons.account_tree_outlined,
                  color: Theme.of(context).colorScheme.primary,
                ),
                const SizedBox(width: 10),
                Text(
                  localizer.t('conceptMap'),
                  style: Theme.of(
                    context,
                  ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final concept in concepts.take(10))
                  ChoiceChip(
                    label: Text(concept.term),
                    selected: selected.id == concept.id,
                    onSelected: (_) => onSelectConcept(concept),
                  ),
              ],
            ),
            if (relations.isNotEmpty) ...[
              const SizedBox(height: 12),
              for (final relation in relations.take(5))
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.link_rounded),
                    title: Text('${relation.source} → ${relation.target}'),
                    subtitle: Text(
                      relation.reason.isNotEmpty
                          ? relation.reason
                          : relation.relation,
                    ),
                  ),
                ),
            ],
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: OutlinedButton.icon(
                onPressed: status.isLoading ? null : () => onShowMentions(selected),
                icon: status.isLoading
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.manage_search_rounded),
                label: Text(localizer.t('whereThisConceptAppears')),
              ),
            ),
            if (status == OperationStatus.error) ...[
              const SizedBox(height: 8),
              StatusMessage(
                message: errorMessage ?? localizer.t('conceptsFailed'),
                isError: true,
              ),
            ],
            if (mentions.isNotEmpty) ...[
              const SizedBox(height: 10),
              for (final mention in mentions)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      color: Theme.of(context).colorScheme.surface,
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(
                        color: Theme.of(context).colorScheme.outlineVariant,
                      ),
                    ),
                    child: Padding(
                      padding: const EdgeInsets.all(10),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            mention.title.isNotEmpty
                                ? mention.title
                                : mention.path,
                            style: Theme.of(context).textTheme.bodyMedium
                                ?.copyWith(fontWeight: FontWeight.w700),
                          ),
                          if (mention.path.isNotEmpty) ...[
                            const SizedBox(height: 4),
                            Text(
                              mention.path,
                              style: Theme.of(context).textTheme.bodySmall,
                            ),
                          ],
                          if (mention.snippet.isNotEmpty) ...[
                            const SizedBox(height: 6),
                            Text(mention.snippet),
                          ],
                          const SizedBox(height: 8),
                          Align(
                            alignment: AlignmentDirectional.centerStart,
                            child: TextButton.icon(
                              onPressed: () => onGoToMention(mention),
                              icon: const Icon(Icons.open_in_new_rounded),
                              label: Text(localizer.t('goToThisPart')),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

class _DirectorsCutPanel extends StatelessWidget {
  const _DirectorsCutPanel({
    required this.selectedCutType,
    required this.status,
    required this.result,
    required this.errorMessage,
    required this.onDirectorsCut,
  });

  final String? selectedCutType;
  final OperationStatus status;
  final DirectorsCutResponse? result;
  final String? errorMessage;
  final ValueChanged<String> onDirectorsCut;

  static const _cuts = [
    ('quick', 'quickCut', Icons.flash_on_rounded),
    ('story', 'storyCut', Icons.timeline_rounded),
    ('exam', 'examCut', Icons.school_outlined),
  ];

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(
          context,
        ).colorScheme.surfaceContainerHighest.withValues(alpha: 0.35),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(
                  Icons.movie_filter_outlined,
                  color: Theme.of(context).colorScheme.primary,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        localizer.t('directorsCut'),
                        style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        localizer.t('directorsCutDescription'),
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final item in _cuts)
                  OutlinedButton.icon(
                    onPressed: status.isLoading
                        ? null
                        : () => onDirectorsCut(item.$1),
                    icon: status.isLoading && selectedCutType == item.$1
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : Icon(item.$3, size: 18),
                    label: Text(localizer.t(item.$2)),
                  ),
              ],
            ),
            if (status.isLoading) ...[
              const SizedBox(height: 12),
              const LinearProgressIndicator(),
              const SizedBox(height: 8),
              Text(localizer.t('directorsCutLoading')),
            ],
            if (status == OperationStatus.error) ...[
              const SizedBox(height: 12),
              StatusMessage(
                message: errorMessage ?? localizer.t('directorsCutFailed'),
                isError: true,
              ),
            ],
            if (result != null && !result!.isEmpty) ...[
              const SizedBox(height: 14),
              _DirectorsCutResultBlock(result: result!),
            ],
          ],
        ),
      ),
    );
  }
}

class _DirectorsCutResultBlock extends StatelessWidget {
  const _DirectorsCutResultBlock({required this.result});

  final DirectorsCutResponse result;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (result.title.trim().isNotEmpty)
          Text(
            result.title,
            style: Theme.of(
              context,
            ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
          ),
        if (result.summary.trim().isNotEmpty) ...[
          const SizedBox(height: 8),
          Text(result.summary),
        ],
        for (final section in result.sections) ...[
          const SizedBox(height: 10),
          CardListBlock(title: section.title, items: section.items),
        ],
        if (result.quiz.isNotEmpty) ...[
          const SizedBox(height: 10),
          for (final item in result.quiz)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surface,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: Theme.of(context).colorScheme.outlineVariant,
                  ),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(10),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (item.question.trim().isNotEmpty)
                        Text(
                          item.question,
                          style: Theme.of(context).textTheme.bodyMedium
                              ?.copyWith(fontWeight: FontWeight.w700),
                        ),
                      if (item.answer.trim().isNotEmpty) ...[
                        const SizedBox(height: 6),
                        Text(item.answer),
                      ],
                    ],
                  ),
                ),
              ),
            ),
        ],
        if (result.source == 'fallback' || result.warning.trim().isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              result.warning.trim().isNotEmpty
                  ? result.warning
                  : localizer.t('directorsCutFallbackNote'),
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
      ],
    );
  }
}

class _RemixConsolePanel extends StatelessWidget {
  const _RemixConsolePanel({
    required this.selectedStyle,
    required this.status,
    required this.result,
    required this.errorMessage,
    required this.onRemix,
  });

  final String? selectedStyle;
  final OperationStatus status;
  final RemixResponse? result;
  final String? errorMessage;
  final ValueChanged<String> onRemix;

  static const _styles = [
    ('short', 'remixShort', Icons.compress_rounded),
    ('simpler', 'remixSimpler', Icons.child_care_rounded),
    ('more_examples', 'remixMoreExamples', Icons.auto_stories_outlined),
    ('table', 'remixTable', Icons.table_chart_outlined),
    ('exam', 'remixExam', Icons.school_outlined),
    ('buddy', 'remixBuddy', Icons.chat_bubble_outline_rounded),
    ('teacher', 'remixTeacher', Icons.menu_book_outlined),
    ('technical', 'remixTechnical', Icons.science_outlined),
  ];

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(
          context,
        ).colorScheme.surfaceContainerHighest.withValues(alpha: 0.35),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(
                  Icons.tune_rounded,
                  color: Theme.of(context).colorScheme.primary,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        localizer.t('remixConsole'),
                        style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        localizer.t('remixDescription'),
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final item in _styles)
                  OutlinedButton.icon(
                    onPressed: status.isLoading ? null : () => onRemix(item.$1),
                    icon: status.isLoading && selectedStyle == item.$1
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : Icon(item.$3, size: 18),
                    label: Text(localizer.t(item.$2)),
                  ),
              ],
            ),
            if (status.isLoading) ...[
              const SizedBox(height: 12),
              const LinearProgressIndicator(),
              const SizedBox(height: 8),
              Text(localizer.t('remixLoading')),
            ],
            if (status == OperationStatus.error) ...[
              const SizedBox(height: 12),
              StatusMessage(
                message: errorMessage ?? localizer.t('remixFailed'),
                isError: true,
              ),
            ],
            if (result != null && !result!.isEmpty) ...[
              const SizedBox(height: 14),
              _RemixResultBlock(result: result!),
            ],
          ],
        ),
      ),
    );
  }
}

class _RemixResultBlock extends StatelessWidget {
  const _RemixResultBlock({required this.result});

  final RemixResponse result;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (result.title.trim().isNotEmpty)
          Text(
            result.title,
            style: Theme.of(
              context,
            ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
          ),
        if (result.content.trim().isNotEmpty) ...[
          const SizedBox(height: 8),
          Text(result.content),
        ],
        if (result.items.isNotEmpty) ...[
          const SizedBox(height: 10),
          CardListBlock(
            title: localizer.t('remixConsole'),
            items: result.items,
          ),
        ],
        if (result.table.isNotEmpty) ...[
          const SizedBox(height: 10),
          for (final row in result.table)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surface,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: Theme.of(context).colorScheme.outlineVariant,
                  ),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(10),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(child: Text(row.left)),
                      const SizedBox(width: 8),
                      Expanded(child: Text(row.middle)),
                      const SizedBox(width: 8),
                      Expanded(child: Text(row.right)),
                    ],
                  ),
                ),
              ),
            ),
        ],
        if (result.source == 'fallback' || result.warning.trim().isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              result.warning.trim().isNotEmpty
                  ? result.warning
                  : localizer.t('remixFallbackNote'),
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
      ],
    );
  }
}

class _EvidenceFollowupPanel extends StatelessWidget {
  const _EvidenceFollowupPanel({
    super.key,
    required this.controller,
    required this.question,
    required this.answer,
    required this.status,
    required this.errorMessage,
    required this.hasDocument,
    required this.onQuestionChanged,
    required this.onAsk,
    required this.onClear,
    required this.showComposer,
    required this.onToggleComposer,
  });

  final TextEditingController controller;
  final String question;
  final EvidenceAnswer? answer;
  final OperationStatus status;
  final String? errorMessage;
  final bool hasDocument;
  final ValueChanged<String> onQuestionChanged;
  final VoidCallback onAsk;
  final VoidCallback onClear;
  final bool showComposer;
  final VoidCallback onToggleComposer;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(
          context,
        ).colorScheme.surfaceContainerHighest.withValues(alpha: 0.45),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(
                  Icons.verified_outlined,
                  color: Theme.of(context).colorScheme.primary,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        localizer.t('deepenWithEvidence'),
                        style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        localizer.t('evidenceComposerDescription'),
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: OutlinedButton.icon(
                onPressed: status.isLoading ? null : onToggleComposer,
                icon: Icon(
                  showComposer
                      ? Icons.keyboard_arrow_up_rounded
                      : Icons.add_comment_outlined,
                ),
                label: Text(
                  showComposer
                      ? localizer.t('hideEvidenceAnswer')
                      : localizer.t('openEvidenceAnswer'),
                ),
              ),
            ),
            if (showComposer) ...[
              const SizedBox(height: 12),
              _EvidenceComposer(
                controller: controller,
                question: question,
                answer: answer,
                status: status,
                errorMessage: errorMessage,
                hasDocument: hasDocument,
                onQuestionChanged: onQuestionChanged,
                onAsk: onAsk,
                onClear: onClear,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _EvidenceComposer extends StatelessWidget {
  const _EvidenceComposer({
    required this.controller,
    required this.question,
    required this.answer,
    required this.status,
    required this.errorMessage,
    required this.hasDocument,
    required this.onQuestionChanged,
    required this.onAsk,
    required this.onClear,
  });

  final TextEditingController controller;
  final String question;
  final EvidenceAnswer? answer;
  final OperationStatus status;
  final String? errorMessage;
  final bool hasDocument;
  final ValueChanged<String> onQuestionChanged;
  final VoidCallback onAsk;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          controller: controller,
          onChanged: onQuestionChanged,
          minLines: 2,
          maxLines: 5,
          textInputAction: TextInputAction.newline,
          decoration: InputDecoration(
            labelText: localizer.t('askQuestionAboutThisPart'),
            hintText: 'ATP hücrede ne işe yarar?',
            prefixIcon: const Icon(Icons.question_answer_outlined),
          ),
        ),
        const SizedBox(height: 10),
        Builder(
          builder: (context) {
            final currentQuestion = question.trim().isNotEmpty
                ? question
                : controller.text;
            final canAsk =
                hasDocument &&
                currentQuestion.trim().isNotEmpty &&
                !status.isLoading;
            return FilledButton.icon(
              onPressed: canAsk ? onAsk : null,
              icon: status.isLoading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.send_rounded),
              label: Text(
                status.isLoading ? 'Soruluyor...' : localizer.t('send'),
              ),
            );
          },
        ),
        if (answer != null) ...[
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: status.isLoading ? null : onClear,
            icon: const Icon(Icons.refresh_rounded),
            label: Text(localizer.t('askFollowupQuestion')),
          ),
        ],
        if (!hasDocument) ...[
          const SizedBox(height: 12),
          _InlineState(
            icon: Icons.info_outline_rounded,
            message: localizer.t('documentRequired'),
          ),
        ],
        if (status == OperationStatus.loading) ...[
          const SizedBox(height: 12),
          const LinearProgressIndicator(),
        ],
        if (status == OperationStatus.error) ...[
          const SizedBox(height: 12),
          StatusMessage(
            message: errorMessage ?? localizer.t('evidence_failed'),
            isError: true,
          ),
        ],
        if (answer?.answer != null && answer!.answer!.trim().isNotEmpty) ...[
          const SizedBox(height: 14),
          TextBlock(title: localizer.t('answer'), text: answer!.answer!),
        ],
        if (answer != null) ...[
          EvidenceBlock(items: answer!.evidence),
          if (answer!.evidence.isEmpty &&
              answer?.answer?.trim().isNotEmpty == true)
            const Padding(
              padding: EdgeInsets.only(top: 12),
              child: _InlineState(
                icon: Icons.info_outline_rounded,
                message: 'Cevap üretildi ancak ayrı kanıt kartı bulunamadı.',
              ),
            ),
          if (answer!.evidence.isEmpty &&
              answer?.answer?.trim().isNotEmpty != true)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: _InlineState(
                icon: Icons.info_outline_rounded,
                message: localizer.t('noEvidenceFound'),
              ),
            ),
        ],
        if (status == OperationStatus.empty && answer == null)
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: _InlineState(
              icon: Icons.info_outline_rounded,
              message: errorMessage ?? localizer.t('noEvidenceFound'),
            ),
          ),
      ],
    );
  }
}
