import { useEffect, useRef, useState, type FormEvent } from 'react';
import type { Language } from './i18n';

export const accountsEnabled = import.meta.env.VITE_AION_AUTH === '1';
const words = {
  en: {
    title: 'Your account',
    email: 'Email address',
    code: 'Verification code',
    send: 'Send a code',
    verify: 'Verify email',
    resend: 'Send another code',
    change: 'Use another email',
    out: 'Sign out',
    about:
      'An optional account verifies your email. Your calendar stays on this device for now; settings sync and reminders are coming in separate releases.',
    consent:
      'Continuing stores your email and a secure session on the account service. It does not upload your calendar or subscribe you to email reminders.',
    sent: 'Enter the eight-digit code from your email. It expires in ten minutes.',
    signed: 'Email verified. Signed in as',
    waiting: 'Please wait…',
    invalid: 'The code is incorrect, expired or no longer active. Try again or request a new code.',
    failed: 'The account service is unavailable. Your local calendar is still usable.',
    limited: 'Please wait before trying again.',
    address: 'Enter a valid email address.',
    local:
      'Local test: use person@example.test. Emails appear only in the local test inbox; no external email is sent.',
  },
  es: {
    title: 'Tu cuenta',
    email: 'Correo electrónico',
    code: 'Código de verificación',
    send: 'Enviar un código',
    verify: 'Verificar correo',
    resend: 'Enviar otro código',
    change: 'Usar otro correo',
    out: 'Cerrar sesión',
    about:
      'Una cuenta opcional verifica tu correo. Tu calendario sigue en este dispositivo por ahora; la sincronización y los recordatorios llegarán en versiones posteriores.',
    consent:
      'Al continuar se guardan tu correo y una sesión segura en el servicio de cuentas. No se sube tu calendario ni se activan recordatorios.',
    sent: 'Introduce el código de ocho dígitos de tu correo. Caduca en diez minutos.',
    signed: 'Correo verificado. Sesión iniciada como',
    waiting: 'Espera un momento…',
    invalid:
      'El código es incorrecto, ha caducado o ya no está activo. Inténtalo de nuevo o pide otro.',
    failed: 'El servicio de cuentas no está disponible. Tu calendario local sigue funcionando.',
    limited: 'Espera antes de intentarlo de nuevo.',
    address: 'Introduce un correo válido.',
    local:
      'Prueba local: usa person@example.test. Los correos solo aparecen en la bandeja de prueba local; no se envía correo externo.',
  },
};

class ApiError extends Error {
  constructor(
    public code: string,
    public retry: number,
  ) {
    super(code);
  }
}
async function api<T>(path: string, body?: unknown, csrf?: string): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    credentials: 'same-origin',
    cache: 'no-store',
    headers:
      body === undefined
        ? {}
        : { 'Content-Type': 'application/json', ...(csrf ? { 'X-CSRF-Token': csrf } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const value = await response.json().catch(() => null);
    throw new ApiError(
      value?.error?.code ?? 'unavailable',
      Number(response.headers.get('Retry-After')) || 0,
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export function Account({ language }: { language: Language }) {
  const c = words[language];
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [challenge, setChallenge] = useState<string | null>(null);
  const [identity, setIdentity] = useState<{ id: string; email: string } | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [until, setUntil] = useState(0);
  const [now, setNow] = useState(Date.now);
  const codeInput = useRef<HTMLInputElement>(null);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    let current = true;
    api<{ id: string; email: string }>('/me')
      .then((value) => {
        if (current) setIdentity(value);
      })
      .catch((value) => {
        if (current && !(value instanceof ApiError && value.code === 'unauthenticated'))
          setError('unavailable');
      })
      .finally(() => {
        if (current) setBusy(false);
      });
    return () => {
      current = false;
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    if (!until) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [until]);
  useEffect(() => {
    if (challenge) codeInput.current?.focus();
  }, [challenge]);
  const cooldown = Math.max(0, Math.ceil((until - now) / 1000));
  const errorText =
    error === 'verification_failed'
      ? c.invalid
      : error === 'rate_limited'
        ? c.limited
        : error === 'invalid_email'
          ? c.address
          : error
            ? c.failed
            : '';
  async function perform(operation: () => Promise<void>) {
    setBusy(true);
    setError('');
    try {
      await operation();
    } catch (value) {
      if (alive.current) {
        setError(value instanceof ApiError ? value.code : 'unavailable');
        if (value instanceof ApiError && value.retry) {
          setNow(Date.now());
          setUntil(Date.now() + value.retry * 1000);
        }
      }
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  async function send() {
    const value = await api<{ challenge_id: string; resend_after: number }>('/auth/challenges', {
      email,
      language,
    });
    if (!alive.current) return;
    setChallenge(value.challenge_id);
    setCode('');
    setNow(Date.now());
    setUntil(Date.now() + value.resend_after * 1000);
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    void perform(async () => {
      if (!challenge) return send();
      const value = await api<{ user: { id: string; email: string } }>('/auth/verify', {
        challenge_id: challenge,
        code,
      });
      if (alive.current) {
        setIdentity(value.user);
        setCode('');
        setChallenge(null);
      }
    });
  }
  return (
    <div className="account-copy">
      <p>{c.about}</p>
      {import.meta.env.VITE_AION_AUTH_LOCAL === '1' && <p className="muted">{c.local}</p>}
      {identity ? (
        <>
          <p role="status">
            {c.signed} <strong>{identity.email}</strong>.
          </p>
          <button
            className="button secondary"
            disabled={busy}
            onClick={() =>
              void perform(async () => {
                const csrf = await api<{ csrf_token: string }>('/auth/csrf');
                await api<void>('/auth/logout', {}, csrf.csrf_token);
                if (alive.current) {
                  setIdentity(null);
                  setEmail('');
                  setUntil(0);
                }
              })
            }
          >
            {busy ? c.waiting : c.out}
          </button>
        </>
      ) : (
        <form onSubmit={submit}>
          <p className="muted">{c.consent}</p>
          {!challenge ? (
            <label>
              {c.email}
              <input
                type="email"
                autoComplete="email"
                required
                maxLength={254}
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>
          ) : (
            <>
              <p>{c.sent}</p>
              <label>
                {c.code}
                <input
                  ref={codeInput}
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  required
                  pattern="[0-9]{8}"
                  maxLength={8}
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  aria-describedby="account-error"
                />
              </label>
            </>
          )}
          <div className="form-actions">
            <button className="button" disabled={busy || (!challenge && cooldown > 0)}>
              {busy ? c.waiting : challenge ? c.verify : c.send}
            </button>
            {challenge && (
              <>
                <button
                  type="button"
                  className="button secondary"
                  disabled={busy || cooldown > 0}
                  onClick={() => void perform(send)}
                >
                  {c.resend}
                  {cooldown > 0 ? ` (${cooldown})` : ''}
                </button>
                <button
                  type="button"
                  className="text-button"
                  disabled={busy}
                  onClick={() => {
                    setChallenge(null);
                    setCode('');
                    setError('');
                  }}
                >
                  {c.change}
                </button>
              </>
            )}
          </div>
        </form>
      )}
      <p id="account-error" role="alert">
        {errorText}
      </p>
    </div>
  );
}
