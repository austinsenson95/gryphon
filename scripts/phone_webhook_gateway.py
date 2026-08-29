"""Narrow public gateway for local Vobiz smoke tests.

Only Griffin's three authenticated phone callback routes are proxied. All
other paths return 404, keeping chat, events, contacts, and WebSockets private.
"""

from __future__ import annotations

import os

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_TARGET = os.getenv("PHONE_GATEWAY_TARGET", "http://127.0.0.1:8000").rstrip("/")
_ALLOWED = {
    "/api/phone/webhooks/vobiz/answer",
    "/api/phone/webhooks/vobiz/recording",
    "/api/phone/webhooks/vobiz/hangup",
}


@app.api_route("/{path:path}", methods=["GET", "POST"])
async def proxy_phone_webhook(path: str, request: Request) -> Response:
    callback_path = f"/{path}"
    if callback_path not in _ALLOWED:
        return Response(status_code=404)

    target = f"{_TARGET}{callback_path}"
    if request.url.query:
        target = f"{target}?{request.url.query}"
    headers = {}
    if content_type := request.headers.get("content-type"):
        headers["content-type"] = content_type

    async with httpx.AsyncClient(timeout=35) as client:
        upstream = await client.request(
            request.method,
            target,
            content=await request.body(),
            headers=headers,
        )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )
