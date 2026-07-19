"""Open PageRank — 1 MCP tool (domain authority via openpagerank.com).

Free tier: 10,000 API calls/hour. Responses are cached in a local SQLite
database (default TTL 30 days) to keep API usage minimal.
"""

import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

import httpx

log = logging.getLogger("seo-stack-mcp.pagerank")

API_URL = "https://openpagerank.com/api/v1.0/getPageRank"

CONFIG_DIR = Path(
    os.getenv("SEO_STACK_CONFIG_DIR", Path.home() / ".config" / "seo-stack-mcp")
)
CACHE_TTL = int(os.getenv("OPENPAGERANK_CACHE_TTL", "2592000"))  # 30 days

_conn: Optional[sqlite3.Connection] = None
_client: Optional[httpx.AsyncClient] = None


def _cache() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(
            CONFIG_DIR / "pagerank-cache.db", check_same_thread=False, isolation_level=None
        )
        _conn.executescript("""
            CREATE TABLE IF NOT EXISTS cache (
                domain TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                fetched_at INTEGER NOT NULL
            );
        """)
    return _conn


def _cache_get(domain: str) -> Optional[dict]:
    row = _cache().execute(
        "SELECT payload, fetched_at FROM cache WHERE domain = ?", (domain,)
    ).fetchone()
    if row is None:
        return None
    payload, fetched_at = row
    if time.time() - fetched_at > CACHE_TTL:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def _cache_set(domain: str, payload: dict) -> None:
    _cache().execute(
        "INSERT OR REPLACE INTO cache (domain, payload, fetched_at) VALUES (?, ?, ?)",
        (domain, json.dumps(payload), int(time.time())),
    )


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        api_key = os.getenv("OPENPAGERANK_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENPAGERANK_API_KEY is not set.")
        _client = httpx.AsyncClient(
            timeout=30.0,
            headers={"API-OPR": api_key, "Accept": "application/json"},
        )
    return _client


def _normalize_domain(d: str) -> str:
    """Strip protocol and path, keep the bare domain."""
    d = d.strip().lower()
    if "://" in d:
        d = d.split("://", 1)[1]
    d = d.split("/", 1)[0]
    if d.startswith("www."):
        d = d[4:]
    return d


def register(mcp):
    """Register the Open PageRank tool on the given FastMCP server."""

    @mcp.tool()
    async def pagerank_score(domains: list[str]) -> str:
        """Domain authority score (0-10) via Open PageRank.

        domains: list of domains (max 100 per call). Uses a local cache
        (TTL 30 days) to minimize API calls; the Open PageRank free tier
        allows 10,000 calls/hour.

        Output: table with domain, page_rank_decimal (0-10), global rank.
        """
        if not domains:
            return "Error: empty domain list."

        norm = [_normalize_domain(d) for d in domains[:100]]
        norm = [d for d in norm if d]

        results: dict[str, dict] = {}
        misses: list[str] = []
        for d in norm:
            cached = _cache_get(d)
            if cached is not None:
                results[d] = cached
            else:
                misses.append(d)

        if misses:
            try:
                client = await _get_client()
                params = [("domains[]", d) for d in misses]
                r = await client.get(API_URL, params=params)
                if r.status_code != 200:
                    return f"Open PageRank API error {r.status_code}: {r.text[:200]}"
                data = r.json()
                if data.get("status_code") != 200:
                    return f"Open PageRank error: {data.get('error', 'unknown')}"
                for entry in data.get("response", []):
                    d = entry.get("domain", "")
                    if d:
                        results[d] = entry
                        _cache_set(d, entry)
            except (httpx.RequestError, RuntimeError) as e:
                return f"Open PageRank error: {e}"

        rows = []
        for d in norm:
            e = results.get(d)
            if not e or e.get("status_code") != 200:
                err = e.get("error", "no data") if e else "no data"
                rows.append([d, "—", "—", err])
            else:
                rows.append([
                    d,
                    f"{e.get('page_rank_decimal', 0):.2f}",
                    f"{e.get('rank', '—')}",
                    "ok",
                ])

        headers = ["Domain", "PR (0-10)", "Global rank", "Status"]
        all_rows = [headers] + rows
        widths = [max(len(str(r[i])) for r in all_rows) for i in range(len(headers))]
        out = ["=== Open PageRank ===", ""]
        out.append(" | ".join(str(h).ljust(w) for h, w in zip(headers, widths)))
        out.append("-+-".join("-" * w for w in widths))
        for row in rows:
            out.append(" | ".join(str(v).ljust(w) for v, w in zip(row, widths)))
        n_cached = len(norm) - len(misses)
        out.append("")
        out.append(f"({len(misses)} API calls used, {n_cached} cache hits)")
        return "\n".join(out)

    log.info("registered 1 Open PageRank tool")
