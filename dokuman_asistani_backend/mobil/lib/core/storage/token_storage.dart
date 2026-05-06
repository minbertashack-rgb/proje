import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class TokenStorage {
  TokenStorage({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage();

  static const _accessKey = 'docverse_access_token';
  static const _refreshKey = 'docverse_refresh_token';

  final FlutterSecureStorage _storage;

  Future<String?> readAccessToken() => _storage.read(key: _accessKey);

  Future<String?> readRefreshToken() => _storage.read(key: _refreshKey);

  Future<bool> hasAccessToken() async {
    final token = await readAccessToken();
    return token != null && token.isNotEmpty;
  }

  Future<bool> hasRefreshToken() async {
    final token = await readRefreshToken();
    return token != null && token.isNotEmpty;
  }

  Future<bool> hasValidAccessToken() async {
    final token = await readAccessToken();
    return token != null && token.isNotEmpty && !isJwtExpired(token);
  }

  bool isJwtExpired(String token) {
    final expiresAt = jwtExpiresAt(token);
    if (expiresAt == null) return false;
    final refreshBefore = DateTime.now().toUtc().add(
      const Duration(seconds: 30),
    );
    return !expiresAt.isAfter(refreshBefore);
  }

  DateTime? jwtExpiresAt(String token) {
    try {
      final parts = token.split('.');
      if (parts.length < 2) return null;
      final normalized = base64Url.normalize(parts[1]);
      final decoded = utf8.decode(base64Url.decode(normalized));
      final payload = jsonDecode(decoded);
      if (payload is! Map<String, dynamic>) return null;
      final exp = payload['exp'];
      final seconds = exp is num ? exp.toInt() : int.tryParse('$exp');
      if (seconds == null) return null;
      return DateTime.fromMillisecondsSinceEpoch(
        seconds * 1000,
        isUtc: true,
      );
    } catch (_) {
      return null;
    }
  }

  Future<void> saveTokens({required String access, String? refresh}) async {
    await _storage.write(key: _accessKey, value: access);
    if (refresh != null && refresh.isNotEmpty) {
      await _storage.write(key: _refreshKey, value: refresh);
    }
  }

  Future<void> clear() async {
    await _storage.delete(key: _accessKey);
    await _storage.delete(key: _refreshKey);
  }
}
