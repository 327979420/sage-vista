import {Localized} from './i18n/locale';

// Quiet site footer: About SV lives here as reading links, not a header button.
const ABOUT = '/zh/watch/resonance/about';
const columns: [string, [string, string][]][] = [
 ['关于 SV', [['SV 是什么', `${ABOUT}#what-is-sv`], ['如何使用 SV', `${ABOUT}#how-to-use`], ['免责声明', `${ABOUT}#disclaimer`], ['新手导览', '/?tour=1']]],
 ['探索', [['多因子机会', '/'], ['大盘', '/zh/watch/market'], ['行业', '/zh/watch/industry-radar'], ['我最喜欢形态', '/zh/watch/resonance/favorite-pattern'], ['回测', '/zh/backtest']]],
 ['方法', [['三重滤网交易系统', `${ABOUT}#opportunity`], ['顺势回调形态', `${ABOUT}#setup`], ['多周期共振评分', `${ABOUT}#confluence`], ['板块轮动与每日复评', `${ABOUT}#re-scoring`], ['时点数据与样本外验证', `${ABOUT}#checked`]]],
];

export default function SiteFooter() {
 return <Localized><footer className="siteFooter">
  <div className="siteFooterColumns">{columns.map(([title, links]) => <nav key={title} aria-label={title}><h2>{title}</h2><ul>{links.map(([label, href]) => <li key={label}><a href={href}>{label}</a></li>)}</ul></nav>)}</div>
  <div className="siteFooterBottom"><span>© 2026 Sage Vista</span><span>研究工具，不构成投资建议</span><span>数据来源：EODHD、FINRA、CFTC、ICI、OCC</span><span>每个美股交易日收盘后更新</span></div>
 </footer></Localized>;
}
