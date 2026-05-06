import '../../../core/utils/parse_utils.dart';

class ConceptItem {
  const ConceptItem({
    required this.id,
    required this.term,
    this.definition = '',
    this.example = '',
    this.sourcePartId,
    this.path = '',
    this.confidence = 0,
  });

  final String id;
  final String term;
  final String definition;
  final String example;
  final int? sourcePartId;
  final String path;
  final double confidence;

  factory ConceptItem.fromDynamic(dynamic value) {
    final map = ParseUtils.asMap(value);
    final term =
        ParseUtils.firstString(map, ['term', 'terim', 'kavram', 'title']) ?? '';
    final id =
        ParseUtils.firstString(map, ['id']) ??
        term.toLowerCase().replaceAll(RegExp(r'\s+'), '-');
    return ConceptItem(
      id: id,
      term: term,
      definition:
          ParseUtils.firstString(map, [
            'definition',
            'tanim',
            'kisa_tanim',
            'description',
            'aciklama',
          ]) ??
          '',
      example: ParseUtils.firstString(map, ['example', 'ornek']) ?? '',
      sourcePartId: ParseUtils.optionalInt(
        map['source_part_id'] ?? map['parca_id'] ?? map['part_id'],
      ),
      path: ParseUtils.firstString(map, ['path', 'adres']) ?? '',
      confidence: ParseUtils.doubleValue(map['confidence']),
    );
  }

  bool get isEmpty => term.trim().isEmpty;
}

class ConceptRelation {
  const ConceptRelation({
    required this.source,
    required this.target,
    this.relation = '',
    this.reason = '',
  });

  final String source;
  final String target;
  final String relation;
  final String reason;

  factory ConceptRelation.fromDynamic(dynamic value) {
    final map = ParseUtils.asMap(value);
    return ConceptRelation(
      source: ParseUtils.firstString(map, ['source', 'kaynak']) ?? '',
      target: ParseUtils.firstString(map, ['target', 'hedef']) ?? '',
      relation: ParseUtils.firstString(map, ['relation', 'iliski']) ?? '',
      reason: ParseUtils.firstString(map, ['reason', 'gerekce']) ?? '',
    );
  }

  bool get isEmpty => source.trim().isEmpty || target.trim().isEmpty;
}

class ConceptMention {
  const ConceptMention({
    required this.partId,
    this.title = '',
    this.path = '',
    this.snippet = '',
  });

  final int partId;
  final String title;
  final String path;
  final String snippet;

  factory ConceptMention.fromDynamic(dynamic value) {
    final map = ParseUtils.asMap(value);
    return ConceptMention(
      partId: ParseUtils.intValue(map['part_id'] ?? map['parca_id']),
      title: ParseUtils.firstString(map, ['title', 'baslik']) ?? '',
      path: ParseUtils.firstString(map, ['path', 'adres']) ?? '',
      snippet: ParseUtils.firstString(map, ['snippet', 'metin', 'text']) ?? '',
    );
  }
}

class ConceptGraphResponse {
  const ConceptGraphResponse({
    this.enabled = true,
    this.concepts = const [],
    this.relations = const [],
    this.mentions = const [],
    this.concept,
  });

  final bool enabled;
  final List<ConceptItem> concepts;
  final List<ConceptRelation> relations;
  final List<ConceptMention> mentions;
  final ConceptItem? concept;

  factory ConceptGraphResponse.fromDynamic(dynamic value) {
    final map = ParseUtils.asMap(value);
    final concepts = ParseUtils.asList(map['concepts'] ?? map['kavramlar'])
        .map(ConceptItem.fromDynamic)
        .where((item) => !item.isEmpty)
        .toList(growable: false);
    final relations = ParseUtils.asList(map['relations'] ?? map['iliski'])
        .map(ConceptRelation.fromDynamic)
        .where((item) => !item.isEmpty)
        .toList(growable: false);
    final mentions = ParseUtils.asList(map['mentions'] ?? map['gecisler'])
        .map(ConceptMention.fromDynamic)
        .where((item) => item.partId > 0)
        .toList(growable: false);
    final conceptMap = ParseUtils.asMap(map['concept']);
    return ConceptGraphResponse(
      enabled: map['enabled'] is bool ? map['enabled'] as bool : true,
      concepts: concepts,
      relations: relations,
      mentions: mentions,
      concept: conceptMap.isEmpty ? null : ConceptItem.fromDynamic(conceptMap),
    );
  }
}
