import {Localized} from '../../i18n/locale';
import {TrackerShell} from "../watch/resonance/tracker-ui";
import Comparison from "./comparison";
import ResearchRuns from "./research-runs";

export default function Page(){return <Localized><TrackerShell active="回测" title="回测" subtitle="看看策略过去表现如何。" description="查看历史研究中的收益和亏损，了解策略的风险，以及哪些结论还需要验证。"><ResearchRuns/><details className="svPanel"><summary>早期20笔成交工程对账</summary><Comparison/></details></TrackerShell></Localized>}
