'use client';
import {Localized} from '../i18n/locale';
import {Missing} from '../app/shared';
import {validTicket} from '../evidence/data';
import {useEvidence} from '../evidence/shared';
import {TicketView} from '../evidence/ticket';

// Facts on this page were checked on 2026-10-24 against the sources listed at the bottom; frozen-rule numbers come from
// research/lab/forward/triangle/config.json (3w-1.9). Update the sources and the check date together.
export const steps: [string, string][] = [
 ['第 1 步 · 形态长什么样', '周线上，价格先跌出一条向下的趋势线，线上有三次反弹高点（三推）；下面至少两次跌到差不多的位置（平底）；然后 MACD 在 0 轴下方金叉。三样都满足，才算一个 3W 信号。'],
 ['第 2 步 · 什么时候买', '信号那周收盘后，在收盘价下方 2% 挂限价买单，最多等 8 周（40 个交易日）。成交前先碰到止损或止盈位，就撤单。还要过两道关：大盘（SPY 在 200 日均线上方，并且一半以上的股票在自己的 200 日均线上方）和月线 MACD 不否决；离最近前高不到 1.5R 的也不做。'],
 ['第 3 步 · 止损止盈放哪', '止损放在最后一个底部下方 1%，而且离买价至少 0.5 个周 ATR。买价减止损就是 1R，也就是每股冒的风险。止盈定在 3R；最多拿 26 周，到期按收盘价卖出。'],
 ['第 4 步 · 亏的多，为什么还做', '历史回测里 3W 的胜率约 40%：亏的单子大约亏 1R，赚的单子目标是 3R。所以重点不是每笔都赢，而是每笔风险固定、严格止损。仓位按账户的 2% 风险计算，单只不超过 20%，所有持仓加起来的风险不超过 10%。'],
];

export const glossary: [string, string][] = [
 ['R', '每股冒的风险，等于买价减止损。赚 3R 就是赚到 3 倍于风险的钱。'],
 ['净 R', '扣掉每边 0.1% 交易成本之后的 R。'],
 ['ATR', '平均真实波幅：一根 K 线通常会波动多大。'],
 ['200 日均线', '过去 200 个交易日收盘价的平均值，用来看长期趋势。'],
 ['市场宽度', '股票池里站在自己 200 日均线上方的股票所占的比例。'],
 ['MACD 金叉', 'MACD 快线从下往上穿过慢线；3W 要求它发生在 0 轴下方。'],
 ['限价单', '只在你定的价格或更好的价格成交的买单。'],
 ['止损', '价格跌到这里就卖出，把一笔的亏损限制在 1R 左右。'],
 ['冻结规则（3w-1.9）', '规则定死以后不再改，所有结果都按同一套规则记录。'],
 ['前向记录', '规则定死之后才出现的真实信号，用来检验规则是否真的有效。'],
 ['随机孪生', '同一天随机挑的股票，用完全相同的买卖规则做对照。'],
 ['SHY', '1–3 年期美国国债 ETF；行业篮子跌到 200 日均线下方时换成它。'],
];

export const costs: [string, string, string][] = [
 ['美股佣金', '每单 US$0.99 起', 'moomoo 价格页（截至 2025 年 12 月）；另有代收的转手费用，官网例子里 100 股合计约 US$1.29'],
 ['澳元换美元', '有点差', '第三方资料说 AUD/USD 约加 50–55 点；以 moomoo 金融服务指南（FSG）为准'],
 ['账户费、不活跃费', '$0', 'moomoo 价格页'],
 ['回测里用的成本', '每边 0.1%', '比实际佣金保守：一单 US$5,000 时，0.1% 是 US$5'],
];

export const taxes: string[] = [
 '澳洲税务居民卖出美股赚的钱算资本利得，要报税；资本亏损可以抵扣资本利得。',
 '持有满 12 个月（不算买入日和卖出日）才能把资本利得打五折（减 50%）。3W 最多持有 26 周，所以 3W 的盈利一般拿不到这个折扣，全额计入当年。',
 '美股股息：在 moomoo 填好 W-8BEN，按澳美税收协定美国预扣税一般是 15%，不填可能按 30% 扣；已被预扣的税一般可以在澳洲申请外国所得税抵免。',
 'ATO 说明：2026–27 联邦预算宣布了 CGT 改动，但不适用于 2026 报税季；以后以 ATO 最新说明为准。',
 '交易很频繁时，ATO 可能把你当作经营交易业务而不是投资者，计税方式不同。拿不准请咨询注册税务师。',
];

export const sources: [string, string][] = [
 ['moomoo AU 价格页', 'https://www.moomoo.com/au/pricing'],
 ['ATO：CGT 折扣', 'https://www.ato.gov.au/individuals-and-families/investments-and-assets/capital-gains-tax/cgt-discount'],
 ['IRS：澳美税收协定', 'https://www.irs.gov/pub/irs-trty/aus.pdf'],
 ['IRS：W-8BEN 填写说明', 'https://www.irs.gov/pub/irs-pdf/iw8ben.pdf'],
 ['Wise：moomoo 澳洲评测（换汇点差）', 'https://wise.com/au/blog/moomoo-review'],
 ['QuantRoutine：moomoo 澳洲费用（引用 FSG）', 'https://quantroutine.com/brokers/moomoo/'],
];

export function LearnView() {
 return <Localized><>
  <section className="researchReplay svLearn" aria-labelledby="learn-steps"><h2 id="learn-steps">四步看懂 3W</h2>
   <ol className="svLearnSteps">{steps.map(([title, body]) => <li key={title} className="cockpitCard"><h3>{title}</h3><p>{body}</p></li>)}</ol>
  </section>
  <section className="researchReplay svLearn" aria-labelledby="learn-example"><h2 id="learn-example">一个真实的历史例子</h2>
   <p>Agilent（A）在 2012-09-14 那周出了信号：限价 $24.68，止损 $22.94（1R = $1.74），止盈 $29.91（3R）。2012-09-20 成交，2012-10-19 跌到止损，亏了 1R。这是一笔亏损的单子，3W 本来就会有很多这样的单子。</p>
   <LearnExample/>
  </section>
  <section className="researchReplay svLearn" aria-labelledby="learn-glossary"><h2 id="learn-glossary">术语表</h2>
   <dl className="svLearnGlossary">{glossary.map(([term, meaning]) => <div key={term}><dt>{term}</dt><dd>{meaning}</dd></div>)}</dl>
  </section>
  <section className="researchReplay svLearn" aria-labelledby="learn-costs"><h2 id="learn-costs">在澳洲用 moomoo：成本与税</h2>
   <p className="svAppWarning">仅供研究和学习，不是投资或税务建议。费用和税务规定会变，下单和报税前请以官方最新说明为准。</p>
   {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll the wide table region. */}
   <div className="svLearnTable" role="region" aria-label="成本" tabIndex={0}><table><thead><tr><th scope="col">项目</th><th scope="col">金额</th><th scope="col">说明</th></tr></thead>
    <tbody>{costs.map(([item, amount, note]) => <tr key={item}><th scope="row">{item}</th><td>{amount}</td><td>{note}</td></tr>)}</tbody></table></div>
   <h3>税</h3>
   <ul className="svLearnTax">{taxes.map(line => <li key={line}>{line}</li>)}</ul>
   <h3>来源</h3>
   <ul className="svLearnSources">{sources.map(([label, href]) => <li key={href}><a href={href} target="_blank" rel="noopener noreferrer">{label}</a></li>)}</ul>
   <p className="svAppSource">资料核对日期：2026-10-24</p>
  </section>
 </></Localized>;
}

function LearnExample() {
 const state = useEvidence('/app/ticket-example.json', validTicket);
 return state.loading ? <Missing loading/> : state.data ? <TicketView ticket={state.data}/> : <Missing/>;
}

export default function LearnPage() {
 return <Localized><main className="rtPage rtFeaturedPage cockpit marketSummaryPage svApp svEvidence"><header className="rtSubHero"><div><p>SAGE VISTA</p><h1>学习</h1><p>用 5 分钟看懂 3W：形态、买点、止损止盈，以及在澳洲用 moomoo 交易的成本和税。</p></div></header><LearnView/></main></Localized>;
}
