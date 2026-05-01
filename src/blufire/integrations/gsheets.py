"""Google Sheets client wrapper.

Single-tenant service-account auth: each tenant gets its own service-account
JSON whose email has been granted edit access to the tenant's sheets. The
JSON path is configured via ``settings.secrets.gsheets_credentials_path``.

API surface is intentionally narrow: append a row to a sheet, list rows from
a sheet. No formula evaluation, no cell formatting. Sheets are an output
target for the daily run, not a workspace.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
from typing import Any

import gspread
from google.oauth2.service_account import Credentials
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from blufire.http import ExternalServiceError
from blufire.logging_setup import get_logger
from blufire.settings import Settings

GSHEETS_SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets",
    # Read-only Drive scope needed to look up sheets by URL/ID.
    "https://www.googleapis.com/auth/drive.readonly",
)


class GSheetsError(ExternalServiceError):
    pass


class GSheetsAuthError(GSheetsError):
    """Service-account JSON missing or unreadable. Don't include the path
    contents in any logged message."""


@lru_cache(maxsize=8)
def _client_for(creds_path: str) -> gspread.Client:
    """Cache the authorized client. The cache is keyed on the credentials
    path so different tenants get different clients in the same process."""
    try:
        creds = Credentials.from_service_account_file(creds_path, scopes=list(GSHEETS_SCOPES))
    except (FileNotFoundError, ValueError) as exc:
        raise GSheetsAuthError(
            f"could not load gsheets service-account credentials ({type(exc).__name__})"
        ) from None
    return gspread.authorize(creds)


class GSheetsClient:
    """Thin wrapper around gspread for the single workflow we have:

    * append a normalized lead/draft row to a worksheet identified by URL
    * list the rows in a worksheet (used for reading curated lists later)
    """

    def __init__(self, settings: Settings) -> None:
        path = settings.secrets.gsheets_credentials_path
        if not path:
            raise GSheetsAuthError("GSHEETS_CREDENTIALS_PATH is not configured.")
        self._client = _client_for(str(path))
        self._log = get_logger("blufire.integrations.gsheets").bind(tenant_id=settings.tenant.id)

    def _open_worksheet(self, sheet_url: str, worksheet: str) -> gspread.Worksheet:
        try:
            sh = self._client.open_by_url(sheet_url)
        except gspread.SpreadsheetNotFound as exc:
            raise GSheetsError("spreadsheet not found / not shared with service account") from exc
        try:
            return sh.worksheet(worksheet)
        except gspread.WorksheetNotFound as exc:
            raise GSheetsError(f"worksheet {worksheet!r} not found in spreadsheet") from exc

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1.0, max=15.0),
        retry=retry_if_exception_type(gspread.exceptions.APIError),
        reraise=True,
    )
    def append_row(
        self,
        sheet_url: str,
        worksheet: str,
        row: Sequence[Any],
    ) -> None:
        """Append a single row at the bottom. Auto-retried on Google API
        errors (rate limits / transient 5xx)."""
        ws = self._open_worksheet(sheet_url, worksheet)
        ws.append_row(list(row), value_input_option="USER_ENTERED")
        self._log.info("gsheets_row_appended", worksheet=worksheet, cells=len(row))

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1.0, max=15.0),
        retry=retry_if_exception_type(gspread.exceptions.APIError),
        reraise=True,
    )
    def list_rows(
        self,
        sheet_url: str,
        worksheet: str,
        *,
        header_row: int = 1,
    ) -> list[dict[str, Any]]:
        """Return every row below ``header_row`` as a dict keyed by header."""
        ws = self._open_worksheet(sheet_url, worksheet)
        return list(ws.get_all_records(head=header_row))
