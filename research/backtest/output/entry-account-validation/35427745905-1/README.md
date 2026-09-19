# 月线等待确认：账户验证

- 先读[一页结论](结论.md)，再看[完整指标](完整报表.md)与[月线逐笔](月线逐笔.csv)。
- **最终判定以 decision.json 为准：KEEP AS CHALLENGER / NEED MORE DATA。**
- manifest.json及其列出的文件是原云端计算证据，保留原字节；其中PENDING_REVIEW只表示计算器当时尚未作研究判定，不是运行未完成。最终人工审阅结果另存decision.json。
- comparison.json.gz保存候选、A/B订单、同源绑定、指标及归因；A/B-book.json.gz保存两本完整逐日账户。
- monthly-lifecycle.json按真实账户结果记录71已平仓、27订单拒绝、2结构失效；没有把出现确认当作已经成交。
- 本次为977个保存机会、同一历史版本的限定A/B；不替换18股V0，不代表完整历史市场。原始行情只读复用observation-history-v1-34766761296-1缓存，690文件hash见price-manifest.json。
- 可复核入口：research/backtest/entry_account_report.py读取、验证原始输出并生成详细报表；不会重扫或重跑账户。
