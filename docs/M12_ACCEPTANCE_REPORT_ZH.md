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
