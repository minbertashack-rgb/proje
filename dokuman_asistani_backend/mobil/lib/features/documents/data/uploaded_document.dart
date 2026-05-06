import '../../../core/utils/parse_utils.dart';

class UploadedDocument {
  const UploadedDocument({required this.id, required this.title, this.status});

  final int id;
  final String title;
  final String? status;

  factory UploadedDocument.fromJson(Map<String, dynamic> json) {
    return UploadedDocument.fromMap(json);
  }

  factory UploadedDocument.fromMap(Map<String, dynamic> json) {
    final map = ParseUtils.nestedMap(json);
    final rawId =
        map['id'] ??
        map['dokuman_id'] ??
        map['document_id'] ??
        map['pk'] ??
        map['uuid'];
    return UploadedDocument(
      id: ParseUtils.intValue(rawId),
      title:
          ParseUtils.firstString(map, [
            'baslik',
            'title',
            'name',
            'filename',
            'file_name',
            'ad',
          ]) ??
          'Yuklenen dokuman',
      status: ParseUtils.firstString(map, ['durum', 'status', 'state']),
    );
  }
}
