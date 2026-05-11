import '../../../core/utils/parse_utils.dart';

class ExcelSummary {
  const ExcelSummary({this.enabled = true, this.sheets = const []});

  final bool enabled;
  final List<ExcelSheetSummary> sheets;

  factory ExcelSummary.fromJson(Map<String, dynamic> json) {
    final sheets = ParseUtils.asList(json['sheets'])
        .whereType<Map>()
        .map((item) => ExcelSheetSummary.fromJson(Map<String, dynamic>.from(item)))
        .toList(growable: false);
    return ExcelSummary(enabled: json['enabled'] != false, sheets: sheets);
  }
}

class ExcelSheetSummary {
  const ExcelSheetSummary({
    required this.name,
    required this.rowCount,
    required this.columnCount,
    this.columns = const [],
    this.previewRows = const [],
    this.summary = '',
  });

  final String name;
  final int rowCount;
  final int columnCount;
  final List<String> columns;
  final List<List<Object?>> previewRows;
  final String summary;

  factory ExcelSheetSummary.fromJson(Map<String, dynamic> json) {
    return ExcelSheetSummary(
      name: ParseUtils.string(json['name']) ?? '',
      rowCount: ParseUtils.intValue(json['row_count']),
      columnCount: ParseUtils.intValue(json['column_count']),
      columns: ParseUtils.asList(json['columns']).map((item) => '$item').toList(growable: false),
      previewRows: ParseUtils.asList(json['preview_rows'])
          .map((row) => ParseUtils.asList(row).toList(growable: false))
          .toList(growable: false),
      summary: ParseUtils.string(json['summary']) ?? '',
    );
  }
}

class ExcelFormulaExplanation {
  const ExcelFormulaExplanation({
    required this.formula,
    this.steps = const [],
    this.plainExplanation = '',
  });

  final String formula;
  final List<String> steps;
  final String plainExplanation;

  factory ExcelFormulaExplanation.fromJson(Map<String, dynamic> json) {
    return ExcelFormulaExplanation(
      formula: ParseUtils.string(json['formula']) ?? '',
      steps: ParseUtils.asList(json['steps']).map((item) => '$item').toList(growable: false),
      plainExplanation: ParseUtils.string(json['plain_explanation']) ?? '',
    );
  }
}

class ExcelQuestionAnswer {
  const ExcelQuestionAnswer({
    required this.answer,
    this.evidenceRows = const [],
    this.source = '',
  });

  final String answer;
  final List<Map<String, dynamic>> evidenceRows;
  final String source;

  factory ExcelQuestionAnswer.fromJson(Map<String, dynamic> json) {
    return ExcelQuestionAnswer(
      answer: ParseUtils.string(json['answer']) ?? '',
      evidenceRows: ParseUtils.asList(json['evidence_rows'])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList(growable: false),
      source: ParseUtils.string(json['source']) ?? '',
    );
  }
}
