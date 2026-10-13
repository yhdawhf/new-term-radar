"""Check observable CLI behavior, failure visibility and log/report separation."""
import json

from radar import __main__ as cli
from radar.diagnostics import configure


def test_verbose_daily_keeps_report_clean_and_exposes_nested_failure(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"lang": "zh"}))
    monkeypatch.setattr(cli.sources, "hf_new", lambda *a: {"models": 100, "first_run": True, "terms": []})
    monkeypatch.setattr(cli.sitemaps, "diff", lambda *a: {"sites": {"example": {"error": "HTTP 403"}}, "terms": []})
    out = tmp_path / "report.md"
    trace = tmp_path / "nested" / "run.log"
    try:
        assert cli.main(["daily", "--config", str(cfg), "--state", str(tmp_path / "state"), "--out", str(out),
                         "--skip", "x,breakout,newsites,judge,review", "--verbose", "--log-file", str(trace)]) == 0
        captured = capsys.readouterr()
        assert captured.out == out.read_text() + "\n"
        assert "[启动]" not in captured.out
        for expected in ("[启动]", "[X] 跳过", "首次快照", "[Sitemap/example] HTTP 403", "[结束]"):
            assert expected in captured.err and expected in trace.read_text()
        assert out.with_suffix(".json").exists()
    finally:
        configure(False)


def test_signal_failure_is_logged_and_later_stage_can_run(tmp_path):
    trace = tmp_path / "run.log"
    configure(False, str(trace))
    try:
        def down():
            raise OSError("network unavailable")
        assert "error" in cli.run(down, label="HF")
        assert cli.run(lambda: {"recorded": 1}, label="SQLite") == {"recorded": 1}
        text = trace.read_text()
        assert "[HF] 失败" in text and "network unavailable" in text and "[SQLite] 完成" in text
    finally:
        configure(False)


def test_default_cli_emits_no_diagnostics(tmp_path, capsys):
    cfg = tmp_path / "config.json"
    cfg.write_text("{}")
    cli.main(["daily", "--config", str(cfg), "--state", str(tmp_path / "state"),
              "--skip", "x,hf,breakout,sitemaps,newsites,gsc,review,judge"])
    captured = capsys.readouterr()
    assert "New-term radar" in captured.out
    assert captured.err == ""


def test_daily_keywords_keep_recent_names_report_storage_and_logs(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text('{}')
    state = tmp_path / "state"
    conn = cli.store.connect(state)
    cli.store.record(conn, [{"term": "qwen3.9", "kinds": ["hf"], "signals": ["HF"]}])
    conn.close()
    keywords = {"names": ["qwen3.9"], "proposed": 1, "relevant": 1, "kept": 1,
                "volume_month": "2026-09", "benchmark": "gpts", "rows": [
                    {"phrase": "local ai model", "kind": "generic", "names": ["qwen3.9"],
                     "brand": False, "evidence": "Runs locally", "volume": 1000,
                     "no_data": True, "decision": "watch"}]}

    def build_keywords(cfg, state, names, repos):
        assert names == ["qwen3.9"]
        return keywords

    monkeypatch.setattr(cli.usecases, "run", build_keywords)
    out, trace = tmp_path / "report.md", tmp_path / "run.log"
    try:
        assert cli.main(["daily", "--config", str(cfg), "--state", str(state), "--out", str(out),
                         "--skip", "x,hf,breakout,sitemaps,newsites,gsc,review,judge", "--log-file", str(trace)]) == 0
        assert json.loads(out.with_suffix(".json").read_text())["keywords"] == keywords
        assert "**local ai model**" in out.read_text()
        with cli.store.connect(state) as conn:
            assert conn.execute("SELECT signals FROM leads WHERE term = ?", ("local ai model",)).fetchone() == ('["usecase"]',)
        assert "[关键词 SQLite 入库] 完成 {'recorded': 1}" in trace.read_text()
    finally:
        configure(False)
