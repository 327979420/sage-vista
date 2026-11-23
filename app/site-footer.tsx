import {Localized} from './i18n/locale';
import PrivacyNote from './privacy-note';

// Quiet site footer: About SV lives here as reading links, not a header button.
const ABOUT = '/zh/watch/resonance/about';
const columns: [string, [string, string][]][] = [
 ['关于 SV', [['SV 是什么', `${ABOUT}#what-is-sv`], ['如何使用 SV', `${ABOUT}#how-to-use`], ['免责声明', `${ABOUT}#disclaimer`], ['从这里开始', '/?tour=1']]],
 ['探索', [['今日', '/'], ['信号', '/signals'], ['前向记录', '/forward'], ['大盘', '/zh/watch/market'], ['行业', '/zh/watch/industry-radar']]],
 ['方法', [['四步看懂 3W', '/learn'], ['回测', '/zh/backtest'], ['研究档案', '/archive']]],
];

export default function SiteFooter() {
 return <Localized><footer className="siteFooter">
  <div className="siteFooterColumns">{columns.map(([title, links]) => <nav key={title} aria-label={title}><h2>{title}</h2><ul>{links.map(([label, href]) => <li key={label}><a href={href}>{label}</a></li>)}</ul></nav>)}</div>
  <div className="siteFooterBottom"><span>© 2026 Sage Vista</span><span>研究工具，不构成投资建议</span><span>数据来源：EODHD、FINRA、CFTC、iShares、SPDR、Invesco、OCC</span><span>每个美股交易日收盘后更新</span><span>TradingView Lightweight Charts™ · <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">TradingView</a></span><PrivacyNote/></div>
 </footer></Localized>;
}
