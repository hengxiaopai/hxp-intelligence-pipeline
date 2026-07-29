"""Registry loading and guarded network primitives.

Live collection is deliberately opt-in. Every request must originate from an
active source in ``config/sources.json`` and pass URL, DNS, robots, size, MIME,
and redirect checks.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

USER_AGENT = (
    "HXPIntelligenceBot/0.1 "
    "(+https://github.com/hengxiaopai/hxp-intelligence-pipeline)"
)
MAX_BODY_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 15


class CollectionError(Exception):
    """Raised when collection is unsafe, unsupported, or unsuccessful."""


@dataclass(frozen=True, slots=True)
class SourceConfig:
    registry_id: str
    name: str
    url: str
    publisher: str
    collection_method: str
    access_policy: str
    parser_hint: str
    active: bool
    requires_auth: bool
    min_interval_minutes: int
    max_age_hours: int

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SourceConfig":
        return cls(
            registry_id=str(value["registry_id"]),
            name=str(value["name"]),
            url=str(value["url"]),
            publisher=str(value["publisher"]),
            collection_method=str(value["collection_method"]),
            access_policy=str(value["access_policy"]),
            parser_hint=str(value["parser_hint"]),
            active=bool(value["active"]),
            requires_auth=bool(value["requires_auth"]),
            min_interval_minutes=int(value["min_interval_minutes"]),
            max_age_hours=int(value["max_age_hours"]),
        )


@dataclass(frozen=True, slots=True)
class FetchResult:
    requested_url: str
    final_url: str
    status: int
    headers: dict[str, str]
    content_type: str
    body: bytes


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(  # type: ignore[override]
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Mapping[str, str],
        newurl: str,
    ) -> None:
        return None


def load_registry_source(registry_path: Path, registry_id: str) -> SourceConfig:
    try:
        with registry_path.open("r", encoding="utf-8") as handle:
            registry = json.load(handle)
    except FileNotFoundError as exc:
        raise CollectionError(f"来源注册表不存在：{registry_path}") from exc
    except json.JSONDecodeError as exc:
        raise CollectionError(
            f"来源注册表 JSON 无效：{registry_path}:{exc.lineno}:{exc.colno}"
        ) from exc

    for raw_source in registry.get("sources", []):
        if raw_source.get("registry_id") == registry_id:
            source = SourceConfig.from_dict(raw_source)
            if not source.active:
                raise CollectionError(f"来源未启用：{registry_id}")
            return source
    raise CollectionError(f"来源未注册：{registry_id}")


def assert_supported_source(source: SourceConfig, *, live: bool) -> None:
    if source.collection_method not in {"rss", "html_index"}:
        raise CollectionError(
            f"当前适配器不支持 collection_method={source.collection_method}"
        )
    if live:
        if source.access_policy == "manual_only":
            raise CollectionError(f"来源策略为 manual_only，禁止实时采集：{source.registry_id}")
        if source.access_policy == "official_api_only":
            raise CollectionError(
                f"来源策略为 official_api_only，禁止 RSS/HTML 实时采集：{source.registry_id}"
            )
        if source.requires_auth:
            raise CollectionError(f"来源需要认证，当前采集器不处理凭据：{source.registry_id}")


def _is_forbidden_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


def validate_public_https_url(url: str, *, resolve_dns: bool) -> urllib.parse.SplitResult:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.lower() != "https":
        raise CollectionError("实时采集只允许 HTTPS URL")
    if not parsed.hostname:
        raise CollectionError("URL 缺少主机名")
    if parsed.username or parsed.password:
        raise CollectionError("URL 不允许包含用户名或密码")
    if parsed.port not in (None, 443):
        raise CollectionError("实时采集只允许默认 HTTPS 端口 443")

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise CollectionError(f"拒绝本地主机：{hostname}")

    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None and _is_forbidden_ip(literal):
        raise CollectionError(f"拒绝非公网 IP：{hostname}")

    if resolve_dns:
        try:
            answers = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise CollectionError(f"DNS 解析失败：{hostname}") from exc
        if not answers:
            raise CollectionError(f"DNS 未返回地址：{hostname}")
        for answer in answers:
            address_text = answer[4][0]
            address = ipaddress.ip_address(address_text)
            if _is_forbidden_ip(address):
                raise CollectionError(
                    f"DNS 解析到非公网地址，拒绝访问：{hostname} -> {address_text}"
                )
    return parsed


def _content_type(headers: Mapping[str, str]) -> str:
    value = headers.get("Content-Type") or headers.get("content-type") or ""
    return value.split(";", 1)[0].strip().lower()


def _selected_headers(headers: Mapping[str, str]) -> dict[str, str]:
    allowed = {"content-type", "etag", "last-modified", "cache-control"}
    selected: dict[str, str] = {}
    for key, value in headers.items():
        normalized = key.lower()
        if normalized in allowed:
            selected[normalized] = str(value)[:500]
    return selected


def _open_without_redirects(request: urllib.request.Request, timeout: int) -> Any:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    return opener.open(request, timeout=timeout)


def _request_bytes(
    url: str,
    *,
    timeout: int,
    max_bytes: int,
    allowed_content_types: set[str],
) -> FetchResult:
    validate_public_https_url(url, resolve_dns=True)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": ", ".join(sorted(allowed_content_types)),
            "Accept-Encoding": "identity",
        },
        method="GET",
    )
    try:
        with _open_without_redirects(request, timeout) as response:
            status = int(getattr(response, "status", 200))
            final_url = str(response.geturl())
            if final_url.rstrip("/") != url.rstrip("/"):
                raise CollectionError("采集器不接受重定向；请在注册表中使用最终 URL")
            headers = dict(response.headers.items())
            content_type = _content_type(headers)
            if content_type not in allowed_content_types:
                raise CollectionError(
                    f"不支持的 Content-Type：{content_type or 'missing'}"
                )
            declared_length = headers.get("Content-Length")
            if declared_length and int(declared_length) > max_bytes:
                raise CollectionError("响应 Content-Length 超过大小限制")
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise CollectionError("响应正文超过大小限制")
            return FetchResult(
                requested_url=url,
                final_url=final_url,
                status=status,
                headers=_selected_headers(headers),
                content_type=content_type,
                body=body,
            )
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            raise CollectionError(
                f"来源返回重定向 HTTP {exc.code}；请更新注册表为最终 URL"
            ) from exc
        raise CollectionError(f"来源返回 HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise CollectionError(f"网络请求失败：{exc.reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise CollectionError("网络请求超时") from exc


def check_robots(source_url: str, *, timeout: int) -> None:
    parsed = validate_public_https_url(source_url, resolve_dns=True)
    robots_url = urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, "/robots.txt", "", "")
    )
    try:
        result = _request_bytes(
            robots_url,
            timeout=timeout,
            max_bytes=256 * 1024,
            allowed_content_types={"text/plain"},
        )
    except CollectionError as exc:
        # A missing robots.txt conventionally means no explicit restriction.
        if "HTTP 404" in str(exc):
            return
        raise CollectionError(f"无法安全确认 robots.txt：{exc}") from exc

    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(result.body.decode("utf-8", errors="replace").splitlines())
    if not parser.can_fetch(USER_AGENT, source_url):
        raise CollectionError(f"robots.txt 不允许访问：{source_url}")


def fetch_live_source(
    source: SourceConfig,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = MAX_BODY_BYTES,
) -> FetchResult:
    assert_supported_source(source, live=True)
    check_robots(source.url, timeout=timeout)
    if source.collection_method == "rss":
        allowed = {
            "application/atom+xml",
            "application/rss+xml",
            "application/xml",
            "text/xml",
        }
    else:
        allowed = {"text/html", "application/xhtml+xml"}
    return _request_bytes(
        source.url,
        timeout=timeout,
        max_bytes=max_bytes,
        allowed_content_types=allowed,
    )
