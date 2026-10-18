import type { Language } from './i18n';
export type Page = 'calendar' | 'login' | 'account';
export function pageFromPath(path: string, enabled: boolean): Page {
  if (!enabled) return 'calendar';
  if (/^\/(?:es\/)?login\/?$/.test(path)) return 'login';
  if (/^\/(?:es\/)?account\/?$/.test(path)) return 'account';
  return 'calendar';
}
export function pagePath(page: Page, language: Language): string {
  const prefix = language === 'es' ? '/es' : '';
  return page === 'calendar' ? prefix || '/' : `${prefix}/${page}`;
}
