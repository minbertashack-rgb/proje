import 'package:flutter/widgets.dart';

import 'app_language.dart';
import 'messages.dart';

class AppLocalizer {
  const AppLocalizer(this.languageCode);

  final String languageCode;

  static final fullUiSupportedLanguages = supportedLanguages
      .map((language) => language.code)
      .toSet();

  static const rtlLanguages = <String>{'ar', 'he', 'fa', 'ur'};

  static AppLocalizer of(BuildContext context) {
    final scope = context
        .dependOnInheritedWidgetOfExactType<AppLanguageScope>();
    return AppLocalizer(scope?.languageCode ?? appLanguageController.value);
  }

  String t(String key) {
    final entry = appMessages[key];
    if (entry == null) return key;
    final normalized = AppLanguageController.normalize(languageCode);
    final uiLanguage = fullUiSupportedLanguages.contains(normalized)
        ? normalized
        : 'en';
    return entry[uiLanguage] ?? entry['en'] ?? entry['tr'] ?? key;
  }

  String tError(String errorCode) => t(errorCode);

  static TextDirection textDirectionFor(String? languageCode) {
    final normalized = AppLanguageController.normalize(languageCode);
    return rtlLanguages.contains(normalized)
        ? TextDirection.rtl
        : TextDirection.ltr;
  }

  static TextDirection textDirectionOf(BuildContext context) {
    final scope = context
        .dependOnInheritedWidgetOfExactType<AppLanguageScope>();
    return textDirectionFor(scope?.languageCode ?? appLanguageController.value);
  }

  static String messageForErrorCode(String? errorCode, {String? lang}) {
    final code = (errorCode ?? '').trim();
    if (code.isEmpty) return '';
    final entry = appMessages[code];
    if (entry == null) return '';
    final normalized = AppLanguageController.normalize(
      lang ?? appLanguageController.value,
    );
    return entry[normalized] ?? entry['en'] ?? entry['tr'] ?? '';
  }

  static String errorCodeForRawMessage(String message) {
    final normalized = message.toLowerCase().replaceAll(RegExp(r'\s+'), ' ');
    for (final entry in rawErrorCodeMessages.entries) {
      if (normalized.contains(entry.key)) return entry.value;
    }
    return '';
  }

  static String localizeRawError(String message, {String? lang}) {
    final code = errorCodeForRawMessage(message);
    return messageForErrorCode(code, lang: lang);
  }
}

class AppLanguageScope extends InheritedNotifier<AppLanguageController> {
  const AppLanguageScope({
    super.key,
    required AppLanguageController controller,
    required super.child,
  }) : super(notifier: controller);

  String get languageCode => AppLanguageController.normalize(notifier?.value);
}
