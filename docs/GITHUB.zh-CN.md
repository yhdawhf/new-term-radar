# GitHub 自动运行

仓库：`yhdawhf/new-term-radar`。工作流：`.github/workflows/radar.yml`。

## 时间与结果

| 任务 | 北京时间 | 内容 |
|---|---|---|
| sources | 每天 00:00、08:00、16:00 | Hugging Face 热门模型和 Spaces 的变化 |
| daily | 每天 09:30 | GitHub 爆发、Glama sitemap 变化和最近的 sources 线索 |

GitHub 定时触发可能延后，时间不是准点保证。云端进程使用 `TZ=Asia/Shanghai`，日期、每周判断和日志时间按北京时间计算。

工作流显示 `active` 或手动运行成功，都不能证明定时触发已经生效。查看 Actions 运行记录的事件类型：`schedule` 才是自动定时，`workflow_dispatch` 是手动，`push` 是配置提交触发。Fork 后应检查并启用定时工作流；GitHub 的规则见[官方说明](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows)。

提交到 main 的工作流或 `config.github.json` 发生变化时，会额外执行一次日报。也可在 Actions > New-term radar > Run workflow 选择 `daily` 或 `sources` 手动执行。日报若缺少模型或 Spaces 任一快照，会顺便建立对应基线；后续日报复用 sources 保存的线索。

每次运行页面的 Summary 先显示触发事件、cron、实际开始时间、命令和代码提交，再显示报告；Artifacts 中包含 `trigger.json`、`report.md`、日报的 `report.json`、`run.log`、完整 `state/`（SQLite 和 gzip 快照）。没有新名字的 sources 不生成报告，但仍保存触发信息、日志和状态。

## 当前为免费模式

`PAID_ENABLED` 明确设为字符串 `"false"`。即使仓库已有 API Key，运行步骤也会清除进程中的 AIsa/GoAnyAPI/TrustMRR Key，并跳过 `x,judge,review,usecases,newsites,revenue,asks,tutorials,sellers`。所以无需添加付费数据 Key 即可采集模型、Spaces、GitHub 和已配置的 sitemap。

`config.github.json` 仅包含公开的关注账号、站点和筛选规则，不含凭证。它继承了本机已验证的中文配置，sitemap 仅启用 Glama。编辑该文件可以修改云端关注方向；本机 `config.json` 继续独立使用，不会被提交。

这次配置没有启用邮件发送。报告在 GitHub 查看，不依赖 Mac 开机。

飞书消息可通过仓库 Secrets 启用：`FEISHU_WEBHOOK_URL` 和可选 `FEISHU_SECRET`。sources/daily 只推送新的候选词，失败队列随状态缓存保留。Run workflow 的 `test_feishu` 选项只发送连接测试。见 [飞书推送说明](FEISHU.zh-CN.md)。

## 状态延续

sources 和 daily 共享串行任务组与状态缓存，避免同时覆盖历史。每轮缓存键包含 run ID 和 attempt，失败重跑也能保存新状态。缓存失效时，下一轮重新建立基线，历史可能中断；运行附件还提供完整状态备份，保留 30 天。

本机首次运行的 `state` 不自动上传；云端从自己的首次运行开始累计变化与线索。

## 2026-10-14 排查记录

更新前，云端只有 10 月 13 日 16:33 的手动日报和 17:10 的飞书连接测试，没有任何 `schedule` 记录。首次日报生成时尚未加入飞书功能；后来的连接测试不执行采集。这解释了此前没有实际新词推送，不能据此推断没有新数据。

本次同步作者版本后，重新提交定时配置并通过 GitHub API 停用、启用工作流。14:37 的配置提交触发了真实日报，检测到 28 个候选，其中 20 个符合现有入库规则并成功推送；飞书待发队列为 0。详见[该次运行](https://github.com/yhdawhf/new-term-radar/actions/runs/38523323609)。

14:40 的手动 sources 又发现 `lfm2.5` 和 `drama 3`，飞书成功推送 2 个候选，待发为 0。详见[该次运行](https://github.com/yhdawhf/new-term-radar/actions/runs/38523620223)。这些是实际发送结果；是否在客户端看到消息，还需查看机器人所在群聊。

重新启用后，临时增加过每 5 分钟的检查规则。到 14:49 仍没有观察到 `schedule` 运行，随后删除临时规则，保留上述正式时间表。截至当时自动触发尚未得到验证；后续验证见下面 10 月 15 日记录。

## 2026-10-15 已验证的自动运行

已出现两次真实 `schedule` 事件，均成功：

| 实际开始时间（北京时间） | 任务 | HF 模型 | 新候选 | 飞书 sent / queued / pending |
|---|---|---|---|---|
| 10 月 14 日 21:16:49 | sources | 100 | 0 | 0 / 0 / 0 |
| 10 月 15 日 03:56:33 | sources | 100 | 0 | 0 / 0 / 0 |

运行链接：[昨晚](https://github.com/yhdawhf/new-term-radar/actions/runs/38570443688)、[凌晨](https://github.com/yhdawhf/new-term-radar/actions/runs/38627845810)。这两轮没有新消息的原因是没有新候选，且没有待发重试，不能再归为没有自动运行。此前已成功发送的 22 个词仍保留在去重状态中。

实际时间与设定时间存在偏移；旧日志没有记录触发用的 cron，无法逐轮确认是哪个定时点延后。本次增加 `trigger.json` 及 Summary 触发信息，后续可直接核对。GitHub 官方说明定时事件可能延迟，负载高时可能丢弃队列，见[调度说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。

同步作者 0.4.0 后，Spaces 使用独立快照 `state/hf_spaces_top.json.gz`；首次只建基线，从下一轮起比较变化。免费模式仍不发送“没有新词”的固定提醒。

本次更新触发的[08:08 日报](https://github.com/yhdawhf/new-term-radar/actions/runs/38658232924)已成功读取模型和 Spaces，建立 Spaces 基线；08:08:52 飞书成功发送 19 个候选词（3 条消息），待发为 0，累计成功去重词为 41。修改和验证详情见[本次说明](CHANGES-2026-10-15.zh-CN.md)。

## 2026-10-21 同步与推送核对

已合并作者 0.5.0 的新收款站点 `sellers`、历史查询 `history`、插件 MCP 配置及文档更新。免费定时任务显式跳过 sellers，未调用历史拉取或分类等付费操作；现有计划时间、状态缓存和飞书去重不变。

截至本次更新前，已核实 26 次真实 `schedule` 事件。最近一次日报的 trigger 记录 `cron=30 1 * * *、command=daily`，实际 10 月 20 日 14:20 开始；飞书 API 在 14:21:20 接受 17 个词。最近一次 sources 记录 `cron=0 */8 * * *`，10 月 21 日 03:48:21 接受 2 个词，待发均为 0。实际时间有明显偏移，计划不等于准点执行。

用户最初反馈群内无消息，随后本次新版日报在 10:16:43 向飞书发送 17 个词（3 条消息），待发为 0；用户已确认连接测试和 3 条真实报告均在目标群可见。当前链路已核对通过；此前历史消息不可见的具体原因无法从现有日志追溯，不能再用“没有采集”或“没有新词”解释。详情见[本次修改说明](CHANGES-2026-10-21.zh-CN.md)。

## 2026-10-23 核查

更新前已有 34 次真实自动运行，均显示成功。10 月 22 日的日报在 14:25:15 获飞书 API 接受 17 个词；10 月 23 日 03:42 的 sources 读取 100 个模型和 100 个 Spaces，但新候选为 0，因此不发消息，待发也为 0。此前 API 接受的累计不同词已达 206 个。

本次作者只有 MCP 依赖固定和 README 更新，版本仍是 0.5.0；定时流程从 main 读取同步后的代码，继续保留免费模式和历史状态。详见[本次修改说明](CHANGES-2026-10-23.zh-CN.md)。

## 以后开启 AIsa

1. 在仓库 Settings > Secrets and variables > Actions 添加 Secret `AISA_API_KEY`。
2. 将工作流中的 `PAID_ENABLED: "false"` 改为 `PAID_ENABLED: "true"` 并提交。单独添加 Key 不会开启付费请求。
3. 按需要再配置可选的 `GOANYAPI_API_KEY`。Search Console 还需要 `GSC_TOKEN_JSON` 和云端配置中的 `gsc.site`。

启用后，sources 才读取 X 并判断名字，daily 才运行关键词表和到期的 Trends 复盘。新站查询仍显式跳过，需验证上游接口后再恢复。付费请求按平台实际用量计费。

## 暂停

Actions > New-term radar > 右上角菜单 > Disable workflow。恢复时选择 Enable workflow。现有配置不依赖 `RADAR_ENABLED` 仓库变量。
