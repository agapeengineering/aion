import { useEffect, useState, useRef, type FormEvent } from 'react';
import type { Language } from './i18n';
import { request, ApiError } from './api';

type Preferences = {
  enabled: boolean;
  frequency: 'daily' | 'weekly';
  timezone: string;
  send_time: string;
  weekday: number;
  language: Language;
  include_phrase: boolean;
  consent: boolean;
  notice_version: '2026-10-18';
};
type Snapshot = {
  user_id: string;
  revision: number;
  preferences: Preferences | null;
  next_due_at: string | null;
  suppressed: boolean;
  available: boolean;
  phrase_available: boolean;
};
const words = {
  en: {
    title: 'A moment, each week.',
    intro:
      'An optional email with your calendar and a little perspective. Reminders stay off until you choose to subscribe.',
    enabled: 'Receive email reminders',
    frequency: 'Frequency',
    weekly: 'Weekly',
    daily: 'Daily',
    day: 'Day',
    time: 'Local send time',
    zone: 'Time zone',
    language: 'Email language',
    phrase: 'Include the weekly passage',
    waiting:
      'No approved passage is available for the scheduled week. You can receive calendar-only reminders.',
    notice:
      'Emails use the calendar saved to your account. Your email address and message content are shared with our email provider, Resend. Your chosen lifespan is an assumption, not a prediction. Signing out does not unsubscribe you.',
    consent:
      'I agree to receive these reminders at the schedule above. I can pause or unsubscribe at any time.',
    save: 'Save reminder preferences',
    pause: 'Pause reminders',
    off: 'Reminders are off.',
    saved: 'Reminder preferences saved.',
    busy: 'Please wait…',
    failed:
      'Could not save or refresh reminders. Your previous saved schedule is unchanged unless the server confirms otherwise.',
    conflict:
      'These preferences changed elsewhere. Load the latest settings before making another change.',
    reload: 'Load latest preferences',
    profile: 'Save a calendar to your account before subscribing.',
    unavailable: 'Scheduled sending is not enabled on this server yet.',
    suppressed:
      'Email delivery to this address is paused after a delivery issue. Contact support before subscribing again.',
    next: 'Next scheduled email',
    unknown:
      'Quoted passages are not ready for that week. Turn off the passage option to receive calendar-only reminders.',
    consentRequired: 'Please confirm your consent before subscribing.',
    offline: 'Reconnect to change reminder preferences.',
  },
  es: {
    title: 'Un momento, cada semana.',
    intro:
      'Un correo opcional con tu calendario y un poco de perspectiva. Los recordatorios siguen desactivados hasta que decidas suscribirte.',
    enabled: 'Recibir recordatorios por correo',
    frequency: 'Frecuencia',
    weekly: 'Semanal',
    daily: 'Diaria',
    day: 'Día',
    time: 'Hora local de envío',
    zone: 'Zona horaria',
    language: 'Idioma del correo',
    phrase: 'Incluir el pasaje de la semana',
    waiting:
      'No hay un pasaje aprobado para la semana programada. Puedes recibir solo el calendario.',
    notice:
      'Los correos usan el calendario guardado en tu cuenta. Tu dirección y el contenido se comparten con nuestro proveedor de correo, Resend. El horizonte elegido es una suposición, no una predicción. Cerrar sesión no cancela los recordatorios.',
    consent:
      'Acepto recibir estos recordatorios con el horario indicado. Puedo pausarlos o cancelar la suscripción cuando quiera.',
    save: 'Guardar preferencias',
    pause: 'Pausar recordatorios',
    off: 'Los recordatorios están desactivados.',
    saved: 'Preferencias guardadas.',
    busy: 'Espera un momento…',
    failed:
      'No se pudieron guardar o actualizar los recordatorios. El horario anterior sigue vigente salvo confirmación del servidor.',
    conflict:
      'Las preferencias cambiaron en otro dispositivo. Carga los ajustes actuales antes de modificarlos.',
    reload: 'Cargar preferencias actuales',
    profile: 'Guarda un calendario en tu cuenta antes de suscribirte.',
    unavailable: 'El envío programado aún no está activado en este servidor.',
    suppressed:
      'El envío a esta dirección está pausado por un problema de entrega. Contacta con soporte antes de volver a suscribirte.',
    next: 'Próximo correo programado',
    unknown:
      'Los pasajes no están listos para esa semana. Desactiva esa opción para recibir solo el calendario.',
    consentRequired: 'Confirma tu consentimiento antes de suscribirte.',
    offline: 'Vuelve a conectarte para cambiar las preferencias.',
  },
};
function defaults(language: Language): Preferences {
  return {
    enabled: false,
    frequency: 'weekly',
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
    send_time: '09:00',
    weekday: 6,
    language,
    include_phrase: true,
    consent: false,
    notice_version: '2026-10-18',
  };
}
export function ReminderPanel({
  owner,
  language,
  hasProfile,
  checkAccount,
}: {
  owner: string;
  language: Language;
  hasProfile: boolean;
  checkAccount: () => Promise<void>;
}) {
  const c = words[language];
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [draft, setDraft] = useState(() => defaults(language));
  const [busy, setBusy] = useState(true),
    [error, setError] = useState(''),
    [saved, setSaved] = useState(false);
  const generation = useRef(0);
  const online = navigator.onLine;
  const days =
    language === 'en'
      ? ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
      : ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];
  function apply(value: Snapshot) {
    if (value.user_id !== owner) throw new Error('Account mismatch');
    setSnapshot(value);
    setDraft(
      value.preferences
        ? { ...value.preferences, consent: false }
        : { ...defaults(language), include_phrase: value.phrase_available },
    );
  }
  function failure(value: unknown) {
    const code = value instanceof ApiError ? value.code : '';
    setError(
      code === 'reminder_conflict'
        ? c.conflict
        : code === 'phrase_not_ready'
          ? c.unknown
          : code === 'consent_required'
            ? c.consentRequired
            : c.failed,
    );
    if (value instanceof ApiError && (value.status === 401 || code === 'account_changed'))
      void checkAccount();
  }
  async function load() {
    const current = ++generation.current;
    setBusy(true);
    setError('');
    setSaved(false);
    try {
      const value = await request<Snapshot>('/reminder-preferences', {
        headers: { 'X-Aion-Account': owner },
      });
      if (generation.current === current) apply(value);
    } catch (value) {
      if (generation.current === current) failure(value);
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }
  useEffect(() => {
    void load();
    return () => {
      generation.current++;
    };
  }, [owner, hasProfile]);
  async function save(event?: FormEvent, pause = false) {
    event?.preventDefault();
    if (!snapshot || !online) return;
    const current = generation.current;
    setBusy(true);
    setError('');
    setSaved(false);
    try {
      const csrf = await request<{ csrf_token: string }>('/auth/csrf');
      if (generation.current !== current) return;
      const data =
        pause && snapshot.preferences
          ? { ...snapshot.preferences, enabled: false, consent: false }
          : draft;
      const value = await request<Snapshot>('/reminder-preferences', {
        method: 'PUT',
        body: data,
        headers: {
          'X-Aion-Account': owner,
          'X-CSRF-Token': csrf.csrf_token,
          'If-Match': `"reminders-${snapshot.revision}"`,
        },
      });
      if (generation.current === current) {
        apply(value);
        setSaved(true);
      }
    } catch (value) {
      if (generation.current === current) failure(value);
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }
  function edit(patch: Partial<Preferences>) {
    setDraft((v) => ({ ...v, ...patch }));
    setSaved(false);
  }
  return (
    <section className="reminder-panel" aria-labelledby="reminder-title">
      <h2 id="reminder-title">{c.title}</h2>
      <p className="muted">{c.intro}</p>
      {!hasProfile && <p>{c.profile}</p>}
      {snapshot && !snapshot.available && <p>{c.unavailable}</p>}
      {snapshot?.suppressed && <p>{c.suppressed}</p>}
      {snapshot && !error && (
        <p aria-live="polite">
          {snapshot.preferences?.enabled
            ? snapshot.next_due_at &&
              `${c.next}: ${new Intl.DateTimeFormat(language, { dateStyle: 'full', timeStyle: 'short', timeZone: snapshot.preferences.timezone }).format(new Date(snapshot.next_due_at))} (${snapshot.preferences.timezone})`
            : c.off}
        </p>
      )}
      {snapshot && (
        <form onSubmit={(e) => void save(e)}>
          <fieldset
            disabled={busy || !online || !hasProfile || !snapshot.available || snapshot.suppressed}
          >
            <legend className="sr-only">{c.title}</legend>
            <label className="reminder-check">
              <input
                type="checkbox"
                checked={draft.enabled}
                onChange={(e) => edit({ enabled: e.target.checked, consent: false })}
              />
              {c.enabled}
            </label>
            <div className="reminder-fields">
              <label htmlFor="reminder-frequency">
                {c.frequency}
                <select
                  id="reminder-frequency"
                  value={draft.frequency}
                  onChange={(e) => edit({ frequency: e.target.value as Preferences['frequency'] })}
                >
                  <option value="weekly">{c.weekly}</option>
                  <option value="daily">{c.daily}</option>
                </select>
              </label>
              {draft.frequency === 'weekly' && (
                <label htmlFor="reminder-day">
                  {c.day}
                  <select
                    id="reminder-day"
                    value={draft.weekday}
                    onChange={(e) => edit({ weekday: Number(e.target.value) })}
                  >
                    {days.map((day, i) => (
                      <option key={day} value={i}>
                        {day}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <label>
                {c.time}
                <input
                  type="time"
                  required
                  value={draft.send_time}
                  onChange={(e) => edit({ send_time: e.target.value })}
                />
              </label>
              <label>
                {c.zone}
                <input
                  required
                  maxLength={64}
                  list="reminder-zones"
                  value={draft.timezone}
                  onChange={(e) => edit({ timezone: e.target.value })}
                />
                <datalist id="reminder-zones">
                  {['UTC', ...Intl.supportedValuesOf('timeZone')].map((zone) => (
                    <option key={zone} value={zone} />
                  ))}
                </datalist>
              </label>
              <label htmlFor="reminder-language">
                {c.language}
                <select
                  id="reminder-language"
                  value={draft.language}
                  onChange={(e) => edit({ language: e.target.value as Language })}
                >
                  <option value="en">English</option>
                  <option value="es">Español</option>
                </select>
              </label>
            </div>
            <label className="reminder-check">
              <input
                type="checkbox"
                disabled={!snapshot.phrase_available && !draft.include_phrase}
                checked={draft.include_phrase}
                onChange={(e) => edit({ include_phrase: e.target.checked })}
              />
              {c.phrase}
            </label>
            {!snapshot.phrase_available && <p className="muted">{c.waiting}</p>}
            <p className="account-consent muted">{c.notice}</p>
            {draft.enabled && (
              <label className="reminder-check">
                <input
                  type="checkbox"
                  required
                  checked={draft.consent}
                  onChange={(e) => edit({ consent: e.target.checked })}
                />
                {c.consent}
              </label>
            )}
            <div className="form-actions">
              <button className="button primary">{busy ? c.busy : c.save}</button>
            </div>
          </fieldset>
          {snapshot.preferences?.enabled && (
            <button
              type="button"
              className="button secondary"
              disabled={busy || !online}
              onClick={() => void save(undefined, true)}
            >
              {c.pause}
            </button>
          )}
        </form>
      )}
      {!online && <p>{c.offline}</p>}
      <p aria-live="polite">{saved ? c.saved : ''}</p>
      <p role="alert">{error}</p>
      {error && (
        <button className="text-button" disabled={busy || !online} onClick={() => void load()}>
          {c.reload}
        </button>
      )}
    </section>
  );
}
