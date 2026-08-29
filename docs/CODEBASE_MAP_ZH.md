# Sage Vista 代码地图

用途：让新对话先定位、后阅读。这里记录代码职责，不复制业务规则、实验数字或当前进度；那些内容仍以 `docs/rules/`、机器账本和 `docs/CURRENT_STATUS_ZH.md` 为准。

## 先看哪里

| 用户问题 | 首要代码 | 必要数据 |
| --- | --- | --- |
| 今日总览、推荐理由 | `app/zh/watch/resonance/page.tsx` | `public/unified-v2-rankings.json`、`public/decision-summary.json`、市场/行业 JSON |
| 多因子排行榜、个股命中明细 | `app/zh/watch/resonance/rare-opportunities/page.tsx` | `public/daily-factor-snapshot.json`、`public/factor-registry.json`、`public/opportunity-ledger.json` |
| 行业与大盘 | `app/zh/watch/industry-radar/page.tsx` | `public/industry-radar.json`、`public/market-etf-watch.json` |
| 历史、实验、回测断点 | `app/zh/watch/resonance/research/page.tsx` | `public/experiment-catalog.json`、`public/signal-history.json`、`public/backtest-progress.json` |
| 因子定义/检测/评分 | `services/scanner/factor_registry.py`、`factor_detectors.py`、`factor_snapshot.py`、`factor_scoring.py` | `public/factor-registry.json` |
| V2 历史回放与排名 | `services/scanner/unified_v2_scan.py` | `public/unified-v2-rankings.json` |
| 永久追踪池 | `services/scanner/opportunity_ledger.py`、`signal_history.py` | `public/opportunity-ledger.json`、`public/signal-history.json` |
| 行业分类与 ETF 上下文 | `services/scanner/industry_membership.py`、`industry_radar.py`、`theme_etf_context.py` | `data/industry/`、`data/themes/` |
| 市场环境 | `services/scanner/market_etf_watch.py` | `public/market-etf-watch.json` |
| 自动化/上线 | `.github/workflows/`、`services/scanner/daily_tracker_update.py`、`verify_live_deployment.py` | `automation/production-state.json`、`public/update-status.json` |
| 每日独立定时与恢复 | `services/automation/eod_scheduler_worker.mjs`、`wrangler.eod-scheduler.jsonc`、`eod-freshness-monitor.yml` | Cloudflare Cron 日志、EOD Actions 运行与新鲜度告警 |

## 正式产品只有四个入口

1. `/`：今日研究总览。
2. `/zh/watch/resonance/rare-opportunities`：多因子机会与唯一权威排行榜。
3. `/zh/watch/industry-radar`：行业与大盘上下文。
4. `/zh/watch/resonance/research`：历史、Forward Testing 与实验。

共享外壳在 `app/zh/watch/resonance/tracker-ui.tsx`；正式视觉分别在 `app/home-v3.css`、`app/product-v2.css` 和少量 `app/globals.css`。`about` 与 strategy/factor/market/ranking/selection 等页面是上述研究中心的详细研究页，不是另一套生产产品。

旧路径 `/technical`、`/data-quality`、`/efficiency`、`/research`、`/zh/**` 的旧入口和独立 RSI/Volume/Confluence 页面只保留兼容跳转。不要在这些路径重新建立平行产品。

## 每日生产数据流

`daily-eod.yml`
→ `daily_tracker_update.py`
→ 同一完整收盘日生成 Tracker、MACD 触发后的全因子快照、旧评分兼容雷达、行业、大盘、真实 signal history
→ 日期与防前视校验全部通过后原子替换 `public/*.json`
→ 生成当日 Unified V2 与永久 opportunity ledger
→ Python 测试、前端 lint/typecheck/build/render 测试
→ Cloudflare 部署
→ 线上日期和审计复核
→ Discord 去重发送。

任何一步失败都不能把半套日期或半套数据发布到网站。

## 自动化各自负责什么

- `daily-eod.yml`：正式日终数据、部署、线上核验和 Discord；不是多年回测。
- `nightly-backtest.yml`：每晚向更早日期完成一周；成功合并、测试、提交后才移动断点。
- `deploy-site.yml`：代码或 UI 改动后的单独部署；使用已有审计数据，不重新扫描市场。
- `eod-freshness-monitor.yml`：检查数据是否过期。
- `open-source-industry-sync.yml`、`industry-radar-validation.yml`：行业数据源同步和验证。
- `opportunity-ledger-refresh.yml`：重建可复用追踪视图，不重写当时冻结事实。
- 其余 `*-backtest.yml` 与 `*-backfill.yml`：人工研究、恢复或历史补算工具；不是重复的每日生产流水线，不要因“平时没自动运行”而删除。

## 应保留但通常不用先读的目录

- `research/backtest/`：已完成和可复现实验实现。
- `research/experiments.jsonl`、`experiment-events.jsonl`、`preregistrations/`：实验永久记录，包括失败和中断。
- `integrations/lean/`：外部框架对照/集成研究。
- `data/`：行业和主题的版本化输入。
- `work/`：可再生成的本地缓存或批次中间产物；不是产品规则来源。

## 快速验证

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
npm test
```

`npm test` 已包含 lint、TypeScript 检查、生产构建和服务端页面渲染测试。只改 Python 时仍需跑 Python 测试；涉及页面、JSON 合约、部署或共享流程时两组都要跑。

## 不要再做的事

- 不要从聊天猜当前日期、版本或回测断点。
- 不要用旧 UI 文件推断当前业务。
- 不要把研究脚本因“静态引用少”判定为垃圾；先查实验账本、工作流和 CLI 用途。
- 不要删除历史信号、负结果、失败实验或兼容入口。
- 不要新增第二套排行榜、第二份因子定义或第二条日终发布通道。
