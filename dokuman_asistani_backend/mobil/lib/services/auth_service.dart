import 'package:flutter/foundation.dart';

import '../core/constants/app_constants.dart';
import '../core/network/api_client.dart';
import '../core/storage/token_storage.dart';
import '../core/utils/parse_utils.dart';
import '../features/auth/data/auth_tokens.dart';

class AuthService {
  AuthService({ApiClient? apiClient, TokenStorage? tokenStorage})
    : this._(
        apiClient: apiClient,
        tokenStorage: tokenStorage ?? TokenStorage(),
      );

  AuthService._({ApiClient? apiClient, required TokenStorage tokenStorage})
    : _apiClient = apiClient ?? ApiClient(tokenStorage: tokenStorage),
      _tokenStorage = tokenStorage;

  final ApiClient _apiClient;
  final TokenStorage _tokenStorage;

  Future<bool> hasStoredSession() async =>
      await _tokenStorage.hasAccessToken() ||
      await _tokenStorage.hasRefreshToken();

  Future<bool> restoreSession() => _apiClient.ensureAuthenticatedSession();

  Future<AuthTokens> login({
    required String username,
    required String password,
  }) async {
    if (kDebugMode) {
      debugPrint('Login request started');
    }
    final response = await _apiClient.post(
      AppConstants.loginEndpoint,
      body: {'username': username, 'password': password},
    );
    final tokens = AuthTokens.fromJson(ParseUtils.asMap(response));
    await _tokenStorage.clear();
    await _tokenStorage.saveTokens(
      access: tokens.access,
      refresh: tokens.refresh,
    );
    if (kDebugMode) {
      debugPrint('Login request done');
    }
    return tokens;
  }

  Future<void> register({
    required String username,
    required String password,
    String? passwordAgain,
    String? email,
  }) async {
    final confirmPassword = passwordAgain ?? password;
    _debugRegisterRequest(username: username, email: email);
    await _apiClient.post(
      AppConstants.registerEndpoint,
      body: {
        'username': username,
        'password': password,
        'password2': confirmPassword,
        if (email != null && email.isNotEmpty) 'email': email,
      },
    );
  }

  void _debugRegisterRequest({required String username, String? email}) {
    if (!kDebugMode) return;
    debugPrint('REGISTER request started');
    debugPrint('REGISTER payload keys: username,email,password,password2');
    debugPrint(
      'REGISTER identity: username=${_mask(username)}, email=${_maskEmail(email)}',
    );
  }

  String _mask(String value) {
    if (value.length <= 2) return '**';
    return '${value.substring(0, 2)}***';
  }

  String _maskEmail(String? value) {
    if (value == null || value.isEmpty) return 'empty';
    final parts = value.split('@');
    if (parts.length != 2) return _mask(value);
    return '${_mask(parts.first)}@${parts.last}';
  }

  Future<void> logout() => clearSession(reason: 'logout');

  Future<void> clearSession({required String reason}) async {
    if (kDebugMode) {
      debugPrint('SESSION cleared reason=$reason');
    }
    await _tokenStorage.clear();
  }
}
