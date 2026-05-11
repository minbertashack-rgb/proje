import '../../../core/utils/parse_utils.dart';

class ReelCard {
  const ReelCard({
    required this.cardNo,
    required this.title,
    required this.summary,
    required this.example,
    required this.question,
    required this.answer,
    required this.source,
  });

  final int cardNo;
  final String title;
  final List<String> summary;
  final String example;
  final String question;
  final String answer;
  final String source;

  factory ReelCard.fromDynamic(dynamic value) {
    final json = ParseUtils.asMap(value);
    return ReelCard(
      cardNo: ParseUtils.intValue(json['card_no']),
      title: ParseUtils.firstString(json, ['title', 'baslik']) ?? '',
      summary: ParseUtils.stringList(json['summary'] ?? json['ozet']),
      example: ParseUtils.firstString(json, ['example', 'ornek']) ?? '',
      question: ParseUtils.firstString(json, ['question', 'soru']) ?? '',
      answer: ParseUtils.firstString(json, ['answer', 'cevap']) ?? '',
      source: ParseUtils.firstString(json, ['source', 'kaynak']) ?? 'fallback',
    );
  }
}

class ReelsPayload {
  const ReelsPayload({this.enabled = true, this.cards = const []});

  final bool enabled;
  final List<ReelCard> cards;

  factory ReelsPayload.fromDynamic(dynamic value) {
    final json = ParseUtils.asMap(value);
    return ReelsPayload(
      enabled: json['enabled'] is bool ? json['enabled'] as bool : true,
      cards: ParseUtils.asList(json['cards'])
          .map(ReelCard.fromDynamic)
          .where((card) => card.title.isNotEmpty || card.summary.isNotEmpty)
          .toList(growable: false),
    );
  }
}
