import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:mobil/core/constants/app_constants.dart';
import 'package:mobil/core/files/file_type_config.dart';
import 'package:mobil/core/i18n/app_language.dart';
import 'package:mobil/core/i18n/app_localizer.dart';
import 'package:mobil/core/i18n/messages.dart';
import 'package:mobil/core/network/api_client.dart';
import 'package:mobil/core/network/api_exception.dart';
import 'package:mobil/features/concepts/data/concept_models.dart';
import 'package:mobil/features/concepts/data/fusion_card.dart';
import 'package:mobil/features/documents/data/document_part.dart';
import 'package:mobil/features/documents/data/uploaded_document.dart';
import 'package:mobil/features/auth/presentation/login_screen.dart';
import 'package:mobil/features/excel/data/excel_models.dart';
import 'package:mobil/features/explain/data/directors_cut_response.dart';
import 'package:mobil/features/explain/data/explain_response.dart';
import 'package:mobil/features/explain/data/learning_game_response.dart';
import 'package:mobil/features/explain/data/remix_response.dart';
import 'package:mobil/features/explain/data/self_check_response.dart';
import 'package:mobil/features/home/presentation/home_screen.dart';
import 'package:mobil/features/home/data/game_models.dart';
import 'package:mobil/features/home/widgets/backend_flow_panel.dart';
import 'package:mobil/features/notes/data/smart_note.dart';
import 'package:mobil/features/outputs/data/export_payload_models.dart';
import 'package:mobil/features/outputs/data/reels_models.dart';
import 'package:mobil/features/preferences/data/learning_preferences.dart';
import 'package:mobil/features/qa/data/evidence_answer.dart';
import 'package:mobil/services/ai_service.dart';
import 'package:mobil/services/concept_service.dart';
import 'package:mobil/services/document_service.dart';
import 'package:mobil/services/export_service.dart';
import 'package:mobil/services/game_service.dart';
import 'package:mobil/services/excel_service.dart';
import 'package:mobil/services/note_service.dart';
import 'package:mobil/services/preference_service.dart';
import 'package:mobil/services/reels_service.dart';
import 'package:mobil/shared/widgets/language_picker.dart';

class _CaptureClient extends http.BaseClient {
  _CaptureClient(this.response);

  final http.Response response;
  final requests = <http.BaseRequest>[];

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    requests.add(request);
    return http.StreamedResponse(
      Stream<List<int>>.value(response.bodyBytes),
      response.statusCode,
      headers: response.headers,
      request: request,
    );
  }
}

class _FakeAiService extends AiService {
  _FakeAiService({
    required this.explain,
    EvidenceAnswer? answer,
    DirectorsCutResponse? directorsCut,
    RemixResponse? remix,
    SelfCheckResponse? selfCheck,
    QuizRouletteResponse? quizRoulette,
    EscapeRoomResponse? escapeRoom,
    SpeedrunResponse? speedrun,
    this.directorsCutDelay = Duration.zero,
    this.remixDelay = Duration.zero,
  }) : answer =
           answer ??
           const EvidenceAnswer(
             answer: 'ATP enerji aktarımında kullanılır.',
             evidence: [],
           ),
       directorsCut =
           directorsCut ??
           const DirectorsCutResponse(
             cutType: 'quick',
             title: 'Hızlı Cut',
             summary: 'ATP enerji taşır.',
             sections: [
               DirectorsCutSection(
                 title: 'Kritik cümleler',
                 items: ['ATP hücre enerjisinde kullanılır.'],
               ),
             ],
           ),
       remix =
           remix ??
           const RemixResponse(
             style: 'short',
             title: 'Kısa anlatım',
             content: 'ATP enerji taşır.',
             items: ['Hücre iş yaparken ATP kullanır.'],
           ),
       selfCheck =
           selfCheck ??
           const SelfCheckResponse(
             score: 0.74,
             level: 'iyi',
             correctPoints: ['JWT kimlik bilgisini taşır.'],
             wrongPoints: ['Refresh token atlanmış.'],
             missingPoints: ['Yenileme akışı eksik.'],
             improvedAnswer:
                 'JWT kimliği taşır, refresh token yeni erişim sağlar.',
             evidenceSnippets: [
               SelfCheckEvidenceSnippet(
                 text: 'JWT access token kullanicinin kimligini tasir.',
                 source: 'Test dokumani',
                 path: '1.1',
               ),
             ],
           ),
       quizRoulette =
           quizRoulette ??
           const QuizRouletteResponse(
             questions: [
               GameQuestion(
                 type: 'multiple_choice',
                 question: 'ATP ne taşır?',
                 options: ['Enerji', 'Su', 'Tuz', 'Işık'],
                 answer: 'Enerji',
                 explanation: 'ATP enerji taşır.',
               ),
             ],
           ),
       escapeRoom =
           escapeRoom ??
           const EscapeRoomResponse(
             keys: [
               EscapeKey(
                 keyId: 1,
                 concept: 'ATP',
                 question: 'ATP nedir?',
                 answer: 'Enerji molekülü.',
                 hint: 'Enerjiye bak.',
               ),
               EscapeKey(
                 keyId: 2,
                 concept: 'Fosfat',
                 question: 'Fosfat ne sağlar?',
                 answer: 'Bağ enerjisi.',
                 hint: 'Bağlara bak.',
               ),
               EscapeKey(
                 keyId: 3,
                 concept: 'Taşıma',
                 question: 'Taşıma nasıl olur?',
                 answer: 'ATP ile.',
                 hint: 'Hareketi bul.',
               ),
             ],
             finalMessage: 'Çıkış açıldı.',
           ),
       speedrun =
           speedrun ??
           const SpeedrunResponse(
             criticalSentences: ['ATP enerji taşır.'],
             miniQuiz: [
               GameQuestion(
                 type: 'short_answer',
                 question: 'ATP ne işe yarar?',
                 answer: 'Enerji taşır.',
               ),
             ],
             repairSteps: ['Yanlış kavramı tekrar oku.'],
           );

  final ExplainResponse explain;
  final EvidenceAnswer answer;
  final DirectorsCutResponse directorsCut;
  final RemixResponse remix;
  final SelfCheckResponse selfCheck;
  final QuizRouletteResponse quizRoulette;
  final EscapeRoomResponse escapeRoom;
  final SpeedrunResponse speedrun;
  final Duration directorsCutDelay;
  final Duration remixDelay;
  LearningPreferences? lastExplainPreferences;
  LearningPreferences? lastEvidencePreferences;
  LearningPreferences? lastRemixPreferences;
  LearningPreferences? lastDirectorsCutPreferences;
  LearningPreferences? lastSelfCheckPreferences;

  @override
  Future<ExplainResponse> askExplain({
    required int partId,
    Map<String, dynamic>? payload,
    LearningPreferences? preferences,
  }) async {
    lastExplainPreferences = preferences;
    return explain;
  }

  @override
  Future<EvidenceAnswer> askEvidenceAnswer({
    required int documentId,
    int? partId,
    required String question,
    LearningPreferences? preferences,
  }) async {
    lastEvidencePreferences = preferences;
    return answer;
  }

  @override
  Future<RemixResponse> requestRemix({
    required int partId,
    required String style,
    Map<String, dynamic>? source,
    String? lang,
    LearningPreferences? preferences,
  }) async {
    lastRemixPreferences = preferences;
    if (remixDelay > Duration.zero) {
      await Future<void>.delayed(remixDelay);
    }
    return remix;
  }

  @override
  Future<DirectorsCutResponse> requestDirectorsCut({
    required int partId,
    required String cutType,
    Map<String, dynamic>? source,
    String? lang,
    LearningPreferences? preferences,
  }) async {
    lastDirectorsCutPreferences = preferences;
    if (directorsCutDelay > Duration.zero) {
      await Future<void>.delayed(directorsCutDelay);
    }
    return directorsCut;
  }

  @override
  Future<SelfCheckResponse> requestSelfCheck({
    required int partId,
    required String answer,
    String? lang,
    LearningPreferences? preferences,
  }) async {
    lastSelfCheckPreferences = preferences;
    return selfCheck;
  }

  @override
  Future<QuizRouletteResponse> requestQuizRoulette({
    required int partId,
    LearningPreferences? preferences,
  }) async {
    return quizRoulette;
  }

  @override
  Future<EscapeRoomResponse> requestEscapeRoom({
    required int partId,
    LearningPreferences? preferences,
  }) async {
    return escapeRoom;
  }

  @override
  Future<SpeedrunResponse> requestSpeedrun({
    required int partId,
    LearningPreferences? preferences,
  }) async {
    return speedrun;
  }
}

class _FakeDocumentService extends DocumentService {
  int uploadCount = 0;
  int partsCount = 0;
  String? lastUploadPath;

  @override
  Future<UploadedDocument> uploadDocument(String filePath) async {
    uploadCount += 1;
    lastUploadPath = filePath;
    return _testDocument;
  }

  @override
  Future<List<DocumentPart>> getDocumentParts(int documentId) async {
    partsCount += 1;
    return _testParts;
  }
}

class _FakePreferenceService extends PreferenceService {
  _FakePreferenceService({this.fetchResult = const LearningPreferences()});

  LearningPreferences fetchResult;
  LearningPreferences? lastSaved;
  int fetchCount = 0;
  int saveCount = 0;

  @override
  Future<LearningPreferences> fetchPreferences() async {
    fetchCount += 1;
    return fetchResult;
  }

  @override
  Future<LearningPreferences> savePreferences(
    LearningPreferences preferences,
  ) async {
    saveCount += 1;
    lastSaved = preferences;
    return preferences;
  }
}

class _FakeConceptService extends ConceptService {
  _FakeConceptService({
    required this.searchResponse,
    this.fusionResponse = const FusionCard(),
  });

  final ConceptGraphResponse searchResponse;
  final FusionCard fusionResponse;
  String? lastTermA;
  String? lastTermB;

  @override
  Future<ConceptGraphResponse> searchConceptMentions(
    int documentId,
    String query,
  ) async {
    return searchResponse;
  }

  @override
  Future<FusionCard> requestConceptFusion({
    required int documentId,
    required String termA,
    required String termB,
    int? partId,
    LearningPreferences? preferences,
  }) async {
    lastTermA = termA;
    lastTermB = termB;
    return fusionResponse;
  }
}

class _FakeNoteService extends NoteService {
  _FakeNoteService({
    this.partNotes = const [],
    // ignore: unused_element_parameter
    this.myNotes = const [],
    this.portalLinks = const [],
  });

  List<SmartNote> partNotes;
  List<SmartNote> myNotes;
  List<PortalLink> portalLinks;
  SmartNote? lastCreated;
  int? lastPortalNoteId;

  @override
  Future<List<SmartNote>> getPartNotes(int partId) async => partNotes;

  @override
  Future<List<SmartNote>> getMyNotes() async => myNotes;

  @override
  Future<SmartNote> createNote({
    required int partId,
    required String title,
    required String body,
    String conceptTerm = '',
  }) async {
    lastCreated = SmartNote(
      id: 99,
      partId: partId,
      title: title,
      body: body,
      conceptTerm: conceptTerm,
    );
    partNotes = [lastCreated!, ...partNotes];
    return lastCreated!;
  }

  @override
  Future<List<PortalLink>> getPortalLinks(int noteId) async {
    lastPortalNoteId = noteId;
    return portalLinks;
  }
}

class _FakeGameService extends GameService {
  GameProfile profile = const GameProfile(
    enabled: true,
    xpTotal: 240,
    level: 3,
    title: 'Terim Avcısı',
    progressRatio: 0.4,
    achievements: [GameAchievement(code: 'first_upload', title: 'İlk yükleme')],
  );
  GameRewards rewards = const GameRewards(
    enabled: true,
    cards: [
      RewardCard(
        type: 'cheatsheet',
        title: 'Cheat Sheet ödülü',
        description: 'Hazır',
        unlocked: true,
      ),
    ],
  );
  WeeklyProgress weekly = const WeeklyProgress(
    enabled: true,
    summary: 'Bu hafta 120 XP topladın.',
    xpThisWeek: 120,
  );

  @override
  Future<GameProfile> fetchProfile() async => profile;

  @override
  Future<GameRewards> fetchRewards() async => rewards;

  @override
  Future<WeeklyProgress> fetchWeeklyProgress() async => weekly;

  @override
  Future<BossPayload> startBossFight(int partId) async => const BossPayload(
    enabled: true,
    bossId: 'boss-1',
    title: 'Mini Boss',
    questions: ['Ana fikir nedir?', 'Terimi açıkla.'],
    task: 'Tuzak noktayı bul.',
    miniTest: ['Kritik terim?'],
  );

  @override
  Future<BossResult> answerBoss({
    required int partId,
    required String bossId,
    required List<String> answers,
  }) async => const BossResult(
    score: 0.8,
    passed: true,
    loot: {
      'golden_sentence': 'Altın cümle',
      'trap_warning': 'Tuzak uyarısı',
      'flashcard': {'front': 'ATP'},
    },
    xpAwarded: 35,
  );

  @override
  Future<BossRush> fetchBossRush(int documentId) async => const BossRush(
    enabled: true,
    bosses: [
      BossPayload(
        enabled: true,
        bossId: 'boss-1',
        title: 'Mini Boss',
        questions: ['Ana fikir nedir?'],
      ),
    ],
  );
}

class _FakeExcelService extends ExcelService {
  _FakeExcelService({
    // ignore: unused_element_parameter
    this.summary = const ExcelSummary(
      sheets: [
        ExcelSheetSummary(
          name: 'Sheet1',
          rowCount: 3,
          columnCount: 2,
          columns: ['Urun', 'Tutar'],
          summary: 'Bu tablo urun tutarlarini gosterir.',
        ),
      ],
    ),
    // ignore: unused_element_parameter
    this.formula = const ExcelFormulaExplanation(
      formula: '=IF(A1>10,"Gecti","Kaldi")',
      steps: ['Kosul kontrol edilir.'],
      plainExplanation: 'Bu formul kosula gore sonuc dondurur.',
    ),
    // ignore: unused_element_parameter
    this.answer = const ExcelQuestionAnswer(
      answer: 'En yuksek deger Sheet1 satir 3.',
      evidenceRows: [
        {
          'sheet': 'Sheet1',
          'row_number': 3,
          'values': {'Urun': 'Defter', 'Tutar': 84},
        },
      ],
      source: 'fallback',
    ),
  });

  final ExcelSummary summary;
  final ExcelFormulaExplanation formula;
  final ExcelQuestionAnswer answer;

  @override
  Future<ExcelSummary> fetchExcelSummary(int documentId) async => summary;

  @override
  Future<ExcelFormulaExplanation> explainFormula({
    required int documentId,
    required String formula,
  }) async => this.formula;

  @override
  Future<ExcelQuestionAnswer> askExcelQuestion({
    required int documentId,
    required String question,
  }) async => answer;
}

_FakeGameService _emptyProgressGame() {
  return _FakeGameService()
    ..profile = const GameProfile(
      enabled: true,
      xpTotal: 0,
      level: 1,
      title: 'Yeni Kaşif',
    )
    ..weekly = const WeeklyProgress(
      enabled: true,
      summary: 'Bu hafta henüz XP hareketi yok.',
      xpThisWeek: 0,
    )
    ..rewards = const GameRewards(
      enabled: true,
      cards: [
        RewardCard(
          type: 'evidence_hunter',
          title: 'Kanıt Avcısı',
          description: '',
          unlocked: true,
        ),
        RewardCard(
          type: 'term_master',
          title: 'Terim Ustası',
          description: '',
          unlocked: true,
        ),
        RewardCard(
          type: 'boss_breaker',
          title: 'Boss Kırıcı',
          description: '',
          unlocked: true,
        ),
      ],
    );
}

class _FakeReelsService extends ReelsService {
  int fetchCount = 0;

  @override
  Future<ReelsPayload> fetchPartReels(int partId) async {
    fetchCount += 1;
    return const ReelsPayload(
      cards: [
        ReelCard(
          cardNo: 1,
          title: 'ATP mini karti',
          summary: [
            'ATP enerji taşır.',
            'Fosfat bağları önemlidir.',
            'Hücre bunu kullanır.',
          ],
          example: 'ATP pil gibi enerji sağlar.',
          question: 'ATP ne taşır?',
          answer: 'Enerji taşır.',
          source: 'fallback',
        ),
      ],
    );
  }
}

class _FakeExportService extends ExportService {
  @override
  Future<ExportPayload> fetchCheatsheet(int documentId) async =>
      ExportPayload.fromDynamic('cheatsheet', {
        'enabled': true,
        'title': 'ATP Cheat Sheet',
        'golden_sentences': ['ATP enerji taşır.'],
        'trap_points': ['ATP besin değildir.'],
      });

  @override
  Future<ExportPayload> fetchStudySummary(int documentId) async =>
      ExportPayload.fromDynamic('study_summary', {
        'enabled': true,
        'title': 'Ders özeti',
        'summary': ['ATP konusu kısa özetlendi.'],
      });

  @override
  Future<ExportPayload> fetchPresentationPlan(int documentId) async =>
      ExportPayload.fromDynamic('presentation_plan', {
        'enabled': true,
        'title': 'Sunum',
        'slides': [
          {
            'title': 'Slayt 1',
            'bullets': ['ATP enerji taşır.'],
            'speaker_notes': 'ATP girişini anlat.',
          },
        ],
      });

  @override
  Future<ExportPayload> fetchReadme(int documentId) async =>
      ExportPayload.fromDynamic('readme', {
        'enabled': true,
        'title': 'README',
        'sections': [
          {
            'title': 'Kurulum',
            'items': ['Adımları izle.'],
          },
        ],
      });

  @override
  Future<ExportPayload> fetchReadiness(int documentId) async =>
      ExportPayload.fromDynamic('readiness', {
        'enabled': true,
        'score': 0.82,
        'ready_exports': ['cheatsheet'],
      });

  @override
  Future<PremiumUiPayload> fetchPremiumPayload(int documentId) async =>
      const PremiumUiPayload(
        clarity: 0.8,
        examples: 0.7,
        testReadiness: 0.6,
        teleports: [
          {'etiket': 'Tanıma git'},
        ],
      );
}

Widget _localizedGuestApp() {
  return _localizedPanelApp(isGuest: true);
}

Widget _localizedPanelApp({
  bool isGuest = false,
  DocumentService? documentService,
  AiService? aiService,
  ConceptService? conceptService,
  ExcelService? excelService,
  ExportService? exportService,
  NoteService? noteService,
  PreferenceService? preferenceService,
  GameService? gameService,
  ReelsService? reelsService,
}) {
  return AppLanguageScope(
    controller: appLanguageController,
    child: MaterialApp(
      builder: (context, child) => Directionality(
        textDirection: AppLocalizer.textDirectionOf(context),
        child: child ?? const SizedBox.shrink(),
      ),
      home: Scaffold(
        resizeToAvoidBottomInset: true,
        body: SingleChildScrollView(
          child: BackendFlowPanel(
            isGuest: isGuest,
            documentService: documentService,
            aiService: aiService,
            conceptService: conceptService,
            excelService: excelService,
            exportService: exportService,
            noteService: noteService ?? _FakeNoteService(),
            preferenceService: preferenceService ?? _FakePreferenceService(),
            gameService: gameService ?? _FakeGameService(),
            reelsService: reelsService,
          ),
        ),
      ),
    ),
  );
}

const _testDocument = UploadedDocument(id: 7, title: 'Test dokumani');
const _testExcelDocument = UploadedDocument(
  id: 8,
  title: 'Tablo.xlsx',
  mime: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
);
const _testParts = [
  DocumentPart(
    id: 11,
    order: 1,
    text: 'Birinci parca metni',
    difficultyLabel: 'kolay',
    difficultyScore: 0.18,
    difficultyReasons: ['Kisa ve sade metin'],
  ),
  DocumentPart(
    id: 12,
    order: 2,
    text: 'Ikinci parca metni',
    difficultyLabel: 'zor',
    difficultyScore: 0.86,
    difficultyReasons: ['Terim yogunlugu yuksek'],
  ),
];

void main() {
  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
    appLanguageController.value = 'tr';
  });

  testWidgets('DocVerse login screen renders', (WidgetTester tester) async {
    await tester.pumpWidget(const MaterialApp(home: LoginScreen()));

    expect(find.text('DocVerse'), findsOneWidget);
    expect(find.text('Giriş Yap'), findsWidgets);
  });

  testWidgets('login screen stays scrollable on phone portrait and landscape', (
    WidgetTester tester,
  ) async {
    for (final size in [const Size(390, 844), const Size(844, 390)]) {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      await tester.pumpWidget(const MaterialApp(home: LoginScreen()));

      expect(find.text('DocVerse'), findsOneWidget);
      expect(find.byType(TextField), findsNWidgets(2));
      expect(find.text('Giriş Yap'), findsWidgets);
      expect(find.text('Kayıt Ol'), findsOneWidget);
      expect(find.byType(LanguagePicker), findsOneWidget);
      expect(tester.takeException(), isNull, reason: '$size overflowed');
    }

    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  });

  testWidgets('login keyboard inset keeps fields and buttons reachable', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(844, 390);
    tester.view.devicePixelRatio = 1;
    tester.view.viewInsets = const FakeViewPadding(bottom: 220);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetViewInsets);

    await tester.pumpWidget(const MaterialApp(home: LoginScreen()));
    await tester.ensureVisible(find.widgetWithText(FilledButton, 'Giriş Yap'));
    await tester.pump();

    expect(find.byType(TextField), findsNWidgets(2));
    expect(find.widgetWithText(FilledButton, 'Giriş Yap'), findsOneWidget);
    expect(find.widgetWithText(OutlinedButton, 'Kayıt Ol'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  test('language normalize supports regions and defaults to tr', () {
    expect(AppLanguageController.normalize('tr-TR'), 'tr');
    expect(AppLanguageController.normalize('en-US'), 'en');
    expect(AppLanguageController.normalize('fr'), 'fr');
    expect(AppLanguageController.normalize('zz-ZZ'), 'tr');
    expect(supportedLanguages.map((language) => language.code), contains('sv'));
    expect(
      AppLocalizer.fullUiSupportedLanguages,
      containsAll(supportedLanguages.map((language) => language.code)),
    );
  });

  test('all picker languages have basic UI dictionaries', () {
    const requiredKeys = {
      'uploadDocument',
      'guestUploadDescription',
      'language',
      'signIn',
      'register',
      'username',
      'password',
      'email',
      'confirmPassword',
      'signOut',
      'sessionExpired',
      'tryAgain',
      'loading',
      'selectFile',
      'changeFile',
      'uploadAndFetchParts',
      'refreshParts',
      'selectedPart',
      'documentRequired',
      'question',
      'questionRequired',
      'newQuestion',
      'answer',
      'evidence',
      'noEvidenceFound',
      'iDontUnderstand',
      'evidenceAnswer',
      'send',
      'terms',
      'stepByStep',
      'examples',
      'miniQuiz',
      'difficultyEasy',
      'difficultyMedium',
      'difficultyHard',
      'hardestSections',
      'whyHard',
      'difficultyReasons',
      'startWithThisPart',
      'confusionMap',
      'hardestSectionsDescription',
      'remixConsole',
      'remixDescription',
      'remixShort',
      'remixSimpler',
      'remixMoreExamples',
      'remixTable',
      'remixExam',
      'remixBuddy',
      'remixTeacher',
      'remixTechnical',
      'remixLoading',
      'remixFailed',
      'directorsCut',
      'directorsCutDescription',
      'selfCheck',
      'selfCheckDescription',
      'writeYourUnderstanding',
      'checkAnswer',
      'correctPoints',
      'wrongPoints',
      'missingPoints',
      'improvedAnswer',
      'selfCheckScore',
      'selfCheckFailed',
      'weak',
      'medium',
      'good',
      'testTime',
      'quizRoulette',
      'escapeRoom',
      'speedrun',
      'repairMistakes',
      'key',
      'hint',
      'showAnswer',
      'correct',
      'wrong',
      'start',
      'completed',
      'quickCut',
      'storyCut',
      'examCut',
      'directorsCutLoading',
      'directorsCutFailed',
      'criticalSentences',
      'quickExamples',
      'cause',
      'result',
      'lesson',
      'whatTeacherMayAsk',
      'trapPoints',
      'learningPreferences',
      'learningPreferencesDescription',
      'savePreferences',
      'preferencesSaved',
      'preferencesUnavailable',
      'personalizationDisabled',
      'personalExamples',
      'theme',
      'explanationStyle',
      'level',
      'exampleDensity',
      'themeDefault',
      'themeSport',
      'themeFood',
      'themeGaming',
      'themeTechnology',
      'themeMovieSeries',
      'themeMusic',
      'themeHistory',
      'themeScience',
      'themeHealth',
      'themeBusiness',
      'styleShort',
      'styleStepByStep',
      'styleManyExamples',
      'styleLightHumor',
      'styleSerious',
      'styleExamFocused',
      'styleConversation',
      'levelBeginner',
      'levelIntermediate',
      'levelAdvanced',
      'densityLow',
      'densityNormal',
      'densityHigh',
      'conceptFusionLab',
      'conceptFusionDescription',
      'selectFirstConcept',
      'selectSecondConcept',
      'fuseConcepts',
      'commonPoints',
      'differences',
      'togetherExample',
      'miniQuestion',
      'fusionFailed',
      'fusionTermsRequired',
      'fusionTermsMustDiffer',
      'gamification',
      'xp',
      'title',
      'achievements',
      'rewards',
      'weeklyProgress',
      'nextLevel',
      'recentActivities',
      'cheatSheetReward',
      'firstUpload',
      'firstExplain',
      'firstEvidence',
      'firstSelfCheck',
      'firstFusion',
      'quizStarter',
      'escapeSolver',
      'speedrunner',
      'conceptHunter',
      'progressFailed',
      'bossFight',
      'bossRush',
      'miniBoss',
      'startBoss',
      'answerBoss',
      'bossScore',
      'bossPassed',
      'bossFailed',
      'loot',
      'flashcard',
      'goldenSentence',
      'trapWarning',
      'bossRushCompleted',
      'bossReward',
      'locked',
      'unlocked',
      'excelModes',
      'tableSummary',
      'explainFormula',
      'askTable',
      'formula',
      'explain',
      'evidenceRows',
      'excelFailed',
      'sheet',
      'rowCount',
      'columnCount',
    };

    for (final language in supportedLanguages) {
      for (final key in requiredKeys) {
        expect(
          appMessages[key]?.containsKey(language.code),
          isTrue,
          reason: '${language.code} is missing $key',
        );
      }
    }
  });

  test(
    'file type config classifies supported blocked and parser-limited extensions',
    () {
      final pdf = fileTypeInfoForExtension('PDF');
      final exe = fileTypeInfoForExtension('exe');
      final epub = fileTypeInfoForExtension('epub');
      final png = fileTypeInfoForExtension('png');

      expect(pdf.uploadAllowed, isTrue);
      expect(pdf.parseSupported, isTrue);
      expect(pdf.category, 'PDF');
      expect(exe.uploadAllowed, isFalse);
      expect(exe.blocked, isTrue);
      expect(epub.uploadAllowed, isTrue);
      expect(epub.parseSupported, isFalse);
      expect(epub.category, 'Diğer');
      expect(png.category, 'Görsel/OCR');
      expect(uploadExtensions, contains('zip'));
      expect(blockedExtensions, contains('exe'));
    },
  );

  test('ApiClient sends Accept-Language header', () async {
    final client = _CaptureClient(
      http.Response(
        jsonEncode({'ok': true}),
        200,
        headers: {'content-type': 'application/json'},
      ),
    );
    final api = ApiClient(httpClient: client);

    await api.get(AppConstants.pingEndpoint);
    expect(client.requests.single.headers['Accept-Language'], 'tr');

    await appLanguageController.setLanguage('en');
    await api.get(AppConstants.pingEndpoint);
    expect(client.requests.last.headers['Accept-Language'], 'en');

    await appLanguageController.setLanguage('fr');
    await api.get(AppConstants.pingEndpoint);
    expect(client.requests.last.headers['Accept-Language'], 'fr');

    await appLanguageController.setLanguage('de');
    await api.get(AppConstants.pingEndpoint);
    expect(client.requests.last.headers['Accept-Language'], 'de');

    await appLanguageController.setLanguage('sv');
    await api.get(AppConstants.pingEndpoint);
    expect(client.requests.last.headers['Accept-Language'], 'sv');
  });

  test('ApiClient maps backend error_code and raw auth messages', () async {
    await appLanguageController.setLanguage('tr');
    final codedClient = _CaptureClient(
      http.Response(
        jsonEncode({'error_code': 'invalid_credentials'}),
        401,
        headers: {'content-type': 'application/json'},
      ),
    );

    await expectLater(
      () => ApiClient(httpClient: codedClient).post(AppConstants.loginEndpoint),
      throwsA(
        isA<ApiException>().having(
          (error) => error.message,
          'message',
          'Kullanıcı adı veya şifre hatalı.',
        ),
      ),
    );

    await appLanguageController.setLanguage('en');
    final rawClient = _CaptureClient(
      http.Response(
        jsonEncode({
          'detail': 'No active account found with the given credentials',
        }),
        401,
        headers: {'content-type': 'application/json'},
      ),
    );

    await expectLater(
      () => ApiClient(httpClient: rawClient).post(AppConstants.loginEndpoint),
      throwsA(
        isA<ApiException>().having(
          (error) => error.message,
          'message',
          'Username or password is incorrect.',
        ),
      ),
    );
  });

  test('ApiClient maps upload extension error codes', () async {
    final client = _CaptureClient(
      http.Response(
        jsonEncode({'error_code': 'blocked_extension'}),
        400,
        headers: {'content-type': 'application/json'},
      ),
    );

    await expectLater(
      () => ApiClient(httpClient: client).post(AppConstants.loginEndpoint),
      throwsA(
        isA<ApiException>().having(
          (error) => error.message,
          'message',
          'Bu dosya türü güvenlik nedeniyle yüklenemez.',
        ),
      ),
    );
  });

  test('ExplainResponse parses backend aliases', () {
    final response = ExplainResponse.fromDynamic({
      'oneLiner': 'Kisa ozet',
      'verySimple': 'Basit anlatim',
      'terimler': ['Terim'],
      'maddeler': ['Adim'],
      'ornekler': ['Ornek'],
      'miniQuiz': ['Soru'],
      'kanitlar': ['Kanit'],
      'concepts': [
        {'id': 'atp', 'term': 'ATP', 'definition': 'Enerji molekulu'},
      ],
      'concept_relations': [
        {'source': 'ATP', 'target': 'enerji', 'reason': 'Yakın bağlam'},
      ],
    });

    expect(response.isEmpty, isFalse);
    expect(response.oneSentence, 'Kisa ozet');
    expect(response.simpleExplanation, 'Basit anlatim');
    expect(response.terms, ['Terim']);
    expect(response.steps, ['Adim']);
    expect(response.examples, ['Ornek']);
    expect(response.quiz, ['Soru']);
    expect(response.evidence, ['Kanit']);
    expect(response.concepts.single.term, 'ATP');
    expect(response.conceptRelations.single.target, 'enerji');
  });

  test('ExplainResponse shows raw plain text as explanation', () {
    final response = ExplainResponse.fromDynamic('Sadece duz metin aciklama');

    expect(response.isEmpty, isFalse);
    expect(response.rawExplanation, 'Sadece duz metin aciklama');
  });

  test('LearningPreferences parses backend shape', () {
    final preferences = LearningPreferences.fromDynamic({
      'enabled': true,
      'theme': 'oyun',
      'explanation_style': 'bol_ornek',
      'level': 'baslangic',
      'example_density': 'cok',
    });

    expect(preferences.enabled, isTrue);
    expect(preferences.theme, 'oyun');
    expect(preferences.explanationStyle, 'bol_ornek');
    expect(preferences.level, 'baslangic');
    expect(preferences.exampleDensity, 'cok');
    expect(preferences.toJson()['explanation_style'], 'bol_ornek');
  });

  testWidgets('Guest upload area shows CTA without upload controls', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(child: BackendFlowPanel(isGuest: true)),
        ),
      ),
    );

    expect(find.text('Doküman yükle'), findsOneWidget);
    expect(
      find.text('Doküman yüklemek ve parçaları görmek için giriş yap.'),
      findsOneWidget,
    );
    expect(find.text('Giriş Yap'), findsOneWidget);
    expect(find.text('Kayıt Ol'), findsOneWidget);
    expect(find.text('Dosya seç'), findsNothing);
    expect(find.text('Yükle ve parçaları getir'), findsNothing);
    expect(find.text('Bunu Anlamadım'), findsNothing);
    expect(find.text('Kanıtlı cevap'), findsNothing);
  });

  testWidgets('Authenticated upload area shows real upload controls', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(body: SingleChildScrollView(child: BackendFlowPanel())),
      ),
    );

    expect(find.text('Dosya seç'), findsOneWidget);
    expect(find.text('Yükle ve parçaları getir'), findsOneWidget);
    expect(find.text('Bunu Anlamadım'), findsWidgets);
    expect(find.text('Kanıtlı cevap'), findsNothing);
    expect(find.text('Kanıtlı cevap sor'), findsOneWidget);
    expect(find.text('Giriş Yap'), findsNothing);
    expect(find.text('Kayıt Ol'), findsNothing);
  });

  testWidgets('tablet width main demo flow renders without overflow', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      _localizedPanelApp(
        aiService: _FakeAiService(explain: const ExplainResponse()),
        exportService: _FakeExportService(),
        reelsService: _FakeReelsService(),
      ),
    );
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(
      document: _testExcelDocument,
      parts: _testParts,
    );
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(find.text('İlerleme'), findsOneWidget);
    expect(find.text('Demo kontrolü'), findsOneWidget);
    expect(find.text('Doküman yükle'), findsOneWidget);
    expect(find.text('Parça listesi'), findsOneWidget);
    expect(find.text('Bunu Anlamadım'), findsWidgets);
    expect(find.text('Test zamanı'), findsOneWidget);
    expect(find.text('Mini Reels').first, findsOneWidget);
    expect(find.text('Çıktılar'), findsWidgets);
    expect(find.text('Excel Modları'), findsNothing);
  });

  testWidgets('tablet workspace renders sources chat and studio panels', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(_localizedPanelApp());

    expect(find.text('Kaynaklar'), findsOneWidget);
    expect(find.text('Sohbet'), findsOneWidget);
    expect(find.text('Studio'), findsOneWidget);
    expect(find.text('Doküman yükle'), findsOneWidget);
    expect(find.text('Parça listesi'), findsOneWidget);
    expect(find.byType(TextField), findsOneWidget);
    expect(find.text('Excel Modları'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('tablet portrait falls back to tabbed workspace', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(900, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(_localizedPanelApp());

    expect(find.byType(SegmentedButton<int>), findsNothing);
    expect(find.text('Sohbet'), findsOneWidget);
    expect(find.text('Kaynaklar'), findsOneWidget);
    expect(find.text('Studio'), findsOneWidget);
    expect(find.text('DocVerse’e sor...'), findsOneWidget);
    expect(find.text('Excel Modları'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('medium tablet width uses tabbed workspace', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(900, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(_localizedPanelApp());

    expect(find.byType(SegmentedButton<int>), findsNothing);
    expect(find.text('Kaynaklar'), findsOneWidget);
    expect(find.text('Sohbet'), findsOneWidget);
    expect(find.text('Studio'), findsOneWidget);
    expect(find.byType(TextField), findsOneWidget);
    expect(find.text('Excel Modları'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('phone workspace uses one scroll page without tabs', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(_localizedPanelApp());

    expect(find.byType(SegmentedButton<int>), findsNothing);
    expect(find.text('Sohbet'), findsNothing);
    expect(find.text('Kaynaklar'), findsNothing);
    expect(find.text('Studio'), findsNothing);
    expect(find.text('Önce dosya seç veya soru yaz...'), findsOneWidget);
    expect(find.text('Doküman yükle'), findsNothing);
    expect(find.text('Parça listesi'), findsNothing);
    expect(find.byTooltip('Dosya seç'), findsWidgets);
    expect(find.byType(PageView), findsNothing);
    expect(find.byType(TextField), findsOneWidget);
    expect(find.widgetWithText(ActionChip, 'Bunu Anlamadım'), findsOneWidget);
    expect(
      find.widgetWithText(ActionChip, 'Kanıtlı cevap sor'),
      findsOneWidget,
    );
    expect(find.widgetWithText(ActionChip, 'Daha basit anlat'), findsOneWidget);
    expect(find.widgetWithText(ActionChip, 'Örnek ver'), findsOneWidget);
    expect(find.widgetWithText(ActionChip, 'Quiz yap'), findsOneWidget);
    expect(find.widgetWithText(ActionChip, 'Boss başlat'), findsOneWidget);
    expect(find.widgetWithText(ActionChip, 'Mini Reels'), findsOneWidget);
    expect(find.widgetWithText(ActionChip, 'Nota ekle'), findsOneWidget);
    expect(find.text('Önce bir parça seç'), findsWidgets);
    final disabledExplain = tester.widget<ActionChip>(
      find.widgetWithText(ActionChip, 'Bunu Anlamadım'),
    );
    expect(disabledExplain.onPressed, isNull);
    expect(
      tester.getTopLeft(find.widgetWithText(ActionChip, 'Bunu Anlamadım')).dy,
      lessThan(tester.getTopLeft(find.byType(TextField).first).dy),
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'phone unified page hides upload card and uses source mini card',
    (WidgetTester tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_localizedPanelApp());
      final state = tester.state<BackendFlowPanelState>(
        find.byType(BackendFlowPanel),
      );
      state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
      await tester.pump();

      expect(find.text('Doküman yükle'), findsNothing);
      expect(find.text('Parça listesi'), findsNothing);
      expect(find.text('Kaynak hazır'), findsNothing);
      expect(find.text('2 parça'), findsWidgets);
      expect(find.widgetWithText(ActionChip, 'Parça seç'), findsOneWidget);
      final enabledExplain = tester.widget<ActionChip>(
        find.widgetWithText(ActionChip, 'Bunu Anlamadım'),
      );
      expect(enabledExplain.onPressed, isNotNull);
      expect(
        tester.getTopLeft(find.widgetWithText(ActionChip, 'Bunu Anlamadım')).dy,
        lessThan(tester.getTopLeft(find.byType(TextField).first).dy),
      );
      expect(
        tester.getTopLeft(find.text('2 parça').first).dy,
        greaterThan(tester.getTopLeft(find.byType(PageView)).dy),
      );
      expect(find.text('Excel Modları'), findsNothing);
      expect(find.text('Tablo özeti'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('phone file attach uploads and opens part picker sheet', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final documents = _FakeDocumentService();
    await tester.pumpWidget(_localizedPanelApp(documentService: documents));
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );

    expect(find.byTooltip('Dosya seç'), findsWidgets);
    await state.selectTestFileAndUpload(
      path: 'C:\\tmp\\doc.pdf',
      name: 'doc.pdf',
    );
    await tester.pumpAndSettle();

    expect(documents.uploadCount, 1);
    expect(documents.partsCount, 1);
    expect(find.text('Dosya eklendi: doc.pdf'), findsOneWidget);
    expect(find.text('Belge yüklendi. Hangi kısmı anlamadın?'), findsOneWidget);
    expect(find.text('Kaynak hazır'), findsNothing);
    expect(find.text('Hangi kısmı anlamadın?'), findsWidgets);
    expect(state.selectedPartId, isNull);

    final miniPartButton = find.widgetWithText(ActionChip, 'Parça seç').first;
    await tester.ensureVisible(miniPartButton);
    await tester.tap(miniPartButton);
    await tester.pumpAndSettle();
    expect(find.text('En zor kısımlar'), findsOneWidget);
    expect(find.text('Tüm parçalar'), findsOneWidget);
    expect(find.textContaining('Ikinci parca metni'), findsWidgets);

    await tester.tap(find.widgetWithText(FilledButton, 'Parça seç').last);
    await tester.pumpAndSettle();
    expect(state.selectedPartId, isNotNull);
    expect(find.text('Seçili parça güncellendi.'), findsOneWidget);
    expect(find.text('Excel Modları'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('phone unified page uses horizontal feature slider', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(_localizedPanelApp());
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    expect(find.byType(PageView), findsOneWidget);
    expect(
      find.byKey(const ValueKey('chat_embedded_tool_shelf')),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('phone_chat_tool_shelf')), findsOneWidget);
    expect(
      tester.getSize(find.byType(PageView)).height,
      lessThanOrEqualTo(220),
    );
    expect(
      find.byKey(
        const ValueKey(
          'phone_feature_slider:Öğrenme Araçları>Oyun Araçları>Notlar ve Çıktılar>İlerleme',
        ),
      ),
      findsOneWidget,
    );
    await tester.ensureVisible(find.byType(PageView));
    await tester.pumpAndSettle();
    expect(find.text('AI Araçları'), findsNothing);
    expect(find.text('Öğrenme Araçları'), findsWidgets);
    expect(
      tester.getTopLeft(find.byType(PageView)).dy,
      lessThan(
        tester.getTopLeft(find.widgetWithText(ActionChip, 'Parça seç')).dy,
      ),
    );

    await tester.fling(find.byType(PageView), const Offset(-600, 0), 1000);
    await tester.pumpAndSettle();
    expect(find.text('Oyun Araçları'), findsWidgets);

    expect(find.text('Excel Modları'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('phone explain action result is rendered in chat not slider', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final ai = _FakeAiService(
      explain: const ExplainResponse(
        oneSentence: 'Bu parçayı basitçe enerji akışı gibi düşünebilirsin.',
        examples: ['ATP pil gibi çalışır.'],
      ),
    );
    await tester.pumpWidget(_localizedPanelApp(aiService: ai));
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    await tester.tap(find.widgetWithText(ActionChip, 'Bunu Anlamadım'));
    await tester.pumpAndSettle();

    expect(
      find.textContaining('Bu parçayı basitçe enerji akışı'),
      findsOneWidget,
    );
    expect(find.textContaining('ATP pil gibi çalışır.'), findsOneWidget);
    expect(
      tester.getSize(find.byType(PageView)).height,
      lessThanOrEqualTo(220),
    );
    expect(find.text('Excel Modları'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('phone evidence action result renders chat evidence chips', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final ai = _FakeAiService(
      explain: const ExplainResponse(),
      answer: const EvidenceAnswer(
        answer: 'Kanıtlı cevap chat içindedir.',
        evidence: [
          EvidenceSnippet(
            text: 'ATP hücrede enerji taşır.',
            source: 'mobil_test_belgesi.txt',
            path: '1. Giriş',
          ),
        ],
      ),
    );
    await tester.pumpWidget(_localizedPanelApp(aiService: ai));
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    await tester.tap(find.widgetWithText(ActionChip, 'Kanıtlı cevap sor'));
    await tester.pumpAndSettle();

    expect(find.text('Kanıtlı cevap chat içindedir.'), findsOneWidget);
    expect(find.text('mobil_test_belgesi.txt / 1. Giriş'), findsOneWidget);
    expect(find.text('Excel Modları'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('phone landscape unified page keeps feature slider visible', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(844, 390);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(_localizedPanelApp());
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    expect(find.byType(SegmentedButton<int>), findsNothing);
    expect(find.text('Sohbet'), findsNothing);
    expect(find.text('Kaynaklar'), findsNothing);
    expect(find.text('Studio'), findsNothing);
    expect(find.text('DocVerse’e sor...'), findsOneWidget);
    expect(find.text('Doküman yükle'), findsNothing);
    expect(find.text('Parça listesi'), findsNothing);
    expect(find.text('Kaynak hazır'), findsNothing);
    expect(find.byType(PageView), findsOneWidget);
    expect(find.text('Excel Modları'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('phone selected part appears in chat context', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(_localizedPanelApp());
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    expect(find.text('Parça 1'), findsWidgets);
    expect(find.text('Excel Modları'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('phone Arabic layout keeps RTL and avoids overflow', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await appLanguageController.setLanguage('ar');

    await tester.pumpWidget(_localizedPanelApp());

    expect(find.byType(SegmentedButton<int>), findsNothing);
    expect(
      Directionality.of(tester.element(find.byType(BackendFlowPanel))),
      TextDirection.rtl,
    );
    expect(find.text('Excel Modları'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('common phone sizes keep unified chat layout overflow-free', (
    WidgetTester tester,
  ) async {
    const sizes = [
      Size(360, 800),
      Size(390, 844),
      Size(412, 915),
      Size(430, 932),
      Size(600, 960),
    ];

    for (final size in sizes) {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      await tester.pumpWidget(_localizedPanelApp());

      expect(find.byType(SegmentedButton<int>), findsNothing);
      expect(find.byType(TextField), findsOneWidget);
      expect(find.byType(PageView), findsNothing);
      expect(find.text('Excel Modları'), findsNothing);
      expect(tester.takeException(), isNull, reason: '$size overflowed');
    }

    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  });

  testWidgets('keyboard inset keeps chat input visible without 3 panels', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(1280, 560);
    tester.view.devicePixelRatio = 1;
    tester.view.viewInsets = const FakeViewPadding(bottom: 320);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetViewInsets);

    await tester.pumpWidget(_localizedPanelApp());
    await tester.ensureVisible(find.byType(TextField).first);
    await tester.tap(find.byType(TextField).first, warnIfMissed: false);
    await tester.pump();

    expect(find.byType(SegmentedButton<int>), findsNothing);
    expect(find.text('Önce dosya seç veya soru yaz...'), findsOneWidget);
    expect(find.byTooltip('Dosya seç'), findsWidgets);
    expect(find.widgetWithText(ActionChip, 'Bunu Anlamadım'), findsOneWidget);
    expect(
      tester.getTopLeft(find.widgetWithText(ActionChip, 'Bunu Anlamadım')).dy,
      lessThan(tester.getTopLeft(find.byType(TextField).first).dy),
    );
    expect(find.byTooltip('Gönder'), findsOneWidget);
    expect(find.text('Excel Modları'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('workspace quick actions disable until a part is selected', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(_localizedPanelApp());

    final disabled = tester.widget<ActionChip>(
      find.widgetWithText(ActionChip, 'Bunu Anlamadım'),
    );
    expect(disabled.onPressed, isNull);

    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    final enabled = tester.widget<ActionChip>(
      find.widgetWithText(ActionChip, 'Bunu Anlamadım'),
    );
    expect(enabled.onPressed, isNotNull);
    expect(tester.takeException(), isNull);
  });

  testWidgets('workspace chat sends user message and renders evidence chips', (
    WidgetTester tester,
  ) async {
    final ai = _FakeAiService(
      explain: const ExplainResponse(),
      answer: const EvidenceAnswer(
        answer: 'ATP enerji aktarımında kullanılır.',
        evidence: [
          EvidenceSnippet(
            text: 'ATP hücrede enerji taşır.',
            source: 'mobil_test_belgesi.txt',
            path: '1. Giriş',
          ),
        ],
      ),
    );
    await tester.pumpWidget(_localizedPanelApp(aiService: ai));

    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    await tester.enterText(find.byType(TextField).first, 'ATP nedir?');
    await tester.tap(find.byTooltip('Gönder'));
    await tester.pumpAndSettle();

    expect(find.text('ATP nedir?'), findsOneWidget);
    expect(find.text('ATP enerji aktarımında kullanılır.'), findsOneWidget);
    expect(find.text('mobil_test_belgesi.txt / 1. Giriş'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('English demo shell localizes progress upload and parts copy', (
    WidgetTester tester,
  ) async {
    await appLanguageController.setLanguage('en');
    final game = _FakeGameService()
      ..profile = const GameProfile(
        enabled: true,
        xpTotal: 0,
        level: 1,
        title: 'Yeni Kaşif',
      )
      ..weekly = const WeeklyProgress(
        enabled: true,
        summary: 'Bu hafta henüz XP hareketi yok.',
        xpThisWeek: 0,
      )
      ..rewards = const GameRewards(
        enabled: true,
        cards: [
          RewardCard(
            type: 'evidence_hunter',
            title: 'Kanıt Avcısı',
            description: '',
            unlocked: true,
          ),
          RewardCard(
            type: 'term_master',
            title: 'Terim Ustası',
            description: '',
            unlocked: true,
          ),
          RewardCard(
            type: 'boss_breaker',
            title: 'Boss Kırıcı',
            description: '',
            unlocked: true,
          ),
        ],
      );

    await tester.pumpWidget(_localizedPanelApp(gameService: game));
    await tester.pumpAndSettle();

    for (final text in [
      'Dosya bekleniyor',
      'Parça listesi',
      'Yeni Kaşif',
      'Kanıt Avcısı',
      'Terim Ustası',
      'Boss Kırıcı',
    ]) {
      expect(find.text(text), findsNothing);
    }
    expect(find.textContaining('Doküman yükleyince'), findsNothing);
    expect(find.textContaining('Bu hafta henüz'), findsNothing);

    expect(find.text('Waiting for file'), findsOneWidget);
    expect(find.text('Part list'), findsOneWidget);
    expect(find.textContaining('No parts yet'), findsOneWidget);
    expect(find.text('No XP activity this week.'), findsOneWidget);
    expect(find.text('Title: New Explorer'), findsOneWidget);
    expect(find.text('Evidence Hunter'), findsOneWidget);
    expect(find.text('Term Master'), findsOneWidget);
    expect(find.text('Boss Breaker'), findsOneWidget);
    expect(find.text('Code'), findsWidgets);
    expect(find.text('Image/OCR'), findsWidgets);
    expect(find.text('Archive'), findsWidgets);
    expect(find.text('Excel Modları'), findsNothing);
  });

  testWidgets(
    'Turkish demo shell keeps Turkish progress upload and parts copy',
    (WidgetTester tester) async {
      await appLanguageController.setLanguage('tr');
      final game = _FakeGameService()
        ..profile = const GameProfile(
          enabled: true,
          xpTotal: 0,
          level: 1,
          title: 'Yeni Kaşif',
        )
        ..weekly = const WeeklyProgress(
          enabled: true,
          summary: 'Bu hafta henüz XP hareketi yok.',
          xpThisWeek: 0,
        );

      await tester.pumpWidget(_localizedPanelApp(gameService: game));
      await tester.pumpAndSettle();

      expect(find.text('Dosya bekleniyor'), findsOneWidget);
      expect(find.text('Parça listesi'), findsOneWidget);
      expect(find.textContaining('Doküman yükleyince'), findsOneWidget);
      expect(find.text('Bu hafta henüz XP hareketi yok.'), findsOneWidget);
      expect(find.text('Ünvan: Yeni Kaşif'), findsOneWidget);
      expect(find.text('Kanıt Avcısı'), findsOneWidget);
      expect(find.text('Terim Ustası'), findsOneWidget);
      expect(find.text('Boss Kırıcı'), findsOneWidget);
      expect(find.text('Kod'), findsWidgets);
      expect(find.text('Görsel/OCR'), findsWidgets);
      expect(find.text('Arşiv'), findsWidgets);
      expect(find.text('Excel Modları'), findsNothing);
    },
  );

  testWidgets('Swedish French German and Arabic demo shell avoid TR/EN leaks', (
    WidgetTester tester,
  ) async {
    final cases = <String>['sv', 'fr', 'de', 'ar'];
    final blocked = <String>[
      'Dosya bekleniyor',
      'Parça listesi',
      'Henüz parça yok',
      'Bu hafta henüz',
      'Yeni Kaşif',
      'Kanıt Avcısı',
      'Terim Ustası',
      'Boss Kırıcı',
      'Waiting for file',
      'Part list',
      'No parts yet',
      'No XP activity this week',
      'New Explorer',
      'Evidence Hunter',
      'Term Master',
      'Boss Breaker',
    ];

    for (final code in cases) {
      await appLanguageController.setLanguage(code);
      await tester.pumpWidget(
        _localizedPanelApp(gameService: _emptyProgressGame()),
      );
      await tester.pumpAndSettle();

      for (final text in blocked) {
        expect(find.text(text), findsNothing, reason: '$code leaked $text');
      }
      expect(find.text('Excel Modları'), findsNothing);
      expect(tester.takeException(), isNull);
      if (code == 'ar') {
        expect(
          Directionality.of(tester.element(find.byType(BackendFlowPanel))),
          TextDirection.rtl,
        );
      }
    }
  });

  test('tablet demo i18n keys are populated for every supported language', () {
    const keys = [
      'progress',
      'noWeeklyXpActivity',
      'newExplorer',
      'evidenceHunter',
      'termMaster',
      'bossBreaker',
      'demoChecklist',
      'uploadDocument',
      'fileWaiting',
      'partList',
      'noPartsYet',
      'uploadDocumentToSeeParts',
      'bossFight',
      'bossRush',
      'miniReels',
      'outputs',
    ];

    for (final language in supportedLanguages) {
      final localizer = AppLocalizer(language.code);
      for (final key in keys) {
        final value = localizer.t(key).trim();
        expect(value, isNotEmpty, reason: '${language.code} $key is empty');
        expect(
          value,
          isNot(key),
          reason: '${language.code} $key fell back to key',
        );
      }
    }
  });

  testWidgets(
    'learning preferences card appears after login and saves changes',
    (WidgetTester tester) async {
      final service = _FakePreferenceService(
        fetchResult: const LearningPreferences(theme: 'default'),
      );
      await tester.pumpWidget(_localizedPanelApp(preferenceService: service));
      await tester.pumpAndSettle();

      expect(find.text('Öğrenme tercihlerim'), findsOneWidget);
      expect(find.text('Tema'), findsOneWidget);

      await tester.ensureVisible(find.text('Varsayılan').first);
      await tester.tap(find.text('Varsayılan').first);
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Oyun').last);
      await tester.tap(find.text('Oyun').last);
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Tercihleri kaydet'));
      await tester.tap(find.text('Tercihleri kaydet'));
      await tester.pumpAndSettle();

      expect(service.saveCount, 1);
      expect(service.lastSaved?.theme, 'oyun');
      expect(find.text('Tercihler kaydedildi.'), findsOneWidget);
    },
  );

  testWidgets('explain request carries current learning preferences', (
    WidgetTester tester,
  ) async {
    final ai = _FakeAiService(
      explain: const ExplainResponse(oneSentence: 'ATP enerji tasir.'),
    );
    final service = _FakePreferenceService(
      fetchResult: const LearningPreferences(
        theme: 'oyun',
        explanationStyle: 'bol_ornek',
        level: 'baslangic',
        exampleDensity: 'cok',
      ),
    );
    await tester.pumpWidget(
      _localizedPanelApp(aiService: ai, preferenceService: service),
    );
    await tester.pumpAndSettle();
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    final explainButton = find.widgetWithText(FilledButton, 'Bunu Anlamadım');
    await tester.ensureVisible(explainButton);
    await tester.tap(explainButton);
    await tester.pumpAndSettle();

    expect(ai.lastExplainPreferences?.theme, 'oyun');
    expect(ai.lastExplainPreferences?.exampleDensity, 'cok');
  });

  testWidgets('disabled preference endpoint does not break workspace', (
    WidgetTester tester,
  ) async {
    final service = _FakePreferenceService(
      fetchResult: const LearningPreferences(enabled: false),
    );
    await tester.pumpWidget(_localizedPanelApp(preferenceService: service));
    await tester.pumpAndSettle();

    expect(find.text('Kişiselleştirme şu anda kapalı.'), findsOneWidget);
    expect(find.text('Dosya seç'), findsOneWidget);
    expect(find.text('Bunu Anlamadım'), findsWidgets);
  });

  testWidgets(
    'evidence composer starts hidden and opens after explain result',
    (WidgetTester tester) async {
      final ai = _FakeAiService(
        explain: const ExplainResponse(
          oneSentence: 'ATP hucre icin enerji tasir.',
          simpleExplanation: 'Hucre ATP ile is yapar.',
        ),
      );
      await tester.pumpWidget(_localizedPanelApp(aiService: ai));

      final state = tester.state<BackendFlowPanelState>(
        find.byType(BackendFlowPanel),
      );
      state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
      await tester.pump();

      expect(find.text('Kanıtlı cevap'), findsNothing);
      expect(find.text('Kanıtlı cevap sor'), findsWidgets);
      expect(find.text('Sorunu yaz'), findsNothing);

      final explainButton = find.widgetWithText(FilledButton, 'Bunu Anlamadım');
      await tester.ensureVisible(explainButton);
      await tester.pumpAndSettle();
      await tester.tap(explainButton);
      await tester.pumpAndSettle();

      expect(find.text('Sorunu kanıtlarla derinleştir'), findsOneWidget);
      expect(find.text('Kanıtlı cevap sor'), findsWidgets);
      expect(find.text('Sorunu yaz'), findsNothing);

      final evidenceButton = find.widgetWithText(
        OutlinedButton,
        'Kanıtlı cevap sor',
      );
      await tester.ensureVisible(evidenceButton);
      await tester.pumpAndSettle();
      await tester.tap(evidenceButton);
      await tester.pumpAndSettle();

      expect(find.text('Sorunu yaz'), findsOneWidget);
      expect(find.text('Gönder'), findsOneWidget);
    },
  );

  testWidgets('self-check is hidden before explain result', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(_localizedPanelApp());
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    expect(find.text('Kendi cümlenle anlat'), findsNothing);
  });

  testWidgets(
    'self-check appears after explain and enables button with input',
    (WidgetTester tester) async {
      final ai = _FakeAiService(
        explain: const ExplainResponse(oneSentence: 'JWT kimlik tasir.'),
      );
      await tester.pumpWidget(_localizedPanelApp(aiService: ai));
      final state = tester.state<BackendFlowPanelState>(
        find.byType(BackendFlowPanel),
      );
      state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
      await tester.pump();

      await state.explainSelectedPart();
      await tester.pumpAndSettle();

      expect(find.text('Kendi cümlenle anlat'), findsOneWidget);
      var checkButton = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Kontrol et'),
      );
      expect(checkButton.onPressed, isNull);

      await tester.enterText(find.byType(TextField).last, 'JWT kimliği taşır.');
      await tester.pumpAndSettle();
      checkButton = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Kontrol et'),
      );
      expect(checkButton.onPressed, isNotNull);
    },
  );

  testWidgets('self-check result blocks appear and clear on part change', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final ai = _FakeAiService(
      explain: const ExplainResponse(oneSentence: 'JWT kimlik tasir.'),
    );
    await tester.pumpWidget(_localizedPanelApp(aiService: ai));
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    final explainButton = find.widgetWithText(FilledButton, 'Bunu Anlamadım');
    await tester.ensureVisible(explainButton);
    await tester.tap(explainButton);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'JWT kimliği taşır.');
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Kontrol et'));
    await tester.pumpAndSettle();

    expect(find.textContaining('74/100'), findsOneWidget);
    expect(find.text('Doğru kısımlar'), findsOneWidget);
    expect(find.text('Düzeltilmesi gerekenler'), findsOneWidget);
    expect(find.text('Eksik kalanlar'), findsOneWidget);
    expect(find.text('Geliştirilmiş cevap'), findsOneWidget);
    expect(
      find.textContaining('JWT access token kullanicinin kimligini tasir.'),
      findsOneWidget,
    );

    await tester.ensureVisible(find.textContaining('Ikinci parca metni'));
    await tester.tap(find.textContaining('Ikinci parca metni'));
    await tester.pumpAndSettle();

    expect(find.text('Kendi cümlenle anlat'), findsNothing);
    expect(find.textContaining('74/100'), findsNothing);
  });

  testWidgets('logout clears self-check state', (WidgetTester tester) async {
    final ai = _FakeAiService(
      explain: const ExplainResponse(oneSentence: 'JWT kimlik tasir.'),
    );
    await tester.pumpWidget(_localizedPanelApp(aiService: ai));
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    await state.explainSelectedPart();
    await tester.pumpAndSettle();
    state.setTestSelfCheckAnswer('JWT kimliği taşır.');
    await state.requestSelfCheck();
    await tester.pumpAndSettle();
    expect(find.textContaining('74/100'), findsOneWidget);

    state.clearSessionState();
    await tester.pumpAndSettle();
    expect(find.text('Kendi cümlenle anlat'), findsNothing);
    expect(find.textContaining('74/100'), findsNothing);
  });

  testWidgets('test time card appears in workspace', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(_localizedPanelApp());
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    expect(find.text('Test zamanı'), findsOneWidget);
    expect(find.text('Quiz Roulette'), findsOneWidget);
    expect(find.text('Escape Room'), findsOneWidget);
    expect(find.text('Speedrun'), findsOneWidget);
  });

  testWidgets(
    'progress card shows XP level achievements and logout clears it',
    (WidgetTester tester) async {
      await tester.pumpWidget(_localizedPanelApp());
      await tester.pumpAndSettle();

      expect(find.text('İlerleme'), findsOneWidget);
      expect(find.text('XP: 240'), findsOneWidget);
      expect(find.text('Seviye 3'), findsOneWidget);
      expect(find.text('İlk yükleme'), findsOneWidget);

      final state = tester.state<BackendFlowPanelState>(
        find.byType(BackendFlowPanel),
      );
      state.clearSessionState();
      await tester.pumpAndSettle();

      expect(find.text('XP: 240'), findsNothing);
    },
  );

  testWidgets('boss fight payload loot and rush list render', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(_localizedPanelApp());
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.text('Boss Fight'));
    await tester.tap(find.text('Boss Fight'));
    await tester.pumpAndSettle();
    expect(find.text('Mini Boss'), findsWidgets);
    expect(find.textContaining('Ana fikir nedir?'), findsOneWidget);

    await tester.ensureVisible(find.text('Cevapla'));
    await tester.tap(find.text('Cevapla'));
    await tester.pumpAndSettle();
    expect(find.text('Loot'), findsOneWidget);
    expect(find.textContaining('Altın cümle'), findsWidgets);

    await tester.ensureVisible(find.text('Boss Rush'));
    await tester.tap(find.text('Boss Rush'));
    await tester.pumpAndSettle();
    expect(find.text('Boss Rush'), findsWidgets);
  });

  testWidgets('quiz mode opens and shows answer feedback', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final ai = _FakeAiService(explain: const ExplainResponse());
    await tester.pumpWidget(_localizedPanelApp(aiService: ai));
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    await tester.ensureVisible(find.text('Quiz Roulette'));
    await tester.tap(find.text('Quiz Roulette'));
    await tester.pumpAndSettle();
    expect(find.text('ATP ne taşır?'), findsOneWidget);
    await tester.tap(find.text('Enerji'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Doğru: Enerji'), findsOneWidget);
    expect(find.text('ATP enerji taşır.'), findsOneWidget);
  });

  testWidgets('escape room key cards appear', (WidgetTester tester) async {
    final ai = _FakeAiService(explain: const ExplainResponse());
    await tester.pumpWidget(_localizedPanelApp(aiService: ai));
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    await tester.ensureVisible(find.text('Escape Room'));
    await tester.tap(find.text('Escape Room'));
    await tester.pumpAndSettle();
    expect(find.text('Anahtar 1: ATP'), findsOneWidget);
    expect(find.text('Anahtar 2: Fosfat'), findsOneWidget);
    expect(find.text('Anahtar 3: Taşıma'), findsOneWidget);
  });

  testWidgets('speedrun blocks appear and clear on part change', (
    WidgetTester tester,
  ) async {
    final ai = _FakeAiService(explain: const ExplainResponse());
    await tester.pumpWidget(_localizedPanelApp(aiService: ai));
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    await tester.ensureVisible(find.text('Speedrun'));
    await tester.tap(find.text('Speedrun'));
    await tester.pumpAndSettle();
    expect(find.text('Kritik cümleler'), findsOneWidget);
    expect(find.text('Yanlış tamiri'), findsOneWidget);
    expect(find.text('ATP enerji taşır.'), findsOneWidget);

    await tester.ensureVisible(find.textContaining('Ikinci parca metni'));
    await tester.tap(find.textContaining('Ikinci parca metni'));
    await tester.pumpAndSettle();

    expect(find.text('Test zamanı'), findsOneWidget);
    expect(find.text('Kritik cümleler'), findsNothing);
    expect(find.text('ATP enerji taşır.'), findsNothing);
  });

  testWidgets('term chips open concept detail and concept map appears', (
    WidgetTester tester,
  ) async {
    final ai = _FakeAiService(
      explain: const ExplainResponse(
        oneSentence: 'ATP enerji tasir.',
        concepts: [
          ConceptItem(
            id: 'atp',
            term: 'ATP',
            definition: 'Hucrede enerji tasiyan molekul.',
            example: 'Enerji bari gibi dusun.',
          ),
          ConceptItem(id: 'enerji', term: 'enerji'),
        ],
        conceptRelations: [
          ConceptRelation(
            source: 'ATP',
            target: 'enerji',
            reason: 'ATP enerji ile birlikte aciklaniyor.',
          ),
        ],
      ),
    );
    await tester.pumpWidget(_localizedPanelApp(aiService: ai));
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    final explainButton = find.widgetWithText(FilledButton, 'Bunu Anlamadım');
    await tester.ensureVisible(explainButton);
    await tester.tap(explainButton);
    await tester.pumpAndSettle();

    expect(find.text('Kavram haritası'), findsOneWidget);
    await tester.ensureVisible(find.widgetWithText(ActionChip, 'ATP'));
    await tester.tap(find.widgetWithText(ActionChip, 'ATP'));
    await tester.pumpAndSettle();

    expect(
      find.textContaining('Hucrede enerji tasiyan molekul.'),
      findsOneWidget,
    );
    expect(find.text('ATP → enerji'), findsOneWidget);
  });

  testWidgets('concept mentions can select another part and clear state', (
    WidgetTester tester,
  ) async {
    final ai = _FakeAiService(
      explain: const ExplainResponse(
        oneSentence: 'ATP enerji tasir.',
        concepts: [ConceptItem(id: 'atp', term: 'ATP')],
      ),
    );
    final concepts = _FakeConceptService(
      searchResponse: const ConceptGraphResponse(
        concept: ConceptItem(id: 'atp', term: 'ATP'),
        mentions: [
          ConceptMention(
            partId: 12,
            title: 'Glikoz ve Solunum',
            path: '2. Glikoz',
            snippet: 'ATP burada tekrar gecer.',
          ),
        ],
      ),
    );
    await tester.pumpWidget(
      _localizedPanelApp(aiService: ai, conceptService: concepts),
    );
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    final explainButton = find.widgetWithText(FilledButton, 'Bunu Anlamadım');
    await tester.ensureVisible(explainButton);
    await tester.tap(explainButton);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.widgetWithText(ActionChip, 'ATP'));
    await tester.tap(find.widgetWithText(ActionChip, 'ATP'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Bu kavram nerelerde geçiyor?'));
    await tester.tap(find.text('Bu kavram nerelerde geçiyor?'));
    await tester.pumpAndSettle();

    expect(find.text('ATP burada tekrar gecer.'), findsOneWidget);
    await tester.tap(find.text('Bu parçaya git'));
    await tester.pumpAndSettle();

    expect(state.selectedPartId, 12);
    expect(find.text('Kavram haritası'), findsNothing);
    expect(find.text('Director’s Cut'), findsNothing);
  });

  testWidgets('fusion lab hidden without concepts', (
    WidgetTester tester,
  ) async {
    final ai = _FakeAiService(
      explain: const ExplainResponse(oneSentence: 'ATP enerji tasir.'),
    );
    await tester.pumpWidget(_localizedPanelApp(aiService: ai));
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();
    await state.explainSelectedPart();
    await tester.pumpAndSettle();
    expect(find.text('Concept Fusion Lab'), findsNothing);
  });

  testWidgets('fusion button activates after two different concepts', (
    WidgetTester tester,
  ) async {
    final ai = _FakeAiService(
      explain: const ExplainResponse(
        oneSentence: 'ATP enerji tasir.',
        concepts: [
          ConceptItem(id: 'atp', term: 'ATP'),
          ConceptItem(id: 'glikoz', term: 'Glikoz'),
        ],
      ),
    );
    await tester.pumpWidget(_localizedPanelApp(aiService: ai));
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();
    await state.explainSelectedPart();
    await tester.pumpAndSettle();
    expect(find.text('Concept Fusion Lab'), findsOneWidget);

    state.selectFusionTermA('ATP');
    state.selectFusionTermB('Glikoz');
    await tester.pumpAndSettle();

    final button = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Kavramları birleştir'),
    );
    expect(button.onPressed, isNotNull);
  });

  testWidgets('fusion shows warning for same concept', (
    WidgetTester tester,
  ) async {
    final ai = _FakeAiService(
      explain: const ExplainResponse(
        oneSentence: 'ATP enerji tasir.',
        concepts: [
          ConceptItem(id: 'atp', term: 'ATP'),
          ConceptItem(id: 'glikoz', term: 'Glikoz'),
        ],
      ),
    );
    await tester.pumpWidget(_localizedPanelApp(aiService: ai));
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();
    await state.explainSelectedPart();
    await tester.pumpAndSettle();

    state.selectFusionTermA('ATP');
    state.selectFusionTermB('ATP');
    await tester.pumpAndSettle();

    expect(find.text('İki farklı kavram seçmelisin.'), findsOneWidget);
  });

  testWidgets('successful fusion card shows sections and evidence', (
    WidgetTester tester,
  ) async {
    final ai = _FakeAiService(
      explain: const ExplainResponse(
        oneSentence: 'ATP enerji tasir.',
        concepts: [
          ConceptItem(id: 'atp', term: 'ATP'),
          ConceptItem(id: 'glikoz', term: 'Glikoz'),
        ],
      ),
    );
    final concepts = _FakeConceptService(
      searchResponse: const ConceptGraphResponse(),
      fusionResponse: const FusionCard(
        termA: 'ATP',
        termB: 'Glikoz',
        title: 'ATP + Glikoz Fusion Card',
        commonPoints: ['İkisi de enerji ile ilgilidir.'],
        differences: [
          FusionDifference(
            termA: 'ATP enerji taşıyıcısıdır.',
            termB: 'Glikoz enerji kaynağıdır.',
          ),
        ],
        togetherExample: 'Hücre glikozdan ATP üretir.',
        miniQuestion: FusionMiniQuestion(
          question: 'Temel fark nedir?',
          answer: 'Glikoz kaynak, ATP taşıyıcıdır.',
        ),
        evidenceSnippets: [
          FusionEvidenceSnippet(
            partId: 11,
            path: '1',
            snippet: 'Glikoz ATP üretiminde kullanılır.',
          ),
        ],
      ),
    );
    await tester.pumpWidget(
      _localizedPanelApp(aiService: ai, conceptService: concepts),
    );
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();
    await state.explainSelectedPart();
    await tester.pumpAndSettle();
    state.selectFusionTermA('ATP');
    state.selectFusionTermB('Glikoz');
    await tester.pumpAndSettle();
    await state.requestConceptFusion();
    await tester.pumpAndSettle();

    expect(find.text('Ortak yönler'), findsOneWidget);
    expect(find.text('Farklar'), findsOneWidget);
    expect(find.text('Hücre glikozdan ATP üretir.'), findsOneWidget);
    expect(find.textContaining('Temel fark nedir?'), findsOneWidget);
    expect(find.text('Glikoz ATP üretiminde kullanılır.'), findsOneWidget);
  });

  testWidgets('changing part clears fusion state', (WidgetTester tester) async {
    final ai = _FakeAiService(
      explain: const ExplainResponse(
        oneSentence: 'ATP enerji tasir.',
        concepts: [
          ConceptItem(id: 'atp', term: 'ATP'),
          ConceptItem(id: 'glikoz', term: 'Glikoz'),
        ],
      ),
    );
    final concepts = _FakeConceptService(
      searchResponse: const ConceptGraphResponse(),
      fusionResponse: const FusionCard(
        termA: 'ATP',
        termB: 'Glikoz',
        commonPoints: ['İkisi de enerji ile ilgilidir.'],
      ),
    );
    await tester.pumpWidget(
      _localizedPanelApp(aiService: ai, conceptService: concepts),
    );
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();
    await state.explainSelectedPart();
    await tester.pumpAndSettle();
    state.selectFusionTermA('ATP');
    state.selectFusionTermB('Glikoz');
    await state.requestConceptFusion();
    await tester.pumpAndSettle();
    expect(find.text('İkisi de enerji ile ilgilidir.'), findsOneWidget);

    await tester.ensureVisible(find.textContaining('Ikinci parca metni'));
    await tester.tap(find.textContaining('Ikinci parca metni'));
    await tester.pumpAndSettle();

    expect(find.text('İkisi de enerji ile ilgilidir.'), findsNothing);
  });

  test('fusion i18n keys work in tr en and sv fallback', () {
    expect(
      AppLocalizer('tr').t('fusionTermsRequired'),
      'İki kavram seçmelisin.',
    );
    expect(AppLocalizer('en').t('fuseConcepts'), 'Fuse concepts');
    expect(AppLocalizer('sv').t('commonPoints'), 'Common points');
  });

  testWidgets('remix console is hidden before explain result', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(_localizedPanelApp());
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    expect(find.text('Remix / Stil Konsolu'), findsNothing);
  });

  testWidgets('directors cut is hidden before explain result', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(_localizedPanelApp());
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    expect(find.text('Director’s Cut'), findsNothing);
  });

  testWidgets('directors cut buttons appear after explain result', (
    WidgetTester tester,
  ) async {
    final ai = _FakeAiService(
      explain: const ExplainResponse(oneSentence: 'ATP enerji tasir.'),
    );
    await tester.pumpWidget(_localizedPanelApp(aiService: ai));
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    final explainButton = find.widgetWithText(FilledButton, 'Bunu Anlamadım');
    await tester.ensureVisible(explainButton);
    await tester.pumpAndSettle();
    await tester.tap(explainButton);
    await tester.pumpAndSettle();

    expect(find.text('Director’s Cut'), findsOneWidget);
    expect(find.text('Hızlı Cut'), findsOneWidget);
    expect(find.text('Story Cut'), findsOneWidget);
    expect(find.text('Exam Cut'), findsOneWidget);
    expect(find.text('Remix / Stil Konsolu'), findsOneWidget);
    expect(find.text('Kanıtlı cevap sor'), findsWidgets);
  });

  testWidgets('tapping quick cut starts loading and shows result', (
    WidgetTester tester,
  ) async {
    final ai = _FakeAiService(
      explain: const ExplainResponse(oneSentence: 'ATP enerji tasir.'),
      directorsCutDelay: const Duration(milliseconds: 40),
    );
    await tester.pumpWidget(_localizedPanelApp(aiService: ai));
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    final explainButton = find.widgetWithText(FilledButton, 'Bunu Anlamadım');
    await tester.ensureVisible(explainButton);
    await tester.pumpAndSettle();
    await tester.tap(explainButton);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Hızlı Cut'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Hızlı Cut'));
    await tester.pump();

    expect(find.text('Kurgu hazırlanıyor...'), findsWidgets);

    await tester.pumpAndSettle();
    expect(find.text('ATP enerji taşır.'), findsOneWidget);
    expect(find.text('ATP hücre enerjisinde kullanılır.'), findsOneWidget);
  });

  testWidgets('exam cut result shows quiz', (WidgetTester tester) async {
    final ai = _FakeAiService(
      explain: const ExplainResponse(oneSentence: 'ATP enerji tasir.'),
      directorsCut: const DirectorsCutResponse(
        cutType: 'exam',
        title: 'Exam Cut',
        summary: 'Sınavda ATP sorulabilir.',
        sections: [
          DirectorsCutSection(
            title: 'Hoca ne sorar?',
            items: ['ATP ne işe yarar?'],
          ),
        ],
        quiz: [
          DirectorsCutQuizItem(
            question: 'ATP nedir?',
            answer: 'Enerji taşıyan moleküldür.',
          ),
        ],
      ),
    );
    await tester.pumpWidget(_localizedPanelApp(aiService: ai));
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    final explainButton = find.widgetWithText(FilledButton, 'Bunu Anlamadım');
    await tester.ensureVisible(explainButton);
    await tester.pumpAndSettle();
    await tester.tap(explainButton);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Exam Cut'));
    await tester.tap(find.text('Exam Cut'));
    await tester.pumpAndSettle();

    expect(find.text('ATP nedir?'), findsOneWidget);
    expect(find.text('Enerji taşıyan moleküldür.'), findsOneWidget);
  });

  testWidgets('changing part clears directors cut state', (
    WidgetTester tester,
  ) async {
    final ai = _FakeAiService(
      explain: const ExplainResponse(oneSentence: 'ATP enerji tasir.'),
    );
    await tester.pumpWidget(_localizedPanelApp(aiService: ai));
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    final explainButton = find.widgetWithText(FilledButton, 'Bunu Anlamadım');
    await tester.ensureVisible(explainButton);
    await tester.pumpAndSettle();
    await tester.tap(explainButton);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Hızlı Cut'));
    await tester.tap(find.text('Hızlı Cut'));
    await tester.pumpAndSettle();
    expect(find.text('ATP enerji taşır.'), findsOneWidget);

    await tester.ensureVisible(find.textContaining('Ikinci parca metni'));
    await tester.tap(find.textContaining('Ikinci parca metni'));
    await tester.pumpAndSettle();

    expect(find.text('Director’s Cut'), findsNothing);
    expect(find.text('ATP enerji taşır.'), findsNothing);
  });

  testWidgets('remix buttons appear after explain result', (
    WidgetTester tester,
  ) async {
    final ai = _FakeAiService(
      explain: const ExplainResponse(oneSentence: 'ATP enerji tasir.'),
    );
    await tester.pumpWidget(_localizedPanelApp(aiService: ai));
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    final explainButton = find.widgetWithText(FilledButton, 'Bunu Anlamadım');
    await tester.ensureVisible(explainButton);
    await tester.pumpAndSettle();
    await tester.tap(explainButton);
    await tester.pumpAndSettle();

    expect(find.text('Remix / Stil Konsolu'), findsOneWidget);
    expect(find.text('Kısa kes'), findsOneWidget);
    expect(find.text('Teknik dil'), findsOneWidget);
    expect(find.text('Kanıtlı cevap sor'), findsWidgets);
  });

  testWidgets('tapping short remix starts loading and shows result', (
    WidgetTester tester,
  ) async {
    final ai = _FakeAiService(
      explain: const ExplainResponse(oneSentence: 'ATP enerji tasir.'),
      remixDelay: const Duration(milliseconds: 40),
    );
    await tester.pumpWidget(_localizedPanelApp(aiService: ai));
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();
    final explainButton = find.widgetWithText(FilledButton, 'Bunu Anlamadım');
    await tester.ensureVisible(explainButton);
    await tester.pumpAndSettle();
    await tester.tap(explainButton);
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.text('Kısa kes'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Kısa kes'));
    await tester.pump();
    expect(find.text('Açıklama yeniden düzenleniyor...'), findsWidgets);

    await tester.pumpAndSettle();
    expect(find.text('ATP enerji taşır.'), findsOneWidget);
    expect(find.text('Hücre iş yaparken ATP kullanır.'), findsOneWidget);
  });

  testWidgets('changing part clears remix state', (WidgetTester tester) async {
    final ai = _FakeAiService(
      explain: const ExplainResponse(oneSentence: 'ATP enerji tasir.'),
    );
    await tester.pumpWidget(_localizedPanelApp(aiService: ai));
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();
    final explainButton = find.widgetWithText(FilledButton, 'Bunu Anlamadım');
    await tester.ensureVisible(explainButton);
    await tester.pumpAndSettle();
    await tester.tap(explainButton);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Kısa kes'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Kısa kes'));
    await tester.pumpAndSettle();
    expect(find.text('ATP enerji taşır.'), findsOneWidget);

    await tester.ensureVisible(find.textContaining('Ikinci parca metni'));
    await tester.tap(find.textContaining('Ikinci parca metni'));
    await tester.pumpAndSettle();

    expect(find.text('Remix / Stil Konsolu'), findsNothing);
    expect(find.text('ATP enerji taşır.'), findsNothing);
  });

  testWidgets(
    'changing part closes evidence composer and clears answer state',
    (WidgetTester tester) async {
      final ai = _FakeAiService(
        explain: const ExplainResponse(oneSentence: 'ATP enerji tasir.'),
        answer: const EvidenceAnswer(answer: 'Kanıtlı cevap metni.'),
      );
      await tester.pumpWidget(_localizedPanelApp(aiService: ai));

      final state = tester.state<BackendFlowPanelState>(
        find.byType(BackendFlowPanel),
      );
      state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
      await tester.pump();

      final explainButton = find.widgetWithText(FilledButton, 'Bunu Anlamadım');
      await tester.ensureVisible(explainButton);
      await tester.pumpAndSettle();
      await tester.tap(explainButton);
      await tester.pumpAndSettle();
      final evidenceButton = find.widgetWithText(
        OutlinedButton,
        'Kanıtlı cevap sor',
      );
      await tester.ensureVisible(evidenceButton);
      await tester.pumpAndSettle();
      await tester.tap(evidenceButton);
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).last, 'ATP nedir?');
      await tester.pump();
      await tester.ensureVisible(find.text('Gönder'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Gönder'));
      await tester.pumpAndSettle();

      expect(find.text('Kanıtlı cevap metni.'), findsOneWidget);

      await tester.ensureVisible(find.textContaining('Ikinci parca metni'));
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('Ikinci parca metni'));
      await tester.pumpAndSettle();

      expect(find.text('Sorunu yaz'), findsNothing);
      expect(find.text('Kanıtlı cevap metni.'), findsNothing);
      expect(
        find.widgetWithText(OutlinedButton, 'Kanıtlı cevap sor'),
        findsNothing,
      );
    },
  );

  testWidgets('difficulty badges and hardest sections are visible', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(_localizedPanelApp());

    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    expect(find.text('Kolay'), findsWidgets);
    expect(find.text('Zor'), findsWidgets);
    expect(find.text('En zor bölümler'), findsOneWidget);
    expect(
      find.text('Bu bölümler daha yoğun terim veya uzun açıklama içerebilir.'),
      findsOneWidget,
    );
    expect(find.text('Bu bölümden başla'), findsWidgets);
  });

  testWidgets('excel doc does not show Excel Modlari card in demo', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      _localizedPanelApp(excelService: _FakeExcelService()),
    );
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(
      document: _testExcelDocument,
      parts: _testParts,
    );
    await tester.pump();

    expect(find.text('Excel Modları'), findsNothing);
    expect(find.text('Tablo özeti'), findsNothing);
    expect(find.text('Çıktılar'), findsWidgets);
  });

  testWidgets('normal txt doc hides Excel Modlari card', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      _localizedPanelApp(excelService: _FakeExcelService()),
    );
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    expect(find.text('Excel Modları'), findsNothing);
  });

  testWidgets('hardest sections sorts top parts by difficulty score', (
    WidgetTester tester,
  ) async {
    final parts = [
      const DocumentPart(
        id: 21,
        order: 1,
        text: 'Orta parca',
        difficultyLabel: 'orta',
        difficultyScore: 0.50,
      ),
      const DocumentPart(
        id: 22,
        order: 2,
        text: 'En zor parca',
        difficultyLabel: 'zor',
        difficultyScore: 0.91,
      ),
      const DocumentPart(
        id: 23,
        order: 3,
        text: 'Kolay parca',
        difficultyLabel: 'kolay',
        difficultyScore: 0.10,
      ),
      const DocumentPart(
        id: 24,
        order: 4,
        text: 'Ikinci zor parca',
        difficultyLabel: 'zor',
        difficultyScore: 0.81,
      ),
    ];
    await tester.pumpWidget(_localizedPanelApp());
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: parts);
    await tester.pump();

    await tester.ensureVisible(find.text('Bu bölümden başla').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Bu bölümden başla').first);
    await tester.pumpAndSettle();

    expect(state.selectedPartId, 22);
  });

  testWidgets('hardest section tap selects part and keeps explain enabled', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(_localizedPanelApp());

    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    await tester.ensureVisible(find.text('Bu bölümden başla').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Bu bölümden başla').first);
    await tester.pumpAndSettle();

    expect(state.selectedPartId, 12);
    final explainButton = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Bunu Anlamadım'),
    );
    expect(explainButton.onPressed, isNotNull);
  });

  testWidgets('reels card is visible and show answer works', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      _localizedPanelApp(reelsService: _FakeReelsService()),
    );
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    final reelsButton = find.widgetWithText(FilledButton, 'Mini Reels');
    await tester.ensureVisible(reelsButton);
    await tester.tap(reelsButton);
    await tester.pumpAndSettle();

    expect(find.text('ATP mini karti'), findsOneWidget);
    expect(find.text('Enerji taşır.'), findsNothing);
    await tester.ensureVisible(find.text('Cevabı göster'));
    await tester.tap(find.text('Cevabı göster'));
    await tester.pumpAndSettle();
    expect(find.text('Enerji taşır.'), findsOneWidget);
  });

  testWidgets('reels state clears when selected part changes', (
    WidgetTester tester,
  ) async {
    final reels = _FakeReelsService();
    await tester.pumpWidget(_localizedPanelApp(reelsService: reels));
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    final reelsButton = find.widgetWithText(FilledButton, 'Mini Reels');
    await tester.ensureVisible(reelsButton);
    await tester.tap(reelsButton);
    await tester.pumpAndSettle();
    expect(find.text('ATP mini karti'), findsOneWidget);

    await tester.ensureVisible(find.text('Parça 2').first);
    await tester.tap(find.text('Parça 2').first);
    await tester.pumpAndSettle();
    expect(find.text('ATP mini karti'), findsNothing);
  });

  testWidgets('outputs card renders cheatsheet presentation and readiness', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      _localizedPanelApp(exportService: _FakeExportService()),
    );
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    expect(find.text('Çıktılar'), findsWidgets);
    await tester.ensureVisible(find.text('Cheat Sheet'));
    await tester.tap(find.text('Cheat Sheet'));
    await tester.pumpAndSettle();
    expect(find.text('ATP Cheat Sheet'), findsOneWidget);
    expect(find.text('ATP enerji taşır.'), findsOneWidget);

    await tester.tap(find.text('Sunum planı'));
    await tester.pumpAndSettle();
    expect(find.text('Slayt 1'), findsOneWidget);

    await tester.tap(find.text('Export hazırlık durumu').last);
    await tester.pumpAndSettle();
    expect(find.text('Export hazırlık durumu: 82%'), findsOneWidget);
  });

  testWidgets('premium indicators are visible after explain', (
    WidgetTester tester,
  ) async {
    final ai = _FakeAiService(
      explain: const ExplainResponse(oneSentence: 'ATP enerji taşır.'),
    );
    await tester.pumpWidget(
      _localizedPanelApp(aiService: ai, exportService: _FakeExportService()),
    );
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    final explainButton = find.widgetWithText(FilledButton, 'Bunu Anlamadım');
    await tester.ensureVisible(explainButton);
    await tester.tap(explainButton);
    await tester.pumpAndSettle();

    expect(find.text('Netlik 80%'), findsOneWidget);
    expect(find.text('Örnek 70%'), findsOneWidget);
    expect(find.text('Test hazırlığı 60%'), findsOneWidget);
  });

  testWidgets('smart note form opens and saves with note service', (
    WidgetTester tester,
  ) async {
    final notes = _FakeNoteService();
    await tester.pumpWidget(_localizedPanelApp(noteService: notes));
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await state.loadPartNotes();
    await tester.pumpAndSettle();

    expect(find.text('Not ekle'), findsOneWidget);
    await tester.ensureVisible(find.text('Not ekle').first);
    await tester.tap(find.text('Not ekle').first);
    await tester.pumpAndSettle();
    expect(find.text('Not başlığı'), findsOneWidget);

    await tester.enterText(
      find.widgetWithText(TextField, 'Not başlığı'),
      'ATP',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Not metni'),
      'Enerji notu',
    );
    await tester.ensureVisible(find.text('Notu kaydet').first);
    await tester.tap(find.text('Notu kaydet').first);
    await tester.pumpAndSettle();

    expect(notes.lastCreated?.partId, 11);
    expect(notes.lastCreated?.title, 'ATP');
    expect(find.text('Enerji notu'), findsOneWidget);
  });

  testWidgets('portal link changes selected part', (WidgetTester tester) async {
    final notes = _FakeNoteService(
      partNotes: const [
        SmartNote(
          id: 7,
          partId: 11,
          title: 'ATP',
          body: 'Enerji',
          conceptTerm: 'ATP',
        ),
      ],
      portalLinks: const [
        PortalLink(
          targetPartId: 12,
          title: 'Parça 2',
          path: '2',
          snippet: 'ATP burada da geçer.',
          reason: 'Aynı kavram',
        ),
      ],
    );
    await tester.pumpWidget(_localizedPanelApp(noteService: notes));
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await state.loadPartNotes();
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.text('Portal bağlantıları').first);
    await tester.tap(find.text('Portal bağlantıları').first);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Bu parçaya git').first);
    await tester.tap(find.text('Bu parçaya git').first);
    await tester.pumpAndSettle();

    expect(state.selectedPartId, 12);
  });

  testWidgets('logout state clears smart note UI', (WidgetTester tester) async {
    final notes = _FakeNoteService();
    await tester.pumpWidget(_localizedPanelApp(noteService: notes));
    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pumpAndSettle();
    expect(find.text('Not ekle'), findsOneWidget);

    state.clearSessionState();
    await tester.pumpAndSettle();

    expect(find.text('Not ekle'), findsNothing);
  });

  testWidgets('empty explain result does not show evidence CTA', (
    WidgetTester tester,
  ) async {
    final ai = _FakeAiService(explain: const ExplainResponse());
    await tester.pumpWidget(_localizedPanelApp(aiService: ai));

    final state = tester.state<BackendFlowPanelState>(
      find.byType(BackendFlowPanel),
    );
    state.setTestDocumentAndParts(document: _testDocument, parts: _testParts);
    await tester.pump();

    final explainButton = find.widgetWithText(FilledButton, 'Bunu Anlamadım');
    await tester.ensureVisible(explainButton);
    await tester.pumpAndSettle();
    await tester.tap(explainButton);
    await tester.pumpAndSettle();

    expect(find.text('Kanıtlı cevap sor'), findsOneWidget);
    expect(find.text('Sorunu yaz'), findsNothing);
  });

  testWidgets('language change updates visible guest copy without restart', (
    WidgetTester tester,
  ) async {
    await appLanguageController.setLanguage('en');
    await tester.pumpWidget(
      AppLanguageScope(
        controller: appLanguageController,
        child: const MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(child: BackendFlowPanel(isGuest: true)),
          ),
        ),
      ),
    );

    expect(find.text('Upload document'), findsOneWidget);
    expect(find.text('Sign in'), findsOneWidget);
    expect(find.text('Register'), findsOneWidget);

    await appLanguageController.setLanguage('tr');
    await tester.pump();

    expect(find.text('Doküman yükle'), findsOneWidget);
    expect(find.text('Giriş Yap'), findsOneWidget);
    expect(find.text('Kayıt Ol'), findsOneWidget);
  });

  testWidgets('English to French updates guest UI from dropdown', (
    WidgetTester tester,
  ) async {
    await appLanguageController.setLanguage('en');
    await tester.pumpWidget(_localizedGuestApp());

    expect(find.text('Upload document'), findsOneWidget);
    expect(find.text('Sign in'), findsOneWidget);
    expect(find.text('Register'), findsOneWidget);

    await tester.tap(find.byType(DropdownButtonFormField<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Français').last);
    await tester.pumpAndSettle();

    expect(find.text('Téléverser un document'), findsOneWidget);
    expect(find.text('Se connecter'), findsOneWidget);
    expect(find.text('S’inscrire'), findsOneWidget);
    expect(find.text('Langue'), findsOneWidget);
    expect(find.text('Upload document'), findsNothing);
  });

  testWidgets('English to Swedish updates guest UI from dropdown', (
    WidgetTester tester,
  ) async {
    await appLanguageController.setLanguage('en');
    await tester.pumpWidget(_localizedGuestApp());

    expect(find.text('Upload document'), findsOneWidget);
    expect(find.text('Sign in'), findsOneWidget);
    expect(find.text('Register'), findsOneWidget);

    await tester.tap(find.byType(DropdownButtonFormField<String>));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.textContaining('Svenska'),
      240,
      scrollable: find.byType(Scrollable).last,
    );
    await tester.tap(find.textContaining('Svenska').last);
    await tester.pumpAndSettle();

    expect(find.text('Ladda upp dokument'), findsOneWidget);
    expect(find.text('Logga in'), findsOneWidget);
    expect(find.text('Registrera dig'), findsOneWidget);
    expect(find.text('Språk'), findsOneWidget);
    expect(find.text('Upload document'), findsNothing);
  });

  testWidgets('German guest UI uses German copy', (WidgetTester tester) async {
    await appLanguageController.setLanguage('de');
    await tester.pumpWidget(_localizedGuestApp());

    expect(find.text('Dokument hochladen'), findsOneWidget);
    expect(find.text('Anmelden'), findsOneWidget);
    expect(find.text('Registrieren'), findsOneWidget);
    expect(find.text('Sprache'), findsOneWidget);
  });

  testWidgets('Turkish guest UI keeps Turkish copy', (
    WidgetTester tester,
  ) async {
    await appLanguageController.setLanguage('tr');
    await tester.pumpWidget(_localizedGuestApp());

    expect(find.text('Doküman yükle'), findsOneWidget);
    expect(find.text('Giriş Yap'), findsOneWidget);
    expect(find.text('Kayıt Ol'), findsOneWidget);
  });

  testWidgets('Arabic guest UI uses Arabic copy and RTL direction', (
    WidgetTester tester,
  ) async {
    await appLanguageController.setLanguage('ar');
    await tester.pumpWidget(_localizedGuestApp());

    expect(find.text('رفع مستند'), findsOneWidget);
    expect(find.text('تسجيل الدخول'), findsOneWidget);
    expect(find.text('إنشاء حساب'), findsOneWidget);
    expect(
      Directionality.of(tester.element(find.text('رفع مستند'))),
      TextDirection.rtl,
    );
  });

  testWidgets('authenticated workspace switches from English to French', (
    WidgetTester tester,
  ) async {
    await appLanguageController.setLanguage('en');
    await tester.pumpWidget(_localizedPanelApp());

    expect(find.text('Upload document'), findsOneWidget);
    expect(find.text('Select file'), findsOneWidget);
    expect(find.text('Refresh parts'), findsOneWidget);
    expect(find.text('I don’t understand'), findsWidgets);
    expect(find.text('Evidence-based answer'), findsNothing);
    expect(find.text('Write your question'), findsNothing);

    await appLanguageController.setLanguage('fr');
    await tester.pump();

    expect(find.text('Téléverser un document'), findsOneWidget);
    expect(find.text('Sélectionner un fichier'), findsOneWidget);
    expect(find.text('Actualiser les sections'), findsOneWidget);
    expect(find.text('Je ne comprends pas'), findsWidgets);
    expect(find.text('Réponse avec preuves'), findsOneWidget);
    expect(find.text('Question'), findsNothing);
    expect(find.text('Upload document'), findsNothing);
  });

  testWidgets('authenticated workspace switches from French to German', (
    WidgetTester tester,
  ) async {
    await appLanguageController.setLanguage('fr');
    await tester.pumpWidget(_localizedPanelApp());

    expect(find.text('Téléverser un document'), findsOneWidget);

    await appLanguageController.setLanguage('de');
    await tester.pump();

    expect(find.text('Dokument hochladen'), findsOneWidget);
    expect(find.text('Datei auswählen'), findsOneWidget);
    expect(find.text('Abschnitte aktualisieren'), findsOneWidget);
    expect(find.text('Ich verstehe das nicht'), findsWidgets);
    expect(find.text('Antwort mit Nachweisen'), findsNothing);
    expect(find.text('Frage'), findsNothing);
  });

  testWidgets('authenticated workspace uses Swedish copy', (
    WidgetTester tester,
  ) async {
    await appLanguageController.setLanguage('sv');
    await tester.pumpWidget(_localizedPanelApp());

    expect(find.text('Ladda upp dokument'), findsOneWidget);
    expect(find.text('Välj fil'), findsOneWidget);
    expect(find.text('Uppdatera delar'), findsOneWidget);
    expect(find.text('Jag förstår inte'), findsWidgets);
    expect(find.text('Svar med bevis'), findsNothing);
    expect(AppLocalizer('sv').t('evidence'), 'Bevis');
    expect(find.text('Select file'), findsNothing);
    expect(find.text('Refresh parts'), findsNothing);
  });

  testWidgets('authenticated workspace uses Arabic copy and keeps RTL', (
    WidgetTester tester,
  ) async {
    await appLanguageController.setLanguage('ar');
    await tester.pumpWidget(_localizedPanelApp());

    expect(find.text('رفع مستند'), findsOneWidget);
    expect(find.text('اختيار ملف'), findsOneWidget);
    expect(find.text('تحديث الأجزاء'), findsOneWidget);
    expect(find.text('لم أفهم'), findsWidgets);
    expect(find.text('إجابة مدعومة بالأدلة'), findsNothing);
    expect(find.text('السؤال'), findsNothing);
    expect(
      Directionality.of(tester.element(find.text('رفع مستند'))),
      TextDirection.rtl,
    );
  });

  testWidgets('Guest home screen hides document and mock modules', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: HomeScreen(isGuest: true)));

    expect(find.text('Doküman yükle'), findsOneWidget);
    expect(find.text('Bunu Anlamadım'), findsNothing);
    expect(find.text('Kanıtlı cevap'), findsNothing);
    expect(find.text("Director's cut"), findsNothing);
    expect(find.text('Kavram grafigi'), findsNothing);
    expect(find.text('Akilli Notlar'), findsNothing);
    expect(find.text('Portal Notlar'), findsNothing);
    expect(find.text('Test zamani'), findsNothing);
    expect(find.text('Boss Fight'), findsNothing);
    expect(find.text('Kacis Odasi'), findsNothing);
    expect(find.text('Speedrun'), findsNothing);
  });

  test('EvidenceAnswer parses source path and score aliases', () {
    final answer = EvidenceAnswer.fromJson({
      'answer': 'ATP enerji taşır.',
      'evidence': [
        {
          'snippet': 'ATP hücresel enerji aktarımında kullanılır.',
          'source': 'mobil_test_belgesi.txt',
          'path': 'docs/mobil_test_belgesi.txt',
          'score': 0.91,
        },
      ],
    });

    expect(answer.answer, 'ATP enerji taşır.');
    expect(answer.evidence, hasLength(1));
    expect(answer.evidence.first.source, 'mobil_test_belgesi.txt');
    expect(answer.evidence.first.path, 'docs/mobil_test_belgesi.txt');
    expect(answer.evidence.first.score, '0.91');
  });

  test('EvidenceAnswer prefers text snippets over compact kanitlar', () {
    final answer = EvidenceAnswer.fromJson({
      'answer':
          'Bu soruya göre belgede en ilgili bölüm ATP görevini anlatıyor.',
      'snippets': [
        {
          'text': 'ATP hücrede enerji taşıyıcısı olarak görev yapar.',
          'source': 'mobil_test_belgesi.txt',
          'path': '1. Giris',
          'score': 0.0,
        },
      ],
      'kanitlar': [
        {'parca_id': 164, 'adres': '1. Giris', 'score': 0.0},
      ],
    });

    expect(answer.answer, contains('ATP'));
    expect(answer.evidence, hasLength(1));
    expect(
      answer.evidence.first.text,
      'ATP hücrede enerji taşıyıcısı olarak görev yapar.',
    );
    expect(answer.evidence.first.source, 'mobil_test_belgesi.txt');
    expect(answer.evidence.first.path, '1. Giris');
  });

  test('EvidenceAnswer parses kaynaklar alias', () {
    final answer = EvidenceAnswer.fromJson({
      'cevap': 'Kaynaklardan cevap üretildi.',
      'kaynaklar': [
        {
          'metin': 'Kaynaklar alias alanından gelen kanıt.',
          'kaynak': 'ders-notu',
          'adres': 'Bölüm 1',
          'skor': 0.42,
        },
      ],
    });

    expect(answer.evidence, hasLength(1));
    expect(
      answer.evidence.first.text,
      'Kaynaklar alias alanından gelen kanıt.',
    );
    expect(answer.evidence.first.source, 'ders-notu');
    expect(answer.evidence.first.path, 'Bölüm 1');
    expect(answer.evidence.first.score, '0.42');
  });

  test('Evidence payload always sends question field', () {
    final payload = AiService.buildEvidencePayload(
      question: '  ATP hücrede ne işe yarar?  ',
      documentId: 12,
      partId: 34,
    );

    expect(payload, {
      'question': 'ATP hücrede ne işe yarar?',
      'doc_id': 12,
      'part_id': 34,
    });
    expect(payload.containsKey('soru'), isFalse);
    expect(payload.containsKey('document_id'), isFalse);
  });

  test('DocumentPart parses difficulty fields with safe defaults', () {
    final fallback = DocumentPart.fromJson({'id': 1, 'metin': 'Metin'});
    expect(fallback.difficultyLabel, 'orta');
    expect(fallback.difficultyScore, isNull);
    expect(fallback.difficultyReasons, isEmpty);

    final parsed = DocumentPart.fromJson({
      'id': 2,
      'difficulty_score': 0.76,
      'difficulty_label': 'zor',
      'difficulty_reasons': ['Terim yogunlugu yuksek'],
      'metin': 'JWT API OAuth',
    });
    expect(parsed.difficultyScore, 0.76);
    expect(parsed.difficultyLabel, 'zor');
    expect(parsed.difficultyReasons, ['Terim yogunlugu yuksek']);
  });

  test('new confusion map i18n keys work in tr en and sv', () {
    expect(AppLocalizer('tr').t('difficultyHard'), 'Zor');
    expect(AppLocalizer('en').t('hardestSections'), 'Hardest sections');
    expect(
      AppLocalizer('sv').t('startWithThisPart'),
      'Börja med detta avsnitt',
    );
  });
}
