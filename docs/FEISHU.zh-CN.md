# 飞书新词推送

GitHub 定时任务发现新的候选词时，向飞书群自定义机器人发送文本消息。没有新词时不打扰；不依赖 Mac 开机，也不需要 AIsa Key。当前免费模式下推送 Hugging Face、GitHub 和 sitemap 产生的候选词。

## 配置

在仓库 Settings > Secrets and variables > Actions > Repository secrets 添加：

| Secret | 内容 |
|---|---|
| `FEISHU_WEBHOOK_URL` | 完整的 `https://open.feishu.cn/open-apis/bot/v2/hook/...` 机器人地址 |
| `FEISHU_SECRET` | 机器人签名校验密钥；未开启签名校验时不配置 |

应保存为 **Secret**，不是 Variable，也不是仅创建一个同名 Environment。当前工作流使用 Repository secrets，不需要绑定 Environment。地址和密钥不能写入配置文件或提交到 Git。

如果机器人采用关键词校验，消息固定包含“新词雷达”，可在机器人的安全设置中配置这个关键词。签名算法、请求格式和大小限制依据[飞书官方自定义机器人文档](https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot)。

## 验证连接

Actions > New-term radar > Run workflow，勾选 `test_feishu`。这轮只发送一条：

```text
新词雷达：飞书连接测试成功。
今后仅发现新候选词时推送，没有新词时保持安静。
测试运行：https://github.com/.../actions/runs/...
```

测试轮不采集数据，也不发送虚构候选词。`Test Feishu delivery` 步骤检查 HTTP 和飞书 JSON 中的 `code=0`；平台拒绝或连接失败时，该步骤显示失败。成功表示飞书 API 接受消息，是否已在设备端看到消息仍需查看群聊。

## 实际推送内容

```text
新词雷达：发现 1 个新候选词

• qwen3.9
  来源：HF 新进热门榜 #4
  例子：Qwen/Qwen3.9
  名字评分：未评分，需自行核实

完整报告：
https://github.com/.../actions/runs/...
```

每批最多 8 个词，每轮最多发送 24 个积压词，自动限制消息大小。候选使用和报告入库相同的过滤规则：已覆盖词不推送；启用模型时过滤低于名字评分门槛的词。免费模式没有模型评分，所以消息明确标记未评分。

推送频率与已有任务相同：北京时间 00:00、08:00、16:00 的 sources，以及 09:30 的 daily。不是持续实时监听。

## 去重和失败重试

`state/feishu_notifications.json.gz` 保存目标机器人的哈希、已发送词和待发送词，不保存 Webhook 地址或签名密钥。该文件跟随 Actions 状态缓存和完整状态备份一起保留。

候选先写入待发队列，再调用飞书。成功后移出待发队列并标记已发送。这样，即使上游快照已更新、下次没有新词，也能重试前次失败的消息。分批发送中途失败时，已确认成功的批次不会重发。

推送失败不会阻止报告写出，日报 JSON 的 `notifications` 和报告数据状态会显示错误；进程返回非零，让 Actions 显示失败。缓存和附件步骤仍然执行，以保留待发消息。没有配置 Webhook 时直接跳过。

状态缓存或备份丢失会重置去重记录。飞书已收消息、但响应丢失或保存状态前进程中断时，也可能出现重复；跨系统发送不保证严格的“恰好一次”。更换机器人地址会为新目标重新开始去重。

## 错误定位

长期没有消息时，先在 Actions 检查最近一次真实采集和 `schedule` 事件记录。连接测试成功只证明机器人能收消息；如果定时采集根本没有执行，也不会发现并推送新词。日报 JSON 的 `notifications.sent` 是已成功发送的词数，消息按每批最多 8 个词拆分，`pending` 为未发队列长度。

运行日志仅记录 HTTP 状态或飞书错误码，不输出 Webhook、密钥或原始错误响应。常见签名/关键词等错误应结合官方文档和机器人设置检查。需要补填签名密钥时，用 `FEISHU_SECRET` Secret，填好后再运行一次连接测试即可。
