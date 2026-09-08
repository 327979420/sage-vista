# Sage Vista 代码地图

用途：让新对话先定位、后阅读。这里记录代码职责，不复制业务规则、实验数字或当前进度；那些内容仍以 `docs/rules/`、机器账本和 `docs/CURRENT_STATUS_ZH.md` 为准。

## 先看哪里

| 用户问题 | 首要代码 | 必要数据 |
| --- | --- | --- |
| 今日总览、推荐理由 | `app/zh/watch/resonance/page.tsx` | `public/unified-v2-latest.json`、`public/signal-history-summary.json`、市场/行业 JSON |
| 多因子排行榜、个股命中明细 | `app/zh/watch/resonance/rare-opportunities/page.tsx` | `public/cr056-ranking.json`；展开明细按需加载 `public/cr056-factor-details.json.gz` |
| 我最喜欢形态 | `app/zh/watch/resonance/favorite-pattern/page.tsx` | `public/favorite-pattern.json` |
| 行业与大盘 | `app/zh/watch/industry-radar/page.tsx` | `public/industry-radar.json`、`public/market-etf-watch.json` |
| 旧版历史、实验、回测断点（Git 后台） | `research/backtest/`、`services/scanner/experiment_catalog.py` | `research/generated/experiment-catalog.json`、`research/experiments.jsonl`、`automation/backtest-state.json`、`automation/backtest-progress.json` |
| 旧版因子登记/检测/评分（历史兼容） | `services/scanner/factor_registry.py`、`factor_detectors.py`、`factor_snapshot.py`、`factor_scoring.py` | `public/factor-registry.json` |
| 新版候选政策/因子/唯一评分 | `services/contracts/cr056_policy.py`、`services/scanner/factor_detectors.py`、`services/ranking/cr056.py` | 同一政策下的三周期事实与评分明细 |
| 新版日终与持续观察 | `services/scanner/cr056_daily.py`、`cr056_runner.py`、`services/ledger/cr056.py` | `automation/cr056-watch-state.json.gz`、`research/generated/cr056-daily/` |
| 回测页面、账户与永久报告 | `app/zh/backtest/page.tsx`、`research/backtest/run_research.py`、`account_runner.py`、`run_store.py` | `research/backtest/output/reusable-runs/`；当前运行输入仍为旧机会账本 |
| 外部候选因子、赢家配对和走步实验 | `research/factor-candidates-v2.json`、`research/factor_lab/features.py`、`research/backtest/factor_strategy_lab_v2.py` | `research/backtest/output/factor-strategy-lab-v2.json` |
| 旧版 V2 历史回放与排名 | `services/scanner/unified_v2_scan.py` | `public/unified-v2-rankings.json` |
| 旧版永久追踪池 | `services/scanner/opportunity_ledger.py`、`signal_history.py` | `public/opportunity-ledger.json`、`public/signal-history.json` |
| 行业分类与 ETF 上下文 | `services/scanner/industry_membership.py`、`industry_radar.py`、`theme_etf_context.py` | `data/industry/`、`data/themes/` |
| 市场环境 | `services/scanner/market_etf_watch.py` | `public/market-etf-watch.json` |
| 自动化/上线 | `.github/workflows/`、`services/scanner/daily_tracker_update.py`、`verify_live_deployment.py` | `automation/production-state.json`、`public/update-status.json` |
| 每日独立定时与恢复 | `services/automation/eod_scheduler_worker.mjs`、`wrangler.eod-scheduler.jsonc`、`eod-freshness-monitor.yml` | Cloudflare Cron 日志、EOD Actions 运行与新鲜度告警 |

## 正式产品的五个入口

1. `/`：今日研究总览。
2. `/zh/watch/resonance/rare-opportunities`：多因子机会与唯一权威排行榜。
3. `/zh/watch/resonance/favorite-pattern`：独立的“我最喜欢形态”每日追踪。
4. `/zh/watch/industry-radar`：SPY 等大盘与常用行业 ETF 上下文。
5. `/zh/backtest`：历史运行、QuantStats 曲线、收益与回撤、逐笔买卖依据；复用已有报告。

共享外壳在 `app/zh/watch/resonance/tracker-ui.tsx`；正式视觉分别在 `app/home-v3.css`、`app/product-v2.css`、`app/favorite-pattern.css` 和少量 `app/globals.css`。实验、失败结果、逐期产物和回测断点永久保存在 Git 研究目录；回测页读取已有运行索引与报告，不另存一套业务结果。旧研究目录不整体恢复为网站菜单。

旧回测路径 `/zh/watch/resonance/strategy-backtest-v2` 兼容跳转到 `/zh/backtest`；不能把整个 `/zh/**` 误认为旧路径。新增报告进入既有回测入口，不另建实验专用页面。

## 一条业务链及职责边界

行情与股票池 → 大盘/行业 ETF 背景 → 个股日线门票 → 同一入口检查月、周、日因子 → 唯一评分 → 每日新提名/持续总榜 → 冻结信号 → 交易执行与账户回测 → 永久结果 → 回测页查看与对照 → 有证据再修改规则。

这是接线目标，不能据此宣称已全部接通：新版每日榜已可用；现有账户回测仍消费旧版信号。下一步缺口是用历史当时可见数据调用同一个新版因子/评分入口，接入现有账户与报告。不得再复制一套历史评分器，也不能把旧信号换个版本号称为新版回测。具体顺序与复用边界只维护在 [规则08](rules/08_BACKTEST_AND_EXPERIMENTS.md#新版日常使用与回测的交付顺序)。

- 大盘/行业提供独立背景；未经批准不混入技术分。ETF 在每日业务上先于个股扫描，具体调度是否符合此顺序应沿日终入口核对，不能由设计顺序推断运行已符合。
- 新版候选由 `cr056_runner.py` 组织、`services/ranking/cr056.py` 评分；`cr056_public.py` 和页面只投影/展示。
- 旧 V2、旧机会账本和旧实验保留其版本身份，用于兼容与比较；不是新版评分的第二个来源。
- VectorBT 账户与 QuantStats 报告沿现有研究入口复用；历史信号连接、缓存及续跑的缺口就地补齐，不再开独立回测系统。

## 每日生产数据流

`daily-eod.yml` → `daily_tracker_update.py` 更新现有日终数据 → `cr056_daily.py` 使用同一完整收盘日生成新版评分、持续观察与公开明细 → 相关校验与提交 → 网站部署 → 线上核验。

失败不得把半套日期或半套数据作为成功版本发布。已有定时调度不等于每个未来交易日都已验证；新政策首次跨交易日更新仍需实际运行证据。Discord 仅在手动运行明确启用 `notify` 且上线核验通过时发送，不是当前每次定时更新都会发送。

## 自动化各自负责什么

- `daily-eod.yml`：正式日终数据、部署和线上核验；Discord 受上述开关控制；不是多年回测。
- `nightly-backtest.yml`：旧模型历史流水线，每晚向更早日期完成一周；不得称为新版历史回测。成功合并、测试、提交后才移动断点。
- `deploy-site.yml`：代码或 UI 改动后的单独部署；使用已有审计数据，不重新扫描市场。
- `eod-freshness-monitor.yml`：检查数据是否过期。
- `open-source-industry-sync.yml`、`industry-radar-validation.yml`：行业数据源同步和验证。
- `opportunity-ledger-refresh.yml`：沿同一工作流分 refresh、comparison、research 模式，分别负责旧追踪视图、成交对账和账户研究结果发布；不重写当时冻结事实。
- 其余 `*-backtest.yml` 与 `*-backfill.yml`：人工研究、恢复或历史补算工具；不是重复的每日生产流水线，不要因“平时没自动运行”而删除。

## 应保留但通常不用先读的目录

- `research/backtest/`：已完成和可复现实验实现。
- `research/backtest/output/legacy-foundation/`：早期EODHD、市场环境与中性化研究结果；只供Git复现，不发布到网站。
- `research/experiments.jsonl`、`experiment-events.jsonl`、`preregistrations/`：实验永久记录，包括失败和中断。
- `data/`：行业和主题的版本化输入。
- `work/`：可再生成的本地缓存或批次中间产物；不是产品规则来源。

## 文件去留判断

- 先看`docs/REPOSITORY_AUDIT_ZH.md`的保留、迁移与删除证据；不要仅凭修改时间判断。
- `public/`是网站发布面，不是实验仓库。没有任何正式页面或生产验证消费者的研究结果应放在`research/`。
- 当前每日链核心入口都应有模块说明；需要理解某个阶段时先读入口顶部，再沿其显式导入继续，不要从整个仓库猜流程。

## 快速验证

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
npm test
```

`npm test` 已包含 lint、TypeScript 检查、生产构建和服务端页面渲染测试。以上为完整检查命令，不是每次任务的强制清单；根据 [唯一执行规则](rules/01_GOVERNANCE.md) 选择受影响检查，纯文档不触发全量回测或前端构建。

## 不要再做的事

- 不要从聊天猜当前日期、版本或回测断点。
- 不要用旧 UI 文件推断当前业务。
- 不要把研究脚本因“静态引用少”判定为垃圾；先查实验账本、工作流和 CLI 用途。
- 不要删除历史信号、负结果、失败实验或兼容入口。
- 不要新增第二套排行榜、第二份因子定义或第二条日终发布通道。
