import 'package:flutter/foundation.dart';

import '../core/config/app_config.dart';
import '../core/constants/app_constants.dart';
import '../core/i18n/app_language.dart';
import '../core/network/api_exception.dart';
import '../core/network/api_client.dart';
import '../core/utils/parse_utils.dart';
import '../features/explain/data/directors_cut_response.dart';
import '../features/explain/data/explain_response.dart';
import '../features/explain/data/remix_response.dart';
import '../features/preferences/data/learning_preferences.dart';
import '../features/qa/data/evidence_answer.dart';

class AiService {
  AiService({ApiClient? apiClient}) : _apiClient = apiClient ?? ApiClient();

  final ApiClient _apiClient;
  static const _aiTimeoutMessage =
      'Anlatım hazırlanırken süre doldu. AI servisi yoğun olabilir, tekrar deneyin.';

  Future<ExplainResponse> askExplain({
    required int partId,
    Map<String, dynamic>? payload,
    LearningPreferences? preferences,
  }) async {
    final endpoint = AppConstants.explainEndpoint(partId);
    if (kDebugMode) {
      debugPrint('ANLAMADIM request started');
      debugPrint('selectedPartId=$partId');
    }

    final response = await _apiClient.postWithMeta(
      endpoint,
      body: {
        ...(payload ?? {'mod': 'basit'}),
        if (preferences != null) 'preferences': preferences.toJson(),
      },
      timeout: AppConfig.aiRequestTimeout,
      timeoutMessage: _aiTimeoutMessage,
    );

    if (kDebugMode) {
      debugPrint(
        'ANLAMADIM response status=${response.statusCode} '
        'parsed=${response.parsedKeys}',
      );
    }

    if (response.parseFailed || _looksHtml(response.bodyText)) {
      if (kDebugMode) {
        debugPrint('ANLAMADIM parse failed');
      }
      throw const ApiException(
        'Anlatım alınamadı. Sunucu yanıtı beklenen formatta değil.',
      );
    }

    final parsed = ExplainResponse.fromDynamic(response.body);
    if (kDebugMode && parsed.isEmpty) {
      debugPrint('ANLAMADIM empty response');
    }
    return parsed;
  }

  bool _looksHtml(String text) {
    final lower = text.toLowerCase();
    return lower.contains('<!doctype html') ||
        lower.contains('<html') ||
        lower.contains('<body') ||
        lower.contains('<head') ||
        lower.contains('<script');
  }

  Future<EvidenceAnswer> askEvidenceAnswer({
    required int documentId,
    int? partId,
    required String question,
    LearningPreferences? preferences,
  }) async {
    final trimmedQuestion = question.trim();
    final payload = buildEvidencePayload(
      question: trimmedQuestion,
      documentId: documentId,
      partId: partId,
      preferences: preferences,
    );
    if (kDebugMode) {
      debugPrint('EVIDENCE request started');
      debugPrint('questionLength=${trimmedQuestion.length}');
      debugPrint('payloadKeys=${payload.keys.join(',')}');
    }
    final response = await _apiClient.post(
      AppConstants.evidenceAnswerEndpoint,
      body: payload,
      timeout: AppConfig.aiRequestTimeout,
      timeoutMessage: _aiTimeoutMessage,
    );
    if (kDebugMode) {
      debugPrint('EVIDENCE request done');
    }
    return EvidenceAnswer.fromJson(ParseUtils.asMap(response));
  }

  Future<RemixResponse> requestRemix({
    required int partId,
    required String style,
    Map<String, dynamic>? source,
    String? lang,
    LearningPreferences? preferences,
  }) async {
    final language = lang?.trim().isNotEmpty == true
        ? lang!.trim()
        : AppLanguageController.normalize(appLanguageController.value);
    final response = await _apiClient.post(
      AppConstants.remixEndpoint(partId),
      body: {
        'style': style,
        if (source != null && source.isNotEmpty) 'source': source,
        if (preferences != null) 'preferences': preferences.toJson(),
        'lang': language,
      },
      timeout: AppConfig.aiRequestTimeout,
      timeoutMessage: _aiTimeoutMessage,
    );
    return RemixResponse.fromDynamic(response);
  }

  Future<DirectorsCutResponse> requestDirectorsCut({
    required int partId,
    required String cutType,
    Map<String, dynamic>? source,
    String? lang,
    LearningPreferences? preferences,
  }) async {
    final language = lang?.trim().isNotEmpty == true
        ? lang!.trim()
        : AppLanguageController.normalize(appLanguageController.value);
    final response = await _apiClient.post(
      AppConstants.directorsCutEndpoint(partId),
      body: {
        'cut_type': cutType,
        if (source != null && source.isNotEmpty) 'source': source,
        if (preferences != null) 'preferences': preferences.toJson(),
        'lang': language,
      },
      timeout: AppConfig.aiRequestTimeout,
      timeoutMessage: _aiTimeoutMessage,
    );
    return DirectorsCutResponse.fromDynamic(response);
  }

  @visibleForTesting
  static Map<String, dynamic> buildEvidencePayload({
    required String question,
    required int documentId,
    int? partId,
    LearningPreferences? preferences,
  }) {
    return {
      'question': question.trim(),
      'doc_id': documentId,
      if (partId != null && partId > 0) 'part_id': partId,
      if (preferences != null) 'preferences': preferences.toJson(),
    };
  }
}
