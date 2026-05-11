import '../../../core/utils/parse_utils.dart';

class ExportPayload {
  const ExportPayload({
    required this.type,
    this.enabled = true,
    this.title = '',
    this.data = const {},
  });

  final String type;
  final bool enabled;
  final String title;
  final Map<String, dynamic> data;

  factory ExportPayload.fromDynamic(String type, dynamic value) {
    final json = ParseUtils.asMap(value);
    return ExportPayload(
      type: type,
      enabled: json['enabled'] is bool ? json['enabled'] as bool : true,
      title: ParseUtils.firstString(json, ['title', 'baslik']) ?? '',
      data: json,
    );
  }

  List<String> stringList(String key) => ParseUtils.stringList(data[key]);
  List<Map<String, dynamic>> mapList(String key) => ParseUtils.asList(data[key])
      .map(ParseUtils.asMap)
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
  double doubleValue(String key) => ParseUtils.doubleValue(data[key]);
}

class PremiumUiPayload {
  const PremiumUiPayload({
    this.clarity = 0,
    this.examples = 0,
    this.testReadiness = 0,
    this.teleports = const [],
    this.spotlight = const [],
  });

  final double clarity;
  final double examples;
  final double testReadiness;
  final List<Map<String, dynamic>> teleports;
  final List<Map<String, dynamic>> spotlight;

  factory PremiumUiPayload.fromDynamic(dynamic value) {
    final json = ParseUtils.asMap(value);
    final spotlightPayload = ParseUtils.asMap(json['spotlight_payload']);
    final badges = ParseUtils.asList(json['cevap_bilekligi_gostergeleri'])
        .map(ParseUtils.asMap)
        .toList(growable: false);
    double badge(String code, String fallbackKey) {
      for (final item in badges) {
        if ((item['kod'] ?? '').toString() == code) {
          return ParseUtils.doubleValue(item['deger']);
        }
      }
      final direct = ParseUtils.doubleValue(json[fallbackKey], fallback: -1);
      if (direct >= 0) return direct;
      final spotlight = ParseUtils.doubleValue(spotlightPayload[fallbackKey], fallback: -1);
      return spotlight >= 0 ? spotlight : 0;
    }

    return PremiumUiPayload(
      clarity: badge('netlik', 'clarity'),
      examples: badge('ornek', 'examples'),
      testReadiness: badge('test', 'test_readiness'),
      teleports: ParseUtils.asList(json['teleports'] ?? json['teleport_links'])
          .map(ParseUtils.asMap)
          .toList(growable: false),
      spotlight: ParseUtils.asList(json['spotlight'])
          .map(ParseUtils.asMap)
          .toList(growable: false),
    );
  }
}
