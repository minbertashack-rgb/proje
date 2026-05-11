class SmartNote {
  const SmartNote({
    required this.id,
    required this.partId,
    required this.title,
    required this.body,
    this.conceptTerm = '',
    this.tags = const [],
  });

  final int id;
  final int? partId;
  final String title;
  final String body;
  final String conceptTerm;
  final List<String> tags;

  factory SmartNote.fromJson(Map<String, dynamic> json) {
    final rawTags = json['etiketler'];
    return SmartNote(
      id: _asInt(json['id']),
      partId: _nullableInt(json['parca_id'] ?? json['parca']),
      title: (json['baslik'] ?? '').toString(),
      body: (json['metin'] ?? json['icerik'] ?? '').toString(),
      conceptTerm: (json['concept_term'] ?? json['kavram'] ?? '').toString(),
      tags: rawTags is List
          ? rawTags.map((item) => '$item').toList()
          : const [],
    );
  }

  static int _asInt(dynamic value) => _nullableInt(value) ?? 0;

  static int? _nullableInt(dynamic value) {
    if (value is int) return value;
    return int.tryParse((value ?? '').toString());
  }
}

class PortalLink {
  const PortalLink({
    required this.targetPartId,
    required this.title,
    required this.path,
    required this.snippet,
    required this.reason,
  });

  final int targetPartId;
  final String title;
  final String path;
  final String snippet;
  final String reason;

  factory PortalLink.fromJson(Map<String, dynamic> json) {
    return PortalLink(
      targetPartId: SmartNote._asInt(
        json['target_part_id'] ?? json['parca_id'],
      ),
      title: (json['title'] ?? '').toString(),
      path: (json['path'] ?? json['adres'] ?? '').toString(),
      snippet: (json['snippet'] ?? '').toString(),
      reason: (json['reason'] ?? '').toString(),
    );
  }
}
