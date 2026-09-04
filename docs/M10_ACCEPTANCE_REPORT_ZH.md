# M10｜内部评价与只读汇总阶段验收报告

- 状态：M10-A／B／C／D均已完成独立审核并进入`main`；M10-D在获批查询与审核导出范围内为`implemented`；M10整体仍为`implementing`
- 基线：`1c7f688bd0d3f0c52386851b302c6197f25437fb`
- Forward实现：`209d088045cd5c9d87be130a1c4b8499336cd202`
- Trade实现：`a81d97ce288f7b62224e08556145c93a41df4b5c`
- 运行收据与同源入口：`940604e8a004a2e2d0c54fbfeda1e7c6e8e3af65`
- 运行结果完整守恒修复：`cd1379cda5513a7f13393ec47f23adbf897effa2`
- ExitState与事件证券绑定修复：`3cecf80f0afd79d84b56518b6f0bb6644d984bcf`
- Forward日历证据绑定修复：`fc3f2b72d37b874719935263dc0f55e11b6fbdd8`
- completed落盘pending根修复：`2f3fe38489668a4aa2929a40bd4f0354dab9fffc`
- Forward窗口目标交易日绑定修复：`9282ffb33c6f3028620b8a36398b1079dc568e6c`
- 无未来目标与ForwardOutcome 2.1隔离修复：`6ac5465ac3b2209dd3f2d0304125e4d6c7342569`
- internal-baseline来源版本统一修复：`ea4b6f187888a1f31b6398556eaa39539538d5b7`
- 历史结果链来源混用封堵：`d99db58d108eb0c404df406d624fb1d543f0a58b`
- 最终审核代码HEAD：`108a29271c75ba6b49f1172350fc3adbf3460a25`
- 合并方式：纯fast-forward进入`main`
- M10-C设计冻结：`dbcdcf6`
- M10-C只读汇总生产层：`041e6be`
- M10-C边界回归测试：`a08dd33`
- M10-C审核代码HEAD：`7bb635617ddcfb06277d23269cca9fdfe4cadb8d`
- M10-C合并方式：纯fast-forward进入`main`
- M10-D设计冻结：`b90c269`
- M10-D基线：`3c0a314c921ffc38121a8ef678cf61be16bd2b86`
- M10-D原子查询与CSV：`e7c649f`
- M10-D锁定XLSX审核副本：`ee6d596`
- M10-D逐格一致与安全复核：`d682897`
- M10-D审核修复：`61de04e`
- M10-D审核通过代码HEAD：`f91a6fa5773561354b255f9217679f237b0f7017`
- M10-D合并方式：纯fast-forward进入`main`
- 生产状态：未部署、未生产启用

## 1. 阶段结论

M10-B已经用固定合成样本形成唯一内部基线评价层：ForwardOutcome从信号后下一有效交易日调整后开盘起算；TradeOutcome只读M08既有计划和退出事实；每次评价先绑定pending运行收据，结果通过后才追加complete收据。每日与回放影子入口调用同一生产器。

本报告还记录M10-C已经独立审核并进入`main`的Portfolio失败关闭边界和只读gross汇总能力。它不产生真实组合或多年回测结论；进入主线不代表生产接入或部署，也不自动批准M10-E或外部引擎。

M10-D已通过独立审核并以纯fast-forward进入`main`：唯一查询入口从`EvaluationShadowStore`取得原子库存，显式执行`all/current`修订语义并验证查询全集；CSV与XLSX逐字段绑定权威payload，完整包通过一次目录重命名发布，并由固定样式与标准库限定OOXML复核逐格对账。`ExportManifest`保存逻辑导出与实际物化证据，Human Review保持只出不进。该`implemented`只表示获批查询和审核导出基础设施进入主线，未部署、未生产启用，也不批准M10-E或外部引擎。

## 2. 已验证口径

| 验收项 | 结果 |
| --- | --- |
| Forward起点只用信号后下一有效交易日调整后开盘 | 通过 |
| 信号日收盘不作为起点；下一开盘缺失不回退其他价格 | 通过 |
| 日历只保存不晚于`as_of`的已发生session前缀；未成熟窗口的目标日和端点均为`null` | 通过 |
| 成熟窗口目标日严格等于已发生session前缀的第N日；端点日期和价格必须来自该日历对应行 | 通过 |
| 旧ForwardOutcome 2.0.0按原字段只读；新formal生产和完成流程只接受严格ForwardOutcome 2.1.0 | 通过 |
| 未成熟窗口为pending；到期缺证据为partial或unavailable | 通过 |
| Forward MFE／MAE只使用已成熟且完整的窗口证据 | 通过 |
| Trade只读M08入场、止损、目标、40日和同日止损优先结果 | 通过 |
| Trade毛收益、R收益和持有交易日数可复核 | 通过 |
| formal净收益因费用／滑点未批准保持unavailable | 通过 |
| 零成本净收益只允许明确comparison | 通过 |
| Trade MFE／MAE均为unavailable，写入数值验证失败 | 通过 |
| pending成熟只追加修订，旧记录不覆盖 | 通过 |
| ExperimentRun输入、结果引用及收据修订守恒 | 通过 |
| pending收据冻结事件、证券、日期、行情、股票池、规范化日历ID与实际session内容指纹、计划、ExitState及预期逻辑结果；五个Forward窗口必须绑定同一日历证据，complete拒绝缺少、重复、多出、外来或换指纹结果 | 通过 |
| Forward每个事件完整保存1／5／20／60／100五个窗口，混合pending／partial／unavailable／mature状态也保持集合守恒 | 通过 |
| 内部基线completed必须在同一run锁内直接承接实际落盘的唯一pending链尾；仅有结果、无pending根或伪造未落盘前序均失败且旧字节不变 | 通过 |
| 新formal internal-baseline的pending收据、全部Forward／Trade结果和completed收据必须共同使用`m10-b-internal-1.1.0`；旧1.0仅通用合同只读，不能参与、追加或完成新运行 | 通过 |
| ExitState状态、退出原因、退出日期与执行价格一致；active不能伪造终态事实 | 通过 |
| M09事件、TradePlan、ExitState及两条机器链接的证券和信号日完全一致 | 通过 |
| 每日与回放相同输入得到相同结果和运行身份 | 通过 |
| M02—M09输入在评价前后不变 | 通过 |

## 3. 验证记录

- M10合同与基线专项：78项通过；M08与M10专项：93项通过。
- M01—M10扩大定向（含M02行情仓）：274项通过。
- 完整Python：630项通过。
- `PYTHONHASHSEED=0/1/42/12345`：每轮93项通过。
- 机械版本攻击及最终四闸门：11项通过。
- 治理状态：19项通过。
- 前端：lint、TypeScript、生产构建及11项测试通过。
- Python编译、文档链接和差异格式检查：通过。
- 新增机械回归证明：日历拒绝晚于`as_of`的session；5、19、59、99个已发生session时未成熟窗口目标日保持`null`，第20／60／100个session实际发生后才首次写入对应目标日。旧2.0.0不允许2.1.0字段且不能进入新formal完成流程；新2.1.0强制包含可空目标日字段，混合版本不能complete。1／5／20／60／100任一窗口换成错误但合法的已发生日历日期，或端点日期正确但使用相邻日价格，均不能complete；明确的5日端点`2026-09-09`改为`2026-09-08`并重建合法结果身份仍失败关闭。目标日行情缺失不回退前后价格；合法五窗口、成熟修订、每日／回放同源及幂等重放继续通过。原有日历指纹、落盘pending根、结果全集、ExitState及事件证券绑定反例继续拒绝。
- 来源版本机械回归证明：pending 1.0＋Outcome 1.1、pending 1.1＋Outcome 1.0、五个Forward结果中仅一个为1.0、以及completed单独降为1.0，即使重新生成稳定身份和内容指纹也全部失败；公共影子存储同样拒绝混合版本且失败后旧字节不变。历史1.0结果即使已经存在，也不能被新1.1生产器或公共存储追加为同一修订链。完整1.1 pending→Outcome→completed及幂等重放继续通过；旧1.0收据仍可由通用合同只读验证，但不能写入或进入新formal运行。
- 测试前后没有出现范围外文件。

## 4. M10-C独立审核与主线验收

| 验收项 | 结果 |
| --- | --- |
| `PortfolioRun 2.1.0`只接收已重新验证的TradeOutcome对象，引用规范排序且输入顺序不改变身份 | 通过 |
| 未批准资本政策时Portfolio恒为`unavailable/capital_allocation_policy_not_approved`，禁止收益、资金、仓位、曲线、回撤或改名指标 | 通过 |
| `ResearchAggregate 2.1.0`只消费一种完整的Forward或Trade结果对象，重新验证ID、内容指纹、逻辑链及共同口径 | 通过 |
| Forward严格区分`pending/mature/partial/unavailable`；Trade严格区分`completed/open/no_trade/unavailable` | 通过 |
| Trade `open`只从已验证的`pending + trade_open`映射，与`no_trade`分别计数，两者都进入missing而不当作零收益 | 通过 |
| `total=sum(status_counts)=evaluated+missing`且`win+loss+flat=evaluated` | 通过 |
| 空样本、无亏损、无盈利、全零、NaN／Infinity及PF量化边界 | 通过 |
| 生产和验证共用Decimal、`1e-10`和`ROUND_HALF_EVEN`；`gross_expectancy`与平均毛收益保持同一公式 | 通过 |
| 公共影子存储在同run锁内要求完整来源结果并重算守恒；重签统计、状态伪装、错误`as_of`和failed收据均失败且旧字节不变 | 通过 |
| 旧Portfolio／Aggregate `2.0.0`仅通用合同只读；新formal生产、运行和存储只接受`2.1.0`+`m10-c-readonly-1.0.0` | 通过 |

- M10-C专项：27项通过；M10合同／基线／汇总：105项通过；M08与M10：120项通过；指定含M09集合：139项通过。
- M01—M10扩大定向：290项通过；完整Python：657项通过。
- `PYTHONHASHSEED=0/1/42/12345`：M10-C每轮27项通过。
- 治理状态：19项通过；前端lint、TypeScript、生产构建和11项测试通过。
- Python编译、文档链接和差异格式检查通过；测试前后工作区没有意外文件。

## 5. M10-D独立审核与主线验收

| 验收项 | 结果 |
| --- | --- |
| `EvaluationQuery 2.0.0`强制显式`revision_mode=all/current`；`current`先验完整修订链、选择唯一叶节点再过滤 | 通过 |
| 查询与写入共享store级inventory锁；锁顺序固定，查询只看到完整旧库存或完整新库存 | 通过 |
| 坏合同、坏ID／指纹、未知版本、断链、分叉、循环和ticker歧义失败关闭 | 通过 |
| M10-D启用前没有历史库存证据时返回`historical_inventory_unavailable`，不按时间戳猜历史 | 通过 |
| CSV使用UTF-8无BOM、RFC 4180／CRLF、固定列序与稳定行序；`audit_cell_codec_v1`可逆区分null、空串、0、false和真实`\\N` | 通过 |
| 每part最多1,000,000数据行；小阈值分片无丢失、重复或截断，各dataset独立守恒 | 通过 |
| `XlsxWriter==3.2.9`只锁入独立研究导出依赖；wheel／sdist哈希和BSD-2-Clause许可证证据已冻结 | 通过 |
| XLSX启用`constant_memory`并关闭公式、URL和数字自动转换；Decimal显示值与canonical text并列，不能安全往返时不伪造数值 | 通过 |
| 标准库限定OOXML复核真实sheet顺序、工作表范围、单元格类型及CSV逐格一致；公式、外链、未知cell和重签篡改失败 | 通过 |
| 没有来源行的结果表不生成；Score／Factor／Pair Matrix只在Coverage标记`not_implemented` | 通过 |
| `ExportManifest 2.0.0`区分稳定`export_id`与物化`export_receipt_id`，绑定来源、配置、逐part行数、字节数及SHA-256 | 通过 |
| 临时包写完、重读、校验、fsync后一次重命名；故障、路径逃逸、符号链接和已有导出冲突不留下半包 | 通过 |
| Human Review只出不进；人工修改使SHA失效，CSV／XLSX没有回写M10的入口 | 通过 |

独立审核随后复现了五个会影响导出数字可信度的阻断点，本分支以窄修复关闭：查询复核现在必须从同一冻结库存内嵌的规范payload重新执行唯一查询推导，缺少该证据明确返回`inventory_evidence_unavailable`；导出包验证从已验证payload重新生成全部主表和引用子表并逐表头、列序、行序和单元格精确对账；OOXML复核改为命名空间感知的固定结构／关系白名单并拒绝全部公式载体、外链、DDE／OLE、宏和异常ZIP成员；`styles.xml`及单元格style角色使用固定XlsxWriter 3.2.9白名单，额外或隐藏格式即失败；`export_receipt_id`由完整Manifest物化语义统一重算，外部传入ID不受信任。上述修复没有处理列宽、分页或66页等非阻断可读性问题。

- M10-D专项：25项通过；M10 A—D相关定向：130项通过；M08—M10：164项通过。
- M01—M10扩大定向：315项通过；完整Python：682项通过。
- `PYTHONHASHSEED=0/1/42/12345`：M10-D每轮25项通过。
- 治理状态：19项通过；前端lint、TypeScript、生产构建和11项测试通过。
- Python编译、隔离依赖完整性、文档链接和差异格式检查通过；测试前后工作区没有意外文件。
- 五项审核修复后：M10-D专项33项、M10 A—D相关定向138项、完整Python 690项通过；四种固定`PYTHONHASHSEED`下M10-D每轮33项通过。治理19项、前端11项、Python编译、独立XlsxWriter依赖证据、lint、TypeScript、生产构建、文档链接及格式检查通过。
- 最终独立审核的五个闸门全部通过，原始六项完整重签攻击全部失败关闭；43个本地文档链接通过。审核代码HEAD为`f91a6fa5773561354b255f9217679f237b0f7017`，已纯fast-forward进入`main`。

## 6. 明确未做

- 未实现Portfolio资本、仓位、现金、权益曲线或风险算法；M10-C只产生明确`unavailable`的Portfolio边界。
- 未实现读取行情或重算逐股收益的研究算法；ResearchAggregate只读已冻结的`gross_return`。
- 未安装或接入VectorBT；`XlsxWriter==3.2.9`仅存在于被忽略`work/`中的隔离研究导出环境和独立锁文件，不进入生产依赖。
- 未创建M10-E CLI或看板；本轮CSV／XLSX只使用固定合成样本和临时目录验收，没有提交生成文件。
- 未运行真实行情、真实每日任务或真实多年回测。
- 未修改生产入口、工作流、网站、Discord、公开JSON或历史断点。
- 未开始M10-E、M11或M12。

M10-A／B／C／D均已完成独立审核并进入`main`，M10整体仍为`implementing`。M10-D进入主线不等于部署、生产启用或完成真实历史导出；尚未生成正式生产CSV／XLSX，网站和Discord也未提供查询或下载。M10-E、Portfolio资本算法、VectorBT、CLI、看板、M11和M12均未开始；默认每日、夜间、网站、Discord和公开JSON均未切换，也未访问EODHD或运行真实行情／真实多年回测。Excel仍是人工审核副本，人工修改不能回写M10权威账本。
