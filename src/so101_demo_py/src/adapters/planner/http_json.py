from __future__ import annotations

import json
from collections.abc import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ...ports.task_planner import PlannerProviderError


def _origin(url: str) -> tuple[str, str | None, int | None]:
    parsed = urlsplit(url)
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80 if parsed.scheme == "http" else None
    return parsed.scheme.lower(), parsed.hostname, port


class _AuthorizationRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        has_authorization = any(
            key.lower() == "authorization" for key, _value in req.header_items()
        )
        if has_authorization and _origin(req.full_url) != _origin(newurl):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def urlopen(request: Request, *, timeout: float):
    opener = build_opener(_AuthorizationRedirectHandler())
    return opener.open(request, timeout=timeout)


def post_json(
    url: str,
    headers: Mapping[str, str],
    body: dict[str, object],
    timeout_s: float,
) -> dict[str, object]:
    try:
        request = Request(
            url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        with urlopen(request, timeout=timeout_s) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (
        TimeoutError,
        OSError,
        HTTPError,
        URLError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
    ):
        raise PlannerProviderError("PROVIDER_TRANSPORT_FAILED") from None
    if not isinstance(payload, dict):
        raise PlannerProviderError("PROVIDER_RESPONSE_INVALID")
    return payload
