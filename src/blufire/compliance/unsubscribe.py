"""HMAC-signed unsubscribe tokens + List-Unsubscribe header builders.

The signing secret is stored at ``$paths.data_dir/.unsubscribe_secret`` with
mode 0600. Tokens encode the email and an expiry timestamp; tampering or
replay-after-expiry returns invalid.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from blufire.compliance._db import normalize_email
from blufire.settings import Settings

_DEFAULT_TTL_SECONDS = 60 * 60 * 24 * 365 * 2  # 2 years; CAN-SPAM requires 30+ days
_SECRET_FILE = ".unsubscribe_secret"  # noqa: S105 — file name, not a credential


def _load_or_create_secret(data_dir: Path) -> bytes:
    path = data_dir / _SECRET_FILE
    if path.exists():
        return path.read_bytes()
    data_dir.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_bytes(32)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, secret)
    finally:
        os.close(fd)
    return secret


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


@dataclass(frozen=True)
class UnsubscribeToken:
    email: str
    expires_at: int
    raw: str


class TokenInvalid(ValueError):
    """Raised when a token signature doesn't match or has expired."""


class UnsubscribeSigner:
    def __init__(self, settings: Settings, *, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        self._secret = _load_or_create_secret(settings.paths.data_dir)
        self._tenant = settings.tenant.id
        self._ttl = ttl_seconds
        self._base = (
            str(settings.compliance.unsubscribe_base_url).rstrip("/")
            if settings.compliance.unsubscribe_base_url
            else None
        )

    def sign(self, email: str) -> str:
        norm = normalize_email(email)
        expires = int(time.time()) + self._ttl
        payload = f"{norm}|{self._tenant}|{expires}".encode()
        sig = hmac.new(self._secret, payload, hashlib.sha256).digest()
        return f"{_b64url(payload)}.{_b64url(sig)}"

    def verify(self, token: str) -> UnsubscribeToken:
        try:
            payload_b64, sig_b64 = token.split(".", 1)
            payload = _b64url_decode(payload_b64)
            sig = _b64url_decode(sig_b64)
        except (ValueError, base64.binascii.Error) as exc:
            raise TokenInvalid("malformed token") from exc

        expected = hmac.new(self._secret, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            raise TokenInvalid("bad signature")

        try:
            email, tenant, expires_str = payload.decode("utf-8").split("|")
        except (UnicodeDecodeError, ValueError) as exc:
            raise TokenInvalid("malformed payload") from exc

        if tenant != self._tenant:
            raise TokenInvalid("wrong tenant")
        try:
            expires = int(expires_str)
        except ValueError as exc:
            raise TokenInvalid("bad expiry") from exc
        if int(time.time()) > expires:
            raise TokenInvalid("expired")

        return UnsubscribeToken(email=email, expires_at=expires, raw=token)

    def build_link(self, email: str) -> str:
        if not self._base:
            raise RuntimeError(
                "compliance.unsubscribe_base_url is not configured. "
                "Set UNSUBSCRIBE_BASE_URL or compliance.unsubscribe_base_url."
            )
        return f"{self._base}/u/{self.sign(email)}"

    def build_list_unsubscribe(self, email: str, mailto: str | None = None) -> str:
        """Return a valid ``List-Unsubscribe`` header value (RFC 8058)."""
        link = self.build_link(email)
        if mailto:
            return f"<{link}>, <mailto:{mailto}?subject=unsubscribe>"
        return f"<{link}>"
