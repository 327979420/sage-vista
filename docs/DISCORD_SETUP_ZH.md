# Discord 日终播报入口

## 当前范围

- 直接读取网站同源的 `resonance-tracker.json`、`rare-opportunity-radar.json` 和 `update-status.json`，不维护第二套评分。
- 5分或以上的多因子稀有机会排在消息最前；随后发送每日 MACD 看涨与看跌榜。
- 日期不同步、防前视检查失败时停止；同一日期、股票、证据与分数去重；消息模板集中在一个模块中，后续可以替换。
- 当前使用 Discord Webhook。Webhook 未配置时只返回“未配置”，不会误发。

## 本地配置

最简单的接入方式：在 Discord 目标频道打开“编辑频道 → 整合 → Webhooks → 新建 Webhook → 复制 Webhook URL”，然后把项目根目录的 `.env.local` 文件交给 Codex，或自行加入下面这一行：

```text
DISCORD_WEBHOOK_URL=用户提供的完整Webhook地址
```

保存后不需要修改代码。`.env.local` 已被 Git 忽略，播报程序会自动读取；不要把 Webhook 粘贴到聊天、代码、文档或 Git 提交中。

不得把 Webhook 写入代码、文档、测试、提交记录或 Sites 环境。先运行预览并人工核对：

```bash
python3 -m services.scanner.discord_daily_digest --preview
```

正式发送命令：

```bash
python3 -m services.scanner.discord_daily_digest
```

正式自动化必须在网站部署成功之后调用发送命令；部署失败、数据日期不一致或测试失败时不得发送。
