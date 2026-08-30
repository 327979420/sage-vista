export type TimeframeProfile={version:string;status:"count_based_research_priority"|"experimental_descriptive_only";label:string;dominant_timeframe:"daily"|"weekly"|"monthly"|null;is_resonance:boolean;points:Record<"daily"|"weekly"|"monthly",number>;shares:Record<"daily"|"weekly"|"monthly",number>;independent_groups:Record<"daily"|"weekly"|"monthly",number>;anchor_present:Record<"daily"|"weekly"|"monthly",boolean>;evidence:Record<"daily"|"weekly"|"monthly",string[]>;resonance_bonus?:number;resonances?:{family:string;timeframes:string[];bonus:number}[]};

const frames=[
 ["daily","日线"],
 ["weekly","周线"],
 ["monthly","月线"],
] as const;

export function TimeframeProfilePanel({profile}:{profile:TimeframeProfile}){
 return <section className="timeframePanel">
  <header><div><small>TIMEFRAME RESONANCE · COUNTED</small><h2>{profile.label}机会</h2><p>把实际命中的日、周、月技术证据拆开，跨周期同家族会获得共振优先级。</p></div><mark>周期共振 +{profile.resonance_bonus??0}</mark></header>
  <div>{frames.map(([key,label])=><article key={key} className={profile.dominant_timeframe===key?"isDominant":""}><span>{label}</span><b>{profile.points[key]}<small>命中颗数</small></b><p>{profile.independent_groups[key]} 个家族 · {(profile.shares[key]*100).toFixed(0)}%</p></article>)}</div>
  <footer>这些颗数直接参与“先看谁”的排序，但仍不是建议持仓天数或已验证胜率。</footer>
 </section>
}
