import 'package:flutter/material.dart';

import '../../../core/i18n/app_localizer.dart';
import '../../../core/network/api_exception.dart';
import '../../../services/auth_service.dart';
import '../../../shared/widgets/status_message.dart';
import 'login_screen.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _usernameController = TextEditingController();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _passwordAgainController = TextEditingController();
  final _authService = AuthService();

  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _usernameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    _passwordAgainController.dispose();
    super.dispose();
  }

  Future<void> _register() async {
    if (_loading) return;
    FocusScope.of(context).unfocus();

    final username = _usernameController.text.trim();
    final email = _emailController.text.trim();
    final password = _passwordController.text;
    final passwordAgain = _passwordAgainController.text;

    if (username.isEmpty ||
        email.isEmpty ||
        password.isEmpty ||
        passwordAgain.isEmpty) {
      setState(() => _error = 'Tum alanlari doldurmalisin.');
      return;
    }
    if (!_isValidEmail(email)) {
      setState(() => _error = 'Gecerli bir email adresi yazmalisin.');
      return;
    }
    if (password.length < 6) {
      setState(() => _error = 'Sifre en az 6 karakter olmali.');
      return;
    }
    if (password != passwordAgain) {
      setState(() => _error = 'Sifreler eslesmiyor.');
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      await _authService.register(
        username: username,
        password: password,
        passwordAgain: passwordAgain,
        email: email,
      );
      if (!mounted) return;
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(
          builder: (_) => const LoginScreen(
            successMessage: 'Kayit basarili. Simdi giris yapabilirsin.',
          ),
        ),
        (_) => false,
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = _friendlyRegisterError(error.message));
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = 'Kayit basarisiz oldu.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _friendlyRegisterError(String message) {
    final lower = message.toLowerCase();
    if (lower.contains('<html') || lower.contains('<!doctype')) {
      return 'Kayit basarisiz oldu. Sunucudan beklenmeyen yanit geldi.';
    }
    if (lower.contains('unexpected') || lower.contains('format')) {
      return 'Kayit basarisiz oldu. Sunucudan beklenmeyen yanit geldi.';
    }
    if (lower.contains('sunucudan beklenmeyen')) {
      return 'Kayit basarisiz oldu. Sunucudan beklenmeyen yanit geldi.';
    }
    if (message.trim().isEmpty || message.length > 180) {
      return 'Kayit basarisiz oldu. Lutfen bilgileri kontrol edip tekrar dene.';
    }
    return message;
  }

  bool _isValidEmail(String value) {
    return RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$').hasMatch(value);
  }

  @override
  Widget build(BuildContext context) {
    final localizer = AppLocalizer.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(localizer.t('register'))),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 430),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    'DocVerse hesabi olustur',
                    style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Kayit tamamlaninca giris ekranina doneceksin.',
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: const Color(0xFF667085),
                    ),
                  ),
                  const SizedBox(height: 24),
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
                    controller: _emailController,
                    enabled: !_loading,
                    keyboardType: TextInputType.emailAddress,
                    textInputAction: TextInputAction.next,
                    decoration: InputDecoration(
                      labelText: localizer.t('email'),
                      prefixIcon: const Icon(Icons.mail_outline_rounded),
                    ),
                  ),
                  const SizedBox(height: 14),
                  TextField(
                    controller: _passwordController,
                    enabled: !_loading,
                    obscureText: true,
                    textInputAction: TextInputAction.next,
                    decoration: InputDecoration(
                      labelText: localizer.t('password'),
                      prefixIcon: const Icon(Icons.lock_outline_rounded),
                    ),
                  ),
                  const SizedBox(height: 14),
                  TextField(
                    controller: _passwordAgainController,
                    enabled: !_loading,
                    obscureText: true,
                    onSubmitted: (_) => _register(),
                    decoration: InputDecoration(
                      labelText: localizer.t('confirmPassword'),
                      prefixIcon: const Icon(Icons.lock_reset_rounded),
                    ),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 14),
                    StatusMessage(message: _error!, isError: true),
                  ],
                  const SizedBox(height: 22),
                  FilledButton.icon(
                    onPressed: _loading ? null : _register,
                    icon: _loading
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.person_add_alt_1_rounded),
                    label: Text(localizer.t('register')),
                  ),
                  const SizedBox(height: 10),
                  OutlinedButton(
                    onPressed: _loading
                        ? null
                        : () => Navigator.of(context).pop(),
                    child: const Text('Giris ekranina don'),
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
