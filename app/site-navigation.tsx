"use client";
import {useNavigationCount} from './navigation-count';
import {usePathname} from 'next/navigation';
import {Localized} from './i18n/locale';
export const siteLinks = [
 ['今日', '/'], ['3W 机会', '/opportunities'], ['我的组合', '/portfolio'],
 ['成绩单', '/scorecard'], ['学习', '/learn'], ['研究档案', '/archive'],
] as const;
const icons=[
 'M3 17V7m6 10V3m6 14v-6m6 6V5',
 'M12 3l1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9zM19 15l.8 2.2 2.2.8-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z',
 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
 'M4 4v16h17M8 15l4-5 4 2 5-7',
 'm3 16 4-7 5 8 5-12 4 5',
 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
];
export default function SiteNavigation() {
 const path=usePathname(),count=useNavigationCount();
 return <Localized><div className="rtPage svNavigation"><nav className="rtModuleNav" aria-label="主要功能">{siteLinks.map(([label,href],index)=>{
 const active=path===href||(href==='/archive'&&path.startsWith('/zh/'));
 return <a key={href} href={href} className={active?'isStar active':undefined} aria-current={active?'page':undefined}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={icons[index]}/></svg><span>{label}</span>{active&&count?.path===href&&<em className="rtStarCount" title={href==='/'?'新信号':'持仓'}>{count.value}</em>}</a>;
 })}</nav></div></Localized>;
}
