from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional
import time
import sys

from .client import HaloAPIError, HaloClient, slugify_dns_label


def _find_first_key(obj: Any, key: str) -> Optional[Any]:
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            found = _find_first_key(v, key)
            if found is not None:
                return found
    if isinstance(obj, list):
        for item in obj:
            found = _find_first_key(item, key)
            if found is not None:
                return found
    return None


def _extract_snapshot_name(post_obj: Mapping[str, Any]) -> Optional[str]:
    for k in ["headSnapshot", "headSnapshotName", "snapshotName", "baseSnapshotName"]:
        v = _find_first_key(post_obj, k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _markdown_to_html(markdown_text: str) -> str:
    try:
        import markdown as md
    except Exception as e:
        raise HaloAPIError(
            "当前脚本需要将 Markdown 渲染为 HTML 才能在文章页正常排版。\n"
            "请先安装依赖：pip install -r requirements.txt"
        ) from e

    return md.markdown(
        markdown_text,
        extensions=[
            "extra",
            "tables",
            "fenced_code",
            "codehilite",
            "toc",
            "sane_lists",
            "smarty",
        ],
        output_format="html5",
    )


def _build_post_request(
    *,
    name: Optional[str],
    title: str,
    slug: str,
    markdown: str,
    publish: bool,
    tags: Optional[list[str]] = None,
    categories: Optional[list[str]] = None,
    cover: Optional[str] = None,
    visible: str = "PUBLIC",
    allow_comment: bool = True,
) -> Dict[str, Any]:
    post = {
        "apiVersion": "content.halo.run/v1alpha1",
        "kind": "Post",
        "metadata": ({"name": name} if name else {"generateName": "post-"}),
        "spec": {
            "title": title,
            "slug": slug,
            "publish": bool(publish),
            "allowComment": bool(allow_comment),
            "deleted": False,
            "pinned": False,
            "priority": 0,
            "visible": visible,
            "excerpt": {"autoGenerate": True},
        },
    }
    if tags:
        post["spec"]["tags"] = tags
    if categories:
        post["spec"]["categories"] = categories
    if cover:
        post["spec"]["cover"] = cover
    return {
        "post": post,
        "content": {
            "rawType": "markdown",
            "raw": markdown,
            "content": markdown,
        },
    }


@dataclass(frozen=True)
class PublishInput:
    title: str
    markdown: str
    slug: Optional[str] = None
    publish: bool = True
    tags: Optional[list[str]] = None
    categories: Optional[list[str]] = None
    cover: Optional[str] = None
    visible: str = "PUBLIC"
    allow_comment: bool = True


def publish_markdown(client: HaloClient, data: PublishInput) -> Dict[str, Any]:
    slug = data.slug or slugify_dns_label(data.title)
    desired_name = slugify_dns_label(slug)
    existing_name = _find_post_name_by_slug(client, slug=slug)
    name = existing_name or desired_name
    _log(f"post={name} slug={slug}")
    existing_version = None
    existing_head_snapshot = None
    if existing_name:
        try:
            _log("fetch existing post")
            crd = client.get_post_console(existing_name)
            if isinstance(crd, dict):
                existing_version = (crd.get("metadata") or {}).get("version")
                existing_head_snapshot = (crd.get("spec") or {}).get("headSnapshot")
                name = existing_name
            else:
                existing_name = None
        except HaloAPIError as e:
            if e.status != 404:
                raise
            existing_name = None

    post_request = _build_post_request(
        name=name,
        title=data.title,
        slug=slug,
        markdown=data.markdown,
        publish=False,
        tags=data.tags,
        categories=data.categories,
        cover=data.cover,
        visible=data.visible,
        allow_comment=data.allow_comment,
    )
    html = _markdown_to_html(data.markdown)
    if existing_version is not None:
        post_request["post"].setdefault("metadata", {})["version"] = existing_version
    if existing_head_snapshot:
        post_request["post"].setdefault("spec", {})["headSnapshot"] = existing_head_snapshot

    post = None
    try:
        if existing_name:
            _log("update draft post")
            post = client.update_draft_post_console(name, post_request)
        else:
            _log("create draft post")
            post_request_create = _build_post_request(
                name=desired_name,
                title=data.title,
                slug=slug,
                markdown=data.markdown,
                publish=False,
                tags=data.tags,
                categories=data.categories,
                cover=data.cover,
                visible=data.visible,
                allow_comment=data.allow_comment,
            )
            post = client.draft_post_console(post_request_create)
            created_name = _extract_post_name_from_response(post) or _find_post_name_by_slug(client, slug=slug)
            if created_name:
                name = created_name
                _log(f"server assigned name={name}")
    except HaloAPIError as e:
        if e.status in {400, 404, 409, 500}:
            _log(f"upsert failed; try find existing by slug/title. status={e.status}")
            found_name = _find_post_name_by_slug(client, slug=slug) or _find_post_name_by_keyword(client, keyword=data.title)
            if not found_name:
                raise
            name = found_name
            _log(f"use existing name={name}")
            crd = client.get_post_console(name)
            if isinstance(crd, dict):
                existing_version = (crd.get("metadata") or {}).get("version")
                if existing_version is not None:
                    post_request["post"].setdefault("metadata", {})["version"] = existing_version
            _log("retry update draft post")
            post = client.update_draft_post_console(name, post_request)
        else:
            raise

    head_snapshot = None
    if isinstance(post, dict):
        head_snapshot = str(((post.get("spec") or {}).get("headSnapshot") or "")).strip() or None

    try:
        _log("set post content")
        client.set_post_content(name, raw_markdown=data.markdown, raw_type="markdown", content=html)
    except HaloAPIError:
        pass
    if data.publish:
        try:
            try:
                _log("publish (async)")
                client.publish_post_console(name, head_snapshot=head_snapshot, async_=True)
            except HaloAPIError:
                _log("publish (async, no headSnapshot)")
                client.publish_post_console(name, async_=True)
        except HaloAPIError as e:
            if e.status != 504:
                raise

        _log("wait for published")
        _wait_for_published(client, name, timeout_s=120.0)

    return {"post_name": name, "slug": slug, "head_snapshot": head_snapshot}


def _wait_for_published(client: HaloClient, name: str, *, timeout_s: float) -> None:
    deadline = time.time() + max(1.0, timeout_s)
    next_report = 0.0
    while time.time() < deadline:
        try:
            post = client.get_post_console(name)
            if isinstance(post, dict):
                spec = post.get("spec") or {}
                if bool(spec.get("publish")):
                    return
                status = post.get("status") or {}
                phase = str(status.get("phase") or "").upper()
                if phase == "PUBLISHED":
                    return
                now = time.time()
                if now >= next_report:
                    next_report = now + 5.0
                    _log(f"still publishing... phase={phase or '-'} publish={bool(spec.get('publish'))}")
        except HaloAPIError:
            pass
        time.sleep(1.0)

    raise HaloAPIError(f"Publish timeout after {int(timeout_s)}s")


def _log(message: str) -> None:
    print(f"[halo-cli] {message}", file=sys.stderr, flush=True)


def _extract_post_name_from_response(obj: Any) -> Optional[str]:
    if isinstance(obj, dict):
        md = obj.get("metadata")
        if isinstance(md, dict):
            n = md.get("name")
            if isinstance(n, str) and n.strip():
                return n.strip()
        post = obj.get("post")
        if isinstance(post, dict):
            md2 = post.get("metadata")
            if isinstance(md2, dict):
                n2 = md2.get("name")
                if isinstance(n2, str) and n2.strip():
                    return n2.strip()
    v = _find_first_key(obj, "name")
    return v.strip() if isinstance(v, str) and v.strip() else None


def _find_post_name_by_slug(client: HaloClient, *, slug: str) -> Optional[str]:
    target = (slug or "").strip()
    if not target:
        return None
    try:
        for publish_phase in [None, "DRAFT", "PUBLISHED"]:
            res = client.list_posts_console(page=0, size=20, keyword=target, publish_phase=publish_phase)
            if not isinstance(res, dict):
                continue
            items = res.get("items")
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                post = item.get("post")
                if not isinstance(post, dict):
                    continue
                spec = post.get("spec") or {}
                if isinstance(spec, dict) and str(spec.get("slug") or "").strip() == target:
                    md = post.get("metadata") or {}
                    if isinstance(md, dict):
                        name = md.get("name")
                        if isinstance(name, str) and name.strip():
                            return name.strip()
    except HaloAPIError:
        return None
    return None


def _find_post_name_by_keyword(client: HaloClient, *, keyword: str) -> Optional[str]:
    kw = (keyword or "").strip()
    if not kw:
        return None
    try:
        res = client.list_posts_console(page=0, size=1, keyword=kw)
        if isinstance(res, dict):
            items = res.get("items")
            if isinstance(items, list) and items:
                first = items[0]
                if isinstance(first, dict):
                    post = first.get("post")
                    if isinstance(post, dict):
                        name = (post.get("metadata") or {}).get("name")
                        if isinstance(name, str) and name.strip():
                            return name.strip()
    except HaloAPIError:
        return None
    return None



