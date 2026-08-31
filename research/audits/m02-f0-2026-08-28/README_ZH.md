# M02 F0｜2026-08-28 股票池证据恢复审计

状态：**完成，负结果永久保存**。本目录只保存小型审计摘要与匿名化文件哈希，不保存完整行情、完整成员名单或原始`active-common`。

## 1. 审计目标与结论

F0检查2026-08-28生产运行留下的Git、GitHub Actions与缓存证据，判断能否恢复当时完整、可点时复核的股票池成员及逐只资格事实。

结论只能是`universe_unavailable`：

- `1337`是资格筛选后的合格数量，不是筛选前完整股票池成员总数。
- 31只MACD触发股票不是完整股票池，也不是全部纳入／排除结果。
- 两个缓存中的`active-common`各有6324条记录，但listing生命周期字段覆盖为`0/6324`。
- `active-common`只有6060条带ISIN，264条缺少该稳定身份字段；`Code`和`Exchange`不能补造缺失的listing生命周期。
- 缓存没有当日bulk输入、权威完整成员来源和全部成员的同日纳入／排除结果。

因此这些证据既不能支持`formal + complete`，也不能安全支持`legacy_observed`。没有生成`UniverseSnapshot`，也不得从1337计数、31只触发股票、缓存文件名或今天名单倒填历史成员。

## 2. 来源链

- 原始EOD运行：[33293559230](https://github.com/327979420/sage-vista/actions/runs/33293559230)。它以`a5f155fa3c2ea39e7f700d1bb022823f6f95edf8`为运行提交，并生成数据提交`dc9bc681f3b1cd4d882312d3bd1009ab69565bf2`。
- F0B1一次性审计运行：[33398109373](https://github.com/327979420/sage-vista/actions/runs/33398109373)，attempt 1，结果为成功。
- 审计工作流提交：`2695ef3124e1d373088b65fdc149179b3f573bc5`。
- 一次性工作流清理提交：`a319abe8a4ead7363156de0687019bf367690212`。清理后`main`文件树与审计前一致。
- 输入缓存键：`eodhd-history-v1-33266737215`。
- 输出缓存键：`eodhd-history-v1-33293559230`。
- Artifact：输入摘要`9760122119`、输出摘要`9760122163`、合并摘要`9760127793`。

两个缓存均由`actions/cache/restore@v4`使用完整键精确命中，没有使用`restore-keys`，也没有保存新缓存。两个缓存分别在隔离runner中恢复；没有检出或执行缓存中的代码，没有读取secret，也没有访问EODHD。

## 3. 保存的原始小型证据

下列5份文件从系统临时审计目录逐字节复制，未重新生成、规范化或改写：

| 文件 | 字节数 | SHA-256 |
| --- | ---: | --- |
| [`input-summary.json`](input-summary.json) | 1693 | `98d72b74d1651c4cbce1b1726b405eb64bf3962b568d17475469872c6492404b` |
| [`output-summary.json`](output-summary.json) | 1694 | `07a42b37f60afea658ff36958308baca14da76d1b861a9a72ab7091d23cbd0c9` |
| [`comparison.json`](comparison.json) | 420 | `c86e527d111f67ad57d915dfcd9fcee7e7c98b00faefa57b2a9387a0ba1f40a1` |
| [`input-market-file-hashes.jsonl`](input-market-file-hashes.jsonl) | 290360 | `1eb21752ae912df5bf8549f0eb7d1acd251dee8660a9bbf271aa1b2385e3883c` |
| [`output-market-file-hashes.jsonl`](output-market-file-hashes.jsonl) | 291120 | `1721f631c02c51db040654f8eaffd19503424d467ee51f678d45390a442b8c20` |

5份原始证据合计585287字节。两份JSONL清单的每一行只能包含：

- `path_token_sha256`：规范化相对路径的不可逆SHA-256标识；
- `size_bytes`：该行情文件的字节数；
- `sha256`：该行情文件内容的SHA-256。

清单不保存原始路径或ticker。摘要只保存计数、大小、哈希、字段名和字段覆盖率；不保存成员记录、名称、OHLCV或完整`active-common`。

## 4. 缓存盘点结果

| 项目 | 输入缓存 | 输出缓存 |
| --- | ---: | ---: |
| 行情文件数 | 1529 | 1533 |
| 总文件数（含`active-common`） | 1530 | 1534 |
| 展开后总字节数 | 434888911 | 437623942 |
| `active-common`记录数 | 6324 | 6324 |
| `active-common`大小 | 1009184 | 1009184 |
| `active-common` SHA-256 | `9204777c71914c0892fb3ef5b8fb1f5d47a53b040398625bed02164bab9502ba` | 同左 |

输入到输出新增4份行情文件、删除0份、变化16份、未变化1513份；`active-common`没有变化。文件数接近或超过1337不代表资格筛选结果，也不证明成员覆盖完整。

## 5. 边界

- F0至此完成并以负结果留档；F0B2没有开始。
- M02仍为`implementing`；包F—包I均未获实施批准。
- 本目录不是生产缓存、股票池快照或ReleaseManifest，任何生产消费者都不得读取它。
- 本次没有修改生产JSON、网站、工作流或Discord，没有运行每日行情、扫描、回测或部署。
