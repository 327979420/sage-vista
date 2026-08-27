import {ReactNode} from "react";
export function StatusBadge({state,children}:{state:string;children:ReactNode}){return <mark className="svStatus" data-state={state}>{children}</mark>}
export function SectionHeader({eyebrow,title,description,action}:{eyebrow:string;title:string;description?:string;action?:ReactNode}){return <header className="svSectionHeader"><div><small>{eyebrow}</small><h2>{title}</h2>{description&&<p>{description}</p>}</div>{action&&<div className="svSectionAction">{action}</div>}</header>}
export function MetricCard({label,value,detail,tone="neutral"}:{label:string;value:ReactNode;detail?:ReactNode;tone?:string}){return <article className="svMetric" data-tone={tone}><small>{label}</small><strong>{value}</strong>{detail&&<span>{detail}</span>}</article>}
export function EmptyState({title,detail}:{title:string;detail?:string}){return <div className="svEmpty"><strong>{title}</strong>{detail&&<p>{detail}</p>}</div>}
