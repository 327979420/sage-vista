'use client';
import {Localized} from '../i18n/locale';
import {SiteIcon,stepIcons} from '../site-icon';
import {num,rText} from './shared';
export type StepperProps = {
 status:string; signalDate:string; fillDate?:string|null; exitDate?:string|null;
 fillPrice?:number|null; exitPrice?:number|null; R:number|null; outcome?:string|null; mini?:boolean;
};
export function OutcomeStepper({status,signalDate,fillDate,exitDate,fillPrice,exitPrice,R,outcome,mini=false}:StepperProps) {
 const closed=status==='closed',filled=closed||status==='filled'||status==='open';
 const active=closed?3:filled?1:status==='waiting'?0:-1;
 // Status, not a mark-to-market R, determines completion and result colour.
 const result=closed?R:null;
 const kind=outcome==='win'?'target':outcome==='loss'?'stop':outcome;
 const icon=kind==='target'||kind==='stop'||kind==='time'?kind:'result';
 const steps:{label:string;icon:keyof typeof stepIcons;date:string|null|undefined;value:string|null;done:boolean}[]=[
  {label:'信号',icon:'signal' as const,date:signalDate,value:null,done:true},
  {label:'成交',icon:'fill' as const,date:filled?fillDate:null,value:filled?num(fillPrice):'—',done:filled},
  {label:'退出',icon:'exit' as const,date:closed?exitDate:null,value:closed?num(exitPrice):'—',done:closed},
  {label:'结果',icon:closed?icon:'result' as const,date:closed?exitDate:null,value:rText(result),done:closed},
 ];
 const statusLabel:Record<string,string>={waiting:'等待成交',filled:'已成交',open:'已成交',closed:'已平仓',cancelled:'已取消',skipped:'不挂单',unverified:'未核验',unavailable:'暂无数据'};
 return <Localized><div className={`svStepperScroll${mini?' isMini':''}`}>
 <ol className="svOutcomeSteps" aria-label={statusLabel[status]??'暂无数据'}>{steps.map((step,i)=><li key={step.label} className={`${step.done?'isDone':'isFuture'}${i===active?' isCurrent':''}${i===3?' isResult':''}`} data-result={i===3?(result!==null&&result>0?'positive':result!==null&&result<0?'negative':'neutral'):undefined} aria-current={i===active?'step':undefined}>
 <span className="svStepNode" role="img" aria-label={step.label} title={step.label}><SiteIcon path={stepIcons[step.icon]}/></span>
 {!mini&&<div className="svStepDetail"><time>{step.date??'—'}</time>{step.value!==null&&<strong>{step.value}</strong>}</div>}
 </li>)}</ol></div></Localized>;
}
