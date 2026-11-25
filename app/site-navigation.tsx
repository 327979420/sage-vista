"use client";
import {useEffect,useRef,useState} from 'react';
import {useNavigationCount} from './navigation-count';
import {usePathname} from 'next/navigation';
import {LanguageSwitch,useLocale} from './i18n/locale';
import {sharedJson} from './json-cache';
import {INTRO_HREF} from './first-visit';
import Term from './term';
import {sessionsLate} from './data-freshness';

// Terminal shell: top status bar, a strip of real events and five sections in a side menu.
// Each section says what it is; a tag says how far it is proven (3W: a locked rule under forward test; the daily lists:
// watch only); each link has one line saying what question its page answers. [zh, en, path, zh line, en line].
type NavTag = 'locked' | 'watch';
type NavLink = [string, string, string, string, string];
type NavSection = [string, string, NavLink[], NavTag?];
export const siteSections: NavSection[] = [
 ['总览', 'Overview', [
  ['今日', 'Today', '/', '今天要不要下单', 'Orders to place today'],
  ['模拟账户', 'Paper account', '/portfolio', '行业篮子 50% + 3W 50%', 'Sector basket 50% + 3W 50%'],
  ['查股票', 'Stock lookup', '/stock', '一只股票在各名单里的状态', 'One stock across every list']]],
 ['3W 周线三角形', '3W weekly triangle', [
  ['信号', 'Signals', '/signals', '锁定后找到的形态，能不能下单', 'Setups since the lock'],
  ['成绩单', 'Scorecard', '/forward', '锁定后的真实成绩（前向记录）', 'Real results since the lock']], 'locked'],
 ['日线观察名单', 'Daily watchlists', [
  ['多因子排行', 'Multi-factor ranking', '/multi-factor', '每天给约 1,500 只打分，取前 30', 'Top 30 of about 1,500, daily'],
  ['日线形态', 'Daily setups', '/patterns', '回调、双底、三推突破', 'Double bottom, then breakout']], 'watch'],
 ['大盘和行业', 'Market and sectors', [
  ['大盘', 'Market', '/market', '大盘灯和上涨股票占比', 'Market light and breadth'],
  ['行业', 'Sectors', '/sectors', '行业强弱和资金流向', 'Sector strength and fund flows']]],
 ['说明和研究', 'Guide and research', [
  ['学习', 'Learn', '/learn', '用一笔真实交易讲懂 3W', '3W on one real trade'],
  ['关于 SV', 'About SV', '/about', 'SV 是什么、怎么用', 'What SV is and how to use it'],
  ['回测', 'Backtests', '/backtests', '历史测试，只算线索', 'History tests: hints only'],
  ['研究档案', 'Archive', '/archive', '旧工具原样保留', 'Old tools, kept as they were']]],
];
const NAV_TAGS: Record<NavTag, [string, string]> = {locked: ['正式 · 规则已锁定', 'Live · rule locked'], watch: ['观察 · 未证明', 'Watch only · not proven']};
const HOME = '/', STOCK = '/stock';
// Old addresses that render a page above, so its menu entry stays lit.
const ALIASES: Record<string, string> = {'/opportunities': '/signals', '/scorecard': '/forward'};

type Status = {as_of?: string; status?: string; source_latest_complete_date?: string};
type Today = {signal_week?: string; new_signals_this_week?: number; orders_to_place?: number;
 market?: {light?: string; breadth?: number; distance_pct?: number}; month_end?: {rebalance_due?: boolean}};
type Record_ = {forward?: {signals?: number; counts?: {closed?: number; open?: number; waiting?: number}}};

const getJson = <T,>(url: string) => sharedJson<T>(url);
const shift = (iso: string, days: number) => { const d = new Date(iso + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + days); return d.toISOString().slice(5, 10); };
const pct = (v: number) => (v > 0 ? '+' : '') + v.toFixed(1) + '%';
function useShellData() {
 const [data, setData] = useState<{status: Status | null; today: Today | null; record: Record_ | null}>({status: null, today: null, record: null});
 useEffect(() => {
  Promise.all([getJson<Status>('/update-status.json'), getJson<Today>('/app/today.json'), getJson<Record_>('/app/record.json')])
   .then(([status, today, record]) => setData({status, today, record}));
 }, []);
 return data;
}

function useNewYorkTime() {
 // Rendered after mount only, so server and client markup agree.
 const [time, setTime] = useState('--:--:--');
 useEffect(() => {
  const tick = () => setTime(new Date().toLocaleTimeString('en-GB', {timeZone: 'America/New_York', hour12: false}));
  tick(); const id = setInterval(tick, 1000); return () => clearInterval(id);
 }, []);
 return time;
}

function events(locale: string, today: Today | null, record: Record_ | null): string[] {
 const en = locale === 'en', out: string[] = [];
 const m = today?.market;
 if (m?.breadth != null && m.distance_pct != null) out.push(en
  ? `Market light ${m.light === 'green' ? 'green' : 'amber'} · ${(m.breadth * 100).toFixed(1)}% of 3W stocks above their 200-day · SPY ${pct(m.distance_pct)} vs its 200-day`
  : `市场灯${m.light === 'green' ? '绿' : '黄'} · 3W 股票 ${(m.breadth * 100).toFixed(1)}% 站上 200 日线 · SPY 距 200 日线 ${pct(m.distance_pct)}`);
 if (today?.new_signals_this_week != null) out.push(en
  ? `This week: ${today.new_signals_this_week} new 3W signals · ${today.orders_to_place ?? 0} orders to place`
  : `本周 3W 新信号 ${today.new_signals_this_week} 个 · 待下单 ${today.orders_to_place ?? 0} 个`);
 const f = record?.forward;
 if (f?.signals != null) { const closed = f.counts?.closed ?? 0; out.push(en
  ? `Forward record: ${f.signals} signals · ${closed} closed trades · ${Math.max(0, 100 - closed)} to go for proof`
  : `前向记录 ${f.signals} 个信号 · 已平仓 ${closed} 笔 · 离证明还差 ${Math.max(0, 100 - closed)} 笔`); }
 // A week's signals are recognised after the first session of the week after next (Friday + 10 days).
 if (today?.signal_week) out.push(en ? `Next scan: week of ${today.signal_week.slice(5)}, after the ${shift(today.signal_week, 10)} close`
  : `下一次扫描：${today.signal_week.slice(5)} 周，${shift(today.signal_week, 10)} 收盘后`);
 if (today?.month_end?.rebalance_due) out.push(en ? 'Month-end rebalance due today' : '今天是月底调仓日');
 return out;
}

export default function SiteNavigation({uiVersion, build}: {uiVersion: string; build: string}) {
 const path = usePathname(), count = useNavigationCount(), {locale} = useLocale(), en = locale === 'en';
 const {status, today, record} = useShellData(), ny = useNewYorkTime();
 const current = ALIASES[path] ?? (path.startsWith('/stock/') ? '/stock' : path);
 const live = status?.status === 'up_to_date', light = today?.market?.light;
 // Show the data date, not just "OK": late data turns amber even if the last run reported success.
 const dataDate = status?.source_latest_complete_date ?? status?.as_of;
 const late = dataDate ? sessionsLate(dataDate, new Date()) : 0;
 const dataState = !status ? 'idle' : live && late === 0 ? 'go' : 'wait';
 const dataLabel = !status ? (en ? 'Loading' : '读取中') : !dataDate ? (en ? 'Update pending' : '日更待核对')
  : late > 0 ? (en ? `Data ${dataDate.slice(5)} · ${late} session${late > 1 ? 's' : ''} late` : `数据 ${dataDate.slice(5)} · 晚 ${late} 个交易日`)
  : (en ? `Data ${dataDate.slice(5)}` : `数据 ${dataDate.slice(5)}`);
 const items = events(locale, today, record);
 // On phones the menu is one sideways strip: bring the current page into view so the visitor sees where they are.
 const navRef = useRef<HTMLElement>(null);
 useEffect(() => {
  const nav = navRef.current, active = nav?.querySelector<HTMLElement>('a.active');
  if (!nav || !active || nav.scrollWidth <= nav.clientWidth) return;
  const a = active.getBoundingClientRect(), n = nav.getBoundingClientRect();
  nav.scrollLeft += a.left - n.left - (n.width - a.width) / 2;
 }, [current]);
 return <>
  <header className="svTopBar">
   <a className="svBrand" href={HOME} aria-label="Sage Vista">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 21 20H3Z"/><path d="M12 9 16.5 17h-9Z"/></svg>
    <b>SAGE VISTA</b><i>{'//'}</i><span>{en ? 'Freddy Liang’s US stock research' : 'Freddy Liang 的美股研究'}</span>
   </a>
   <div className="svPills">
    <span className="svPill"><em data-state={dataState}/>{dataLabel}</span>
    {light && <span className="svPill"><em data-state={light === 'green' ? 'go' : 'wait'}/><span><Term k="light">{en ? 'Market light' : '市场灯'}</Term>{en ? `: ${light === 'green' ? 'green' : 'amber'}` : `：${light === 'green' ? '绿' : '黄'}`}</span></span>}
    <span className="svPill"><span>{en ? 'Rule v1.9 · ' : '规则 v1.9 · '}<Term k="locked">{en ? 'locked' : '已锁定'}</Term></span></span>
   </div>
   <a className="slTopLink" href={STOCK} aria-label={en ? 'Look up a stock' : '查股票'} title={en ? 'Look up a stock' : '查股票'}>
    <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg></a>
   <div className="svClock"><small>{en ? 'New York' : '纽约'}</small><b>{ny}</b><span>ET</span></div>
   <a className="svStartButton" href={INTRO_HREF}>{en ? 'What is SV?' : 'SV 是什么？'}</a>
   <LanguageSwitch/>
  </header>
  <div className="svTicker" aria-label={en ? 'Latest events' : '最新动态'}>
   <div className="svTickerTrack">{items.length ? [...items, ...items].map((text, i) => <span key={i} aria-hidden={i >= items.length || undefined}>{text}</span>) : <span>{en ? 'Reading the latest data…' : '正在读取最新数据…'}</span>}</div>
  </div>
  <nav ref={navRef} className="svSideNav" aria-label={en ? 'Main sections' : '主要功能'}>
   {siteSections.map(([zh, enLabel, links, tag]) => <div key={zh} className="svNavGroup">
    <div className="svNavHead"><small>{en ? enLabel : zh}</small>{tag && <span className="svNavTag" data-tag={tag}>{NAV_TAGS[tag][en ? 1 : 0]}</span>}</div>
    {links.map(([label, labelEn, href, note, noteEn]) => {
     const active = current === href;
     return <a key={href} href={href} className={active ? 'active' : undefined} aria-current={active ? 'page' : undefined}>
      <span className="svNavText"><span>{en ? labelEn : label}</span><i>{en ? noteEn : note}</i></span>{active && count?.path === href && <em className="rtStarCount" title={href === '/' ? '新信号' : '持仓'}>{count.value}</em>}
     </a>;
    })}
   </div>)}
   <div className="svNavFoot"><b>{`Sage Vista ${uiVersion}`}</b><span>{`Build ${build}`}</span></div>
  </nav>
 </>;
}
