"""Optional Starlette server hosting the ``/u/<token>`` unsubscribe endpoint.

Run with::

    blufire unsubscribe-server --host 0.0.0.0 --port 8000

GET renders a confirm page; POST (or one-click POST per RFC 8058) flips the
suppression entry. Tampered tokens return 400.
"""

from __future__ import annotations

from typing import Any

from blufire.compliance.suppression import SuppressionList
from blufire.compliance.unsubscribe import TokenInvalid, UnsubscribeSigner
from blufire.logging_setup import get_logger
from blufire.settings import Settings


def build_app(settings: Settings) -> Any:
    """Construct a Starlette ASGI app. Imports Starlette lazily so the optional
    ``unsubscribe-server`` extra isn't required for the rest of Blufire."""
    try:
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse
        from starlette.routing import Route
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Install the unsubscribe-server extra: pip install 'blufire[unsubscribe-server]'"
        ) from exc

    signer = UnsubscribeSigner(settings)
    suppression = SuppressionList(settings.suppression_db_path, settings.tenant.id)
    log = get_logger("blufire.compliance.unsubscribe_server").bind(tenant_id=settings.tenant.id)

    async def get_unsubscribe(request: Request) -> HTMLResponse:
        token = request.path_params["token"]
        try:
            signer.verify(token)
        except TokenInvalid:
            return HTMLResponse("Invalid or expired link.", status_code=400)
        return HTMLResponse(
            f"""<!doctype html>
<html><body style="font-family: sans-serif; max-width: 480px; margin: 4em auto;">
<h1>Confirm unsubscribe</h1>
<p>Click below to stop future emails from {settings.sender.company}.</p>
<form method="post"><button type="submit">Unsubscribe</button></form>
</body></html>""",
            status_code=200,
        )

    async def post_unsubscribe(request: Request) -> JSONResponse | PlainTextResponse:
        token = request.path_params["token"]
        try:
            payload = signer.verify(token)
        except TokenInvalid:
            return PlainTextResponse("Invalid or expired link.", status_code=400)
        suppression.add(payload.email, reason="user_unsubscribed", source="unsubscribe-link")
        log.info("unsubscribed", recipient_hash_prefix=payload.email[:3] + "***")
        return JSONResponse({"status": "unsubscribed"})

    routes = [
        Route("/u/{token:path}", endpoint=get_unsubscribe, methods=["GET"]),
        Route("/u/{token:path}", endpoint=post_unsubscribe, methods=["POST"]),
    ]
    return Starlette(routes=routes)
