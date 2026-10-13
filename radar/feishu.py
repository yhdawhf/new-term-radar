"""New-lead notifications for a Feishu custom bot; no new leads means no message.

FEISHU_WEBHOOK_URL and optional FEISHU_SECRET are environment secrets. A small
persistent outbox survives failed delivery and is shared by sources/daily via state.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import UA, snap

BATCH = 8
MAX_PER_RUN = 24


class FeishuError(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def signature(timestamp: str, secret: str) -> str:
    key = f"{timestamp}\n{secret}".encode()
    return base64.b64encode(hmac.new(key, b"", hashlib.sha256).digest()).decode()


def report_url() -> str:
    repo, run = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_RUN_ID")
    if repo and run:
        return f"https://github.com/{repo}/actions/runs/{run}"
    return ""


def _webhook() -> str:
    url = os.environ.get("FEISHU_WEBHOOK_URL", "").strip()
    if not url:
        raise FeishuError("未配置 FEISHU_WEBHOOK_URL")
    if not re.fullmatch(r"https://open\.feishu\.cn/open-apis/bot/v2/hook/[A-Za-z0-9_-]+", url):
        raise FeishuError("FEISHU_WEBHOOK_URL 必须是飞书自定义机器人的 HTTPS Webhook 地址")
    return url


def _post(url: str, body: dict) -> None:
    raw = json.dumps(body, ensure_ascii=False).encode()
    if len(raw) > 20000:
        raise FeishuError("飞书消息超过 20 KB，未发送")
    req = urllib.request.Request(url, data=raw, method="POST", headers={
        "Content-Type": "application/json", "User-Agent": UA})
    try:
        with urllib.request.build_opener(_NoRedirect()).open(req, timeout=25) as res:
            answer = json.load(res)
    except urllib.error.HTTPError as exc:
        raise FeishuError(f"飞书 HTTP {exc.code}；待发消息保留") from None
    except (OSError, ValueError) as exc:
        # Transport exceptions may contain the secret URL: never log their text.
        raise FeishuError(f"飞书请求失败（{type(exc).__name__}）；待发消息保留") from None
    if not isinstance(answer, dict) or answer.get("code") != 0:
        code = answer.get("code") if isinstance(answer, dict) else None
        safe = str(code) if isinstance(code, int) else "未知"
        raise FeishuError(f"飞书拒绝消息，错误码 {safe}；请检查机器人签名/关键词等设置")


def send(text: str) -> None:
    url = _webhook()
    body = {"msg_type": "text", "content": {"text": text}}
    secret = os.environ.get("FEISHU_SECRET", "").strip()
    if secret:
        timestamp = str(int(time.time()))
        body.update(timestamp=timestamp, sign=signature(timestamp, secret))
    _post(url, body)


def _plain(text: str, limit: int) -> str:
    # Feishu interprets <at> even in text messages; source content must not ping people.
    return " ".join(str(text).split()).replace("<", "‹").replace(">", "›")[:limit]


def message(rows: list[dict]) -> str:
    lines = [f"新词雷达：发现 {len(rows)} 个新候选词", ""]
    for row in rows:
        lines.append(f"• {_plain(row['term'], 100)}")
        lines.append("  来源：" + _plain("；".join(row.get("signals", [])), 160))
        if row.get("examples"):
            lines.append("  例子：" + _plain(row["examples"][0], 120))
        if row.get("named") is None:
            lines.append("  名字评分：未评分，需自行核实")
        else:
            lines.append(f"  名字评分：{row['named']:.2f}")
        links = row.get("variants", [])[1:3]
        if links:
            lines.append("  搜索写法：" + _plain("、".join(links), 120))
        lines.append("")
    urls = list(dict.fromkeys(r.get("report_url", "") for r in rows if r.get("report_url")))
    if not urls and report_url():
        urls = [report_url()]
    if urls:
        lines += ["完整报告：", *urls[:3]]
    return "\n".join(lines)


def _save(path: Path, data: dict) -> None:
    temp = path.with_suffix(".tmp")
    snap.save(temp, data)
    temp.replace(path)


def notify(state: Path, rows: list[dict]) -> dict:
    if not os.environ.get("FEISHU_WEBHOOK_URL", "").strip():
        return {"skipped": True}
    destination = hashlib.sha256(_webhook().encode()).hexdigest()
    path = state / "feishu_notifications.json.gz"
    data = snap.load(path)
    if data is None or data.get("destination") != destination:
        data = {"destination": destination, "sent": [], "pending": {}}
    sent = set(data["sent"])
    pending = data["pending"]
    queued = 0
    for row in rows:
        term = row["term"]
        if term not in sent and term not in pending:
            pending[term] = {**row, "report_url": report_url()}
            queued += 1
    if not pending:
        return {"sent": 0, "queued": 0, "pending": 0}
    # Save BEFORE sending: upstream snapshots already consumed these discoveries.
    _save(path, data)
    todo = list(pending)[:MAX_PER_RUN]
    delivered = 0
    for start in range(0, len(todo), BATCH):
        terms = todo[start:start + BATCH]
        send(message([pending[t] for t in terms]))
        for term in terms:
            del pending[term]
            data["sent"].append(term)
        delivered += len(terms)
        _save(path, data)
    return {"sent": delivered, "queued": queued, "pending": len(pending)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Send one Feishu connection test; no radar collection.")
    parser.add_argument("--test", action="store_true", required=True)
    parser.parse_args()
    text = "新词雷达：飞书连接测试成功。\n今后仅发现新候选词时推送，没有新词时保持安静。"
    if report_url():
        text += "\n测试运行：" + report_url()
    try:
        send(text)
    except FeishuError as exc:
        print(str(exc))
        return 1
    print("飞书连接测试：API 返回 code=0，消息已接受")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
