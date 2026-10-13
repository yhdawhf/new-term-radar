# GitHub 自动运行

仓库：`yhdawhf/new-term-radar`。工作流：`.github/workflows/radar.yml`。

## 时间与结果

| 任务 | 北京时间 | 内容 |
|---|---|---|
| sources | 每天 00:00、08:00、16:00 | Hugging Face 热门模型的变化 |
| daily | 每天 09:30 | GitHub 爆发、Glama sitemap 变化和最近的 sources 线索 |

GitHub 定时触发可能延后，时间不是准点保证。云端进程使用 `TZ=Asia/Shanghai`，日期、每周判断和日志时间按北京时间计算。

提交到 main 的工作流或 `config.github.json` 发生变化时，会额外执行一次日报。也可在 Actions > New-term radar > Run workflow 选择 `daily` 或 `sources` 手动执行。首次日报若尚无 HF 快照，会顺便建立 HF 基线；后续日报复用 sources 保存的线索。

每次运行页面的 Summary 显示报告；Artifacts 中包含 `report.md`、日报的 `report.json`、`run.log`、完整 `state/`（SQLite 和 gzip 快照）。没有新名字的 sources 不生成报告，但仍保存日志和状态。

## 当前为免费模式

`PAID_ENABLED` 明确设为字符串 `"false"`。即使仓库已有 API Key，运行步骤也会清除进程中的 AIsa/GoAnyAPI Key，并跳过 `x,judge,review,usecases,newsites`。所以无需添加 Secret 即可开始本次配置的信号采集。

`config.github.json` 仅包含公开的关注账号、站点和筛选规则，不含凭证。它继承了本机已验证的中文配置，sitemap 仅启用 Glama。编辑该文件可以修改云端关注方向；本机 `config.json` 继续独立使用，不会被提交。

这次配置没有启用邮件发送。报告在 GitHub 查看，不依赖 Mac 开机。

飞书消息可通过仓库 Secrets 启用：`FEISHU_WEBHOOK_URL` 和可选 `FEISHU_SECRET`。sources/daily 只推送新的候选词，失败队列随状态缓存保留。Run workflow 的 `test_feishu` 选项只发送连接测试。见 [飞书推送说明](FEISHU.zh-CN.md)。

## 状态延续

sources 和 daily 共享串行任务组与状态缓存，避免同时覆盖历史。每轮缓存键包含 run ID 和 attempt，失败重跑也能保存新状态。缓存失效时，下一轮重新建立基线，历史可能中断；运行附件还提供完整状态备份，保留 30 天。

本机首次运行的 `state` 不自动上传；云端从自己的首次运行开始累计变化与线索。

## 以后开启 AIsa

1. 在仓库 Settings > Secrets and variables > Actions 添加 Secret `AISA_API_KEY`。
2. 将工作流中的 `PAID_ENABLED: "false"` 改为 `PAID_ENABLED: "true"` 并提交。单独添加 Key 不会开启付费请求。
3. 按需要再配置可选的 `GOANYAPI_API_KEY`。Search Console 还需要 `GSC_TOKEN_JSON` 和云端配置中的 `gsc.site`。

启用后，sources 才读取 X 并判断名字，daily 才运行关键词表和到期的 Trends 复盘。新站查询仍显式跳过，需验证上游接口后再恢复。付费请求按平台实际用量计费。

## 暂停

Actions > New-term radar > 右上角菜单 > Disable workflow。恢复时选择 Enable workflow。现有配置不依赖 `RADAR_ENABLED` 仓库变量。
