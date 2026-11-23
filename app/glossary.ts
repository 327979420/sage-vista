// Tap-to-explain definitions: one sentence each, only for words a visitor cannot act without.
// Anything needed to act stays visible on the page; these only define a term (dotted underline).
export const GLOSSARY = {
 light: {
  en: 'Green when SPY is above its 200-day average and over half of the 3W stocks are above theirs. On amber, new signals are not ordered.',
  zh: 'SPY 在 200 日线上方、且 3W 股票过半站上各自 200 日线时是绿灯；黄灯时新信号不下单。'},
 breadth: {
  en: 'Share of the 3W stocks above their own 200-day average. Over half counts as strong.',
  zh: '3W 股票里站上各自 200 日线的比例，过半才算强。'},
 rr: {
  en: 'Distance to the target divided by distance to the stop. 3W needs at least 1.5.',
  zh: '到目标的距离除以到止损的距离，3W 至少要 1.5。'},
 r: {
  en: 'One R is the loss if the stop is hit. +2R means twice that.',
  zh: '1R 是打到止损的亏损，+2R 就是它的两倍。'},
 limit: {
  en: 'A buy order 2% under the signal close, valid for up to 8 weeks.',
  zh: '在信号收盘价下方 2% 挂的买单，最多等 8 周。'},
 locked: {
  en: 'Rule v1.9 has not changed since 2026-10-16, so the forward record is a fair test.',
  zh: '规则 v1.9 自 2026-10-16 起没改过，所以前向记录是公平的检验。'},
 turtle: {
  en: 'In 1983 Richard Dennis taught beginners a few written rules to prove trading can be taught. All got the same rules; results differed with how strictly each followed them.',
  zh: '1983 年 Richard Dennis 只教新手几条写好的规则，想证明交易能教会。规则人人相同，成绩差在谁能照做。'},
 proof: {
  en: '100 closed trades after the lock that beat random picks by more than luck would (t ≥ 2), with the account ahead of SPY.',
  zh: '锁定后平仓满 100 笔，明显好于随机选股（t ≥ 2），且账户跑赢 SPY。'},
} as const;

export type GlossaryKey = keyof typeof GLOSSARY;
