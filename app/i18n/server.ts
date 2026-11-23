import type {Metadata} from 'next';
import {cookies, headers} from 'next/headers';
import {LOCALE_COOKIE, browserLocale} from './settings';

// A saved choice wins; otherwise the browser's language decides (see settings.ts).
export async function requestLocale() {
 const saved = (await cookies()).get(LOCALE_COOKIE)?.value;
 if (saved === 'zh' || saved === 'en') return saved;
 return browserLocale((await headers()).get('accept-language'));
}
export async function localizedMetadata(zh: Metadata, en: Metadata): Promise<Metadata> {
 return (await requestLocale()) === 'zh' ? zh : en;
}
