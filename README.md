# devlog

> 一个本机 CLI:把当天 **Claude Code / Codex / Cursor** 的会话采集、脱敏、总结成一份开发日报。可选推送到飞书 Inbox,人工 5 分钟内审完。

[![CI](https://github.com/your-org/devlog-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/devlog-cli/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## ✨ 特点

- **数据不出本机**:全部在本地读、本地脱敏,LLM 后端也是本机 CLI(codex / cursor / claude code)
- **多端融合**:Claude Code JSONL、Codex JSONL、Cursor SQLite 一次性聚合
- **脱敏可信**:正则黑名单 (JWT / AWS / GH / OpenAI key / 私钥 / Bearer / password) + 白名单 + Codex env 块剥离 + 长代码块裁剪
- **后端可插拔**:`codex → cursor → claude-code → none` 链式 fallback,任何一档配额耗尽都不阻塞
- **便于人审**:每日生成"今日新增 / 与昨日 diff / 待确认 / 统计"四段,所有条目带 checkbox
- **可选飞书落地**:`--post` 直接写到飞书 Inbox 文件夹

## 🚀 安装

```bash
pip install devlog-cli            # 待发布到 PyPI
# 或源码安装
git clone https://github.com/your-org/devlog-cli.git
cd devlog-cli && pip install -e .
```

要求 Python ≥ 3.10。

## ⚡ 快速上手

```bash
# 1. 生成默认配置(~/.devlog/config.toml)
devlog init

# 2. 跑一次:采集今天 → 总结 → 落地到 ~/.devlog/reports/YYYY-MM-DD.md
devlog run

# 3. 只采集不调 LLM(配额紧张时)
devlog run --no-llm

# 4. 同步到飞书 Inbox(先在 config.toml 里 enable)
devlog run --post
```

## 📋 子命令

| 命令 | 作用 |
|---|---|
| `devlog run [--date today] [--out PATH] [--no-llm] [--no-diff] [--post]` | 默认命令:采集 → 脱敏 → 总结 → 写报告 |
| `devlog collect [--date today] [--out PATH]` | 只采集 + 脱敏,输出 prompt(便于手动喂别的模型)|
| `devlog post FILE [--title T]` | 推送已有 Markdown 到飞书 Inbox |
| `devlog promote [--date yesterday] [--file PATH] [--dry-run] [--yes]` | 把报告中已勾选 `[x]` 的条目推到对应分类文件夹 |
| `devlog init [--force]` | 写一份配置模板 |
| `devlog version` | 版本号 |

## 🛠️ 配置

`~/.devlog/config.toml` 示例:

```toml
output_dir = "~/.devlog/reports"
max_messages_per_source = 500

[[sources]]
name    = "claude-code"
kind    = "jsonl"
path    = "~/.claude/projects"

[[sources]]
name    = "codex"
kind    = "jsonl"
path    = "~/.codex/sessions"

[[sources]]
name    = "cursor"
kind    = "sqlite"
path    = "~/Library/Application Support/Cursor/User/globalStorage/state.vscdb"

# 按顺序尝试,首个 exit 0 的胜出
[[backends]]
name        = "codex"
command     = ["codex", "exec", "--skip-git-repo-check", "-"]
timeout_sec = 120

[[backends]]
name    = "cursor"
command = ["cursor"]

[[backends]]
name = "none"   # 兜底:不调 LLM,只产 prompt 文件

[feishu]
enabled            = false
inbox_folder_token = ""       # 在飞书目录 URL 里
lark_cli           = "lark-cli"

# 可选:per-category 文件夹(devlog promote 用)
[feishu.folders]
# pit      = ""   # 踩坑
# tool     = ""   # 工具
# sop      = ""   # SOP/知识
# decision = ""   # 决策
# active   = ""   # 待办/进行中
# archive  = ""   # 归档
```

## 🔀 Promote 工作流

当每日报告里有你确认过的条目(手动打 `[x]`),运行 `devlog promote` 把它们分发到对应分类文件夹:

```bash
# 查看计划(不上传)
devlog promote --dry-run

# 确认推送(默认取昨天的报告)
devlog promote --yes

# 指定某天的报告
devlog promote --date 2026-05-25
```

**分类映射规则**(`[xxx]` 标签 → folder_key):

| 标签 | 映射 folder_key |
|---|---|
| 踩坑 / pit / bug / 故障 | `pit` |
| 工具 / tool / tools | `tool` |
| sop / 流程 / 规范 | `sop` |
| 决策 / decision / 选型 | `decision` |
| 待办 / todo / task | `active` |
| 知识 / library / note | `sop` |

## 📑 输出样例

```markdown
# 2026-05-26 开发日报

> backend: `codex`

## 🟢 今日新增
- [ ] [踩坑] codex Operation not permitted → ~/.codex 权限
- [ ] [工具] lark-cli 1.0.39 升级
- [ ] [决策] devlog 总结后端可插拔

## 🟡 状态变化
- [→] 大屏适配 iPhone 17 Pro Max: 进行中 → 已完成

## 🔴 待确认
- [?] 讲解卡是否需要兼容横屏

## 🆚 与昨日对比
**新增**
- ✨ [工具] lark-cli 1.0.39 升级

## 📊 原始统计
- claude-code: 73
- codex: 22
- cursor: 14
```

## 🤖 LaunchAgent(macOS 定时跑)

`~/Library/LaunchAgents/com.devlog.daily.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.devlog.daily</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/env</string>
    <string>devlog</string>
    <string>run</string>
    <string>--post</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>22</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>/tmp/devlog.out</string>
  <key>StandardErrorPath</key><string>/tmp/devlog.err</string>
</dict></plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.devlog.daily.plist
```

## 🔒 隐私

- 所有采集、脱敏在本机完成
- 仅在调用 LLM 后端时把**脱敏后**的 prompt 经 stdin 喂给本机 CLI;`name = "none"` 兜底完全离线
- 飞书推送是**可选**,默认关闭

## 🧪 开发

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## 📜 License

MIT. See [LICENSE](LICENSE).
