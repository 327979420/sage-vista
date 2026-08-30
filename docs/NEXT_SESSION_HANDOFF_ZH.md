# Sage Vista 新对话接手入口

状态：长期维护的固定入口，不再保存一次性路径或手抄进度。

## 三分钟接手顺序

1. 根目录 `AGENTS.md`：必须遵守的工作顺序和防误改护栏。
2. [`CURRENT_STATUS_ZH.md`](CURRENT_STATUS_ZH.md)：生产日期、回测断点、模型版本、实验数量和下一批次。
3. [`CODEBASE_MAP_ZH.md`](CODEBASE_MAP_ZH.md)：先定位页面、数据生成器和自动化，不再全仓库搜索。
4. [`SAGE_VISTA_RULEBOOK_ZH.md`](SAGE_VISTA_RULEBOOK_ZH.md)：项目宗旨、全系统流程和 12 个模块地图。
5. [`PROJECT_REQUIREMENTS_MASTER_ZH.md`](PROJECT_REQUIREMENTS_MASTER_ZH.md)：先理解用户最终要做成什么，以及哪些人工经验已经被提炼成长期要求。
6. [`rules/README.md`](rules/README.md)：根据用户本次要求只选一个主模块，再读取它的联动文件。
7. [`CHANGE_REQUESTS_ZH.md`](CHANGE_REQUESTS_ZH.md)：确认本次需求是否已经记录、批准、实现或暂缓。

不要先通读所有旧文档，不要把旧聊天里的日期、分数、页面数量、因子数量或运行状态当成当前事实。

## 新对话第一轮必须做什么

- 同步并检查 `main`，保护用户未提交修改。
- 用人话报告：网站最新数据日、当前 UI / 模型 / 因子版本、历史覆盖到哪里、下一周跑哪里、待运行实验有哪些。
- 复述用户这次要解决的问题，并说明它属于哪个模块、需要联动哪些模块。
- 如果用户只是要求检查或解释，先只读审计，不擅自改代码。
- 如果用户要求实现，先更新需求账本和对应规则文字，再改代码。

## 永远不能跳过的护栏

- 日线 MACD 是当前研究触发门票；改变触发器意味着重建事件池，必须另立实验。
- 历史事件冻结当时分数、证据和规则版本；新规则不能静默重写旧数据。
- 技术分、大盘、行业分开保存；未验证因子不能伪装成正式胜率或买入承诺。
- 成功、失败、负结果、样本不足和中断实验都永久保留。
- 排行榜是唯一权威顺序，精选机会只是其严格子集。
- 代码完成、本地测试、GitHub 提交、生产部署和线上核验是不同状态，必须如实说明。

## 当前工作的来源

- 自动回测断点：`automation/backtest-state.json`
- 生产交付状态：`automation/production-state.json` 与 `public/update-status.json`
- 当前因子库：`public/factor-registry.json`
- 实验状态：`research/generated/experiment-catalog.json`、`research/experiments.jsonl`、`research/experiment-events.jsonl`
- 真实历史机会：`research/production-history/opportunity-ledger.json` 与 `research/production-history/signal-history.json`
- 生产网站：<https://sage-vista-parallel.gizmo-allied-0s.workers.dev>

[`CURRENT_STATUS_ZH.md`](CURRENT_STATUS_ZH.md) 是上述机器源的人话快照；若它与机器源不一致，停止改代码，先修复状态生成器。

## 可直接复制到新对话的开场词

> 请接手 Sage Vista。先完整读取仓库根目录 `AGENTS.md`、`docs/NEXT_SESSION_HANDOFF_ZH.md`、`docs/CURRENT_STATUS_ZH.md`、`docs/CODEBASE_MAP_ZH.md` 和 `docs/PROJECT_REQUIREMENTS_MASTER_ZH.md`，再读总手册并用 `docs/rules/README.md` 只定位本次受影响模块。先用人话告诉我生产数据日、回测覆盖与下一断点、当前模型 / 因子版本、待运行实验和本次模块边界。不要依赖旧聊天，不要先改代码；先把我的新要求写入 `docs/CHANGE_REQUESTS_ZH.md`，更新对应规则文字后再实施。保护历史版本、失败实验和现有自动化。每次交付都给我测试、提交、线上验证和生产网站。

实际上，只要新对话直接打开本仓库并提出具体需求，根目录 `AGENTS.md` 会自动提供这些要求；上面的开场词用于人工复核或对话没有正确加载仓库时。
