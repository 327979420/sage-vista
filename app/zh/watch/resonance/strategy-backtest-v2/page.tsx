import {TrackerShell} from "../tracker-ui";
import Comparison from "./comparison";

export default function Page(){return <TrackerShell active="多因子机会" title="逐笔成交对账" subtitle="复用真实旧成交，分别核对缓存重放与VectorBT记账；不改变生产策略。"><Comparison/></TrackerShell>}
