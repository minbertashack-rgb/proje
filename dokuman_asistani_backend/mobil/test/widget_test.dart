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
import 'package:mobil/features/documents/data/document_part.dart';
import 'package:mobil/features/documents/data/uploaded_document.dart';
import 'package:mobil/features/auth/presentation/login_screen.dart';
import 'package:mobil/features/explain/data/directors_cut_response.dart';
import 'package:mobil/features/explain/data/explain_response.dart';
import 'package:mobil/features/explain/data/remix_response.dart';
import 'package:mobil/features/home/presentation/home_screen.dart';
import 'package:mobil/features/home/widgets/backend_flow_panel.dart';
import 'package:mobil/features/preferences/data/learning_preferences.dart';
import 'package:mobil/features/qa/data/evidence_answer.dart';
import 'package:mobil/services/ai_service.dart';
import 'package:mobil/services/concept_service.dart';
import 'package:mobil/services/preference_service.dart';

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
           );

  final ExplainResponse explain;
  final EvidenceAnswer answer;
  final DirectorsCutResponse directorsCut;
  final RemixResponse remix;
  final Duration directorsCutDelay;
  final Duration remixDelay;
  LearningPreferences? lastExplainPreferences;
  LearningPreferences? lastEvidencePreferences;
  LearningPreferences? lastRemixPreferences;
  LearningPreferences? lastDirectorsCutPreferences;

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
  _FakeConceptService({required this.searchResponse});

  final ConceptGraphResponse searchResponse;

  @override
  Future<ConceptGraphResponse> searchConceptMentions(
    int documentId,
    String query,
  ) async {
    return searchResponse;
  }
}

Widget _localizedGuestApp() {
  return _localizedPanelApp(isGuest: true);
}

Widget _localizedPanelApp({
  bool isGuest = false,
  AiService? aiService,
  ConceptService? conceptService,
  PreferenceService? preferenceService,
}) {
  return AppLanguageScope(
    controller: appLanguageController,
    child: MaterialApp(
      builder: (context, child) => Directionality(
        textDirection: AppLocalizer.textDirectionOf(context),
        child: child ?? const SizedBox.shrink(),
      ),
      home: Scaffold(
        body: SingleChildScrollView(
          child: BackendFlowPanel(
            isGuest: isGuest,
            aiService: aiService,
            conceptService: conceptService,
            preferenceService: preferenceService ?? _FakePreferenceService(),
          ),
        ),
      ),
    ),
  );
}

const _testDocument = UploadedDocument(id: 7, title: 'Test dokumani');
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
    expect(find.text('Kanıtlı cevap sor'), findsNothing);
    expect(find.text('Giriş Yap'), findsNothing);
    expect(find.text('Kayıt Ol'), findsNothing);
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

      await tester.tap(find.text('Varsayılan').first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Oyun').last);
      await tester.pumpAndSettle();
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
      expect(find.text('Kanıtlı cevap sor'), findsNothing);
      expect(find.text('Sorunu yaz'), findsNothing);

      final explainButton = find.widgetWithText(FilledButton, 'Bunu Anlamadım');
      await tester.ensureVisible(explainButton);
      await tester.pumpAndSettle();
      await tester.tap(explainButton);
      await tester.pumpAndSettle();

      expect(find.text('Sorunu kanıtlarla derinleştir'), findsOneWidget);
      expect(find.text('Kanıtlı cevap sor'), findsOneWidget);
      expect(find.text('Sorunu yaz'), findsNothing);

      await tester.ensureVisible(find.text('Kanıtlı cevap sor'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Kanıtlı cevap sor'));
      await tester.pumpAndSettle();

      expect(find.text('Sorunu yaz'), findsOneWidget);
      expect(find.text('Gönder'), findsOneWidget);
    },
  );

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

    expect(find.textContaining('Hucrede enerji tasiyan molekul.'), findsOneWidget);
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
    expect(find.text('Kanıtlı cevap sor'), findsOneWidget);
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
    expect(find.text('Kanıtlı cevap sor'), findsOneWidget);
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
      await tester.ensureVisible(find.text('Kanıtlı cevap sor'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Kanıtlı cevap sor'));
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
      expect(find.text('Kanıtlı cevap sor'), findsNothing);
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

    expect(find.text('Kanıtlı cevap sor'), findsNothing);
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
    expect(find.text('Réponse avec preuves'), findsNothing);
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
