import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class AppLanguage {
  const AppLanguage({
    required this.code,
    required this.nativeName,
    required this.englishName,
  });

  final String code;
  final String nativeName;
  final String englishName;

  String get label =>
      nativeName == englishName ? nativeName : '$nativeName · $englishName';
}

const supportedLanguages = <AppLanguage>[
  AppLanguage(code: 'tr', nativeName: 'Türkçe', englishName: 'Turkish'),
  AppLanguage(code: 'en', nativeName: 'English', englishName: 'English'),
  AppLanguage(code: 'fr', nativeName: 'Français', englishName: 'French'),
  AppLanguage(code: 'de', nativeName: 'Deutsch', englishName: 'German'),
  AppLanguage(code: 'es', nativeName: 'Español', englishName: 'Spanish'),
  AppLanguage(code: 'ar', nativeName: 'العربية', englishName: 'Arabic'),
  AppLanguage(code: 'ru', nativeName: 'Русский', englishName: 'Russian'),
  AppLanguage(code: 'ja', nativeName: '日本語', englishName: 'Japanese'),
  AppLanguage(code: 'ko', nativeName: '한국어', englishName: 'Korean'),
  AppLanguage(code: 'zh', nativeName: '中文', englishName: 'Chinese'),
  AppLanguage(code: 'it', nativeName: 'Italiano', englishName: 'Italian'),
  AppLanguage(code: 'pt', nativeName: 'Português', englishName: 'Portuguese'),
  AppLanguage(code: 'sv', nativeName: 'Svenska', englishName: 'Swedish'),
  AppLanguage(code: 'nl', nativeName: 'Nederlands', englishName: 'Dutch'),
  AppLanguage(code: 'pl', nativeName: 'Polski', englishName: 'Polish'),
  AppLanguage(code: 'fa', nativeName: 'فارسی', englishName: 'Persian'),
  AppLanguage(code: 'ur', nativeName: 'اردو', englishName: 'Urdu'),
  AppLanguage(code: 'uk', nativeName: 'Українська', englishName: 'Ukrainian'),
  AppLanguage(
    code: 'az',
    nativeName: 'Azərbaycanca',
    englishName: 'Azerbaijani',
  ),
  AppLanguage(code: 'hi', nativeName: 'हिन्दी', englishName: 'Hindi'),
  AppLanguage(code: 'bn', nativeName: 'বাংলা', englishName: 'Bangla'),
  AppLanguage(code: 'id', nativeName: 'Indonesia', englishName: 'Indonesian'),
  AppLanguage(code: 'ms', nativeName: 'Melayu', englishName: 'Malay'),
  AppLanguage(code: 'vi', nativeName: 'Tiếng Việt', englishName: 'Vietnamese'),
  AppLanguage(code: 'th', nativeName: 'ไทย', englishName: 'Thai'),
  AppLanguage(code: 'ro', nativeName: 'Română', englishName: 'Romanian'),
  AppLanguage(code: 'el', nativeName: 'Ελληνικά', englishName: 'Greek'),
  AppLanguage(code: 'cs', nativeName: 'Čeština', englishName: 'Czech'),
  AppLanguage(code: 'hu', nativeName: 'Magyar', englishName: 'Hungarian'),
  AppLanguage(code: 'fi', nativeName: 'Suomi', englishName: 'Finnish'),
  AppLanguage(code: 'da', nativeName: 'Dansk', englishName: 'Danish'),
  AppLanguage(code: 'no', nativeName: 'Norsk', englishName: 'Norwegian'),
  AppLanguage(code: 'he', nativeName: 'עברית', englishName: 'Hebrew'),
];

class AppLanguageController extends ValueNotifier<String> {
  AppLanguageController({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage(),
      super(_defaultDeviceLanguage());

  static const _storageKey = 'docverse_selected_language';

  final FlutterSecureStorage _storage;

  static String normalize(String? value) {
    final raw = (value ?? '').trim().toLowerCase();
    if (raw.isEmpty) return 'tr';
    final first = raw.split(',').first.split(';').first.trim();
    final code = first.replaceAll('_', '-').split('-').first;
    return supportedLanguages.any((item) => item.code == code) ? code : 'tr';
  }

  static String _defaultDeviceLanguage() {
    final device = PlatformDispatcher.instance.locale.languageCode;
    return normalize(device);
  }

  AppLanguage get selectedLanguage => supportedLanguages.firstWhere(
    (item) => item.code == value,
    orElse: () => supportedLanguages.first,
  );

  Future<void> load() async {
    final stored = await _storage.read(key: _storageKey);
    value = normalize(
      stored ?? PlatformDispatcher.instance.locale.languageCode,
    );
  }

  Future<void> setLanguage(String code) async {
    final normalized = normalize(code);
    value = normalized;
    await _storage.write(key: _storageKey, value: normalized);
  }
}

final appLanguageController = AppLanguageController();
