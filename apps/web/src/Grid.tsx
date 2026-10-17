import { memo, useEffect, useRef, useState } from 'react';
import { dateAtDay, dateString, ordinal, parseDate, type Snapshot } from '@aion/calendar';
import { copy, type Language } from './i18n';
type Props = { birthDate: string; grid: Snapshot['grid']; language: Language; hideRemaining: boolean };
export const LifeGrid = memo(function LifeGrid({ birthDate, grid, language, hideRemaining }: Props) {
 const canvas = useRef<HTMLCanvasElement>(null), wrap = useRef<HTMLDivElement>(null);
 const [width, setWidth] = useState(600), [selected, setSelected] = useState<number | null>(null), [detail, setDetail] = useState(false);
 const index = Math.min(Math.max(selected ?? grid.currentIndex ?? grid.totalCells - 1, 0), grid.totalCells - 1);
 const startIndex = detail ? Math.floor(index / (52 * 10)) * (52 * 10) : 0;
 const count = detail ? Math.min(520, grid.totalCells - startIndex) : grid.totalCells;
 const rows = Math.ceil(count / 52), cell = Math.min(width / 52, 660 / rows), height = rows * cell;
 const c = copy[language], fmt = new Intl.NumberFormat(language);
 useEffect(() => { const el = wrap.current; if (!el) return; const resize = new ResizeObserver(entries => setWidth(Math.max(1, entries[0].contentRect.width))); resize.observe(el); return () => resize.disconnect(); }, []);
 useEffect(() => {
  const el = canvas.current; if (!el) return;
  const ratio = window.devicePixelRatio || 1, w = cell * 52;
  el.width = Math.ceil(w * ratio); el.height = Math.ceil(height * ratio); el.style.width = `${w}px`; el.style.height = `${height}px`;
  const ctx = el.getContext('2d'); if (!ctx) return;
  ctx.scale(ratio, ratio); ctx.clearRect(0, 0, w, height);
  const gap = Math.min(2.2, cell * .24), size = Math.max(.2, cell - gap);
  for (let n = 0; n < count; n++) {
   const i = startIndex + n, x = n % 52 * cell + gap / 2, y = Math.floor(n / 52) * cell + gap / 2;
   if (i < grid.elapsedCells) { ctx.fillStyle = '#1a1a1a'; ctx.fillRect(x, y, size, size); }
   else if (i === grid.currentIndex) { ctx.fillStyle = '#b5532a'; ctx.fillRect(x, y, size, size); ctx.strokeStyle = '#b5532a'; ctx.lineWidth = Math.max(.6, cell * .1); ctx.strokeRect(x - gap * .22, y - gap * .22, size + gap * .44, size + gap * .44); }
   else { ctx.strokeStyle = '#837664'; ctx.lineWidth = Math.min(1, size * .3); ctx.strokeRect(x + .4, y + .4, Math.max(.1, size - .8), Math.max(.1, size - .8)); }
   if (selected !== null && i === index && cell > 3) { ctx.strokeStyle = '#b5532a'; ctx.lineWidth = 1; ctx.strokeRect(x - 1.5, y - 1.5, size + 3, size + 3); }
  }
 }, [cell, height, count, startIndex, grid.elapsedCells, grid.currentIndex, index, selected]);
 const B = ordinal(parseDate(birthDate)!), start = B + index * 7;
 const horizonDay = B + (grid.totalCells - 1) * 7 + grid.finalCellDays;
 const interval = `${dateString(dateAtDay(start))} → ${dateString(dateAtDay(Math.min(start + 7, horizonDay)))}`;
 const summary = `${c.gridTitle}. ${fmt.format(grid.elapsedCells)} ${c.lived.toLowerCase()}. ${grid.currentStart ? `${c.current}: ${grid.currentStart} → ${grid.currentEndExclusive}.` : ''} ${hideRemaining ? '' : `${fmt.format(grid.futureCells)} ${c.ahead.toLowerCase()}.`}`;
 return <section className="atlas" aria-labelledby="grid-heading">
  <div className="section-heading"><h2 id="grid-heading" className="eyebrow">{c.oneSquare}</h2><button className="text-button" aria-pressed={detail} onClick={() => setDetail(!detail)}>{detail ? c.allWeeks : c.detail} ↗</button></div>
  <p className="sr-only" id="grid-summary">{summary}</p>
  <div className="canvas-wrap" ref={wrap}><canvas ref={canvas} role="img" aria-label={summary} onClick={event => { const el = canvas.current!; const bounds = el.getBoundingClientRect(); const col = Math.floor((event.clientX - bounds.left) / cell), row = Math.floor((event.clientY - bounds.top) / cell); const next = startIndex + row * 52 + col; if (col >= 0 && col < 52 && next < grid.totalCells) setSelected(next); }} /></div>
  <div className="legend"><span><i className="lived-key"/>{c.lived}</span><span><i className="current-key"/>{c.current}</span><span><i className="future-key"/>{c.ahead}</span></div>
  <p className="caption">{c.rowNote}</p>
  <details className="week-detail"><summary>{c.detail}</summary><p className="caption">{c.detailHint}</p><div className="week-controls"><label>{c.selectWeek}<input type="number" min="1" max={grid.totalCells} value={index + 1} onChange={e => { const n = Number(e.target.value); if (Number.isInteger(n) && n >= 1 && n <= grid.totalCells) setSelected(n - 1); }} /></label><button className="button secondary" onClick={() => setSelected(grid.currentIndex ?? grid.totalCells - 1)}>{c.currentWeek}</button></div><p className="mono interval">{c.interval}: {interval}</p></details>
 </section>;
});
