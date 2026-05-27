# Contributing

感谢愿意贡献!这是一个很小的本机 CLI,目标是简单、可审查、不出本机。

## 开发环境

```bash
git clone https://github.com/your-org/devlog-cli.git
cd devlog-cli
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## 提交前自检

```bash
ruff check .
pytest
```

CI 在 Ubuntu / macOS × Python 3.10 / 3.11 / 3.12 全跑这两个命令,本地通过即可。

## 设计原则(改动前请先对齐)

1. **数据不出本机** — 任何采集 / 脱敏 / 总结路径都必须本地完成;新增网络出站调用需在 PR 描述里特别说明
2. **后端可插拔** — 不绑死任何 LLM 厂商,所有总结后端走 `subprocess` + stdin
3. **失败隔离** — 单个 source 损坏不能拖垮整次运行;`collect_all` 用 try/except 包住每个 source
4. **人审优先** — 输出必须保留 `[ ]` checkbox 和 diff 段,任何对模板的改动都要更新对应测试

## 新增一个 source

1. 在 `devlog/collectors.py` 里加 `_iter_xxx` 函数,返回 `Iterator[Message]`
2. 在 `_collect_one` 加 `kind` 分支
3. 在 `tests/test_collectors.py` 加单测(用 tmp_path 造假数据,**禁止**依赖本机真实路径)
4. 更新 README 的"配置"段

## 新增一个 summarizer 后端

只要它能 **从 stdin 读 prompt、写到 stdout**,就直接在 `config.toml` 的 `[[backends]]` 配置 `command`,无需改代码。

## 提交规范

- commit message 用 [Conventional Commits](https://www.conventionalcommits.org/):`feat:` / `fix:` / `docs:` / `test:` / `refactor:` / `chore:`
- 一个 PR 一件事;diff 控制在 ~300 行内更易 review
