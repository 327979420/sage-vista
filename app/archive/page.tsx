import {localizedMetadata} from '../i18n/server';
import {Localized} from '../i18n/locale';
import {strings as s} from '../app/strings';
import {ArchiveGrid} from '../app/research-heads';
import MoreDetails from '../app/more-details';
export const generateMetadata=()=>localizedMetadata({title:'Sage Vista — 研究档案'},{title:'Sage Vista — Research Archive'});
const links=[['大盘','/zh/watch/market'],['行业','/zh/watch/industry-radar'],['多因子机会','/zh/watch/resonance/rare-opportunities'],['我最喜欢形态','/zh/watch/resonance/favorite-pattern'],['回测','/zh/backtest'],['功能介绍与方法','/zh/watch/resonance/about']] as const;
export default function Page() {
 return <Localized><main className="rtPage rtFeaturedPage cockpit marketSummaryPage svApp svTerminalPage"><ArchiveGrid/><MoreDetails zh="详细数据（原来的档案列表）" en="Detailed data (the original archive list)"><p className="rtHeroDescription">{s.archiveIntro}</p><section className="cockpitCard cockpitBody"><nav className="svArchiveLinks" aria-label={s.archive}>{links.map(([label,href])=><a key={href} href={href}>{label}</a>)}</nav></section></MoreDetails></main></Localized>;
}
