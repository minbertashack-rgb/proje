import '../core/constants/app_constants.dart';
import '../core/network/api_client.dart';
import '../features/outputs/data/export_payload_models.dart';

class ExportService {
  ExportService({ApiClient? apiClient}) : _apiClient = apiClient ?? ApiClient();

  final ApiClient _apiClient;

  Future<ExportPayload> fetchCheatsheet(int documentId) =>
      _fetch('cheatsheet', AppConstants.exportCheatsheetEndpoint(documentId));

  Future<ExportPayload> fetchStudySummary(int documentId) =>
      _fetch('study_summary', AppConstants.exportStudySummaryEndpoint(documentId));

  Future<ExportPayload> fetchPresentationPlan(int documentId) =>
      _fetch('presentation_plan', AppConstants.exportPresentationPlanEndpoint(documentId));

  Future<ExportPayload> fetchReadme(int documentId) =>
      _fetch('readme', AppConstants.exportReadmeEndpoint(documentId));

  Future<ExportPayload> fetchReadiness(int documentId) =>
      _fetch('readiness', AppConstants.exportReadinessEndpoint(documentId));

  Future<PremiumUiPayload> fetchPremiumPayload(int documentId) async {
    final response = await _apiClient.get(AppConstants.premiumPayloadEndpoint(documentId));
    return PremiumUiPayload.fromDynamic(response);
  }

  Future<ExportPayload> _fetch(String type, String endpoint) async {
    final response = await _apiClient.get(endpoint);
    return ExportPayload.fromDynamic(type, response);
  }
}
