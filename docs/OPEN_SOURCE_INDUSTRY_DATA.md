# 开源行业数据接入

Sage Vista 不复制第三方项目代码，而是通过窄适配器消费并保存可审计快照。

- FinanceDatabase：MIT；用于 `Sector → Industry Group → Industry` 基础分类。每次同步记录日期、来源文件和未匹配代码；当前分类不得回填为历史事实。
- OpenBB：AGPL-3.0；保持可选、隔离依赖，仅通过公开 Python API 获取 ETF holdings 与 SEC N-PORT disclosure。Sage Vista 不复制 OpenBB 源码。
- ETF 官方持仓：继续作为主题成员关系的首选来源。FinanceDatabase 的公司分类不能替代主题 ETF 持仓，OpenBB/SEC 历史披露用于补充有日期的成员证据。

回测只接受 `effective_from <= signal_date` 的快照。没有当时快照就是 `UNAVAILABLE`，不能用当前分类倒算。

`Open Source Industry Snapshot` 每周锁定 FinanceDatabase 的准确 Git commit，为当前跟踪范围保存新快照。OpenBB N-PORT 只在历史披露研究任务中调用，不成为每日生产任务的重型依赖。

## FinanceDatabase固定版本许可留档（2026-09-06）

- 上游项目：[JerBouma/FinanceDatabase](https://github.com/JerBouma/FinanceDatabase)。
- 固定上游提交：`5865ce3b26e6f393dc0600cad1ae02339bd7d52d`；[该提交原始LICENSE](https://github.com/JerBouma/FinanceDatabase/blob/5865ce3b26e6f393dc0600cad1ae02339bd7d52d/LICENSE)。
- 仓库原文副本：[LICENSE](../data/industry/licenses/FinanceDatabase/5865ce3b26e6f393dc0600cad1ae02339bd7d52d/LICENSE)。原样保存MIT许可全文及`Copyright (c) 2023 Jeroen Bouma`，不在原文中追加说明或更改换行。
- 对应bot快照提交：`992042ab1a3a746b735821dea30a50d958651b42`；[该提交的finance-database-2026-09-05.json](https://github.com/327979420/sage-vista/blob/992042ab1a3a746b735821dea30a50d958651b42/data/industry/finance-database-2026-09-05.json)。其`source.ref`为上述固定上游提交，`effective_from`为`2026-09-05`。本许可补档不导入、重写或重新生成该快照。
- 字节核验：从GitHub Contents API按该固定提交取得LICENSE原始字节，保存副本后逐字节相等；共1069字节，Git blob SHA-1为`1a1e8a1a258291d88337e23bd21fcda21db3e100`，SHA-256为`dea317ce7193c52174ebb0def6df1a2f762f75b60e5bc026176fea6cf3ede4ff`。Git blob按`blob <字节数>\0`加正文重新计算，与上游返回身份一致。

## 现有消费者与M06 formal边界

旧生产行业程序[industry_radar.py](../services/scanner/industry_radar.py)的`run`已调用[open_source_industry.py](../services/scanner/open_source_industry.py)的`select_finance_database_snapshot(as_of)`及`classification_by_ticker`，并在行业报告中保存分类及快照信息。因此，不能把这类快照描述成“没有消费者”。

该选择器仅在`effective_from <= as_of`的快照中选择最新日期（同日按文件名排序）；没有符合日期的快照时返回`None`，分类映射为空。存在消费者不证明本次指定bot快照已部署或已被线上某次运行使用。

以上是旧生产行业分类消费路径，**不等于新版M06 formal接入**。新版M06的唯一formal生产层为`services/context/`，要求通过验证的稳定身份、带日期成员证据及`ContextSnapshot 2.x`合同；按日期选择ticker分类快照不能替代这些证据。边界见[M06设计](M06_MARKET_INDUSTRY_CONTEXT_DESIGN_ZH.md)及[行业规则](rules/06_INDUSTRY.md)。本次仅修许可留档与说明，不修改或启用任何生产入口。
