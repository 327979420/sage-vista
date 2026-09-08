import {TrackerShell} from "../tracker-ui";
import Comparison from "./comparison";
import ResearchRuns from "./research-runs";

export default function Page(){return <TrackerShell active="多因子机会" title="策略回测与历史结果" subtitle="选择已有策略和日期，查看收益、回撤与交易明细；研究结论不自动激活生产规则。"><ResearchRuns/><details className="svPanel"><summary>早期20笔成交工程对账</summary><Comparison/></details></TrackerShell>}
