'use client';
import {Localized} from '../i18n/locale';
import {Missing} from '../app/shared';
import {validForward,type Forward,type Judging} from '../evidence/data';
import {OutcomeStepper} from '../evidence/stepper';
import {EvidenceHeader,pct,rText,useEvidence} from '../evidence/shared';
// The record update date is the last check, distinct from the older price-data date.
export function nextFriday(date:string) {
 const day=new Date(`${date.slice(0,10)}T00:00:00Z`);
 day.setUTCDate(day.getUTCDate()+((5-day.getUTCDay()+7)%7||7));
 return day.toISOString().slice(5,10);
}
export function CumulativeChart({points,example=false}:{points:Forward['cumulative_R'];example?:boolean}) {
 if(!points.length)return <Localized><figure className="svCumulative"><div className="svCumulativeEmpty" role="img" aria-label="累计净R图表">{example?'有信号平仓后，这里画出累计净 R 曲线':'还没有已核验的平仓结果'}</div></figure></Localized>;
 const low=Math.min(0,...points.map(p=>p.R)),high=Math.max(0,...points.map(p=>p.R));
 const y=(v:number)=>170-(v-low)/(high-low||1)*140;
 const start=Date.parse(points[0].date),span=Date.parse(points[points.length-1].date)-start;
 const path=points.map((p,i)=>`${i?'L':'M'}${40+(Date.parse(p.date)-start)*540/(span||1)},${y(p.R)}`).join(' ');
 return <Localized><figure className="svCumulative"><svg viewBox="0 0 640 220" role="img" aria-label="按退出日期累计的净R，不是账户净值"><line x1="40" x2="580" y1={y(0)} y2={y(0)} stroke="currentColor" opacity=".2"/><text x="4" y={y(0)}>0R</text><path d={path} fill="none" stroke="var(--sv-positive)" strokeWidth="2"/>{points.length===1&&<circle cx="40" cy={y(points[0].R)} r="3" fill="var(--sv-positive)"/>}<text x="40" y="200">{points[0].date}</text><text x="580" y="200" textAnchor="end">{points[points.length-1].date}</text><text x="580" y="20" textAnchor="end">{rText(points[points.length-1].R)}</text></svg><figcaption>按退出日期累计已核验平仓信号的净R，等权相加，不是账户收益。</figcaption></figure></Localized>;
}
const outcomeLabels:Record<string,string>={target:'止盈',stop:'止损',time:'时间退出'};
const lifecycleLabels:Record<string,string>={waiting:'等待成交',filled:'已成交',target:'止盈',stopped:'止损',time:'时间退出',cancelled:'已撤单',expired:'已到期',skipped:'跳过',unverified:'未核验'};
export function JudgingPanel({judging:j}:{judging:Judging}) {
 const t=j.thresholds;
 return <Localized><section className="cockpitCard" style={{padding:24,marginBottom:20,overflowWrap:'anywhere'}}>
 <h2>前向判卷</h2><p className="svAppSource">主指标：每笔净R减去同日随机孪生的平均净R。</p><p role="status"><strong>{j.verdict}</strong></p>
 {j.status==='available'&&<><p><span>已结束 / 下一检查点</span> <strong style={{fontVariantNumeric:'tabular-nums'}}>{j.completed} / {j.next_checkpoint}</strong> · <span>还差</span> {j.to_go} <span>笔</span></p>
 <progress aria-label="前向检查点进度" value={j.completed??0} max={j.next_checkpoint??30} style={{width:'100%'}}/>
 <p><span>可计分</span> {j.scored} · <span>不可计分</span> {j.unscorable}</p></>}
 <p><span>警报 1</span>：<strong>{j.alarm1===null?'本次运行未生成计分':j.alarm1?'触发':'未触发'}</strong></p>
 <p><span>警报 2</span>：<span>{j.alarm2}</span></p><p><span>证明有效</span>：<span>{j.proof}</span></p>
 <p className="svAppSource"><span>检查点</span> {t.checkpoints.join(' / ')} <span>笔，之后每</span> {t.checkpoint_step} <span>笔；净R差均值小于</span> {t.alarm1_mean_lt} <span>且 t ≤</span> {t.alarm1_t_lte} <span>触发警报1。有效性需至少</span> {t.proof_min_trades} <span>笔、t ≥</span> {t.proof_t_gte} <span>且卫星 Sharpe ≥ SPY；卫星回撤大于</span> {t.satellite_drawdown_gt*100}<span>% 触发警报2。不可计分超过</span> {t.unscorable_fraction_gt*100}<span>% 暂停该检查点判断。检查点之间只记录。</span></p>
 {j.checkpoints.length>0&&<div className="svForwardTable"><table><thead><tr>{['检查点','可计分','不可计分','平均净R差','t','结论'].map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{j.checkpoints.map(c=><tr key={c.k}><td>{c.k}</td><td>{c.scored}</td><td>{c.unscorable}</td><td>{rText(c.mean_d)}</td><td>{c.t===null?'—':c.t.toFixed(2)}</td><td>{c.verdict}</td></tr>)}</tbody></table></div>}
 <p className="svAppSource">等待时间粗估：历史每年约28笔已完成候选；若真实优势为+0.07R，期望t达到2约需2,900笔。用净R波动代替配对差波动，粗估，不是保证。</p>
 <p className="svAppSource">其他市场考试：香港14笔，p=0.089；韩国29笔，p=0.172。两者均样本不足/未证明。</p>
 </section></Localized>;
}
export function ForwardView({data}:{data:Forward}) {
 const s=data.summary,f=data.expectation;
 return <Localized><><JudgingPanel judging={data.judging}/><div className="svForwardTiles">{[['真实信号',s.signals],['已平仓',s.closed],['平均每笔净R',rText(s.average_R)],['胜过随机对照比例',pct(s.beat_random_share===null?null:s.beat_random_share*100)]].map(([label,value])=><section className="cockpitCard" key={label}><span>{label}</span><strong>{value}</strong></section>)}</div>
 <p className="svAppSource"><span>实际能做到（信号认出后才挂单）</span>：{data.executable?<><span>已平仓</span> {data.executable.trades} · <span>平均每笔净R</span> {rText(data.executable.mean_R)}</>:<span>暂无</span>}</p>
 <p className="svAppSource"><span>数据日期</span> {data.as_of} · <span>结果更新</span> {data.outcomes_as_of.slice(0,10)}</p>
 {f&&<section className="cockpitCard" style={{padding:24}}><h2>与回测参考比较</h2><p><span>历史平均</span> {rText(f.average_R)} · <span>胜率</span> {pct(f.win_rate*100)} · {f.trades} <span>笔</span></p><p>{f.label}</p><p className="svAppSource">{f.note}</p><details><summary>账本来源</summary><p>{f.ledger_heading}</p></details></section>}
 {s.signals===0&&<div className="cockpitEmpty" role="status"><strong>还没有真实前向信号</strong><p><span>下次检查：周五收盘后</span>（{nextFriday(data.outcomes_as_of)}）</p></div>}
 <section className="cockpitCard svForwardCurve" style={{padding:24}}><h2>累计净R</h2><CumulativeChart points={data.cumulative_R} example={s.signals===0}/></section>
 {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll the wide table region. */}
 <section className="cockpitCard" style={{padding:24}}><h2>逐个信号记录 {s.signals===0&&<span className="svEvidenceChip">示例</span>}</h2><div className="svForwardTable" role="region" aria-label="前向记录表，可横向滚动" tabIndex={0}><table><thead><tr>{['信号','提醒ID','信号周','状态','生命周期','1周涨跌','4周涨跌','13周涨跌','退出方式','净R','随机中位净R','胜过对照'].map(h=><th key={h} scope="col">{h}</th>)}</tr></thead><tbody>{s.signals===0&&<tr className="svForwardSample"><th scope="row">示例</th>{Array.from({length:11},(_,i)=><td key={i}>—</td>)}</tr>}{data.signals.map(r=><tr key={r.id}><th scope="row"><a href="/signals">{r.symbol}</a></th><td>{r.alert_id}</td><td>{r.signal_week}</td><td><OutcomeStepper mini status={r.status} signalDate={r.signal_week} exitDate={r.exit_date} R={r.R} outcome={r.outcome}/></td><td><span>{lifecycleLabels[r.lifecycle.status]}</span><small>{r.lifecycle.date??'—'}</small></td>{(['1w','4w','13w'] as const).map(w=><td key={w}>{pct(r.moves[w]?.move_pct)}<small><span>对照中位</span> {pct(r.random.moves?.[w]?.median_pct)}{r.random.moves?.[w]&&` (n=${r.random.moves[w]?.sample})`}</small></td>)}<td>{r.outcome?outcomeLabels[r.outcome]??'—':'—'}</td><td>{rText(r.R)}<small><span>毛R</span> {rText(r.gross_R)}</small></td><td>{r.random.twins==='verified'?rText(r.random.median_R):'未核验'}<small>{r.random.closed}/{r.random.sampled}</small>{r.random.exits&&<small><span>对照退出</span>: {Object.entries(r.random.exits).map(([kind,n])=><span key={kind}>{outcomeLabels[kind]??kind} {n} </span>)}</small>}</td><td>{r.random.twins==='verified'?pct(r.random.beat_share===null?null:r.random.beat_share*100):'—'}</td></tr>)}</tbody></table></div>

 <p className="svAppSource">净R扣除每边0.1%成本，以实际成交风险计算；毛R仅供核对。涨跌从信号收盘价起算，未到期或缺价显示—。随机净R只统计已平仓对照，最多抽30只；毛R均值核对失败显示未核验。胜过对照使用净R严格大于，平手不算胜出。</p></section></></Localized>;
}
export default function ForwardPage(){const state=useEvidence('/app/forward.json',validForward);return <Localized><main className="rtPage rtFeaturedPage cockpit marketSummaryPage svApp svEvidence"><EvidenceHeader forward/>{state.loading?<Missing loading/>:state.data?<ForwardView data={state.data}/>:<Missing/>}</main></Localized>}
