# 架构

## 数据流

```
┌────────────────┐    ┌────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────┐
│ Collectors     │ -> │ Sanitizer  │ -> │ Summarizer   │ -> │ Differ +    │ -> │ Output / │
│ (jsonl/sqlite) │    │ (regex+wl) │    │ (codex/...)  │    │ Report      │    │ Feishu   │
└────────────────┘    └────────────┘    └──────────────┘    └─────────────┘    └──────────┘
```

每一阶段都是纯函数 / 显式 IO,便于单测与替换。

## 模块职责

| 模块 | 文件 | 职责 |
|---|---|---|
| Config | `devlog/config.py` | 加载 / 初始化 `~/.devlog/config.toml` |
| Models | `devlog/models.py` | `Message` 统一中间表示 |
| Collectors | `devlog/collectors.py` | 各 source → `list[Message]`,失败隔离 |
| Sanitizer | `devlog/sanitizer.py` | 7 类正则黑名单 + 白名单 + 代码块裁剪 |
| Summarizer | `devlog/summarizer.py` | 多后端 fallback,统一 stdin/stdout 协议 |
| Differ | `devlog/differ.py` | 与昨日 report 做 set diff |
| Report | `devlog/report.py` | 拼装 prompt / stats / 最终 Markdown |
| Feishu | `devlog/feishu.py` | 调用 `lark-cli` 上传到 Inbox |
| CLI | `devlog/cli.py` | argparse + 5 个子命令 |

## 关键设计决策

### 为什么后端走 subprocess 不走 API SDK?

- 避免绑死任何 LLM 厂商
- 本机 CLI 已经处理好鉴权、配额、网络
- 任何能"读 stdin、写 stdout"的工具都能立刻接入

### 为什么 Cursor 用 SQLite 而不是 JSONL?

Cursor 把会话存在 `globalStorage/state.vscdb`,没有 JSONL 导出。用 `mode=ro&immutable=1` URI 打开,避免锁竞争。

### 为什么先做 diff 再发飞书?

人审的核心成本是"找出今天新发生了什么"。先 diff 让"今日新增"段一眼可见,不用逐条对比昨天的报告。

### 为什么坚持 checkbox?

`- [ ]` 是飞书原生交互。人审完勾选 = 给未来的 `devlog promote` 留下确定信号,不需要额外 UI。

## 失败模式

| 场景 | 行为 |
|---|---|
| 某个 source 路径不存在 | log warning,继续其它 source |
| 某个 JSONL 文件损坏 | 忽略损坏行,继续 |
| 第一个 backend 报错 | 自动跑下一个 |
| 全部 backend 失败 | 退出码 2,prompt 已落盘可手工总结 |
| 飞书上传失败 | 退出码 3,本地 Markdown 仍在 |

## 扩展点

1. **新 source**: 实现 `_iter_xxx` + `_collect_one` 分支
2. **新 backend**: 改 `config.toml` 即可
3. **新输出**: 在 `cli._cmd_run` 里 `report` 生成后调用
4. **promote 流程**(规划中): 读飞书评论/checkbox → 自动归类到 Library
