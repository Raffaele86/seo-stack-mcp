"""HTTP client for the Microsoft Clarity Data Export API.

Single endpoint: GET https://www.clarity.ms/export-data/api/v1/project-live-insights
Auth: Authorization: Bearer <token> (env ``CLARITY_API_TOKEN``).
Quota: the API allows 10 requests/day/project — enforced locally one call
short (see ``quota``), with responses cached (see ``cache``) so repeated
tool calls do not burn quota.
"""

import hashlib
import json
import logging
import os
from typing import Any, Optional

import httpx

from . import cache, quota

log = logging.getLogger("seo-stack-mcp.clarity")

ENDPOINT = "https://www.clarity.ms/export-data/api/v1/project-live-insights"

VALID_DIMENSIONS = {
    "Browser", "Device", "Country/Region", "OS",
    "Source", "Medium", "Campaign", "Channel", "URL",
}


class ClarityError(Exception):
    """Raised on any Clarity API failure (auth, quota, malformed, network)."""


_client: Optional[httpx.AsyncClient] = None


def get_token() -> str:
    """Return the Clarity API token, or raise ClarityError if not configured."""
    token = os.getenv("CLARITY_API_TOKEN", "").strip()
    if not token:
        raise ClarityError(
            "CLARITY_API_TOKEN is not set. Generate a Data Export API token in "
            "clarity.microsoft.com -> your project -> Settings -> Data Export "
            "and export it as the CLARITY_API_TOKEN environment variable."
        )
    return token


def project_key() -> str:
    """Stable key identifying the configured project for cache/quota buckets.

    Derived from the token hash so that switching to a different project's
    token does not inherit the previous project's quota counter (the 10
    requests/day limit is per project on the API side).
    """
    return "clarity-" + hashlib.sha256(get_token().encode("utf-8")).hexdigest()[:12]


def _cache_ttl() -> int:
    return int(os.getenv("CLARITY_CACHE_TTL", "21600"))


async def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=30.0,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
    return _client


def _validate_dimensions(*dims: Optional[str]) -> None:
    for d in dims:
        if d is None:
            continue
        if d not in VALID_DIMENSIONS:
            raise ClarityError(
                f"Invalid dimension '{d}'. Allowed: {sorted(VALID_DIMENSIONS)}"
            )


def _validate_days(days: int) -> None:
    if days not in (1, 2, 3):
        raise ClarityError(f"days must be 1, 2 or 3 (got {days}).")


async def fetch_insights(
    days: int = 1,
    dimension1: Optional[str] = None,
    dimension2: Optional[str] = None,
    dimension3: Optional[str] = None,
) -> tuple[Any, bool]:
    """Fetch a Clarity insights payload (cached). Returns (payload, from_cache)."""
    token = get_token()
    project = project_key()
    _validate_days(days)
    _validate_dimensions(dimension1, dimension2, dimension3)

    key = cache.make_key(project, days, dimension1, dimension2, dimension3)
    cached = cache.get(key)
    if cached is not None:
        return cached, True

    if quota.is_blocked(project):
        used = quota.used(project)
        raise ClarityError(
            f"Clarity quota exhausted for today ({used}/{os.getenv('CLARITY_DAILY_LIMIT', '9')} calls). "
            "The API limit resets at midnight UTC. Try again tomorrow or reuse cached data (TTL 6h)."
        )

    params: dict[str, str] = {"numOfDays": str(days)}
    if dimension1:
        params["dimension1"] = dimension1
    if dimension2:
        params["dimension2"] = dimension2
    if dimension3:
        params["dimension3"] = dimension3

    client = await _http()
    try:
        r = await client.get(
            ENDPOINT,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
    except httpx.RequestError as e:
        raise ClarityError(f"Network error: {e}") from e

    if r.status_code == 401:
        raise ClarityError(
            "401 Unauthorized — the Clarity token is expired or invalid. "
            "Regenerate it in clarity.microsoft.com -> Settings -> Data Export."
        )
    if r.status_code == 403:
        raise ClarityError(
            "403 Forbidden — the token is not authorized for Data Export. "
            "Only project admins can generate Data Export tokens."
        )
    if r.status_code == 429:
        # The API counted 10+ calls. Record it to realign the local counter.
        quota.record_call(project)
        raise ClarityError(
            "429 Too Many Requests — Clarity limit exceeded (10 calls/day/project). "
            "Resets at midnight UTC."
        )
    if r.status_code >= 400:
        raise ClarityError(f"Clarity API {r.status_code}: {r.text[:300]}")

    try:
        payload = r.json()
    except json.JSONDecodeError as e:
        raise ClarityError(f"Non-JSON response from Clarity: {e}") from e

    # Success: count quota and store in cache.
    quota.record_call(project)
    cache.set(key, payload, _cache_ttl())
    return payload, False


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
