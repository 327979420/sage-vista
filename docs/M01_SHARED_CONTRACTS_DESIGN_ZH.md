# M01｜共享数据合同与发布清单设计

- 模块状态：`implemented`；包A—E及D1/D1b/D1c已完成并fast-forward进入`main`
- 对应需求：`CR-2026-08-31-039`
- 基线提交：`e12edc9a807e009c52ac4f99092f6763b0a1110d`
- 审计样本数据日：`2026-08-28`
- 边界：本文件是设计，不是实施许可；不改变M00、CR-035或CR-037状态。

## 人话版

现在像是厨房、仓库和收银台各自给同一种东西贴标签：有的写`version`，有的写`schema_version`，日期和“没有偷看未来”也不总在同一位置。每个页面又自己拿一张购物清单，所以一批文件只换了一半时，大家可能看到不同的一天。

M01准备做两件事：第一，规定每种数据盒子的标签和验货规则；第二，在本地或CI给每天的一箱文件制作影子装箱单。装箱单列出每件文件的日期、合同版本、字节大小和SHA-256指纹。少一件、日期不同、指纹不同、偷看未来或遇到不认识的主版本，影子验货必须判失败。真正让生产“整箱不发”属于M12，不在M01实施。

这不等于制造十份新JSON。十类名称是共同语言：有些是核心实体，有些只是实体里的小格子，有些只是给网站看的紧凑视图。现有JSON先原样保留，由唯一的只读适配层翻译；翻译器不能改写历史，也不能凭空补事实。

## 已确认设计选择

1. **选择1A：中立合同层。** 未来代码统一放在`services/contracts/`，供生成器、回测、发布和核验共同使用，不属于扫描器私有逻辑。扫描器和回测不得复制合同定义；网站只消费已经验证的JSON输出和未来生产Manifest，不维护另一套Python合同或转换逻辑。
2. **选择2A：完整生产包并标用途。** ReleaseManifest覆盖完整生产发布包，每个文件标注`web`、`discord`、`audit`中的一个或多个用途。用途不等于加载要求：网页只加载自己的轻量文件，完整历史和审计文件不得因此进入页面首屏。
3. **选择3A：严格只读兼容。** 现有旧格式持续只读，历史文件不改写；新格式只接受已知主版本，未知主版本失败关闭。同一主版本新增可选字段可以兼容，但任何适配器都不得猜测缺失事实。

## 包A冻结结果

- 唯一规范入口：本文件保存十类合同、共同字段、版本兼容、稳定ID、影子Manifest和测试要求；`docs/rules/02_DATA_AND_SCAN.md`只保存长期有效的强制规则并引用本文件，不再复制一套详细字段表。
- 未来唯一代码入口：`services/contracts/`。生成器、回测、适配器、影子发布和核验共同调用；扫描器内部不得建立平行合同包。
- 网站边界：网站未来只消费经过共享合同层验证的JSON和M12生产Manifest，可以保存展示类型，但不得自行推断缺失字段、转换旧格式或复制Python合同语义。
- 版本边界：`schema_version`、`adapter_version`、`source_version`各司其职；未知合同主版本失败关闭，同主版本只允许向后兼容的可选新增。
- 影子边界：M01输出只能存在于测试临时目录或被Git忽略的`work/`；不得写入`public/`，不得进入生产构建。
- 生产边界：M01完成不改变现有网站、Discord、工作流、生产JSON或线上核验；所有真实接入仍属于M12。
- 实施状态：包A规则、包B验证器、包C只读适配器、包D影子Manifest、D1/D1b/D1c安全修复及包E本地验收均已完成。三个提交`6f5fbb0`、`1017490`、`ca52a72`已进入`main`。M01的完成定义不包含生产接入，因此可标为`implemented`；生产尚未采用Manifest。
- 发布文件按时间语义分三类：`daily_snapshot`必须与发布日相同且防未来明确为`false`；`versioned_config`不伪造`as_of`或`future_data_used`，改查版本引用一致；`research_summary`不要求等于发布日，改查研究覆盖末日不晚于发布日并保留来源实验。

## 一、现状审计

### 1. 当前生产链为什么容易分叉

- 每日生成器先在临时目录生成并检查一组文件，再逐个替换公开文件；`unified-v2-*`和机会总账随后由其他步骤生成。因此单次脚本内部较安全，但整个网站发布包没有共同身份。
- 网站四个入口、Discord和线上核验各自列出要读取的文件并各自解释字段，没有唯一发布清单。
- 日期有`as_of`、`coverage.end`、`date`、`signal_date`、`first_seen_date`及多个`*_as_of`；它们含义不同，但目前没有统一合同说明。
- 版本有`version`、`schema_version`、`signal_schema_version`、`model_versions`、`registry_version`、`pattern_version`和`membership_version`。业务版本与结构版本容易混在一起。
- 防未来字段大多叫`future_data_used`，机会总账使用`selection_future_data_used`，个别紧凑视图没有自己的明确声明。
- `event_id`、`signal_id`和`experiment_id`已经存在，但快照、证据、评估与发布包缺少统一稳定ID规则。

### 2. 当前权威产物与使用者

| 当前产物 | 唯一生产者/权威来源 | 主要消费者 | 已有证据 | 主要缺口 |
|---|---|---|---|---|
| `public/update-status.json` | `daily_tracker_update.py` | 网站、Discord、线上核验、状态报告 | 多个数据日、检查结果 | 无结构版本、生成时间和来源版本 |
| `public/daily-factor-snapshot.json` | `factor_snapshot.py` | 统一扫描、网站、每日链、核验 | `as_of`、注册表版本、门票、因子证据、防未来 | 无统一快照ID；结构与业务版本混杂 |
| `public/unified-v2-latest.json` | `unified_v2_scan.py` | 首页、机会页、核验 | 覆盖日、模型版本、规则集、候选与计划视图 | 用`version`而非明确结构版本；是组合视图，不应成为原始事实库 |
| `public/favorite-pattern.json` | 每日跟踪器生成的紧凑视图 | 独立形态页面、核验 | 形态版本、数据日、候选 | 根层缺统一防未来、生成时间和结构版本 |
| `public/market-etf-watch.json` | `market_etf_watch.py` | 网站、统一扫描、历史记录、核验 | 结构版本、时间、数据日、防未来 | 无稳定上下文ID |
| `public/industry-radar.json` | `industry_radar.py` | 网站、统一扫描、历史记录、核验 | 结构/成员版本、时间、数据日、防未来 | 体积大；同时承担事实与网站视图 |
| `public/opportunity-ledger.json` | `opportunity_ledger.py` | 历史复盘、核验 | `event_id`、信号日、来源、机器证据、内容哈希 | 防未来字段命名特殊；历史事件形态先保留，不能强行重写 |
| `public/opportunity-ledger-latest.json` | 同上，由完整账本裁出的视图 | 网站、核验 | 与完整账本同源、视图范围 | 只是视图，不是第二本总账 |
| `public/signal-history.json` | `signal_history.py` | 机会账本、核验 | `signal_id`、不可变指纹、版本、前瞻审计 | 旧ID语义与未来“一股一日一事件”合同未完全一致 |
| `public/signal-history-summary.json` | 每日跟踪器从完整历史压缩 | 首页、核验 | 数据日、防未来、紧凑案例 | 缺结构版本、生成时间和来源版本 |
| `automation/production-state.json` | 已核验部署收据写入器；Discord只更新自己的结果 | 状态报告、部署流程 | 网站版本、部署提交、数据日 | 是部署收据，不属于公开业务数据包 |
| `automation/backtest-state.json` | 回测进度模块/工作流 | 状态报告、回测续跑 | 批次ID、模型版本、覆盖、下一窗口 | 是运行状态，不是生产发布文件 |
| `research/experiments.jsonl`、`experiment-events.jsonl`、`generated/experiment-catalog.json` | 追加账本；目录由`experiment_catalog.py`唯一生成 | 研究工具、状态和合同测试 | 实验ID、生命周期事件、目录结构版本 | 历史记录存在多代字段，只能版本化适配 |

`factor-registry.json`、`rare-opportunity-radar.json`、`resonance-tracker.json`、`unified-v2-rankings.json`和`decision-summary.json`仍被当前生产页面、每日链或核验使用。它们虽不是十类合同各自的一一对应物，也必须在发布清单迁移审计中登记，不能被遗漏。

## 二、共同字段冻结建议

下列规则适用于真正落盘的合同根对象；嵌套结构继承根对象证据，不机械复制所有字段。

| 字段 | 规则 |
|---|---|
| `schema_version` | 合同结构版本，使用`MAJOR.MINOR.PATCH`；不得用模型版本代替。 |
| `adapter_version` | 仅在旧格式经过适配时记录适配器版本，例如`legacy-adapter-1.0.0`；不是合同结构版本。原生新合同可不含此字段。 |
| `as_of` | 该事实允许使用信息的截止数据日，严格`YYYY-MM-DD`。它不是生成时间。跨期实验中指证据截止日，并另存开始/结束日。 |
| `generated_at` | 生成本产物的UTC时间，ISO 8601并带`Z`；只用于追踪，不参与交易判断。 |
| `source_version` | 业务模型、数据政策或生成逻辑的可追溯版本；可由模型、规则、数据供应/复权政策组成，但结构必须由各合同固定。缺失不能拿本地常量冒充。 |
| `future_data_used` | 必须是布尔值。生产发布只能是明确的`false`；缺失、`null`、字符串或`true`均失败关闭。 |
| 稳定ID | 同一事实重复生成必须得到同一ID；显示顺序、生成时间或文件位置不得改变ID。不同实体使用不同前缀。 |

推荐ID：快照由`类型+as_of+来源/政策版本`组成；门票事件为`symbol+signal_date+gate_policy_version`；技术证据在门票ID后加`factor_id+timeframe+evidence_date`；模型评估、计划分别在事件ID后加模型或执行政策版本；机会事件采用`symbol+signal_date+gate_policy_version`保证同一股票同一天同一门票只产生一个事件；发布ID由规范化文件条目内容计算；实验继续使用现有`experiment_id`。

## 三、十类目标合同

| 合同 | 职责与生产者 | 允许读取者 | 必填字段（除适用的共同字段） | 禁止内容 | 落盘与当前对应 | 旧数据兼容 |
|---|---|---|---|---|---|---|
| `MarketDataSnapshot` | 点时行情事实；未来由M02市场数据入口唯一生产 | 股票池、门票、回放；网站只读派生结果 | 市场、交易日、标的、OHLCV/调整政策、数据源、快照ID | 因子分数、候选、交易判断 | 核心实体；M01不新落盘，当前行情缓存/供应源仅作引用 | 缺少完整来源或复权政策时标未知并禁止冒充完整快照 |
| `UniverseSnapshot` | 某日可扫描股票池及纳入/排除理由；未来由M02唯一生产 | 门票、回测、审计 | 股票池ID、成员、资格日、规则版本、排除原因 | MACD结果、模型评分、人工结论 | 核心实体；当前由因子快照中的股票集合和资格统计部分对应，暂不独立公开 | 适配只能声明可确认成员；不能反推不存在的排除理由 |
| `GateEvent` | 一股一日的共同日线MACD门票事件；门票模块唯一生产 | 两个分析器、事件账、回放 | `gate_event_id`、symbol、signal_date、gate_policy_version、passed、门票证据引用 | 多因子总分、喜爱形态结论、市场/行业判断、退出结果 | 核心事件；现由因子快照`trigger`部分适配，未来随事件落盘 | 旧触发记录缺证据时明确不完整；不补造通过理由 |
| `TechnicalEvidence` | 对门票或模型使用的单项技术证据；因子/技术生产者生成 | 模型评估、审计、回放 | `evidence_id`、factor_id/version、timeframe、evidence_date、available、value/evidence、lookahead结果 | 市场、行业、人工判断、交易结果 | 嵌套结构；当前因子快照`symbols[].factors[]`对应，不单独公开落盘 | 继承父级日期与生成证据；缺失值保持未知，不能默认命中 |
| `ModelAssessment` | 复杂多因子或喜爱形态对同一门票的独立分析 | 排名、事件账、网站视图 | assessment_id、gate_event_id、model_id/version、eligible、分项结果、分数/排名（仅适用模型） | 把两个模型合并成竞争主榜；人工覆盖原分数 | 嵌套结构；统一扫描和喜爱形态JSON可部分适配 | 两个模型分别适配；不因字段相似而合并语义 |
| `ContextSnapshot` | 独立保存大盘或行业上下文 | 模型、交易就绪、网站、复盘 | context_id、context_type、as_of、规则/成员版本、状态、证据 | 技术评分、人工否决、退出结果 | 核心快照/事件引用；对应市场ETF与行业雷达，可继续现有落盘 | 两个文件分别进入唯一适配入口，不把行业状态塞进市场状态 |
| `TradePlan` | 只有达到交易标准时保存执行计划 | 模拟交易、事件账、复盘；网站只读紧凑视图 | plan_id、opportunity/gate引用、entry、stop、size/risk、execution_policy_version、status | 未达标候选的虚构计划；实际成交或退出结果 | 事件内嵌结构；当前`support_plan`和执行政策只能部分适配 | 缺少关键价格/政策则为无完整计划，不补默认值 |
| `OpportunityEvent` | 同一股票同一天唯一候选事件，组合机器原证据并追加人工/结果层 | 总账、回放、案例、网站视图 | event_id、symbol、signal_date、gate、两模型独立区、上下文引用、机器时间/证据、来源 | 覆盖机器证据；把人工结论写回模型；重复事件 | 核心且不可覆盖；对应机会总账/信号历史，`latest`与summary只是视图 | 保留原`event_id`/`signal_id`；冲突列入迁移报告，禁止静默合并或改写历史 |
| `ReleaseManifest` | 一次发布包的唯一装箱单；M01仅由影子生成器在本地/CI生成，M12才接入生产 | M01验证测试；未来M12的构建、部署、线上核验、网站和Discord | manifest schema、release_id、as_of、generated_at、source_version、future=false、文件条目 | 股票计算、页面展示结论、Discord发送结果 | 发布核心；M01只写临时目录或被Git忽略的`work/`，不进入`public/` | 没有Manifest时当前生产继续原样运行；不能伪造Manifest |
| `ExperimentRun` | 预登记假设、变量、数据窗口、运行与结论 | 研究、审核、目录生成；生产不得直接采用 | experiment_id、合同版本、状态、预登记时间、证据截止/窗口、代码/规则版本、输入引用、结果引用 | 未批准的生产规则、改写历史事件、无来源结论 | 研究核心；现有JSONL为权威、catalog为可再生视图 | 按记录版本只读适配；目录不得成为第二本实验账 |

## 四、版本与唯一适配规则

1. `MAJOR`：删除/重命名字段，改变字段类型或业务含义，把可选改必填，改变稳定ID算法，或改变失败关闭语义。读取者遇到未知主版本必须失败关闭。
2. `MINOR`：只增加可选字段、可选枚举值或不改变旧含义的新能力。同主版本读取者可以忽略自己不认识的可选字段，但不得忽略未知的必填能力声明。
3. `PATCH`：文档澄清、排序或不改变合同含义的修正。它不能掩盖结构变化。
4. `schema_version`只保存合同结构版本；`adapter_version`只保存旧格式适配器版本；`source_version`只保存业务模型、数据政策或生成逻辑版本。三者不能互相冒充，Manifest根对象和每个文件条目遵守同一规则。
5. 每个旧文件只有一个注册入口：`legacy file -> named adapter -> canonical validation result`。网站、扫描器、回测和每日链不得各写一套转换。
6. 适配器只读原字节，不回写、不迁移大型历史JSON、不改变旧ID。缺失的可选事实输出明确`unknown`；缺失的安全必填项直接失败。
7. 适配结果必须带来源文件、来源结构识别结果、`adapter_version`及适配警告。无法识别旧版本时不猜。
8. M01中新合同或影子Manifest验证失败只让影子验证失败，不得影响当前生产。M12未来接入后，才由同一失败结果阻止新发布。

## 五、ReleaseManifest正式设计

### 1. 装箱范围

已确认采用“完整生产包+角色”，而不是只列网页眼前使用的文件：

- 必需的紧凑运行视图：`update-status.json`、`factor-registry.json`、`daily-factor-snapshot.json`、`unified-v2-latest.json`、`favorite-pattern.json`、`market-etf-watch.json`、`industry-radar.json`、`opportunity-ledger-latest.json`、`signal-history-summary.json`、`rare-opportunity-radar.json`和`decision-summary.json`。
- 必需的当前审计/历史产物：`resonance-tracker.json`、`unified-v2-rankings.json`、`opportunity-ledger.json`和`signal-history.json`；它们可标为非浏览器加载，但仍属于同次生产发布。
- `automation/*`和`research/*`不属于网站发布箱。可选文件必须在Manifest中显式写`required:false`及用途；第一版不建议默认可选，以免掩盖遗漏。
- `web`、`discord`、`audit`只是消费用途标签。Manifest覆盖完整包，不表示网页要下载完整包；网站首屏只加载其明确需要的轻量条目。
- `factor-registry.json`分类为`versioned_config`：它是因子说明书，不是某日行情，不要求`as_of`或`future_data_used`；Manifest必须核对其`registry_version`与当日因子快照及模型引用一致。
- `decision-summary.json`分类为`research_summary`：它是历史研究报告，不是每日选股输入，不要求日期等于发布日；Manifest必须确认`coverage.end`不晚于发布日并保存来源实验编号。扫描、评分和排行明确禁止读取它作为输入。
- 其余随每日生产更新的文件分类为`daily_snapshot`，日期必须等于发布日且防未来证据必须明确为布尔`false`。

M01影子生成前必须用当前工作流和四个网站入口再次生成精确清单；漏项会令影子验证失败。真正阻止生产切换的接入由M12实施。

### 2. 文件条目与校验

每项记录：相对路径、合同名称、合同结构`schema_version`、业务/生成来源`source_version`、旧文件适用时的`adapter_version`、`as_of`、字节大小、精确文件字节的`sha256`小写十六进制值、`required`、角色（web/discord/audit）和可选记录数。三种版本字段不得互换。哈希算法固定为SHA-256；不得对重新解析后的JSON哈希。

Manifest根对象包含自身`schema_version`、`release_id`、`as_of`、`generated_at`、生成逻辑的`source_version`、`future_data_used:false`和文件条目。`release_id`由规范化文件条目计算，避免使用生成时间；Manifest不把自己的哈希递归写入自己，也不尝试预先写入包含它的最终Git提交。部署构建与部署收据负责把Manifest原始字节的SHA-256、线上地址和实际部署提交绑定起来，用来核验Manifest自身且避免提交自引用。

所有必需文件都必须存在且大小、SHA-256和已知结构版本通过。`daily_snapshot`的业务截止日必须等于Manifest的`as_of`且防未来明确为`false`；`versioned_config`按版本引用一致性检查；`research_summary`按覆盖末日和来源实验检查。不能把某一类缺少的字段用另一类规则补造。历史覆盖的开始日可以不同，但每日快照的生产末日必须一致。

### 3. M01影子生成位置与顺序

1. M01只读取现有样本，在临时目录或被Git忽略的`work/`建立影子候选目录；不得写入生产`public/`。
2. 逐个通过唯一适配器转换并执行合同验证，再对候选发布字节计算大小和哈希。
3. 最后在影子目录生成Manifest并验证自身结构。
4. 影子Manifest不参与网站构建、工作流、Discord或线上核验；当前生产JSON和读取入口保持原样。

缺文件、错日、未来数据不为明确`false`、未知主版本、重复稳定ID、大小或哈希不一致，均令M01影子验证失败。M12接入生产以后，这些错误才停止新发布，不能降级成警告后继续。

### 4. M01与M12边界

M01只负责：冻结共享合同规范；建立纯合同验证器；建立旧JSON唯一只读适配器；在本地或CI影子生成ReleaseManifest；用现有`2026-08-28`样本完成兼容和失败关闭测试。M01结束时，当前网站、Discord、工作流和生产JSON仍原样运行。

M01明确不修改`daily-eod.yml`、`deploy-site.yml`、网站或Discord读取入口、线上核验流程；不创建真实生产Manifest；不从候选目录部署；不做生产切换、真实部署或回退演练。

以下想法完整保留为**M12未来集成任务**，必须另行设计和批准：

1. 每日生产链改用不可变候选发布目录。
2. 生成真实生产ReleaseManifest。
3. 网站按Manifest和`release_id`读取轻量文件。
4. Discord按同一Manifest和`release_id`读取。
5. 线上核验逐项检查Manifest、文件日期、大小和哈希。
6. 执行受控生产切换。
7. 执行真实部署和回退演练。

M01可以冻结M12需要的接口，但不得实施或声称上述生产集成已经完成。

## 六、测试与验收设计

必须覆盖：缺必填字段；各文件数据日不一致；`future_data_used`不是布尔`false`；未知主版本；稳定ID重复；同一股票同一天同一门票版本出现两个`OpportunityEvent`；Manifest缺必需文件；大小或SHA-256不一致；旧JSON能通过其唯一适配器；转换前后原文件字节完全一致；当前`2026-08-28`样本能够只读适配；M01迁移开关关闭时网站旧数据不受影响。

补充验收：多版本批次不得静默挑选；缺失证据保持未知；Manifest自身主版本未知时失败；可选文件缺失必须显式记录而非假装存在；影子Manifest的用途标签与文件清单完整；Opportunity旧ID冲突只报告不改写。网站、Discord和核验使用同一`release_id`属于M12验收，不冒充M01结果。

## 七、三个精简结构示例

示例只解释结构，不代表当前生产已经采用，也不改变门票、评分或交易规则。

### `GateEvent`

```json
{
  "schema_version": "1.0.0",
  "as_of": "2026-08-28",
  "generated_at": "2026-08-28T22:00:00Z",
  "source_version": {"gate_policy": "existing-policy-id"},
  "future_data_used": false,
  "gate_event_id": "gate:ABC:2026-08-28:existing-policy-id",
  "symbol": "ABC",
  "signal_date": "2026-08-28",
  "passed": true,
  "evidence_refs": ["evidence:gate:ABC:2026-08-28:existing-policy-id:macd:daily:2026-08-28"]
}
```

### `OpportunityEvent`

```json
{
  "schema_version": "1.0.0",
  "as_of": "2026-08-28",
  "generated_at": "2026-08-28T22:05:00Z",
  "source_version": {"model": "existing-model-version", "ruleset": "existing-ruleset-id"},
  "future_data_used": false,
  "event_id": "opportunity:ABC:2026-08-28:existing-policy-id",
  "symbol": "ABC",
  "signal_date": "2026-08-28",
  "gate_event_id": "gate:ABC:2026-08-28:existing-policy-id",
  "model_assessments": {"complex_multi_factor": {}, "favorite_pattern": {}},
  "context_refs": [],
  "trade_plan": null,
  "human_review": null,
  "outcome": null
}
```

### `ReleaseManifest`

```json
{
  "schema_version": "1.0.0",
  "release_id": "sha256:example-content-derived-id",
  "as_of": "2026-08-28",
  "generated_at": "2026-08-28T22:10:00Z",
  "source_version": {"generator": "contract-and-generator-version"},
  "future_data_used": false,
  "files": [
    {
      "path": "update-status.json",
      "contract": "UpdateStatusLegacyView",
      "schema_version": "1.0.0",
      "adapter_version": "legacy-adapter-1.0.0",
      "source_version": {"generator": "existing-generator-version"},
      "as_of": "2026-08-28",
      "size_bytes": 845,
      "sha256": "example-lowercase-sha256",
      "required": true,
      "roles": ["web", "discord", "audit"]
    }
  ]
}
```

## 八、影响、不影响、风险与回退

M01会影响的边界：未来的共享合同规范、生成器和回测可共同调用的纯验证接口、旧JSON只读适配以及本地/CI影子Manifest。网站数据加载、Discord、每日工作流、部署打包和线上核验只预留接口，实际变化全部属于M12。

明确不影响：MACD门票定义、当前有效因子集合及数量、评分、主榜、精选门槛、喜爱形态、大盘/行业判断、止损止盈、持仓、历史事件、回测结论及M00/CR状态。本设计不制造任何股票结论。

最大风险是把现有异构历史强行“洗成整齐数据”，从而悄悄改变事实；其次是Manifest清单漏掉隐藏消费者。防护是只读适配、逐文件来源登记、影子运行、字节不变测试和消费者全清点。M01没有生产切换，因此回退只需撤销M01代码提交或停止影子任务；当前旧JSON、网站和工作流始终不动。真实部署回退方案留给M12。

## 九、未来小工作包（每包预计不超过20分钟）

1. **包A：规则和合同规范冻结。** 经用户批准后更新规则与接口规范，冻结`services/contracts/`、三种版本字段、稳定ID和影子发布成员。
2. **包B：纯验证器及失败关闭测试。** 在`services/contracts/`实现不依赖生产I/O的合同验证。
3. **包C：旧JSON只读适配器。** 每次只接一组相关文件，验证原字节不变，不猜缺失事实。
4. **包D：影子ReleaseManifest。** 只在临时目录或被Git忽略的`work/`生成，并用`2026-08-28`样本验证。
5. **包E：M01完整本地验收、提交和文档证据。** 不部署、不触发Actions、不改生产。

包A—E及D1/D1b/D1c均已完成本地实现、验收和提交。验收证据：363项Python测试；前端lint、类型检查、生产构建及11项本地测试；四种固定`PYTHONHASHSEED`；15项影子包及固定release_id全部通过。原设计中的每日链、网站、Discord、线上核验、生产部署和回退演练仍属于“M12未来集成任务”，没有删除且尚未开始。

## 十、M01完成标准

M01达到`implemented`只代表：合同定义完成；验证器完成；旧数据只读适配完成；影子Manifest能够生成和验证；测试通过；代码和文档已提交并进入`main`。

它不代表生产已经改用Manifest，不代表网站或Discord已经切换，不代表每日工作流已经改变，也不代表线上已经发布Manifest。当前没有生产Manifest；这些生产状态必须等待M12独立批准、实施、部署和线上核验。M02尚未开始。

本轮三个设计选择已经全部确认，当前没有遗留的二选一设计问题。实施过程中如果发现合同含义、发布成员或M01/M12边界需要扩大，必须停止并返回`design_review`，不能自行决定。
