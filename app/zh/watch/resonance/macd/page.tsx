"use client";
import {useState} from "react";
import {SignalBoard,TrackerShell,useTracker} from "../tracker-ui";

export default function Macd(){
 const data=useTracker();
 const [side,setSide]=useState<"buy"|"sell">("buy");
 const [structureOnly,setStructureOnly]=useState(false);
 const source=data?(side==="buy"?data.macd_buy_top10:data.macd_sell_top10):[];
 const items=structureOnly?source.filter(x=>x.price_structure.confirmed):source;
 return <TrackerShell active="指标共振" title="MACD 多周期排行榜" subtitle="看涨与看跌完全分榜；每一只都必须先通过对应的MACD规则。">
  {data&&<section className="rtSignals">
   <div className="rtSectionTitle"><div><p>{side==="buy"?"MACD 看涨 TOP 10":"MACD 看跌 TOP 10"}</p><h2>{side==="buy"?"零轴下金叉与小周期传导优先":"零轴上死叉与大周期转弱优先"}</h2></div><div className="rtDirectionTabs"><button className={side==="buy"?"active":""} onClick={()=>setSide("buy")}>看涨 MACD</button><button className={side==="sell"?"active":""} onClick={()=>setSide("sell")}>看跌 MACD</button></div></div>
   <p className="rtRankNote">{side==="buy"?"只有MACD看涨规则成立的股票才能进入本榜；零轴下新金叉权重最高，月线空头柱收缩可作为大周期正在改善的证据。":"只有零轴上形成且当前仍有效的死叉才有较高看跌权重；零轴下死叉不会被包装成强看跌。"}</p>
   <label className="rtStructureToggle"><input type="checkbox" checked={structureOnly} onChange={e=>setStructureOnly(e.target.checked)}/><span>只看价格结构确认</span></label>
   <SignalBoard items={items} kind="macd" combined={new Set(data.combined_top10.map(x=>x.symbol))}/>
   {items.length===0&&<p className="rtEmpty">当前没有通过这组MACD规则的候选。</p>}
  </section>}
 </TrackerShell>
}
