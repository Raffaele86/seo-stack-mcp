"""Google Search Console MCP tools.

Registers every GSC tool on a FastMCP instance via ``register(mcp)``.
All tools accept ``site_url`` explicitly; when omitted, the ``GSC_SITE_URL``
environment variable is used as fallback.
"""

import asyncio

from .client import (
    get_gsc_service,
    get_indexing_service,
    resolve_site_url,
    query_gsc,
    date_ago,
    fresh_authorized_http,
)


async def _run_batch(items: list, worker, concurrency: int) -> list:
    """Run ``worker(item, http)`` concurrently in threads with a concurrency cap.

    Each task gets its own AuthorizedHttp (httplib2 is not thread-safe).
    Results come back in input order.
    """
    sem = asyncio.Semaphore(concurrency)

    async def one(item):
        async with sem:
            return await asyncio.to_thread(worker, item, fresh_authorized_http())

    return list(await asyncio.gather(*(one(i) for i in items)))


def register(mcp) -> None:
    """Register all GSC tools on the given FastMCP instance."""

    # =====================================================================
    # CORE TOOLS
    # =====================================================================

    @mcp.tool()
    async def gsc_list_sites() -> list:
        """List all Google Search Console properties available to the configured credentials."""
        service = get_gsc_service()
        result = service.sites().list().execute()
        return result.get("siteEntry", [])

    @mcp.tool()
    async def gsc_search_analytics(
        start_date: str,
        end_date: str,
        site_url: str = "",
        dimensions: list[str] = ["query"],
        row_limit: int = 10,
    ) -> dict:
        """Query Search Analytics: clicks, impressions, CTR and position for the requested dimensions.
        Available dimensions: query, page, country, device, searchAppearance, date."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": dimensions,
            "rowLimit": row_limit,
        }
        return service.searchanalytics().query(siteUrl=site_url, body=body).execute()

    @mcp.tool()
    async def gsc_inspect_url(inspection_url: str, site_url: str = "") -> dict:
        """Inspect a URL via the Google Search Console URL Inspection API."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        body = {"inspectionUrl": inspection_url, "siteUrl": site_url}
        return service.urlInspection().index().inspect(body=body).execute()

    @mcp.tool()
    async def gsc_list_sitemaps(site_url: str = "") -> list:
        """List all sitemaps of a site in Google Search Console."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        result = service.sitemaps().list(siteUrl=site_url).execute()
        return result.get("sitemap", [])

    @mcp.tool()
    async def gsc_submit_sitemap(sitemap_url: str, site_url: str = "") -> dict:
        """Submit a sitemap to Google Search Console. Requires write scope on the credentials."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        service.sitemaps().submit(siteUrl=site_url, feedpath=sitemap_url).execute()
        return {"status": "submitted", "sitemap_url": sitemap_url}

    @mcp.tool()
    async def gsc_request_indexing(url: str) -> dict:
        """Request indexing of a URL via the Google Indexing API.
        Requires the indexing scope on the credentials."""
        service = get_indexing_service()
        body = {"url": url, "type": "URL_UPDATED"}
        return service.urlNotifications().publish(body=body).execute()

    # =====================================================================
    # PERFORMANCE ANALYSIS
    # =====================================================================

    @mcp.tool()
    async def gsc_top_queries(
        site_url: str = "", start_date: str = "", end_date: str = "",
        row_limit: int = 25, order_by: str = "clicks"
    ) -> dict:
        """Top queries by clicks or impressions. order_by: clicks, impressions, ctr, position. Default: last 28 days."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        if not start_date:
            start_date = date_ago(28)
        if not end_date:
            end_date = date_ago(1)
        rows = query_gsc(service, site_url, start_date, end_date, ["query"], row_limit=25000)
        sort_key = {"clicks": "clicks", "impressions": "impressions", "ctr": "ctr", "position": "position"}.get(order_by, "clicks")
        reverse = sort_key != "position"
        rows.sort(key=lambda r: r.get(sort_key, 0), reverse=reverse)
        result = []
        for r in rows[:row_limit]:
            result.append({
                "query": r["keys"][0],
                "clicks": r["clicks"], "impressions": r["impressions"],
                "ctr": round(r["ctr"] * 100, 2), "position": round(r["position"], 1),
            })
        return {"period": f"{start_date} → {end_date}", "order_by": order_by, "rows": result}

    @mcp.tool()
    async def gsc_top_pages(
        site_url: str = "", start_date: str = "", end_date: str = "",
        row_limit: int = 25, order_by: str = "clicks"
    ) -> dict:
        """Top pages by clicks or impressions. order_by: clicks, impressions, ctr, position. Default: last 28 days."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        if not start_date:
            start_date = date_ago(28)
        if not end_date:
            end_date = date_ago(1)
        rows = query_gsc(service, site_url, start_date, end_date, ["page"], row_limit=25000)
        sort_key = {"clicks": "clicks", "impressions": "impressions", "ctr": "ctr", "position": "position"}.get(order_by, "clicks")
        reverse = sort_key != "position"
        rows.sort(key=lambda r: r.get(sort_key, 0), reverse=reverse)
        result = []
        for r in rows[:row_limit]:
            result.append({
                "page": r["keys"][0],
                "clicks": r["clicks"], "impressions": r["impressions"],
                "ctr": round(r["ctr"] * 100, 2), "position": round(r["position"], 1),
            })
        return {"period": f"{start_date} → {end_date}", "order_by": order_by, "rows": result}

    @mcp.tool()
    async def gsc_query_trend(
        query: str, site_url: str = "", days: int = 90
    ) -> dict:
        """Daily trend for a specific query over the last N days (default 90)."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        start_date = date_ago(days)
        end_date = date_ago(1)
        rows = query_gsc(service, site_url, start_date, end_date, ["date"], row_limit=25000,
                         dimension_filters=[{"dimension": "query", "expression": query, "operator": "equals"}])
        result = []
        for r in rows:
            result.append({
                "date": r["keys"][0],
                "clicks": r["clicks"], "impressions": r["impressions"],
                "ctr": round(r["ctr"] * 100, 2), "position": round(r["position"], 1),
            })
        result.sort(key=lambda x: x["date"])
        return {"query": query, "days": days, "data": result}

    @mcp.tool()
    async def gsc_page_trend(
        page_url: str, site_url: str = "", days: int = 90
    ) -> dict:
        """Daily trend for a specific page over the last N days (default 90)."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        start_date = date_ago(days)
        end_date = date_ago(1)
        rows = query_gsc(service, site_url, start_date, end_date, ["date"], row_limit=25000,
                         dimension_filters=[{"dimension": "page", "expression": page_url, "operator": "equals"}])
        result = []
        for r in rows:
            result.append({
                "date": r["keys"][0],
                "clicks": r["clicks"], "impressions": r["impressions"],
                "ctr": round(r["ctr"] * 100, 2), "position": round(r["position"], 1),
            })
        result.sort(key=lambda x: x["date"])
        return {"page": page_url, "days": days, "data": result}

    @mcp.tool()
    async def gsc_compare_periods(
        period1_start: str, period1_end: str,
        period2_start: str, period2_end: str,
        site_url: str = "", dimension: str = "query",
        row_limit: int = 50
    ) -> dict:
        """Compare two periods: shows deltas of clicks, impressions, CTR and position per item.
        Useful for month-over-month or week-over-week comparisons."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        rows1 = query_gsc(service, site_url, period1_start, period1_end, [dimension], row_limit=25000)
        rows2 = query_gsc(service, site_url, period2_start, period2_end, [dimension], row_limit=25000)
        data1 = {r["keys"][0]: r for r in rows1}
        data2 = {r["keys"][0]: r for r in rows2}
        all_keys = set(data1.keys()) | set(data2.keys())
        comparisons = []
        for key in all_keys:
            r1 = data1.get(key, {"clicks": 0, "impressions": 0, "ctr": 0, "position": 0})
            r2 = data2.get(key, {"clicks": 0, "impressions": 0, "ctr": 0, "position": 0})
            comparisons.append({
                dimension: key,
                "period1_clicks": r1["clicks"], "period2_clicks": r2["clicks"],
                "delta_clicks": r2["clicks"] - r1["clicks"],
                "period1_impressions": r1["impressions"], "period2_impressions": r2["impressions"],
                "delta_impressions": r2["impressions"] - r1["impressions"],
                "period1_position": round(r1["position"], 1) if r1["position"] else None,
                "period2_position": round(r2["position"], 1) if r2["position"] else None,
                "delta_position": round(r1["position"] - r2["position"], 1) if r1["position"] and r2["position"] else None,
            })
        comparisons.sort(key=lambda x: abs(x["delta_clicks"]), reverse=True)
        return {
            "period1": f"{period1_start} → {period1_end}",
            "period2": f"{period2_start} → {period2_end}",
            "dimension": dimension,
            "rows": comparisons[:row_limit],
        }

    @mcp.tool()
    async def gsc_country_performance(
        site_url: str = "", start_date: str = "", end_date: str = "", row_limit: int = 30
    ) -> dict:
        """Performance by country: clicks, impressions, CTR and average position. Default: last 28 days."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        if not start_date:
            start_date = date_ago(28)
        if not end_date:
            end_date = date_ago(1)
        rows = query_gsc(service, site_url, start_date, end_date, ["country"], row_limit=25000)
        rows.sort(key=lambda r: r["clicks"], reverse=True)
        result = []
        for r in rows[:row_limit]:
            result.append({
                "country": r["keys"][0],
                "clicks": r["clicks"], "impressions": r["impressions"],
                "ctr": round(r["ctr"] * 100, 2), "position": round(r["position"], 1),
            })
        return {"period": f"{start_date} → {end_date}", "rows": result}

    @mcp.tool()
    async def gsc_device_performance(
        site_url: str = "", start_date: str = "", end_date: str = ""
    ) -> dict:
        """Compare performance across MOBILE vs DESKTOP vs TABLET. Default: last 28 days."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        if not start_date:
            start_date = date_ago(28)
        if not end_date:
            end_date = date_ago(1)
        rows = query_gsc(service, site_url, start_date, end_date, ["device"])
        result = []
        for r in rows:
            result.append({
                "device": r["keys"][0],
                "clicks": r["clicks"], "impressions": r["impressions"],
                "ctr": round(r["ctr"] * 100, 2), "position": round(r["position"], 1),
            })
        return {"period": f"{start_date} → {end_date}", "devices": result}

    @mcp.tool()
    async def gsc_search_appearance(
        site_url: str = "", start_date: str = "", end_date: str = ""
    ) -> dict:
        """Performance by SERP result type (rich snippet, video, FAQ, etc.). Default: last 28 days."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        if not start_date:
            start_date = date_ago(28)
        if not end_date:
            end_date = date_ago(1)
        rows = query_gsc(service, site_url, start_date, end_date, ["searchAppearance"])
        result = []
        for r in rows:
            result.append({
                "type": r["keys"][0],
                "clicks": r["clicks"], "impressions": r["impressions"],
                "ctr": round(r["ctr"] * 100, 2), "position": round(r["position"], 1),
            })
        result.sort(key=lambda x: x["clicks"], reverse=True)
        return {"period": f"{start_date} → {end_date}", "appearances": result}

    # =====================================================================
    # SEO OPPORTUNITIES
    # =====================================================================

    @mcp.tool()
    async def gsc_keyword_opportunities(
        site_url: str = "", start_date: str = "", end_date: str = "",
        min_impressions: int = 50, max_position: float = 20, min_position: float = 5,
        row_limit: int = 50
    ) -> dict:
        """Queries with high impressions but low CTR in position 5-20: optimization opportunities.
        These keywords have visibility but don't get clicked — improve title/meta description."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        if not start_date:
            start_date = date_ago(28)
        if not end_date:
            end_date = date_ago(1)
        rows = query_gsc(service, site_url, start_date, end_date, ["query"], row_limit=25000)
        opportunities = []
        for r in rows:
            pos = r["position"]
            if min_position <= pos <= max_position and r["impressions"] >= min_impressions:
                opportunities.append({
                    "query": r["keys"][0],
                    "clicks": r["clicks"], "impressions": r["impressions"],
                    "ctr": round(r["ctr"] * 100, 2), "position": round(pos, 1),
                    "potential_clicks": round(r["impressions"] * 0.10 - r["clicks"]),
                })
        opportunities.sort(key=lambda x: x["potential_clicks"], reverse=True)
        return {
            "period": f"{start_date} → {end_date}",
            "criteria": f"position {min_position}-{max_position}, min {min_impressions} impressions",
            "rows": opportunities[:row_limit],
        }

    @mcp.tool()
    async def gsc_declining_queries(
        site_url: str = "", days: int = 28, row_limit: int = 30
    ) -> dict:
        """Queries losing clicks/positions: compares last N days vs the equivalent previous period."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        p2_end = date_ago(1)
        p2_start = date_ago(days)
        p1_end = date_ago(days + 1)
        p1_start = date_ago(days * 2)
        rows_before = query_gsc(service, site_url, p1_start, p1_end, ["query"], row_limit=25000)
        rows_after = query_gsc(service, site_url, p2_start, p2_end, ["query"], row_limit=25000)
        before = {r["keys"][0]: r for r in rows_before}
        after = {r["keys"][0]: r for r in rows_after}
        declining = []
        for query, r1 in before.items():
            r2 = after.get(query)
            if not r2:
                if r1["clicks"] >= 3:
                    declining.append({
                        "query": query, "before_clicks": r1["clicks"], "after_clicks": 0,
                        "delta_clicks": -r1["clicks"],
                        "before_position": round(r1["position"], 1), "after_position": None,
                        "status": "disappeared",
                    })
                continue
            delta_clicks = r2["clicks"] - r1["clicks"]
            delta_pos = r1["position"] - r2["position"]
            if delta_clicks < -2 or delta_pos < -2:
                declining.append({
                    "query": query,
                    "before_clicks": r1["clicks"], "after_clicks": r2["clicks"],
                    "delta_clicks": delta_clicks,
                    "before_position": round(r1["position"], 1),
                    "after_position": round(r2["position"], 1),
                    "delta_position": round(delta_pos, 1),
                    "status": "declining",
                })
        declining.sort(key=lambda x: x["delta_clicks"])
        return {
            "period_before": f"{p1_start} → {p1_end}",
            "period_after": f"{p2_start} → {p2_end}",
            "rows": declining[:row_limit],
        }

    @mcp.tool()
    async def gsc_rising_queries(
        site_url: str = "", days: int = 28, row_limit: int = 30
    ) -> dict:
        """Rising queries: compares last N days vs the equivalent previous period."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        p2_end = date_ago(1)
        p2_start = date_ago(days)
        p1_end = date_ago(days + 1)
        p1_start = date_ago(days * 2)
        rows_before = query_gsc(service, site_url, p1_start, p1_end, ["query"], row_limit=25000)
        rows_after = query_gsc(service, site_url, p2_start, p2_end, ["query"], row_limit=25000)
        before = {r["keys"][0]: r for r in rows_before}
        after = {r["keys"][0]: r for r in rows_after}
        rising = []
        for query, r2 in after.items():
            r1 = before.get(query)
            if not r1:
                if r2["clicks"] >= 3:
                    rising.append({
                        "query": query, "before_clicks": 0, "after_clicks": r2["clicks"],
                        "delta_clicks": r2["clicks"],
                        "before_position": None, "after_position": round(r2["position"], 1),
                        "status": "new",
                    })
                continue
            delta_clicks = r2["clicks"] - r1["clicks"]
            delta_pos = r1["position"] - r2["position"]
            if delta_clicks > 2 or delta_pos > 2:
                rising.append({
                    "query": query,
                    "before_clicks": r1["clicks"], "after_clicks": r2["clicks"],
                    "delta_clicks": delta_clicks,
                    "before_position": round(r1["position"], 1),
                    "after_position": round(r2["position"], 1),
                    "delta_position": round(delta_pos, 1),
                    "status": "rising",
                })
        rising.sort(key=lambda x: x["delta_clicks"], reverse=True)
        return {
            "period_before": f"{p1_start} → {p1_end}",
            "period_after": f"{p2_start} → {p2_end}",
            "rows": rising[:row_limit],
        }

    @mcp.tool()
    async def gsc_cannibalization_check(
        site_url: str = "", start_date: str = "", end_date: str = "",
        min_impressions: int = 20, row_limit: int = 30
    ) -> dict:
        """Find queries where multiple pages compete (keyword cannibalization). Shows queries with 2+ ranking pages."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        if not start_date:
            start_date = date_ago(28)
        if not end_date:
            end_date = date_ago(1)
        rows = query_gsc(service, site_url, start_date, end_date, ["query", "page"], row_limit=25000)
        query_pages: dict[str, list] = {}
        for r in rows:
            query = r["keys"][0]
            page = r["keys"][1]
            if r["impressions"] >= min_impressions:
                query_pages.setdefault(query, []).append({
                    "page": page,
                    "clicks": r["clicks"], "impressions": r["impressions"],
                    "ctr": round(r["ctr"] * 100, 2), "position": round(r["position"], 1),
                })
        cannibalized = []
        for query, pages in query_pages.items():
            if len(pages) >= 2:
                pages.sort(key=lambda x: x["clicks"], reverse=True)
                total_clicks = sum(p["clicks"] for p in pages)
                cannibalized.append({
                    "query": query,
                    "num_pages": len(pages),
                    "total_clicks": total_clicks,
                    "pages": pages,
                })
        cannibalized.sort(key=lambda x: x["total_clicks"], reverse=True)
        return {
            "period": f"{start_date} → {end_date}",
            "cannibalized_queries": cannibalized[:row_limit],
        }

    @mcp.tool()
    async def gsc_low_hanging_fruit(
        site_url: str = "", start_date: str = "", end_date: str = "",
        min_impressions: int = 30, row_limit: int = 50
    ) -> dict:
        """Queries in position 3-10 with high impression volume: small optimizations can push them into the top 3.
        Sorted by potential extra clicks."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        if not start_date:
            start_date = date_ago(28)
        if not end_date:
            end_date = date_ago(1)
        rows = query_gsc(service, site_url, start_date, end_date, ["query"], row_limit=25000)
        fruits = []
        for r in rows:
            pos = r["position"]
            if 3 <= pos <= 10 and r["impressions"] >= min_impressions:
                estimated_top3_ctr = 0.15
                potential = round(r["impressions"] * estimated_top3_ctr - r["clicks"])
                fruits.append({
                    "query": r["keys"][0],
                    "clicks": r["clicks"], "impressions": r["impressions"],
                    "ctr": round(r["ctr"] * 100, 2), "position": round(pos, 1),
                    "potential_extra_clicks": max(0, potential),
                })
        fruits.sort(key=lambda x: x["potential_extra_clicks"], reverse=True)
        return {
            "period": f"{start_date} → {end_date}",
            "criteria": "position 3-10, easy wins",
            "rows": fruits[:row_limit],
        }

    # =====================================================================
    # ADVANCED FILTERS
    # =====================================================================

    @mcp.tool()
    async def gsc_search_analytics_filtered(
        start_date: str, end_date: str,
        site_url: str = "",
        dimensions: list[str] = ["query"],
        query_contains: str = "", query_regex: str = "",
        page_contains: str = "", page_regex: str = "",
        country: str = "", device: str = "",
        row_limit: int = 100
    ) -> dict:
        """Search Analytics with advanced filters. Filters: query_contains, query_regex, page_contains, page_regex, country (e.g. 'ita'), device (MOBILE/DESKTOP/TABLET)."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        filters = []
        if query_contains:
            filters.append({"dimension": "query", "operator": "contains", "expression": query_contains})
        if query_regex:
            filters.append({"dimension": "query", "operator": "includingRegex", "expression": query_regex})
        if page_contains:
            filters.append({"dimension": "page", "operator": "contains", "expression": page_contains})
        if page_regex:
            filters.append({"dimension": "page", "operator": "includingRegex", "expression": page_regex})
        if country:
            filters.append({"dimension": "country", "operator": "equals", "expression": country})
        if device:
            filters.append({"dimension": "device", "operator": "equals", "expression": device})
        rows = query_gsc(service, site_url, start_date, end_date, dimensions, row_limit=row_limit,
                         dimension_filters=filters if filters else None)
        result = []
        for r in rows:
            entry = {"clicks": r["clicks"], "impressions": r["impressions"],
                     "ctr": round(r["ctr"] * 100, 2), "position": round(r["position"], 1)}
            for i, dim in enumerate(dimensions):
                entry[dim] = r["keys"][i]
            result.append(entry)
        return {"period": f"{start_date} → {end_date}", "filters_applied": len(filters), "rows": result}

    @mcp.tool()
    async def gsc_pages_for_query(
        query: str, site_url: str = "", start_date: str = "", end_date: str = ""
    ) -> dict:
        """Which pages rank for a specific query? Shows all pages with performance data."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        if not start_date:
            start_date = date_ago(28)
        if not end_date:
            end_date = date_ago(1)
        rows = query_gsc(service, site_url, start_date, end_date, ["page"], row_limit=25000,
                         dimension_filters=[{"dimension": "query", "expression": query, "operator": "equals"}])
        result = []
        for r in rows:
            result.append({
                "page": r["keys"][0],
                "clicks": r["clicks"], "impressions": r["impressions"],
                "ctr": round(r["ctr"] * 100, 2), "position": round(r["position"], 1),
            })
        result.sort(key=lambda x: x["clicks"], reverse=True)
        return {"query": query, "period": f"{start_date} → {end_date}", "pages": result}

    @mcp.tool()
    async def gsc_queries_for_page(
        page_url: str, site_url: str = "", start_date: str = "", end_date: str = "",
        row_limit: int = 50
    ) -> dict:
        """Which queries drive traffic to a specific page? Shows all keywords with performance data."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        if not start_date:
            start_date = date_ago(28)
        if not end_date:
            end_date = date_ago(1)
        rows = query_gsc(service, site_url, start_date, end_date, ["query"], row_limit=25000,
                         dimension_filters=[{"dimension": "page", "expression": page_url, "operator": "equals"}])
        result = []
        for r in rows:
            result.append({
                "query": r["keys"][0],
                "clicks": r["clicks"], "impressions": r["impressions"],
                "ctr": round(r["ctr"] * 100, 2), "position": round(r["position"], 1),
            })
        result.sort(key=lambda x: x["clicks"], reverse=True)
        return {"page": page_url, "period": f"{start_date} → {end_date}", "queries": result[:row_limit]}

    # =====================================================================
    # ADVANCED INDEXING
    # =====================================================================

    @mcp.tool()
    async def gsc_bulk_inspect_urls(urls: list[str], site_url: str = "") -> dict:
        """Inspect multiple URLs in batch via the URL Inspection API. Max 50 URLs per call."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()

        def inspect(url, http):
            try:
                body = {"inspectionUrl": url, "siteUrl": site_url}
                result = service.urlInspection().index().inspect(body=body).execute(http=http)
                inspection = result.get("inspectionResult", {})
                index_status = inspection.get("indexStatusResult", {})
                return {
                    "url": url,
                    "verdict": index_status.get("verdict", "UNKNOWN"),
                    "coverageState": index_status.get("coverageState", ""),
                    "robotsTxtState": index_status.get("robotsTxtState", ""),
                    "indexingState": index_status.get("indexingState", ""),
                    "lastCrawlTime": index_status.get("lastCrawlTime", ""),
                    "pageFetchState": index_status.get("pageFetchState", ""),
                    "crawledAs": index_status.get("crawledAs", ""),
                }
            except Exception as e:
                return {"url": url, "error": str(e)}

        results = await _run_batch(urls[:50], inspect, concurrency=4)
        return {"inspected": len(results), "results": results}

    @mcp.tool()
    async def gsc_bulk_request_indexing(urls: list[str]) -> dict:
        """Request indexing for multiple URLs via the Google Indexing API. Max 50 URLs.
        WARNING: Google enforces a daily limit of ~200 requests. Requires the indexing scope."""
        service = get_indexing_service()

        def publish(url, http):
            try:
                body = {"url": url, "type": "URL_UPDATED"}
                result = service.urlNotifications().publish(body=body).execute(http=http)
                return {"url": url, "status": "submitted", "response": result}
            except Exception as e:
                return {"url": url, "status": "error", "error": str(e)}

        # concorrenza bassa: il vincolo vero è la quota giornaliera (~200/die)
        results = await _run_batch(urls[:50], publish, concurrency=3)
        return {"submitted": len([r for r in results if r["status"] == "submitted"]),
                "errors": len([r for r in results if r["status"] == "error"]),
                "results": results}

    @mcp.tool()
    async def gsc_delete_sitemap(sitemap_url: str, site_url: str = "") -> dict:
        """Remove a sitemap from Google Search Console. Requires write scope on the credentials."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        service.sitemaps().delete(siteUrl=site_url, feedpath=sitemap_url).execute()
        return {"status": "deleted", "sitemap_url": sitemap_url}

    @mcp.tool()
    async def gsc_indexing_status_summary(urls: list[str], site_url: str = "") -> dict:
        """Indexing status summary for multiple URLs: how many indexed, not indexed, and errored."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()

        def inspect(url, http):
            try:
                body = {"inspectionUrl": url, "siteUrl": site_url}
                result = service.urlInspection().index().inspect(body=body).execute(http=http)
                verdict = result.get("inspectionResult", {}).get("indexStatusResult", {}).get("verdict", "UNKNOWN")
                return {"url": url, "verdict": verdict}
            except Exception as e:
                return {"url": url, "verdict": "ERROR", "error": str(e)}

        details = await _run_batch(urls[:50], inspect, concurrency=4)
        indexed = sum(1 for d in details if d["verdict"] == "PASS")
        errors = sum(1 for d in details if d["verdict"] == "ERROR")
        not_indexed = len(details) - indexed - errors
        return {
            "total": len(urls[:50]), "indexed": indexed,
            "not_indexed": not_indexed, "errors": errors,
            "details": details,
        }

    # =====================================================================
    # DASHBOARD / REPORTING
    # =====================================================================

    @mcp.tool()
    async def gsc_daily_stats(
        site_url: str = "", days: int = 30
    ) -> dict:
        """Aggregated daily site statistics: clicks, impressions, CTR and average position per day."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        start_date = date_ago(days)
        end_date = date_ago(1)
        rows = query_gsc(service, site_url, start_date, end_date, ["date"], row_limit=25000)
        result = []
        for r in rows:
            result.append({
                "date": r["keys"][0],
                "clicks": r["clicks"], "impressions": r["impressions"],
                "ctr": round(r["ctr"] * 100, 2), "position": round(r["position"], 1),
            })
        result.sort(key=lambda x: x["date"])
        total_clicks = sum(r["clicks"] for r in result)
        total_impressions = sum(r["impressions"] for r in result)
        avg_position = round(sum(r["position"] for r in result) / len(result), 1) if result else 0
        return {
            "site": site_url, "days": days,
            "totals": {"clicks": total_clicks, "impressions": total_impressions, "avg_position": avg_position},
            "daily": result,
        }

    @mcp.tool()
    async def gsc_weekly_report(
        site_url: str = ""
    ) -> dict:
        """Automatic weekly report: last 7 days vs previous 7 days metrics with deltas and top queries/pages."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        this_week_start = date_ago(7)
        this_week_end = date_ago(1)
        last_week_start = date_ago(14)
        last_week_end = date_ago(8)

        # Totals this week
        tw_rows = query_gsc(service, site_url, this_week_start, this_week_end, ["date"], row_limit=7)
        tw_clicks = sum(r["clicks"] for r in tw_rows)
        tw_impressions = sum(r["impressions"] for r in tw_rows)
        tw_avg_pos = round(sum(r["position"] for r in tw_rows) / len(tw_rows), 1) if tw_rows else 0

        # Totals last week
        lw_rows = query_gsc(service, site_url, last_week_start, last_week_end, ["date"], row_limit=7)
        lw_clicks = sum(r["clicks"] for r in lw_rows)
        lw_impressions = sum(r["impressions"] for r in lw_rows)
        lw_avg_pos = round(sum(r["position"] for r in lw_rows) / len(lw_rows), 1) if lw_rows else 0

        # Top 10 queries this week
        tw_queries = query_gsc(service, site_url, this_week_start, this_week_end, ["query"], row_limit=25000)
        tw_queries.sort(key=lambda r: r["clicks"], reverse=True)
        top_queries_list = [{"query": r["keys"][0], "clicks": r["clicks"], "position": round(r["position"], 1)} for r in tw_queries[:10]]

        # Top 10 pages this week
        tw_pages = query_gsc(service, site_url, this_week_start, this_week_end, ["page"], row_limit=25000)
        tw_pages.sort(key=lambda r: r["clicks"], reverse=True)
        top_pages_list = [{"page": r["keys"][0], "clicks": r["clicks"], "position": round(r["position"], 1)} for r in tw_pages[:10]]

        return {
            "this_week": {"period": f"{this_week_start} → {this_week_end}", "clicks": tw_clicks, "impressions": tw_impressions, "avg_position": tw_avg_pos},
            "last_week": {"period": f"{last_week_start} → {last_week_end}", "clicks": lw_clicks, "impressions": lw_impressions, "avg_position": lw_avg_pos},
            "delta": {
                "clicks": tw_clicks - lw_clicks,
                "clicks_pct": round((tw_clicks - lw_clicks) / lw_clicks * 100, 1) if lw_clicks else 0,
                "impressions": tw_impressions - lw_impressions,
                "impressions_pct": round((tw_impressions - lw_impressions) / lw_impressions * 100, 1) if lw_impressions else 0,
                "position": round(lw_avg_pos - tw_avg_pos, 1),
            },
            "top_queries": top_queries_list,
            "top_pages": top_pages_list,
        }

    @mcp.tool()
    async def gsc_content_gap_analysis(
        competitor_url: str, site_url: str = "", start_date: str = "", end_date: str = "",
        row_limit: int = 50
    ) -> dict:
        """Content gap analysis: queries where the competitor ranks but you don't (or you are far behind).
        Requires the competitor property to be verified in your GSC account (e.g. another of your properties)."""
        site_url = resolve_site_url(site_url)
        service = get_gsc_service()
        if not start_date:
            start_date = date_ago(28)
        if not end_date:
            end_date = date_ago(1)

        my_rows = query_gsc(service, site_url, start_date, end_date, ["query"], row_limit=25000)
        my_queries = {r["keys"][0]: r for r in my_rows}

        try:
            comp_rows = query_gsc(service, competitor_url, start_date, end_date, ["query"], row_limit=25000)
        except Exception as e:
            return {"error": f"Cannot access competitor data: {e}. Make sure the property is verified in your GSC account."}

        gaps = []
        for r in comp_rows:
            query = r["keys"][0]
            my_data = my_queries.get(query)
            if not my_data:
                gaps.append({
                    "query": query, "competitor_clicks": r["clicks"],
                    "competitor_position": round(r["position"], 1),
                    "your_clicks": 0, "your_position": None,
                    "gap_type": "missing",
                })
            elif my_data["position"] > r["position"] + 5:
                gaps.append({
                    "query": query, "competitor_clicks": r["clicks"],
                    "competitor_position": round(r["position"], 1),
                    "your_clicks": my_data["clicks"],
                    "your_position": round(my_data["position"], 1),
                    "gap_type": "behind",
                })
        gaps.sort(key=lambda x: x["competitor_clicks"], reverse=True)
        return {
            "site": site_url, "competitor": competitor_url,
            "period": f"{start_date} → {end_date}",
            "gaps": gaps[:row_limit],
        }
