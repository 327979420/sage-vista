"use client";
import {SiteIcon,navigationIcons} from './site-icon';
import {useNavigationCount} from './navigation-count';
import {usePathname} from 'next/navigation';
import {Localized} from './i18n/locale';
export const siteLinks = [
 ['今日', '/'], ['3W 信号', '/signals'], ['前向记录', '/forward'], ['形态速览', '/patterns'],
 ['我的组合', '/portfolio'], ['成绩单', '/scorecard'], ['学习', '/learn'],
] as const;
export default function SiteNavigation() {
 const path=usePathname(),count=useNavigationCount();
 return <Localized><div className="rtPage svNavigation"><nav className="rtModuleNav" aria-label="主要功能">{siteLinks.map(([label,href],index)=>{
 const active=path===href||(href==='/signals'&&path==='/opportunities')||(href==='/patterns'&&path==='/zh/watch/resonance/favorite-pattern');
 return <a key={href} href={href} className={active?'isStar active':undefined} aria-current={active?'page':undefined}><SiteIcon path={navigationIcons[index]}/><span>{label}</span>{active&&count?.path===href&&<em className="rtStarCount" title={href==='/'?'新信号':'持仓'}>{count.value}</em>}</a>;
 })}<details className="svNavMore" key={path}><summary className={path==='/archive'?'active':undefined}>更多</summary><div><a href="/archive">研究档案</a></div></details></nav></div></Localized>;
}
