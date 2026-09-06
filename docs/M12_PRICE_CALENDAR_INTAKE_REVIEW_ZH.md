# M12｜价格、日历与上市区间接入细化卡

版本：`0.2`；日期：2026-09-07；状态：`design_review`。

关联CR-053及[已批准v0.2.1设计](M12_PRODUCTION_CHAIN_MINIMAL_DESIGN_ZH.md)。本卡纠正来源前提并提出接法，尚未批准价格接入实施；已批准的成员登记接线可继续，不将整个M12退回未批准状态。审核后判断是否涉及AGENTS要求的新设计批准。没有真实供应商请求、读取账户密钥、购买数据、添加依赖、创建云资源或启用生产。

## 1. 结论与唯一推荐

继续使用现有EODHD集成，先核实既有账户可用且获准用途的资料，再实现唯一M02取证入口。候选组合为：v2当前年交易所资料、v1明确历史区间资料、按证券身份限定区间的EOD原始价格；General资料只能辅助核对上市身份。依据是复用现有供应商与复权规则，避免新源、新依赖和第二套行情算法。

**目前没有已取得并验证的完整日历／价格覆盖／重上市原件，不能声称该组合已足够运行formal。** 当前年日历不足以单独覆盖420个交易日；历史资料的提前收盘、临时休市及五个范围内交易所对应关系仍需实证。若既有权益与材料不能补齐，正式日保持unavailable，交回一个具体缺项，不擅自换源、购买或缩小原股票池。

## 2. 只读盘点：已经知道与尚未知道

| 对象 | 可核实事实 | 尚未取得的证明 |
| --- | --- | --- |
| 旧生产参考日 | `services/scanner/eodhd.py:latest_reference_day`取SPY最近有效bar最大日期；旧每日入口调用它 | 不能证明所有交易所完整会话、当天实际收盘、临时休市或供应商已完成全市场更新 |
| 旧价格入口 | `prices`使用EOD路径，默认起点2000年；M02已有原复权、修订及截止D读取 | 默认区间、有效行或指纹均不证明该listing历史连续或供应商返回完整 |
| 当前成员身份 | 原始同日列表给出代码、交易所及可选ISIN；连续成功观察形成epoch | 首次观察不是IPO，名称、当前ISIN及当前active状态不能证明重上市或历史代码复用 |
| 现有资格接点 | `build_same_day_qualifications`要求可信完整性输入，沿用420日、5美元、1000万美元 | `complete_history_instruments`不是外部许可，也不能直接填成员全集；真实取证尚未接入 |
| 账户与运行 | 固定daily运行配置仍禁用；仓库保留EODHD集成代码 | 未核验账户套餐、端点实际权限、私有留存及公开衍生展示用途；有token不等于许可证明 |

公共文档核读于2026-09-07，链接内容可能更新，以下只证明文档声明，不证明本账户已能取得资料：

- [EODHD交易时间／假日](https://eodhd.com/financial-apis/exchanges-api-trading-hours-and-stock-market-holidays)：v2提供`data.Timezone`、`TradingHours`及`ExchangeHolidays`（含`EarlyClose`时刻），声明完整日历限当前年；v1接受`from/to`历史范围。文档列有All-In-One和EOD+Intraday — All World Extended计划。示例US聚合名称不能自行证明原五类交易所的全部历史适用范围。
- [EODHD日线](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes)：EOD端点接受`from/to`、`period=d`、`order=a`，返回`date/open/high/low/close/adjusted_close/volume`。所列参数没有分页项；“没列分页”不能代替真实返回完整性验证。
- [EODHD基本资料](https://eodhd.com/financial-apis/stock-etfs-fundamental-data-feeds)：General含`Code/Exchange/ISIN/PrimaryTicker/IPODate`，IPODate描述首次公开发行日期；文档列All-In-One和Fundamentals Data Feed计划。未找到足以证明当前listing完整起止及重上市的字段合同，不能把IPODate直接当本次上市起点。

## 3. 待审输入、输出及归档边界

唯一负责人：M02价格／日历来源取证；M12仅在原认证准备会话和租约下调度、读回原件并保存结果。业务复权继续`eodhd-adjusted-ratio-1.0.0`，Universe继续原3.x及唯一合同验证入口；不在页面、M03或任务消费者另算完整性。

| 材料 | 推荐请求与区间 | 必须归档、绑定和核验 |
| --- | --- | --- |
| 会话材料 | `api/v2/exchange-details/US?fmt=json`用于当前年；`api/exchange-details/US?fmt=json&from=S&to=D`用于明确历史范围。S来自所需回看区间，不能从SPY行数猜 | 实际响应原字节、端点版本、UTC采集时间、状态、长度／EOF、内容哈希；有效覆盖起止、市场／交易所映射证据、时区及常规开闭市、假日和提前收盘。历史范围不因请求参数存在就视作覆盖已证 |
| 价格材料 | `api/eod/{provider_code}.US?fmt=json&period=d&order=a&from=S&to=D`；只允许从已核验成员映射构造代码。短历史路径的S受已证listing起点约束 | 绑定instrument_id、provider／market／exchange／provider_code／epoch、原成员证据及历史身份映射；保存全部原始返回及请求区间、实际首末日／行数、复权版本／修订引用。绝不把前一同名listing的价格拼进当前身份 |
| 上市区间材料 | 若既有账户授权可取得，v1.1 fundamentals的General作为辅助；确切listing起点／重上市来源当前未知 | 实际原件须明确证券与市场身份、上市生效区间及代码／交易所变更关联。IPODate、首次观察、首根bar、名称或“已返回少于420行”单独均不构成起点证明 |
| 获取许可 | 复用既有当前授权和固定许可归档设计，分别核对本次数据种类及用途 | 私有采集／存储／研究与公开衍生展示分开；保存既有权益证明、许可原件及期限，不将成员许可扩展到日历或fundamentals，不使用FinanceDatabase MIT代替EODHD许可 |

以上是待实施的内部证据要求，不冒充供应商字段或已发布新合同。原件以现有私有不可变归档存储，保存实际字节sha256和size_bytes；请求记录移除token，密钥不进入文件或错误。文档／政策版本与取得时间另存来源说明，不能只存可变网页URL。修订追加新原件及来源关系，不覆盖原价格／日历，也不重写冻结信号。

输出给原资格入口的是每个listing在所需窗口的可核验覆盖事实及对应RepositoryRead，或明确unavailable；源证明通过后才形成内部完整性集合。至少420日路径只证明本次计算实际需要的回看窗口，不增加无关全生命周期要求；原模型若要求更长预热则取其所需窗口，不改原算法或用420行截断其输入。该接法及证据合同须本卡复核后再实施。

## 4. 完整性与不可用判定

1. 日历必须先有适用于该交易所和年份的已证材料，才能枚举会话。核对时区／夏令时、常规交易周、节假日、历史提前收盘和临时休市；不能固定每个工作日或统一16:00，不能由有无SPY bar构造日历。v2当前年与v1历史重叠冲突时停止，不任选一个覆盖。
2. 价格只覆盖截止D且属于同一listing的范围。HTTP成功、完整JSON、实际EOF、声明长度、唯一有序日期及所有预期会话逐日匹配一起验证；如果实际出现分页、截断、限额或未知字段语义，停止并保留原件，不能称“已取完整”。逐段获取时每段与拼接边界均要证明，不能漏页后按行数放行。
3. ≥420个完整会话且相关窗口价格逐日有效，才交原资格规则判断。窗口中的同名代码历史仍须身份对应证据，但不要求证明更早无关生命周期。旧epoch只定义观察身份，不能擅自作为价格起点，也不能自动授权读取任意更早历史。
4. <420只有在当前listing历史起点已被原件证明、从起点至D的全部应有会话及价格完整时，才允许原规则写`insufficient_history`。缺日须逐项保留原因与来源：正式休市由日历解释；停牌、上市前、退市后等必须有相应身份／事件证据。供应商遗漏或原因未知保持unavailable；不补零、不前填、不把停牌改成市场休市，也不自行改变原OHLCV有效性门槛。
5. 任一成员资格未知则原formal日失败，保留原完整页面；不能静默删除该成员使剩余集合成功。此卡不阻止已获准的成员原件登记或旧冻结链条继续处理已有合法材料。后续跨日M08／M10若所需价格不足仍沿原重试／页面滞后边界，不拿该缺口重建旧信号。

## 5. 短样例与验收（要求，尚未执行）

| 输入情形 | 必须得到的结果 |
| --- | --- |
| 同一listing所需420会话、实际价格、历史身份映射和日历原件完整 | 完整性通过，再交原门槛；不要求该listing更早所有价格 |
| 返回419行，没有当前listing起点证明 | unavailable；不能写“上市不足420日” |
| 已证当前listing从S上市，S至D共100会话全部完整 | 原资格明确排除insufficient_history，不补造420行 |
| v2仅当前年，420窗口跨年而历史提前收盘／临时休市无法核实 | 日历覆盖unavailable，不能借SPY或v1请求区间自证 |
| 价格少一天，供应商说明暂停交易但不满足原有效行情合同 | 保留暂停交易原件和不可用原因，不填充或绕过原合同 |
| 候选代码与旧listing同名，只有IPODate或名称相似 | 历史身份未知；不合并、不猜重上市 |
| 权限到期、原件丢失、日历冲突或响应截断 | 失败关闭，保持旧发布指针；现有成功原件／账本不删除 |

验收覆盖上述正反例、逐段边界／未知分页、正常与提前收盘时区、取证后撤权、原件修订及完整股票池失败关闭；真实端点演练须另有相应授权，不以合成测试冒充实际源覆盖。

## 6. 分包、迁移与回退

本卡无价格代码修改。复核后按每包≤20分钟拆分：先固定获证原件及唯一覆盖合同；再接获准范围的原字节取得／归档；最后将已证覆盖交原M02资格及Universe入口并完成定点联测。每包先登记规则／版本再写代码。实际授权／材料仍缺时不能通过把集合填满来继续；是否加入其他来源或改变业务边界须重新设计批准。

旧SPY参考日、旧每日／夜间入口及断点保持；新接点默认禁用，取消新接点可回退，保留不可变原件及日志。M11不重审，CR-043 captured；本卡不授权main合并、部署、生产启用、通知、策略优化或M13。


## 7. v0.2最小实证方案（待最终批准，尚未执行）

v0.1来源方向获审核认可，未获完整价格入口实施批准。本节把无法从公开资料解决的部分收敛为一次有限取证；已有成员登记继续，不等待本卡。目的仅核实可取得的原件与用途范围，不运行全池价格扫描或上线。

### 字段接法与五个来源标签

日历解析按端点版本分开：v2取`data.Timezone/TradingHours`与日期键假日；v1取顶层同名字段、`ExchangeHolidays.*.Date`。后者不是v2日期键格式，历史提前收盘字段仍未获确认，不猜补。输出内部会话表按交易所、日期、当地开闭市、UTC闭市、状态及原件引用记录；时间转换使用现有Python标准库时区，不装新日历库。`Bank`不自动等于股票休市，未知类型或该市场适用性不明失败关闭。[供应商字段说明](https://eodhd.com/financial-apis/exchanges-api-trading-hours-and-stock-market-holidays)

下表是待证映射，**不是把已有证券exchange字段改名或合并identity**：

| 原成员Exchange标签 | 外部实体线索 | 升格为可用日历映射仍须取得 |
| --- | --- | --- |
| NASDAQ | SEC列有The Nasdaq Stock Market，供应商US示例提及NASDAQ | 该US会话原件适用于所需年份及该成员标签的供应商范围说明 |
| NYSE | SEC列有New York Stock Exchange，供应商US示例提及NYSE | 同上；不能从标题推出临时休市历史全部包含 |
| AMEX | SEC把American Stock Exchange列为现NYSE American前身 | 供应商当前AMEX标签究竟如何映射，以及生效期；不是单凭旧名称归并 |
| NYSE MKT | SEC把NYSE MKT列为NYSE American旧称 | 供应商这个标签的有效期／现行语义；与AMEX标签同时出现时不得改写既有身份 |
| NYSE ARCA | SEC单列NYSE Arca | 供应商US聚合日历是否覆盖该场所、相应年份及例外会话 |

实体线索来自[SEC全国交易所列表](https://www.sec.gov/about/divisions-offices/division-trading-markets/national-securities-exchanges)。[EODHD列表文档](https://eodhd.com/financial-apis/exchanges-api-list-of-tickers-and-trading-hours)列明可直接查询NYSE、NASDAQ、NYSE MKT等venue；这不证明其exchange-details支持相同别名或覆盖全部五标签。[NYSE官方交易时间页](https://www.nyse.com/trade/hours-calendars)可作公开交叉核对，不能自动取代供应商历史覆盖证据。本轮仅阅读这些公开页面，不新增它们为生产数据源。

### 一次取证的前置材料、请求上限及判定

先从用户已持有且明确授权检查的材料取得：账户套餐／剩余额度及有效期、允许私有研究和留存的许可、适用的端点范围说明。公开衍生展示权限独立记未知，不用私有取证批准代替上线卡。当前没有这些已核实材料；不读取密钥试探、不调用账户API、不联系供应商或购买套餐。若需要供应商书面范围／listing证据，先整理请求内容交用户批准后才可对外发送。

拟议API取证至多7次HTTP GET、无自动重试；实际执行前把D、S与两只样本证券的既有身份材料和具体URL冻结为取证清单。D取已留存的目标成员来源日；S取D减800个自然日作为有限探测范围（不是420会话证明）。没有已获准的同日成员原件，则此价格探测不启动，不追加成员抓取权限。

| 数量上限 | 固定端点和参数（省略密钥） | 要解决的唯一问题／成功标准 |
| --- | --- | --- |
| 1 | `/api/v2/exchange-details?fmt=json` | 实際支持代码包含US；不试探猜测的别名端点 |
| 1 | `/api/v2/exchange-details/US?fmt=json` | 当前年原件字段／例外时刻符合文档，且来源适用范围有依据 |
| 1 | `/api/exchange-details/US?fmt=json&from=S&to=D` | 所需历史是否真正可取；逐年覆盖和例外事件须有材料支持，与v2重叠部分无冲突；不足时到此停止，不能扩大查询直到“凑够” |
| 至多2 | `/api/v1.1/fundamentals/{code}.US?filter=General` | 核对两个已冻结样本的代码／交易所／ISIN／PrimaryTicker／IPODate，仅辅助；无完整listing证据则短历史路径保持未知 |
| 至多2 | `/api/eod/{code}.US?fmt=json&period=d&order=a&from=S&to=D` | 仅对已有区间身份证明的样本取得原件，与已证会话逐日比对；短历史样本S改为已证listing起点。无起点证明不发短历史请求 |

样本由实施者从已授权成员原件中按稳定代码顺序选取：一只有所需窗口身份连续证明的样本，另选一只有明确近期listing起点证据的样本；找不到后一类就少做相应请求并记录缺口，不让用户挑股票，也不拿名称或IPODate猜起点。该小样本仅用于验证材料接法，不能证明全成员范围完整，更不构成策略实验。

额度估算依据三份官方接口页：日历每请求按5个API额度、General每请求10个、日线每请求1个计，7次HTTP合计最多37个额度；计费单位不是HTTP次数。此估算须在执行前与实际既有权益核对；不允许自动超额或加购。货币支出上限建议为新增0：仅当既有套餐覆盖且无额外费用时执行，否则停止，不能承诺现有账户一定免费。[日历额度](https://eodhd.com/financial-apis/exchanges-api-trading-hours-and-stock-market-holidays)、[General额度](https://eodhd.com/financial-apis/stock-etfs-fundamental-data-feeds)、[日线额度](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes)

每次保存去密钥请求、实际状态／字节长度／EOF／起止时间、原始响应与hash，并出一张“已证／缺证／冲突”表。五标签映射、历史提前收盘／临时休市范围、上市区间三类缺项不能由小样本推断补齐。若供应商现有材料无法证明，方案结果就是明确不足，价格入口继续unavailable；再就具体新来源／权益或规则调整提交设计，不自动扩大本取证单。此处未执行取证，也不要求现在批准部署。
