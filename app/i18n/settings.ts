import type {Locale} from './messages';

export const DEFAULT_LOCALE: Locale = 'en';
// A choice made with the language switch lasts for the browser session. With no choice, the
// first render follows the browser's own language order (W3C: Accept-Language is a starting
// point the visitor can always override); no header (crawlers) or no zh/en preference means
// English. The old year-long cookie is ignored and cleared.
export const LOCALE_COOKIE = 'sv-language-session';
export const LEGACY_LOCALE_COOKIE = 'sv-language';
export const normalizeLocale = (value: unknown): Locale => value === 'zh' ? 'zh' : DEFAULT_LOCALE;

// The highest-weighted zh or en tag in an Accept-Language header; ties go to the one listed first.
export function browserLocale(header: string | null | undefined): Locale {
 let best: Locale = DEFAULT_LOCALE, bestQ = -1;
 for (const part of (header ?? '').split(',')) {
  const [tag, ...params] = part.trim().toLowerCase().split(';');
  const primary = tag.split('-')[0];
  if (primary !== 'zh' && primary !== 'en') continue;
  const weight = params.map(value => value.trim()).find(value => value.startsWith('q='));
  const q = weight ? Number(weight.slice(2)) : 1;
  if (Number.isFinite(q) && q > 0 && q > bestQ) { best = primary; bestQ = q; }
 }
 return best;
}
