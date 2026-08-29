# Sage Vista 当前状态

> 本文件由 `python3 -m services.scanner.project_status` 从机器状态生成；不要手工修改数字。若与下方机器源不一致，先修复生成流程再改业务代码。

## 现在可确认的事实

- 生产网站：<https://sage-vista-parallel.gizmo-allied-0s.workers.dev>
- 最新完整美股收盘：2026-08-28；生产状态已核验。
- UI：v5.7。
- 因子库：0.9.0，共 37 项。
- 当前夜间新批次模型：`unified-v2-macd-trigger-1.3.0`；因子注册表代码版本 `0.9.0`。
- 数据审计：日期一致 `true`；未来数据 `false`。

## 历史回测断点

- 已保存：2026-01-02 至 2026-08-27，共 164 个交易日。
- 最近成功周：2026-04-20 至 2026-04-26，共 5 个交易日。
- 下一批：2025-12-29 至 2026-01-01。
- 夜间续跑：已开启；21:30 AEST / 22:30 AEDT；成功后才移动断点，失败重试同一周。
- 旧批次冻结原规则版本；新规则只用于后续尚未运行批次。
- 回测状态更新时间：2026-08-28T15:23:35Z。

## 实验

- 总数 25；已完成 20；待运行 / 进行中 5。
- `score-timeframe-attribution-v2.0.0-2026-08-29`：完整事件池评分、周期与因子归因V2。
- `evidence-calibrated-daily-score-v1.0.0-2026-08-29`：长期证据校准每日评分V1。
- `score-monotonicity-factor-attribution-v1.0.0-2026-08-29`：评分单调性与因子归因V1。
- `exit-score-v0.1.0-2026-08-28`：独立离场风险分V0.1。
- `timeframe-score-v3.0.0-2026-08-28`：大周期优先评分V3。
- 目前策略宝典仍没有达到完整验证门槛的正式条目；候选结论不能冒充生产胜率。

## 当前工作顺序

1. 保持每日 EOD、永久机会账本和夜间逐周回测稳定运行。
2. 用持续扩展的历史样本完成已预登记的周期评分和独立退出实验。
3. 只有验证通过后才调整正式评分、持仓或退出生产规则。
4. 技术主线稳定后再精进行业、大盘和最终 UI 表达。

## 新对话下一步

1. 先检查 `git status` 和最新 `main` 提交。
2. 根据用户的新要求在 `docs/CHANGE_REQUESTS_ZH.md` 新增或更新一条需求。
3. 用 `docs/rules/README.md` 选择唯一主模块；先改规则文字，再改代码。
4. 未收到新的明确任务时，不自行改变生产评分或重跑旧历史。

## 权威机器源

- `automation/backtest-state.json`
- `automation/production-state.json`
- `public/update-status.json`
- `public/factor-registry.json`
- `public/experiment-catalog.json`

来源时间：生产数据更新 2026-08-29T00:58:35.269626+00:00；实验目录生成 2026-08-29T12:16:00+10:00。
