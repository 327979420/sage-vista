'use client';
import {Localized} from '../i18n/locale';
import {Missing} from '../app/shared';
import {validForward,type Forward} from '../evidence/data';
import {OutcomeStepper} from '../evidence/stepper';
import {EvidenceHeader,pct,rText,useEvidence} from '../evidence/shared';
// The record update date is the last check, distinct from the older price-data date.
export function nextFriday(date:string) {
 const day=new Date(`${date.slice(0,10)}T00:00:00Z`);
 day.setUTCDate(day.getUTCDate()+((5-day.getUTCDay()+7)%7||7));
 return day.toISOString().slice(5,10);
}
export function CumulativeChart({points,example=false}:{points:Forward['cumulative_R'];example?:boolean}) {
 if(!points.length)return <Localized><figure className="svCumulative"><div className="svCumulativeEmpty" role="img" aria-label="累计R图表">{example?'有信号平仓后，这里画出累计 R 曲线':'还没有已核验的平仓结果'}</div></figure></Localized>;
 const low=Math.min(0,...points.map(p=>p.R)),high=Math.max(0,...points.map(p=>p.R));
 const y=(v:number)=>170-(v-low)/(high-low||1)*140;
 const start=Date.parse(points[0].date),span=Date.parse(points[points.length-1].date)-start;
 const path=points.map((p,i)=>`${i?'L':'M'}${40+(Date.parse(p.date)-start)*540/(span||1)},${y(p.R)}`).join(' ');
 return <Localized><figure className="svCumulative"><svg viewBox="0 0 640 220" role="img" aria-label="按退出日期累计的R，不是账户净值"><line x1="40" x2="580" y1={y(0)} y2={y(0)} stroke="currentColor" opacity=".2"/><text x="4" y={y(0)}>0R</text><path d={path} fill="none" stroke="var(--sv-positive)" strokeWidth="2"/>{points.length===1&&<circle cx="40" cy={y(points[0].R)} r="3" fill="var(--sv-positive)"/>}<text x="40" y="200">{points[0].date}</text><text x="580" y="200" textAnchor="end">{points[points.length-1].date}</text><text x="580" y="20" textAnchor="end">{rText(points[points.length-1].R)}</text></svg><figcaption>按退出日期累计已核验平仓信号的R，等权相加，不是账户收益。</figcaption></figure></Localized>;
}
const outcomeLabels:Record<string,string>={target:'止盈',stop:'止损',time:'时间退出'};
export function ForwardView({data}:{data:Forward}) {
 const s=data.summary,f=data.expectation;
 return <Localized><><div className="svForwardTiles">{[['真实信号',s.signals],['已平仓',s.closed],['平均每笔R',rText(s.average_R)],['胜过随机对照比例',pct(s.beat_random_share===null?null:s.beat_random_share*100)]].map(([label,value])=><section className="cockpitCard" key={label}><span>{label}</span><strong>{value}</strong></section>)}</div>
 <p className="svAppSource"><span>数据日期</span> {data.as_of} · <span>结果更新</span> {data.outcomes_as_of.slice(0,10)}</p>
 {f&&<section className="cockpitCard"><h2>与回测参考比较</h2><p><span>历史平均</span> {rText(f.average_R)} · <span>胜率</span> {pct(f.win_rate*100)} · {f.trades} <span>笔</span></p><p>{f.label}</p><p className="svAppSource">{f.note}</p><details><summary>账本来源</summary><p>{f.ledger_heading}</p></details></section>}
 {s.signals===0&&<div className="cockpitEmpty" role="status"><strong>还没有真实前向信号</strong><p><span>下次检查：周五收盘后</span>（{nextFriday(data.outcomes_as_of)}）</p></div>}
 <section className="cockpitCard svForwardCurve"><h2>累计R</h2><CumulativeChart points={data.cumulative_R} example={s.signals===0}/></section>
 {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll the wide table region. */}
 <section className="cockpitCard"><h2>逐个信号记录 {s.signals===0&&<span className="svEvidenceChip">示例</span>}</h2><div className="svForwardTable" role="region" aria-label="前向记录表，可横向滚动" tabIndex={0}><table><thead><tr>{['信号','信号周','状态','1周涨跌','4周涨跌','13周涨跌','退出方式','R','随机中位R','胜过对照','盲判','判得对吗'].map(h=><th key={h} scope="col">{h}</th>)}</tr></thead><tbody>{s.signals===0&&<tr className="svForwardSample"><th scope="row">示例</th>{Array.from({length:11},(_,i)=><td key={i}>—</td>)}</tr>}{data.signals.map(r=><tr key={r.id}><th scope="row"><a href="/signals">{r.symbol}</a></th><td>{r.signal_week}</td><td><OutcomeStepper mini status={r.status} signalDate={r.signal_week} exitDate={r.exit_date} R={r.R} outcome={r.outcome}/></td>{(['1w','4w','13w'] as const).map(w=><td key={w}>{pct(r.moves[w]?.move_pct)}<small><span>对照中位</span> {pct(r.random.moves?.[w]?.median_pct)}{r.random.moves?.[w]&&` (n=${r.random.moves[w]?.sample})`}</small></td>)}<td>{r.outcome?outcomeLabels[r.outcome]??'—':'—'}</td><td>{rText(r.R)}</td><td>{r.random.twins==='verified'?rText(r.random.median_R):'未核验'}<small>{r.random.closed}/{r.random.sampled}</small>{r.random.exits&&<small><span>对照退出</span>: {Object.entries(r.random.exits).map(([kind,n])=><span key={kind}>{outcomeLabels[kind]??kind} {n} </span>)}</small>}</td><td>{r.random.twins==='verified'?pct(r.random.beat_share===null?null:r.random.beat_share*100):'—'}</td><td>{r.blind.choice==='do'?'做':r.blind.choice==='no'?'不做':'未记录'}{r.blind.judged_after_fill&&<small>成交后判断</small>}</td><td>{!r.blind.choice?'未记录':r.blind.score==='right'?'对':r.blind.score==='wrong'?'不对':'尚未计分'}</td></tr>)}</tbody></table></div>
 <p className="svAppSource">计分规则：做，在已平仓R大于0时正确；不做，在已平仓R小于或等于0时正确。未成交或仍持仓的信号尚未计分。</p>
 <p className="svAppSource">涨跌从信号收盘价起算，未到观察期或缺价显示—。随机R只统计已平仓对照，最多抽30只；均值核对失败显示未核验。胜过对照使用严格大于，平手不算胜出；汇总是已核验平仓信号的比例均值。</p></section></></Localized>;
}
export default function ForwardPage(){const state=useEvidence('/app/forward.json',validForward);return <Localized><main className="rtPage rtFeaturedPage cockpit marketSummaryPage svApp svEvidence"><EvidenceHeader forward/>{state.loading?<Missing loading/>:state.data?<ForwardView data={state.data}/>:<Missing/>}</main></Localized>}
