"""GA4 — Google Analytics Data API v1beta client wrapper.

Uses the shared Google credentials (service account or local OAuth) from
``seo_stack_mcp.google_auth``. The Analytics client is cached at module
level and rebuilt once on an Unauthenticated (401) response.
"""

import logging
import os

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest,
    RunRealtimeReportRequest,
    Dimension,
    Metric,
    DateRange,
    FilterExpression,
    OrderBy,
)
from google.api_core.exceptions import Unauthenticated

from ..google_auth import get_google_credentials

log = logging.getLogger("seo-stack-mcp.ga4")

_client: BetaAnalyticsDataClient | None = None


def get_property_id(property_id: str | None = None) -> str:
    """Resolve the GA4 property ID from the argument or the environment."""
    pid = property_id or os.getenv("GA4_PROPERTY_ID", "")
    if not pid:
        raise ValueError(
            "No GA4 property ID configured. Pass property_id (e.g. '123456789') "
            "or set the GA4_PROPERTY_ID environment variable."
        )
    return pid


def _get_client(force_rebuild: bool = False) -> BetaAnalyticsDataClient:
    """Return a cached BetaAnalyticsDataClient, rebuilding it on demand."""
    global _client
    if _client is None or force_rebuild:
        _client = BetaAnalyticsDataClient(credentials=get_google_credentials())
    return _client


def _parse_response_rows(response, dimensions: list[str], metrics: list[str]) -> list[dict]:
    """Extract rows from a GA4 report response."""
    rows = []
    for row in response.rows:
        r = {}
        for i, dim in enumerate(dimensions):
            r[dim] = row.dimension_values[i].value
        for i, met in enumerate(metrics):
            r[met] = row.metric_values[i].value
        rows.append(r)
    return rows


def run_report(
    dimensions: list[str],
    metrics: list[str],
    start_date: str,
    end_date: str,
    limit: int = 100,
    dimension_filter: FilterExpression | None = None,
    order_bys: list[OrderBy] | None = None,
    property_id: str | None = None,
) -> list[dict]:
    """Run a GA4 report and return rows as a list of dicts."""
    pid = get_property_id(property_id)

    request = RunReportRequest(
        property=f"properties/{pid}",
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        limit=limit,
    )
    if dimension_filter:
        request.dimension_filter = dimension_filter
    if order_bys:
        request.order_bys = order_bys

    try:
        response = _get_client().run_report(request)
    except Unauthenticated:
        log.warning("GA4 API returned 401, rebuilding client and retrying")
        response = _get_client(force_rebuild=True).run_report(request)

    return _parse_response_rows(response, dimensions, metrics)


def run_report_compare(
    dimensions: list[str],
    metrics: list[str],
    start_date_1: str,
    end_date_1: str,
    start_date_2: str,
    end_date_2: str,
    limit: int = 100,
    property_id: str | None = None,
) -> list[dict]:
    """Run a GA4 report with two date ranges for comparison."""
    pid = get_property_id(property_id)

    request = RunReportRequest(
        property=f"properties/{pid}",
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        date_ranges=[
            DateRange(start_date=start_date_1, end_date=end_date_1, name="period1"),
            DateRange(start_date=start_date_2, end_date=end_date_2, name="period2"),
        ],
        limit=limit,
    )

    try:
        response = _get_client().run_report(request)
    except Unauthenticated:
        log.warning("GA4 Compare API returned 401, rebuilding client and retrying")
        response = _get_client(force_rebuild=True).run_report(request)

    # With 2 date ranges, GA4 returns metrics doubled: first set for period1, second for period2
    num_metrics = len(metrics)
    rows = []
    for row in response.rows:
        r = {}
        for i, dim in enumerate(dimensions):
            r[dim] = row.dimension_values[i].value
        for i, met in enumerate(metrics):
            r[f"{met}_period1"] = row.metric_values[i].value
            if i + num_metrics < len(row.metric_values):
                r[f"{met}_period2"] = row.metric_values[i + num_metrics].value
        rows.append(r)

    return rows


def run_realtime_report(
    dimensions: list[str],
    metrics: list[str],
    limit: int = 100,
    property_id: str | None = None,
) -> list[dict]:
    """Run a GA4 realtime report."""
    pid = get_property_id(property_id)

    request = RunRealtimeReportRequest(
        property=f"properties/{pid}",
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        limit=limit,
    )

    try:
        response = _get_client().run_realtime_report(request)
    except Unauthenticated:
        log.warning("GA4 Realtime API returned 401, rebuilding client and retrying")
        response = _get_client(force_rebuild=True).run_realtime_report(request)

    return _parse_response_rows(response, dimensions, metrics)


def test_connection(property_id: str | None = None) -> str:
    """Test the GA4 connection with a minimal report. Returns a status string."""
    pid = get_property_id(property_id)

    request = RunReportRequest(
        property=f"properties/{pid}",
        metrics=[Metric(name="activeUsers")],
        date_ranges=[DateRange(start_date="yesterday", end_date="today")],
        limit=1,
    )

    try:
        response = _get_client().run_report(request)
    except Unauthenticated:
        response = _get_client(force_rebuild=True).run_report(request)

    total = 0
    if response.rows:
        total = response.rows[0].metric_values[0].value
    return f"OK — Property {pid}: {total} active users yesterday/today"
