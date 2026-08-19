"use client";
import { useEffect, useState } from "react";
type Project = {
  name: string;
  url: string;
  practice: string;
  adoption: string;
};
type Report = {
  reviewed_at: string;
  projects: Project[];
  priority_changes: string[];
  decision: string;
};
export default function OpenSourceMethods() {
  const [data, setData] = useState<Report | null>(null);
  useEffect(() => {
    fetch("/open-source-methods.json")
      .then((x) => x.json())
      .then(setData);
  }, []);
  if (!data) return <main className="watchdash">正在载入开源系统研究…</main>;
  return (
    <main className="watchdash">
      <header className="watchhero contextHero">
        <div>
          <a href="/zh">← 返回因子研究</a>
          <p className="label">开源量化系统研究 · {data.reviewed_at}</p>
          <h1>学习流程，不照搬收益。</h1>
          <p>比较成熟系统如何管理数据、训练、回测、风险和实盘迁移。</p>
        </div>
        <div className="contextScore">
          <small>研究项目</small>
          <b>{data.projects.length}</b>
          <span>套主流开源系统</span>
        </div>
      </header>
      <section className="watchnote">
        <b>决定：</b>
        {data.decision}
      </section>
      <section className="methodGrid">
        {data.projects.map((x) => (
          <article key={x.name}>
            <a href={x.url} target="_blank" rel="noreferrer">
              {x.name} ↗
            </a>
            <h2>他们怎么做</h2>
            <p>{x.practice}</p>
            <h2>我们怎么吸收</h2>
            <p>{x.adoption}</p>
          </article>
        ))}
      </section>
      <section className="zhrules">
        <h2>训练流程升级顺序</h2>
        {data.priority_changes.map((x, i) => (
          <p key={x}>
            <b>{i + 1}</b>
            {x}
          </p>
        ))}
        <mark>
          最重要的变化：以后“训练”不是不断换参数，而是让每个想法经过同一套可复现、可否决的晋级流程。
        </mark>
      </section>
    </main>
  );
}
