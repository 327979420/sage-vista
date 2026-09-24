import type {Locale} from './messages';

export const DEFAULT_LOCALE: Locale = 'en';
export const LOCALE_COOKIE = 'sv-language';
export const normalizeLocale = (value: unknown): Locale => value === 'zh' ? 'zh' : DEFAULT_LOCALE;
