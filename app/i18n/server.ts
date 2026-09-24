import type {Metadata} from 'next';
import {cookies} from 'next/headers';
import {LOCALE_COOKIE, normalizeLocale} from './settings';

export async function requestLocale() {
 return normalizeLocale((await cookies()).get(LOCALE_COOKIE)?.value);
}
export async function localizedMetadata(zh: Metadata, en: Metadata): Promise<Metadata> {
 return (await requestLocale()) === 'zh' ? zh : en;
}
