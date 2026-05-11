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
  static const gameProfileEndpoint = '/api/dokuman-asistani/oyun/profil/';
  static const gameRewardsEndpoint = '/api/dokuman-asistani/oyun/oduller/';
  static const weeklyProgressEndpoint =
      '/api/dokuman-asistani/oyun/haftalik-ilerleme/';

  static String partsEndpoint(int documentId) =>
      '/api/dokuman-asistani/dokumanlar/$documentId/parcalar/';

  static String excelSummaryEndpoint(int documentId) =>
      '/api/dokuman-asistani/dokumanlar/$documentId/excel/ozet/';

  static String excelFormulaEndpoint(int documentId) =>
      '/api/dokuman-asistani/dokumanlar/$documentId/excel/formul-acikla/';

  static String excelQuestionEndpoint(int documentId) =>
      '/api/dokuman-asistani/dokumanlar/$documentId/excel/sor/';

  static String explainEndpoint(int partId) =>
      '/api/dokuman-asistani/parcalar/$partId/anlamadim-v2/';

  static String remixEndpoint(int partId) =>
      '/api/dokuman-asistani/parcalar/$partId/remix/';

  static String directorsCutEndpoint(int partId) =>
      '/api/dokuman-asistani/parcalar/$partId/directors-cut/';

  static String selfCheckEndpoint(int partId) =>
      '/api/dokuman-asistani/parcalar/$partId/kendi-cumlenle-anlat/';

  static String quizRouletteEndpoint(int partId) =>
      '/api/dokuman-asistani/parcalar/$partId/quiz-roulette/';

  static String escapeRoomEndpoint(int partId) =>
      '/api/dokuman-asistani/parcalar/$partId/escape-room/';

  static String speedrunEndpoint(int partId) =>
      '/api/dokuman-asistani/parcalar/$partId/speedrun/';

  static String partReelsEndpoint(int partId) =>
      '/api/dokuman-asistani/parcalar/$partId/reels/';

  static String documentReelsEndpoint(int documentId) =>
      '/api/dokuman-asistani/dokumanlar/$documentId/reels/';

  static String exportCheatsheetEndpoint(int documentId) =>
      '/api/dokuman-asistani/dokumanlar/$documentId/export/cheatsheet/';

  static String exportStudySummaryEndpoint(int documentId) =>
      '/api/dokuman-asistani/dokumanlar/$documentId/export/study-summary/';

  static String exportPresentationPlanEndpoint(int documentId) =>
      '/api/dokuman-asistani/dokumanlar/$documentId/export/presentation-plan/';

  static String exportReadmeEndpoint(int documentId) =>
      '/api/dokuman-asistani/dokumanlar/$documentId/export/readme/';

  static String exportReadinessEndpoint(int documentId) =>
      '/api/dokuman-asistani/dokumanlar/$documentId/export/readiness/';

  static String premiumPayloadEndpoint(int documentId) =>
      '/api/dokuman-asistani/dokumanlar/$documentId/premium-payload/';

  static String partConceptsEndpoint(int partId) =>
      '/api/dokuman-asistani/parcalar/$partId/kavramlar/';

  static String partNotesEndpoint(int partId) =>
      '/api/dokuman-asistani/parcalar/$partId/notlar/';

  static const myNotesEndpoint = '/api/dokuman-asistani/notlarim/';

  static String notePortalEndpoint(int noteId) =>
      '/api/dokuman-asistani/notlar/$noteId/portal/';

  static String documentConceptsEndpoint(int documentId) =>
      '/api/dokuman-asistani/dokumanlar/$documentId/kavramlar/';

  static String searchConceptEndpoint(int documentId, String query) {
    final encoded = Uri.encodeQueryComponent(query);
    return '/api/dokuman-asistani/dokumanlar/$documentId/kavramlar/ara/?q=$encoded';
  }

  static String conceptFusionEndpoint(int documentId) =>
      '/api/dokuman-asistani/dokumanlar/$documentId/concept-fusion/';

  static String bossFightEndpoint(int partId) =>
      '/api/dokuman-asistani/parcalar/$partId/boss-fight/';

  static String bossFightAnswerEndpoint(int partId) =>
      '/api/dokuman-asistani/parcalar/$partId/boss-fight/cevapla/';

  static String bossRushEndpoint(int documentId) =>
      '/api/dokuman-asistani/dokumanlar/$documentId/boss-rush/';
}
