# Northstar

Northstar 是一个私有、可解释、可人工复核的美股技术研究与日终扫描项目。当前研究主线是 MACD：使用长期趋势、价格位置、支撑、结构、RSI、成交量等独立证据，检验它们能否提高日线 MACD 金叉后 20 个与 100 个交易日的结果。

项目不是自动荐股或自动下单系统。所有信号只使用当时已经完整收盘的数据；回测按下一交易日复权开盘价进入；失败、不稳定和样本不足的实验也永久保留。

## 当前产品结构

网站最终只保留四个主要功能入口：

1. **总览**：最新数据日期、当日重点和稀有机会摘要。
2. **MACD Tracker**：日线、周线、月线 MACD 状态与候选。
3. **多因子雷达**：从统一因子库读取命中证据并动态评分。
4. **MACD 研究**：历史实验、失败记录、样本和 20/100 日结论。

RSI、RSI 底背离、成交量放大等不再需要各自占用独立功能页，但其检测能力必须保留并逐步迁移到统一因子库。

## 长期方向

- 建立约 20 个或更多可扩展因子的统一因子库。
- 每个因子记录定义、类别、周期、状态、样本、20/100 日结果、版本和防前视审计。
- 多因子雷达不长期固定为当前六项一分制，而是读取因子库，区分正式验证分、观察分和冲突扣分。
- 美国市场完整收盘后自动更新 MACD Tracker 与多因子雷达。
- 未来接入 Discord Bot，只在达到门槛的稀有机会出现时播报，并提供网站复查链接。
- 在信息结构稳定后统一升级为简洁、专业、适合桌面与手机复查的金融研究 UI。

## 文档

- [项目蓝图与产品框架](docs/PROJECT_BLUEPRINT_ZH.md)
- [产品决策日志](docs/DECISION_LOG_ZH.md)
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
