import '../core/config/app_config.dart';
import '../core/constants/app_constants.dart';
import '../core/network/api_client.dart';
import '../features/home/data/game_models.dart';

class GameService {
  GameService({ApiClient? apiClient}) : _apiClient = apiClient ?? ApiClient();

  final ApiClient _apiClient;

  Future<GameProfile> fetchGameProfile() async {
    final response = await _apiClient.get(AppConstants.gameProfileEndpoint);
    return GameProfile.fromDynamic(response);
  }

  Future<GameProfile> fetchProfile() => fetchGameProfile();

  Future<GameRewards> fetchRewards() async {
    final response = await _apiClient.get(AppConstants.gameRewardsEndpoint);
    return GameRewards.fromDynamic(response);
  }

  Future<WeeklyProgress> fetchWeeklyProgress() async {
    final response = await _apiClient.get(AppConstants.weeklyProgressEndpoint);
    return WeeklyProgress.fromDynamic(response);
  }

  Future<BossPayload> startBossFight(int partId) async {
    final response = await _apiClient.post(
      AppConstants.bossFightEndpoint(partId),
      timeout: AppConfig.aiRequestTimeout,
    );
    return BossPayload.fromDynamic(response);
  }

  Future<BossResult> answerBossFight({
    required int partId,
    required String bossId,
    required List<String> answers,
  }) async {
    final response = await _apiClient.post(
      AppConstants.bossFightAnswerEndpoint(partId),
      body: {'boss_id': bossId, 'answers': answers},
      timeout: AppConfig.aiRequestTimeout,
    );
    return BossResult.fromDynamic(response);
  }

  Future<BossResult> answerBoss({
    required int partId,
    required String bossId,
    required List<String> answers,
  }) => answerBossFight(partId: partId, bossId: bossId, answers: answers);

  Future<BossRush> fetchBossRush(int documentId) async {
    final response = await _apiClient.get(
      AppConstants.bossRushEndpoint(documentId),
      timeout: AppConfig.aiRequestTimeout,
    );
    return BossRush.fromDynamic(response);
  }
}
