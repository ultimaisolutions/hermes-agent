"""Signal AI creator discovery tools.

Provides four tools for niche-based Instagram creator discovery:
- get_niche_clusters: Fetch cached niche clusters from Neon
- get_rotation_status: Check which niches need searching next
- search_instagram_creators: Search Instagram via ScrapeCreators API
- log_rotation: Record search rotation and upsert discovered creators
"""

import base64
import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schemas (OpenAI function-calling format)
# ---------------------------------------------------------------------------

GET_NICHE_CLUSTERS_SCHEMA: Dict[str, Any] = {
    "name": "get_niche_clusters",
    "description": "Fetch the current niche clusters from the cache. Returns niche names and their keywords.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

GET_ROTATION_STATUS_SCHEMA: Dict[str, Any] = {
    "name": "get_rotation_status",
    "description": "Check the rotation status for all niches. Shows which niches need searching next.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

SEARCH_INSTAGRAM_CREATORS_SCHEMA: Dict[str, Any] = {
    "name": "search_instagram_creators",
    "description": "Search Instagram reels for creators matching a keyword via ScrapeCreators API.",
    "parameters": {
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "The keyword to search for.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of unique creators to return.",
                "default": 10,
            },
        },
        "required": ["keyword"],
    },
}

LOG_ROTATION_SCHEMA: Dict[str, Any] = {
    "name": "log_rotation",
    "description": "Log a completed search rotation and upsert discovered creators into the database.",
    "parameters": {
        "type": "object",
        "properties": {
            "niche_name": {
                "type": "string",
                "description": "Name of the niche that was searched.",
            },
            "keywords_used": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Keywords that were used in the search.",
            },
            "creators_found": {
                "type": "integer",
                "description": "Number of unique creators found.",
            },
            "credits_spent": {
                "type": "integer",
                "description": "Number of API credits spent.",
            },
            "creators": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "username": {"type": "string"},
                        "follower_count": {"type": "integer"},
                        "is_verified": {"type": "boolean"},
                    },
                },
                "description": "List of creator objects to upsert.",
            },
        },
        "required": [
            "niche_name",
            "keywords_used",
            "creators_found",
            "credits_spent",
            "creators",
        ],
    },
}

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _check_neon() -> bool:
    """Return True if SIGNAL_DATABASE_URL is set."""
    return bool(os.environ.get("SIGNAL_DATABASE_URL"))


def _check_scrape() -> bool:
    """Return True if SCRAPECREATORS_API_KEY is set."""
    return bool(os.environ.get("SCRAPECREATORS_API_KEY"))


def _neon_query(sql: str, params: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Execute a SQL query against the Neon HTTP API.

    Reads SIGNAL_DATABASE_URL, parses it to extract host/user/password,
    POSTs to https://{host}/sql, and returns the parsed JSON response.
    """
    db_url = os.environ.get("SIGNAL_DATABASE_URL", "")
    parsed = urlparse(db_url)

    host = parsed.hostname or ""
    user = parsed.username or ""
    password = parsed.password or ""

    credentials = base64.b64encode(f"{user}:{password}".encode()).decode()

    body = json.dumps({"query": sql, "params": params or []}).encode("utf-8")

    req = urllib.request.Request(
        f"https://{host}/sql",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {credentials}",
            "Neon-Connection-String": db_url,
        },
        method="POST",
    )

    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def get_niche_clusters() -> str:
    """Fetch current niche clusters from the database cache.

    Returns a JSON string with niche_count and niches list,
    or an error object if env is missing or no cached data exists.
    """
    db_url = os.environ.get("SIGNAL_DATABASE_URL")
    if not db_url:
        return json.dumps({"error": "SIGNAL_DATABASE_URL is not set"})

    try:
        result = _neon_query(
            "SELECT value FROM niche_cluster_cache WHERE key = 'current' LIMIT 1"
        )
        rows = result.get("rows", [])
        if not rows:
            return json.dumps({"error": "No niche clusters found in cache"})

        raw = rows[0][0]
        cluster_data = json.loads(raw) if isinstance(raw, str) else raw

        # Handle both dict and list formats
        if isinstance(cluster_data, dict):
            clusters = cluster_data.get("clusters", [])
        elif isinstance(cluster_data, list):
            clusters = cluster_data
        else:
            clusters = []

        niches = [
            {
                "name": c["name"],
                "keywords": c.get("keywords", [])[:5],
            }
            for c in clusters
        ]

        return json.dumps({"niche_count": len(niches), "niches": niches})
    except Exception as exc:
        logger.exception("get_niche_clusters failed: %s", exc)
        return json.dumps({"error": str(exc)})


def get_rotation_status() -> str:
    """Check rotation status for all niches.

    Calls get_niche_clusters() first, then queries rotation_tracker
    to determine which niches were searched most recently.
    Returns niches sorted: never-searched first, then oldest first.
    """
    clusters_raw = get_niche_clusters()
    clusters_result = json.loads(clusters_raw)

    if "error" in clusters_result:
        return json.dumps({"error": clusters_result["error"]})

    niches = clusters_result.get("niches", [])
    niche_names = [n["name"] for n in niches]

    if not niche_names:
        return json.dumps({"niches_total": 0, "rotation": []})

    try:
        placeholders = ", ".join(f"'{name}'" for name in niche_names)
        sql = (
            f"SELECT niche_name, MAX(searched_at) FROM rotation_tracker "
            f"WHERE niche_name IN ({placeholders}) GROUP BY niche_name"
        )
        result = _neon_query(sql)
        rows = result.get("rows", [])

        last_searched_map: Dict[str, Optional[str]] = {}
        for row in rows:
            last_searched_map[row[0]] = row[1]

        now = datetime.now(timezone.utc)
        rotation = []
        for name in niche_names:
            last_searched = last_searched_map.get(name)
            days_ago = None
            if last_searched:
                searched_dt = datetime.fromisoformat(
                    last_searched.replace("Z", "+00:00")
                )
                days_ago = (now - searched_dt).days
            rotation.append({
                "niche": name,
                "last_searched": last_searched,
                "days_ago": days_ago,
            })

        # Sort: never-searched first (None), then oldest first (largest days_ago)
        rotation.sort(
            key=lambda r: (
                0 if r["last_searched"] is None else 1,
                -(r["days_ago"] or 0),
            )
        )

        return json.dumps({"niches_total": len(rotation), "rotation": rotation})
    except Exception as exc:
        logger.exception("get_rotation_status failed: %s", exc)
        return json.dumps({"error": str(exc)})


def search_instagram_creators(keyword: str, max_results: int = 10) -> str:
    """Search Instagram reels for creators matching a keyword.

    Uses the ScrapeCreators API to find creators. Deduplicates by username
    and caps results at max_results.
    """
    api_key = os.environ.get("SCRAPECREATORS_API_KEY")
    if not api_key:
        return json.dumps({"error": "SCRAPECREATORS_API_KEY is not set"})

    try:
        url = (
            f"https://api.scrapecreators.com/v2/instagram/reels/search"
            f"?keyword={urllib.parse.quote(keyword)}"
        )
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
            method="GET",
        )

        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())

        reels = data.get("reels", [])
        credits_remaining = data.get("credits_remaining", 0)

        # Deduplicate by username, preserving order
        seen_usernames: set = set()
        creators: List[Dict[str, Any]] = []
        for reel in reels:
            owner = reel.get("owner", {})
            username = owner.get("username", "")
            if username in seen_usernames:
                continue
            seen_usernames.add(username)
            creators.append({
                "username": username,
                "full_name": owner.get("full_name", ""),
                "follower_count": owner.get("follower_count", 0),
                "post_count": owner.get("post_count", 0),
                "is_verified": owner.get("is_verified", False),
                "profile_url": f"https://instagram.com/{username}",
                "discovered_via": keyword,
            })
            if len(creators) >= max_results:
                break

        return json.dumps({
            "keyword": keyword,
            "creators_found": len(creators),
            "credits_remaining": credits_remaining,
            "creators": creators,
        })
    except Exception as exc:
        logger.exception("search_instagram_creators failed: %s", exc)
        return json.dumps({"error": str(exc)})


def log_rotation(
    niche_name: str,
    keywords_used: List[str],
    creators_found: int,
    credits_spent: int,
    creators: List[Dict[str, Any]],
) -> str:
    """Log a completed search rotation and upsert creators.

    Makes 1 call for rotation_tracker INSERT, then 1 call per creator
    for upsert (INSERT ... ON CONFLICT DO UPDATE).
    """
    db_url = os.environ.get("SIGNAL_DATABASE_URL")
    if not db_url:
        return json.dumps({"error": "SIGNAL_DATABASE_URL is not set"})

    try:
        # Insert rotation record
        _neon_query(
            "INSERT INTO rotation_tracker (niche_name, keywords_used, creators_found, credits_spent, searched_at) "
            "VALUES ($1, $2, $3, $4, NOW())",
            [niche_name, json.dumps(keywords_used), creators_found, credits_spent],
        )

        # Upsert each creator individually
        for creator in creators:
            _neon_query(
                "INSERT INTO creators (username, follower_count, is_verified, niche_name, discovered_at) "
                "VALUES ($1, $2, $3, $4, NOW()) "
                "ON CONFLICT (username) DO UPDATE SET "
                "follower_count = $2, is_verified = $3, niche_name = $4, updated_at = NOW()",
                [
                    creator["username"],
                    creator["follower_count"],
                    creator["is_verified"],
                    niche_name,
                ],
            )

        return json.dumps({
            "status": "logged",
            "niche_name": niche_name,
            "creators_upserted": len(creators),
        })
    except Exception as exc:
        logger.exception("log_rotation failed: %s", exc)
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# Registry registration
# ---------------------------------------------------------------------------

from tools.registry import registry

registry.register(
    name="get_niche_clusters",
    toolset="signal_ai",
    schema=GET_NICHE_CLUSTERS_SCHEMA,
    handler=lambda args, **kw: get_niche_clusters(),
    check_fn=_check_neon,
    requires_env=["SIGNAL_DATABASE_URL"],
)

registry.register(
    name="get_rotation_status",
    toolset="signal_ai",
    schema=GET_ROTATION_STATUS_SCHEMA,
    handler=lambda args, **kw: get_rotation_status(),
    check_fn=_check_neon,
    requires_env=["SIGNAL_DATABASE_URL"],
)

registry.register(
    name="search_instagram_creators",
    toolset="signal_ai",
    schema=SEARCH_INSTAGRAM_CREATORS_SCHEMA,
    handler=lambda args, **kw: search_instagram_creators(
        keyword=args["keyword"],
        max_results=args.get("max_results", 10),
    ),
    check_fn=_check_scrape,
    requires_env=["SCRAPECREATORS_API_KEY"],
)

registry.register(
    name="log_rotation",
    toolset="signal_ai",
    schema=LOG_ROTATION_SCHEMA,
    handler=lambda args, **kw: log_rotation(
        niche_name=args["niche_name"],
        keywords_used=args["keywords_used"],
        creators_found=args["creators_found"],
        credits_spent=args["credits_spent"],
        creators=args["creators"],
    ),
    check_fn=_check_neon,
    requires_env=["SIGNAL_DATABASE_URL"],
)
