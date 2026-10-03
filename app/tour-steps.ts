// First-visit tour for the current version of SV. One sentence per step; the
// screenshot carries the detail. Add future topics (position size, stops,
// paper trading) as new steps here. Images: public/tour/<lang>/<image>.webp,
// regenerated with scripts/capture-tour-screens.mjs.
export type TourStep = {id: string; icon: string; image: string; title: {en: string; zh: string}; text: {en: string; zh: string}};

export const TOUR_STEPS: TourStep[] = [
 {id: 'multi-factor', icon: '🎯', image: 'multi-factor',
  title: {en: 'Multi-Factor Opportunities', zh: '多因子机会'},
  text: {en: 'Start here: our main list of strong stocks pulling back in an uptrend.', zh: '从这里开始：我们的主榜单，上升趋势中正在回调的强势股。'}},
 {id: 'search', icon: '🔍', image: 'search',
  title: {en: 'Find a stock', zh: '查找股票'},
  text: {en: 'Type any ticker, like BJ, to see why it is or isn’t on the list.', zh: '输入任意代码（如 BJ），看它为什么入榜或没有入榜。'}},
 {id: 'daily-setups', icon: '⚡', image: 'daily-setups',
  title: {en: 'Daily Setups', zh: '我最喜欢形态'},
  text: {en: 'A quick scan of today’s 100 most-traded stocks for clean pullback setups.', zh: '快速扫描当天成交额最大的 100 只股票，寻找清晰的回调形态。'}},
 {id: 'market-sectors', icon: '📊', image: 'market',
  title: {en: 'Market and Sectors', zh: '大盘与行业'},
  text: {en: 'Optional context: check whether the market is strong and which sectors are leading.', zh: '辅助参考：看看大盘强不强、哪个行业在领涨。'}},
];

export const TOUR_COPY = {
 welcome: {en: 'Welcome to Sage Vista 👋', zh: '欢迎来到 Sage Vista 👋'},
 question: {en: 'Have you used Sage Vista before?', zh: '你以前用过 Sage Vista 吗？'},
 yes: {en: 'Yes, take me to the list', zh: '用过，直接看榜单'},
 no: {en: 'I’m new, show me around', zh: '第一次用，带我看看'},
 skip: {en: 'Skip', zh: '跳过'},
 skipTour: {en: 'Skip tour', zh: '跳过导览'},
 back: {en: 'Back', zh: '上一步'},
 next: {en: 'Next', zh: '下一步'},
 doneTitle: {en: 'You’re all set ✅', zh: '准备好了 ✅'},
 doneText: {en: 'The list refreshes after every US market close.', zh: '每个美股交易日收盘后，榜单都会更新。'},
 go: {en: 'Go to the list', zh: '去看榜单'},
 step: {en: 'Step', zh: '第'},
 of: {en: 'of', zh: '/'},
};

// The tour shows once per browser. Cookies and storage are per device and
// browser, so a new device or browser counts as new; IP addresses are not used.
export const TOUR_SEEN_KEY = 'sv-onboarded';

export function tourSeen(cookie: string, stored: string | null) {
 return stored === '1' || cookie.split(/;\s*/).some(part => part === `${TOUR_SEEN_KEY}=1`);
}
