"""HTTP actions using urllib."""

from __future__ import annotations

import json
from typing import Any, Dict
from urllib import parse, request

from .flow import Step
from .runner import ExecutionContext


def http_get(step: Step, ctx: ExecutionContext) -> Any:
    url = step.params["url"]
    params: Dict[str, Any] | None = step.params.get("params")
    headers: Dict[str, str] = step.params.get("headers") or {}
    if params:
        query = parse.urlencode(params)
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{query}"
    req = request.Request(url, headers=headers, method="GET")
    with request.urlopen(req) as resp:
        body = resp.read()
        content_type = resp.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return json.loads(body.decode())
        return body.decode()


def http_post(step: Step, ctx: ExecutionContext) -> Any:
    url = step.params["url"]
    data = step.params.get("data")
    headers: Dict[str, str] = step.params.get("headers") or {}
    body: bytes | None
    if data is None:
        body = None
    elif isinstance(data, (dict, list)):
        body = json.dumps(data).encode()
        headers.setdefault("Content-Type", "application/json")
    elif isinstance(data, str):
        body = data.encode()
    else:
        body = data
    req = request.Request(url, data=body, headers=headers, method="POST")
    with request.urlopen(req) as resp:
        body = resp.read()
        content_type = resp.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return json.loads(body.decode())
        return body.decode()


HTTP_ACTIONS = {
    "http.get": http_get,
    "http.post": http_post,
}
