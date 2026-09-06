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
