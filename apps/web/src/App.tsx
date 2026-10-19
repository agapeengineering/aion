import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type FormEvent,
  type MouseEvent,
} from 'react';
import {
  calculate,
  localClock,
  advanceDisplay,
  units,
  type DisplayEvent,
  type DisplayState,
  type Snapshot,
  type Unit,
  type CalculationError,
} from '@aion/calendar';
import { copy, phrases, unitNames, type Language } from './i18n';
import {
  browserStorage,
  decodeSettings,
  loadSettings,
  saveSettings,
  STORAGE_KEY,
  type Settings,
  type StorageStatus,
} from './storage';
import { LifeGrid } from './Grid';
import { createWallpaper } from './export';
import { Account, accountsEnabled } from './Account';
import { pageFromPath, pagePath, type Page } from './routes';
import { useProfileSync } from './use-profile-sync';
import { SyncStatus, syncWords } from './ProfilePanel';

function Arrow({ down = false }: { down?: boolean }) {
  return (
    <svg aria-hidden="true" width="17" height="17" viewBox="0 0 24 24" fill="none">
      <path
        d={down ? 'M12 4v15m-6-6 6 6 6-6M4 21h16' : 'M5 19 19 5M5 5h14v14'}
        stroke="currentColor"
        strokeWidth="1.5"
      />
    </svg>
  );
}
function Modal({
  title,
  closeLabel,
  onClose,
  children,
}: {
  title: string;
  closeLabel: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = ref.current!;
    el.showModal();
    return () => el.close();
  }, []);
  return (
    <dialog
      className="modal"
      ref={ref}
      aria-labelledby="modal-title"
      onClose={() => {
        if (!ref.current?.open) onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) ref.current?.close();
      }}
    >
      <div className="modal-inner">
        <div className="modal-heading">
          <h2 id="modal-title">{title}</h2>
          <button
            className="icon-button"
            aria-label={closeLabel}
            onClick={() => ref.current?.close()}
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}
function errorMessage(error: CalculationError['error'], language: Language) {
  const c = copy[language];
  return {
    INVALID_CLOCK: c.clockInvalid,
    INVALID_BIRTH_DATE: c.birthInvalid,
    FUTURE_BIRTH_DATE: c.birthFuture,
    INVALID_LIFESPAN: c.lifespanInvalid,
    HORIZON_OUT_OF_RANGE: c.rangeInvalid,
  }[error.code];
}
function SettingsForm({
  initial,
  language,
  onSave,
  onCancel,
}: {
  initial: Settings | null;
  language: Language;
  onSave: (settings: Settings) => void;
  onCancel?: () => void;
}) {
  const c = copy[language],
    [birth, setBirth] = useState(initial?.birthDate ?? ''),
    [lifespan, setLifespan] = useState(String(initial?.lifespanYears ?? 90));
  const [error, setError] = useState<CalculationError['error'] | null>(null);
  const birthRef = useRef<HTMLInputElement>(null),
    lifeRef = useRef<HTMLInputElement>(null);
  function submit(e: FormEvent) {
    e.preventDefault();
    const n = lifespan.trim() === '' ? NaN : Number(lifespan);
    const result = calculate({ birthDate: birth, lifespanYears: n, clock: localClock() });
    if ('error' in result) {
      setError(result.error);
      (result.error.field === 'birthDate' ? birthRef : lifeRef).current?.focus();
      return;
    }
    setError(null);
    onSave({
      version: 1,
      birthDate: birth,
      lifespanYears: n,
      language,
      unit: initial?.unit ?? 'weeks',
      hideRemaining: initial?.hideRemaining ?? false,
    });
  }
  return (
    <form onSubmit={submit} noValidate className="settings-form">
      <label htmlFor="birth-date">{c.birth}</label>
      <input
        ref={birthRef}
        id="birth-date"
        name="birthDate"
        type="date"
        min="0001-01-01"
        max={localClock().date}
        value={birth}
        required
        aria-invalid={error?.field === 'birthDate'}
        aria-describedby={error?.field === 'birthDate' ? 'form-error' : undefined}
        onChange={(e) => setBirth(e.target.value)}
      />
      <label htmlFor="lifespan">
        {c.horizon} <span className="label-unit">/ {c.yearsLabel}</span>
      </label>
      <input
        ref={lifeRef}
        id="lifespan"
        name="lifespan"
        type="number"
        min="1"
        step="1"
        inputMode="numeric"
        value={lifespan}
        required
        aria-invalid={error?.field === 'lifespanYears'}
        aria-describedby={
          error?.field === 'lifespanYears' ? 'horizon-hint form-error' : 'horizon-hint'
        }
        onChange={(e) => setLifespan(e.target.value)}
      />
      <p id="horizon-hint" className="caption">
        {c.assumption}
      </p>
      {error && (
        <p className="field-error" id="form-error" role="alert">
          {errorMessage(error, language)}
        </p>
      )}
      <div className="form-actions">
        {onCancel && (
          <button type="button" className="button secondary" onClick={onCancel}>
            {c.cancel}
          </button>
        )}
        <button className="button primary" type="submit">
          {initial ? c.save : c.see}
          <Arrow />
        </button>
      </div>
    </form>
  );
}
function useLifeClock(settings: Settings) {
  const getSnapshot = useCallback(
    () =>
      calculate({
        birthDate: settings.birthDate,
        lifespanYears: settings.lifespanYears,
        clock: localClock(),
      }),
    [settings.birthDate, settings.lifespanYears],
  );
  const [state, setState] = useState<DisplayState | null>(() => {
    const s = getSnapshot();
    return 'error' in s ? null : advanceDisplay(null, 'load', s);
  });
  const [error, setError] = useState<CalculationError['error'] | null>(null);
  const dispatch = useCallback(
    (event: DisplayEvent) => {
      const s = getSnapshot();
      if ('error' in s) {
        setError(s.error);
        return;
      }
      setError(null);
      setState((prev) => advanceDisplay(prev, event, s));
    },
    [getSnapshot],
  );
  useEffect(() => {
    const id = window.setInterval(() => {
      if (document.visibilityState === 'visible') dispatch('tick');
    }, 1000);
    const visibility = () => dispatch(document.visibilityState === 'hidden' ? 'hide' : 'show');
    const focus = () => dispatch('show');
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('focus', focus);
    window.addEventListener('pageshow', focus);
    return () => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('focus', focus);
      window.removeEventListener('pageshow', focus);
    };
  }, [dispatch]);
  return { state, error, dispatch };
}
function CalendarView({
  settings,
  language,
  update,
  onExport,
}: {
  settings: Settings;
  language: Language;
  update: (s: Settings) => void;
  onExport: () => void;
}) {
  const { state, error, dispatch } = useLifeClock(settings),
    c = copy[language],
    [phraseOffset, setPhraseOffset] = useState(0);
  const fmt = useMemo(() => new Intl.NumberFormat(language), [language]);
  if (!state) return <p role="alert">{c.clockInvalid}</p>;
  const { live, subday, paused } = state,
    isSubday = (unit: Unit) => ['hours', 'minutes', 'seconds'].includes(unit);
  const totals = (direction: 'lived' | 'remaining', unit: Unit) =>
    (isSubday(unit) ? subday : live)[direction][unit];
  const phraseIndex = (Math.floor(live.lived.days / 7) + phraseOffset) % phrases.length;
  return (
    <div id="calendar" tabIndex={-1} className="calendar-view">
      {error && (
        <p role="alert" className="notice">
          {errorMessage(error, language)}
        </p>
      )}
      {live.horizonState !== 'before' && (
        <p className="notice horizon-notice" role="status">
          {c.horizonReached}
        </p>
      )}
      <div className="calendar-layout">
        <LifeGrid
          birthDate={settings.birthDate}
          grid={live.grid}
          language={language}
          hideRemaining={settings.hideRemaining}
        />
        <aside className="calendar-aside" aria-label={c.calendar}>
          <section className="summary-block">
            <span className="eyebrow">
              {unitNames[language][settings.unit]} · {language === 'es' ? 'Tiempo vivido' : c.lived}
            </span>
            <p className="summary-number" data-testid="primary-lived">
              {fmt.format(totals('lived', settings.unit))}
            </p>
            <p className="caption">{c.livedStory}</p>
          </section>
          {!settings.hideRemaining && (
            <section className="summary-block">
              <span className="eyebrow">
                {unitNames[language][settings.unit]} · {c.remaining}
              </span>
              <p className="summary-number" data-testid="primary-remaining">
                {fmt.format(totals('remaining', settings.unit))}
              </p>
              <p className="caption">
                {c.within}: {settings.lifespanYears} {c.yearsLabel}.
              </p>
            </section>
          )}
          <section className="summary-block present-block">
            <span className="eyebrow">
              <span className="present-dot" />
              {c.present}
            </span>
            <p className="present-copy">{c.presentText}</p>
            {live.grid.currentStart && (
              <p className="caption mono">
                {live.grid.currentStart}
                <br />→ {live.grid.currentEndExclusive}
              </p>
            )}
            <button className="button secondary export-action" onClick={onExport}>
              {c.export}
              <Arrow />
            </button>
          </section>
        </aside>
      </div>
      <section className="statistics" aria-labelledby="statistics-title">
        <div className="statistics-heading">
          <div>
            <span className="eyebrow">02 / {c.calendar}</span>
            <h2 id="statistics-title">{c.numbers}</h2>
            <p className="caption">{c.figures}</p>
          </div>
          <div className="stats-actions">
            <label className="unit-select">
              {c.primary}
              <select
                value={settings.unit}
                onChange={(e) => update({ ...settings, unit: e.target.value as Unit })}
              >
                {units.map((unit) => (
                  <option key={unit} value={unit}>
                    {unitNames[language][unit]}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="text-button pause-button"
              aria-pressed={paused}
              onClick={() => dispatch(paused ? 'resume' : 'pause')}
            >
              {paused ? '▶' : 'Ⅱ'} {paused ? c.resume : c.pause}
            </button>
          </div>
        </div>
        <label className="toggle-row">
          <input
            type="checkbox"
            checked={settings.hideRemaining}
            onChange={(e) => update({ ...settings, hideRemaining: e.target.checked })}
          />
          <span>{c.hide}</span>
        </label>
        {paused && (
          <p className="caption pause-message" role="status">
            {c.paused}
          </p>
        )}
        <div className="table-scroll">
          <table aria-live="off">
            <thead>
              <tr>
                <th scope="col">{language === 'en' ? 'Unit' : 'Unidad'}</th>
                <th scope="col">{language === 'es' ? 'Tiempo vivido' : c.lived}</th>
                {!settings.hideRemaining && <th scope="col">{c.remaining}</th>}
              </tr>
            </thead>
            <tbody>
              {units.map((unit) => (
                <tr key={unit} className={settings.unit === unit ? 'selected-unit' : ''}>
                  <th scope="row">
                    {unitNames[language][unit]}{' '}
                    {isSubday(unit) && (
                      <span className="approx-marker" aria-label={c.approx}>
                        ≈
                      </span>
                    )}
                  </th>
                  <td data-testid={`lived-${unit}`}>{fmt.format(totals('lived', unit))}</td>
                  {!settings.hideRemaining && (
                    <td data-testid={`remaining-${unit}`}>
                      {fmt.format(totals('remaining', unit))}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="caption counter-caveat">
          {c.caveat} {c.calendarCaveat}
        </p>
      </section>
      <section className="reflection" aria-labelledby="reflection-title">
        <div className="section-heading">
          <h2 id="reflection-title" className="eyebrow">
            03 / {c.reflection}
          </h2>
          <button
            className="icon-button thought-button"
            aria-label={c.nextThought}
            onClick={() => setPhraseOffset((x) => x + 1)}
          >
            ↗
          </button>
        </div>
        <p key={phraseIndex} className="reflection-quote">
          {phrases[phraseIndex][language]}
        </p>
        <span className="reflection-rule" />
      </section>
    </div>
  );
}
function ExportDialog({
  settings,
  language,
  onClose,
}: {
  settings: Settings;
  language: Language;
  onClose: () => void;
}) {
  const c = copy[language],
    [format, setFormat] = useState<'phone' | 'desktop'>('phone'),
    [url, setUrl] = useState(''),
    [failed, setFailed] = useState(false),
    [retry, setRetry] = useState(0);
  const [reference] = useState(() => {
    const clock = localClock();
    return { clock, result: calculate({ ...settings, clock }) };
  });
  useEffect(() => {
    let cancelled = false,
      resource = '';
    setUrl('');
    setFailed(false);
    if ('error' in reference.result) {
      setFailed(true);
      return;
    }
    void createWallpaper({
      snapshot: reference.result,
      referenceDate: reference.clock.date,
      lifespanYears: settings.lifespanYears,
      language,
      unit: settings.unit,
      hideRemaining: settings.hideRemaining,
      format,
      phraseIndex: Math.floor(reference.result.lived.days / 7) % phrases.length,
    })
      .then((blob) => {
        if (!cancelled) {
          resource = URL.createObjectURL(blob);
          setUrl(resource);
        }
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
      if (resource) URL.revokeObjectURL(resource);
    };
  }, [
    format,
    settings.lifespanYears,
    settings.unit,
    settings.hideRemaining,
    language,
    reference,
    retry,
  ]);
  return (
    <Modal title={c.exportTitle} closeLabel={c.close} onClose={onClose}>
      <p className="muted">{c.exportText}</p>
      <div className="format-switch" role="group" aria-label={c.export}>
        <button
          className={format === 'phone' ? 'active' : ''}
          aria-pressed={format === 'phone'}
          onClick={() => setFormat('phone')}
        >
          {c.phone} · 1440 × 2560
        </button>
        <button
          className={format === 'desktop' ? 'active' : ''}
          aria-pressed={format === 'desktop'}
          onClick={() => setFormat('desktop')}
        >
          {c.desktop} · 2560 × 1600
        </button>
      </div>
      <div className={`wallpaper-preview ${format}`}>
        {url ? (
          <img src={url} alt={`${c.export} · ${reference.clock.date}`} />
        ) : (
          <p role="status">{failed ? c.exportError : c.preparing}</p>
        )}
      </div>
      <p className="caption">
        {c.discreet} {c.native}
      </p>
      {failed && (
        <button className="button secondary" onClick={() => setRetry((x) => x + 1)}>
          {language === 'en' ? 'Try again' : 'Intentar de nuevo'}
        </button>
      )}
      {url && (
        <a
          className="button primary download-button"
          href={url}
          download={`aion-${format}-${reference.clock.date}.png`}
        >
          {c.download}
          <Arrow down />
        </a>
      )}
    </Modal>
  );
}
export function App() {
  const [initial] = useState(() => loadSettings(browserStorage()));
  const [guestSettings, setGuestSettings] = useState<Settings | null>(initial.settings),
    [status, setStatus] = useState<StorageStatus>(initial.status);
  const sync = useProfileSync(accountsEnabled, guestSettings);
  const settings = sync.state.selected ? sync.settings : guestSettings;
  const selectedRef = useRef(sync.state.selected);
  selectedRef.current = sync.state.selected;
  const [language, setLanguage] = useState<Language>(() =>
    location.pathname.startsWith('/es') ? 'es' : (initial.settings?.language ?? 'en'),
  );
  const [page, setPage] = useState<Page>(() => pageFromPath(location.pathname, accountsEnabled));
  const [modal, setModal] = useState<'edit' | 'export' | 'privacy' | 'reset' | null>(() =>
    location.pathname.includes('privacy') || location.pathname.includes('privacidad')
      ? 'privacy'
      : null,
  );
  const [resetFailed, setResetFailed] = useState(false),
    c = copy[language];
  const [editor, setEditor] = useState<{ owner: string | null; revision?: number }>({
    owner: null,
  });
  const activeOwner = sync.state.selected ? (sync.state.identity?.id ?? null) : null;
  function openEdit() {
    setEditor({
      owner: activeOwner,
      revision: sync.state.pending?.base ?? sync.state.snapshot?.revision,
    });
    setModal('edit');
  }
  useEffect(() => {
    if (modal === 'edit' && editor.owner !== activeOwner) setModal(null);
  }, [modal, editor.owner, activeOwner]);
  function update(next: Settings, expectedRevision?: number) {
    const actual = { ...next, language };
    if (sync.state.selected) sync.controller.edit(actual, expectedRevision);
    else {
      setGuestSettings(actual);
      setStatus(saveSettings(browserStorage(), actual, status));
    }
  }
  function switchLanguage(next: Language) {
    setLanguage(next);
    if (settings) {
      const value = { ...settings, language: next };
      if (sync.state.selected) sync.controller.edit(value);
      else {
        setGuestSettings(value);
        setStatus(saveSettings(browserStorage(), value, status));
      }
    }
  }
  function navigate(next: Page, replace = false) {
    const path = pagePath(next, language);
    if (location.pathname !== path) history[replace ? 'replaceState' : 'pushState'](null, '', path);
    setModal(null);
    setPage(next);
  }
  function follow(event: MouseEvent<HTMLAnchorElement>, next: Page) {
    if (event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    navigate(next);
  }
  useEffect(() => {
    const back = () => {
      setPage(pageFromPath(location.pathname, accountsEnabled));
      setLanguage(/^\/es(?:\/|$)/.test(location.pathname) ? 'es' : 'en');
      setModal(null);
    };
    window.addEventListener('popstate', back);
    return () => window.removeEventListener('popstate', back);
  }, []);
  useEffect(() => {
    document.documentElement.lang = language;
    const title =
      page === 'calendar'
        ? language === 'en'
          ? 'A life, in weeks.'
          : 'Una vida, en semanas.'
        : page === 'login'
          ? language === 'en'
            ? 'Sign in'
            : 'Iniciar sesión'
          : language === 'en'
            ? 'Your account'
            : 'Tu cuenta';
    document.title = `Aion — ${title}`;
    const path = pagePath(page, language);
    if (location.pathname !== path) history.replaceState(null, '', path);
  }, [language, page]);
  useEffect(() => {
    const heading = document.querySelector<HTMLElement>('main h1');
    heading?.setAttribute('tabindex', '-1');
    heading?.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }, [page]);
  useEffect(() => {
    const handler = (e: StorageEvent) => {
      if (e.key !== STORAGE_KEY && e.key !== null) return;
      const loaded = decodeSettings(e.newValue);
      if (loaded.status === 'ok') {
        setGuestSettings(loaded.settings);
        if (loaded.settings && !selectedRef.current) setLanguage(loaded.settings.language);
      }
      setStatus(loaded.status);
    };
    window.addEventListener('storage', handler);
    return () => window.removeEventListener('storage', handler);
  }, []);
  const wasSelected = useRef(sync.state.selected);
  useEffect(() => {
    if (sync.state.selected && sync.settings) setLanguage(sync.settings.language);
    else if (wasSelected.current && !sync.state.selected && guestSettings)
      setLanguage(guestSettings.language);
    wasSelected.current = sync.state.selected;
  }, [sync.state.selected, sync.settings?.language, guestSettings?.language]);
  async function reset() {
    if (sync.state.selected) {
      try {
        await sync.controller.reset();
        setResetFailed(false);
        setModal(null);
      } catch {
        setResetFailed(true);
      }
      return;
    }
    try {
      browserStorage().removeItem(STORAGE_KEY);
      setStatus('ok');
      setResetFailed(false);
    } catch {
      setStatus('unavailable');
      setResetFailed(true);
    }
    setGuestSettings(null);
    setModal(null);
  }
  const warning =
    resetFailed && !sync.state.selected
      ? language === 'en'
        ? 'Stored settings could not be removed. Clear Aion’s site data in your browser settings. This visit has been reset.'
        : 'No se pudieron borrar los ajustes guardados. Borra los datos de Aion en tu navegador. Esta visita se ha reiniciado.'
      : status === 'unavailable'
        ? c.storageError
        : status === 'invalid'
          ? c.storageInvalid
          : status === 'newer'
            ? c.storageNewer
            : null;
  return (
    <>
      <a className="skip-link" href={page === 'calendar' ? '#calendar' : '#account-content'}>
        {page === 'calendar'
          ? c.skip
          : language === 'en'
            ? 'Skip to main content'
            : 'Ir al contenido principal'}
      </a>
      <header className="site-header">
        <a
          className="brand"
          href={pagePath('calendar', language)}
          onClick={(e) => follow(e, 'calendar')}
          aria-label="Aion by Agape"
        >
          aion<span>.</span>
          <small>by Agape</small>
        </a>
        <nav aria-label={language === 'en' ? 'Main' : 'Principal'}>
          <div className="language-control" aria-label={language === 'en' ? 'Language' : 'Idioma'}>
            <button
              lang="en"
              aria-label="English"
              aria-pressed={language === 'en'}
              onClick={() => switchLanguage('en')}
            >
              EN
            </button>
            <span>/</span>
            <button
              lang="es"
              aria-label="Español"
              aria-pressed={language === 'es'}
              onClick={() => switchLanguage('es')}
            >
              ES
            </button>
          </div>
          {settings && page === 'calendar' && (
            <button className="text-button header-edit" onClick={openEdit}>
              {c.calendar}
              <Arrow />
            </button>
          )}
          {accountsEnabled && (
            <a
              className="text-button"
              href={pagePath(sync.state.identity ? 'account' : 'login', language)}
              onClick={(e) => follow(e, sync.state.identity ? 'account' : 'login')}
              aria-current={page !== 'calendar' ? 'page' : undefined}
            >
              {language === 'en' ? 'Account' : 'Cuenta'}
            </a>
          )}
        </nav>
      </header>
      {page !== 'calendar' && accountsEnabled ? (
        <main className="site-main account-page" id="account-content">
          <a
            className="account-back"
            href={pagePath('calendar', language)}
            onClick={(e) => follow(e, 'calendar')}
          >
            ← {language === 'en' ? 'Back to calendar' : 'Volver al calendario'}
          </a>
          <div className={`account-sheet ${page === 'login' ? 'login-sheet' : ''}`}>
            <p className="eyebrow">
              {page === 'login'
                ? language === 'en'
                  ? 'A little continuity'
                  : 'Un poco de continuidad'
                : 'Aion / ' + (language === 'en' ? 'Account' : 'Cuenta')}
            </p>
            <h1>
              {page === 'login'
                ? language === 'en'
                  ? 'Sign in to Aion.'
                  : 'Entra en Aion.'
                : language === 'en'
                  ? 'Your account.'
                  : 'Tu cuenta.'}
            </h1>
            <Account
              language={language}
              controller={sync.controller}
              state={sync.state}
              guest={guestSettings}
              done={() => navigate('calendar')}
              page={page}
              navigate={navigate}
            />
          </div>
        </main>
      ) : (
        <main className="site-main">
          {accountsEnabled &&
            (sync.state.identity || sync.state.phase === 'expired' || sync.state.cacheIssue) && (
              <aside className="sync-banner">
                <SyncStatus state={sync.state} language={language} />
                <a
                  className="text-button"
                  href={pagePath(sync.state.identity ? 'account' : 'login', language)}
                  onClick={(e) => follow(e, sync.state.identity ? 'account' : 'login')}
                >
                  {language === 'en' ? 'Manage account' : 'Gestionar cuenta'}
                </a>
              </aside>
            )}
          <section className="hero">
            <div>
              <p className="eyebrow">
                <span className="tiny-rule" />
                {c.kicker}
              </p>
              <h1>{c.title}</h1>
            </div>
            <p className="hero-copy">
              {c.intro}
              <br />
              {c.intro2}
            </p>
          </section>
          {warning && (
            <div className="notice" role="status">
              <p>{warning}</p>
              {(status === 'invalid' || status === 'newer') && (
                <button className="text-button" onClick={() => setModal('reset')}>
                  {sync.state.selected ? syncWords[language].reset : c.reset}
                </button>
              )}
            </div>
          )}
          {settings ? (
            <CalendarView
              key={`${settings.birthDate}:${settings.lifespanYears}`}
              settings={settings}
              language={language}
              update={update}
              onExport={() => setModal('export')}
            />
          ) : (
            <section className="onboarding" id="calendar" tabIndex={-1}>
              <div className="onboarding-story">
                <span className="eyebrow">01 / {c.start}</span>
                <h2>{c.emptyHeading}</h2>
                <p>{c.emptyText}</p>
                <div className="sample-grid" aria-hidden="true">
                  {Array.from({ length: 156 }, (_, i) => (
                    <i
                      key={i}
                      className={i < 55 ? 'sample-past' : i === 55 ? 'sample-current' : ''}
                    />
                  ))}
                </div>
                <p className="caption local-copy">
                  <svg aria-hidden="true" width="16" height="17" viewBox="0 0 20 20" fill="none">
                    <rect x="4" y="8" width="12" height="10" rx="2" stroke="currentColor" />
                    <path d="M7 8V5a3 3 0 0 1 6 0v3" stroke="currentColor" />
                  </svg>
                  {c.local}
                  <br />
                  {accountsEnabled
                    ? language === 'en'
                      ? 'Guest settings stay on this device. Account saving is optional; PNGs stay local.'
                      : 'Los ajustes locales siguen en este dispositivo. Guardar en la cuenta es opcional; las imágenes siguen siendo locales.'
                    : c.localDetail}
                </p>
              </div>
              <div className="onboarding-form">
                <p className="eyebrow">{c.own}</p>
                <SettingsForm
                  key={activeOwner ?? 'guest'}
                  initial={null}
                  language={language}
                  onSave={update}
                />
              </div>
            </section>
          )}
          {settings && (
            <div className="local-footer">
              <p className="caption">
                {sync.state.selected
                  ? language === 'en'
                    ? 'Account calendar.'
                    : 'Calendario de cuenta.'
                  : c.local}{' '}
                {accountsEnabled
                  ? language === 'en'
                    ? 'Guest settings stay on this device. Account saving is optional; PNGs stay local.'
                    : 'Los ajustes locales siguen en este dispositivo. Guardar en la cuenta es opcional; las imágenes siguen siendo locales.'
                  : c.localDetail}
              </p>
              <button className="text-button reset-link" onClick={() => setModal('reset')}>
                {sync.state.selected ? syncWords[language].reset : c.reset}
              </button>
            </div>
          )}
        </main>
      )}
      <footer className="site-footer">
        <span>{c.made}</span>
        <div>
          <button className="text-button" onClick={() => setModal('privacy')}>
            {c.privacy}
          </button>
          <a href="https://github.com/agapeengineering/aion" target="_blank" rel="noreferrer">
            {c.source} ↗
          </a>
          <a
            href="https://github.com/agapeengineering/aion/issues"
            target="_blank"
            rel="noreferrer"
          >
            {c.feedback} ↗
          </a>
          <span className="version">{c.version}</span>
        </div>
      </footer>
      {modal === 'edit' && (
        <Modal title={c.edit} closeLabel={c.close} onClose={() => setModal(null)}>
          <SettingsForm
            initial={settings}
            language={language}
            onCancel={() => setModal(null)}
            onSave={(value) => {
              if (editor.owner === activeOwner) update(value, editor.revision);
              setModal(null);
            }}
          />
        </Modal>
      )}
      {modal === 'export' && settings && (
        <ExportDialog settings={settings} language={language} onClose={() => setModal(null)} />
      )}
      {modal === 'reset' && (
        <Modal
          title={sync.state.selected ? syncWords[language].reset : c.resetTitle}
          closeLabel={c.close}
          onClose={() => setModal(null)}
        >
          <p className="muted">
            {sync.state.selected ? syncWords[language].resetText : c.resetText}
          </p>
          {resetFailed && sync.state.selected && <p role="alert">{syncWords[language].error}</p>}
          <div className="form-actions">
            <button className="button secondary" onClick={() => setModal(null)}>
              {c.cancel}
            </button>
            <button
              className="button primary"
              disabled={sync.state.selected && (sync.state.busy || !navigator.onLine)}
              onClick={() => void reset()}
            >
              {c.resetConfirm}
            </button>
          </div>
        </Modal>
      )}
      {modal === 'privacy' && (
        <Modal
          title={accountsEnabled ? c.privacy : c.privacyTitle}
          closeLabel={c.close}
          onClose={() => setModal(null)}
        >
          <div className="privacy-copy">
            <p>
              {accountsEnabled
                ? language === 'en'
                  ? 'Guest settings and PNG generation stay on this device. Optional sign-in sends your email and code to the account service. Saving to your account sends your birth date, chosen lifespan and preferences for cross-device sync. Your guest calendar is preserved separately. Account settings and pending edits may be cached on this device for offline use. Signing out revokes this session and clears its account cache, with confirmation before discarding pending changes. Remote revocation cannot erase an offline device until it reconnects. Email reminders require separate consent, use saved account settings, and share message content with Resend. Signing out does not unsubscribe; reminder emails include an unsubscribe link. Guest use makes no account requests. No advertising or product analytics.'
                  : 'Los ajustes locales y las imágenes siguen en este dispositivo. Iniciar sesión envía tu correo y código al servicio de cuentas. Guardar en la cuenta envía tu fecha de nacimiento, horizonte y preferencias para sincronizarlos. El calendario local se conserva por separado. Los ajustes de cuenta y cambios pendientes pueden guardarse en caché para usarlos sin conexión. Cerrar sesión revoca la sesión y borra su caché, con confirmación para descartar cambios pendientes. Una revocación remota no borra un dispositivo desconectado hasta que vuelva a conectarse. Los recordatorios requieren consentimiento aparte, usan los ajustes guardados y comparten el contenido con Resend. Cerrar sesión no cancela la suscripción; los correos incluyen un enlace para cancelarla. El modo local no consulta la cuenta. Sin publicidad ni analítica.'
                : c.privacyBody}
            </p>
            <p>
              {c.privacyHost}{' '}
              <a href="https://www.cloudflare.com/privacypolicy/" target="_blank" rel="noreferrer">
                Cloudflare ↗
              </a>
            </p>
            <p>{c.privacyReset}</p>
            <p>{c.support}</p>
            <p>
              <a
                href="https://github.com/agapeengineering/aion/blob/main/LICENSE"
                target="_blank"
                rel="noreferrer"
              >
                MIT License ↗
              </a>
            </p>
          </div>
        </Modal>
      )}
    </>
  );
}
