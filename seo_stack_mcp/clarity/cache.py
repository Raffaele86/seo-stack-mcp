"""SQLite TTL cache for Microsoft Clarity Data Export responses.

The cache lives under the seo-stack-mcp config directory
(``~/.config/seo-stack-mcp/`` or ``SEO_STACK_CONFIG_DIR``). Because Clarity
allows only 10 API requests per project per day, every response is cached
(default TTL 6 hours) and all URL-based tools share the same cached payload.
"""

import hashlib
import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("seo-stack-mcp.clarity")

CONFIG_DIR = Path(
    os.getenv("SEO_STACK_CONFIG_DIR", Path.home() / ".config" / "seo-stack-mcp")
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    cache_key   TEXT PRIMARY KEY,
    payload     TEXT NOT NULL,
    fetched_at  INTEGER NOT NULL,
    ttl_seconds INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cache_fetched ON cache(fetched_at);
"""

_conn: Optional[sqlite3.Connection] = None


def _db_path() -> str:
    return str(CONFIG_DIR / "clarity-cache.db")


def _conn_get() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        path = _db_path()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        _conn.executescript(_SCHEMA)
        log.info("Clarity cache DB at %s", path)
    return _conn


def make_key(project: str, days: int, dim1: Optional[str], dim2: Optional[str], dim3: Optional[str]) -> str:
    """Deterministic SHA256 hash of the (project, days, dim1..3) tuple."""
    blob = json.dumps(
        {"svc": "clarity", "project": project, "days": days, "d1": dim1, "d2": dim2, "d3": dim3},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def get(key: str) -> Optional[Any]:
    row = _conn_get().execute(
        "SELECT payload, fetched_at, ttl_seconds FROM cache WHERE cache_key = ?",
        (key,),
    ).fetchone()
    if row is None:
        return None
    payload, fetched_at, ttl = row
    if time.time() - fetched_at > ttl:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def set(key: str, payload: Any, ttl_seconds: int) -> None:
    _conn_get().execute(
        "INSERT OR REPLACE INTO cache (cache_key, payload, fetched_at, ttl_seconds) VALUES (?, ?, ?, ?)",
        (key, json.dumps(payload), int(time.time()), int(ttl_seconds)),
    )


def stats() -> dict:
    cur = _conn_get()
    total = cur.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
    now = int(time.time())
    valid = cur.execute(
        "SELECT COUNT(*) FROM cache WHERE fetched_at + ttl_seconds > ?",
        (now,),
    ).fetchone()[0]
    return {"total": total, "valid": valid, "expired": total - valid}


def purge_expired() -> int:
    now = int(time.time())
    cur = _conn_get().execute(
        "DELETE FROM cache WHERE fetched_at + ttl_seconds <= ?", (now,)
    )
    return cur.rowcount or 0
