import time

import pytest

from halo_cli.publish import PublishInput, _wait_for_published, publish_markdown


class FakeClient:
    def __init__(self):
        self.calls = []
        self._get_calls = 0

    def list_posts_console(self, *args, **kwargs):
        self.calls.append(("list_posts_console", args, kwargs))
        return {"items": []}

    def get_post_console(self, name: str):
        self.calls.append(("get_post_console", name))
        raise Exception("should be patched")

    def draft_post_console(self, post_request):
        self.calls.append(("draft_post_console", post_request))
        return {"metadata": {"name": post_request["post"]["metadata"].get("name") or "post-1"}, "spec": {}}

    def update_draft_post_console(self, name: str, post_request):
        self.calls.append(("update_draft_post_console", name, post_request))
        return {"metadata": {"name": name}, "spec": {}}

    def set_post_content(self, name: str, *, raw_markdown: str, raw_type: str, content: str):
        self.calls.append(("set_post_content", name, raw_type))
        return {"ok": True}

    def publish_post_console(self, name: str, head_snapshot=None, async_=False):
        self.calls.append(("publish_post_console", name, head_snapshot, async_))
        return {"ok": True}


def test_publish_markdown_creates_and_sets_content(monkeypatch: pytest.MonkeyPatch):
    client = FakeClient()

    def fake_get_post_console(name: str):
        raise RuntimeError("404")

    monkeypatch.setattr(client, "get_post_console", fake_get_post_console)

    result = publish_markdown(
        client,
        PublishInput(
            title="t",
            slug="s",
            markdown="# hi",
            publish=False,
            tags=["a"],
            categories=["c"],
        ),
    )

    assert result["slug"] == "s"
    assert any(c[0] == "draft_post_console" for c in client.calls)
    assert any(c[0] == "set_post_content" for c in client.calls)


def test_wait_for_published_eventually_true(monkeypatch: pytest.MonkeyPatch):
    class C:
        def __init__(self):
            self.n = 0

        def get_post_console(self, name: str):
            self.n += 1
            if self.n < 3:
                return {"spec": {"publish": False}, "status": {"phase": "DRAFT"}}
            return {"spec": {"publish": True}, "status": {"phase": "PUBLISHED"}}

    c = C()
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    _wait_for_published(c, "x", timeout_s=5)

