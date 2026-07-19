"""Google Search Console API client helpers.

Builds (and caches) the Search Console and Indexing API service objects
using the shared credential source in ``seo_stack_mcp.google_auth``.
"""

import os
from datetime import datetime, timedelta

from googleapiclient.discovery import build

from ..google_auth import get_google_credentials

_gsc_service = None
_indexing_service = None


def get_gsc_service():
    """Return a cached Search Console API service object."""
    global _gsc_service
    if _gsc_service is None:
        _gsc_service = build(
            "searchconsole", "v1",
            credentials=get_google_credentials(),
            cache_discovery=False,
        )
    return _gsc_service


def get_indexing_service():
    """Return a cached Google Indexing API service object.

    Note: the Indexing API requires the ``https://www.googleapis.com/auth/indexing``
    scope on the configured credentials.
    """
    global _indexing_service
    if _indexing_service is None:
        _indexing_service = build(
            "indexing", "v3",
            credentials=get_google_credentials(),
            cache_discovery=False,
        )
    return _indexing_service


def fresh_authorized_http():
    """Return a new AuthorizedHttp bound to the shared credentials.

    httplib2 is not thread-safe: concurrent ``.execute()`` calls must each use
    their own http object (``request.execute(http=...)``), one per thread.
    """
    import httplib2
    import google_auth_httplib2

    return google_auth_httplib2.AuthorizedHttp(
        get_google_credentials(), http=httplib2.Http()
    )


def resolve_site_url(site_url: str | None) -> str:
    """Return the site URL to use: the explicit parameter, or the GSC_SITE_URL env var."""
    if site_url:
        return site_url
    env_site = os.getenv("GSC_SITE_URL", "")
    if env_site:
        return env_site
    raise ValueError(
        "No site URL provided. Pass the site_url parameter "
        "(e.g. 'https://example.com/' or 'sc-domain:example.com') "
        "or set the GSC_SITE_URL environment variable."
    )


def query_gsc(service, site_url: str, start_date: str, end_date: str,
              dimensions: list[str], row_limit: int = 25000,
              dimension_filters: list[dict] | None = None) -> list[dict]:
    """Query the GSC Search Analytics API with optional dimension filters."""
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": dimensions,
        "rowLimit": row_limit,
    }
    if dimension_filters:
        body["dimensionFilterGroups"] = [{
            "filters": dimension_filters
        }]
    result = service.searchanalytics().query(siteUrl=site_url, body=body).execute()
    return result.get("rows", [])


def date_ago(days: int) -> str:
    """Return the date N days ago as a YYYY-MM-DD string."""
    return (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
