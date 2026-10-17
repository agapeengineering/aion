import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode, type FormEvent } from 'react';
import { calculate, localClock, advanceDisplay, units, type DisplayEvent, type DisplayState, type Snapshot, type Unit, type CalculationError } from '@aion/calendar';
import { copy, phrases, unitNames, type Language } from './i18n';
import { browserStorage, decodeSettings, loadSettings, saveSettings, STORAGE_KEY, type Settings, type StorageStatus } from './storage';
import { LifeGrid } from './Grid';
import { createWallpaper } from './export';

function Arrow({ down = false }: { down?: boolean }) { return <svg aria-hidden="true" width="17" height="17" viewBox="0 0 24 24" fill="none"><path d={down ? 'M12 4v15m-6-6 6 6 6-6M4 21h16' : 'M5 19 19 5M5 5h14v14'} stroke="currentColor" strokeWidth="1.5"/></svg>; }
function Modal({ title, closeLabel, onClose, children }: { title: string; closeLabel: string; onClose: () => void; children: ReactNode }) {
 const ref = useRef<HTMLDialogElement>(null);
 useEffect(() => { const el = ref.current!; el.showModal(); return () => el.close(); }, []);
 return <dialog className="modal" ref={ref} aria-labelledby="modal-title" onClose={() => { if (!ref.current?.open) onClose(); }} onClick={e => { if (e.target === e.currentTarget) ref.current?.close(); }}><div className="modal-inner"><div className="modal-heading"><h2 id="modal-title">{title}</h2><button className="icon-button" aria-label={closeLabel} onClick={() => ref.current?.close()}>×</button></div>{children}</div></dialog>;
}
function errorMessage(error: CalculationError['error'], language: Language) {
 const c = copy[language];
 return ({ INVALID_CLOCK: c.clockInvalid, INVALID_BIRTH_DATE: c.birthInvalid, FUTURE_BIRTH_DATE: c.birthFuture, INVALID_LIFESPAN: c.lifespanInvalid, HORIZON_OUT_OF_RANGE: c.rangeInvalid })[error.code];
}
function SettingsForm({ initial, language, onSave, onCancel }: { initial: Settings | null; language: Language; onSave: (settings: Settings) => void; onCancel?: () => void }) {
 const c = copy[language], [birth, setBirth] = useState(initial?.birthDate ?? ''), [lifespan, setLifespan] = useState(String(initial?.lifespanYears ?? 90));
 const [error, setError] = useState<CalculationError['error'] | null>(null);
 const birthRef = useRef<HTMLInputElement>(null), lifeRef = useRef<HTMLInputElement>(null);
 function submit(e: FormEvent) {
  e.preventDefault(); const n = lifespan.trim() === '' ? NaN : Number(lifespan);
  const result = calculate({ birthDate: birth, lifespanYears: n, clock: localClock() });
  if ('error' in result) { setError(result.error); (result.error.field === 'birthDate' ? birthRef : lifeRef).current?.focus(); return; }
  setError(null); onSave({ version: 1, birthDate: birth, lifespanYears: n, language, unit: initial?.unit ?? 'weeks', hideRemaining: initial?.hideRemaining ?? false });
 }
 return <form onSubmit={submit} noValidate className="settings-form">
  <label htmlFor="birth-date">{c.birth}</label><input ref={birthRef} id="birth-date" name="birthDate" type="date" min="0001-01-01" max={localClock().date} value={birth} required aria-invalid={error?.field === 'birthDate'} aria-describedby={error?.field === 'birthDate' ? 'form-error' : undefined} onChange={e => setBirth(e.target.value)}/>
  <label htmlFor="lifespan">{c.horizon} <span className="label-unit">/ {c.yearsLabel}</span></label><input ref={lifeRef} id="lifespan" name="lifespan" type="number" min="1" step="1" inputMode="numeric" value={lifespan} required aria-invalid={error?.field === 'lifespanYears'} aria-describedby={error?.field === 'lifespanYears' ? 'horizon-hint form-error' : 'horizon-hint'} onChange={e => setLifespan(e.target.value)}/>
  <p id="horizon-hint" className="caption">{c.assumption}</p>
  {error && <p className="field-error" id="form-error" role="alert">{errorMessage(error, language)}</p>}
  <div className="form-actions">{onCancel && <button type="button" className="button secondary" onClick={onCancel}>{c.cancel}</button>}<button className="button primary" type="submit">{initial ? c.save : c.see}<Arrow/></button></div>
 </form>;
}
function useLifeClock(settings: Settings) {
 const getSnapshot = useCallback(() => calculate({ birthDate: settings.birthDate, lifespanYears: settings.lifespanYears, clock: localClock() }), [settings.birthDate, settings.lifespanYears]);
 const [state, setState] = useState<DisplayState | null>(() => { const s = getSnapshot(); return 'error' in s ? null : advanceDisplay(null, 'load', s); });
 const [error, setError] = useState<CalculationError['error'] | null>(null);
 const dispatch = useCallback((event: DisplayEvent) => { const s = getSnapshot(); if ('error' in s) { setError(s.error); return; } setError(null); setState(prev => advanceDisplay(prev, event, s)); }, [getSnapshot]);
 useEffect(() => {
  const id = window.setInterval(() => { if (document.visibilityState === 'visible') dispatch('tick'); }, 1000);
  const visibility = () => dispatch(document.visibilityState === 'hidden' ? 'hide' : 'show');
  const focus = () => dispatch('show');
  document.addEventListener('visibilitychange', visibility); window.addEventListener('focus', focus); window.addEventListener('pageshow', focus);
  return () => { clearInterval(id); document.removeEventListener('visibilitychange', visibility); window.removeEventListener('focus', focus); window.removeEventListener('pageshow', focus); };
 }, [dispatch]);
 return { state, error, dispatch };
}
function CalendarView({ settings, language, update, onExport }: { settings: Settings; language: Language; update: (s: Settings) => void; onExport: () => void }) {
 const { state, error, dispatch } = useLifeClock(settings), c = copy[language], [phraseOffset, setPhraseOffset] = useState(0);
 const fmt = useMemo(() => new Intl.NumberFormat(language), [language]);
 if (!state) return <p role="alert">{c.clockInvalid}</p>;
 const { live, subday, paused } = state, isSubday = (unit: Unit) => ['hours', 'minutes', 'seconds'].includes(unit);
 const totals = (direction: 'lived' | 'remaining', unit: Unit) => (isSubday(unit) ? subday : live)[direction][unit];
 const phraseIndex = (Math.floor(live.lived.days / 7) + phraseOffset) % phrases.length;
 return <div id="calendar" tabIndex={-1} className="calendar-view">
  {error && <p role="alert" className="notice">{errorMessage(error, language)}</p>}
  {live.horizonState !== 'before' && <p className="notice horizon-notice" role="status">{c.horizonReached}</p>}
  <div className="calendar-layout"><LifeGrid birthDate={settings.birthDate} grid={live.grid} language={language} hideRemaining={settings.hideRemaining}/><aside className="calendar-aside" aria-label={c.calendar}>
   <section className="summary-block"><span className="eyebrow">{unitNames[language][settings.unit]} · {language === 'es' ? 'Tiempo vivido' : c.lived}</span><p className="summary-number" data-testid="primary-lived">{fmt.format(totals('lived', settings.unit))}</p><p className="caption">{c.livedStory}</p></section>
   {!settings.hideRemaining && <section className="summary-block"><span className="eyebrow">{unitNames[language][settings.unit]} · {c.remaining}</span><p className="summary-number" data-testid="primary-remaining">{fmt.format(totals('remaining', settings.unit))}</p><p className="caption">{c.within}: {settings.lifespanYears} {c.yearsLabel}.</p></section>}
   <section className="summary-block present-block"><span className="eyebrow"><span className="present-dot"/>{c.present}</span><p className="present-copy">{c.presentText}</p>{live.grid.currentStart && <p className="caption mono">{live.grid.currentStart}<br/>→ {live.grid.currentEndExclusive}</p>}<button className="button secondary export-action" onClick={onExport}>{c.export}<Arrow/></button></section>
  </aside></div>
  <section className="statistics" aria-labelledby="statistics-title"><div className="statistics-heading"><div><span className="eyebrow">02 / {c.calendar}</span><h2 id="statistics-title">{c.numbers}</h2><p className="caption">{c.figures}</p></div><div className="stats-actions"><label className="unit-select">{c.primary}<select value={settings.unit} onChange={e => update({ ...settings, unit: e.target.value as Unit })}>{units.map(unit => <option key={unit} value={unit}>{unitNames[language][unit]}</option>)}</select></label><button className="text-button pause-button" aria-pressed={paused} onClick={() => dispatch(paused ? 'resume' : 'pause')}>{paused ? '▶' : 'Ⅱ'} {paused ? c.resume : c.pause}</button></div></div>
   <label className="toggle-row"><input type="checkbox" checked={settings.hideRemaining} onChange={e => update({ ...settings, hideRemaining: e.target.checked })}/><span>{c.hide}</span></label>
   {paused && <p className="caption pause-message" role="status">{c.paused}</p>}
   <div className="table-scroll"><table aria-live="off"><thead><tr><th scope="col">{language === 'en' ? 'Unit' : 'Unidad'}</th><th scope="col">{language === 'es' ? 'Tiempo vivido' : c.lived}</th>{!settings.hideRemaining && <th scope="col">{c.remaining}</th>}</tr></thead><tbody>{units.map(unit => <tr key={unit} className={settings.unit === unit ? 'selected-unit' : ''}><th scope="row">{unitNames[language][unit]} {isSubday(unit) && <span className="approx-marker" aria-label={c.approx}>≈</span>}</th><td data-testid={`lived-${unit}`}>{fmt.format(totals('lived', unit))}</td>{!settings.hideRemaining && <td data-testid={`remaining-${unit}`}>{fmt.format(totals('remaining', unit))}</td>}</tr>)}</tbody></table></div>
   <p className="caption counter-caveat">{c.caveat} {c.calendarCaveat}</p>
  </section>
  <section className="reflection" aria-labelledby="reflection-title"><div className="section-heading"><h2 id="reflection-title" className="eyebrow">03 / {c.reflection}</h2><button className="icon-button thought-button" aria-label={c.nextThought} onClick={() => setPhraseOffset(x => x + 1)}>↗</button></div><p key={phraseIndex} className="reflection-quote">{phrases[phraseIndex][language]}</p><span className="reflection-rule"/></section>
 </div>;
}
function ExportDialog({ settings, language, onClose }: { settings: Settings; language: Language; onClose: () => void }) {
 const c = copy[language], [format, setFormat] = useState<'phone' | 'desktop'>('phone'), [url, setUrl] = useState(''), [failed, setFailed] = useState(false), [retry, setRetry] = useState(0);
 const [reference] = useState(() => { const clock = localClock(); return { clock, result: calculate({ ...settings, clock }) }; });
 useEffect(() => {
  let cancelled = false, resource = ''; setUrl(''); setFailed(false);
  if ('error' in reference.result) { setFailed(true); return; }
  void createWallpaper({ snapshot: reference.result, referenceDate: reference.clock.date, lifespanYears: settings.lifespanYears, language, unit: settings.unit, hideRemaining: settings.hideRemaining, format, phraseIndex: Math.floor(reference.result.lived.days / 7) % phrases.length }).then(blob => { if (!cancelled) { resource = URL.createObjectURL(blob); setUrl(resource); } }).catch(() => { if (!cancelled) setFailed(true); });
  return () => { cancelled = true; if (resource) URL.revokeObjectURL(resource); };
 }, [format, settings.lifespanYears, settings.unit, settings.hideRemaining, language, reference, retry]);
 return <Modal title={c.exportTitle} closeLabel={c.close} onClose={onClose}><p className="muted">{c.exportText}</p><div className="format-switch" role="group" aria-label={c.export}><button className={format === 'phone' ? 'active' : ''} aria-pressed={format === 'phone'} onClick={() => setFormat('phone')}>{c.phone} · 1440 × 2560</button><button className={format === 'desktop' ? 'active' : ''} aria-pressed={format === 'desktop'} onClick={() => setFormat('desktop')}>{c.desktop} · 2560 × 1600</button></div><div className={`wallpaper-preview ${format}`}>{url ? <img src={url} alt={`${c.export} · ${reference.clock.date}`} /> : <p role="status">{failed ? c.exportError : c.preparing}</p>}</div><p className="caption">{c.discreet} {c.native}</p>{failed && <button className="button secondary" onClick={() => setRetry(x => x + 1)}>{language === 'en' ? 'Try again' : 'Intentar de nuevo'}</button>}{url && <a className="button primary download-button" href={url} download={`aion-${format}-${reference.clock.date}.png`}>{c.download}<Arrow down/></a>}</Modal>;
}
export function App() {
 const [initial] = useState(() => loadSettings(browserStorage()));
 const [settings, setSettings] = useState<Settings | null>(initial.settings), [status, setStatus] = useState<StorageStatus>(initial.status);
 const [language, setLanguage] = useState<Language>(() => location.pathname.startsWith('/es') ? 'es' : initial.settings?.language ?? 'en');
 const [modal, setModal] = useState<'edit' | 'export' | 'privacy' | 'reset' | null>(() => location.pathname.includes('privacy') || location.pathname.includes('privacidad') ? 'privacy' : null);
 const [resetFailed, setResetFailed] = useState(false), c = copy[language];
 function update(next: Settings) { const actual = { ...next, language }; setSettings(actual); setStatus(saveSettings(browserStorage(), actual, status)); }
 function switchLanguage(next: Language) { setLanguage(next); if (settings) { const value = { ...settings, language: next }; setSettings(value); setStatus(saveSettings(browserStorage(), value, status)); } }
 useEffect(() => { document.documentElement.lang = language; document.title = language === 'en' ? 'Aion — A life, in weeks.' : 'Aion — Una vida, en semanas.'; const path = language === 'es' ? '/es' : '/'; if (location.pathname !== path) history.replaceState(null, '', path); }, [language]);
 useEffect(() => { const handler = (e: StorageEvent) => { if (e.key !== STORAGE_KEY && e.key !== null) return; const loaded = decodeSettings(e.newValue); if (loaded.status === 'ok') { setSettings(loaded.settings); if (loaded.settings) setLanguage(loaded.settings.language); } setStatus(loaded.status); }; window.addEventListener('storage', handler); return () => window.removeEventListener('storage', handler); }, []);
 function reset() { try { browserStorage().removeItem(STORAGE_KEY); setStatus('ok'); setResetFailed(false); } catch { setStatus('unavailable'); setResetFailed(true); } setSettings(null); setModal(null); }
 const warning = resetFailed ? (language === 'en' ? 'Stored settings could not be removed. Clear Aion’s site data in your browser settings. This visit has been reset.' : 'No se pudieron borrar los ajustes guardados. Borra los datos de Aion en tu navegador. Esta visita se ha reiniciado.') : status === 'unavailable' ? c.storageError : status === 'invalid' ? c.storageInvalid : status === 'newer' ? c.storageNewer : null;
 return <><a className="skip-link" href="#calendar">{c.skip}</a><header className="site-header"><a className="brand" href={language === 'es' ? '/es' : '/'} aria-label="Aion by Agape">aion<span>.</span><small>by Agape</small></a><nav aria-label={language === 'en' ? 'Main' : 'Principal'}><div className="language-control" aria-label={language === 'en' ? 'Language' : 'Idioma'}><button lang="en" aria-label="English" aria-pressed={language === 'en'} onClick={() => switchLanguage('en')}>EN</button><span>/</span><button lang="es" aria-label="Español" aria-pressed={language === 'es'} onClick={() => switchLanguage('es')}>ES</button></div>{settings && <button className="text-button header-edit" onClick={() => setModal('edit')}>{c.calendar}<Arrow/></button>}</nav></header>
 <main className="site-main"><section className="hero"><div><p className="eyebrow"><span className="tiny-rule"/>{c.kicker}</p><h1>{c.title}</h1></div><p className="hero-copy">{c.intro}<br/>{c.intro2}</p></section>
 {warning && <div className="notice" role="status"><p>{warning}</p>{(status === 'invalid' || status === 'newer') && <button className="text-button" onClick={() => setModal('reset')}>{c.reset}</button>}</div>}
 {settings ? <CalendarView key={`${settings.birthDate}:${settings.lifespanYears}`} settings={settings} language={language} update={update} onExport={() => setModal('export')}/> : <section className="onboarding" id="calendar" tabIndex={-1}><div className="onboarding-story"><span className="eyebrow">01 / {c.start}</span><h2>{c.emptyHeading}</h2><p>{c.emptyText}</p><div className="sample-grid" aria-hidden="true">{Array.from({ length: 156 }, (_, i) => <i key={i} className={i < 55 ? 'sample-past' : i === 55 ? 'sample-current' : ''}/>)}</div><p className="caption local-copy"><svg aria-hidden="true" width="16" height="17" viewBox="0 0 20 20" fill="none"><rect x="4" y="8" width="12" height="10" rx="2" stroke="currentColor"/><path d="M7 8V5a3 3 0 0 1 6 0v3" stroke="currentColor"/></svg>{c.local}<br/>{c.localDetail}</p></div><div className="onboarding-form"><p className="eyebrow">{c.own}</p><SettingsForm initial={null} language={language} onSave={update}/></div></section>}
 {settings && <div className="local-footer"><p className="caption">{c.local} {c.localDetail}</p><button className="text-button reset-link" onClick={() => setModal('reset')}>{c.reset}</button></div>}
 </main><footer className="site-footer"><span>{c.made}</span><div><button className="text-button" onClick={() => setModal('privacy')}>{c.privacy}</button><a href="https://github.com/agapeengineering/aion" target="_blank" rel="noreferrer">{c.source} ↗</a><a href="https://github.com/agapeengineering/aion/issues" target="_blank" rel="noreferrer">{c.feedback} ↗</a><span className="version">{c.version}</span></div></footer>
 {modal === 'edit' && <Modal title={c.edit} closeLabel={c.close} onClose={() => setModal(null)}><SettingsForm initial={settings} language={language} onCancel={() => setModal(null)} onSave={value => { update(value); setModal(null); }}/></Modal>}
 {modal === 'export' && settings && <ExportDialog settings={settings} language={language} onClose={() => setModal(null)}/>}
 {modal === 'reset' && <Modal title={c.resetTitle} closeLabel={c.close} onClose={() => setModal(null)}><p className="muted">{c.resetText}</p><div className="form-actions"><button className="button secondary" onClick={() => setModal(null)}>{c.cancel}</button><button className="button primary" onClick={reset}>{c.resetConfirm}</button></div></Modal>}
 {modal === 'privacy' && <Modal title={c.privacyTitle} closeLabel={c.close} onClose={() => setModal(null)}><div className="privacy-copy"><p>{c.privacyBody}</p><p>{c.privacyHost} <a href="https://www.cloudflare.com/privacypolicy/" target="_blank" rel="noreferrer">Cloudflare ↗</a></p><p>{c.privacyReset}</p><p>{c.support}</p><p><a href="https://github.com/agapeengineering/aion/blob/main/LICENSE" target="_blank" rel="noreferrer">MIT License ↗</a></p></div></Modal>}
 </>;
}
