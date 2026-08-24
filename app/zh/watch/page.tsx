export default function WatchHome() {
  return (
    <main className="rtPage watchFocus">
      <header className="rtSubHero">
        <div>
          <p className="rtEyebrow">盯盘助手</p>
          <h1>先把最重要的信号看清楚</h1>
          <p>当前首页只保留两个决策入口：指标共振负责找机会，ETF 温度计负责判断市场环境。</p>
        </div>
      </header>
      <section className="watchFocusGrid">
        <a className="watchFocusCard primary" href="/zh/watch/resonance">
          <small>核心功能</small><h2>指标共振</h2>
          <p>查看 MACD 多周期传导、RSI 底背离、双指标确认和成交量异动。</p>
          <b>进入今日扫描 →</b>
        </a>
        <a className="watchFocusCard" href="/zh/watch/market">
          <small>辅助判断</small><h2>ETF 市场温度计</h2>
          <p>用 SPY、QQQ、DIA、IWM 等主流 ETF 判断趋势、风险偏好和市场宽度。</p>
          <b>查看市场环境 →</b>
        </a>
      </section>
      <p className="watchFocusNote">行业消息和研究页面不再占用核心导航；数据与研究仍保留，但不会干扰每日盯盘。</p>
    </main>
  );
}
