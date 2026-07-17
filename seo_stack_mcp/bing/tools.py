"""Bing Webmaster Tools — 22 MCP tools.

Each tool returns a formatted text table (a plain string), not raw JSON.
"""

import logging
from datetime import datetime, timedelta

from .client import BingWebmasterError, format_date, get_client, get_site_url

log = logging.getLogger("seo-stack-mcp.bing")


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_number(val) -> str:
    """Format a number with thousands separator."""
    try:
        n = float(val)
        if n == int(n):
            return f"{int(n):,}"
        return f"{n:,.2f}"
    except (ValueError, TypeError):
        return str(val)


def _fmt_table(headers: list[str], rows: list[list[str]], title: str = "") -> str:
    """Build a formatted text table with aligned columns."""
    if not rows:
        return f"{title}\n(no data)" if title else "(no data)"

    all_rows = [headers] + rows
    widths = [max(len(str(r[i])) for r in all_rows) for i in range(len(headers))]

    lines = []
    if title:
        lines.append(f"=== {title} ===")
        lines.append("")

    header_line = " | ".join(str(h).ljust(w) for h, w in zip(headers, widths))
    lines.append(header_line)
    lines.append("-+-".join("-" * w for w in widths))

    for row in rows:
        line = " | ".join(str(v).ljust(w) for v, w in zip(row, widths))
        lines.append(line)

    return "\n".join(lines)


def _safe_attr(obj, attr, default="N/A") -> str:
    """Safely get an attribute from an object."""
    val = getattr(obj, attr, None)
    if val is None:
        return default
    return str(val)


def _sort_date(obj) -> datetime:
    """Sort key: the item's date, falling back to datetime.min."""
    return getattr(obj, "date", None) or datetime.min


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register(mcp):
    """Register all Bing Webmaster tools on the given FastMCP server."""

    # ── 1. Site management ──────────────────────────────────────────────

    @mcp.tool()
    async def bing_sites() -> str:
        """List all sites verified in the Bing Webmaster Tools account."""
        try:
            client = await get_client()
            sites = await client.get_sites()

            if not sites:
                return "No verified sites found."

            rows = []
            for s in sites:
                rows.append([
                    _safe_attr(s, "url"),
                    _safe_attr(s, "is_verified", "?"),
                ])

            return _fmt_table(
                ["URL", "Verified"],
                rows,
                "Bing Webmaster sites",
            )
        except BingWebmasterError as e:
            return f"Bing API error: {e} (code: {getattr(e, 'error_code', '?')})"

    # ── 2. Traffic analytics ────────────────────────────────────────────

    @mcp.tool()
    async def bing_top_queries(
        site_url: str = "",
        limit: int = 20,
    ) -> str:
        """Top Bing search queries with clicks, impressions and average position.
        site_url: site URL (default: BING_SITE_URL env var). limit: max results."""
        try:
            client = await get_client()
            site = site_url or get_site_url()
            stats = await client.get_query_stats(site)

            if not stats:
                return f"No query data for {site}"

            # The API returns one row per (query, date). Aggregate across dates.
            agg = {}
            for s in stats:
                q = getattr(s, "query", None) or "(?)"
                if q not in agg:
                    agg[q] = {"clicks": 0, "impressions": 0, "pos_sum": 0.0, "pos_n": 0, "last_date": None}
                a = agg[q]
                a["clicks"] += int(getattr(s, "clicks", 0) or 0)
                a["impressions"] += int(getattr(s, "impressions", 0) or 0)
                pos = getattr(s, "avg_impression_position", None)
                if pos is not None:
                    try:
                        a["pos_sum"] += float(pos); a["pos_n"] += 1
                    except (TypeError, ValueError):
                        pass
                d = getattr(s, "date", None)
                if d is not None and (a["last_date"] is None or d > a["last_date"]):
                    a["last_date"] = d

            top = sorted(agg.items(), key=lambda kv: (kv[1]["clicks"], kv[1]["impressions"]), reverse=True)[:limit]

            rows = []
            for q, a in top:
                avg_pos = f"{a['pos_sum']/a['pos_n']:.1f}" if a["pos_n"] else "N/A"
                rows.append([
                    q,
                    _fmt_number(a["clicks"]),
                    _fmt_number(a["impressions"]),
                    avg_pos,
                    format_date(a["last_date"]),
                ])

            return _fmt_table(
                ["Query", "Clicks", "Impressions", "Avg pos.", "Last date"],
                rows,
                f"Bing top queries — {site} (aggregated over {len(stats)} historical rows)",
            )
        except BingWebmasterError as e:
            return f"Bing API error: {e} (code: {getattr(e, 'error_code', '?')})"

    @mcp.tool()
    async def bing_top_pages(
        site_url: str = "",
        limit: int = 20,
    ) -> str:
        """Top pages on Bing with clicks, impressions and average position.
        site_url: site URL (default: BING_SITE_URL env var). limit: max results."""
        try:
            client = await get_client()
            site = site_url or get_site_url()
            stats = await client.get_page_stats(site)

            if not stats:
                return f"No page data for {site}"

            # The API exposes the page URL in the .query field (Bing API idiosyncrasy).
            agg = {}
            for s in stats:
                p = getattr(s, "query", None) or "(?)"
                if p not in agg:
                    agg[p] = {"clicks": 0, "impressions": 0, "pos_sum": 0.0, "pos_n": 0, "last_date": None}
                a = agg[p]
                a["clicks"] += int(getattr(s, "clicks", 0) or 0)
                a["impressions"] += int(getattr(s, "impressions", 0) or 0)
                pos = getattr(s, "avg_impression_position", None)
                if pos is not None:
                    try:
                        a["pos_sum"] += float(pos); a["pos_n"] += 1
                    except (TypeError, ValueError):
                        pass
                d = getattr(s, "date", None)
                if d is not None and (a["last_date"] is None or d > a["last_date"]):
                    a["last_date"] = d

            top = sorted(agg.items(), key=lambda kv: (kv[1]["clicks"], kv[1]["impressions"]), reverse=True)[:limit]

            rows = []
            for p, a in top:
                avg_pos = f"{a['pos_sum']/a['pos_n']:.1f}" if a["pos_n"] else "N/A"
                rows.append([
                    p,
                    _fmt_number(a["clicks"]),
                    _fmt_number(a["impressions"]),
                    avg_pos,
                    format_date(a["last_date"]),
                ])

            return _fmt_table(
                ["Page", "Clicks", "Impressions", "Avg pos.", "Last date"],
                rows,
                f"Bing top pages — {site} (aggregated over {len(stats)} historical rows)",
            )
        except BingWebmasterError as e:
            return f"Bing API error: {e} (code: {getattr(e, 'error_code', '?')})"

    @mcp.tool()
    async def bing_traffic_stats(
        site_url: str = "",
        days: int = 30,
    ) -> str:
        """Daily Bing traffic statistics: clicks and impressions over time.
        site_url: site URL. days: last N days to show."""
        try:
            client = await get_client()
            site = site_url or get_site_url()
            stats = await client.get_rank_and_traffic_stats(site)

            if not stats:
                return f"No traffic data for {site}"

            # The API returns data ordered by date ASC. Take last N days, show DESC.
            recent = sorted(stats, key=_sort_date, reverse=True)[:days]

            rows = []
            for s in recent:
                rows.append([
                    format_date(getattr(s, "date", None)),
                    _fmt_number(getattr(s, "clicks", 0)),
                    _fmt_number(getattr(s, "impressions", 0)),
                ])

            tot_clicks = sum(int(getattr(s, "clicks", 0) or 0) for s in recent)
            tot_impr = sum(int(getattr(s, "impressions", 0) or 0) for s in recent)

            return _fmt_table(
                ["Date", "Clicks", "Impressions"],
                rows,
                f"Bing daily traffic — {site} (last {len(recent)} days: {tot_clicks} clicks, {tot_impr} impr)",
            )
        except BingWebmasterError as e:
            return f"Bing API error: {e} (code: {getattr(e, 'error_code', '?')})"

    @mcp.tool()
    async def bing_queries_for_page(
        page: str,
        site_url: str = "",
        limit: int = 20,
    ) -> str:
        """Search queries that drive traffic to a specific page.
        page: full page URL (e.g. https://example.com/some-page)."""
        try:
            client = await get_client()
            site = site_url or get_site_url()
            stats = await client.get_page_query_stats(site, page)

            if not stats:
                return f"No queries found for {page}"

            agg = {}
            for s in stats:
                q = getattr(s, "query", None) or "(?)"
                if q not in agg:
                    agg[q] = {"clicks": 0, "impressions": 0, "pos_sum": 0.0, "pos_n": 0}
                a = agg[q]
                a["clicks"] += int(getattr(s, "clicks", 0) or 0)
                a["impressions"] += int(getattr(s, "impressions", 0) or 0)
                pos = getattr(s, "avg_click_position", None)
                if pos is not None:
                    try:
                        a["pos_sum"] += float(pos); a["pos_n"] += 1
                    except (TypeError, ValueError):
                        pass

            top = sorted(agg.items(), key=lambda kv: (kv[1]["clicks"], kv[1]["impressions"]), reverse=True)[:limit]

            rows = []
            for q, a in top:
                avg_pos = f"{a['pos_sum']/a['pos_n']:.1f}" if a["pos_n"] else "N/A"
                rows.append([
                    q,
                    _fmt_number(a["clicks"]),
                    _fmt_number(a["impressions"]),
                    avg_pos,
                ])

            return _fmt_table(
                ["Query", "Clicks", "Impressions", "Click pos."],
                rows,
                f"Queries for page: {page} (aggregated over {len(stats)} rows)",
            )
        except BingWebmasterError as e:
            return f"Bing API error: {e} (code: {getattr(e, 'error_code', '?')})"

    @mcp.tool()
    async def bing_pages_for_query(
        query: str,
        site_url: str = "",
        limit: int = 20,
    ) -> str:
        """Pages that rank for a specific query on Bing.
        query: search term to analyze."""
        try:
            client = await get_client()
            site = site_url or get_site_url()
            stats = await client.get_query_page_stats(site, query)

            if not stats:
                return f"No pages found for query '{query}'"

            agg = {}
            for s in stats:
                p = getattr(s, "query", None) or "(?)"
                if p not in agg:
                    agg[p] = {"clicks": 0, "impressions": 0, "pos_sum": 0.0, "pos_n": 0}
                a = agg[p]
                a["clicks"] += int(getattr(s, "clicks", 0) or 0)
                a["impressions"] += int(getattr(s, "impressions", 0) or 0)
                pos = getattr(s, "avg_click_position", None)
                if pos is not None:
                    try:
                        a["pos_sum"] += float(pos); a["pos_n"] += 1
                    except (TypeError, ValueError):
                        pass

            top = sorted(agg.items(), key=lambda kv: (kv[1]["clicks"], kv[1]["impressions"]), reverse=True)[:limit]

            rows = []
            for p, a in top:
                avg_pos = f"{a['pos_sum']/a['pos_n']:.1f}" if a["pos_n"] else "N/A"
                rows.append([
                    p,
                    _fmt_number(a["clicks"]),
                    _fmt_number(a["impressions"]),
                    avg_pos,
                ])

            return _fmt_table(
                ["Page", "Clicks", "Impressions", "Click pos."],
                rows,
                f"Pages for query: {query} (aggregated over {len(stats)} rows)",
            )
        except BingWebmasterError as e:
            return f"Bing API error: {e} (code: {getattr(e, 'error_code', '?')})"

    @mcp.tool()
    async def bing_query_page_detail(
        query: str,
        page: str,
        site_url: str = "",
    ) -> str:
        """Detailed statistics for a specific query + page combination.
        query: search term. page: full page URL."""
        try:
            client = await get_client()
            site = site_url or get_site_url()
            stats = await client.get_query_page_detail_stats(site, query, page)

            if not stats:
                return f"No detail for query='{query}' page='{page}'"

            stats = sorted(stats, key=_sort_date, reverse=True)
            rows = []
            for s in stats:
                rows.append([
                    format_date(getattr(s, "date", None)),
                    _fmt_number(getattr(s, "clicks", 0)),
                    _fmt_number(getattr(s, "impressions", 0)),
                    _safe_attr(s, "avg_click_position"),
                    _safe_attr(s, "avg_impression_position"),
                ])

            return _fmt_table(
                ["Date", "Clicks", "Impressions", "Click pos.", "Impr. pos."],
                rows,
                f"Detail: '{query}' -> {page}",
            )
        except BingWebmasterError as e:
            return f"Bing API error: {e} (code: {getattr(e, 'error_code', '?')})"

    @mcp.tool()
    async def bing_query_traffic(
        query: str,
        site_url: str = "",
    ) -> str:
        """Daily traffic trend for a specific query on Bing.
        query: search term to analyze."""
        try:
            client = await get_client()
            site = site_url or get_site_url()
            stats = await client.get_query_traffic_stats(site, query)

            if not stats:
                return f"No traffic data for query '{query}'"

            stats = sorted(stats, key=_sort_date, reverse=True)
            rows = []
            for s in stats:
                rows.append([
                    format_date(getattr(s, "date", None)),
                    _fmt_number(getattr(s, "clicks", 0)),
                    _fmt_number(getattr(s, "impressions", 0)),
                ])

            tot_clicks = sum(int(getattr(s, "clicks", 0) or 0) for s in stats)
            tot_impr = sum(int(getattr(s, "impressions", 0) or 0) for s in stats)
            return _fmt_table(
                ["Date", "Clicks", "Impressions"],
                rows,
                f"Query traffic: '{query}' (total: {tot_clicks} clicks, {tot_impr} impr over {len(stats)} days)",
            )
        except BingWebmasterError as e:
            return f"Bing API error: {e} (code: {getattr(e, 'error_code', '?')})"

    # ── 3. Crawl statistics ─────────────────────────────────────────────

    @mcp.tool()
    async def bing_crawl_stats(
        site_url: str = "",
    ) -> str:
        """Bing crawl statistics: crawled pages, errors, redirects, etc.
        site_url: site URL (default: BING_SITE_URL env var)."""
        try:
            client = await get_client()
            site = site_url or get_site_url()
            stats = await client.get_crawl_stats(site)

            if not stats:
                return f"No crawl data for {site}"

            rows = []
            for s in stats:
                rows.append([
                    format_date(getattr(s, "date", None)),
                    _fmt_number(getattr(s, "crawled_pages", 0)),
                    _fmt_number(getattr(s, "in_index", 0)),
                    _fmt_number(getattr(s, "in_links", 0)),
                    _fmt_number(getattr(s, "crawl_errors", 0)),
                    _safe_attr(s, "all_other_codes"),
                ])

            return _fmt_table(
                ["Date", "Pages", "In Index", "Inbound Links", "Errors", "Other Codes"],
                rows,
                f"Bing crawl stats — {site}",
            )
        except BingWebmasterError as e:
            return f"Bing API error: {e} (code: {getattr(e, 'error_code', '?')})"

    @mcp.tool()
    async def bing_crawl_issues(
        site_url: str = "",
        limit: int = 30,
    ) -> str:
        """URLs with crawl problems (4xx/5xx errors, redirects, etc.).
        site_url: site URL. limit: max results."""
        try:
            client = await get_client()
            site = site_url or get_site_url()
            issues = await client.get_crawl_issues(site)

            if not issues:
                return f"No crawl issues for {site}"

            rows = []
            for i in issues[:limit]:
                rows.append([
                    _safe_attr(i, "url"),
                    _safe_attr(i, "http_code"),
                    _safe_attr(i, "issues"),
                    format_date(getattr(i, "date", None)),
                ])

            return _fmt_table(
                ["URL", "HTTP Code", "Issue", "Date"],
                rows,
                f"Bing crawl issues — {site}",
            )
        except BingWebmasterError as e:
            return f"Bing API error: {e} (code: {getattr(e, 'error_code', '?')})"

    # ── 4. Keyword research ─────────────────────────────────────────────

    @mcp.tool()
    async def bing_keyword_stats(
        keyword: str,
        country: str = "us",
        language: str = "en-US",
    ) -> str:
        """Historical statistics for a keyword on Bing: impressions and trend.
        keyword: term to analyze. country: lowercase country code (e.g. "us").
        language: locale code (e.g. "en-US")."""
        try:
            client = await get_client()
            stats = await client.get_keyword_stats(keyword, country, language)

            if not stats:
                return f"No data for keyword '{keyword}' ({country}/{language})"

            rows = []
            for s in stats:
                rows.append([
                    format_date(getattr(s, "date", None)),
                    _fmt_number(getattr(s, "impressions", 0)),
                    _safe_attr(s, "broad_impressions"),
                ])

            return _fmt_table(
                ["Date", "Impressions", "Broad Impressions"],
                rows,
                f"Bing keyword stats: '{keyword}' ({country}/{language})",
            )
        except BingWebmasterError as e:
            return f"Bing API error: {e} (code: {getattr(e, 'error_code', '?')})"

    @mcp.tool()
    async def bing_related_keywords(
        keyword: str,
        country: str = "us",
        language: str = "en-US",
        days: int = 30,
    ) -> str:
        """Keywords related to a search term on Bing, with impression data.
        keyword: seed term. days: lookback period in days."""
        try:
            client = await get_client()
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            related = await client.get_related_keywords(
                keyword, country, language, start_date, end_date
            )

            if not related:
                return f"No related keywords for '{keyword}'"

            rows = []
            for r in related:
                rows.append([
                    _safe_attr(r, "query"),
                    _fmt_number(getattr(r, "impressions", 0)),
                    _safe_attr(r, "broad_impressions"),
                ])

            return _fmt_table(
                ["Keyword", "Impressions", "Broad Impressions"],
                rows,
                f"Keywords related to '{keyword}' ({country}/{language})",
            )
        except BingWebmasterError as e:
            return f"Bing API error: {e} (code: {getattr(e, 'error_code', '?')})"

    @mcp.tool()
    async def bing_keyword(
        query: str,
        country: str = "us",
        language: str = "en-US",
        days: int = 30,
    ) -> str:
        """Bing impression volume for an exact query (impressions + broad).
        query: exact term. days: lookback period in days.
        Note: country must be lowercase (e.g. "us", not "US"); language is a
        locale code (e.g. "en-US")."""
        try:
            client = await get_client()
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            kw = await client.get_keyword(
                query, country, language, start_date, end_date
            )

            if not kw:
                return f"No data for '{query}' ({country}/{language})"

            rows = [[
                _safe_attr(kw, "query"),
                _fmt_number(getattr(kw, "impressions", 0)),
                _fmt_number(getattr(kw, "broad_impressions", 0)),
            ]]

            return _fmt_table(
                ["Query", "Impressions", "Broad Impressions"],
                rows,
                f"Bing keyword volume — '{query}' ({country}/{language}, {days}d)",
            )
        except BingWebmasterError as e:
            return f"Bing API error: {e} (code: {getattr(e, 'error_code', '?')})"

    # ── 5. URL info ─────────────────────────────────────────────────────

    @mcp.tool()
    async def bing_url_info(
        url: str,
        site_url: str = "",
    ) -> str:
        """Indexing status of a specific URL on Bing.
        url: full URL to check."""
        try:
            client = await get_client()
            site = site_url or get_site_url()
            info = await client.get_url_info(site, url)

            if not info:
                return f"No data for {url}"

            lines = [
                "=== Bing URL Info ===",
                f"URL: {url}",
                "",
                f"  HTTP Status:     {_safe_attr(info, 'http_status')}",
                f"  Is Page:         {_safe_attr(info, 'is_page')}",
                f"  Anchor Count:    {_safe_attr(info, 'anchor_count')}",
                f"  Last Crawled:    {format_date(getattr(info, 'last_crawled_date', None))}",
                f"  Discovered:      {format_date(getattr(info, 'discovery_date', None))}",
            ]
            return "\n".join(lines)
        except BingWebmasterError as e:
            return f"Bing API error: {e} (code: {getattr(e, 'error_code', '?')})"

    @mcp.tool()
    async def bing_url_traffic(
        url: str,
        site_url: str = "",
    ) -> str:
        """Traffic data for a specific URL on Bing.
        url: full URL to analyze."""
        try:
            client = await get_client()
            site = site_url or get_site_url()
            info = await client.get_url_traffic_info(site, url)

            if not info:
                return f"No traffic data for {url}"

            lines = [
                "=== Bing URL Traffic ===",
                f"URL: {url}",
                "",
                f"  Clicks:          {_fmt_number(getattr(info, 'clicks', 0))}",
                f"  Impressions:     {_fmt_number(getattr(info, 'impressions', 0))}",
            ]
            return "\n".join(lines)
        except BingWebmasterError as e:
            return f"Bing API error: {e} (code: {getattr(e, 'error_code', '?')})"

    # ── 6. URL submission ───────────────────────────────────────────────

    @mcp.tool()
    async def bing_submit_url(
        url: str,
        site_url: str = "",
    ) -> str:
        """Submit a URL to Bing for indexing.
        url: full URL to submit."""
        try:
            client = await get_client()
            site = site_url or get_site_url()
            await client.submit_url(site, url)
            return f"URL successfully submitted to Bing: {url}"
        except BingWebmasterError as e:
            return f"URL submission error: {e.message} (code: {e.error_code})"

    @mcp.tool()
    async def bing_submit_urls_batch(
        urls: list[str],
        site_url: str = "",
    ) -> str:
        """Submit a batch of URLs to Bing for indexing (max 500).
        urls: list of full URLs to submit."""
        try:
            client = await get_client()
            site = site_url or get_site_url()

            if len(urls) > 500:
                return f"Error: max 500 URLs per batch, got {len(urls)}"

            await client.submit_url_batch(site, urls)
            return f"{len(urls)} URLs successfully submitted to Bing"
        except BingWebmasterError as e:
            return f"Batch submission error: {e.message} (code: {e.error_code})"

    @mcp.tool()
    async def bing_submission_quota(
        site_url: str = "",
    ) -> str:
        """Check the URL submission quota for Bing.
        Shows the daily and monthly quotas (limits)."""
        try:
            client = await get_client()
            site = site_url or get_site_url()
            quota = await client.get_url_submission_quota(site)

            if not quota:
                return f"Could not retrieve quota for {site}"

            lines = [
                "=== Bing URL Submission Quota ===",
                f"Site: {site}",
                "",
                f"  Daily quota:    {_safe_attr(quota, 'daily_quota')}",
                f"  Monthly quota:  {_safe_attr(quota, 'monthly_quota')}",
            ]
            return "\n".join(lines)
        except BingWebmasterError as e:
            return f"Quota error: {e.message} (code: {e.error_code})"

    # ── 7. Sitemaps / feeds ─────────────────────────────────────────────

    @mcp.tool()
    async def bing_sitemaps(
        site_url: str = "",
    ) -> str:
        """List all sitemaps/feeds submitted to Bing.
        site_url: site URL (default: BING_SITE_URL env var)."""
        try:
            client = await get_client()
            site = site_url or get_site_url()
            feeds = await client.get_feeds(site)

            if not feeds:
                return f"No sitemaps/feeds for {site}"

            rows = []
            for f in feeds:
                rows.append([
                    _safe_attr(f, "url"),
                    _safe_attr(f, "status"),
                    _safe_attr(f, "last_crawled"),
                    _safe_attr(f, "url_count"),
                ])

            return _fmt_table(
                ["URL", "Status", "Last Crawl", "URL Count"],
                rows,
                f"Bing sitemaps/feeds — {site}",
            )
        except BingWebmasterError as e:
            return f"Bing API error: {e} (code: {getattr(e, 'error_code', '?')})"

    @mcp.tool()
    async def bing_submit_sitemap(
        feed_url: str,
        site_url: str = "",
    ) -> str:
        """Submit a new sitemap/feed to Bing.
        feed_url: sitemap URL (e.g. https://example.com/sitemap.xml)."""
        try:
            client = await get_client()
            site = site_url or get_site_url()
            await client.submit_feed(site, feed_url)
            return f"Sitemap successfully submitted: {feed_url}"
        except BingWebmasterError as e:
            return f"Sitemap submission error: {e.message} (code: {e.error_code})"

    # ── 8. Backlinks ────────────────────────────────────────────────────

    @mcp.tool()
    async def bing_link_counts(
        site_url: str = "",
    ) -> str:
        """Pages with the highest number of backlinks according to Bing.
        site_url: site URL (default: BING_SITE_URL env var)."""
        try:
            client = await get_client()
            site = site_url or get_site_url()

            counts = await client.get_link_counts(site)
            items = list(getattr(counts, "links", None) or [])
            total_pages = getattr(counts, "total_pages", 0) or 0
            for page in range(1, total_pages):
                more = await client.get_link_counts(site, page=page)
                items.extend(getattr(more, "links", None) or [])

            if not items:
                return (
                    f"No backlinks in the Bing API for {site}. "
                    f"The legacy API (GetLinkCounts) is empty; backlinks visible "
                    f"in the dashboard are NOT exposed via the API."
                )

            rows = [
                [_safe_attr(item, "url"), _fmt_number(getattr(item, "count", 0))]
                for item in items
            ]

            return _fmt_table(
                ["URL", "Backlinks"],
                rows,
                f"Bing backlinks — {site}",
            )
        except BingWebmasterError as e:
            return f"Bing API error: {e} (code: {getattr(e, 'error_code', '?')})"

    @mcp.tool()
    async def bing_url_links(
        url: str,
        site_url: str = "",
    ) -> str:
        """Inbound backlinks to a specific URL according to Bing.
        url: full URL to find backlinks for."""
        try:
            client = await get_client()
            site = site_url or get_site_url()

            details = await client.get_url_links(site, url)
            items = list(getattr(details, "details", None) or [])
            total_pages = getattr(details, "total_pages", 0) or 0
            for page in range(1, total_pages):
                more = await client.get_url_links(site, url, page=page)
                items.extend(getattr(more, "details", None) or [])

            if not items:
                return (
                    f"No backlinks in the Bing API to {url}. "
                    f"The legacy API (GetUrlLinks) is empty; backlinks visible "
                    f"in the dashboard are NOT exposed via the API."
                )

            rows = [
                [_safe_attr(item, "url"), _safe_attr(item, "anchor_text")]
                for item in items
            ]

            return _fmt_table(
                ["Source", "Anchor Text"],
                rows,
                f"Backlinks to {url}",
            )
        except BingWebmasterError as e:
            return f"Bing API error: {e} (code: {getattr(e, 'error_code', '?')})"
