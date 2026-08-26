# Discord 日终播报入口

## Cloudflare 自动发布链

生产 scheduled workflow 使用 Repository Secrets `CLOUDFLARE_API_TOKEN`、`CLOUDFLARE_ACCOUNT_ID`、`DISCORD_OPPORTUNITY` 和 `EODHD_API_TOKEN`。新 EOD 数据通过全部测试后发布到平行的 Cloudflare Workers production；只有线上 `update-status.json`、Tracker、Radar 日期完全一致且 future-data audit 安全，才调用现有 Discord digest。`already_current` 且 production state 已同步时不会重复发布或发送。

## 当前范围

- 直接读取网站同源的 `resonance-tracker.json`、`rare-opportunity-radar.json` 和 `update-status.json`，不维护第二套评分。
- Early Watch／Confirmed 特殊提醒保持原有详情。每个完整 EOD 日期另发送两份极简榜单：按现有 `macd_rank_score` 排序的 MACD Top 10，以及按现有多因子总分排序的 Multi-Factor Top 10；榜单只显示日期、排名和股票代码，不显示分数、价格或解释。
- 日期不同步、防前视检查失败时停止；同一日期、股票、证据与分数去重；消息模板集中在一个模块中，后续可以替换。
- 当前使用 Discord Webhook。Webhook 未配置时只返回“未配置”，不会误发。

## GitHub Actions 配置

- 正式自动化从 GitHub Repository Secret 读取 `DISCORD_WEBHOOK_URL`；兼容现有旧名称 `DISCORD_OPPORTUNITY`。workflow 不打印、上传或写回 Secret。
- EODHD 自动扫描需要独立的 Repository Secret：`EODHD_API_TOKEN`。
- 定时 update job 永远先生成 Discord preview；它本身不发送。Sage Vista 是私有 Sites，GitHub Runner 无法匿名读取线上文件；因此部署协调任务只有在 Sites API 明确返回成功后，才创建带 EOD 日期与站点 URL 的 GitHub Deployment success 记录，并把其 ID 交给 `notify`。notify 核对该不可变记录、仓库日期与 future-data 状态，任一不一致即停止。
- Early Watch 和 Confirmed 状态保存在 `automation/discord-state.json`。同一股票相同状态不重复；Early Watch 升级 Confirmed 可以再次提醒；Confirmed 不会降级重发 Early Watch。两份排行榜分别以“榜单类型 + EOD 日期”去重，每日各发送一次，互不影响。

## 密钥与人工配置

生产环境只从 GitHub Repository Secrets 读取。Discord 支持 `DISCORD_WEBHOOK_URL`，也兼容已有的 `DISCORD_OPPORTUNITY`；EODHD 扫描读取 `EODHD_API_TOKEN`。

```text
DISCORD_WEBHOOK_URL=用户提供的完整Webhook地址
```

`.env.local` 只用于本地人工运行且已被 Git 忽略；不要把 Webhook 粘贴到聊天、代码、文档、日志或 Git 提交中。

不得把 Webhook 写入代码、文档、测试、提交记录或 Sites 环境。先运行预览并人工核对：

```bash
python3 -m services.scanner.discord_daily_digest --preview
```

正式发送命令：

```bash
python3 -m services.scanner.discord_daily_digest
```

正式自动化必须在网站部署成功之后调用发送命令；部署失败、数据日期不一致或测试失败时不得发送。
