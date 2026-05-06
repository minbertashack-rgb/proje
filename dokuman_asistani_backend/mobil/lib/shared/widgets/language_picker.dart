import 'package:flutter/material.dart';

import '../../core/i18n/app_language.dart';
import '../../core/i18n/app_localizer.dart';

class LanguagePicker extends StatelessWidget {
  const LanguagePicker({super.key, this.compact = false});

  final bool compact;

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<String>(
      valueListenable: appLanguageController,
      builder: (context, selectedCode, _) {
        final selected = AppLanguageController.normalize(selectedCode);
        final localizer = AppLocalizer(selected);
        return DropdownButtonFormField<String>(
          initialValue: selected,
          isExpanded: true,
          decoration: InputDecoration(
            labelText: compact ? null : localizer.t('language'),
            prefixIcon: compact ? null : const Icon(Icons.language_rounded),
            contentPadding: compact
                ? const EdgeInsets.symmetric(horizontal: 12, vertical: 8)
                : null,
          ),
          items: supportedLanguages
              .map(
                (language) => DropdownMenuItem<String>(
                  value: language.code,
                  child: Text(language.label, overflow: TextOverflow.ellipsis),
                ),
              )
              .toList(),
          onChanged: (value) {
            if (value == null) return;
            appLanguageController.setLanguage(value);
          },
        );
      },
    );
  }
}
