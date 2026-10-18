'use client';
import {Localized} from '../i18n/locale';
import type {Check,Ticket} from './data';
import {EvidenceChart} from './chart';
import {OutcomeStepper} from './stepper';
import {num,Status} from './shared';
const labels:Record<string,string>={weekly_history:'周线历史足够',bullish_week:'信号周收阳',cooldown:'距上次形态至少13周',golden_cross:'金叉前至少4周在DEA下方',push_line:'三推下降线',bottoms:'底部结构',bottom_before_signal:'最后底部早于信号',near_bottom:'靠近最后底部',converging:'上下边界收敛',pullback_pct:'回撤10%—60%',flat_bottom_pct:'最后底部不高于最低底10%',bottom_count:'至少两个底部',not_three_year_low:'未显著跌破前三年低点',shape_stop_atr:'形态止损距离足够',target_at_least_7pct:'最近目标至少高7%',shape_reward_to_risk:'形态盈亏比或调整条件',shape_helper:'完整形态核对',dif_under_zero:'DIF在零轴下',signal_window:'信号在记录窗口内',tradable_pool:'价格、历史与成交额门槛',plan_stop:'限价及止损计划',plan_geometry:'止损、限价、目标顺序有效',monthly_macd_veto:'月线MACD不否决',plan_reward_to_risk:'计划盈亏比至少1.5',spy_over_200d:'SPY高于200日均线',breadth_over_half:'超过一半股票高于200日线'};
export function checkValue(c:Check) {
 if(typeof c.value==='number')return num(c.value,4);
 const v=(c.value&&typeof c.value==='object'?c.value:{}) as Record<string,unknown>;
 const list=(key:string)=>(Array.isArray(v[key])?v[key] as unknown[]:[]);
 switch(c.id){
  case 'weekly_history':return `${v.completed_bars} ≥ ${v.minimum}`;
  case 'bullish_week':return `${num(v.close)} > ${num(v.open)}`;
  case 'cooldown':return `${v.weeks} ≥ ${v.minimum}`;
  case 'golden_cross':return list('histogram').map(n=>num(n,3)).join(' → ');
  case 'push_line':return `${list('drop_ratios').map(n=>num(n,3)).join(' / ')} · ${v.span} wk`;
  case 'bottoms':return list('prices').map(n=>num(n)).join(' / ');
  case 'bottom_before_signal':return `${v.last_bottom} < ${v.signal}`;
  case 'near_bottom':return `${num(v.low)} ≤ ${num(Number(v.last_bottom)+1.5*Number(v.shape_atr))}`;
  case 'converging':return list('anchors').map(p=>Array.isArray(p)?num(p[1]):'—').join(' → ');
  case 'pullback_pct':case 'flat_bottom_pct':case 'target_at_least_7pct':return `${num(v.pct)}%`;
  case 'bottom_count':return `${v.count} ≥ ${v.minimum}`;
  case 'not_three_year_low':return `${num(v.bottom)} ≥ ${num(v.floor)}`;
  case 'shape_stop_atr':return `${num(v.distance)} ≥ ${num(Number(v.atr)*Number(v.minimum_multiple))}`;
  case 'shape_reward_to_risk':case 'plan_reward_to_risk':return `${num(v.rr)}R`;
  case 'shape_helper':return `${v.week??'—'} · ${num(v.t1)}`;
  case 'signal_window':return `${v.start} → ${v.end}`;
  case 'tradable_pool':return `$${num(v.price)} · $${num(v.dollar_volume,0)} · ${v.history_index} d`;
  case 'plan_stop':return `${num(v.limit)} / ${num(v.stop)}`;
  case 'plan_geometry':return `${num(v.stop)} < ${num(v.limit)} < ${num(v.t1)}`;
  case 'monthly_macd_veto':return `${v.completed_month??'—'} · DIF ${num(v.dif,3)} · ${list('hist').map(n=>num(n,3)).join(' / ')}`;
  case 'spy_over_200d':return `${num(v.close)} / ${num(v.sma200)}`;
  case 'breadth_over_half':return `${num(typeof v.fraction==='number'?v.fraction*100:null,1)}% · n=${v.sample_size??'—'}`;
  default:return '—';
 }
}
export function KeyChecks({checks}:{checks:Check[]}) {
 const groups=[['三推下降线',['push_line']],['底部平',['flat_bottom_pct','bottom_count']],['金叉在零轴下',['golden_cross','dif_under_zero']],['盈亏比',['plan_reward_to_risk']],['大盘',['spy_over_200d','breadth_over_half']]] as const;
 return <Localized><section className="svKeyChecks"><h3>为什么触发</h3><ul className="svEvidenceChecks">{groups.map(([label,ids])=>{
  const found=ids.map(id=>checks.find(c=>c.id===id));const pass=found.every(c=>c?.pass);
  return <li key={label}><span className={pass?'isPass':'isFail'} aria-label={pass?'通过':'未通过'}>{pass?'✓':'×'}</span><span>{label}</span><span className="svCheckValue">{found.map(c=>c?checkValue(c):'—').join(' · ')}</span></li>;
 })}</ul></section></Localized>;
}
export function TicketView({ticket,chart=true}:{ticket:Ticket;chart?:boolean}) {
 const t=ticket,o=t.outcome;
 return <Localized><article className="cockpitCard svTicket" aria-label="信号凭证详情"><header className="svTicketHead"><h2>{t.symbol} · <span>信号凭证</span></h2>{t.example&&<span className="svEvidenceChip isWarning">历史示例 · 冻结规则重算</span>}<Status status={o.status}/><span className="svAppMeta">{t.signal_week} · {t.version}</span></header>
 {t.example&&<p className="svAppWarning">历史示例，不计入真实前向信号。</p>}
 {chart&&<EvidenceChart ticket={t}/>}
 <KeyChecks checks={t.checks}/>
 <div className="svTicketColumns"><section><h3>订单计划</h3><dl className="svOrder"><div><dt>限价</dt><dd>{num(t.order.limit)}</dd></div><div><dt>止损</dt><dd>{num(t.order.stop)}</dd></div><div><dt>目标 3R</dt><dd>{num(t.order.target)}</dd></div><div><dt>每股风险</dt><dd>{num(t.order.R)}</dd></div><div><dt>挂单到期</dt><dd>{t.order.valid_until}</dd></div><div><dt>最长持有</dt><dd>{t.order.max_hold_sessions} <span>交易日</span></dd></div></dl><p className="svAppSource">{t.order.eligible?'挂单到期为估计日期。':'不满足挂单条件。'}</p></section>
 <section><h3>后来怎么样</h3><OutcomeStepper status={o.status} signalDate={t.signal_day} fillDate={o.fill_date} exitDate={o.exit_date} exitPrice={o.exit} R={o.R} outcome={o.source_status}/></section></div>
 <details className="svAllChecks"><summary>{`全部 ${t.checks.length} 条`}</summary><ul className="svEvidenceChecks">{t.checks.map(c=><li key={c.id}><span className={c.pass?'isPass':'isFail'} aria-label={c.pass?'通过':'未通过'}>{c.pass?'✓':'×'}</span><span>{labels[c.id]??c.id}</span><span className="svCheckValue">{checkValue(c)}</span></li>)}</ul>
 <div className="svAnchors"><p><strong>三推</strong> {t.pushes.map((p,i)=><span key={p.date}>{i+1}: {p.date} · {num(p.price)} </span>)}</p><p><strong>底部</strong> {t.bottoms.map((p,i)=><span key={p.date}>{i+1}: {p.date} · {num(p.price)} </span>)}</p></div></details></article></Localized>;
}
