import json
import random
import time
import urllib.error
import urllib.request

import pytest

import halo_cli.client as client_mod
from halo_cli.client import HaloAPIError, HaloClient, HaloClientConfig


class FakeResp:
    def __init__(self, status: int, body: str, headers=None):
        self.status = status
        self._body = body.encode("utf-8")
        self.headers = headers or {}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_lang_mode_and_bi(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("HALO_LANG", raising=False)
    assert "\n" in client_mod._bi("中", "EN")

    monkeypatch.setenv("HALO_LANG", "zh")
    assert client_mod._bi("中", "EN") == "中"

    monkeypatch.setenv("HALO_LANG", "en")
    assert client_mod._bi("中", "EN") == "EN"

    monkeypatch.setenv("HALO_LANG", "xx")
    assert "\n" in client_mod._bi("中", "EN")


def test_trace_headers_extracts_trace_ids():
    h = {
        "X-Request-Id": "abc",
        "Content-Type": "application/json",
        "TraceId": "t",
        "requestid": "r",
    }
    out = client_mod._trace_headers(h)
    assert "X-Request-Id" in out
    assert "TraceId" in out


def test_body_summary():
    c = HaloClient(HaloClientConfig(base_url="https://a.example", pat="pat_x"))
    assert c._body_summary(None)["present"] is False
    bs = c._body_summary(b"hello")
    assert bs["present"] is True
    assert bs["bytes"] == 5


def test_sleep_backoff_retry_after_caps(monkeypatch: pytest.MonkeyPatch):
    c = HaloClient(HaloClientConfig(base_url="https://a.example", pat="pat_x"))
    monkeypatch.setenv("HALO_RETRY_MAX_SLEEP_S", "1")
    assert c._sleep_backoff(base=0.5, attempt=3, retry_after_s=10) == 1.0


def test_request_success_updates_tracker(monkeypatch: pytest.MonkeyPatch, tmp_path):
    trace_path = tmp_path / "t.json"
    tracker = client_mod.ResponseTracker(trace_path=str(trace_path))
    client_mod.ResponseTracker._instance = tracker

    c = HaloClient(HaloClientConfig(base_url="https://a.example", pat="pat_x", timeout_s=1))

    def fake_urlopen(req, timeout=None):
        return FakeResp(200, json.dumps({"ok": True}), headers={"X-Request-Id": "rid"})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    out = c.request_json("GET", "/v")
    assert out == {"ok": True}
    last = c.get_last_trace()
    assert isinstance(last, dict)
    assert last.get("ok") is True
    assert last.get("response", {}).get("status") == 200
    assert last.get("response", {}).get("trace", {}).get("X-Request-Id") == "rid"
    assert trace_path.exists()


def test_request_http_error_404_not_retry(monkeypatch: pytest.MonkeyPatch, tmp_path):
    tracker = client_mod.ResponseTracker(trace_path=str(tmp_path / "t.json"))
    client_mod.ResponseTracker._instance = tracker

    c = HaloClient(HaloClientConfig(base_url="https://a.example", pat="pat_x", timeout_s=1))

    class E(urllib.error.HTTPError):
        def __init__(self):
            super().__init__(url="https://a.example/v", code=404, msg="not found", hdrs={"X-Request-Id": "r"}, fp=None)

        def read(self):
            return b"{}"

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_a, **_k: (_ for _ in ()).throw(E()))
    with pytest.raises(HaloAPIError) as ei:
        c.request_json("GET", "/v", retry=2)
    assert ei.value.status == 404
    last = c.get_last_trace()
    assert last and last.get("response", {}).get("status") == 404


def test_request_http_error_retry_then_success(monkeypatch: pytest.MonkeyPatch):
    c = HaloClient(HaloClientConfig(base_url="https://a.example", pat="pat_x", timeout_s=1))
    calls = {"n": 0}
    sleeps = []

    class E(urllib.error.HTTPError):
        def __init__(self):
            super().__init__(url="https://a.example/v", code=503, msg="busy", hdrs={"Retry-After": "1"}, fp=None)

        def read(self):
            return b"{}"

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise E()
        return FakeResp(200, "{}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(random, "random", lambda: 0.0)

    c.request_json("GET", "/v", retry=1)
    assert calls["n"] == 2
    assert any(abs(s - 1.0) < 0.01 for s in sleeps)


def test_request_urlerror_timeout(monkeypatch: pytest.MonkeyPatch):
    c = HaloClient(HaloClientConfig(base_url="https://a.example", pat="pat_x", timeout_s=1))

    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError(TimeoutError("timed out"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(HaloAPIError):
        c.request_json("GET", "/v", retry=0)
    last = c.get_last_trace()
    assert last and last.get("error", {}).get("type") in {"TimeoutError", "URLError"}


def test_request_urlerror_retry_then_success(monkeypatch: pytest.MonkeyPatch):
    c = HaloClient(HaloClientConfig(base_url="https://a.example", pat="pat_x", timeout_s=1))
    calls = {"n": 0}
    sleeps = []

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.URLError(ConnectionRefusedError(111, "refused"))
        return FakeResp(200, "{}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(random, "random", lambda: 0.0)

    c.request_json("GET", "/v", retry=1)
    assert calls["n"] == 2
    assert sleeps


def test_request_generic_exception_retry_then_success(monkeypatch: pytest.MonkeyPatch):
    c = HaloClient(HaloClientConfig(base_url="https://a.example", pat="pat_x", timeout_s=1))
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("boom")
        return FakeResp(200, "{}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    monkeypatch.setattr(random, "random", lambda: 0.0)
    c.request_json("GET", "/v", retry=1)
    assert calls["n"] == 2


def test_tracker_set_error_is_swallowed(monkeypatch: pytest.MonkeyPatch, tmp_path):
    tracker = client_mod.ResponseTracker(trace_path=str(tmp_path / "t.json"))
    monkeypatch.setattr(client_mod.os, "makedirs", lambda *_a, **_k: (_ for _ in ()).throw(OSError("no")))
    tracker.set({"a": 1})
    assert tracker.get() == {"a": 1}


def test_tracker_get_from_file(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"x": 1}), encoding="utf-8")
    tracker = client_mod.ResponseTracker(trace_path=str(p))
    assert tracker.get() == {"x": 1}


def test_mask_token_variants():
    assert client_mod._mask_token("") == ""
    assert client_mod._mask_token("short") == "***"
    assert "…" in client_mod._mask_token("a" * 20)


def test_request_json_empty_body_returns_none(monkeypatch: pytest.MonkeyPatch):
    c = HaloClient(HaloClientConfig(base_url="https://a.example", pat="pat_x"))

    monkeypatch.setattr(c, "request", lambda *_a, **_k: (204, {}, ""))
    assert c.request_json("GET", "/v") is None


def test_wrapper_methods_call_correct_paths(monkeypatch: pytest.MonkeyPatch):
    c = HaloClient(HaloClientConfig(base_url="https://a.example", pat="pat_x"))
    calls = []

    def fake_request_json(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {}

    monkeypatch.setattr(c, "request_json", fake_request_json)

    c.whoami()
    c.list_posts_console(page=1, size=2, field_selector=["a"], keyword="k", publish_phase="DRAFT")
    c.draft_post_console({"post": {}})
    c.update_draft_post_console("n", {"post": {}})
    c.get_post_console("n")
    c.publish_post_console("n", head_snapshot="h", async_=True)
    c.list_posts(page=1, size=2)
    c.list_tags(page=1, size=2)
    c.list_categories(page=1, size=2)
    c.list_attachments_uc(page=1, size=2)
    c.delete_post_console("n")
    c.get_post("n")
    c.create_post_crd(title="t", slug="s", published=True)
    with pytest.raises(HaloAPIError):
        c.replace_post_crd({"metadata": {}})
    c.replace_post_crd({"metadata": {"name": "p"}})
    c.set_post_content("p", raw_markdown="#", raw_type="markdown", content="<p></p>")
    c.fetch_post_head_content("p")
    c.fetch_post_release_content("p")
    c.try_publish_console("p")

    assert any(m == "GET" and "/users/-" in p for m, p, _ in calls)
    assert any(m == "GET" and p.endswith("/posts") for m, p, _ in calls)

