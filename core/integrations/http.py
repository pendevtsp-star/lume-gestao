import json
from urllib import error, parse, request


class IntegrationError(Exception):
    pass


def post_json(url, payload, headers=None, timeout=15):
    return send_json(url, payload, headers=headers, timeout=timeout, method="POST")


def patch_json(url, payload, headers=None, timeout=15):
    return send_json(url, payload, headers=headers, timeout=timeout, method="PATCH")


def delete_json(url, headers=None, timeout=15):
    req = request.Request(url, headers=headers or {}, method="DELETE")
    return _open_json(req, timeout)


def send_json(url, payload, headers=None, timeout=15, method="POST"):
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    return _open_json(req, timeout)


def post_form(url, payload, timeout=15):
    data = parse.urlencode(payload).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    return _open_json(req, timeout)


def get_json(url, headers=None, timeout=15):
    req = request.Request(url, headers=headers or {}, method="GET")
    return _open_json(req, timeout)


def _open_json(req, timeout):
    try:
        with request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise IntegrationError(f"HTTP {exc.code}: {body}") from exc
    except error.URLError as exc:
        raise IntegrationError(str(exc.reason)) from exc

    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise IntegrationError(f"Resposta invalida: {body[:200]}") from exc
