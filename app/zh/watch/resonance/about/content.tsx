"use client";
import {useLocale} from "../../../../i18n/locale";

// About SV as short cards that mirror the footer groups. English and Chinese are
// written side by side; every claim mirrors docs/rules/04_SCORING.md and
// 07_RANKING_AND_TRACKING.md. Section ids are the footer link targets.
type Method={id:string;tag:string;title:string;body:string};
type Copy={
 nav:{about:string;method:string;what:string;how:string;disclaimer:string};
 what:{title:string;lead:string;note:string;stats:[string,string][];main:string;support:string;tools:[string,string,boolean][]};
 how:{title:string;sub:string;steps:[string,string,string][];note:string};
 methodTitle:string;methods:Method[];
 visuals:{screens:[string,string][];setups:string[];weights:string[];context:string[];timeline:[string,string][]};
 disclaimer:string;
};

const en:Copy={
 nav:{about:"About SV",method:"Method",what:"What is SV",how:"How to use SV",disclaimer:"Disclaimer"},
 what:{title:"What is SV",
  lead:"SV is the trading system I built and use myself. After every US close it reviews about 1,500 US stocks and shortlists the few in a long-term uptrend that are pulling back to a clear setup.",
  note:"It shows you where to look and why. It doesn't place trades; every decision stays yours.",
  stats:[["~1,500","stocks reviewed every trading day"],["3","timeframes: monthly, weekly, daily"],["26","sector themes tracked"]],
  main:"Main tools",support:"Support",
  tools:[["Multi-Factor Opportunities","/",true],["Daily Setups","/zh/watch/resonance/favorite-pattern",true],["Market","/zh/watch/market",false],["Sectors","/zh/watch/industry-radar",false]]},
 how:{title:"How to use SV",sub:"My daily routine, top down, in about ten minutes.",
  steps:[["📊","Market","Is the market strong? Check participation and leadership."],["🧭","Sectors","Which themes are leading or turning up?"],["⚡","Daily Setups","Any obvious setup among today's most-traded stocks?"],["🎯","Multi-Factor","Review the main list, and search any name, like BJ, for details."]],
  note:"New here? Daily Setups and Multi-Factor work on their own; Market and Sectors add context when you're ready."},
 methodTitle:"Method",
 methods:[
  {id:"opportunity",tag:"Alexander Elder",title:"Triple Screen trading system",body:"The long-term trend sets the direction, a pullback creates the opportunity, and a short-term signal times the entry. SV runs the three screens on monthly, weekly and daily charts."},
  {id:"setup",tag:"Entry",title:"Trend-pullback setups",body:"A new name needs one of three setups plus a fresh daily MACD cross. A quick dip below support that is reclaimed (a spring, or liquidity sweep) still counts."},
  {id:"confluence",tag:"Scoring",title:"Multi-timeframe confluence score",body:"26 factors per timeframe: support levels, reversal candles, momentum (Appel's MACD, Wilder's RSI) and volume, with similar signals capped. Timeframes are weighted 3:2:1, so bigger charts count most."},
  {id:"re-scoring",tag:"Context",title:"Sector rotation and daily re-scoring",body:"Each stock links to one of 26 themes and its ETF's relative strength. The list is re-scored after every US close, and past nominations are never rewritten."},
  {id:"checked",tag:"Research",title:"Point-in-time and out-of-sample testing",body:"Only completed bars are used, so there is no look-ahead. A score ranks what to review first; it isn't a win rate."},
 ],
 visuals:{screens:[["Monthly","Trend allows it"],["Weekly","Trend agrees"],["Daily","Entry signal"]],setups:["Double-bottom MACD cross","Three-push breakout","Support reversal"],weights:["Monthly 3","Weekly 2","Daily 1"],context:["26 themes","Relative strength","Re-scored daily"],timeline:[["2000–2024","Build"],["2025","Validate"],["2026","Live"]]},
 disclaimer:"A research tool, not investment advice. Stocks come from SV's own pool of about 1,500 US stocks, not the whole market.",
};

const zh:Copy={
 nav:{about:"关于 SV",method:"方法",what:"SV 是什么",how:"如何使用 SV",disclaimer:"免责声明"},
 what:{title:"SV 是什么",
  lead:"SV 是我自己搭建、并在实际交易中使用的交易系统。每个美股交易日收盘后，它复评约 1,500 只美股，只留下长期上升趋势中、正回调到清晰形态的少数股票。",
  note:"它告诉你该看哪里、为什么看；它不会替你下单，每个决定都由你来做。",
  stats:[["约 1,500","只股票，每个交易日复评"],["3","个周期：月线、周线、日线"],["26","个行业主题"]],
  main:"主要功能",support:"辅助参考",
  tools:[["多因子机会","/",true],["我最喜欢形态","/zh/watch/resonance/favorite-pattern",true],["大盘","/zh/watch/market",false],["行业","/zh/watch/industry-radar",false]]},
 how:{title:"如何使用 SV",sub:"我的每日流程：自上而下，大约十分钟。",
  steps:[["📊","大盘","大盘强不强？看参与度和领涨力量。"],["🧭","行业","哪些主题在领涨或开始回升？"],["⚡","我最喜欢形态","当天最热门的股票里有没有明显形态？"],["🎯","多因子机会","复核主榜单，搜索任意代码（如 BJ）看详情。"]],
  note:"刚开始用？只看“我最喜欢形态”和“多因子机会”也可以；大盘和行业是更多背景参考。"},
 methodTitle:"方法",
 methods:[
  {id:"opportunity",tag:"亚历山大·埃尔德",title:"三重滤网交易系统",body:"长期趋势决定方向，回调创造机会，短期信号把握入场时机。SV 在月线、周线、日线上依次执行这三层滤网。"},
  {id:"setup",tag:"入场",title:"顺势回调形态",body:"新提名需要三类门票之一，并且日线出现新的 MACD 金叉。短暂跌破支撑后迅速收回（弹簧形态，或称流动性扫荡）仍然有效。"},
  {id:"confluence",tag:"评分",title:"多周期共振评分",body:"每个周期 26 个因子：支撑位、反转 K 线、动能（阿佩尔的 MACD、怀尔德的 RSI）和成交量，同类信号设上限。三个周期按 3∶2∶1 加权，大周期权重最高。"},
  {id:"re-scoring",tag:"背景",title:"板块轮动与每日复评",body:"每只股票关联 26 个主题之一及其 ETF 的相对强弱。每个美股交易日收盘后整份榜单重新评分，原提名永远不会改写。"},
  {id:"checked",tag:"研究",title:"时点数据与样本外验证",body:"只使用已完整收盘的 K 线，没有未来函数。分数决定先复核什么，不是胜率。"},
 ],
 visuals:{screens:[["月线","方向获得许可"],["周线","趋势确认"],["日线","入场信号"]],setups:["两底金叉","三推突破","支撑反转"],weights:["月线 3","周线 2","日线 1"],context:["26 个主题","相对强弱","每日复评"],timeline:[["2000—2024","开发"],["2025","验证"],["2026","实盘跟踪"]]},
 disclaimer:"研究工具，不构成投资建议。股票来自 SV 自己约 1,500 只美股的观察池，不代表整个市场。",
};

export const aboutCopy={en,zh};

// One small diagram per method card, so each idea can be read at a glance.
function Visual({id,v}:{id:string;v:Copy["visuals"]}){
 if(id==="opportunity")return <ol className="svVisScreens">{v.screens.map(([tf,label])=><li key={tf}><b>{tf}</b><span>{label}</span></li>)}</ol>;
 if(id==="setup")return <div className="svVisChips">{v.setups.map((s,i)=><span key={s} className={["isBlue","isViolet","isAmber"][i]}>{s}</span>)}</div>;
 if(id==="confluence")return <div className="svVisWeights">{v.weights.map((w,i)=><span key={w} style={{flexGrow:3-i}}>{w}</span>)}</div>;
 if(id==="re-scoring")return <div className="svVisPills">{v.context.map(c=><span key={c}>{c}</span>)}</div>;
 return <ol className="svVisTimeline">{v.timeline.map(([years,label])=><li key={years}><b>{years}</b><span>{label}</span></li>)}</ol>;
}

export default function AboutContent(){
 const {locale}=useLocale();
 const c=locale==="en"?en:zh;
 return <div className="svAboutLayout">
  <nav className="svAboutNav" aria-label={c.nav.about}>
   <b>{c.nav.about}</b><a href="#what-is-sv">{c.nav.what}</a><a href="#how-to-use">{c.nav.how}</a>
   <b>{c.nav.method}</b>{c.methods.map(m=><a key={m.id} href={`#${m.id}`}>{m.title}</a>)}
   <a className="svAboutNavLast" href="#disclaimer">{c.nav.disclaimer}</a>
  </nav>
  <div className="svAboutMain">
   <section className="svCard" id="what-is-sv">
    <small>{c.nav.about}</small><h2>{c.what.title}</h2><p className="svLead">{c.what.lead}</p><p>{c.what.note}</p>
    <div className="svStats">{c.what.stats.map(([n,l])=><div key={l}><b>{n}</b><span>{l}</span></div>)}</div>
    <div className="svTools"><span>{c.what.main}</span>{c.what.tools.filter(t=>t[2]).map(([label,href])=><a className="isMain" key={label} href={href}>{label}</a>)}<span>{c.what.support}</span>{c.what.tools.filter(t=>!t[2]).map(([label,href])=><a key={label} href={href}>{label}</a>)}</div>
   </section>
   <section className="svCard" id="how-to-use">
    <small>{c.nav.about}</small><h2>{c.how.title}</h2><p>{c.how.sub}</p>
    <ol className="svFlow">{c.how.steps.map(([icon,title,body],i)=><li key={title}><span className="svFlowNo">{i+1}</span><h3><span aria-hidden="true">{icon}</span> {title}</h3><p>{body}</p></li>)}</ol>
    <p className="svHint">{c.how.note}</p>
   </section>
   <h2 className="svGroupTitle">{c.methodTitle}</h2>
   <div className="svMethodGrid">{c.methods.map(m=><section className="svCard svMethod" id={m.id} key={m.id}>
    <small>{m.tag}</small><h3>{m.title}</h3><p>{m.body}</p><Visual id={m.id} v={c.visuals}/>
   </section>)}</div>
   <p className="svAboutNote" id="disclaimer">{c.disclaimer}</p>
  </div>
 </div>;
}
