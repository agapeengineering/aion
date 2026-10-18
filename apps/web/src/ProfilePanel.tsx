import { useState } from 'react';
import { unitNames, type Language } from './i18n';
import type { Settings } from './storage';
import type { ProfileSync, SyncState } from './profile-sync';

export const syncWords = {
  en: {
    guest: 'Saved on this device',
    checking: 'Checking your account…',
    choice: 'Choose where your calendar lives',
    saved: 'Saved to your account',
    pending: 'Changes pending sync',
    offline: 'Offline — viewing your cached calendar',
    error: 'Could not refresh your account. Cached changes are preserved.',
    conflict: 'This calendar changed on another device',
    expired: 'Your session ended. Sign in again to sync.',
    cache:
      'Account storage is unavailable or protected. Pending changes may exist only in this tab; keep it open until sync succeeds.',
    heading: 'Your calendar, across devices.',
    privacy:
      'Saving sends your birth date, lifespan and preferences to your account. Reminders stay off.',
    device: 'This device',
    account: 'Account',
    empty: 'No saved calendar',
    birth: 'Birth date',
    years: 'Chosen lifespan',
    preferences: 'Language / unit / remaining',
    hidden: 'hidden',
    shown: 'shown',
    use: 'Use account calendar',
    replace: 'Replace account with this device',
    confirm: 'Confirm replacement',
    upload: 'Save this device to my account',
    setup: 'Create account calendar',
    local: 'Keep using this device only',
    compare: 'Choose the calendar you want to use. Your device’s local copy stays separate.',
    keep: 'Keep account version',
    reapply: 'Reapply my device changes',
    retry: 'Refresh / retry sync',
    reset: 'Reset account calendar',
    resetText:
      'Resetting removes your saved calendar from the account and other devices after they refresh. Your guest calendar is preserved. This does not delete your account.',
    discard:
      'There are unsynced edits. Signing out discards this browser’s pending account changes.',
    discardOut: 'Discard pending edits and sign out',
    cancel: 'Cancel',
  },
  es: {
    guest: 'Guardado en este dispositivo',
    checking: 'Consultando tu cuenta…',
    choice: 'Elige dónde guardar tu calendario',
    saved: 'Guardado en tu cuenta',
    pending: 'Cambios pendientes de sincronizar',
    offline: 'Sin conexión — mostrando el calendario en caché',
    error: 'No se pudo actualizar tu cuenta. Los cambios en caché se conservan.',
    conflict: 'El calendario cambió en otro dispositivo',
    expired: 'Tu sesión terminó. Inicia sesión para sincronizar.',
    cache:
      'El almacenamiento de la cuenta no está disponible o está protegido. Los cambios pendientes pueden estar solo en esta pestaña; mantenla abierta hasta sincronizarlos.',
    heading: 'Tu calendario, entre dispositivos.',
    privacy:
      'Guardar envía tu fecha de nacimiento, horizonte y preferencias a tu cuenta. Los recordatorios siguen desactivados.',
    device: 'Este dispositivo',
    account: 'Cuenta',
    empty: 'Sin calendario guardado',
    birth: 'Fecha de nacimiento',
    years: 'Horizonte elegido',
    preferences: 'Idioma / unidad / restante',
    hidden: 'oculto',
    shown: 'visible',
    use: 'Usar calendario de la cuenta',
    replace: 'Reemplazar la cuenta con este dispositivo',
    confirm: 'Confirmar reemplazo',
    upload: 'Guardar este dispositivo en mi cuenta',
    setup: 'Crear calendario de cuenta',
    local: 'Seguir solo en este dispositivo',
    compare: 'Elige el calendario que quieres usar. La copia local se conserva por separado.',
    keep: 'Conservar versión de la cuenta',
    reapply: 'Volver a aplicar mis cambios',
    retry: 'Actualizar / reintentar',
    reset: 'Reiniciar calendario de la cuenta',
    resetText:
      'Reiniciar elimina el calendario guardado de la cuenta y de otros dispositivos cuando se actualicen. Tu calendario local se conserva. Esto no elimina tu cuenta.',
    discard:
      'Hay cambios sin sincronizar. Cerrar sesión descarta los cambios pendientes de esta cuenta en este navegador.',
    discardOut: 'Descartar cambios y cerrar sesión',
    cancel: 'Cancelar',
  },
};
export function SyncStatus({ state, language }: { state: SyncState; language: Language }) {
  const c = syncWords[language];
  return (
    <div className="sync-status" aria-live="polite">
      <p>
        {state.phase === 'saved' && !state.snapshot?.profile && !state.pending
          ? c.empty
          : c[state.phase]}
      </p>
      {state.cacheIssue && <p className="storage-warning">{c.cache}</p>}
    </div>
  );
}
function Summary({
  value,
  label,
  language,
}: {
  value: Settings | null;
  label: string;
  language: Language;
}) {
  const c = syncWords[language];
  return (
    <section className="profile-summary">
      <h3>{label}</h3>
      {value ? (
        <dl>
          <dt>{c.birth}</dt>
          <dd>{value.birthDate}</dd>
          <dt>{c.years}</dt>
          <dd>{value.lifespanYears}</dd>
          <dt>{c.preferences}</dt>
          <dd>
            {value.language.toUpperCase()} / {unitNames[language][value.unit]} /{' '}
            {value.hideRemaining ? c.hidden : c.shown}
          </dd>
        </dl>
      ) : (
        <p>{c.empty}</p>
      )}
    </section>
  );
}
export function ProfilePanel({
  controller,
  state,
  guest,
  language,
  done,
}: {
  controller: ProfileSync;
  state: SyncState;
  guest: Settings | null;
  language: Language;
  done: () => void;
}) {
  const c = syncWords[language];
  const [replace, setReplace] = useState(false);
  const current = state.conflict ?? state.snapshot;
  const different = Boolean(
    guest && current?.profile && JSON.stringify(guest) !== JSON.stringify(current.profile),
  );
  const noCalendar = current && !current.profile && !guest && !state.pending;
  const title = state.conflict
    ? c.conflict
    : noCalendar
      ? language === 'en'
        ? 'Create your calendar.'
        : 'Crea tu calendario.'
      : !state.selected && guest && !current?.profile
        ? language === 'en'
          ? 'Keep your calendar with you.'
          : 'Lleva tu calendario contigo.'
        : different && !state.selected
          ? language === 'en'
            ? 'Which calendar would you like to use?'
            : '¿Qué calendario quieres usar?'
          : language === 'en'
            ? 'Your calendar'
            : 'Tu calendario';
  return (
    <section className="profile-panel">
      <h2>{title}</h2>
      {(state.selected ||
        state.busy ||
        state.phase === 'error' ||
        state.conflict ||
        state.cacheIssue) && <SyncStatus state={state} language={language} />}
      {!state.selected && !state.conflict && (
        <p className="muted">
          {noCalendar
            ? language === 'en'
              ? 'Enter your birth date and chosen lifespan. Your calendar will sync across your devices.'
              : 'Introduce tu fecha de nacimiento y horizonte de vida. Tu calendario se sincronizará entre dispositivos.'
            : c.privacy}
        </p>
      )}
      {state.conflict ? (
        <>
          <div className="profile-comparison">
            <Summary
              value={state.pending?.profile ?? state.snapshot?.profile ?? null}
              label={c.device}
              language={language}
            />
            <Summary value={state.conflict.profile} label={c.account} language={language} />
          </div>
          <div className="form-actions">
            <button
              className="button primary"
              disabled={state.busy}
              onClick={() => controller.keepServer()}
            >
              {c.keep}
            </button>
            {state.pending && (
              <button
                className="button secondary"
                disabled={state.busy}
                onClick={() => controller.reapply()}
              >
                {c.reapply}
              </button>
            )}
          </div>
        </>
      ) : !state.selected && current ? (
        <>
          {different ? (
            <>
              <p>{c.compare}</p>
              <div className="profile-comparison">
                <Summary value={guest} label={c.device} language={language} />
                <Summary value={current.profile} label={c.account} language={language} />
              </div>
            </>
          ) : guest && !current.profile ? (
            <Summary value={guest} label={c.device} language={language} />
          ) : null}
          <div className="form-actions">
            {current.profile && (
              <button
                className="button primary"
                disabled={state.busy}
                onClick={() => {
                  controller.chooseAccount();
                  done();
                }}
              >
                {c.use}
              </button>
            )}
            {guest && (!current.profile || different) && (
              <button
                className="button secondary"
                disabled={state.busy}
                onClick={() => {
                  if (current.profile && !replace) {
                    setReplace(true);
                    return;
                  }
                  controller.importGuest();
                  setReplace(false);
                }}
              >
                {current.profile ? (replace ? c.confirm : c.replace) : c.upload}
              </button>
            )}
            {!current.profile && (
              <button
                className="button primary"
                disabled={state.busy}
                onClick={() => {
                  controller.chooseSetup();
                  done();
                }}
              >
                {c.setup}
              </button>
            )}
            <button
              className="text-button"
              disabled={state.busy}
              onClick={() => {
                controller.useGuest();
                done();
              }}
            >
              {c.local}
            </button>
            {replace && (
              <button className="text-button" onClick={() => setReplace(false)}>
                {c.cancel}
              </button>
            )}
          </div>
        </>
      ) : state.selected ? (
        <Summary
          value={state.pending?.profile ?? current?.profile ?? null}
          label={c.account}
          language={language}
        />
      ) : null}
      {state.selected && current && !current.profile && !state.pending && (
        <button
          className="button primary"
          onClick={() => {
            controller.chooseSetup();
            done();
          }}
        >
          {c.setup}
        </button>
      )}
      {(state.phase === 'error' || state.cacheIssue) && (
        <button
          className="text-button"
          disabled={state.busy || !navigator.onLine}
          onClick={() => void controller.refresh()}
        >
          {c.retry}
        </button>
      )}
    </section>
  );
}
