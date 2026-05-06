class AppConfig {
  AppConfig._();

  static const String baseApiUrl = String.fromEnvironment(
    'BASE_API_URL',
    defaultValue: 'http://127.0.0.1:8001',
  );

  static const String emulatorApiUrlHint = 'http://10.0.2.2:8001';

  static const Duration requestTimeout = Duration(seconds: 30);
  static const Duration aiRequestTimeout = Duration(seconds: 180);

  static Uri apiUri(String path, [Map<String, dynamic>? query]) {
    final normalizedPath = path.startsWith('/') ? path : '/$path';
    final base = Uri.parse(baseApiUrl);
    return base.replace(
      path: normalizedPath,
      queryParameters: query?.map((key, value) => MapEntry(key, '$value')),
    );
  }
}
