# 从这里开始：Sage Vista 交接总入口

最后更新：2026-10-13。新的人或新的 AI 先读这一页（约 5 分钟），再按需打开下面列出的现行文档。旧文档开头都标了状态；标"历史"或"已淘汰"的只用来查证据，不用来做决定。

## 1. 这是什么

Sage Vista（SV）是用户（Freddy）的美股研究系统，分两部分：

- **生产**：每天收盘后扫描约 1,500 只美股，生成多因子机会排行，发布到网站 <https://sage.freddyliang.com>，并记录模拟账户。
- **研究实验室**：在冻结的历史数据上做预先登记的实验，回答"这样做是否真的比随机选股、比 SPY 好"。

## 2. 现在的结论（2026-10-13）

| 问题 | 结论 | 证据 |
|---|---|---|
| 账户核心放什么 | **永久组合**（股票、长债、黄金、短债各 25%），1993—2026 年化 7.5%、最大回撤 18%、Sharpe 1.10 | 实验 E0、C1、E8 |
| 旧的 SV 多因子选股能不能用来买股票 | **不能**。四次检验（E1b、E5a、E1c、E7b）都没胜过同规则的随机选股；网站上的机会排行只作观察 | 08 规则"E7b、E8 结论" |
| 买入系统 0.2.0 能不能用 | **不能**。训练与考试未通过：2005—2016 明显差于同日随机股票，7 个改动都没帮上；2017—2025 和随机差不多。止损、目标、分批卖出对随机股票同样有效 | 实验 `lab-buysystem-train-v1`、08 规则 `#buysystem-train` |
| 现在在做 | **只做一个固定形态：用户的周线三角形**（三推以上下降压力线、两个以上的底、后一个底最多低 1%）。只有两种买点：C 底部金叉、B 突破后回踩；不买突破本身、不追高。规则按用户 12 个例子冻结（对上 10 个），登记一次考试：老股票 2005—2016 练习，5,500 只新股票分 4 份各考一次，对同日随机股票和 SPY | 案例账本第十七节、`research/lab/triangle.py`、08 规则 `#triangle-exam` |
| 反向盲评 | 用户认可 10 个里 3 个：机器还没学会用户的眼光，先修定义 | 案例账本第十七节 |
| 模拟账户 | E6 自 2026-10-12 起每天记录（SPY、永久组合、60/40 等，不含 SV 信号） | `research/lab/forward/` |

## 3. 买入系统一句话

**大周期定方向，中周期找位置，日线定时机，每一层都通过才买；止损放在结构下面，止盈看被价格验证过的阻力；宁可出手少。** 0.2.0 的训练与考试没有通过（见第 2 节），不进账户。

| | 月线机会（优先） | 周线机会 |
|---|---|---|
| 过滤 → 方向 → 位置 → 时机 | 无 → 月线 → 周线 → 日线 | 月线不作对 → 周线 → 日线 → 日线 |
| 20 年信号（交易池内） | 195 个 | 887 个 |

完整规则只维护在 `docs/BUY_SYSTEM_ZH.md`；代码是 `research/lab/buysystem.py`（一套引擎）；测试 `tests/test_buysystem.py`。

## 4. 现行文档（只看这些）

| 想知道 | 看哪份 |
|---|---|
| 当前机器状态（网站版本、数据日期、实验数） | `docs/CURRENT_STATUS_ZH.md`（程序生成，不要手改） |
| 买入系统规则 | `docs/BUY_SYSTEM_ZH.md` |
| 用户逐个复盘过的案例与判断 | `docs/CASE_REVIEW_LEDGER_ZH.md`（第十六节是最新的盲评与买入系统） |
| 每次改动的来龙去脉 | `docs/CHANGE_REQUESTS_ZH.md`（只读最新几条，`CR-2026-10-1x`） |
| 实验怎样登记、结论是什么 | `docs/rules/08_BACKTEST_AND_EXPERIMENTS.md`；机器账本 `research/experiments.jsonl` |
| 止损、仓位、风险 | `docs/rules/09_RISK_AND_EXECUTION.md` |
| 数据与每日扫描 | `docs/rules/02_DATA_AND_SCAN.md`、`docs/DAILY_EOD_AUTOMATION_ZH.md` |
| 生产系统怎么协同、各模块规则在哪 | `docs/SAGE_VISTA_RULEBOOK_ZH.md`、`docs/rules/README.md` |
| 代码在哪 | `docs/CODEBASE_MAP_ZH.md`；研究实验室见第 7 节 |
| 执行规矩 | `docs/rules/01_GOVERNANCE.md` 和第 6 节 |

## 5. 已淘汰或只作历史的东西（不要拿来做决定）

| 东西 | 状态 | 被什么取代 |
|---|---|---|
| 旧代码里的交易规则（支撑下 5%、单只 10%、2R 止盈、40 天） | **已淘汰**，从来不是用户的规则 | 09 规则 E7b 研究口径、`BUY_SYSTEM_ZH.md` |
| 把 SV 多因子分数当买入依据（分数越高越好） | **已淘汰**（E5a：高分更差） | 买入系统；多因子只作零件、排序与风控 |
| 实验 E1（随机池有缺陷）、E7（用了旧规则） | **作废**，结果不引用 | E1b、E7b |
| 买入系统 0.1.0 的"两层"做法（限价单直接成交）、INCY 演练 | **已被 0.2.0 取代** | `BUY_SYSTEM_ZH.md` 0.2.0、JLL 演练 |
| `docs/PERSONAL_TRADING_SYSTEM_ZH.md`（日线"我最喜欢形态"V3） | 网站上仍作日线形态观察；**不再作买入依据**；日线"小带大"暂缓 | 买入系统 |
| `docs/PROJECT_REQUIREMENTS_MASTER_ZH.md` | 历史需求草稿 | 需求账本、各规则文件 |
| `docs/MODULE_REFACTOR_PLAN_ZH.md`、`docs/M01—M11_*_DESIGN_ZH.md`、`docs/SYSTEM_ARCHITECTURE_ZH.md` | 生产模块重构的工程设计记录 | 只在改对应生产模块时查 |
| `docs/FACTOR_ARCHITECTURE.md`、`docs/LONG_HISTORY_CONCLUSIONS_ZH.md`、`docs/PULLBACK_FACTOR_RESEARCH_ZH.md` | 历史因子审计与研究（结论：31 个附加因子没有一个通过验证） | 研究实验室结论 |
| `docs/REPOSITORY_AUDIT_ZH.md`、`docs/LEGACY_SIGNAL_RECOVERY_AUDIT_ZH.md`、`docs/EOD_WEBSITE_RECOVERY_MINIMAL_CARD_ZH.md` | 一次性审计和应急记录 | — |
| `docs/NEXT_SESSION_HANDOFF_ZH.md`、`docs/CHANGE_WORKFLOW_ZH.md` | 旧入口，只剩指向本页和治理规则的链接 | 本页 |

## 6. 必须遵守的工作规矩

1. **不在每日更新时段推送或合并 main**：UTC 23:30—04:30（墨尔本 10:30—15:30），也不在 daily-eod 运行时合并。合并命令里先查时间。
2. **实验先登记再跑**：规格写在 `research/lab/queue/*.json`，登记写进 `research/experiments.jsonl`、`research/experiment-events.jsonl`、`research/experiment-summaries.zh.json`；成功标准事先写好、跑完不改；失败结果也保留。
3. **生产不能自己改**：评分、排名、交易规则、数据生产、`public/` 数据、网站，没有用户明确批准不动。
4. **每次改动的收尾**：改 08 规则版本和变更记录 → 写需求账本条目（CR）→ 运行 `python3 -m services.scanner.experiment_catalog` 和 `python3 -m services.scanner.project_status` → 跑全部测试 `python3 -m unittest discover -s tests -p 'test_*.py'` → 开 PR → 检查通过后合并。
5. **实验在后台跑**：GitHub Actions `research-lab.yml`（UTC 04:45、08:15 定时，或手动触发）；本地只做工程检查，不看比较结果。
6. **每次实验跑完**：写中文报告，更新进度页 <https://claude.ai/artifact/DAvLFAzoaQt7vfLsUaWC7V>（先读再改）。
7. **设计实验前先列出用户已定的规则**，说明这次是遵守还是有意挑战哪一条。
8. **和用户沟通**：简体中文，结论在前，短句，小表格，术语要解释。用户常用语音输入，字可能错，按意思理解。

## 7. 研究实验室代码地图（`research/lab/`）

| 文件 | 做什么 |
|---|---|
| `run_queue.py` | 读取 `queue/` 里预先登记的实验，逐个运行，结果写进 `results/<实验>/` 并更新成绩板 |
| `datasets.py` | 冻结数据集（存在 GitHub release `research-datasets`，按 SHA256 校验）；`universe-1985-v1` 是 1,228 只股票从 1985 年起的复权日线 |
| `buysystem.py` | **买入系统 0.2.0**：月线机会和周线机会的扫描、依据卡、交易模拟 |
| `buytrain.py` | 买入系统的训练与考试：全市场扫描、练习段比较改动、考试段一次、同日随机对照 |
| `v3weekly.py` | 周线 V3 标注期的辅助函数（转折点、吞噬、MACD），被 `triangle.py` 复用 |
| `triangle.py` | 周线三角形 1.0（冻结）：C 底部金叉、B 突破后回踩两种买点 |
| `answer_key.py` | 用用户的标准答案（`cases/triangle-answer-key-v1.json`）给形态打分 |
| `triangle_exam.py` | 周线三角形的练习与一次考试（4 份新股票，各对 200 个随机账户） |
| `screen.py` | 扩大股票池：找出从没见过的美股（含退市），分份 |
| `exit_rules.py` | 通用交易模拟（止损、目标、跟踪、趋势卖出、时间卖出） |
| `account.py` | 10 万美元账户逐日模拟（仓位、风险上限） |
| `selection.py`、`levels.py`、`timeframe.py` | 与随机选股对比的实验（E1b、E7b 等） |
| `structure.py` | 结构检查：深跌没筑底、宽幅箱体、卖压、多重顶、向下跳空 |
| `allocation.py`、`forward.py` | 成熟组合与模拟账户 |
| `coverage.py`、`metrics.py` | 数据覆盖统计、统一指标与通过判定 |

## 8. 给用户看的页面

| 页面 | 地址 |
|---|---|
| 研究进度（每次实验后更新） | <https://claude.ai/artifact/DAvLFAzoaQt7vfLsUaWC7V> |
| 需要用户核对的案例（买入系统 0.2.0） | <https://claude.ai/artifact/YJMwf3jKVEzmZYbiwRUehf> |
| 周线 V3 标注（用户选“做/不做”，自动保存） | <https://claude.ai/artifact/YNNtUwXBuRvAehRDvK2KD8> |
| 反向盲评、结果、为什么输给随机 | <https://claude.ai/artifact/LsWT2mAZmV1HVS8Byw5vo5> |
| 交易演练：JLL 2009（三层规则） | <https://claude.ai/artifact/J92pfNvWT3zgyEWtVmqF2z> |
| 交易演练：INCY 2020（旧两层规则，已被取代） | <https://claude.ai/artifact/4AsyQr7XtaY4tY64LkK39W> |
| 盲评打分页（2026-10-11，12 个案例） | <https://claude.ai/artifact/61aLnbsym85tvoupxPHZXm> |

## 9. 新对话怎样快速接上

1. 读本页；
2. 看 `docs/CURRENT_STATUS_ZH.md` 和 `git log` 最近几条；
3. 读 `docs/CHANGE_REQUESTS_ZH.md` 最新的 2—3 条 CR；
4. 做买入系统相关的事，再读 `docs/BUY_SYSTEM_ZH.md`；
5. 有疑问先问用户，不要凭旧聊天记忆做决定。
