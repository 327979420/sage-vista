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
