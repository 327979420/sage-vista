"use client";
import {useEffect,useState} from 'react';
import {useNavigationCount} from './navigation-count';
import {usePathname} from 'next/navigation';
import {LanguageSwitch,useLocale} from './i18n/locale';

// Terminal shell: top status bar, a strip of real events and five sections in a side menu.
// [zh label, en label, path]; each section lists the pages it absorbed.
export const siteSections = [
 ['总览', 'Overview', [['今日', 'Today', '/']]],
 ['3W', '3W', [['信号', 'Signals', '/signals'], ['前向记录', 'Forward record', '/forward'], ['我的组合', 'My portfolio', '/portfolio']]],
 ['市场', 'Market', [['大盘', 'Market', '/zh/watch/market'], ['行业', 'Sectors', '/zh/watch/industry-radar']]],
 ['候选', 'Candidates', [['多因子', 'Multi-factor', '/zh/watch/resonance/rare-opportunities'], ['形态', 'Daily setups', '/patterns']]],
 ['研究', 'Research', [['回测', 'Backtests', '/zh/backtest'], ['研究档案', 'Archive', '/archive'], ['学习', 'Learn', '/learn'], ['关于 SV', 'About SV', '/zh/watch/resonance/about']]],
] as const;
// Old addresses that render a page above, so its menu entry stays lit.
const ALIASES: Record<string, string> = {'/opportunities': '/signals', '/scorecard': '/forward', '/zh/watch/resonance/favorite-pattern': '/patterns'};

type Status = {as_of?: string; status?: string};
type Today = {signal_week?: string; new_signals_this_week?: number; orders_to_place?: number;
 market?: {light?: string; breadth?: number; distance_pct?: number}; month_end?: {rebalance_due?: boolean}};
type Record_ = {forward?: {signals?: number; counts?: {closed?: number; open?: number; waiting?: number}}};

const getJson = <T,>(url: string) => fetch(url, {cache: 'no-store'}).then(r => r.ok ? r.json() as Promise<T> : null).catch(() => null);
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

function events(locale: string, today: Today | null, record: Record_ | null, status: Status | null): string[] {
 const en = locale === 'en', out: string[] = [];
 if (status?.as_of) out.push(en ? `Data ${status.as_of.slice(5)} close · checked and published` : `数据 ${status.as_of.slice(5)} 收盘 · 已核对发布`);
 const m = today?.market;
 if (m?.breadth != null && m.distance_pct != null) out.push(en
  ? `Gate ${m.light === 'green' ? 'green' : 'amber'} · breadth ${(m.breadth * 100).toFixed(1)}% · SPY ${pct(m.distance_pct)} vs 200-day`
  : `闸门${m.light === 'green' ? '绿灯' : '黄灯'} · 广度 ${(m.breadth * 100).toFixed(1)}% · SPY 距 200 日线 ${pct(m.distance_pct)}`);
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
 const current = ALIASES[path] ?? path;
 const live = status?.status === 'up_to_date', light = today?.market?.light;
 const items = events(locale, today, record, status);
 return <>
  <header className="svTopBar">
   <a className="svBrand" href={siteSections[0][2][0][2]} aria-label="Sage Vista">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 21 20H3Z"/><path d="M12 9 16.5 17h-9Z"/></svg>
    <b>SAGE VISTA</b><i>{'//'}</i><span>{en ? '3W research desk' : '3W 研究台'}</span>
   </a>
   <div className="svPills">
    <span className="svPill"><em data-state={status ? (live ? 'go' : 'wait') : 'idle'}/>{status ? (en ? (live ? 'Daily update OK' : 'Update pending') : (live ? '日更 正常' : '日更 待核对')) : (en ? 'Loading' : '读取中')}</span>
    {light && <span className="svPill"><em data-state={light === 'green' ? 'go' : 'wait'}/>{en ? `Gate ${light === 'green' ? 'green' : 'amber'}` : `闸门 ${light === 'green' ? '绿灯' : '黄灯'}`}</span>}
    <span className="svPill">{en ? 'Rule 3w-1.9 · frozen' : '规则 3w-1.9 · 已冻结'}</span>
   </div>
   <div className="svClock"><small>{en ? 'New York' : '纽约'}</small><b>{ny}</b><span>ET</span></div>
   <LanguageSwitch/>
  </header>
  <div className="svTicker" aria-label={en ? 'Latest events' : '最新动态'}>
   <div className="svTickerTrack">{items.length ? [...items, ...items].map((text, i) => <span key={i} aria-hidden={i >= items.length || undefined}>{text}</span>) : <span>{en ? 'Reading the latest data…' : '正在读取最新数据…'}</span>}</div>
  </div>
  <nav className="svSideNav" aria-label={en ? 'Main sections' : '主要功能'}>
   {siteSections.map(([zh, enLabel, links]) => <div key={zh} className="svNavGroup">
    <small>{en ? enLabel : zh}</small>
    {links.map(([label, labelEn, href]) => {
     const active = current === href;
     return <a key={href} href={href} className={active ? 'active' : undefined} aria-current={active ? 'page' : undefined}>
      <span>{en ? labelEn : label}</span>{active && count?.path === href && <em className="rtStarCount" title={href === '/' ? '新信号' : '持仓'}>{count.value}</em>}
     </a>;
    })}
   </div>)}
   <div className="svNavFoot"><b>{`Sage Vista ${uiVersion}`}</b><span>{`Build ${build}`}</span></div>
  </nav>
 </>;
}
