# ELV 行情版本修复核验

冻结版本：`sha256:c287c7b91604d5881e04e5929cf55b848550febd17603284b7d45eed96220a7a`

| Ticker | Price difference | Signal affected | Support affected | Prior-high affected | Trade affected | P&L impact | Decision |
|---|---|---|---|---|---|---|---|
| ANF | False | retained_not_revalidated | previous_audit_equal | not_used_by_this_account | False | 0.0 | diagnostic_only |
| AR | False | retained_not_revalidated | previous_audit_equal | not_used_by_this_account | False | 0.0 | diagnostic_only |
| BMRN | False | retained_not_revalidated | previous_audit_equal | not_used_by_this_account | False | 0.0 | diagnostic_only |
| CNC | False | retained_not_revalidated | previous_audit_equal | not_used_by_this_account | False | 0 | diagnostic_only |
| COO | False | retained_not_revalidated | previous_audit_equal | not_used_by_this_account | False | 0.0 | diagnostic_only |
| DNLI | False | retained_not_revalidated | previous_audit_equal | not_used_by_this_account | False | 0.0 | diagnostic_only |
| DOC | False | retained_not_revalidated | previous_audit_equal | not_used_by_this_account | False | 0 | diagnostic_only |
| ELV | True | False | True | not_used_by_this_account | True | -40.862581514998965 | diagnostic_only |
| GKOS | False | retained_not_revalidated | previous_audit_equal | not_used_by_this_account | False | 0 | diagnostic_only |
| MRNA | False | retained_not_revalidated | previous_audit_equal | not_used_by_this_account | False | 0 | diagnostic_only |
| MXL | False | retained_not_revalidated | previous_audit_equal | not_used_by_this_account | False | 0.0 | diagnostic_only |
| NVAX | False | retained_not_revalidated | previous_audit_equal | not_used_by_this_account | False | 0.0 | diagnostic_only |
| PNFP | False | retained_not_revalidated | previous_audit_equal | not_used_by_this_account | False | 0.0 | diagnostic_only |
| REGN | False | retained_not_revalidated | previous_audit_equal | not_used_by_this_account | False | 0.0 | diagnostic_only |
| SBUX | False | retained_not_revalidated | previous_audit_equal | not_used_by_this_account | False | 0.0 | diagnostic_only |
| SGML | False | retained_not_revalidated | previous_audit_equal | not_used_by_this_account | False | 0.0 | diagnostic_only |
| VCEL | False | retained_not_revalidated | previous_audit_equal | not_used_by_this_account | False | 0 | diagnostic_only |
| WEX | False | retained_not_revalidated | previous_audit_equal | not_used_by_this_account | False | 0.0 | diagnostic_only |

ELV资格：True；原日期 2026-02-18，重算首次日期 2026-02-18。
分数：33.8542 → 33.8542；原候选内排名：2 → 2。
账户期末：混合版本 102034.82 → 修复诊断 101993.96。

尚不能称正式基准：另17只旧信号缺少完整历史行情版本证明。本次仅重算ELV，没有将旧结果伪装成已重验。
