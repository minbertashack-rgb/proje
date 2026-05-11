import '../core/constants/app_constants.dart';
import '../core/network/api_client.dart';
import '../features/outputs/data/reels_models.dart';

class ReelsService {
  ReelsService({ApiClient? apiClient}) : _apiClient = apiClient ?? ApiClient();

  final ApiClient _apiClient;

  Future<ReelsPayload> fetchPartReels(int partId) async {
    final response = await _apiClient.post(AppConstants.partReelsEndpoint(partId));
    return ReelsPayload.fromDynamic(response);
  }

  Future<ReelsPayload> fetchDocumentReels(int documentId) async {
    final response = await _apiClient.get(AppConstants.documentReelsEndpoint(documentId));
    return ReelsPayload.fromDynamic(response);
  }
}
