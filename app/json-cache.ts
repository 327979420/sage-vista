// One request per published file per page view: the shell, the page and its panels often need the
// same small JSON (update status, today, record, the candidate ranking). Entries expire after a
// minute so a long-open tab still picks up a new daily update.
const TTL_MS = 60_000;
const entries = new Map<string, {at: number; value: Promise<unknown>}>();

export function sharedJson<T>(url: string, load: () => Promise<Response> = () => fetch(url, {cache: 'no-store'})): Promise<T | null> {
 const hit = entries.get(url);
 if (hit && Date.now() - hit.at < TTL_MS) return hit.value as Promise<T | null>;
 const value = load().then(r => (r.ok ? r.json() as Promise<T> : null)).catch(() => null);
 entries.set(url, {at: Date.now(), value});
 return value;
}
