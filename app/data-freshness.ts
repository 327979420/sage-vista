// When the published data counts as late. The daily run normally lands around 19:00–20:00 New York time,
// so by midnight New York every NYSE session before today should be in; one missing session is late.

// NYSE weekday closures, copied from data/calendars/xnys-2005-2030.json (tests/test_site_calendar.py keeps them equal).
// After 2030 every weekday counts as a session.
export const NYSE_CLOSED = new Set([
 '2026-01-01', '2026-01-19', '2026-02-16', '2026-04-03', '2026-05-25', '2026-06-19', '2026-07-03', '2026-09-07', '2026-11-26', '2026-12-25',
 '2027-01-01', '2027-01-18', '2027-02-15', '2027-03-26', '2027-05-31', '2027-06-18', '2027-07-05', '2027-09-06', '2027-11-25', '2027-12-24',
 '2028-01-17', '2028-02-21', '2028-04-14', '2028-05-29', '2028-06-19', '2028-07-04', '2028-09-04', '2028-11-23', '2028-12-25',
 '2029-01-01', '2029-01-15', '2029-02-19', '2029-03-30', '2029-05-28', '2029-06-19', '2029-07-04', '2029-09-03', '2029-11-22', '2029-12-25',
 '2030-01-01', '2030-01-21', '2030-02-18', '2030-04-19', '2030-05-27', '2030-06-19', '2030-07-04', '2030-09-02', '2030-11-28', '2030-12-25',
]);

const newYorkDate = (now: Date) => new Intl.DateTimeFormat('en-CA', {timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit'}).format(now);

export function isSession(iso: string) {
 const weekday = new Date(iso + 'T00:00:00Z').getUTCDay();
 return weekday !== 0 && weekday !== 6 && !NYSE_CLOSED.has(iso);
}

// NYSE sessions after the data date and before today in New York: each of them should already be published.
export function sessionsLate(dataDate: string, now: Date) {
 if (!/^\d{4}-\d{2}-\d{2}$/.test(dataDate) || Number.isNaN(Date.parse(dataDate))) return 0;
 const today = newYorkDate(now);
 let late = 0;
 for (const d = new Date(dataDate + 'T00:00:00Z'); ; ) {
  d.setUTCDate(d.getUTCDate() + 1);
  const iso = d.toISOString().slice(0, 10);
  if (iso >= today) break;
  if (isSession(iso)) late++;
 }
 return late;
}
