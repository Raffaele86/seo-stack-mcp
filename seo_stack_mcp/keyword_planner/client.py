"""Google Keyword Planner via the official Google Ads API.

Real Keyword Planner data through ``KeywordPlanIdeaService``
(GenerateKeywordIdeas / GenerateKeywordHistoricalMetrics) and
``GeoTargetConstantService`` (SuggestGeoTargetConstants).

Google Ads API calls are free, but they require:
- a developer token (Basic access, requested in the Google Ads API Center)
- OAuth client_id/secret + refresh_token with the ``adwords`` scope
- a customer_id (10 digits) and, under a manager account, login_customer_id

The ``google-ads`` library import is lazy: install it with
``pip install seo-stack-mcp[ads]`` (or ``uvx --with google-ads seo-stack-mcp``).

Missing credentials and API errors are surfaced as explicit errors,
never masked with estimates.
"""

import os

API_VERSION = "v24"

# Google geo/language constant IDs (stable).
DEFAULT_LOCATION_ID = int(os.getenv("GOOGLE_ADS_LOCATION_ID", "2840"))  # United States
DEFAULT_LANGUAGE_ID = int(os.getenv("GOOGLE_ADS_LANGUAGE_ID", "1000"))  # English

_ENV_KEYS = {
    "developer_token": "GOOGLE_ADS_DEVELOPER_TOKEN",
    "client_id": "GOOGLE_ADS_CLIENT_ID",
    "client_secret": "GOOGLE_ADS_CLIENT_SECRET",
    "refresh_token": "GOOGLE_ADS_REFRESH_TOKEN",
    "login_customer_id": "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
    "customer_id": "GOOGLE_ADS_CUSTOMER_ID",
}


def _digits(s):
    return "".join(ch for ch in (s or "") if ch.isdigit())


def _env_config():
    return {k: os.getenv(env, "").strip() for k, env in _ENV_KEYS.items()}


def credentials_present():
    """Which credentials are present (masked, never echoed in clear)."""
    cfg = _env_config()
    required = ["developer_token", "client_id", "client_secret", "refresh_token", "customer_id"]
    cid = _digits(cfg["customer_id"])
    return {
        "all_required_present": all(cfg[k] for k in required),
        "fields": {k: bool(cfg[k]) for k in _ENV_KEYS},
        "customer_id": cid[-4:].rjust(len(cid), "*") if cid else None,
    }


def library_installed():
    try:
        import google.ads.googleads.client  # noqa: F401
        return True
    except Exception:
        return False


def _get_client():
    from google.ads.googleads.client import GoogleAdsClient

    cfg = _env_config()
    missing = [
        _ENV_KEYS[k]
        for k in ("developer_token", "client_id", "client_secret", "refresh_token", "customer_id")
        if not cfg[k]
    ]
    if missing:
        raise RuntimeError(f"Missing Google Ads credentials: {', '.join(missing)}")

    config = {
        "developer_token": cfg["developer_token"],
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "refresh_token": cfg["refresh_token"],
        "use_proto_plus": True,
    }
    login_cid = _digits(cfg["login_customer_id"])
    if login_cid:
        config["login_customer_id"] = login_cid

    return GoogleAdsClient.load_from_dict(config, version=API_VERSION)


def _customer_id():
    return _digits(_env_config()["customer_id"])


def _micros(v):
    """Micros -> currency units (1,000,000 micros = 1 unit). None if 0/absent."""
    if not v:
        return None
    return round(v / 1_000_000, 2)


def format_exception(ex):
    """Extract the real error messages from a GoogleAdsException."""
    msgs = []
    try:
        for err in ex.failure.errors:
            msgs.append(err.message)
    except Exception:
        msgs.append(str(ex))
    return msgs or [str(ex)]


def _metrics_dict(text, metrics):
    return {
        "keyword": text,
        "avg_monthly_searches": metrics.avg_monthly_searches or 0,
        "competition": metrics.competition.name if metrics.competition else "UNSPECIFIED",
        "competition_index": metrics.competition_index or None,
        "top_of_page_bid_low": _micros(metrics.low_top_of_page_bid_micros),
        "top_of_page_bid_high": _micros(metrics.high_top_of_page_bid_micros),
        "monthly_search_volumes": [
            {"year": v.year, "month": v.month.name, "searches": v.monthly_searches}
            for v in metrics.monthly_search_volumes
        ],
    }


def generate_keyword_ideas(seed_keywords=None, page_url="", location_id=0,
                           language_id=0, network="GOOGLE_SEARCH", limit=100):
    """Keyword ideas + real metrics. At least one of seed_keywords/page_url."""
    client = _get_client()
    gads = client.get_service("GoogleAdsService")
    svc = client.get_service("KeywordPlanIdeaService")

    request = client.get_type("GenerateKeywordIdeasRequest")
    request.customer_id = _customer_id()
    request.language = gads.language_constant_path(str(language_id or DEFAULT_LANGUAGE_ID))
    request.geo_target_constants.append(
        gads.geo_target_constant_path(str(location_id or DEFAULT_LOCATION_ID))
    )
    request.include_adult_keywords = False
    net_enum = client.enums.KeywordPlanNetworkEnum
    request.keyword_plan_network = (
        net_enum.GOOGLE_SEARCH_AND_PARTNERS if network.upper().endswith("PARTNERS")
        else net_enum.GOOGLE_SEARCH
    )

    seeds = [s for s in (seed_keywords or []) if s and s.strip()]
    if seeds and page_url:
        request.keyword_and_url_seed.url = page_url
        request.keyword_and_url_seed.keywords.extend(seeds)
    elif page_url:
        request.url_seed.url = page_url
    elif seeds:
        request.keyword_seed.keywords.extend(seeds)
    else:
        raise ValueError("Provide at least seed_keywords or page_url.")

    results = []
    for idea in svc.generate_keyword_ideas(request=request):
        results.append(_metrics_dict(idea.text, idea.keyword_idea_metrics))
        if len(results) >= limit:
            break
    return results


def get_historical_metrics(keywords, location_id=0, language_id=0):
    """Real metrics for a list of known keywords."""
    kws = [k for k in (keywords or []) if k and k.strip()]
    if not kws:
        raise ValueError("Provide at least one keyword.")

    client = _get_client()
    gads = client.get_service("GoogleAdsService")
    svc = client.get_service("KeywordPlanIdeaService")

    request = client.get_type("GenerateKeywordHistoricalMetricsRequest")
    request.customer_id = _customer_id()
    request.keywords.extend(kws)
    request.language = gads.language_constant_path(str(language_id or DEFAULT_LANGUAGE_ID))
    request.geo_target_constants.append(
        gads.geo_target_constant_path(str(location_id or DEFAULT_LOCATION_ID))
    )
    request.keyword_plan_network = client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH

    response = svc.generate_keyword_historical_metrics(request=request)
    return [_metrics_dict(r.text, r.keyword_metrics) for r in response.results]


def suggest_geo_targets(location_name, locale="en", country_code="US"):
    """Resolve a location name -> geo target constant IDs (for location_id)."""
    client = _get_client()
    svc = client.get_service("GeoTargetConstantService")
    request = client.get_type("SuggestGeoTargetConstantsRequest")
    request.locale = locale
    request.country_code = country_code
    request.location_names.names.append(location_name)

    out = []
    for s in svc.suggest_geo_target_constants(request=request).geo_target_constant_suggestions:
        g = s.geo_target_constant
        out.append({
            "id": g.id,
            "name": g.name,
            "country_code": g.country_code,
            "target_type": g.target_type,
            "reach": s.reach,
        })
    return out


def test_connection():
    """A minimal real call to validate credentials. Returns (ok, detail)."""
    try:
        ideas = generate_keyword_ideas(seed_keywords=["test"], limit=1)
        return True, f"Credentials valid ({len(ideas)} sample idea received)."
    except Exception as ex:
        try:
            from google.ads.googleads.errors import GoogleAdsException
            if isinstance(ex, GoogleAdsException):
                return False, "; ".join(format_exception(ex))
        except Exception:
            pass
        return False, str(ex)
