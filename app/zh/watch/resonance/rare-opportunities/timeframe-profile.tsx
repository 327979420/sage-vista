export type TimeframeProfile={version:string;status:"experimental_descriptive_only";label:string;dominant_timeframe:"daily"|"weekly"|"monthly"|null;is_resonance:boolean;points:Record<"daily"|"weekly"|"monthly",number>;shares:Record<"daily"|"weekly"|"monthly",number>;independent_groups:Record<"daily"|"weekly"|"monthly",number>;anchor_present:Record<"daily"|"weekly"|"monthly",boolean>;evidence:Record<"daily"|"weekly"|"monthly",string[]>};

const frames=[
 ["daily","日线"],
 ["weekly","周线"],
 ["monthly","月线"],
] as const;

export function TimeframeProfilePanel({profile}:{profile:TimeframeProfile}){
 return <section className="timeframePanel">
  <header><div><small>TIMEFRAME PROFILE · EXPERIMENTAL</small><h2>{profile.label}机会</h2><p>根据去重后的日、周、月技术证据判断机会主要来自哪个周期。</p></div><mark>不改变当前 V2 排名</mark></header>
  <div>{frames.map(([key,label])=><article key={key} className={profile.dominant_timeframe===key?"isDominant":""}><span>{label}</span><b>{profile.points[key]}<small>实验贡献</small></b><p>{profile.independent_groups[key]} 组独立证据 · {(profile.shares[key]*100).toFixed(0)}%</p></article>)}</div>
  <footer>当前标签只解释“这是哪一个周期的机会”，不是建议持仓天数。日线、周线、月线的持仓窗口将在 V3 回测完成后分别确定。</footer>
 </section>
}
