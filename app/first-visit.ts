// First-visit view: the server shows the intro while this cookie is absent; the intro sets it,
// so the next visit opens the normal page. /?intro=1 shows the intro again on demand.
export const SEEN_COOKIE = 'sv-seen';
export const INTRO_HREF = '/?intro=1';
// Rule v1.9 has not changed since this date; only signals from then on count.
export const RULE_LOCKED = '2026-10-16';

export function markSeen() {
 try { document.cookie = `${SEEN_COOKIE}=1; Path=/; Max-Age=31536000; SameSite=Lax${location.protocol === 'https:' ? '; Secure' : ''}`; } catch { /* cookies may be disabled */ }
}
export const seenFrom = (cookieValue: string | undefined) => cookieValue === '1';
