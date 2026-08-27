# 开源行业数据接入

Sage Vista 不复制第三方项目代码，而是通过窄适配器消费并保存可审计快照。

- FinanceDatabase：MIT；用于 `Sector → Industry Group → Industry` 基础分类。每次同步记录日期、来源文件和未匹配代码；当前分类不得回填为历史事实。
- OpenBB：AGPL-3.0；保持可选、隔离依赖，仅通过公开 Python API 获取 ETF holdings 与 SEC N-PORT disclosure。Sage Vista 不复制 OpenBB 源码。
- ETF 官方持仓：继续作为主题成员关系的首选来源。FinanceDatabase 的公司分类不能替代主题 ETF 持仓，OpenBB/SEC 历史披露用于补充有日期的成员证据。

回测只接受 `effective_from <= signal_date` 的快照。没有当时快照就是 `UNAVAILABLE`，不能用当前分类倒算。

`Open Source Industry Snapshot` 每周锁定 FinanceDatabase 的准确 Git commit，为当前跟踪范围保存新快照。OpenBB N-PORT 只在历史披露研究任务中调用，不成为每日生产任务的重型依赖。
