"""HTTP foundation: a single ``requests.Session`` factory with retries, timeouts,
and per-service circuit breakers. All external HTTP must funnel through here.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

import pybreaker
import requests
from requests.adapters import HTTPAdapter
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)
from urllib3.util.retry import Retry

from blufire.logging_setup import get_logger

DEFAULT_TIMEOUT: tuple[float, float] = (5.0, 30.0)


class ExternalServiceError(RuntimeError):
    """Raised when an external service call exhausts retries or trips the breaker."""


def build_session(
    *,
    total_retries: int = 5,
    backoff_factor: float = 0.5,
    status_forcelist: tuple[int, ...] = (408, 429, 500, 502, 503, 504),
    pool_connections: int = 10,
    pool_maxsize: int = 20,
) -> requests.Session:
    """Construct a ``requests.Session`` with HTTP-level retries on idempotent verbs."""
    retry = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=list(status_forcelist),
        allowed_methods=frozenset({"GET", "POST", "PATCH", "PUT", "DELETE"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=pool_connections,
        pool_maxsize=pool_maxsize,
    )
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


_BREAKERS: dict[str, pybreaker.CircuitBreaker] = {}


def breaker(
    service: str, *, fail_max: int = 5, reset_timeout: int = 60
) -> pybreaker.CircuitBreaker:
    """Return (or create) the named circuit breaker for an external service."""
    if service not in _BREAKERS:
        _BREAKERS[service] = pybreaker.CircuitBreaker(
            fail_max=fail_max,
            reset_timeout=reset_timeout,
            name=service,
            exclude=[requests.HTTPError],
        )
    return _BREAKERS[service]


T = TypeVar("T")


def _log_retry(retry_state: RetryCallState) -> None:
    if retry_state.outcome and retry_state.outcome.failed:
        get_logger("blufire.http").warning(
            "external_call_retry",
            attempt=retry_state.attempt_number,
            wait_seconds=getattr(retry_state.next_action, "sleep", None),
            exception=type(retry_state.outcome.exception()).__name__,
        )


def retry_external(
    *,
    max_attempts: int = 3,
    initial: float = 1.0,
    maximum: float = 30.0,
    exceptions: tuple[type[BaseException], ...] = (
        requests.ConnectionError,
        requests.Timeout,
    ),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator: tenacity exponential-backoff retry for non-HTTP failures.

    Note: ``HTTPAdapter`` already retries on listed status codes; this decorator
    targets connection/timeout failures and other transient exceptions.
    """
    return retry(  # type: ignore[no-any-return]
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential_jitter(initial=initial, max=maximum),
        retry=retry_if_exception_type(exceptions),
        before_sleep=_log_retry,
        reraise=True,
    )


def request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout: tuple[float, float] = DEFAULT_TIMEOUT,
    expected_status: tuple[int, ...] = (200, 201),
    **kwargs: Any,
) -> dict[str, Any] | list[Any]:
    """Issue a request and return JSON. Raises ``ExternalServiceError`` on failure."""
    log = get_logger("blufire.http").bind(method=method, url=url)
    try:
        resp = session.request(method, url, timeout=timeout, **kwargs)
    except requests.RequestException as exc:
        log.error("external_call_failed", exception=type(exc).__name__)
        raise ExternalServiceError(f"{method} {url}: {exc}") from exc

    if resp.status_code not in expected_status:
        log.error("external_call_bad_status", status=resp.status_code)
        raise ExternalServiceError(
            f"{method} {url}: unexpected status {resp.status_code}: {resp.text[:200]}"
        )

    try:
        return resp.json()  # type: ignore[no-any-return]
    except ValueError as exc:
        raise ExternalServiceError(f"{method} {url}: response is not JSON") from exc
