import '../core/constants/app_constants.dart';
import '../core/i18n/app_language.dart';
import '../core/network/api_client.dart';
import '../features/concepts/data/concept_models.dart';
import '../features/concepts/data/fusion_card.dart';
import '../features/preferences/data/learning_preferences.dart';

class ConceptService {
  ConceptService({ApiClient? apiClient})
    : _apiClient = apiClient ?? ApiClient();

  final ApiClient _apiClient;

  Future<ConceptGraphResponse> fetchPartConcepts(int partId) async {
    final response = await _apiClient.get(
      AppConstants.partConceptsEndpoint(partId),
    );
    return ConceptGraphResponse.fromDynamic(response);
  }

  Future<ConceptGraphResponse> fetchDocumentConcepts(int documentId) async {
    final response = await _apiClient.get(
      AppConstants.documentConceptsEndpoint(documentId),
    );
    return ConceptGraphResponse.fromDynamic(response);
  }

  Future<ConceptGraphResponse> searchConceptMentions(
    int documentId,
    String query,
  ) async {
    final response = await _apiClient.get(
      AppConstants.searchConceptEndpoint(documentId, query),
    );
    return ConceptGraphResponse.fromDynamic(response);
  }

  Future<FusionCard> requestConceptFusion({
    required int documentId,
    required String termA,
    required String termB,
    int? partId,
    LearningPreferences? preferences,
  }) async {
    final body = <String, dynamic>{
      'term_a': termA,
      'term_b': termB,
      'lang': AppLanguageController.normalize(appLanguageController.value),
    };
    if (partId != null) body['part_id'] = partId;
    if (preferences != null) body['preferences'] = preferences.toJson();
    final response = await _apiClient.post(
      AppConstants.conceptFusionEndpoint(documentId),
      body: body,
    );
    return FusionCard.fromDynamic(response);
  }
}
