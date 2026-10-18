import { useEffect, useRef, useState, type FormEvent } from 'react';
import type { Language } from './i18n';
import type { Page } from './routes';
import { api, ApiError } from './api';
import type { ProfileSync, SyncState } from './profile-sync';
import type { Settings } from './storage';
import { ProfilePanel, syncWords } from './ProfilePanel';

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
      'An optional account can save your calendar across devices. You choose whether to upload this device’s settings. Email reminders are not enabled.',
    consent:
      'Continuing stores your email and a secure session on the account service. It does not upload your calendar or subscribe you to email reminders.',
    sent: 'Enter the eight-digit code from your email. It expires in ten minutes.',
    signed: 'Signed in as',
    waiting: 'Please wait…',
    invalid: 'The code is incorrect, expired or no longer active. Try again or request a new code.',
    failed: 'The account service is unavailable. Your local calendar is still usable.',
    limited: 'Please wait before trying again.',
    address: 'Enter a valid email address.',
    allowed: 'This preview sends codes only to configured test recipients.',
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
      'Una cuenta opcional guarda tu calendario entre dispositivos. Tú eliges si subes los ajustes de este dispositivo. Los recordatorios no están activos.',
    consent:
      'Al continuar se guardan tu correo y una sesión segura en el servicio de cuentas. No se sube tu calendario ni se activan recordatorios.',
    sent: 'Introduce el código de ocho dígitos de tu correo. Caduca en diez minutos.',
    signed: 'Sesión iniciada como',
    waiting: 'Espera un momento…',
    invalid:
      'El código es incorrecto, ha caducado o ya no está activo. Inténtalo de nuevo o pide otro.',
    failed: 'El servicio de cuentas no está disponible. Tu calendario local sigue funcionando.',
    limited: 'Espera antes de intentarlo de nuevo.',
    address: 'Introduce un correo válido.',
    allowed: 'Esta vista previa solo envía códigos a los destinatarios de prueba configurados.',
    local:
      'Prueba local: usa person@example.test. Los correos solo aparecen en la bandeja de prueba local; no se envía correo externo.',
  },
};

export function Account({
  language,
  controller,
  state,
  guest,
  done,
  page,
  navigate,
}: {
  language: Language;
  controller: ProfileSync;
  state: SyncState;
  guest: Settings | null;
  done: () => void;
  page: Page;
  navigate: (page: Page, replace?: boolean) => void;
}) {
  const c = words[language];
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [challenge, setChallenge] = useState<string | null>(null);
  const identity = state.identity;
  const [confirmOut, setConfirmOut] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [until, setUntil] = useState(0);
  const [now, setNow] = useState(Date.now);
  const codeInput = useRef<HTMLInputElement>(null);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    let current = true;
    controller.resume().finally(() => {
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
  useEffect(() => {
    if (busy) return;
    if (identity && page === 'login') navigate('account', true);
    else if (!identity && page === 'account') navigate('login', true);
  }, [busy, identity?.id, page]);
  const cooldown = Math.max(0, Math.ceil((until - now) / 1000));
  const errorText =
    error === 'email_not_allowed'
      ? c.allowed
      : error === 'verification_failed'
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
        await controller.signIn(value.user);
        if (!alive.current) return;
        setCode('');
        setChallenge(null);
      }
    });
  }
  async function signOut() {
    await controller.signOut();
    if (alive.current) {
      setEmail('');
      setUntil(0);
      setConfirmOut(false);
    }
  }
  return (
    <div className="account-copy">
      {!identity && (
        <p className="account-intro">
          {language === 'en'
            ? 'Save your calendar across devices. We’ll email you a code—no password needed.'
            : 'Guarda tu calendario entre dispositivos. Te enviaremos un código por correo; no necesitas contraseña.'}
        </p>
      )}
      {!identity && import.meta.env.VITE_AION_AUTH_LOCAL === '1' && (
        <p className="muted">{c.local}</p>
      )}
      {busy && !identity && !challenge ? (
        <p aria-live="polite">{c.waiting}</p>
      ) : identity ? (
        <>
          <p role="status">
            {c.signed} <strong className="account-address">{identity.email}</strong>.
          </p>
          <ProfilePanel
            controller={controller}
            state={state}
            guest={guest}
            language={language}
            done={done}
          />
          {confirmOut ? (
            <>
              <p>{syncWords[language].discard}</p>
              <div className="form-actions">
                <button
                  className="button primary"
                  disabled={busy || state.busy || !navigator.onLine}
                  onClick={() => void perform(signOut)}
                >
                  {syncWords[language].discardOut}
                </button>
                <button className="button secondary" onClick={() => setConfirmOut(false)}>
                  {syncWords[language].cancel}
                </button>
              </div>
            </>
          ) : (
            <button
              className="button secondary"
              disabled={busy || state.busy || !navigator.onLine}
              onClick={() => {
                if (state.pending) setConfirmOut(true);
                else void perform(signOut);
              }}
            >
              {busy ? c.waiting : c.out}
            </button>
          )}
        </>
      ) : (
        <form onSubmit={submit}>
          <p className="eyebrow">
            {challenge
              ? language === 'en'
                ? '02 / Check your email'
                : '02 / Revisa tu correo'
              : language === 'en'
                ? '01 / Your email'
                : '01 / Tu correo'}
          </p>
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
              <p>
                {c.sent} <strong className="account-address">{email}</strong>
              </p>
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
            <button className="button primary" disabled={busy || (!challenge && cooldown > 0)}>
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
      {!identity && <p className="account-consent muted">{c.consent}</p>}
      <p id="account-error" role="alert">
        {errorText || (!identity && state.phase === 'error' ? c.failed : '')}
      </p>
    </div>
  );
}
