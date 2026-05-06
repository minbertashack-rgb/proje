import '../../../core/utils/parse_utils.dart';

class DirectorsCutResponse {
  const DirectorsCutResponse({
    this.enabled = true,
    required this.cutType,
    required this.title,
    required this.summary,
    this.sections = const [],
    this.quiz = const [],
    this.source = '',
    this.warning = '',
  });

  final bool enabled;
  final String cutType;
  final String title;
  final String summary;
  final List<DirectorsCutSection> sections;
  final List<DirectorsCutQuizItem> quiz;
  final String source;
  final String warning;

  factory DirectorsCutResponse.fromDynamic(dynamic value) {
    final payload = ParseUtils.asMap(value);
    return DirectorsCutResponse(
      enabled: payload['enabled'] is bool ? payload['enabled'] as bool : true,
      cutType: ParseUtils.string(payload['cut_type']) ?? '',
      title: ParseUtils.string(payload['title']) ?? '',
      summary: ParseUtils.string(payload['summary']) ?? '',
      sections: DirectorsCutSection.listFrom(payload['sections']),
      quiz: DirectorsCutQuizItem.listFrom(payload['quiz']),
      source: ParseUtils.string(payload['source']) ?? '',
      warning: ParseUtils.string(payload['warning']) ?? '',
    );
  }

  bool get isEmpty =>
      title.trim().isEmpty &&
      summary.trim().isEmpty &&
      sections.isEmpty &&
      quiz.isEmpty;
}

class DirectorsCutSection {
  const DirectorsCutSection({required this.title, required this.items});

  final String title;
  final List<String> items;

  static List<DirectorsCutSection> listFrom(dynamic value) {
    return ParseUtils.asList(value, includeSingleMap: false)
        .map(ParseUtils.asMap)
        .map(
          (section) => DirectorsCutSection(
            title: ParseUtils.string(section['title']) ?? '',
            items: ParseUtils.stringList(section['items']),
          ),
        )
        .where(
          (section) =>
              section.title.trim().isNotEmpty || section.items.isNotEmpty,
        )
        .toList(growable: false);
  }
}

class DirectorsCutQuizItem {
  const DirectorsCutQuizItem({required this.question, required this.answer});

  final String question;
  final String answer;

  static List<DirectorsCutQuizItem> listFrom(dynamic value) {
    return ParseUtils.asList(value, includeSingleMap: false)
        .map(ParseUtils.asMap)
        .map(
          (item) => DirectorsCutQuizItem(
            question: ParseUtils.string(item['question']) ?? '',
            answer: ParseUtils.string(item['answer']) ?? '',
          ),
        )
        .where(
          (item) =>
              item.question.trim().isNotEmpty || item.answer.trim().isNotEmpty,
        )
        .toList(growable: false);
  }
}
