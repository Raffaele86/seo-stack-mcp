"""Google Keyword Planner — 4 MCP tools (via Google Ads API).

Requires the ``google-ads`` extra: ``pip install seo-stack-mcp[ads]``.
"""

import logging

from . import client as kp

log = logging.getLogger("seo-stack-mcp.keyword-planner")


def _live_error(ex):
    """Structured, honest error payload when a live call fails."""
    try:
        from google.ads.googleads.errors import GoogleAdsException
        if isinstance(ex, GoogleAdsException):
            return {"error": "google_ads_api", "messages": kp.format_exception(ex)}
    except Exception:
        pass
    return {"error": type(ex).__name__, "messages": [str(ex)]}


def register(mcp):
    """Register all Keyword Planner tools on the given FastMCP server."""

    @mcp.tool()
    def kp_status() -> dict:
        """Keyword Planner source status: google-ads library, credential
        completeness (masked) and a live connection test. Never fakes data:
        it states explicitly what is configured and what is not."""
        status = {
            "google_ads_library_installed": kp.library_installed(),
            "credentials": kp.credentials_present(),
            "defaults": {
                "location_id": kp.DEFAULT_LOCATION_ID,
                "language_id": kp.DEFAULT_LANGUAGE_ID,
            },
            "live_api": "unavailable",
            "detail": "",
        }
        if not status["google_ads_library_installed"]:
            status["detail"] = (
                "The 'google-ads' library is not installed. "
                "Install with: pip install seo-stack-mcp[ads] "
                "(or run: uvx --with google-ads seo-stack-mcp)."
            )
        elif not status["credentials"]["all_required_present"]:
            status["detail"] = "Incomplete Google Ads credentials (see README)."
        else:
            ok, detail = kp.test_connection()
            status["live_api"] = "ok" if ok else "error"
            status["detail"] = detail
        return status

    @mcp.tool()
    def kp_keyword_ideas(seed_keywords: list[str] | None = None, page_url: str = "",
                         location_id: int = 0, language_id: int = 0,
                         network: str = "GOOGLE_SEARCH", limit: int = 100) -> dict:
        """Keyword ideas with REAL Google Keyword Planner metrics.

        At least one of seed_keywords and page_url. Defaults: US / English
        (override with location_id/language_id or the GOOGLE_ADS_LOCATION_ID /
        GOOGLE_ADS_LANGUAGE_ID env vars). Per keyword: avg_monthly_searches,
        competition (LOW/MEDIUM/HIGH), competition_index, top-of-page bid
        low/high (account currency), monthly_search_volumes (12 months).
        """
        try:
            rows = kp.generate_keyword_ideas(
                seed_keywords=seed_keywords, page_url=page_url,
                location_id=location_id, language_id=language_id,
                network=network, limit=limit,
            )
            return {"count": len(rows), "rows": rows}
        except Exception as ex:
            return _live_error(ex)

    @mcp.tool()
    def kp_historical_metrics(keywords: list[str], location_id: int = 0,
                              language_id: int = 0) -> dict:
        """REAL historical Keyword Planner metrics for a list of known keywords."""
        try:
            rows = kp.get_historical_metrics(
                keywords, location_id=location_id, language_id=language_id
            )
            return {"count": len(rows), "rows": rows}
        except Exception as ex:
            return _live_error(ex)

    @mcp.tool()
    def kp_suggest_geo_target(location_name: str, locale: str = "en",
                              country_code: str = "US") -> dict:
        """Resolve a location name to its geo target constant ID
        (use the ID as location_id in the other kp_* tools)."""
        try:
            return {
                "suggestions": kp.suggest_geo_targets(
                    location_name, locale=locale, country_code=country_code
                )
            }
        except Exception as ex:
            return _live_error(ex)

    log.info("registered 4 Keyword Planner tools")
