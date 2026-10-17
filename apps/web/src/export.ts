import { type Snapshot, type Unit } from '@aion/calendar';
import { copy, phrases, unitNames, type Language } from './i18n';
export type WallpaperOptions = { snapshot: Snapshot; referenceDate: string; lifespanYears: number; language: Language; unit: Unit; hideRemaining: boolean; format: 'phone' | 'desktop'; phraseIndex: number };
export async function createWallpaper(options: WallpaperOptions): Promise<Blob> {
 const { snapshot, referenceDate, lifespanYears, language, unit, hideRemaining, format, phraseIndex } = options;
 await document.fonts.ready;
 await Promise.all([document.fonts.load('400 32px Inter'), document.fonts.load('400 32px "Geist Mono"')]);
 const canvas = document.createElement('canvas'); canvas.width = format === 'phone' ? 1440 : 2560; canvas.height = format === 'phone' ? 2560 : 1600;
 const ctx = canvas.getContext('2d'); if (!ctx) throw new Error('Canvas unavailable');
 const { width: w, height: h } = canvas, c = copy[language], fmt = new Intl.NumberFormat(language);
 ctx.fillStyle = '#FAF6EE'; ctx.fillRect(0, 0, w, h);
 const margin = w * .09, titleY = format === 'phone' ? h * .19 : h * .12;
 ctx.fillStyle = '#1A1A1A'; ctx.font = `400 ${format === 'phone' ? 84 : 96}px Georgia, serif`; ctx.fillText(c.title, margin, titleY);
 ctx.fillStyle = '#62584D'; ctx.font = '400 27px Inter'; ctx.fillText(c.assumption, margin, titleY + 60);
 const rows = Math.ceil(snapshot.grid.totalCells / 52), availableH = format === 'phone' ? h * .45 : h * .43;
 const cell = Math.min((w - margin * 2) / 52, availableH / rows), gridW = cell * 52, gridH = rows * cell;
 const gx = margin, gy = titleY + 130;
 // Fixed canvas size bounds memory even for unusually large valid horizons.
 for (let i = 0; i < snapshot.grid.totalCells; i++) {
  const x = gx + i % 52 * cell, y = gy + Math.floor(i / 52) * cell, gap = Math.max(.1, cell * .24), size = Math.max(.1, cell - gap);
  if (i < snapshot.grid.elapsedCells) { ctx.fillStyle = '#1A1A1A'; ctx.fillRect(x, y, size, size); }
  else if (i === snapshot.grid.currentIndex) { ctx.fillStyle = '#B5532A'; ctx.fillRect(x, y, size, size); ctx.strokeStyle = '#B5532A'; ctx.lineWidth = Math.max(.5, cell * .1); ctx.strokeRect(x - gap / 4, y - gap / 4, size + gap / 2, size + gap / 2); }
  else { ctx.strokeStyle = '#837664'; ctx.lineWidth = Math.min(1.2, size * .25); ctx.strokeRect(x, y, size, size); }
 }
 ctx.font = '400 20px Inter'; ctx.fillStyle = '#62584D'; ctx.fillText(`${c.lived} · ${c.current} · ${c.ahead}`, margin, gy + gridH + 32);
 const sy = gy + gridH + 90;
 ctx.font = '400 34px "Geist Mono"'; ctx.fillStyle = '#1A1A1A';
 ctx.fillText(`${fmt.format(snapshot.lived[unit])} ${unitNames[language][unit].toLowerCase()} · ${language === 'es' ? 'tiempo vivido' : c.lived.toLowerCase()}`, margin, sy);
 if (!hideRemaining) ctx.fillText(`${fmt.format(snapshot.remaining[unit])} · ${c.remaining.toLowerCase()}`, margin, sy + 52);
 ctx.font = '400 24px Inter'; ctx.fillStyle = '#62584D';
 ctx.fillText(`${lifespanYears} ${c.yearsLabel} · ${c.screenshotDate}: ${referenceDate}`, margin, sy + (hideRemaining ? 52 : 105));
 if (['hours', 'minutes', 'seconds'].includes(unit)) ctx.fillText(c.approx, margin, sy + (hideRemaining ? 90 : 142));
 ctx.font = '400 35px Georgia, serif'; ctx.fillStyle = '#1A1A1A';
 const phrase = phrases[phraseIndex % phrases.length][language];
 const words = phrase.split(' '); let line = '', y = Math.max(sy + 190, h - 210);
 for (const word of words) { if (ctx.measureText(line + word).width > w - margin * 2) { ctx.fillText(line.trim(), margin, y); y += 45; line = ''; } line += word + ' '; }
 ctx.fillText(line.trim(), margin, y);
 ctx.font = '400 23px Inter'; ctx.fillStyle = '#62584D'; ctx.fillText('aion · by Agape', margin, h - 80);
 void gridW;
 return new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('PNG generation failed')), 'image/png'));
}
