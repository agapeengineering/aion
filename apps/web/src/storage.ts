import { calculate, localClock, units, type Unit } from '@aion/calendar';
import type { Language } from './i18n';
export const STORAGE_KEY = 'aion:settings';
export type Settings = { version: 1; birthDate: string; lifespanYears: number; language: Language; unit: Unit; hideRemaining: boolean };
export type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
export type StorageStatus = 'ok' | 'unavailable' | 'invalid' | 'newer';
export function decodeSettings(raw: string | null): { settings: Settings | null; status: StorageStatus } {
  if (raw === null) return { settings: null, status: 'ok' };
  try {
    const x = JSON.parse(raw);
    if (x && typeof x === 'object' && typeof x.version === 'number' && x.version > 1) return { settings: null, status: 'newer' };
    if (!x || x.version !== 1 || !['en', 'es'].includes(x.language) || !units.includes(x.unit) || typeof x.hideRemaining !== 'boolean' || 'error' in calculate({ ...x, clock: localClock() })) return { settings: null, status: 'invalid' };
    return { settings: { version: 1, birthDate: x.birthDate, lifespanYears: x.lifespanYears, language: x.language, unit: x.unit, hideRemaining: x.hideRemaining }, status: 'ok' };
  } catch { return { settings: null, status: 'invalid' }; }
}
export function loadSettings(storage: StorageLike): ReturnType<typeof decodeSettings> {
  try { return decodeSettings(storage.getItem(STORAGE_KEY)); } catch { return { settings: null, status: 'unavailable' }; }
}
export function saveSettings(storage: StorageLike, settings: Settings, status: StorageStatus): StorageStatus {
  if (status === 'newer' || status === 'invalid') return status;
  try { storage.setItem(STORAGE_KEY, JSON.stringify(settings)); return 'ok'; } catch { return 'unavailable'; }
}
export function browserStorage(): StorageLike {
  // Accessing the property itself can throw when browser storage is denied.
  try { return window.localStorage; } catch { return { getItem() { throw new Error('Storage unavailable'); }, setItem() { throw new Error('Storage unavailable'); }, removeItem() { throw new Error('Storage unavailable'); } }; }
}
