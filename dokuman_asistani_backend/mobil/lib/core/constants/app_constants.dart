class AppConstants {
  AppConstants._();

  static const appName = 'DocVerse';
  static const appSubtitle = 'TUBITAK Dokuman Asistani';

  static const loginEndpoint = '/api/kimlik/token/';
  static const refreshEndpoint = '/api/kimlik/token/refresh/';
  static const registerEndpoint = '/api/kimlik/kayit/';
  static const uploadEndpoint = '/api/dokuman-asistani/dokumanlar/yukle/';
  static const evidenceAnswerEndpoint =
      '/api/dokuman-asistani/ai2/kanitli-cevap/';
  static const pingEndpoint = '/api/dokuman-asistani/ping/';
  static const preferencesEndpoint = '/api/dokuman-asistani/tercihlerim/';

  static String partsEndpoint(int documentId) =>
      '/api/dokuman-asistani/dokumanlar/$documentId/parcalar/';

  static String explainEndpoint(int partId) =>
      '/api/dokuman-asistani/parcalar/$partId/anlamadim-v2/';

  static String remixEndpoint(int partId) =>
      '/api/dokuman-asistani/parcalar/$partId/remix/';

  static String directorsCutEndpoint(int partId) =>
      '/api/dokuman-asistani/parcalar/$partId/directors-cut/';

  static String partConceptsEndpoint(int partId) =>
      '/api/dokuman-asistani/parcalar/$partId/kavramlar/';

  static String documentConceptsEndpoint(int documentId) =>
      '/api/dokuman-asistani/dokumanlar/$documentId/kavramlar/';

  static String searchConceptEndpoint(int documentId, String query) {
    final encoded = Uri.encodeQueryComponent(query);
    return '/api/dokuman-asistani/dokumanlar/$documentId/kavramlar/ara/?q=$encoded';
  }
}
