import {localizedMetadata} from '../i18n/server';
import {Localized} from '../i18n/locale';
import {strings as s} from '../app/strings';
export const generateMetadata=()=>localizedMetadata({title:'Sage Vista — 研究档案'},{title:'Sage Vista — Research Archive'});
const links=[['大盘','/zh/watch/market'],['行业','/zh/watch/industry-radar'],['多因子机会','/zh/watch/resonance/rare-opportunities'],['我最喜欢形态','/zh/watch/resonance/favorite-pattern'],['回测','/zh/backtest'],['功能介绍与方法','/zh/watch/resonance/about']] as const;
export default function Page() {
 return <Localized><main className="rtPage rtFeaturedPage cockpit marketSummaryPage svApp"><header className="rtSubHero"><div><p>SAGE VISTA</p><h1>{s.archive}</h1><p className="rtHeroDescription">{s.archiveIntro}</p></div></header><section className="cockpitCard cockpitBody"><nav className="svArchiveLinks" aria-label={s.archive}>{links.map(([label,href])=><a key={href} href={href}>{label}</a>)}</nav></section></main></Localized>;
}
