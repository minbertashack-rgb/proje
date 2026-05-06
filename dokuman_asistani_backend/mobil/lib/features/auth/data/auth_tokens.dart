import '../../../core/utils/parse_utils.dart';

class AuthTokens {
  const AuthTokens({required this.access, this.refresh});

  final String access;
  final String? refresh;

  factory AuthTokens.fromJson(Map<String, dynamic> json) {
    final map = ParseUtils.nestedMap(json);
    final access = ParseUtils.firstString(map, [
      'access',
      'access_token',
      'token',
    ]);
    if (access == null || access.isEmpty) {
      throw const FormatException('Access token response icinde bulunamadi.');
    }
    return AuthTokens(
      access: access,
      refresh: ParseUtils.firstString(map, ['refresh', 'refresh_token']),
    );
  }
}
