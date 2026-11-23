"use client";
import {useEffect} from 'react';

// Site-wide motion, after hydration and only without reduced motion (Material motion: short
// ease-out entrances, a small stagger). Panels rise into place when they scroll into view, the
// CSS animations inside them (chart draws, bar growth) wait until then, and headline numbers count
// up from zero to their real value. Movement only ever replays the real numbers on the page.
const REVEAL = '.ovPanel, .ovFold, .fvBanner, .sbNear, .sbCard, .mfCard, .fwFact, .siteFooter';
const COUNT = '.ovPanel > b, .ovGateTop > b, .ovTrack li > b, .sbFacts dd, .mkKpis .ovPanel > b, .mfScore, .mfNarrow b, .fwGates b, .pfNums b';
const NUMBER = /^([+−-]?)(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(%?)$/;

function countUp(el: Element) {
 const node = [...el.childNodes].find(n => n.nodeType === Node.TEXT_NODE && n.nodeValue?.trim());
 if (!node?.nodeValue) return;
 const text = node.nodeValue, core = text.trim(), match = core.match(NUMBER);
 if (!match) return;
 const [, sign, whole, fraction = '', percent] = match;
 const target = Number(whole.replace(/,/g, '') + fraction);
 if (!Number.isFinite(target) || target === 0) return;
 const digits = fraction ? fraction.length - 1 : 0, grouped = whole.includes(','), start = text.indexOf(core);
 const show = (v: number) => text.slice(0, start) + sign + (grouped ? v.toLocaleString('en-US', {minimumFractionDigits: digits, maximumFractionDigits: digits}) : v.toFixed(digits)) + percent + text.slice(start + core.length);
 let written = show(0), begin = 0;
 node.nodeValue = written;
 const step = (now: number) => {
  // React owns this text: if it changed the value meanwhile, stop and keep React's value.
  if (node.nodeValue !== written) return;
  begin ||= now;
  const p = Math.min(1, (now - begin) / 900);
  written = p < 1 ? show(target * (1 - Math.pow(1 - p, 3))) : text;
  node.nodeValue = written;
  if (p < 1) requestAnimationFrame(step);
 };
 requestAnimationFrame(step);
}

export default function Motion() {
 useEffect(() => {
  if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches || !('IntersectionObserver' in window)) return;
  const root = document.documentElement, seen = new WeakSet<Element>(), counted = new WeakSet<Element>();
  const view = new IntersectionObserver(entries => {
   let k = 0;
   for (const entry of entries) {
    if (!entry.isIntersecting) continue;
    const el = entry.target as HTMLElement;
    view.unobserve(el);
    if (el.matches(COUNT)) { if (!counted.has(el)) { counted.add(el); countUp(el); } continue; }
    el.style.setProperty('--svIn', `${Math.min(k++, 6) * 70}ms`);
    el.setAttribute('data-in', '');
   }
  }, {rootMargin: '0px 0px -8% 0px'});
  const scan = (scope: ParentNode) => {
   for (const el of scope.querySelectorAll(REVEAL)) {
    if (seen.has(el)) continue;
    seen.add(el);
    view.observe(el);
   }
   for (const el of scope.querySelectorAll(COUNT)) {
    if (counted.has(el) || seen.has(el)) continue;
    seen.add(el);
    view.observe(el);
   }
  };
  // What is already on screen at start stays put (no flash); everything else waits to rise in.
  for (const el of document.querySelectorAll(REVEAL)) {
   const box = el.getBoundingClientRect();
   if (box.top < innerHeight && box.bottom > 0) { el.setAttribute('data-in', ''); seen.add(el); }
  }
  root.setAttribute('data-motion', '');
  scan(document);
  // Data-driven panels arrive after the first render; pick them up as they appear.
  const added = new MutationObserver(records => { for (const r of records) for (const n of r.addedNodes) if (n instanceof Element) { if (n.matches(REVEAL) || n.matches(COUNT)) scan(n.parentElement ?? document); else scan(n); } });
  added.observe(document.body, {childList: true, subtree: true});
  return () => { added.disconnect(); view.disconnect(); root.removeAttribute('data-motion'); };
 }, []);
 return null;
}
