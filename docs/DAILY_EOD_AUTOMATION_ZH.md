# 每日行情独立调度与恢复手册

状态：代码契约已建立；生产启用以 Cloudflare Worker 部署和真实自动 dispatch 证据为准。

## 生产结构

```text
Cloudflare Cron（主触发）
        ↓
GitHub daily-eod.yml（同一幂等生产流水线）
        ↓
数据审计 → 测试 → Cloudflare网站部署 → 线上核验 → Discord

GitHub schedule（备用）

Cloudflare独立新鲜度触发
        ↓
eod-freshness-monitor.yml
        ↓ 若落后
自动 dispatch 一次 freshness_recovery
```

Cloudflare只负责准时发起，不读取行情、不计算分数、不部署网站。所有数据和发布仍由唯一的 `daily-eod.yml` 完成。

## 时间

- Cloudflare只占用2条 Cron Trigger。日终宽窗口表达式为 `17,47 0-3,23 * * 1-6`；Worker内部只允许 UTC `23:47`（周一至周五），以及次日 `00:17 / 00:47 / 01:17 / 01:47 / 02:17 / 03:17`（周二至周六）真正 dispatch。其他宽窗口唤醒立即空退出，不调用GitHub。
- 第二条独立新鲜度检查为 UTC `04:37`，周二至周六。
- 重复运行是安全的：全套数据和因子版本已经一致时返回 `already_current`，不重新部署或通知。

## 一次性安全配置

1. 在 GitHub 为仓库 `327979420/sage-vista` 创建专用 fine-grained token。
2. Repository access 只选本仓库；Repository permission 只给 `Actions: Read and write`，不授予代码、管理或其他仓库权限。
3. 把令牌保存为 GitHub Actions secret `SAGE_VISTA_SCHEDULER_GITHUB_TOKEN`；不得使用个人广权限 CLI 登录令牌。
4. 手动运行 `Deploy EOD Scheduler`。工作流会把该值写成 Cloudflare Worker 加密 secret `GITHUB_ACTIONS_TOKEN`，然后部署 `sage-vista-eod-scheduler` 与 Cron Triggers。

令牌不得出现在 Git、普通 GitHub Variables、Cloudflare普通变量、命令输出、Actions artifact 或网站 JSON。

## 验收

- Cloudflare Cron 产生的日终运行显示 `trigger_source=cloudflare_cron`。
- 新鲜度恢复产生的日终运行显示 `trigger_source=freshness_recovery`。
- 自动运行完整通过数据日期、防前视、Python、网站构建、部署和线上核验。
- 连续五个完整美股交易日不需要人工 update；网站在当日恢复窗口内推进到数据源最新完整收盘。
- 任一步失败不得发送 Discord，也不得把半套数据发布到网站。
