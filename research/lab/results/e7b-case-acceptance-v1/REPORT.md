# e7b-case-acceptance-v1

Case-ledger acceptance check written by the research lab on 2026-10-10. These are seen cases: they check the rules do what the user's reviews say, they are not evidence of returns.

All cases as expected: **yes**

| Case | Signal | Expected | Got | Reason / flags | Stop below close | As expected |
|---|---|---|---|---|---|---|
| MRNA | 2024-04-24 | reject | reject | deep_drawdown | 22.5% | yes |
| BTDR | 2024-03-15 | reject | reject | deep_drawdown | 35.1% | yes |
| TTD | 2025-01-17 | flag | flag | bearish_pressure | 16.9% | yes |
| AEVA | 2026-07-01 | flag | flag | multiple_tops | 57.7% | yes |
| DLTR | 2024-04-01 | flag | flag | gap_supply | 10.7% | yes |
| ADBE | 2023-05-18 | accept | accept | — | 12.5% | yes |
| CGEM | 2024-04-17 | accept | flag | multiple_tops | 32.5% | yes |

## Next step (planned before the run)

If every case gets the expected verdict, E7b runs with these exact rules. If a case does not, the definition is corrected once on these seen cases, the change and its reason are recorded, both specs are updated before E7b runs, and the cases are never counted as evidence of returns.
