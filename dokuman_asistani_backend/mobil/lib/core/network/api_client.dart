import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../constants/app_constants.dart';
import '../i18n/app_language.dart';
import '../i18n/app_localizer.dart';
import '../storage/token_storage.dart';
import '../utils/parse_utils.dart';
import 'api_exception.dart';

class ApiClient {
  ApiClient({http.Client? httpClient, TokenStorage? tokenStorage})
    : _httpClient = httpClient ?? http.Client(),
      _tokenStorage = tokenStorage ?? TokenStorage();

  final http.Client _httpClient;
  final TokenStorage _tokenStorage;
  Future<bool>? _refreshInFlight;

  Future<dynamic> get(
    String path, {
    Duration? timeout,
    String? timeoutMessage,
  }) => _send('GET', path, timeout: timeout, timeoutMessage: timeoutMessage);

  Future<ApiResponse<dynamic>> getWithMeta(
    String path, {
    Duration? timeout,
    String? timeoutMessage,
  }) => _sendWithMeta(
    'GET',
    path,
    timeout: timeout,
    timeoutMessage: timeoutMessage,
  );

  Future<dynamic> post(
    String path, {
    Map<String, dynamic>? body,
    Duration? timeout,
    String? timeoutMessage,
  }) => _send(
    'POST',
    path,
    body: body,
    timeout: timeout,
    timeoutMessage: timeoutMessage,
  );

  Future<ApiResponse<dynamic>> postWithMeta(
    String path, {
    Map<String, dynamic>? body,
    Duration? timeout,
    String? timeoutMessage,
  }) => _sendWithMeta(
    'POST',
    path,
    body: body,
    timeout: timeout,
    timeoutMessage: timeoutMessage,
  );

  Uri uriFor(String path) => AppConfig.apiUri(path);

  Future<bool> ensureAuthenticatedSession() async {
    try {
      return await _ensureUsableToken(AppConstants.uploadEndpoint);
    } on ApiException {
      return false;
    }
  }

  Future<dynamic> multipart(
    String path, {
    required String filePath,
    String fileField = 'dosya',
    Map<String, String>? fields,
  }) async {
    final response = await multipartWithMeta(
      path,
      filePath: filePath,
      fileField: fileField,
      fields: fields,
    );
    return response.body;
  }

  Future<ApiResponse<dynamic>> multipartWithMeta(
    String path, {
    required String filePath,
    String fileField = 'dosya',
    Map<String, String>? fields,
  }) async {
    try {
      final hasToken = await _ensureUsableToken(path);
      final request = await _buildMultipartRequest(
        path,
        filePath: filePath,
        fileField: fileField,
        fields: fields,
      );
      if (kDebugMode) {
        debugPrint('MULTIPART auth header added=$hasToken path=$path');
      }

      var response = await _sendMultipart(request);
      if (_shouldRetryWithRefresh(path, response.statusCode) &&
          await _refreshAccessToken()) {
        final retryRequest = await _buildMultipartRequest(
          path,
          filePath: filePath,
          fileField: fileField,
          fields: fields,
        );
        response = await _sendMultipart(retryRequest);
      }
      if (_isUnauthorizedStatus(response.statusCode)) {
        await _clearSessionAfterUnauthorized(path);
      }
      return _decodeResponseWithMeta(response, path: path);
    } on TimeoutException {
      throw const ApiException('Istek zaman asimina ugradi.');
    } on http.ClientException catch (error) {
      throw ApiException('Ag hatasi: ${error.message}');
    } on ApiException {
      rethrow;
    } catch (error) {
      throw ApiException('Dosya yukleme basarisiz: $error');
    }
  }

  Future<dynamic> _send(
    String method,
    String path, {
    Map<String, dynamic>? body,
    Duration? timeout,
    String? timeoutMessage,
  }) async {
    final response = await _sendWithMeta(
      method,
      path,
      body: body,
      timeout: timeout,
      timeoutMessage: timeoutMessage,
    );
    return response.body;
  }

  Future<ApiResponse<dynamic>> _sendWithMeta(
    String method,
    String path, {
    Map<String, dynamic>? body,
    Duration? timeout,
    String? timeoutMessage,
  }) async {
    final headers = await _jsonHeaders();
    await _ensureUsableToken(path);
    if (_requiresAuth(path)) {
      await _withAuth(headers);
    }

    final uri = AppConfig.apiUri(path);
    final encodedBody = body == null ? null : jsonEncode(body);
    final requestTimeout = timeout ?? AppConfig.requestTimeout;
    http.Response response;

    try {
      response = await _sendRequest(
        method,
        uri,
        headers: headers,
        encodedBody: encodedBody,
        timeout: requestTimeout,
      );
      if (_shouldRetryWithRefresh(path, response.statusCode) &&
          await _refreshAccessToken()) {
        final retryHeaders = await _jsonHeaders();
        await _withAuth(retryHeaders);
        response = await _sendRequest(
          method,
          uri,
          headers: retryHeaders,
          encodedBody: encodedBody,
          timeout: requestTimeout,
        );
      }
      if (_isUnauthorizedStatus(response.statusCode)) {
        await _clearSessionAfterUnauthorized(path);
      }
    } on TimeoutException {
      throw ApiException(timeoutMessage ?? 'Istek zaman asimina ugradi.');
    } on http.ClientException catch (error) {
      final message = error.message.toLowerCase();
      if (message.contains('software caused connection abort') ||
          message.contains('connection abort') ||
          message.contains('connection reset')) {
        throw const ApiException(
          'Kanıtlı cevap alınamadı. Sunucu bağlantısı kesildi, lütfen tekrar deneyin.',
        );
      }
      throw ApiException('Ag hatasi: ${error.message}');
    } on ApiException {
      rethrow;
    } on FormatException {
      throw const ApiException('Istek govdesi hazirlanamadi.');
    } catch (_) {
      throw const ApiException('Ag istegi tamamlanamadi.');
    }

    return _decodeResponseWithMeta(response, path: path);
  }

  Future<Map<String, String>> _jsonHeaders() async {
    return <String, String>{
      'Accept': 'application/json',
      'Content-Type': 'application/json',
      'Accept-Language': AppLanguageController.normalize(
        appLanguageController.value,
      ),
    };
  }

  Future<http.Response> _sendRequest(
    String method,
    Uri uri, {
    required Map<String, String> headers,
    required String? encodedBody,
    required Duration timeout,
  }) {
    return switch (method) {
      'GET' => _httpClient.get(uri, headers: headers).timeout(timeout),
      'POST' => _httpClient
          .post(uri, headers: headers, body: encodedBody)
          .timeout(timeout),
      _ => throw ApiException('Desteklenmeyen HTTP metodu: $method'),
    };
  }

  Future<http.MultipartRequest> _buildMultipartRequest(
    String path, {
    required String filePath,
    required String fileField,
    Map<String, String>? fields,
  }) async {
    final request = http.MultipartRequest('POST', AppConfig.apiUri(path));
    request.files.add(await http.MultipartFile.fromPath(fileField, filePath));
    request.fields.addAll(fields ?? {});
    request.headers['Accept-Language'] = AppLanguageController.normalize(
      appLanguageController.value,
    );
    await _withAuth(request.headers);
    return request;
  }

  Future<http.Response> _sendMultipart(http.MultipartRequest request) async {
    final streamed = await request.send().timeout(AppConfig.requestTimeout);
    return http.Response.fromStream(streamed);
  }

  Future<bool> _withAuth(Map<String, String> headers) async {
    final token = await _tokenStorage.readAccessToken();
    if (token != null && token.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
      return true;
    }
    return false;
  }

  Future<bool> _ensureUsableToken(String path) async {
    if (!_requiresAuth(path)) return false;
    if (await _tokenStorage.hasValidAccessToken()) return true;
    if (await _refreshAccessToken()) return true;
    await _clearSessionAfterUnauthorized(path);
    throw const ApiException(
      'Oturum süresi doldu. Lütfen tekrar giriş yap.',
      statusCode: 401,
    );
  }

  bool _requiresAuth(String path) {
    if (path == AppConstants.loginEndpoint ||
        path == AppConstants.registerEndpoint ||
        path == AppConstants.refreshEndpoint ||
        path == AppConstants.pingEndpoint) {
      return false;
    }
    return path.startsWith('/api/dokuman-asistani/');
  }

  bool _shouldRetryWithRefresh(String path, int statusCode) =>
      _requiresAuth(path) && _isUnauthorizedStatus(statusCode);

  bool _isUnauthorizedStatus(int statusCode) =>
      statusCode == 401 || statusCode == 403;

  Future<bool> _refreshAccessToken() {
    final inFlight = _refreshInFlight;
    if (inFlight != null) return inFlight;
    final refresh = _performRefresh();
    _refreshInFlight = refresh;
    return refresh.whenComplete(() => _refreshInFlight = null);
  }

  Future<bool> _performRefresh() async {
    final refreshToken = await _tokenStorage.readRefreshToken();
    if (refreshToken == null || refreshToken.isEmpty) return false;
    try {
      final response = await _httpClient
          .post(
            AppConfig.apiUri(AppConstants.refreshEndpoint),
            headers: await _jsonHeaders(),
            body: jsonEncode({'refresh': refreshToken}),
          )
          .timeout(AppConfig.requestTimeout);
      if (response.statusCode < 200 || response.statusCode >= 300) {
        await _tokenStorage.clear();
        return false;
      }
      final body = jsonDecode(response.body);
      final map = ParseUtils.nestedMap(body);
      final access = ParseUtils.firstString(map, [
        'access',
        'access_token',
        'token',
      ]);
      if (access == null || access.isEmpty) {
        await _tokenStorage.clear();
        return false;
      }
      final nextRefresh =
          ParseUtils.firstString(map, ['refresh', 'refresh_token']) ??
          refreshToken;
      await _tokenStorage.saveTokens(access: access, refresh: nextRefresh);
      if (kDebugMode) {
        debugPrint('SESSION refresh succeeded');
      }
      return true;
    } catch (_) {
      await _tokenStorage.clear();
      return false;
    }
  }

  Future<void> _clearSessionAfterUnauthorized(String path) async {
    if (!_requiresAuth(path)) return;
    await _tokenStorage.clear();
    if (kDebugMode) {
      debugPrint('SESSION cleared reason=unauthorized path=$path');
    }
  }

  ApiResponse<dynamic> _decodeResponseWithMeta(
    http.Response response, {
    required String path,
  }) {
    final text = response.body.trim();
    final contentType = response.headers['content-type']?.toLowerCase() ?? '';
    final expectsJson =
        contentType.contains('application/json') ||
        contentType.contains('+json') ||
        text.startsWith('{') ||
        text.startsWith('[');
    dynamic body;
    var parseFailed = false;
    if (text.isNotEmpty && expectsJson) {
      try {
        body = jsonDecode(text);
      } catch (_) {
        body = null;
        parseFailed = true;
      }
    } else if (text.isNotEmpty) {
      body = text;
    }

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return ApiResponse<dynamic>(
        statusCode: response.statusCode,
        contentType: contentType,
        bodyText: text,
        body: body,
        parseFailed: parseFailed,
      );
    }

    _debugResponseIssue(
      path: path,
      response: response,
      contentType: contentType,
      bodyText: text,
      parsedBody: body,
    );

    final fallback = switch (response.statusCode) {
      401 => 'Oturum süresi doldu. Lütfen tekrar giriş yap.',
      403 => 'Oturum süresi doldu. Lütfen tekrar giriş yap.',
      >= 500 => 'Sunucu hatasi olustu.',
      _ => 'API hatasi olustu.',
    };
    final message = _friendlyErrorMessage(
      body,
      fallback,
      contentType: contentType,
    );
    throw ApiException(message, statusCode: response.statusCode);
  }

  void _debugResponseIssue({
    required String path,
    required http.Response response,
    required String contentType,
    required String bodyText,
    required dynamic parsedBody,
  }) {
    if (!kDebugMode) return;
    final preview = bodyText.replaceAll(RegExp(r'\s+'), ' ').trim();
    final clipped = preview.length > 280
        ? '${preview.substring(0, 280)}...'
        : preview;
    final parsedSummary = parsedBody is Map<String, dynamic>
        ? parsedBody.keys.join(',')
        : parsedBody is List
        ? 'list(${parsedBody.length})'
        : parsedBody == null
        ? 'none'
        : parsedBody.runtimeType.toString();
    debugPrint(
      'API error: status=${response.statusCode}, '
      'contentType=${contentType.isEmpty ? 'unknown' : contentType}, '
      'parsed=$parsedSummary, bodyPreviewLength=${clipped.length}',
    );
  }

  String _friendlyErrorMessage(
    dynamic body,
    String fallback, {
    String contentType = '',
  }) {
    if (body is Map<String, dynamic>) {
      final localized = AppLocalizer.messageForErrorCode(
        body['error_code']?.toString(),
      );
      if (localized.isNotEmpty) return localized;

      final fieldErrors = _fieldErrorMessage(
        _asStringKeyMap(body['field_errors']),
      );
      if (fieldErrors != null) return _cleanErrorText(fieldErrors, fallback);

      final direct = _firstErrorValue(body, [
        'detail',
        'status_text',
        'message',
        'mesaj',
        'error',
        'hata',
        'non_field_errors',
      ]);
      if (direct != null) {
        final rawLocalized = AppLocalizer.localizeRawError(direct);
        if (rawLocalized.isNotEmpty) return rawLocalized;
        return _cleanErrorText(direct, fallback);
      }

      final fieldMessage = _fieldErrorMessage(body);
      if (fieldMessage != null) {
        return _cleanErrorText(fieldMessage, fallback);
      }
    }

    if (body is String && body.isNotEmpty) {
      final lowerContentType = contentType.toLowerCase();
      if (lowerContentType.contains('text/html')) {
        return 'Sunucudan beklenmeyen yanit geldi.';
      }
      final rawLocalized = AppLocalizer.localizeRawError(body);
      if (rawLocalized.isNotEmpty) return rawLocalized;
      return _cleanErrorText(body, fallback);
    }

    return fallback;
  }

  String? _firstErrorValue(Map<String, dynamic> body, List<String> keys) {
    for (final key in keys) {
      final value = body[key];
      if (value is List && value.isNotEmpty) return value.first?.toString();
      if (value is Map && value.isNotEmpty) {
        return _fieldErrorMessage(Map<String, dynamic>.from(value));
      }
      if (value != null) return value.toString();
    }
    return null;
  }

  Map<String, dynamic> _asStringKeyMap(dynamic value) {
    if (value is Map<String, dynamic>) return value;
    if (value is Map) return Map<String, dynamic>.from(value);
    return const {};
  }

  String? _fieldErrorMessage(Map<String, dynamic> body) {
    const labels = {
      'username': 'Kullanici adi',
      'question': 'Soru',
      'soru': 'Soru',
      'doc_id': 'Dokuman',
      'document_id': 'Dokuman',
      'part_id': 'Parca',
      'parca_id': 'Parca',
      'email': 'Email',
      'password': 'Sifre',
      'password1': 'Sifre',
      'password2': 'Sifre tekrar',
      'password_confirm': 'Sifre tekrar',
      'sifre': 'Sifre',
      'non_field_errors': 'Hata',
    };

    for (final entry in body.entries) {
      final value = entry.value;
      String? message;
      if (value is List && value.isNotEmpty) {
        message = value.first?.toString();
      } else if (value is String) {
        message = value;
      }
      if (message == null || message.trim().isEmpty) continue;
      final label = labels[entry.key] ?? entry.key;
      return '$label: $message';
    }
    return null;
  }

  String _cleanErrorText(String? raw, String fallback) {
    final text = raw?.trim();
    if (text == null || text.isEmpty) return fallback;
    final lower = text.toLowerCase();
    final looksHtml =
        lower.contains('<!doctype html') ||
        lower.contains('<html') ||
        lower.contains('<body') ||
        lower.contains('<head') ||
        lower.contains('</div>') ||
        lower.contains('<script');
    if (looksHtml) return 'Sunucudan beklenmeyen yanit geldi.';
    if (text.length > 180) return fallback;
    return text;
  }
}

class ApiResponse<T> {
  const ApiResponse({
    required this.statusCode,
    required this.contentType,
    required this.bodyText,
    required this.body,
    required this.parseFailed,
  });

  final int statusCode;
  final String contentType;
  final String bodyText;
  final T body;
  final bool parseFailed;

  String get bodyPreview {
    final preview = bodyText.replaceAll(RegExp(r'\s+'), ' ').trim();
    return preview.length > 280 ? '${preview.substring(0, 280)}...' : preview;
  }

  String get parsedKeys {
    final value = body;
    if (value is Map<String, dynamic>) return value.keys.join(',');
    if (value is Map) return value.keys.map((key) => '$key').join(',');
    if (value is List) return 'list(${value.length})';
    if (value == null) return 'none';
    return value.runtimeType.toString();
  }
}
