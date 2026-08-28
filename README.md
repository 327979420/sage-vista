# Sage Vista

Sage Vista 是一个开源、可解释、可人工复核的美股技术研究与日终扫描项目。当前主线是以日线 MACD 触发的多因子模型：使用月线、周线、日线的趋势、价格位置、支撑、结构、RSI、成交量，以及大盘和行业上下文，持续检验哪些组合真正有帮助。

项目不是自动荐股或自动下单系统。所有信号只使用当时已经完整收盘的数据；回测按下一交易日复权开盘价进入；失败、不稳定和样本不足的实验也永久保留。

唯一生产站点：<https://sage-vista-parallel.gizmo-allied-0s.workers.dev>。旧 `chatgpt.site` 已退出生产链，不作为数据新鲜度、发布成功或 Discord 链接的依据。

## 当前产品结构

每日产品流固定为四层，不再维护平行 Signal Board 或旧 MACD Tracker 页面：

1. **今日研究总览**：市场状态、行业位置、Top 5 技术机会、Forward Observation 与数据审计。
2. **多因子机会**：当前 37 项统一技术证据层；日线 MACD 触发后检测其余 36 项，并维护唯一权威排行榜、精选子集和个股详情。
3. **行业雷达**：行业与 Theme 上下文，不进入 Technical Score。
4. **研究 / 实验**：明确分开 Backtesting、Forward Testing 和 Experiments；Signal History 的 canonical UI 在 Forward Testing。

生产提醒另有一份 append-only `signal-history.json`：它保存当时真实显示的 Technical / Multi-Factor opportunity、冻结当时的因子与 Industry 上下文，并只随未来交易日逐步填写 forward outcome。它不等于历史回测，也不会因股票离开今日榜单而消失。

旧根路径 `US Equity Signals / Signal Board` 及其 mock candidates 已移除；根路径现在就是使用 production JSON 的今日研究总览。

RSI、RSI 底背离、成交量放大等不再需要各自占用独立功能页，但其检测能力必须保留并逐步迁移到统一因子库。

## 长期方向

- 在当前 37 因子库上继续扩展可验证、可审计的多周期因子。
- 每个因子记录定义、类别、周期、状态、样本、20/100 日结果、版本和防前视审计。
- 多因子雷达读取统一因子库，区分技术候选分、实验观察分、正式验证分和风险扣分。
- 美国市场完整收盘后自动更新 MACD Tracker 与多因子雷达。
- 未来接入 Discord Bot，只在达到门槛的稀有机会出现时播报，并提供网站复查链接。
- 持续维护简洁、专业、适合桌面与手机复查的金融研究 UI；正文不低于 15–16px，工程审计元数据不与决策信息竞争。

## 文档

- [Sage Vista 总规则手册：项目宗旨、全局流程和模块地图](docs/SAGE_VISTA_RULEBOOK_ZH.md)
- [模块规则索引：精准定位评分、因子、实验、回测、红线等规则](docs/rules/README.md)
- [Factor Architecture：权威 inventory、生命周期与系统边界](docs/FACTOR_ARCHITECTURE.md)
- [Industry Radar V1 架构、数据与 Theme Universe 说明](research/INDUSTRY_RADAR.md)
- [Signal History 与 Production Forward Observation 权威说明](docs/SIGNAL_HISTORY.md)
- [项目蓝图与产品框架](docs/PROJECT_BLUEPRINT_ZH.md)
- [产品决策日志](docs/DECISION_LOG_ZH.md)
- [下一对话交接说明](docs/NEXT_SESSION_HANDOFF_ZH.md)
- [Tracker 产品要求](docs/TRACKER_PRODUCT_REQUIREMENTS_ZH.md)
- [技术规则手册](docs/TECHNICAL_RULEBOOK.md)
- [研究账本说明](research/README.md)
- 实验机器记录：`research/experiments.jsonl`

出现文档冲突时，具体业务含义以对应的 `docs/rules/*.md` 模块规则为准；总手册负责项目宗旨、模块边界和全系统流程；实验数字以机器账本和版本化产物为准。任何语义改动必须先更新对应模块规则，再改代码、测试和生产页面。

## 本地运行与验证

```bash
npm install
npm run dev
```

```bash
python3 -m unittest discover -s tests
npm run build
```
