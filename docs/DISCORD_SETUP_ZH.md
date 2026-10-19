# Discord 日终播报入口

## Cloudflare 自动发布链

生产 scheduled workflow 使用 Repository Secrets `CLOUDFLARE_API_TOKEN`、`CLOUDFLARE_ACCOUNT_ID`、`DISCORD_OPPORTUNITY` 和 `EODHD_API_TOKEN`。新 EOD 数据通过全部测试后只发布到唯一 Cloudflare Workers production；只有线上 `update-status.json`、Tracker、factor snapshot、Radar 日期完全一致且 future-data audit 安全，才调用现有 Discord digest。`already_current` 且 production state 已同步时不会重复发布或发送。

## 当前范围

- 直接读取网站同源的 `resonance-tracker.json`、`rare-opportunity-radar.json` 和 `update-status.json`，不维护第二套评分。
- Early Watch／Confirmed 特殊提醒保持原有详情。每个完整 EOD 日期另发送两份极简榜单：按现有 `macd_rank_score` 排序的 MACD Top 10，以及按现有多因子总分排序的 Multi-Factor Top 10；榜单只显示日期、排名和股票代码，不显示分数、价格或解释。
- 日期不同步、防前视检查失败时停止；同一日期、股票、证据与分数去重；消息模板集中在一个模块中，后续可以替换。
- 当前使用 Discord Webhook。Webhook 未配置时只返回“未配置”，不会误发。

## GitHub Actions 配置

- 正式自动化从 GitHub Repository Secret 读取 `DISCORD_WEBHOOK_URL`；兼容现有旧名称 `DISCORD_OPPORTUNITY`。workflow 不打印、上传或写回 Secret。
- EODHD 自动扫描需要独立的 Repository Secret：`EODHD_API_TOKEN`。
- 定时 update job 永远先生成 Discord preview，再发布同一个 Cloudflare Worker。发布完成后，workflow 直接从该 production URL 重新读取整组 JSON 并验证日期和防前视；验证成功才发送 Discord。旧 Sites deployment attestation 与独立 `notify` job 已移除。
- Early Watch 和 Confirmed 状态保存在 `automation/discord-state.json`。同一股票相同状态不重复；Early Watch 升级 Confirmed 可以再次提醒；Confirmed 不会降级重发 Early Watch。两份排行榜分别以“榜单类型 + EOD 日期”去重，每日各发送一次，互不影响。

## 密钥与人工配置

生产环境只从 GitHub Repository Secrets 读取。Discord 支持 `DISCORD_WEBHOOK_URL`，也兼容已有的 `DISCORD_OPPORTUNITY`；EODHD 扫描读取 `EODHD_API_TOKEN`。

```text
DISCORD_WEBHOOK_URL=用户提供的完整Webhook地址
```

`.env.local` 只用于本地人工运行且已被 Git 忽略；不要把 Webhook 粘贴到聊天、代码、文档、日志或 Git 提交中。

不得把 Webhook 写入代码、文档、测试或提交记录。先运行预览并人工核对：

```bash
python3 -m services.scanner.discord_daily_digest --preview
```

正式发送命令：

```bash
python3 -m services.scanner.discord_daily_digest
```

正式自动化必须在网站部署成功之后调用发送命令；部署失败、数据日期不一致或测试失败时不得发送。

## 3W 冻结机会提醒（2026-10-19）

用户授权独立接入 3W 机会提醒；旧 MACD／多因子摘要的暂停状态不变。
新增 `services/scanner/triangle_discord.py`，只读 `public/app/signals.json` 和已有的信号票据，
不扫描历史、不调整规则、不修改冻结代码或 `research/lab/forward/`。

- 仅发送 `3w-1.9`、允许下单、仍 waiting、行情新鲜、票据重放核对通过且未过期的机会。
- 入场和止损照抄冻结记录；目标必须等于计划入场价 + 3 ×（计划入场价 − 止损），不使用旧版 t1。
- 有效期为信号后 40 个交易日；日期照用票据的常规 NYSE 交易日历估算并明确标注；最多持仓 130 个交易日。
- 形态出现但未通过大盘或原计划门槛，不发送；已成交、取消、结束、状态未核实和示例均不作为新挂单机会发送。
- 当前交易日行情缺失、价格或版本不一致、时间异常均阻断。无机会则不发送空消息。
- `Research Lab` 成功后独立 job 从 main 重新取已发布的 app 数据，先测试、预览并留 artifact，再发送。
  不依赖旧多因子通知，也不要求网站部署产生变化；生产 job 成功仍是前提。
- Secrets 优先 `DISCORD_WEBHOOK_URL`，其次原有 `DISCORD_OPPORTUNITY`；不读本地 `.env`，缺失则明确失败。

预览（不读密钥、不写状态、不联网）：

```sh
python3 -m services.scanner.triangle_discord
python3 -m unittest tests.test_triangle_discord tests.test_triangle15 tests.test_app_data tests.test_discord_digest
```

### 去重与异常核查

`automation/triangle-discord-state.json` 永久按 `3w-1.9:信号ID` 保存通知记录，不按股票终身去重：
同一机会不重发，未来同股的新信号可以通知。发送前先通过独立 Git index 将 `reserved` 状态推送到 main；
成功回执后再保存 `sent`。并发或推送失败时不得调用 Discord。运行时遵守 EOD 禁推窗口。

Discord HTTP 与 Git 之间无法做原子事务：超时、发送后进程终止或结果保存失败时，可能已送达也可能漏发。
为了遵守用户“不重复发”，`reserved` 不自动重发；下次运行报告待核查并令 job 失败。
人工先按消息中的机会编号检查频道：已收到则将该记录改为 `sent`；确定未收到时才解除该条保留并重跑。
解除保留仍须经过最新行情、waiting 与有效期检查，过期或已成交的机会不会补成可下单消息。
不要清空整个账本。常规单元测试只模拟 HTTP。用户明确请求时，可从 `3W Discord preview and simulation` 手动选择 `simulate`，通过 GitHub Secrets 向真实频道发送一条清楚标注“模拟／非真实机会”的 TEST 样例。

通知使用 Discord Embed 卡片：入场／止损／3R 止盈分为三个字段，挂单有效期独占一行，规则版本置于页脚；模拟仅在标题标注，不再追加“非真实机会”。价格保留至少两位、最多四位小数，不丢失记录中的四位精度。

模拟使用独立去重键 `simulation:3w-1.9:brief-v1`，与真实机会的状态隔离；再次运行同一样例不会重发，也不写入信号、行情或账户记录。手动 `preview` 只生成样例 artifact，不发送。模拟运行不依赖扫描／回测／网站部署。

上线流程：PR 上运行通知及现有消费者测试，验证无 Secret 的短版预览；随后按用户 2026-10-19 明确授权提交、推送、合并，在 main 上手动运行 `mode=simulate`。仍遵守 EOD 禁推窗口。

本次用户明确批准 EOD 窗口例外：手动模拟可设置 `allow_eod_window=true`，仅对模拟命令生效；默认 false，真实机会提醒不能使用该例外。
