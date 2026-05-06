import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../../../services/auth_service.dart';
import '../../../core/i18n/app_localizer.dart';
import '../../auth/presentation/login_screen.dart';
import '../../auth/presentation/register_screen.dart';
import '../widgets/app_drawer.dart';
import '../widgets/backend_flow_panel.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({
    super.key,
    this.isGuest = false,
    this.username,
    this.guestMessage,
  });

  final bool isGuest;
  final String? username;
  final String? guestMessage;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _flowKey = GlobalKey<BackendFlowPanelState>();
  AuthService? _authService;
  bool _buildLogged = false;

  AuthService get _auth => _authService ??= AuthService();

  @override
  void dispose() {
    _authService = null;
    super.dispose();
  }

  Future<void> _logout() async {
    _flowKey.currentState?.clearSessionState();
    await _auth.logout();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const HomeScreen(isGuest: true)),
      (_) => false,
    );
  }

  Future<void> _handleUnauthorized(String reason) async {
    await _auth.clearSession(reason: reason);
    if (!mounted) return;
    final message = AppLocalizer.of(context).t('sessionExpired');
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(
        builder: (_) => HomeScreen(
          isGuest: true,
          guestMessage: message,
        ),
      ),
      (_) => false,
    );
  }

  Future<void> _openLogin() async {
    await Navigator.of(
      context,
    ).push(MaterialPageRoute(builder: (_) => const LoginScreen()));
  }

  Future<void> _openRegister() async {
    await Navigator.of(
      context,
    ).push(MaterialPageRoute(builder: (_) => const RegisterScreen()));
  }

  @override
  Widget build(BuildContext context) {
    if (kDebugMode && !_buildLogged) {
      _buildLogged = true;
      debugPrint(
        widget.isGuest
            ? 'Guest HomeScreen build'
            : 'Authenticated HomeScreen build',
      );
    }
    final keyboardOpen = MediaQuery.viewInsetsOf(context).bottom > 0;

    return Scaffold(
      drawer: widget.isGuest ? null : AppDrawer(onLogout: _logout),
      appBar: widget.isGuest ? null : AppBar(title: const Text('DocVerse')),
      body: SafeArea(
        child: ListView(
          keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
          padding: EdgeInsets.fromLTRB(18, 10, 18, keyboardOpen ? 24 : 118),
          children: [
            BackendFlowPanel(
              key: _flowKey,
              isGuest: widget.isGuest,
              username: widget.username,
              guestMessage: widget.guestMessage,
              onLogin: _openLogin,
              onRegister: _openRegister,
              onLogout: _logout,
              onUnauthorized: _handleUnauthorized,
            ),
          ],
        ),
      ),
    );
  }
}
