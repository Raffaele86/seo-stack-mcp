"""GA4 MCP tools.

Each tool returns a formatted text table (not raw JSON). All tools accept an
optional ``property_id``; when omitted, the ``GA4_PROPERTY_ID`` environment
variable is used.
"""

import logging

from google.analytics.data_v1beta.types import (
    FilterExpression,
    Filter,
    OrderBy,
)

from .client import (
    run_report,
    run_realtime_report,
    get_property_id,
)

log = logging.getLogger("seo-stack-mcp.ga4")


# ---------------------------------------------------------------------------
# Formatting Helpers
# ---------------------------------------------------------------------------

def _fmt_number(val: str) -> str:
    """Format a number string with thousands separator."""
    try:
        n = float(val)
        if n == int(n):
            return f"{int(n):,}"
        return f"{n:,.2f}"
    except (ValueError, TypeError):
        return val


def _fmt_duration(seconds_str: str) -> str:
    """Format seconds into Xm Ys."""
    try:
        s = float(seconds_str)
        m = int(s) // 60
        sec = int(s) % 60
        if m > 0:
            return f"{m}m {sec}s"
        return f"{sec}s"
    except (ValueError, TypeError):
        return seconds_str


def _fmt_percent(val: str, multiply_100: bool = True) -> str:
    """Format a decimal as percentage."""
    try:
        n = float(val)
        if multiply_100:
            n *= 100
        return f"{n:.1f}%"
    except (ValueError, TypeError):
        return val


def _fmt_delta(old_str: str, new_str: str) -> str:
    """Calculate percentage delta between two values."""
    try:
        old = float(old_str)
        new = float(new_str)
        if old == 0:
            return "N/A" if new == 0 else "+inf"
        delta = ((new - old) / abs(old)) * 100
        sign = "+" if delta >= 0 else ""
        return f"{sign}{delta:.1f}%"
    except (ValueError, TypeError):
        return "N/A"


def _fmt_table(headers: list[str], rows: list[list[str]], title: str = "") -> str:
    """Build a formatted text table with aligned columns."""
    if not rows:
        return f"{title}\n(no data)" if title else "(no data)"

    # Calculate column widths
    all_rows = [headers] + rows
    widths = [max(len(str(r[i])) for r in all_rows) for i in range(len(headers))]

    # Build table
    lines = []
    if title:
        lines.append(f"=== {title} ===")
        lines.append("")

    # Header
    header_line = " | ".join(str(h).ljust(w) for h, w in zip(headers, widths))
    lines.append(header_line)
    lines.append("-+-".join("-" * w for w in widths))

    # Rows
    for row in rows:
        line = " | ".join(str(v).ljust(w) for v, w in zip(row, widths))
        lines.append(line)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool Registration
# ---------------------------------------------------------------------------

def register(mcp):
    """Register all GA4 tools on the given FastMCP server."""

    @mcp.tool()
    async def ga4_overview(
        start_date: str = "28daysAgo",
        end_date: str = "yesterday",
        property_id: str | None = None,
    ) -> str:
        """Site overview: users, sessions, pageviews, bounce rate, average session duration.
        Dates in YYYY-MM-DD format or 'NdaysAgo', 'yesterday', 'today'.
        property_id: GA4 property ID (e.g. '123456789'); defaults to GA4_PROPERTY_ID env var."""
        rows = run_report(
            dimensions=[],
            metrics=[
                "totalUsers", "sessions", "screenPageViews",
                "bounceRate", "averageSessionDuration",
            ],
            start_date=start_date,
            end_date=end_date,
            limit=1,
            property_id=property_id,
        )

        if not rows:
            return "No data for the selected period."

        r = rows[0]
        pid = get_property_id(property_id)
        lines = [
            f"=== GA4 Overview — Property {pid} ===",
            f"Period: {start_date} → {end_date}",
            "",
            f"  Total users:          {_fmt_number(r.get('totalUsers', '0'))}",
            f"  Sessions:             {_fmt_number(r.get('sessions', '0'))}",
            f"  Pageviews:            {_fmt_number(r.get('screenPageViews', '0'))}",
            f"  Bounce Rate:          {_fmt_percent(r.get('bounceRate', '0'))}",
            f"  Avg session duration: {_fmt_duration(r.get('averageSessionDuration', '0'))}",
        ]
        return "\n".join(lines)

    @mcp.tool()
    async def ga4_top_pages(
        start_date: str = "28daysAgo",
        end_date: str = "yesterday",
        limit: int = 20,
        property_id: str | None = None,
    ) -> str:
        """Top pages by traffic with full metrics (pageviews, users, duration, bounce rate).
        Dates in YYYY-MM-DD format or 'NdaysAgo', 'yesterday', 'today'.
        property_id: GA4 property ID (e.g. '123456789'); defaults to GA4_PROPERTY_ID env var."""
        rows = run_report(
            dimensions=["pagePath"],
            metrics=["screenPageViews", "totalUsers", "averageSessionDuration", "bounceRate"],
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="screenPageViews"), desc=True)],
            property_id=property_id,
        )

        table_rows = []
        for i, r in enumerate(rows, 1):
            table_rows.append([
                str(i),
                r["pagePath"][:60],
                _fmt_number(r["screenPageViews"]),
                _fmt_number(r["totalUsers"]),
                _fmt_duration(r["averageSessionDuration"]),
                _fmt_percent(r["bounceRate"]),
            ])

        return _fmt_table(
            ["#", "Page", "Pageviews", "Users", "Duration", "Bounce"],
            table_rows,
            f"Top {limit} Pages ({start_date} → {end_date})",
        )

    @mcp.tool()
    async def ga4_traffic_sources(
        start_date: str = "28daysAgo",
        end_date: str = "yesterday",
        limit: int = 20,
        property_id: str | None = None,
    ) -> str:
        """Traffic breakdown by source/medium (e.g. google/organic, direct/none).
        Dates in YYYY-MM-DD format or 'NdaysAgo', 'yesterday', 'today'.
        property_id: GA4 property ID (e.g. '123456789'); defaults to GA4_PROPERTY_ID env var."""
        rows = run_report(
            dimensions=["sessionSource", "sessionMedium"],
            metrics=["sessions", "totalUsers", "bounceRate", "averageSessionDuration"],
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
            property_id=property_id,
        )

        table_rows = []
        for i, r in enumerate(rows, 1):
            source_medium = f"{r['sessionSource']} / {r['sessionMedium']}"
            table_rows.append([
                str(i),
                source_medium[:40],
                _fmt_number(r["sessions"]),
                _fmt_number(r["totalUsers"]),
                _fmt_percent(r["bounceRate"]),
                _fmt_duration(r["averageSessionDuration"]),
            ])

        return _fmt_table(
            ["#", "Source / Medium", "Sessions", "Users", "Bounce", "Duration"],
            table_rows,
            f"Traffic Sources ({start_date} → {end_date})",
        )

    @mcp.tool()
    async def ga4_page_performance(
        page_path: str,
        start_date: str = "28daysAgo",
        end_date: str = "yesterday",
        property_id: str | None = None,
    ) -> str:
        """Detailed performance of a single page with device and source breakdown.
        page_path: page path (e.g. '/pricing').
        Dates in YYYY-MM-DD format or 'NdaysAgo', 'yesterday', 'today'.
        property_id: GA4 property ID (e.g. '123456789'); defaults to GA4_PROPERTY_ID env var."""
        page_filter = FilterExpression(
            filter=Filter(
                field_name="pagePath",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.CONTAINS,
                    value=page_path,
                ),
            )
        )

        # Main metrics
        main = run_report(
            dimensions=["pagePath"],
            metrics=["screenPageViews", "totalUsers", "sessions", "averageSessionDuration", "bounceRate"],
            start_date=start_date,
            end_date=end_date,
            limit=1,
            dimension_filter=page_filter,
            property_id=property_id,
        )

        lines = [f"=== Page Performance: {page_path} ===", f"Period: {start_date} → {end_date}", ""]

        if main:
            r = main[0]
            lines.extend([
                f"  Pageviews:   {_fmt_number(r['screenPageViews'])}",
                f"  Users:       {_fmt_number(r['totalUsers'])}",
                f"  Sessions:    {_fmt_number(r['sessions'])}",
                f"  Duration:    {_fmt_duration(r['averageSessionDuration'])}",
                f"  Bounce Rate: {_fmt_percent(r['bounceRate'])}",
            ])
        else:
            lines.append("  No data found for this page.")
            return "\n".join(lines)

        # Device breakdown
        device_rows = run_report(
            dimensions=["deviceCategory"],
            metrics=["sessions", "totalUsers"],
            start_date=start_date,
            end_date=end_date,
            limit=10,
            dimension_filter=page_filter,
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
            property_id=property_id,
        )

        lines.append("")
        lines.append("--- By Device ---")
        for r in device_rows:
            lines.append(f"  {r['deviceCategory']:12s}  {_fmt_number(r['sessions']):>8s} sessions  {_fmt_number(r['totalUsers']):>8s} users")

        # Source breakdown
        source_rows = run_report(
            dimensions=["sessionSource"],
            metrics=["sessions", "totalUsers"],
            start_date=start_date,
            end_date=end_date,
            limit=10,
            dimension_filter=page_filter,
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
            property_id=property_id,
        )

        lines.append("")
        lines.append("--- By Source ---")
        for r in source_rows:
            lines.append(f"  {r['sessionSource']:20s}  {_fmt_number(r['sessions']):>8s} sessions  {_fmt_number(r['totalUsers']):>8s} users")

        return "\n".join(lines)

    @mcp.tool()
    async def ga4_realtime(property_id: str | None = None) -> str:
        """Realtime report: pages currently being viewed and active users.
        No date parameters required.
        property_id: GA4 property ID (e.g. '123456789'); defaults to GA4_PROPERTY_ID env var."""
        # Overall active users
        overall = run_realtime_report(
            dimensions=[],
            metrics=["activeUsers"],
            limit=1,
            property_id=property_id,
        )

        total_active = "0"
        if overall:
            total_active = overall[0].get("activeUsers", "0")

        # By page
        page_rows = run_realtime_report(
            dimensions=["unifiedScreenName"],
            metrics=["activeUsers"],
            limit=20,
            property_id=property_id,
        )

        lines = [
            "=== GA4 Realtime ===",
            f"Active users now: {_fmt_number(total_active)}",
            "",
        ]

        if page_rows:
            table_rows = []
            for i, r in enumerate(page_rows, 1):
                table_rows.append([
                    str(i),
                    r["unifiedScreenName"][:60],
                    _fmt_number(r["activeUsers"]),
                ])
            lines.append(_fmt_table(["#", "Page", "Users"], table_rows))
        else:
            lines.append("No active users at the moment.")

        return "\n".join(lines)

    @mcp.tool()
    async def ga4_user_demographics(
        start_date: str = "28daysAgo",
        end_date: str = "yesterday",
        limit: int = 10,
        property_id: str | None = None,
    ) -> str:
        """User demographics breakdown: country, device, browser, language.
        Dates in YYYY-MM-DD format or 'NdaysAgo', 'yesterday', 'today'.
        property_id: GA4 property ID (e.g. '123456789'); defaults to GA4_PROPERTY_ID env var."""
        sections = [
            ("country", "Country"),
            ("deviceCategory", "Device"),
            ("browser", "Browser"),
            ("language", "Language"),
        ]

        all_lines = [f"=== User Demographics ({start_date} → {end_date}) ===", ""]

        for dim_name, label in sections:
            rows = run_report(
                dimensions=[dim_name],
                metrics=["totalUsers", "sessions"],
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="totalUsers"), desc=True)],
                property_id=property_id,
            )

            table_rows = []
            for i, r in enumerate(rows, 1):
                table_rows.append([
                    str(i),
                    r[dim_name][:30],
                    _fmt_number(r["totalUsers"]),
                    _fmt_number(r["sessions"]),
                ])

            all_lines.append(_fmt_table(
                ["#", label, "Users", "Sessions"],
                table_rows,
                f"By {label}",
            ))
            all_lines.append("")

        return "\n".join(all_lines)

    @mcp.tool()
    async def ga4_landing_pages(
        start_date: str = "28daysAgo",
        end_date: str = "yesterday",
        limit: int = 20,
        property_id: str | None = None,
    ) -> str:
        """Entry pages (landing pages) with sessions, users and bounce rate.
        Dates in YYYY-MM-DD format or 'NdaysAgo', 'yesterday', 'today'.
        property_id: GA4 property ID (e.g. '123456789'); defaults to GA4_PROPERTY_ID env var."""
        rows = run_report(
            dimensions=["landingPagePlusQueryString"],
            metrics=["sessions", "totalUsers", "bounceRate", "averageSessionDuration"],
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
            property_id=property_id,
        )

        table_rows = []
        for i, r in enumerate(rows, 1):
            table_rows.append([
                str(i),
                r["landingPagePlusQueryString"][:55],
                _fmt_number(r["sessions"]),
                _fmt_number(r["totalUsers"]),
                _fmt_percent(r["bounceRate"]),
                _fmt_duration(r["averageSessionDuration"]),
            ])

        return _fmt_table(
            ["#", "Landing Page", "Sessions", "Users", "Bounce", "Duration"],
            table_rows,
            f"Landing Pages ({start_date} → {end_date})",
        )

    @mcp.tool()
    async def ga4_compare_periods(
        period1_start: str,
        period1_end: str,
        period2_start: str,
        period2_end: str,
        property_id: str | None = None,
    ) -> str:
        """Compare two periods with percentage delta on key metrics.
        Period 1 is the current period, Period 2 is the comparison (previous) one.
        Dates in YYYY-MM-DD format.
        property_id: GA4 property ID (e.g. '123456789'); defaults to GA4_PROPERTY_ID env var."""
        metrics = ["totalUsers", "sessions", "screenPageViews", "bounceRate", "averageSessionDuration"]

        # Run two separate reports for cleaner comparison
        rows_p1 = run_report(
            dimensions=[],
            metrics=metrics,
            start_date=period1_start,
            end_date=period1_end,
            limit=1,
            property_id=property_id,
        )
        rows_p2 = run_report(
            dimensions=[],
            metrics=metrics,
            start_date=period2_start,
            end_date=period2_end,
            limit=1,
            property_id=property_id,
        )

        p1 = rows_p1[0] if rows_p1 else {}
        p2 = rows_p2[0] if rows_p2 else {}

        labels = {
            "totalUsers": "Users",
            "sessions": "Sessions",
            "screenPageViews": "Pageviews",
            "bounceRate": "Bounce Rate",
            "averageSessionDuration": "Avg duration",
        }

        lines = [
            "=== Period Comparison ===",
            f"Period 1: {period1_start} → {period1_end}",
            f"Period 2: {period2_start} → {period2_end}",
            "",
        ]

        table_rows = []
        for met in metrics:
            v1 = p1.get(met, "0")
            v2 = p2.get(met, "0")

            if met == "bounceRate":
                fmt1 = _fmt_percent(v1)
                fmt2 = _fmt_percent(v2)
            elif met == "averageSessionDuration":
                fmt1 = _fmt_duration(v1)
                fmt2 = _fmt_duration(v2)
            else:
                fmt1 = _fmt_number(v1)
                fmt2 = _fmt_number(v2)

            delta = _fmt_delta(v2, v1)
            table_rows.append([labels[met], fmt1, fmt2, delta])

        lines.append(_fmt_table(["Metric", "Period 1", "Period 2", "Delta"], table_rows))

        return "\n".join(lines)

    @mcp.tool()
    async def ga4_events(
        start_date: str = "28daysAgo",
        end_date: str = "yesterday",
        limit: int = 20,
        property_id: str | None = None,
    ) -> str:
        """Top GA4 events with count and number of users.
        Dates in YYYY-MM-DD format or 'NdaysAgo', 'yesterday', 'today'.
        property_id: GA4 property ID (e.g. '123456789'); defaults to GA4_PROPERTY_ID env var."""
        rows = run_report(
            dimensions=["eventName"],
            metrics=["eventCount", "totalUsers"],
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="eventCount"), desc=True)],
            property_id=property_id,
        )

        table_rows = []
        for i, r in enumerate(rows, 1):
            table_rows.append([
                str(i),
                r["eventName"][:40],
                _fmt_number(r["eventCount"]),
                _fmt_number(r["totalUsers"]),
            ])

        return _fmt_table(
            ["#", "Event", "Count", "Users"],
            table_rows,
            f"Top Events ({start_date} → {end_date})",
        )

    @mcp.tool()
    async def ga4_conversion_paths(
        start_date: str = "28daysAgo",
        end_date: str = "yesterday",
        limit: int = 20,
        property_id: str | None = None,
    ) -> str:
        """User paths: acquisition source → landing page with sessions and users.
        Dates in YYYY-MM-DD format or 'NdaysAgo', 'yesterday', 'today'.
        property_id: GA4 property ID (e.g. '123456789'); defaults to GA4_PROPERTY_ID env var."""
        rows = run_report(
            dimensions=["sessionSource", "landingPagePlusQueryString"],
            metrics=["sessions", "totalUsers"],
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
            property_id=property_id,
        )

        table_rows = []
        for i, r in enumerate(rows, 1):
            table_rows.append([
                str(i),
                r["sessionSource"][:20],
                r["landingPagePlusQueryString"][:40],
                _fmt_number(r["sessions"]),
                _fmt_number(r["totalUsers"]),
            ])

        return _fmt_table(
            ["#", "Source", "Landing Page", "Sessions", "Users"],
            table_rows,
            f"Conversion Paths ({start_date} → {end_date})",
        )

    log.info("Registered 10 GA4 tools")
