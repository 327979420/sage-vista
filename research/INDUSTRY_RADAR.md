# Industry Radar V1 — Architecture and Theme Universe Manual

Last reviewed: 2026-08-29. The Chinese universe and study entry point is `docs/INDUSTRY_RESEARCH_UNIVERSE_ZH.md`; this document retains the detailed architecture and source audit. `research/EXPERIMENTS.md` remains the authoritative registry for completed experiments; Industry Radar has not yet produced a validated alpha result.

## 1. Business purpose and boundary

Industry Radar supplies stable, explainable industry/theme context for human decisions. It is parallel to, not upstream of, Technical Tracker:

```text
Technical Tracker ──────┐
                        ├─> Dashboard / human decision
Industry Radar ─────────┘
```

Radar must not filter Tracker stocks or modify Technical Score, Ranking Score, ranking order, production strategy, Discord behavior, or validated research conclusions. A Radar state is context, not a buy/sell signal and not validated alpha.

## 2. V1 model

V1 deliberately uses adjusted prices only; it does not use volume, MACD, RSI, fundamentals, news, options, or machine learning.

- **Strength:** equal-weight constituent 20D and 60D returns minus SPY returns; cross-theme percentile uses the mean of 20D/60D relative strength.
- **Breadth:** percent above SMA50, percent with positive 20D return, and valid constituent count. Metrics are withheld below five valid members.
- **Direction:** 5D excess return versus SPY and change in percent above SMA50 versus ten trading observations earlier.

Thresholds live only in `industry_radar.CONFIG`:

- **Pullback Watch** (precedence first): strength percentile at least 70, breadth at least 60%, and either 5D relative strength below zero or breadth change at most -10 percentage points.
- **Leadership:** strength percentile at least 70, breadth at least 60%, and not weakening under the Pullback rule.
- **Recovery:** below the Leadership percentile, 5D relative strength positive, and breadth change at least +5 percentage points.
- **Neutral:** every sufficiently populated theme not matching the above.
- **Unavailable:** fewer than five valid constituents or no comparable strength percentile.

These are research parameters. Do not optimize them against forward returns during membership/universe work.

## 3. Data and membership rules

No paid subscription, new login, EODHD Fundamentals, or AI-guessed membership is allowed.

1. Prices use the existing EODHD adjusted-price loader and `work/eodhd-cache`; do not build a second price layer.
2. Membership priority is: official ETF provider holdings; documented public dataset; SEC/company-disclosure evidence.
3. Nasdaq public classification is a current `Sector → Industry` snapshot only. FinanceDatabase is a useful manually curated fallback/cross-check, not historical truth and not an authoritative theme source.
4. Every snapshot records source URL/date and `effective_from`. Never overwrite a historical snapshot. A same-day correction increments `snapshot_revision` and creates a new file.
5. For `as_of=D`, use only price rows dated at or before D and only membership/classification effective at or before D. Before the first membership snapshot, report `historical_membership_safe=false`.
6. Never apply today's ETF constituents to an earlier backtest. This protects against future leakage and false historical membership, but does not eliminate survivorship bias before genuine historical snapshots accumulate.
7. Preserve official foreign-market identifiers. If the existing `.US` EODHD path cannot resolve one, record it as unavailable; never guess a mapping.

## 4. Current architecture

- `data/themes/theme-registry.json`: data-driven theme identity and membership-source configuration.
- `data/themes/snapshots/*.json`: immutable dated membership versions.
- `data/industry/*.json`: dated current-classification snapshots.
- `services/scanner/industry_membership.py`: generic snapshot writer plus small provider adapters. Adapters convert provider holdings to the generic snapshot schema; they must be provider-specific, never theme-specific.
- `services/scanner/industry_radar.py`: provider-agnostic metrics, leakage checks, state mapping, ticker context, and report generation.
- `public/industry-radar.json`: standalone output; never merged into Tracker ranking JSON.
- `app/zh/watch/industry-radar/page.tsx`: standalone presentation.
- `.github/workflows/industry-radar-validation.yml`: manual real-data validation only; no schedule or deployment integration.
- `tests/test_industry_radar.py`: membership, leakage, equal weighting, breadth, state precedence, failure handling, and Tracker-isolation contracts.

Production consolidation（2026-08-27）：Industry Radar 仍有独立手动验证入口，但 daily EOD 现会使用同一个 dated membership snapshot 生成 `public/industry-radar.json`，并与 Tracker、27-factor snapshot、Rare Radar 一起提交、部署和执行 live date/leakage verification。它仍不进入 Tracker ranking 或 Discord threshold。

### Adding a theme

1. Select a defensible source and record a registry entry with `membership_source.provider` and provider fund/source identifier.
2. If the provider already has an adapter, add no Python branch. Otherwise add one provider adapter and parser tests.
3. Generate a new dated snapshot; never edit an old membership version.
4. Audit US-tradeable, unavailable, and valid-history counts.
5. Compute pairwise overlap and challenge redundant themes.
6. Run Radar tests, full Python tests, production build, and rendered tests. Do not touch Tracker, Discord, or the daily workflow.

## 5. Architecture hygiene audit

Before cleanup the architecture was **ACCEPTABLE**: Radar already reused `adjusted_rows`, EOD cache, and `technical.py` where appropriate, and its engine was theme-agnostic. The expansion risk was a Python `GLOBAL_X` theme table inside membership ingestion.

Cleanup moved theme/fund configuration into the registry and introduced a small provider-adapter map. The following duplication is intentionally retained:

- Radar as-of trimming and SPY/date alignment are point-in-time safety logic, not generic price formatting.
- `sector_watch.py` and `market_etf_watch.py` contain tiny ETF-level return/report helpers for separate products; extracting them now would create cross-product coupling without reducing theme expansion cost.
- `adjusted_rows` remains in `eodhd_factor_pilot.py` because it is the stable existing cache implementation. Rehousing it would widen the change across scanner modules.
- JSON writes remain local because report contracts and failure behavior differ.

**Expansion answer: YES.** Moving from four to roughly 25 configured themes should not grow the core Radar engine. Python should grow only when a genuinely new provider format needs one reusable adapter.

## 6. Theme universe research proposal

Counts below are current published ETF holdings or the latest verified US-resolvable count where available. They are planning figures, not a new membership snapshot. Exact US-tradeable counts must be audited when adapters ingest the same dated source.

| Theme | Category | Primary source | US-tradeable planning count | Overlap risk | Maintenance | Decision |
|---|---|---|---:|---|---|---|
| Semiconductors | Technology | SOXX (iShares) | 30 | High vs AI/Semi Equipment | Low | KEEP |
| Software & Applications | Technology | IGV (iShares) | source audit pending | Medium/high vs Cloud/AI Software | Low | KEEP, next dated snapshot |
| Cybersecurity | Technology | CIBR (First Trust) | ~42 | Low/medium vs Cloud | Medium | KEEP |
| Cloud Computing | Technology | SKYY (First Trust) | ~60 | Medium/high vs AI Infra | Medium | KEEP |
| Robotics & Automation | Technology | BOTZ (Global X) | 23 verified | Medium vs AI Infra | Low | KEEP |
| Quantum Computing | Technology | QTUM (Defiance) | source audit pending | Medium vs Semis | Medium/high | REVIEW |
| AI Infrastructure | Technology | custom, two-source evidence | unresolved | High | High | REVIEW |
| AI Software & Applications | Technology | AIQ/IGV/SKYY candidates + revenue evidence | unresolved | High vs Software/Cloud | High | REVIEW |
| Memory & Data Storage | Technology | SOXX/classification candidates + revenue evidence | unresolved | High vs Semiconductors | High | REVIEW |
| Semiconductor Equipment | Technology | SOXX/SMH subset + revenue evidence | unresolved | Very high vs Semis | High | REVIEW |
| Data Center Power | Technology/Industrial | GRID/PAVE + revenue evidence | unresolved | High vs AI/Grid | High | REVIEW |
| Uranium | Energy/Materials | URA (Global X) | 12 verified | High vs Nuclear | Low | KEEP |
| Nuclear | Energy | NLR (VanEck) | source audit pending | High vs Uranium | Medium | REVIEW |
| Copper Miners | Materials | COPX (Global X) | 4 verified | Medium vs Critical Minerals | Low | KEEP, data-quality warning |
| Clean Energy | Energy | ICLN (iShares) | broad basket | High vs Solar/Grid | Low | KEEP |
| Solar | Energy | TAN (Invesco) | focused basket | High vs Clean Energy | Medium | KEEP |
| Oil & Gas / Energy | Energy | XLE (State Street) | focused US basket | Low | Low | KEEP |
| Critical Minerals | Materials | REMX (VanEck) | focused global basket | High vs Battery/Copper | Medium | KEEP |
| Battery Materials | Materials | LIT (Global X) | 41 published; US subset TBD | High vs EV/Critical | Low | KEEP |
| Defense & Aerospace | Industrials | XAR (State Street) | 47 | Medium vs Space | Low | KEEP |
| Infrastructure | Industrials | PAVE (Global X) | 100 | Medium vs Grid | Low | KEEP |
| Grid Modernization | Industrials | GRID (First Trust) | global basket; US subset TBD | High vs Data Center Power | Medium | KEEP |
| Space | Industrials | UFO (Procure) | source audit pending | Medium vs Defense | High | REVIEW |
| Fintech | Financial | FINX (Global X) | 55 verified | Medium vs Digital Assets | Low | KEEP |
| Digital Assets / Crypto Infrastructure | Financial/Technology | BKCH (Global X) | 34 published; US subset TBD | Medium vs Fintech | Low | KEEP |
| Biotechnology | Healthcare | XBI (State Street) | 155 | Low vs Medical Devices | Low | KEEP |
| Medical Devices | Healthcare | IHI (iShares) | 46 | Low | Low | KEEP |
| EV / Battery | Consumer/Industrial | DRIV (Global X) | 74 published; US subset TBD | High vs Battery/Semis | Low | KEEP |
| Water Infrastructure | Industrials/Utilities | PHO (Invesco) | US-listed basket; count TBD | Medium vs Infrastructure | Medium | KEEP |

The configured automatic-source universe is now the original 20 KEEP rows plus Software & Applications, for 21 themes. The five custom themes remain REVIEW/manual until evidence and overlap checks pass. This is a source-ready proposal, not authorization to backfill memberships. No candidate is rejected permanently yet; undifferentiated “Healthcare Innovation,” broad “Renewables,” and combined “AI & Robotics” aliases should be rejected if they merely duplicate a KEEP basket.

### Public repository assessment

- [thematic-equity-pipeline](https://github.com/thibault2710/thematic-equity-pipeline) is a useful methodology reference for SEC 10-K keyword/revenue evidence and custom themes such as AI infrastructure, nuclear, semiconductors, and grid modernization. It must not be copied as authoritative membership or used to infer historical membership.
- [FinanceDatabase](https://github.com/JerBouma/FinanceDatabase) supplies free sector/industry/exchange fields and primary-listing controls. Its classifications are manually curated and only loosely approximate GICS, so use it as a traditional-industry fallback/cross-check.
- [us-stocks-dataset](https://github.com/scottcovert/us-stocks-dataset) has broad US coverage and convenient industry labels, but no releases and weak provenance/version history for point-in-time research. Use for discovery/QA only, not membership authority.
- [themetracker](https://github.com/khorjayyang/themetracker) is useful for Theme → ETF taxonomy discovery, not authoritative constituents.

## 7. KEEP source map

All sources are free/no-login for public holdings downloads at the time of review; none provides a complete, trustworthy historical membership series. Store snapshots prospectively.

| Theme | Primary | Fallback | Mode | Login/Paid | Historical membership | Stability |
|---|---|---|---|---|---|---|
| Semiconductors | SOXX/iShares | SMH/VanEck | Auto | No/No | Limited dates only | High |
| Software & Applications | IGV/iShares | XSW/State Street | Auto | No/No | No complete series | High |
| Cybersecurity | CIBR/First Trust | HACK provider holdings | Auto | No/No | No complete series | High |
| Cloud Computing | SKYY/First Trust | CLOU/Global X | Auto | No/No | No complete series | High |
| Robotics & Automation | BOTZ/Global X | ROBO official holdings | Auto | No/No | No complete series | High |
| Uranium | URA/Global X | NLR/VanEck | Auto | No/No | No complete series | High |
| Copper Miners | COPX/Global X | Nasdaq industry QA | Auto | No/No | No complete series | High; low US count |
| Clean Energy | ICLN/iShares | QCLN/First Trust | Auto | No/No | Limited dates only | High |
| Solar | TAN/Invesco | Nasdaq industry QA | Auto | No/No | No complete series | High |
| Oil & Gas / Energy | XLE/State Street | Nasdaq Energy classification | Auto | No/No | No complete series | High |
| Critical Minerals | REMX/VanEck | LIT/COPX overlap evidence | Auto | No/No | No complete series | Medium |
| Battery Materials | LIT/Global X | REMX + company evidence | Auto | No/No | No complete series | High |
| Defense & Aerospace | XAR/State Street | ITA/iShares | Auto | No/No | No complete series | High |
| Infrastructure | PAVE/Global X | IFRA/iShares | Auto | No/No | No complete series | High |
| Grid Modernization | GRID/First Trust | PAVE + SEC evidence | Auto | No/No | No complete series | High |
| Fintech | FINX/Global X | Nasdaq industry QA | Auto | No/No | No complete series | High |
| Digital Assets | BKCH/Global X | SEC business-description evidence | Auto | No/No | No complete series | Medium/high turnover |
| Biotechnology | XBI/State Street | IBB/iShares | Auto | No/No | No complete series | High |
| Medical Devices | IHI/iShares | Nasdaq industry QA | Auto | No/No | Limited dates only | High |
| EV / Battery | DRIV/Global X | LIT overlap evidence | Auto | No/No | No complete series | Medium |
| Water Infrastructure | PHO/Invesco | FIW/First Trust | Auto | No/No | No complete series | High |

## 8. Custom/unresolved themes

- **AI Infrastructure:** semi-automatic, manually reviewed. Candidate pool is the union of official AI/semiconductor/cloud/grid ETFs; include only companies with a documented role in compute, networking, data-center systems, or enabling power and a second source such as 10-K segment/revenue evidence. Review quarterly. Record evidence per member and create a new effective-dated version.
- **AI Software & Applications:** manually reviewed. Use official AIQ, IGV, and SKYY holdings only as a candidate union; require documented software/application revenue or product evidence. Popularity, price performance, or an AI marketing claim is not membership evidence.
- **Memory & Data Storage:** manually reviewed. Start from SOXX and current industry classifications, then require documented primary exposure to DRAM, NAND, SSD, HDD, controllers, enterprise storage, or closely related memory/storage systems. Keep it separate from the broad semiconductor basket.
- **Semiconductor Equipment:** derive candidates from SOXX/SMH, then include only companies whose documented primary business is wafer-fab, process, inspection/metrology, test, or semiconductor-design equipment/software. This is a subset theme, so publish only if its overlap and differentiated behavior justify coexistence with Semiconductors.
- **Data Center Power:** candidate union from GRID/PAVE and official data-center/digital-infrastructure ETFs where available; require documented revenue exposure to switchgear, UPS, cooling, power distribution, generation, or grid connection for data centers. Do not include a company merely because AI demand may benefit it.

All five remain `manual_curated_required`. Required fields are inclusion rule, evidence URLs/date, reviewer decision, review cadence (quarterly), `effective_from`, and immutable version. SEC/NLP output can propose candidates but never auto-admit them.

## 9. Overlap policy and current audit

A ticker may belong to multiple themes. Report both shared count and:

```text
overlap_pct = shared_members / min(theme_A_members, theme_B_members)
```

Also retain Jaccard overlap for diagnostics. At 50% min-set overlap, require an explicit differentiation note; at 75%, default to REVIEW one theme unless economic roles clearly differ.

Current snapshot (`themes-2026-08-25-v2`):

| Theme | Members | Highest-overlap theme | Shared | Overlap | Jaccard |
|---|---:|---|---:|---:|---:|
| Fintech | 74 | Robotics & AI / Uranium / Copper | 0 | 0% | 0% |
| Robotics & AI | 61 | Fintech / Uranium / Copper | 0 | 0% | 0% |
| Uranium | 57 | Copper Miners | 1 (`BHP AU`) | 2.5% | 1.0% |
| Copper Miners | 40 | Uranium | 1 (`BHP AU`) | 2.5% | 1.0% |

Expected high-risk pairs for the expansion are Nuclear/Uranium, AI Infrastructure/Semiconductors, AI Infrastructure/Data Center Power, Cloud/AI Infrastructure, Robotics/AI Infrastructure, Clean Energy/Solar, and Battery/EV. Their exact overlap must be computed from one same-date candidate snapshot before approval.

## 10. Protected modules, limitations, and next research

Do not casually modify `resonance_tracker.py`, `daily_tracker_update.py`, Tracker UI/ranking JSON, factor/scoring registries, Discord modules/workflows, `.github/workflows/daily-eod.yml`, or production deployment/strategy.

Known limitations:

- Official holdings are current snapshots, not historical truth; long historical backtests remain unsafe until snapshots accumulate.
- Foreign identifiers do not map through the existing `.US` EODHD helper; the current verified valid counts can be far below published holdings.
- Cross-theme percentiles are unstable with only four themes and will change mechanically as the universe expands.
- ETF taxonomies can be broad, overlap heavily, or change methodology; equal-weight Radar calculations intentionally ignore ETF weights.
- Public provider URLs and file formats can change, so adapter fixtures and fail-closed tests are required.
- Nasdaq/FinanceDatabase traditional industry labels complement themes but do not replace them.

## 11. 2026-08-26 same-date candidate snapshot

`themes-2026-08-26` 是不可覆盖的历史快照，只包含当日已配置的20个ETF主题；当时另有AI Infrastructure、Semiconductor Equipment、Data Center Power三项为 `manual_curated_required`。注册表v3后来增加IGV综合软件，并补记AI Software & Applications、Memory & Data Storage；这些新增项只能从后续新快照开始，不能倒写本快照。

- Provider adapters：Global X、iShares、First Trust、State Street、Invesco、VanEck。Adapter 只负责将 provider 格式转为 generic snapshot；registry 配置 fund/URL，core Radar 无 theme branch。
- 成功来源 11/20，合计 698 个原始 holdings。Global X 与 State Street 在该日成功；iShares、First Trust、Invesco、VanEck 当前响应/格式未通过 parser contract，9 个 Theme 明确记录 `source_status=unavailable` 和零成员，而不是猜数据。
- US-tradeable identifier audit：Robotics 23/61、Uranium 12/57、Copper 4/40、XLE 22/22、Battery 7/41、XAR 47/47、PAVE 100/100、Fintech 55/74、Digital Assets 26/33、XBI 147/149、EV 39/74。外国或未映射 identifier 原样保留。
- Overlap 使用 `shared/min(size)` 与 Jaccard。当前没有达到 75% near-duplicate；Fintech/Digital Assets 共享 16，min-set overlap 48.48%；Battery/EV 共享 14，34.15%。预定高风险 pair 中，Clean Energy/Solar、Cloud/AI、AI/Semis 等因 source unavailable 或 custom unresolved 尚不能下结论。
- 这只是 membership/data-quality candidate，不是 alpha experiment，因此没有更新 `research/EXPERIMENTS.md`。

下一步：修复/确认四类当前 unavailable 官方下载格式，生成新 revision 而不覆盖本 snapshot；用 GitHub EODHD production run 填充每 Theme valid member count 与 state。只有 membership quality 被接受后，才可另行预注册历史验证。

## 12. 2026-08-26 provider repair revision

`themes-2026-08-26-v2` 是新的 immutable correction，不覆盖 base snapshot。Provider-level 修复如下：

- iShares：从官方产品页发现 `latest-holdings.csv`，并修正 IHI 的官方 product ID；SOXX 33、ICLN 130、IHI 50 raw holdings。
- First Trust：只解析 Holdings 表的七列 security rows，不把导航文字当 ticker；CIBR 42、SKYY 63、GRID 119 raw holdings，外国标识原样保留。
- Invesco：从官方产品页读取公开 CUSIP，再调用官网公开 holdings API；TAN 43、PHO 42 raw holdings。
- VanEck：官方 REMX 页面可见 holdings，但下载入口在无登录 runner 中发生循环重定向；保持 `source_status=unavailable`、`parse_status=source_error`，不复制网页搜索结果、不猜 membership。

每个 Theme snapshot 现在明确保存 `source_status`、`parse_status`、`holdings_count`、categorical `error_reason`、raw/US-resolvable/foreign-or-unmapped counts。Radar 输出再加入 valid price-history count。Parser/transport failure 必须是 `Unavailable / source_error`，不能表现为正常的零成员 Theme。

本 revision 仍是 data coverage / quality work，不是 alpha experiment；没有修改 V1 thresholds，也没有向 `research/EXPERIMENTS.md` 添加结论。下一步只能先用 production EODHD run 验证新增 baskets 的 valid counts 与状态，再预注册 Industry-context forward comparison。

## 13. 2026-08-27 targeted source audit

### Semiconductors — KEEP / supported

Primary membership remains the official [iShares SOXX holdings](https://www.ishares.com/us/products/239705/ishares-semiconductor-etf). The official page describes a US semiconductor value-chain index, publishes a holdings download, and reports about 30 portfolio holdings. The immutable `themes-2026-08-26-v2` snapshot contains 33 raw identifiers (including cash/future-like rows retained for audit), 33 US-resolvable identifiers by the existing conservative syntax check, and the production EODHD run produced 30 valid price histories. The resulting 2026-08-26 Radar state is **Neutral** (20D RS +6.4%, 60D RS −14.1%, 10% above SMA50, breadth change −23.3%). No theme-specific scraper, mapping guess, threshold, or ranking change was required. SMH remains fallback/cross-check evidence only.

### AI Infrastructure — MANUAL_CURATED_REQUIRED

The official [iShares AINF holdings](https://www.ishares.com/uk/professionals/en/products/338777/ishares-ai-infrastructure-ucits-etf) are useful candidate evidence, but not an automatic Sage Vista membership source. The basket is UCITS/global, includes foreign primary listings such as Taiwan `2330`, and mixes infrastructure enablers with broad platforms/software such as PLTR, MSFT, PANW, AMZN and AAPL. [Global X AIQ](https://www.globalxetfs.com/funds/aiq) is explicitly a broad Artificial Intelligence & Technology ETF and is only secondary cross-check evidence. Neither source alone defines the narrower economic exposure required by Sage Vista.

Decision: **MANUAL_CURATED_REQUIRED**. Do not add `membership_source` or publish the Theme until a separate task approves an exact inclusion rule, second-source company evidence, review cadence, overlap audit, and dated immutable membership. Semiconductor Equipment also remains unresolved; this audit did not guess a production subset.

This was a source/data-quality audit, not an alpha experiment. `research/EXPERIMENTS.md` and V1 thresholds remain unchanged.
