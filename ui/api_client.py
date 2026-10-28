"""Thin HTTP client for the Escalate API. The UI never imports the backend directly."""

import os
from typing import Any

import httpx

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
# Links opened by the browser (PDF downloads) need an address the browser can reach; inside
# docker compose the UI talks to http://api:8000, which only works between containers.
PUBLIC_API_URL = os.environ.get("PUBLIC_API_URL", API_URL).rstrip("/")


class ApiError(Exception):
    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(f"{status}: {detail}")
        self.status = status
        self.detail = detail


def _client() -> httpx.Client:
    return httpx.Client(base_url=API_URL, timeout=600)


def _check(r: httpx.Response) -> Any:
    if r.status_code >= 400:
        try:
            detail = r.json()
        except ValueError:
            detail = r.text
        raise ApiError(r.status_code, detail)
    if r.headers.get("content-type", "").startswith("application/json"):
        return r.json()
    return r.content


def get(path: str, **params: Any) -> Any:
    with _client() as c:
        return _check(c.get(path, params=params or None))


def post(path: str, json: Any = None, files: Any = None) -> Any:
    with _client() as c:
        return _check(c.post(path, json=json, files=files))


def put(path: str, json: Any) -> Any:
    with _client() as c:
        return _check(c.put(path, json=json))


def delete(path: str) -> Any:
    with _client() as c:
        return _check(c.delete(path))
