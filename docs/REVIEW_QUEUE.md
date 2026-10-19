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
| 2026-10-19 | mixed1 单次构建维护 + 复盘答题原图 | `codex/mixed-feedback-build` | 私有 `work/v3w/mixed035/`：build/template接入feedback-v2，旧入口停用，锁定bank/keys哈希；summaries/style增加同源原图切换。21项Python、两个Node mock通过；390/1440小结/累计表/走势图/导入前后截图，9/10/11题门控、模拟刷新与重复导入、答题/复盘SVG相同均本地核验。证据 `qa-feedback-build/QA.md`、tests-maintenance.log、page-build-report.json | 可以交给Claude发布 `work/site-v2/mixed-trainer-2.html` 到原mixed1网址；未访问线上或owner导出，无真实DB写入。旧磁盘发布HTML落后于Claude源，保留源中修正；合并本身与旧流程当前源输出字节一致。真实保存仍待Claude验收；work不提交 | **通过**（Claude 2026-10-19）：已发布到原 mixed1 网址（version 2），题库 80 题 id/顺序/结果与原版一致、keys_sha256 不变；真实页面刷新后恢复 80 题，账户 $88,422 不变；第 1 题「答题原图 / 后续走势」两个按钮都在，原图与答题时同一张（三推线、底、成交量、MACD，截止信号K线）；云端 80 条答案与备份逐条一致、版本均为 1（发布未写入）。小问题待下次：第 3 批“做均R”显示为 −0.00R（应显示 0.00R、不标红）。 |
| 2026-10-19 | Task036 预登记与样本量估算（计分暂停） | `codex/forward-judging` | 预登记逐字比对通过；571候选缓存哈希与既有Task002报告一致，287笔账户交易直接读取既有结果。仅算样本量公式与历史频率，整数门槛/年数反算检查通过，无新扫描/账户/变体。输出 `work/reports/forward-sample-size-v1.{json,md}`，私有脚本 `work/forward-judge/sample_size.py` | 部分交付；冻结前向R未扣费、随机逐笔成交价格未保存，无法实现卡中净R主指标。按卡暂停Step3等待补充口径，没有计分脚本或对应合成测试；未改冻结/工作流 | 待核查 |
| 2026-10-19 | Task035 混合训练80题；Task034研究取消 | `codex/training-followup` | 账本§17先登记及取消/80题批准；80题=日33/周34/月13，80只股票；已判周排除73候选（日5/周68），期末未完成排除12（日7/周4/月1），排除映射426股票周。私有 `work/v3w/mixed035/` 的 build-report、keys、bank、tests.log、README；候选来源 `work/v3w/timeframe034/candidate_only.py`、training-audit、CANCELLED。17项候选边界测试、17项训练Python测试（含真实bank逐日账户对账）、2套Node mock通过；390/1440浏览器实际截图检查 | 页面 `work/site-v2/mixed-trainer-1.html` 本地完成未发布。新增累计账户/后续图/可编辑每批心得/仅揭晓题按周期眼光表；真实云端保存由Claude隔离副本验收，mock不能替代。旧daily1与真实答案不改；研究取消于比较结果前，未跑三账户/随机对照/周期表现表，尝试次数不增加；BASE保留。work全部私有 | 待核查 |
| 2026-10-19 | 首十题退出后走势图 | `codex/training-followup` | 私有 `work/v3w/daily1_replay.py`、`daily1_replay_view.js`、`daily1-first-ten-replay.json`、`test_daily1_replay.py`；原缓存哈希与逐笔身份核对，4项边界测试通过；390/1440实际截图查看，移动端横滑默认定位后续，价格标签避免重叠 | 已给owner独立本地首十题图集；原daily1页面及DB未改。固定退出后5/20/60日观察，不改原盈亏；个人答案和结果不公开 | 待核查 |
| 2026-10-19 | 累计总览与首批真实复盘 | `codex/training-followup` | 私有报告总表优先、明细折叠；18 项本地回归通过。真实正式页已恢复十题；通过已揭晓明细核对题号/名字/日期/展示 R，原始美股缓存哈希验证后按冻结引擎算累计。证据 `work/v3w/daily1-first-batch-observed.json`、`daily1-overall-10.json`；个人答案与成绩保持私有 | 真实来源为可见批次明细；复制按钮显示成功但工具剪贴板为空，没有伪造导出哈希或 answered_at。只读、无 DB 修改。报告在本线程送达；网页本身未升级美元总览 | 待核查 |
| 2026-10-19 | 10 万美元训练账户反馈 | `codex/training-followup`，owner 直接确认冻结 3W 账户 | §17 先补登记；私有 `work/v3w/daily1_account.py`、`daily1_recap.py`、`test_daily1_account.py`、`test_daily1_recap.py`、`daily1-account-tests.log`、`daily1-followup-state.json`。18 项本地合成测试通过：原冻结引擎的风险/仓位/整股/费用/现金占用，含浮亏的回撤、跳空超计划风险、原日期排序、批次累计不可相加、哈希阻断和不满十题不揭晓。源码与输入保持私有，公开仅交接文档 | 每小时复盘已改为冻结规则；正式页只读仍 0/100，无真实批次收益验证；未改页面、题库、冻结代码或真实 DB。现金、复利及持仓重叠按原引擎；日线收据沿用 Task 033，不宣称完整周线策略业绩；Claude 核对首批真实答案导出与美元报告 | 待核查 |
| 2026-10-19 | 训练总结与运行记录接手 | `codex/training-followup`，基于已验收 ee3c02f | 账本 §17 已预登记；正式页只读显示 0/100；私有 `work/v3w/daily1_recap.py`、`test_daily1_recap.py`、`daily1-followup-state.json`，5 项合成输入测试通过；真实新批次尚无。保护检查器原样取自 `origin/docs/baton-guardrails`，只纳入脚本，不带入该分支其他改动；前向步骤成功、夜间旧断言失败均只读记录 | 每小时只读跟进已启用；10 万美元口径已由 owner 确认，见新增账户反馈行；未改线上页面或真实 DB | 待核查 |
| 2026-10-19 | Task 033 日线盘感训练器 | `codex/daily-trainer`（未合并 main） | 100 题=历史 70+新 30；10 项 Python、统计与浏览器交互检查通过；已判周排除 6 / 撤单 810 / 未完成 5；核查第二推触线、成交顺序、5 美元回退（universe 2,718 候选，其余 0）、盲态和每 10 题复盘。交付：`work/v3w/daily_trainer.py`、`daily_trainer.log`、`daily1-keys.json`、`daily1.md`、`daily1-src/`；`work/site-v2/daily-trainer-1.html`。上述 work/ 产物保持私有，公开仓库只列路径；原先越界提交及修复见 Claude 核查结论 | 已由 Claude 核查发布，真实环境保存验收通过；Codex 不重复作答验证 | **通过（Claude，2026-10-19）**：独立重算 100 笔成交/出场/净 R 全部一致；第二推触线、推点不晚于信号前 5 日、图截至信号日、无已判周重叠均核对；冻结代码与港股 B 组未改未用。修复：① `work/` 私有文件（含答案键）被推上公开分支——已从分支移除（本地保留），分支历史已改写；② 页面「下载备份」在发布环境不可用→改为复制到剪贴板；③ 首次答案只在本窗口锁定→保存前先在云端查是否已答（acquire + get），已答则保留第一次。线上验证（测试副本）：保存、刷新、关标签重开均恢复选择/信心/画错/理由/时间；另一设备先答时不被覆盖；测试记录已清理。正式页 https://claude.ai/artifact/Q3Asb9s4H6itz8axpDK8yu（daily1 为空，未混入测试数据）。 |
| 2026-10-19 | 接力棒与核查队列收尾 | [#137](https://github.com/327979420/sage-vista/pull/137)，`codex/baton-review-cleanup`；队列入口 #132 | 链接有效；#101 不再写等待合并；#133 与 #134 的未授权部分仍暂停；本表不冒称 Claude 已核查 | 文档已整理，合并状态见对应 PR | 待 Claude 核查 |
| 2026-10-19 | Discord 纵向正式模板 | [#136](https://github.com/327979420/sage-vista/pull/136)，`codex/3w-discord-card-layout` | 通知测试 15 项通过；[同一提交的 Actions](https://github.com/327979420/sage-vista/actions/runs/39182916981)验证及纵向样例送达成功；价格各一行，去掉版本号 / 冗余提示；价格精度、规则与生产去重未变 | 已合并并用于正式通知；用户认可样式 | 待 Claude 核查 |
| 2026-10-19 | 冻结 1.9 机会提醒及持久去重 | [#135](https://github.com/327979420/sage-vista/pull/135)，`services/scanner/triangle_discord.py`、研究任务通知 job | 核对仅允许新鲜、合格、waiting、未过期机会；止盈为计划入场 + 3R；发送前 reserved，成功后 sent，结果不确定时不自动重发；[基础模拟回执](https://github.com/327979420/sage-vista/actions/runs/39180740698)为 sent / count=1 | 已上线，模拟已送达；真实信号自动送达待首例验收 | 待 Claude 核查 |
| 2026-10-19 | 旧页面测试断言修正 | #135 中 `tests/test_product_consolidation.py` | 旧断言在 main 原样复现失败，仅对齐已有 TodayPage 和 SiteNavigation，未改页面；[完整回归](https://github.com/327979420/sage-vista/actions/runs/39179871983)共 1230 项、跳过 16 项，通过 | 已合并；夜间续跑仍待正常任务验收 | 待 Claude 核查 |

## Claude 怎样核查

1. 核对该行原始授权、PR 的最终差异和证据；研究行另核对预登记时间、数据边界与唯一判据。
2. 运行该行相关测试或复算关键数字；按治理规则只扩大到受影响问题，不默认重跑无关研究。
3. 已合并 / 已上线的行只复核，不重复合并；未合并的改动核查通过后，按实际授权、EOD 窗口及日更运行状态处理。
4. 回填“通过”或“退回：原因”，记录核查人和日期，再同步在线工作台。Codex 不代填 Claude 的结论。

生产模拟样例已经去重。检查格式请直接调用 `brief_payload()` 或看既有发送记录，不清空通知账本，也不为核查另发消息。
