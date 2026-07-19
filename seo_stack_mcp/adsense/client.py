"""Google AdSense Management API v2 client (read-only reporting)."""

import os
from datetime import datetime

from googleapiclient.discovery import build

from ..google_auth import get_google_credentials

_service = None


def get_account_id() -> str:
    """The AdSense account, e.g. 'accounts/pub-XXXXXXXXXXXXXXXX'."""
    aid = os.getenv("ADSENSE_ACCOUNT_ID", "").strip()
    if not aid:
        raise ValueError(
            "ADSENSE_ACCOUNT_ID is not set "
            "(format: accounts/pub-XXXXXXXXXXXXXXXX)."
        )
    if not aid.startswith("accounts/"):
        aid = f"accounts/{aid}"
    return aid


def get_currency() -> str:
    return os.getenv("ADSENSE_CURRENCY", "USD").strip() or "USD"


def get_service():
    global _service
    if _service is None:
        _service = build("adsense", "v2", credentials=get_google_credentials())
    return _service


def _parse_report_response(response: dict) -> list[dict]:
    """Flatten an AdSense report response into a list of row dicts."""
    headers = [h.get("name", "") for h in response.get("headers", [])]
    rows = []
    for row in response.get("rows", []):
        cells = row.get("cells", [])
        rows.append(
            {
                header: cells[i].get("value", "") if i < len(cells) else ""
                for i, header in enumerate(headers)
            }
        )
    return rows


def _parse_date(date_str: str) -> tuple[int, int, int]:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.year, dt.month, dt.day


def _report_kwargs(
    metrics: list[str],
    date_range: str | None,
    start_date: str | None,
    end_date: str | None,
) -> dict:
    kwargs = {
        "account": get_account_id(),
        "metrics": metrics,
        "currencyCode": get_currency(),
        "reportingTimeZone": "ACCOUNT_TIME_ZONE",
    }
    if date_range:
        kwargs["dateRange"] = date_range
    elif start_date and end_date:
        sy, sm, sd = _parse_date(start_date)
        ey, em, ed = _parse_date(end_date)
        kwargs.update(
            startDate_year=sy, startDate_month=sm, startDate_day=sd,
            endDate_year=ey, endDate_month=em, endDate_day=ed,
        )
    else:
        kwargs["dateRange"] = "LAST_28_DAYS"
    return kwargs


def run_report(
    metrics: list[str],
    dimensions: list[str] | None = None,
    date_range: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Run an AdSense report and return rows as a list of dicts.

    Either date_range (e.g. 'LAST_28_DAYS') or start_date+end_date.
    """
    kwargs = _report_kwargs(metrics, date_range, start_date, end_date)
    if dimensions:
        kwargs["dimensions"] = dimensions
    if order_by:
        kwargs["orderBy"] = [order_by]
    if limit:
        kwargs["limit"] = limit
    response = get_service().accounts().reports().generate(**kwargs).execute()
    return _parse_report_response(response)


def run_report_totals(
    metrics: list[str],
    date_range: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Run a dimensionless AdSense report and return the totals row."""
    kwargs = _report_kwargs(metrics, date_range, start_date, end_date)
    response = get_service().accounts().reports().generate(**kwargs).execute()
    headers = [h.get("name", "") for h in response.get("headers", [])]
    cells = response.get("totals", {}).get("cells", [])
    return {
        header: cells[i].get("value", "") if i < len(cells) else ""
        for i, header in enumerate(headers)
    }


def list_payments() -> list[dict]:
    response = get_service().accounts().payments().list(parent=get_account_id()).execute()
    return response.get("payments", [])


def list_alerts() -> list[dict]:
    response = get_service().accounts().alerts().list(parent=get_account_id()).execute()
    return response.get("alerts", [])


def list_sites() -> list[dict]:
    response = get_service().accounts().sites().list(parent=get_account_id()).execute()
    return response.get("sites", [])
