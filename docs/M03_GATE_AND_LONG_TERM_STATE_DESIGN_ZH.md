# M03｜唯一门卫与长期状态设计包

- 对应需求：`CR-2026-09-01-042`
- 设计状态：已批准
- 实施状态：`implemented`（M03获批影子范围）；A— I及独立审计修复已通过纯fast-forward随`d02b03295a5e37cebeb788bc780fbede67e574a0`进入`main`
- 生产状态：未部署、未启用
- 设计基线：`main`合并提交`345a1ee018134801ad2a1dd91d396a76e1917f2e`，以及其后的M02治理收口提交`c35c154`
- 本文性质：正式设计版与人话版合一；获批交付范围仅限影子基础设施，不改变当前选股结果

## 一、人话版：M03到底要解决什么

现在系统像有几位门卫，各拿着一本不同的名单：

- 每日因子快照先检查价格、成交额和日线MACD；
- 复杂多因子又检查一次长期趋势；
- 稀有机会扫描器还会自己检查长期趋势和60日回调；
- 旧Tracker使用另一套日／周／月MACD组合门槛；
- “我最喜欢形态”在旧Tracker里独立观察，并不引用统一门票。

这会造成同一只股票在同一天被不同模块用不同理由放行或拦下。M03准备建立一位唯一门卫：它只看统一输入。没有通过数据完整性、可交易性、流动性和精确日线MACD刚金叉这条创建边界的股票，不伪造一张“失败事件”，只进入扫描审计计数；到达边界后才生成一张唯一、可追溯的`GateEvent`。后面的复杂多因子和个人形态只能引用这张事件，不能自己再造门票。

M03不负责算39项因子、不负责排名，也不决定买卖计划。现有`qualification.long_trend`只按原定义保存为基线等价结果；长期筑底、深跌、宽幅箱体、持续供给和新增0.618／70%结构在没有实验批准前只进入`shadow_assessment`，且固定`production_effect=false`，不能因为四个已见案例就直接改变生产结果。

## 二、本轮冻结边界

目标流程：

```text
M02行情与股票池
→ 数据完整／可交易／流动性
→ 精确日线MACD刚金叉
→ 当前长期资格行为等价检查
→ 局部0.618／70%结构事实
→ 多年回撤事实
→ 完整月线长期状态
→ 唯一GateEvent
```

精确日线MACD刚金叉完成后，就已经到达“允许形成完整事件”的创建边界；后续步骤负责把当前长期资格基线和影子结构事实填完整，最后一次性输出GateEvent。现有长期趋势基线只决定`baseline_passed`；其余新增结构和长期事实只作影子观察。任何影子判断都不能倒过来取消事件、改变`baseline_passed`或改变当前生产结果。

目标长期状态只有：

- `uptrend_pullback`
- `long_base_reversal`
- `broad_range`
- `structural_damage`
- `unavailable`

本轮明确不做：

- 不修改正式评分、因子权重、排行榜或精选门槛；
- 不设计评分、排行、交易、总账或收益评价合同；M03止于GateEvent；
- 不修改止损、退出或持仓；
- 不用今天名单倒填历史股票池；
- 不把CGEM、MRNA、BTDR或DLTR观察直接变成生产硬规则；
- 不重写历史`GateEvent`、信号史或机会账本；
- 不修改生产网站、Discord、工作流或公开JSON；
- 不运行真实每日行情或真实多年回测；
- 不进入M04、M05实现或M12；
- 不实施任何M04—M13业务代码；M03超出本设计的变化必须重新批准。

## 三、设计基线时的真实生产链路审计

本节“当前”指M03开始前的生产默认链路。A— I本地影子实现完成后，`services/gates/`已经存在，但尚未接管生产；因此下表对生产现状仍成立，关于“仓库尚无M03影子实现”的历史描述以本节标题和文末验收状态为准。

### 3.1 每日生产链

当前`.github/workflows/daily-eod.yml`先运行`services.scanner.daily_tracker_update`，之后另行运行`services.scanner.unified_v2_scan --published-latest`。

| 位置 | 当前职责 | 当前问题 | M03处理建议 |
|---|---|---|---|
| `services/scanner/daily_tracker_update.py::run` | 依次生成Tracker、因子快照、稀有机会、大盘、行业和事件史，再原子发布 | 只是流程编排，没有统一GateEvent | M03影子期不改默认调用；以后只接收门卫产物引用 |
| `services/scanner/factor_snapshot.py::load_symbol_rows` | 从旧缓存、active-common和当日bulk拼行情，并可能回写旧缓存 | 仍是legacy生产输入，不是M02 formal入口 | 生产保持不动；M03影子只用M02注入输入 |
| `services/scanner/factor_snapshot.py::build_snapshot` | 要求同日、至少420行、收盘不低于5美元、成交额不低于1000万美元；随后检查精确日线MACD刚金叉，再计算全部因子 | 它最接近当前主门票，但没有独立GateEvent；长期资格不是这里的前置硬门 | 行为等价部分先迁到唯一门卫；全因子留给M04 |
| `services/scanner/factor_snapshot.py::exact_daily_macd_bull_cross` | 只认当日完整收盘由下向上穿越 | 是应保留的精确门票定义 | 迁为唯一纯函数或由唯一门卫调用，其他消费者不得复制 |
| `services/scanner/factor_detectors.py::evaluate_all_factors` | 计算`qualification.long_trend`、Fibonacci、周月证据及其他因子 | 资格事实和深度因子混在全因子库里；MACD因子还保留近5日状态 | M03只抽取门卫所需事实；近5日状态不能冒充当日事件 |
| `services/scanner/unified_v2_scan.py::_candidate` | 再次要求精确MACD触发和`qualification.long_trend`命中，然后计算共振和排名 | 形成第二道门；长期资格藏在排名器中 | 未来只接受同一`gate_event_id`；M03影子期保持旧结果作对照 |
| `services/scanner/rare_opportunity_scanner.py::run` | 自己再检查长期趋势和60日回调后才形成研究信号 | 第三套资格判断 | 未来只消费GateEvent和技术证据，不再自己判断资格 |
| `services/scanner/resonance_tracker.py::macd_buy_gate` | 使用日／周／月MACD“新交叉、接近交叉、柱体收缩”等组合 | 与“精确日线刚金叉”不是同一门票 | 标为legacy，迁移后退休；不得冒充M03门卫 |
| `services/scanner/favorite_pattern_tracker.py` | 在Tracker内独立检测个人形态 | 当前可以在没有精确日线刚金叉时观察，不引用GateEvent | 生产暂不变；目标迁移必须明确兼容方式，见未决选择 |

### 3.2 历史回放链

| 位置 | 当前职责 | 风险 |
|---|---|---|
| `services/scanner/unified_v2_scan.py::run` | 直接加载旧缓存，逐日调用`build_snapshot()`与`_candidate()` | 复制每日门槛，默认历史路径仍是legacy；尚未使用formal股票池 |
| `services/scanner/macd_factor_backtest.py::event_rows` | 自己计算精确日线MACD、价格和成交额；周月数据使用完整周期 | 是研究事件生成器，不是唯一GateEvent生产者 |
| `services/scanner/macd_factor_backtest.py::long_trend_ok` | `close >= 0.9*EMA200`且EMA200近60日跌幅不超过3% | 当前简化长期资格，不能识别多年筑底、宽幅箱体或深度结构破坏 |
| `services/scanner/macd_factor_backtest.py::fibonacci_support_levels` | 从最近有效、已确认的上涨波段计算0.5／0.618附近事实 | 只判断“靠近”，尚未表达70%破坏与0.618收复状态 |
| `services/scanner/detectors.py::pivots` | 只返回在查询截止日前已经得到右侧K线确认的pivot | 这是M03必须复用的防未来基础，不能另写一套无右侧确认pivot |

### 3.3 其他同名判断不能漏算

- `factor_detectors.evaluate_all_factors()`把`macd.daily_bull_cross`作为事件因子保存，并允许“近5日命中过”的记忆；这个记忆只能作技术事实，不能再次触发GateEvent。
- `rare_opportunity_scanner.py`保留了自己的`recent_bull_cross()`定义，但当前`run()`实际先依赖同日因子快照，再自行检查`long_trend_ok()`与60日回调；未被调用的重复定义也应在迁移后删除或明确退休，不能成为备用门票。
- `macd_factor_backtest.higher_timeframe_events()`会独立产生周线／月线金叉研究事件。这些是高周期研究事实，不是M03的日线候选门票。
- `factor_effectiveness.py`把`qualification.long_trend`和`macd.daily_bull_cross`列为共同门槛，用于既有因子效果报告；未来必须读取GateEvent身份，但M03不能改写已保存研究结论。
- `favorite_pattern_tracker.py`内部有二底附近MACD、二次启动MACD、至少5%客观回调和序列重置回撤。这些是个人形态内部证据，不是共同门卫的多年回撤或局部0.618／70%定义。
- 当前仓库没有五种目标长期状态的统一分类器；大盘温度、行业状态、个人形态stage和Tracker方向标签都不是股票长期状态，禁止拿来代替。

### 3.4 事件与合同现状

- M01在`services/contracts/validation.py`中只有`GateEvent 1.x`的最小合同：`gate_event_id`、`symbol`、`signal_date`、`gate_policy_version`和`passed`。它是验证外壳，不是生产者。
- 旧适配器把`daily-factor-snapshot.json`描述为`GateEvent + TechnicalEvidence`，但旧文件只有合格数量与MACD触发股票，缺少formal股票池、结构和长期状态证据；只能继续标为legacy只读适配，不能冒充M03完整事件。
- `signal_history.py`和`opportunity_ledger.py`目前以Tracker、稀有机会、个人形态或V2排名为来源，没有稳定`gate_event_id`外键。M03不改写这些历史；以后只对新事件追加引用。

### 3.5 审计结论

当前生产默认链没有唯一门卫，也没有发布完整M03 `GateEvent`。最接近主流程的是：

```text
factor_snapshot.build_snapshot
→ unified_v2_scan._candidate
→ unified_v2_scan._rank_day
```

但稀有机会、旧Tracker和个人形态仍各有旁路。M03必须先影子建立唯一事件，再逐个消费者迁移，不能一次替换生产链。

## 四、唯一负责人和文件边界

唯一门卫已经按用户确认放在中立目录`services/gates/`，而不是放进扫描器、因子模型或回测器。职责如下：

| 实施文件 | 唯一职责 |
|---|---|
| `services/gates/baseline.py` | 冻结现有历史长度、价格、流动性、精确日线MACD和长期资格行为等价语义 |
| `services/gates/local_structure.py` | 已确认局部波段、0.618／70%结构事实 |
| `services/gates/long_term_state.py` | 多年回撤、完整月线和五态分类事实 |
| `services/gates/producer.py` | 组合输入证据、失败关闭并生成唯一GateEvent |
| `services/gates/producer.py::require_gate_event_for_path` | 只读隔离旧1.x门票，不补造缺失事实、不回写历史 |

共享日期、SemVer、规范哈希、合同验证、OHLCV验证和点时输入必须复用`services/contracts/`与`services/market_data/`。禁止在`services/gates/`复制第二套。

`services/gates/producer.py`是唯一允许创建新M03 `gate_event_id`的模块。每日、回测、复杂多因子、个人形态、事件账和页面只能读取或引用，不能自行生成。

## 五、M01与M02怎样接入

### 5.1 formal输入

formal门卫只接受：

- 已验证的`UniverseSnapshot 3.x`，查询日必须有同日完整成员与每名成员资格／排除证据；
- M02唯一消费者桥交付的不可变、已验证调整后OHLCV；
- 与查询日一致的`MarketDataSnapshot`身份；
- 明确的`as_of`、`universe_id`、`market_snapshot_id`和`adjustment_policy`；
- `future_data_used=false`。

缺少formal股票池时直接返回`universe_unavailable`，不得自动使用今天名单或legacy名单。2026-08-28及更早日期因为缺少完整历史成员与逐名资格证据，必须继续失败关闭。

### 5.2 legacy研究输入

legacy研究必须由调用者显式选择，至少携带：

- `path_status=legacy_observed`或对应旧路径标识；
- `survivorship_bias`；
- `incomplete_membership_evidence`；
- `not_formal_point_in_time_universe`。

legacy可用于新旧结果对照和历史兼容，不能被formal选择器接受，也不能在formal缺失时自动接管。

### 5.3 M03可以独立验收的输入与输出

M03输入只有M02已经验证的点时股票池、不可变行情和它们的身份；不依赖因子分、排行榜、交易计划、事件总账或未来收益才能运行。

M03输出只有：

- `GateEvent 2.x`：唯一、不可变、点时的门卫结论和结构事实；
- `GateScanAudit 1.x`：没有形成事件时的批次级原因计数；
- `shadow_assessment`：GateEvent内部的结构化长期状态事实，固定`production_effect=false`。

因此M03可以单独证明唯一生产者、确定性、每日／回放纯函数复用、当前基线行为等价、formal／legacy隔离和防未来；不需要等待任何后续模块完成。

## 六、GateEvent 2.0.0设计

### 6.1 为什么升级主版本

M01的`GateEvent 1.x`只要求五个业务字段。M03要新增输入身份、分级检查、长期状态、偏差、失败原因和不可变内容身份，并改变稳定ID算法。这是破坏性合同变化，因此建议新建`GateEvent 2.0.0`；旧1.x继续只读验证，不能静默解释成2.x。

### 6.2 创建边界、基线结果与影子结果

完整`GateEvent`的创建边界冻结为：

1. formal或显式legacy路径身份可验证；
2. 截止`as_of`的数据完整且可交易；
3. 当前既有价格、历史长度和流动性门槛通过；
4. 当日完整日K发生精确MACD刚金叉。

任一项未通过或无法判断，都不得创建`passed=false`的完整`GateEvent`。它只能进入第6.7节定义的`GateScanAudit`原因计数。到达创建边界后，事件才保存两类彼此独立的结果：

- `baseline_passed`：当前获批基线门卫结果。M03影子对照期，它等于创建边界已经通过，并且当前复杂多因子候选使用的`qualification.long_trend`等价检查通过。该长期趋势定义保持为`close >= 0.9 × EMA200`且EMA200近60日跌幅不超过3%，M03不得借重构调整阈值或公式。
- `passed`：为M01字段兼容保留的显式别名，必须与`baseline_passed`严格相等；任何不相等都属于合同错误。未来若移除别名必须升级合同主版本。
- `shadow_assessment`：保存新增结构和长期研究事实，必须带`production_effect=false`。它可以给出`shadow_exclusion_candidate`等观察建议，但不能改变`baseline_passed`或任何当前生产输出。

现有长期判断的归类冻结如下：

| 判断 | M03归类 | 行为要求 |
|---|---|---|
| `factor_detectors`中的`qualification.long_trend`及`macd_factor_backtest.long_trend_ok()` | 必须保持行为等价的基线语义 | 只迁移唯一实现，不改EMA200阈值、斜率窗口或通过结果 |
| `unified_v2_scan._candidate()`对上述长期资格的要求 | 当前复杂多因子基线消费语义 | 影子期逐候选对照，不改变现有生产输入 |
| 稀有机会的60日回调／长期趋势、Tracker高周期组合 | legacy消费者私有语义 | 默认结果保持不变，不能冒充M03共同基线 |
| `long_base_reversal`、`broad_range`、`structural_damage`、多年回撤、0.618／70%和持续供给 | 新增影子研究 | 结构化保存，`production_effect=false`，不改变基线资格或生产输出 |

### 6.3 建议结构

```json
{
  "schema_version": "2.0.0",
  "as_of": "2027-01-05",
  "generated_at": "2027-01-05T23:10:00Z",
  "source_version": {
    "gate_policy": "m03-shadow-1.0.0",
    "market_data_contract": "1.0.0",
    "universe_contract": "3.0.0"
  },
  "future_data_used": false,
  "gate_event_id": "gate:sha256:<64位小写十六进制>",
  "event_content_fingerprint": "sha256:<64位小写十六进制>",
  "logical_signal_id": "gate-signal:sha256:<64位小写十六进制>",
  "supersedes_event_id": null,
  "instrument_id": "instrument:sha256:<64位小写十六进制>",
  "symbol": "SAMPLE",
  "signal_date": "2027-01-05",
  "gate_policy_version": "m03-shadow-1.0.0",
  "path_status": "formal",
  "input_identity": {
    "universe_id": "universe:sha256:<...>",
    "market_snapshot_id": "market:sha256:<...>",
    "adjustment_policy": {
      "version": "eodhd-adjusted-ratio-1.0.0",
      "formula": "ratio=adjusted_close/close; adjusted_ohlc=raw_ohlc*ratio"
    }
  },
  "baseline_checks": {
    "data_integrity": {"status": "passed", "reason_codes": []},
    "tradability_liquidity": {"status": "passed", "close": 10.0, "dollar_volume": 15000000, "history_sessions": 500},
    "exact_daily_macd_cross": {"status": "passed", "date": "2027-01-05", "recent_state_used": false},
    "legacy_long_trend_equivalence": {"status": "passed", "ema200_ratio_floor": 0.9, "ema200_change_60d_floor": -0.03}
  },
  "baseline_passed": true,
  "passed": true,
  "baseline_reason_codes": [],
  "shadow_assessment": {
    "status": "observed",
    "suggested_disposition": "observe",
    "production_effect": false,
    "shadow_fact_schema_version": "m03-shadow-facts-1.0.0",
    "local_structure": {"status": "observed", "classification": "deep_sweep_reclaimed", "swing_low": 6.0, "swing_high": 18.0, "retracement": 0.72, "fib_618": 10.584, "latest_close": 11.0},
    "multi_year_drawdown": {"status": "observed", "peak_date": "2022-03-01", "trough_date": "2024-01-02", "max_drawdown": 0.66},
    "monthly_state": {"status": "observed", "completed_through": "2026-12-31"},
    "long_term_state": "uptrend_pullback",
    "supply_risk": {"status": "unavailable"}
  },
  "bias_labels": []
}
```

示例只说明结构，不批准阈值，也不是生产事件。

### 6.4 必填语义

- `schema_version`：只表示合同结构，必须为纯SemVer。
- `source_version.gate_policy`：表示判断政策；不得冒充合同版本。
- `as_of`与`signal_date`：必须相同且是完成交易日。
- `instrument_id`：来自M02点时成员身份；稳定ID不得只靠可复用ticker。
- `input_identity`：把事件绑定到同一股票池、行情内容和M02规范复权政策；其中`adjustment_policy`必须逐字段等于M02实际合同，不得使用`method`简称。
- `path_status`：只能明确为formal或legacy研究；不得隐式回退。
- `baseline_checks`：只放创建边界与现有长期趋势等价检查；不得混入新增研究判断。
- `baseline_passed`与`passed`：两者必须相等，只表示当前`gate_policy_version`的基线结果，不表示买入、排名或生产已经采用。
- `shadow_assessment`：保存新增结构化事实、五态和观察建议；`production_effect`必须是布尔`false`。
- `shadow_assessment.shadow_fact_schema_version`：只表示M03影子事实自身的字段结构，不是未来评分、因子或排行版本。
- `shadow_assessment.long_term_state`：只能取五个冻结值之一；证据不足必须是`unavailable`。
- `event_content_fingerprint`：绑定排除自身字段和`generated_at`等非语义审计时间后的其余规范事件内容；同一完整身份下该指纹变化就是冲突。
- `supersedes_event_id`：仅在合法行情证据修订时指向同一逻辑信号链的直接前一版本；首版为`null`。
- `bias_labels`：formal为空；legacy必须明确列出已知偏差。

### 6.5 M02复权政策直接复用

M03不定义第二套复权政策。`input_identity.adjustment_policy`直接完整嵌入M02的`ADJUSTMENT_POLICY`：

```json
{
  "version": "eodhd-adjusted-ratio-1.0.0",
  "formula": "ratio=adjusted_close/close; adjusted_ohlc=raw_ohlc*ratio"
}
```

字段名、版本和公式语义以`services/market_data/normalization.py::ADJUSTMENT_POLICY`及M02 `MarketDataSnapshot`验证器为唯一事实来源。GateEvent身份使用该完整对象的M01规范JSON表示，不另造`method`、简称或近似映射。任何版本或公式变化都必须先产生新的市场快照身份，再产生新的事件身份；不得把公式变化静默当成兼容字段。

`GateEvent 1.x`缺少该证据，只能通过唯一legacy适配入口显式只读；适配器可以报告`adjustment_policy=unknown`，但不得补造M02政策后交给2.x formal消费者。

### 6.6 稳定ID、幂等与修订链

新ID对以下规范化字段做SHA-256：

```text
schema major
+ instrument_id
+ signal_date
+ gate_policy_version
+ path_status
+ universe_id
+ market_snapshot_id
+ 规范化后的M02 adjustment_policy完整对象
```

输出为`gate:sha256:<digest>`。规范JSON排序、日期、数值和哈希复用M01公共入口。规则：

- **完整事件身份**就是上述全部字段，缺一不可。`market_snapshot_id`或复权政策身份不是说明文字，而是身份的一部分。
- **逻辑信号身份**由`instrument_id + signal_date + gate_policy_version + path_status + universe_id + adjustment_policy`生成，只用于把同一次逻辑信号的行情证据修订串成链，不代替完整事件身份。
- **幂等重放**：完整身份相同、规范语义内容也相同，返回同一个`gate_event_id`和既有不可变记录，不因新的运行时间重写文件。
- **合法证据修订**：逻辑信号身份相同，但M02留下可追溯修订证据并产生不同`market_snapshot_id`；创建新的不可变事件，`supersedes_event_id`必须指向直接前一有效版本。旧事件保留，不删除、不覆盖、不原地修改。
- **真正冲突**：完整身份完全相同，但`event_content_fingerprint`或任何规范语义内容不同；验证器必须失败，不能按输入、文件或生成时间顺序择一。
- `supersedes_event_id`不参与新事件ID计算，但必须指向同一逻辑信号链、禁止循环和跨政策串链；完全相同重放不得创建自我修订。
- 门卫政策升级、股票池身份变化或复权政策变化会产生新的完整事件身份；除明确的数据证据修订外，不得自动声称它替代旧政策结论。
- 正式消费者默认只读取由显式修订链解析出的当前有效版本；审计和历史回放必须能选择并读取任一旧版本及整条链，禁止按“文件最后修改时间”猜当前版本。
- 行情证据修订不得自动改写已经发布的历史生产结果。重新发布、重新回放或替换生产引用必须由后续获批流程控制。
- ticker改变不改变同一上市实体身份；重上市形成新的M02 `instrument_id`。

### 6.7 未形成事件时的扫描审计

未到创建边界的股票只进入每日／回放批次级`GateScanAudit 1.0.0`，不创建逐股失败GateEvent。最小字段冻结为：

- `schema_version`、`as_of`、`generated_at`、`future_data_used=false`；
- `scan_audit_id`、调用层注入的`scan_batch_id`、`gate_policy_version`和`path_status`；
- 可用时保存`universe_id`、`market_snapshot_id`和完整M02 `adjustment_policy`；证据不存在时保存明确`null`与对应失败原因，不能猜值；
- `input_count`、`gate_event_created_count`、`baseline_passed_count`、`baseline_failed_count`；
- `non_event_reason_counts`，至少区分`data_unavailable`、`not_tradable`、`insufficient_history`、`below_price_floor`、`below_liquidity_floor`和`no_exact_daily_macd_cross`；
- `audit_status`与批次级`reason_codes`。formal股票池整体缺失时写`universe_unavailable`，事件数为零。

`scan_audit_id`对`as_of + scan_batch_id + gate_policy_version + path_status + 已存在的输入身份`做规范哈希；相同身份不同计数属于冲突。影子期只允许保存到测试临时目录或被忽略的`work/m03-shadow/scan-audits/`。它不含分数、排名、交易计划，也不进入`public/`。未来生产保存位置必须由后续发布设计批准，M03不预先接入。

## 七、每一道检查负责什么

### 7.1 数据完整／可交易／流动性

负责保存：OHLCV合同有效、查询日存在、历史长度、收盘价、成交额、formal当日资格、暂停／退市等点时状态。第一版影子对照必须保留当前`420`行、`close >= 5`和`close × volume >= 10,000,000`的结果，以证明行为等价；是否改变这些阈值不属于M03。

禁止：下载行情、猜成员、补造listing生命周期、计算因子分。

### 7.2 精确日线MACD刚金叉

只在当日完整收盘满足：

```text
MACD[t] > Signal[t]
且 MACD[t-1] <= Signal[t-1]
```

近5日发生过、接近金叉、周线金叉或柱体改善都只能是其他事实，不能冒充当日门票。该检查应从当前`exact_daily_macd_bull_cross()`迁移并以黄金样本证明逐股一致。

### 7.3 局部波段0.618／70%结构

只使用截止`as_of`已经右侧确认的上一段有效上涨波段，保存pivot索引、确认日、低点、高点、0.618价位、最大回撤和最新完整收盘。

建议状态：

- 回撤不超过0.618：`structure_intact`；
- 0.618—0.70：`deep_pullback_warning`；
- 超过0.70且最新收盘重新站回0.618：`deep_sweep_reclaimed`；
- 超过0.70且未站回0.618：`structure_broken`；
- 没有足够确认波段：`unavailable`。

该结构方向已经写入总需求，但当前生产尚未执行。M03首轮只能作为`shadow_assessment.local_structure`计算并与旧结果并列；`structure_broken`也只能形成影子排除建议，不能把`baseline_passed`改成`false`。若以后希望它改变门卫资格，必须由用户另行审核反例、受影响事件和回退证据，并升级门卫政策；M03设计不替后续模块规定其他生产采用方式。

### 7.4 多年回撤事实

保存点时历史窗口、确认高低点、最大回撤、发生日期、是否已经有足够后续底部消化。它回答“曾经跌多深”，不单独回答“现在能买吗”。

没有实验批准时，多年深跌不得直接改变基线资格或生产输出；MRNA只用于验证事实是否被正确看见。

### 7.5 完整月线与长期状态

- 月线只能由已经结束的自然月组成；月中运行不得把本月临时K线当完整月线。
- 周线同理，只能使用已经结束的交易周。
- 所有pivot必须等足右侧确认K线，`confirmation_date`不得晚于`as_of`。
- 同一证据不足或多状态冲突时返回`unavailable`，不能用优先级硬猜。

五态职责：

| 状态 | 只保存什么事实 | 当前是否可改变生产资格 |
|---|---|---|
| `uptrend_pullback` | 长期上行仍在、局部回调及重新启动证据 | 先与当前`long_trend_ok`行为做影子等价对照；不在本轮切换 |
| `long_base_reversal` | 长期下跌后足够长底部、多次拒绝新低、完整月线转变和日线重启 | 否；必须独立实验批准 |
| `broad_range` | 冻结箱体上下沿、触碰、停留和是否完整收盘脱离 | 否；必须独立实验批准 |
| `structural_damage` | 多年深跌、局部结构破坏及恢复不足等事实 | 否；没有实验批准不得直接改变生产结果 |
| `unavailable` | 长期窗口、完整周期、确认pivot或定义不足 | 影子事实明确不可用；不得猜测，也不得改变已经形成事件的基线结果 |

DLTR式持续供给不塞进五态枚举。它作为独立事实保存：每次向下跳空日期、区间、回补日／未回补、回补失败、新缺口及最近关键缺口控制权。没有匹配对照实验前，它必须保持`production_effect=false`，不能改变基线资格或当前生产输出。

## 八、事实、资格和生产效果必须分开

| 层 | 含义 | M03首轮权限 |
|---|---|---|
| 事实 | 机器在点时数据上测到的数值、日期、pivot、回撤、月线和缺口 | 可以影子生成并测试 |
| 门卫资格 | 某个明确`gate_policy_version`是否通过 | 可以生成影子结果；不得替换生产默认 |
| 下游分析 | 后续模块怎样使用门卫事实 | M03只提供只读GateEvent，不定义下游合同或算法 |
| 排名与交易 | 后续模块的分数、名次、精选、计划、持仓和退出 | M03不负责 |
| 生产采用 | 每日、夜间、网站和Discord实际读取新事件 | 属于以后受控迁移与M12，不由本文授权 |

### 8.1 M03止于GateEvent

M03只保存门卫结论和可以复核的结构事实，不定义后续模块的数据结构、算法或验收矩阵。`gate_policy_version`只负责事件创建边界和`baseline_passed`；`shadow_fact_schema_version`只负责M03影子事实的字段结构。两者都不得被解释成下游因子、选择、排名、交易、留档或收益评价政策。

后续责任只作边界交叉引用：

| 模块 | 责任归属 |
|---|---|
| M04 | 因子注册表和TechnicalEvidence |
| M05 | 两个选股器及技术优先级 |
| M06 | 大盘、行业和热度上下文 |
| M07 | 唯一复杂多因子排行榜与交易就绪判断 |
| M08 | 入场、止损、目标、持仓和退出 |
| M09 | 一本OpportunityEvent总账及后续结果追加 |
| M10 | 历史重放、实验、前向评价和人工复盘 |
| M12 | 真实工作流、Manifest、网站、Discord、部署及回退 |

M03不依赖上述模块完成就能独立验收，也不替它们提前设计合同。唯一兼容原则是：**GateEvent保存不可变、点时、版本化的门卫结论和结构事实，供后续模块只读引用。后续评分、排名、交易、留档和收益结果不得反向修改GateEvent。**

## 九、下游消费者怎样共享同一GateEvent

目标状态：

- 后续复杂多因子消费者只能接收唯一`gate_event_id`，不得再调用`long_trend_ok()`或自算MACD门票；
- 后续个人形态消费者只能引用同一股票同一天的GateEvent事实，不得创建第二个门卫ID；
- 两者具体怎样分析和保存结果属于M05及其后模块，M03不定义其下游合同；
- 任何下游结果都不得反向修改GateEvent或创建第二套门卫。

当前个人形态能观察没有当日MACD刚金叉的标的，这与“两个分析器只消费同一门票”存在真实兼容差异。M03不能偷偷改变个人形态产量。推荐做法是：M03只为到达精确MACD创建边界的候选生成GateEvent；个人形态旧观察在M05迁移前保持legacy。M05再由用户决定是否只消费`baseline_passed=true`事件，或也观察已经形成事件但`baseline_passed=false`的MACD候选。没有MACD事件的股票只有批次级扫描原因计数，不能伪造逐股失败GateEvent供个人形态引用。无论选择哪一种，都不能新建第二套门卫。

## 十、失败关闭语义

以下任一前置情况发生时，formal扫描必须失败或记录非事件原因，不能创建完整GateEvent，也不能降级猜测：

- 当日formal股票池不存在、冲突或资格证据不完整；
- 行情日期、`as_of`、股票池或行情快照身份不一致；
- OHLCV无效、乱序、重复、含未来行或内容指纹不符；
- 查询日不是最新返回的完成交易日；
- 精确MACD所需历史不足；
- 未知合同主版本、未知门卫政策或稳定ID冲突；
- legacy数据试图进入formal选择器。

上述失败必须进入`GateScanAudit`机器可读原因码，例如`universe_unavailable`、`insufficient_history`、`identity_mismatch`，但不得伪造一个`passed=false`来掩盖“根本没有形成事件”。

事件创建以后，新增结构或长期观察若遇到`incomplete_month`、`unconfirmed_pivot`或长期窗口不足，只能把对应`shadow_assessment`字段写成`unavailable`并保存原因；它们不能删除事件或改变`baseline_passed`。只有当前既有`legacy_long_trend_equivalence`失败时，才可按已冻结基线语义得到`baseline_passed=false`。

## 十一、当前生产如何保持不变

M03实施若获批准，第一阶段仍必须是影子：

1. 保留`factor_snapshot`、`unified_v2_scan`、Tracker、稀有机会和个人形态默认入口原样运行；
2. 只向测试临时目录或被忽略的`work/m03-shadow/`写影子事件；
3. 用相同注入小样本对比当前门票、M03事件和每日／回测结果；
4. 任何无法解释的候选差异立即停止，不改旧输出迎合新代码；
5. 未经后续批准，不写`public/`、`automation/`、事件账或生产Manifest；
6. 单个消费者迁移失败时，删除其影子调用即可回退，旧生产链不动。

历史1.x GateEvent、旧因子快照、信号史和机会账本全部只读保留。新事件只追加，不回写、不补造旧字段。

## 十二、影响与不影响矩阵

| 模块 | 设计影响 | 本轮实际影响 | 以后迁移边界 |
|---|---|---|---|
| M01合同 | 设计新增GateEvent 2.x | 无代码变化 | 保留1.x只读，2.x未知主版本失败关闭 |
| M02行情／股票池 | 作为唯一formal输入 | 无代码变化 | formal缺失失败，legacy显式偏差 |
| 每日扫描 | 未来读取唯一门卫 | 默认结果不变 | 先影子、逐候选对照，再单独切换 |
| 夜间回测 | 未来读取同一门卫 | 断点和历史结果不变 | formal缺历史股票池失败；legacy研究显式启用 |
| M04因子证据 | 未来只读引用GateEvent | 无变化 | 因子注册表和TechnicalEvidence由M04设计 |
| M05两个选股器 | 未来引用同一事件身份 | 无变化 | 技术优先级和个人形态兼容由M05批准 |
| M06—M10 | 只读消费M03事实 | 无变化 | 各模块分别负责上下文、排行、交易、总账和评价；M03不设计其合同 |
| 网站／Discord | 将来只展示紧凑门卫解释 | 无变化 | 生产同源发布属于M12 |
| 止损／持仓／退出 | 无职责 | 无变化 | 留给对应后续模块 |

## 十三、四个人工案例的检测走查

这些走查只验证“机器是否在当时看见并如实解释”，不评价收益、不建立生产排除规则。精确数字必须在未来用统一复权、点时行情重新核验；当前只保存已有案例账事实。

### 13.1 CGEM｜长期筑底候选

预期路径：

```text
2024-04-17点时输入
→ 只允许使用截至当日完成日线、截至2024-03-31完成月线
→ 检查当日精确MACD
→ 保存2022年以来底部时长、多次拒绝新低和完整月线转变事实
→ shadow_assessment可能分类long_base_reversal；证据不足则unavailable
→ 不使用04-19至04-24后来出现的更高第二底、吞没、突破和跟随美化04-17
```

人工检查重点：04-17早期机器事件与04-22／24结构确认必须分开。即使影子检测为`long_base_reversal`，也只是假设候选，不改变`baseline_passed`或当前生产输出。

### 13.2 MRNA｜深跌／结构破坏

预期路径：

```text
2024-04-24点时输入
→ 只使用截至2024-03-31完成月线
→ 保存2021高点至2023低点接近90%回撤事实
→ 检查局部回撤是否超过70%及是否重新站回冻结0.618
→ shadow_assessment预期识别structural_damage或在证据不足时unavailable
→ 不使用2024-04-30才完整的月线，也不因信号日之后的走势倒改判断
```

人工检查重点：机器必须看见多年深跌和点时月线边界；该案例不能单独批准生产硬否决。

### 13.3 BTDR｜宽幅箱体

预期路径：

```text
2024-03-15点时输入
→ 当日精确MACD与局部看多事实可成立
→ 冻结当时可见的箱体上下沿、触碰和停留证据
→ 检查收盘是否真正脱离箱体
→ shadow_assessment预期识别broad_range；定义或证据不足则unavailable
→ 不使用2024-06-12附近后来的突破尝试解释3月信号
```

人工检查重点：箱体内部反弹不能被解释为趋势突破；在独立批准前也不能直接改变当前生产输出。

### 13.4 DLTR｜持续供给风险

预期路径：

```text
2024-04-01点时输入
→ 保存截至当日已经发生的每次向下跳空
→ 逐一记录是否回补、回补失败、回补后再出新缺口
→ 保存最近关键缺口是否收复
→ 长期五态按独立结构证据分类；供给链作为独立事实附着
→ 不把多个相关缺口机械重复计算，也不把一个布尔值当完整故事
```

人工检查重点：案例账中的具体日期先逐项核验；持续供给在匹配对照前保持`production_effect=false`，不改变基线资格或当前生产输出。

## 十四、自动测试设计

### 14.1 合同和身份

- GateEvent 1.x继续只读验证，2.x按新合同验证；未知主版本失败；
- GateEvent 1.x不得通过字段补造进入2.x formal消费者；
- 缺`instrument_id`、完整输入身份、基线检查、影子结构或明确偏差时失败；
- 相同完整输入重复生成相同ID和内容；字段顺序与`PYTHONHASHSEED`不影响ID；
- 同一逻辑信号的`market_snapshot_id`合法修订产生新ID、建立`supersedes_event_id`链并保留旧事件；
- 完整身份相同但内容不同报“门卫事件冲突”；
- 门卫或复权政策变化产生新ID且保留旧事件；
- GateEvent中的复权对象必须与M02 `ADJUSTMENT_POLICY`逐字段相同；
- 旧JSON适配前后字节完全不变。

### 14.2 点时和完整周期

- 所有读取强制`as_of`，返回行不晚于`as_of`；
- 未结束月线、周线不能进入高周期状态；
- pivot在右侧确认前不可见，确认后最早从确认日使用；
- 截止日后的坏数据不能反向阻断更早安全读取；
- 未来行情、身份元数据或今天股票池不能进入历史事件。

### 14.3 门卫顺序和失败关闭

- 数据不完整、不可交易、流动性不足或无精确MACD时不创建GateEvent，只增加扫描审计原因计数；
- 近5日金叉、接近金叉和周线金叉不能冒充当日精确金叉或创建事件；
- formal股票池缺失返回`universe_unavailable`，不回退legacy；
- legacy必须有偏差标签，formal选择器拒绝legacy；
- 事件形成后，局部波段不足、长期窗口不足或状态冲突只让影子字段返回`unavailable`；
- `shadow_assessment.production_effect`只接受布尔`false`；
- 未经批准的长期状态、结构和供给事实不改变`baseline_passed`或旧生产结果。

### 14.4 消费者与兼容

- 复杂多因子和个人形态不能生成第二个`gate_event_id`；
- 每日与回测对同一`universe_id + market_snapshot_id + as_of + policy`得到同一事件；
- 当前精确MACD、价格、成交额和旧长期趋势结果在固定小样本逐项对照；
- 2026-08-28 formal明确失败，legacy对照显式带偏差；
- 旧生产默认入口、公开JSON、断点、网站和Discord在影子期逐字节不变；
- CGEM、MRNA、BTDR、DLTR正反例只能验检测和解释，不能被阈值调优测试当收益样本。

### 14.5 机械可验证验收矩阵

| ID | 固定输入／动作 | 必须结果 |
|---|---|---|
| M03-A01 | 当日没有精确日线MACD刚金叉 | 不创建完整GateEvent；`GateScanAudit.non_event_reason_counts.no_exact_daily_macd_cross`增加 |
| M03-A02 | 已形成MACD事件，分别给出`long_base_reversal`、`structural_damage`或`structure_broken`影子观察 | `baseline_passed`和`passed`保持原基线结果，生产候选集合不变 |
| M03-A03 | `shadow_assessment.production_effect`为`true`、字符串或缺失 | 合同失败；只接受布尔`false` |
| M03-A04 | formal股票池缺失而legacy样本存在 | 返回`universe_unavailable`，不自动回退legacy |
| M03-A05 | 月中或周中运行 | 仅使用上一完整自然月／完整交易周，未完成周期不进入事实 |
| M03-A06 | pivot右侧确认日晚于`as_of` | pivot不可见；相应影子事实为`unavailable` |
| M03-A07 | 完整身份和规范内容完全相同，重复运行 | 事件ID、内容指纹和持久化字节相同，不新增修订 |
| M03-A08 | 同一逻辑信号有可追溯行情修订，`market_snapshot_id`变化 | 生成新不可变事件，`supersedes_event_id`指向旧事件，旧事件仍可读 |
| M03-A09 | 完整身份完全相同但任一规范语义内容变化 | 验证器报“门卫事件冲突”并失败关闭 |
| M03-A10 | GateEvent使用`method`简称、错误公式或错误版本 | formal验证失败；只有M02完整`version + formula`对象通过 |
| M03-A11 | GateEvent 1.x尝试进入2.x formal消费者 | 明确拒绝；只能走legacy只读入口，不能补造复权或输入身份 |
| M03-A12 | 走查CGEM、MRNA、BTDR、DLTR | 每例只使用信号日及以前完成周期；改变信号日之后数据不得改变当日判断 |
| M03-A13 | `PYTHONHASHSEED=0/1/42/12345`重复同一规范输入 | `scan_audit_id`、`logical_signal_id`、`gate_event_id`和内容指纹完全相同 |
| M03-A14 | 执行全部M03影子验收 | 当前每日、夜间、网站、Discord、工作流和公开JSON默认路径与字节不变 |

## 十五、人工验收清单

1. 人工逐字段检查一个formal GateEvent的行情、股票池、复权和政策身份。
2. 人工检查一个没有精确当日MACD金叉的标的不会生成候选GateEvent，只在`GateScanAudit`留下原因计数。
3. 人工检查一个`structure_broken`观察仍保留在`shadow_assessment`，但`production_effect=false`且不改变基线结果。
4. 人工检查一个行情修订样本形成两条不可变事件和可追溯修订链；旧事件仍可读取。
5. 用同一固定样本比较每日和回测事件ID与事实完全相同。
6. 分别按第十三节走查CGEM、MRNA、BTDR和DLTR，确认没有使用案例日之后的数据。
7. 比较影子运行前后所有当前生产JSON哈希，必须不变。
8. 核对长期状态和供给事实没有改变`baseline_passed`或任何当前生产输出。

## 十六、版本迁移与回退

迁移规则：

- `GateEvent 1.x`：历史只读，缺失新字段显示`unknown`或明确不可用，不补造；不得进入2.x formal消费者；
- `GateEvent 2.x`：M03完整事件；只有已知2.x次版本可兼容；
- 新增可选解释字段升级次版本；
- 新增必填字段、改变`baseline_passed`／`passed`含义、稳定ID算法或影子事实结构语义升级主版本；
- M02复权政策版本或公式变化必须形成新的市场快照和事件身份，不能靠GateEvent次版本静默吸收；
- 所有消费者调用同一适配入口，禁止每日、回测和页面各写转换器。

回退分三层：

1. 纯函数或合同失败：撤回对应M03小包，旧生产不受影响；
2. 影子消费者差异：停用该影子入口，保存差异证据，不改旧输出；
3. 未来生产切换异常：由受控发布包恢复旧消费者和旧Manifest；M03本身不执行部署回退。

## 十七、未来实施小包（每包预计不超过20分钟）

这些是计划，不授权实施：

1. **包A｜规则与GateEvent 2.x合同冻结**：经用户确认后更新因子规则，增加创建边界、`GateScanAudit`、基线／影子语义、修订链、M02复权复用和1.x只读兼容测试。
2. **包B｜精确日线门票等价迁移**：抽取数据／流动性／精确MACD纯函数，用固定小样本证明与`factor_snapshot`一致。
3. **包C｜局部0.618／70%结构事实**：复用已确认pivot，加入边界和防未来反例，只写影子事实。
4. **包D｜多年回撤与完整月线五态**：实现事实检测和`unavailable`语义，不接生产资格。
5. **包E｜唯一GateEvent生产者**：组合M01合同与M02输入；幂等、行情修订链、真正冲突、formal／legacy测试。
6. **包F｜每日影子迁移**：`factor_snapshot`只加影子调用，对照旧结果，不改默认输出。
7. **包G｜回测影子迁移**：`unified_v2_scan`只加影子入口；formal缺失失败、legacy显式偏差，不运行真实多年回测。
8. **包H｜消费者与四案例验收**：验证后续消费者不复制门卫，完成人工案例的点时检测说明；不接入或设计下游模块。
9. **包I｜本地验收与证据**：完整测试、编译、前端回归、确定性和补丁检查，形成独立验收报告；不部署。

任何小包若需要修改工作流、公开JSON、生产默认入口、评分或交易规则，必须停止并重新申请范围。

### 17.1 包H机械消费者清单（本地影子验收口径）

以下旧模块仍含门票、长期资格或近似MACD判断。它们是迁移清单，不代表已切换，也不是允许删除旧逻辑的授权：

- `factor_snapshot.py`：默认生产仍按旧快照流程运行；新增入口只做M03影子对照；
- `unified_v2_scan.py`：默认回放与排名路径不变；新增入口只调用同一M03影子生产器；
- `factor_detectors.py`、`factor_effectiveness.py`、`macd_factor_backtest.py`、`rare_opportunity_scanner.py`：仍属旧因子／研究门票消费者；
- `resonance_tracker.py`、`theme_etf_context.py`：仍保留各自高周期或上下文MACD语义，不得冒充M03精确日线门票；
- `favorite_pattern_tracker.py`：兼容迁移明确留给M05，M03不改变当前观察产量。

`tests/test_m03_gate_consumer_inventory.py`机械搜索冻结标记；新增或遗漏旧消费者会令测试失败，必须在其所属模块获批后更新清单。唯一身份创建器同时机械冻结为`services/gates/producer.py`。

## 十八、风险与未决选择

### 风险

- 当前长期资格只是EMA200简化条件；直接替换会改变候选池。
- 0.618／70%必须绑定正确、已确认的局部上涨波段；选错波段会制造假精确。
- 长期状态定义过宽会让同一事实同时命中筑底、箱体和破坏；冲突必须返回`unavailable`。
- 2026-08-28及更早缺formal股票池，无法做全市场正式历史等价验收。
- 个人形态当前非MACD观察与未来共同门票存在真实语义差异，不能在M03中偷偷解决。
- 四个已见案例容易造成过拟合，必须与未参与定义的样本分开。

### 已冻结选择与后续边界

1. **唯一模块位置**：已确认使用`services/gates/`，作为M01合同和M02数据之上的中立层；不放进扫描器或回测器。
2. **个人形态兼容**：已确认延后M05。本次保持当前个人形态默认行为，不在M03选择共同门票消费方式。

事件创建边界、影子`production_effect=false`、行情修订链和M02复权复用已作为本次设计修订的合同结论，不再列作开放选择。后续模块的具体数据结构、算法和生产启用不属于M03选择。

## 十九、完成定义

M03已在获批范围完成A— I、独立审计修复、固定本地案例边界、完整测试、代码与证据提交，并通过纯fast-forward进入`main`，因此在获批影子范围记为`implemented`。真实CGEM／MRNA／BTDR／DLTR全历史行情不在本地，验收没有伪造它们的OHLCV，也没有把合成固定样本当成收益证明。进入`main`不表示生产采用，仍必须明确写明“未部署、未启用”。

当前结论：**M03在获批影子范围为`implemented`，最终main提交为`d02b03295a5e37cebeb788bc780fbede67e574a0`；尚未部署或生产启用。正式每日扫描、夜间回测、网站、Discord、工作流和公开JSON均未切换；M04与M12均未开始。**
