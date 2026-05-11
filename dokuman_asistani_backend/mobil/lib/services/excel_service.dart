import '../core/constants/app_constants.dart';
import '../core/network/api_client.dart';
import '../core/storage/token_storage.dart';
import '../core/utils/parse_utils.dart';
import '../features/excel/data/excel_models.dart';

class ExcelService {
  ExcelService({ApiClient? apiClient, TokenStorage? tokenStorage})
    : _apiClient = apiClient ?? ApiClient(tokenStorage: tokenStorage ?? TokenStorage());

  final ApiClient _apiClient;

  Future<ExcelSummary> fetchExcelSummary(int documentId) async {
    final response = await _apiClient.getWithMeta(AppConstants.excelSummaryEndpoint(documentId));
    return ExcelSummary.fromJson(ParseUtils.asMap(response.body));
  }

  Future<ExcelFormulaExplanation> explainFormula({
    required int documentId,
    required String formula,
  }) async {
    final response = await _apiClient.postWithMeta(
      AppConstants.excelFormulaEndpoint(documentId),
      body: {'formula': formula.trim()},
    );
    return ExcelFormulaExplanation.fromJson(ParseUtils.asMap(response.body));
  }

  Future<ExcelQuestionAnswer> askExcelQuestion({
    required int documentId,
    required String question,
  }) async {
    final response = await _apiClient.postWithMeta(
      AppConstants.excelQuestionEndpoint(documentId),
      body: {'question': question.trim()},
    );
    return ExcelQuestionAnswer.fromJson(ParseUtils.asMap(response.body));
  }
}
