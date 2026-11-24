"use client";
import {useEffect, useId, useRef, useState, type ReactNode} from 'react';
import {useLocale} from './i18n/locale';
import {GLOSSARY, type GlossaryKey} from './glossary';

// A word with a dotted underline; hover, focus or tap shows its one-sentence definition
// (the "definition tooltip" pattern). It never hides anything a visitor needs to act.
export default function Term({k, children}: {k: GlossaryKey; children: ReactNode}) {
 const {locale} = useLocale();
 const [open, setOpen] = useState(false);
 const id = useId();
 const box = useRef<HTMLSpanElement>(null);
 useEffect(() => {
  if (!open) return;
  const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false); };
  const onDown = (event: PointerEvent) => { if (box.current && !box.current.contains(event.target as Node)) setOpen(false); };
  window.addEventListener('keydown', onKey);
  window.addEventListener('pointerdown', onDown);
  return () => { window.removeEventListener('keydown', onKey); window.removeEventListener('pointerdown', onDown); };
 }, [open]);
 return <span className="svTerm" ref={box} onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
  <button type="button" aria-describedby={open ? id : undefined} aria-expanded={open} onClick={() => setOpen(!open)} onBlur={() => setOpen(false)}>{children}</button>
  {open && <span className="svTermTip" role="tooltip" id={id}>{GLOSSARY[k][locale === 'en' ? 'en' : 'zh']}</span>}
 </span>;
}
