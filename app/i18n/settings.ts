import type {Locale} from './messages';

export const DEFAULT_LOCALE: Locale = 'en';
// English is the default on every new visit: a language choice lasts only for the
// browser session. The old year-long cookie is ignored and cleared.
export const LOCALE_COOKIE = 'sv-language-session';
export const LEGACY_LOCALE_COOKIE = 'sv-language';
export const normalizeLocale = (value: unknown): Locale => value === 'zh' ? 'zh' : DEFAULT_LOCALE;
