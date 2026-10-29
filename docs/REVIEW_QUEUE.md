# 核查队列：Codex 与用户直接工作，Claude 随后复核

本文件记录实际完成的工作，区分“已合并 / 已上线 / 已送达”和“独立核查通过”。
只有 Claude 实际核查并回填结论后，才将核查状态改为“通过”或“退回：原因”；用户批准发布不替代独立核查。
执行规则仍见 [tasks/README.md](../tasks/README.md) 与[治理规则](rules/01_GOVERNANCE.md)。

## 开始工作前

1. 读 [STATUS.md](STATUS.md) 与 [TRIANGLE_HANDOVER_ZH.md](TRIANGLE_HANDOVER_ZH.md) 第零节：当前为运行和记录，冻结 3w-1.9 不改，未经用户明确要求不再挖掘旧数据。
2. 新研究必须在[案例账本第十七节](CASE_REVIEW_LEDGER_ZH.md)先登记问题、数据、唯一判据和门槛，再计算；锁定数据不得擅自使用。
3. 只处理本轮授权的文件和事项；在 `codex/<主题>` 分支上工作，通过 PR 合并，不直接在 main 编辑或推送人工修改。

## 完成后怎样记录

- 每件已完成工作新增一行，附分支 / PR、验证证据、核查重点和真实交付状态，最新在前。
- **研究结果**写入案例账本第十七节；**纯通知、界面、运维和文档工作**写入原需求记录及 [COLLAB-LOG.md](COLLAB-LOG.md)，不伪装成研究结果。
- 尚未提交或合并必须明说；例子、计划、建议不写成已完成，不把“待核查”改成“通过”。

## 当前队列

| 日期 | 事项 | 分支 / PR | 验证证据与核查重点 | 交付状态 | 独立核查 |
|---|---|---|---|---|---|
| 2026-10-26 | Task047 周报数据源与前向日期修复 | `codex/weekly-report-fix` | Claude 2026-10-26 确认：history.jsonl 的 values.spy 为「SPY 买入持有账户净值（含少量现金）」、与账户同期归一；as_of / price_as_of 对估值日防未来，generated_at 仅展示；forward UTC日期允许报告日+1。37项通过（周报12 + app_data25），命令见下；diff检查通过。覆盖未来portfolio、+1/+2及UTC偏移、缺基准、NAV归一及显式冻结回退 | 本地完成；样例 work/task047/2026-10-24.html：XLB/XLP候选变化、无过期、未到期；10-25前向0记录接受；基准不可用。无真实cockpit，仅合成夹具适配估值日且保留旧价，账户估值不可用；未联网/暂存/提交，未验证真实冻结dataset或浏览器视觉 | 待核查 |
| 2026-10-24 | Task046 实施前预检与预登记（阻断） | `codex/paper-account`，sv-wt-036 | §17记录account.py入场/退出顺序冲突、核心权重冲突、起点及盯市建议；workflow/ETF manifest静态核对，未计算账户值 | 仅预检和登记完成；代码、测试、JSON、workflow接线待澄清；未联网/暂存/提交 | **通过（Claude，2026-10-24）**：已由 Task046 实施（#153 合并）取代，冲突按 §17 定论处理，不单独复核。 |
| 2026-10-22 | Task045 公开前向判卷页 | `codex/forward-page`，449059d起点 | Python54项、npm112项（lint/typecheck/build）通过；日志work/task045-python-test.log、task045-npm-test.log；核查计分白名单/同次时间、全部检查点、净R及毛R核对、Discord稳定ID、ticket生命周期、缺失计分、中英文本；public仅forward.json，经追加授权由空记录生成 | 本地完成；未联网/暂存/提交/发布；Claude运行preview-site并核查390/1440，owner UAT待做；§17有范围澄清 | 待核查 |
| 2026-10-22 | Task044 Discord生命周期实施 | `codex/discord-lifecycle`，sv-wt-036 | 70项单测通过；两份workflow YAML解析、diff检查通过；核查ticket唯一来源、40/41日边界、短ID碰撞/稳定、实盘权益不落盘、失败预约保留、模拟独立账本；私有预览work/task044/preview.json、日志tests.log | 本地完成；未联网/暂存/提交，未发送；Claude合并前Actions card_preview | 待核查 |
| 2026-10-22 | Task044 实施前预检（阻断） | `codex/discord-lifecycle`，sv-wt-036 | 只读核对工作流、ticket_outcome及冻结trade；第40交易日仍waiting、缺trade_review.py；建议ticket唯一来源、10万美元模拟回退，见§17 | 仅预检完成；等待澄清，代码/模板/测试尚未完成；无网络或提交 | 待核查 |
| 2026-10-19 | Task042 自动交易复盘与周报 | `codex/trade-review` | §17含Claude日期澄清；`work/trade-review/REPORT.md`、tests.log（最终89项通过，33项新增）、protected-before/after（303文件一致）、validation.json。核对统一提醒风险影响、跳过零盈亏、036/038复用、缺字段/无孪生/空周、各退出与滑点、OHLC范围限制。合成样例 `work/trade-review/synthetic/weekly-2026-10-18.html` 与空周 `weekly-2026-10-25.html` | 本地完成；真实空周0笔且cockpit未提供。截图交Claude；workflow.patch仅建议并通过apply --check，未应用。未暂存/提交/发布，work保持私有 | 已核查 |
| 2026-10-20 | 日更运维恢复 | PR #147、#148 | 两种失败均先复现再修复；111项网站、30项定向发布检查通过；恢复运行1341项Python检查通过（22跳过）。线上四模块10/19，Build4f55f4a与收据一致；原发布保护保留 | 已合入、已上线；补更39426266704成功，notify=false；CR-2026-10-20含完整证据 | **通过（Claude，2026-10-24）**：两 PR 已合并且检查通过；10-23 main 上日更连续 6 次成功，恢复持续有效。 |
| 2026-10-19 | Task043 韩国一次考试结果 | `codex/kr-exam-3`，sv-wt-036 | 资金澄清先登记；合成自测通过后一次运行。29笔，Sharpe p=.171828，样本不足未证明。work/reports/kr-exam-v1.{json,html}、work/v3w/kr_exam.log、kr043/verification.json；保存结果p值及净盈亏加总核对，1,000随机账户，代理日期检查。核查随机抽样/日历排除、净R与固定资本、全窗口排除偏差 | 本地完成，无网络/提交/冻结代码改动；不重跑考试。HTML结构检查，真实浏览器截图未验收 | 待核查 |
| 2026-10-19 | Task043 Step3运行前检查（资金单位阻断） | `codex/kr-exam-3`，sv-wt-036，d839338 | 本地gzip完整hash匹配manifest；4项合成自测，work/v3w/kr043/preflight.json；₩100000整股账户的20%上限导致₩50000合成股票不能买1股 | 仅前置检查完成；未解压行情/扫描/运行考试，暂无结果报告。待Claude明确初始资本单位；建议₩130000000，未应用。未提交 | 待核查 |
| 2026-10-19 | Task043 Step2数据集规格及板块路由 | `codex/kr-exam`，sv-wt-036，基点8afc6d4 | 新增5项测试；相关119项：118通过/1跳过。全部1,532个mock请求均为CODE.KO/KQ一次后缀，raw_close保留；错误后缀在请求前拒绝。US默认/显式US/HK相对基点请求与合成输出字节一致；work/kr-step2/tests.log及protected.json | 仅本地准备完成；spec全名单+069500.KO、不分组、1995起、keep_raw、5%缺失门槛；未联网/实际构建/考试/暂存/提交。Claude核查后触发data-kr-a-v1 | 待核查 |
| 2026-10-19 | Task043 韩国考试 Step 1 | `codex/kr-exam`，sv-wt-036，基点`b849055` | 原值逐字测试；新增16项；相关114项：113通过/1跳过。US/HK/TSE×重试开关6组合成结果、stats、failed、REPORT、shard字节一致。`work/kr-step1/tests.log`、`protected.json`；核查六字符/前导零、同板重用、KO平局、去重先于流动性、失败别名不替代及名称提示 | 仅STOP 1本地完成，未暂存/提交；无网络/真实韩股/分组/冻结/考试。037已关闭。核查后仅触发韩国screen，STOP 2冻结前审查全部review_flags与失败覆盖 | 待核查 |
| 2026-10-19 | Task037 Step 1 日股screen预登记及工程准备 | `codex/jp-exam`（sv-wt-039） | 任务卡/08/§17原值及两条Claude澄清逐字测试；`tests/test_japan_screen.py`新增16项，相关套件97项：96通过/1跳过；US/HK与HEAD合成基线结果、stats、failed、REPORT及shards相同。检查名称子串误杀、失败别名不替代、有效日线定义；核实Actions使用此spec，冻结前审查所有review_flags并记日期 | 仅STOP 1本地完成；无网络/真实日股数据/信号/分组/冻结；未暂存/提交。builder原逻辑模拟验证，真实provider未验收 | 待核查 |
| 2026-10-19 | Task038眼光判卷与自选股前向记录 | `codex/owner-eye` | §17原文预登记、限价/期限/参考价及compute抽孪生澄清；`work/own-picks-038/README.md`、tests.log、protected-before/after（103文件一致），`work/eye-judge/latest.{json,md}`。71项测试：A揭晓顺序/末4题/合计门槛，B/C退出日全部检查点，C追加/迟到/跳空/限价/持有/无前视/冻结池种子。复核市价开盘已越止损时R不可计分处理、B开盘前盲判证据及孪生可用性 | 本地完成，正式前向0、自选0；真实训练90题只能参考。workflow仅建议，未暂存/提交/发布；首次既有回归曾使用系统临时目录，最终测试TMPDIR固定在工作树 | 待核查 |
| 2026-10-19 | Task040 daily1迁入mixed共享模板（UI迁移，无新研究） | `codex/daily1-template` | `work/v3w/daily040/README.md`；protected-before/after与hashes（48文件）、baseline-check/account-parity（真实十答副本mock四指标吻合）、node-tests（11题/心得集合隔离）、blind-check（100/100可见文本）、full-account-parity（4组）。Python30项，daily Node8组、mixed2套、hk10组通过 | 新页 `work/site-v2/daily-trainer-2.html`；未暂存/提交/发布，真实答案不动。390/1440截图与线上恢复待Claude；第59题1日缺价沿用冻结估值，详见valuation-coverage | 待核查 |
| 2026-10-19 | Task039公司去重/非普通股代码段修订：hk1共34题（日20/周12/月2） | `codex/hk-trainer` | §17两条规则先登记再抽题；`work/v3w/hk039/README.md`、data-quality（全源51组/105代码重复、冗余54，指定区间9含代理）、quality-exclusions（候选同公司4/区间3）、build-report、raw-five-check（原规则重选五题5/5）、account-parity（5组）、blind-check（34/34 mock）、node-tests（33/34不揭晓，34/34末批4题入账户/心得/眼光）、protected-before/after（16文件相同）。22+9项Python、10+2组Node通过；原扫描及Task010结果未动 | 新页 `work/site-v2/hk-trainer-1.html`；旧36题版完整归档。34家公司各一题，无指定区间或代理题；待Claude真实390/1440截图/发布/保存验收。Task010同源62个冗余或区间非代理代码局限已记录，不重算。未暂存、未提交 | 待核查 |
| 2026-10-19 | Task036 Step3 前向净R判卷（按Claude澄清） | `codex/forward-judging`，基点 `6253fea` | 新增 `research/lab/forward_judge.py`、`tests/test_forward_judge.py`；Claude初审确认原测试及三条复现检查通过；按复核要求修复跨检查点漏判：按重算退出日期/id排序，逐一判定所有已达到检查点的前k笔，报告检查点表及最近检查点结论，补充bulk缓存缺失限制。`python3 -m unittest tests.test_forward_judge tests.test_triangle15 -q`：20项合成测试+12项冻结交易回归通过。三条fingerprint工程记录 A/2008-04-25、A/2012-09-14、AA/2012-12-14 的3W毛R/孪生毛R均值逐条均相等；仅核对相等，不报R统计。重点复核净R公式、同池同种子与跳过规则、1.7未成交、缺对照计数、10%严格边界和检查点门槛 | 已实现，尚不能正式计分；未暂存、未提交。当前0笔报告暂存 `/private/tmp/task036-forward-judge/latest.{json,md}`（work符号链接目标被沙箱拒写）；默认目标为 `work/forward-judge/`。workflow仅建议，待owner批准；正式价格须为同次前向延伸缓存，paper未提供。Steps1/2未改 | 待核查 |
| 2026-10-19 | Task036 预登记与样本量估算（计分暂停） | `codex/forward-judging` | 预登记逐字比对通过；571候选缓存哈希与既有Task002报告一致，287笔账户交易直接读取既有结果。仅算样本量公式与历史频率，整数门槛/年数反算检查通过，无新扫描/账户/变体。输出 `work/reports/forward-sample-size-v1.{json,md}`，私有脚本 `work/forward-judge/sample_size.py` | 部分交付；冻结前向R未扣费、随机逐笔成交价格未保存，无法实现卡中净R主指标。按卡暂停Step3等待补充口径，没有计分脚本或对应合成测试；未改冻结/工作流 | 待核查 |
| 2026-10-19 | Task035 混合训练80题；Task034研究取消 | `codex/training-followup` | 账本§17先登记及取消/80题批准；80题=日33/周34/月13，80只股票；已判周排除73候选（日5/周68），期末未完成排除12（日7/周4/月1），排除映射426股票周。私有 `work/v3w/mixed035/` 的 build-report、keys、bank、tests.log、README；候选来源 `work/v3w/timeframe034/candidate_only.py`、training-audit、CANCELLED。17项候选边界测试、17项训练Python测试（含真实bank逐日账户对账）、2套Node mock通过；390/1440浏览器实际截图检查 | 页面 `work/site-v2/mixed-trainer-1.html` 本地完成未发布。新增累计账户/后续图/可编辑每批心得/仅揭晓题按周期眼光表；真实云端保存由Claude隔离副本验收，mock不能替代。旧daily1与真实答案不改；研究取消于比较结果前，未跑三账户/随机对照/周期表现表，尝试次数不增加；BASE保留。work全部私有 | 待核查 |
| 2026-10-19 | 首十题退出后走势图 | `codex/training-followup` | 私有 `work/v3w/daily1_replay.py`、`daily1_replay_view.js`、`daily1-first-ten-replay.json`、`test_daily1_replay.py`；原缓存哈希与逐笔身份核对，4项边界测试通过；390/1440实际截图查看，移动端横滑默认定位后续，价格标签避免重叠 | 已给owner独立本地首十题图集；原daily1页面及DB未改。固定退出后5/20/60日观察，不改原盈亏；个人答案和结果不公开 | 待核查 |
| 2026-10-19 | 累计总览与首批真实复盘 | `codex/training-followup` | 私有报告总表优先、明细折叠；18 项本地回归通过。真实正式页已恢复十题；通过已揭晓明细核对题号/名字/日期/展示 R，原始美股缓存哈希验证后按冻结引擎算累计。证据 `work/v3w/daily1-first-batch-observed.json`、`daily1-overall-10.json`；个人答案与成绩保持私有 | 真实来源为可见批次明细；复制按钮显示成功但工具剪贴板为空，没有伪造导出哈希或 answered_at。只读、无 DB 修改。报告在本线程送达；网页本身未升级美元总览 | 待核查 |
| 2026-10-19 | 10 万美元训练账户反馈 | `codex/training-followup`，owner 直接确认冻结 3W 账户 | §17 先补登记；私有 `work/v3w/daily1_account.py`、`daily1_recap.py`、`test_daily1_account.py`、`test_daily1_recap.py`、`daily1-account-tests.log`、`daily1-followup-state.json`。18 项本地合成测试通过：原冻结引擎的风险/仓位/整股/费用/现金占用，含浮亏的回撤、跳空超计划风险、原日期排序、批次累计不可相加、哈希阻断和不满十题不揭晓。源码与输入保持私有，公开仅交接文档 | 每小时复盘已改为冻结规则；正式页只读仍 0/100，无真实批次收益验证；未改页面、题库、冻结代码或真实 DB。现金、复利及持仓重叠按原引擎；日线收据沿用 Task 033，不宣称完整周线策略业绩；Claude 核对首批真实答案导出与美元报告 | 待核查 |
| 2026-10-19 | 训练总结与运行记录接手 | `codex/training-followup`，基于已验收 ee3c02f | 账本 §17 已预登记；正式页只读显示 0/100；私有 `work/v3w/daily1_recap.py`、`test_daily1_recap.py`、`daily1-followup-state.json`，5 项合成输入测试通过；真实新批次尚无。保护检查器原样取自 `origin/docs/baton-guardrails`，只纳入脚本，不带入该分支其他改动；前向步骤成功、夜间旧断言失败均只读记录 | 每小时只读跟进已启用；10 万美元口径已由 owner 确认，见新增账户反馈行；未改线上页面或真实 DB | 待核查 |
| 2026-10-19 | Task 033 日线盘感训练器 | `codex/daily-trainer`（未合并 main） | 100 题=历史 70+新 30；10 项 Python、统计与浏览器交互检查通过；已判周排除 6 / 撤单 810 / 未完成 5；核查第二推触线、成交顺序、5 美元回退（universe 2,718 候选，其余 0）、盲态和每 10 题复盘。交付：`work/v3w/daily_trainer.py`、`daily_trainer.log`、`daily1-keys.json`、`daily1.md`、`daily1-src/`；`work/site-v2/daily-trainer-1.html`。上述 work/ 产物保持私有，公开仓库只列路径；原先越界提交及修复见 Claude 核查结论 | 已由 Claude 核查发布，真实环境保存验收通过；Codex 不重复作答验证 | **通过（Claude，2026-10-19）**：独立重算 100 笔成交/出场/净 R 全部一致；第二推触线、推点不晚于信号前 5 日、图截至信号日、无已判周重叠均核对；冻结代码与港股 B 组未改未用。修复：① `work/` 私有文件（含答案键）被推上公开分支——已从分支移除（本地保留），分支历史已改写；② 页面「下载备份」在发布环境不可用→改为复制到剪贴板；③ 首次答案只在本窗口锁定→保存前先在云端查是否已答（acquire + get），已答则保留第一次。线上验证（测试副本）：保存、刷新、关标签重开均恢复选择/信心/画错/理由/时间；另一设备先答时不被覆盖；测试记录已清理。正式页 https://claude.ai/artifact/Q3Asb9s4H6itz8axpDK8yu（daily1 为空，未混入测试数据）。 |
| 2026-10-19 | 接力棒与核查队列收尾 | [#137](https://github.com/327979420/sage-vista/pull/137)，`codex/baton-review-cleanup`；队列入口 #132 | 链接有效；#101 不再写等待合并；#133 与 #134 的未授权部分仍暂停；本表不冒称 Claude 已核查 | 文档已整理，合并状态见对应 PR | **通过（Claude，2026-10-24）**：已合并，纯文档；队列入口与 PR 链接有效。 |
| 2026-10-19 | Discord 纵向正式模板 | [#136](https://github.com/327979420/sage-vista/pull/136)，`codex/3w-discord-card-layout` | 通知测试 15 项通过；[同一提交的 Actions](https://github.com/327979420/sage-vista/actions/runs/39182916981)验证及纵向样例送达成功；价格各一行，去掉版本号 / 冗余提示；价格精度、规则与生产去重未变 | 已合并并用于正式通知；用户认可样式 | **通过（Claude，2026-10-24）**：已合并、检查通过；main 上 Discord 相关 39 项单测（triangle_discord/discord_digest/product_consolidation）通过。 |
| 2026-10-19 | 冻结 1.9 机会提醒及持久去重 | [#135](https://github.com/327979420/sage-vista/pull/135)，`services/scanner/triangle_discord.py`、研究任务通知 job | 核对仅允许新鲜、合格、waiting、未过期机会；止盈为计划入场 + 3R；发送前 reserved，成功后 sent，结果不确定时不自动重发；[基础模拟回执](https://github.com/327979420/sage-vista/actions/runs/39180740698)为 sent / count=1 | 已上线，模拟已送达；真实信号自动送达待首例验收 | **通过（Claude，2026-10-24）**：已合并、检查通过；同上 39 项单测通过。真实信号自动送达仍待首例（前向至今 0 信号）。 |
| 2026-10-19 | 旧页面测试断言修正 | #135 中 `tests/test_product_consolidation.py` | 旧断言在 main 原样复现失败，仅对齐已有 TodayPage 和 SiteNavigation，未改页面；[完整回归](https://github.com/327979420/sage-vista/actions/runs/39179871983)共 1230 项、跳过 16 项，通过 | 已合并；夜间续跑仍待正常任务验收 | **通过（Claude，2026-10-24）**：test_product_consolidation 在 main 通过；夜间回测 10-23 成功。 |


### Task047 本地复现（2026-10-26）

仅读取本地已有依赖环境，不安装依赖；缓存、测试临时文件及产物全部位于本 worktree。测试日志：`work/task047/tests.log`。

```sh
SV_PY=/Users/xianpeil/Documents/Codex/2026-09-23/files-pasted-by-the-user-you/work/github-portfolio/sage-vista/work/vectorbt-env/bin/python
PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR="$PWD/work/task047/mpl" XDG_CACHE_HOME="$PWD/work/task047/cache" "$SV_PY" -m unittest tests.test_weekly_report tests.test_app_data -q
PYTHONDONTWRITEBYTECODE=1 python3 -m research.lab.weekly_report --cockpit work/task047/cockpit-fixture.json --date 2026-10-24 --output-dir work/task047
```

样例来源：`public/app/portfolio.json`、`public/app/today.json`、`research/lab/forward/triangle/{outcomes.json,signals.jsonl}`。账户输入由 `tests/fixtures/weekly/cockpit.json` 复制，只将 as_of 适配为 2026-10-23、日志改为合成夹具说明；旧持仓/价格保留，所以缺 10-23 收盘价、总资产不可用。paper 历史当前未提交，公共 SPY 仅 09-30/10-23 两个日期，不足每日历史；不补价、不计算绩效。保护边界：Git 差异仅四个授权文件；`work/task047/` 私有产物未暂存。

## Claude 怎样核查

1. 核对该行原始授权、PR 的最终差异和证据；研究行另核对预登记时间、数据边界与唯一判据。
2. 运行该行相关测试或复算关键数字；按治理规则只扩大到受影响问题，不默认重跑无关研究。
3. 已合并 / 已上线的行只复核，不重复合并；未合并的改动核查通过后，按实际授权、EOD 窗口及日更运行状态处理。
4. 回填“通过”或“退回：原因”，记录核查人和日期，再同步在线工作台。Codex 不代填 Claude 的结论。

生产模拟样例已经去重。检查格式请直接调用 `brief_payload()` 或看既有发送记录，不清空通知账本，也不为核查另发消息。
| 2026-10-19 | Task043 韩股考试 Claude 核查 | `codex/kr-exam-3` | 报告字段核对；入场日来自冻结 trade() 的成交日（信号日之后），无前视。交易明细的 `signal_date` 栏被写成入场日，仅标签错误，不影响账户与结论 | 结论「样本不足，未证明」（29 笔，Sharpe p 0.172）按预登记成立 | 已核查 |
| 2026-10-24 | Task046 模拟账户自动化（Claude 实现） | `codex/paper-account` | `tests/test_paper.py` 11 项 + forward_judge/research_lab 相关共 103 项通过；三项冲突按 §17 定论处理；冻结代码与 research/lab/forward/ 未改 | 起算 10-26，首个真实值待合并后运行验收 | 已核查（Claude 自写，owner 可抽查） |
| 2026-10-29 | Task048 前向「实际能做到」一栏 | `claude/forward-executable` | 历史对照（5 个数据集，信号 2005—2024-06）原口径 571 笔 +0.244R、能做到口径 484 笔 +0.262R 与 Claude 脚本逐笔一致；`--fingerprint` 未变；Python 109 / npm 115 通过；冻结代码与 research/lab/forward/ 未改 | 待 owner 批准合并（workflow 新增一步） | 已核查（Claude） |
