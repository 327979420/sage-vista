# M12｜完整生产链路最小设计

版本：`0.2.0-draft`；日期：2026-09-06；状态：`design_review`。

关联CR-2026-09-06-053。用户仅授权设计补齐及独立提交，不授权实施、部署或生产启用。合并`14fef535f67b7c4de035b4c84224e604850f1fed`与治理`be1119e643ea9f5aa9f63dd25223ee6848dda1f5`已由用户确认通过独立审核；M11不重复审核，CR-043保持captured。本版替代0.1草案的未冻结技术选项，上线日期和实际部署授权留在上线卡。

## 1. 推荐方案与职责

采用**现有GitHub Actions运行Python业务链＋Cloudflare私有R2不可变对象＋一个SQLite-backed Durable Object协调器＋现有四页Worker**。M12唯一实现负责人为`services/publication/`，负责编排、只读投影、发布和收据；各上游模块仍各自唯一计算／校验业务事实。首轮只交付四页完整生产研究服务，不新增看板、策略优化或M13删除。

选择依据：R2适合长期保存行情、事件、结果和发布文件，直接读取具有强一致性；DO提供事务和跨请求持久状态，适合当前指针、互斥和追加链；现有项目已使用Cloudflare和Actions，无需再引入独立数据库服务器。R2不是多对象事务数据库，跨对象一致性通过“先写不可变对象，后由DO事务登记引用”实现。Git和Actions缓存不担任运行账本；缓存失效不能丢事件或断点。

技术依据：[R2一致性](https://developers.cloudflare.com/r2/reference/consistency/)、[SQLite-backed DO](https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/)、[R2锁定保留](https://developers.cloudflare.com/r2/buckets/bucket-locks/)。这是本设计推荐，不声称这些云资源已经创建。

完整链：同日成员来源与M02行情 → M03 Gate → M04事实 → M05模型 → M06上下文 → M07唯一研究排行 → M08研究计划／退出 → M09账本 → 到期任务登记；M10评价异步更新 → M12从冻结库存生成四页包 → 验证候选 → 发布切换 → 线上验证 → 通知。每日扫描不等待M10任务执行完。

## 2. 首轮真实股票池、身份与政策

### 2.1 数据来源与完整性

推荐唯一来源为现有EODHD账户；每个交易日D重新取得`exchange-symbol-list/US?delisted=0`完整响应，归档未过滤原始字节、请求参数（移除token）、抓取UTC时间、HTTP结果和哈希。按现有`audit_eodhd.common`固定范围取`Type=Common Stock`且`Exchange`属于`NASDAQ/NYSE/AMEX/NYSE MKT/NYSE ARCA`；不按缓存是否存在截断，不沿用1000只下载目标作为formal宇宙。原始全集及范围外记录保留，正式成员全集是该明确范围的全部记录，不宣称覆盖所有美股或退市历史。

EODHD US接口是聚合列表，active与delisted请求分离；它不是历史成员接口。[供应商接口说明](https://eodhd.com/financial-apis/exchanges-api-list-of-tickers-and-trading-hours)。完整性按供应商该非分页端点的成功全量响应、JSON完整解析、每行必需字段、重复／冲突检查、规范化前后计数与过滤审计证明；空列表、截断、未知交易所／类型不能默默排除为成功。两次相同哈希只能证明采集稳定，不能证明交易所现实中绝无遗漏。coverage的承诺仅限上述供应商报告范围。

成员采集必须在纽约交易日D内完成，记录实际观察日期，不把D+1抓取的当前列表标成D。复用现有EOD触发中D收盘后、纽约午夜前的窗口先保存成员源（现有23:47、次日00:17至03:17 UTC白名单在美东日期仍为D），价格尚未就绪可稍后重试；若这些窗口全部错过且没有D归档，则D formal unavailable，保留旧页面，不用次日名单补造。交易日／收盘时间使用现有交易日历，节假日不开新日。上线前演练必须确认现有触发窗口能覆盖此采集期，不另造第二条扫描链。

逐成员在M02形成同日资格：有效完整复权OHLCV、至少420个完整日、收盘价≥5美元、当日调整后收盘×成交量≥1000万美元，严格复用`gates/baseline.py`现有门槛；新资格配置标识`m12-eodhd-primary-common-1.0.0`。价格／流动性／历史不达标是明确排除；供应商请求失败、数据无法判定不是“淘汰”，而是资格未知，整个formal日失败。合法上市不足420日可在源证据完整时明确排除；不得把下载不全误写成短历史。已退市且仍有未结事件的证券作为评价输入继续跟踪，不加入当天活跃候选池。

成员身份复用`observed_instrument_id(provider,market,exchange,provider_code,observed_listing_epoch)`和`UniverseSnapshot 3.x`唯一验证。provider固定`EODHD`、market固定`US`，代码与交易所来自归档响应，epoch为首次成功完整观察的交易日，非IPO日期；identity_source指向原始响应哈希和过滤政策。DO的身份登记按日期升序串行处理完整每日集合，已有D+1身份根时不得用晚到D来源回写epoch；晚到来源仅作修订证据：连续观察保持ID，完整来源中消失后重现／换交易所／供应商重上市证据产生新epoch；采集失败日不算消失。冲突不猜测。ISIN可辅助检查，不单独决定合并。source_as_of=D、member_count和规范成员指纹由M02构造器核验；历史预热只服务D计算，不补造D以前的成员证据。

行情复用现有M02 EODHD读取／修订和`eodhd-adjusted-ratio-1.0.0`，原始历史按身份与修订内容寻址保存，消费者只读截止D的视图。M06首轮ETF集合固定现有注册表`SPY/QQQ/IWM/XLE/SOXX/BOTZ`；独立ETF状态可展示，有可靠带日期成员映射才关联个股，否则显示“成分关联不可用”。FinanceDatabase与旧主题ticker快照只能作为标注来源的旧分类参考，不冒充formal成员关系；上下文不改变本轮排名。

### 2.2 精确政策（均以14fef535内容为业务冻结基线）

| 模块 | 首轮选择 |
| --- | --- |
| M03 | `m03-shadow-1.0.0`，保持MACD门票及现有长期／局部结构定义，不重命名以暗示已上线 |
| M04 | 因子库`0.10.0`，`m04-factor-evidence-1.0.0` |
| M05 | selector=`m05-selector-assessment-1.0.0`；complex_multifactor=`1.0.0`，favorite_pattern=`3.0.0` |
| M06 | `m06-market-industry-context-1.0.0`、`m06-etf-state-1.0.0`；上下文贡献零 |
| M07 score | `technical_resonance_count 1.0.0`；指纹`sha256:3c9f4b0906aca617943a863f1c3dd47dcbb9fcfc6c66a0a7eab496df3ed8ccda` |
| M07 ranking | `technical_resonance_deterministic_order 1.0.0`；指纹`sha256:11637db181b6806db901c281c521e6ae2cdeb4d58be0f9af4822e505573d38e6` |
| M07 authority | `future_effective_append_only_authority 1.0.0`；指纹`sha256:c9fe70a2d2dab9651961dd882cb003d2bbccc18e6b2b066614693d422e75908e` |
| M08 | PLAN／EXIT=`1.0.0`，原`services/execution/policies.py`；下一调整开盘、支撑下5%、最大风险10%、2R／40日，无新持仓实验 |
| M10 | EVALUATION／PARTITION／AGGREGATION=`1.0.0`，FORWARD_WINDOW=`1.1.0`，窗口1/5/20/60/100；净收益缺可信成本则unavailable，Portfolio仍unavailable，不套零成本comparison为formal |
| M11 | 当前`2.2.0`合同只读展示四轴；本轮策略激活集合为空 |

配置归档上表完整政策对象与内容指纹，非政策对象的定义以`definition_commit=14fef535…`、仓库相对路径和Git blob绑定；实际运行`code_commit`另存M12实施提交，必须证明上游政策未漂移。不能只比较版本字符串或使用“main最新”。研究主排行排序固定total_score降序→timeframe_resonance_bonus降序→family_count降序→positive_hit_count降序→instrument_id升序，精选固定前5，为完整主排行的严格子集。它与旧生产按ticker／上下文同分排序存在差异，属于待上线批准的明确迁移选择，不承诺逐股完全等价，也不做参数优化。

### 2.3 合法授权及无validated时的功能

推荐首轮`publication_mode=research_only`。用户能看真实覆盖日／范围、技术证据与唯一人工复核排行、四项形态、风险和模拟计划、事件追踪、已成熟客观评价及缺失／落后状态；网站明确“研究排序，不是胜率或买入承诺”，M11 validated／active仍为0。M07 authoritative仅指此已批准研究产品内的唯一展示顺序，不代表M11策略active，不产生下单或资金执行权限。

个人形态保持全体当日合格成员的独立观察范围，复用M05所使用的`evaluate_v3_model_facts`唯一计算函数；非MACD日没有GateEvent时仅生成只读观察投影，不伪造ModelAssessment／M09主事件，不混入主排名／主交易结果／通知候选。已有合法M09事件才进入M10评价；首轮不声称非Gate观察项已有formal收益覆盖，不新增一套交易账本。

首轮禁止：自动下单、买卖通知、有效策略承诺、未验证净收益／组合收益、历史成员倒填及未实施的周期升级。Discord首轮仅发送日更研究摘要和相同前5研究候选，不发送交易执行指令。计划缺支撑／次日行情／批准成本时对应字段明确unavailable，不能用0或旧值填满。

授权路径选择“GitHub受保护生产环境＋固定身份审核人＋只读核验授权记录”。上线卡必须归档EODHD账户的数据使用／衍生展示授权证据，覆盖网站及Discord渠道；现有token或FinanceDatabase MIT许可证不能代替该授权，证据缺失不得公开发布。原始供应商数据保持私有。上线卡批准后，`PublicationAuthorization 1.0.0`由受保护的授权工作流写入，只允许显式允许的稳定用户ID批准，禁用自审；记录精确配置、代码、范围、模式及生效期。DO入口验证GitHub OIDC签名、issuer、audience=`sage-vista-publication`、repository_id、ref=main、固定workflow_ref／工作流内容提交、环境、sha、run_id／run_attempt、有效期，并通过GitHub API取得真实环境批准回执，二者同时满足。不能相信调用方提供的reviewer_id、SHA或test解析器。后续定时运行使用已归档的有效授权，不要求用户每天重批；改代码或配置必须新授权。撤销通过独立追加记录生效。

M12在调用M07 activation和正式写入前重新解析上述授权，绑定三项政策、scope和effective_from；M07现有非空approval_ref检查不能单独当生产授权。M11不创建任何production_activation事件；未来真策略激活另走完整M11条件，本设计无此权限。[GitHub OIDC](https://docs.github.com/en/actions/reference/security/oidc)。

## 3. 精确合同与唯一验证入口

以下是本稿的完整允许字段，不允许额外键，必填键即使可空也必须存在。所有新合同通过现有`services/contracts/validation.py:validate_contract`新增明确类型／版本分支；嵌套类型只有一份定义，生产者／存储／验证器／消费者复用，不在Worker另抄业务校验。协调器只检查认证、对象摘要、令牌及状态机；正式内容由固定提交的唯一Python验证器验证后出具可信收据。既有M01 Manifest 1.0 shadow-only及M02—M11旧合同保持原验证／只读边界。

### 3.1 公共类型和规范编码

- `Date`=YYYY-MM-DD；`Time`=UTC YYYY-MM-DDTHH:MM:SSZ；`Commit`=40位小写hex；`Hash`=`sha256:`＋64位小写hex；`UInt`=非负整数且不接受bool；`Text`=去首尾空白后非空字符串。`T?`仅允许T或null。
- `Ref`精确为`{id:Text, content_fingerprint:Hash}`；解析时须查实际库存并复核类型和内容，不因格式正确即可信。
- `Job`=`{repository_id:Text, workflow_ref:Text, workflow_commit:Commit, run_id:Text, run_attempt:UInt, environment:Text}`；只从已认证GitHub执行身份取得。
- `PolicyRef`=`{module:Text, name:Text, version:Text, content_fingerprint:Hash, definition_commit:Commit, source_path:Text, source_blob:Text}`；module仅M02—M11及M12，source_blob为固定Git blob，指纹按完整政策语义计算。
- `Check`=`{name:Text, result:pass|fail, evidence_ref:Ref}`；name仅contract/date/identity/hash/coverage/four_pages/authorization。
- 规范JSON使用现有canonical_fingerprint同一规范：UTF-8、键排序、无多余空白、禁NaN/Infinity；列表按下文键排序并拒绝重复。所有对象先形成语义体S（排除其id字段、content_fingerprint、generated_at），指纹=H(S)，ID=`<合同前缀>:`＋H(S)。generated_at不改变身份，首次保存后同ID新时间不另写；同ID语义不同失败。文件哈希对实际原始字节计算，包含换行，不能拿JSON语义哈希替代。
- 上游已有身份公式不改；新身份只用于M12合同。Manifest、投影文件和收据禁止自引用／循环：文件不含release_id，目录由Manifest身份派生；收据后建，不放回原Manifest。

`SourceInventory 1.0.0`精确字段：`schema_version='1.0.0',inventory_id,content_fingerprint,generated_at,as_of:Date,config_ref:Ref,roots:[Ref],records:[Ref]`，前缀`source-inventory`；roots是本日完整扫描批次、相关事件链和评价快照的库存根，records为这些根在DO权威索引中可达的完整引用闭包，均按id排序唯一，由库存锁内重建。缺根／漏项／多项／不可解析Ref失败，调用者不能自行挑选有利结果。评价快照先冻结独立任务inventory（roots为任务索引根）；发布inventory再引用该快照，禁止反向引用发布Manifest。

### 3.2 PublicationAuthorization 1.0.0

精确字段：`schema_version='1.0.0', authorization_id, content_fingerprint, generated_at, action=grant|revoke, prior_authorization_ref:Ref?, approver_id:Text, approval_evidence_ref:Ref, job:Job, config_ref:Ref, code_commit:Commit, publication_mode='research_only', scope='complex_multifactor_main', effective_from:Date, valid_until:Date?, permissions:[prepare|publish|notify|rollback], reason:Text`。前缀`publication-authorization`。grant权限首轮固定四项；revoke必须引用直接前序，不能换配置或代码；批准证据原件私存、只读重验。valid_until为空代表未设到期，但撤销即时生效。此对象不接受`strategy_active`权限。

### 3.3 ReleaseManifest 2.0.0

精确字段：`schema_version='2.0.0', release_id, content_fingerprint, generated_at, as_of:Date, code_commit:Commit, config_ref:Ref, authorization_ref:Ref, publication_mode='research_only', future_data_used=false, previous_release_ref:Ref?, source_inventory_ref:Ref, policy_refs:[PolicyRef], evaluation_snapshot_ref:Ref, files:[FileEntry]`。前缀`release`。首个新版release的previous允许null；以后必须等于preflight读取到的last_verified新版Ref，若准备期间其他release抢先发布，丢弃旧切换意图并以相同文件重建新的Manifest后再验证，不能跳过CAS；旧站回退目标另存切换状态，不伪造旧Manifest 2.0。

`FileEntry`精确字段：`path:Text, contract_name:Text, schema_version:Text, size_bytes:UInt, sha256:Hash, roles:[web|discord|audit], required:true, temporal_class:daily_snapshot|versioned_config|research_summary, as_of:Date?, coverage_end:Date?, registry_version:Text?, source_refs:[Ref]`。path仅第4节固定文件名，不含斜杠、..、URL或symlink；files按path、roles字典序、refs按id、policies按(module,name)排序且唯一。required全部true；“无评价／无匹配”用合法空结果文件表达，不通过缺文件表达。

daily_snapshot的as_of=Manifest.as_of，其余两个时间键null；versioned_config只有registry_version非空，其余时间键null；research_summary只有coverage_end可为Date或null（从未有完成评价），其余为null，且coverage_end≤Manifest.as_of。元数据必须从同一次读取的文件内容重验。source_inventory_ref指向一次冻结的完整M02—M11输入索引，排序的Ref数组及其H，不接受调用者挑出的子集。源文件每日输入不晚于as_of，评价截止不得超过as_of。

### 3.4 PublicationReceipt 1.0.0

精确字段：`schema_version='1.0.0', receipt_id, content_fingerprint, generated_at, release_ref:Ref?, previous_receipt_ref:Ref?, job:Job, fence:UInt, occurred_at:Time, kind:prepare|preflight|promote|online|rollback|notify, outcome:success|failed|uncertain, reason_code:Text?, details:<下列对应对象>`。前缀`publication-receipt`。形成Manifest前的prepare失败允许release_ref及inventory_ref为null，链根按Job标识绑定，成功prepare及所有其他kind必须非空release_ref并解析到已落盘Manifest。每次重试保留失败收据并引用该release（或尚无release时该Job）直接前序；不同kind不能携带其他kind字段。成功reason_code=null；失败仅允许source_missing/contract_invalid/hash_mismatch/coverage_incomplete/authority_missing/lease_lost/switch_conflict/provider_error/transport_unknown；uncertain仅适用通知或外部部署响应不明。

| kind | details精确字段 |
| --- | --- |
| prepare | `inventory_ref:Ref?, checked_files:[{path:Text,sha256:Hash,size_bytes:UInt}], checks:[Check]` |
| preflight | `target:PointerTarget, candidate_url:Text, renderer_version_id:Text, provider_deployment_id:Text?, manifest_hash:Hash, checked_files:[{path,sha256,size_bytes}], page_paths:[Text], checks:[Check]` |
| promote | `before:PointerTarget?, after:PointerTarget, expected_generation:UInt, resulting_generation:UInt, preflight_ref:Ref` |
| online | `target:PointerTarget, pointer_generation:UInt, renderer_version_id:Text, provider_deployment_id:Text?, manifest_hash:Hash, checked_files:[{path,sha256,size_bytes}], page_paths:[Text], checks:[Check]` |
| rollback | `before:PointerTarget, after:PointerTarget, failed_receipt_ref:Ref, rollback_check_ref:Ref, expected_generation:UInt, resulting_generation:UInt` |
| notify | `online_receipt_ref:Ref, notification_plan_ref:Ref, items:[{key:Hash,status:sent|skipped|failed|uncertain,platform_message_id:Text?,attempt:UInt}]` |

path/hash/size类型同FileEntry；检查文件按path、页面按路由、通知按key排序。成功prepare必须非空inventory_ref、七类Check齐全；失败prepare只保存已执行检查和对应日志证据，不要求不存在的文件／库存引用；preflight/online必须hash/date/four_pages/authorization齐全，成功时全部pass并覆盖全部公开files和四个路由。平台部署ID不存在的数据更新不能冒填，使用已核验renderer版本和明确null。sent必须有真实message_id；uncertain禁止自动再发该键，平台查询或人工确认后才追加修订。

`PointerTarget`为封闭union：新版`{kind:'release',release_ref:Ref,renderer_version_id:Text}`，首次回退旧站`{kind:'legacy',baseline_ref:Ref,renderer_version_id:Text}`。legacy baseline_ref是切换前归档的旧站完整文件清单／字节和代码证据，不得成为2.0研究Manifest。两种都必须有可信线上核验依据。preflight／online的target明确本次实际核验对象；正常发布等于release_ref目标，回退核验等于rollback.after，release_ref仍标识触发本轮恢复的失败新版。legacy核验中的manifest_hash为已归档旧文件清单原字节哈希，checked_files覆盖该清单，不把旧清单当2.0合同；四路由与字节核验仍必需。

### 3.5 EvaluationSnapshot 1.0.0 与当前指针

`ResultRow`精确字段：`result_ref:Ref, event_id:Text?, result_contract:ForwardOutcome|TradeOutcome|PortfolioRun|ResearchAggregate, window_sessions:UInt?, status:pending|mature|partial|unavailable|completed|no_trade, gross_return:Number?, net_return:Number?, mfe:Number?, mae:Number?, gross_r_multiple:Number?, mean_gross_return:Number?, win_rate:Number?, unavailable_reason:Text?`。Number为有限数值且非bool。字段逐一从相应M10已存对象投影，不适用字段null，禁止重新计算；状态按结果合同的原允许集合再验证。Portfolio所有数值null并带原不可用原因；Trade净收益无成本时null。result_rows按result_ref.id排序，必须与result_refs一一对应，事件／窗口／结果类型也须重验；公开页面无需访问私有R2原件即可显示这些有限数据。不新增全量收益统计或新的成功率口径。

EvaluationSnapshot精确字段：`schema_version='1.0.0', evaluation_snapshot_id, content_fingerprint, generated_at, scan_as_of:Date, inventory_ref:Ref, state:current|lagging|unavailable, completed_through:Date?, due_count:UInt, completed_count:UInt, failed_count:UInt, pending_due_count:UInt, immature_count:UInt, result_refs:[Ref], result_rows:[ResultRow], reason_codes:[Text]`；前缀`evaluation-snapshot`。计数按冻结inventory内的任务根去重，due_count=completed_count+failed_count+pending_due_count；immature不计due。无历史到期任务时current且completed_through=null，显示“尚无成熟样本”；有到期任务但零完成时unavailable；有完成但到期未清零为lagging。completed_through是所有在该日及之前到期的任务都已终结且结果合同可读的连续水位，失败不推进，不能用最新单个成功日期替代。

DO内部`CurrentPointer 1.0.0`精确字段：`schema_version='1.0.0', generation:UInt, visible:PointerTarget?, last_verified:PointerTarget?, phase:empty|switching|verified|rollback_pending, pending_receipt_ref:Ref?, last_receipt_ref:Ref?, updated_at:Time`。generation从0起，每次可见目标切换+1，包括回退，禁止ABA；浏览器只读取公开投影`{generation,visible,phase}`，不读取私有批准信息。默认no-store并绕过CDN缓存；首次服务端渲染把同一公开指针注入页面，浏览器不再另取一个不同版本开始渲染。浏览器一次固定release_id和renderer版本；所有数据请求为`/data/releases/<release_digest>/<path>`，不再读无版本根JSON作回退。客户端不得以一个新指针刷新一半组件。

## 4. 四页文件映射与投影

所有文件位于不可变release目录；统一`WebProjection 1.0.0`封装`schema_version, kind, as_of, source_refs, data`，kind由下表路径固定，data只读映射现有上游可公开字段。factor-registry沿原版本化注册表合同；evaluation沿3.5独立合同。Manifest不复制这两种合同，仍调用其唯一验证入口。以下十个文件是完整允许集，全部必需，不能回落到旧Rare Radar或静默恢复旧排行。

| 文件／kind | 权威来源与边界 | 消费者 |
| --- | --- | --- |
| update-status.json／status | 当前包扫描日期／覆盖、上一成功日、研究模式；不含会循环依赖的release_id | 四页共享外壳、Discord |
| overview.json／overview | M07前5严格子集、M06大盘、M08风险摘要；不重新排序 | `/`（现有resonance/page.tsx） |
| rankings.json／rankings | M07完整当日主排行、分项及排除理由；已冻结顺序 | `/zh/watch/resonance/rare-opportunities` |
| technical-evidence.json／technical_evidence | 当前排行及个人观察项的M04／M05证据、来源日期、命中／缺项 | 多因子、个人形态详情 |
| factor-registry.json | 原因子库0.10.0定义／研究角色，只读 | 多因子 |
| favorite-pattern.json／favorite_pattern | 当日全合格池V3观察投影，标注Gate关联／非Gate观察；无第二排名 | `/zh/watch/resonance/favorite-pattern` |
| context.json／context | M06六个ETF状态及可靠个股映射，缺成员关联明确unavailable | `/`及`/zh/watch/industry-radar` |
| events.json／events | M09当前包涉及事件和最近30交易日摘要、M08计划，历史正文私存 | 多因子、个人形态 |
| evaluation.json | 3.5快照及其result_rows的已保存结果投影；收益原件不下载 | 总览、多因子、个人形态 |
| notification-plan.json／notification_plan | 固定日更摘要及M07前5原序，事件／状态键，不包含Webhook或密钥 | 仅Discord与审计，不向浏览器公开 |

WebProjection的source_refs指向Manifest同一inventory中的来源，as_of=D，禁从网络补算。未成熟、零匹配、缺可选上下文均是带原因的明确状态，不能省略整文件。evaluation.json标research_summary、coverage_end=completed_through；factor-registry标versioned_config，其余daily_snapshot。Manifest可公开的是移除私有引用后的只读展示副本，不能用该副本替代私有权威Manifest；公开服务仅暴露标web的文件，源行情、通知计划、批准／收据私存。

首次页面只加载本页上述文件，事件／证据可按需加载；移除四页对完整unified-v2-rankings.json、opportunity-ledger.json、旧tracker／radar及研究实验目录的在线依赖，旧文件不删。manifest目录中只有本表文件，不新增历史查询API或看板。用户能看当日与近30日，完整历史仍留现有Git／私有审核输出。

## 5. 持久存储、锁与写入边界

固定R2逻辑桶`SAGE_VISTA_ARCHIVE`（私有，禁止公网桶访问），键空间：`raw/<hash>`原始字节、`facts/<contract>/<id_digest>`上游不可变记录、`indexes/<hash>`完整库存、`releases/<release_digest>/<path>`、`manifests/<release_digest>.json`、`receipts/<receipt_digest>.json`、`authority/<id_digest>.json`。通过write-if-absent及原字节重验保证幂等；raw/facts/indexes/manifests/receipts/authority/releases设置无限保留锁，运行角色无删除／解锁权限。临时未完成包只放`staging/<job_id>/`，七天清理；成为权威对象后不自动删除。R2写成功后由DO登记引用，未登记对象不参与权威库存，故障形成的孤立对象只算审计材料。

推荐单个DO实例`production-coordinator`管理所有本项目生产写资源，SQLite事务保存身份epoch、各合同线性链索引、任务队列、租约和CurrentPointer。对象正文仍在R2；协调器登记前核验可信合同验证收据、R2对象哈希、前序链及令牌，事务只提交指针／索引，不跨网络持事务。事务追加完整操作日志，异步导出到R2；DO丢失／不可用时拒绝切换和写入，不拿陈旧导出自动恢复生产。恢复先冻结写入，以R2收据重建并人工批准新租约epoch，旧runner令牌全部失效。

租约精确字段`{resource,owner_job:Job,fence:UInt,expires_at:Time}`，DO服务端计时，TTL=300秒，每60秒续约；每次授予递增fence，续约不改fence。resource为Text且固定四族：`daily/<D>/<config_id>`、`evaluation/<task_id>`、`publish/global`、`legacy-nightly`。请求必须携带当前owner＋fence，过期后旧runner即使继续运行也不能登记事实、完成队列、切换指针或通知。只能提交内容寻址临时字节，无权绕过DO改权威索引。发布锁只占用发布／核验／通知登记期，不覆盖全市场计算或历史回放。

所有手动／定时／恢复任务调用同一入口；GitHub concurrency只是减少重复，跨任务正确性由DO实现。借助R2＋DO的生产适配器复用既有M02—M11合同与线性链校验，不削弱原ShadowStore路径守门；正式存储能力只由已认证生产runner固定注入，CLI、下载内容、环境变量不能提供任意根目录。共用纯校验必须从原实现提取复用，不在publication复制第二套算法。此适配为本M12包明确包含的接点，不是授权重写上游身份。

## 6. 发布切换与回退状态机

采用稳定四页前端外壳＋版本化数据包。日常仅发布数据，不每天替换Worker代码。需要前端代码变化时先上传／部署候选版本到隔离预览，取得真实Cloudflare版本／部署证据；生产网关按PointerTarget中的renderer_version_id选择已经注册的渲染版本（服务绑定路由），候选renderer按独立不可变服务名部署、每次发布只更新允许映射；网关预先注册新旧服务绑定且仍路由旧target，核验成功后再切指针。浏览器不能指定任意服务或把外部头当授权。renderer与数据release一起切换，不能分别更新两条“最新”指针。旧版本保留用于回退；本版不使用随机流量灰度，以免同用户看到混合包。[Workers版本与部署](https://developers.cloudflare.com/workers/versions-and-deployments/)。

1. **prepare**：持daily锁生成facts并登记冻结库存，生成十文件和Manifest，上传不可变对象，完成唯一合同／覆盖／身份检查。无任何公开指针副作用。
2. **preflight**：持publish/global租约，读取generation与last_verified；使用受认证候选路由固定renderer＋release，检查实际下载字节、日期、四页内容及无旧文件回退。候选预览没有生产写权限。失败留收据、旧站继续。
3. **promote**：可信成功preflight存在且授权有效，DO一个事务比较generation＋fence，记录promote意图并把visible设候选、phase=switching、generation+1，last_verified保持旧值。并发CAS失败不自动覆盖对方版本。
4. **online**：通过正式域名重新获取指针、十文件中可公开文件的真实响应和四页，私有文件经认证验证，核对相同release／renderer／哈希。成功事务记录online收据、last_verified=visible、phase=verified，然后才允许notify；验证期间不会发通知。
5. **rollback**：online失败或runner崩溃且300秒租约到期，DO告警／恢复任务接手。先检查上一完整目标仍可读并形成rollback_check（一次preflight成功收据），CAS仅在visible仍为失败候选且generation未变时回退，generation再+1。回退后再次线上核验才标verified；失败保持rollback_pending、冻结发布和通知并报警，不伪报已恢复。失效授权只允许回退到事先授权的last_verified，不允许换第三个候选。
6. **崩溃恢复**：DO持久记录切换前目标及pending收据；重启先读取状态与平台证据，再续做online或rollback，不盲目重复部署。外部部署结果不明先查询版本／部署ID。归档收据与DO事务的持久操作记录双向核对后才报告成功。

首次切换前必须把旧站完整发布包和真实renderer版本归档成legacy PointerTarget并完成一次回退演练；没有可用回退目标不做第一次promote。迁移网关本身属于单独上线步骤，批准后先保持100%旧目标验证，再允许新包切换。已打开页面锁住旧release可继续读旧包，新的导航才取得新指针；公共JSON不能被CDN当前指针缓存混淆。旧baseline路由只服务归档的旧完整包，legacy对象不走新Manifest验证。

notification key=H({scope, event_id或日更D, semantic_state, notification_policy_version})，不含release_id，避免评价修订包重复提醒；同键内容变更留冲突记录，不重发。首轮实际对外发送以日更D生成一个摘要key，事件键作为其中items的归属证据，不逐只另外发消息；已发送摘要不因同日评价修订补发。平台请求使用返回message_id的模式，DO先登记inflight再发送，timeout为uncertain、禁止自动再发，待查回执。浏览器／普通runner不能持有Webhook。M11策略状态与技术发布回退分离，回退不删除或伪造active／retired事件。

## 7. 每日、夜间、到期评价与页面水位

- **每日**：复用daily-eod和现有Cloudflare／GitHub备用／恢复触发。先归档同日成员，再准备M02，串联M03—M09；成功事件以不可变Ref登记到期任务后即可发布当前扫描。不因M10落后拖住新交易日。相同D输入／配置重跑复用；不同来源修订形成新库存／新release，保留原件。
- **到期评价**：独立Actions job复用M10统一运行入口，每个EOD完成及现有freshness恢复触发检查DO队列，不增设另一套扫描。任务ID=H({event_ref, result_contract, window_sessions或null, evaluation_policy_ref, candidate_or_baseline, partition_role})；每次attempt另绑定as_of、行情修订Ref、代码和前次attempt。不同as_of成熟进度及供应商修订用既有M10线性结果链，不覆盖旧pending／失败。
- task状态固定queued/running/retry_wait/completed/blocked；immutable M10收据是完成事实。429／5xx／网络错误按15分钟、60分钟、下一EOD重试，每任务每纽约日最多3次；到期闹钟仅dispatch评价job，不跑扫描。身份、合同冲突为blocked，需明确修复证据后恢复；未知数据不得把失败标completed。尚未达到交易日窗口的任务保持queued且尚不可领取，快照计入immature_count；immature是到期分类，不另增task状态，未到期不是失败。每个job最多10分钟，保存checkpoint后退出，下一触发继续。
- **原夜间历史**：继续每晚一自然周的legacy研究线，保持`automation/backtest-state.json`和`backtest-progress.json`原字段、旧覆盖、已完成周及下一断点。接入时先归档原状态字节并固定legacy回放业务基线`14fef535…`；下一周仍为机器源记录的未完成周（当前2025-12-22—28），不从M12首次formal日重置。夜间继续原M10以前legacy路径及版本标签，新M02宇宙不倒填2000—2026旧历史。每周产物、检查与普通Git提交成功后才推进原断点；推送冲突不强推、不覆盖新状态，重新读取确认证据再处理。
- nightly只持legacy-nightly锁和自己的历史缓存，不能获取publish/global来更新新release，也不能改DO每日／评价水位。原夜间写旧public文件仍为legacy归档，新四页不读取它们；M12不删除这些入口。新formal前向评价队列和索引放DO／R2，与旧两个断点文件完全隔离。未来新formal历史回放另立范围，本轮不替换夜间算法。
- 所有任务仅读共享不可变原件；供应商新增修订需经M02唯一写入与fence登记，日任务优先。资源紧张时nightly让出采集配额，不取消或丢掉已存周；评价和发布均不写旧夜间断点。

页面始终分别显示“扫描截至D”“评价连续完成截至E或尚无”“N项到期待补／F项失败／I项未成熟”。D新而E旧时显示“今日候选已更新；后续表现评价落后”，已完成结果仍按原窗口／样本显示，失败或pending不计入成功率分母。无成熟样本显示“尚无”，不得用零胜率。可选上下文缺失局部标不可用，不影响已完整的技术事实；必需行情／身份缺失则不发布新扫描包，保留旧日期并展示更新失败状态。

评价恢复只生成同D的新evaluation快照与新release（排名／扫描字节复用），按完整发布验证流程切换，通知键去重。D+1新扫描已成为当前时，D的晚到任务不能把页面退回D；只将结果纳入当前或下一release且result as_of≤其D。失败提示来自DO独立运行状态的只读小投影`/run-status.json`（不在发布Manifest、不改变业务事实），精确字段为`scan_target_date:Date,last_attempt_at:Time,scan_state:running|current|failed,evaluation_state:current|lagging|unavailable,pending_due_count:UInt,failed_count:UInt`；不得覆盖冻结包里的指标或日期。它可在新包失败时说明“旧包仍有效”，也不能使旧排行冒充今日。

## 8. 四个简短样例（D/E为示意交易日，非上线日期）

| 情况 | 系统动作 | 用户看见什么 |
| --- | --- | --- |
| 正常 | D同日成员全量、资格完整；扫描与账本成功；到期评价清零；preflight→切换→online成功→日更摘要 | 四页扫描D，评价水位E≤D；可看前5研究候选／形态／模拟风险，validated与active仍0 |
| 来源缺失 | D列表下载截断或某成员资格未知；formal整日停止，保存失败收据，不移动发布指针；来源修复后仅重试失败阶段 | 保留D-1完整排行，顶部明确“D更新失败：来源不完整”；不会出现混日期或假的空榜 |
| 评价失败 | D扫描成功，20日窗口任务网络失败进入15分钟重试；其余完成结果保存，daily不等待 | 扫描D、评价E较早，标“到期评价待补”，失败样本不当零收益；恢复后同D修订包只补评价不重复通知 |
| 发布失败 | 候选字节预验通过，切换后正式域名某文件错哈希；online失败，禁止通知，CAS回退上一已验证目标并复核 | 切换期锁定候选版本，校验失败的内容显示不可用、不拼接旧字段；随后恢复上一版本并标日期与发布失败；失败收据／新包保留不删除 |

## 9. 实施边界、验收与交付拆包

只允许本设计涉及的Manifest／收据版本、M02—M11现有纯入口与正式存储适配、publication协调器、四页只读消费者及现有工作流接点。新生产存储是显式新增适配，不取消原影子路径守门；合同／数据身份语义变化必须回到对应唯一入口，未在本设计说明的业务变化不实施。既有业务政策字节、FinanceDatabase快照与许可不变。候选与已验证策略分离不削弱M11；M11不再重复审核。

| 包（每包≤20分钟，超时进一步拆分） | 交付 |
| --- | --- |
| A1/A2 | 本文精确合同／身份／封闭枚举及单一验证；正常与伪造收据反例 |
| B1/B2 | R2只追加适配＋DO身份／租约／索引及失效fence测试；保留shadow边界 |
| C1/C2 | 同日EODHD成员归档与资格、现有M03—M09串联、精确政策与research授权 |
| D1/D2 | 独立评价队列、旧夜间断点隔离、重试与页面水位 |
| E1/E2 | 十文件投影、四页版本锁定及来源映射，无新产品页 |
| F1/F2 | preflight／CAS切换／online／回退、首个legacy回退目标 |
| G | Discord日更摘要、跨release去重与uncertain恢复 |
| H | 合成端到端、跨runner崩溃／并发、只读真实dry-run上线卡 |

验收必须覆盖：未知字段／版本／伪造批准失败；文件集合完整与身份无循环；来源截断／同日缺失／epoch冲突失败；合法研究授权可发布但不能创建M11 active；过期runner不能登记／切换；DO事务与R2孤立对象恢复；旧夜间断点不变且周完成才推进；评价错误不阻塞扫描或污染分母；切换前后客户端均不混读；首次回退演练；重复通知与不确定发送不盲重发。实施后运行对应Python／工作流契约／前端构建渲染；本设计轮只检查文档、链接、政策引用与范围，不重复M11或无变化完整测试。

上线卡只填写实际首次生效日期、已获批准的配置与运行提交、云资源实物ID／权限与数据授权证据、真实dry-run覆盖／差异／成本、回退演练及部署／通知批准。技术栈、合同、股票池范围、身份、政策、任务关系与锁／回退方案均已在本稿推荐冻结，不再交用户决定实现细节。若实际数据源或平台不能满足此设计，失败关闭并将差异交回审核，不能现场换口径。本稿保持design_review，尚未授权任何实施或上线。
