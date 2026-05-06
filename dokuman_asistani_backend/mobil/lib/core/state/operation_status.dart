enum OperationStatus { idle, loading, success, error, empty }

extension OperationStatusX on OperationStatus {
  bool get isLoading => this == OperationStatus.loading;
}
