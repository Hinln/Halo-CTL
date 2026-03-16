import json
import urllib.error
import urllib.request
import random
import time

import pytest

from halo_cli.client import HaloClient, HaloClientConfig, HaloAPIError


class FakeHTTPResponse:
    def __init__(self, status: int, body: str):
        self.status = status
        self._body = body.encode("utf-8")
        self.headers = {"Content-Type": "application/json"}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_request_json_url_rejects_cross_origin():
    c = HaloClient(HaloClientConfig(base_url="https://a.example", pat="pat_x"))
    with pytest.raises(HaloAPIError):
        c.request_json_url("GET", "https://b.example/v3/api-docs")


def test_request_json_url_converts_to_path(monkeypatch: pytest.MonkeyPatch):
    c = HaloClient(HaloClientConfig(base_url="https://a.example", pat="pat_x"))

    captured = {}

    def fake_request_json(method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        return {"ok": True}

    monkeypatch.setattr(c, "request_json", fake_request_json)
    out = c.request_json_url("GET", "https://a.example/v3/api-docs?x=1")
    assert out == {"ok": True}
    assert captured["path"] == "/v3/api-docs?x=1"


def test_request_json_parses_json(monkeypatch: pytest.MonkeyPatch):
    c = HaloClient(HaloClientConfig(base_url="https://a.example", pat="pat_x"))

    def fake_urlopen(req, timeout=None):
        return FakeHTTPResponse(200, json.dumps({"hello": "world"}))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert c.request_json("GET", "/v") == {"hello": "world"}


def test_request_json_non_json_raises(monkeypatch: pytest.MonkeyPatch):
    c = HaloClient(HaloClientConfig(base_url="https://a.example", pat="pat_x"))

    def fake_urlopen(req, timeout=None):
        return FakeHTTPResponse(200, "not-json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(HaloAPIError):
        c.request_json("GET", "/v")


def test_request_retries_on_500(monkeypatch: pytest.MonkeyPatch):
    c = HaloClient(HaloClientConfig(base_url="https://a.example", pat="pat_x", timeout_s=1))
    calls = {"n": 0}

    class FakeHTTPError(urllib.error.HTTPError):
        def __init__(self):
            super().__init__(
                url="https://a.example/v",
                code=500,
                msg="err",
                hdrs=None,
                fp=None,
            )

        def read(self):
            return b"{}"

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] < 2:
            raise FakeHTTPError()
        return FakeHTTPResponse(200, "{}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    c.request_json("GET", "/v", retry=1)
    assert calls["n"] == 2


def test_response_tracker_persists(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from halo_cli import client as client_mod

    trace_path = tmp_path / "trace.json"
    tracker = client_mod.ResponseTracker(trace_path=str(trace_path))
    client_mod.ResponseTracker._instance = tracker

    c = HaloClient(HaloClientConfig(base_url="https://a.example", pat="pat_x"))

    def fake_urlopen(req, timeout=None):
        return FakeHTTPResponse(200, "{}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    c.request_json("GET", "/v")
    data = c.get_last_trace()
    assert isinstance(data, dict)
    assert data.get("ok") is True
    assert trace_path.exists()


def test_http_retry_respects_retry_after(monkeypatch: pytest.MonkeyPatch):
    c = HaloClient(HaloClientConfig(base_url="https://a.example", pat="pat_x"))
    sleeps = []

    class FakeHTTPError(urllib.error.HTTPError):
        def __init__(self):
            super().__init__(url="https://a.example/v", code=503, msg="err", hdrs={"Retry-After": "2"}, fp=None)

        def read(self):
            return b"{}"

    def fake_urlopen(req, timeout=None):
        raise FakeHTTPError()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(random, "random", lambda: 0.0)

    with pytest.raises(HaloAPIError):
        c.request_json("GET", "/v", retry=1)
    assert any(abs(s - 2.0) < 0.01 for s in sleeps)


def test_request_401_raises_with_status_and_body(monkeypatch: pytest.MonkeyPatch):
    c = HaloClient(HaloClientConfig(base_url="https://a.example", pat="pat_xxxxxxxxxxxxxxxx"))

    class FakeHTTPError(urllib.error.HTTPError):
        def __init__(self):
            super().__init__(url="https://a.example/v", code=401, msg="unauthorized", hdrs={"Content-Type": "application/json"}, fp=None)

        def read(self):
            return b"{\"message\":\"unauthorized\"}"

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_a, **_k: (_ for _ in ()).throw(FakeHTTPError()))
    with pytest.raises(HaloAPIError) as e:
        c.request_json("GET", "/v", retry=0)
    assert e.value.status == 401
    assert "HTTP 401" in str(e.value)
    assert "unauthorized" in (e.value.body or "")


def test_request_500_raises(monkeypatch: pytest.MonkeyPatch):
    c = HaloClient(HaloClientConfig(base_url="https://a.example", pat="pat_x"))

    class FakeHTTPError(urllib.error.HTTPError):
        def __init__(self):
            super().__init__(url="https://a.example/v", code=500, msg="err", hdrs={"Content-Type": "application/json"}, fp=None)

        def read(self):
            return b"{}"

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_a, **_k: (_ for _ in ()).throw(FakeHTTPError()))
    with pytest.raises(HaloAPIError) as e:
        c.request_json("GET", "/v", retry=0)
    assert e.value.status == 500
    assert "HTTP 500" in str(e.value)


def test_dump_http_prints_sanitized_authorization(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    c = HaloClient(HaloClientConfig(base_url="https://a.example", pat="pat_xxxxxxxxxxxxxxxx"))

    def fake_urlopen(req, timeout=None):
        return FakeHTTPResponse(200, "{}")

    monkeypatch.setenv("HALO_DUMP_HTTP", "1")
    monkeypatch.setenv("HALO_TRACE_FIXED_TS", "2026-03-16T00:14:54+0800")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    _ = c.request_json("GET", "/v")
    err = capsys.readouterr().err
    assert "2026-03-16T00:14:54+0800" in err
    assert "Authorization:" in err
    assert "pat_xxxxxxxxxxxxxxxx" not in err
