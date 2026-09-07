# CR-056｜月周日评分与持续观察最小设计包

版本：`0.2.0-design-review`。日期：2026-09-07。状态：`implementing`（2026-09-07用户明确授权本轮后台策略/排行包）。
用户已授权推进并由执行方提出琐碎参数建议，不再逐项提问；完整设计经独立复核后，用户明确要求“我们能不能开始优化多因子策略，并且重新跑出排行榜？之后我们着手做大盘和行业的内容，就开始回测”。本轮批准后台规则/评分与真实最新榜实施；先多因子真实榜，再大盘/行业，再真实策略回测。未批准线上策略激活、外部引擎安装或实验UI。以下分清“用户已确认”与“建议默认值”；默认值是可实验配置，不是用户逐字指令或已验证优势。基线875c1d2；当前网站Build6dc33ee、数据2026-09-04不因本设计改变。CR057卖空单独captured，CR036持仓延长仍不实施。

## 1. 已确认业务与交付顺序

1. 初次日线MACD金叉是提名门票，随后月→周→日判断。月/周不允许时，其他因子高分不可补救；许可通过后以加权总分主排序，月>周>日权重，不采用周期词典序。月线刚合格、日线更强者可以总分反超月线强、日线一般者。
2. 小带大允许旧月死叉后尚未金叉、负柱改善者继续看周日，不预判未来金叉；用户原话为“连续两根完整月柱缩短”。大带小允许月线已/刚金叉，周线负柱改善/准备金叉可考虑。
3. 月线正柱开始缩短或刚死叉暂不做；周线正柱一般缩短降分、临近死叉才否决。负柱变长是恶化，负柱缩短是改善，不用红绿颜色定义。
4. 月线价格高位和MACD自身高位都限制。只做长期上涨或长期筑底背景下的回调；不做历史高位延续上涨/创新高突破，但允许回调后的局部突破，不强制等局部突破才进池。
5. 两榜：今日新提名自动加入持续观察总榜；旧候选每日以最新完整数据复评，原提名事件/分数不变。失格退出当前合格排名、停止高分警报，历史跟踪保留；恢复资格自动回榜，无需新日金叉，标恢复合格而非首次提名。恢复不等于买入/交易重入，符合高分规则才报警。
6. 持续强候选是人工优先查看对象，非已验证买入优势。月线假突破/指标失效概率最低属于待验证主观假设，不保证回本、不取消退出。减少深套与收益/alpha的取舍交回测，不预定牺牲收益或风险必优先。
7. 先完善多因子评分和上述资格/复评，再接用户能简单使用的结果与外部对照，其他执行层随后。参数由本包建议，不再逐项问用户；仍须完整包审核及实施授权。

原需求来源：[总手册](SAGE_VISTA_RULEBOOK_ZH.md)、[评分规则](rules/04_SCORING.md)、[总需求第五/六节](PROJECT_REQUIREMENTS_MASTER_ZH.md)、[2026-08-30决策](DECISION_LOG_ZH.md)。这些原则不是本轮新优化；本轮将缺失语义补成可实施候选政策。

## 2. 实现差异与唯一落点

| 环节 | 当前实际 | 本包最小改变 |
| --- | --- | --- |
| 旧生产 | _candidate只认日MACD与日线EMA200长期资格，按命中/家族/共振计数 | 保留旧版只读对照，不声称符合新方向许可 |
| M03 | GateEvent 2.x冻结日金叉；月/周只保存完整周期数量/截止日，长期事实shadow不改baseline | 保留旧Gate语义；新政策允许长期上涨/筑底两背景，不再仅以旧baseline决定新模型资格 |
| M04 | TechnicalEvidence 2.x要求Gate日期与当前输入同日 | 新版本接受精确提名或复评上下文；复用同一完整周期/指标纯函数，不伪造旧候选今日金叉 |
| M05 | complex eligible直接取baseline_passed | 唯一月周许可/两背景/回调判断，输出许可及原因，无分数 |
| M07 | 旧计数Score/Ranking；CR054仅必需事实适用性 | 唯一加权评分、全量持续合格榜及今日新提名子视图，无第二套评分 |
| M09 | 永久事件与关联追加 | 保存复评引用、状态迁移与警报事实，原提名冻结 |
| M10/现有comparison | 逐信号评价，Portfolio资本政策未获批 | 对照新旧政策，执行与费用保持同一原政策，不新增资本引擎 |
| M12/网页 | 旧四页与受审新链分离 | 后续最小消费两榜/复评/异步实验状态；本包不提前开启完整新链 |

M03/M05/M07已通过的是原影子/行为等价范围，非此需求全链验收。对应[设计](M03_GATE_AND_LONG_TERM_STATE_DESIGN_ZH.md)、[M03验收](M03_ACCEPTANCE_REPORT_ZH.md)、[M05验收](M05_ACCEPTANCE_REPORT_ZH.md)、[M07验收](M07_ACCEPTANCE_REPORT_ZH.md)原样保留。

## 3. 可实验默认政策：数据、方向与背景

本节数值均为执行方建议，统一配置`cr056-policy 1.0.0-candidate`并绑定内容指纹。禁止用配置热更新改历史；参数变化新增版本。价格使用同一M02复权OHLCV，as_of为最新完整交易日D；月/周只使用M02会话日历证明已完整的周期，指标种子/EMA/MACD算法复用现有实现，不混供应商图表默认。

### 3.1 数据与MACD许可

建议至少420个完整日K、61个完整月K（供当前月及此前60月高位分位）；IPO较短或必需窗口不足返回unavailable，不凭短窗口补零。设每周期MACD为现有12/26/9、H=MACD线−信号线。以下严格比较为我们的明确数学建议，不冒充用户“连续两根”的逐字展开；H=0统一neutral，不当金叉。负柱连续两次改善采用H[-3]<H[-2]<H[-1]<0，即三根完整观测柱支持两个相邻变化；不额外加等待月数。

| 周期/状态 | 建议默认判据 | 结果 |
| --- | --- | --- |
| 月线已多头 | H[-1]>0 且 H[-1]>=H[-2] | 方向允许；刚金叉可通过，不替代高位/回调检查 |
| 月线负柱改善 | H[-3]<H[-2]<H[-1]<0 | 方向允许，小带大候选；不预言未来金叉 |
| 月线刚死叉/恶化 | H[-2]>=0>H[-1]，或正柱缩短，或负柱变长 | blocked；刚死叉后必须实际满足上述两次负柱改善才恢复，不自加月份 |
| 其余月线（含平负柱/零柱） | 不满足允许判据 | blocked，reason=monthly_not_confirmed；缺数据另为unavailable |
| 周线负柱改善 | 同样两次负柱改善 | 允许；“准备金叉”不以预测代替此可观察事实 |
| 周线正柱不缩短 | H[-1]>0 且H[-1]>=H[-2] | 允许 |
| 周线正柱缩短但未临近死叉 | H[-1]>0，H[-1]<H[-2]且不满足下行临近判据 | 允许，周线分乘0.75 |
| 周线临近/已死叉 | 正柱缩短且 H[-1]/P<=0.10，其中P为最近13根已完成周柱正值最大值；或H[-2]>=0>H[-1] | blocked；P=0不适用正柱分支 |
| 其余周线 | 未达到允许条件 | blocked；必需数据缺失为unavailable |

临近死叉使用上述H/P<=0.10（10%）这一处配置值。月线判定先于周线，保存全部可得事实但许可原因按月→周→背景顺序展示；日线没有额外死叉硬门槛，只影响复评分，不给旧候选重新设金叉门票。

### 3.2 月线高位与可控回调

- 高位建议默认使用同一复权/稳定证券的已观测历史高价H_obs（截至D之前全部已归档完整行情）。若C<0.95H_obs，因为H_obs<=真实全历史高H_all，足以证明C<0.95H_all，可通过此项而无需IPO全覆盖证明。C>=0.95H_obs时保守blocked，reason=near_observed_history_high；有完整上市历史证据才可另标near_all_time_high，否则明确“已观测高位保守代理，可能多排”，不得把窗口最高冒充全历史。行情窗口本身不足/复权口径不一致仍unavailable，不额外要求新供应商或listing覆盖元数据才能计算这一项。
- 月线远离承接：C/EMA20_month−1>0.20则暂不做；等号允许。近月线压力用历史高位条件作首轮可复核代理，不额外发明阻力线检测器。
- 指标自身高位：A=abs(月MACD线)/月收盘，B=abs(月H)/月收盘；最新MACD线>0且A>=此前60完整月A的经验90分位，或最新H>0且B>=此前60完整月B的经验90分位，暂不做。分位采用排序nearest-rank ceil(0.9*n)，不含当前月；需要当前及此前60月共61月才能计算该分支，故高位检查实际最小月历史为61。深负柱绝对值大不因该“正向高位”规则被误排。分母>0、非有限数失败。
- 回调：C<=0.95×此前60个完整交易日最高价，沿原pullback_60d事实；此为位置要求，不要求局部突破。原已确认pivot局部结构若回撤>70%且未收复0.618，blocked；pivot证据缺失unavailable，深插后收复只留风险提示，不加分。

### 3.3 两条背景资格均实现

- 长期上涨回调默认：保留现有日EMA200背景谓词（C>=0.9×EMA200、EMA200/60日前EMA200>=0.97）并满足3.2回调/结构及月周许可；旧谓词本身不代表月线允许。
- 长期筑底回调默认（独立OR路径）：取当前完整月之前12个完整月为冻结底部区间[L,U]；此前24个月最高价到L回撤>=30%；(U−L)/L<=50%；12月底部至少两次月低价<=1.05L、两次相隔>=3月；最近6个底部月最低价>=0.98×前6个月最低价；当前C>=底部12月收盘中位数。再满足相同回调/结构及月周许可。该定义不要求突破U、不强制日EMA200通过，不按CGEM等单票定制；它是待对照的候选定义，不能称筑底必反转。
- 两者同时满足时保存两条事实，展示primary=uptrend_pullback；只有筑底满足时primary=long_base_pullback。缺某一路必需事实时该路unavailable；另一条已知通过可继续，若均无通过且有未知则整体unavailable，否则blocked。月周/高位/回调共同条件缺失始终不能绕过。

## 4. 月周日评分数学（许可先行）

评分政策建议主版本2.0.0；不改变旧1.x或CR054 1.1.x含义。所有分项记录原始事实、去重归属、时间、倍率与未计分理由；没有validated策略仍可展示候选分，但分数不是胜率。

- 周期权重w_M=3、w_W=2、w_D=1。只读固定注册表0.10.0及本包显式月线方向候选扩展，runtime=definition_required的5项继续观察且不计分；M07名单及redundancy_group/depends_on绑定注册表指纹。MACD初次门票、long_trend与pullback资格不重复加分；M06大盘行业只参考、不加总分。
- 可计分因子只限下表13项旧candidate及1项新提议的月线方向状态白名单；它是本包建议的候选评分，不把candidate/display_only改标validated或已批准生产权重。pending/testing/rejected/unstable/paused及definition_required仍保留观测与原研究状态，不因优化整批升格。raw_hit=true且父条件满足得q=1；仅在原注册observation_window内recent_hit=true而raw_hit=false得q=0.5；无明确窗口的近期事件不延寿。两者皆真取1，不相加。子事实父条件不成立取0。不把连续日命中当多条证据累加。
- 同周期同redundancy_group或父子依赖连通组为一故事组g：主贡献max(q_i)；其中每个已确认子事实可加0.25×q_child，组内确认奖励封顶0.5；组总贡献G<=1.5。纯并列无依赖同组取最大值，不靠重复EMA距离堆分。父子跨周期时按各周期独立事实计一次，禁止额外跨周期父子奖励。
- 每周期家族贡献F_tf,f=min(2,sum(G))；正向家族限定macd/support/price_structure/volume，其他注册家族只有明确列入政策才计分，不由当日有无数据决定名单。月/周当前无对应因子的家族不进该周期分母。每周期上限K_tf为冻结名单依上述组/家族约束全命中时的可达贡献，不按当天数据动态调整。
- T_tf=sum(F_tf,f)/K_tf，范围[0,1]；周线一般正柱缩短时T_W乘0.75。Score=round(100*(3*T_M+2*T_W+T_D)/6,4)。家族、颗数、父子确认已进入公式，不再另加旧共振/家族bonus；跨周期共振显示证据，不二次奖励。
- 许可blocked/unavailable：可保存诊断分项，但total_score=null，不得进入当前合格排名或警报。通过许可但评分某项不可得：该项不计贡献且保持missing状态、分母不缩小；coverage=可得计分故事组数/冻结故事组总数。coverage<80%则score_status=unavailable、不排名；>=80%标partial并显示覆盖率，不冒充完整。方向/背景/高位事实是必需，不适用80%豁免。
- 排序键：总分降序、月分降序、周分降序、证券稳定ID升序；月周仅作同总分tie-break，不阻止更高总分反超。每日两榜均来自同一复评结果集，精选取当前合格榜前5，绝不另算分。

固定白名单与每周期可达满分（注册表0.10.0元数据冻结；新增月线方向状态替代一次性月金叉计分，其他新增方向/资格不加分）：

| 周期 | 唯一计分factor_id白名单 | 可达满分K / 固定故事组数 |
| --- | --- | --- |
| 日 | support.ema_proximity；support.fibonacci_618；structure.trendline_three_push；structure.trendline_three_push_retest；structure.bullish_fvg_support；structure.bottom_bullish_engulfing；structure.support_bullish_engulfing；volume.bottom_expansion | K_D=5（support2+price_structure2+volume1），7组 |
| 周 | macd.weekly_histogram_improving；support.weekly_ema_proximity | K_W=2，2组 |
| 月 | direction.macd_state.monthly；support.monthly_ema_proximity；structure.monthly_bullish_engulfing；structure.monthly_double_bullish_engulfing | K_M=3.25（macd1+support1+同组吞没/双吞没1.25），3组 |

月/周因子少，通过固定可达满分归一而非原始颗数与日线竞争；月/周缺失不得挪权重给日线。固定12故事组计算coverage；组内任一白名单成员缺失即该组不可得，观察型非白名单不进入coverage。新增月线方向状态候选按macd家族/macd_monthly组：H>0且不缩短q=1，负柱两次改善q=0.5；这只是本包建议离散证据映射，不伪称已有连续强度或可靠性。它替代macd.monthly_bull_cross的一次性得分，后者仍显示原事实，不重复加分；因此月金叉已过去而多头仍在不会自动丢失方向分。K由全命中合成事实机械验算，不能因当前没金叉或缺数据缩小。跨周期强度未知时不捏造连续数值，历史样本不能自动改变白名单。

“强弱”首版用已确认/仅近期、独立证据及受限确认表达；不凭主观给单因子赢面权重，也不引入未注册的连续强度函数。可实验变量只通过新配置版本对照，不对结果现场改参数。

## 5. 两榜生命周期、每日复评与警报

- 首次提名：同日formal股票池、原精确日MACD门票、当前新资格通过才入可交易新提名榜；MACD触发但资格失败仍保存紧凑观察/排除事实，不能冒充正式入池。每证券/模型谱系/路径scope首次成功入池产生一个watch_id；watch_id=hash(instrument_id,model_lineage,path_scope)，不含policy版本，关联原Gate、原分及日期。
- 持续榜：每天遍历已入池watch_id，使用D完整数据重新计算M04事实→M05许可→M07分；不重跑“必须今日金叉”创建边界。已在跟踪的证券后来再金叉可追加事件引用，但不制造重复watch行、不再次显示首次提名。
- 状态：qualified→disqualified（已知许可失败）、qualified→data_unavailable（数据/评分不足）、disqualified/data_unavailable→qualified（自动恢复）。退市等明确不可交易状态为inactive，只留历史；未获用户自动清退期限，不默认过期删除。重新上市身份epoch不同走新证券身份，不偷偷复用旧watch。
- 今日新提名=当日首次合格入池的严格子视图；持续当前榜=当日qualified且score可用的全体。历史/跟踪标签保留不合格/不可用对象及原因。初次记录、每日review、恢复记录分别有身份，不覆盖，恢复无新金叉也不构造新提名。评价落后只标pending，不阻断当前有完整输入的评分。
- 建议网站高分规则：Score>=60、coverage=100%、有>=2个正向证据家族；首次满足、从不满足到满足、或冷却结束仍持续满足时可产生警报。score_partial可排名但不报警。若该默认过严/过松交固定样本对照，不动态调阈值迎合数量。
- 冷却默认5个M02交易会话，以该watch最近成功记录的警报会话计数；D到last_alert相差>=5才可再报。失格/缺失当日停止警报，恢复也不绕过冷却；从未报过者满足条件可报。每次复评另外维护consecutive_high_sessions显示持续性：连续完整会话满足高分累计，否则归零；缺失中断并显式记录，不补连续天数。
- 警报逻辑去重键=(watch_id,as_of,channel=website)，保存review_id、score_id和两种政策指纹（政策进内容/版本溯源，不进逻辑去重键），原子追加一次；页面重复加载/任务重试不重发。watch身份跨政策稳定；换政策不新建首次提名，原origin固定。唯一冷却查询按watch_id跨政策沿用已成功警报，不靠换版本刷警报。当前只网站警报状态，Discord/邮件/交易通知不在授权内。

## 6. 精确合同与单一负责人

所有新结构通过现有`services/contracts/validation.py::validate_contract`唯一入口验证；模块包装器只调用该入口并验证引用，不能各写一套结构/业务许可。旧schema不放宽。

| 合同/版本建议 | 唯一生产者 | 必填新增内容/约束 |
| --- | --- | --- |
| ReviewContext 1.0.0（本包唯一新增上下文类型） | M03 `services/gates/producer.py`现有编排层 | review_context_id、instrument_id、origin_gate_event_id、origin_date、as_of、universe_id、market_snapshot_id、point_in_time_fingerprint、path_status、mode=initial/daily_review、policy_fingerprint；origin_date<=as_of。initial必须同日精确Gate；daily_review必须引用M09已入池事实，不可任意指定股票 |
| TechnicalEvidence 3.0.0 | M04 `services/factors/producer.py` | evidence_context_type=gate/review、evidence_context_id、as_of当前事实日期，origin_gate_event_id只作溯源；因子ID/版本、周期完整日、可用性、输入指纹保留。月周MACD/高位/背景基础数值作为注册的方向/资格事实输出，不由M05重算指标 |
| ModelAssessment 3.0.0，complex model 2.0.0 | M05 `services/selectors/producer.py` | review_context_id、permission_policy_version/fingerprint、monthly/weekly/background/pullback/high_zone各observed状态与证据refs、permission=allowed/blocked/unavailable、reason_codes、eligible=(permission=allowed)。禁止含分数/排名；不改变favorite_pattern旧模型 |
| ScoreResult 3.0.0，score policy 2.0.0 | M07 `services/ranking/producer.py` | assessment_id、context_id、当前D、完整计分名单指纹、每组贡献/上限、T_M/W/D、coverage、score_status、total_score；blocked/unavailable不得有可排名分数 |
| RankingSnapshot 3.0.0，ranking policy 2.0.0 | M07同一入口 | ranked_entries为当前合格持续榜，new_nomination_refs为当日首次入池子集，selected_entries前5，nonranked refs含状态/原因；唯一authority_scope=complex_multifactor_main，不为第二张视图制造第二权威榜 |
| OpportunityEvent/MachineAssessmentLink扩展新主版本 | M09 `services/ledger/producer.py` | event_kind=nomination/review/qualification_lost/qualification_restored/high_score_alert及watch_id、origin refs、review/score refs、as_of、前一状态、consecutive_high_sessions；警报另含幂等键、policy refs、last_alert refs。M09只按M05/M07事实归档/派生状态，不计算因子或许可 |

约定M09 OpportunityEvent升级3.0.0、MachineAssessmentLink升级2.0.0，旧2.x/1.x只读。ReviewContext身份为规范内容SHA-256；各已有合同身份继续复用canonical_fingerprint，包含新版本、当前输入、原事件、政策和业务字段，不包含generated_at。相同业务身份不同内容失败；同一watch/as_of/policy出现冲突来源作为revision追加明确supersedes，不覆盖原件，不发第二次当日警报。所有ref须解析到相同instrument/原事件/路径，当前事实日期一致；禁止以旧Gate日期放宽M04同日校验。

复评新方向/资格事实以registry下一主版本登记，现有因子检测函数和ID保持原版本；新增事实ID固定为`direction.macd_state.{daily,weekly,monthly}`、`qualification.monthly_high_zone`、`qualification.long_base_pullback`，只有direction.macd_state.monthly按第4节明确替代一次性月金叉计分；其余新增事实不计分。ReviewContext只承接事实日期/身份，不构造passed=true Gate，也不向M08发交易授权。当前无formal来源不能将legacy原提名伪装formal：legacy观察/历史comparison单列路径，新增正式轨只从首个完整授权日建立；跨路径禁止直接引用升格。

## 7. 持久化、失败与历史边界

复用M09现有只追加内容寻址存储、M12已审Manifest/收据/跨任务租约，不建新数据库/锁框架。单次D批次先保存context/evidence/assessment/score，再保存M09状态/警报与RankingSnapshot；发布只在引用全集校验通过后切换。状态索引是可重建派生缓存，不能比不可变记录先提交；部分成功重试按幂等键补齐，不重复名额/连续天数/警报。

原始行情、来源版本、会话日历、稳定身份缺失或冲突：该证券unavailable、保留旧结果但明确旧日期，不能沿用成今日分；整批Manifest必要文件缺失不发布半批。已知失格与证据不可用分开，不从缺数据推断技术空头。补到缺失日后仅追加当日修订/对照，不补发过去高分警报、不倒改当时用户看到的记录；恢复连续性按实际已完整保存会话计算。

旧提名导入持续观察列表可保留legacy原身份及原字节，只为拥有相应D完整行情的日期生成明确legacy_comparison复评；旧11896事件不得倒填新政策分数或formal来源。当前未補齐8/31—9/3，不把169历史sessions说成连续无缺口。

## 8. 旧回测与外部项目的最小实用接入

沿[M10既有设计](M10_UNIFIED_EVALUATION_RESEARCH_ENGINE_DESIGN_ZH.md)comparison边界，不另选平台。用户最小操作目标：在现网站选择已有政策版本/日期范围→启动固定实验→看到排队/运行/缺失/失败/完成→查看新旧分组、失败案例→点证券看原提名与当日复评/排除理由。首版不让用户写代码，不做任意脚本编辑器，UI在评分包之后单独审核。

- [VectorBT from_orders/from_signals](https://vectorbt.dev/api/portfolio/base/)只作为隔离对照适配器：锁定原行情、信号、入场/退出与费用政策，逐笔核对日期、价格、费用、退出原因。默认成交规则不能替换Sage口径。沿原X1版本/依赖隔离，[许可证](https://github.com/polakowo/vectorbt/blob/master/LICENSE.md)为Apache2+CommonsClause；本轮无安装/采购或新平台切换，商业用途仍遵原许可边界。
- [QuantStats HTML报告](https://github.com/ranaroussi/quantstats)需一致的资本收益序列；现M10-C没有批准资本政策，首版不拼假净值/组合Sharpe。先用M10逐信号收益、相同窗口基准差、MAE/MFE、分组/失败样本；资本政策以后具备才接组合报告，不能拿事件平均收益当组合总收益。
- 借鉴[Freqtrade lookahead-analysis](https://www.freqtrade.io/en/stable/lookahead-analysis/)截断重算法，逐D截断输入后同一事实/许可/分数必须一致；不引入全平台。
- 已核旧实验：`timeframe-score-v3.0.0-2026-08-28`在当前experiments.jsonl为pre_registered/Not run，1/1.5/2未获证实；`score-monotonicity-factor-attribution-v1.0.0-2026-08-29`为in_progress，11896为冻结旧Tracker事件而非中性全池，100日结果缺；`winner-loser-strategy-optimization-v1.0.0-2026-08-29`为completed_not_validated，2025/2026候选合分未通过且含旧EMA200门票。这些仅作原版本基准/反例，不证明新方案有效；已看过2025/2026不得再称未见样本。新两背景全池与每日复评必须按对应as_of完整行情真正重放，不能旧池换标签。
- 同账本后续完成记录必须同时报告：`score-timeframe-attribution-v2.0.0-2026-08-29`为completed_research_only，62170审计事件/13296主样本，等权和V3均未通过2025、31附加因子零验证通过；不能用较早V3预登记Not run概括全部周期研究未运行。`macd-factor-history-v2.0.0-2026-08-29`为completed_research_only，57271历史候选/6539会话；8%追踪全期提高胜率中位数，开发期与2025均收益/PF稍降，2026相关指标全面改善。它提供用户回忆的相关原版本研究线索，不直接证明“深套减少/alpha下降”这两个具体指标，更不代表新月周许可、两背景、持续复评政策已验证。保持事件/主样本/会话与收益/PF/alpha各自口径，不跨实验拼结论。
- 固定对照先用同源相交样本：旧冻结政策、只加方向/背景许可、再加加权分、最后加持续复评观察。持仓/成本仍固定同一既有执行政策，不借本包优化退出；单票重复review不是独立交易样本。初次提名、持续合格天数、恢复和警报分别统计，警报不自动生成新交易。
- 报告同时列收益、相对基准、风险调整后表现、回撤/尾部损失、覆盖与样本；没有资本政策的组合指标明确unavailable。旧版“深套减少而收益/alpha下降”仅在核对具体实验/版本/成本后引用，不能当新方案结论。旧结果原样留档；负结果、不足样本和缺失不得隐藏。不预先宣布哪种收益风险取舍更优。

## 9. 验收反例、迁移与回退

下列为实施验收要求，尚未运行；不是本设计已验证策略。

1. 月正柱1.0→0.8：周日再强也blocked。月负柱−3→−2→−1：可进入下一层；0.2→−0.1刚死叉blocked；零/平负柱不偷算改善。
2. 月允许，周P=1、当前0.5且缩短：允许且周分×0.75；周当前0.1且缩短：按含等号阈值blocked。负柱变长不被当改善。
3. C=0.95H_obs正好边界blocked；远离月EMA20正好20%不因该项阻断；指标分位仅用先前月份，深负柱不误作正向高位。有限历史只标已观测高位；低于0.95H_obs可证明远离全历史高位，不额外强制IPO覆盖。
4. 旧EMA200不通过但固定筑底样本通过新OR背景且回调/许可成立：不得被旧baseline排除。高位突破不选；回调中尚无局部突破不因此排除。
5. A的(T_M,T_W,T_D)=(0.6,0.5,0.1)，B=(0.5,0.5,0.8)，均许可：A=48.3333、B=55，B在前；方向blocked者即使诊断分100也不排名。父子/EMA重复不越组/家族封顶。
6. D初次提名→D+1无金叉仍复评→D+2失格停排名/警报→D+3恢复无需新金叉；只一首次提名，全部日期原件不变，恢复不是交易重入。
7. 高分第一次报、冷却内持续高分不再报、满5会话可报；失格/缺失停止并中断连续计数，恢复不绕过冷却；任务重跑/版本切换不重复当日警报。
8. 评分coverage低于80%不可用，达到80%可partial排名但不报警（12组实际离散边界为9/12不可用、10/12可partial）；100%且分>=60与2家族才满足网站高分。方向数据缺失不能被coverage容忍。
9. 补数、revision、跨任务部分提交重试、错证券/错日期refs、legacy升格、未来月K均失败关闭或追加明确修订；同身份不同内容拒绝。
10. 初始日与每日review共享同一评分/事实入口，截断重算一致；旧1.x/2.x政策和公开文件字节不变。对照引擎逐笔不一致则报告comparison_failed，不替换权威结果。

迁移先留旧生产默认；新schema和policy只在显式新版本路径运行，历史只comparison。新榜接受正式切换必须有审核提交、版本生效日、同日完整输入、M12既有发布收据，不把“推进”当上线授权。回退撤销新政策激活/网站指针到上一完整已核版本，保留所有新旧记录及失败结果，不反向覆写策略分数。CR036延长持仓、CR057卖空、资本模型和其他执行优化不在本包。

## 10. ≤20分钟可审工作包（实施须另获批准）

| 包 | 范围与完成判据 |
| --- | --- |
| A0 | 先用既有来源归档实报可计算/缺失数量与原因，尤其61月窗口/必需结构证据；零可计算不是交付完成，只补既有授权来源缺失窗口或证据，不新供应商、不伪造数据 |
| A1 | 注册候选配置/名单指纹与schema，唯一validate_contract正反例，旧合同只读 |
| A2 | M03 ReviewContext与旧Gate区分、M04同源复评日期/身份，不伪造金叉 |
| B1 | M04完整周期MACD/高位基础事实与截断反例 |
| B2 | 两背景、回调/结构与M05唯一许可，筑底非EMA200路径反例 |
| C1 | M07分组封顶/3-2-1公式/缺失覆盖/确定性排序 |
| C2 | M09提名/复评/失格/恢复只追加及两榜子视图 |
| C3 | 网站警报事实/冷却/幂等；无通知发送 |
| D1 | 固定新旧comparison样本、版本与覆盖报告；不批量重跑全部历史 |
| D2 | 原VectorBT隔离适配器逐笔对账小样本；未授权运行前仅实现可注入接口 |
| E1 | 现有多因子页两榜/状态/详情最小消费，测试版可审，不加独立看板 |
| E2 | 固定实验启动/结果只读入口与失败可见性；沿原任务/收据，不开放任意脚本 |
| F | 整理定向证据、迁移与回退预览，交独立审核；生产切换另获上线批准 |

超过20分钟的包按合同/生产器/消费测试继续拆分，不能以一包为名扩写。新增业务文件仅落现有gates/factors/selectors/ranking/ledger与contracts；对照沿research/M10，发布沿原M12和页面，无第二套行情/指标/评分引擎。治理实施时同步对应02/03/04/07模块规则及版本、决策、验收；本次只修改本卡和CR登记。

## 11. 本次文档检查（非实施验收）

仅本卡与CR账本更新，未提交/推送。19项规则合同/项目状态检查通过；固定白名单核13个既有candidate ID/周期及1个明确提议的新月线状态，组数与K_D=5/K_W=2/K_M=3.25、A/B分48.3333/55机械核算通过；两文档本地链接与差异格式通过。上述第9节业务反例尚未执行，新参数/策略未回测、未部署，不将文档通过等同实施通过。

## 12. 当前实施授权与A0证据

2026-09-07用户上述原话由独立审核任务转交为本方案实施授权。优先可复用后台产物，每票保存分项、许可/排除、覆盖与日期；不以UI重做为前置。A0本机eod-recovery与共享M12工作树的work/eodhd-cache、eodhd-bulk均0文件/0字节；9/4公开因子48只、Tracker89只图表各60日，不能满足61月重算。原行情当前本地可计算0不是合格新榜；远端daily已有eodhd-history-v1缓存，由审核任务统一协调既有缓存取得。保留缺失原因，不重复真实生产dispatch、不新供应商。执行方继续规则/预登记及可注入入口，缓存到位后以同入口计算新结果。
