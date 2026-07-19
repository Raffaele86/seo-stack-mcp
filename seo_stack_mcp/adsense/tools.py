"""Google AdSense — 10 MCP tools.

Each tool returns a formatted text table (a plain string), not raw JSON.
"""

import logging
from datetime import datetime, timedelta

from .client import (
    get_account_id,
    get_currency,
    list_alerts,
    list_payments,
    list_sites,
    run_report,
    run_report_totals,
)

log = logging.getLogger("seo-stack-mcp.adsense")


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_number(val) -> str:
    try:
        n = float(val)
        if n == int(n):
            return f"{int(n):,}"
        return f"{n:,.2f}"
    except (ValueError, TypeError):
        return str(val)


def _fmt_currency(val) -> str:
    try:
        n = float(val)
        return f"{n:,.2f} {get_currency()}"
    except (ValueError, TypeError):
        return str(val)


def _fmt_percent(val) -> str:
    try:
        return f"{float(val):.2f}%"
    except (ValueError, TypeError):
        return str(val)


def _fmt_delta(old_str: str, new_str: str) -> str:
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
    if not rows:
        return f"{title}\n(no data)" if title else "(no data)"

    all_rows = [headers] + rows
    widths = [max(len(str(r[i])) for r in all_rows) for i in range(len(headers))]

    lines = []
    if title:
        lines.append(f"=== {title} ===")
        lines.append("")

    lines.append(" | ".join(str(h).ljust(w) for h, w in zip(headers, widths)))
    lines.append("-+-".join("-" * w for w in widths))
    for row in rows:
        lines.append(" | ".join(str(v).ljust(w) for v, w in zip(row, widths)))

    return "\n".join(lines)


def _date_ago(days: int) -> str:
    return (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")


def _days_to_date_range(days: int) -> str | None:
    return {1: "TODAY", 7: "LAST_7_DAYS", 28: "LAST_28_DAYS"}.get(days)


def _report_for_days(days: int, **kwargs) -> list[dict]:
    date_range = _days_to_date_range(days)
    if date_range:
        return run_report(date_range=date_range, **kwargs)
    return run_report(start_date=_date_ago(days), end_date=_date_ago(1), **kwargs)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register(mcp):
    """Register all AdSense tools on the given FastMCP server."""

    @mcp.tool()
    async def adsense_earnings_overview(days: int = 28) -> str:
        """AdSense earnings overview: estimated earnings, page views, impressions,
        clicks, RPM and CTR, aggregated over the last N days (default 28)."""
        metrics = [
            "ESTIMATED_EARNINGS", "PAGE_VIEWS", "IMPRESSIONS",
            "CLICKS", "PAGE_VIEWS_RPM", "IMPRESSIONS_RPM",
            "AD_REQUESTS_CTR",
        ]
        date_range = _days_to_date_range(days)
        if date_range:
            totals = run_report_totals(metrics=metrics, date_range=date_range)
        else:
            totals = run_report_totals(
                metrics=metrics, start_date=_date_ago(days), end_date=_date_ago(1)
            )

        if not totals:
            return "No data for the selected period."

        return "\n".join([
            f"=== AdSense Overview — {get_account_id()} ===",
            f"Period: last {days} days",
            "",
            f"  Estimated earnings:   {_fmt_currency(totals.get('ESTIMATED_EARNINGS', '0'))}",
            f"  Page views:           {_fmt_number(totals.get('PAGE_VIEWS', '0'))}",
            f"  Impressions:          {_fmt_number(totals.get('IMPRESSIONS', '0'))}",
            f"  Clicks:               {_fmt_number(totals.get('CLICKS', '0'))}",
            f"  RPM (per page view):  {_fmt_currency(totals.get('PAGE_VIEWS_RPM', '0'))}",
            f"  RPM (per impression): {_fmt_currency(totals.get('IMPRESSIONS_RPM', '0'))}",
            f"  CTR:                  {_fmt_percent(totals.get('AD_REQUESTS_CTR', '0'))}",
        ])

    @mcp.tool()
    async def adsense_earnings_by_date(
        start_date: str = "", end_date: str = "", days: int = 28
    ) -> str:
        """Daily AdSense earnings with total, average and trend. Pass
        start_date/end_date (YYYY-MM-DD) or days (default 28)."""
        metrics = ["ESTIMATED_EARNINGS", "PAGE_VIEWS", "IMPRESSIONS", "CLICKS"]

        if start_date and end_date:
            rows = run_report(
                metrics=metrics, dimensions=["DATE"],
                start_date=start_date, end_date=end_date, order_by="+DATE",
            )
            period_label = f"{start_date} → {end_date}"
        else:
            rows = _report_for_days(
                days, metrics=metrics, dimensions=["DATE"], order_by="+DATE"
            )
            period_label = f"last {days} days"

        if not rows:
            return "No data for the selected period."

        table_rows = []
        total_earnings = 0.0
        for r in rows:
            earnings = r.get("ESTIMATED_EARNINGS", "0")
            total_earnings += float(earnings) if earnings else 0
            table_rows.append([
                r.get("DATE", ""),
                _fmt_currency(earnings),
                _fmt_number(r.get("PAGE_VIEWS", "0")),
                _fmt_number(r.get("IMPRESSIONS", "0")),
                _fmt_number(r.get("CLICKS", "0")),
            ])

        num_days = len(rows)
        avg_earnings = total_earnings / num_days if num_days > 0 else 0

        result = _fmt_table(
            ["Date", "Earnings", "Page views", "Impressions", "Clicks"],
            table_rows,
            f"Daily Earnings ({period_label})",
        )
        result += "\n\n--- Summary ---"
        result += f"\n  Total:      {_fmt_currency(str(total_earnings))}"
        result += f"\n  Daily avg:  {_fmt_currency(str(avg_earnings))}"
        result += f"\n  Days:       {num_days}"

        if num_days >= 4:
            mid = num_days // 2
            first_half = sum(float(rows[i].get("ESTIMATED_EARNINGS", "0") or 0) for i in range(mid))
            second_half = sum(float(rows[i].get("ESTIMATED_EARNINGS", "0") or 0) for i in range(mid, num_days))
            result += f"\n  Trend:      {_fmt_delta(str(first_half), str(second_half))} (2nd half vs 1st half)"

        return result

    @mcp.tool()
    async def adsense_top_pages(days: int = 28, limit: int = 20) -> str:
        """Top URL channels by revenue (dimension: URL_CHANNEL_NAME).
        Requires URL channels configured in AdSense."""
        rows = _report_for_days(
            days,
            metrics=["ESTIMATED_EARNINGS", "PAGE_VIEWS", "IMPRESSIONS", "CLICKS", "PAGE_VIEWS_RPM"],
            dimensions=["URL_CHANNEL_NAME"],
            order_by="-ESTIMATED_EARNINGS",
            limit=limit,
        )

        table_rows = [
            [
                str(i),
                r.get("URL_CHANNEL_NAME", "")[:55],
                _fmt_currency(r.get("ESTIMATED_EARNINGS", "0")),
                _fmt_number(r.get("PAGE_VIEWS", "0")),
                _fmt_number(r.get("IMPRESSIONS", "0")),
                _fmt_number(r.get("CLICKS", "0")),
                _fmt_currency(r.get("PAGE_VIEWS_RPM", "0")),
            ]
            for i, r in enumerate(rows, 1)
        ]

        return _fmt_table(
            ["#", "Page", "Earnings", "Page views", "Impressions", "Clicks", "RPM"],
            table_rows,
            f"Top {limit} Pages by Revenue (last {days} days)",
        )

    @mcp.tool()
    async def adsense_by_platform(days: int = 28) -> str:
        """Revenue breakdown by device platform (Desktop, Mobile, Tablet)."""
        rows = _report_for_days(
            days,
            metrics=["ESTIMATED_EARNINGS", "PAGE_VIEWS", "IMPRESSIONS", "CLICKS", "PAGE_VIEWS_RPM"],
            dimensions=["PLATFORM_TYPE_NAME"],
            order_by="-ESTIMATED_EARNINGS",
        )

        table_rows = [
            [
                r.get("PLATFORM_TYPE_NAME", ""),
                _fmt_currency(r.get("ESTIMATED_EARNINGS", "0")),
                _fmt_number(r.get("PAGE_VIEWS", "0")),
                _fmt_number(r.get("IMPRESSIONS", "0")),
                _fmt_number(r.get("CLICKS", "0")),
                _fmt_currency(r.get("PAGE_VIEWS_RPM", "0")),
            ]
            for r in rows
        ]

        return _fmt_table(
            ["Platform", "Earnings", "Page views", "Impressions", "Clicks", "RPM"],
            table_rows,
            f"Performance by Platform (last {days} days)",
        )

    @mcp.tool()
    async def adsense_by_country(days: int = 28, limit: int = 15) -> str:
        """Revenue breakdown by country, sorted by earnings."""
        rows = _report_for_days(
            days,
            metrics=["ESTIMATED_EARNINGS", "IMPRESSIONS", "CLICKS", "IMPRESSIONS_RPM"],
            dimensions=["COUNTRY_NAME"],
            order_by="-ESTIMATED_EARNINGS",
            limit=limit,
        )

        table_rows = [
            [
                str(i),
                r.get("COUNTRY_NAME", "")[:25],
                _fmt_currency(r.get("ESTIMATED_EARNINGS", "0")),
                _fmt_number(r.get("IMPRESSIONS", "0")),
                _fmt_number(r.get("CLICKS", "0")),
                _fmt_currency(r.get("IMPRESSIONS_RPM", "0")),
            ]
            for i, r in enumerate(rows, 1)
        ]

        return _fmt_table(
            ["#", "Country", "Earnings", "Impressions", "Clicks", "eCPM"],
            table_rows,
            f"Performance by Country (last {days} days)",
        )

    @mcp.tool()
    async def adsense_by_ad_unit(days: int = 28, limit: int = 20) -> str:
        """Performance per ad unit: earnings, impressions, clicks, CTR, eCPM."""
        rows = _report_for_days(
            days,
            metrics=["ESTIMATED_EARNINGS", "IMPRESSIONS", "CLICKS", "AD_REQUESTS_CTR", "IMPRESSIONS_RPM"],
            dimensions=["AD_UNIT_NAME"],
            order_by="-ESTIMATED_EARNINGS",
            limit=limit,
        )

        table_rows = [
            [
                str(i),
                r.get("AD_UNIT_NAME", "")[:35],
                _fmt_currency(r.get("ESTIMATED_EARNINGS", "0")),
                _fmt_number(r.get("IMPRESSIONS", "0")),
                _fmt_number(r.get("CLICKS", "0")),
                _fmt_percent(r.get("AD_REQUESTS_CTR", "0")),
                _fmt_currency(r.get("IMPRESSIONS_RPM", "0")),
            ]
            for i, r in enumerate(rows, 1)
        ]

        return _fmt_table(
            ["#", "Ad Unit", "Earnings", "Impressions", "Clicks", "CTR", "eCPM"],
            table_rows,
            f"Performance by Ad Unit (last {days} days)",
        )

    @mcp.tool()
    async def adsense_compare_periods(
        period1_start: str, period1_end: str, period2_start: str, period2_end: str
    ) -> str:
        """Compare two periods with percentage deltas on key metrics.
        Period 1 = current, period 2 = baseline. Dates in YYYY-MM-DD."""
        metrics = ["ESTIMATED_EARNINGS", "PAGE_VIEWS", "IMPRESSIONS", "CLICKS", "PAGE_VIEWS_RPM"]

        totals_p1 = run_report_totals(metrics=metrics, start_date=period1_start, end_date=period1_end)
        totals_p2 = run_report_totals(metrics=metrics, start_date=period2_start, end_date=period2_end)

        labels = {
            "ESTIMATED_EARNINGS": "Earnings",
            "PAGE_VIEWS": "Page views",
            "IMPRESSIONS": "Impressions",
            "CLICKS": "Clicks",
            "PAGE_VIEWS_RPM": "RPM",
        }
        currency_metrics = {"ESTIMATED_EARNINGS", "PAGE_VIEWS_RPM"}

        table_rows = []
        for met in metrics:
            v1 = totals_p1.get(met, "0")
            v2 = totals_p2.get(met, "0")
            fmt = _fmt_currency if met in currency_metrics else _fmt_number
            table_rows.append([labels[met], fmt(v1), fmt(v2), _fmt_delta(v2, v1)])

        return "\n".join([
            "=== Period Comparison ===",
            f"Period 1: {period1_start} → {period1_end}",
            f"Period 2: {period2_start} → {period2_end}",
            "",
            _fmt_table(["Metric", "Period 1", "Period 2", "Delta"], table_rows),
        ])

    @mcp.tool()
    async def adsense_payments() -> str:
        """Recent payments on the AdSense account (date, amount, id)."""
        payments = list_payments()
        if not payments:
            return "=== AdSense Payments ===\n\nNo payments found."

        table_rows = []
        for p in payments:
            date_obj = p.get("date", {})
            if isinstance(date_obj, dict):
                y = date_obj.get("year", "")
                m = date_obj.get("month", "")
                d = date_obj.get("day", "")
                date_display = f"{y}-{str(m).zfill(2)}-{str(d).zfill(2)}" if y else ""
            else:
                date_display = str(date_obj)
            name = p.get("name", "")
            table_rows.append([
                date_display,
                str(p.get("amount", "")),
                name.split("/")[-1] if "/" in name else name,
            ])

        return _fmt_table(["Date", "Amount", "ID"], table_rows, "AdSense Payments")

    @mcp.tool()
    async def adsense_alerts() -> str:
        """Active alerts on the AdSense account (severity, type, message)."""
        alerts = list_alerts()
        if not alerts:
            return "=== AdSense Alerts ===\n\nNo active alerts."

        table_rows = [
            [a.get("severity", ""), a.get("type", ""), a.get("message", "")[:80]]
            for a in alerts
        ]
        return _fmt_table(["Severity", "Type", "Message"], table_rows, "AdSense Alerts")

    @mcp.tool()
    async def adsense_sites() -> str:
        """Sites linked to the AdSense account (domain, state, auto-ads)."""
        sites = list_sites()
        if not sites:
            return "=== AdSense Sites ===\n\nNo sites linked."

        table_rows = [
            [
                s.get("domain", s.get("name", "")),
                s.get("state", ""),
                "Yes" if s.get("autoAdsEnabled") else "No",
            ]
            for s in sites
        ]
        return _fmt_table(["Domain", "State", "Auto-ads"], table_rows, "AdSense Sites")

    log.info("registered 10 AdSense tools")
