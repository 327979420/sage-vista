# Sage Vista

Sage Vista 是一个私有、可解释、可人工复核的美股技术研究与日终扫描项目。当前研究主线是 MACD：使用长期趋势、价格位置、支撑、结构、RSI、成交量等独立证据，检验它们能否提高日线 MACD 金叉后 20 个与 100 个交易日的结果。

项目不是自动荐股或自动下单系统。所有信号只使用当时已经完整收盘的数据；回测按下一交易日复权开盘价进入；失败、不稳定和样本不足的实验也永久保留。

唯一生产站点：<https://sage-vista-parallel.gizmo-allied-0s.workers.dev>。旧 `chatgpt.site` 已退出生产链，不作为数据新鲜度、发布成功或 Discord 链接的依据。

## 当前产品结构

每日产品流固定为五层，不再维护平行 Signal Board：

1. **今日研究总览**：市场状态、行业位置、技术机会、多因子上下文与数据审计。
2. **指标共振 / Technical Tracker**：唯一的股票技术机会排名。
3. **多因子**：27 项技术证据层，不建立第二套排名。
4. **行业雷达**：行业与 Theme 上下文，不进入 Technical Score。
5. **研究 / 实验**：历史实验、失败记录、样本和 20/100 日结论。

旧根路径 `US Equity Signals / Signal Board` 及其 mock candidates 已移除；根路径现在就是使用 production JSON 的今日研究总览。

RSI、RSI 底背离、成交量放大等不再需要各自占用独立功能页，但其检测能力必须保留并逐步迁移到统一因子库。

## 长期方向

- 建立约 20 个或更多可扩展因子的统一因子库。
- 每个因子记录定义、类别、周期、状态、样本、20/100 日结果、版本和防前视审计。
- 多因子雷达不长期固定为当前六项一分制，而是读取因子库，区分正式验证分、观察分和冲突扣分。
- 美国市场完整收盘后自动更新 MACD Tracker 与多因子雷达。
- 未来接入 Discord Bot，只在达到门槛的稀有机会出现时播报，并提供网站复查链接。
- 在信息结构稳定后统一升级为简洁、专业、适合桌面与手机复查的金融研究 UI。

## 文档

- [Factor Architecture：权威 inventory、生命周期与系统边界](docs/FACTOR_ARCHITECTURE.md)
- [Industry Radar V1 架构、数据与 Theme Universe 说明](research/INDUSTRY_RADAR.md)
- [项目蓝图与产品框架](docs/PROJECT_BLUEPRINT_ZH.md)
- [产品决策日志](docs/DECISION_LOG_ZH.md)
- [下一对话交接说明](docs/NEXT_SESSION_HANDOFF_ZH.md)
- [Tracker 产品要求](docs/TRACKER_PRODUCT_REQUIREMENTS_ZH.md)
- [技术规则手册](docs/TECHNICAL_RULEBOOK.md)
- [研究账本说明](research/README.md)
- 实验机器记录：`research/experiments.jsonl`

出现文档冲突时，以 `docs/PROJECT_BLUEPRINT_ZH.md` 中最新注明日期的决定为准；实现完成后必须同步更新 README、蓝图和决策日志。

## 本地运行与验证

```bash
npm install
npm run dev
```

```bash
python3 -m unittest discover -s tests
npm run build
```
