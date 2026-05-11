import '../core/constants/app_constants.dart';
import '../core/network/api_client.dart';
import '../core/storage/token_storage.dart';
import '../core/utils/parse_utils.dart';
import '../features/notes/data/smart_note.dart';

class NoteService {
  NoteService({ApiClient? apiClient, TokenStorage? tokenStorage})
    : _apiClient =
          apiClient ?? ApiClient(tokenStorage: tokenStorage ?? TokenStorage());

  final ApiClient _apiClient;

  Future<List<SmartNote>> getPartNotes(int partId) async {
    final response = await _apiClient.getWithMeta(
      AppConstants.partNotesEndpoint(partId),
    );
    return _parseNotes(response.body);
  }

  Future<List<SmartNote>> getMyNotes() async {
    final response = await _apiClient.getWithMeta(AppConstants.myNotesEndpoint);
    return _parseNotes(response.body);
  }

  Future<SmartNote> createNote({
    required int partId,
    required String title,
    required String body,
    String conceptTerm = '',
  }) async {
    final response = await _apiClient.postWithMeta(
      AppConstants.partNotesEndpoint(partId),
      body: {
        'baslik': title,
        'metin': body,
        if (conceptTerm.trim().isNotEmpty) 'concept_term': conceptTerm.trim(),
      },
    );
    return SmartNote.fromJson(ParseUtils.asMap(response.body));
  }

  Future<List<PortalLink>> getPortalLinks(int noteId) async {
    final response = await _apiClient.getWithMeta(
      AppConstants.notePortalEndpoint(noteId),
    );
    final map = ParseUtils.asMap(response.body);
    final raw = map['portal_links'] ?? map['oneriler'] ?? [];
    return ParseUtils.asList(raw)
        .whereType<Map>()
        .map((item) => PortalLink.fromJson(Map<String, dynamic>.from(item)))
        .where((item) => item.targetPartId > 0)
        .toList();
  }

  List<SmartNote> _parseNotes(dynamic body) {
    final raw = body is List
        ? body
        : body is Map<String, dynamic>
        ? body['notlar'] ??
              body['results'] ??
              body['items'] ??
              body['data'] ??
              []
        : [];
    return ParseUtils.asList(raw)
        .whereType<Map>()
        .map((item) => SmartNote.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }
}
