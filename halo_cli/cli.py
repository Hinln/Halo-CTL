from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional

from .client import HaloAPIError, HaloClient, HaloClientConfig
from .openapi_sync import generate_api_index, generate_error_code_table, sync_openapi_specs
from .publish import PublishInput, publish_markdown


def _read_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name)
    if v is None:
        return default
    v = v.strip()
    return v if v else default


def _build_client(args: argparse.Namespace) -> HaloClient:
    base_url = args.base_url or _env("HALO_BASE_URL")
    pat = args.pat or _env("HALO_PAT")
    timeout_s = None
    if getattr(args, "timeout", None) is not None:
        timeout_s = float(args.timeout)
    else:
        v = _env("HALO_TIMEOUT_S")
        if v is not None:
            try:
                timeout_s = float(v)
            except Exception:
                raise HaloAPIError("Invalid HALO_TIMEOUT_S; must be a number")
    if not base_url:
        raise HaloAPIError("Missing base URL. Provide --base-url or set HALO_BASE_URL")
    if not pat:
        raise HaloAPIError("Missing PAT. Provide --pat or set HALO_PAT")
    if timeout_s is None:
        return HaloClient(HaloClientConfig(base_url=base_url, pat=pat))
    return HaloClient(HaloClientConfig(base_url=base_url, pat=pat, timeout_s=timeout_s))


def cmd_whoami(args: argparse.Namespace) -> int:
    client = _build_client(args)
    me = client.whoami()
    print(json.dumps(me, ensure_ascii=False, indent=2))
    return 0


def cmd_list_tags(args: argparse.Namespace) -> int:
    client = _build_client(args)
    data = client.list_tags(page=args.page, size=args.size)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_list_categories(args: argparse.Namespace) -> int:
    client = _build_client(args)
    data = client.list_categories(page=args.page, size=args.size)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_sync_openapi(args: argparse.Namespace) -> int:
    client = _build_client(args)
    specs = sync_openapi_specs(client, output_dir=args.out, overwrite=not args.no_overwrite)
    index_path = generate_api_index(specs)
    err_path = generate_error_code_table(specs)
    print(
        json.dumps(
            {
                "written": [{"name": s.name, "source": s.url} for s in specs],
                "api_index": str(index_path),
                "error_codes": str(err_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_last_trace(args: argparse.Namespace) -> int:
    client = _build_client(args)
    trace = client.get_last_trace()
    print(json.dumps(trace, ensure_ascii=False, indent=2))
    return 0


def _extract_named_items(obj: Any) -> list[dict[str, Any]]:
    if not isinstance(obj, dict):
        return []
    items = obj.get("items")
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        md = it.get("metadata")
        spec = it.get("spec")
        name = (md or {}).get("name") if isinstance(md, dict) else None
        display_name = None
        if isinstance(spec, dict):
            display_name = spec.get("displayName") or spec.get("title")
        if isinstance(name, str) and name.strip():
            out.append({"name": name.strip(), "displayName": str(display_name) if display_name else None})
    return out


def cmd_context(args: argparse.Namespace) -> int:
    client = _build_client(args)
    tags = client.list_tags(page=0, size=min(args.size, 200))
    categories = client.list_categories(page=0, size=min(args.size, 200))
    out = {
        "baseUrl": client.base_url,
        "tags": _extract_named_items(tags),
        "categories": _extract_named_items(categories),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_pat_probe(args: argparse.Namespace) -> int:
    client = _build_client(args)

    results: dict[str, Any] = {
        "baseUrl": client.base_url,
        "checks": [],
    }

    def run_check(key: str, fn):
        try:
            data = fn()
            results["checks"].append({"key": key, "ok": True})
            return data
        except HaloAPIError as e:
            results["checks"].append({"key": key, "ok": False, "status": getattr(e, "status", None), "error": str(e)})
            return None
        except Exception as e:
            results["checks"].append({"key": key, "ok": False, "error": str(e)})
            return None

    run_check("whoami", lambda: client.whoami())
    run_check("list_tags", lambda: client.list_tags(page=0, size=1))
    run_check("list_categories", lambda: client.list_categories(page=0, size=1))
    run_check("list_attachments", lambda: client.list_attachments_uc(page=0, size=1))

    if args.write_probe:
        payload = {
            "post": {
                "apiVersion": "content.halo.run/v1alpha1",
                "kind": "Post",
                "metadata": {"generateName": "post-"},
                "spec": {"title": "Halo-CTL Permission Probe", "slug": "halo-ctl-permission-probe", "publish": False},
            }
        }

        created = run_check("create_draft_post", lambda: client.draft_post_console(payload))
        created_name = None
        if isinstance(created, dict):
            md = created.get("metadata")
            if isinstance(md, dict):
                created_name = md.get("name")
        if isinstance(created_name, str) and created_name.strip():
            run_check("delete_draft_post", lambda: client.delete_post_console(created_name.strip()))

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


def _validate_publish_payload(payload: Any) -> tuple[bool, list[str], list[str]]:
    errors: list[str] = []
    tips: list[str] = []
    if not isinstance(payload, dict):
        errors.append("payload 必须是 JSON 对象 / payload must be a JSON object")
        tips.append("请输出形如 {\"title\":..., \"markdown\":...} 的对象 / output an object with title & markdown")
        return False, errors, tips

    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append("缺少 title（字符串）/ missing title (string)")
        tips.append("示例：\"title\": \"我的新文章\" / example: \"title\": \"My post\"")

    markdown = payload.get("markdown")
    content = payload.get("content")
    if (not isinstance(markdown, str) or not markdown.strip()) and (not isinstance(content, str) or not content.strip()):
        errors.append("缺少 markdown 或 content（字符串）/ missing markdown or content (string)")
        tips.append("建议使用 markdown 字段 / prefer using markdown field")

    slug = payload.get("slug")
    if slug is not None and (not isinstance(slug, str) or not slug.strip()):
        errors.append("slug 必须是非空字符串（或省略）/ slug must be a non-empty string (or omitted)")

    visible = payload.get("visible")
    if visible is not None:
        if not isinstance(visible, str) or visible not in {"PUBLIC", "INTERNAL", "PRIVATE"}:
            errors.append("visible 只能是 PUBLIC/INTERNAL/PRIVATE / visible must be PUBLIC/INTERNAL/PRIVATE")

    publish = payload.get("publish")
    if publish is not None and not isinstance(publish, bool):
        errors.append("publish 必须是布尔值 / publish must be boolean")

    allow_comment = payload.get("allowComment")
    if allow_comment is not None and not isinstance(allow_comment, bool):
        errors.append("allowComment 必须是布尔值 / allowComment must be boolean")

    for key in ["tags", "categories"]:
        v = payload.get(key)
        if v is None:
            continue
        if isinstance(v, list):
            if not all(isinstance(x, str) and x.strip() for x in v):
                errors.append(f"{key} 列表元素必须为非空字符串 / {key} list items must be non-empty strings")
        elif isinstance(v, str):
            pass
        else:
            errors.append(f"{key} 必须是字符串或字符串数组 / {key} must be string or string[]")

    cover = payload.get("cover")
    if cover is not None and (not isinstance(cover, str) or not cover.strip()):
        errors.append("cover 必须是非空字符串（URL）/ cover must be a non-empty string (URL)")

    return len(errors) == 0, errors, tips


def cmd_debug_head_content(args: argparse.Namespace) -> int:
    client = _build_client(args)
    data = client.fetch_post_head_content(args.name)
    _print_content_wrapper(data, head=args.head)
    return 0


def cmd_debug_release_content(args: argparse.Namespace) -> int:
    client = _build_client(args)
    data = client.fetch_post_release_content(args.name)
    _print_content_wrapper(data, head=args.head)
    return 0


def _print_content_wrapper(data: Any, *, head: int) -> None:
    if not isinstance(data, dict):
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    content = data.get("content")
    raw = data.get("raw")
    raw_type = data.get("rawType")
    snapshot_name = data.get("snapshotName")

    def _preview(v: Any) -> Any:
        if v is None:
            return None
        s = str(v)
        if head == 0:
            return s
        return s[:head]

    out = {
        "rawType": raw_type,
        "snapshotName": snapshot_name,
        "contentPreview": _preview(content),
        "contentLength": len(str(content)) if content is not None else 0,
        "rawPreview": _preview(raw),
        "rawLength": len(str(raw)) if raw is not None else 0,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_publish(args: argparse.Namespace) -> int:
    client = _build_client(args)

    md = args.markdown
    if args.markdown_file:
        md = _read_text(args.markdown_file)
    if not md:
        raise HaloAPIError("Missing markdown content. Provide --markdown or --markdown-file")

    data = PublishInput(
        title=args.title,
        slug=args.slug,
        markdown=md,
        publish=not args.draft,
        tags=_split_csv(args.tags),
        categories=_split_csv(args.categories),
        cover=args.cover,
        visible=args.visible,
        allow_comment=not args.disallow_comment,
    )
    result = publish_markdown(client, data)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_publish_json(args: argparse.Namespace) -> int:
    client = _build_client(args)
    payload = json.loads(_read_text(args.file))
    ok, errors, tips = _validate_publish_payload(payload)
    if not ok:
        msg = "JSON Schema 校验失败 / JSON schema validation failed\n" + "\n".join(f"- {e}" for e in errors)
        if tips:
            msg += "\n\n修复建议 / Suggestions\n" + "\n".join(f"- {t}" for t in tips)
        raise HaloAPIError(msg)
    print("Loaded payload", file=sys.stderr, flush=True)
    title = str(payload.get("title") or "")
    markdown = str(payload.get("markdown") or payload.get("content") or "")
    slug = payload.get("slug")
    publish = bool(payload.get("publish", True))
    tags = payload.get("tags")
    categories = payload.get("categories")
    cover = payload.get("cover")
    visible = str(payload.get("visible") or "PUBLIC")
    allow_comment = bool(payload.get("allowComment", True))
    if not title or not markdown:
        raise HaloAPIError("JSON 必须至少包含 title 与 markdown/content 字段")
    result = publish_markdown(
        client,
        PublishInput(
            title=title,
            markdown=markdown,
            slug=slug,
            publish=publish,
            tags=list(tags) if isinstance(tags, list) else _split_csv(tags),
            categories=list(categories) if isinstance(categories, list) else _split_csv(categories),
            cover=str(cover) if cover else None,
            visible=visible,
            allow_comment=allow_comment,
        ),
    )
    if args.dump_input:
        print(json.dumps({"input": payload, "result": result}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _split_csv(value: Any) -> Optional[list[str]]:
    if value is None:
        return None
    if isinstance(value, list):
        out = [str(x).strip() for x in value if str(x).strip()]
        return out or None
    s = str(value).strip()
    if not s:
        return None
    out = [p.strip() for p in s.split(",") if p.strip()]
    return out or None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="halo-ctl", add_help=True)
    p.add_argument("--base-url", help="Halo 站点地址，例如 https://your-halo.example")
    p.add_argument("--pat", help="Halo PAT（建议通过环境变量 HALO_PAT 提供）")
    p.add_argument("--timeout", type=float, help="请求超时秒数（也可用环境变量 HALO_TIMEOUT_S）")

    sub = p.add_subparsers(dest="cmd", required=True)

    who = sub.add_parser("whoami", help="验证 token 并获取当前用户信息")
    who.set_defaults(func=cmd_whoami)

    lt = sub.add_parser("list-tags", help="列出 tags（用于获取 tag 的 name）")
    lt.add_argument("--page", type=int, default=0)
    lt.add_argument("--size", type=int, default=50)
    lt.set_defaults(func=cmd_list_tags)

    lc = sub.add_parser("list-categories", help="列出 categories（用于获取分类的 name）")
    lc.add_argument("--page", type=int, default=0)
    lc.add_argument("--size", type=int, default=50)
    lc.set_defaults(func=cmd_list_categories)

    dbg = sub.add_parser("debug-head-content", help="查看文章 head-content（用于排查排版/渲染）")
    dbg.add_argument("--name", required=True, help="文章 metadata.name（通常与 slug 一致）")
    dbg.add_argument("--head", type=int, default=300, help="预览前 N 个字符，0 表示全部")
    dbg.set_defaults(func=cmd_debug_head_content)

    dbr = sub.add_parser("debug-release-content", help="查看文章 release-content（发布后前台通常使用）")
    dbr.add_argument("--name", required=True, help="文章 metadata.name（通常与 slug 一致）")
    dbr.add_argument("--head", type=int, default=300, help="预览前 N 个字符，0 表示全部")
    dbr.set_defaults(func=cmd_debug_release_content)

    pub = sub.add_parser("publish", help="发布/更新一篇 Markdown 文章")
    pub.add_argument("--title", required=True)
    pub.add_argument("--slug")
    pub.add_argument("--tags", help="逗号分隔，例如 tag-a,tag-b")
    pub.add_argument("--categories", help="逗号分隔，值为分类的 name")
    pub.add_argument("--cover", help="封面图片 URL")
    pub.add_argument("--visible", default="PUBLIC", choices=["PUBLIC", "INTERNAL", "PRIVATE"])
    pub.add_argument("--disallow-comment", action="store_true")
    pub.add_argument("--markdown")
    pub.add_argument("--markdown-file")
    pub.add_argument("--draft", action="store_true", help="仅创建草稿，不发布")
    pub.set_defaults(func=cmd_publish)

    pubj = sub.add_parser("publish-json", help="从 JSON（可对接 openclaw 输出）发布文章")
    pubj.add_argument("--file", required=True)
    pubj.add_argument("--dump-input", action="store_true", help="输出完整输入（大文章会很慢）")
    pubj.set_defaults(func=cmd_publish_json)

    so = sub.add_parser("sync-openapi", help="从当前 Halo 实例同步官方 OpenAPI 文档")
    so.add_argument("--out", default="openapi/specs", help="OpenAPI 输出目录")
    so.add_argument("--no-overwrite", action="store_true", help="如果文件已存在则不覆盖")
    so.set_defaults(func=cmd_sync_openapi)

    lt = sub.add_parser("last-trace", help="输出最近一次 API 请求现场（用于 AI 自愈）")
    lt.set_defaults(func=cmd_last_trace)

    ctx = sub.add_parser("context", help="输出博客元数据快照（分类/标签等），便于注入 AI Prompt")
    ctx.add_argument("--size", type=int, default=100, help="最多返回多少条分类/标签")
    ctx.set_defaults(func=cmd_context)

    pp = sub.add_parser("pat-probe", help="探测 PAT 可用性与权限（尽量只读）")
    pp.add_argument("--write-probe", action="store_true", help="执行写入探针（会创建并尝试删除一篇草稿）")
    pp.set_defaults(func=cmd_pat_probe)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except HaloAPIError as e:
        msg = str(e)
        if getattr(e, "body", None):
            msg += "\n" + str(e.body)
        print(msg, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

