import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'core/theme/app_theme.dart';
import 'core/i18n/app_language.dart';
import 'core/i18n/app_localizer.dart';
import 'features/home/presentation/home_screen.dart';
import 'services/auth_service.dart';

class DocVerseApp extends StatelessWidget {
  const DocVerseApp({super.key});

  @override
  Widget build(BuildContext context) {
    return AppLanguageScope(
      controller: appLanguageController,
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        title: 'DocVerse',
        theme: AppTheme.light(),
        builder: (context, child) => Directionality(
          textDirection: AppLocalizer.textDirectionOf(context),
          child: child ?? const SizedBox.shrink(),
        ),
        home: const AuthGate(),
      ),
    );
  }
}

class AuthGate extends StatefulWidget {
  const AuthGate({super.key});

  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  bool _authenticated = false;
  bool _authResolved = false;
  String? _guestMessage;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadAuthState());
  }

  Future<void> _loadAuthState() async {
    if (kDebugMode) {
      debugPrint('AUTH init started');
    }
    var authenticated = false;
    var hadStoredSession = false;
    var guestMessage = null as String?;
    final auth = AuthService();
    try {
      await appLanguageController.load();
      hadStoredSession = await auth.hasStoredSession();
      authenticated = await auth.restoreSession();
      if (hadStoredSession && !authenticated) {
        guestMessage = 'Oturum süresi doldu. Lütfen tekrar giriş yap.';
      }
    } catch (error) {
      authenticated = false;
      if (hadStoredSession) {
        guestMessage = 'Oturum süresi doldu. Lütfen tekrar giriş yap.';
      }
    }
    if (kDebugMode) {
      debugPrint('AUTH init done authenticated=$authenticated');
    }
    if (!mounted) return;
    setState(() {
      _authenticated = authenticated;
      _guestMessage = guestMessage;
      _authResolved = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!_authResolved) {
      return const Scaffold(
        body: SafeArea(child: Center(child: CircularProgressIndicator())),
      );
    }
    return _authenticated
        ? const HomeScreen()
        : HomeScreen(isGuest: true, guestMessage: _guestMessage);
  }
}
