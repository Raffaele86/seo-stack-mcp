"""Daily quota tracker for the Microsoft Clarity Data Export API.

Clarity enforces a hard limit of 10 requests/day/project (resets at UTC
midnight). This local counter blocks at ``CLARITY_DAILY_LIMIT`` (default 9)
so we always stop one call short of the API-side 429.

State is persisted to a JSON file under the seo-stack-mcp config directory
(``~/.config/seo-stack-mcp/`` or ``SEO_STACK_CONFIG_DIR``), keyed by project:
{project: {YYYY-MM-DD: count}}.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("seo-stack-mcp.clarity")

CONFIG_DIR = Path(
    os.getenv("SEO_STACK_CONFIG_DIR", Path.home() / ".config" / "seo-stack-mcp")
)

_lock = threading.Lock()


def _path() -> str:
    return str(CONFIG_DIR / "clarity-quota.json")


def _daily_limit() -> int:
    return int(os.getenv("CLARITY_DAILY_LIMIT", "9"))


def _warning_threshold() -> int:
    return int(os.getenv("CLARITY_WARNING_THRESHOLD", "7"))


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load() -> dict:
    p = _path()
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    if not os.path.exists(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Quota file corrupted (%s), resetting", e)
        return {}


def _save(data: dict) -> None:
    p = _path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, p)


def _gc(data: dict, keep_days: int = 7) -> None:
    """Drop daily buckets older than keep_days — keeps the quota file tiny."""
    today = datetime.now(timezone.utc).date()
    for project, buckets in list(data.items()):
        if not isinstance(buckets, dict):
            data[project] = {}
            continue
        for d in list(buckets.keys()):
            try:
                bucket_date = datetime.strptime(d, "%Y-%m-%d").date()
            except ValueError:
                buckets.pop(d, None)
                continue
            if (today - bucket_date).days > keep_days:
                buckets.pop(d, None)


def used(project: str) -> int:
    with _lock:
        data = _load()
        return int(data.get(project, {}).get(_today(), 0))


def remaining(project: str) -> int:
    return max(0, _daily_limit() - used(project))


def is_blocked(project: str) -> bool:
    return used(project) >= _daily_limit()


def is_warning(project: str) -> bool:
    return used(project) >= _warning_threshold()


def record_call(project: str) -> int:
    """Increment today's counter for the project and return the new value."""
    with _lock:
        data = _load()
        bucket = data.setdefault(project, {})
        today = _today()
        bucket[today] = int(bucket.get(today, 0)) + 1
        _gc(data)
        _save(data)
        return bucket[today]


def status() -> dict:
    """Snapshot of all projects with usage today / remaining / limit."""
    with _lock:
        data = _load()
    today = _today()
    out = {
        "date_utc": today,
        "daily_limit": _daily_limit(),
        "warning_threshold": _warning_threshold(),
        "projects": {},
    }
    for project, buckets in data.items():
        u = int(buckets.get(today, 0)) if isinstance(buckets, dict) else 0
        out["projects"][project] = {
            "used": u,
            "remaining": max(0, _daily_limit() - u),
            "blocked": u >= _daily_limit(),
            "warning": u >= _warning_threshold(),
        }
    return out
