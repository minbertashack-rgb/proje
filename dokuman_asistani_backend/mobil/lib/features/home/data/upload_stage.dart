enum UploadStage { idle, selected, uploading, waitingResponse, success, error }

extension UploadStageX on UploadStage {
  String get label {
    return switch (this) {
      UploadStage.idle => 'Dosya bekleniyor',
      UploadStage.selected => 'Dosya seçildi',
      UploadStage.uploading => 'Yükleniyor',
      UploadStage.waitingResponse => 'Yanıt bekleniyor',
      UploadStage.success => 'Başarılı',
      UploadStage.error => 'Hata',
    };
  }
}
