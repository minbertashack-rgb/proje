import '../core/constants/app_constants.dart';
import '../core/network/api_client.dart';
import '../features/preferences/data/learning_preferences.dart';

class PreferenceService {
  PreferenceService({ApiClient? apiClient})
    : _apiClient = apiClient ?? ApiClient();

  final ApiClient _apiClient;

  Future<LearningPreferences> fetchPreferences() async {
    final response = await _apiClient.get(AppConstants.preferencesEndpoint);
    return LearningPreferences.fromDynamic(response);
  }

  Future<LearningPreferences> savePreferences(
    LearningPreferences preferences,
  ) async {
    final response = await _apiClient.post(
      AppConstants.preferencesEndpoint,
      body: preferences.toJson(),
    );
    return LearningPreferences.fromDynamic(response);
  }
}
