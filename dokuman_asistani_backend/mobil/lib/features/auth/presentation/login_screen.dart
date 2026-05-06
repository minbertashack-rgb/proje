import 'package:flutter/material.dart';

import '../../../core/i18n/app_localizer.dart';
import '../../../core/network/api_exception.dart';
import '../../../services/auth_service.dart';
import '../../../shared/widgets/language_picker.dart';
import '../../../shared/widgets/status_message.dart';
import '../../home/presentation/home_screen.dart';
import 'register_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, this.successMessage});

  final String? successMessage;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  final _authService = AuthService();

  bool _loading = false;
  String? _error;
  String? _success;

  @override
  void initState() {
    super.initState();
    _success = widget.successMessage;
  }

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    final localizer = AppLocalizer.of(context);
    if (_usernameController.text.trim().isEmpty ||
        _passwordController.text.isEmpty) {
      setState(
        () => _error =
            '${localizer.t('username')} / ${localizer.t('password')} gerekli.',
      );
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
      _success = null;
    });

    try {
      await _authService.login(
        username: _usernameController.text.trim(),
        password: _passwordController.text,
      );
      if (!mounted) return;
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(
          builder: (_) => HomeScreen(username: _usernameController.text.trim()),
        ),
        (_) => false,
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = _friendlyAuthError(error.message));
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = localizer.t('unexpected_error'));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _friendlyAuthError(String message) {
    final lower = message.toLowerCase();
    if (lower.contains('<html') || lower.contains('<!doctype')) {
      return 'Sunucudan beklenmeyen yanit geldi.';
    }
    if (lower.contains('unexpected') || lower.contains('format')) {
      return 'Sunucudan beklenmeyen yanit geldi.';
    }
    if (message.trim().isEmpty || message.length > 180) {
      return 'Giris basarisiz oldu. Lutfen bilgileri kontrol edip tekrar dene.';
    }
    return message;
  }

  Future<void> _openRegister() async {
    await Navigator.of(
      context,
    ).push(MaterialPageRoute(builder: (_) => const RegisterScreen()));
  }

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 430),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Align(
                    alignment: Alignment.centerRight,
                    child: SizedBox(
                      width: 210,
                      child: LanguagePicker(compact: true),
                    ),
                  ),
                  const SizedBox(height: 14),
                  Container(
                    width: 68,
                    height: 68,
                    decoration: BoxDecoration(
                      color: Theme.of(context).colorScheme.primary,
                      borderRadius: BorderRadius.circular(22),
                    ),
                    child: const Icon(
                      Icons.auto_stories_rounded,
                      color: Colors.white,
                      size: 32,
                    ),
                  ),
                  const SizedBox(height: 22),
                  Text(
                    'DocVerse',
                    style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    localizer.t('signIn'),
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: const Color(0xFF667085),
                    ),
                  ),
                  const SizedBox(height: 28),
                  TextField(
                    controller: _usernameController,
                    enabled: !_loading,
                    textInputAction: TextInputAction.next,
                    decoration: InputDecoration(
                      labelText: localizer.t('username'),
                      prefixIcon: const Icon(Icons.person_outline_rounded),
                    ),
                  ),
                  const SizedBox(height: 14),
                  TextField(
                    controller: _passwordController,
                    enabled: !_loading,
                    obscureText: true,
                    onSubmitted: (_) => _login(),
                    decoration: InputDecoration(
                      labelText: localizer.t('password'),
                      prefixIcon: const Icon(Icons.lock_outline_rounded),
                    ),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 14),
                    StatusMessage(message: _error!, isError: true),
                  ],
                  if (_success != null) ...[
                    const SizedBox(height: 14),
                    StatusMessage(message: _success!),
                  ],
                  const SizedBox(height: 22),
                  FilledButton.icon(
                    onPressed: _loading ? null : _login,
                    icon: _loading
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.login_rounded),
                    label: Text(localizer.t('signIn')),
                  ),
                  const SizedBox(height: 10),
                  OutlinedButton.icon(
                    onPressed: _loading ? null : _openRegister,
                    icon: const Icon(Icons.person_add_alt_1_rounded),
                    label: Text(localizer.t('register')),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'Oturumunuz guvenli sekilde saklanir.',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: const Color(0xFF667085),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
