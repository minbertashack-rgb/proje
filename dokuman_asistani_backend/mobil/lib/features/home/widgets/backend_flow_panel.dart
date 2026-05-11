import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/utils/parse_utils.dart';
import '../../../core/state/operation_status.dart';
import '../../../core/i18n/app_localizer.dart';
import '../../../core/files/file_type_config.dart';
import '../../../services/ai_service.dart';
import '../../../services/concept_service.dart';
import '../../../services/document_service.dart';
import '../../../services/excel_service.dart';
import '../../../services/export_service.dart';
import '../../../services/game_service.dart';
import '../../../services/note_service.dart';
import '../../../services/preference_service.dart';
import '../../../services/reels_service.dart';
import '../../../shared/widgets/content_blocks.dart';
import '../../../shared/widgets/section_card.dart';
import '../../../shared/widgets/status_message.dart';
import '../../../shared/widgets/language_picker.dart';
import '../../documents/data/document_part.dart';
import '../../documents/data/uploaded_document.dart';
import '../../concepts/data/concept_models.dart';
import '../../concepts/data/fusion_card.dart';
import '../../explain/data/directors_cut_response.dart';
import '../../explain/data/explain_response.dart';
import '../../explain/data/learning_game_response.dart';
import '../../explain/data/remix_response.dart';
import '../../explain/data/self_check_response.dart';
import '../../notes/data/smart_note.dart';
import '../../outputs/data/export_payload_models.dart';
import '../../outputs/data/reels_models.dart';
import '../../preferences/data/learning_preferences.dart';
import '../data/game_models.dart';
import '../data/upload_stage.dart';
import '../../qa/data/evidence_answer.dart';

enum _WorkspaceMessageRole {
  user,
  assistant,
  system,
  evidence,
  actionResult,
  actionCarousel,
}

class _WorkspaceChatMessage {
  const _WorkspaceChatMessage({
    required this.id,
    required this.role,
    required this.text,
    required this.createdAt,
    this.evidence = const [],
    this.actionType,
  });

  final String id;
  final _WorkspaceMessageRole role;
  final String text;
  final DateTime createdAt;
  final List<EvidenceSnippet> evidence;
  final String? actionType;
}

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
    this.excelService,
    this.exportService,
    this.gameService,
    this.noteService,
    this.preferenceService,
    this.reelsService,
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
  final ExcelService? excelService;
  final ExportService? exportService;
  final GameService? gameService;
  final NoteService? noteService;
  final PreferenceService? preferenceService;
  final ReelsService? reelsService;

  @override
  State<BackendFlowPanel> createState() => BackendFlowPanelState();
}

class BackendFlowPanelState extends State<BackendFlowPanel> {
  final _qaKey = GlobalKey();
  final _explainKey = GlobalKey();
  DocumentService? _documentService;
  AiService? _aiService;
  ConceptService? _conceptService;
  ExportService? _exportService;
  GameService? _gameService;
  NoteService? _noteService;
  PreferenceService? _preferenceService;
  ReelsService? _reelsService;
  TextEditingController? _questionController;
  TextEditingController? _selfCheckController;
  TextEditingController? _noteTitleController;
  TextEditingController? _noteBodyController;
  TextEditingController? _noteConceptController;
  TextEditingController? _chatController;

  DocumentService get _documents =>
      _documentService ??= widget.documentService ?? DocumentService();
  AiService get _ai => _aiService ??= widget.aiService ?? AiService();
  ConceptService get _concepts =>
      _conceptService ??= widget.conceptService ?? ConceptService();
  ExportService get _exports =>
      _exportService ??= widget.exportService ?? ExportService();
  GameService get _game => _gameService ??= widget.gameService ?? GameService();
  NoteService get _notes =>
      _noteService ??= widget.noteService ?? NoteService();
  PreferenceService get _preferencesService =>
      _preferenceService ??= widget.preferenceService ?? PreferenceService();
  ReelsService get _reels =>
      _reelsService ??= widget.reelsService ?? ReelsService();
  TextEditingController get _questionInput =>
      _questionController ??= TextEditingController();
  TextEditingController get _selfCheckInput =>
      _selfCheckController ??= TextEditingController();
  TextEditingController get _noteTitleInput =>
      _noteTitleController ??= TextEditingController();
  TextEditingController get _noteBodyInput =>
      _noteBodyController ??= TextEditingController();
  TextEditingController get _noteConceptInput =>
      _noteConceptController ??= TextEditingController();
  TextEditingController get _chatInput =>
      _chatController ??= TextEditingController();

  UploadedDocument? _document;
  List<DocumentPart> _parts = const [];
  DocumentPart? _selectedPart;
  ExplainResponse? _explain;
  DirectorsCutResponse? _directorsCutResult;
  RemixResponse? _remixResult;
  SelfCheckResponse? _selfCheckResult;
  QuizRouletteResponse? _quizRouletteResult;
  EscapeRoomResponse? _escapeRoomResult;
  SpeedrunResponse? _speedrunResult;
  EvidenceAnswer? _answer;
  LearningPreferences? _learningPreferences;
  List<ConceptItem> _partConcepts = const [];
  List<ConceptRelation> _conceptRelations = const [];
  List<ConceptMention> _conceptMentions = const [];
  List<SmartNote> _partNotes = const [];
  List<SmartNote> _myNotes = const [];
  List<PortalLink> _portalLinks = const [];
  ConceptItem? _selectedConcept;
  SmartNote? _activePortalNote;
  FusionCard? _fusionResult;
  GameProfile? _gameProfile;
  GameRewards? _gameRewards;
  WeeklyProgress? _weeklyProgress;
  BossPayload? _bossPayload;
  BossResult? _bossResult;
  BossRush? _bossRush;
  ReelsPayload? _reelsPayload;
  ExportPayload? _activeExportPayload;
  PremiumUiPayload? _premiumPayload;
  List<_WorkspaceChatMessage> _chatMessages = const [];

  String? _selectedFilePath;
  String? _selectedFileName;
  String? _selectedFileExtension;
  FileTypeInfo? _selectedFileType;
  String? _notice;
  String? _error;
  String? _explainError;
  String? _directorsCutError;
  String? _remixError;
  String? _selfCheckError;
  String? _gameError;
  String? _answerError;
  String? _conceptError;
  String? _preferencesError;
  String? _notesError;
  String? _fusionError;
  String? _progressError;
  String? _bossError;
  String? _reelsError;
  String? _outputsError;
  String? _selectedOutputType;
  int _chatMessageCounter = 0;
  String _evidenceQuestion = '';
  String _selfCheckAnswer = '';
  String? _selectedDirectorsCutType;
  String? _selectedRemixStyle;
  String? _selectedFusionTermA;
  String? _selectedFusionTermB;
  String? _selectedGameMode;
  Map<int, String> _quizSelections = const {};
  Set<int> _completedEscapeKeys = const {};
  UploadStage _uploadStage = UploadStage.idle;
  bool _showEvidenceComposer = false;
  bool _showNoteForm = false;
  bool _showMyNotes = false;

  OperationStatus _pingStatus = OperationStatus.idle;
  OperationStatus _uploadStatus = OperationStatus.idle;
  OperationStatus _partsStatus = OperationStatus.idle;
  OperationStatus _explainStatus = OperationStatus.idle;
  OperationStatus _directorsCutStatus = OperationStatus.idle;
  OperationStatus _remixStatus = OperationStatus.idle;
  OperationStatus _selfCheckStatus = OperationStatus.idle;
  OperationStatus _gameStatus = OperationStatus.idle;
  OperationStatus _answerStatus = OperationStatus.idle;
  OperationStatus _conceptStatus = OperationStatus.idle;
  OperationStatus _preferencesStatus = OperationStatus.idle;
  OperationStatus _notesStatus = OperationStatus.idle;
  OperationStatus _saveNoteStatus = OperationStatus.idle;
  OperationStatus _myNotesStatus = OperationStatus.idle;
  OperationStatus _portalStatus = OperationStatus.idle;
  OperationStatus _fusionStatus = OperationStatus.idle;
  OperationStatus _progressStatus = OperationStatus.idle;
  OperationStatus _bossStatus = OperationStatus.idle;
  OperationStatus _bossRushStatus = OperationStatus.idle;
  OperationStatus _reelsStatus = OperationStatus.idle;
  OperationStatus _outputsStatus = OperationStatus.idle;
  bool _unauthorizedRedirectScheduled = false;

  bool get _busy =>
      _uploadStatus.isLoading ||
      _partsStatus.isLoading ||
      _explainStatus.isLoading ||
      _directorsCutStatus.isLoading ||
      _remixStatus.isLoading ||
      _selfCheckStatus.isLoading ||
      _gameStatus.isLoading ||
      _answerStatus.isLoading ||
      _conceptStatus.isLoading ||
      _notesStatus.isLoading ||
      _saveNoteStatus.isLoading ||
      _myNotesStatus.isLoading ||
      _portalStatus.isLoading ||
      _fusionStatus.isLoading ||
      _bossStatus.isLoading ||
      _bossRushStatus.isLoading ||
      _reelsStatus.isLoading ||
      _outputsStatus.isLoading ||
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
      Future<void>.microtask(loadGameProfile);
    }
  }

  @override
  void dispose() {
    _questionController?.dispose();
    _selfCheckController?.dispose();
    _noteTitleController?.dispose();
    _noteBodyController?.dispose();
    _noteConceptController?.dispose();
    _chatController?.dispose();
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

  Future<void> pickFile({bool autoUpload = false}) async {
    if (_busy) return;
    final localizer = AppLocalizer.of(context);
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: uploadExtensions,
      withData: false,
    );
    if (!mounted) return;
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
      _resetSelfCheckState();
      _resetGameState();
      _resetReelsState();
      _resetConceptState();
      _resetFusionState();
      _resetExcelState();
      _resetNotesState();
      _resetOutputsState();
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
      _chatMessages = const [];
      _chatMessageCounter = 0;
      _error = fileType.blocked
          ? localizer.t('blocked_extension')
          : !fileType.uploadAllowed
          ? localizer.t('unsupported_extension')
          : null;
      _notice = fileType.uploadAllowed && !fileType.parseSupported
          ? localizer.t('parserLimitedHint')
          : localizer.t('fileAttached');
    });
    if (autoUpload) {
      _addChatMessage(
        _WorkspaceMessageRole.system,
        '${localizer.t('fileAttached')}: ${result.files.single.name}',
      );
      if (!fileType.uploadAllowed) return;
      await upload(askAfterUpload: true, preserveChatMessages: true);
    }
  }

  @visibleForTesting
  Future<void> selectTestFileAndUpload({
    required String path,
    required String name,
    String extension = 'pdf',
  }) async {
    final normalizedExtension = normalizeFileExtension(extension);
    final fileType = fileTypeInfoForExtension(normalizedExtension);
    setState(() {
      _selectedFilePath = path;
      _selectedFileName = name;
      _selectedFileExtension = normalizedExtension.toUpperCase();
      _selectedFileType = fileType;
      _uploadStatus = OperationStatus.idle;
      _uploadStage = UploadStage.selected;
      _document = null;
      _parts = const [];
      _selectedPart = null;
      _explain = null;
      _resetDirectorsCutState();
      _resetRemixState();
      _resetSelfCheckState();
      _resetGameState();
      _resetReelsState();
      _resetConceptState();
      _resetFusionState();
      _resetExcelState();
      _resetNotesState();
      _resetOutputsState();
      _answer = null;
      _chatMessages = const [];
      _chatMessageCounter = 0;
      _error = null;
      _notice = AppLocalizer.of(context).t('fileAttached');
    });
    _addChatMessage(
      _WorkspaceMessageRole.system,
      '${AppLocalizer.of(context).t('fileAttached')}: $name',
    );
    await upload(askAfterUpload: true, preserveChatMessages: true);
  }

  Future<void> upload({
    bool askAfterUpload = false,
    bool preserveChatMessages = false,
  }) async {
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
      _resetSelfCheckState();
      _resetGameState();
      _resetReelsState();
      _resetConceptState();
      _resetFusionState();
      _resetExcelState();
      _resetNotesState();
      _resetOutputsState();
      _answer = null;
      _explainError = null;
      _answerError = null;
      _explainStatus = OperationStatus.idle;
      _answerStatus = OperationStatus.idle;
      if (!preserveChatMessages) {
        _chatMessages = const [];
        _chatMessageCounter = 0;
      }
      _error = null;
      _notice = AppLocalizer.of(context).t('documentPreparing');
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
        _resetSelfCheckState();
        _resetGameState();
        _resetConceptState();
        _resetFusionState();
        _resetExcelState();
        _resetNotesState();
        _explainError = null;
        _answer = null;
        _answerError = null;
        _showEvidenceComposer = false;
        _uploadStatus = OperationStatus.success;
        _uploadStage = UploadStage.success;
        _notice = AppLocalizer.of(context).t('documentUploaded');
      });
      if (document.id <= 0) {
        setState(() {
          _partsStatus = OperationStatus.empty;
          _notice = 'Doküman yüklendi ancak parçalar alınamadı.';
        });
        return;
      }
      await loadParts(document.id, autoSelectFirst: !askAfterUpload);
      if (!mounted) return;
      if (askAfterUpload) {
        _addChatMessage(
          _WorkspaceMessageRole.assistant,
          AppLocalizer.of(context).t('askAfterUpload'),
        );
      }
      await loadGameProfile();
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_upload')) return;
      setState(() {
        _uploadStatus = OperationStatus.error;
        _uploadStage = UploadStage.error;
        _error = _friendlyApiMessage(error, 'uploadFailedTryAgain');
      });
      if (askAfterUpload) {
        _addChatMessage(
          _WorkspaceMessageRole.system,
          AppLocalizer.of(context).t('uploadFailedTryAgain'),
        );
      }
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _uploadStatus = OperationStatus.error;
        _uploadStage = UploadStage.error;
        _error = AppLocalizer.of(context).t('uploadFailedTryAgain');
      });
      if (askAfterUpload) {
        _addChatMessage(
          _WorkspaceMessageRole.system,
          AppLocalizer.of(context).t('uploadFailedTryAgain'),
        );
      }
    }
  }

  Future<void> loadParts(int documentId, {bool autoSelectFirst = true}) async {
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
        _selectedPart = autoSelectFirst && parts.isNotEmpty
            ? parts.first
            : null;
        _explain = null;
        _explainError = null;
        _resetDirectorsCutState();
        _resetRemixState();
        _resetSelfCheckState();
        _resetGameState();
        _resetReelsState();
        _resetConceptState();
        _resetFusionState();
        _resetOutputsState();
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
            : AppLocalizer.of(context).t('sourceReady');
      });
      if (parts.isNotEmpty) {
        await loadPartNotes();
      }
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

  Future<void> loadGameProfile() async {
    if (widget.isGuest || _progressStatus.isLoading) return;
    setState(() {
      _progressStatus = OperationStatus.loading;
      _progressError = null;
    });
    try {
      final results = await Future.wait<dynamic>([
        _game.fetchProfile(),
        _game.fetchRewards(),
        _game.fetchWeeklyProgress(),
      ]);
      if (!mounted) return;
      setState(() {
        _gameProfile = results[0] as GameProfile;
        _gameRewards = results[1] as GameRewards;
        _weeklyProgress = results[2] as WeeklyProgress;
        _progressStatus = OperationStatus.success;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _progressStatus = OperationStatus.error;
        _progressError = AppLocalizer.of(context).t('progressFailed');
      });
    }
  }

  Future<void> loadPartReels() async {
    final part = _selectedPart;
    if (part == null || _reelsStatus.isLoading) return;
    setState(() {
      _reelsStatus = OperationStatus.loading;
      _reelsError = null;
    });
    try {
      final payload = await _reels.fetchPartReels(part.id);
      if (!mounted) return;
      setState(() {
        _reelsPayload = payload;
        _reelsStatus = payload.enabled && payload.cards.isNotEmpty
            ? OperationStatus.success
            : OperationStatus.empty;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_reels')) return;
      setState(() {
        _reelsStatus = OperationStatus.error;
        _reelsError = _friendlyApiMessage(error, 'reelsFailed');
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _reelsStatus = OperationStatus.error;
        _reelsError = AppLocalizer.of(context).t('reelsFailed');
      });
    }
  }

  Future<void> loadExportPayload(String type) async {
    final document = _document;
    if (document == null || _outputsStatus.isLoading) return;
    setState(() {
      _outputsStatus = OperationStatus.loading;
      _outputsError = null;
      _selectedOutputType = type;
    });
    try {
      final payload = switch (type) {
        'cheatsheet' => await _exports.fetchCheatsheet(document.id),
        'study_summary' => await _exports.fetchStudySummary(document.id),
        'presentation_plan' => await _exports.fetchPresentationPlan(
          document.id,
        ),
        'readme' => await _exports.fetchReadme(document.id),
        'readiness' => await _exports.fetchReadiness(document.id),
        _ => await _exports.fetchCheatsheet(document.id),
      };
      if (!mounted) return;
      setState(() {
        _activeExportPayload = payload;
        _outputsStatus = payload.enabled
            ? OperationStatus.success
            : OperationStatus.empty;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_outputs')) return;
      setState(() {
        _outputsStatus = OperationStatus.error;
        _outputsError = _friendlyApiMessage(error, 'outputsFailed');
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _outputsStatus = OperationStatus.error;
        _outputsError = AppLocalizer.of(context).t('outputsFailed');
      });
    }
  }

  Future<void> loadPremiumPayload() async {
    final document = _document;
    if (document == null || widget.exportService == null) return;
    try {
      final payload = await _exports.fetchPremiumPayload(document.id);
      if (!mounted) return;
      setState(() {
        _premiumPayload = payload;
      });
    } catch (_) {
      // Premium polish is optional; keep the main explanation flow quiet.
    }
  }

  Future<void> startBossFight() async {
    final part = _selectedPart;
    if (part == null || _bossStatus.isLoading) return;
    setState(() {
      _bossStatus = OperationStatus.loading;
      _bossError = null;
      _bossPayload = null;
      _bossResult = null;
    });
    try {
      final payload = await _game.startBossFight(part.id);
      if (!mounted) return;
      setState(() {
        _bossPayload = payload;
        _bossStatus = payload.questions.isEmpty
            ? OperationStatus.empty
            : OperationStatus.success;
      });
      await loadGameProfile();
      await loadPremiumPayload();
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_boss_fight')) return;
      setState(() {
        _bossStatus = OperationStatus.error;
        _bossError = _friendlyApiMessage(error, 'bossActionFailed');
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _bossStatus = OperationStatus.error;
        _bossError = AppLocalizer.of(context).t('tryAgain');
      });
    }
  }

  Future<void> answerBossFight() async {
    final part = _selectedPart;
    final boss = _bossPayload;
    if (part == null || boss == null || _bossStatus.isLoading) return;
    setState(() {
      _bossStatus = OperationStatus.loading;
      _bossError = null;
    });
    try {
      final result = await _game.answerBoss(
        partId: part.id,
        bossId: boss.bossId,
        answers: [...boss.questions, boss.task],
      );
      if (!mounted) return;
      setState(() {
        _bossResult = result;
        _bossStatus = OperationStatus.success;
      });
      await loadGameProfile();
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_boss_answer')) return;
      setState(() {
        _bossStatus = OperationStatus.error;
        _bossError = _friendlyApiMessage(error, 'bossActionFailed');
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _bossStatus = OperationStatus.error;
        _bossError = AppLocalizer.of(context).t('tryAgain');
      });
    }
  }

  Future<void> loadBossRush() async {
    final document = _document;
    if (document == null || _bossRushStatus.isLoading) return;
    setState(() {
      _bossRushStatus = OperationStatus.loading;
      _bossError = null;
    });
    try {
      final rush = await _game.fetchBossRush(document.id);
      if (!mounted) return;
      setState(() {
        _bossRush = rush;
        _bossRushStatus = rush.bosses.isEmpty
            ? OperationStatus.empty
            : OperationStatus.success;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_boss_rush')) return;
      setState(() {
        _bossRushStatus = OperationStatus.error;
        _bossError = _friendlyApiMessage(error, 'bossActionFailed');
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _bossRushStatus = OperationStatus.error;
        _bossError = AppLocalizer.of(context).t('tryAgain');
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
      _resetSelfCheckState();
      _resetGameState();
      _resetEvidenceState();
      _resetConceptState();
      _resetFusionState();
      _resetFusionState();
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
        _resetSelfCheckState();
        _resetGameState();
        _resetFusionState();
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
      await loadPremiumPayload();
      await loadGameProfile();
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_anlamadim')) return;
      setState(() {
        _explainStatus = OperationStatus.error;
        _explainError = _friendlyApiMessage(error, 'explainFailed');
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
        _remixError = _friendlyApiMessage(error, 'remixFailed');
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
        _directorsCutError = _friendlyApiMessage(error, 'directorsCutFailed');
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

  Future<void> requestSelfCheck() async {
    FocusScope.of(context).unfocus();
    final part = _selectedPart;
    final explain = _explain;
    final answer = _selfCheckInput.text.trim();
    if (part == null || explain == null || explain.isEmpty) return;
    if (answer.isEmpty) {
      setState(() {
        _selfCheckStatus = OperationStatus.empty;
        _selfCheckError = AppLocalizer.of(context).t('writeYourUnderstanding');
      });
      return;
    }
    if (_selfCheckStatus.isLoading) return;

    setState(() {
      _selfCheckStatus = OperationStatus.loading;
      _selfCheckError = null;
      _selfCheckResult = null;
      _notice = AppLocalizer.of(context).t('selfCheckLoading');
    });

    try {
      final response = await _ai.requestSelfCheck(
        partId: part.id,
        answer: answer,
        preferences: _learningPreferences,
      );
      if (!mounted) return;
      setState(() {
        _selfCheckResult = response;
        _selfCheckStatus = response.isEmpty
            ? OperationStatus.empty
            : OperationStatus.success;
        _notice = response.enabled
            ? AppLocalizer.of(context).t('selfCheckReady')
            : (response.warning ??
                  AppLocalizer.of(context).t('selfCheckFailed'));
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_self_check')) return;
      setState(() {
        _selfCheckStatus = OperationStatus.error;
        _selfCheckError = _friendlyApiMessage(error, 'selfCheckFailed');
        _error = null;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _selfCheckStatus = OperationStatus.error;
        _selfCheckError = AppLocalizer.of(context).t('selfCheckFailed');
        _error = null;
      });
    }
  }

  Future<void> requestGameMode(String mode) async {
    final part = _selectedPart;
    if (part == null || _gameStatus.isLoading) return;
    setState(() {
      _selectedGameMode = mode;
      _gameStatus = OperationStatus.loading;
      _gameError = null;
      _quizSelections = const {};
      _completedEscapeKeys = const {};
      if (mode == 'quiz_roulette') _quizRouletteResult = null;
      if (mode == 'escape_room') _escapeRoomResult = null;
      if (mode == 'speedrun') _speedrunResult = null;
      _notice = '${AppLocalizer.of(context).t('testTime')} hazırlanıyor...';
    });
    try {
      if (mode == 'quiz_roulette') {
        final response = await _ai.requestQuizRoulette(
          partId: part.id,
          preferences: _learningPreferences,
        );
        if (!mounted) return;
        setState(() {
          _quizRouletteResult = response;
          _gameStatus = response.questions.isEmpty
              ? OperationStatus.empty
              : OperationStatus.success;
          _notice = AppLocalizer.of(context).t('quizRoulette');
        });
        await loadGameProfile();
      } else if (mode == 'escape_room') {
        final response = await _ai.requestEscapeRoom(
          partId: part.id,
          preferences: _learningPreferences,
        );
        if (!mounted) return;
        setState(() {
          _escapeRoomResult = response;
          _gameStatus = response.keys.isEmpty
              ? OperationStatus.empty
              : OperationStatus.success;
          _notice = AppLocalizer.of(context).t('escapeRoom');
        });
        await loadGameProfile();
      } else {
        final response = await _ai.requestSpeedrun(
          partId: part.id,
          preferences: _learningPreferences,
        );
        if (!mounted) return;
        setState(() {
          _speedrunResult = response;
          _gameStatus = response.criticalSentences.isEmpty
              ? OperationStatus.empty
              : OperationStatus.success;
          _notice = AppLocalizer.of(context).t('speedrun');
        });
        await loadGameProfile();
      }
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_learning_games')) return;
      setState(() {
        _gameStatus = OperationStatus.error;
        _gameError = _friendlyApiMessage(error, 'gameFailed');
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _gameStatus = OperationStatus.error;
        _gameError = AppLocalizer.of(context).t('tryAgain');
      });
    }
  }

  void selectQuizAnswer(int index, String answer) {
    setState(() {
      _quizSelections = {..._quizSelections, index: answer};
    });
  }

  void completeEscapeKey(int keyId) {
    setState(() {
      _completedEscapeKeys = {..._completedEscapeKeys, keyId};
    });
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
      await loadGameProfile();
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_evidence')) return;
      setState(() {
        _answerStatus = OperationStatus.error;
        _answerError = _friendlyApiMessage(error, 'evidence_failed');
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

  Future<void> loadPartNotes() async {
    final part = _selectedPart;
    if (part == null || _notesStatus.isLoading) return;
    setState(() {
      _notesStatus = OperationStatus.loading;
      _notesError = null;
    });
    try {
      final notes = await _notes.getPartNotes(part.id);
      if (!mounted) return;
      setState(() {
        _partNotes = notes;
        _notesStatus = notes.isEmpty
            ? OperationStatus.empty
            : OperationStatus.success;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_notes')) return;
      setState(() {
        _notesStatus = OperationStatus.error;
        _notesError = _friendlyApiMessage(error, 'notesFailed');
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _notesStatus = OperationStatus.error;
        _notesError = AppLocalizer.of(context).t('notesFailed');
      });
    }
  }

  Future<void> loadMyNotes() async {
    if (_myNotesStatus.isLoading) return;
    setState(() {
      _showMyNotes = true;
      _myNotesStatus = OperationStatus.loading;
      _notesError = null;
    });
    try {
      final notes = await _notes.getMyNotes();
      if (!mounted) return;
      setState(() {
        _myNotes = notes;
        _myNotesStatus = notes.isEmpty
            ? OperationStatus.empty
            : OperationStatus.success;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_my_notes')) return;
      setState(() {
        _myNotesStatus = OperationStatus.error;
        _notesError = _friendlyApiMessage(error, 'notesFailed');
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _myNotesStatus = OperationStatus.error;
        _notesError = AppLocalizer.of(context).t('notesFailed');
      });
    }
  }

  Future<void> saveSmartNote() async {
    final part = _selectedPart;
    if (part == null || _saveNoteStatus.isLoading) return;
    final body = _noteBodyInput.text.trim();
    if (body.isEmpty) {
      setState(() {
        _notesError = AppLocalizer.of(context).t('noteBody');
      });
      return;
    }
    setState(() {
      _saveNoteStatus = OperationStatus.loading;
      _notesError = null;
    });
    try {
      final note = await _notes.createNote(
        partId: part.id,
        title: _noteTitleInput.text.trim(),
        body: body,
        conceptTerm: _noteConceptInput.text.trim(),
      );
      if (!mounted) return;
      setState(() {
        _partNotes = [note, ..._partNotes.where((item) => item.id != note.id)];
        _saveNoteStatus = OperationStatus.success;
        _notesStatus = OperationStatus.success;
        _showNoteForm = false;
        _notice = AppLocalizer.of(context).t('notesSaved');
        _noteTitleController?.clear();
        _noteBodyController?.clear();
        _noteConceptController?.clear();
      });
      _addChatMessage(
        _WorkspaceMessageRole.system,
        AppLocalizer.of(context).t('notesSaved'),
        actionType: 'note',
      );
      await loadGameProfile();
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_save_note')) return;
      setState(() {
        _saveNoteStatus = OperationStatus.error;
        _notesError = _friendlyApiMessage(error, 'notesFailed');
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _saveNoteStatus = OperationStatus.error;
        _notesError = AppLocalizer.of(context).t('notesFailed');
      });
    }
  }

  Future<void> loadPortalLinks(SmartNote note) async {
    if (_portalStatus.isLoading) return;
    setState(() {
      _activePortalNote = note;
      _portalLinks = const [];
      _portalStatus = OperationStatus.loading;
      _notesError = null;
    });
    try {
      final links = await _notes.getPortalLinks(note.id);
      if (!mounted) return;
      setState(() {
        _portalLinks = links;
        _portalStatus = links.isEmpty
            ? OperationStatus.empty
            : OperationStatus.success;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_portal_notes')) return;
      setState(() {
        _portalStatus = OperationStatus.error;
        _notesError = _friendlyApiMessage(error, 'notesFailed');
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _portalStatus = OperationStatus.error;
        _notesError = AppLocalizer.of(context).t('notesFailed');
      });
    }
  }

  void goToPortalLink(PortalLink link) {
    DocumentPart? nextPart;
    for (final part in _parts) {
      if (part.id == link.targetPartId) {
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
      _resetSelfCheckState();
      _resetGameState();
      _resetEvidenceState();
      _resetConceptState();
      _resetFusionState();
      _resetExcelState();
      _resetNotesState();
      _notice = 'Parça seçildi.';
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
      _resetSelfCheckState();
      _resetGameState();
      _resetReelsState();
      _resetConceptState();
      _resetFusionState();
      _resetExcelState();
      _resetNotesState();
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
      _gameProfile = null;
      _gameRewards = null;
      _weeklyProgress = null;
      _progressError = null;
      _progressStatus = OperationStatus.idle;
      _resetReelsState();
      _resetOutputsState();
      _questionController?.clear();
      _evidenceQuestion = '';
      _showEvidenceComposer = false;
      _unauthorizedRedirectScheduled = false;
      _chatMessages = const [];
      _chatMessageCounter = 0;
      _chatController?.clear();
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
  void setTestSelfCheckAnswer(String value) {
    _selfCheckInput.text = value;
    setState(() {
      _selfCheckAnswer = value;
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
      _resetSelfCheckState();
      _resetGameState();
      _resetReelsState();
      _resetConceptState();
      _resetFusionState();
      _resetExcelState();
      _explainError = null;
      _explainStatus = OperationStatus.idle;
      _resetEvidenceState();
      _resetNotesState();
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

  void _resetNotesState() {
    _partNotes = const [];
    _myNotes = const [];
    _portalLinks = const [];
    _activePortalNote = null;
    _notesError = null;
    _notesStatus = OperationStatus.idle;
    _saveNoteStatus = OperationStatus.idle;
    _myNotesStatus = OperationStatus.idle;
    _portalStatus = OperationStatus.idle;
    _showNoteForm = false;
    _showMyNotes = false;
    _noteTitleController?.clear();
    _noteBodyController?.clear();
    _noteConceptController?.clear();
  }

  void _resetReelsState() {
    _reelsPayload = null;
    _reelsError = null;
    _reelsStatus = OperationStatus.idle;
  }

  void _resetOutputsState() {
    _activeExportPayload = null;
    _premiumPayload = null;
    _outputsError = null;
    _selectedOutputType = null;
    _outputsStatus = OperationStatus.idle;
  }

  void _resetConceptState() {
    _partConcepts = const [];
    _conceptRelations = const [];
    _conceptMentions = const [];
    _selectedConcept = null;
    _conceptError = null;
    _conceptStatus = OperationStatus.idle;
  }

  void _resetFusionState() {
    _selectedFusionTermA = null;
    _selectedFusionTermB = null;
    _fusionResult = null;
    _fusionError = null;
    _fusionStatus = OperationStatus.idle;
  }

  void _resetExcelState() {
    // Excel upload support stays enabled, but special Excel modes are not part
    // of the TÜBİTAK demo surface.
  }

  void _resetRemixState() {
    _selectedRemixStyle = null;
    _remixResult = null;
    _remixError = null;
    _remixStatus = OperationStatus.idle;
  }

  void _resetSelfCheckState() {
    _selfCheckResult = null;
    _selfCheckError = null;
    _selfCheckStatus = OperationStatus.idle;
    _selfCheckController?.clear();
    _selfCheckAnswer = '';
  }

  void _resetGameState() {
    _quizRouletteResult = null;
    _escapeRoomResult = null;
    _speedrunResult = null;
    _gameError = null;
    _gameStatus = OperationStatus.idle;
    _selectedGameMode = null;
    _bossPayload = null;
    _bossResult = null;
    _bossRush = null;
    _bossError = null;
    _bossStatus = OperationStatus.idle;
    _bossRushStatus = OperationStatus.idle;
    _quizSelections = const {};
    _completedEscapeKeys = const {};
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
        _conceptError = _friendlyApiMessage(error, 'conceptsFailed');
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _conceptStatus = OperationStatus.error;
        _conceptError = AppLocalizer.of(context).t('conceptsFailed');
      });
    }
  }

  void selectFusionTermA(String? value) {
    setState(() {
      _selectedFusionTermA = value;
      _fusionError = null;
      if (_selectedFusionTermB == value) {
        _fusionResult = null;
      }
    });
  }

  void selectFusionTermB(String? value) {
    setState(() {
      _selectedFusionTermB = value;
      _fusionError = null;
      if (_selectedFusionTermA == value) {
        _fusionResult = null;
      }
    });
  }

  Future<void> requestConceptFusion() async {
    final document = _document;
    final part = _selectedPart;
    final termA = (_selectedFusionTermA ?? '').trim();
    final termB = (_selectedFusionTermB ?? '').trim();
    final localizer = AppLocalizer.of(context);
    if (document == null || termA.isEmpty || termB.isEmpty) {
      setState(() {
        _fusionStatus = OperationStatus.empty;
        _fusionError = localizer.t('fusionTermsRequired');
      });
      return;
    }
    if (termA.toLowerCase() == termB.toLowerCase()) {
      setState(() {
        _fusionStatus = OperationStatus.empty;
        _fusionError = localizer.t('fusionTermsMustDiffer');
      });
      return;
    }
    if (_fusionStatus.isLoading) return;
    setState(() {
      _fusionStatus = OperationStatus.loading;
      _fusionError = null;
      _fusionResult = null;
    });
    try {
      final card = await _concepts.requestConceptFusion(
        documentId: document.id,
        termA: termA,
        termB: termB,
        partId: part?.id,
        preferences: _learningPreferences,
      );
      if (!mounted) return;
      setState(() {
        _fusionResult = card;
        _fusionStatus = card.isEmpty
            ? OperationStatus.empty
            : OperationStatus.success;
        _fusionError = card.enabled
            ? null
            : (card.warning.isNotEmpty
                  ? card.warning
                  : localizer.t('fusionFailed'));
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_concept_fusion')) return;
      setState(() {
        _fusionStatus = OperationStatus.error;
        _fusionError = _friendlyApiMessage(error, 'fusionFailed');
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _fusionStatus = OperationStatus.error;
        _fusionError = localizer.t('fusionFailed');
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
      _resetSelfCheckState();
      _resetGameState();
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

  String _friendlyApiMessage(ApiException error, String fallbackKey) {
    final localizer = AppLocalizer.of(context);
    final coded = AppLocalizer.messageForErrorCode(error.message);
    if (coded.isNotEmpty) return coded;
    final raw = AppLocalizer.localizeRawError(error.message);
    if (raw.isNotEmpty) return raw;
    final message = error.message.trim();
    if (message.startsWith('{') ||
        message.startsWith('[') ||
        message.toLowerCase().contains('exception') ||
        message.toLowerCase().contains('traceback') ||
        message.toLowerCase().contains('socket') ||
        message.toLowerCase().contains('xmlhttprequest') ||
        message.toLowerCase().contains('network') ||
        message.toLowerCase().contains('timeout') ||
        message.toLowerCase().contains('zaman')) {
      return localizer.t(fallbackKey);
    }
    return message.isEmpty ? localizer.t(fallbackKey) : message;
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

  void _addChatMessage(
    _WorkspaceMessageRole role,
    String text, {
    List<EvidenceSnippet> evidence = const [],
    String? actionType,
  }) {
    final trimmed = text.trim();
    if (trimmed.isEmpty && evidence.isEmpty) return;
    setState(() {
      _chatMessages = [
        ..._chatMessages,
        _WorkspaceChatMessage(
          id: 'msg-${++_chatMessageCounter}',
          role: role,
          text: trimmed,
          createdAt: DateTime.now(),
          evidence: evidence,
          actionType: actionType,
        ),
      ];
    });
  }

  void _addAssistantMessageFromAction({
    required String text,
    List<EvidenceSnippet> evidence = const [],
    String? actionType,
  }) {
    _addChatMessage(
      evidence.isNotEmpty
          ? _WorkspaceMessageRole.evidence
          : _WorkspaceMessageRole.actionResult,
      text,
      evidence: evidence,
      actionType: actionType,
    );
  }

  void _selectWorkspacePart(DocumentPart part) {
    setState(() {
      _selectedPart = part;
      _explain = null;
      _resetDirectorsCutState();
      _resetRemixState();
      _resetSelfCheckState();
      _resetGameState();
      _resetReelsState();
      _resetConceptState();
      _resetFusionState();
      _resetExcelState();
      _resetNotesState();
      _explainError = null;
      _explainStatus = OperationStatus.idle;
      _resetEvidenceState();
    });
    _addChatMessage(
      _WorkspaceMessageRole.system,
      AppLocalizer.of(context).t('selectedPartUpdated'),
    );
  }

  Future<void> _showPhonePartPicker() async {
    if (_parts.isEmpty) return;
    final selected = await showModalBottomSheet<DocumentPart>(
      context: context,
      isScrollControlled: true,
      builder: (context) => _PhonePartPickerSheet(
        parts: _parts,
        hardestParts: _hardestParts,
        selectedPart: _selectedPart,
      ),
    );
    if (selected == null || !mounted) return;
    _selectWorkspacePart(selected);
  }

  String _explainAsChatText(ExplainResponse response) {
    final chunks = <String>[
      if (response.oneSentence?.trim().isNotEmpty == true)
        response.oneSentence!.trim(),
      if (response.simpleExplanation?.trim().isNotEmpty == true)
        response.simpleExplanation!.trim(),
      if (response.rawExplanation?.trim().isNotEmpty == true)
        response.rawExplanation!.trim(),
      if (response.steps.isNotEmpty) response.steps.take(4).join('\n'),
      if (response.examples.isNotEmpty)
        '${AppLocalizer.of(context).t('examples')}: ${response.examples.take(2).join(' / ')}',
    ];
    return chunks.isEmpty
        ? AppLocalizer.of(context).t('docverseAnswer')
        : chunks.join('\n\n');
  }

  String _remixAsChatText(RemixResponse response) {
    final chunks = <String>[
      if (response.title.trim().isNotEmpty) response.title.trim(),
      if (response.content.trim().isNotEmpty) response.content.trim(),
      if (response.items.isNotEmpty) response.items.take(4).join('\n'),
      if (response.warning.trim().isNotEmpty) response.warning.trim(),
    ];
    return chunks.isEmpty
        ? AppLocalizer.of(context).t('remixFailed')
        : chunks.join('\n\n');
  }

  String _directorsCutAsChatText(DirectorsCutResponse response) {
    final chunks = <String>[
      if (response.title.trim().isNotEmpty) response.title.trim(),
      if (response.summary.trim().isNotEmpty) response.summary.trim(),
      for (final section in response.sections.take(2))
        [
          if (section.title.trim().isNotEmpty) section.title.trim(),
          ...section.items.take(3),
        ].join('\n'),
      if (response.quiz.isNotEmpty) response.quiz.first.question,
      if (response.warning.trim().isNotEmpty) response.warning.trim(),
    ];
    return chunks.where((item) => item.trim().isNotEmpty).join('\n\n');
  }

  String _quizAsChatText(QuizRouletteResponse response) {
    final question = response.questions.isEmpty
        ? null
        : response.questions.first;
    if (question == null) return AppLocalizer.of(context).t('startQuiz');
    final options = question.options.isEmpty
        ? ''
        : '\n${question.options.take(4).join('\n')}';
    return '${question.question}$options';
  }

  String _bossAsChatText(BossPayload payload) {
    final chunks = <String>[
      if (payload.title.trim().isNotEmpty) payload.title.trim(),
      if (payload.preview.trim().isNotEmpty) payload.preview.trim(),
      if (payload.task.trim().isNotEmpty) payload.task.trim(),
      if (payload.questions.isNotEmpty) payload.questions.take(3).join('\n'),
    ];
    return chunks.isEmpty
        ? AppLocalizer.of(context).t('startBoss')
        : chunks.join('\n\n');
  }

  String _reelsAsChatText(ReelsPayload payload) {
    if (payload.cards.isEmpty) return AppLocalizer.of(context).t('miniReels');
    final card = payload.cards.first;
    final chunks = <String>[
      card.title,
      if (card.summary.isNotEmpty) card.summary.take(3).join('\n'),
      if (card.example.trim().isNotEmpty)
        '${AppLocalizer.of(context).t('giveExample')}: ${card.example}',
      if (card.question.trim().isNotEmpty) card.question,
    ];
    return chunks.where((item) => item.trim().isNotEmpty).join('\n\n');
  }

  String _fusionAsChatText(FusionCard card) {
    final chunks = <String>[
      if (card.title.trim().isNotEmpty) card.title.trim(),
      if (card.commonPoints.isNotEmpty) card.commonPoints.take(3).join('\n'),
      if (card.togetherExample.trim().isNotEmpty) card.togetherExample.trim(),
      if (card.miniQuestion.question.trim().isNotEmpty)
        card.miniQuestion.question.trim(),
    ];
    return chunks.isEmpty
        ? AppLocalizer.of(context).t('fusionFailed')
        : chunks.join('\n\n');
  }

  String _exportAsChatText(ExportPayload payload) {
    final chunks = <String>[
      if (payload.title.trim().isNotEmpty) payload.title.trim(),
      ...payload.stringList('bullets').take(4),
      ...payload.stringList('summary').take(4),
      ...payload.stringList('slides').take(4),
    ];
    return chunks.isEmpty
        ? AppLocalizer.of(context).t('outputs')
        : chunks.join('\n');
  }

  Future<bool> _ensureExplainForAction(String actionType) async {
    if (_explain != null && !_explain!.isEmpty) return true;
    await explainSelectedPart();
    if (!mounted) return false;
    final response = _explain;
    if (response == null || response.isEmpty) {
      _addChatMessage(
        _WorkspaceMessageRole.system,
        AppLocalizer.of(context).t('explainFailed'),
        actionType: actionType,
      );
      return false;
    }
    return true;
  }

  Future<void> _askEvidenceFromAction() async {
    final document = _document;
    final part = _selectedPart;
    final localizer = AppLocalizer.of(context);
    if (document == null || part == null || _answerStatus.isLoading) return;
    final partLabel = part.title?.isNotEmpty == true
        ? part.title!
        : 'Parça ${part.order}';
    final question = '${localizer.t('showEvidence')}: $partLabel';
    setState(() {
      _answerStatus = OperationStatus.loading;
      _answerError = null;
      _answer = null;
    });
    try {
      final response = await _ai.askEvidenceAnswer(
        documentId: document.id,
        partId: part.id,
        question: question,
        preferences: _learningPreferences,
      );
      if (!mounted) return;
      setState(() {
        _answer = response;
        _answerStatus =
            response.answer?.trim().isNotEmpty == true ||
                response.evidence.isNotEmpty
            ? OperationStatus.success
            : OperationStatus.empty;
      });
      _addAssistantMessageFromAction(
        text: response.answer?.trim().isNotEmpty == true
            ? response.answer!
            : localizer.t('noEvidenceFound'),
        evidence: response.evidence,
        actionType: 'evidence',
      );
      await loadGameProfile();
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_action_evidence')) return;
      _addChatMessage(
        _WorkspaceMessageRole.system,
        _friendlyApiMessage(error, 'evidence_failed'),
      );
    } catch (_) {
      if (!mounted) return;
      _addChatMessage(
        _WorkspaceMessageRole.system,
        localizer.t('evidence_failed'),
      );
    }
  }

  Future<void> _sendChatQuestion() async {
    final localizer = AppLocalizer.of(context);
    final question = _chatInput.text.trim();
    if (question.isEmpty) return;
    final document = _document;
    if (document == null) {
      _addChatMessage(
        _WorkspaceMessageRole.system,
        localizer.t('documentRequired'),
      );
      return;
    }
    _chatInput.clear();
    _addChatMessage(_WorkspaceMessageRole.user, question);
    try {
      final response = await _ai.askEvidenceAnswer(
        documentId: document.id,
        partId: _selectedPart?.id,
        question: question,
        preferences: _learningPreferences,
      );
      if (!mounted) return;
      setState(() {
        _answer = response;
        _answerStatus = OperationStatus.success;
      });
      _addChatMessage(
        response.evidence.isNotEmpty
            ? _WorkspaceMessageRole.evidence
            : _WorkspaceMessageRole.assistant,
        response.answer?.trim().isNotEmpty == true
            ? response.answer!
            : localizer.t('noEvidenceFound'),
        evidence: response.evidence,
        actionType: 'evidence',
      );
      await loadGameProfile();
    } on ApiException catch (error) {
      if (!mounted) return;
      if (_handleUnauthorized(error, '401_chat_evidence')) return;
      _addChatMessage(
        _WorkspaceMessageRole.system,
        _friendlyApiMessage(error, 'evidence_failed'),
      );
    } catch (_) {
      if (!mounted) return;
      _addChatMessage(
        _WorkspaceMessageRole.system,
        localizer.t('evidence_failed'),
      );
    }
  }

  Future<void> _runWorkspaceAction(String action) async {
    final localizer = AppLocalizer.of(context);
    if (_selectedPart == null) {
      _addChatMessage(
        _WorkspaceMessageRole.system,
        localizer.t('selectPartFirst'),
      );
      return;
    }
    if (action == 'explain') {
      await explainSelectedPart();
      if (!mounted) return;
      final response = _explain;
      if (response != null && !response.isEmpty) {
        _addAssistantMessageFromAction(
          text: _explainAsChatText(response),
          actionType: action,
        );
      }
      return;
    }
    if (action == 'evidence') {
      await _askEvidenceFromAction();
      return;
    }
    if (action == 'self_check') {
      if (!await _ensureExplainForAction(action)) return;
      if (_selfCheckInput.text.trim().isEmpty) {
        _addChatMessage(
          _WorkspaceMessageRole.system,
          localizer.t('writeYourUnderstanding'),
          actionType: action,
        );
        return;
      }
      await requestSelfCheck();
      if (!mounted) return;
      final response = _selfCheckResult;
      _addAssistantMessageFromAction(
        text: response == null || response.isEmpty
            ? localizer.t('selfCheckFailed')
            : [
                localizer.t('selfCheckReady'),
                '${localizer.t('selfCheckScore')}: ${response.score.toStringAsFixed(0)}',
                if (response.correctPoints.isNotEmpty)
                  response.correctPoints.take(3).join('\n'),
                if (response.missingPoints.isNotEmpty)
                  response.missingPoints.take(3).join('\n'),
                if (response.improvedAnswer?.trim().isNotEmpty == true)
                  response.improvedAnswer!.trim(),
                if (response.warning?.trim().isNotEmpty == true)
                  response.warning!.trim(),
              ].join('\n\n'),
        actionType: action,
      );
      return;
    }
    if (action == 'simplify') {
      if (!await _ensureExplainForAction(action)) return;
      await remixExplanation('simpler');
      if (!mounted) return;
      _addAssistantMessageFromAction(
        text: _remixResult == null
            ? localizer.t('simplify')
            : _remixAsChatText(_remixResult!),
        actionType: action,
      );
      return;
    }
    if (action == 'example') {
      if (!await _ensureExplainForAction(action)) return;
      await remixExplanation('more_examples');
      if (!mounted) return;
      _addAssistantMessageFromAction(
        text: _remixResult == null
            ? localizer.t('giveExample')
            : _remixAsChatText(_remixResult!),
        actionType: action,
      );
      return;
    }
    if (action == 'remix') {
      if (!await _ensureExplainForAction(action)) return;
      await remixExplanation('short');
      if (!mounted) return;
      _addAssistantMessageFromAction(
        text: _remixResult == null
            ? localizer.t('remixFailed')
            : _remixAsChatText(_remixResult!),
        actionType: action,
      );
      return;
    }
    if (action == 'directors_cut') {
      if (!await _ensureExplainForAction(action)) return;
      await requestDirectorsCut('story');
      if (!mounted) return;
      _addAssistantMessageFromAction(
        text: _directorsCutResult == null || _directorsCutResult!.isEmpty
            ? localizer.t('directorsCutFailed')
            : _directorsCutAsChatText(_directorsCutResult!),
        actionType: action,
      );
      return;
    }
    if (action == 'concept_fusion') {
      if (!await _ensureExplainForAction(action)) return;
      final concepts = _partConcepts
          .map((item) => item.term.trim())
          .where((term) => term.isNotEmpty)
          .toList(growable: false);
      if (concepts.length < 2) {
        _addChatMessage(
          _WorkspaceMessageRole.system,
          localizer.t('fusionTermsRequired'),
          actionType: action,
        );
        return;
      }
      setState(() {
        _selectedFusionTermA = concepts[0];
        _selectedFusionTermB = concepts[1];
      });
      await requestConceptFusion();
      if (!mounted) return;
      _addAssistantMessageFromAction(
        text: _fusionResult == null || _fusionResult!.isEmpty
            ? localizer.t('fusionFailed')
            : _fusionAsChatText(_fusionResult!),
        actionType: action,
      );
      return;
    }
    if (action == 'quiz') {
      await requestGameMode('quiz_roulette');
      if (!mounted) return;
      _addAssistantMessageFromAction(
        text: _quizRouletteResult == null
            ? localizer.t('startQuiz')
            : _quizAsChatText(_quizRouletteResult!),
        actionType: action,
      );
      return;
    }
    if (action == 'boss') {
      await startBossFight();
      if (!mounted) return;
      _addAssistantMessageFromAction(
        text: _bossPayload == null
            ? localizer.t('startBoss')
            : _bossAsChatText(_bossPayload!),
        actionType: action,
      );
      return;
    }
    if (action == 'reels') {
      await loadPartReels();
      if (!mounted) return;
      _addAssistantMessageFromAction(
        text: _reelsPayload == null
            ? localizer.t('miniReels')
            : _reelsAsChatText(_reelsPayload!),
        actionType: action,
      );
      return;
    }
    if (action == 'note') {
      setState(() {
        _showNoteForm = true;
      });
      _addChatMessage(_WorkspaceMessageRole.system, localizer.t('addToNotes'));
      return;
    }
    if (action == 'outputs') {
      await loadExportPayload(_selectedOutputType ?? 'study_summary');
      if (!mounted) return;
      _addAssistantMessageFromAction(
        text: _activeExportPayload == null
            ? localizer.t('outputs')
            : _exportAsChatText(_activeExportPayload!),
        actionType: action,
      );
    }
  }

  Widget _buildSourcesPanel({
    bool showHeader = true,
    bool showLanguagePicker = true,
    bool showStatus = true,
  }) {
    final statusSection = _StatusSection(
      username: widget.username,
      pingStatus: _pingStatus,
      document: _document,
      partsCount: _parts.length,
      selectedPart: _selectedPart,
      aiFallbackActive: _bossPayload != null || _reelsPayload != null,
      onPing: ping,
      onLogout: widget.onLogout,
    );
    return _WorkspacePanel(
      title: AppLocalizer.of(context).t('sources'),
      icon: Icons.folder_copy_outlined,
      showHeader: showHeader,
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (showLanguagePicker) ...[
              const LanguagePicker(),
              const SizedBox(height: 12),
            ],
            if (showStatus) ...[statusSection, const SizedBox(height: 12)],
            _UploadSection(
              fileName: _selectedFileName,
              extension: _selectedFileExtension,
              fileType: _selectedFileType,
              status: _uploadStatus,
              stage: _uploadStage,
              onPick: pickFile,
              onUpload: upload,
            ),
            const SizedBox(height: 12),
            _DocumentSection(
              document: _document,
              parts: _parts,
              hardestParts: _hardestParts,
              selectedPart: _selectedPart,
              status: _partsStatus,
              explainStatus: _explainStatus,
              onReload: _document == null
                  ? null
                  : () => loadParts(_document!.id),
              onSelect: _selectWorkspacePart,
              onStartHardPart: _selectWorkspacePart,
              onExplain: explainSelectedPart,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildChatPanel({
    bool showHeader = true,
    bool showQuickActions = true,
    bool showAttachButton = false,
    Widget? phoneSourceSummary,
    Widget? actionCarousel,
  }) {
    final selectedPartTitle = _selectedPart == null
        ? null
        : _selectedPart!.title?.isNotEmpty == true
        ? _selectedPart!.title!
        : 'Parça ${_selectedPart!.order}';
    return _WorkspaceChatPanel(
      messages: _chatMessages,
      controller: _chatInput,
      hasSelectedPart: _selectedPart != null,
      selectedSourceLabel: selectedPartTitle,
      busy: _busy,
      onSend: _sendChatQuestion,
      onAttachFile: () => pickFile(autoUpload: true),
      onAction: _runWorkspaceAction,
      showHeader: showHeader,
      showQuickActions: showQuickActions,
      showAttachButton: showAttachButton,
      phoneSourceSummary: phoneSourceSummary,
      actionCarousel: actionCarousel,
      hintText: showAttachButton
          ? _phoneChatHint(AppLocalizer.of(context))
          : AppLocalizer.of(context).t('askDocVerse'),
    );
  }

  String _phoneChatHint(AppLocalizer localizer) {
    if (_document == null) return localizer.t('askOrChooseFileFirst');
    if (_partsStatus.isLoading) return localizer.t('documentPreparing');
    return localizer.t('askDocVerse');
  }

  Widget _buildPhoneSourceSummary() {
    return _PhoneSourceMiniCard(
      document: _document,
      partsCount: _parts.length,
      selectedPart: _selectedPart,
      partsLoading: _partsStatus.isLoading,
      onSelectPart: _parts.isEmpty ? null : _showPhonePartPicker,
      onChangeFile: _busy ? null : () => pickFile(autoUpload: true),
    );
  }

  Widget _buildPhoneToolShelf() {
    final localizer = AppLocalizer.of(context);
    final hasPart = _selectedPart != null;
    final slides = [
      _StudioSlideData(
        title: localizer.t('learningTools'),
        subtitle: localizer.t('learningToolsDescription'),
        icon: Icons.account_tree_outlined,
        children: [
          _PhoneStudioActionPanel(
            enabled: hasPart && !_busy,
            onAction: _runWorkspaceAction,
            actions: [
              _PhoneStudioAction(
                id: 'concept_fusion',
                label: localizer.t('conceptFusionLab'),
                icon: Icons.hub_outlined,
              ),
              _PhoneStudioAction(
                id: 'directors_cut',
                label: localizer.t('directorsCut'),
                icon: Icons.movie_creation_outlined,
              ),
              _PhoneStudioAction(
                id: 'remix',
                label: localizer.t('remixConsole'),
                icon: Icons.auto_fix_high_outlined,
              ),
              _PhoneStudioAction(
                id: 'self_check',
                label: localizer.t('selfCheck'),
                icon: Icons.check_circle_outline_rounded,
              ),
            ],
          ),
        ],
      ),
      _StudioSlideData(
        title: localizer.t('gameTools'),
        subtitle: localizer.t('gameToolsDescription'),
        icon: Icons.emoji_events_outlined,
        children: [
          _PhoneStudioActionPanel(
            enabled: hasPart && !_busy,
            onAction: _runWorkspaceAction,
            actions: [
              _PhoneStudioAction(
                id: 'quiz',
                label: localizer.t('startQuiz'),
                icon: Icons.quiz_outlined,
              ),
              _PhoneStudioAction(
                id: 'boss',
                label: localizer.t('startBoss'),
                icon: Icons.shield_outlined,
              ),
              _PhoneStudioAction(
                id: 'reels',
                label: localizer.t('miniReels'),
                icon: Icons.video_library_outlined,
              ),
            ],
          ),
        ],
      ),
      _StudioSlideData(
        title: localizer.t('productivityTools'),
        subtitle: localizer.t('productivityToolsDescription'),
        icon: Icons.task_alt_outlined,
        children: [
          _PhoneStudioActionPanel(
            enabled: _document != null && !_busy,
            onAction: _runWorkspaceAction,
            actions: [
              _PhoneStudioAction(
                id: 'note',
                label: localizer.t('addToNotes'),
                icon: Icons.note_add_outlined,
              ),
              _PhoneStudioAction(
                id: 'outputs',
                label: localizer.t('outputs'),
                icon: Icons.ios_share_outlined,
              ),
            ],
          ),
        ],
      ),
      _StudioSlideData(
        title: localizer.t('progressTools'),
        subtitle: localizer.t('progressToolsDescription'),
        icon: Icons.trending_up_rounded,
        children: [
          _PhoneStudioProgressSummary(
            profile: _gameProfile,
            weeklyProgress: _weeklyProgress,
            status: _progressStatus,
          ),
        ],
      ),
    ];
    return SizedBox(
      key: const ValueKey('phone_chat_tool_shelf'),
      height: 220,
      child: _PhoneStudioSlider(slides: slides),
    );
  }

  Widget _buildStudioPanel({bool compact = false, bool showHeader = true}) {
    final hasPart = _selectedPart != null;
    final progress = _GamificationPanel(
      profile: _gameProfile,
      rewards: _gameRewards,
      weeklyProgress: _weeklyProgress,
      status: _progressStatus,
      errorMessage: _progressError,
      onRefresh: loadGameProfile,
    );
    final preferences = _LearningPreferencesSection(
      preferences: _learningPreferences ?? const LearningPreferences(),
      status: _preferencesStatus,
      errorMessage: _preferencesError,
      onSave: savePreferences,
    );
    final explain = hasPart
        ? _ExplainSection(
            key: _explainKey,
            response: _explain,
            status: _explainStatus,
            errorMessage: _explainError,
            hasSelectedPart: true,
            evidenceKey: _qaKey,
            controller: _questionInput,
            question: _evidenceQuestion,
            selfCheckController: _selfCheckInput,
            selfCheckAnswer: _selfCheckAnswer,
            selfCheckResult: _selfCheckResult,
            selfCheckStatus: _selfCheckStatus,
            selfCheckErrorMessage: _selfCheckError,
            premiumPayload: _premiumPayload,
            answer: _answer,
            notes: _partNotes,
            myNotes: _myNotes,
            portalLinks: _portalLinks,
            activePortalNote: _activePortalNote,
            concepts: _partConcepts,
            conceptRelations: _conceptRelations,
            selectedConcept: _selectedConcept,
            conceptMentions: _conceptMentions,
            conceptStatus: _conceptStatus,
            conceptErrorMessage: _conceptError,
            selectedFusionTermA: _selectedFusionTermA,
            selectedFusionTermB: _selectedFusionTermB,
            fusionResult: _fusionResult,
            fusionStatus: _fusionStatus,
            fusionErrorMessage: _fusionError,
            directorsCutResult: _directorsCutResult,
            selectedDirectorsCutType: _selectedDirectorsCutType,
            directorsCutStatus: _directorsCutStatus,
            directorsCutErrorMessage: _directorsCutError,
            remixResult: _remixResult,
            selectedRemixStyle: _selectedRemixStyle,
            remixStatus: _remixStatus,
            remixErrorMessage: _remixError,
            answerStatus: _answerStatus,
            notesStatus: _notesStatus,
            saveNoteStatus: _saveNoteStatus,
            myNotesStatus: _myNotesStatus,
            portalStatus: _portalStatus,
            answerErrorMessage: _answerError,
            notesErrorMessage: _notesError,
            hasDocument: _document != null,
            showEvidenceComposer: _showEvidenceComposer,
            onQuestionChanged: (value) => setState(() {
              _evidenceQuestion = value;
            }),
            onSelfCheckAnswerChanged: (value) => setState(() {
              _selfCheckAnswer = value;
            }),
            onToggleEvidenceComposer: _toggleEvidenceComposer,
            onToggleNoteForm: () => setState(() {
              _showNoteForm = !_showNoteForm;
            }),
            onLoadPartNotes: loadPartNotes,
            onLoadMyNotes: loadMyNotes,
            onSaveNote: saveSmartNote,
            onPortalLinks: loadPortalLinks,
            onGoToPortalLink: goToPortalLink,
            onSelectConcept: selectConcept,
            onShowConceptMentions: loadConceptMentions,
            onGoToMention: goToMention,
            onSelectFusionTermA: selectFusionTermA,
            onSelectFusionTermB: selectFusionTermB,
            onFuseConcepts: requestConceptFusion,
            onDirectorsCut: requestDirectorsCut,
            onRemix: remixExplanation,
            onSelfCheck: requestSelfCheck,
            onAsk: askQuestion,
            onClear: clearAnswer,
            showNoteForm: _showNoteForm,
            showMyNotes: _showMyNotes,
            noteTitleController: _noteTitleInput,
            noteBodyController: _noteBodyInput,
            noteConceptController: _noteConceptInput,
          )
        : null;
    final testTime = hasPart
        ? _TestTimeSection(
            selectedMode: _selectedGameMode,
            status: _gameStatus,
            errorMessage: _gameError,
            quiz: _quizRouletteResult,
            escapeRoom: _escapeRoomResult,
            speedrun: _speedrunResult,
            bossPayload: _bossPayload,
            bossResult: _bossResult,
            bossRush: _bossRush,
            bossStatus: _bossStatus,
            bossRushStatus: _bossRushStatus,
            bossErrorMessage: _bossError,
            quizSelections: _quizSelections,
            completedEscapeKeys: _completedEscapeKeys,
            onStart: requestGameMode,
            onStartBoss: startBossFight,
            onAnswerBoss: answerBossFight,
            onLoadBossRush: loadBossRush,
            onSelectQuizAnswer: selectQuizAnswer,
            onCompleteEscapeKey: completeEscapeKey,
          )
        : null;
    final reels = hasPart
        ? _MiniReelsSection(
            payload: _reelsPayload,
            status: _reelsStatus,
            errorMessage: _reelsError,
            onLoad: loadPartReels,
          )
        : null;
    final notes = hasPart
        ? _SmartNotesPanel(
            notes: _partNotes,
            myNotes: _myNotes,
            portalLinks: _portalLinks,
            activePortalNote: _activePortalNote,
            notesStatus: _notesStatus,
            saveNoteStatus: _saveNoteStatus,
            myNotesStatus: _myNotesStatus,
            portalStatus: _portalStatus,
            errorMessage: _notesError,
            showForm: _showNoteForm,
            showMyNotes: _showMyNotes,
            titleController: _noteTitleInput,
            bodyController: _noteBodyInput,
            conceptController: _noteConceptInput,
            onToggleForm: () => setState(() {
              _showNoteForm = !_showNoteForm;
            }),
            onLoadPartNotes: loadPartNotes,
            onLoadMyNotes: loadMyNotes,
            onSave: saveSmartNote,
            onPortalLinks: loadPortalLinks,
            onGoToPortalLink: goToPortalLink,
          )
        : null;
    final outputs = _document != null
        ? _OutputsSection(
            payload: _activeExportPayload,
            status: _outputsStatus,
            errorMessage: _outputsError,
            selectedType: _selectedOutputType,
            onSelect: loadExportPayload,
          )
        : null;
    final localizer = AppLocalizer.of(context);
    if (compact) {
      final slides = [
        _StudioSlideData(
          title: localizer.t('learningTools'),
          subtitle: localizer.t('learningToolsDescription'),
          icon: Icons.account_tree_outlined,
          children: [
            _PhoneStudioActionPanel(
              enabled: hasPart && !_busy,
              onAction: _runWorkspaceAction,
              actions: [
                _PhoneStudioAction(
                  id: 'concept_fusion',
                  label: localizer.t('conceptFusionLab'),
                  icon: Icons.hub_outlined,
                ),
                _PhoneStudioAction(
                  id: 'directors_cut',
                  label: localizer.t('directorsCut'),
                  icon: Icons.movie_creation_outlined,
                ),
                _PhoneStudioAction(
                  id: 'remix',
                  label: localizer.t('remixConsole'),
                  icon: Icons.auto_fix_high_outlined,
                ),
                _PhoneStudioAction(
                  id: 'self_check',
                  label: localizer.t('selfCheck'),
                  icon: Icons.check_circle_outline_rounded,
                ),
              ],
            ),
          ],
        ),
        _StudioSlideData(
          title: localizer.t('gameTools'),
          subtitle: localizer.t('gameToolsDescription'),
          icon: Icons.emoji_events_outlined,
          children: [
            _PhoneStudioActionPanel(
              enabled: hasPart && !_busy,
              onAction: _runWorkspaceAction,
              actions: [
                _PhoneStudioAction(
                  id: 'quiz',
                  label: localizer.t('startQuiz'),
                  icon: Icons.quiz_outlined,
                ),
                _PhoneStudioAction(
                  id: 'boss',
                  label: localizer.t('startBoss'),
                  icon: Icons.shield_outlined,
                ),
                _PhoneStudioAction(
                  id: 'reels',
                  label: localizer.t('miniReels'),
                  icon: Icons.video_library_outlined,
                ),
              ],
            ),
          ],
        ),
        _StudioSlideData(
          title: localizer.t('productivityTools'),
          subtitle: localizer.t('productivityToolsDescription'),
          icon: Icons.task_alt_outlined,
          children: [
            _PhoneStudioActionPanel(
              enabled: _document != null && !_busy,
              onAction: _runWorkspaceAction,
              actions: [
                _PhoneStudioAction(
                  id: 'note',
                  label: localizer.t('addToNotes'),
                  icon: Icons.note_add_outlined,
                ),
                _PhoneStudioAction(
                  id: 'outputs',
                  label: localizer.t('outputs'),
                  icon: Icons.ios_share_outlined,
                ),
              ],
            ),
          ],
        ),
        _StudioSlideData(
          title: localizer.t('progressTools'),
          subtitle: localizer.t('progressToolsDescription'),
          icon: Icons.trending_up_rounded,
          children: [
            _PhoneStudioProgressSummary(
              profile: _gameProfile,
              weeklyProgress: _weeklyProgress,
              status: _progressStatus,
            ),
          ],
        ),
      ];
      return _WorkspacePanel(
        title: localizer.t('studio'),
        icon: Icons.dashboard_customize_outlined,
        showHeader: showHeader,
        child: _PhoneStudioSlider(slides: slides),
      );
    }
    final children = <Widget>[
      progress,
      const SizedBox(height: 12),
      preferences,
      if (explain != null) ...[const SizedBox(height: 12), explain],
      if (testTime != null) ...[const SizedBox(height: 12), testTime],
      if (reels != null) ...[const SizedBox(height: 12), reels],
      if (notes != null) ...[const SizedBox(height: 12), notes],
      if (outputs != null) ...[const SizedBox(height: 12), outputs],
    ];
    return _WorkspacePanel(
      title: localizer.t('studio'),
      icon: Icons.dashboard_customize_outlined,
      showHeader: showHeader,
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: children,
        ),
      ),
    );
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

    return LayoutBuilder(
      builder: (context, constraints) {
        final media = MediaQuery.of(context);
        final width = constraints.maxWidth;
        final keyboardInset = media.viewInsets.bottom;
        final keyboardOpen = keyboardInset > 0;
        final viewportHeight = media.size.height;
        final availableHeight = (viewportHeight - keyboardInset).clamp(
          360.0,
          viewportHeight,
        );
        final isWideTablet =
            width >= 1000 && availableHeight >= 600 && !keyboardOpen;
        final isMediumTablet =
            width >= 700 &&
            width < 1000 &&
            availableHeight >= 520 &&
            !keyboardOpen;
        final isPhone = !isWideTablet && !isMediumTablet;
        final body = isWideTablet
            ? _DocVerseWorkspaceShell(
                sources: _buildSourcesPanel(),
                chat: _buildChatPanel(),
                studio: _buildStudioPanel(),
              )
            : isMediumTablet
            ? _DocVerseMediumWorkspaceShell(
                sources: _buildSourcesPanel(),
                chat: _buildChatPanel(),
                studio: _buildStudioPanel(),
              )
            : _DocVersePhoneWorkspaceShell(
                username: widget.username ?? '',
                chat: _buildChatPanel(
                  showHeader: false,
                  showQuickActions: true,
                  showAttachButton: true,
                  phoneSourceSummary: _buildPhoneSourceSummary(),
                  actionCarousel: _selectedPart == null
                      ? null
                      : _buildPhoneToolShelf(),
                ),
              );
        final panelHeight = availableHeight < 640
            ? availableHeight
            : availableHeight - 96;
        return SizedBox(
          height: panelHeight,
          child: Column(
            children: [
              if (_notice != null && !isPhone) StatusMessage(message: _notice!),
              if (_error != null) ...[
                const SizedBox(height: 8),
                StatusMessage(message: _error!, isError: true),
              ],
              Expanded(child: body),
            ],
          ),
        );
      },
    );
  }
}

class _DocVerseMediumWorkspaceShell extends StatelessWidget {
  const _DocVerseMediumWorkspaceShell({
    required this.sources,
    required this.chat,
    required this.studio,
  });

  final Widget sources;
  final Widget chat;
  final Widget studio;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ConstrainedBox(
          constraints: const BoxConstraints(minWidth: 260, maxWidth: 300),
          child: sources,
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            children: [
              Expanded(flex: 3, child: chat),
              const SizedBox(height: 12),
              Expanded(flex: 2, child: studio),
            ],
          ),
        ),
      ],
    );
  }
}

class _DocVerseWorkspaceShell extends StatelessWidget {
  const _DocVerseWorkspaceShell({
    required this.sources,
    required this.chat,
    required this.studio,
  });

  final Widget sources;
  final Widget chat;
  final Widget studio;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ConstrainedBox(
          constraints: const BoxConstraints(minWidth: 240, maxWidth: 300),
          child: sources,
        ),
        const SizedBox(width: 12),
        Expanded(flex: 5, child: chat),
        const SizedBox(width: 12),
        ConstrainedBox(
          constraints: const BoxConstraints(minWidth: 260, maxWidth: 340),
          child: studio,
        ),
      ],
    );
  }
}

class _DocVersePhoneWorkspaceShell extends StatelessWidget {
  const _DocVersePhoneWorkspaceShell({
    required this.username,
    required this.chat,
  });

  final String username;
  final Widget chat;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final media = MediaQuery.of(context);
        final width = constraints.maxWidth;
        final height = constraints.maxHeight;
        final landscapePhone = width > height && height < 600;
        final chatHeight = landscapePhone ? 420.0 : 640.0;
        return SingleChildScrollView(
          keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
          padding: EdgeInsets.fromLTRB(0, 0, 0, 12 + media.viewInsets.bottom),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _PhoneWorkspaceHeader(username: username),
              const SizedBox(height: 12),
              SizedBox(height: chatHeight, child: chat),
            ],
          ),
        );
      },
    );
  }
}

class _PhoneSourceMiniCard extends StatelessWidget {
  const _PhoneSourceMiniCard({
    required this.document,
    required this.partsCount,
    required this.selectedPart,
    required this.partsLoading,
    required this.onSelectPart,
    required this.onChangeFile,
  });

  final UploadedDocument? document;
  final int partsCount;
  final DocumentPart? selectedPart;
  final bool partsLoading;
  final VoidCallback? onSelectPart;
  final VoidCallback? onChangeFile;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    final title = document?.title.trim().isNotEmpty == true
        ? document!.title
        : localizer.t('chooseFile');
    final selectedLabel = selectedPart == null
        ? localizer.t('whichPartDidYouNotUnderstand')
        : selectedPart!.title?.isNotEmpty == true
        ? selectedPart!.title!
        : 'Parça ${selectedPart!.order}';
    final theme = Theme.of(context);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Wrap(
          spacing: 6,
          runSpacing: 6,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 210),
              child: Chip(
                avatar: Icon(
                  document == null
                      ? Icons.attach_file_rounded
                      : Icons.description_outlined,
                  size: 18,
                ),
                label: Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                visualDensity: VisualDensity.compact,
                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
            ),
            if (partsLoading)
              const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            if (document != null)
              Chip(
                avatar: const Icon(Icons.segment_outlined, size: 18),
                label: Text(
                  localizer
                      .t('partsCountShort')
                      .replaceAll('{count}', '$partsCount'),
                ),
                visualDensity: VisualDensity.compact,
                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
            if (document != null)
              ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 220),
                child: Chip(
                  avatar: const Icon(Icons.article_outlined, size: 18),
                  label: Text(
                    selectedLabel,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  visualDensity: VisualDensity.compact,
                  materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
              ),
            ActionChip(
              avatar: const Icon(Icons.attach_file_rounded, size: 18),
              label: Text(
                document == null
                    ? localizer.t('chooseFile')
                    : localizer.t('changeFile'),
              ),
              onPressed: onChangeFile,
              visualDensity: VisualDensity.compact,
              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            ActionChip(
              avatar: const Icon(Icons.list_alt_rounded, size: 18),
              label: Text(localizer.t('selectPart')),
              onPressed: onSelectPart,
              visualDensity: VisualDensity.compact,
              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
          ],
        ),
      ),
    );
  }
}

class _PhonePartPickerSheet extends StatelessWidget {
  const _PhonePartPickerSheet({
    required this.parts,
    required this.hardestParts,
    required this.selectedPart,
  });

  final List<DocumentPart> parts;
  final List<DocumentPart> hardestParts;
  final DocumentPart? selectedPart;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    return SafeArea(
      child: DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.82,
        minChildSize: 0.45,
        maxChildSize: 0.94,
        builder: (context, controller) => ListView(
          controller: controller,
          padding: const EdgeInsets.all(16),
          children: [
            Text(
              localizer.t('partPickerTitle'),
              style: Theme.of(
                context,
              ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w900),
            ),
            if (hardestParts.isNotEmpty) ...[
              const SizedBox(height: 14),
              Text(
                localizer.t('hardestParts'),
                style: Theme.of(
                  context,
                ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 8),
              for (final part in hardestParts)
                _PhonePartPickerTile(part: part, selectedPart: selectedPart),
            ],
            const SizedBox(height: 14),
            Text(
              localizer.t('allParts'),
              style: Theme.of(
                context,
              ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 8),
            for (final part in parts)
              _PhonePartPickerTile(part: part, selectedPart: selectedPart),
          ],
        ),
      ),
    );
  }
}

class _PhonePartPickerTile extends StatelessWidget {
  const _PhonePartPickerTile({required this.part, required this.selectedPart});

  final DocumentPart part;
  final DocumentPart? selectedPart;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    final isSelected = selectedPart?.id == part.id;
    final title = part.title?.isNotEmpty == true
        ? part.title!
        : 'Parça ${part.order}';
    final preview = part.text.length > 180
        ? '${part.text.substring(0, 180)}...'
        : part.text;
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    title,
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                Chip(
                  label: Text(
                    part.difficultyLabel.isEmpty ? '-' : part.difficultyLabel,
                  ),
                  visualDensity: VisualDensity.compact,
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              preview,
              maxLines: 3,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 8),
            Align(
              alignment: AlignmentDirectional.centerEnd,
              child: FilledButton(
                onPressed: () => Navigator.of(context).pop(part),
                child: Text(
                  isSelected
                      ? localizer.t('selectedPart')
                      : localizer.t('selectPart'),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PhoneWorkspaceHeader extends StatelessWidget {
  const _PhoneWorkspaceHeader({required this.username});

  final String username;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.primary,
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Icon(
                Icons.auto_stories_rounded,
                color: Colors.white,
                size: 21,
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'DocVerse',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                  Text(
                    username,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: const Color(0xFF667085),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 168, child: LanguagePicker(compact: true)),
          ],
        ),
      ),
    );
  }
}

class _WorkspacePanel extends StatelessWidget {
  const _WorkspacePanel({
    required this.title,
    required this.icon,
    required this.child,
    this.showHeader = true,
  });

  final String title;
  final IconData icon;
  final Widget child;
  final bool showHeader;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (showHeader) ...[
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 12, 14, 8),
              child: Row(
                children: [
                  Icon(icon, size: 18),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      title,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const Divider(height: 1),
          ],
          Expanded(child: child),
        ],
      ),
    );
  }
}

class _StudioSlideData {
  const _StudioSlideData({
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.children,
  });

  final String title;
  final String subtitle;
  final IconData icon;
  final List<Widget> children;
}

class _PhoneStudioSlider extends StatefulWidget {
  const _PhoneStudioSlider({required this.slides});

  final List<_StudioSlideData> slides;

  @override
  State<_PhoneStudioSlider> createState() => _PhoneStudioSliderState();
}

class _PhoneStudioSliderState extends State<_PhoneStudioSlider> {
  final _controller = PageController(viewportFraction: 0.94);
  int _index = 0;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.slides.isEmpty) {
      return const SizedBox.shrink();
    }
    return LayoutBuilder(
      builder: (context, constraints) {
        final height = constraints.maxHeight.isFinite
            ? constraints.maxHeight
            : MediaQuery.sizeOf(context).height * 0.56;
        final sliderHeight = height.clamp(260.0, 620.0);
        return Column(
          children: [
            Expanded(
              child: PageView.builder(
                key: ValueKey(
                  'phone_feature_slider:${widget.slides.map((slide) => slide.title).join('>')}',
                ),
                controller: _controller,
                itemCount: widget.slides.length,
                onPageChanged: (value) => setState(() => _index = value),
                itemBuilder: (context, index) => Padding(
                  padding: const EdgeInsets.fromLTRB(4, 10, 4, 8),
                  child: _PhoneStudioSlideCard(slide: widget.slides[index]),
                ),
              ),
            ),
            SizedBox(
              height: 22,
              child: Center(
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    for (var i = 0; i < widget.slides.length; i++)
                      AnimatedContainer(
                        duration: const Duration(milliseconds: 180),
                        width: i == _index ? 18 : 7,
                        height: 7,
                        margin: const EdgeInsets.symmetric(horizontal: 3),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(999),
                          color: i == _index
                              ? Theme.of(context).colorScheme.primary
                              : Theme.of(context).colorScheme.outlineVariant,
                        ),
                      ),
                  ],
                ),
              ),
            ),
            SizedBox(height: sliderHeight == height ? 4 : 0),
          ],
        );
      },
    );
  }
}

class _PhoneStudioSlideCard extends StatelessWidget {
  const _PhoneStudioSlideCard({required this.slide});

  final _StudioSlideData slide;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerLowest,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 8),
            child: Row(
              children: [
                Icon(slide.icon, size: 19),
                const SizedBox(width: 8),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        slide.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        slide.subtitle,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: const Color(0xFF667085),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: slide.children,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _PhoneStudioAction {
  const _PhoneStudioAction({
    required this.id,
    required this.label,
    required this.icon,
  });

  final String id;
  final String label;
  final IconData icon;
}

class _PhoneStudioActionPanel extends StatelessWidget {
  const _PhoneStudioActionPanel({
    required this.actions,
    required this.enabled,
    required this.onAction,
  });

  final List<_PhoneStudioAction> actions;
  final bool enabled;
  final ValueChanged<String> onAction;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        for (final action in actions)
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 170),
            child: ActionChip(
              avatar: Icon(action.icon, size: 18),
              label: Text(
                action.label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                softWrap: false,
              ),
              onPressed: enabled ? () => onAction(action.id) : null,
              visualDensity: VisualDensity.compact,
              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
          ),
      ],
    );
  }
}

class _PhoneStudioProgressSummary extends StatelessWidget {
  const _PhoneStudioProgressSummary({
    required this.profile,
    required this.weeklyProgress,
    required this.status,
  });

  final GameProfile? profile;
  final WeeklyProgress? weeklyProgress;
  final OperationStatus status;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    final chips = <Widget>[
      Chip(
        avatar: const Icon(Icons.stars_outlined, size: 18),
        label: Text(
          profile == null
              ? localizer.t('progressTools')
              : '${profile!.xpTotal} XP',
        ),
        visualDensity: VisualDensity.compact,
        materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
      ),
      if (profile != null)
        Chip(
          avatar: const Icon(Icons.trending_up_rounded, size: 18),
          label: Text('Lv ${profile!.level}'),
          visualDensity: VisualDensity.compact,
          materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
        ),
      if (weeklyProgress != null)
        Chip(
          avatar: const Icon(Icons.calendar_month_outlined, size: 18),
          label: Text('${weeklyProgress!.xpThisWeek} XP'),
          visualDensity: VisualDensity.compact,
          materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
        ),
      if (status.isLoading)
        const SizedBox(
          width: 18,
          height: 18,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
    ];
    return Wrap(spacing: 8, runSpacing: 8, children: chips);
  }
}

class _WorkspaceChatPanel extends StatelessWidget {
  const _WorkspaceChatPanel({
    required this.messages,
    required this.controller,
    required this.hasSelectedPart,
    required this.selectedSourceLabel,
    required this.busy,
    required this.onSend,
    required this.onAttachFile,
    required this.onAction,
    required this.hintText,
    this.showHeader = true,
    this.showQuickActions = true,
    this.showAttachButton = false,
    this.phoneSourceSummary,
    this.actionCarousel,
  });

  final List<_WorkspaceChatMessage> messages;
  final TextEditingController controller;
  final bool hasSelectedPart;
  final String? selectedSourceLabel;
  final bool busy;
  final VoidCallback onSend;
  final VoidCallback onAttachFile;
  final ValueChanged<String> onAction;
  final String hintText;
  final bool showHeader;
  final bool showQuickActions;
  final bool showAttachButton;
  final Widget? phoneSourceSummary;
  final Widget? actionCarousel;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    final baseMessages = messages.isEmpty
        ? [
            _WorkspaceChatMessage(
              id: 'welcome',
              role: _WorkspaceMessageRole.system,
              text: localizer.t('docverseWelcome'),
              createdAt: DateTime.now(),
            ),
          ]
        : messages;
    final visibleMessages = [...baseMessages];
    if (showAttachButton && actionCarousel != null) {
      var insertIndex = visibleMessages.length;
      for (var i = 0; i < visibleMessages.length; i++) {
        final message = visibleMessages[i];
        if (message.role == _WorkspaceMessageRole.actionResult ||
            message.role == _WorkspaceMessageRole.evidence ||
            message.actionType != null) {
          insertIndex = i;
          break;
        }
      }
      visibleMessages.insert(
        insertIndex,
        _WorkspaceChatMessage(
          id: 'phone-action-carousel',
          role: _WorkspaceMessageRole.actionCarousel,
          text: '',
          createdAt: DateTime.now(),
        ),
      );
    }
    final displayMessages = showAttachButton
        ? visibleMessages.reversed.toList(growable: false)
        : visibleMessages;
    return _WorkspacePanel(
      title: localizer.t('chat'),
      icon: Icons.chat_bubble_outline_rounded,
      showHeader: showHeader,
      child: Column(
        children: [
          if (selectedSourceLabel?.isNotEmpty == true && !showAttachButton)
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 10, 12, 0),
              child: Align(
                alignment: AlignmentDirectional.centerStart,
                child: Chip(
                  avatar: const Icon(Icons.article_outlined, size: 18),
                  label: Text(
                    '${localizer.t('selectedSource')}: $selectedSourceLabel',
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ),
            ),
          Expanded(
            child: ListView.builder(
              reverse: showAttachButton,
              padding: const EdgeInsets.all(14),
              itemCount: displayMessages.length,
              itemBuilder: (context, index) {
                final message = displayMessages[index];
                if (message.role == _WorkspaceMessageRole.actionCarousel) {
                  return _WorkspaceActionCarouselBubble(child: actionCarousel!);
                }
                return _WorkspaceMessageBubble(message: message);
              },
            ),
          ),
          const Divider(height: 1),
          Padding(
            padding: const EdgeInsets.all(12),
            child: SafeArea(
              top: false,
              left: false,
              right: false,
              minimum: EdgeInsets.zero,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (showAttachButton && phoneSourceSummary != null) ...[
                    phoneSourceSummary!,
                    const SizedBox(height: 8),
                  ],
                  if (selectedSourceLabel?.isNotEmpty == true &&
                      showAttachButton &&
                      phoneSourceSummary == null) ...[
                    Align(
                      alignment: AlignmentDirectional.centerStart,
                      child: Chip(
                        avatar: const Icon(Icons.article_outlined, size: 18),
                        label: Text(
                          '${localizer.t('selectedSource')}: $selectedSourceLabel',
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                  ],
                  if (showQuickActions) ...[
                    _QuickActionBar(
                      enabled: hasSelectedPart && !busy,
                      onAction: onAction,
                      wrapActions: showAttachButton,
                    ),
                    if (!hasSelectedPart) ...[
                      const SizedBox(height: 6),
                      Text(
                        localizer.t('selectPartFirst'),
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                    const SizedBox(height: 10),
                  ],
                  Row(
                    children: [
                      if (showAttachButton) ...[
                        IconButton.outlined(
                          tooltip: localizer.t('chooseFile'),
                          onPressed: busy ? null : onAttachFile,
                          icon: const Icon(Icons.attach_file_rounded),
                        ),
                        const SizedBox(width: 8),
                      ],
                      Expanded(
                        child: TextField(
                          controller: controller,
                          minLines: 1,
                          maxLines: 4,
                          decoration: InputDecoration(
                            hintText: hintText,
                            border: const OutlineInputBorder(),
                            isDense: true,
                          ),
                          onSubmitted: (_) => onSend(),
                        ),
                      ),
                      const SizedBox(width: 8),
                      IconButton.filled(
                        tooltip: localizer.t('send'),
                        onPressed: busy ? null : onSend,
                        icon: const Icon(Icons.send_rounded),
                      ),
                    ],
                  ),
                  if (!hasSelectedPart && !showQuickActions) ...[
                    const SizedBox(height: 8),
                    Text(
                      localizer.t('selectPartFirst'),
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _QuickActionData {
  const _QuickActionData({
    required this.id,
    required this.labelKey,
    required this.icon,
  });

  final String id;
  final String labelKey;
  final IconData icon;
}

class _QuickActionBar extends StatelessWidget {
  const _QuickActionBar({
    required this.enabled,
    required this.onAction,
    this.wrapActions = false,
  });

  static const _defaultActions = [
    _QuickActionData(
      id: 'explain',
      labelKey: 'iDontUnderstand',
      icon: Icons.psychology_alt_outlined,
    ),
    _QuickActionData(
      id: 'evidence',
      labelKey: 'showEvidence',
      icon: Icons.fact_check_outlined,
    ),
    _QuickActionData(
      id: 'simplify',
      labelKey: 'simplify',
      icon: Icons.child_care_outlined,
    ),
    _QuickActionData(
      id: 'example',
      labelKey: 'giveExample',
      icon: Icons.lightbulb_outline_rounded,
    ),
    _QuickActionData(
      id: 'quiz',
      labelKey: 'startQuiz',
      icon: Icons.quiz_outlined,
    ),
    _QuickActionData(
      id: 'boss',
      labelKey: 'startBoss',
      icon: Icons.shield_outlined,
    ),
    _QuickActionData(
      id: 'reels',
      labelKey: 'miniReels',
      icon: Icons.video_library_outlined,
    ),
    _QuickActionData(
      id: 'note',
      labelKey: 'addToNotes',
      icon: Icons.note_add_outlined,
    ),
  ];

  final bool enabled;
  final ValueChanged<String> onAction;
  final bool wrapActions;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    final chips = [
      for (final action in _defaultActions)
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 160),
          child: ActionChip(
            avatar: Icon(action.icon, size: 18),
            label: Text(
              localizer.t(action.labelKey),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              softWrap: false,
            ),
            onPressed: enabled ? () => onAction(action.id) : null,
          ),
        ),
    ];
    if (wrapActions) {
      return SizedBox(
        height: 42,
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              for (final chip in chips) ...[chip, const SizedBox(width: 8)],
            ],
          ),
        ),
      );
    }
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          for (final chip in chips) ...[chip, const SizedBox(width: 8)],
        ],
      ),
    );
  }
}

class _WorkspaceActionCarouselBubble extends StatelessWidget {
  const _WorkspaceActionCarouselBubble({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: AlignmentDirectional.centerStart,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 620),
        child: Container(
          key: const ValueKey('chat_embedded_tool_shelf'),
          margin: const EdgeInsets.only(bottom: 10),
          child: child,
        ),
      ),
    );
  }
}

class _WorkspaceMessageBubble extends StatelessWidget {
  const _WorkspaceMessageBubble({required this.message});

  final _WorkspaceChatMessage message;

  @override
  Widget build(BuildContext context) {
    final isUser = message.role == _WorkspaceMessageRole.user;
    final colorScheme = Theme.of(context).colorScheme;
    final background = isUser
        ? colorScheme.primaryContainer
        : message.role == _WorkspaceMessageRole.system
        ? colorScheme.surfaceContainerHighest
        : colorScheme.surface;
    return Align(
      alignment: isUser
          ? AlignmentDirectional.centerEnd
          : AlignmentDirectional.centerStart,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 620),
        child: Container(
          margin: const EdgeInsets.only(bottom: 10),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: background,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: colorScheme.outlineVariant),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(message.text),
              if (message.evidence.isNotEmpty) ...[
                const SizedBox(height: 8),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: [
                    for (final evidence in message.evidence.take(4))
                      Chip(
                        label: Text(
                          evidence.metaLabel?.isNotEmpty == true
                              ? evidence.metaLabel!
                              : evidence.text,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _MiniReelsSection extends StatefulWidget {
  const _MiniReelsSection({
    required this.payload,
    required this.status,
    required this.errorMessage,
    required this.onLoad,
  });

  final ReelsPayload? payload;
  final OperationStatus status;
  final String? errorMessage;
  final VoidCallback onLoad;

  @override
  State<_MiniReelsSection> createState() => _MiniReelsSectionState();
}

class _MiniReelsSectionState extends State<_MiniReelsSection> {
  final Set<int> _openAnswers = <int>{};

  @override
  void didUpdateWidget(covariant _MiniReelsSection oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.payload != widget.payload) {
      _openAnswers.clear();
    }
  }

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    final cards = widget.payload?.cards ?? const <ReelCard>[];
    return SectionCard(
      title: '${localizer.t('miniReels')} ',
      subtitle: localizer.t('swipeToLearn'),
      icon: Icons.view_carousel_outlined,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: FilledButton.icon(
              onPressed: widget.status.isLoading ? null : widget.onLoad,
              icon: widget.status.isLoading
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.auto_stories_outlined),
              label: Text(localizer.t('miniReels')),
            ),
          ),
          if (widget.status == OperationStatus.error) ...[
            const SizedBox(height: 10),
            StatusMessage(
              message: widget.errorMessage ?? localizer.t('reelsFailed'),
              isError: true,
            ),
          ],
          if (cards.isNotEmpty) ...[
            const SizedBox(height: 12),
            SizedBox(
              height: 310,
              child: PageView.builder(
                itemCount: cards.length,
                controller: PageController(viewportFraction: 0.92),
                itemBuilder: (context, index) {
                  final card = cards[index];
                  final answerOpen = _openAnswers.contains(index);
                  return Padding(
                    padding: const EdgeInsetsDirectional.only(end: 10),
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        color: Theme.of(context).colorScheme.surface,
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(
                          color: Theme.of(context).colorScheme.outlineVariant,
                        ),
                      ),
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: SingleChildScrollView(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                card.title,
                                style: Theme.of(context).textTheme.titleMedium
                                    ?.copyWith(fontWeight: FontWeight.w800),
                              ),
                              const SizedBox(height: 8),
                              for (final line in card.summary.take(3))
                                Padding(
                                  padding: const EdgeInsets.only(bottom: 5),
                                  child: Text('• $line'),
                                ),
                              const SizedBox(height: 8),
                              Text(
                                '${localizer.t('reelExample')}: ${card.example}',
                              ),
                              const SizedBox(height: 8),
                              Text(
                                '${localizer.t('reelQuestion')}: ${card.question}',
                                style: const TextStyle(
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                              if (answerOpen) ...[
                                const SizedBox(height: 6),
                                Text(card.answer),
                              ],
                              Align(
                                alignment: AlignmentDirectional.centerEnd,
                                child: TextButton(
                                  onPressed: () => setState(() {
                                    answerOpen
                                        ? _openAnswers.remove(index)
                                        : _openAnswers.add(index);
                                  }),
                                  child: Text(
                                    localizer.t(
                                      answerOpen ? 'hideAnswer' : 'showAnswer',
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _OutputsSection extends StatelessWidget {
  const _OutputsSection({
    required this.payload,
    required this.status,
    required this.errorMessage,
    required this.selectedType,
    required this.onSelect,
  });

  final ExportPayload? payload;
  final OperationStatus status;
  final String? errorMessage;
  final String? selectedType;
  final ValueChanged<String> onSelect;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    final items = <(String, String)>[
      ('cheatsheet', localizer.t('cheatSheet')),
      ('study_summary', localizer.t('studySummary')),
      ('presentation_plan', localizer.t('presentationPlan')),
      ('readme', localizer.t('readme')),
      ('readiness', localizer.t('exportReadiness')),
    ];
    return SectionCard(
      title: localizer.t('outputs'),
      subtitle: localizer.t('exportReadiness'),
      icon: Icons.file_present_outlined,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final item in items)
                ActionChip(
                  label: Text(item.$2),
                  avatar: status.isLoading && selectedType == item.$1
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.description_outlined, size: 18),
                  onPressed: status.isLoading ? null : () => onSelect(item.$1),
                ),
            ],
          ),
          if (status == OperationStatus.error) ...[
            const SizedBox(height: 10),
            StatusMessage(
              message: errorMessage ?? localizer.t('outputsFailed'),
              isError: true,
            ),
          ],
          if (payload != null) ...[
            const SizedBox(height: 12),
            _ExportPayloadView(payload: payload!),
          ],
        ],
      ),
    );
  }
}

class _ExportPayloadView extends StatelessWidget {
  const _ExportPayloadView({required this.payload});

  final ExportPayload payload;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    final title = payload.title.isNotEmpty ? payload.title : payload.type;
    final slides = payload.mapList('slides');
    final score = payload.doubleValue('score');
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(
          context,
        ).colorScheme.surfaceContainerHighest.withValues(alpha: 0.35),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: Theme.of(
                context,
              ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
            ),
            if (payload.type == 'readiness') ...[
              const SizedBox(height: 8),
              Text(
                '${localizer.t('exportReadiness')}: ${(score * 100).round()}%',
              ),
              LinearProgressIndicator(value: score.clamp(0, 1)),
            ],
            _StringListPreview(
              title: localizer.t('goldenSentences'),
              items: payload.stringList('golden_sentences'),
            ),
            _StringListPreview(
              title: localizer.t('trapPoints'),
              items: payload.stringList('trap_points'),
            ),
            _StringListPreview(
              title: localizer.t('studySummary'),
              items: payload.stringList('summary'),
            ),
            if (slides.isNotEmpty) ...[
              const SizedBox(height: 10),
              Text(
                localizer.t('presentationPlan'),
                style: const TextStyle(fontWeight: FontWeight.w800),
              ),
              for (final slide in slides)
                ListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  title: Text((slide['title'] ?? '').toString()),
                  subtitle: Text(
                    '${localizer.t('speakerNotes')}: ${(slide['speaker_notes'] ?? '').toString()}',
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

class _StringListPreview extends StatelessWidget {
  const _StringListPreview({required this.title, required this.items});

  final String title;
  final List<String> items;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
          for (final item in items.take(5)) Text(item),
        ],
      ),
    );
  }
}

class _PremiumIndicators extends StatelessWidget {
  const _PremiumIndicators({required this.payload});

  final PremiumUiPayload payload;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          _ScoreChip(label: localizer.t('clarity'), value: payload.clarity),
          _ScoreChip(
            label: localizer.t('examplesScore'),
            value: payload.examples,
          ),
          _ScoreChip(
            label: localizer.t('testReadiness'),
            value: payload.testReadiness,
          ),
          for (final teleport in payload.teleports.take(4))
            Chip(
              avatar: const Icon(Icons.near_me_outlined, size: 18),
              label: Text(
                (teleport['etiket'] ??
                        teleport['label'] ??
                        localizer.t('teleport'))
                    .toString(),
              ),
            ),
        ],
      ),
    );
  }
}

class _ScoreChip extends StatelessWidget {
  const _ScoreChip({required this.label, required this.value});

  final String label;
  final double value;

  @override
  Widget build(BuildContext context) {
    return Chip(label: Text('$label ${(value * 100).round()}%'));
  }
}

class _StatusSection extends StatelessWidget {
  const _StatusSection({
    required this.username,
    required this.pingStatus,
    required this.document,
    required this.partsCount,
    required this.selectedPart,
    required this.aiFallbackActive,
    required this.onPing,
    required this.onLogout,
  });

  final String? username;
  final OperationStatus pingStatus;
  final UploadedDocument? document;
  final int partsCount;
  final DocumentPart? selectedPart;
  final bool aiFallbackActive;
  final VoidCallback onPing;
  final VoidCallback? onLogout;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    final connectionLabel = switch (pingStatus) {
      OperationStatus.success => localizer.t('backendReady'),
      OperationStatus.loading => localizer.t('checkingConnection'),
      OperationStatus.error => localizer.t('backendUnavailable'),
      _ => localizer.t('connectionPending'),
    };
    final demoReady =
        pingStatus == OperationStatus.success &&
        document != null &&
        partsCount > 0 &&
        selectedPart != null;

    return SectionCard(
      title: localizer.t(demoReady ? 'demoReady' : 'demoChecklist'),
      subtitle: username?.isNotEmpty == true
          ? username!
          : localizer.t('workspace'),
      icon: Icons.person_outline_rounded,
      child: Column(
        children: [
          _InfoRow(
            icon: Icons.monitor_heart_outlined,
            label: localizer.t('backendConnection'),
            value: connectionLabel,
          ),
          _InfoRow(
            icon: Icons.description_outlined,
            label: localizer.t('activeDocument'),
            value: document?.title ?? localizer.t('noDocumentYet'),
          ),
          _InfoRow(
            icon: Icons.segment_outlined,
            label: localizer.t('partCount'),
            value: '$partsCount',
          ),
          _InfoRow(
            icon: Icons.article_outlined,
            label: localizer.t('selectedPart'),
            value: selectedPart?.title ?? localizer.t('noPartSelected'),
          ),
          _InfoRow(
            icon: Icons.auto_awesome_outlined,
            label: localizer.t('aiStatus'),
            value: aiFallbackActive
                ? localizer.t('fallbackReady')
                : localizer.t('aiReady'),
          ),
          const SizedBox(height: 10),
          _ResponsiveActionRow(
            children: [
              OutlinedButton.icon(
                onPressed: pingStatus.isLoading ? null : onPing,
                icon: pingStatus.isLoading
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.refresh_rounded),
                label: Text(localizer.t('checkConnection')),
              ),
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
          Expanded(
            flex: 5,
            child: Text(
              label,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: const Color(0xFF667085)),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            flex: 4,
            child: Text(
              value,
              textAlign: TextAlign.right,
              maxLines: 3,
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
          _ResponsiveActionRow(
            children: [
              FilledButton.icon(
                onPressed: onLogin,
                icon: const Icon(Icons.login_rounded),
                label: Text(localizer.t('signIn')),
              ),
              OutlinedButton.icon(
                onPressed: onRegister,
                icon: const Icon(Icons.person_add_alt_1_rounded),
                label: Text(localizer.t('register')),
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
          LayoutBuilder(
            builder: (context, constraints) {
              final narrow = constraints.maxWidth < 520;
              final level = _PreferenceDropdown(
                label: localizer.t('level'),
                value: _draft.level,
                values: const ['baslangic', 'orta', 'ileri'],
                labelFor: (value) => localizer.t(_levelKey(value)),
                onChanged: (value) => setState(() {
                  _draft = _draft.copyWith(level: value);
                }),
              );
              final density = _PreferenceDropdown(
                label: localizer.t('exampleDensity'),
                value: _draft.exampleDensity,
                values: const ['az', 'normal', 'cok'],
                labelFor: (value) => localizer.t(_densityKey(value)),
                onChanged: (value) => setState(() {
                  _draft = _draft.copyWith(exampleDensity: value);
                }),
              );
              if (narrow) {
                return Column(
                  children: [level, const SizedBox(height: 10), density],
                );
              }
              return Row(
                children: [
                  Expanded(child: level),
                  const SizedBox(width: 10),
                  Expanded(child: density),
                ],
              );
            },
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
      isExpanded: true,
      initialValue: values.contains(value) ? value : values.first,
      decoration: InputDecoration(labelText: label),
      items: [
        for (final item in values)
          DropdownMenuItem(
            value: item,
            child: Text(labelFor(item), overflow: TextOverflow.ellipsis),
          ),
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
      subtitle: fileName == null ? localizer.t('uploadHint') : null,
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
              Chip(label: Text(localizer.t('fileCategoryCode'))),
              Chip(label: Text(localizer.t('fileCategoryImageOcr'))),
              Chip(label: Text(localizer.t('fileCategoryArchive'))),
              if (extension != null)
                Chip(
                  label: Text(
                    '${localizer.t('selectedFilePrefix')}: $extension',
                  ),
                ),
              if (fileType != null)
                Chip(
                  label: Text(
                    _localizedFileCategory(localizer, fileType!.category),
                  ),
                ),
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

String _localizedFileCategory(AppLocalizer localizer, String category) {
  return switch (category) {
    'Kod' => localizer.t('fileCategoryCode'),
    'Görsel/OCR' => localizer.t('fileCategoryImageOcr'),
    'Arşiv' => localizer.t('fileCategoryArchive'),
    'Diğer' => localizer.t('fileCategoryOther'),
    _ => category,
  };
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
    final localizer = AppLocalizer.of(context);
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
                  localizer.t(stage.labelKey),
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

class _GamificationPanel extends StatelessWidget {
  const _GamificationPanel({
    required this.profile,
    required this.rewards,
    required this.weeklyProgress,
    required this.status,
    required this.errorMessage,
    required this.onRefresh,
  });

  final GameProfile? profile;
  final GameRewards? rewards;
  final WeeklyProgress? weeklyProgress;
  final OperationStatus status;
  final String? errorMessage;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    final activeProfile = profile;
    final weeklySummary = _localizedWeeklySummary(localizer, weeklyProgress);
    final rewardLabels = _localizedRewardLabels(localizer, rewards);
    return SectionCard(
      title: localizer.t('gamification'),
      subtitle: weeklySummary,
      icon: Icons.trending_up_rounded,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (status.isLoading) const LinearProgressIndicator(),
          if (status == OperationStatus.error)
            StatusMessage(
              message: errorMessage ?? localizer.t('progressFailed'),
              isError: true,
            ),
          if (activeProfile != null) ...[
            Row(
              children: [
                Expanded(
                  child: Text(
                    '${localizer.t('xp')}: ${activeProfile.xpTotal}',
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                Text('${localizer.t('level')} ${activeProfile.level}'),
              ],
            ),
            const SizedBox(height: 8),
            LinearProgressIndicator(value: activeProfile.progressRatio),
            const SizedBox(height: 8),
            Text(
              '${localizer.t('title')}: ${_localizedProgressTitle(localizer, activeProfile.title)}',
            ),
            if (activeProfile.achievements.isNotEmpty) ...[
              const SizedBox(height: 10),
              CardListBlock(
                title: localizer.t('achievements'),
                items: activeProfile.achievements
                    .take(3)
                    .map((item) => _localizedAchievementLabel(localizer, item))
                    .toList(growable: false),
              ),
            ],
          ],
          const SizedBox(height: 10),
          Text(
            localizer.t('rewards'),
            style: Theme.of(
              context,
            ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final label in rewardLabels) Chip(label: Text(label)),
            ],
          ),
          Align(
            alignment: AlignmentDirectional.centerEnd,
            child: TextButton.icon(
              onPressed: status.isLoading ? null : onRefresh,
              icon: const Icon(Icons.refresh_rounded),
              label: Text(localizer.t('weeklyProgress')),
            ),
          ),
        ],
      ),
    );
  }
}

String _localizedWeeklySummary(
  AppLocalizer localizer,
  WeeklyProgress? weeklyProgress,
) {
  if (weeklyProgress == null || weeklyProgress.xpThisWeek <= 0) {
    return localizer.t('noXpActivityThisWeek');
  }
  return localizer
      .t('weeklyXpSummary')
      .replaceAll('{xp}', '${weeklyProgress.xpThisWeek}');
}

String _localizedProgressTitle(AppLocalizer localizer, String title) {
  final normalized = title.trim().toLowerCase();
  if (normalized.isEmpty ||
      normalized == 'yeni kaşif' ||
      normalized == 'yeni kasif' ||
      normalized == 'explorer' ||
      normalized == 'new explorer') {
    return localizer.t('newExplorer');
  }
  if (normalized == 'kanıt avcısı' ||
      normalized == 'kanit avcisi' ||
      normalized == 'evidence hunter') {
    return localizer.t('evidenceHunter');
  }
  if (normalized == 'terim ustası' ||
      normalized == 'terim ustasi' ||
      normalized == 'term master' ||
      normalized == 'terim avcısı' ||
      normalized == 'terim avcisi') {
    return localizer.t('termMaster');
  }
  if (normalized == 'boss kırıcı' ||
      normalized == 'boss kirici' ||
      normalized == 'boss breaker') {
    return localizer.t('bossBreaker');
  }
  return title;
}

String _localizedAchievementLabel(
  AppLocalizer localizer,
  GameAchievement achievement,
) {
  final code = achievement.code.trim();
  if (code == 'first_upload') return localizer.t('firstUpload');
  if (code == 'first_explain') return localizer.t('firstExplain');
  if (code == 'first_evidence') return localizer.t('firstEvidence');
  if (code == 'first_self_check') return localizer.t('firstSelfCheck');
  if (code == 'first_fusion') return localizer.t('firstFusion');
  return _localizedProgressTitle(
    localizer,
    achievement.title.isNotEmpty ? achievement.title : achievement.code,
  );
}

List<String> _localizedRewardLabels(
  AppLocalizer localizer,
  GameRewards? rewards,
) {
  final labels = <String>[
    localizer.t('cheatSheetReward'),
    localizer.t('evidenceHunter'),
    localizer.t('termMaster'),
    localizer.t('bossBreaker'),
  ];
  for (final card in rewards?.cards ?? const <RewardCard>[]) {
    final label = _localizedRewardCardLabel(localizer, card);
    if (label.isNotEmpty && !labels.contains(label)) labels.add(label);
  }
  return labels;
}

String _localizedRewardCardLabel(AppLocalizer localizer, RewardCard card) {
  final type = card.type.trim().toLowerCase();
  if (type == 'cheatsheet' || type == 'cheat_sheet') {
    return localizer.t('cheatSheetReward');
  }
  if (card.title.trim().toLowerCase() == 'cheat sheet' ||
      card.title.trim().toLowerCase() == 'cheatsheet' ||
      card.title.trim().toLowerCase() == 'cheat sheet ödülü') {
    return localizer.t('cheatSheetReward');
  }
  if (type == 'evidence' || type == 'evidence_hunter') {
    return localizer.t('evidenceHunter');
  }
  if (type == 'term' || type == 'term_master' || type == 'concept') {
    return localizer.t('termMaster');
  }
  if (type == 'boss' || type == 'boss_breaker') {
    return localizer.t('bossBreaker');
  }
  return _localizedProgressTitle(localizer, card.title);
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
      title: localizer.t('partList'),
      subtitle: document == null
          ? localizer.t('partsAfterUpload')
          : localizer
                .t('partsCountShort')
                .replaceAll('{count}', '${parts.length}'),
      icon: Icons.article_outlined,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (status.isLoading) ...[
            const LinearProgressIndicator(),
            const SizedBox(height: 12),
            Text(localizer.t('partsPreparing')),
          ] else if (status == OperationStatus.error) ...[
            _InlineState(
              icon: Icons.error_outline_rounded,
              message: localizer.t('partsCouldNotLoadRetry'),
              error: true,
            ),
          ] else if (parts.isEmpty) ...[
            _InlineState(
              icon: Icons.info_outline_rounded,
              message: localizer.t('noPartsYetUpload'),
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
          _ResponsiveActionRow(
            children: [
              OutlinedButton.icon(
                onPressed: onReload,
                icon: const Icon(Icons.refresh_rounded),
                label: Text(localizer.t('refreshParts')),
              ),
              FilledButton.icon(
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
            ],
          ),
        ],
      ),
    );
  }
}

class _ResponsiveActionRow extends StatelessWidget {
  const _ResponsiveActionRow({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final stack = constraints.maxWidth < 420;
        if (stack) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (var index = 0; index < children.length; index++) ...[
                children[index],
                if (index != children.length - 1) const SizedBox(height: 10),
              ],
            ],
          );
        }
        return Row(
          children: [
            for (var index = 0; index < children.length; index++) ...[
              Expanded(child: children[index]),
              if (index != children.length - 1) const SizedBox(width: 10),
            ],
          ],
        );
      },
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
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontWeight: FontWeight.w700),
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
                      const SizedBox(height: 6),
                      Wrap(
                        spacing: 8,
                        runSpacing: 6,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        children: [
                          _DifficultyBadge(part: part),
                          Text(
                            localizer.t('startWithThisPart'),
                            overflow: TextOverflow.ellipsis,
                            style: Theme.of(context).textTheme.labelSmall
                                ?.copyWith(fontWeight: FontWeight.w700),
                          ),
                        ],
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

class _TestTimeSection extends StatelessWidget {
  const _TestTimeSection({
    required this.selectedMode,
    required this.status,
    required this.errorMessage,
    required this.quiz,
    required this.escapeRoom,
    required this.speedrun,
    required this.bossPayload,
    required this.bossResult,
    required this.bossRush,
    required this.bossStatus,
    required this.bossRushStatus,
    required this.bossErrorMessage,
    required this.quizSelections,
    required this.completedEscapeKeys,
    required this.onStart,
    required this.onStartBoss,
    required this.onAnswerBoss,
    required this.onLoadBossRush,
    required this.onSelectQuizAnswer,
    required this.onCompleteEscapeKey,
  });

  final String? selectedMode;
  final OperationStatus status;
  final String? errorMessage;
  final QuizRouletteResponse? quiz;
  final EscapeRoomResponse? escapeRoom;
  final SpeedrunResponse? speedrun;
  final BossPayload? bossPayload;
  final BossResult? bossResult;
  final BossRush? bossRush;
  final OperationStatus bossStatus;
  final OperationStatus bossRushStatus;
  final String? bossErrorMessage;
  final Map<int, String> quizSelections;
  final Set<int> completedEscapeKeys;
  final ValueChanged<String> onStart;
  final VoidCallback onStartBoss;
  final VoidCallback onAnswerBoss;
  final VoidCallback onLoadBossRush;
  final void Function(int index, String answer) onSelectQuizAnswer;
  final ValueChanged<int> onCompleteEscapeKey;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    return SectionCard(
      title: localizer.t('testTime'),
      subtitle: localizer.t('testTimeDescription'),
      icon: Icons.sports_score_outlined,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _GameStartChip(
                mode: 'quiz_roulette',
                label: localizer.t('quizRoulette'),
                icon: Icons.casino_outlined,
                selectedMode: selectedMode,
                status: status,
                onStart: onStart,
              ),
              _GameStartChip(
                mode: 'escape_room',
                label: localizer.t('escapeRoom'),
                icon: Icons.vpn_key_outlined,
                selectedMode: selectedMode,
                status: status,
                onStart: onStart,
              ),
              _GameStartChip(
                mode: 'speedrun',
                label: localizer.t('speedrun'),
                icon: Icons.timer_outlined,
                selectedMode: selectedMode,
                status: status,
                onStart: onStart,
              ),
              OutlinedButton.icon(
                onPressed: bossStatus.isLoading ? null : onStartBoss,
                icon: bossStatus.isLoading
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.local_fire_department_outlined),
                label: Text(localizer.t('bossFight')),
              ),
              OutlinedButton.icon(
                onPressed: bossRushStatus.isLoading ? null : onLoadBossRush,
                icon: const Icon(Icons.format_list_numbered_rounded),
                label: Text(localizer.t('bossRush')),
              ),
            ],
          ),
          if (status.isLoading) ...[
            const SizedBox(height: 12),
            const LinearProgressIndicator(),
          ],
          if (status == OperationStatus.error) ...[
            const SizedBox(height: 12),
            StatusMessage(
              message: errorMessage ?? localizer.t('tryAgain'),
              isError: true,
            ),
          ],
          if (selectedMode == 'quiz_roulette' && quiz != null) ...[
            const SizedBox(height: 12),
            _QuizRouletteBlock(
              response: quiz!,
              selections: quizSelections,
              onSelect: onSelectQuizAnswer,
            ),
          ],
          if (selectedMode == 'escape_room' && escapeRoom != null) ...[
            const SizedBox(height: 12),
            _EscapeRoomBlock(
              response: escapeRoom!,
              completedKeys: completedEscapeKeys,
              onComplete: onCompleteEscapeKey,
            ),
          ],
          if (selectedMode == 'speedrun' && speedrun != null) ...[
            const SizedBox(height: 12),
            _SpeedrunBlock(response: speedrun!),
          ],
          if (bossStatus == OperationStatus.error ||
              bossRushStatus == OperationStatus.error) ...[
            const SizedBox(height: 12),
            StatusMessage(
              message: bossErrorMessage ?? localizer.t('tryAgain'),
              isError: true,
            ),
          ],
          if (bossPayload != null) ...[
            const SizedBox(height: 12),
            _BossFightBlock(
              payload: bossPayload!,
              result: bossResult,
              status: bossStatus,
              onAnswer: onAnswerBoss,
            ),
          ],
          if (bossRush != null) ...[
            const SizedBox(height: 12),
            _BossRushBlock(rush: bossRush!),
          ],
        ],
      ),
    );
  }
}

class _BossFightBlock extends StatelessWidget {
  const _BossFightBlock({
    required this.payload,
    required this.result,
    required this.status,
    required this.onAnswer,
  });

  final BossPayload payload;
  final BossResult? result;
  final OperationStatus status;
  final VoidCallback onAnswer;

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
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              localizer.t('miniBoss'),
              style: Theme.of(
                context,
              ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 8),
            for (final question in payload.questions)
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Text('• $question'),
              ),
            if (payload.task.isNotEmpty) Text(payload.task),
            if (payload.miniTest.isNotEmpty) ...[
              const SizedBox(height: 8),
              CardListBlock(
                title: localizer.t('miniQuiz'),
                items: payload.miniTest,
              ),
            ],
            const SizedBox(height: 10),
            FilledButton.icon(
              onPressed: status.isLoading ? null : onAnswer,
              icon: const Icon(Icons.check_circle_outline_rounded),
              label: Text(localizer.t('answerBoss')),
            ),
            if (result != null) ...[
              const SizedBox(height: 10),
              Text(
                '${localizer.t('bossScore')}: ${(result!.score * 100).round()}',
                style: Theme.of(
                  context,
                ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
              ),
              Text(
                result!.passed
                    ? localizer.t('bossPassed')
                    : localizer.t('bossFailed'),
              ),
              const SizedBox(height: 8),
              CardListBlock(
                title: localizer.t('loot'),
                items: [
                  '${localizer.t('goldenSentence')}: ${result!.loot['golden_sentence'] ?? ''}',
                  '${localizer.t('trapWarning')}: ${result!.loot['trap_warning'] ?? ''}',
                  '${localizer.t('flashcard')}: ${ParseUtils.string(ParseUtils.asMap(result!.loot['flashcard'])['front']) ?? ''}',
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _BossRushBlock extends StatelessWidget {
  const _BossRushBlock({required this.rush});

  final BossRush rush;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          localizer.t('bossRush'),
          style: Theme.of(
            context,
          ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 8),
        for (final entry in rush.bosses.asMap().entries)
          ListTile(
            dense: true,
            leading: CircleAvatar(child: Text('${entry.key + 1}')),
            title: Text(
              entry.value.title.isEmpty
                  ? localizer.t('miniBoss')
                  : entry.value.title,
            ),
            subtitle: Text(
              entry.value.preview.isNotEmpty
                  ? entry.value.preview
                  : entry.value.questions.isEmpty
                  ? entry.value.status
                  : entry.value.questions.first,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
            trailing: const Icon(Icons.play_circle_outline_rounded),
          ),
      ],
    );
  }
}

class _GameStartChip extends StatelessWidget {
  const _GameStartChip({
    required this.mode,
    required this.label,
    required this.icon,
    required this.selectedMode,
    required this.status,
    required this.onStart,
  });

  final String mode;
  final String label;
  final IconData icon;
  final String? selectedMode;
  final OperationStatus status;
  final ValueChanged<String> onStart;

  @override
  Widget build(BuildContext context) {
    final selected = selectedMode == mode;
    return ActionChip(
      avatar: Icon(icon, size: 18),
      label: Text(label),
      onPressed: status.isLoading ? null : () => onStart(mode),
      backgroundColor: selected
          ? Theme.of(context).colorScheme.primaryContainer
          : null,
    );
  }
}

class _QuizRouletteBlock extends StatelessWidget {
  const _QuizRouletteBlock({
    required this.response,
    required this.selections,
    required this.onSelect,
  });

  final QuizRouletteResponse response;
  final Map<int, String> selections;
  final void Function(int index, String answer) onSelect;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    if (!response.enabled) {
      return StatusMessage(message: localizer.t('quizRoulette'));
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final entry in response.questions.asMap().entries)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: Theme.of(
                  context,
                ).colorScheme.surfaceContainerHighest.withValues(alpha: 0.35),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: Theme.of(context).colorScheme.outlineVariant,
                ),
              ),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: _QuizQuestionTile(
                  index: entry.key,
                  question: entry.value,
                  selected: selections[entry.key],
                  onSelect: onSelect,
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class _QuizQuestionTile extends StatelessWidget {
  const _QuizQuestionTile({
    required this.index,
    required this.question,
    required this.selected,
    required this.onSelect,
  });

  final int index;
  final GameQuestion question;
  final String? selected;
  final void Function(int index, String answer) onSelect;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    final answer = question.answer.trim();
    final isAnswered = selected != null;
    final isCorrect = selected?.trim().toLowerCase() == answer.toLowerCase();
    final options = question.options.isNotEmpty
        ? question.options
        : [localizer.t('showAnswer')];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          question.question,
          style: Theme.of(
            context,
          ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final option in options)
              ChoiceChip(
                label: Text(option),
                selected: selected == option,
                onSelected: (_) => onSelect(index, option),
              ),
          ],
        ),
        if (isAnswered) ...[
          const SizedBox(height: 8),
          Text(
            isCorrect || selected == localizer.t('showAnswer')
                ? '${localizer.t('correct')}: $answer'
                : '${localizer.t('wrong')}: $answer',
            style: TextStyle(
              fontWeight: FontWeight.w800,
              color: isCorrect || selected == localizer.t('showAnswer')
                  ? const Color(0xFF166534)
                  : const Color(0xFF991B1B),
            ),
          ),
          if (question.explanation.trim().isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(question.explanation),
          ],
        ],
      ],
    );
  }
}

class _EscapeRoomBlock extends StatelessWidget {
  const _EscapeRoomBlock({
    required this.response,
    required this.completedKeys,
    required this.onComplete,
  });

  final EscapeRoomResponse response;
  final Set<int> completedKeys;
  final ValueChanged<int> onComplete;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    final completed =
        response.keys.isNotEmpty &&
        response.keys.every((item) => completedKeys.contains(item.keyId));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final item in response.keys)
          Container(
            width: double.infinity,
            margin: const EdgeInsets.only(bottom: 10),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: completedKeys.contains(item.keyId)
                  ? const Color(0xFFEFF6EE)
                  : const Color(0xFFF8FAFC),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(0xFFE5EAF1)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${localizer.t('key')} ${item.keyId}: ${item.concept}',
                  style: const TextStyle(fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 6),
                Text(item.question),
                const SizedBox(height: 6),
                Text('${localizer.t('hint')}: ${item.hint}'),
                const SizedBox(height: 8),
                OutlinedButton.icon(
                  onPressed: () => onComplete(item.keyId),
                  icon: Icon(
                    completedKeys.contains(item.keyId)
                        ? Icons.lock_open_rounded
                        : Icons.visibility_outlined,
                  ),
                  label: Text(
                    completedKeys.contains(item.keyId)
                        ? localizer.t('completed')
                        : localizer.t('showAnswer'),
                  ),
                ),
                if (completedKeys.contains(item.keyId)) Text(item.answer),
              ],
            ),
          ),
        if (completed)
          StatusMessage(
            message: response.finalMessage.isNotEmpty
                ? response.finalMessage
                : localizer.t('completed'),
          ),
      ],
    );
  }
}

class _SpeedrunBlock extends StatelessWidget {
  const _SpeedrunBlock({required this.response});

  final SpeedrunResponse response;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        CardListBlock(
          title: localizer.t('criticalSentences'),
          items: response.criticalSentences,
        ),
        CardListBlock(
          title: localizer.t('miniQuiz'),
          items: response.miniQuiz
              .map((item) => '${item.question}\n${item.answer}')
              .toList(growable: false),
        ),
        CardListBlock(
          title: localizer.t('repairMistakes'),
          items: response.repairSteps,
        ),
      ],
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
    required this.selfCheckController,
    required this.selfCheckAnswer,
    required this.selfCheckResult,
    required this.selfCheckStatus,
    required this.selfCheckErrorMessage,
    required this.premiumPayload,
    required this.answer,
    required this.notes,
    required this.myNotes,
    required this.portalLinks,
    required this.activePortalNote,
    required this.concepts,
    required this.conceptRelations,
    required this.selectedConcept,
    required this.conceptMentions,
    required this.conceptStatus,
    required this.conceptErrorMessage,
    required this.selectedFusionTermA,
    required this.selectedFusionTermB,
    required this.fusionResult,
    required this.fusionStatus,
    required this.fusionErrorMessage,
    required this.directorsCutResult,
    required this.selectedDirectorsCutType,
    required this.directorsCutStatus,
    required this.directorsCutErrorMessage,
    required this.remixResult,
    required this.selectedRemixStyle,
    required this.remixStatus,
    required this.remixErrorMessage,
    required this.answerStatus,
    required this.notesStatus,
    required this.saveNoteStatus,
    required this.myNotesStatus,
    required this.portalStatus,
    required this.answerErrorMessage,
    required this.notesErrorMessage,
    required this.hasDocument,
    required this.showEvidenceComposer,
    required this.onQuestionChanged,
    required this.onSelfCheckAnswerChanged,
    required this.onToggleEvidenceComposer,
    required this.onToggleNoteForm,
    required this.onLoadPartNotes,
    required this.onLoadMyNotes,
    required this.onSaveNote,
    required this.onPortalLinks,
    required this.onGoToPortalLink,
    required this.onSelectConcept,
    required this.onShowConceptMentions,
    required this.onGoToMention,
    required this.onSelectFusionTermA,
    required this.onSelectFusionTermB,
    required this.onFuseConcepts,
    required this.onDirectorsCut,
    required this.onRemix,
    required this.onSelfCheck,
    required this.onAsk,
    required this.onClear,
    required this.showNoteForm,
    required this.showMyNotes,
    required this.noteTitleController,
    required this.noteBodyController,
    required this.noteConceptController,
  });

  final ExplainResponse? response;
  final OperationStatus status;
  final String? errorMessage;
  final bool hasSelectedPart;
  final Key evidenceKey;
  final TextEditingController controller;
  final String question;
  final TextEditingController selfCheckController;
  final String selfCheckAnswer;
  final SelfCheckResponse? selfCheckResult;
  final OperationStatus selfCheckStatus;
  final String? selfCheckErrorMessage;
  final PremiumUiPayload? premiumPayload;
  final EvidenceAnswer? answer;
  final List<SmartNote> notes;
  final List<SmartNote> myNotes;
  final List<PortalLink> portalLinks;
  final SmartNote? activePortalNote;
  final List<ConceptItem> concepts;
  final List<ConceptRelation> conceptRelations;
  final ConceptItem? selectedConcept;
  final List<ConceptMention> conceptMentions;
  final OperationStatus conceptStatus;
  final String? conceptErrorMessage;
  final String? selectedFusionTermA;
  final String? selectedFusionTermB;
  final FusionCard? fusionResult;
  final OperationStatus fusionStatus;
  final String? fusionErrorMessage;
  final DirectorsCutResponse? directorsCutResult;
  final String? selectedDirectorsCutType;
  final OperationStatus directorsCutStatus;
  final String? directorsCutErrorMessage;
  final RemixResponse? remixResult;
  final String? selectedRemixStyle;
  final OperationStatus remixStatus;
  final String? remixErrorMessage;
  final OperationStatus answerStatus;
  final OperationStatus notesStatus;
  final OperationStatus saveNoteStatus;
  final OperationStatus myNotesStatus;
  final OperationStatus portalStatus;
  final String? answerErrorMessage;
  final String? notesErrorMessage;
  final bool hasDocument;
  final bool showEvidenceComposer;
  final ValueChanged<String> onQuestionChanged;
  final ValueChanged<String> onSelfCheckAnswerChanged;
  final VoidCallback onToggleEvidenceComposer;
  final VoidCallback onToggleNoteForm;
  final VoidCallback onLoadPartNotes;
  final VoidCallback onLoadMyNotes;
  final VoidCallback onSaveNote;
  final ValueChanged<SmartNote> onPortalLinks;
  final ValueChanged<PortalLink> onGoToPortalLink;
  final ValueChanged<ConceptItem> onSelectConcept;
  final ValueChanged<ConceptItem> onShowConceptMentions;
  final ValueChanged<ConceptMention> onGoToMention;
  final ValueChanged<String?> onSelectFusionTermA;
  final ValueChanged<String?> onSelectFusionTermB;
  final VoidCallback onFuseConcepts;
  final ValueChanged<String> onDirectorsCut;
  final ValueChanged<String> onRemix;
  final VoidCallback onSelfCheck;
  final VoidCallback onAsk;
  final VoidCallback onClear;
  final bool showNoteForm;
  final bool showMyNotes;
  final TextEditingController noteTitleController;
  final TextEditingController noteBodyController;
  final TextEditingController noteConceptController;

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
                if (premiumPayload != null)
                  _PremiumIndicators(payload: premiumPayload!),
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
                _ConceptFusionLabPanel(
                  concepts: visibleConcepts,
                  selectedTermA: selectedFusionTermA,
                  selectedTermB: selectedFusionTermB,
                  result: fusionResult,
                  status: fusionStatus,
                  errorMessage: fusionErrorMessage,
                  onSelectTermA: onSelectFusionTermA,
                  onSelectTermB: onSelectFusionTermB,
                  onFuse: onFuseConcepts,
                ),
                const SizedBox(height: 14),
                _SelfCheckPanel(
                  controller: selfCheckController,
                  answer: selfCheckAnswer,
                  result: selfCheckResult,
                  status: selfCheckStatus,
                  errorMessage: selfCheckErrorMessage,
                  onChanged: onSelfCheckAnswerChanged,
                  onCheck: onSelfCheck,
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
                Expanded(
                  child: Text(
                    localizer.t('conceptMap'),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
                  ),
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
                onPressed: status.isLoading
                    ? null
                    : () => onShowMentions(selected),
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

class _ConceptFusionLabPanel extends StatelessWidget {
  const _ConceptFusionLabPanel({
    required this.concepts,
    required this.selectedTermA,
    required this.selectedTermB,
    required this.result,
    required this.status,
    required this.errorMessage,
    required this.onSelectTermA,
    required this.onSelectTermB,
    required this.onFuse,
  });

  final List<ConceptItem> concepts;
  final String? selectedTermA;
  final String? selectedTermB;
  final FusionCard? result;
  final OperationStatus status;
  final String? errorMessage;
  final ValueChanged<String?> onSelectTermA;
  final ValueChanged<String?> onSelectTermB;
  final VoidCallback onFuse;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    final terms = <String>[];
    for (final concept in concepts) {
      final term = concept.term.trim();
      if (term.isNotEmpty && !terms.contains(term)) terms.add(term);
    }
    if (terms.length < 2) return const SizedBox.shrink();
    final canFuse =
        selectedTermA?.trim().isNotEmpty == true &&
        selectedTermB?.trim().isNotEmpty == true &&
        selectedTermA?.toLowerCase() != selectedTermB?.toLowerCase() &&
        !status.isLoading;
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
                  Icons.hub_outlined,
                  color: Theme.of(context).colorScheme.primary,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        localizer.t('conceptFusionLab'),
                        style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        localizer.t('conceptFusionDescription'),
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              initialValue: terms.contains(selectedTermA)
                  ? selectedTermA
                  : null,
              decoration: InputDecoration(
                labelText: localizer.t('selectFirstConcept'),
              ),
              items: [
                for (final term in terms)
                  DropdownMenuItem(value: term, child: Text(term)),
              ],
              onChanged: status.isLoading ? null : onSelectTermA,
            ),
            const SizedBox(height: 10),
            DropdownButtonFormField<String>(
              initialValue: terms.contains(selectedTermB)
                  ? selectedTermB
                  : null,
              decoration: InputDecoration(
                labelText: localizer.t('selectSecondConcept'),
              ),
              items: [
                for (final term in terms)
                  DropdownMenuItem(value: term, child: Text(term)),
              ],
              onChanged: status.isLoading ? null : onSelectTermB,
            ),
            const SizedBox(height: 10),
            FilledButton.icon(
              onPressed: canFuse ? onFuse : null,
              icon: status.isLoading
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.auto_awesome_rounded),
              label: Text(localizer.t('fuseConcepts')),
            ),
            if (selectedTermA?.toLowerCase() == selectedTermB?.toLowerCase() &&
                selectedTermA?.trim().isNotEmpty == true) ...[
              const SizedBox(height: 10),
              StatusMessage(
                message: localizer.t('fusionTermsMustDiffer'),
                isError: true,
              ),
            ],
            if (errorMessage != null) ...[
              const SizedBox(height: 10),
              StatusMessage(message: errorMessage!, isError: true),
            ],
            if (status.isLoading) ...[
              const SizedBox(height: 10),
              const LinearProgressIndicator(),
            ],
            if (result != null && !result!.isEmpty) ...[
              const SizedBox(height: 14),
              _FusionCardView(card: result!),
            ],
          ],
        ),
      ),
    );
  }
}

class _FusionCardView extends StatelessWidget {
  const _FusionCardView({required this.card});

  final FusionCard card;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          card.title.isNotEmpty ? card.title : '${card.termA} + ${card.termB}',
          style: Theme.of(
            context,
          ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
        ),
        CardListBlock(
          title: localizer.t('commonPoints'),
          items: card.commonPoints,
        ),
        if (card.differences.isNotEmpty) ...[
          const SizedBox(height: 10),
          Text(
            localizer.t('differences'),
            style: Theme.of(
              context,
            ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 6),
          for (final item in card.differences)
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
                      if (item.termA.isNotEmpty) Text(item.termA),
                      if (item.termB.isNotEmpty) ...[
                        const SizedBox(height: 4),
                        Text(item.termB),
                      ],
                    ],
                  ),
                ),
              ),
            ),
        ],
        if (card.togetherExample.isNotEmpty)
          TextBlock(
            title: localizer.t('togetherExample'),
            text: card.togetherExample,
          ),
        if (card.miniQuestion.question.isNotEmpty)
          TextBlock(
            title: localizer.t('miniQuestion'),
            text: card.miniQuestion.answer.isNotEmpty
                ? '${card.miniQuestion.question}\n${card.miniQuestion.answer}'
                : card.miniQuestion.question,
          ),
        if (card.evidenceSnippets.isNotEmpty) ...[
          const SizedBox(height: 8),
          Text(
            localizer.t('evidence'),
            style: Theme.of(
              context,
            ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
          ),
          for (final evidence in card.evidenceSnippets)
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.article_outlined),
              title: Text(
                evidence.path.isNotEmpty
                    ? evidence.path
                    : 'Parça ${evidence.partId}',
              ),
              subtitle: Text(evidence.snippet),
            ),
        ],
        if (card.warning.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              card.warning,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
      ],
    );
  }
}

class _SmartNotesPanel extends StatelessWidget {
  const _SmartNotesPanel({
    required this.notes,
    required this.myNotes,
    required this.portalLinks,
    required this.activePortalNote,
    required this.notesStatus,
    required this.saveNoteStatus,
    required this.myNotesStatus,
    required this.portalStatus,
    required this.errorMessage,
    required this.showForm,
    required this.showMyNotes,
    required this.titleController,
    required this.bodyController,
    required this.conceptController,
    required this.onToggleForm,
    required this.onLoadPartNotes,
    required this.onLoadMyNotes,
    required this.onSave,
    required this.onPortalLinks,
    required this.onGoToPortalLink,
  });

  final List<SmartNote> notes;
  final List<SmartNote> myNotes;
  final List<PortalLink> portalLinks;
  final SmartNote? activePortalNote;
  final OperationStatus notesStatus;
  final OperationStatus saveNoteStatus;
  final OperationStatus myNotesStatus;
  final OperationStatus portalStatus;
  final String? errorMessage;
  final bool showForm;
  final bool showMyNotes;
  final TextEditingController titleController;
  final TextEditingController bodyController;
  final TextEditingController conceptController;
  final VoidCallback onToggleForm;
  final VoidCallback onLoadPartNotes;
  final VoidCallback onLoadMyNotes;
  final VoidCallback onSave;
  final ValueChanged<SmartNote> onPortalLinks;
  final ValueChanged<PortalLink> onGoToPortalLink;

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
              children: [
                Icon(
                  Icons.sticky_note_2_outlined,
                  color: Theme.of(context).colorScheme.primary,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    localizer.t('smartNotes'),
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                OutlinedButton.icon(
                  onPressed: saveNoteStatus.isLoading ? null : onToggleForm,
                  icon: const Icon(Icons.add_rounded),
                  label: Text(localizer.t('addNote')),
                ),
                OutlinedButton.icon(
                  onPressed: notesStatus.isLoading ? null : onLoadPartNotes,
                  icon: notesStatus.isLoading
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.refresh_rounded),
                  label: Text(localizer.t('notesSaved')),
                ),
                OutlinedButton.icon(
                  onPressed: myNotesStatus.isLoading ? null : onLoadMyNotes,
                  icon: const Icon(Icons.list_alt_rounded),
                  label: Text(localizer.t('myNotes')),
                ),
              ],
            ),
            if (showForm) ...[
              const SizedBox(height: 12),
              TextField(
                controller: titleController,
                decoration: InputDecoration(
                  labelText: localizer.t('noteTitle'),
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: bodyController,
                minLines: 3,
                maxLines: 5,
                decoration: InputDecoration(labelText: localizer.t('noteBody')),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: conceptController,
                decoration: InputDecoration(labelText: localizer.t('concepts')),
              ),
              const SizedBox(height: 10),
              FilledButton.icon(
                onPressed: saveNoteStatus.isLoading ? null : onSave,
                icon: saveNoteStatus.isLoading
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.save_outlined),
                label: Text(localizer.t('saveNote')),
              ),
            ],
            if (errorMessage != null) ...[
              const SizedBox(height: 10),
              StatusMessage(message: errorMessage!, isError: true),
            ],
            const SizedBox(height: 12),
            if (notesStatus == OperationStatus.empty && notes.isEmpty)
              _InlineState(
                icon: Icons.info_outline_rounded,
                message: localizer.t('noNotesYet'),
              ),
            for (final note in notes)
              _NoteTile(note: note, onPortalLinks: onPortalLinks),
            if (showMyNotes) ...[
              const SizedBox(height: 12),
              Text(
                localizer.t('myNotes'),
                style: Theme.of(
                  context,
                ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
              ),
              if (myNotesStatus == OperationStatus.empty && myNotes.isEmpty)
                _InlineState(
                  icon: Icons.info_outline_rounded,
                  message: localizer.t('noNotesYet'),
                ),
              for (final note in myNotes)
                _NoteTile(note: note, onPortalLinks: onPortalLinks),
            ],
            if (activePortalNote != null ||
                portalStatus.isLoading ||
                portalLinks.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text(
                localizer.t('portalNotes'),
                style: Theme.of(
                  context,
                ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
              ),
              if (portalStatus.isLoading) const LinearProgressIndicator(),
              if (portalStatus == OperationStatus.empty)
                _InlineState(
                  icon: Icons.link_off_rounded,
                  message: localizer.t('portalLinks'),
                ),
              for (final link in portalLinks)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      border: Border.all(
                        color: Theme.of(context).colorScheme.outlineVariant,
                      ),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Padding(
                      padding: const EdgeInsets.all(10),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Row(
                            children: [
                              const Icon(Icons.open_in_new_rounded, size: 18),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text(
                                  link.title.isNotEmpty
                                      ? link.title
                                      : link.path,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 4),
                          Text(
                            link.snippet.isNotEmpty
                                ? link.snippet
                                : link.reason,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                          Align(
                            alignment: AlignmentDirectional.centerEnd,
                            child: TextButton(
                              onPressed: () => onGoToPortalLink(link),
                              child: Text(localizer.t('goToThisPart')),
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

class _NoteTile extends StatelessWidget {
  const _NoteTile({required this.note, required this.onPortalLinks});

  final SmartNote note;
  final ValueChanged<SmartNote> onPortalLinks;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: DecoratedBox(
        decoration: BoxDecoration(
          border: Border.all(
            color: Theme.of(context).colorScheme.outlineVariant,
          ),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  const Icon(Icons.notes_rounded, size: 18),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      note.title.isNotEmpty
                          ? note.title
                          : localizer.t('smartNotes'),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Text(note.body, maxLines: 2, overflow: TextOverflow.ellipsis),
              Align(
                alignment: AlignmentDirectional.centerEnd,
                child: TextButton(
                  onPressed: () => onPortalLinks(note),
                  child: Text(localizer.t('portalLinks')),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SelfCheckPanel extends StatelessWidget {
  const _SelfCheckPanel({
    required this.controller,
    required this.answer,
    required this.result,
    required this.status,
    required this.errorMessage,
    required this.onChanged,
    required this.onCheck,
  });

  final TextEditingController controller;
  final String answer;
  final SelfCheckResponse? result;
  final OperationStatus status;
  final String? errorMessage;
  final ValueChanged<String> onChanged;
  final VoidCallback onCheck;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    final canSubmit = answer.trim().isNotEmpty && !status.isLoading;
    return Container(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                Icons.fact_check_outlined,
                color: Theme.of(context).colorScheme.primary,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  localizer.t('selfCheck'),
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(localizer.t('selfCheckDescription')),
          const SizedBox(height: 12),
          TextField(
            controller: controller,
            minLines: 3,
            maxLines: 5,
            onChanged: onChanged,
            decoration: InputDecoration(
              labelText: localizer.t('writeYourUnderstanding'),
              border: const OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 10),
          Align(
            alignment: Alignment.centerRight,
            child: FilledButton.icon(
              onPressed: canSubmit ? onCheck : null,
              icon: status.isLoading
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.check_circle_outline),
              label: Text(localizer.t('checkAnswer')),
            ),
          ),
          if (status == OperationStatus.error) ...[
            const SizedBox(height: 10),
            StatusMessage(
              message: errorMessage ?? localizer.t('selfCheckFailed'),
              isError: true,
            ),
          ],
          if (status == OperationStatus.success && result != null) ...[
            const SizedBox(height: 12),
            _SelfCheckResultBlock(result: result!),
          ],
        ],
      ),
    );
  }
}

class _SelfCheckResultBlock extends StatelessWidget {
  const _SelfCheckResultBlock({required this.result});

  final SelfCheckResponse result;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    final percent = (result.score * 100).round();
    final levelKey = switch (result.level) {
      'iyi' || 'good' => 'good',
      'orta' || 'medium' => 'medium',
      _ => 'weak',
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '${localizer.t('selfCheckScore')}: $percent/100 (${localizer.t(levelKey)})',
          style: Theme.of(
            context,
          ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
        ),
        if (result.warning?.trim().isNotEmpty == true)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: StatusMessage(message: result.warning!),
          ),
        CardListBlock(
          title: localizer.t('correctPoints'),
          items: result.correctPoints,
        ),
        CardListBlock(
          title: localizer.t('wrongPoints'),
          items: result.wrongPoints,
        ),
        CardListBlock(
          title: localizer.t('missingPoints'),
          items: result.missingPoints,
        ),
        if (result.improvedAnswer?.trim().isNotEmpty == true)
          TextBlock(
            title: localizer.t('improvedAnswer'),
            text: result.improvedAnswer!,
          ),
        CardListBlock(
          title: localizer.t('evidence'),
          items: result.evidenceSnippets
              .map((item) => item.displayText)
              .toList(growable: false),
        ),
      ],
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
