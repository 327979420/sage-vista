# M06｜市场与行业上下文本地验收报告

- 状态：`implemented`（获批影子范围已进入`main`）
- 基线：`f73512584bb412ddced3179a993fabee623a0b7a`
- 设计／规则提交：`c7f072a`
- 实现提交：`d97a74f`
- 测试提交：`d80744c`
- formal成分守恒修复：`187c0ec`
- 结论：影子成果和formal成分守恒修复已通过快速独立审核，完整审核链以纯fast-forward进入`main`；未部署或生产启用。

## 已完成

- `services/context/`成为唯一formal `ContextSnapshot 2.x`生产层。
- 精选注册表登记`SPY`、`QQQ`、`IWM`、`XLE`、`SOXX`、`BOTZ`；未核实的`BOTT`和`XOXX`未登记。
- 现有2026-08-26官方成分证据只以ticker-only legacy索引登记，缺listing生命周期时formal失败关闭。
- ETF状态集中保存趋势、回调、接近／确认突破、结构走弱及原始数字证据，同一ETF每批只计算一次。
- 一只股可同时引用多个ETF；M03—M05身份和事实只读引用，没有重算。
- 每日和回放影子入口调用同一生产器，默认生产入口不变。

## 独立审核修复

独立审核发现原验证器只要formal快照至少有一名稳定身份成员，就会忽略`members_source_count`和`unresolved_member_count`。这使“来源33名、只解析1名”可能冒充formal完整覆盖。

`187c0ec`已在唯一`validate_membership_registry()`入口失败关闭：所有快照的来源总数与未解析数必须是非负整数，且必须满足`来源总数 = 已解析成员数 + 未解析数`。formal还必须零未解析、至少一名稳定身份成员、完整数量相等、`formal_eligible=true`并且无偏差标签。legacy仍可保存未解析成员，但必须数量守恒、保存非空bias，且不能被formal选择。

当前真实2026-08-26成分仍是ticker-only legacy证据。SOXX—AVGO固定合成样本只证明合同能正确处理完整身份，不代表真实行业连接已完成。

## 验证证据

| 检查 | 结果 |
| --- | --- |
| M06专项 | 15项通过 |
| M01—M06相关定向 | 138项通过 |
| 完整Python | 505项通过 |
| `PYTHONHASHSEED=0/1/42/12345` | 每轮M06 15项通过 |
| 治理状态 | 19项通过 |
| Python编译 | 通过 |
| 前端lint／TypeScript／生产构建 | 通过 |
| 前端测试 | 11项通过 |
| 文档链接／`git diff --check` | 通过 |

## 固定反例

- SOXX—AVGO、BOTZ及一股多ETF完整formal合成样本可生成客观上下文。
- 只有当前ticker的成分快照不能进更早formal回放；显式legacy携带`current_membership_bias`。
- ETF行情缺失、成分版本冲突、稳定身份缺失或legacy进formal时失败关闭。
- formal来源33名而只解析1名、formal含任何未解析成员，或任何路径数量不守恒时失败关闭；完整formal和现有数量守恒legacy继续通过。
- `as_of`之后的极端K线不能改变当日ETF状态。
- 输入顺序、每日／回放入口和四种哈希种子不改身份与内容。

## 未改变的生产范围

本包没有修改`.github/`、`public/`、`automation/`、网站、Discord、默认每日／夜间入口、MACD、因子、评分、排名、交易或历史结果。`production_effect=false`。M07和M12尚未开始。

## 残余证据缺口

- 本地没有可用的真实ETF点时行情缓存，因此本轮不宣称完成真实市场全量复现。
- 2026-08-26成分证据缺可靠listing生命周期，只能作legacy证据。从未来完整保存稳定身份的成分日开始，formal才可向前追加。
- 真实生产缓存、Manifest、工作流、网站和Discord切换仍属M12，不属于M06缺陷。
