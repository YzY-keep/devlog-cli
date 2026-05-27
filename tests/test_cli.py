from datetime import date

from devlog.cli import main


def test_version(capsys):
    code = main(["version"])
    assert code == 0
    assert capsys.readouterr().out.strip()


def test_init_writes_config(tmp_path, capsys):
    cfg = tmp_path / "config.toml"
    code = main(["--config", str(cfg), "init"])
    assert code == 0
    assert cfg.exists()
    body = cfg.read_text(encoding="utf-8")
    assert "[[sources]]" in body
    assert "[[backends]]" in body


def test_run_with_no_messages(tmp_path, capsys, monkeypatch):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '''output_dir = "{out}"
state_dir = "{state}"
[[sources]]
name = "x"
kind = "jsonl"
path = "{empty}"
[[backends]]
name = "none"
[feishu]
enabled = false
'''.format(
            out=tmp_path / "out",
            state=tmp_path / "state",
            empty=tmp_path / "no_such",
        ),
        encoding="utf-8",
    )
    code = main(["--config", str(cfg), "run", "--date", date.today().isoformat()])
    assert code == 1  # no messages
