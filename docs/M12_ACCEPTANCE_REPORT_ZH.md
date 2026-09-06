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
