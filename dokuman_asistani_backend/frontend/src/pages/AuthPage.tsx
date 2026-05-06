import { useEffect, useState } from 'react';
import { login, register } from '../api/authApi';
import { ApiError } from '../api/client';
import { asArray, asRecord, extractMessage } from '../api/normalize';
import { FeedbackPanel } from '../components/common/StateViews';
import { useAuthSession } from '../hooks/useAuthSession';
import type { LoginCredentials, RegisterFormValues } from '../types/api';
import type { LoadableState } from '../types/ui';

type AuthMode = 'login' | 'register';

type AuthPageProps = {
  initialMode: AuthMode;
};

const fieldLabels: Record<string, string> = {
  username: 'Kullanıcı adı',
  email: 'Email',
  password: 'Şifre',
  password2: 'Şifre tekrar',
  password_confirm: 'Şifre tekrar',
  non_field_errors: 'Hata',
};

function createState<T>(
  status: LoadableState<T>['status'],
  data?: T,
  message?: string,
): LoadableState<T> {
  return {
    status,
    data,
    message,
    updatedAt: new Date().toISOString(),
  };
}

function readFieldMessages(payload: unknown) {
  const record = asRecord(payload);
  if (!record) {
    return [];
  }

  const fieldSource = asRecord(record.field_errors) ?? asRecord(record.errors) ?? record;
  const messages: string[] = [];

  Object.entries(fieldLabels).forEach(([field, label]) => {
    const value = fieldSource[field];
    if (!value) {
      return;
    }

    const text = asArray(value).length
      ? asArray(value).map((item) => String(item)).join(' ')
      : String(value);

    if (text.trim()) {
      messages.push(`${label}: ${text.trim()}`);
    }
  });

  return messages;
}

function pickFriendlyMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    const fieldMessages = readFieldMessages(error.payload);
    if (fieldMessages.length) {
      return fieldMessages.join('\n');
    }

    const record = asRecord(error.payload);
    const statusText = typeof record?.status_text === 'string' ? record.status_text : undefined;
    const message =
      extractMessage(record?.detail) ??
      statusText ??
      extractMessage(record?.message) ??
      extractMessage(record?.mesaj) ??
      extractMessage(record?.error) ??
      extractMessage(record?.hata) ??
      error.message;

    return message || fallback;
  }

  return extractMessage(error) ?? fallback;
}

function setAuthRoute(mode: AuthMode) {
  window.location.hash = `#/auth/${mode}`;
}

export function AuthPage({ initialMode }: AuthPageProps) {
  const { setSession } = useAuthSession();
  const [mode, setMode] = useState<AuthMode>(initialMode);
  const [loginForm, setLoginForm] = useState<LoginCredentials>({ username: '', password: '' });
  const [registerForm, setRegisterForm] = useState<RegisterFormValues>({
    username: '',
    email: '',
    password: '',
    passwordConfirm: '',
  });
  const [authState, setAuthState] = useState<LoadableState<null>>(createState('idle'));
  const [registerState, setRegisterState] = useState<LoadableState<null>>(createState('idle'));
  const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  useEffect(() => {
    setMode(initialMode);
    setAuthState(createState('idle'));
    setRegisterState(createState('idle'));
  }, [initialMode]);

  const switchMode = (nextMode: AuthMode) => {
    setMode(nextMode);
    setAuthState(createState('idle'));
    setRegisterState(createState('idle'));
    setAuthRoute(nextMode);
  };

  const handleLoginSubmit = async () => {
    const username = loginForm.username.trim();

    if (!username || !loginForm.password.trim()) {
      setAuthState(createState('error', null, 'Kullanıcı adı ve şifre gerekli.'));
      return;
    }

    setAuthState(createState('loading'));
    try {
      const nextSession = await login({
        username,
        password: loginForm.password,
      });
      setSession(nextSession);
      setLoginForm((previous) => ({ ...previous, password: '' }));
      window.location.hash = '#/';
    } catch (error) {
      setAuthState(createState('error', null, pickFriendlyMessage(error, 'Giriş yapılamadı.')));
    }
  };

  const handleRegisterSubmit = async () => {
    const username = registerForm.username.trim();
    const email = registerForm.email?.trim() ?? '';

    if (!username || !email || !registerForm.password || !registerForm.passwordConfirm) {
      setRegisterState(createState('error', null, 'Kullanıcı adı, email, şifre ve şifre tekrar gerekli.'));
      return;
    }

    if (!emailPattern.test(email)) {
      setRegisterState(createState('error', null, 'Geçerli bir email adresi girin.'));
      return;
    }

    if (registerForm.password !== registerForm.passwordConfirm) {
      setRegisterState(createState('error', null, 'Şifre tekrar alanı eşleşmiyor.'));
      return;
    }

    setRegisterState(createState('loading'));
    try {
      await register({
        username,
        email,
        password: registerForm.password,
        password2: registerForm.passwordConfirm,
      });
      setLoginForm({ username, password: '' });
      setRegisterForm({
        username,
        email: '',
        password: '',
        passwordConfirm: '',
      });
      setMode('login');
      setAuthRoute('login');
      setAuthState(createState('idle'));
      setRegisterState(createState('success', null, 'Kayıt tamamlandı. Şimdi giriş yapabilirsiniz.'));
    } catch (error) {
      setRegisterState(createState('error', null, pickFriendlyMessage(error, 'Kayıt oluşturulamadı.')));
    }
  };

  return (
    <main className="min-h-screen px-4 py-6 text-slate-900 sm:px-6 lg:px-8">
      <div className="mx-auto flex min-h-[calc(100vh-3rem)] max-w-6xl items-center">
        <div className="grid w-full gap-6 lg:grid-cols-[minmax(0,0.95fr),minmax(360px,0.7fr)] lg:items-center">
          <section className="rounded-3xl border border-white/70 bg-white/[0.78] p-6 shadow-ambient backdrop-blur-xl sm:p-8">
            <a href="#/" className="inline-flex items-center gap-3">
              <span className="grid h-11 w-11 place-items-center rounded-2xl bg-gradient-to-br from-teal-500 via-sky-500 to-indigo-500 text-sm font-extrabold text-white shadow-soft">
                D
              </span>
              <span>
                <span className="display-font block text-xl font-semibold tracking-tight text-slate-950">DocVerse</span>
                <span className="block text-sm font-medium text-slate-500">Belge çalışma alanı</span>
              </span>
            </a>

            <div className="mt-10 max-w-xl space-y-4">
              <span className="chip bg-white/90">TÜBİTAK öğrenme deneyimi</span>
              <h1 className="display-font text-3xl font-semibold tracking-tight text-slate-950 sm:text-5xl">
                Dokümanlarını oku, parçaları aç, kanıtlı cevaplarla ilerle.
              </h1>
              <p className="text-sm leading-7 text-slate-600 sm:text-base">
                Giriş yaptıktan sonra doküman yükleme, parça seçme, açıklama alma ve kanıtlı soru sorma akışları ana çalışma alanında devam eder.
              </p>
            </div>

            <div className="mt-8 grid gap-3 sm:grid-cols-3">
              {['Belge yükleme', 'Açıklama akışı', 'Kanıtlı cevap'].map((item) => (
                <div key={item} className="rounded-2xl border border-slate-200 bg-white/75 p-4">
                  <p className="text-sm font-semibold text-slate-900">{item}</p>
                  <p className="mt-2 text-xs leading-6 text-slate-500">Hesabınla çalışma alanında kullanılır.</p>
                </div>
              ))}
            </div>
          </section>

          <section className="section-card p-5 sm:p-6">
            <div className="mb-5 flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-semibold text-slate-900">
                  {mode === 'login' ? 'Giriş Yap' : 'Kayıt Ol'}
                </p>
                <p className="mt-1 text-sm text-slate-500">
                  {mode === 'login' ? 'Çalışma alanına devam et.' : 'Yeni hesabını oluştur.'}
                </p>
              </div>
              <a href="#/" className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold text-slate-700">
                Ana Sayfa
              </a>
            </div>

            <div className="mb-5 grid grid-cols-2 rounded-xl border border-slate-200 bg-slate-50 p-1">
              <button
                type="button"
                onClick={() => switchMode('login')}
                className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${
                  mode === 'login' ? 'bg-white text-slate-950 shadow-soft' : 'text-slate-600'
                }`}
              >
                Giriş Yap
              </button>
              <button
                type="button"
                onClick={() => switchMode('register')}
                className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${
                  mode === 'register' ? 'bg-white text-slate-950 shadow-soft' : 'text-slate-600'
                }`}
              >
                Kayıt Ol
              </button>
            </div>

            {mode === 'login' ? (
              <div className="space-y-4">
                <input
                  value={loginForm.username}
                  onChange={(event) => {
                    setAuthState(createState('idle'));
                    setLoginForm((previous) => ({ ...previous, username: event.target.value }));
                  }}
                  placeholder="Kullanıcı adı"
                  className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
                />
                <input
                  type="password"
                  value={loginForm.password}
                  onChange={(event) => {
                    setAuthState(createState('idle'));
                    setLoginForm((previous) => ({ ...previous, password: event.target.value }));
                  }}
                  placeholder="Şifre"
                  className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
                />
                <button
                  type="button"
                  onClick={handleLoginSubmit}
                  disabled={authState.status === 'loading'}
                  className="w-full rounded-xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {authState.status === 'loading' ? 'Giriş yapılıyor...' : 'Giriş Yap'}
                </button>
                <p className="text-center text-sm text-slate-500">
                  Hesabın yok mu?{' '}
                  <button type="button" onClick={() => switchMode('register')} className="font-semibold text-teal-700">
                    Kayıt ol
                  </button>
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                <input
                  value={registerForm.username}
                  onChange={(event) => {
                    setRegisterState(createState('idle'));
                    setRegisterForm((previous) => ({ ...previous, username: event.target.value }));
                  }}
                  placeholder="Kullanıcı adı"
                  className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
                />
                <input
                  type="email"
                  value={registerForm.email ?? ''}
                  onChange={(event) => {
                    setRegisterState(createState('idle'));
                    setRegisterForm((previous) => ({ ...previous, email: event.target.value }));
                  }}
                  placeholder="E-posta"
                  className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
                />
                <input
                  type="password"
                  value={registerForm.password}
                  onChange={(event) => {
                    setRegisterState(createState('idle'));
                    setRegisterForm((previous) => ({ ...previous, password: event.target.value }));
                  }}
                  placeholder="Şifre"
                  className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
                />
                <input
                  type="password"
                  value={registerForm.passwordConfirm}
                  onChange={(event) => {
                    setRegisterState(createState('idle'));
                    setRegisterForm((previous) => ({ ...previous, passwordConfirm: event.target.value }));
                  }}
                  placeholder="Şifre tekrar"
                  className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
                />
                <button
                  type="button"
                  onClick={handleRegisterSubmit}
                  disabled={registerState.status === 'loading'}
                  className="w-full rounded-xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {registerState.status === 'loading' ? 'Kayıt oluşturuluyor...' : 'Kayıt Ol'}
                </button>
                <p className="text-center text-sm text-slate-500">
                  Hesabın var mı?{' '}
                  <button type="button" onClick={() => switchMode('login')} className="font-semibold text-teal-700">
                    Giriş yap
                  </button>
                </p>
              </div>
            )}

            {authState.status === 'error' ? (
              <FeedbackPanel
                title="Giriş hatası"
                message={authState.message ?? 'Giriş yapılamadı.'}
                tone="error"
                className="mt-5 whitespace-pre-line"
              />
            ) : null}

            {registerState.status === 'error' ? (
              <FeedbackPanel
                title="Kayıt hatası"
                message={registerState.message ?? 'Kayıt oluşturulamadı.'}
                tone="error"
                className="mt-5 whitespace-pre-line"
              />
            ) : null}

            {registerState.status === 'success' ? (
              <FeedbackPanel
                title="Kayıt tamamlandı"
                message={registerState.message ?? 'Kayıt tamamlandı. Şimdi giriş yapabilirsiniz.'}
                tone="success"
                className="mt-5"
              />
            ) : null}
          </section>
        </div>
      </div>
    </main>
  );
}
