// Display-only explanations of saved observations. Never used by trading logic.
export type Row={date:string;value:number;customer?:number;firm?:number;market_maker?:number;total?:number};
export type PositionRow={date:string;leveraged:number;asset:number;leveraged_net:number;asset_net:number};
export type Contract={code:string;label:string;history:PositionRow[];percentiles:{leveraged:number|null;asset:number|null};percentile_weeks:number};
export type Fund={ticker:string;label:string;history:Row[];returns:Record<string,number>};
export type Panel={id:string;frequency:string;status:string;observation_date:string|null;value?:number;history?:Row[];change_pct?:number|null;change_yoy_pct?:number|null;sum_4w?:number|null;contracts?:Contract[];funds?:Fund[];sources?:{provider:string;url:string;fetched_at:string;sha256:string}[]};
export type CockpitReport={schema_version:string;as_of:string;checked_at:string;panels:Record<string,Panel>};
export type Indicator={value:number|null;reliable:boolean;valid_count?:number};
export type Snapshot={date:string;quality:{status:string;universe_size:number;valid_ticker_count:number};counts:{advances:number;declines:number;unchanged:number;new_highs:number;new_lows:number};indicators:Record<string,Indicator>};
export type SampleReport={as_of:string;history:Snapshot[]};
export type Direction={label:string;arrow:string;detail:string};
export type Reading={level:string;tone:'positive'|'negative'|'caution'|'neutral';explanation:string;evidence:{label:string;value:string}[];direction:Direction;basis:string;available:boolean};
export const finite=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v);
export const num=(v:number|null|undefined,d=1)=>finite(v)?v.toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
export const signed=(v:number|null|undefined,d=1)=>finite(v)?`${v>0?'+':''}${num(v,d)}`:'—';
export const percent=(v:number|null|undefined)=>finite(v)?`${signed(v)}%`:'—';
const pending=(detail='历史不足，暂不比较'):Direction=>({label:'待比较',arrow:'—',detail});
export const unavailable=(explanation='暂无同日可验证数据',level='等待数据'):Reading=>({level,tone:'neutral',explanation,evidence:[],direction:pending(),basis:'缺失不填零，不作状态判断。',available:false});
const direction=(v:number|null,label:string,unit:string,neutral=false):Direction=>!finite(v)?pending():({label:Math.abs(v)<1e-8?(neutral?'持平':'稳定'):v>0?(neutral?'上升':'改善'):(neutral?'下降':'恶化'),arrow:Math.abs(v)<1e-8?'→':v>0?'↑':'↓',detail:`${label} ${signed(v)}${unit}`});
export function complete(s:Snapshot|undefined|null):boolean{return !!s&&s.quality.status==='complete'&&s.quality.universe_size>0&&s.quality.valid_ticker_count===s.quality.universe_size&&s.counts.advances+s.counts.declines+s.counts.unchanged===s.quality.valid_ticker_count}
export function participation(s:Snapshot|undefined|null,previous?:Snapshot):Reading{
 if(!s||!complete(s))return unavailable(s?`覆盖不足：有效 ${num(s.quality.valid_ticker_count,0)} / ${num(s.quality.universe_size,0)} 只，暂不判断强弱。`:'等待完整固定样本','覆盖待核对');
 const up=s.counts.advances/s.quality.valid_ticker_count*100,down=s.counts.declines/s.quality.valid_ticker_count*100;
 const delta=previous&&complete(previous)&&previous.quality.universe_size===s.quality.universe_size?up-previous.counts.advances/previous.quality.valid_ticker_count*100:null;
 return {available:true,level:up<down?'偏弱':up>down?'偏强':'均衡',tone:up<down?'negative':up>down?'positive':'neutral',explanation:up<down?'下跌股票多于上涨股票。':up>down?'上涨股票多于下跌股票。':'上涨与下跌家数相同。',evidence:[{label:`上涨 · ${num(s.counts.advances,0)}只`,value:`${num(up)}%`},{label:`下跌 · ${num(s.counts.declines,0)}只`,value:`${num(down)}%`}],direction:direction(delta,'上涨占比较5个交易日前','个百分点'),basis:'当前状态比较上涨、下跌家数；方向比较上涨占比与5个交易日前。两端均须完整覆盖同一固定样本。比例分母含平盘。'};
}
export function breakouts(s:Snapshot|undefined|null,previous?:Snapshot):Reading{
 const metric=s?.indicators.new_high_low;
 if(!s||!complete(s)||!metric?.reliable||!metric.valid_count)return unavailable('覆盖不足或52周历史不完整，暂不判断突破强弱。','覆盖待核对');
 const {new_highs:h,new_lows:l}=s.counts;const prior=previous?.indicators.new_high_low;
 const delta=previous&&complete(previous)&&prior?.reliable&&prior.valid_count===metric.valid_count?((h-l)-(previous.counts.new_highs-previous.counts.new_lows))/metric.valid_count*100:null;
 const explanation=h===0&&l===0?'今天没有股票触及52周新高或新低。':h===0?`新低 ${l} 只，没有新高。`:l===0?`新高 ${h} 只，没有新低。`:l>h?`新低数量约为新高的 ${num(l/h)} 倍。`:h>l?`新高数量约为新低的 ${num(h/l)} 倍。`:'新高与新低家数相同。';
 return {available:true,level:l>h?'偏弱':h>l?'偏强':'均衡',tone:l>h?'caution':h>l?'positive':'neutral',explanation,evidence:[{label:'52周新高',value:`${h}只`},{label:'52周新低',value:`${l}只`}],direction:finite(delta)?direction(delta,'净新高占比较5个交易日前','个百分点'):pending(prior?.valid_count&&prior.valid_count!==metric.valid_count?'前后可比样本数不同，暂不比较':'历史覆盖不足，暂不比较'),basis:`52周可比样本 ${num(metric.valid_count,0)} 只。净新高占比=(新高−新低)/可比家数。两端分母一致才比较；新高/新低两组并非互斥。`};
}
export function relativeReturn(f:Fund|undefined,benchmark:Fund|undefined,n:number):number|null{
 const a=f?.returns[String(n)],b=benchmark?.returns[String(n)];return finite(a)&&finite(b)&&a>-100&&b>-100?((1+a/100)/(1+b/100)-1)*100:null;
}
export function leadership(funds:Fund[]):Reading{
 const spy=funds.find(f=>f.ticker==='SPY'),rsp=funds.find(f=>f.ticker==='RSP'),iwm=funds.find(f=>f.ticker==='IWM');
 const a=relativeReturn(rsp,spy,20),b=relativeReturn(iwm,spy,20),shortA=relativeReturn(rsp,spy,5),shortB=relativeReturn(iwm,spy,5);
 if(!finite(a)||!finite(b))return unavailable();
 const lag=a<0&&b<0,lead=a>0&&b>0,flat=a===0&&b===0,rising=finite(spy?.returns['20'])&&spy.returns['20']>0;
 const change=!finite(shortA)||!finite(shortB)?pending():{label:shortA>0&&shortB>0?'改善':shortA<0&&shortB<0?'恶化':shortA===0&&shortB===0?'稳定':'分化',arrow:shortA>0&&shortB>0?'↑':shortA<0&&shortB<0?'↓':'↔',detail:`近5日：等权 ${percent(shortA)} · 小盘 ${percent(shortB)}（相对标普）`};
 return {available:true,level:lag?(rising?'上涨较集中':'等权、小盘更弱'):lead?'等权、小盘更强':flat?'表现接近':'表现分化',tone:lag?'caution':lead?'positive':'neutral',explanation:lag?'近20日，等权与小盘都落后于标普。':lead?'近20日，等权与小盘都跑赢标普。':flat?'近20日，等权和小盘与标普表现相同。':'近20日，等权与小盘的相对表现不同。',evidence:[{label:'等权相对标普 · 20日',value:percent(a)},{label:'小盘相对标普 · 20日',value:percent(b)}],direction:change,basis:'相对收益=(1+ETF收益)/(1+SPY收益)−1。当前水平用20日，变化用5日。只有标普上涨时才把两者落后描述为上涨集中；不是资金流统计。'};
}
export function sectorReading(funds:Fund[]):Reading{
 const sectors=funds.filter(f=>!['SPY','RSP','IWM'].includes(f.ticker)),spy=funds.find(f=>f.ticker==='SPY');
 if(sectors.length!==11||!finite(spy?.returns['5'])||sectors.some(f=>!finite(f.returns['5'])))return unavailable();
 const up=sectors.filter(f=>f.returns['5']>0).length,beat=sectors.filter(f=>f.returns['5']>spy!.returns['5']).length;
 const previous=sectors.map(f=>{const rows=f.history;const end=rows.at(-6),start=rows.at(-11);return end&&start&&start.value>0?end.value/start.value-1:null});
 const before=previous.every(finite)?previous.filter(v=>v!>0).length:null;
 return {available:true,level:up>5?'范围较广':'范围较窄',tone:up>5?'positive':'negative',explanation:up>5?'多数基本行业近5日上涨。':'多数基本行业近5日没有上涨。',evidence:[{label:'近5日上涨',value:`${up} / 11`},{label:'近5日跑赢标普',value:`${beat} / 11`}],direction:direction(before===null?null:up-before,'5日上涨行业数较上一个5日窗口','个'),basis:'范围按11行业中近5日上涨是否超过一半判断。方向比较两个相邻5日窗口上涨行业数，不把行业ETF表现当作行业内个股广度。'};
}
export function positionReading(contract:Contract|undefined|null):Reading{
 const last=contract?.history.at(-1),prior=contract?.history.at(-2);if(!last)return unavailable();
 const days=prior?(Date.parse(last.date)-Date.parse(prior.date))/86400000:0;
 const delta=prior&&days>=6&&days<=8?last.leveraged-prior.leveraged:null;
 const short=last.leveraged<0;return {available:true,level:short?'杠杆基金净空':last.leveraged>0?'杠杆基金净多':'杠杆基金净仓为零',tone:short?'caution':'neutral',explanation:short?(finite(delta)&&delta>0?'仍为净空，但本周净空敞口收窄。':finite(delta)&&delta<0?'仍为净空，本周净空敞口扩大。':'当前仍为净空，需结合持仓用途理解。'):(finite(delta)&&delta>0?'本周净敞口向多头方向增加。':finite(delta)&&delta<0?'本周净敞口向空头方向移动。':'多空净敞口基本持平。'),evidence:[{label:'杠杆基金净仓 / 未平仓',value:percent(last.leveraged)},{label:'较上周',value:finite(delta)?`${signed(delta)}个百分点`:'待比较'}],direction:direction(delta,'周度净仓占比变化','个百分点'),basis:'净仓=多头−空头；再除以未平仓总量。改善/恶化只描述净敞口方向，不能代表机构全部仓位或预测行情。净空收窄可能来自加多或减空。'};
}
export function marginReading(panel:Panel|undefined|null):Reading{
 if(!finite(panel?.value))return unavailable();const change=panel.change_pct;
 return {available:true,level:!finite(change)?'融资余额已更新':change>0?'融资使用上升':change<0?'融资使用下降':'融资使用持平',tone:'neutral',explanation:!finite(change)?'缺少连续月度记录，暂不判断变化。':change>0?'客户借钱持有证券的规模增加。':change<0?'客户借钱持有证券的规模减少。':'客户融资余额与上月相同。',evidence:[{label:'客户融资余额',value:`$${num(panel.value/1000,3)}T`},{label:'较上月 / 较去年同月',value:`${percent(change)} / ${percent(panel.change_yoy_pct)}`}],direction:direction(change??null,'较上月','%',true),basis:'FINRA customer margin accounts，包含个人及机构客户，不代表纯散户。月度数据有发布滞后；增加或减少都不直接等于利好/利空。T为万亿美元。'};
}
