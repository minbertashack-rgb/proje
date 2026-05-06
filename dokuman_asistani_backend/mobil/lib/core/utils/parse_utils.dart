class ParseUtils {
  ParseUtils._();

  static Map<String, dynamic> asMap(dynamic value) {
    if (value is Map<String, dynamic>) return value;
    if (value is Map) return Map<String, dynamic>.from(value);
    return const {};
  }

  static Map<String, dynamic> nestedMap(dynamic value) {
    final map = asMap(value);
    for (final key in const [
      'data',
      'payload',
      'result',
      'results',
      'item',
      'document',
      'dokuman',
      'response',
    ]) {
      final nested = map[key];
      if (nested is Map) return asMap(nested);
    }
    return map;
  }

  static List<dynamic> asList(dynamic value, {bool includeSingleMap = true}) {
    if (value is List) return value;
    if (value is Map) {
      final map = asMap(value);
      for (final key in const [
        'results',
        'items',
        'payload',
        'data',
        'parcalar',
        'parts',
        'kanitlar',
        'evidence',
        'snippets',
        'sources',
      ]) {
        final nested = map[key];
        if (nested is List) return nested;
      }
      if (includeSingleMap && map.isNotEmpty) return [map];
    }
    final single = string(value);
    if (single != null) return [single];
    return const [];
  }

  static String? string(dynamic value) {
    if (value == null) return null;
    final text = value.toString().trim();
    if (text.isEmpty || text == 'null') return null;
    return text;
  }

  static String? firstString(Map<String, dynamic> map, List<String> keys) {
    for (final key in keys) {
      final value = string(map[key]);
      if (value != null) return value;
    }
    return null;
  }

  static int intValue(dynamic value, {int fallback = 0}) {
    if (value is int) return value;
    return int.tryParse('${value ?? ''}') ?? fallback;
  }

  static int? optionalInt(dynamic value) {
    if (value == null) return null;
    if (value is int) return value;
    return int.tryParse('$value');
  }

  static double doubleValue(dynamic value, {double fallback = 0}) {
    if (value is num) return value.toDouble();
    return double.tryParse('${value ?? ''}') ?? fallback;
  }

  static List<String> stringList(dynamic value) {
    final raw = asList(value);

    return raw
        .map((item) {
          if (item is Map) {
            final map = asMap(item);
            return firstString(map, [
                  'terim',
                  'term',
                  'baslik',
                  'title',
                  'soru',
                  'question',
                  'text',
                  'metin',
                  'aciklama',
                  'description',
                ]) ??
                map.values.map((value) => value.toString()).join(' - ');
          }
          return item.toString();
        })
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty && item != 'null')
        .toList();
  }
}
