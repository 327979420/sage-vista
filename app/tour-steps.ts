// "Start here": four pages in the order a new visitor needs them, one short line each.
// Opened from the top bar (and the footer, /?tour=1); it never covers the page.
// Pattern borrowed from product "getting started" checklists: 3–5 steps, non-blocking.
export type TourStep = {id: string; href: string; title: {en: string; zh: string}; text: {en: string; zh: string}};

export const TOUR_STEPS: TourStep[] = [
 {id: 'today', href: '/',
  title: {en: 'Today', zh: '今日'},
  text: {en: 'Do I need to act today?', zh: '今天要不要动？'}},
 {id: 'signals', href: '/signals',
  title: {en: 'Signals', zh: '信号'},
  text: {en: 'This week’s setups and why each passed or not.', zh: '本周的形态，过没过、为什么。'}},
 {id: 'forward', href: '/forward',
  title: {en: 'Forward record', zh: '前向记录'},
  text: {en: 'The live score since the rule froze.', zh: '规则冻结后的真实成绩。'}},
 {id: 'learn', href: '/learn',
  title: {en: 'Learn', zh: '学习'},
  text: {en: 'The rule in four steps.', zh: '四步看懂规则。'}},
];

export const TOUR_COPY = {
 button: {en: 'New here?', zh: '新手？'},
 title: {en: 'Start here', zh: '从这里开始'},
 close: {en: 'Got it', zh: '知道了'},
};

// The pulse on the button shows once per browser. Cookies and storage are per device and
// browser, so a new device or browser counts as new; IP addresses are not used.
export const TOUR_SEEN_KEY = 'sv-onboarded';

export function tourSeen(cookie: string, stored: string | null) {
 return stored === '1' || cookie.split(/;\s*/).some(part => part === `${TOUR_SEEN_KEY}=1`);
}
