# Sage Vista 仓库瘦身审计

审计日期：2026-08-30  
范围：Git跟踪文件、正式四页、每日EOD、测试、工作流、文档引用和实验账本。  
原则：修改时间只用于发现候选，不作为删除依据。仓库最早提交为2026-08-17，本轮没有真正“超过两周未维护”的文件。

## 必须保留

| 范围 | 理由 |
|---|---|
| 四个正式页面及其CSS、轻量JSON | 当前网站产品 |
| `daily_tracker_update.py`及其显式依赖 | 每日原子更新主链 |
| 因子注册、检测、评分、Unified V2、机会与信号账本 | 当前39项因子、排行和历史追踪 |
| `research/backtest/`、实验账本和预登记 | 永久复现成功、失败与负结果 |
| 行业、大盘、主题成员与数据输入 | 正式行业与大盘页和独立分层 |
| 历史更名记录与旧实验冻结抽样种子 | 保持事实和确定性样本可复现 |

## 迁移到Git研究档案

以下结果没有正式网页消费者，但仍能说明早期数据、因子和中性化实验做过什么，因此从`public/`迁入`research/backtest/output/legacy-foundation/`：

- `data-audit.json`
- `eodhd-factor-pilot.json`
- `eodhd-factor-validation.json`
- `market-context-factor-test.json`
- `neutralization-test.json`
- `research-report.json`

夜间回测紧凑进度不是网页功能，`public/backtest-progress.json`等内容迁到`automation/backtest-progress.json`；权威断点仍是`automation/backtest-state.json`。

对应研究脚本继续保留并把默认输出改到新目录。迁移不改JSON内容，也不重跑实验。

## 确认删除

| 文件或模块 | 删除证据 |
|---|---|
| `public/file.svg`、`globe.svg`、`window.svg` | Next.js模板资产；代码、样式和元数据均无引用 |
| `public/open-source-methods.json` | 无生成入口、无页面、测试、文档或实验引用 |
| `run_universe.py`、`run_efficiency.py`、`run_backtest.py`及其旧公开产物 | 只覆盖7只样例股票；无工作流、测试、页面或实验账本入口，已由全市场EODHD与正式回测取代 |
| `public/market-data/` | 仅由上述旧7股票脚本生成，无消费者 |
| `frameworks.py` | 从未被导入或测试的指标原型；正式因子检测由`factor_detectors.py`负责 |
| `sector_watch.py`及`sector-watch.json` | 无消费者，已由正式`industry_radar.py`与`market_etf_watch.py`取代 |
| `research_opportunity_pool.py`及公开JSON | 旧研究页已退役，无当前消费者；永久事件仍在正式机会／信号账本和研究周档案 |
| `integrations/lean/` | 从未在本项目安装或运行LEAN/.NET，无结果、测试、工作流或账本引用；Git历史可恢复 |
| `public/universe-expansion.json` | 每日链只在临时目录生成审计报告，正式网页从不读取此旧副本 |

## 删除后护栏

1. 全仓库搜索不得残留对已删路径的活动引用。
2. 完整Python测试、网站lint、类型检查、生产构建与渲染测试必须通过。
3. 工作流必须通过YAML解析；正式每日输出日期与防前视合同不改。
4. 若以后确实需要旧原型，先从Git历史单独恢复并重新登记用途，不把整套旧目录无条件带回。
