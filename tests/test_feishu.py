import io
import json
import urllib.error

import pytest

from radar import __main__ as cli
from radar import feishu, snap

WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/test-hook"


@pytest.fixture
def bot(monkeypatch):
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", WEBHOOK)


def row(term="qwen3.9"):
    return {"term": term, "signals": ["HF new at #4"], "examples": ["Qwen/Qwen3.9"], "variants": []}


def test_signature_matches_fixed_vector():
    assert feishu.signature("1700000000", "secret") == "fiWS2+gh28DOydAv7hzONH/mDn9+b1Y4Y5ivXWXy8vA="


def test_signed_request_checks_application_success(bot, monkeypatch):
    monkeypatch.setenv("FEISHU_SECRET", "secret")
    monkeypatch.setattr(feishu.time, "time", lambda: 1700000000)
    requests = []

    class Opener:
        def open(self, req, timeout):
            requests.append(req)
            return io.BytesIO(b'{"code":0,"msg":"success"}')

    monkeypatch.setattr(feishu.urllib.request, "build_opener", lambda *a: Opener())
    feishu.send("新词雷达：测试")
    body = json.loads(requests[0].data)
    assert body["timestamp"] == "1700000000"
    assert body["sign"] == "fiWS2+gh28DOydAv7hzONH/mDn9+b1Y4Y5ivXWXy8vA="
    assert body["content"]["text"] == "新词雷达：测试"


@pytest.mark.parametrize("answer", [b'{"code":19021,"msg":"sign failed"}', b'{}', b'[]'])
def test_http_success_is_not_enough(bot, monkeypatch, answer):
    class Opener:
        def open(self, *a, **k):
            return io.BytesIO(answer)

    monkeypatch.setattr(feishu.urllib.request, "build_opener", lambda *a: Opener())
    with pytest.raises(feishu.FeishuError, match="飞书拒绝消息"):
        feishu.send("test")


def test_network_errors_do_not_expose_webhook(bot, monkeypatch):
    class Opener:
        def open(self, *a, **k):
            raise urllib.error.URLError("failed request to " + WEBHOOK)

    monkeypatch.setattr(feishu.urllib.request, "build_opener", lambda *a: Opener())
    with pytest.raises(feishu.FeishuError) as exc:
        feishu.send("test")
    assert WEBHOOK not in str(exc.value) and "test-hook" not in str(exc.value)


@pytest.mark.parametrize("url", ["http://open.feishu.cn/open-apis/bot/v2/hook/abc", "https://example.com/hook/abc"])
def test_only_official_feishu_webhook_is_accepted(monkeypatch, url):
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", url)
    with pytest.raises(feishu.FeishuError, match="HTTPS Webhook"):
        feishu.send("test")


def test_missing_hook_is_quiet(tmp_path):
    assert feishu.notify(tmp_path, [row()]) == {"skipped": True}
    assert not list(tmp_path.iterdir())


def test_once_per_term_across_runs_and_no_empty_messages(bot, tmp_path, monkeypatch):
    messages = []
    monkeypatch.setattr(feishu, "send", messages.append)
    assert feishu.notify(tmp_path, []) == {"sent": 0, "queued": 0, "pending": 0}
    assert feishu.notify(tmp_path, [row()])["sent"] == 1
    assert feishu.notify(tmp_path, [row()])["sent"] == 0
    assert len(messages) == 1 and "qwen3.9" in messages[0]
    data = snap.load(tmp_path / "feishu_notifications.json.gz")
    assert data["pending"] == {} and data["sent"] == ["qwen3.9"]
    assert WEBHOOK not in json.dumps(data)


def test_failed_delivery_retries_even_without_new_leads(bot, tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/radar")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")

    def down(text):
        raise feishu.FeishuError("network unavailable")

    monkeypatch.setattr(feishu, "send", down)
    with pytest.raises(feishu.FeishuError):
        feishu.notify(tmp_path, [row()])
    data = snap.load(tmp_path / "feishu_notifications.json.gz")
    assert data["sent"] == [] and "qwen3.9" in data["pending"]
    messages = []
    monkeypatch.setattr(feishu, "send", messages.append)
    monkeypatch.setenv("GITHUB_RUN_ID", "456")
    assert feishu.notify(tmp_path, [])["sent"] == 1
    assert "https://github.com/owner/radar/actions/runs/123" in messages[0]


def test_partial_success_does_not_resend_successful_batch(bot, tmp_path, monkeypatch):
    messages = []

    def send(text):
        if messages:
            raise feishu.FeishuError("second batch failed")
        messages.append(text)

    monkeypatch.setattr(feishu, "send", send)
    with pytest.raises(feishu.FeishuError):
        feishu.notify(tmp_path, [row(f"model{i}") for i in range(9)])
    data = snap.load(tmp_path / "feishu_notifications.json.gz")
    assert len(data["sent"]) == 8 and list(data["pending"]) == ["model8"]
    monkeypatch.setattr(feishu, "send", messages.append)
    assert feishu.notify(tmp_path, [])["sent"] == 1
    assert "model8" in messages[-1] and "model0" not in messages[-1]


def test_message_is_bounded_and_source_cannot_ping_everyone():
    rows = [{"term": "😀" * 10000, "signals": ['<at user_id="all">everyone</at>' + "😀" * 10000],
             "examples": ["😀" * 10000], "variants": ["x", "😀" * 10000]} for _ in range(feishu.BATCH)]
    text = feishu.message(rows)
    assert "<at" not in text
    assert len(json.dumps({"msg_type": "text", "content": {"text": text}}, ensure_ascii=False).encode()) < 20000


def test_cli_keeps_report_and_pending_outbox_when_delivery_fails(bot, tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text('{"lang":"zh"}')
    state, out = tmp_path / "state", tmp_path / "report.md"
    monkeypatch.setattr(cli.sources, "hf_new", lambda *a: {"models": 100, "first_run": False, "terms": [
        {**row(), "recent": 1, "note": "HF new at #4"}]})

    def down(text):
        raise feishu.FeishuError("test delivery failed")

    monkeypatch.setattr(feishu, "send", down)
    args = ["daily", "--config", str(cfg), "--state", str(state), "--out", str(out),
            "--skip", "x,breakout,sitemaps,newsites,gsc,review,judge,usecases"]
    assert cli.main(args) == 1
    assert "test delivery failed" in out.read_text()
    assert "error" in json.loads(out.with_suffix(".json").read_text())["notifications"]
    monkeypatch.setattr(cli.sources, "hf_new", lambda *a: {"models": 100, "first_run": False, "terms": []})
    messages = []
    monkeypatch.setattr(feishu, "send", messages.append)
    assert cli.main(args) == 0
    assert len(messages) == 1 and "qwen3.9" in messages[0]


def test_sources_writes_delivery_failure_in_report(tmp_path, monkeypatch):
    cfg, out = tmp_path / "config.json", tmp_path / "sources.md"
    cfg.write_text('{"lang":"zh"}')
    monkeypatch.setattr(cli.sources, "hf_new", lambda *a: {"models": 100, "terms": []})

    def down(*a):
        raise feishu.FeishuError("delivery unavailable")

    monkeypatch.setattr(feishu, "notify", down)
    assert cli.main(["sources", "--config", str(cfg), "--state", str(tmp_path / "state"),
                     "--out", str(out), "--skip", "x,judge"]) == 1
    assert "飞书推送:FeishuError: delivery unavailable" in out.read_text()
