"""Shared Google authentication for GSC and GA4.

Two supported modes, checked in order:

1. Service account — set ``GOOGLE_APPLICATION_CREDENTIALS`` to the path of a
   service-account JSON key. The service account's email must be added as a
   user in Search Console / GA4.
2. Local OAuth — set ``SEO_STACK_OAUTH_CLIENT`` to the path of an OAuth client
   secrets JSON ("Desktop app" type). On first run a browser window opens for
   consent; the refresh token is cached in ``~/.config/seo-stack-mcp/``.
"""

import hashlib
import json
import os
from pathlib import Path

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest

SCOPES = [
    "https://www.googleapis.com/auth/webmasters",
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/indexing",
]

# Set SEO_STACK_READONLY=1 to drop write scopes (sitemap submit/delete and
# indexing requests will then return 403 from Google).
if os.getenv("SEO_STACK_READONLY"):
    SCOPES = [
        "https://www.googleapis.com/auth/webmasters.readonly",
        "https://www.googleapis.com/auth/analytics.readonly",
    ]

# AdSense is opt-in via ADSENSE_ACCOUNT_ID. The scope is only requested when
# the source is enabled, so existing cached OAuth tokens keep working for
# users who don't use AdSense. If you enable AdSense after a first OAuth run,
# delete the cached token in ~/.config/seo-stack-mcp/ to re-consent.
if os.getenv("ADSENSE_ACCOUNT_ID"):
    SCOPES.append("https://www.googleapis.com/auth/adsense.readonly")

CONFIG_DIR = Path(
    os.getenv("SEO_STACK_CONFIG_DIR", Path.home() / ".config" / "seo-stack-mcp")
)

_cached_credentials = None


class GoogleAuthNotConfigured(Exception):
    """Raised when no Google credential source is configured."""


def google_configured() -> bool:
    return bool(
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        or os.getenv("SEO_STACK_OAUTH_CLIENT")
    )


def _token_cache_path(client_secrets_path: str) -> Path:
    digest = hashlib.sha256(client_secrets_path.encode()).hexdigest()[:12]
    return CONFIG_DIR / f"token-{digest}.json"


def _oauth_credentials(client_secrets_path: str) -> Credentials:
    cache = _token_cache_path(client_secrets_path)
    creds = None
    if cache.exists():
        # No scope override: the cached token keeps the scopes it was granted,
        # otherwise refresh would request scopes the token doesn't have.
        creds = Credentials.from_authorized_user_file(str(cache))
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(GoogleAuthRequest())
        cache.write_text(creds.to_json())
    if not creds or not creds.valid:
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, SCOPES)
        creds = flow.run_local_server(port=0)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(creds.to_json())
    return creds


def get_google_credentials():
    """Return refreshed Google credentials, or raise GoogleAuthNotConfigured."""
    global _cached_credentials
    if _cached_credentials is not None:
        creds = _cached_credentials
        if getattr(creds, "expired", False) and getattr(creds, "refresh_token", None):
            creds.refresh(GoogleAuthRequest())
        return creds

    sa_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if sa_path:
        _cached_credentials = service_account.Credentials.from_service_account_file(
            sa_path, scopes=SCOPES
        )
        return _cached_credentials

    client_secrets = os.getenv("SEO_STACK_OAUTH_CLIENT")
    if client_secrets:
        _cached_credentials = _oauth_credentials(client_secrets)
        return _cached_credentials

    raise GoogleAuthNotConfigured(
        "No Google credentials configured. Set GOOGLE_APPLICATION_CREDENTIALS "
        "(service-account key) or SEO_STACK_OAUTH_CLIENT (OAuth client secrets). "
        "See the README quickstart."
    )
