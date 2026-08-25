# Discord 日终播报入口

## 当前范围

- 直接读取网站同源的 `resonance-tracker.json`、`rare-opportunity-radar.json` 和 `update-status.json`，不维护第二套评分。
- 5分或以上的多因子稀有机会排在消息最前；随后发送每日 MACD 看涨与看跌榜。
- 日期不同步、防前视检查失败时停止；同一日期、股票、证据与分数去重；消息模板集中在一个模块中，后续可以替换。
- 当前使用 Discord Webhook。Webhook 未配置时只返回“未配置”，不会误发。

## GitHub Actions 配置

- 正式自动化从 GitHub Repository Secret 读取 `DISCORD_WEBHOOK_URL`；兼容现有旧名称 `DISCORD_OPPORTUNITY`。workflow 不打印、上传或写回 Secret。
- EODHD 自动扫描需要独立的 Repository Secret：`EODHD_API_TOKEN`。
- 定时 update job 永远先生成 Discord preview；它本身不发送。只有 Sites 已发布并且线上 `update-status.json` 精确匹配本次完整收盘日后，部署任务才以 `notify` 模式触发 workflow 正式发送。
- Early Watch 和 Confirmed 状态保存在 `automation/discord-state.json`。同一股票相同状态不重复；Early Watch 升级 Confirmed 可以再次提醒；Confirmed 不会降级重发 Early Watch。

## 本地配置

最简单的接入方式：在 Discord 目标频道打开“编辑频道 → 整合 → Webhooks → 新建 Webhook → 复制 Webhook URL”，然后把项目根目录的 `.env.local` 文件交给 Codex，或自行加入下面这一行：

```text
DISCORD_WEBHOOK_URL=用户提供的完整Webhook地址
```

`.env.local` 只用于本地人工运行且已被 Git 忽略；GitHub Actions 只读取 Repository Secrets。不要把 Webhook 粘贴到聊天、代码、文档或 Git 提交中。

不得把 Webhook 写入代码、文档、测试、提交记录或 Sites 环境。先运行预览并人工核对：

```bash
python3 -m services.scanner.discord_daily_digest --preview
```

正式发送命令：

```bash
python3 -m services.scanner.discord_daily_digest
```

正式自动化必须在网站部署成功之后调用发送命令；部署失败、数据日期不一致或测试失败时不得发送。
