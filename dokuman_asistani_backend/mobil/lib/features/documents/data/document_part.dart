import '../../../core/utils/parse_utils.dart';

class DocumentPart {
  const DocumentPart({
    required this.id,
    required this.order,
    required this.text,
    this.title,
    this.address,
    this.difficultyScore,
    this.difficultyLabel = 'orta',
    this.difficultyReasons = const [],
  });

  final int id;
  final int order;
  final String text;
  final String? title;
  final String? address;
  final double? difficultyScore;
  final String difficultyLabel;
  final List<String> difficultyReasons;

  factory DocumentPart.fromJson(Map<String, dynamic> json) {
    return DocumentPart.fromMap(json);
  }

  factory DocumentPart.fromMap(Map<String, dynamic> json) {
    final map = ParseUtils.nestedMap(json);
    final rawId = map['id'] ?? map['parca_id'] ?? map['part_id'] ?? map['pk'];
    final rawOrder =
        map['sira'] ??
        map['order'] ??
        map['index'] ??
        map['chunk_index'] ??
        rawId;

    return DocumentPart(
      id: ParseUtils.intValue(rawId),
      order: ParseUtils.intValue(rawOrder),
      title: ParseUtils.firstString(map, ['baslik', 'title', 'heading']),
      address: ParseUtils.firstString(map, ['adres', 'path', 'address']),
      difficultyScore: _doubleValue(
        map['difficulty_score'] ?? map['zorluk_skoru'],
      ),
      difficultyLabel:
          ParseUtils.firstString(map, [
            'difficulty_label',
            'zorluk',
            'difficulty',
          ]) ??
          'orta',
      difficultyReasons: ParseUtils.stringList(
        map['difficulty_reasons'] ?? map['zorluk_nedenleri'],
      ),
      text:
          ParseUtils.firstString(map, [
            'metin',
            'text',
            'icerik',
            'content',
            'chunk',
            'body',
          ]) ??
          '',
    );
  }

  static double? _doubleValue(dynamic value) {
    if (value == null) return null;
    if (value is num) return value.toDouble();
    return double.tryParse(value.toString());
  }
}
