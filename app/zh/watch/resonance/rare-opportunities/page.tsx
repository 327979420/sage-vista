import {Localized} from '../../../../i18n/locale';
import CandidateRanking from "./cr056-ranking";
import {TrackerShell} from "../tracker-ui";

export default function RareOpportunities(){
 return <Localized><TrackerShell active="多因子机会" title="多因子机会" subtitle="SV 的核心：寻找值得深入研究的中长期投资机会。" description="综合月线、周线和日线的多个指标，为股票评分和排序，帮你缩小选股范围。评分提供研究线索，是否值得买入，仍需人工判断。"><CandidateRanking/></TrackerShell></Localized>;
}
