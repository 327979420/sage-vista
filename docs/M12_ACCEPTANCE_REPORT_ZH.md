# M12 实施验收记录

日期：2026-09-06；CR-053：`implementing`。设计基线：`505c89f2d93ab7bd2991c477ef2f306e84dd7a73`（v0.2.1）。用户已批准分包实施，尚未批准上线。

## 首批 A1a：SourceInventory 合同基础

- 实现：`services/contracts/validation.py`新增SourceInventory 1.0.0明确分支；其他合同继续原路径。`validate_contract`和`validate_contracts`均要求显式可信库存证据，缺失即失败关闭。
- 完整性：从可信索引根迭代遍历完整引用闭包，包含根、共享节点去重；拒绝缺节点、指纹冲突、重复节点及环。对照完整闭包拒绝重新签名后的删项、增项、替换、换根／日期／配置。1500节点历史链无需Python递归。
- 身份：仅允许设计字段和1.0.0版本；严格日期、UTC秒时间、Ref结构及有序唯一数组。复用canonical_fingerprint规范，generated_at不改变身份。
- 构造：`services/publication/inventory.py:build_source_inventory`复用唯一合同推导及验证，不修改／引用可变调用输入，无文件或网络I/O。

### 信任边界与未完成部分

`source_inventory_evidence`是内部适配输入，精确形状为`{as_of,config_ref,roots,nodes}`；每个node为`{ref,dependencies}`。未来B包须由认证生产适配器在库存锁内取得完整roots，对实际对象类型／内容和完整直接依赖重验后注入。当前仅使用合成可信索引；函数能校验声明与该索引一致，不能证明调用方真实持锁、远端对象存在或GitHub授权有效。不得把用户JSON直接作为此证据，不存在默认放行的生产适配器。

本批没有实现其余M12合同、发布收据、R2／DO持久存储或租约、跨日M08／M09任务、M10任务接线、四页／工作流／通知。其余合同仍未知即拒绝；Manifest 2.0尚未开放，Manifest 1.0旧影子边界保留。设计中的跨日掉榜续跑及部分提交恢复仍是后续实施验收要求，尚未执行，不能记为通过。

### 实际检查

| 检查 | 结果 |
| --- | --- |
| `test_m12_inventory.py` | 13项通过，包含删增替换重签、缺证据、错误版本／字段／类型、冲突／循环、长历史、幂等身份及集合重复 |
| `test_shared_contracts.py` | 31项通过，覆盖既有共享合同与影子Manifest |
| `test_rulebook_contract.py` | 7项通过 |
| `test_project_status.py` | 12项通过 |
| 合计 | 63项通过，无跳过 |
| 差异格式、本地文档链接、生产机器状态一致性 | 通过 |

未重审M11，未重复全业务测试，无真实行情或回测运行。未改变业务政策、快照、许可证、旧断点和生产文件。

## 提交与回退

本报告与首批代码同属独立提交`feat: add M12 source inventory contract foundation [skip ci]`（父提交505c89f，完整SHA见交付消息）。代码及治理文件提交后交审核，不推送或合并。纯新增合同无生产消费者，无数据迁移；如本批需回退，撤回本批代码／测试即可，保留批准与验收历史。没有部署、生产启用或对外通知。

## A1a独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认6aa60cd在本批实际边界内通过，无阻断。审核员自行运行63项测试，另用独立递归算法对照200个固定种子有向图，并验证删项／换指纹重签后单对象和集合入口拒绝。HEAD未变且工作区干净。结论仅限纯合同与可信注入索引一致性，B包仍须验证真实来源认证、锁内完整索引及持久存储。

## A1b：PublicationAuthorization合同（待独立审核）

- 唯一合同入口新增PublicationAuthorization 1.0.0；封闭字段、Job结构／UInt／完整提交SHA、固定research_only／complex_multifactor_main、日期区间及规范身份。纯构造器为`services/publication/authorization.py:build_publication_authorization`。
- grant权限按设计列举顺序固定prepare/publish/notify/rollback；revoke使用空permissions、不授予新权限，并必须引用可信历史直接前序，代码和配置保持一致。历史逐条检查结构、身份和前序，保留grant→revoke→新grant的追加记录。generated_at不改变身份。
- `publication_authorization_evidence`内部输入精确为`{request,approver_id,approval_evidence_ref,job,history}`。request只含action/prior_authorization_ref/config_ref/code_commit/publication_mode/scope/effective_from/valid_until/permissions/reason；history为已由可信适配器验证来源的完整前序序列。请求绑定精确前序，不能因后来新增授权而对旧批准静默换根。
- 单对象和集合入口都要求可信证据；重签后的批准人、批准证据引用、执行身份、代码／配置／生效日／期限或理由替换均拒绝。构造器复用唯一推导和验证，不修改或共享可变输入。

### A1b实际验证

15项新授权专项、13项A1a回归、31项共享合同、7项治理和12项状态测试，共78项通过，无跳过；差异格式、本地文档链接及机器状态一致性通过。新测试覆盖正常grant／revoke／续grant、缺证据、越权、重签篡改、错误前序／历史、嵌套字段／类型、日期和身份。未重审M11或重跑完整业务测试。

### 仍未完成的生产闸门

本批只验证**记录与注入的可信批准输入／前序一致**，不执行GitHub API或OIDC验证，不证明批准者在允许名单、非自审、工作流受保护或真实批准回执存在。后续适配器必须在锁内读取完整历史，并核验实际代码／配置、OIDC、GitHub环境批准和原件，不能从调用方JSON构造可信证据。

合同可存未来生效或已到期的历史批准，不代表当前可发布；生效时间、到期、即时撤销和回退例外的运行时权限执行仍由后续包落实。未提供任何默认允许的is_authorized接口或生产消费者；没有将此处grant转成M11 active。Manifest、收据、评价快照、R2／DO及跨日端到端仍待实现／验收。

本批与本段同属独立提交`feat: add M12 publication authorization contract [skip ci]`，父提交6aa60cdb66469fb19cfe03cf61349b9b2b174e9d；完整SHA见交付消息。未推送、合并、部署、生产启用或对外通知。无数据迁移；如需回退仅撤回本批代码／测试，保留审核与实施历史。

## A1b独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认5461741在纯合同及可信批准输入绑定范围内通过，无阻断。审核员自行运行78项测试，另验证40条交替grant/revoke历史、80次重签Job仓库身份替换及38次跳过直接前序请求；后两者均拒绝。HEAD不变、工作区干净。结论不涵盖真实OIDC、批准人／保护环境、完整历史来源、实时期限／即时撤销或生产存储。

## A1c：EvaluationSnapshot合同（待独立审核）

- `validate_contract`及集合入口新增EvaluationSnapshot 1.0.0，封闭字段／ResultRow、UInt计数、有限数值、规范身份及可信任务输入必需；纯构造器位于`services/publication/evaluation.py`。
- 重新验证SourceInventory，要求同一扫描日的独立任务索引根；任务全集必须等于索引根的直接依赖，按task_ref排序唯一。每个已引用结果必须绑定对应任务节点、在冻结库存内、ID／指纹吻合，不能遗漏、重复或加入额外结果。
- 通过现有M10 `validate_result`核验实际完整结果对象，并逐字段只读投影，拒绝晚于扫描日、legacy或comparison对象冒充formal研究结果。事件／窗口／结果类型必须吻合任务元数据。Forward仅投影gross/MFE/MAE，Trade沿现有净收益缺成本为null边界，Portfolio指标全null，ResearchAggregate读取已有mean_gross_return/win_rate；无新收益计算。
- 到期分类按可信任务due_on与scan_as_of比较；queued/running为到期待补，retry_wait/blocked为失败，completed必须已有到期且非pending的合法M10结果。未到期单计immature，不计due。终结且明确unavailable结果表示评价任务已完成，不等于指标可用，页面仍须保留原不可用原因。
- 同日任何到期任务未完成就阻止该日及以后水位；部分失败时保守保存阻断日之前最后一个全部完成的到期日，全清零时推进至scan_as_of。无到期任务为current／水位null，有到期但零完成为unavailable，有完成且仍待补为lagging。收益、状态、日期和计数改写后重签也必须与可信输入一致。

### A1c内部证据与后续验收

`evaluation_snapshot_evidence`精确输入为`{scan_as_of,inventory,inventory_evidence,task_index_ref,tasks,results}`。tasks每项为`{task_ref,due_on,state,result_ref,result_contract,event_id,window_sessions,reason_codes}`；results每项为`{contract_name,payload}`，payload为实际M10结果。来源适配器须在锁内证明完整任务索引、真实到期计划／状态、已持久化完成收据及结果链最新叶，并核验任务元数据与task_ref所指原件一致。本批用合成可信任务元数据验证这些输入之间的一致性，不能据此证明真实任务状态或调度已经正确运行；不接受外部用户JSON充当可信证据。

首轮不可用说明只映射原结果的status_reason，其为空时读取metric_reason或net_return_reason；不编造成功率或收益。尚未启动每日／夜间／M10评价任务，也未执行跨日掉榜端到端样例。Manifest／收据、R2／DO、任务恢复、页面发布和实时权限仍待后续包。

### A1c实际检查与提交

- 15项新增评价快照测试，包括现有四类M10合同、当前2.1汇总投影、禁止重新计算、缺证据、闭包删改、同日／跨日失败水位、未成熟、未来／comparison、缺成本及重签篡改。
- 加上28项A1a/b、31项共享合同、7项治理、12项状态，共93项通过，无跳过。文档链接、差异格式及机器状态一致性通过。
- 未重审M11，无真实数据或实验运行，旧政策、快照、许可及断点未改。
- 与本段同属独立提交`feat: add M12 evaluation snapshot contract [skip ci]`，父提交5461741c3ed53ae7b1d3aba618cf5fb49a8d0f16；完整SHA见交付消息。无数据迁移／生产消费者，可撤回本批代码和测试，保留实施审核历史。未合并、推送、部署、生产启用或对外通知。

## A1c独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认9af3983在EvaluationSnapshot纯合同、实际M10对象只读投影及可信任务索引一致性范围内通过。审核员自行运行93项测试及250组同日／跨日任务状态组合对照，计数、状态和失败阻断水位全部符合预期；diff通过、工作区干净。真实任务全集、到期安排、持久化收据、最新叶及元数据原件真实性仍留后续验收，跨日端到端未执行。

## A1d：ReleaseManifest 2.0.0（待独立审核）

- 唯一合同入口新增明确2.0.0分支，旧M01 1.x仍走原路径；新分支即使传allow_partial_manifest也不能省文件。构造器为`services/publication/manifest.py:build_release_manifest`，无文件／网络／发布I/O。
- 固定十文件、按路径排序且全required；公开文件为audit/web，update-status额外discord，notification-plan仅audit/discord。哈希与长度来自同一次注入的不可变bytes，包含换行，不拿JSON语义指纹替代文件摘要。
- 严格UTF-8 JSON、拒绝重复键／NaN／Infinity／数字溢出以及文件内release_id自引用。WebProjection只校验固定封装、kind／日期／来源引用并逐字节规范语义对照可信生产者给出的冻结投影，不计算扫描、排行或收益。
- factor-registry通过现有唯一legacy只读适配器验证，并与可信配置固定原件字节一致，首轮registry_version必须0.10.0；FileEntry合同标签为FactorRegistry、适配schema为1.0.0。evaluation复用EvaluationSnapshot唯一入口，文件须等于完整冻结对象，日期及其库存配置须同本包，coverage_end只取其完成水位，可为null。
- 重验SourceInventory与授权合同；配置／代码和发布日期须被grant涵盖，拒绝将revoke作为发布依据。评价Ref、注册表Ref及文件来源Ref须位于本包库存，来源日期不晚于扫描日；Manifest精确绑定可信政策Ref列表及last_verified新版Ref，未知键／版本或重签篡改均拒绝。

### A1d可信输入及未完成边界

`release_manifest_evidence`精确输入为`{as_of,code_commit,config_ref,policy_refs,last_verified_release_ref,inventory,inventory_evidence,source_dates,authorization,authorization_evidence,evaluation,evaluation_evidence,registry_ref,registry_bytes,projection_expectations,files}`。文件是内存bytes；projection_expectations为八个WebProjection预期对象；source_dates为库存records的完整ID→日期或null映射。既有三个合同仍使用其各自可信证据接口。

本批证明**文件字节、合同和注入的准备输入彼此一致**，不能证明真实准备生产者已执行。B／C／E／F包仍须验证：源日期与对象原件、政策完整集合与固定14fef535源码／blob和配置绑定、原注册表字节出处、业务投影与上游的唯一映射、当前未撤销授权、last_verified真实对象及锁内CAS。PolicyRef当前做封闭格式／排序／SHA／路径检查并绑定可信列表，不在纯合同函数内读Git或自行选择真实政策；合成测试政策不代表获批生产配置。不能将外部JSON当上述可信输入。

没有写R2、改DO指针、部署Worker或发送通知。收据／当前指针合同、生产存储、实际四页映射和跨日续跑仍待实现与验收；本批不是上线批准。

### A1d实际检查与提交

14项新增Manifest专项、43项A1a/b/c回归、31项共享合同、7项治理、12项状态，共107项通过，无跳过。覆盖字节换行身份、删增重复文件、私有roles篡改、投影改写、路径越界、严格JSON、日期／来源、错误授权／前序／政策、未知版本及集合重复。共享回归保留旧影子Manifest边界；未重审M11。文档链接、差异格式、机器状态一致性通过。

本段与代码同属独立提交`feat: add M12 release manifest byte contract [skip ci]`，父提交9af398344d58155196bcd27323fb82036c8b6547，完整SHA见交付消息。无数据迁移和生产消费者；可撤回本批代码／测试，保留审核历史。未合并、推送、部署、生产启用或对外通知。

## A1d独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认0f0b7c2在Manifest 2.0纯合同、可信准备输入及实际字节一致性范围内通过。审核员自行运行107项测试，另覆盖十文件字节变化及哈希／roles／source_refs重签篡改，单对象／partial／集合入口共88次拒绝检查全部通过。HEAD不变，diff通过，工作区干净。真实投影、政策完整性／源码blob、registry出处、当前未撤销授权、last_verified和锁内CAS仍待后续证明。

## A2a：PublicationReceipt与PointerTarget结构（待独立审核）

- 六类PublicationReceipt 1.0.0统一经validate_contract及集合入口；精确字段／kind专属details、UInt／时间、规范内容身份、直接前序链、release或提前prepare的Job根。纯构造器为`services/publication/receipts.py`，不执行任何操作。
- PointerTarget封闭为release或legacy，两者都绑定renderer。核验四路由、检查名与Ref、已检文件路径／长度／哈希、成功／失败理由及通知项目均验证格式和集合；成功prepare需七类检查和全文件，成功preflight／online需四类检查及全部公开文件／四页。失败收据可保留部分检查及实际测得的错误字节哈希，不能把失败值伪装为成功。
- 收据解析当前M12 Manifest实际字节并复用其合同，当前目标文件清单／公开roles／Manifest字节哈希由该对象核对。提前prepare失败允许无Manifest但保留部分prepared_files原字节；不需伪造不存在的库存或release。
- promote／rollback依赖成功preflight同一目标，成功generation恰加1，失败不变；online绑定最近成功切换的目标和generation。rollback绑定失败online和旧目标成功preflight；旧站回退后的online不能用于通知失败新版。notify必须引用本release最近成功online及可解析通知计划Ref，sent须带message_id，uncertain不能冒充success。

### A2a可信输入与运行边界

`publication_receipt_evidence`精确为`{observation,history,release,release_evidence,release_bytes,targets,references,prepared_files}`。observation含合同的九个业务字段（release_ref／previous_receipt_ref／job／fence／occurred_at／kind／outcome／reason_code／details）；history为该release或提前失败Job根的完整可信前序链。references为已验证来源的辅助Ref全集；targets每项为`{target,manifest_hash,files,public_paths}`，旧目标／legacy来源由后续适配器重验。prepared_files只用于尚无Manifest的失败准备字节；Manifest存在后必须为空，避免双文件权威。

本批只证明观测、前序、引用与字节材料的一致性，不证明真实HTTP检查、平台message_id／部署ID、辅助Check原件、历史全集或旧目标库存来源。主release已实际复用Manifest验证；其它归档目标的完整字节／renderer和last_verified真实性仍待B／F包认证及持锁接线。generation这里只验证收据声明，不代表CAS已执行或lease仍有效；CurrentPointer完整状态转换留A2b。即时撤销、通知去重、uncertain后禁止自动重发及查询／人工确认恢复仍由后续运行适配器执行，记录uncertain不等于已实现重试保护。

### A2a实际检查与提交

15项新增专项覆盖正常五阶段、提前准备失败／部分字节、旧站回退及再核验、失败不得递增generation、online切换绑定、失败观测错误哈希留档、成功检查／文件／页面守门、未知字段／版本／bool、缺证据与前序、通知失败／uncertain、集合重复及输入隔离。加57项A1、31项共享合同、7项治理、12项状态，共122项通过，无跳过；文档链接、diff、机器状态一致性通过。未重审M11，跨日端到端仍未执行。

与本段同属独立提交`feat: add M12 publication receipt contracts [skip ci]`，父提交0f0b7c206312fbac94a7a399b6c8d70ec4852fbe，完整SHA见交付消息。无持久存储／工作流／页面变化，可撤回本批代码测试，保留治理历史。未合并、推送、部署、生产启用或对外通知。

## A2a通知计划引用定点修复（待独立复核）

独立审核发现1项P2：1b5e65a的notify仅要求notification_plan_ref在辅助references中可解析，未绑定当前release文件。审核员既有122项测试通过仍可复现；实施侧修复前亦复现库存Ref替换后构造器／单对象／集合入口全部接受。本轮暂停A2b，只修此项。

- 在唯一合同入口增加`release_file_reference`：先复用Manifest 2.0及实际冻结字节验证，按设计3.4补充的`release_ref + path + sha256 + size_bytes`规范身份生成`release-file:sha256:…`；Ref的content_fingerprint就是文件原始字节SHA-256。
- notify必须精确等于当前Manifest固定notification-plan.json派生的Ref，再检查辅助引用可解析；不能用库存、检查证据或其它release计划替代。复用现有Manifest文件字节，不引入第二套消费者校验或额外可信输入。
- 合同字段／schema、上游身份、通知去重key不变；文件Ref即使字节相同也按release区分，这不改变未来通知按日／事件跨release去重的设计。任意旧占位Ref不再作为合法新收据输入，旧测试样本已改用明确映射；本功能尚未上线，无生产迁移。

### 定点验证

- 三个反例：已在辅助列表的库存Ref、普通check Ref、另一release不同计划Ref（额外放入辅助列表保证可解析）；分别构造并重签，在构造器、单对象和集合入口共9次拒绝。
- 合法notify及uncertain留档回归通过。文件Ref测试验证原字节哈希（含换行）、release／path绑定、缺Manifest证据拒绝，以及相同计划字节在不同release中的Ref ID不同。
- 74项M12专项／回归、31项共享合同、7项治理、12项状态，共124项通过，无跳过；diff、文档链接与机器状态一致性通过。没有重复M11或全业务审核。

与本段同属独立提交`fix: bind receipt notification plan to release file [skip ci]`，父提交1b5e65abfe0370fa0e1a60a0152d833b015850b5，完整SHA见交付消息。仅本处修复，未开始A2b；真实发送、去重、平台认证、持久存储与CAS继续待后续。不合并、推送、部署、生产启用或对外通知；交回独立定点复核，不自行宣布审核通过。

## A2a定点独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认1d4ba84关闭通知计划Ref绑定P2，A2a纯合同范围审核通过。审核员运行相关receipts＋manifest共31项（未重复完整124项），并独立验证库存Ref、check Ref、另一release相同通知计划字节Ref在三个入口共9次拒绝；diff通过、工作区干净。真实来源、租约、CAS、HTTP、发送及恢复仍待后续验收。

## A2b：CurrentPointer纯状态转换（待独立审核）

- CurrentPointer 1.0.0保持设计八字段，通过唯一validate_contract入口验证；集合入口将其视为唯一可变单例，拒绝一个集合出现多个CurrentPointer，不伪造内容ID。
- initialize只允许可信前态不存在，生成generation=0的empty；bootstrap只允许从empty登记已核验legacy目标，generation=1，visible=last_verified、phase=verified。不能用bootstrap把新release直接置为已发布。
- promote要求verified前态、before／expected_generation匹配；Manifest.previous_release_ref也必须匹配保存的last_verified新版Ref（legacy时null）。成功generation+1并置switching，保留旧last_verified；失败保持可见目标／generation／verified状态，仅记录本次收据。
- online必须匹配当前target／generation及switching或恢复状态。成功后才更新last_verified、清pending并verified；失败／uncertain保持目标与generation，置rollback_pending。失败候选不能以又一次成功online跳过回退；已回退旧目标若核验失败，则仍pending，可重新核验旧目标后恢复verified。
- rollback仅允许恢复前态保存的last_verified，不许第三目标；成功generation+1、visible回旧目标但仍switching，等待线上核验；失败继续rollback_pending，不伪报恢复。prepare／preflight／notify收据不更新CurrentPointer。
- 重放与前态last_receipt_ref相同的已验证收据返回完整原指针，generation及updated_at不再改变；仍需调用方提供匹配当前generation的可信前态。检查过期generation、时间倒退、目标或renderer错配、未知字段／版本／bool UInt。
- `services/publication/pointer.py`提供纯构造器及公开投影；公开对象严格只有generation／visible／phase且不共享可变内部引用。未添加HTTP端点或缓存策略实现。

### A2b内部证据和持久化边界

`current_pointer_evidence`精确为`{operation,previous,expected_generation,updated_at,receipt,receipt_evidence,bootstrap}`；operation为initialize／bootstrap／apply_receipt。bootstrap是来自可信基线验证适配器的`{target,verification_ref}`配对，代码检查封闭形状与legacy类别，但不证明远端原件存在、verification_ref类型／内容确实对应target或回退演练发生；这些来源配对必须由B/F适配器核验。其余操作禁止混入bootstrap信息，apply_receipt重验A2a完整收据及证据。

本批把previous作为可信锁内读取的已验证前态，检查其结构及本次转换一致性，不在此重建完整旧状态历史。后续协调器必须确认前态真实、持锁读取及原子CAS、当前lease/fence有效、收据已持久化、bootstrap基线及即时授权有效；纯函数可推导状态不等于真实写入或发布。initialize不能据此覆盖已有DO，重放也不能绕过生产令牌检查。

### A2b实际检查与提交

15项新增专项、74项M12回归、31项共享合同、7项治理、12项状态，共139项通过，无跳过。覆盖正常初始化至核验、legacy bootstrap边界、回退／回退失败及再次核验、失败候选拒绝跳过恢复、第三目标拒绝、stale generation、完整收据重放、混合renderer／类型反例、单例重复和公开投影隔离；文档链接、diff及机器状态一致性通过。未重审M11，跨日端到端仍未执行。

与本段同属独立提交`feat: add M12 current pointer transitions [skip ci]`，父提交1d4ba84a244760f62f092b98cb3462efefa7bd9f；完整SHA见交付消息。无持久存储／工作流／页面变更，可撤回本批代码测试并保留治理历史。未合并、推送、部署、生产启用或对外通知。


## A2b独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认bf4a705ef77cd87e911e3f628ab866a0d07076f3在CurrentPointer纯转换及最小公开投影范围通过。审核员运行139项测试，串联promote、online失败、rollback失败／成功、旧目标online失败／成功；同收据重放保持完整状态和时间，6次旧generation操作被拒绝。真实前态、bootstrap基线、收据持久化、认证和lease／fence／CAS仍不在通过范围。

## B1a：私有R2原字节归档绑定（待独立审核）

`services/publication/archive.mjs`新增显式注入R2绑定的ImmutableArchive，仅提供put／read。采用设计第5节七类永久对象键空间，拒绝staging、任意根及路径穿越；raw／indexes键须与原字节SHA-256一致。其它身份键与合同身份的对应由后续可信协调器核验，本层不解析业务JSON、不复制Python合同验证逻辑、不登记权威引用。

输入为Uint8Array和精确`{sha256,size_bytes}`，摘要格式为sha256冒号加64位小写十六进制。写前复制输入并校验实际摘要／长度，通过R2原子If-None-Match星号条件写入，随后无条件读回原字节，重算摘要／长度并逐字节比较。同键同字节返回相同描述符，冲突不覆盖；写异常或读回复核失败不确认成功，重试仍使用原键和原字节。只返回`{key,sha256,size_bytes}`字节定位信息，不充当合同验证、批准或权威登记收据。读取亦按期望摘要／长度检查原件，不依赖ETag或可修改元数据。

API依据为[Cloudflare R2 Workers官方参考](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/)的条件put和get／arrayBuffer；条件不满足返回null，仍需读取并比较既有对象。实现不调用delete、不提供普通覆盖写或外部HTTP入口，不增加绑定配置、依赖或工作流。

### B1a验证及未覆盖边界

9项Node专项采用本地R2绑定替身，覆盖七类键及UTF-8换行原字节、20次同键并发、异字节竞争、非法路径／描述符、调用者中途修改输入、缺失／损坏读回、响应丢失及读取故障恢复、返回值隔离和无删除接口。该测试不证明真实云存储、永久保留锁、桶私有性或角色权限已经配置；这些配置必须在上线授权后独立核验。当前实现整对象缓冲，正式编排接入前须对真实最大对象体积及Workers内存上限验收，不能据此声明已支持全量行情归档。

尚无DO索引、身份认证、当前授权、跨任务锁、队列、实际CAS及发布接线；R2存在对象不等于已验证或已登记事实，孤立对象不进入权威库存。既有ShadowStore守门不变。跨日端到端仍未执行，无运行通过声明。本批只完成B的字节传输基础，后续登记必须重新验证合同身份、原件、真实前序和当前令牌，不能直接信任调用方描述符。

本批检查：9项Node专项、7项治理及12项项目状态测试；新增文件定点lint、机器状态一致性、文档链接与差异格式检查。独立提交`feat: add M12 immutable R2 archive binding [skip ci]`，父提交bf4a705ef77cd87e911e3f628ab866a0d07076f3，完整SHA见交付消息。回退可撤销本批模块／测试，保留治理记录；尚无真实存储对象需迁移。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B1a独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认13d9925f274a9af9fc15092aa57d3e86c5bc1ffa在字节归档适配器及本地R2绑定替身范围通过。审核员自行运行28项测试、20组六方不同字节竞争，均只有一个成功，140次读回且原键重试保留赢家；另核对官方条件put接口，diff通过、HEAD不变、工作区干净。真实云桶、无限保留锁／私有权限、最大对象内存、生产认证及DO／lease／CAS不在该结论范围。

## B1b：SQLite持久租约生命周期（待独立审核）

`services/publication/leases.mjs`新增内部LeaseStore，直接使用SQLite-backed DO的sql.exec和transactionSync API。五类资源保持设计第5节边界，daily校验实际日期；服务端时钟，TTL固定300秒，续约不改fence，runner每60秒续约的调度留后续。每个资源保留递增fence，释放不删除记录；恰好到期视为失效。有效期内同Job重复acquire返回原租约且不延长TTL，另一Job被拒绝；过期／释放后重新授予加1，即使Job相同也拒绝旧fence。renew／release在同一事务比较epoch、完整owner Job、当前fence和有效期；不同epoch、旧令牌、非owner、无租约及超出安全整数范围均失败关闭。

SQLite三表保存epoch／服务时钟水位、租约及只追加租约操作日志；每次初始化／授予／续约／释放的前后状态与日志同事务提交，日志失败一起回滚。服务时钟比已记录成功操作倒退时拒绝操作。默认时钟来自Date.now，测试才注入固定时间。打开存储只建表，不激活epoch；initialize仅是未来可信控制面的一次初始化接点，同epoch重放不清表，不允许以另一epoch覆盖。epoch缺失但租约／日志尚存时要求恢复；没有自动重建、删表、租约epoch轮换或旧导出恢复入口。

返回内部句柄`{epoch,lease}`，lease精确为设计的`{resource,owner_job,fence,expires_at}`；续约／释放令牌为`{epoch,fence}`，请求另带resource及可信Job。expires_at由服务时间转换为UTC字符串。Job仅按已验证原始字段排序保存并比较，不在JS复制Python的Job合同／身份认证逻辑；不接受输入时间作为过期依据。该类尚无HTTP/RPC暴露，未来认证适配器必须提供经唯一合同入口验证且与真实认证身份绑定的Job，不能将客户端JSON直接注入。获得句柄不证明当前生产批准有效。

### B1b实际检查与边界

12项专项使用Node本地真实SQLite及DO同步API薄适配，覆盖五族／TTL、完整Job变化、acquire重放、到期接管、释放后再授予、epoch隔离、文件数据库重开、日志失败事务回滚、非法资源／时钟／令牌、部分状态丢失、fence溢出和两个实例争用同一SQLite状态。首次测试发现本地Node版本没有Statement.columns，已将测试薄适配改为直接all执行语句，12项最终全部通过；不改生产模块来迎合替身。此验证不等于Cloudflare DO调度、输出门或远端落盘已通过。

本批仅租约生命周期，不提供“验证令牌后脱离事务写事实”的接口；后续权威登记／队列完成／CurrentPointer CAS必须在其提交事务内重新比较当前认证授权、epoch、owner、fence及期限，不能缓存本批返回句柄当写入许可。release成功响应丢失后的重复release当前拒绝旧令牌，不承诺已实现业务操作重放收据；业务幂等、恢复查询、操作日志R2导出、真实初始化控制面及灾难恢复仍待后续。没有全量协调器或租约已保护生产写入的声明。

API依据为[Cloudflare SQLite-backed Durable Object官方参考](https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/)；同步事务回调不跨网络或await。没有新增Worker入口、绑定／迁移配置或依赖，无云资源创建。B1b不修改B1a、已有纯合同、ShadowStore守门或业务算法。跨日端到端仍未执行。

本批12项专项、7项治理及12项项目状态共31项通过；新增文件定点lint、机器状态一致性、文档链接和diff检查通过。独立提交`feat: add M12 persistent lease lifecycle [skip ci]`，父提交13d9925f274a9af9fc15092aa57d3e86c5bc1ffa，完整SHA见交付消息。本地测试SQLite已清理，无真实数据迁移；可撤回本包代码／测试并保留治理历史。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B1b独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认edd2a67e00423321f9848a4c06ff6fac86d5a9fe在内部租约生命周期及本地SQLite事务范围通过。审核员运行31项测试、100轮释放／到期再授予及198次旧token renew／release拒绝；fence连续递增，有效同Job acquire重放不延长TTL。官方transactionSync同步／回滚语义、diff及干净工作区已核对。生产认证、真实DO输出门／持久性、60秒续约及权威写入CAS不在本结论内；后续必须在提交事务检查实时授权及当前令牌。

## B2a：GitHub OIDC签名与固定执行身份（待独立审核）

`services/publication/identity.mjs`新增内部GitHubIdentityVerifier，使用平台WebCrypto RSA-SHA256验签，不实现密码学算法或增加依赖。issuer固定https://token.actions.githubusercontent.com，audience固定sage-vista-publication；只从该issuer的固定/.well-known/jwks取钥，禁重定向，不跟随token里的URL或内嵌公钥，无网络失败时的陈旧公钥回退。kid必须唯一、RSA签名公钥、至少2048位；只接受RS256／JWT及alg、typ、kid、可选x5t头，不接受crit或算法替换。token限制64KiB，JWKS流式限256KiB，取钥超时10秒；这些为传输限额，不改变业务合同。

服务端构造器固定精确策略`{repository,repository_id,workflow_ref,workflow_commit,code_commit,environment,subject}`并复制冻结，不能由请求覆盖。身份必须匹配main分支、仓库稳定ID及全名、精确工作流ref与workflow_sha、代码sha、环境和subject；run_id／actor_id保留十进制文本，run_attempt严格转换为安全正整数。验签和取钥等待结束后重新检查exp／nbf／iat，恰好到期拒绝，不用客户端时钟。本批只支持已固定的普通工作流，包含job_workflow_ref／job_workflow_sha的可复用工作流令牌失败关闭，避免将调用者工作流当作实际受信执行体。

返回`{job,code_commit,actor_id,subject,token_id,issued_at,expires_at}`已签名身份投影，job字段来自token，与现有M12 Job映射一致；时间字段为token的整数秒。这里没有权限／approved／grant结果，不生成PublicationAuthorization或验证任何业务合同。GitHub身份通过不等于环境批准通过；真实批准回执、允许审核人／禁自审、代码配置对应的实时grant／revoke及唯一Python合同验证接线仍留B2后续，当前未向LeaseStore、归档或DO写入口暴露任何调用通道。后续必须由服务端直接调用核验器，不能把外部同形JSON当已认证身份，也不能长期缓存此返回值充当许可。

### B2a实际检查及边界

13项专项使用本地RSA密钥真实签名／验签、受控Response公钥响应，覆盖完整合法身份、正文／签名篡改、11个固定claim分别替换与null、算法混淆／嵌入钥匙／外部URL、时间边界／等待期间到期、run及actor类型、可复用工作流替换、未知／重复kid、轮换／网络失败、异常／超大公钥正文、JWT编码、固定策略隔离及弱钥／无效时钟。没有取得或保存真实GitHub任务令牌，没有调用环境批准API，没有使用真实生产凭据。

核对[GitHub OIDC官方字段说明](https://docs.github.com/en/actions/reference/security/oidc)及[官方公开发现文档](https://token.actions.githubusercontent.com/.well-known/openid-configuration)，确认issuer、公钥地址、RS256和workflow_sha字段。正式配置仍须从可信上线配置固定真实仓库／工作流／环境／subject，不猜测subject格式；GitHub可自定义subject且新仓库默认格式可能不同。该内部核验器不支持GitHub Enterprise自定义issuer，也未声明真实protected environment已配置。jti只作为身份材料返回，不是单次消费或业务幂等证明；真实请求的重放／授权撤销／租约到期保护须在后续提交事务重新核验。

本批13项专项、7项治理及12项项目状态共32项通过；定点lint、机器状态一致性、文档链接及diff检查通过。独立提交`feat: add M12 GitHub OIDC identity verifier [skip ci]`，父提交edd2a67e00423321f9848a4c06ff6fac86d5a9fe，完整SHA见交付消息。无生产入口或存储迁移，回退可撤销本模块／测试并保留治理历史。M11不重审、跨日端到端仍未执行。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B2a独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认5782e16deef54e3af20c66dd2c2be592d255396b在GitHubIdentityVerifier本地真实验签、固定身份／密钥源／时效范围通过。审核员运行32项测试并逐段核对实现、GitHub官方OIDC参考、公开发现文档及JWKS地址；diff通过，工作区干净。真实工作流令牌端到端、环境保护／批准回执／审核人／禁自审、实时grant/revoke和事务写许可仍不在此结论内，外部同形JSON或缓存身份不能当授权。

## B2b：GitHub环境批准观测（待独立审核）

`services/publication/environment_review.mjs`新增GitHubEnvironmentReviewVerifier，verify只接收原签名token，并直接组合B2a验证器。服务端固定B2a身份策略、环境稳定ID、工作流稳定ID和允许的审核人稳定ID集合；只读API凭据在内部构造时注入，不接受请求提供的Job、审核人、API文档或目标URL。请求固定api.github.com、对应仓库及GET方法，禁止重定向，不跟随响应URL／分页Link，无陈旧缓存兜底，单响应流式限1MiB、单请求10秒超时；生产凭据与权限配置待上线卡批准后接入，本轮仅测试凭据。

读取顺序为当前run、环境保护设置、该run批准历史、再次当前run。run必须与已签名身份的run_id、repository_id／全名、main、代码sha、固定workflow_id、actor匹配，且workflow_dispatch、第1轮、in_progress／未结论；triggering_actor与原actor一致。环境必须精确匹配ID及名称，恰有一条required_reviewers规则且prevent_self_review=true，审核人全为User且ID集合与服务端允许集合精确相同，不按login或Team推断成员。该环境批准记录必须唯一且approved，审核人须在允许集合中且不是发起人；零记录、冲突／重复、同名异ID、异名同ID、未知审核人、自审、API失败或不完整响应全部失败关闭。其它环境记录不替代本环境。

官方批准历史只按run_id提供，没有批准级run_attempt或批准发生时间；不能把环境created_at／updated_at当批准时间。本包因此对新授权的环境观测只接受尚未重跑的第1轮，取回历史前后都核对当前run轮次，拒绝将旧批准带入重试。新批准流程失败后需用新的workflow_dispatch run取得新回执；已经归档的有效授权仍可供日常任务重试使用，不要求每天重批，不限制B2a认证任意合法run_attempt。此为当前可信回执的失败关闭边界，不伪造API缺失字段。

返回`{identity,approver_id,environment_id,observed_at,documents}`，documents含四个GET原URL、原UTF-8字节、实际SHA-256及长度；保留空白／换行以便B1a归档，observed_at只表示服务端观测时间。读取及摘要计算后再次检查身份有效期，不输出原token或内部API凭据，不生成approval_evidence_ref、PublicationAuthorization或生产许可。

### B2b验证及未覆盖部分

12项专项使用本地真实RSA签名的OIDC令牌、B2a真实验签及受控GitHub GET响应，覆盖合法观测／原字节摘要、伪造JSON／签名、旧重试与读取期间重跑、run来源替换、环境保护／允许集合、自审及显示名冒充、零／重复／冲突批准、环境条目全集检查、网络／重定向／分页／超大正文／解析失败、读取期间token到期及策略隔离。加7项治理、12项项目状态共31项通过；定点lint、机器状态一致性、本地文档链接、diff检查通过。没有调用真实仓库API、取得真实令牌或审核批准任何任务。

依据[GitHub workflow run／批准历史官方API](https://docs.github.com/en/rest/actions/workflow-runs#get-the-review-history-for-a-workflow-run)及[环境保护官方API](https://docs.github.com/en/rest/deployments/environments#get-an-environment)。当前API版本固定2026-03-10。只读调用权限为Actions及Environments所需的read范围，最终GitHub App／凭据配置留后续，不在此创建或授予权限。

**尚未绑定批准请求正文**：环境批准证明哪个用户放行了哪个固定执行run，不能单凭本结果证明用户批准了任意调用方传入的配置、范围、模式、期限或grant／revoke请求。后续必须把该run与预先归档且冻结的唯一授权请求绑定、归档本包原件、经唯一Python合同入口验证，并在DO提交事务重验身份有效期、当前批准链及lease令牌。没有把API观测当作跨服务原子快照；当前环境配置和批准事实核验不代表此刻已具有生产许可。授权工作流／环境实际配置、批准请求绑定、存储登记、即时撤销、队列／指针CAS及真实端到端继续排队。M11不重审，跨日端到端仍未执行。

独立提交`feat: verify M12 environment review observations [skip ci]`，父提交5782e16deef54e3af20c66dd2c2be592d255396b，完整SHA见交付消息。只新增内部模块／测试及治理记录，可撤回本批实现并保留治理历史；没有已创建的远端对象需迁移。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B2b独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认9d6fd8d6ce782380b191badc94f660dc15710f1c在真实B2a验签＋受控API环境批准观测范围通过。审核员逐段审读并运行31项测试，核对官方API无批准轮次／时间字段，确认第1轮且前后in_progress限制有依据。diff通过，工作区干净；不代表用户已批准任意请求正文。唯一冻结请求绑定、实际归档、Python合同验证及DO内实时授权链／租约检查仍须实施。

## B2c：批准run绑定固定提交中的请求原件（待独立审核）

在GitHubEnvironmentReviewVerifier增加verifyRequest(token)，内部先调用已审核verify取得真实验签／环境观测，再从同一OIDC代码提交读取固定路径`config/publication-authorization-request.json`。该固定路径不接受请求参数覆盖；没有创建真实授权请求文件或grant／revoke。每个新批准run只关联其执行提交该路径唯一原件，提交内的文件在run启动前已经存在，取证时不用浮动main或调用方上传的正文。运行工作流向审核人呈现该固定原件的接线仍留后续，不把本包当作人已阅读请求全部字段的证明。

只读Git API依次取得指定commit、根tree、config子tree及blob，再次读取当前run。commit SHA必须等于已签名身份SHA，tree SHA逐层匹配且非递归结果truncated=false；每级路径唯一，目录只能040000／tree，最终只能100644／blob，拒绝symlink、可执行文件、gitlink和目录替代。请求原件1—65536字节，blob SHA／size／encoding与树条目绑定，严格base64解码并保留原字节；重算Git的SHA-1(blob头＋字节)及原件SHA-256／长度。所有URL由固定仓库与已验证SHA构造，不跟随响应中的url字段。身份到期、读取期间重跑或run不再符合B2b条件均拒绝返回。

返回`{review,observed_at,request,documents}`：review为B2b四份原件观测，request精确为`{source_commit,path,blob_sha,bytes,sha256,size_bytes}`，documents追加commit／两层tree／blob／最终run五份原始API字节证据。source_commit指冻结请求的执行提交，不自动替代请求内拟批准的业务code_commit；本包不修改或推导请求字段。commit与tree关联以固定GitHub HTTPS API返回为来源证据，blob原字节另行重算Git摘要；没有声称重建原始Git commit序列化或验证提交签名。后续实际归档使用B1a，原件来源和Python请求解析接线完成前不得登记授权。

### B2c实际检查与范围

新增9项专项＋原B2b 12项共21项Node测试，覆盖合法固定路径／原字节、无批准不得取件、commit／tree／截断／路径多匹配、各种非普通文件、blob身份／编码／长度／内容替换、大小边界、取件期间rerun／过期、源故障和不跟随外部URL。特意验证合法Git字节即使不是请求JSON也只能返回来源材料，不产生authorization_id或permissions；请求是否满足业务合同仍由唯一Python入口判断。加7项治理及12项状态共40项通过；定点lint、机器状态／文档链接、diff通过。

依据[GitHub Git commit API](https://docs.github.com/en/rest/git/commits#get-a-commit)、[tree API](https://docs.github.com/en/rest/git/trees#get-a-tree)及[blob API](https://docs.github.com/en/rest/git/blobs#get-a-blob)。源码读取还需要Contents read权限；本轮只有本地受控响应，未访问真实私有仓库或改凭据／平台设置。没有新增配置依赖或业务计算，不重审M11。请求语义、批准范围／版本／前序、实际原件归档、授权线性登记、实时撤销／lease／CAS和跨日端到端仍未完成；跨日样例仍未执行。

独立提交`feat: bind M12 review to frozen request source [skip ci]`，父提交9d6fd8d6ce782380b191badc94f660dc15710f1c，完整SHA见交付消息。只改既有环境核验模块、其专项测试及3个治理文档；可以撤回本包方法／测试并保留治理记录，不影响已有verify接口。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B2c独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认4b8b01fdda6284591ed7c5a8c6c29a486c685dde在固定执行提交→固定路径→原blob绑定范围通过。审核员逐段审读并运行40项测试，核对官方tree/blob接口；原字节Git SHA-1／SHA-256、固定路径／普通文件守门及取源后run／时效检查符合范围。diff通过、HEAD不变、工作区干净。来源一致不等于人已批准正文，请求展示／语义、业务code_commit分离、实际归档、Python合同和DO实时链／lease／CAS仍须后续落实。

## B2d：冻结请求语义及唯一合同绑定（待独立审核）

在`services/contracts/validation.py`提取原有嵌套请求规则为唯一_m12_authorization_request_fields，原PublicationAuthorization字段验证和新publication_request_body共同调用。固定请求文件正文精确为既有十字段`action,prior_authorization_ref,config_ref,code_commit,publication_mode,scope,effective_from,valid_until,permissions,reason`，不增加schema、审核人、控制SHA或运行身份字段。PublicationAuthorization 1.0.0最终字段／身份公式和合法grant／revoke含义保持不变，因此不升级合同或业务规则版本；只扩展内部可信原件证据接点。

publication_request_body(source, source_commit=...)接B2c的六字段原件描述，要求独立注入的可信控制提交与原件source_commit一致、固定路径、1—65536字节不可变bytes、严格整数长度及实际原字节SHA-256／Git blob SHA-1。复用既有严格JSON解析器，拒绝重复键、非法UTF-8、非对象、NaN／Infinity及指数溢出；缺字段／多字段、非法模式或策略权限、错Ref／日期／代码版本、空白原因等由同一请求规则拒绝。解析只使用已核对原字节，不接第二份可覆盖正文。

PublicationAuthorization的内部publication_authorization_evidence可增强为原五字段加`request_source,source_commit`。两字段只要出现其一就必须同时存在；在统一合同入口重新解析原件，request声明须与原件规范内容完全相同，然后继续原有完整历史／直接前序／撤销目标检查。既有build_publication_authorization无需消费者新增校验；构造器、单对象及集合验证都经过该路径。source_commit只标识保存请求的控制提交，原件内code_commit仍为实际请求的业务目标，不覆盖或要求两者相等；新的控制提交可撤销前一业务代码／配置，仍不得换掉撤销目标。

### B2d实际检查与保留边界

10项新增专项覆盖合法grant／revoke、控制和业务提交分离、五种合法字段重签替换在三个入口共15次拒绝、十字段缺失／未知字段、权限／类型／日期／Ref、严格JSON、字节／hash／Git blob、部分增强证据、前序／撤销目标与输出隔离。99项M12专项／回归、31项共享合同、7项治理、12项项目状态共149项通过；机器状态／文档链接、diff检查通过。合成新旧可信证据构造出的合法授权完全相同，不改变既有内容身份。

本批是纯原件语义／证据一致性，不执行GitHub、R2、DO或运行时批准。保留原五字段可信注入路径以支持已有纯合同、历史及合成验证，不把它升级为生产认证入口；后续生产适配器必须由B2c直接取得原件并强制提供增强证据，不能允许外部删去两字段降级。source_commit及原件字节的真实来源仍由上游认证取证保证，纯函数不能证明同形JSON来自GitHub。实际原件归档、approval_evidence_ref与完整观测绑定、审核人看到固定请求的工作流、业务目标／配置实际库存验证、当前授权链及lease锁内登记仍待实施；不得以构造出的合同当作已生效许可。跨日端到端仍未执行，M11不重审。

独立提交`feat: validate M12 frozen authorization request semantics [skip ci]`，父提交4b8b01fdda6284591ed7c5a8c6c29a486c685dde，完整SHA见交付消息。只改唯一合同模块、新增专项测试及3个治理文档；可撤回本批内部原件接点并保留记录，无存储迁移。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B2d独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认c69951bc46ccffc27b0cbbcc9aaac29a780dc356在原件语义与授权合同绑定范围通过。审核员运行149项测试，另删除单一source字段／重签reason替换共9次三入口反例被拒绝；原合法身份、控制与业务提交分离及撤销前序不变。diff通过、HEAD不变、工作区干净。旧五字段纯注入路径非生产入口，后续必须强制verifyRequest＋增强路径；来源冻结仍不能替代正文批准或事务内授权。

## B2e：完整观测原件归档及证据引用（待独立审核）

`services/publication/review_archive.mjs`新增内部ReviewedRequestArchive，构造时固定身份／审核政策及R2绑定，archive只接签名token。内部直接组合B2c verifyRequest与B1a ImmutableArchive，不存在接收外部“已验证观测”JSON、可覆盖请求正文或退回五字段可信证据的方法。先核验来源，再写请求原件及九份API原件到raw/<sha256摘要>，全部条件写入并读回原字节核对完成后，才写私有authority/<摘要>.json批准观测清单。清单自身同样条件写入和读回复核，任意失败不返回完成。

清单是字节归档清单，不是PublicationAuthorization或新的业务批准合同。精确内容为`{kind:'github_environment_approval_observation',version:1,identity,approver_id,environment_id,observed_at,review_observed_at,request,documents}`。identity及两观测时间来自真实取证流程；request为source_commit／path／blob_sha加已归档key／sha256／size_bytes；documents为九个`{role,url,key,sha256,size_bytes}`，顺序固定run_before_review、environment、review_history、run_after_review、source_commit、source_root_tree、source_config_tree、request_blob、run_after_source。同字节run原件可共用raw键，九个角色位置仍完整保留，不因去重漏掉核验步骤。清单用UTF-8无空白、键排序JSON保存；不保存原token或API凭据。

清单完整原字节的SHA-256为F，引用精确为`{id:'approval-observation:'+F,content_fingerprint:F}`；与authority键及返回字节定位描述绑定。archive返回`{approval_evidence_ref,bundle,request_source}`，request_source包含已复核原件字节副本，便于后续Python增强证据接线。引用只定位私有观测清单，不表示权威索引已经登记、正文合同已验证或权限生效。来源来自服务器内部取证对象，不能把外部返回值同形JSON再当成已认证材料。

每次原件写入前、清单写入前及读回后均检查当前服务时间与token期限，过期不返回完成。失败／过期可以留下原件或完整但未登记的清单，保留为孤立审计材料，不删除、不进入权威库存。重复相同观测返回同一引用并复用原字节；新观测时间、token身份或API字节变化会形成新观测清单，不覆盖旧件，不能因此重复授予授权。DO后续必须按已绑定run／请求执行授权幂等、验证完整原件和当前链／lease，而不能只看清单存在。

### B2e实际检查与边界

8项新增归档接点专项＋21项取证回归共29项Node测试，使用本地真实RSA／B2a签名核验、受控GitHub响应和R2绑定替身。覆盖九角色原件及SHA引用、11次条件写／读回、相同观测重放、外部伪造JSON／无批准／坏来源不写入、部分原件失败、清单响应丢失重试、损坏原件／读回、归档中途及末次过期、变化观测保留历史。加7项治理、12项项目状态共48项通过；定点lint、机器状态／文档链接、diff检查通过。

本批实现实际R2绑定调用路径，但测试没有真实云桶、角色权限／无限保留锁或远端持久性证据。没有DO或RPC／HTTP入口，API凭据和存储能力仅内部注入；生产配置及权限隔离仍待上线卡与接线验收。尚未运行Python语义验证或形成授权记录；后续必须从已持久化清单重验原件、强制B2d增强证据，把approval_evidence_ref与请求／Job／approver完整绑定，并核验真实业务目标／config、审核人可审阅工作流及当前授权链／lease。原件存在不能当作已批准任意请求或生产许可。跨日端到端仍未执行，M11不重审。

独立提交`feat: archive M12 approval observation evidence [skip ci]`，父提交c69951bc46ccffc27b0cbbcc9aaac29a780dc356，完整SHA见交付消息。仅新增内部归档组合器、扩展现有取证测试及3个治理文档，无业务算法／配置变更；可撤销本包并保留记录，无真实数据迁移。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B2e独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认d414597f18115dee6f7f9bfd05fdc035d21f8bbd在内部签名取证→原件归档→完整清单引用组合范围通过。审核员运行48项测试、逐段检查原件先读回／清单后写、字节hash引用、失败／过期／幂等及不留原token／凭据；diff通过、HEAD不变、工作区干净。受控API／R2替身结论不覆盖真实云或生产授权，实际归档原件、Job／审核人／请求及DO当前链／lease仍须后续重验。

## B2f：归档清单原件的唯一合同重验（待独立审核）

在`services/contracts/validation.py`增加publication_approval_archive_body，输入仅为可信读取的`{bundle_bytes,objects}`及预期approval_evidence_ref；objects为本清单所需raw键到不可变bytes的精确映射。重算清单原字节SHA-256／Ref、规范字节编码、kind／版本及封闭字段；逐一验证请求与九角色API原件的长度／hash／raw键，缺项、多项、重复角色、顺序或URL替换拒绝，同字节多角色可以共用同一raw对象。归档JSON仍复用既有严格解析器，仅对review_history显式允许数组；原Manifest／请求等对象边界默认不变。

源身份使用既有Job校验，核对观测在已存身份issued_at／expires_at范围内；控制提交由identity绑定到固定请求原件，经B2d解析业务请求，不用控制SHA替代业务code_commit。Job的run／attempt／仓库稳定身份／actor与三份run原件对应，环境和审核人对应环境／批准历史原件；源码commit／两层tree／普通文件／blob关联及原字节一致性再次检查，九个URL必须由对应仓库、run、环境和Git对象身份导出。此处重验归档内部关联，不重新实施Github签名或外部政策认证；例如workflow_commit、subject的真实签名来源仍依赖受信B2a取证，不从本清单存在推断真实性。

publication_authorization_evidence增加可选的approval_archive接点；只要带该字段，request_source和source_commit也强制存在，不能仅删除两个source字段退回五字段路径。唯一入口从归档原件推导request／request_source／source_commit／Job／approver，与声明逐项比较，再走已有完整历史／直接前序规则。另显式调用既有Job／Ref／Text规则验证可信证据自身，避免仅靠Python字典相等让bool冒充Job整数。构造器／单对象／集合共享该路径；没有新业务合同、权限、身份公式或消费者侧第二套规则。

### B2f实际检查与未完成接点

6项新增跨语言专项直接将B2e通过实际组合器写入本地R2替身的清单／原件字节送入Python解析／授权构造／单对象／集合入口，验证编码和身份一致，未重新手写一套理想化清单样本。覆盖错误Ref、缺失／额外／损坏原件、重签kind／version／role／URL／元数据、Job／审核人／时间替换、原API内容与blob变更后重算所有相关hash、删除增强字段或替换声明。35项Node专项／取证回归、99项M12 Python、31项共享合同、7项治理、12项项目状态共184项通过；定点lint、机器状态／文档链接、diff检查通过。Node跨语言测试需本地python3，只用标准库和当前源码。

本批输入是可信读回字节上下文；测试字节来自真实组合器＋本地绑定替身，不代表已接入真实R2读取／权限或DO。纯校验不能证明调用者提供的自制清单来自受信协调器；原token未归档，不能离线重验OIDC签名。后续运行入口必须从受控归档及真实取证登记来源取得预期Ref／字节，强制完整approval_archive上下文，并在提交事务重验当前Job／授权链／lease；不得接受外部完整重造的同形JSON，也不得删除整个归档上下文退回旧纯合同路径。旧五字段／仅source增强路径仍仅保留为内部纯验证边界，不增加生产入口。

来源和原件一致依然不是当前生产许可。审核工作流展示冻结请求、业务目标／config实际库存校验、原件引用权威登记、可信Python验证收据及DO当前链／lease／CAS接线仍待后续；归档日期检查验证历史一致性，不把历史身份窗口当作现在有效。跨日端到端仍未执行，M11不重审。

独立提交`feat: validate M12 archived approval evidence binding [skip ci]`，父提交d414597f18115dee6f7f9bfd05fdc035d21f8bbd，完整SHA见交付消息。只改唯一合同模块、现有环境／归档专项测试及3个治理文档；可撤回本包归档接点并保留历史，无真实数据迁移。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B2f独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认38424b4aff6ad91c07248dd72f017b91959eb390在归档内部一致性与增强Python合同接点范围通过。审核员运行184项测试、逐段核对清单Ref／规范原字节、全集／角色／URL／请求／运行身份／审核人，增强字段及Job bool守门生效；旧对象默认解析路径未放宽数组。diff通过、HEAD不变、工作区干净。完整自制一致清单仍不能冒充可信来源，真实取证／受控读取、强制完整上下文和DO实时授权仍须接线。

## B2g：受控读回与强制归档构造接点（待独立审核）

ReviewedRequestArchive增加readForValidation(token)，内部先完成自身archive(token)获取预期Ref及定位，随后通过同一R2绑定再次读取清单原字节并重验hash／长度，再按清单引用读取全部不同raw原件，拒绝同键元数据冲突。返回仅`{approval_evidence_ref,approval_archive:{bundle_bytes,objects}}`，不复用archive返回的请求字节副本充作存储读回，不纳入其它孤立对象或客户端选择的引用。所有输入来源由已绑定策略／凭据的内部B2a—e流程取得；不新增接收“verified JSON”或任意archive key的通道。

取件前及末次读回后重验身份时效；已成功归档之后，清单／任一raw读取缺失、损坏、故障或token过期，均不交出部分验证输入。不同角色引用相同raw字节只读一次，角色完整性继续由B2f唯一Python入口验证；JS只执行存储定位／摘要检查，不复制业务语义。此前原件及孤立清单不删除，不把读回成功记作DO权威登记。

`services/publication/authorization.py`增加build_publication_authorization_from_archive(archive,approval_evidence_ref,history=...,generated_at=...)；强制完整归档输入，经B2f推导请求／source／Job／审核人，自动构建完整增强证据，再复用既有授权构造及唯一合同验证。函数无request、approver_id、Job或source_commit覆盖参数，也无退回旧五字段上下文选项；缺原件或错误Ref不能构造。没有新增业务合同／规则／权限／身份公式，原纯构造器保留用于既有内部纯验证。

### B2g实际检查与未完成边界

新增7项读回／跨语言专项＋35项原取证／归档／合同接点回归共42项Node测试；用实际内部组合器的受控R2读回来驱动Python强制构造器，验证原业务目标与控制提交分离、所有读取确实发生、无调用方引用选择、排除孤立对象、二次读取清单／原件失败、取件时失效、覆盖参数拒绝及返回值隔离。加15项授权、10项请求语义、7项治理、12项状态共86项通过；定点lint、机器状态／链接和diff检查通过。未改共享合同入口，未重复无变化全套业务测试。

这是内部绑定调用及Python函数接点，测试仍用受控GitHub／R2绑定替身，不是已部署RPC／HTTP服务。真实跨进程传输、可信Python验证收据、DO持锁提供完整当前历史／当前授权／lease及最终原子登记尚未接入；不能把Python纯函数可接受同形bytes视为认证。将来HTTP入口必须直接使用内部readForValidation路径，并由服务端取得history，不允许外部提供自制清单、预期Ref或截断历史。当前构造出的PublicationAuthorization只是未登记合同，不是生效授权。审核人可审阅冻结请求的工作流、真实业务目标/config库存及生产设置仍待后续；跨日端到端仍未执行，M11不重审。

独立提交`feat: connect M12 controlled archive reads to authorization builder [skip ci]`，父提交38424b4aff6ad91c07248dd72f017b91959eb390，完整SHA见交付消息。只改内部归档组合器／纯构造器、现有专项测试及3个治理文档；可撤回本批接点并保留历史，无真实数据迁移。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B2g独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认aa4848802a9baccde1f5dbb2a30c13dfe46bad18在内部新取证→受控R2读回→强制Python归档构造范围通过。审核员运行86项测试、逐段核对实际读回／跨语言、故障／过期、覆盖参数拒绝及隔离；diff通过、HEAD不变、工作区干净。真实平台／跨进程通道和验证收据未覆盖，后续必须服务端取得完整持锁历史，不接受自制Ref／清单或截断历史，构造对象尚未登记／生效。

## B3a：持锁授权历史快照与持久验证票据（待独立审核）

新增内部AuthorizationStore，复用同一SQLite-backed DO storage和B1b LeaseStore。在publish/global当前lease事务内读取授权head／revision及完整有序索引，保存待验证票据和日志，不允许调用方传入历史或head。索引条目只包含不可变授权Ref、归档key／原字节hash／长度及直接前序Ref；验证位置连续、无重复身份、前序线性、条数等于revision及末尾等于head。真正授权正文仍在R2，读取并经Python唯一合同验证留后续；索引格式检查不等于正文已复核。

LeaseStore提取共用owner事务检查，renew／release继续复用；withOwnedLease只供内部硬编码同步SQL回调，在事务开始比较当前epoch、owner、fence、期限，并在回调结束前再次检查未过期，拒绝async回调或Promise结果，异常同事务回滚。AuthorizationStore只传内部固定闭包，不接受外部回调代码，不在事务中等待网络；回调类型守门不替代此内部使用约束。该包装本批保护的是票据准备，不声称已保护未实现的生产事实／发布写入。

四张SQLite表保存head、授权索引、票据和操作日志；新空库可建立revision=0／head=null，若head缺失但索引／票据／日志尚存，不自动当作空历史恢复。当前只实现prepareValidation(ownerJob,token,approvalEvidenceRef)，无授权追加／登记或消费票据方法。输入Job和批准证据Ref必须由未来内部B2g认证接线提供，此低层方法仅检查引用格式及lease持有关系，不独立证明批准来源或当前发布权限。

票据精确字段`ticket_id,resource,owner_job,epoch,fence,prepared_at,expires_at,approval_evidence_ref,expected_revision,expected_head_ref,history`，ticket_id为服务端UUID。history冻结完整索引描述，resource固定publish/global，期限取本次lease期限，不给调用者覆盖。相同epoch／Job／fence／lease期限／revision／head／证据Ref复用同一票据及prepared_at，不重复日志；读取既有票据要求对应准备日志完整一致。续约改变期限或head变化可生成新快照，旧票据原件保留，不能延长旧票有效期。票据／日志写入与lease检查同事务，日志故障或结束时过期均回滚。

### B3a实际检查及后续要求

11项新增＋12项lease回归共23项Node测试，使用真实本地SQLite和DO同步API薄适配，覆盖空／两条合成索引快照、重放、期限／epoch／owner／fence、索引缺项／位置／前序／head／归档定位异常、日志故障及事务内到期回滚、续约／head变化保留旧票据、文件数据库重开和部分状态丢失。加7项治理、12项状态共42项通过，定点lint、机器状态／链接／diff检查通过。历史行仅在测试中直接插入合成索引，不声称已运行授权登记或真实批准链。

下一步必须在事务外按该快照读取全部R2授权正文，交强制B2g Python构造器，并把可信验证结果绑定票据、完整历史及原件Ref；最终登记必须重新读取当前授权head／revision及当前身份／授权／lease，比较票据前态并原子追加授权索引和日志，不能仅凭旧快照或票据存在放行。当前无票据消费、通过收据、授权登记、有效授权查询、队列或CurrentPointer CAS。真实平台配置／凭据、业务目标/config和可审阅工作流仍待接线；跨日端到端尚未执行，M11不重审。

独立提交`feat: persist M12 lease-bound authorization validation tickets [skip ci]`，父提交aa4848802a9baccde1f5dbb2a30c13dfe46bad18，完整SHA见交付消息。只改内部租约包装、新增授权存储基础、现有lease专项测试及3个治理文档，无Worker配置／迁移／云资源操作；可撤回本包并保留治理历史，本地SQLite测试文件已清理。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B3a独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认2193c7235772c4fbe9499aa6de127bdeb7a3a8a2在完整授权索引快照、租约绑定准备票据和同步事务范围通过。审核员运行23项Node（11项新增及12项lease回归）和19项治理／状态共42项，确认完整性／线性前序／head、日志故障和到期回滚、重放、续约／head变化票据及文件重开。当前索引元数据是合成样本，票据仍仅为待验证输入，不代表正文验证或授权生效。

## B3b：完整授权字节历史与票据绑定构造（待独立审核）

新增内部AuthorizationPreparation.prepare(token,leaseToken)，串联B2g自身取证和受控归档读回，从该清单取得Job和批准证据Ref，再由B3a在当前publish/global租约事务内生成完整历史票据。事务外按每条冻结索引的归档键／hash／长度读回全部R2授权正文；末次读取后，AuthorizationStore.readPreparedValidation在当前租约事务中重读持久票据及准备日志，比较epoch／owner／fence、原票据期限与当前head／revision／完整索引。读取期间前序变化、租约丢失、票据缺失或不一致均拒绝。取件前后及最终事务后均检查取证身份未到期；不允许调用方选择Job、历史、票据、请求或Ref。

Python唯一合同入口新增publication_ticket_history，验证票据封闭字段、Job／批准证据绑定、UUID／整数／历史时间格式和完整条数，再逐份核对不可变bytes长度／SHA-256、严格JSON、既有授权合同身份及直接前序，最终head必须等于实际完整历史末尾。带validation_ticket或history_bytes任一字段时，另一字段及完整approval_archive／source上下文均强制存在，声明history必须与实际字节历史一致。build_publication_authorization_for_ticket从完整归档和票据字节历史推导输入，复用原构造器及唯一验证，不增加业务合同、权限或身份公式。

### B3b实际检查与未完成边界

新增8项跨语言／编排专项覆盖合法旧授权续接撤销、空历史首授、R2缺失或损坏、读取期间head或租约变化、末次读取身份到期、截断／额外／替换历史、票据字段和强制上下文反例。50项环境取证／归档／跨语言Node与23项租约Node共73项，加99项M12 Python、31项共享合同、7项治理和12项状态共222项通过；定点lint、机器状态／文档链接和diff检查通过。现有旧授权正文由Python构造器生成，索引在测试中合成插入；使用本地R2／GitHub绑定替身和真实本地SQLite，未验证真实历史批准来源、真实云权限或平台持久性。

当前结果仍是内部受控输入和未登记合同，未追加授权索引、生成可信Python验证收据或消费票据。Python纯校验只证明历史一致性，不能证明票据来自DO或目前仍有效；真实入口必须使用服务端持久票据及本包内部读取路径。Python处理完成后的最终登记仍须重新核对当前身份／授权、业务目标/config、lease、head／revision和票据前态，并在同一事务消费票据、追加索引与日志；本包末次读取检查不能替代该最终检查。跨进程可信回执通道、工作流请求展示、实际平台配置、队列及CurrentPointer CAS继续后续，旧纯验证路径不成为生产入口。跨日端到端仍未执行，M11不重审。

独立提交`feat: prepare M12 authorization from ticket-bound history [skip ci]`，父提交2193c7235772c4fbe9499aa6de127bdeb7a3a8a2，完整SHA见交付消息。仅修改内部准备／授权存储／纯构造及唯一合同入口、现有两组专项测试和3个治理文档；可撤回本包接点并保留历史，无真实数据迁移。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B3b独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认3e36cada8daf7d3d3edd1861d9add7796b9aba2d在内部取证、完整票据历史读回及Python唯一合同绑定范围无阻断。审核员逐段审读并自行运行50项环境取证Node、23项租约Node、99项M12 Python和50项共享／治理／状态，共222项通过；确认末次原件读取后重新核对持久票据／日志、lease、head／revision及完整历史，缺失、损坏、截断、上下文降级及读取期间状态变化均拒绝。diff通过、HEAD不变、工作区干净。结论不含票据消费、可信Python回执、授权追加或权限生效；最终登记仍需在Python完成后重验当前身份／授权、业务目标/config、lease及票据前态。

## B3c：Python验证原字节协议及绑定收据产物（待独立审核）

AuthorizationPreparation.prepareValidationInput(token,leaseToken)仅序列化自身B3b受控准备结果，无外部Job／引用／历史覆盖参数。输入为UTF-8 JSON，精确字段`protocol,approval_evidence_ref,approval_archive,validation_ticket,history_base64`，protocol固定`m12-authorization-validation/1`；approval_archive精确含`bundle_base64,objects`，objects仍为全部raw键到原件标准base64文本的映射，history_base64按票据顺序保存全部历史正文。唯一合同模块publication_validation_input复用严格JSON解析，拒绝重复键、非有限数、额外或缺失字段、旧上下文降级，以及非标准编码／空白／不规范填充位的base64。解码只恢复不可变bytes，不把传输格式正确当正文通过。

新增内部命令`python3 -m services.publication.authorization_validation`，只从stdin读完整输入，复用B2f归档唯一校验及B3b强制票据构造器，不接网络、凭据或权威存储。成功stdout精确输出`{authorization_base64,receipt_base64}`；两者为规范UTF-8 JSON原字节的base64，未生成签名或PublicationReceipt业务收据。合同失败返回非零码、stdout为空，stderr仅固定失败信息，不回显私有请求。未知故障同样不能产生成功材料，不自动回落其它构造路径。

内部验证收据精确字段为`protocol,verdict,validated_at,input_sha256,input_size_bytes,ticket_id,ticket_sha256,approval_evidence_ref,authorization_ref,authorization_archive`；protocol同输入、verdict只可能valid。input摘要／长度绑定整个实际输入原字节，ticket摘要绑定排序键、UTF-8、无空白的规范票据JSON；authorization_archive精确为`{key,sha256,size_bytes}`，指向authority/<授权语义指纹>.json并绑定输出实际原字节。authorization_ref保留既有合同身份，未改变身份公式。授权generated_at取已验证批准清单observed_at的UTC整秒，确保同一批准在不同时间／票据重验仍输出相同授权字节；实际本次验证结束时间另存validated_at（UTC毫秒）。开始／结束使用命令内部时钟，拒绝早于冻结准备／批准观测、到达票据或归档身份期限、时钟倒退及非整数时钟；这只是拒绝超期计算，不能证明DO现在仍持锁。

### B3c实际检查及下一接点

6项新增专项覆盖真实B3b输入→Python命令产物的首次grant和旧链revoke，逐项重算全输入／票据／输出字节摘要，重跑和晚时重验的授权字节稳定性，同义不同排版输入的原字节区别，封闭字段／严格base64／历史和原件篡改、冻结窗口端点，以及实际模块stdin/stdout成功与失败。56项环境取证／跨语言Node、99项M12 Python、31项共享合同、7项治理和12项状态共205项通过；定点lint、机器状态／文档链接和diff检查通过。新测试使用本地绑定替身和真实SQLite，命令测试仅注入本地时钟；没有运行真实GitHub工作流或云服务，也未重跑无变化的整套租约测试。

收据目前只是可校验的内部产物：任何人可重算摘要，不能凭其存在或verdict声明取得权限。下一包须由服务端持久绑定本次发送的完整原字节摘要／票据，认证固定验证工作流的回传身份，比较收据与服务端记录及授权输出，再按设计读回R2并完成当前业务目标/config／授权、lease、head及票据前态的最终同事务消费／追加；本包不接受外部成功声明，不建立可信回执接收入口、不写R2授权正文、不消费票据或追加索引。输入仍全量内存处理，真实最大历史规模与平台限制留运行适配验收。跨日端到端未执行，M11不重审；无算法、业务合同版本、政策、快照或生产入口变化。

独立提交`feat: emit M12 ticket-bound Python validation artifacts [skip ci]`，父提交3e36cada8daf7d3d3edd1861d9add7796b9aba2d，完整SHA见交付消息。仅修改内部准备器、新增Python验证命令、唯一合同传输解析、现有环境专项测试及3个治理文档。可撤回本包接口并保留历史，无真实数据迁移。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B3c独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认bf56d72d2c50c945b90f053377690902da39cac9在内部原字节验证协议及绑定收据产物范围无阻断。审核员逐段审读7文件，自行运行56项环境取证／跨语言Node、99项M12 Python及50项共享／治理／状态，共205项通过；确认封闭协议／标准base64、完整归档／票据路径、输入／输出hash和长度、票据与批准Ref绑定、重验授权字节稳定、冻结窗口及失败空stdout。diff通过、HEAD不变、工作区干净。限定通过不含可信回传认证、授权登记或生产许可，摘要不能替代身份认证。

## B3d：服务端输入归档与持久发送准备绑定（待独立审核）

AuthorizationPreparation新增dispatchValidationInput(token,leaseToken)，仅调用自身B3c准备路径取得完整输入，内部计算实际原字节SHA-256／长度及规范票据摘要。先通过既有ImmutableArchive写入raw/<输入摘要>并实际读回核对，再调用AuthorizationStore.recordValidationDispatch，最后返回`{dispatch,input_bytes}`。调用方不能选择输入正文、摘要、票据、Job或来源提交。原字节含批准原件及完整历史，保持私有；失败遗留对象不算已登记发送。这里的dispatch是“输入已冻结、可交给验证任务”的准备记录，未向GitHub派发任务、未证明Python已运行或接收输入。

新增SQLite表m12_authorization_dispatches，ticket_id唯一且dispatch_id唯一，同步日志operation为dispatch_validation。记录精确字段`protocol,ticket_id,ticket_sha256,input_archive,owner_job,epoch,fence,approval_evidence_ref,source_commit,identity_issued_at,identity_expires_at,expires_at,dispatch_id,dispatched_at`；protocol沿B3c，input_archive精确为`{key,sha256,size_bytes}`。source_commit是本次已验证执行身份的控制提交，不能替代授权请求中的业务code_commit。有效期取原票据和已验证身份的较早到期时间，不因lease续约延长。记录只是下一阶段回传比对的服务端依据，不代表授权批准已生效。

当前lease事务内重用唯一私有票据读取逻辑，验证持久票据／准备日志、完整head／revision／历史、当前epoch／owner／fence及原期限，整个冻结票据必须与本次准备一致；然后保存发送绑定及日志。LeaseStore.withOwnedLease增加仅供内部同步调用的可选deadlineMs，在事务开始和结束用同一租约时钟守门；结束时同时检查lease及本操作的更早期限，异常整笔回滚。原默认调用行为不变，不增加异步事务。相同票据和完整绑定重放保留dispatch_id、dispatched_at及原日志，不重复写入；相同票据换输入／来源／期限／摘要拒绝。丢失发送记录但日志尚在、记录存在但日志缺失或不一致均要求恢复；仅剩发送记录时也不能自动建立空head。

### B3d实际检查及未完成边界

新增6项SQLite专项及5项实际内部编排专项。覆盖同绑定幂等及不同输入拒绝、无效描述／旧lease／过期身份／head变化、日志故障回滚、事务内身份或原票据到期（含lease已续期）、文件数据库重开、记录／日志／head部分丢失，以及实际完整输入先写读回后登记、Python收据各hash与发送记录一致、返回值隔离、写入不确定留下孤立对象并一致重试、输入缺失／损坏、归档期间head／lease改变和身份到期。61项环境取证／跨语言Node、29项租约／存储Node、7项治理及12项状态共109项通过；定点lint、机器状态／文档链接、diff检查通过。未修改Python合同或业务代码，未重复无变化Python整套测试。

SQL低层方法只消费内部可信编排的描述，不独立认证自报hash、身份或R2来源；后续外部入口必须通过本包dispatchValidationInput，不可暴露低层方法或以纯prepareValidationInput替代持久发送绑定。测试用本地GitHub／R2绑定替身及真实本地SQLite，低层SQLite专项的字节描述是合成元数据，完整原字节来源由组合专项覆盖；真实平台权限／资源和最大输入规模尚未验收。

下一包仍须认证固定验证工作流回传、从持久发送记录取回原输入并比对收据与授权输出，读回归档授权原件；在最终事务重新检查当时身份／授权、目标/config、lease、head及票据前态，才可消费票据和追加授权索引／日志。本包没有成功回执接收、票据消费、授权追加或权限启用；准备记录和收据摘要均不能代替这些步骤。跨日端到端尚未执行，M11不重审。

独立提交`feat: persist M12 validation input dispatch bindings [skip ci]`，父提交bf56d72d2c50c945b90f053377690902da39cac9，完整SHA见交付消息。仅修改内部准备／授权存储／租约包装、现有两组专项测试及3个治理文档。无业务合同／政策版本变化；可撤回本包接点并保留历史，无真实生产数据迁移。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B3d独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认922a3a8ad3603755e52bcb37878fec1f24705e7d在服务端输入归档及持久发送准备绑定范围无阻断。审核员读取8文件差异及归档／票据／租约路径，运行61项环境取证／跨语言Node、29项租约／存储Node和19项治理／状态，共109项通过；确认先写读回再持锁核对完整票据／head／history、一致重放／冲突拒绝、日志故障和原票据／身份到期回滚、续租不延长原票据及部分状态丢失保护。diff通过、HEAD不变、工作区干净。记录仅证明发送准备，不证明已发送、执行或授权生效。

## B3e：固定执行身份回传及持久输入／收据字节比对（待独立审核）

新增内部AuthorizationValidationReturn.verify(token,leaseToken,dispatchId,resultBytes)，resultBytes为B3c命令stdout的完整Uint8Array，进入函数即复制，不能在后续await期间改写。服务端构造器固定身份政策及存储绑定，内部直接调用既有GitHubIdentityVerifier重新验签及核对固定仓库／main／workflow版本／控制代码提交／环境，不接受“已验证身份JSON”。本接点要求回传来自原发送记录对应的同一固定工作流run／attempt／Job，控制提交也必须一致；换工作流版本、换run、rerun或换控制提交均拒绝。原件中的actor再与本次已验签actor核对。允许同Job取得新OIDC token，但新token不能延长原dispatch、票据或lease期限。

AuthorizationStore新增readValidationDispatch(identity,token,dispatchId)，先仅定位持久记录以取得截止时间，随后在当前lease事务内重新读取并比较记录／日志、持久票据及完整head／history；比对Job、epoch、fence、批准Ref、控制提交、发送时间及原身份窗口。读取起末沿B3d deadline守门，不从调用方接收快照、输入Ref或输入字节。返回完整当前票据供核对，文件数据库重开仍读取原发送绑定；低层identity参数仅由内部实际验签路径供给，不公开成为RPC身份声明入口。

回传适配器按该记录的R2位置实际读回完整输入，重验hash／长度，再比较输入中的票据／批准Ref／原取证身份及规范票据摘要。resultBytes要求精确`{authorization_base64,receipt_base64}`的规范JSON及末尾单个换行；两份内层对象也要求规范UTF-8 JSON，标准base64须逐字回编码一致。此传输约束拒绝重复键、BOM、另一个成功声明、额外字段、非规范编码及替换输入。收据的协议／valid、input摘要和长度、ticket_id／摘要、批准Ref必须逐项等于持久记录和实际读回票据；授权输出实际原字节的摘要／长度必须等于收据，输出Ref／归档位置、Job、批准Ref及直接前序必须对应当前准备材料。validated_at必须为UTC毫秒，位于持久发送之后、冻结到期之前且不晚于服务端当前时刻。

所有异步读回／摘要结束后，再次在当前lease事务读取发送记录、票据及完整head／history，并要求与首次快照完全一致；失败不返回部分“通过材料”。成功只返回`{identity,dispatch,validation_ticket,input_bytes,receipt_bytes,authorization_bytes}`供后续内部登记接线，不保存授权正文／收据、不消费票据、不追加授权索引。Job／Ref／字节及时间比对属于传输绑定；本包不在JS重算业务合同、权限、身份公式或策略语义。

### B3e实际检查与信任边界

9项新增专项通过真实本地RSA验签、内部发送准备、实际R2替身读回及Python产物验证：正常回传／隔离、未签名或错误签名／政策／run／attempt／actor及当前控制政策变化、借另一dispatch的收据、原件／日志缺失或损坏、收据与输入／票据／批准／授权字节替换、输出元数据改写后重算字节hash、重复键／编码／假成功结构、读取期间head／lease／日志变化、未来或过期验证时间、新token不能延长旧期限。70项环境取证／跨语言Node、29项租约／存储Node、7项治理和12项状态共118项通过；定点lint、机器状态／文档链接／diff检查通过。未修改Python合同，未重复其无变化完整测试；实际固定工作流及真实平台仍未执行。

本包认证的是回传执行身份并核对材料绑定，不提供独立执行证明。信任前提是随后接入的固定工作流确实对服务端原输入运行B3c唯一Python入口，并原样回传其stdout，不能转发外部成功声明、替换输入或接受任意产物；OIDC本身不能证明已执行Python，也不能抵御该可信执行方伪造自洽收据和正文。故当前适配器不可单独成为生产许可入口，不能把本地通过称为完整可信验证／授权链已验收。后续固定工作流接线及其代码／配置检查仍须覆盖这个前提，不能用JS第二套业务验证补洞。

最终登记还须实际归档并读回授权及收据原件，再按当时身份／授权、目标/config、lease、head和票据前态同事务消费／追加；本包返回对象不能由外部提交后直接当作可信票据，最终入口必须自身调用内部验证路径。真实授权状态、业务库存、权限生效、CurrentPointer及跨日端到端继续后续，M11不重审。

独立提交`feat: verify M12 validation return identity and byte bindings [skip ci]`，父提交922a3a8ad3603755e52bcb37878fec1f24705e7d，完整SHA见交付消息。仅新增内部回传适配、扩展授权存储只读接点、现有两组专项测试及3个治理文档；无业务合同／政策版本变更，可撤回本包接点并保留历史，无真实数据迁移。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B3e独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认4d9e81547df972184c0aaa7d2cb73f7828b40556在内部回传身份认证与持久输入／收据字节绑定范围无阻断。审核员逐段读取7文件及OIDC Job路径，自行运行70项环境取证／跨语言Node、29项租约／存储Node及19项治理／状态，共118项通过；确认实际重新验签、原Job／控制提交／actor绑定、持久输入读回、字节与编码对应、外部bytes复制及末次异步后重查。diff通过、HEAD不变、工作区干净。结论仅覆盖认证与传输，OIDC和自洽摘要不证明Python执行，固定工作流实际执行接线仍须独立验收。

## B3f：授权与验证收据原件归档及最终读回（待独立审核）

新增内部AuthorizationValidationArchive.archive(token,leaseToken,dispatchId,resultBytes)，自身调用B3e实际回传认证／持久输入读回／字节绑定验证，不接受“verified对象”、自选Ref或归档位置。沿B3c收据中已核对的授权归档描述，将授权原字节写到authority/<授权语义指纹>.json；验证收据没有PublicationReceipt业务ID，按实际原字节摘要保存在raw/<摘要>，不占用业务发布生命周期的receipts命名空间。均复用ImmutableArchive条件写入和读回复核，无新存储规则或业务身份公式。

两份对象各自写入并读回后，再独立从R2读取授权及验证收据原件，不能用内存中的原输出替代最终读回。摘要计算后、每个异步写入／读取之间及最终读回之后，都通过现有readValidationDispatch在当前lease事务检查原发送记录／日志、票据／完整head／history、固定身份和较早期限，并比较初始快照不变。任一步故障或状态漂移，不返回完整归档结果；此前成功写入的对象保留为未登记材料，不能推断已授权。

成功返回B3e已验证上下文，并将authorization_bytes／receipt_bytes替换为实际最终存储读回字节，增加authorization_archive及validation_receipt_archive（各为精确key／sha256／size_bytes描述）。返回值只供后续内部登记入口使用，不允许外部把相同JSON提交为可信证明。相同授权与收据可一致重试；同授权位置异字节保留既有原件并拒绝，不覆盖。同一批准稍后重验仍使用相同授权字节，新验证时间形成独立raw收据，两份验证记录同时保留。

### B3f实际检查及未完成接点

8项新增组合专项覆盖：内部实际认证＋Python产物→两次写入、各自写后读取及两次独立最终读回（连同输入读回共5次读取）；返回值隔离；伪造verified对象／错误签名／替代stdout不触发写入；授权或收据写入不确定留孤立对象并一致重试；既有授权同键异字节拒绝；两种原件在最终读回时缺失或损坏；首次写入及末次读取期间head／lease／日志变化和期限到达；稍后合法重验保持授权字节且保留两份验证收据。78项环境取证／跨语言Node、7项治理及12项状态共97项通过，定点lint、机器状态／文档链接和diff检查通过。未修改合同、SQL存储或租约实现，未重复无变化Python／完整租约测试；测试仍为本地GitHub／R2绑定替身和真实本地SQLite。

本包继承B3e信任边界：实际固定工作流对服务端原输入执行唯一Python命令并原样回传的接线尚未完成，身份认证不等于独立执行证明。归档成功不证明该缺口已关闭，也不产生生效权限；当前没有公开HTTP入口、真实工作流运行、授权索引追加或票据消费。最终入口必须内部调用完整验证／归档路径，再检查当时身份／授权、业务目标/config、lease／head和票据前态，同事务消费票据并追加索引／日志。不能在本包之后仅凭对象存在或调用方返回JSON放行。真实平台配置、最大输入规模和跨日端到端仍待后续，M11不重审。

独立提交`feat: archive M12 authorization validation originals [skip ci]`，父提交4d9e81547df972184c0aaa7d2cb73f7828b40556，完整SHA见交付消息。仅新增内部归档组合器、扩展现有环境专项测试及3个治理文档；无业务合同／政策版本变化，可撤回本包接点并保留历史，无真实数据迁移。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B3f独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认5b2e8f3b48cea7cb5584cea1b106b6eea1f37ecd在内部授权／验证收据原件归档及最终读回范围无阻断。审核员逐段读取5文件，自行运行78项环境取证／跨语言Node及19项治理／状态，共97项通过；确认自身验证后写入、raw收据、两次条件写后读回及两次独立最终读回、返回实际存储字节、每阶段当前状态重查。故障孤立对象不能推断登记，同键异字节保留原件并拒绝；diff通过、HEAD不变、工作区干净。固定工作流实际执行前提仍未接线，归档不等于权限生效。

## B3g：固定Python验证任务执行器（待独立审核）

固定执行接线拆成可独立审核的小包，本包先完成执行核心，真实通道和受保护工作流随后接入。新增services/publication/authorization_execution.py的execute_authorization_validation(transport)，内部通道仅提供prepare()和return_result(dispatch_id,lease_token,result_bytes)。prepare返回精确`{dispatch_id,lease_token,input_sha256,input_size_bytes,input_bytes}`，input_bytes必须为不可变bytes，令牌精确epoch／fence；复制准备对象，核对摘要／长度／UUID／整数并将令牌绑定输入票据的epoch／fence。该结构是内部通道交接，不新增外部HTTP合同或可触发工作流。

执行器只有transport参数，没有自选输入、验证函数、命令、可执行文件或成功stdout参数。正文由B3c的真实唯一合同路径处理：从authorization_validation.py提取authorization_validation_output(raw)，CLI main和固定执行器共用同一个输出函数，实际执行validate_authorization_input并按原B3c规范输出两份base64产物及单个换行。CLI成功／失败stdout格式不变。执行器把该输出原字节、原dispatch_id及原lease_token直接交return_result，不在调用方重建收据、改写输出或额外计算业务规则。

准备、字节／合同验证或回传异常均向调用方传播，不生成替代失败收据、不自动重发，特别是回传响应丢失不能自行再次提交。返回值只保留通道原始响应bytes，不解读为授权生效；字典形式的“成功声明”被拒绝。服务端是否已收件、归档或登记，仍须后续真实通道的权威响应与状态恢复规则处理。

### B3g实际检查及后续前提

7项新增专项使用实际B3d输入和Python固定执行函数，核对传给通道的stdout与B3c命令输出一致，再将这些真实执行字节交B3f内部适配器验证／归档；还覆盖字段／摘要／长度／令牌篡改、可变bytes拒绝、重算摘要后仍无效的原件／历史／票据、禁止覆盖执行函数／命令／成功产物、过期计算停止、准备失败／回传不确定仅单次调用以及原始响应不冒充授权结论。85项环境取证／跨语言Node、7项治理和12项状态共104项通过；定点lint、机器状态／文档链接和diff检查通过。既有B3c实际模块stdin/stdout测试继续通过；合同规则和存储／租约实现未变，不重复其无变化整套测试。

这里的transport是受信运行适配器依赖，当前测试使用内存通道并仅注入本地时钟；它不认证任意调用方自制的transport，也没有执行真实GitHub任务或网络往返。下一包仍必须实现受控认证通道、固定来源获取、及时续租及错误恢复，再将唯一执行入口接入冻结checkout和受保护工作流；不能向用户暴露替换transport／输入／执行代码的参数，也不能把本包调用成功视作实际工作流执行前提已关闭。此前OIDC／固定workflow政策只能认证身份的限制仍保留。

最终权限／业务目标/config检查及同事务票据消费／索引追加继续后续，本包不增加授权登记或生产许可。跨日端到端仍未执行，M11不重审。独立提交`feat: execute M12 validation through the fixed Python path [skip ci]`，父提交5b2e8f3b48cea7cb5584cea1b106b6eea1f37ecd，完整SHA见交付消息。仅新增内部固定执行器、提取现有命令共同输出函数、扩展现有环境专项测试及3个治理文档；无业务合同／政策版本变化，可撤回本包接点并保留历史。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B3g独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认87320fc19f87c2d9888c29622e47ac6059bf0af9在内部固定Python执行核心范围无阻断。审核员逐段读取6文件，自行运行85项环境取证／跨语言Node及19项治理／状态，共104项通过；确认输入复制、hash／长度／lease绑定、直接调用CLI共用的唯一输出路径、原字节回传、无执行替换参数及不伪造／重发。diff通过、HEAD不变、工作区干净。该限定结论不认证任意transport，真实通道、冻结checkout／固定工作流、续租与错误恢复仍待验收。

## B3h：受控HTTPS任务通道（待独立审核）

新增内部AuthorizationHttpsTransport，作为B3g固定执行器的真实HTTP客户端实现；构造器只接受运行适配器提供的固定coordinator_origin、Actions运行环境及测试用opener依赖，非外部任务参数。默认采用标准库验证TLS证书、禁用环境代理、拒绝HTTP重定向；仅允许规范HTTPS域名，协调器配置不能含路径／query／fragment／用户信息／端口或控制字符。Actions令牌请求URL取运行环境，限定*.actions.githubusercontent.com且拒绝预置audience，追加固定sage-vista-publication；不把该请求凭据发送到协调器。相关依据已核对[GitHub OIDC参考](https://docs.github.com/en/actions/reference/security/oidc#methods-for-requesting-the-oidc-token)及[托管runner网络要求](https://docs.github.com/en/actions/reference/runners/github-hosted-runners#communication-requirements-for-github-hosted-runners)，不自行生成身份令牌；服务端仍须真实验签和核对Job／政策。

每次准备或回传前分别请求新的OIDC token，只向同一固定origin的两个路径POST：`/v1/authorization/prepare`请求正文精确为空对象；响应精确`{protocol,dispatch_id,lease_token,input_sha256,input_size_bytes,input_base64}`，protocol为内部传输版本m12-authorization-job/1。通道严格解析JSON、标准base64、UUID／epoch／fence及输入原字节hash／长度，返回B3g需要的不可变input_bytes结构并私存会话副本。`/v1/authorization/return`正文精确`{protocol,dispatch_id,lease_token,result_base64}`，仅接受本会话原dispatch／令牌和不可变结果bytes，编码时不改变B3c stdout。该协议是客户端接点约定，两个服务端HTTP路由尚未实现或部署。

HTTP只接受200、未变化的响应URL及单一application/json声明，拒绝压缩响应、重复长度／类型／编码头、错误长度和空正文，读取中执行上限而不是截断后继续。OIDC响应最多128KiB、准备响应最多32MiB、回传响应最多1MiB，阻塞网络操作30秒超时；B3h当时尚无请求总时限。超限失败关闭，不省略授权历史以绕过上限；真实最大输入规模仍须后续验收。令牌响应只检查传输形状，不在客户端增加另一套JWT或业务合同验证；收到的协调器JSON对象原字节仍保持opaque，HTTP 200不是授权登记证明。

会话按new→preparing→prepared→returning→returned推进，网络或解析失败进入failed，重复准备及已发送／不确定回传不得在同实例再次发送。发送前错误dispatch／令牌／可变bytes直接拒绝且不发网络请求。网络错误只抛固定脱敏信息，不含URL、令牌或私有响应正文；HTTPError响应句柄会关闭。默认配置未创建任何真实资源或工作流，不读取本机真实Actions凭据、不调用外部协调器。

### B3h实际检查及未完成边界

11项Python专项覆盖固定origin／audience／凭据分离、新令牌逐次获取、完整输入与原输出、配置与会话隔离、协议／摘要／base64／令牌守门、重定向／响应URL／状态／MIME／编码／长度／资源上限、重复JSON键／非有限数、会话替换、不确定网络错误脱敏及无自动重发。另使用真实urllib重定向处理链和替代网络层验证302不会向新地址转发凭据；未进行真实TLS握手。1项新增跨语言组合将实际B3d输入交本HTTP客户端和B3g唯一执行器，检查四次请求封装，再把真正生成的回传字节交B3f接收／归档；网络层及响应均为受控替身，不声称服务端路由往返已经实现。

86项环境取证／跨语言Node、11项HTTPS通道Python、7项治理及12项状态共116项通过；通道专项同时将ResourceWarning视为错误，定点lint、机器状态／文档链接／diff检查通过。合同、租约及权威存储实现未改，未重复其无变化完整测试。

本包仅完成受控客户端，不补足真实受保护工作流执行前提。后续须完成服务端认证路由、60秒续租／失效停止、权威状态查询与不确定回传恢复，并将固定执行入口及此通道接入冻结checkout和经过批准的环境／工作流；运行配置不能来自可任意修改的dispatch输入。最终当时权限、业务目标/config和同事务票据消费／索引追加仍待后续，任何opaque响应均不得当作已登记授权。跨日端到端未执行，M11不重审。

独立提交`feat: add controlled M12 authorization HTTPS transport [skip ci]`，父提交87320fc19f87c2d9888c29622e47ac6059bf0af9，完整SHA见交付消息。仅新增内部通道及其Python专项、扩展现有跨语言测试和3个治理文档；无业务合同／政策版本变化，可撤回本包接点并保留历史。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B3h独立复核回传及P3文案更正

审核对话01a074f9-098a-7b82-b486-3185683290fe确认524ffb0f08743b793289c4dcd284dfd6b5ed28e5在未启用客户端范围通过，附一项非阻断P3。审核员运行86项环境／跨语言Node、11项通道Python及19项治理／状态，共116项通过（ResourceWarning按错误处理），并独立核对GitHub接口；diff通过、HEAD不变、工作区干净。已将B3h“单请求30秒超时”更正为“阻塞网络操作30秒超时；B3h当时尚无请求总时限”。[Python urllib文档](https://docs.python.org/3/library/urllib.request.html#urllib.request.OpenerDirector.open)明确该timeout限制阻塞操作，持续慢响应可超过30秒；不以它证明60秒续租或及时失效停止。该文案已改，新取消实现以下单独交审，不把客户端审核扩大到运行或登记。

## B3i：默认HTTP请求隔离与总等待超时取消（待独立审核）

默认AuthorizationHttpsTransport不再在任务主进程执行阻塞HTTP，每个请求启动固定`sys.executable -I <当前authorization_transport.py绝对路径>`子进程，原请求url／token／data_base64／limit仅经匿名stdin管道传递。无shell、无自选程序／路径参数、不继承环境变量、关闭其它文件描述符，stderr丢弃。原URL／身份和会话政策仍由父通道控制；子进程再次检查封闭输入及允许的响应上限，使用原阻塞请求函数、默认TLS证书验证、无环境代理及拒绝重定向策略，只有完整读回并通过原有长度／响应检查后才将原字节写到stdout。

父进程使用subprocess.run的30秒总等待预算，超时由标准库终止并回收该请求子进程，不返回部分stdout；非零退出、空或超过上限的输出也拒绝，仅抛固定脱敏错误。[Python subprocess文档](https://docs.python.org/3/library/subprocess.html#subprocess.run)说明超时会杀死并等待子进程，同时进程创建可能无法中断。因此准确边界是“子进程启动后的总等待预算”，进程创建和终止回收开销不计入这30秒；序列化准备开销也不在其中。每个OIDC GET及协调器POST分别受预算约束，并不是整个prepare／return阶段或整个job的30秒总时限。

保留opener注入仅用于内部受控测试；该分支直接调用原阻塞请求函数，没有子进程总等待保证，真实运行工厂不得从任务参数接受opener替换。取消只停止本地请求进程，不能撤销远端已收到或完成的操作；父通道沿B3h将不确定请求记为failed，不在同实例再次发送。它仍不能作为60秒续租、收到失效信号后立即停止、或远端事务回滚的保证，相关运行接线和状态查询恢复继续下一包。

### B3i实际检查与剩余边界

新增6项通道专项，覆盖默认路径固定argv／隔离标志／空环境／私有stdin及原始输出、不合规输入由实际隔离脚本静默拒绝、实际子进程成功读回保持字节、持续每20毫秒有数据的慢响应超过总等待后被终止并回收（验证其PID已不存在）、非零／空／超量输出及进程失败拒绝、不确定回传总等待超时后无重发。慢响应测试用真实子进程和生产请求读取循环，只有网络opener由独立测试harness替代；测试将预算缩短到1秒，确认此前已有多次读进展，避免只覆盖完全不响应情况。生产代码没有测试开关或可替换子进程命令参数。

86项环境取证／跨语言Node、17项通道Python、7项治理及12项状态共122项通过；通道测试将ResourceWarning视为错误，机器状态／文档链接／diff检查通过。既有注入opener的完整执行／回传组合仍通过；未进行真实TLS／外部网络请求。该包未修改业务合同、服务端存储或租约实现，未重复其无变化完整测试。

服务端路由、60秒续租及失效停止／状态恢复、冻结checkout与受保护工作流、最终当时权限／目标config和同事务消费追加均未完成；不因增加取消边界而提前启用。跨日端到端未执行，M11不重审。独立提交`feat: bound M12 HTTP waits with isolated request workers [skip ci]`，父提交524ffb0f08743b793289c4dcd284dfd6b5ed28e5，完整SHA见交付消息。仅修改通道实现及其专项和3个治理文档；无业务合同／政策版本变化，可撤回本包接点并保留历史。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B3i独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认9a8b6e660f9791b5b9213f907bd065396a7de696在默认HTTP子进程隔离及总等待取消范围通过；B3h P3文案更正确认关闭。审核员自行运行86项环境／跨语言Node、17项通道Python及19项治理／状态，共122项通过，ResourceWarning按错误处理；确认固定隔离命令、空环境及私有stdin、慢响应进程终止回收、部分输出拒绝和准确时间边界。该结论不证明远端取消、续租、真实TLS或工作流执行。

## B3j：默认关闭的认证任务路由（待独立审核）

新增内部AuthorizationJobApi.fetch，默认enabled=false直接返回503且不访问存储或网络。启用仅为受信运行适配器配置，必须指定既有leaseEpoch；本包没有Worker部署入口、云绑定、环境创建或工作流配置。只接受两个固定POST路径，无查询参数；先按现有政策真实验证OIDC，再读取正文。prepare正文只能是精确空对象，return只能带内部协议、dispatch_id、lease_token和result_base64；严格规范JSON／UTF-8／标准base64、UUID及整数fence，不接受外部epoch初始化、Job、输入原件或成功声明。

AuthorizationPreparation新增prepareJob(token,epoch)，复用自身环境批准及固定来源取证、归档和独立读回，在证据可用且身份未过期后才获取既有epoch下的publish/global租约。随后复用原历史快照、冻结输入及持久发送绑定；原prepare／dispatchValidationInput内部接口保持兼容。prepare响应精确为B3h协议六字段，返回前再次检查当前持锁发送记录。缺失epoch不会初始化，其他owner不会被抢占；取得租约后若部分失败，不自动释放或重新执行，保留现有TTL及孤立对象规则，权威状态恢复留待后续。

return复用B3f自身验签、当前发送／票据／原件核对、不可变归档及最终读回，编码响应后再次核对当前发送记录。成功只返回state=archived_pending_registration、dispatch_id及两份实际归档描述符；不消费票据、不追加授权、不宣称权限生效。相同有效回传的服务端重放可读回相同归档确认，这不授权客户端对不确定回传盲目重发。失效及内部失败统一返回409 job_not_ready，不泄露取证正文或错误原因；非法请求400、身份401、未知路径404、方法405，所有响应no-store。

prepare请求最多2字节，return最多4MiB，按实际流长度核对并拒绝错误Content-Length／压缩内容；正文读取采用5秒总等待计时，超时取消读取。此计时仅覆盖正文读取，不限制此前验签、后续归档、整个处理器或事件循环阻塞，也不保证撤销远端操作。prepare在分配base64响应前按展开长度加固定余量检查32MiB上限，不截断历史以满足上限；真实最大输入规模仍待验收。

### B3j实际检查与剩余边界

新增7项专项覆盖默认关闭零依赖访问、批准原件读回后才取锁、未初始化epoch及其他owner拒绝、路径／方法／身份／私有字段／重复键等拒绝、真实产物归档与一致重放不追加权威、正文大小及实际5秒取消。另启动真实Python客户端与固定执行器，通过本地双向消息桥实际调用两个Fetch路由并返回其真实响应，完成准备—唯一合同验证—回传—归档往返。SQLite及Python执行真实，GitHub／R2／HTTP网络层为替身；未执行真实TLS或GitHub任务，也未使用默认隔离HTTP网络分支。这不补足受保护工作流实际执行前提。

93项环境取证／跨语言Node、29项租约Node、7项治理及12项状态共141项通过；定点lint、机器状态／文档链接／diff检查通过。未改业务合同或Python通道，不重复其无变化完整测试。60秒续租及失效停止／状态恢复、冻结checkout与受保护工作流、最终当时权限／业务目标config和同事务票据消费／索引追加仍待后续；跨日端到端仍未执行，M11不重审。

独立提交feat: add disabled M12 authorization job routes [skip ci]，父提交9a8b6e660f9791b5b9213f907bd065396a7de696，完整SHA见交付消息。仅新增内部路由、调整准备接点、扩展既有环境专项及3个治理文档，无业务合同／政策版本变化；可撤回本包接点并保留历史。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B3j独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认67636da5ac3611cad54ea953dea7d8d4086da29e在默认关闭内部AuthorizationJobApi及prepareJob接点范围无阻断。审核员逐段审读6文件及租约acquire语义，自行运行93项环境／跨语言Node、29项租约Node及19项治理／状态，共141项通过；diff通过、HEAD不变、工作区干净。确认取证后取既有epoch租约、封闭请求、真实5秒正文取消、编码后当前发送重查和本地消息桥往返，回传只有已归档待登记。该结论不覆盖默认隔离HTTP分支与真实TLS／平台往返、续租恢复、固定工作流及最终登记。

## B3k：服务端当前状态及续租接点（待独立审核）

同一默认关闭AuthorizationJobApi新增POST /v1/authorization/status及/renew。两者请求精确`{protocol,dispatch_id,lease_token}`，沿用m12-authorization-job/1、规范JSON及UUID／epoch／整数fence，正文最多1024字节并沿用5秒正文读取期限；不能指定TTL、资源、输入或结果。仍先验签再读正文。由AuthorizationValidationReturn提取verifyDispatch，共用现有真实OIDC、当前持久发送／票据／历史、R2原输入摘要／长度及原actor／Job／来源绑定，末次异步读取后重查；原结果verify继续调用此共同接点，业务验证规则未复制或更改。

取得受信快照后，在一个外层storage.transactionSync内重查当前快照；status只读当前租约，renew复用既有LeaseStore.renew固定300秒TTL。形成响应后再次执行readValidationDispatch，以当前身份、原dispatch截止、票据／租约、head／revision与完整历史守门。任一同步步骤失败使租约更新与renew日志一起回滚；无网络或await进入事务，不改lease实现或表结构。外层只管理原子性，不将旧读取时钟写回epoch。

成功响应精确`{protocol,dispatch_id,state,lease_token,lease_expires_at,validation_expires_at}`，state固定dispatch_current，validation_expires_at始终为原冻结dispatch的截止（原票据与原取证身份期限的较早者）。这只说明本次事务内原发送仍可继续；后续请求必须重新验证。续租不改票据／输入／dispatch原字节或fence，新JWT也不能延长原验证窗口。status不续租、不写归档／授权／续租日志，既有检查仍维护lease的last_now。所有失效或原件不可读返回既有409 job_not_ready，不泄露是否存在其他Job的记录。

该status刻意不判断回传结果是否已归档、是否执行或是否已登记：即使一次return已确认archived_pending_registration，status仍只给dispatch_current且无产物引用。它不构成不确定回传的完成查询或自动重试许可；丢失响应、已过期dispatch及部分准备恢复仍待独立恢复接点，不重建输入、不重发验证或结果。客户端60秒心跳及及时停止仍未接线，本包没有宣称任务可无限续跑。

### B3k实际检查与剩余边界

新增7项环境专项覆盖status跨适配器重开一致且不续租／不报成功、60秒后续租但原dispatch字节与截止不变、原身份提前到期不能被新JWT救活、actor／Job／来源／epoch／fence／dispatch及额外控制字段拒绝、缺失R2原件及读回期间head／owner变化拒绝、renew日志插入后SQL故障或跨过原截止导致全部续租回滚、return后status不推断产物登记。真实SQLite测试夹具使用保存点模拟嵌套transactionSync，保持同步回调及外层失败回滚。

另外新增1项本地Miniflare／workerd内存SQLite DO测试，实际确认内层成功事务在外层抛错后回滚，外层成功时保留全部写入；未部署到Cloudflare。本机已安装运行时最高兼容日期2026-05-22，专项使用此日期；最初以2026-09-01启动被运行时拒绝后改为支持日期，没有改依赖或生产配置。普通沙箱禁止回环监听，该本地测试经执行权限放行后通过。平台同步回调／抛错回滚约定见[Cloudflare SQLite存储文档](https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/#transactionsync)；嵌套行为的本轮证据来自已安装本地运行时，不当作云平台往返验收。

100项环境／跨语言Node、29项租约Node、1项本地workerd事务、7项治理及12项状态共149项通过；定点lint、机器状态／文档链接／diff检查通过。没有修改Python／业务合同／底层租约，不重复无变化完整测试。冻结checkout／受保护工作流、客户端续租停止、权威回传恢复、最终权限／目标config与同事务登记仍后续，跨日端到端仍未执行，M11不重审。

独立提交feat: add authenticated M12 dispatch status and renewal [skip ci]，父提交67636da5ac3611cad54ea953dea7d8d4086da29e，完整SHA见交付消息。仅调整内部API与共用回传绑定、专项测试及3个治理文档，无业务合同／政策版本变化，可撤回接点并保留历史。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B3k独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认047f136d0f96fa5cd8618bf4807a5bcd54934f88在默认关闭API的status／renew及共用verifyDispatch范围无阻断。审核员逐段读取7文件，运行100项环境／跨语言Node、29项租约Node、19项治理／状态及1项本地workerd事务，共149项通过。workerd首次被沙箱禁止回环监听，单独以本地执行权限重跑通过；使用提交内2026-05-22配置，没有云部署。确认输入原件与身份绑定、同步事务中的续租及最后重查、故障／过期整笔回滚和原截止不变；diff通过、HEAD不变、工作区干净。status只说明dispatch_current，不推断归档／登记或允许盲重发。

## B3l：客户端状态查询及续租通道（待独立审核）

AuthorizationHttpsTransport新增无参数status()和renew()，只操作自身prepare保存的会话，不能传入另一dispatch、lease、TTL、资源或路径。只有prepared状态可调用，调用期间分别进入checking／renewing；成功返回prepared，任何解码、时间、网络或响应错误进入failed并抛固定脱敏validation control failed。failed后不允许再次查询、续租或回传；未准备及已回传会话不能调用。本包仍是单调用顺序通道，没有并发线程安全或调度循环承诺。

每次请求单独取得新OIDC，向固定origin的/status或/renew发送精确`{protocol,dispatch_id,lease_token}`。沿用默认隔离HTTP子进程、TLS／重定向／URL／响应检查及每请求启动后30秒等待预算，控制响应最多128KiB；没有新增可配置地址、超时或子进程参数。受信opener注入仍仅供测试，无隔离取消保证。新通道不是60秒定时续租本身，也不证明失效信号能及时终止正在运行的计算。

复用唯一publication_validation_input解码器读取私存原输入，核对其中epoch／fence，提取原票据expires_at及原取证identity.expires_at，计算较早的冻结截止用于传输响应一致性比较。该步骤只读时间／会话元数据，不认定批准、策略、历史或业务合同有效，实际执行仍走B3c唯一验证路径。服务端与客户端继续各自承担身份／事务守门及传输一致性，摘要和自洽时间都不是执行或登记证明。

成功响应必须精确含protocol、dispatch_id、state、lease_token、lease_expires_at、validation_expires_at；protocol和原dispatch／lease一致，state只能dispatch_current。时间必须是规范UTC毫秒字符串，validation_expires_at严格等于原冻结截止；lease_expires_at不能短于原票据期限或此前观察到的租约期限。客户端在网络前及完整响应后检查本地墙钟，负时间、到期、单次请求或两次请求间时钟倒退均拒绝；不以新JWT／新租约改变原验证窗口。这里的时钟检查失败关闭，没有放宽漂移容忍或授予额外有效期。

返回解析对象使用副本，调用者改写响应不会修改私存会话或已观察截止。查询／续租成功仍仅表示这次状态读取成功，不检查或报告结果已归档／授权已登记，不自动重放不确定回传；后续操作仍须服务端重新校验。权威恢复查询及原件完成证据仍待后续。

### B3l实际检查与剩余边界

新增8项Python专项覆盖固定路径、逐次新令牌、原句柄与返回副本、精确状态／时间／字段拒绝、网络前后到期与时钟倒退、连续响应租约期限倒退、原身份早于票据期限、输入解码或lease不符提前拒绝、网络／HTTP／重复键失败脱敏且停止会话，以及默认路径继续使用固定隔离子进程和既有128KiB限制。专项时间／原件为合成传输样本，明确不是业务有效性证据。

扩展已有本地跨语言往返，实际Python客户端和固定执行器经双向消息桥依次调用服务端prepare→status→renew→return，四个Fetch路由返回真实处理结果，最终仍只已归档待登记。测试适配器子类只在prepare后顺序调用两项新方法；没有生产定时循环或执行器逻辑变化。GitHub／R2／网络仍为替身，未执行真实TLS或平台工作流。

100项环境／跨语言Node、25项通道Python、7项治理及12项状态共144项通过，ResourceWarning按错误处理；定点lint、机器状态／文档链接／diff检查通过。服务端API、底层租约和合同未修改，不重复无变化整套检查。后续仍须60秒调度／运行失效停止、权威恢复、冻结checkout／受保护工作流及最终权限／目标config／同事务登记；跨日端到端未执行，M11不重审。

独立提交feat: add M12 client dispatch status and renewal [skip ci]，父提交047f136d0f96fa5cd8618bf4807a5bcd54934f88，完整SHA见交付消息。仅调整客户端、相关Python／跨语言专项及3个治理文档，无业务合同／政策版本变化，可撤回通道接点并保留历史。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B3l独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认db1b1f40f8bd83e05a4436e572da5c2908c5e374在顺序客户端status／renew范围无阻断。审核员逐段读取6文件，自行运行100项环境／跨语言Node、25项通道Python及19项治理／状态，共144项通过，ResourceWarning按错误；diff通过、HEAD不变、工作区干净。确认自身会话、新OIDC及固定路径、原冻结截止、异常关闭及四路由本地往返。该结论不覆盖60秒循环、并发／线程安全、及时停止、权威恢复或真实平台／固定工作流。

## B3m：可取消的固定验证进程（待独立审核）

新增AuthorizationValidationProcess(input_bytes)，作为后续监督调度器的内部进程句柄，必须使用上下文管理器管理生命周期。输入只接受非空不可变bytes，最多32MiB，无自选命令、参数、执行函数或输出参数。启动固定`sys.executable -I <authorization_validation_worker.py绝对路径>`，cwd固定为该文件所属仓库根，env为空、close_fds=True、无shell、stderr丢弃。新worker仅从自身绝对位置确定仓库导入根，不使用外部PYTHONPATH、调用者cwd或请求路径；它调用现有authorization_validation_output，共用B3c唯一业务验证及stdout编码，没有第二套业务规则。

输入与stdout分别使用权限0600的TemporaryFile，由上下文结束关闭并清理；输入写完并回到起点后供子进程读取，父进程在启动后关闭自身输入句柄。文件式stdio避免子进程stdout填满管道时阻塞未来的续租监督流程，不经命令行传私有证据、不落到仓库或永久归档。worker最多读取32MiB并在输出前检查成品2MiB上限；此上限给后续4MiB回传base64封装留出余量，不截断任何合同或产物。真正最大输入／产物规模仍待运行验收。

poll()在运行中只返回None；只有退出码0且读得非空、完整且不超过2MiB的stdout后才返回一次不可变原字节，并关闭文件／回收进程。失败、空／超量输出或异常退出仅给固定脱敏错误，不交出部分内容，不产生替代成功收据。运行中poll也检查已写文件大小，但这不是操作系统磁盘配额或独立监控器；固定worker先核验完整输出长度再写入，调用方仍须按监督节奏轮询。

cancel()终止仍运行的直接子进程并wait回收，取消与退出竞争时也回收；重复清理安全，取消后不能poll出成功结果。上下文中的调用方异常同样触发取消清理，保留原调用方异常。上下文清理针对正常退出和可处理异常，不保证父进程被操作系统强制终止后的自动回收。进程启动、文件准备及终止回收本身不承诺硬实时；本包无自动超时、定时线程或60秒心跳，句柄只有在调用方轮询／取消时采取动作。现有execute_authorization_validation未改接此进程，后续监督执行器必须实际接入并在续租／身份失败后取消，不能把此处“可取消”写成已有完整失效停止。

### B3m实际检查与剩余边界

新增8项Python专项覆盖固定argv／-I／空环境／cwd／私有文件权限与原输入、无替换参数、真实长运行子进程已有部分stdout后取消及PID不存在、上下文异常取消、非零／空／超量stdout拒绝、完整字节仅交一次、启动错误脱敏及文件关闭、不可变／大小输入守门，以及直接运行实际隔离worker对非法输入返回空stdout／stderr。生命周期测试中的慢进程及输出替代只在测试Popen钩子中使用；生产没有可替换子进程入口。

新增1项跨语言验证，使用真实B3d输入和此进程句柄，启动实际固定worker脚本及唯一验证函数，输出与B3c逐字节一致，再被现有B3f回传归档接受且授权索引不变。为了适配既有冻结合成时间，测试Popen钩子只将固定脚本置于测试时钟harness中执行；生产worker无时钟／验证函数注入。它不代表真实GitHub任务或固定checkout执行证据。

101项环境／跨语言Node、8项进程Python、7项治理及12项状态共128项通过，ResourceWarning按错误；定点lint、机器状态／文档链接／diff检查通过。原传输／租约／合同实现未变，不重复其无变化整套检查。后续仍须监督调度及60秒心跳、运行失效停止的完整接线与验收、权威恢复、冻结checkout／受保护工作流及最终权限／目标config／同事务登记；跨日端到端未执行，M11不重审。

独立提交feat: add cancellable fixed M12 validation process [skip ci]，父提交db1b1f40f8bd83e05a4436e572da5c2908c5e374，完整SHA见交付消息。仅新增进程句柄／固定bootstrap及专项、扩展现有跨语言专项和3个治理文档，无业务合同／政策版本变化，可撤回接点并保留历史。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B3m独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认c6e8680981e6f7901b6901c8d08ea0f03e245f47在可取消固定验证进程及worker范围无阻断。审核员逐段读取7文件，自行运行101项环境／跨语言Node、8项进程Python及19项治理／状态，共128项通过，ResourceWarning按错误；diff通过、HEAD不变、工作区干净。确认固定隔离命令、私有stdio、唯一完整成品、实际慢进程部分输出后取消回收及归档一致。限定结论不含自主心跳、运行失效停止接线、硬实时／OS配额或父进程强杀清理。

## B3n：监督执行、周期续租与失效停止（待独立审核）

新增内部execute_supervised_authorization_validation(transport)，仅接受受信运行适配器提供的通道，不新增外部参数、可选命令／worker／时钟或工作流。将B3g原准备对象复制与字节／摘要／lease绑定检查提取为validation_job_preparation，由旧同步入口和新监督入口共用；实际业务计算仍唯一固定worker。旧入口保留内部兼容，新监督入口失败不回落旧入口。将来受保护工作流必须绑定此监督入口，本包尚未接入实际任务。

所有prepare、status、renew及return_result由max_workers=1的单一I/O线程顺序执行，线程只访问通道，不触碰验证进程。主监督线程独占B3m进程句柄，默认每0.1秒轮询预算和计算状态，避免阻塞HTTP让主监督器无法停止计算；没有对B3l会话做并发调用或宣称它线程安全。流程为prepare→共用准备检查→首次status→固定验证进程→末次status→原字节return。任何步骤异常只抛固定脱敏停止错误，清理后退出，不伪造失败收据或自动重发。

验证运行期间从启动前确定的单调时钟基点，每60秒发起一次renew；一次未结束不发第二次，保持原60秒节拍而非完成后重新计时。续租必须在其计划发起时刻之后60秒内被主循环观察到成功，否则取消计算。成功控制响应的冻结截止必须与首次status一致，不延长验证窗口。若计算先完成但续租仍在途，保留字节但必须等续租成功；续租失败或超时则丢弃，不能提前回传。计算已完成后的最后状态检查失败同样丢弃输出。

监督总预算固定600秒；首次status取得B3l已核对的原验证截止，使用共享时间解析器，同时冻结墙钟截止和按当时剩余时长计算的单调时钟截止，后续以较早者停止。每次轮询拒绝墙钟／单调时钟倒退，原身份及票据期限不因续租改变。prepare、首次／末次status及return的每次控制等待也设60秒观察预算，始终受总预算和已知原截止约束。主循环失效时先退出验证上下文、终止回收计算子进程，之后才等待I/O线程收束；不会因为仍有网络请求而让计算继续运行。

准确边界：0.1秒是正常调度下的轮询间隔，不是硬实时上界；输入复制／解码、进程启动、操作系统调度和终止回收仍有开销。取消计算不能撤回已经发送的网络请求，也不强制终止正在运行的I/O线程；线程池关闭会等待其返回，默认通道每个隔离HTTP请求的既有等待预算仍适用，故监督函数返回耗时可能超过触发停止的预算。停止后监督器不再发起新的通道调用；已在执行的通道方法仍可能继续其OIDC／POST步骤，因此不声称已取消HTTP或远端操作。失败的监督调用不提供恢复入口，所属运行适配器必须丢弃该通道实例，不能在外部复用它重试；实际返回／登记仍由服务端当前状态守门。父进程被强杀的清理不在本包保证内，未进行真实平台时序或云端失效验收。

### B3n实际检查与剩余边界

新增11项Python专项使用真实计算子进程及受信假通道，验证周期续租、所有I/O始终同一线程且与监督线程不同、原字节及末次状态检查、续租异常取消、阻塞续租未返回前计算已被终止、原冻结截止在I/O途中停止、已完成字节在续租随后失败时丢弃、末次status失败、回传不确定仅一次、坏准备不启动进程、拒绝延长截止、单调总预算及墙钟倒退。生命周期专项只在测试Popen钩子替换计算脚本，缩短间隔／预算用于确定性验证，生产无此参数。

另新增1项跨语言完整本地接线：真实B3l客户端通过双向消息桥与实际prepare／status／renew／return Fetch路由通信；监督器运行实际固定worker及唯一验证函数，计算期间产生续租，末次status后回传原产物，最后仍仅archived_pending_registration且授权索引不变。只在测试时钟harness给固定worker增加短等待、冻结合成时间，并缩短监督间隔；GitHub／R2／网络为替身，没有真实TLS或GitHub执行。

102项环境／跨语言Node、11项监督Python、7项治理及12项状态共132项通过，ResourceWarning按错误；定点lint、机器状态／文档链接／diff检查通过。既有B3g直接执行与B3m产物检查仍通过，传输／底层租约／合同实现未改，不重复无变化整套检查。权威恢复、冻结checkout／受保护工作流及最终权限／目标config／同事务登记仍待后续，平台60秒续租／失效停止仍需上线前实测，跨日端到端未执行，M11不重审。

独立提交feat: supervise M12 validation with serial lease heartbeats [skip ci]，父提交c6e8680981e6f7901b6901c8d08ea0f03e245f47，完整SHA见交付消息。仅新增监督器、提取共用准备检查、相关专项和3个治理文档，无业务合同／政策版本变化，可撤回接点并保留历史。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B3n独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认113282090dccffbc96d6be72a8ae0bb69938cb17在内部监督执行、周期续租及计算取消范围无阻断。审核员逐段读取7文件，自行运行102项环境／跨语言Node、11项监督Python及19项治理／状态，共132项通过，ResourceWarning按错误；diff通过、HEAD不变、工作区干净。确认串行通道及主线程进程所有权、原期限／预算、取消先于I/O收束、在途失败续租不能放行完成字节，以及末次status后的单次原字节回传。本地往返不证明平台时序／固定工作流；HTTP继续运行和失败通道丢弃边界保留。

## B3o：回传归档的持久记录（待独立审核）

在AuthorizationStore增加m12_authorization_returns表，以`(dispatch_id,receipt_key)`为主键，保存ticket_id及完整record_json；archive_validation日志与记录同行为事务提交。新表只保存内部回传阶段的完成事实，不是PublicationReceipt业务合同、授权索引或票据消费。构造器仅增加空表，不激活epoch；若已有回传记录但head及其他历史丢失，不自动初始化空head，保留恢复阻断。

AuthorizationValidationArchive.archive仍先自行验证返回身份／原输入／产物，再写并独立读回两份原件。最后读回与当前快照检查之后，调用内部recordValidationArchive，封闭描述符并绑定既有dispatch、ticket、epoch／fence、owner_job、原actor、source_commit、输入原件、授权Ref／实际位置及验证收据原件位置；state固定archived_pending_registration，protocol为内部m12-authorization-return/1，recorded_at取当前服务端时间。对象先读回、数据库后记账；网络／R2失败不会生成此记录，可能存在的孤立原件保留。

同一外层同步事务先验证当前签名身份所对应的发送快照、原期限、租约及完整历史，核对该ticket全部回传行和archive_validation日志一一对应，校验本次描述符与Ref位置／摘要形状，然后写记录和日志，末次再验证当前快照。recorded_at不早于已观察lease时钟／发送时间，不能到达原截止或当前身份期限。行、日志或末次检查异常整笔回滚，不把原件写入成功等同于数据库已记账。SQL层仍只接收内部B3f实际读回结果，不独立证明自选描述符已被取证，未暴露为RPC。

同一dispatch与验证收据原件重放时，必须与既有绑定逐项一致，复用原recorded_at和原日志，不覆盖或重复追加。后来重新计算产生合法的新验证收据，虽可复用同一授权原字节，仍按新的receipt_key保留第二条独立记录；不把“一个dispatch只能有一份收据”作为新限制。任一现有行／日志部分丢失、重复或本次绑定冲突都失败关闭，不能凭新回传覆盖冲突证据。后续恢复查询应按具体原发送／收据定位，不能随意选择某个“最新成功”。

内部archive返回增加return_record供后续接点使用，现有HTTP return响应字段保持不变，依旧只是已归档待登记；status仍只dispatch_current。持久记录本身不保证R2现在仍可读，也不证明真实固定工作流执行或授权生效；未来恢复查询必须再核对请求身份及归档原件，过期／跨epoch恢复规则尚未实现。无恢复RPC、自动重发、授权追加或票据消费。

### B3o实际检查与剩余边界

新增6项环境专项覆盖四次产物读回期间始终无成功记录、记录／日志精确一致与适配器重开重放保留时间、返回对象修改不影响存储、记录行或日志插入后故障整笔回滚且原件保留、日志写入后head／lease／epoch／原期限变化拒绝、部分行／日志丢失不重建、冲突原记录不覆盖，以及仅剩回传记录时不初始化空head。扩展既有R2失败／末次读回失败样例，确认无回传记录；既有较晚合法复验样例确认两份收据／两条记录并存且授权索引不变。底层专项的封闭接口列表同步加入内部recordValidationArchive，继续确认尚无授权提交方法。

108项环境／跨语言Node、29项租约／存储Node、7项治理及12项状态共156项通过；定点lint、机器状态／文档链接／diff检查通过。使用真实本地SQLite和既有假GitHub／R2／网络，既有完整监督往返继续通过；不重复无变化Python整套。权威恢复读取、冻结checkout／受保护工作流、最终权限／目标config／同事务登记仍后续；平台时序和跨日端到端未执行，M11不重审。

独立提交feat: persist M12 archived return records atomically [skip ci]，父提交113282090dccffbc96d6be72a8ae0bb69938cb17，完整SHA见交付消息。仅调整内部存储／归档接点、相关专项及3个治理文档，无业务合同／政策版本变化；可撤回写接点但保留已归档对象及内部历史表，不清空证据。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B3o独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认a68874b57b685f5a6bc228fc34f502009d19da26在内部回传归档记账范围无阻断。审核员逐段读取7文件；首轮dot运行约一分钟无新输出且未退出，原因未定位，仅终止该轮两个已定位测试PID，改spec完整重跑137项Node全部通过（15.65秒，无失败／取消／跳过），另19项治理／状态通过，共156项，未复现停滞。diff通过、HEAD不变、工作区干净。确认原件最终读回后记账、记录／日志原子性、合法多收据与丢失／冲突保护；该结论不证明R2现在可读、真实执行或权限生效。

## B3p：内部历史回传恢复读回（待独立审核）

AuthorizationValidationReturn新增recover(token,dispatchId,receiptKey)，只在受信构造配置提供recoveryEpoch时可用，默认未配置即拒绝；epoch不能由方法请求选择。先实际重新验签，必须匹配原固定工作流／来源政策、原Job（包含run／attempt）及actor；新任务、新attempt或其他来源不因持有收据键获得读取权。输入只定位指定原发送和raw验证收据键，不接受原件、成功对象或替代位置。本包没有HTTP恢复路由、客户端恢复工厂或部署接线。

AuthorizationStore新增内部readArchivedValidation，复用ticket原记录／日志读取、全部回传行日志配对和回传绑定归一化。一次同步事务确认当前配置epoch及新身份时间有效、当前授权历史完整、原dispatch／ticket／Job／来源／原期限关系，以及指定回传记录和日志时间／字段一致。原任务的lease和票据可以已经到期，或lease已由另一Job持有，因为该方法只读历史回传事实；不获取／续期／恢复lease，不修改原票据或输入。当前head可已合法推进，返回中保留当前完整历史快照用于随后重查，不能把历史record的archived_pending_registration状态解释成此刻权限状态。

恢复适配器从已配对记录取得位置，依次真正读回原输入、授权原件、验证收据，核对每份摘要／长度；复用回传路径的输入绑定及私有产物关系校验，不再执行Python计算，也不新建一套业务规则。共同输入绑定同时核对原取证身份issued_at／expires_at与原dispatch；Job字段按值比较，不能因JSON键顺序差异拒绝合法原身份。收据的验证时间必须属于原冻结窗口、不得晚于记录记账时间；授权Ref／实际位置及收据的ticket／输入／输出关系必须一致。

每次异步原件读回及产物摘要校验后，重新读取持久快照并比较记录、配对日志、原票据、当前epoch、新身份期限及当前完整历史；发生变化则拒绝，不返回此前内存中的成功。成功只提供指定历史记录和本次读到的原字节，不承诺原件未来一直可读，也不证明真实工作流执行或授权生效。业务数据／归档／lease行／授权索引／日志不写入；现有epoch的last_now仅作单调时钟维护。读取失败不会重建原件或记录，也不把“没有记录”解释为“未收到，可以重发”。

只允许当前epoch内、仍能取得原Job新有效OIDC的历史核对；跨epoch／新attempt／跨来源恢复仍失败关闭，不开放通用历史查询。后续还需受控恢复RPC、客户端保留指定原回传的恢复凭证和运行工厂，尤其不能在失败监督调用后复用原通道盲重发。本包并未完成整套崩溃恢复，也不会把旧完成记录用于消费已失效票据。

### B3p实际检查与剩余边界

新增8项环境专项覆盖：原验证窗口到期且lease被另一Job接手后，新原身份仍可只读核对、租约／授权记录／日志／R2写入计数不变；后续完整head可与旧ticket版本不同；未配置／错误epoch、原身份／来源不符、旧令牌过期及未知收据拒绝；记录、ticket或dispatch日志丢失不重建；原输入／授权／收据缺失或损坏均拒绝；末次读回期间记录／epoch／head／身份变化拒绝；两份合法复验收据逐个精确读取；即使重算被改收据的哈希并同步修改内部行／日志，产物关系校验仍拒绝其错误ticket。既有实时回传／续租／归档及监督完整往返回归通过，仍无授权追加。

116项环境／跨语言Node、29项租约／存储Node、7项治理及12项状态共164项通过；本轮145项Node使用spec完整运行（18.25秒），无失败／取消／跳过。定点lint、机器状态／文档链接／diff检查通过。真实本地SQLite与假GitHub／R2／网络边界不变，不重复无变化Python整套。恢复RPC／客户端接线、冻结checkout／受保护工作流及最终权限／目标config／同事务登记仍后续；平台时序和跨日端到端未执行，M11不重审。

独立提交feat: verify archived M12 returns for internal recovery [skip ci]，父提交a68874b57b685f5a6bc228fc34f502009d19da26，完整SHA见交付消息。仅调整内部存储／回传共用验证、相关专项及3个治理文档，无业务合同／政策版本变化；可撤回恢复读接点并保留原件与记录。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B3p独立复核回传

审核对话01a074f9-098a-7b82-b486-3185683290fe确认4ca4129f548a935fc5d5a51c6cee63f112a9a39e在内部历史恢复读回范围无阻断。审核员逐段审查实现差异、新增8项恢复测试及治理记录，145项Node spec完整通过（18.07秒，无失败／取消／跳过），另19项治理／状态通过，总164项；定点eslint和diff通过，HEAD一致、工作区干净。确认默认禁用、配置epoch、原身份和三份原件实际读回、共同产物绑定及末次重查。current_history仅为结构完整快照，不代表本轮重读全部历史原件或当前发布获授权；历史读取不复活权限，last_now只作时钟维护。

## B3q：受控恢复RPC与客户端本地凭证（待独立审核）

默认关闭AuthorizationJobApi增加POST /v1/authorization/recover，沿用新OIDC验签、1024字节请求上限、规范JSON及5秒正文读取期限；正文精确`{protocol,dispatch_id,receipt_key}`，不接受epoch、lease、原件或成功声明。服务器从自身leaseEpoch配置恢复适配器，完整调用已审核B3p读取，再编码精确响应`{protocol,dispatch_id,state,authorization_archive,validation_receipt_archive,input_sha256,recorded_at}`，最后重新读取并比较持久快照。state固定archived_return_verified，仅说明指定历史回传及此次原件读回一致，不是授权生效／票据可继续。缺少记录、原件或身份／状态失效均返回既有409，绝不返回“未收到，可重发”。

新增RecoverableAuthorizationTransport，继承已审核HTTPS通道并要求受信工厂配置recovery_directory。每次真实return前，核对本会话原dispatch／lease及固定输出的传输元数据，读取stdout内原验证收据和授权字节，绑定原输入摘要／长度、实际授权字节摘要／长度及验证收据摘要。先保存并读回精确恢复凭证，然后才交原return_result取新令牌／发HTTP；文件保存失败即failed，不发送回传。元数据检查不替代业务验证，也不把本地凭证当执行证明。

凭证协议为内部m12-authorization-recovery/1，字段精确`{protocol,origin,dispatch_id,input_sha256,authorization_archive,validation_receipt_archive,validated_at}`。不含OIDC／Actions请求凭据、完整输入、stdout或业务正文。AuthorizationRecoveryJournal要求本机当前用户拥有的私有0700目录，文件0600，固定文件名为规范凭证字节的SHA-256＋.json。先写同目录私有临时文件、flush／fsync，再通过不覆盖的原子硬链接安装最终文件、fsync目录，并以摘要／规范JSON／权限／非符号链接读取核对；同字节重放复用，损坏或冲突不覆盖。临时文件仅清理本次创建者，异常关闭保留已安装凭证；这是POSIX本地持久文件，不是跨runner云存储或磁盘故障保证。

客户端只通过新RecoverableAuthorizationTransport实例的recover(recovery_id)恢复。先读本地已保存凭证并匹配固定origin，再取新OIDC，仅发送recover查询；不调用prepare、renew或return。响应字段／state、原dispatch、输入摘要及两份原件描述符必须精确匹配凭证，描述符数值拒绝bool等类型混用，recorded_at为规范时间且不早于原验证时间。成功只返回历史核对响应原字节；异常则failed，已用／失败会话不能恢复或重发。只读recovery_id属性供运行工厂在丢弃失败会话时定位已保存文件，不赋予任何网络或权限能力。

本包收口同一原Job仍能取得新OIDC时的恢复RPC及本地凭证链路；旧租约可以到期或换owner，不会因此复活。跨Job／新attempt／跨epoch继续失败关闭。固定工作流必须使用此凭证客户端与B3n监督器，并安排私有凭证文件在所需生命周期内可取回；本包未创建Actions artifact、云资源或跨runner凭证传输，也未将旧无凭证客户端当作最终生产工厂。临时.pending文件不是恢复凭证，后续归档只能选规范摘要文件名。

按用户要求一并修正MODULE_REFACTOR_PLAN_ZH.md页首过时总览，版本更新为0.12.1-m12-implementing：明确M12已获批且正在分包实施，完整生产链尚未收口，新看板／M13未实施，生产仍走旧流程。该同步不改变业务含义、规则或生产状态。

### B3q实际检查与剩余边界

新增8项Python专项验证凭证确实先持久读回再发return且不含令牌／正文、回传响应不确定后新客户端只查原记录、fsync失败不发网络、同字节保存／损坏／符号链接拒绝且不覆盖、错误状态／额外字段／摘要／类型／时间拒绝、origin与标识不符提前拒绝、坏结果／错误会话不保存，以及恢复409不能转为重发。使用真实本地文件和受控网络替身，ResourceWarning按错误。

新增3项Node专项覆盖默认关闭／封闭恢复请求／历史响应，以及真实Python凭证客户端＋监督器＋固定worker＋实际Fetch路由往返。组合样例在服务器已成功记账后人为让客户端收到503，令旧窗口到期并由另一Job接手lease，再用新原身份和新客户端从同一私有目录读取凭证，成功recover；全程只1次prepare、1次return，授权索引和接手owner不变。固定worker仅用测试时钟harness适配合成时间，GitHub／R2／网络仍为替身；不是实际网络断连、TLS或GitHub平台恢复验收。

119项环境／跨语言Node、8项恢复Python、7项治理及12项状态共146项通过；定点lint、机器状态／文档链接／diff检查通过。未修改存储、业务合同或原基础通道，不重复其无变化整套测试。接下来收口固定checkout／受保护工作流／凭证运行工厂及最终权限／目标config／同事务登记，再进入获批C／D每日业务与跨日链；平台时序和跨日端到端未执行，M11不重审。

独立提交feat: add controlled M12 recovery RPC and local journal [skip ci]，父提交4ca4129f548a935fc5d5a51c6cee63f112a9a39e，完整SHA见交付消息。仅增加恢复RPC、凭证客户端／本地日志及相关专项、同步3个治理文档；业务合同／政策版本不变，可撤回接点但保留凭证及原件／记录。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B3q定点审核P2与最小修复（待独立复核）

审核对象27e25314b7c626ee08e71040399e78a085706125尚未通过：审核员指出，新建凭证目录后仅fsync凭证文件及目录自身，缺少其父目录项同步，因此“回传前已完成本地持久保存”的承诺尚未满足。独立包装真实fsync并核对fstat设备／inode，观察到return成功、同步2次且新目录父目录未同步；未进行断电实验。其余119项Node spec（18.98秒）、8项恢复Python及19项治理／状态通过，不能替代此缺口验证；本记录不自行将B3q标为审核通过。

本修复仅把save中的目录同步扩为固定顺序“凭证目录→父目录”，置于文件flush／fsync、不可覆盖安装之后、最终读回及发送之前；每次save都执行，不根据目录或最终文件已存在跳过。目录父级必须预先存在（既有mkdir不递归创建父级），本包不扩展目录创建范围。父目录打开或fsync失败沿既有失败关闭路径返回，客户端不取得恢复ID、不发return令牌／HTTP；已安装的完整凭证保留，下一次显式保存仍重新执行全部同步步骤。同一失败客户端仍不可重用，没有自动重试。

新增2项Python验证：包装真实os.fsync，通过设备／inode确认新建目录的父目录在return请求前完成同步，实际顺序为文件、凭证目录、父目录；连续注入两次父目录fsync失败，第二次目录与最终凭证已存在，仍命中同步失败且仅发生prepare阶段请求，凭证原字节不变、无.pending残留，故障清除后的显式新尝试成功。10项恢复Python整体通过（含新增2项，ResourceWarning按错误）；另定点运行1项实际监督客户端／固定worker／本地路由的已记账响应不确定→新客户端恢复样例通过，19项治理／状态通过，共30项检查。状态／文档链接／差异检查通过，未重复无变化的119项Node完整测试。

该证据补足同步调用链及失败关闭，未进行主机断电实验，不改变跨runner存储、磁盘故障、跨Job／epoch和生产未启用边界。仅修改客户端save、相关测试及3个治理文件；独立提交fix: persist M12 recovery journal directory entry [skip ci]，父提交27e25314b7c626ee08e71040399e78a085706125，完整SHA见交付消息。交回本问题的定点复核后，再继续已批准的冻结工作流／运行工厂和最终登记。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B3q／P2独立复核结论

审核任务确认27e25314b7c626ee08e71040399e78a085706125及ae474fedff28bbe06e568488f7699db21a9567fd在受控恢复RPC／本地凭证范围通过，父目录同步P2关闭。独立重跑10项恢复Python＋19项治理／状态及1项实际监督客户端／固定worker／本地路由恢复往返，共30项通过（ResourceWarning按错误）；原始新目录probe实际同步3次，最后设备／inode为父目录。每次save均同步父目录，已存在目录或文件不跳过，失败阻止回传。原146项证据保留，不重复无变化119项Node。未做断电实验，不承诺跨runner持久性或授权生效。

## B3r：禁用的固定工作流与凭证运行工厂（待独立审核）

本包收口固定执行接线：新增`.github/workflows/m12-publication-authorize.yml`，仅workflow_dispatch且无inputs；唯一job固定`if: ${{ false }}`，引用production环境，权限仅contents:read与id-token:write。无schedule／push／可调用工作流／自选命令或产物输入；checkout只取触发的github.sha、不保存Git凭据、不取submodule／LFS。checkout固定de0fac2e4500dabe0009e67214ff5f5447ce83dd（v6.0.2），setup-python固定e797f83bcb11b83ae66e0230d6156d7c80228e7c（v6.0.0），Python固定3.12.12、ubuntu-24.04 x64，job上限15分钟。两个Action SHA已通过GitHub官方只读tag API确认指向commit，Python版本已在官方版本清单确认；不声称是最新版本或已经运行过此GitHub job。

来源：[checkout固定标签](https://api.github.com/repos/actions/checkout/git/ref/tags/v6.0.2)、[setup-python固定标签](https://api.github.com/repos/actions/setup-python/git/ref/tags/v6.0.0)、[官方Python版本清单](https://github.com/actions/python-versions/blob/main/versions-manifest.json)、[Actions变量](https://docs.github.com/en/actions/reference/workflows-and-actions/variables)。GitHub托管镜像本身仍由平台维护，本包未验证真实runner环境、环境保护规则或网络TLS。

固定命令`python -I -B "$GITHUB_WORKSPACE/services/publication/authorization_runtime.py"`没有CLI参数，根目录从自身文件派生。内部配置协议m12-authorization-runtime/1只有protocol／enabled／coordinator_origin三个字段，固定文件`config/publication-authorization-runtime.json`当前enabled=false、origin=null，是第二道禁用门。不存在真实协调器URL或授权请求文件，本包未造grant。启用后只读已提交配置，不接受dispatch、环境变量或参数覆盖来源／命令／验证输入／客户端。工作流及源码配置启用、固定服务端workflow_ref／commit／source身份政策和真实受保护环境都必须在后续上线卡明确批准后配置；仅修改其中一处不能表示生产获批。

运行工厂先要求隔离Python3.12.12，核对Actions、workflow_dispatch、main受保护分支、第1attempt、github-hosted Linux、规范仓库／run／actor标识、固定workflow_ref、workflow SHA与触发SHA一致、workspace与自身根一致、Git HEAD一致。再用Git树对象逐文件重算services代码、工作流及固定配置的实际Git blob SHA，拒绝符号链接、额外导入文件（含被忽略文件）、篡改及未提交替换；不依赖diff缓存或assume-unchanged。只有复核后才导入凭证客户端及监督器。此为受信平台内的本地前置核对，不是调用者不可伪造的身份证明；服务器仍必须独立验证OIDC／批准证据及最终授权条件。控制来源提交与授权请求中的业务code_commit保持分离。

工厂只创建RecoverableAuthorizationTransport并调用execute_supervised_authorization_validation，无opener、validator或命令注入参数。恢复目录固定为RUNNER_TEMP下m12-authorization-<原run_id>-1，父目录须为已存在绝对真实路径且不在源码内，子目录／文件权限和持久保存继续由已审核journal负责。固定worker只补sys.dont_write_bytecode=True，避免正常导入写入源码目录后阻挡恢复前复核，不改变合同计算。回传异常且已有恢复ID时，等待监督器完成取消／清理后重核源码与原上下文，创建一个新客户端，只查原历史一次；无ID、恢复失败或原件缺失均失败关闭，不重prepare／return，不把失败改成成功。

输出仅固定粗粒度状态：禁用、回传已收到待登记、历史回传已核对待登记或统一失败；不输出私有输入、令牌、原stdout或异常细节。普通回传状态只说明受控调用返回，不赋予授权；恢复成功也仅证明指定历史记录，不能复活旧lease／票据。凭证保留在同一原Job的runner本地目录，RUNNER_TEMP在job前后由平台清理，故不保证job结束、runner丢失或换attempt后的文件可用；没有增加artifact上传或跨runner恢复。两类完成状态都仍须后续最终权限／目标config核验及同事务登记，本包不消费票据或追加授权链。

### B3r实际检查与边界

11项新Python检查包含：真实隔离CLI默认禁用／拒绝参数；本地Git真实树／SHA通过；16种身份上下文替换拒绝且不创建客户端；assume-unchanged隐藏改动、额外字节码、symlink和staged配置替换拒绝；封闭配置；错误解释器／目录；固定工厂只调用监督器、不接受环境变量来源替换；不确定回传只用新客户端查询一次；无凭证／恢复失败不重发且隐藏私有错误；实际固定worker导入后无字节码写入。运行工厂的启用分支以受控环境／客户端替身验证，不伪称真实Actions执行。

11项运行Python＋8项进程＋10项恢复＋11项监督＋19项治理／状态=59项通过（ResourceWarning按错误）；2项Node实际YAML解析验证封闭触发、权限、双重禁用和固定步骤通过；另1项实际Python监督／凭证客户端／固定worker／本地Fetch路由恢复往返通过688.69ms，共62项。单独运行还发现测试解释器标志替身遗漏标准属性，已改为保留原属性并重新独跑11项、重跑59项通过；这是测试隔离修正。定点eslint发现测试未使用变量后已修正并重跑；机器状态／文档链接／diff检查通过。不重复无变化119项Node及M11测试。尚未执行GitHub平台工作流或跨日端到端，不改变旧生产及夜间断点。

独立提交feat: wire disabled M12 authorization workflow [skip ci]，父提交ae474fedff28bbe06e568488f7699db21a9567fd，完整SHA见交付消息。可撤回本固定工作流／工厂接点，保留已有归档和凭证；业务合同及政策版本不变。下一包为最终权限／业务目标config及同事务登记，然后进入既定C／D每日和跨日业务链。未合并、推送、创建云资源、部署、生产启用或对外通知。


## B3r导入边界P2与定点修复（待独立复核）

审核员针对3c1936c31957cc9600088907eacfee411b633285复现：runtime第52—54行只核验services／配置／工作流，却在第108行将整仓ROOT加入sys.path；未追踪的根目录base64.py因此能在checkout核验通过后执行。-I不能阻止代码自行扩大导入搜索路径，双重禁用仅说明尚无生产暴露，不能抵消此缺口。审核员已有59项Python、2项YAML、eslint及diff通过，仍判本包暂不通过。

本修复删除runtime和固定validation worker的ROOT搜索路径插入，统一用绝对同目录文件authorization_imports.py注册唯一services命名空间，其__path__仅为该固定文件所属的services目录。引导通过标准库runpy读取指定文件，不把仓库根加入sys.path；其他顶层模块仍只从隔离解释器路径解析。已有services命名空间仅允许同一精确目录（重复同路径不扩大权限），不同目录拒绝；不以预加载base64或某个模块黑名单遮蔽问题。固定HTTP子进程仍用-I、空环境和绝对脚本，不新增仓库导入或命令参数。该修复不复制业务验证，也不改变凭证、恢复、权限或工作流配置；worker的固定代码来源仍由已审核运行工厂checkout核验绑定。

新增3项测试使用真实-I -B子进程。第一项复制真实services到临时Git并提交，真实_checkout通过后执行实际runtime.run（仅测试覆盖本机解释器版本），分别在无遮蔽和根目录新增未追踪base64.py／urllib包／services.py／额外顶层模块的情况下验证：实际监督器与凭证客户端正确导入，缺Actions凭据在网络前按既有规则拒绝，base64／urllib来自标准库、仓库根不在sys.path、额外顶层模块不可解析。没有预加载base64，运行前明确断言尚未导入它。第二项直接运行实际固定worker及HTTP脚本，恶意同名模块带文件写入标记；两个进程均正常拒绝无效输入且不执行标记，不产生pyc。第三项验证已有外来services路径不能被接纳或覆盖。原工厂测试同时保持合法接线、恢复与封闭参数回归。

14项运行入口、8项进程、25项HTTPS通道、10项恢复、11项监督与19项治理／状态，共87项Python通过（ResourceWarning按错误，4.87秒）；另1项实际监督客户端／固定worker／本地Fetch路由恢复往返通过，总88项。状态生成／文档链接及diff检查通过；工作流未改变，不重复YAML和119项Node无变化完整套件。未进行真实Actions／TLS／跨runner恢复或跨日端到端验收。仅调整两处引导、新增共享命名空间文件、定点测试及三份治理文档，业务合同／政策不变。

独立提交fix: confine M12 imports to verified services namespace [skip ci]，父提交3c1936c31957cc9600088907eacfee411b633285；完整SHA见交付消息，交回此P2定点复核，不自行宣布通过。未合并、推送、创建云资源、部署、生产启用或对外通知；最终权限／目标config／同事务登记仍为下一包。


## B3r及导入P2独立复核结论

审核任务确认3c1936c31957cc9600088907eacfee411b633285及bb2807c205b77cebee2b92aa37be9ccd52bb1a8b在默认禁用固定工作流／凭证运行工厂范围通过，根目录导入P2关闭。独立87项Python（ResourceWarning按错误，4.369秒）及1项实际监督客户端／固定worker／本地API恢复（638.4ms）共88项通过；原2项YAML证据保留，diff及干净HEAD核对通过。结论不证明真实Actions环境保护、OIDC平台／TLS或最终授权生效。

## B3s：固定请求权限与内部原子授权登记（待独立审核）

新增内部AuthorizationRegistration，registrationPolicy缺省null时不构造存储／网络依赖，任何register请求立即拒绝。非空策略只能由受信服务器配置注入，字段精确为actor_id、approver_id、request；request为已批准的完整十字段请求。构造时保存不可变规范字节，不能在调用过程中由原配置对象改写；不接受RPC传入策略、已验证对象或成功声明。固定策略表示允许指定执行者与审核人登记这一个精确请求，不是任意grant权限。真实部署必须把该策略与获批控制提交／环境配置同步；本包没有配置任何生产策略实例或修改HTTP／工作流启用状态。

register始终复用B3f内部认证、原输入／票据绑定、授权及收据归档和独立读回。随后将实际授权产物的十字段请求、审核人和已验证OIDC actor规范编码，与服务器固定策略逐项精确匹配：业务config_ref、业务code_commit、publication_mode、scope、permissions、action、前序、生效／到期日期及reason全部绑定。控制来源code_commit仍与请求内业务提交分开；不把控制工作流版本当业务版本。该比较仅限制服务器允许登记的目标，不复算或另定义Python业务合同；日期、权限语义、链后继和授权身份计算仍由唯一Python验证器负责。

AuthorizationStore新增只供内部调用的registerValidatedAuthorization；在publish/global当前租约事务中核对原发送／票据／历史快照、原归档回传行与日志、actor、服务器权限谓词及未消费状态。实际登记时钟不得倒退、早于归档或超出原票据／原OIDC与新OIDC期限；写入前再次检查。一个事务追加授权index、更新head/revision、写单次票据consumption及register_authorization日志；写完再核历史、权限，并由withOwnedLease在提交前重验epoch／owner／fence／期限，任一失败全部回滚，R2原件及先前归档记录保留。重复或并发使用旧票据只允许一次成功；head改变后旧请求拒绝，不自动重建票据或另发授权。

新增SQLite表m12_authorization_consumptions，以ticket_id唯一，保存内部m12-authorization-registration/1记录：protocol、ticket_id、dispatch_id、原return_record、previous_ref、position、registered_at。消费记录与登记日志逐行配对，并关联实际index位置、授权Ref／原字节位置、前序及原回传行；缺行／错配在后续历史读取时要求恢复，不静默补记成功。启动增加该表但保留全部旧记录；若只有consumption幸存，禁止自动初始化空head。迁移不修改已有业务合同／身份或授权原件。

本包完成的是受信固定目标策略下的内部登记操作。完整业务配置对象、政策blob和实际运行代码来源仍由C包配置生产者核验；本操作的Ref精确匹配不能代替这些检查。登记记录也不等于允许当前时点发布：后续每次使用仍须解析最新授权链、有效期／撤销及实际配置／代码、M07政策和相应租约。真实服务器工厂与受控任务路由尚未连接此登记入口，既有return／recover响应仍表示归档事实，不能因新增此内部类把其解释为授权已登记或已生效。不存在生产grant、M11 active或生产切换。

### B3s实际检查与边界

新增9项Node专项，使用真实本地SQLite、实际Python唯一验证产生的授权／收据和已审核取证替身：默认关闭无依赖；首次grant与后继revoke的完整原字节、消费／日志及重开历史；完整请求各字段／审核人／actor不匹配；服务器策略深冻结；并发及重复单次消费；index／head／consumption／日志四个写入点逐次注入失败后全回滚并能显式重试；写完消费后租约到期全回滚；事务中原回传行损坏拒绝且回滚；消费与日志失配重开拒绝。正常用例最初只因Buffer与Uint8Array类型断言不一致失败，改为统一字节容器后通过，未为此改变业务实现。

157项环境取证／跨语言／登记及租约Node完整通过（最终19.34秒，无失败、取消或跳过），19项治理／项目状态通过，共176项；定点eslint、机器状态／文档链接／diff检查通过。未改变Python业务或工作流，不重复其完整测试和M11。测试使用本地SQLite事务、合成GitHub／R2和既有固定Python验证，不证明真实平台执行、云持久配置、HTTP登记接线、权限消费或跨日端到端已完成。

独立提交feat: atomically register approved M12 authorization [skip ci]，父bb2807c205b77cebee2b92aa37be9ccd52bb1a8b，完整SHA见交付消息。可撤回内部接线，但保留已存授权、消费和日志以供恢复，不删除记录来重开已消费票据。待此包审核后收口受控登记接线并进入既定C／D业务链；未合并、推送、创建云资源、部署、生产启用或对外通知。


## B3s索引来源完整性P2定点修复（待独立复核）

审核员针对2d709d480e0c4e4dcc3b04435f3e1ee44942c56f用真实本地SQLite和真实Python授权产物复现：首次grant登记后仅删除consumption及register_authorization日志，保留index／head／ticket／dispatch／R2原件，历史recover仍成功，预期拒绝断言失败。原因是只比较两类记录数量并遍历幸存consumption，双方为0时未从index反向要求来源。原157项Node（独立20.55秒）与19项治理状态、eslint及diff通过不能关闭此缺口。

修复在唯一Store历史读取中要求每个非基线索引位置都有且仅有一项已逐字段核对的consumption／登记日志。数量必须等于index长度减完整基线长度；每项位置必须位于基线之后、不得重复，最后反向遍历索引确认全覆盖。因此首项、内部项或尾项的两类证据同时丢失仍会失败，不依赖“曾登记过”的布尔标志。既有前序、归档、票据、回传与日志配对验证保留，prepare／return／登记／历史recover共享该检查。

基线边界通过单行m12_authorization_import_baseline保存完整、有序的reference／archive／previous_ref前缀，内容必须逐项等于实际历史前缀；不能只凭一个revision数豁免未登记历史。完全新库仅在所有授权表均为空时同事务初始化head和显式空基线[]。有任何幸存状态时绝不根据现存index生成或扩大基线；基线丢失、错配、实际历史短于基线、未标注旧索引均拒绝。生产代码没有写入非空基线或更新基线的入口，本轮不提供历史导入／迁移授权。将来若需导入，必须另经可信原件核验及显式批准迁移；旧版数据库缺边界时先失败关闭，不自动接纳。现有本地合成历史测试显式保存其完整固定前缀，仅作为受信测试夹具；这不证明存在真实导入历史。

新增3项专项：首grant后成对删除，实际recover及重开prepare均拒绝且index原字节不动；从空基线先后通过实际取证／Python验证及登记入口形成grant、不同控制提交的revoke，合法两项历史可恢复，然后逐项成对删除第一项或尾项证据，其他项仍完整时同样拒绝，回滚注入后恢复正常；明确基线的空值／错前序／缺失边界不能豁免旧索引，合法固定前缀保留。第二项使用受控GitHub响应与本地R2替身，不是真实平台批准。原“较新合法head可做历史恢复”测试改用真实登记入口生成后继，不再裸写无来源index；两项原历史删除反例改为精确期待更早的registration_recovery_required，不放宽成功条件。

本包仅修改Store完整性、对应测试夹具及三治理文档；默认禁用、业务合同／权限／原件及事务回滚不变。独立提交fix: verify complete M12 authorization index provenance [skip ci]，父2d709d480e0c4e4dcc3b04435f3e1ee44942c56f，完整SHA见交付消息。交回P2定点复核；不自行宣布通过，不扩展受控登记接线或C／D。未合并、推送、创建云资源、部署、生产启用或对外通知；跨日端到端仍未执行。

本P2修复实际检查：160项环境／跨语言／登记／恢复及租约Node完整通过19.30秒，无失败／取消／跳过；19项治理／状态通过，共179项。定点eslint、机器状态生成一致性、文档链接和diff检查通过。未重跑无变化Python业务完整套件或M11。


## B3s及索引来源P2独立复核结论

审核任务确认2d709d480e0c4e4dcc3b04435f3e1ee44942c56f及3788fb8301ff6582162213535179c267068ad61a在内部固定目标权限／原子登记范围通过，成对丢失P2关闭。独立160项Node（19.69秒）与19项治理／状态共179项通过，eslint／diff与干净HEAD核对通过；另以临时文件重跑原始首grant成对DELETE反例，真实recover按registration_recovery_required拒绝，额外1项probe通过。未来可信导入仍须另行批准；不证明真实配置原件、当前可发布或平台／TLS／跨日端到端。

## B3t：受控return登记接线（待独立审核）

AuthorizationJobApi新增仅由服务器构造参数提供的registrationPolicy，默认null保留原归档模式；整个API仍默认enabled=false，关闭时即使传有策略也不访问存储／网络。服务器显式配置固定策略时，既有POST /v1/authorization/return直接调用已审核AuthorizationRegistration.register，内部完成认证、固定目标权限匹配、原件归档读回及原子登记。请求仍精确为原protocol／dispatch_id／lease_token／result_base64，不能加入登记开关、策略或目标配置，也不新增/register RPC。没有第二套业务验证、消费写入或降级成功路径；策略不匹配继续409，已归档孤立对象保留。

登记成功响应精确为`{protocol,dispatch_id,state:'authorization_registered',authorization_archive,validation_receipt_archive,registration_position,registered_at}`。两个位置描述符和登记位置／时间来自实际持久登记记录，不由请求指定。状态仅说明该记录已登记，不表示当前发布操作已获准。响应编码后再用新鲜请求身份及服务器epoch读取已审核历史来源，比较原回传记录及对应索引位置的Ref／归档／前序；原票据因head推进已失效，不调用原current-dispatch逻辑复活它。编码后若身份过期或消费／日志证据丢失，返回原409，不发送成功响应；登记已提交时也不回滚或声称服务器从未收到。

未配置登记策略时仍返回原archived_pending_registration及原五字段形状；recover保持原archived_return_verified协议，只核对历史归档，不推断“未登记所以可以重发”。运行工厂两个完成文案分别改为validation_return_received与historical_return_verified，移除未核实的pending_registration后缀：无论服务器选择归档或登记，客户端都不凭粗粒度完成文案宣称登记生效／允许发布。原回传不确定→保留凭证→新客户端只查一次的流程不变。

新增4项路由专项：固定服务器策略登记并返回真实位置／时间，重复拒绝且只消费一次；请求不能替换策略／target或调用额外/register，服务器业务目标不符拒绝；默认无策略保留归档且整个API关闭时不触碰依赖；响应编码后分别注入身份过期、登记证据成对丢失，已提交索引保留但返回409。原实际Python监督器／凭证客户端／固定worker／本地Fetch恢复样例扩为归档、登记两种模式，登记模式确认服务器返回authorization_registered且index前进后人为丢弃HTTP响应、旧租约到期被另一Job接手，再用新原身份客户端只recover，最终只一次prepare／return、一次consumption，无重发或权限复活。

136项环境／跨语言／路由Node完整通过20.92秒，无失败／取消／跳过（新增登记恢复往返666.6ms）；14项运行工厂Python与19项治理状态共33项通过（ResourceWarning按错误），总169项。定点eslint、机器状态／文档链接／diff检查通过。Store／业务Python／工作流未改，不重复无变化租约整套及M11。新增实际往返仍为本地API、受控GitHub／R2和测试时钟，不证明真实网络断连、TLS或Actions平台配置。

独立提交feat: connect controlled M12 authorization registration [skip ci]，父3788fb8301ff6582162213535179c267068ad61a，完整SHA见交付消息。仅API接线、中性运行文案、对应测试及三治理；无实际生产registrationPolicy实例，工作流与runtime配置两道禁用均保持。撤回接线可恢复归档模式，但保留消费、授权及原件，不重新使用旧票据。待本包审核后进入已批准C／D同日来源、业务配置及每日／跨日链路；实际使用授权仍需核验完整配置／政策blob、当前链／撤销／日期与运行代码，未以本包代替。未合并、推送、创建云资源、部署、生产启用或对外通知，跨日端到端未执行。


## B3t独立审核结论

审核任务确认70bdd976a1adf6a0c461f9ef6a18746715690086在受控return登记接线范围通过，无新增阻断。独立136项Node（20.79秒，登记丢响应往返658.2ms）及14项运行工厂Python＋19项治理状态共169项通过（ResourceWarning按错误）；eslint／diff与干净HEAD核对通过，工作流if:false及runtime enabled:false／origin:null保留。结论不证明真实生产策略实例、平台／TLS、完整业务配置或跨日端到端。

## C1a：M02同日成员原字节解析及过滤审计（待独立审核）

进入已批准C同日来源包，先解决旧eodhd.symbols直接解析JSON、无法保留本轮原响应字节的问题。新增services/market_data/eodhd_membership.py纯解析入口parse_us_symbol_response；不新增HTTP客户端、文件根或formal写入口。入参为不可变原始bytes、规范as_of及可信采集开始／完成UTC datetime；两个实际观察时间必须均属同一个请求纽约日期且不能倒退，按America/New_York处理夏令时，不用UTC日期代替交易所日期。交易日历是否有实际交易会话仍由下一采集／资格接线验证；本函数的日期检查本身不证明某日已开市或完整收盘。

返回冻结dataclass材料，含as_of、开始／结束时间、原字节及其实际SHA-256、解析政策版本m12-eodhd-membership-source-1.0.0、原总数、全部纳入记录与全部排除记录／原因。记录保留供应商Code、Exchange、Type、Name、Country、Currency及可空Isin，不生成instrument_id／epoch／资格或UniverseSnapshot。额外供应商字段完整留在原字节，不能丢掉未知元数据或把显示顺序当成员身份。返回对象没有complete／universe_id标志；其source解析版本不是M12资格配置m12-eodhd-primary-common-1.0.0，两者不混用。

先严格解析整份UTF-8 JSON，拒绝空／非列表／坏行／重复JSON键／截断／非有限数（含溢出和额外元数据）／非法Unicode；原字节上限32MiB，超限整体拒绝，不截取部分列表。每行要求上述六个基本字符串规范非空且无控制字符，Isin缺失或null允许，其他非文本拒绝。按供应商Code检查整个响应的重复或跨交易所冲突，包括已排除项。全量校验后复用services/scanner/audit_eodhd.py:common现有Common Stock＋PRIMARY范围，不从缓存或下载目标取候选；非普通股与范围外交易所分别保留明确原因，零纳入拒绝，所有成功响应满足原总数＝纳入＋排除。

已识别Type固定Common Stock、Preferred Stock、ETF、FUND、Mutual Fund、Warrant、Unit、Notes；Exchange固定原PRIMARY及BATS／PINK／NMFQS／OTCQB／OTCQX／OTCMKTS／OTCBB／OTCGREY／OTC。该词表仅识别正常排除，不扩大主股票池；未知值整批失败，未来遇到其他标签须凭来源证据定点扩充适配，不能静默猜测或忽略。[EODHD官方端点说明](https://eodhd.com/financial-apis/exchanges-api-list-of-tickers-and-trading-hours)确认US为组合列表、非分页，Type返回值多于过滤参数允许值。此次仅查官方说明，没有读取真实账户token、请求真实股票名单或消耗供应商调用。

复用既有资格、身份、UniverseSnapshot3.x及影子根守门的边界已写入规则02 v1.8.0和已批准决策细化。纯解析既不证明HTTP响应完整、供应商现实覆盖或数据使用许可，也不写任何文件；未来可信采集器必须保存全部原件（包括被拒绝的响应），绑定实际固定请求／状态／时刻／完整读回，再接身份及逐成员资格。不能用调用者提供的raw或这份解析材料自证formal complete。当前旧每日／夜间和生产文件未改。

9项新测试覆盖原字节及中文额外元数据／摘要／完整分组；全部识别类型与交易所组合严格等于旧common选择；不可变交付及1001条不截断；重排／格式只改变原字节摘要；夏冬纽约跨UTC日期及午夜／倒时／非法时间；空／截断／重复键／非有限值／非法Unicode及大小；排除项缺字段仍失败；未知词表与重复Code／跨交易所冲突；无I/O和错误不回显私有内容。9项来源专项＋29项M02合同／股票池＋19项治理状态共57项通过（ResourceWarning按错误），机器状态／文档链接／diff检查通过。未重复M11、B层或无变化全部业务测试；这不是实际供应商全量或formal日验收。

独立提交feat: parse audited M12 daily membership sources [skip ci]，父70bdd976a1adf6a0c461f9ef6a18746715690086，完整SHA见交付消息。回退可撤回新解析接点，旧入口与已有记录保持；下一小包接真实受信采集及私有原字节归档，再继续身份／同日资格、配置和每日链。未合并、推送、创建云资源、部署、生产启用、真实数据调用或对外通知；跨日端到端未执行。


## C1a独立审核结论

审核任务确认6a194c9bdb770efb7ae3ddb68e5c53174c3c07b8在M02纯原字节解析／过滤审计范围通过，无新增阻断。独立57项Python通过0.055秒（ResourceWarning为错误）；另4项probe确认4097条完整保留，末尾未知Type、已排除ETF重复Code、坏Currency整体拒绝。diff、精确HEAD与干净工作区通过。不证明词表实际全量覆盖、交易会话、HTTP来源或数据授权。

## C1b：固定源采集与私有原件归档内部接点（待独立审核）

在原services/scanner/eodhd.py中新增observe_active_us_symbols，原get／symbols与每日／夜间消费者保持原行为。新接点只有固定HTTPS GET exchange-symbol-list/US、delisted=0、fmt=json及原token读取方式，无自选路径／参数、无自动重试；禁用环境代理和重定向，要求identity编码，固定30秒socket操作超时，另在每次读取前检查120秒预算。预算不是硬进程期限，未来运行监督负责取消；真实网络、TLS和供应商调用未执行。

采集开始／结束取实际UTC时钟。保存HTTP状态、合法Content-Length或null、是否达到响应EOF、有限错误码及实际接收bytes；HTTPError（包括被拒绝重定向、401、429、503）仍读取正文。HTTP失败、重复／不规范长度、编码／传输冲突、长度不符、连接失败、读取中断不产生成功材料。IncompleteRead的partial和此前收到的片段合并保留。上限32MiB，最多保存上限＋1字节便停止；超限、超时及中断都标不完整，不把捕获前缀当整份响应或哈希证据。供应商传输本身未交付的剩余字节无法归档；这一限制与采集失败一起明确保留。

services/market_data/membership_collection.py提供内部collect_membership(as_of, authorize, archive)：authorize是可信运行方提供的实际采集许可核验能力，接收精确日期和固定无token请求描述，拒绝或不返回非空原始证据bytes则不发源请求；先将许可证据write-if-absent且实际读回，再调用固定采集接点。这里不提供任意引用换许可的生产实现；测试能力返回的合成证据不能用于真实采集，token也不等于数据展示许可。真正的授权来源解析／身份绑定工厂以及R2通道仍为后续接线，当前没有可触发入口。

响应原件先归档／读回，之后只调用C1a唯一解析器；成功或拒绝再保存私有观察记录，包含无token固定请求、as_of、两次UTC实际时间、状态／长度／EOF、响应描述符、许可原件描述符、有限原因及成功时解析版本。所有对象使用raw/<实际SHA-256>；同一原件复用，不同观察时间形成不同记录，无权威索引更新。归档能力复用B1a put/read字节语义，由受信运行方固定注入，无本地任意目录或新持久存储实现；每次写后本模块独立比对实际读回的不可变bytes。写／读回失败统一失败关闭，可能已有的不可变孤立对象保留，不删除或伪报成功。返回仅包含观察记录位置／摘要及解析材料或失败码，不含formal complete、证券ID或资格。

14项新测试覆盖固定请求和许可原件在网络前读回、成功字节与时间、解析前已存原件、HTTP失败留正文不重试、部分读取／超时留前缀、连接失败空捕获、坏长度／编码、无Content-Length合法EOF、超限／预算、跨纽约日期、许可／前置归档失败不请求、后置归档失败不交付、重复原件／新观察保留和默认禁代理／重定向。测试调用实际EODHD字节采集逻辑，以内存响应和私有存储替身替代网络／R2；不声称真实跨语言存储桥已完成。14项采集＋9项解析＋24项旧EODHD＋29项M02合同／股票池＋19项治理状态共95项通过0.072秒（ResourceWarning按错误），机器状态／本地链接／diff通过；未重复无变化B／M11。

独立提交feat: collect fixed M12 membership source with private audit [skip ci]，父6a194c9bdb770efb7ae3ddb68e5c53174c3c07b8，完整SHA见交付消息。回退撤回新内部接点即可，既有来源／生产文件不迁移；保留已留存原件。下一包先完成受信私有R2通道和运行权限绑定，再接M02观察身份／同日资格与实际业务配置、C/D链。未合并、推送、创建云资源、真实数据调用、部署、生产启用或对外通知；跨日端到端仍未执行。


## C1b独立审核结论

审核任务确认98c82a76c510107d182d46a2fa3b1b0057a1e098在固定字节观察／可信内部采集与归档接点范围通过，无新增阻断。独立95项Python通过0.092秒（ResourceWarning为错误），diff、精确HEAD及干净工作区通过。另4项标准库HTTPResponse内存线协议probe中，合法Content-Length和chunked成功；短Content-Length为http_length_mismatch，截断chunked为http_incomplete_read且eof=false。只保证HTTPResponse已交付bytes／IncompleteRead.partial，不承诺底层缓冲未交付尾字节，EOF必须与failure共同消费。真实TLS、Python-R2／权限工厂及硬总期限均未验收。

## C1c：私有归档桥服务端会话（待独立审核）

新增services/publication/membership_archive.mjs内部MembershipArchiveSession，复用GitHubIdentityVerifier、ImmutableArchive及LeaseStore；无新HTTP路由、工作流或生产工厂。sessionPolicy默认null，禁用时不初始化SQL或访问网络。服务器固定策略精确包含acquisition_evidence原件描述符、actor_id、as_of、config_id、expires_at（UTC毫秒）、job及lease_token；结合固定identityPolicy编码成不可变会话归属，代码／工作流／任务／配置／来源／期限任一变化不能借用旧读取资格。配置根或供应商内容不能注入策略；当前仅测试构造，不声称来源核验工厂已完成或任意非空证据等于合法许可。

每个acquisitionEvidence／put／read调用都实际进行新OIDC签名与固定来源身份验证，核对完整Job和actor，持有daily/<as_of>/<config_id>既有租约；不初始化epoch、不自取租约、不续租。原租约期限、fence、会话固定期限和本次JWT期限共同约束，沿用withOwnedLease的事务前后期限／时钟检查。acquisitionEvidence只接受固定US active URL及会话日期，从私有R2绑定真实读回指定许可原件并校验长度和哈希，返回原bytes；每次put/read也重新读回该固定原件，原件缺失／损坏不给出成功。这里只绑定已批准运行能力的使用，实际许可语义与当前PublicationAuthorization／配置／撤销链的生产核验仍必须由后续唯一授权工厂完成。

put只接受raw/<SHA-256>及精确sha256／size_bytes，正文上限32MiB＋1（与C1b失败捕获边界一致），允许空失败捕获；原bytes在第一次await前复制。B1a实际write-if-absent并读回后，才在当前租约同步事务内登记m12_membership_raw_access及m12_membership_raw_log（配对描述符／服务器时刻）。完全相同重放复用一条归属和日志；归属与日志不配对或冲突失败关闭。中途归档／事务／租约失败可能留下不可变孤立原件，不能据此获得读取资格或formal事实身份。

read只允许服务器固定许可原件或本会话已实际写入／读回并登记的raw对象，不开放仅凭哈希查询整桶；在R2读取前后均重验归属／配对日志和当前租约。另一Job、actor、执行代码或会话参数不可继承读取权限；读中丢失配对记录也不给出字节。该表只控制私有字节可见范围，不是SourceInventory／UniverseSnapshot登记，不选择业务事实、不产生采集真实性或公开展示承诺。旧shadow守门及B授权合同／代码全部未变。

16项专项使用真实RSA签名、原身份验证器、真实本地SQLite事务和B1a实际适配器，R2/JWKS端点为内存替身：默认禁用、固定许可及任务归属、持久对象重开、他人哈希拒读、Job／actor／代码／签名差错、来源／日期替换、许可缺失／损坏、策略和入参不可变、R2失败孤立对象、会话／JWT期限（租约续约后旧JWT仍失效）、读写中fence接管、SQL末尾到期回滚、并发重放与腐坏、严格raw描述符、配对日志丢失／写失败及读取中归属丢失。16项Node＋19项治理状态共35项通过，定点eslint、机器状态／链接／diff通过。无真实Cloudflare跨请求持久性或Python↔R2网络验收，不重复无变化B／M11／C1b整套。

独立提交feat: bind private M12 raw archive access to task sessions [skip ci]，父98c82a76c510107d182d46a2fa3b1b0057a1e098，完整SHA见交付消息。回退撤回未接线会话，不删除对象或读取日志。下一小包接Python受控字节通道与服务端路由，随后补实际授权来源工厂／当前使用核验、M02身份资格和C/D链；完整归档桥尚未验收。未真实供应商调用、外部写入、合并、推送、云资源、部署、生产启用或对外通知；跨日端到端仍未执行。
