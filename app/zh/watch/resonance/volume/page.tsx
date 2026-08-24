"use client";
import {TrackerShell,useTracker} from "../tracker-ui";
export default function Volume(){const data=useTracker();return <TrackerShell active="成交量" title="成交量异动" subtitle="成交量证据单独展示，不与动能指标混在同一张表。">{data&&<section className="rtVolume"><div className="rtSectionTitle"><div><p>VOLUME ALERTS</p><h2>达到20日均量的1.8倍以上</h2></div><span>放量下跌仅作风险提示</span></div><div className="rtVolumeGrid">{data.volume_top10.map((x,i)=><article key={x.symbol} className={x.volume.direction==="下跌"?"isDown":""}><i>{String(i+1).padStart(2,"0")}</i><div><b>{x.symbol}</b><small>{x.volume.label}</small></div><strong>{x.volume.ratio??"—"}×</strong><span>{x.volume.near_bottom?"底部区域":"非底部"} · {x.volume.direction}</span></article>)}</div></section>}</TrackerShell>}

