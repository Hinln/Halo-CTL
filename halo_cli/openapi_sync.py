from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .client import HaloAPIError, HaloClient


@dataclass(frozen=True)
class OpenAPISpec:
    name: str
    url: str
    document: Dict[str, Any]


def sync_openapi_specs(
    client: HaloClient,
    *,
    output_dir: str | Path = "openapi/specs",
    overwrite: bool = True,
) -> List[OpenAPISpec]:
    specs = _discover_openapi_specs(client)
    if not specs:
        raise HaloAPIError(
            "Unable to discover Halo OpenAPI specs from this instance. "
            "Tried swagger-config and /v3/api-docs endpoints."
        )

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written: List[OpenAPISpec] = []
    for name, url, doc in specs:
        path = out_dir / f"{name}.json"
        if path.exists() and not overwrite:
            continue
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(OpenAPISpec(name=name, url=url, document=doc))

    return written


def generate_api_index(
    specs: Iterable[OpenAPISpec],
    *,
    output_file: str | Path = "openapi/API_INDEX.md",
) -> Path:
    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    lines.append("# Halo 官方 OpenAPI 接口清单\n")
    lines.append("本文件由 `halo-ctl sync-openapi` 自动生成，来源为 Halo 实例暴露的 OpenAPI 文档。\n")
    for spec in specs:
        title = _spec_title(spec.document) or spec.name
        version = _spec_version(spec.document)
        lines.append(f"## {title}\n")
        lines.append(f"- Spec: `{spec.name}.json`\n")
        lines.append(f"- Source: `{spec.url}`\n")
        if version:
            lines.append(f"- Version: `{version}`\n")
        endpoints = _list_endpoints(spec.document)
        lines.append(f"- Endpoints: `{len(endpoints)}`\n\n")

        lines.append("| Method | Path | OperationId | Tags |\n")
        lines.append("| --- | --- | --- | --- |\n")
        for method, path, operation_id, tags in endpoints:
            op = operation_id or ""
            tg = ",".join(tags) if tags else ""
            lines.append(f"| `{method}` | `{path}` | `{op}` | `{tg}` |\n")
        lines.append("\n")

    out_path.write_text("".join(lines), encoding="utf-8")
    return out_path


def generate_error_code_table(
    specs: Iterable[OpenAPISpec],
    *,
    output_file: str | Path = "openapi/ERROR_CODES.md",
) -> Path:
    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    statuses: Dict[str, int] = {}
    schemas: Dict[str, int] = {}

    for spec in specs:
        responses = ((spec.document.get("components") or {}).get("responses") or {}) if isinstance(spec.document, dict) else {}
        if isinstance(responses, dict):
            for k in responses.keys():
                statuses[str(k)] = statuses.get(str(k), 0) + 1

        sch = ((spec.document.get("components") or {}).get("schemas") or {}) if isinstance(spec.document, dict) else {}
        if isinstance(sch, dict):
            for k in sch.keys():
                schemas[str(k)] = schemas.get(str(k), 0) + 1

    lines: List[str] = []
    lines.append("# Halo 官方错误码与错误结构对照\n")
    lines.append("本文件由 `halo-publish sync-openapi` 自动生成。\n")
    lines.append("\n")
    lines.append("## Components.responses 统计\n")
    lines.append("\n")
    lines.append("| key | occurrences |\n")
    lines.append("| --- | ---: |\n")
    for k in sorted(statuses.keys()):
        lines.append(f"| `{k}` | {statuses[k]} |\n")

    lines.append("\n")
    lines.append("## Components.schemas 统计（常见错误结构）\n")
    lines.append("\n")
    lines.append("| schema | occurrences |\n")
    lines.append("| --- | ---: |\n")
    for k in sorted(schemas.keys()):
        if "error" in k.lower() or "problem" in k.lower() or "exception" in k.lower():
            lines.append(f"| `{k}` | {schemas[k]} |\n")

    out_path.write_text("".join(lines), encoding="utf-8")
    return out_path


def _discover_openapi_specs(client: HaloClient) -> List[Tuple[str, str, Dict[str, Any]]]:
    config_url, config = _fetch_swagger_config(client)
    specs: List[Tuple[str, str, Dict[str, Any]]] = []

    if isinstance(config, dict):
        urls = config.get("urls")
        if isinstance(urls, list) and urls:
            for u in urls:
                if not isinstance(u, dict):
                    continue
                name = str(u.get("name") or "openapi").strip() or "openapi"
                url = str(u.get("url") or "").strip()
                if not url:
                    continue
                doc = _fetch_openapi_document(client, url)
                if isinstance(doc, dict):
                    safe = _safe_name(name)
                    specs.append((safe, url, doc))
            if specs:
                return specs

        url = config.get("url")
        if isinstance(url, str) and url.strip():
            doc = _fetch_openapi_document(client, url.strip())
            if isinstance(doc, dict):
                return [("openapi", url.strip(), doc)]

    for path in ["/v3/api-docs", "/api-docs", "/openapi.json"]:
        try:
            doc = client.request_json("GET", path)
            if isinstance(doc, dict) and doc.get("paths"):
                return [("openapi", path, doc)]
        except HaloAPIError:
            continue

    raise HaloAPIError(f"OpenAPI discovery failed. swagger-config={config_url or 'n/a'}")


def _fetch_swagger_config(client: HaloClient) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    for path in [
        "/v3/api-docs/swagger-config",
        "/swagger-ui/swagger-config",
        "/swagger-config",
    ]:
        try:
            cfg = client.request_json("GET", path)
            if isinstance(cfg, dict):
                return path, cfg
        except HaloAPIError:
            continue
    return None, None


def _fetch_openapi_document(client: HaloClient, url_or_path: str) -> Any:
    target = url_or_path.strip()
    if not target:
        return None
    if target.startswith("http://") or target.startswith("https://"):
        return client.request_json_url("GET", target)
    return client.request_json("GET", target)


def _safe_name(value: str) -> str:
    out = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    out = "-".join([p for p in out.split("-") if p])
    return out or "openapi"


def _spec_title(doc: Dict[str, Any]) -> Optional[str]:
    info = doc.get("info")
    if isinstance(info, dict):
        t = info.get("title")
        if isinstance(t, str) and t.strip():
            return t.strip()
    return None


def _spec_version(doc: Dict[str, Any]) -> Optional[str]:
    info = doc.get("info")
    if isinstance(info, dict):
        v = info.get("version")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _list_endpoints(doc: Dict[str, Any]) -> List[Tuple[str, str, Optional[str], List[str]]]:
    paths = doc.get("paths")
    if not isinstance(paths, dict):
        return []

    out: List[Tuple[str, str, Optional[str], List[str]]] = []
    for path, ops in paths.items():
        if not isinstance(ops, dict):
            continue
        for method, op in ops.items():
            m = str(method).upper()
            if m not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
                continue
            if not isinstance(op, dict):
                continue
            operation_id = op.get("operationId")
            op_id = operation_id.strip() if isinstance(operation_id, str) and operation_id.strip() else None
            tags = op.get("tags")
            tag_list = [str(t) for t in tags] if isinstance(tags, list) else []
            out.append((m, str(path), op_id, tag_list))
    out.sort(key=lambda x: (x[1], x[0]))
    return out
