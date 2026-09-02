# M10｜内部基线评价器阶段验收报告

- 状态：M10-B在审核分支达到`verified`；M10整体仍为`implementing`
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
- 生产状态：未合并`main`、未部署、未生产启用

## 1. 阶段结论

M10-B已经用固定合成样本形成唯一内部基线评价层：ForwardOutcome从信号后下一有效交易日调整后开盘起算；TradeOutcome只读M08既有计划和退出事实；每次评价先绑定pending运行收据，结果通过后才追加complete收据。每日与回放影子入口调用同一生产器。

本报告只证明获批的内部Forward／Trade固定样本能力。它不产生真实多年回测结论，不代表生产接入，也不批准M10-C—E或外部引擎。

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
- 治理状态：19项通过。
- 前端：lint、TypeScript、生产构建及11项测试通过。
- Python编译和差异格式检查：通过。
- 新增机械回归证明：日历拒绝晚于`as_of`的session；5、19、59、99个已发生session时未成熟窗口目标日保持`null`，第20／60／100个session实际发生后才首次写入对应目标日。旧2.0.0不允许2.1.0字段且不能进入新formal完成流程；新2.1.0强制包含可空目标日字段，混合版本不能complete。1／5／20／60／100任一窗口换成错误但合法的已发生日历日期，或端点日期正确但使用相邻日价格，均不能complete；明确的5日端点`2026-09-09`改为`2026-09-08`并重建合法结果身份仍失败关闭。目标日行情缺失不回退前后价格；合法五窗口、成熟修订、每日／回放同源及幂等重放继续通过。原有日历指纹、落盘pending根、结果全集、ExitState及事件证券绑定反例继续拒绝。
- 来源版本机械回归证明：pending 1.0＋Outcome 1.1、pending 1.1＋Outcome 1.0、五个Forward结果中仅一个为1.0、以及completed单独降为1.0，即使重新生成稳定身份和内容指纹也全部失败；公共影子存储同样拒绝混合版本且失败后旧字节不变。完整1.1 pending→Outcome→completed及幂等重放继续通过；旧1.0收据仍可由通用合同只读验证，但不能写入或进入新formal运行。
- 测试前后没有出现范围外文件。

## 4. 明确未做

- 未实现PortfolioRun或ResearchAggregate算法。
- 未安装或接入VectorBT、Excel或其他依赖。
- 未创建CSV、Excel、CLI或看板。
- 未运行真实行情、真实每日任务或真实多年回测。
- 未修改生产入口、工作流、网站、Discord、公开JSON或历史断点。
- 未开始M10-C—E、M11或M12。

M10-B需经独立审核并另行批准合并；`verified`不等于`implemented`、部署或生产启用。
