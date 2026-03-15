import json
from types import SimpleNamespace

import pytest

import halo_cli.cli as cli


def test_build_parser_has_commands():
    p = cli.build_parser()
    assert p.prog == "halo-ctl"


def test_split_csv():
    assert cli._split_csv(None) is None
    assert cli._split_csv("") is None
    assert cli._split_csv("a,b") == ["a", "b"]
    assert cli._split_csv([" a ", "", "b"]) == ["a", "b"]


def test_env_reads_and_strips(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("X", "  v ")
    assert cli._env("X") == "v"


def test_build_client_missing_env_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("HALO_BASE_URL", raising=False)
    monkeypatch.delenv("HALO_PAT", raising=False)
    args = SimpleNamespace(base_url=None, pat=None, timeout=None)
    with pytest.raises(cli.HaloAPIError):
        cli._build_client(args)


def test_cmd_publish_json_calls_publish(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    payload = {
        "title": "t",
        "slug": "s",
        "markdown": "# hi",
        "publish": True,
        "tags": ["a"],
        "categories": "c1,c2",
        "visible": "PUBLIC",
    }

    monkeypatch.setattr(cli, "_read_text", lambda path: json.dumps(payload, ensure_ascii=False))
    monkeypatch.setattr(cli, "_build_client", lambda args: object())

    captured = {}

    def fake_publish_markdown(_client, data):
        captured["title"] = data.title
        captured["slug"] = data.slug
        captured["publish"] = data.publish
        captured["tags"] = data.tags
        captured["categories"] = data.categories
        return {"ok": True}

    monkeypatch.setattr(cli, "publish_markdown", fake_publish_markdown)

    args = SimpleNamespace(file="-", dump_input=False, base_url="x", pat="y", timeout=None)
    rc = cli.cmd_publish_json(args)
    assert rc == 0
    assert captured["title"] == "t"
    assert captured["slug"] == "s"
    assert captured["publish"] is True
    assert captured["tags"] == ["a"]
    assert captured["categories"] == ["c1", "c2"]

    out = capsys.readouterr().out
    assert '"ok": true' in out


def test_cmd_sync_openapi_outputs_paths(monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setattr(cli, "_build_client", lambda args: object())

    spec = cli.sync_openapi_specs  # type: ignore[attr-defined]
    _ = spec

    class FakeSpec:
        def __init__(self):
            self.name = "x"
            self.url = "/v3/api-docs"

    monkeypatch.setattr(cli, "sync_openapi_specs", lambda *_a, **_k: [FakeSpec()])
    monkeypatch.setattr(cli, "generate_api_index", lambda *_a, **_k: tmp_path / "API_INDEX.md")
    monkeypatch.setattr(cli, "generate_error_code_table", lambda *_a, **_k: tmp_path / "ERROR_CODES.md")

    args = SimpleNamespace(out=str(tmp_path), no_overwrite=False, base_url="x", pat="y", timeout=None)
    rc = cli.cmd_sync_openapi(args)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["written"][0]["name"] == "x"
