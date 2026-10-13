import copy

import pytest

from radar import config, goanyapi, i18n


@pytest.fixture(autouse=True)
def english(monkeypatch):
    i18n.set_lang("en")
    # Unit tests must never deliver messages through developer credentials.
    monkeypatch.delenv("FEISHU_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("FEISHU_SECRET", raising=False)
    monkeypatch.delenv("GOANYAPI_API_KEY", raising=False)   # the optional source is off unless a test turns it on

    def no_network(*a, **k):
        raise goanyapi.GoAnyError("no network in tests")
    monkeypatch.setattr(goanyapi, "call", no_network)


@pytest.fixture
def cfg(tmp_path):
    c = copy.deepcopy(config.DEFAULTS)
    c["_dir"] = tmp_path
    return c
