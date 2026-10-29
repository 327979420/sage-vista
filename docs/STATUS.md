# Sage Vista — 接力棒（开始先读，结束前更新）

更新：2026-10-22，Codex（Task045）；此前 Claude 合并 #134 时补充。用户在 Claude 与 Codex 之间切换时，以本文件和[核查队列](REVIEW_QUEUE.md)交接。
在线工作台：<https://claude.ai/artifact/BdbVybVXiShDN5MtaqtVUQ>；本轮没有直接修改或读取其在线内容。
机器日期、版本和运行断点仍以 [CURRENT_STATUS_ZH.md](CURRENT_STATUS_ZH.md) 及其机器来源为准；本文件只记工作状态。

## 当前阶段

2026-10-19 owner 明确分工：Codex 负责研究开发实施与记录；Claude 只做核查验收。按任务卡和 ADR-16 运行记录；只提交推送 codex 分支，不合并 main。研究脚本、页面答案与日志留在私有 work/，提交前确认暂存列表无 work/，推送前运行 `python3 scripts/guardrails.py origin/main HEAD`。

运行和记录（用户 2026-10-19 决定）。3W `3w-1.9` 冻结，机械执行；模拟账户方向为行业趋势篮子核心 50% + 3W 卫星 50%。
不自行在旧数据上找新规则；新研究必须先在[案例账本第十七节](CASE_REVIEW_LEDGER_ZH.md)登记。港股 B 组继续锁定。

## 进行中 / 下一步

- **Task048 前向记录「实际能做到」一栏（2026-10-29，`claude/forward-executable`）**：信号要到信号周之后第二周首个交易日收盘后才认得出，冻结重放却从信号日挂单；按 §17 预登记新增 `research/lab/forward_exec.py`，从认出后的下一交易日起挂单（挂单前已破止损/已到止盈则跳过），其余复用冻结 `trade()`；只并排展示，不进警报/证明，模拟账户不变。research-lab 加一步（continue-on-error），/forward 页加一行。Codex 实现（中途配额用尽），Claude 验收：历史对照 571→484 笔逐笔对上，冻结指纹不变，Python 109 项、npm 115 项通过。待 owner 批准合并（含 workflow 改动）。

- **Task047 周报修复本地完成，待 Claude 核查（2026-10-26）**：`codex/weekly-report-fix`。默认读取已发布 portfolio；paper `history.jsonl` 的 `values.spy` 按「SPY 买入持有账户净值（含少量现金）」展示并同期归一；缺完整同期基准显示不可用，不拼接净值与收盘价。行情按 as_of / price_as_of 拒绝未来，generated_at 仅展示；forward 按 UTC 日期允许报告日 +1，+2 拒绝；显式 `--sectors-frozen` 保留离线回退。Claude 两项澄清已记录核查队列。周报12项 + app_data25项共37项全通过，`git diff --check` 通过。样例 `work/task047/2026-10-24.html` 使用今日仓库的 portfolio/today/forward：月底未到期、变化 XLB/XLP、过期无；10-25 computed_at 接受、0记录；基准不可用。无真实 cockpit，样例仅适配已提交合成夹具的估值日、保留旧价，账户估值明确不可用；输入夹具与测试日志在 `work/task047/`。未做浏览器视觉验收；冻结回退 CLI 用合成行情验证，未加载真实离线 dataset。仅改获准四文件，无网络、新依赖、暂存、提交或冻结/workflow改动。

- **Task046 模拟账户自动化已实现（Claude 直接实现，2026-10-24）**：`research/lab/paper.py` + `tests/test_paper.py`；账户 paper-core-sat-v1 登记 10-24、起算 10-26（不倒推）；每日 research-lab 在前向记录后计算并把序列传给 `forward_judge --paper`，补上警报 2 与「证明有效」。合并后首个真实值在 10-26 收盘后的运行产生。

- **Task045 公开前向判卷页本地完成，待Claude核查/预览及owner UAT**（2026-10-22，`codex/forward-page`，基于449059d）：新增Task036计分白名单投影、全部检查点、缺失/过期计分降级、净R曲线/信号/孪生、Task044短ID和ticket生命周期；删除公开盲判字段，中英双语。按本轮Claude追加授权，仅用新版app_data从已核实0信号生成 `public/app/forward.json`；0/30、还差30笔、继续记录未证明，警报1未触发，警报2/有效性均提示需模拟账户、不公开。Python54项、npm112项（含lint/typecheck/build）通过；日志/空记录生成脚本在私有 `work/task045-*`。无网络/暂存/提交；未改其他public文件、冻结代码/规则或workflow。完整数据集不在本worktree，未运行完整app_data行情构建；读取接线有合成测试，390/1440真实预览交Claude，owner验收后才能上线。

- **Task044 Discord生命周期本地完成，待Claude核查/Actions预览**（2026-10-22，`codex/discord-lifecycle`）：澄清已记§17；唯一来源app-data ticket outcomes，补成交价/撤单投影，保留冻结第41日确认到期、第40日为到期日。稳定alert ID写入消息/状态；10万美元模拟及可选实盘股数；六类后续事件有序持久去重，模拟独立账本。70项测试通过，两份workflow YAML解析通过；预览 `work/task044/preview.json`、日志 `work/task044/tests.log`。未接Task042，未改冻结代码/规则，无网络/暂存/提交/真实送达；Claude合并前运行card_preview。

- **Task042 自动交易复盘本地完成，Claude 已核查（0ad956b），2026-10-22 合入 main 并加入周六定时任务**（2026-10-19）：`codex/trade-review`。新增 `research/lab/trade_review.py`，复用036/038交易、孪生及净R；cockpit可选，缺文件「未提供」、缺字段「缺数据」。按Claude澄清以提醒风险统一计算偏差影响，明确跳过实际盈亏为0。合成3笔周报及空周样例 `work/trade-review/synthetic/`；真实空周 `work/trade-review/weekly-2026-10-19.html`（0笔，无cockpit）。最终一次重跑89项测试通过，303个保护文件哈希不变；HTML结构检查通过，截图交Claude，未做浏览器视觉验收。报告/证据/未应用Actions补丁 `work/trade-review/`。MFE/MAE为首尾日完整OHLC范围，精确盘中值缺数据；未暂存、提交、联网或修改生产/冻结代码/workflow。
- **10/20 网站日更已恢复**：用户心跳授权的运维修复#147/#148已合入；补更39426266704成功，notify=false。独立核对四模块均为10/19、Build4f55f4a与收据一致；发布核验通过，最大gzip3.43MiB。恢复常规巡检；证据见CR-2026-10-20，独立同行核查待Claude，其他研究任务保持原状态。

- **Task043 韩国一次考试完成：样本不足，未证明，待Claude核查**（2026-10-19）：资金澄清先登记，真实/1,000随机账户均₩130,000,000；合成自测后仅运行一次。29笔，CAGR0.4463%、Sharpe0.1744、最大回撤11.3249%、平均在场3.2861%，全期Sharpe p=.171828；不足100笔，按预登记不通过证明门槛。报告work/reports/kr-exam-v1.{json,html}、脚本/日志work/v3w/kr_exam.py及kr_exam.log，验证work/v3w/kr043/verification.json；详见§17。冻结代码不改，无网络/暂存/提交；不得重跑。

- **Task037 已关闭（日本无覆盖）**：按Task043记录，provider不覆盖日本，未下载日本数据；原spec保留在 `research/lab/queue-parked/`，TSE代码保留。不可再触发日本screen。

- **Task038 本地实现完成，待Claude核查；尚未接入Actions正式计分**（2026-10-19）：`codex/owner-eye`。§17原文预登记及两次澄清保留；新增训练/前向眼光判卷和自选股追加日志CLI，B/C共用Task036按退出日期的全部检查点遍历。真实答案daily1/mixed1/hk1揭晓10/80/0题，合计90题，仅供参考；前向0笔、自选股0笔。私有结果 `work/eye-judge/latest.{json,md}`，测试/报告/保护哈希 `work/own-picks-038/`；71项测试通过，103保护文件哈希一致。用法见 `OWN_PICKS_HOWTO_ZH.md`。孪生在compute时按冻结池/种子抽，登记参数不看未来；未应用workflow补丁，未暂存、提交或连接真实DB。

- **Task040 daily1共享模板迁移本地完成，待Claude核查/截图/发布**（2026-10-19）：`codex/daily1-template`，新页 `work/site-v2/daily-trainer-2.html`。共享profile新增daily1及独立`daily1_reflections`；100题原盲图、题序、交易和keys保持不变，累计账户/心得/日线眼光/原图与后续图均复用mixed模块。48个保护文件哈希不变，mixed1/hk1重建逐字节相同；真实十份答案副本仅mock恢复锁定，四项账户指标吻合原报告，第11题和心得写入隔离通过。Python9+21项、daily Node8组、mixed2套及hk10组通过，100/100可见文本盲检通过。证据 `work/v3w/daily040/README.md`。第59题有1股票日缺价，保留冻结引擎前收盘估值并记录；不改原行情。真实390/1440截图按指令交Claude，未发布、未碰真实DB、未暂存或提交。

- **Task039 退回修订完成，待Claude复核/截图/发布**（2026-10-19）：按公司键去重及指定非普通股代码段规则，hk1重抽34题（日20/周12/月2；目标60、缺26），最后4题全部答完才揭晓并计入账户/心得/眼光。新增候选排除：同公司重复4、非普通股代码段3。全A数据51组重复公司键涉及105代码（冗余54），区间代码9含代理、非代理8；Task010有同样股票池局限，仅报告合计62个应排除代码，不重跑/不改结果。页面 `work/site-v2/hk-trainer-1.html`；证据 `work/v3w/hk039/README.md`。五题独立重算、5组账户对账、34题盲态mock、22+9项Python及10+2组Node通过；16个保护文件前后哈希相同，mixed1默认构建逐字节相同。旧36题版本完整归档。截图/真实保存仍交Claude；未发布、未暂存或提交。

- **Task036 已实现，尚不能正式计分；等待 Claude 核查**：Step1/2 保留不变。Step3 新增非冻结 `research/lab/forward_judge.py`，只读重算 1.9 与同日孪生的实际成交/退出价、净R差，四位毛R复现闸门；全部已结束规则1.9交易计入检查点，不可计分超过10%暂停该检查点判断，警报2独立。`python3 -m unittest tests.test_forward_judge tests.test_triangle15 -q`：28项通过（新增16项、冻结交易回归12项）。获准三条工程记录 A/2008-04-25、A/2012-09-14、AA/2012-12-14 的3W毛R及孪生毛R均值逐条均相等；未报告收益统计。
  - 当前0笔，CLI正常生成「继续记录，未证明」。`work` 是共享目录符号链接，沙箱拒绝写入默认路径，实际报告暂存 `/private/tmp/task036-forward-judge/latest.{json,md}`；默认目标仍为 `work/forward-judge/latest.{json,md}`。未改符号链接、冻结文件或workflow，未暂存、未提交；建议workflow补丁随交付报告提供，待owner批准后由Claude接入。正式使用须紧接前向运行，读取同次本地延伸缓存；未提供paper时明确标注未提供。
- **Task 035 本地完成，等待 Claude 核查与发布**：独立 mixed1 共80题（日33/周34/月13，owner因月线覆盖不足明确批准），80只股票、八批；周期隐藏，真实周期8根挂单/26根持有，累计10万美元冻结账户。含每题揭晓后60日走势图、每批可编辑心得、仅已揭晓题的分周期做/不做平均净R与小样本提示。17项Python测试（含真实80题账户对账）及两个Node mock套件通过；正式盲图与mock复盘在390/1440实际截图检查，取消遮挡MACD的悬浮作答栏。页面 `work/site-v2/mixed-trainer-1.html`；题库/构建/验证 `work/v3w/mixed035/`。没有发布、没有真实云端保存验收，daily1页面和真实答案未改。
- **Task 034 研究已取消**（owner 2026-10-19，比较结果出来前）：已停止比较运行，三账户汇总尚未执行，没有比较结果/报告；尝试次数不增加。冻结周线BASE已复现并保留。034模板只供035生成训练题，已有候选检查点可复用；不再做周期系统收益/胜率表、随机对照或优劣结论。

## 待 Codex 执行的任务卡（Claude 统筹，2026-10-19 起一次只派一张）

| 顺序 | 卡 | 内容 | 分支 | 工作台 | 状态 |
|---|---|---|---|---|---|
| 1 | [036](../tasks/036-forward-judging-plan.md) | 前向判卷：预登记、样本量、计分脚本已实现 | `codex/forward-judging` | SV-54 | 已实现，尚不能正式计分；等待 Claude 核查 |
| 2 | [038](../tasks/038-owner-eye-and-own-picks.md) | owner 眼光判定 + 自选股前向记录 | `codex/owner-eye` | SV-55 | 本地完成；待Claude核查与Actions接入 |
| 3 | [039](../tasks/039-hk-training-bank.md) | 港股 A 组盲训练34题（公司去重修订，目标60） | `codex/hk-trainer` | SV-56 | 本地完成；待Claude截图、核查与发布 |
| 4 | [043](../tasks/043-korea-exam.md) | 冻结 3W 韩国考试，替代已关闭037 | `codex/kr-exam` | SV-57 | 一次考试完成：样本不足，未证明；待Claude核查 |

Claude 自己：发布混合训练器 v2 到原地址并实测保存（SV-58）；每张卡交付后独立抽查重算再验收。规则：同一时间只有一个 Codex 任务改代码；owner 自己开的 Codex 线程（每小时训练跟进）只读，不改这些分支。

## 本轮已完成

- **训练反馈改为累计总览优先**：owner 要求先看整个账户。私有报告先显示累计余额、净盈亏、收益率、实际成交胜率和最大回撤，批次明细折叠置后；每小时任务已同步。首次真实完整十题已从正式页恢复后的批次明细只读取得，与本地键逐题核对名字/日期/展示净 R；原缓存哈希校验后调用冻结账户完成真实累计计算，结果留在私有 `work/v3w/daily1-overall-10.json`，不公开个人成绩。未修改已发布页面或真实答案；Claude 待核查。

- **10 万美元训练账户口径已确认并实现**（`codex/training-followup`）：全额独立训练，调用冻结 3W 账户（单笔风险 2%、仓位上限 20%、总风险上限 10%、最多 10 只；上一日净值、整股、现金约束、每边成本 0.1%）。此前 1% 提议作废。每十题报告本批及累计美元盈亏、胜率、每日盯市回撤与逐笔复盘，保留判断/R/信心统计及累计表。按原交易日期重放，保留重叠；各批独立从 10 万开始，不能直接累加，累计按全部已揭晓题重算。私有计算与 18 项合成输入测试完成，每小时跟进任务已更新；实施账户工具时正式页为 0/100；后续已取得真实首十题，见上方累计复盘记录，Claude 待核查。线上页面、题库、真实答案均未修改；美元报告在本线程提供。

- **训练跟进已接手**（`codex/training-followup`）：接手当时正式页只读恢复云端后显示 0/100（2026-10-19 03:22 UTC 附近）；其后首十题已完成复盘；未操作任何真实答案。已设本线程每小时检查，有新增十题才总结。私有复盘工具的 5 项合成输入测试通过，不等于真实作答或保存验收。

- **Task 033 日线盘感训练器：100 题（历史 70 / 新数据 30），每股一题；已判股票周排除 6、撤单 810、未完成 5；另因 2005 年前形态锚点排除 74、流动性门槛排除 5,751。** 分支 `codex/daily-trainer`，未合并 main。本地页面 `work/site-v2/daily-trainer-1.html` 与题库已生成；10 项 Python 测试、汇总统计与浏览器交互测试通过。详情见核查队列；**已发布：https://claude.ai/artifact/Q3Asb9s4H6itz8axpDK8yu**（Claude 2026-10-19 核查通过，线上保存已实测）。

- **Discord 机会提醒已上线**：基础链路 [#135](https://github.com/327979420/sage-vista/pull/135)，用户确认的纵向版 [#136](https://github.com/327979420/sage-vista/pull/136) 已合并；正式模板为普通纵向文本，入场、止损、3R 止盈各一行，有效期前留白，不显示版本号或“非真实机会”。规则、价格计算和生产去重未改。
- **模拟送达已验证**：[纵向版发送记录](https://github.com/327979420/sage-vista/actions/runs/39182916981)成功。真实新机会的自动送达仍需等首个符合条件的真实信号验收；不要把模拟送达记成这项验收已完成。
- **核查队列已建立**：[#132](https://github.com/327979420/sage-vista/pull/132) 已合并；[#137](https://github.com/327979420/sage-vista/pull/137) 补入已上线内容与待 Claude 复核条目。交接文档整理不等于独立核查通过。

## 持续运行 / 等待验收

| 事项 | 当前状态 | 下一步 |
|---|---|---|
| 冻结 3W 前向记录 | 只读检查 [39127981877](https://github.com/327979420/sage-vista/actions/runs/39127981877)：2026-10-18 运行成功，前向记录步骤成功；不据此断言有新信号 | 按正常节奏检查信号和结果，每周复核；无信号如实记无信号 |
| Discord 真实机会闭环 | 发送、格式与去重已测试，尚无首个真实机会送达验收 | 首次真实信号时核对网站 / 记录 / 消息一致，不伪造机会或清账重发 |
| 夜间回测修复 SV-22 | #101 早已合并；最近失败涉及的旧页面断言已在 #135 修正 | 等下一次正常夜间续跑成功后补验收，本轮不触发、不修改 |
| 盘感训练器（日线 daily1，任务 033 → 040） | 2026-10-19 换成混合训练器同一页面（任务 040），同一网址，owner 已答 10 题保留 | owner 继续做题；每满十题出总结 |
| 混合训练器（日/周/月 mixed1，任务 035） | 已发布；owner 已答完 80/80 | 眼光结论按任务 038 与其他题库合计 |
| 港股训练题（hk1，任务 039） | 34 题已发布：https://claude.ai/artifact/MNsi8huKuMMrdzn45BTvnD | owner 做题；首题后 Claude 确认云端保存 |
| 前向计分（任务 036 / 038） | owner 2026-10-19 批准接入前向 workflow：`forward_judge` 与 `own_picks compute` 紧接 `triangle_forward` | 合并后看第一次运行的计分产物 |
| 周期比较研究（任务 034） | **owner 2026-10-19 取消**（出结果之前）；其周期规则只供 035 出题 | 不再运行 |
| 周六例行（SV-52） | Claude 定时任务，每周六 10:00 墨尔本 | 首次 2026-10-24：信号、驾驶舱、周报、核查队列；10-30 收盘月末再平衡 |
| Codex 独立核查 | 见 [REVIEW_QUEUE.md](REVIEW_QUEUE.md)，本轮条目均待 Claude 复核 | 用户要求“核查”时，Claude 按行核对并回填结论 |

## 明确暂缓 / 本轮不处理

- 手机安装 / 离线、框架升级、完整交易记账及其他产品工作：仅保留原待办，不在本轮启动。

## 待用户决定

- 是否删除公开数据副本（SV-21）：仍需明确批准；本轮未删除。
- 行业篮子的“候选”标签是否调整：沿用暂缓决定。
- 港股 B 组继续锁定；韩国Task043一次考试已完成，结论样本不足、未证明；不得重跑或调参。

## 下次接手

先读本文件、[REVIEW_QUEUE.md](REVIEW_QUEUE.md)、[交接第零节](TRIANGLE_HANDOVER_ZH.md)与[任务规则](../tasks/README.md)，再查 Git 状态和对应 PR。
结束前更新本文件，只把实际完成的工作加入核查队列；历史留在 [COLLAB-LOG.md](COLLAB-LOG.md)。
Task 033 已由 Claude 核查、发布并验证保存；Codex 继续只读跟进训练总结，真实答案不改。训练结果不改冻结 3W，不用于在旧数据上定新规则。
