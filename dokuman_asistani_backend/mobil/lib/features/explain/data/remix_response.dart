import '../../../core/utils/parse_utils.dart';

class RemixResponse {
  const RemixResponse({
    this.enabled = true,
    required this.style,
    required this.title,
    required this.content,
    this.items = const [],
    this.table = const [],
    this.source = '',
    this.warning = '',
  });

  final bool enabled;
  final String style;
  final String title;
  final String content;
  final List<String> items;
  final List<RemixTableRow> table;
  final String source;
  final String warning;

  factory RemixResponse.fromDynamic(dynamic value) {
    final payload = ParseUtils.asMap(value);
    return RemixResponse(
      enabled: payload['enabled'] is bool ? payload['enabled'] as bool : true,
      style: ParseUtils.string(payload['style']) ?? '',
      title: ParseUtils.string(payload['title']) ?? '',
      content: ParseUtils.string(payload['content']) ?? '',
      items: ParseUtils.stringList(payload['items']),
      table: RemixTableRow.listFrom(payload['table']),
      source: ParseUtils.string(payload['source']) ?? '',
      warning: ParseUtils.string(payload['warning']) ?? '',
    );
  }

  bool get isEmpty =>
      title.trim().isEmpty &&
      content.trim().isEmpty &&
      items.isEmpty &&
      table.isEmpty;
}

class RemixTableRow {
  const RemixTableRow({
    required this.left,
    required this.middle,
    required this.right,
  });

  final String left;
  final String middle;
  final String right;

  static List<RemixTableRow> listFrom(dynamic value) {
    return ParseUtils.asList(value, includeSingleMap: false)
        .map(ParseUtils.asMap)
        .map(
          (row) => RemixTableRow(
            left: ParseUtils.string(row['left']) ?? '',
            middle: ParseUtils.string(row['middle']) ?? '',
            right: ParseUtils.string(row['right']) ?? '',
          ),
        )
        .where(
          (row) =>
              row.left.trim().isNotEmpty ||
              row.middle.trim().isNotEmpty ||
              row.right.trim().isNotEmpty,
        )
        .toList(growable: false);
  }
}
