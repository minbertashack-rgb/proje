import 'package:flutter/material.dart';

import '../../../core/i18n/app_localizer.dart';
import '../../../shared/widgets/language_picker.dart';

class AppDrawer extends StatelessWidget {
  const AppDrawer({super.key, this.onLogout});

  final VoidCallback? onLogout;

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    final items = [
      (Icons.warning_amber_rounded, 'Zor Kisimlar'),
      (Icons.abc_rounded, 'Terim Yogun Alanlar'),
      (Icons.note_alt_outlined, 'Akilli Notlar'),
      (Icons.public_rounded, 'Portal Notlar'),
      (Icons.quiz_outlined, 'Quiz'),
      (Icons.history_rounded, 'Gecmis'),
    ];

    return Drawer(
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(18),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.primaryContainer,
                  borderRadius: BorderRadius.circular(18),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                      Icons.auto_stories_rounded,
                      color: Theme.of(context).colorScheme.primary,
                    ),
                    const SizedBox(height: 12),
                    Text(
                      'DocVerse',
                      style: Theme.of(context).textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                    const SizedBox(height: 4),
                    const Text('Dokuman asistan paneli'),
                  ],
                ),
              ),
              const SizedBox(height: 18),
              const LanguagePicker(),
              const SizedBox(height: 18),
              ...items.map(
                (item) => Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: ListTile(
                    leading: Icon(item.$1),
                    title: Text(item.$2),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14),
                    ),
                    onTap: () => Navigator.of(context).pop(),
                  ),
                ),
              ),
              const Spacer(),
              if (onLogout != null)
                ListTile(
                  leading: const Icon(Icons.logout_rounded),
                  title: Text(localizer.t('signOut')),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14),
                  ),
                  onTap: onLogout,
                ),
              const SizedBox(height: 8),
              Text(
                'Belgelerini daha kolay anlamak icin hazir.',
                style: Theme.of(
                  context,
                ).textTheme.bodySmall?.copyWith(color: const Color(0xFF667085)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
