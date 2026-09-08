import CandidateRanking from "./cr056-ranking";
import {TrackerShell} from "../tracker-ui";

export default function RareOpportunities(){
 return <TrackerShell active="多因子机会" title="候选榜" subtitle="新提名与持续观察 · 每日更新，同一套评分"><CandidateRanking/></TrackerShell>;
}
