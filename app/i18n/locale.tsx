"use client";
import {cloneElement, createContext, Fragment, isValidElement, useContext, useEffect, useState, type ReactNode, type ReactElement} from 'react';
import {translate, type Locale} from './messages';

export const LOCALE_COOKIE = 'sv-language';
export function saveLocalePreference(locale: Locale) {
 try {document.cookie = `${LOCALE_COOKIE}=${locale}; Path=/; Max-Age=31536000; SameSite=Lax${window.location.protocol === 'https:' ? '; Secure' : ''}`;} catch { /* Storage may be disabled; the current page still switches. */ }
}
export const normalizeLocale = (value: unknown): Locale => value === 'en' ? 'en' : 'zh';
const LocaleContext = createContext<{locale: Locale; setLocale: (locale: Locale) => void}>({locale: 'zh', setLocale: () => {}});
export const useLocale = () => useContext(LocaleContext);

export function LocaleProvider({initialLocale = 'zh', children}: {initialLocale?: Locale; children: ReactNode}) {
 const [locale, setLocale] = useState<Locale>(initialLocale);
 useEffect(() => {
  document.documentElement.lang = locale === 'en' ? 'en' : 'zh-CN';
  const titles: Record<string, [string, string]> = {
   '/': ['大盘', 'Market'], '/zh/watch/market': ['大盘', 'Market'],
   '/zh/watch/industry-radar': ['行业', 'Industries'],
   '/zh/watch/resonance/rare-opportunities': ['候选榜', 'Candidates'],
   '/zh/watch/resonance/favorite-pattern': ['日线形态', 'Daily Patterns'],
   '/zh/backtest': ['回测', 'Backtests'],
  };
  const title = titles[window.location.pathname.replace(/\/$/, '') || '/'];
  if (title) document.title = `Sage Vista — ${title[locale === 'en' ? 1 : 0]}`;
 }, [locale]);
 const choose = (next: Locale) => {
  setLocale(next);
  // A cookie also makes full-page navigation and the first server render agree.
  saveLocalePreference(next);
 };
 return <LocaleContext.Provider value={{locale, setLocale: choose}}>{children}</LocaleContext.Provider>;
}

export function LanguageSwitch() {
 const {locale, setLocale} = useLocale();
 return <div className="languageSwitch" role="group" aria-label={locale === 'en' ? 'Language' : '语言'}>
  <button type="button" lang="zh-CN" aria-pressed={locale === 'zh'} onClick={() => setLocale('zh')}>中文</button>
  <button type="button" lang="en" aria-pressed={locale === 'en'} onClick={() => setLocale('en')}>English</button>
 </div>;
}

/** Translate rendered text, never application props, values, handlers or identifiers.
 * Each component owns its boundary; custom components render under the same context.
 * No DOM rewriting, network translation, or mutation of saved research inputs.
 */
export function localizeNodes(node: ReactNode, locale: Locale): ReactNode {
 if (typeof node === 'string') return translate(node, locale);
 if (Array.isArray(node)) return node.map(child => localizeNodes(child, locale));
 if (!isValidElement(node)) return node;
 const element = node as ReactElement<Record<string, unknown>>;
 if (typeof element.type !== 'string' && element.type !== Fragment) return node;
 if (element.props.translate === 'no' || ['code', 'pre', 'script', 'style'].includes(String(element.type))) return node;
 const props: Record<string, unknown> = {};
 for (const key of ['title', 'placeholder', 'aria-label', 'alt']) {
  if (typeof element.props[key] === 'string') props[key] = translate(element.props[key] as string, locale);
 }
 if (!('children' in element.props)) return cloneElement(element, props);
 const children = localizeNodes(element.props.children as ReactNode, locale);
 return Array.isArray(children) ? cloneElement(element, props, ...children) : cloneElement(element, props, children);
}
export function Localized({children}: {children: ReactNode}) {
 const {locale} = useLocale();
 return <>{localizeNodes(children, locale)}</>;
}
