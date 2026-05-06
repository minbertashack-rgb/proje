import '../../../core/utils/parse_utils.dart';

class EvidenceAnswer {
  const EvidenceAnswer({this.answer, this.evidence = const []});

  final String? answer;
  final List<EvidenceSnippet> evidence;

  factory EvidenceAnswer.fromJson(Map<String, dynamic> json) {
    return EvidenceAnswer.fromMap(json);
  }

  factory EvidenceAnswer.fromMap(Map<String, dynamic> json) {
    final payload = ParseUtils.nestedMap(json);
    return EvidenceAnswer(
      answer: ParseUtils.firstString(payload, [
        'cevap',
        'answer',
        'yanit',
        'text',
        'response',
      ]),
      evidence: _evidenceList(
        payload['snippets'] ??
            payload['evidence'] ??
            payload['kanitlar'] ??
            payload['kaynaklar'] ??
            payload['sources'],
      ),
    );
  }

  static List<EvidenceSnippet> _evidenceList(dynamic value) {
    return ParseUtils.asList(value)
        .map((item) {
          if (item is Map) {
            return EvidenceSnippet.fromJson(Map<String, dynamic>.from(item));
          }
          return EvidenceSnippet(text: item.toString());
        })
        .where((item) => item.text.trim().isNotEmpty && item.text != 'null')
        .toList();
  }
}

class EvidenceSnippet {
  const EvidenceSnippet({
    required this.text,
    this.source,
    this.path,
    this.page,
    this.partId,
    this.score,
  });

  final String text;
  final String? source;
  final String? path;
  final String? page;
  final String? partId;
  final String? score;

  String? get metaLabel {
    final parts = [
      if (source != null && source!.isNotEmpty) source,
      if (path != null && path!.isNotEmpty) path,
      if (page != null && page!.isNotEmpty) 'sayfa $page',
      if (partId != null && partId!.isNotEmpty) 'parça $partId',
      if (score != null && score!.isNotEmpty) 'skor $score',
    ];
    return parts.isEmpty ? null : parts.join(' / ');
  }

  factory EvidenceSnippet.fromJson(Map<String, dynamic> json) {
    final map = ParseUtils.nestedMap(json);
    return EvidenceSnippet(
      text:
          ParseUtils.firstString(map, [
            'snippet',
            'metin',
            'text',
            'icerik',
            'content',
            'quote',
          ]) ??
          '',
      source: ParseUtils.firstString(map, ['source', 'kaynak']),
      path: ParseUtils.firstString(map, ['path', 'adres', 'url']),
      page: ParseUtils.firstString(map, ['page', 'sayfa', 'page_number']),
      partId: ParseUtils.firstString(map, ['part_id', 'parca_id', 'chunk_id']),
      score: ParseUtils.firstString(map, ['score', 'skor']),
    );
  }
}
