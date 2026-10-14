# 运行原理与首次运行

这个项目是一个 Python 命令行程序，没有网页界面。它用多种早期信号寻找新名字，再用本地快照回答“相较上次，什么刚出现”。更新后的关键词表还会查询通用词的月搜索量、估算日搜索量并分析趋势；这些需要付费接口，不能保证候选词会变热门。

## 在这台 Mac 上运行

系统 `/usr/bin/python3` 是 3.9.6，低于项目要求的 3.10。本次用机器已有的 Python 3.12.14 创建了 `.venv`，并安装 pytest 和 markdown 来运行测试。核心抓取逻辑只依赖标准库。2026-10-14 同步作者 0.2.1 后，另安装了 MCP 依赖；合并后的 103 项测试全部通过。

在项目目录执行：

```bash
.venv/bin/python -m radar daily \
  --config config.json --state state --out report.md \
  --skip x,newsites,judge,usecases,review \
  --verbose --log-file state/run.log
```

本机 `config.json` 使用示例配置，报告语言改为 `zh`，sitemap 仅启用 Glama。保留示例 X 账号和主题，供以后调整，但免费运行时跳过 X。上面的命令跳过 X、新站、模型判断、付费关键词表和 Trends 复盘；Search Console 未配置。

作者 0.2.1 增加了以下入口：`python -m radar leads --days 7` 免费读取本地历史；`python -m radar keywords "名字"` 主动查询付费关键词表；`python -m radar mcp` 启动 stdio MCP 服务。MCP 的 `recent_leads` 只读取本地历史，`keyword_table` 和 `run_radar` 可能调用付费接口，不因安装而自动执行。作者上游仍保留在 `upstream`，自己的远程为 `origin`；不要用覆盖目录的方式更新，以免丢失飞书和日志改动。

首次抓取前检查了示例站点的 robots.txt：Glama 未禁止所访问的 sitemap 路径，配置每次间隔 2 秒；mcp.so 和 lobehub.com 的 robots.txt 返回 HTTP 403，本机配置暂未启用这两个站点。

`--verbose` 将过程打印到 stderr；`--log-file` 同时保存 UTF-8 日志，追加写入并自动创建父目录。stdout 仍然是报告正文，可单独重定向。日志包含具体候选词和公开请求网址，不打印完整配置或认证请求头。

## 从入口读到报告

入口是 [`radar/__main__.py`](../radar/__main__.py) 的 `main()`。`python -m radar` 会自动执行这个文件：

```python
cfg = config.load(Path(args.config))
if "judge" in args.skip:
    cfg["judge"]["model"] = ""
state = Path(args.state)
state.mkdir(parents=True, exist_ok=True)
```

`config.load()` 把用户配置与默认值合并，设置报告语言和停用词。密钥不放在 `config.json`；AIsa 优先使用环境变量，作者新版还可读取 `aisa login` 保存的本机凭证。日常采集选择以下两个任务之一：

- `sources`：只采集 X 与 Hugging Face，适合每隔几小时执行。没有新候选也没有错误时，只打印简短状态，不写报告。
- `daily`：依次采集各信号，合并候选，写入 SQLite，读取独立 sources 任务留下的名字，生成关键词表并入库，复盘，再生成 Markdown 和 JSON。各信号串行运行，日志中的耗时可以直接看出时间花在哪里。

`daily` 的主线是：

```python
lead, judged = _leads(cfg, blocks)  # 内部调用 report.leads()
conn = store.connect(state)
# store.record(conn, report.to_record(cfg, lead)) 记住本次发现
# usecases.run(...)                             生成关键词表
# store.record(conn, report.usecase_leads(...))  记住通用词与关联名字
# review.review(cfg, conn)                       检查旧线索
# report.daily(...)                             生成报告
```

Search Console 的查询单独展示在报告中；当前代码没有把这些查询并入 `report.leads()` 的候选词池或写入 `leads` 表。

## 每个信号怎样判断

| 信号与代码 | 读取内容 | 判断方法 | 第一次运行 |
|---|---|---|---|
| X：[`sources.x_new()`](../radar/sources.py) | 配置账号的近期帖子 | 提取类似名字的短语，对照保留 60 天的词表；近 30 小时至少两个账号提到，或明显的名字且单账号获得至少 100 赞 | 只建立词表；这不等于已经获取了此前 60 天的全部帖子 |
| Hugging Face：[`sources.hf_new()`](../radar/sources.py) | 热门前 100 个模型 | 当前前 50 中模型 ID 未出现在上次前 100，才作为新增；随后去掉量化/大小等后缀并合并基础名字 | 保存 100 个模型 ID，不产出新增词 |
| GitHub：[`breakout.breakouts()`](../radar/breakout.py) | 近 14 天创建、至少 300 星的仓库，最多两页、每页 100 个 | 平均星速至少 200/天，或与上次相比增加至少 400 星；最多保留 15 个 | 没有上次星数，但可以用平均星速筛选 |
| Sitemap：[`sitemaps.diff()`](../radar/sitemaps.py) | 配置站点的 sitemap 网址 | 当前网址减旧网址；提取 URL 路径词，至少 3 个不同新网址共现，再和旧网址中的词频比较 | 保存网址基线，不把整站所有网址当成新增 |
| 新站：[`new_sites.new_sites()`](../radar/new_sites.py) | 通过 AIsa 读取域名数据 | 注册和首次收录都在近 90 天，估算流量 > 1000，排名关键词至少 20；默认每周执行 | 按域名去重，付费信号，本次跳过 |
| Search Console：[`gsc.gsc_new()`](../radar/gsc.py) | 自己站点的查询曝光 | 最近 3 天有曝光、此前 60 天没有，至少 5 次曝光；过滤搜索操作符 | 依赖 Google 的历史数据，不需要本地首次快照；本次未配置 |

**GitHub 的公式尤其需要读清楚。** 在 `breakout.score()`：

```python
age = max((now - created).total_seconds() / 86400, 1.0)
velocity = stars / age
delta = stars - before[r["full_name"]] if before and r["full_name"] in before else None
if velocity < velocity_min and (delta is None or delta < delta_min):
    continue
```

`velocity` 是创建以来的平均值，年龄不足一天按一天算；`delta` 是两次运行之间的差值。只有每天一次运行时，后者才近似“日增星”。首次运行 `delta=None` 表示无历史，不是增星为零。

搜索请求没有 AI 主题限制：`created:>=日期 stars:>=300`。`topics` 只是将匹配内容额外列在主题章节，并不提前排除其他领域仓库。`math` 等普通名字仍可能入选；关闭名字判断时要自行核实。

**Sitemap 使用按网址去重的词频。** 在 [`terms.surges()`](../radar/terms.py)：

```python
expected = len(baseline.get(term, ())) * ratio
lift = n / (expected + 1)
```

其中 `ratio = 新网址总量 / max(旧网址总量, 1)`，`n` 是包含这个词的不同新网址数。`+1` 防止基线为零时除零。结果按 lift 和共现数排序，最多保留 25 个；当前代码没有额外设置最低 lift 门槛。一个 URL 重复同一个词不会让它被算多次。

Hugging Face 比较的是模型 ID，所以某个基础模型的新变体也可能触发信号；清洗和合并只能减少重复，不能证明基础模型本身刚发布。

## 为什么要合并、评分和记忆

[`report.leads()`](../radar/report.py) 以标准化的词为键合并各来源。一个词同时来自 X 和 GitHub 时，只显示一条，并保留两边的信号和原文例子。

名字判断由 [`judge.score()`](../radar/judge.py) 完成：每批最多 25 个词，每词带最多 3 段上下文，模型给出 0～1 的名字得分。默认阈值 0.5。排序顺序是：达到名字阈值优先、出现于更多信号优先、较早的信号优先，再比较名字得分。这是“是否像具体事物的名字”的评分，不是热度或成功概率。

没有评分的候选仍可展示和入库。`report.to_record()` 从可展示候选的前 20 条中排除已覆盖词；`known_terms` 使用双向子串匹配进行标记。关闭模型后，这些记录表示“发现过的候选”，不代表已经确认是专有名词。

记忆分两层：

| 文件 | 用途 |
|---|---|
| `state/hf_top.json.gz` | 上次热门模型 ID |
| `state/gh_stars.json.gz` | 上次搜索得到的仓库星数 |
| `state/gh_flagged.json.gz` | 已报出的爆发仓库，保留 30 天，避免每天重复作为新词 |
| `state/usecases.json.gz` | 关键词表已读取的名字和次数，控制后续复查 |
| `state/sitemaps/glama.json.gz` | 上次 Glama 网址集合 |
| `state/radar.db` | SQLite 的 `leads` 表：term 主键、首次和最近发现日期、信号、名字得分、搜索变体、复盘结论 |

gzip 快照由 [`snap.load()/save()`](../radar/snap.py) 读写。SQLite 的 [`store.record()`](../radar/store.py) 首次插入，后续更新最近发现日期并合并信号，保留首次发现时间。

[`review.review()`](../radar/review.py) 只取至少 14 天前、尚未复盘的线索，默认每次最多 5 条。每个搜索变体独立查询 Trends；发现后的峰值同时达到此前均值的 2 倍、并比均值高至少 10 点，才算上涨。它检验线索效果，不能在首次运行时给出可靠命中率。

## 失败为什么仍能生成报告

入口的 `run()` 捕获单个信号的异常，将错误变成 `{"error": "..."}`，再继续后面的信号。Sitemap 内部进一步按站点隔离失败。失败或空数据不会覆盖已有的 sitemap 快照，避免下一次把恢复的数据误当新增。

因此 **进程退出码 0 表示任务完成了报告流程，不代表每个数据源都成功**。应同时查看日志的失败状态和报告的抓取状态。配置读取错误、无法打开数据库等外围错误仍可能直接终止进程。

日志实现位于 [`diagnostics.py`](../radar/diagnostics.py)，入口负责阶段开始、状态、耗时；各模块补充抓取规则、数量与快照细节。

## 本机首次运行记录

首次运行的完整日志保存在 `state/first-run.log`，报告为 `report.md` 和 `report.json`。下面是同步作者新版本之前的历史记录，结果以该次实际产物为准；当时尚无关键词表功能。

运行时间：2026-10-13 11:43:26～11:51:02（Asia/Shanghai），总耗时 **456.19 秒**，退出码 **0**。本次实际启用的抓取信号均未报告错误。

| 阶段 | 实际结果 | 耗时 |
|---|---|---|
| Hugging Face | 保存 100 个模型 ID，首次建立基线，0 个新增词 | 1.32 秒 |
| GitHub | 搜索 198 个仓库，保留 15 个爆发仓库，产出 15 个候选词 | 29.48 秒 |
| Glama sitemap | 读取索引和 14 个文件，保存 126,127 个网址；首次建立基线，0 个新增词 | 425.37 秒 |
| 合并与 SQLite | 15 个候选、15 条入库，等待未来复盘 | 日志显示小于 0.01 秒 |
| Trends 到期检查 | 0 条到期，因此没有外部查询 | 日志显示小于 0.01 秒 |

日志节选：

```text
11:43:27 [Hugging Face] 完成 {'models': 100, 'first_run': True, 'terms': 0}
11:43:34 [GitHub 筛选] 搜索=198，保留最多15个爆发仓库，实际=15
11:43:34 [GitHub 仓库] storytold/photocraft stars=54081 age=12.6天 velocity=4296/天 delta=None 首次标记=True
11:51:01 [Sitemap/glama] 旧网址=无快照，当前=126127，新增=0
11:51:02 [候选合并] 原始=15，去重=15，可展示=15，可入库=15
11:51:02 [SQLite 入库] 完成 {'recorded': 15}
11:51:02 [结束] exit=0，总耗时 456.19s
```

日志中的 `age` 已四舍五入到一位小数；星速使用原始精确年龄计算，不能用显示的 `12.6` 精确反推 `4296`。

15 个候选是：`photocraft`、`math`、`wordcraft`、`anatomy`、`filmcraft`、`pdfcraft`、`lightcraft`、`ccbaga`、`d2r mobile`、`artex`、`gridcraft`、`new term radar`、`vectorcraft`、`cadcraft`、`esp32 iphone agent`。名字得分全部未评分。

检查了 Markdown/JSON 输出、gzip 快照可解压、报告候选集合与 SQLite 完全一致，以及 SQLite `PRAGMA integrity_check` 返回 `ok`。自动测试 **52 项通过**，包括原有的 49 项和新增的 3 项日志测试；另通过 Python 编译检查和 `git diff --check`。

本次没有实测 X、新站、模型评分、已授权 Search Console、真实 Trends 查询和邮件发送；mcp.so/lobehub sitemap 也未抓取。本次不涉及 API 计费，报告中的 AIsa 数据费用为 $0.000。

首次启动曾发现日志目录尚不存在时创建文件失败，已修复自动创建父目录，并在新增测试中覆盖；该失败发生在抓取前，没有写入信号快照。这里记录的是修复后完整完成的一轮。

后续继续使用相同 `state` 即可比较变化。快照比较的是“上次成功运行”，不是固定的昨天；刚运行完立即再跑可能没有新候选，GitHub 已标记仓库仍会出现在爆发仓库表中。
