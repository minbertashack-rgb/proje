import '../core/constants/app_constants.dart';
import '../core/network/api_client.dart';
import '../features/concepts/data/concept_models.dart';

class ConceptService {
  ConceptService({ApiClient? apiClient}) : _apiClient = apiClient ?? ApiClient();

  final ApiClient _apiClient;

  Future<ConceptGraphResponse> fetchPartConcepts(int partId) async {
    final response = await _apiClient.get(AppConstants.partConceptsEndpoint(partId));
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
}
