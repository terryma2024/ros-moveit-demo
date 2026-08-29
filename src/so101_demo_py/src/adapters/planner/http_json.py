from __future__ import annotations

import json
from collections.abc import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ...ports.task_planner import PlannerProviderError


def post_json(url: str, headers: Mapping[str, str], body: dict[str, object], timeout_s: float) -> dict[str, object]:
    try:
        request = Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                          headers={"Content-Type": "application/json", **headers}, method="POST")
        with urlopen(request, timeout=timeout_s) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (TimeoutError, OSError, HTTPError, URLError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise PlannerProviderError("PROVIDER_TRANSPORT_FAILED") from None
    if not isinstance(payload, dict):
        raise PlannerProviderError("PROVIDER_RESPONSE_INVALID")
    return payload
