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
