"""MCP tools wrapping the Microsoft Clarity Data Export API.

The Clarity endpoint returns *all* metrics (Traffic, Engagement Time, Popular
Pages, Dead Click, Rage Click, etc.) in a single response, grouped by the
dimensions requested. Tools share the cache: e.g. clarity_popular_pages,
clarity_dead_clicks, clarity_rage_clicks etc. all hit the same
(days, "URL", None, None) cached payload — one API call feeds them all.
"""

import logging
from typing import Any, Optional

from . import cache, client, quota

log = logging.getLogger("seo-stack-mcp.clarity")


# ───── Helpers ─────

# The real metricName values returned by the API are CamelCase without spaces
# (Microsoft docs show "Dead Click Count" but the API returns "DeadClickCount").
METRIC = {
    "traffic": "Traffic",
    "engagement_time": "EngagementTime",
    "scroll_depth": "ScrollDepth",
    "dead_click": "DeadClickCount",
    "rage_click": "RageClickCount",
    "excessive_scroll": "ExcessiveScroll",
    "quickback_click": "QuickbackClick",
    "script_error": "ScriptErrorCount",
    "error_click": "ErrorClickCount",
}

# Metric (non-dimension) keys present in Clarity rows. Anything NOT in this set
# is treated as a dimension key. This lets us recover the dimension value
# without worrying about casing (e.g. URL -> Url, totalSessionCount stays as-is).
_VALUE_KEYS = {
    "sessionsCount", "sessionsWithMetricPercentage", "sessionsWithoutMetricPercentage",
    "pagesViews", "subTotal",
    "totalSessionCount", "totalBotSessionCount", "distinctUserCount",
    "pagesPerSessionPercentage",
    "totalTime", "activeTime",
    "averageScrollDepth",
}


def _metric_rows(payload: Any, metric_name: str) -> list[dict]:
    """Extract the `information` list for a given metricName from a Clarity payload."""
    if not isinstance(payload, list):
        return []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        if entry.get("metricName") == metric_name:
            info = entry.get("information")
            return info if isinstance(info, list) else []
    return []


def _dim_value(row: dict) -> Any:
    """Extract the first dimension value from the row (any non-value key)."""
    if not isinstance(row, dict):
        return None
    for k, v in row.items():
        if k not in _VALUE_KEYS and k != "metricName":
            return v
    return None


def _count(row: dict) -> int:
    """Extract subTotal (for click-based metrics)."""
    return _to_int(row.get("subTotal") or row.get("sessionsCount") or 0)


def _to_int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return 0


def _to_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _format_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "  (no data)"
    str_rows = [[str(c) if c is not None else "—" for c in r] for r in rows]
    all_rows = [headers] + str_rows
    widths = [max(len(r[i]) for r in all_rows) for i in range(len(headers))]
    out = []
    out.append(" | ".join(h.ljust(w) for h, w in zip(headers, widths)))
    out.append("-+-".join("-" * w for w in widths))
    for r in str_rows:
        out.append(" | ".join(c.ljust(w) for c, w in zip(r, widths)))
    return "\n".join(out)


def _footer(from_cache: bool) -> str:
    if from_cache:
        return "\n(cache hit, 0 API calls consumed)"
    project = client.project_key()
    return (
        f"\n(1 Clarity API call consumed — "
        f"used today {quota.used(project)}/{quota.status()['daily_limit']})"
    )


def _err(e: Exception) -> str:
    return f"Clarity error: {e}"


# ───── Registration ─────

def register(mcp) -> None:
    """Register all Clarity tools on the given FastMCP server."""

    @mcp.tool()
    async def clarity_traffic(
        days: int = 1,
        dimension: str = "OS",
    ) -> str:
        """Traffic breakdown from Microsoft Clarity (sessions, bot %, pages per session).

        days: 1, 2 or 3 (last 24/48/72h).
        dimension: one of Browser, Device, Country/Region, OS, Source, Medium, Campaign, Channel, URL.
        """
        try:
            payload, hit = await client.fetch_insights(days, dimension)
        except client.ClarityError as e:
            return _err(e)

        rows_raw = _metric_rows(payload, METRIC["traffic"])
        rows = []
        for r in rows_raw:
            total = _to_int(r.get("totalSessionCount"))
            bots = _to_int(r.get("totalBotSessionCount"))
            distinct = _to_int(r.get("distinctUserCount"))
            pps = _to_float(r.get("pagesPerSessionPercentage"))
            bot_pct = (bots / total * 100) if total else 0
            dim_val = _dim_value(r)
            rows.append([
                dim_val if dim_val is not None else "—",
                total,
                f"{bot_pct:.1f}%",
                distinct,
                f"{pps:.2f}",
            ])
        rows.sort(key=lambda r: r[1], reverse=True)
        out = [
            f"=== Clarity Traffic (last {days}d) ===",
            "",
            _format_table(
                [dimension, "Sessions", "Bot %", "Distinct Users", "Pages/Session"],
                rows,
            ),
            _footer(hit),
        ]
        return "\n".join(out)

    @mcp.tool()
    async def clarity_popular_pages(
        days: int = 1,
        limit: int = 20,
    ) -> str:
        """Top URLs by visits over the last days (Popular Pages metric, dimension=URL).

        Shares the cache with all other URL-based tools: 1 API call feeds
        popular_pages + dead_clicks + rage_clicks + excessive_scroll + quickback + script_errors.
        """
        try:
            payload, hit = await client.fetch_insights(days, "URL")
        except client.ClarityError as e:
            return _err(e)

        # Popular Pages = Traffic with dimension=URL: sort URLs by totalSessionCount.
        rows_raw = _metric_rows(payload, METRIC["traffic"])
        rows = []
        for r in rows_raw:
            url = _dim_value(r)
            if url is None:
                continue
            visits = _to_int(r.get("totalSessionCount"))
            users = _to_int(r.get("distinctUserCount"))
            rows.append([url, visits, users])
        rows.sort(key=lambda r: r[1], reverse=True)
        rows = rows[:limit]
        return "\n".join([
            f"=== Clarity Popular Pages (last {days}d, top {limit}) ===",
            "",
            _format_table(["URL", "Sessions", "Distinct Users"], rows),
            _footer(hit),
        ])

    @mcp.tool()
    async def clarity_engagement(
        days: int = 1,
        dimension: str = "URL",
        limit: int = 20,
    ) -> str:
        """Engagement Time + Scroll Depth per URL (or another dimension).

        For URL it shares the cache with popular_pages and the other URL-based tools.
        """
        try:
            payload, hit = await client.fetch_insights(days, dimension)
        except client.ClarityError as e:
            return _err(e)

        eng_rows = [r for r in _metric_rows(payload, METRIC["engagement_time"]) if isinstance(r, dict)]
        scroll_rows = [r for r in _metric_rows(payload, METRIC["scroll_depth"]) if isinstance(r, dict)]
        eng = {_dim_value(r): r for r in eng_rows}
        scroll = {_dim_value(r): r for r in scroll_rows}
        keys = list({*eng.keys(), *scroll.keys()})
        rows = []
        for k in keys:
            if k is None:
                continue
            e = eng.get(k, {})
            s = scroll.get(k, {})
            total_sec = _to_float(e.get("totalTime"))
            active_sec = _to_float(e.get("activeTime"))
            scroll_pct = _to_float(s.get("averageScrollDepth"))
            rows.append([k, f"{total_sec:.0f}s", f"{active_sec:.0f}s", f"{scroll_pct:.1f}%"])
        rows.sort(key=lambda r: _to_float(r[1][:-1]), reverse=True)
        rows = rows[:limit]
        return "\n".join([
            f"=== Clarity Engagement (last {days}d, top {limit} by {dimension}) ===",
            "",
            _format_table([dimension, "Total Time", "Active Time", "Scroll Depth"], rows),
            _footer(hit),
        ])

    @mcp.tool()
    async def clarity_dead_clicks(
        days: int = 1,
        limit: int = 20,
    ) -> str:
        """Top URLs with dead clicks (clicks on non-interactive elements — a UX problem signal).

        Shares the cache with all URL-based tools: 0 extra calls if a URL fetch already ran today.
        """
        try:
            payload, hit = await client.fetch_insights(days, "URL")
        except client.ClarityError as e:
            return _err(e)

        rows_raw = _metric_rows(payload, METRIC["dead_click"])
        rows = [[_dim_value(r), _count(r)] for r in rows_raw if isinstance(r, dict)]
        rows = [r for r in rows if r[0] is not None and r[1] > 0]
        rows.sort(key=lambda r: r[1], reverse=True)
        rows = rows[:limit]
        return "\n".join([
            f"=== Clarity Dead Clicks (last {days}d, top {limit}) ===",
            "",
            _format_table(["URL", "Dead Clicks"], rows),
            _footer(hit),
        ])

    @mcp.tool()
    async def clarity_rage_clicks(
        days: int = 1,
        limit: int = 20,
    ) -> str:
        """Top URLs with rage clicks (fast repeated clicks — user frustration)."""
        try:
            payload, hit = await client.fetch_insights(days, "URL")
        except client.ClarityError as e:
            return _err(e)

        rows_raw = _metric_rows(payload, METRIC["rage_click"])
        rows = [[_dim_value(r), _count(r)] for r in rows_raw if isinstance(r, dict)]
        rows = [r for r in rows if r[0] is not None and r[1] > 0]
        rows.sort(key=lambda r: r[1], reverse=True)
        rows = rows[:limit]
        return "\n".join([
            f"=== Clarity Rage Clicks (last {days}d, top {limit}) ===",
            "",
            _format_table(["URL", "Rage Clicks"], rows),
            _footer(hit),
        ])

    @mcp.tool()
    async def clarity_excessive_scroll(
        days: int = 1,
        limit: int = 20,
    ) -> str:
        """Top URLs with excessive scrolling (users hunting for info they can't easily find)."""
        try:
            payload, hit = await client.fetch_insights(days, "URL")
        except client.ClarityError as e:
            return _err(e)

        rows_raw = _metric_rows(payload, METRIC["excessive_scroll"])
        rows = [[_dim_value(r), _count(r)] for r in rows_raw if isinstance(r, dict)]
        rows = [r for r in rows if r[0] is not None and r[1] > 0]
        rows.sort(key=lambda r: r[1], reverse=True)
        rows = rows[:limit]
        return "\n".join([
            f"=== Clarity Excessive Scroll (last {days}d, top {limit}) ===",
            "",
            _format_table(["URL", "Excessive Scroll"], rows),
            _footer(hit),
        ])

    @mcp.tool()
    async def clarity_quickback_clicks(
        days: int = 1,
        limit: int = 20,
    ) -> str:
        """Top URLs with quickback clicks (user goes back immediately — page not relevant)."""
        try:
            payload, hit = await client.fetch_insights(days, "URL")
        except client.ClarityError as e:
            return _err(e)

        rows_raw = _metric_rows(payload, METRIC["quickback_click"])
        rows = [[_dim_value(r), _count(r)] for r in rows_raw if isinstance(r, dict)]
        rows = [r for r in rows if r[0] is not None and r[1] > 0]
        rows.sort(key=lambda r: r[1], reverse=True)
        rows = rows[:limit]
        return "\n".join([
            f"=== Clarity Quickback Clicks (last {days}d, top {limit}) ===",
            "",
            _format_table(["URL", "Quickback"], rows),
            _footer(hit),
        ])

    @mcp.tool()
    async def clarity_script_errors(
        days: int = 1,
        limit: int = 20,
    ) -> str:
        """Top URLs with JS errors + error clicks (technical problems on the page)."""
        try:
            payload, hit = await client.fetch_insights(days, "URL")
        except client.ClarityError as e:
            return _err(e)

        script_err = {_dim_value(r): r for r in _metric_rows(payload, METRIC["script_error"]) if isinstance(r, dict)}
        err_click = {_dim_value(r): r for r in _metric_rows(payload, METRIC["error_click"]) if isinstance(r, dict)}
        urls = list({*script_err.keys(), *err_click.keys()})
        rows = []
        for u in urls:
            if u is None:
                continue
            se = _count(script_err.get(u, {}))
            ec = _count(err_click.get(u, {}))
            if se + ec == 0:
                continue
            rows.append([u, se, ec])
        rows.sort(key=lambda r: r[1] + r[2], reverse=True)
        rows = rows[:limit]
        return "\n".join([
            f"=== Clarity Script/Error Clicks (last {days}d, top {limit}) ===",
            "",
            _format_table(["URL", "JS Errors", "Error Clicks"], rows),
            _footer(hit),
        ])

    @mcp.tool()
    async def clarity_breakdown(
        dimension1: str,
        days: int = 1,
        dimension2: Optional[str] = None,
        dimension3: Optional[str] = None,
    ) -> str:
        """Free-form raw breakdown (1-3 dimensions). Power-user — costs 1 quota unit if not already cached.

        dimension1/2/3 in {Browser, Device, Country/Region, OS, Source, Medium, Campaign, Channel, URL}.
        days in {1,2,3}. Output: all metrics grouped as returned by the API.
        """
        try:
            payload, hit = await client.fetch_insights(days, dimension1, dimension2, dimension3)
        except client.ClarityError as e:
            return _err(e)

        out = [
            f"=== Clarity Breakdown ({days}d, dims: "
            f"{dimension1}{', '+dimension2 if dimension2 else ''}{', '+dimension3 if dimension3 else ''}) ===",
            "",
        ]
        if not isinstance(payload, list):
            out.append("(unexpected payload)")
            out.append(_footer(hit))
            return "\n".join(out)
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            name = entry.get("metricName", "?")
            info = entry.get("information", [])
            out.append(f"--- {name} ({len(info)} rows) ---")
            for row in info[:5]:
                out.append(f"  {row}")
            if len(info) > 5:
                out.append(f"  ... (+{len(info)-5} rows truncated)")
        out.append(_footer(hit))
        return "\n".join(out)

    @mcp.tool()
    async def clarity_quota_status() -> str:
        """Daily quota status (local counter, does not call the API).

        Resets automatically at midnight UTC. The local limit (`CLARITY_DAILY_LIMIT`,
        default 9) stops one call short of the API's 10/day to avoid 429s.
        """
        s = quota.status()
        cache_stats = cache.stats()
        out = [
            f"=== Clarity Quota Status — {s['date_utc']} (UTC) ===",
            f"Local daily limit: {s['daily_limit']} (warning >= {s['warning_threshold']})",
            f"Cache: {cache_stats['valid']} valid / {cache_stats['total']} total entries",
            "",
        ]
        if not s["projects"]:
            out.append("No project has consumed quota today.")
            return "\n".join(out)
        rows = []
        for project, info in s["projects"].items():
            flag = "BLOCKED" if info["blocked"] else ("WARNING" if info["warning"] else "ok")
            rows.append([project, info["used"], info["remaining"], flag])
        rows.sort(key=lambda r: r[1], reverse=True)
        out.append(_format_table(["Project", "Used", "Remaining", "Status"], rows))
        return "\n".join(out)
