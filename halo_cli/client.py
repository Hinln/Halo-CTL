from __future__ import annotations

import json
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import os
import sys
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from .version import __version__


class HaloAPIError(RuntimeError):
    def __init__(self, message: str, *, status: Optional[int] = None, body: Optional[str] = None):
        super().__init__(message)
        self.status = status
        self.body = body


def _lang_mode() -> str:
    v = os.environ.get("HALO_LANG")
    if not v:
        return "bi"
    v = v.strip().lower()
    if v in {"zh", "cn", "zh-cn"}:
        return "zh"
    if v in {"en", "en-us"}:
        return "en"
    return "bi"


def _bi(zh: str, en: str) -> str:
    mode = _lang_mode()
    if mode == "zh":
        return zh
    if mode == "en":
        return en
    return f"{zh}\n{en}"


def _trace_headers(headers: Mapping[str, str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in headers.items():
        lk = k.lower()
        if "trace" in lk or lk in {"requestid", "request-id", "x-request-id"}:
            out[k] = v
    return out


class ResponseTracker:
    _instance: Optional["ResponseTracker"] = None

    def __init__(self, *, trace_path: Optional[str] = None):
        self._trace_path = trace_path or os.environ.get("HALO_TRACE_PATH") or os.path.join(
            tempfile.gettempdir(), "halo-ctl-last-trace.json"
        )
        self._last: Optional[Dict[str, Any]] = None

    @classmethod
    def instance(cls) -> "ResponseTracker":
        if cls._instance is None:
            cls._instance = ResponseTracker()
        return cls._instance

    def set(self, data: Dict[str, Any]) -> None:
        self._last = dict(data)
        try:
            os.makedirs(os.path.dirname(self._trace_path) or ".", exist_ok=True)
            with open(self._trace_path, "w", encoding="utf-8") as f:
                json.dump(self._last, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get(self) -> Optional[Dict[str, Any]]:
        if self._last is not None:
            return dict(self._last)
        try:
            with open(self._trace_path, "r", encoding="utf-8") as f:
                v = json.load(f)
            return v if isinstance(v, dict) else None
        except Exception:
            return None


def _join_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/") + "/"
    return urllib.parse.urljoin(base, path.lstrip("/"))


def _mask_token(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 12:
        return "***"
    return token[:6] + "…" + token[-4:]


_DNS_1123_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


def slugify_dns_label(value: str, *, fallback: str = "post") -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    if not value:
        value = fallback
    value = value[:63].strip("-")
    if not value:
        value = fallback
    if _DNS_1123_LABEL_RE.match(value):
        return value
    value = re.sub(r"[^a-z0-9-]", "-", value).strip("-")
    value = re.sub(r"-+", "-", value)
    value = value[:63].strip("-")
    return value if value else fallback


@dataclass(frozen=True)
class HaloClientConfig:
    base_url: str
    pat: str
    timeout_s: float = 120.0
    user_agent: str = f"halo-ctl/{__version__}"


class HaloClient:
    def __init__(self, config: HaloClientConfig):
        self._config = config

    @property
    def base_url(self) -> str:
        return self._config.base_url

    def _headers(self, extra: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": self._config.user_agent,
            "Authorization": f"Bearer {self._config.pat}",
        }
        if extra:
            headers.update(dict(extra))
        return headers

    def get_last_trace(self) -> Optional[Dict[str, Any]]:
        return ResponseTracker.instance().get()

    def _body_summary(self, body_bytes: Optional[bytes]) -> Dict[str, Any]:
        if body_bytes is None:
            return {"present": False}
        text = body_bytes.decode("utf-8", errors="replace")
        return {
            "present": True,
            "bytes": len(body_bytes),
            "preview": text[:400],
        }

    def _sleep_backoff(self, *, base: float, attempt: int, retry_after_s: Optional[float]) -> float:
        cap = float(os.environ.get("HALO_RETRY_MAX_SLEEP_S") or 12.0)
        if retry_after_s is not None and retry_after_s > 0:
            return min(retry_after_s, cap)
        exp = base * (2**attempt)
        jitter = 0.5 + random.random()
        return min(exp * jitter, cap)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json_body: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
        retry: int = 2,
        retry_backoff_s: float = 0.8,
    ) -> Tuple[int, Dict[str, str], str]:
        url = _join_url(self._config.base_url, path)
        if params:
            cleaned: Dict[str, Any] = {k: v for k, v in params.items() if v is not None}
            query = urllib.parse.urlencode(cleaned, doseq=True)
            url = url + ("&" if ("?" in url) else "?") + query

        body_bytes = None
        request_headers = self._headers(headers)
        if json_body is not None:
            body_bytes = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")

        last_err: Optional[Exception] = None
        for attempt in range(retry + 1):
            start = time.time()
            req = urllib.request.Request(url=url, data=body_bytes, headers=request_headers, method=method.upper())
            try:
                with urllib.request.urlopen(req, timeout=self._config.timeout_s) as resp:
                    status = int(getattr(resp, "status", 0) or 0)
                    resp_headers = {k: v for k, v in resp.headers.items()}
                    resp_body = resp.read().decode("utf-8", errors="replace")
                    if os.environ.get("HALO_DEBUG") == "1":
                        cost_ms = int((time.time() - start) * 1000)
                        print(f"[halo-ctl] {method.upper()} {path} -> {status} ({cost_ms}ms)", file=sys.stderr, flush=True)
                    ResponseTracker.instance().set(
                        {
                            "ok": True,
                            "url": url,
                            "path": path,
                            "method": method.upper(),
                            "request": {"body": self._body_summary(body_bytes)},
                            "response": {"status": status, "trace": _trace_headers(resp_headers)},
                            "attempt": attempt,
                            "retry": retry,
                            "cost_ms": int((time.time() - start) * 1000),
                        }
                    )
                    return status, resp_headers, resp_body
            except urllib.error.HTTPError as e:
                status = int(getattr(e, "code", 0) or 0)
                try:
                    resp_body = e.read().decode("utf-8", errors="replace")
                except Exception:
                    resp_body = ""
                resp_headers = {k: v for k, v in getattr(e, "headers", {}).items()} if getattr(e, "headers", None) else {}
                if os.environ.get("HALO_DEBUG") == "1":
                    cost_ms = int((time.time() - start) * 1000)
                    print(f"[halo-ctl] {method.upper()} {path} -> {status} ({cost_ms}ms)", file=sys.stderr, flush=True)

                retry_after = None
                ra = resp_headers.get("Retry-After") or resp_headers.get("retry-after")
                if ra:
                    try:
                        retry_after = float(ra)
                    except Exception:
                        retry_after = None

                ResponseTracker.instance().set(
                    {
                        "ok": False,
                        "url": url,
                        "path": path,
                        "method": method.upper(),
                        "request": {"body": self._body_summary(body_bytes)},
                        "response": {"status": status, "trace": _trace_headers(resp_headers)},
                        "attempt": attempt,
                        "retry": retry,
                        "error": {"type": "HTTPError", "message": str(e)},
                        "cost_ms": int((time.time() - start) * 1000),
                    }
                )

                if status in {429, 500, 502, 503, 504} and attempt < retry:
                    sleep_s = self._sleep_backoff(base=retry_backoff_s, attempt=attempt, retry_after_s=retry_after)
                    time.sleep(sleep_s)
                    last_err = HaloAPIError(
                        _bi(
                            f"HTTP {status}：请求失败，将重试（{attempt + 1}/{retry}）",
                            f"HTTP {status}: request failed, retrying ({attempt + 1}/{retry})",
                        ),
                        status=status,
                        body=resp_body,
                    )
                    continue
                raise HaloAPIError(
                    _bi(
                        f"HTTP {status}：请求失败（Authorization=Bearer {_mask_token(self._config.pat)}）",
                        f"HTTP {status}: request failed (Authorization=Bearer {_mask_token(self._config.pat)})",
                    ),
                    status=status,
                    body=resp_body,
                ) from None
            except urllib.error.URLError as e:
                reason = getattr(e, "reason", None)
                err_type = type(reason).__name__ if reason is not None else type(e).__name__
                msg = str(reason) if reason is not None else str(e)
                if os.environ.get("HALO_DEBUG") == "1":
                    cost_ms = int((time.time() - start) * 1000)
                    print(f"[halo-ctl] {method.upper()} {path} -> urlerror ({cost_ms}ms): {msg}", file=sys.stderr, flush=True)
                ResponseTracker.instance().set(
                    {
                        "ok": False,
                        "url": url,
                        "path": path,
                        "method": method.upper(),
                        "request": {"body": self._body_summary(body_bytes)},
                        "response": {"status": None, "trace": {}},
                        "attempt": attempt,
                        "retry": retry,
                        "error": {"type": err_type, "message": msg},
                        "cost_ms": int((time.time() - start) * 1000),
                    }
                )

                retryable = True
                if reason is not None and isinstance(reason, OSError):
                    if getattr(reason, "errno", None) in {111, 61}:
                        retryable = True

                if attempt < retry and retryable:
                    sleep_s = self._sleep_backoff(base=retry_backoff_s, attempt=attempt, retry_after_s=None)
                    time.sleep(sleep_s)
                    last_err = e
                    continue
                raise HaloAPIError(
                    _bi(
                        f"网络异常：请求失败（Authorization=Bearer {_mask_token(self._config.pat)}）：{msg}",
                        f"Network error: request failed (Authorization=Bearer {_mask_token(self._config.pat)}): {msg}",
                    )
                ) from None
            except Exception as e:
                if os.environ.get("HALO_DEBUG") == "1":
                    cost_ms = int((time.time() - start) * 1000)
                    print(f"[halo-ctl] {method.upper()} {path} -> error ({cost_ms}ms): {e}", file=sys.stderr, flush=True)
                ResponseTracker.instance().set(
                    {
                        "ok": False,
                        "url": url,
                        "path": path,
                        "method": method.upper(),
                        "request": {"body": self._body_summary(body_bytes)},
                        "response": {"status": None, "trace": {}},
                        "attempt": attempt,
                        "retry": retry,
                        "error": {"type": type(e).__name__, "message": str(e)},
                        "cost_ms": int((time.time() - start) * 1000),
                    }
                )
                if attempt < retry:
                    sleep_s = self._sleep_backoff(base=retry_backoff_s, attempt=attempt, retry_after_s=None)
                    time.sleep(sleep_s)
                    last_err = e
                    continue
                raise HaloAPIError(
                    _bi(
                        f"请求失败（Authorization=Bearer {_mask_token(self._config.pat)}）：{e}",
                        f"Request failed (Authorization=Bearer {_mask_token(self._config.pat)}): {e}",
                    )
                ) from None

        raise HaloAPIError(_bi(f"重试后仍失败：{last_err}", f"Failed after retries: {last_err}"))

    def request_json(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json_body: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
        retry: int = 2,
    ) -> Any:
        status, _, text = self.request(
            method,
            path,
            params=params,
            json_body=json_body,
            headers=headers,
            retry=retry,
        )
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            raise HaloAPIError(f"Non-JSON response (HTTP {status}) from {path}", status=status, body=text) from None

    def request_json_url(
        self,
        method: str,
        url: str,
        *,
        json_body: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
        retry: int = 2,
    ) -> Any:
        parsed = urllib.parse.urlsplit(url)
        base = urllib.parse.urlsplit(self._config.base_url)
        if parsed.scheme and parsed.netloc:
            if (parsed.scheme, parsed.netloc) != (base.scheme, base.netloc):
                raise HaloAPIError(f"Refuse cross-origin request: {url}")

        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return self.request_json(method, path, json_body=json_body, headers=headers, retry=retry)

    def whoami(self) -> Any:
        return self.request_json("GET", "/apis/api.console.halo.run/v1alpha1/users/-")

    def list_posts_console(
        self,
        *,
        page: int = 0,
        size: int = 20,
        field_selector: Optional[list[str]] = None,
        keyword: Optional[str] = None,
        publish_phase: Optional[str] = None,
    ) -> Any:
        params: Dict[str, Any] = {"page": page, "size": size}
        if field_selector:
            params["fieldSelector"] = field_selector
        if keyword:
            params["keyword"] = keyword
        if publish_phase:
            params["publishPhase"] = publish_phase
        return self.request_json("GET", "/apis/api.console.halo.run/v1alpha1/posts", params=params)

    def draft_post_console(self, post_request: Mapping[str, Any]) -> Any:
        return self.request_json("POST", "/apis/api.console.halo.run/v1alpha1/posts", json_body=post_request)

    def update_draft_post_console(self, name: str, post_request: Mapping[str, Any]) -> Any:
        return self.request_json(
            "PUT",
            f"/apis/api.console.halo.run/v1alpha1/posts/{urllib.parse.quote(name)}",
            json_body=post_request,
        )

    def get_post_console(self, name: str) -> Any:
        return self.request_json(
            "GET",
            f"/apis/api.console.halo.run/v1alpha1/posts/{urllib.parse.quote(name)}",
        )

    def publish_post_console(self, name: str, *, head_snapshot: Optional[str] = None, async_: bool = False) -> Any:
        params: Dict[str, str] = {}
        if head_snapshot:
            params["headSnapshot"] = head_snapshot
        if async_:
            params["async"] = "true"
        return self.request_json(
            "PUT",
            f"/apis/api.console.halo.run/v1alpha1/posts/{urllib.parse.quote(name)}/publish",
            params=params if params else None,
        )

    def list_posts(self, *, page: int = 0, size: int = 20) -> Any:
        return self.request_json(
            "GET",
            "/apis/content.halo.run/v1alpha1/posts",
            params={"page": str(page), "size": str(size)},
        )

    def list_tags(self, *, page: int = 0, size: int = 50) -> Any:
        return self.request_json(
            "GET",
            "/apis/content.halo.run/v1alpha1/tags",
            params={"page": page, "size": size},
        )

    def list_categories(self, *, page: int = 0, size: int = 50) -> Any:
        return self.request_json(
            "GET",
            "/apis/content.halo.run/v1alpha1/categories",
            params={"page": page, "size": size},
        )

    def list_attachments_uc(self, *, page: int = 0, size: int = 1) -> Any:
        return self.request_json(
            "GET",
            "/apis/uc.api.content.halo.run/v1alpha1/attachments",
            params={"page": page, "size": size},
        )

    def delete_post_console(self, name: str) -> Any:
        return self.request_json(
            "DELETE",
            f"/apis/api.console.halo.run/v1alpha1/posts/{urllib.parse.quote(name)}",
        )

    def get_post(self, name: str) -> Any:
        return self.request_json("GET", f"/apis/content.halo.run/v1alpha1/posts/{urllib.parse.quote(name)}")

    def create_post_crd(self, *, title: str, slug: Optional[str] = None, published: bool = False) -> Any:
        spec: Dict[str, Any] = {"title": title}
        if slug:
            spec["slug"] = slug
        spec["published"] = bool(published)

        payload = {
            "apiVersion": "content.halo.run/v1alpha1",
            "kind": "Post",
            "metadata": {"generateName": "post-"},
            "spec": spec,
        }
        return self.request_json("POST", "/apis/content.halo.run/v1alpha1/posts", json_body=payload)

    def replace_post_crd(self, post_obj: Mapping[str, Any]) -> Any:
        name = str(post_obj.get("metadata", {}).get("name") or "")
        if not name:
            raise HaloAPIError("Post object missing metadata.name")
        return self.request_json(
            "PUT",
            f"/apis/content.halo.run/v1alpha1/posts/{urllib.parse.quote(name)}",
            json_body=post_obj,
        )

    def set_post_content(
        self,
        post_name: str,
        *,
        raw_markdown: str,
        raw_type: str = "markdown",
        content: Optional[str] = None,
    ) -> Any:
        payload: Dict[str, Any] = {"raw": raw_markdown, "rawType": raw_type, "content": content or raw_markdown}
        return self.request_json(
            "PUT",
            f"/apis/api.console.halo.run/v1alpha1/posts/{urllib.parse.quote(post_name)}/content",
            json_body=payload,
        )

    def fetch_post_head_content(self, name: str) -> Any:
        return self.request_json(
            "GET",
            f"/apis/api.console.halo.run/v1alpha1/posts/{urllib.parse.quote(name)}/head-content",
        )

    def fetch_post_release_content(self, name: str) -> Any:
        return self.request_json(
            "GET",
            f"/apis/api.console.halo.run/v1alpha1/posts/{urllib.parse.quote(name)}/release-content",
        )

    def try_publish_console(self, post_name: str) -> Any:
        return self.publish_post_console(post_name)

