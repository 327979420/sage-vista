'use client';
import {useState} from 'react';
import {Localized} from '../i18n/locale';
import {Missing} from '../app/shared';
import {orderedTickets,validIndex,validTicket,type TicketIndex} from '../evidence/data';
import {EvidenceHeader,Status,useEvidence} from '../evidence/shared';
import {TicketView} from '../evidence/ticket';
export function TicketList({rows,selected,onSelect}:{rows:TicketIndex;selected:string|null;onSelect:(id:string)=>void}) {
 const sorted=orderedTickets(rows);
 return <Localized><section className="cockpitCard svTicketList" aria-label="全部信号"><h2>信号列表 · 最新一周在前</h2><div>{sorted.map(r=><button key={r.id} type="button" aria-pressed={r.id===selected} onClick={()=>onSelect(r.id)}><strong>{r.symbol}</strong><time>{r.signal_week}</time><Status status={r.status}/></button>)}</div></section></Localized>;
}
export default function SignalsPage() {
 const index=useEvidence('/app/tickets/index.json',validIndex);const [selected,setSelected]=useState<string|null>(null);
 const rows=index.data,first=rows?orderedTickets(rows)[0]?.id:null;
 const id=rows?.some(r=>r.id===selected)?selected:first;
 const empty=rows?.length===0;
 const url=rows?(empty?'/app/ticket-example.json':id?`/app/tickets/${encodeURIComponent(id)}.json`:null):null;
 const detail=useEvidence(url,validTicket);
 const validDetail=detail.data&&(empty?detail.data.example:!detail.data.example&&detail.data.id===id);
 return <Localized><main className="rtPage rtFeaturedPage cockpit marketSummaryPage svApp svEvidence"><EvidenceHeader/>
 {index.loading?<Missing loading/>:!rows?<Missing/>:<>{empty?<div className="cockpitEmpty" role="status"><strong>目前没有真实前向信号</strong><p>每周五收盘后检查。下面展示一张历史示例，帮助理解凭证。</p></div>:<TicketList rows={rows} selected={id??null} onSelect={setSelected}/>}
 {detail.loading?<Missing loading/>:validDetail&&detail.data?<TicketView ticket={detail.data}/>:<Missing/>}</>}</main></Localized>;
}
