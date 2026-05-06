import 'package:flutter/foundation.dart';

import '../core/constants/app_constants.dart';
import '../core/network/api_client.dart';
import '../core/network/api_exception.dart';
import '../core/storage/token_storage.dart';
import '../core/utils/parse_utils.dart';
import '../features/documents/data/document_part.dart';
import '../features/documents/data/uploaded_document.dart';

class DocumentService {
  DocumentService({ApiClient? apiClient, TokenStorage? tokenStorage})
    : this._(
        apiClient: apiClient,
        tokenStorage: tokenStorage ?? TokenStorage(),
      );

  DocumentService._({ApiClient? apiClient, required TokenStorage tokenStorage})
    : _apiClient = apiClient ?? ApiClient(tokenStorage: tokenStorage),
      _tokenStorage = tokenStorage;

  final ApiClient _apiClient;
  final TokenStorage _tokenStorage;

  Future<bool> ping() async {
    await _apiClient.get(AppConstants.pingEndpoint);
    return true;
  }

  Future<UploadedDocument> uploadDocument(String filePath) async {
    if (kDebugMode) {
      final hasToken = await _tokenStorage.hasValidAccessToken();
      debugPrint('UPLOAD request started hasToken=$hasToken');
    }
    late final ApiResponse<dynamic> response;
    try {
      response = await _apiClient.multipartWithMeta(
        AppConstants.uploadEndpoint,
        filePath: filePath,
      );
    } on ApiException catch (error) {
      if (kDebugMode) {
        final status = error.statusCode?.toString() ?? 'error';
        debugPrint('UPLOAD response status=$status');
      }
      rethrow;
    }
    if (kDebugMode) {
      debugPrint('UPLOAD response status=${response.statusCode}');
    }
    final map = ParseUtils.asMap(response.body);
    final document = ParseUtils.asMap(
      map['dokuman'] ?? map['document'] ?? map['data'] ?? map,
    );
    return UploadedDocument.fromJson(document);
  }

  Future<List<DocumentPart>> getDocumentParts(int documentId) async {
    if (kDebugMode) {
      final hasToken = await _tokenStorage.hasValidAccessToken();
      debugPrint(
        'PARTS request started hasToken=$hasToken documentId=$documentId',
      );
    }
    late final ApiResponse<dynamic> response;
    try {
      response = await _apiClient.getWithMeta(
        AppConstants.partsEndpoint(documentId),
      );
    } on ApiException catch (error) {
      if (kDebugMode) {
        final status = error.statusCode?.toString() ?? 'error';
        debugPrint('PARTS response status=$status');
      }
      rethrow;
    }
    if (kDebugMode) {
      debugPrint('PARTS response status=${response.statusCode}');
    }
    final body = response.body;
    final rawList = body is List
        ? body
        : body is Map<String, dynamic>
        ? body['results'] ??
              body['items'] ??
              body['parcalar'] ??
              body['parts'] ??
              body['data'] ??
              []
        : [];

    return ParseUtils.asList(rawList)
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .map(DocumentPart.fromJson)
        .toList();
  }
}
