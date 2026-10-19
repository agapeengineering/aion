import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError, request } from './api';
import { verificationDeadline } from './account-time';
import type { Language } from './i18n';
import type { ProfileSync } from './profile-sync';

type Session = {
  id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  current: boolean;
};
const words = {
  en: {
    sessions: 'Signed-in sessions',
    sessionIntro:
      'Review where your account is signed in. Dates identify sessions; Aion does not store device fingerprints.',
    current: 'This session',
    other: 'Another session',
    created: 'Created',
    seen: 'Last active',
    revoke: 'Sign out this session',
    reload: 'Refresh sessions',
    all: 'Sign out everywhere',
    confirmAll: 'Confirm sign out everywhere',
    allNotice:
      'This signs out every device, including this one, and discards this browser’s queued account edits. Changes already sent may have been saved. Your saved calendar and separate guest calendar remain.',
    data: 'Your data',
    dataIntro:
      'Download your saved account data or permanently delete your account. We’ll ask for a fresh email code first.',
    export: 'Download my data',
    remove: 'Delete account',
    confirmRemove: 'Permanently delete my account',
    deletion:
      'This permanently removes your account, saved calendar and reminder settings, cancels pending emails and signs out every session. Unsynced account edits on this browser are discarded. Your separate guest calendar and downloaded images remain.',
    retention:
      'Delivered emails cannot be recalled. Encrypted backups can retain deleted data for up to 30 days. Minimal deletion and delivery-suppression identifiers are retained to prevent restored backups from reactivating deleted data or sending mail.',
    send: 'Send confirmation code',
    resend: 'Send another confirmation code',
    code: 'Account confirmation code',
    verify: 'Confirm it’s me',
    codeNotice:
      'Enter the eight-digit code sent to your account email. It expires in ten minutes and works only in this session.',
    verified: 'Email confirmed. Choose an action below; confirmation lasts ten minutes.',
    agree: 'I understand that deleting my account is permanent.',
    cancel: 'Cancel',
    busy: 'Please wait…',
    failed: 'The request could not be confirmed. Refresh before trying again.',
    invalid: 'That code is incorrect, expired or no longer active.',
    limited: 'Please wait before requesting another code.',
    fresh: 'Confirm your email again before continuing.',
    offline: 'Reconnect to manage your account.',
    exported: 'Your account data download is ready.',
    pending:
      'The export includes saved server data. Unsynced edits on this browser are not included.',
  },
  es: {
    sessions: 'Sesiones iniciadas',
    sessionIntro:
      'Revisa dónde está iniciada tu cuenta. Las fechas identifican las sesiones; Aion no guarda huellas digitales del dispositivo.',
    current: 'Esta sesión',
    other: 'Otra sesión',
    created: 'Creada',
    seen: 'Última actividad',
    revoke: 'Cerrar esta sesión',
    reload: 'Actualizar sesiones',
    all: 'Cerrar todas las sesiones',
    confirmAll: 'Confirmar cierre de todas las sesiones',
    allNotice:
      'Se cerrará la sesión en todos los dispositivos, incluido este, y se descartarán los cambios de cuenta en espera de este navegador. Los cambios ya enviados pueden haberse guardado. Tu calendario guardado y el calendario local separado se conservan.',
    data: 'Tus datos',
    dataIntro:
      'Descarga los datos guardados de tu cuenta o elimínala permanentemente. Antes te pediremos un nuevo código por correo.',
    export: 'Descargar mis datos',
    remove: 'Eliminar cuenta',
    confirmRemove: 'Eliminar mi cuenta permanentemente',
    deletion:
      'Se eliminarán tu cuenta, calendario guardado y ajustes de recordatorios, se cancelarán los correos pendientes y se cerrarán todas las sesiones. Se descartarán los cambios de cuenta sin sincronizar de este navegador. Tu calendario local separado y las imágenes descargadas se conservan.',
    retention:
      'Los correos entregados no se pueden retirar. Las copias cifradas pueden conservar los datos eliminados hasta 30 días. Se retienen identificadores mínimos de eliminación y de bloqueo de correo para impedir que una copia restaurada reactive datos eliminados o envíe mensajes.',
    send: 'Enviar código de confirmación',
    resend: 'Enviar otro código de confirmación',
    code: 'Código de confirmación de cuenta',
    verify: 'Confirmar que soy yo',
    codeNotice:
      'Introduce el código de ocho dígitos enviado al correo de tu cuenta. Caduca en diez minutos y solo funciona en esta sesión.',
    verified: 'Correo confirmado. Elige una acción abajo; la confirmación dura diez minutos.',
    agree: 'Entiendo que eliminar mi cuenta es permanente.',
    cancel: 'Cancelar',
    busy: 'Espera un momento…',
    failed: 'No se pudo confirmar la solicitud. Actualiza antes de volver a intentarlo.',
    invalid: 'El código es incorrecto, ha caducado o ya no está activo.',
    limited: 'Espera antes de pedir otro código.',
    fresh: 'Confirma tu correo otra vez antes de continuar.',
    offline: 'Vuelve a conectarte para gestionar tu cuenta.',
    exported: 'La descarga de tus datos está lista.',
    pending:
      'La exportación incluye los datos guardados en el servidor. No incluye los cambios sin sincronizar de este navegador.',
  },
};
export function AccountManagement({
  owner,
  language,
  controller,
  pending,
}: {
  owner: string;
  language: Language;
  controller: ProfileSync;
  pending: boolean;
}) {
  const c = words[language];
  const [sessions, setSessions] = useState<Session[]>([]);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [notice, setNotice] = useState('');
  const [action, setAction] = useState<'export' | 'delete' | 'all' | null>(null);
  const [challenge, setChallenge] = useState(''),
    [code, setCode] = useState('');
  const [verifiedUntil, setVerifiedUntil] = useState(0),
    [resendAt, setResendAt] = useState(0);
  const [now, setNow] = useState(performance.now()),
    [confirmed, setConfirmed] = useState(false);
  const epoch = useRef(0),
    codeRef = useRef<HTMLInputElement>(null),
    actionRef = useRef<HTMLHeadingElement>(null);
  const online = navigator.onLine;
  const fresh = verifiedUntil > now;
  const headers = { 'X-Aion-Account': owner };
  async function write<T>(path: string, method: 'POST' | 'DELETE', body?: unknown) {
    const csrf = await request<{ csrf_token: string }>('/auth/csrf');
    return request<T>(path, {
      method,
      body,
      headers: { ...headers, 'X-CSRF-Token': csrf.csrf_token },
    });
  }
  async function perform(operation: () => Promise<void>) {
    const generation = epoch.current;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await operation();
    } catch (err) {
      if (generation !== epoch.current) return;
      const value = err instanceof ApiError ? err : null;
      if (value?.status === 401 || value?.code === 'account_changed') {
        await controller.refresh();
        return;
      }
      if (value?.code === 'reverification_required') setVerifiedUntil(0);
      if (value?.retry) setResendAt(performance.now() + value.retry * 1000);
      setError(
        value?.code === 'verification_failed'
          ? c.invalid
          : value?.code === 'rate_limited'
            ? c.limited
            : value?.code === 'reverification_required'
              ? c.fresh
              : c.failed,
      );
    } finally {
      if (generation === epoch.current) setBusy(false);
    }
  }
  async function load() {
    const generation = epoch.current;
    const result = await request<{
      user_id: string;
      sessions: Session[];
      reverified_for: number;
    }>('/sessions', {
      headers,
    });
    if (generation !== epoch.current) return;
    if (result.user_id !== owner) throw new Error('Account changed');
    setSessions(result.sessions);
    setVerifiedUntil(verificationDeadline(result.reverified_for));
  }
  useEffect(() => {
    mountedEpoch.current = epoch.current;
    void perform(load);
    return () => {
      epoch.current++;
    };
  }, [owner]);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(performance.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (challenge) codeRef.current?.focus();
  }, [challenge]);
  useEffect(() => {
    if (action) actionRef.current?.focus();
  }, [action]);
  async function send() {
    const generation = epoch.current;
    const result = await write<{ challenge_id: string; resend_after: number }>(
      '/auth/reverify/challenges',
      'POST',
      { language },
    );
    if (generation !== epoch.current) return;
    setChallenge(result.challenge_id);
    setCode('');
    setResendAt(performance.now() + result.resend_after * 1000);
  }
  function verify(e: FormEvent) {
    e.preventDefault();
    void perform(async () => {
      const generation = epoch.current;
      const result = await controller.accountAction(owner, () =>
        write<{ reverified_for: number }>('/auth/reverify', 'POST', {
          challenge_id: challenge,
          code,
        }),
      );
      if (generation !== epoch.current) return;
      setVerifiedUntil(verificationDeadline(result.reverified_for));
      setChallenge('');
      setCode('');
      actionRef.current?.focus();
    });
  }
  async function download() {
    const result = await request<unknown>('/account/export', { headers });
    if (!alive()) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(result, null, 2) + '\n'], { type: 'application/json' }),
    );
    const a = document.createElement('a');
    a.href = url;
    a.download = 'aion-account.json';
    a.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice(c.exported);
  }
  // The keyed component unmounts on account changes; no late result may start another action.
  const mountedEpoch = useRef(epoch.current);
  function alive() {
    return epoch.current === mountedEpoch.current;
  }
  const choose = (value: typeof action) => {
    setAction(value);
    setError('');
    setNotice('');
    setConfirmed(false);
  };
  return (
    <div className="account-management">
      <section aria-labelledby="sessions-title">
        <h2 id="sessions-title">{c.sessions}</h2>
        <p className="muted">{c.sessionIntro}</p>
        <ul className="account-sessions">
          {sessions.map((session) => (
            <li key={session.id}>
              <div>
                <strong>{session.current ? c.current : c.other}</strong>
                <p>
                  {c.created}:{' '}
                  <time dateTime={session.created_at}>
                    {new Date(session.created_at).toLocaleString(language)}
                  </time>
                  <br />
                  {c.seen}:{' '}
                  <time dateTime={session.last_seen_at}>
                    {new Date(session.last_seen_at).toLocaleString(language)}
                  </time>
                </p>
              </div>
              {!session.current && (
                <button
                  className="button secondary"
                  disabled={busy || !online}
                  onClick={() =>
                    void perform(async () => {
                      await write(`/sessions/${session.id}`, 'DELETE');
                      if (alive()) await load();
                    })
                  }
                >
                  {c.revoke}
                </button>
              )}
            </li>
          ))}
        </ul>
        <div className="form-actions">
          <button
            className="text-button"
            disabled={busy || !online}
            onClick={() => void perform(load)}
          >
            {c.reload}
          </button>
          <button
            className="button secondary"
            disabled={busy || !online}
            onClick={() => choose('all')}
          >
            {c.all}
          </button>
        </div>
      </section>
      <section aria-labelledby="account-data-title">
        <h2 id="account-data-title">{c.data}</h2>
        <p className="muted">{c.dataIntro}</p>
        {pending && <p>{c.pending}</p>}
        <div className="form-actions">
          <button
            className="button secondary"
            disabled={busy || !online}
            onClick={() => choose('export')}
          >
            {c.export}
          </button>
          <button
            className="text-button danger-text"
            disabled={busy || !online}
            onClick={() => choose('delete')}
          >
            {c.remove}
          </button>
        </div>
      </section>
      {action && (
        <section className="account-confirm" aria-labelledby="account-action-title">
          <h3 id="account-action-title" tabIndex={-1} ref={actionRef}>
            {action === 'all' ? c.all : action === 'delete' ? c.remove : c.export}
          </h3>
          {action === 'all' ? (
            <>
              <p>{c.allNotice}</p>
              <button
                className="button primary"
                disabled={busy || !online}
                onClick={() =>
                  void perform(async () => {
                    await controller.accountAction(
                      owner,
                      () => write('/sessions', 'DELETE'),
                      'revoked',
                    );
                  })
                }
              >
                {c.confirmAll}
              </button>
            </>
          ) : (
            <>
              {action === 'delete' && (
                <>
                  <p>{c.deletion}</p>
                  <p className="muted">{c.retention}</p>
                </>
              )}
              {!fresh ? (
                <>
                  <p>{c.codeNotice}</p>
                  {challenge && (
                    <form onSubmit={verify}>
                      <label>
                        {c.code}
                        <input
                          ref={codeRef}
                          type="text"
                          inputMode="numeric"
                          autoComplete="one-time-code"
                          pattern="[0-9]{8}"
                          maxLength={8}
                          required
                          value={code}
                          onChange={(e) => setCode(e.target.value)}
                        />
                      </label>
                      <button className="button primary" disabled={busy || !online}>
                        {busy ? c.busy : c.verify}
                      </button>
                    </form>
                  )}
                  <button
                    className="button secondary"
                    disabled={busy || !online || resendAt > now}
                    onClick={() => void perform(send)}
                  >
                    {challenge ? c.resend : c.send}
                    {resendAt > now ? ` (${Math.ceil((resendAt - now) / 1000)})` : ''}
                  </button>
                </>
              ) : (
                <>
                  <p>{c.verified}</p>
                  {action === 'export' ? (
                    <button
                      className="button primary"
                      disabled={busy || !online}
                      onClick={() => void perform(download)}
                    >
                      {c.export}
                    </button>
                  ) : (
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        if (!confirmed) return;
                        void perform(async () => {
                          await controller.accountAction(
                            owner,
                            () => write('/account', 'DELETE', { confirmation: 'delete' }),
                            'deleted',
                          );
                        });
                      }}
                    >
                      <label className="reminder-check">
                        <input
                          type="checkbox"
                          required
                          checked={confirmed}
                          onChange={(e) => setConfirmed(e.target.checked)}
                        />
                        {c.agree}
                      </label>
                      <button
                        className="button primary danger-button"
                        disabled={busy || !online || !confirmed}
                      >
                        {c.confirmRemove}
                      </button>
                    </form>
                  )}
                </>
              )}
            </>
          )}
          <button className="text-button" disabled={busy} onClick={() => choose(null)}>
            {c.cancel}
          </button>
        </section>
      )}
      {!online && <p>{c.offline}</p>}
      <p role="alert">{error}</p>
      <p aria-live="polite">{notice}</p>
    </div>
  );
}
