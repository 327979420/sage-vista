"use client";
import posthog from 'posthog-js';
import {useEffect} from 'react';

/* PostHog visitor analytics (US cloud), shared with freddyliang.com: the cookie on
 * .freddyliang.com keeps one anonymous visitor across both sites, and opting out on
 * either site applies to both. No session replay. Deployed hosts only; local dev stays silent.
 * The project key is public by design. */
const POSTHOG_KEY = 'phc_tT898VwuWXwX7s5zaAaJjuzz9qKa2j3tNqrKsxn5W6d8';
const POSTHOG_HOST = 'https://us.i.posthog.com';
const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]']);

let searchTimer: ReturnType<typeof setTimeout> | undefined;

function start() {
 if (posthog.__loaded || process.env.NODE_ENV !== 'production' || LOCAL_HOSTS.has(location.hostname)) return;
 posthog.init(POSTHOG_KEY, {
  api_host: POSTHOG_HOST,
  defaults: '2026-08-30',
  person_profiles: 'identified_only',
  disable_session_recording: true,
  capture_heatmaps: true,
  opt_out_capturing_persistence_type: 'cookie',
  respect_dnt: true,
 });
 document.addEventListener('input', trackSearch);
}

export function trackEvent(event: string, properties?: Record<string, string | number | boolean>) {
 if (posthog.__loaded) posthog.capture(event, properties);
}

// Ticker / sector searches filter as you type, so record the settled query once typing pauses.
function trackSearch(event: Event) {
 const input = event.target;
 if (!(input instanceof HTMLInputElement) || !['text', 'search'].includes(input.type)) return;
 clearTimeout(searchTimer);
 searchTimer = setTimeout(() => {
  const query = input.value.trim().slice(0, 40);
  if (query) trackEvent('search_used', {query, field: input.getAttribute('aria-label') ?? input.name, page: location.pathname});
 }, 1200);
}

/** Starts PostHog once per page load; navigation is full-page, so each load records a pageview. */
export default function Analytics() {
 useEffect(start, []);
 return null;
}

export const trackingActive = () => { start(); return posthog.__loaded; };
export const optedOut = () => posthog.__loaded && posthog.has_opted_out_capturing();
export function setOptedOut(value: boolean) {
 if (!posthog.__loaded) return;
 if (value) posthog.opt_out_capturing(); else posthog.opt_in_capturing();
}
