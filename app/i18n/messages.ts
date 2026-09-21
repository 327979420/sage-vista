import {catalog} from './catalog';
export type Locale = 'zh' | 'en';
const hasChinese = /[\u3400-\u9fff]/;
const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const patterns = Object.entries(catalog).filter(([key]) => /\{\d+\}/.test(key)).map(([key, value]) => {
 const slots = [...key.matchAll(/\{(\d+)\}/g)].map(match => Number(match[1]));
 return {regex: new RegExp('^' + key.split(/\{\d+\}/).map(escape).join('(.*?)') + '$'), value, slots, specificity: key.replace(/\{\d+\}/g, '').length};
}).sort((a, b) => b.specificity - a.specificity);

/** Exact reviewed messages first, then reviewed templates. No guessed word replacement. */
export function translate(text: string, locale: Locale, depth = 0): string {
 if (locale === 'zh' || !hasChinese.test(text) || depth > 8) return text;
 const key = text.trim();
 let result = catalog[key];
 if (result === undefined && key.endsWith('。') && catalog[key.slice(0, -1)] !== undefined) result = catalog[key.slice(0, -1)] + '.';
 if (result === undefined) {
  for (const pattern of patterns) {
   const match = key.match(pattern.regex);
   if (!match) continue;
   result = pattern.value.replace(/\{(\d+)\}/g, (_, slot) => translate(match[pattern.slots.indexOf(Number(slot)) + 1], locale, depth + 1));
   break;
  }
 }
 // Composite conclusions keep sentence punctuation so complete messages still match.
 if (result === undefined && /[；：、／\n]|: /.test(key)) {
  result = key.split(/([；：、／\n]|: )/).map(part => part === '；' ? '; ' : part === '：' ? ': ' : part === '、' ? ', ' : part === '／' ? ' / ' : translate(part, locale, depth + 1)).join('');
 }
 if (result === undefined && key.includes('。')) {
  const sentences = key.match(/[^。]+。?|。/g) ?? [];
  if (sentences.length > 1) result = sentences.map(part => translate(part, locale, depth + 1)).join(' ');
 }
 if (result === undefined) return text;
 return text.slice(0, text.indexOf(key)) + result + text.slice(text.indexOf(key) + key.length);
}
