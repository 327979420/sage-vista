# 模块索引

这是按需查找表，不是必读清单。先选择本次受影响模块；具体业务规则从 [总手册模块地图](../SAGE_VISTA_RULEBOOK_ZH.md#3-模块地图) 打开，代码位置见下表。跨模块时只读取实际联动部分。

执行流程仅见 [01｜执行与文档维护](01_GOVERNANCE.md)，本页不重复规定审批或验证步骤。表中路径用于定位，不证明当前生产状态。

## 模块接手表

| 模块 | 主要实现入口 | 主要状态 / 产物 | 首要测试 |
|---|---|---|---|
| 01 治理 | `AGENTS.md`、`docs/*.md` | `CURRENT_STATUS_ZH.md`、`CHANGE_REQUESTS_ZH.md` | `test_rulebook_contract.py`、`test_project_status.py` |
| 02 数据扫描 | `daily_tracker_update.py`、`eodhd.py`、`factor_snapshot.py` | `update-status.json`、`daily-factor-snapshot.json` | `test_eodhd.py`、`test_factor_snapshot.py` |
| 03 因子模型 | `factor_registry.py`、`factor_detectors.py`；研究候选另见`research/factor_lab/` | `factor-registry.json`、`research/factor-candidates-v2.json` | `test_factor_snapshot.py`、`test_factor_scoring.py`、`test_factor_strategy_lab_v2.py` |
| 04 评分 | `factor_scoring.py`、`unified_v2_scan.py` | `unified-v2-rankings.json` | `test_factor_scoring.py`、`test_unified_v2_scan.py` |
| 05 大盘 | `market_etf_watch.py` | `market-etf-watch.json` | `test_market_etf_watch.py` |
| 06 行业 | `industry_radar.py`、`industry_membership.py` | `industry-radar.json` | `test_industry_radar.py` |
| 07 排行追踪 | `unified_v2_scan.py`、`opportunity_ledger.py`、`signal_history.py` | `unified-v2-rankings.json`、`opportunity-ledger.json`、`signal-history.json` | `test_opportunity_ledger.py`、`test_signal_history.py` |
| 08 回测实验 | `research/backtest/`、`experiment_catalog.py`、`backtest_progress.py` | `research/experiments.jsonl`、`backtest-state.json`、`research/generated/experiment-catalog.json` | `test_backtest_progress.py`、`test_experiment_catalog.py` |
| 09 风险执行 | `support_risk.py`、研究回测脚本 | 风险 / 退出实验产物 | `test_support_risk.py`、对应回测测试 |
| 10 UI 运维 | `app/`、`.github/workflows/`、`verify_live_deployment.py` | 生产网站、`production-state.json` | `test_ui_v2_contract.py`、`rendered-html.test.mjs` |
| 11 策略宝典 | 已验证实验引用 | `11_VALIDATED_PLAYBOOK.md` | 规则契约测试 |
| 12 交易红线 | 证据与禁区条目 | `12_HARD_RULES.md` | 规则契约测试 |
