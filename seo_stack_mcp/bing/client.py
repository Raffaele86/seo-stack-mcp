"""Bing Webmaster Tools API client.

Thin async wrapper around the Bing Webmaster JSON API
(https://ssl.bing.com/webmaster/api.svc/json), using httpx.

Responses are wrapped in :class:`ApiObject` instances that expose the
API's PascalCase fields as snake_case attributes (``AvgClickPosition``
-> ``avg_click_position``) and parse WCF ``/Date(ms)/`` strings into
``datetime`` objects, so callers can use plain attribute access.
"""

import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

API_BASE = "https://ssl.bing.com/webmaster/api.svc/json"


class BingWebmasterError(Exception):
    """Error returned by the Bing Webmaster API (or missing configuration)."""

    def __init__(self, message: str, error_code: Any = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


# ---------------------------------------------------------------------------
# Response conversion
# ---------------------------------------------------------------------------

_WCF_DATE_RE = re.compile(r"^/Date\((-?\d+)(?:[+-]\d{4})?\)/$")
_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")


def _snake(name: str) -> str:
    """Convert a PascalCase API field name to snake_case."""
    return _CAMEL_RE.sub("_", name).lower()


def _convert(value):
    """Recursively convert an API JSON value (objects, lists, WCF dates)."""
    if isinstance(value, dict):
        return ApiObject(value)
    if isinstance(value, list):
        return [_convert(v) for v in value]
    if isinstance(value, str):
        m = _WCF_DATE_RE.match(value)
        if m:
            return datetime.fromtimestamp(
                int(m.group(1)) / 1000, tz=timezone.utc
            ).replace(tzinfo=None)
    return value


class ApiObject:
    """Attribute-access wrapper over an API JSON object (snake_case keys)."""

    def __init__(self, data: dict):
        self._data = {
            _snake(k): _convert(v)
            for k, v in data.items()
            if not k.startswith("__")  # drop WCF "__type" metadata
        }

    def __getattr__(self, name: str):
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(name) from None

    def __repr__(self) -> str:
        return f"ApiObject({self._data!r})"


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class BingWebmasterClient:
    """Async client for the Bing Webmaster Tools JSON API."""

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._http = httpx.AsyncClient(timeout=30.0)

    async def _request(self, method: str, params: dict, json_body: Optional[dict] = None):
        query = {k: v for k, v in params.items() if v is not None}
        query["apikey"] = self._api_key
        try:
            if json_body is None:
                resp = await self._http.get(f"{API_BASE}/{method}", params=query)
            else:
                resp = await self._http.post(
                    f"{API_BASE}/{method}", params=query, json=json_body
                )
        except httpx.HTTPError as e:
            raise BingWebmasterError(f"HTTP request failed: {e}") from e

        if resp.status_code >= 400:
            message = resp.text
            code: Any = resp.status_code
            try:
                err = resp.json()
                if isinstance(err, dict):
                    message = err.get("Message") or err.get("message") or message
                    code = err.get("ErrorCode", code)
            except ValueError:
                pass
            raise BingWebmasterError(message, error_code=code)

        try:
            data = resp.json()
        except ValueError:
            raise BingWebmasterError(f"Invalid JSON response from {method}") from None
        if isinstance(data, dict) and "d" in data:
            data = data["d"]
        return _convert(data)

    async def _get(self, method: str, **params):
        return await self._request(method, params)

    async def _post(self, method: str, body: dict):
        return await self._request(method, {}, json_body=body)

    @staticmethod
    def _date(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%d")

    # ── Sites ───────────────────────────────────────────────────────────

    async def get_sites(self):
        """List all sites verified in the account."""
        return await self._get("GetUserSites") or []

    # ── Traffic analytics ───────────────────────────────────────────────

    async def get_query_stats(self, site_url: str):
        return await self._get("GetQueryStats", siteUrl=site_url) or []

    async def get_page_stats(self, site_url: str):
        return await self._get("GetPageStats", siteUrl=site_url) or []

    async def get_rank_and_traffic_stats(self, site_url: str):
        return await self._get("GetRankAndTrafficStats", siteUrl=site_url) or []

    async def get_page_query_stats(self, site_url: str, page: str):
        return await self._get("GetPageQueryStats", siteUrl=site_url, page=page) or []

    async def get_query_page_stats(self, site_url: str, query: str):
        return await self._get("GetQueryPageStats", siteUrl=site_url, query=query) or []

    async def get_query_page_detail_stats(self, site_url: str, query: str, page: str):
        return (
            await self._get(
                "GetQueryPageDetailStats", siteUrl=site_url, query=query, page=page
            )
            or []
        )

    async def get_query_traffic_stats(self, site_url: str, query: str):
        return (
            await self._get("GetQueryTrafficStats", siteUrl=site_url, query=query) or []
        )

    # ── Crawl statistics ────────────────────────────────────────────────

    async def get_crawl_stats(self, site_url: str):
        return await self._get("GetCrawlStats", siteUrl=site_url) or []

    async def get_crawl_issues(self, site_url: str):
        return await self._get("GetCrawlIssues", siteUrl=site_url) or []

    # ── Keyword research ────────────────────────────────────────────────

    async def get_keyword_stats(self, keyword: str, country: str, language: str):
        return (
            await self._get(
                "GetKeywordStats", q=keyword, country=country, language=language
            )
            or []
        )

    async def get_related_keywords(
        self,
        keyword: str,
        country: str,
        language: str,
        start_date: datetime,
        end_date: datetime,
    ):
        return (
            await self._get(
                "GetRelatedKeywords",
                q=keyword,
                country=country,
                language=language,
                startDate=self._date(start_date),
                endDate=self._date(end_date),
            )
            or []
        )

    async def get_keyword(
        self,
        query: str,
        country: str,
        language: str,
        start_date: datetime,
        end_date: datetime,
    ):
        return await self._get(
            "GetKeyword",
            q=query,
            country=country,
            language=language,
            startDate=self._date(start_date),
            endDate=self._date(end_date),
        )

    # ── URL info ────────────────────────────────────────────────────────

    async def get_url_info(self, site_url: str, url: str):
        return await self._get("GetUrlInfo", siteUrl=site_url, url=url)

    async def get_url_traffic_info(self, site_url: str, url: str):
        return await self._get("GetUrlTrafficInfo", siteUrl=site_url, url=url)

    # ── URL submission ──────────────────────────────────────────────────

    async def submit_url(self, site_url: str, url: str):
        return await self._post("SubmitUrl", {"siteUrl": site_url, "url": url})

    async def submit_url_batch(self, site_url: str, urls: list):
        return await self._post(
            "SubmitUrlBatch", {"siteUrl": site_url, "urlList": urls}
        )

    async def get_url_submission_quota(self, site_url: str):
        return await self._get("GetUrlSubmissionQuota", siteUrl=site_url)

    # ── Sitemaps / feeds ────────────────────────────────────────────────

    async def get_feeds(self, site_url: str):
        return await self._get("GetFeeds", siteUrl=site_url) or []

    async def submit_feed(self, site_url: str, feed_url: str):
        return await self._post(
            "SubmitFeed", {"siteUrl": site_url, "feedUrl": feed_url}
        )

    # ── Backlinks ───────────────────────────────────────────────────────

    async def get_link_counts(self, site_url: str, page: int = 0):
        return await self._get("GetLinkCounts", siteUrl=site_url, page=page)

    async def get_url_links(self, site_url: str, url: str, page: int = 0):
        return await self._get("GetUrlLinks", siteUrl=site_url, link=url, page=page)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_client: Optional[BingWebmasterClient] = None


async def get_client() -> BingWebmasterClient:
    """Get or create the singleton BingWebmasterClient."""
    global _client
    if _client is None:
        api_key = os.getenv("BING_WEBMASTER_API_KEY", "")
        if not api_key:
            raise BingWebmasterError(
                "BING_WEBMASTER_API_KEY environment variable is not set. "
                "Generate an API key in Bing Webmaster Tools "
                "(Settings > API access) and export it."
            )
        _client = BingWebmasterClient(api_key)
    return _client


def get_site_url() -> str:
    """Get the default site URL from the environment."""
    url = os.getenv("BING_SITE_URL", "")
    if not url:
        raise ValueError(
            "No site URL provided. Pass the site_url parameter or set the "
            "BING_SITE_URL environment variable (e.g. https://example.com)."
        )
    return url


def format_date(dt) -> str:
    """Convert a datetime object to a YYYY-MM-DD string."""
    if dt is None:
        return "N/A"
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d")
    return str(dt)
