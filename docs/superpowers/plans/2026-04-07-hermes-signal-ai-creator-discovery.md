# Hermes Agent — Signal AI Creator Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fork NousResearch/hermes-agent, add 4 custom tools for Signal AI creator discovery with DB-backed niche rotation, and deploy as a persistent Docker service on Railway.

**Architecture:** Fork the upstream repo, add a single tool module (`tools/signal_creators.py`) with 4 tools that use Neon's HTTP SQL API and ScrapeCreators REST API. Register tools via Hermes' self-registering pattern. Deploy to Railway's `stellar-rebirth` project as a new persistent service with a volume at `/opt/data`.

**Tech Stack:** Python 3.11, Hermes Agent framework, Neon HTTP SQL API, ScrapeCreators API, OpenRouter (LLM), Telegram Bot API, Docker, Railway.

**Design Spec:** `docs/superpowers/specs/2026-04-07-hermes-signal-ai-creator-discovery-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `tools/signal_creators.py` | Create | All 4 tools: get_niche_clusters, get_rotation_status, search_instagram_creators, log_rotation + schemas + registration |
| `model_tools.py` | Edit | Add `"tools.signal_creators"` to `_modules` list in `_discover_tools()` |
| `toolsets.py` | Edit | Add `signal_ai` toolset to `TOOLSETS` dict + add 4 tool names to `_HERMES_CORE_TOOLS` |
| `skills/marketing/signal-creator-discovery/SKILL.md` | Create | Agent skill file teaching the discovery + rotation pipeline |
| `docker-compose.yml` | Create | Local dev compose file |
| `.env.signal-ai.example` | Create | Signal AI env var template |
| `config/signal-ai-config.yaml` | Create | Hermes config template for OpenRouter + signal_ai toolset |
| `tests/test_signal_creators.py` | Create | Unit tests for all 4 tool functions |

---

## Task 1: Fork and Clone the Repository

**Files:** None (git operations only)

- [ ] **Step 1: Fork NousResearch/hermes-agent**

```bash
gh repo fork NousResearch/hermes-agent --clone=false
```

Expected: Fork created at `<your-username>/hermes-agent` on GitHub.

- [ ] **Step 2: Clone the fork with submodules**

```bash
cd "F:/Ultim AI Solutions"
rm -rf hermes-agent/CLAUDE_CODE_PROMPT.md hermes-agent/SETUP_INSTRUCTIONS.md hermes-agent/SKILL.md hermes-agent/tools_signal_creators.py hermes-agent/docs
git clone --recurse-submodules https://github.com/$(gh api user --jq .login)/hermes-agent.git hermes-agent-fork
```

Note: The existing `hermes-agent` directory contains prep files. Clone the fork to `hermes-agent-fork`, then move contents or work from the fork directory. Alternatively, back up the prep files, delete the directory, and clone directly:

```bash
mkdir -p "F:/Ultim AI Solutions/hermes-agent-backup"
cp "F:/Ultim AI Solutions/hermes-agent/"* "F:/Ultim AI Solutions/hermes-agent-backup/"
rm -rf "F:/Ultim AI Solutions/hermes-agent"
git clone --recurse-submodules https://github.com/$(gh api user --jq .login)/hermes-agent.git "F:/Ultim AI Solutions/hermes-agent"
```

Expected: Full repo cloned with git history. Verify with `ls tools/registry.py model_tools.py toolsets.py`.

- [ ] **Step 3: Create a feature branch**

```bash
cd "F:/Ultim AI Solutions/hermes-agent"
git checkout -b feat/signal-ai-creator-discovery
```

- [ ] **Step 4: Copy prep files into the repo**

```bash
cp "F:/Ultim AI Solutions/hermes-agent-backup/docs" "F:/Ultim AI Solutions/hermes-agent/" -r 2>/dev/null || true
```

Move the design spec back:
```bash
mkdir -p docs/superpowers/specs docs/superpowers/plans
cp "F:/Ultim AI Solutions/hermes-agent-backup/docs/superpowers/specs/2026-04-07-hermes-signal-ai-creator-discovery-design.md" docs/superpowers/specs/
```

- [ ] **Step 5: Commit baseline**

```bash
git add docs/
git commit -m "docs: add Signal AI creator discovery design spec"
```

---

## Task 2: Write Unit Tests for Neon HTTP Helper

**Files:**
- Create: `tests/test_signal_creators.py`

The 4 tools all use Neon's HTTP SQL API via `urllib`. We'll extract a shared helper `_neon_query(sql, params)` and test it, plus test each tool function in isolation by mocking the HTTP calls.

- [ ] **Step 1: Write test file with helper tests**

Create `tests/test_signal_creators.py`:

```python
"""Tests for Signal AI creator discovery tools."""

import json
import os
from unittest.mock import patch, MagicMock
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def signal_env(monkeypatch):
    """Set required env vars for all tests."""
    monkeypatch.setenv(
        "SIGNAL_DATABASE_URL",
        "postgresql://testuser:testpass@ep-test-host.us-east-1.aws.neon.tech/testdb?sslmode=require",
    )
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", "test-api-key-123")


def _make_neon_response(rows, fields=None):
    """Build a mock Neon HTTP API response body."""
    body = json.dumps({"rows": rows, "fields": fields or []}).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _make_scrape_response(reels, credits_remaining=24500):
    """Build a mock ScrapeCreators API response body."""
    body = json.dumps({
        "success": True,
        "reels": reels,
        "credits_remaining": credits_remaining,
    }).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ---------------------------------------------------------------------------
# get_niche_clusters
# ---------------------------------------------------------------------------

class TestGetNicheClusters:
    @patch("urllib.request.urlopen")
    def test_returns_niches_from_dict_format(self, mock_urlopen):
        cluster_data = {
            "clusters": [
                {"name": "fitness", "keywords": ["workout", "gym", "health", "diet", "protein", "cardio"]},
                {"name": "crypto", "keywords": ["bitcoin", "defi"]},
            ]
        }
        mock_urlopen.return_value = _make_neon_response([[json.dumps(cluster_data)]])

        from tools.signal_creators import get_niche_clusters

        result = json.loads(get_niche_clusters())
        assert result["niche_count"] == 2
        assert result["niches"][0]["name"] == "fitness"
        assert len(result["niches"][0]["keywords"]) == 5  # capped at 5

    @patch("urllib.request.urlopen")
    def test_returns_niches_from_list_format(self, mock_urlopen):
        cluster_data = [
            {"name": "ai tools", "keywords": ["chatgpt", "automation"]},
        ]
        mock_urlopen.return_value = _make_neon_response([[json.dumps(cluster_data)]])

        from tools.signal_creators import get_niche_clusters

        result = json.loads(get_niche_clusters())
        assert result["niche_count"] == 1
        assert result["niches"][0]["name"] == "ai tools"

    @patch("urllib.request.urlopen")
    def test_empty_cache_returns_error(self, mock_urlopen):
        mock_urlopen.return_value = _make_neon_response([])

        from tools.signal_creators import get_niche_clusters

        result = json.loads(get_niche_clusters())
        assert "error" in result
        assert "No niche clusters" in result["error"]

    def test_missing_env_returns_error(self, monkeypatch):
        monkeypatch.delenv("SIGNAL_DATABASE_URL")

        from tools.signal_creators import get_niche_clusters

        result = json.loads(get_niche_clusters())
        assert "error" in result
        assert "SIGNAL_DATABASE_URL" in result["error"]


# ---------------------------------------------------------------------------
# get_rotation_status
# ---------------------------------------------------------------------------

class TestGetRotationStatus:
    @patch("urllib.request.urlopen")
    def test_returns_sorted_rotation(self, mock_urlopen):
        # First call: get niches
        niches_resp = _make_neon_response([[json.dumps({
            "clusters": [
                {"name": "fitness", "keywords": ["workout"]},
                {"name": "crypto", "keywords": ["bitcoin"]},
                {"name": "ai tools", "keywords": ["chatgpt"]},
            ]
        })]])
        # Second call: get rotation history
        rotation_resp = _make_neon_response([
            ["fitness", "2026-04-05T09:00:00Z"],
            ["crypto", "2026-04-01T09:00:00Z"],
        ])
        mock_urlopen.side_effect = [niches_resp, rotation_resp]

        from tools.signal_creators import get_rotation_status

        result = json.loads(get_rotation_status())
        assert result["niches_total"] == 3
        # ai tools has never been searched → should be first
        assert result["rotation"][0]["niche"] == "ai tools"
        assert result["rotation"][0]["last_searched"] is None

    @patch("urllib.request.urlopen")
    def test_no_rotation_history(self, mock_urlopen):
        niches_resp = _make_neon_response([[json.dumps({
            "clusters": [{"name": "fitness", "keywords": []}]
        })]])
        rotation_resp = _make_neon_response([])
        mock_urlopen.side_effect = [niches_resp, rotation_resp]

        from tools.signal_creators import get_rotation_status

        result = json.loads(get_rotation_status())
        assert result["niches_total"] == 1
        assert result["rotation"][0]["last_searched"] is None


# ---------------------------------------------------------------------------
# search_instagram_creators
# ---------------------------------------------------------------------------

class TestSearchInstagramCreators:
    @patch("urllib.request.urlopen")
    def test_returns_deduplicated_creators(self, mock_urlopen):
        reels = [
            {
                "owner": {"username": "creator1", "full_name": "Creator One", "follower_count": 5000, "post_count": 100, "is_verified": False},
                "url": "https://instagram.com/reel/1",
                "video_play_count": 1000,
                "like_count": 50,
                "comment_count": 5,
            },
            {
                "owner": {"username": "creator1", "full_name": "Creator One", "follower_count": 5000, "post_count": 100, "is_verified": False},
                "url": "https://instagram.com/reel/2",
                "video_play_count": 2000,
                "like_count": 100,
                "comment_count": 10,
            },
            {
                "owner": {"username": "creator2", "full_name": "Creator Two", "follower_count": 10000, "post_count": 200, "is_verified": True},
                "url": "https://instagram.com/reel/3",
                "video_play_count": 5000,
                "like_count": 300,
                "comment_count": 20,
            },
        ]
        mock_urlopen.return_value = _make_scrape_response(reels)

        from tools.signal_creators import search_instagram_creators

        result = json.loads(search_instagram_creators("fitness"))
        assert result["creators_found"] == 2  # deduplicated
        assert result["creators"][0]["username"] == "creator1"
        assert result["creators"][1]["username"] == "creator2"
        assert result["credits_remaining"] == 24500

    @patch("urllib.request.urlopen")
    def test_respects_max_results(self, mock_urlopen):
        reels = [
            {"owner": {"username": f"creator{i}", "full_name": "", "follower_count": 100, "post_count": 10, "is_verified": False}, "url": f"https://instagram.com/reel/{i}", "video_play_count": 100, "like_count": 10, "comment_count": 1}
            for i in range(20)
        ]
        mock_urlopen.return_value = _make_scrape_response(reels)

        from tools.signal_creators import search_instagram_creators

        result = json.loads(search_instagram_creators("fitness", max_results=3))
        assert result["creators_found"] == 3

    def test_missing_api_key_returns_error(self, monkeypatch):
        monkeypatch.delenv("SCRAPECREATORS_API_KEY")

        from tools.signal_creators import search_instagram_creators

        result = json.loads(search_instagram_creators("fitness"))
        assert "error" in result
        assert "SCRAPECREATORS_API_KEY" in result["error"]


# ---------------------------------------------------------------------------
# log_rotation
# ---------------------------------------------------------------------------

class TestLogRotation:
    @patch("urllib.request.urlopen")
    def test_logs_rotation_and_upserts_creators(self, mock_urlopen):
        # Both Neon calls return success
        success_resp_1 = _make_neon_response([])
        success_resp_2 = _make_neon_response([])
        mock_urlopen.side_effect = [success_resp_1, success_resp_2]

        from tools.signal_creators import log_rotation

        result = json.loads(log_rotation(
            niche_name="fitness",
            keywords_used=["workout", "gym"],
            creators_found=2,
            credits_spent=2,
            creators=[
                {"username": "fitguru", "follower_count": 5000, "is_verified": False},
                {"username": "gymrat", "follower_count": 12000, "is_verified": True},
            ],
        ))
        assert result["status"] == "logged"
        assert result["niche_name"] == "fitness"
        assert result["creators_upserted"] == 2

        # Verify Neon was called twice (rotation insert + creator upsert)
        assert mock_urlopen.call_count == 2

    def test_missing_env_returns_error(self, monkeypatch):
        monkeypatch.delenv("SIGNAL_DATABASE_URL")

        from tools.signal_creators import log_rotation

        result = json.loads(log_rotation(
            niche_name="fitness",
            keywords_used=["workout"],
            creators_found=0,
            credits_spent=1,
            creators=[],
        ))
        assert "error" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "F:/Ultim AI Solutions/hermes-agent"
python -m pytest tests/test_signal_creators.py -v 2>&1 | head -40
```

Expected: All tests FAIL with `ModuleNotFoundError: No module named 'tools.signal_creators'`

- [ ] **Step 3: Commit test file**

```bash
git add tests/test_signal_creators.py
git commit -m "test: add unit tests for Signal AI creator discovery tools (RED)"
```

---

## Task 3: Implement the Tool Module

**Files:**
- Create: `tools/signal_creators.py`

This is the core implementation — all 4 tools in one module with shared Neon HTTP helper.

- [ ] **Step 1: Create `tools/signal_creators.py`**

```python
#!/usr/bin/env python3
"""
Signal AI Creator Discovery Tools

Four tools for the Signal AI marketing pipeline:
1. get_niche_clusters     — reads niche clusters from NeonDB
2. get_rotation_status    — checks which niches were searched recently
3. search_instagram_creators — searches ScrapeCreators for creators by keyword
4. log_rotation           — logs a completed search to the rotation tracker

Requires:
  SCRAPECREATORS_API_KEY — from https://app.scrapecreators.com
  SIGNAL_DATABASE_URL    — NeonDB connection string
"""

from __future__ import annotations

import base64
import json
import logging
import os
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared: Neon HTTP SQL helper
# ---------------------------------------------------------------------------

def _neon_query(sql: str, params: list[Any] | None = None) -> dict:
    """
    Execute a SQL query against Neon's serverless HTTP API.
    Returns the parsed JSON response with 'rows' and 'fields' keys.
    Raises ValueError if SIGNAL_DATABASE_URL is not set.
    """
    db_url = os.getenv("SIGNAL_DATABASE_URL", "")
    if not db_url:
        raise ValueError("SIGNAL_DATABASE_URL not configured")

    parsed = urlparse(db_url)
    neon_host = parsed.hostname
    neon_user = parsed.username
    neon_pass = parsed.password

    sql_url = f"https://{neon_host}/sql"
    payload = json.dumps({"query": sql, "params": params or []}).encode("utf-8")
    credentials = base64.b64encode(f"{neon_user}:{neon_pass}".encode()).decode()

    req = urllib.request.Request(
        sql_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {credentials}",
            "Neon-Connection-String": db_url,
        },
        method="POST",
    )

    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        return json.loads(resp.read().decode())


# ---------------------------------------------------------------------------
# Availability checks
# ---------------------------------------------------------------------------

def _check_scrapecreators() -> bool:
    return bool(os.getenv("SCRAPECREATORS_API_KEY"))


def _check_neon() -> bool:
    return bool(os.getenv("SIGNAL_DATABASE_URL"))


# ---------------------------------------------------------------------------
# Tool 1: get_niche_clusters
# ---------------------------------------------------------------------------

def get_niche_clusters() -> str:
    """Fetch current niche clusters from Signal AI's NeonDB cache."""
    db_url = os.getenv("SIGNAL_DATABASE_URL", "")
    if not db_url:
        return json.dumps({"error": "SIGNAL_DATABASE_URL not configured"})

    try:
        result = _neon_query(
            "SELECT value FROM niche_cluster_cache WHERE key = 'current' LIMIT 1"
        )
        rows = result.get("rows", [])
        if not rows:
            return json.dumps({
                "error": "No niche clusters found in cache",
                "hint": "Run the clustering job first",
            })

        raw = rows[0][0] if isinstance(rows[0], list) else rows[0].get("value", rows[0])
        cluster_data = json.loads(raw) if isinstance(raw, str) else raw

        niches: list[dict] = []
        items: list = []
        if isinstance(cluster_data, dict):
            items = cluster_data.get("clusters", cluster_data.get("niches", []))
        elif isinstance(cluster_data, list):
            items = cluster_data

        for item in items:
            if isinstance(item, dict):
                niches.append({
                    "name": item.get("name", item.get("label", item.get("niche", str(item)))),
                    "keywords": item.get("keywords", item.get("terms", []))[:5],
                })
            elif isinstance(item, str):
                niches.append({"name": item, "keywords": []})

        return json.dumps({"niche_count": len(niches), "niches": niches}, indent=2)

    except Exception as e:
        logger.exception("Failed to fetch niche clusters from NeonDB")
        return json.dumps({"error": f"NeonDB query failed: {e}"})


# ---------------------------------------------------------------------------
# Tool 2: get_rotation_status
# ---------------------------------------------------------------------------

def get_rotation_status() -> str:
    """Check which niches have been searched recently and which are overdue."""
    db_url = os.getenv("SIGNAL_DATABASE_URL", "")
    if not db_url:
        return json.dumps({"error": "SIGNAL_DATABASE_URL not configured"})

    try:
        # Step 1: Get all current niches
        niches_result = json.loads(get_niche_clusters())
        if "error" in niches_result:
            return json.dumps(niches_result)

        niche_names = [n["name"] for n in niches_result.get("niches", [])]
        if not niche_names:
            return json.dumps({"error": "No niches found"})

        # Step 2: Get latest search date per niche from rotation_tracker
        placeholders = ", ".join(f"${i+1}" for i in range(len(niche_names)))
        sql = f"""
            SELECT niche_name, MAX(searched_at) AS last_searched
            FROM rotation_tracker
            WHERE niche_name IN ({placeholders})
            GROUP BY niche_name
        """
        result = _neon_query(sql, niche_names)
        rows = result.get("rows", [])

        last_searched_map: dict[str, str] = {}
        for row in rows:
            if isinstance(row, list):
                last_searched_map[row[0]] = row[1]
            elif isinstance(row, dict):
                last_searched_map[row["niche_name"]] = row["last_searched"]

        # Step 3: Build rotation list sorted by least recently searched
        now = datetime.now(timezone.utc)
        rotation: list[dict] = []
        for name in niche_names:
            last = last_searched_map.get(name)
            days_ago = None
            if last:
                last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
                days_ago = (now - last_dt).days
            rotation.append({
                "niche": name,
                "last_searched": last,
                "days_ago": days_ago,
            })

        rotation.sort(key=lambda x: (x["days_ago"] is not None, x["days_ago"] or 0))

        return json.dumps({
            "niches_total": len(niche_names),
            "rotation": rotation,
        }, indent=2)

    except Exception as e:
        logger.exception("Failed to get rotation status")
        return json.dumps({"error": f"Rotation status query failed: {e}"})


# ---------------------------------------------------------------------------
# Tool 3: search_instagram_creators
# ---------------------------------------------------------------------------

def search_instagram_creators(keyword: str, max_results: int = 10) -> str:
    """Search ScrapeCreators for Instagram reels matching a keyword."""
    api_key = os.getenv("SCRAPECREATORS_API_KEY", "")
    if not api_key:
        return json.dumps({"error": "SCRAPECREATORS_API_KEY not configured"})

    try:
        params = urllib.parse.urlencode({"keyword": keyword})
        url = f"https://api.scrapecreators.com/v2/instagram/reels/search?{params}"

        req = urllib.request.Request(
            url,
            headers={"x-api-key": api_key, "Accept": "application/json"},
            method="GET",
        )

        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            data = json.loads(resp.read().decode())

        if not data.get("success"):
            return json.dumps({"error": "ScrapeCreators API returned failure", "data": data})

        reels = data.get("reels", [])
        credits_remaining = data.get("credits_remaining", "unknown")

        seen: set[str] = set()
        creators: list[dict] = []
        for reel in reels:
            owner = reel.get("owner", {})
            username = owner.get("username", "")
            if not username or username in seen:
                continue
            seen.add(username)

            creators.append({
                "username": username,
                "full_name": owner.get("full_name", ""),
                "follower_count": owner.get("follower_count", 0),
                "post_count": owner.get("post_count", 0),
                "is_verified": owner.get("is_verified", False),
                "profile_url": f"https://instagram.com/{username}",
                "discovered_via": {
                    "reel_url": reel.get("url", ""),
                    "play_count": reel.get("video_play_count", 0),
                    "like_count": reel.get("like_count", 0),
                    "comment_count": reel.get("comment_count", 0),
                },
            })

            if len(creators) >= max_results:
                break

        return json.dumps({
            "keyword": keyword,
            "creators_found": len(creators),
            "credits_remaining": credits_remaining,
            "creators": creators,
        }, indent=2)

    except Exception as e:
        logger.exception("ScrapeCreators API call failed")
        return json.dumps({"error": f"ScrapeCreators API failed: {e}"})


# ---------------------------------------------------------------------------
# Tool 4: log_rotation
# ---------------------------------------------------------------------------

def log_rotation(
    niche_name: str,
    keywords_used: list[str],
    creators_found: int,
    credits_spent: int,
    creators: list[dict],
) -> str:
    """Log a completed niche search to the rotation tracker and upsert discovered creators."""
    db_url = os.getenv("SIGNAL_DATABASE_URL", "")
    if not db_url:
        return json.dumps({"error": "SIGNAL_DATABASE_URL not configured"})

    try:
        # Insert rotation record
        _neon_query(
            """
            INSERT INTO rotation_tracker (niche_name, keywords_used, creators_found, credits_spent)
            VALUES ($1, $2, $3, $4)
            """,
            [niche_name, keywords_used, creators_found, credits_spent],
        )

        # Upsert each creator
        for creator in creators:
            _neon_query(
                """
                INSERT INTO discovered_creators (username, niche_name, follower_count, is_verified)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (username, niche_name) DO UPDATE SET
                    last_seen_at = NOW(),
                    times_seen = discovered_creators.times_seen + 1,
                    follower_count = EXCLUDED.follower_count,
                    is_verified = EXCLUDED.is_verified
                """,
                [
                    creator.get("username", ""),
                    niche_name,
                    creator.get("follower_count", 0),
                    creator.get("is_verified", False),
                ],
            )

        return json.dumps({
            "status": "logged",
            "niche_name": niche_name,
            "creators_upserted": len(creators),
        })

    except Exception as e:
        logger.exception("Failed to log rotation")
        return json.dumps({"error": f"Failed to log rotation: {e}"})


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

GET_NICHE_CLUSTERS_SCHEMA: dict = {
    "name": "get_niche_clusters",
    "description": (
        "Fetch the current niche clusters from Signal AI's database. "
        "Returns a list of niches with their associated keywords. "
        "Use this to get search terms for creator discovery."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

GET_ROTATION_STATUS_SCHEMA: dict = {
    "name": "get_rotation_status",
    "description": (
        "Check which niches have been searched recently and which are overdue for rotation. "
        "Returns all niches sorted by least-recently-searched first (never-searched niches at top). "
        "Use this before searching to pick the right niches for today's run."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

SEARCH_INSTAGRAM_CREATORS_SCHEMA: dict = {
    "name": "search_instagram_creators",
    "description": (
        "Search Instagram for content creators by keyword via ScrapeCreators API. "
        "Returns deduplicated creators with follower counts, engagement metrics, "
        "and the reel that surfaced them. Costs 1 API credit per search."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "Search keyword or niche term (e.g. 'fitness meal prep', 'ecommerce dropshipping')",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of unique creators to return (default: 10)",
                "default": 10,
            },
        },
        "required": ["keyword"],
    },
}

LOG_ROTATION_SCHEMA: dict = {
    "name": "log_rotation",
    "description": (
        "Log a completed niche search to the rotation tracker. "
        "Records which niche was searched, keywords used, credits spent, "
        "and upserts discovered creators for deduplication tracking. "
        "Call this after each search_instagram_creators call."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "niche_name": {
                "type": "string",
                "description": "Name of the niche that was searched",
            },
            "keywords_used": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of keywords that were searched for this niche",
            },
            "creators_found": {
                "type": "integer",
                "description": "Total number of unique creators found across all keyword searches",
            },
            "credits_spent": {
                "type": "integer",
                "description": "Number of ScrapeCreators credits used (1 per search call)",
            },
            "creators": {
                "type": "array",
                "description": "List of creator objects to upsert into the discovered_creators table",
                "items": {
                    "type": "object",
                    "properties": {
                        "username": {"type": "string"},
                        "follower_count": {"type": "integer"},
                        "is_verified": {"type": "boolean"},
                    },
                    "required": ["username"],
                },
            },
        },
        "required": ["niche_name", "keywords_used", "creators_found", "credits_spent", "creators"],
    },
}


# ---------------------------------------------------------------------------
# Registration
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
        keyword=args.get("keyword", ""),
        max_results=args.get("max_results", 10),
    ),
    check_fn=_check_scrapecreators,
    requires_env=["SCRAPECREATORS_API_KEY"],
)

registry.register(
    name="log_rotation",
    toolset="signal_ai",
    schema=LOG_ROTATION_SCHEMA,
    handler=lambda args, **kw: log_rotation(
        niche_name=args.get("niche_name", ""),
        keywords_used=args.get("keywords_used", []),
        creators_found=args.get("creators_found", 0),
        credits_spent=args.get("credits_spent", 0),
        creators=args.get("creators", []),
    ),
    check_fn=_check_neon,
    requires_env=["SIGNAL_DATABASE_URL"],
)
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
cd "F:/Ultim AI Solutions/hermes-agent"
python -m pytest tests/test_signal_creators.py -v
```

Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tools/signal_creators.py
git commit -m "feat: add Signal AI creator discovery tools (4 tools, Neon HTTP + ScrapeCreators)"
```

---

## Task 4: Register Tools in Hermes

**Files:**
- Modify: `model_tools.py` — add `"tools.signal_creators"` to `_modules` list in `_discover_tools()`
- Modify: `toolsets.py` — add `signal_ai` toolset + add tool names to `_HERMES_CORE_TOOLS`

- [ ] **Step 1: Edit `model_tools.py`**

Find the `_modules` list inside `_discover_tools()`. Add `"tools.signal_creators"` at the end of the list, before the closing bracket:

```python
        "tools.homeassistant_tool",
        "tools.signal_creators",
    ]
```

- [ ] **Step 2: Edit `toolsets.py` — add toolset**

Find the `TOOLSETS` dictionary. Add this entry alongside the other toolsets:

```python
    "signal_ai": {
        "description": "Signal AI creator discovery and rotation tracking tools",
        "tools": [
            "get_niche_clusters",
            "get_rotation_status",
            "search_instagram_creators",
            "log_rotation",
        ],
        "includes": [],
    },
```

- [ ] **Step 3: Edit `toolsets.py` — add to core tools**

Find the `_HERMES_CORE_TOOLS` list. Add the 4 tool names at the end:

```python
    "get_niche_clusters",
    "get_rotation_status",
    "search_instagram_creators",
    "log_rotation",
```

- [ ] **Step 4: Verify import works**

```bash
cd "F:/Ultim AI Solutions/hermes-agent"
python -c "import tools.signal_creators; print('Import OK')"
```

Expected: `Import OK` (no errors).

- [ ] **Step 5: Run tests again to make sure nothing broke**

```bash
python -m pytest tests/test_signal_creators.py -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add model_tools.py toolsets.py
git commit -m "feat: register signal_ai toolset in Hermes discovery and core tools"
```

---

## Task 5: Create the Agent Skill

**Files:**
- Create: `skills/marketing/signal-creator-discovery/SKILL.md`

- [ ] **Step 1: Create skill directory and file**

```bash
mkdir -p "F:/Ultim AI Solutions/hermes-agent/skills/marketing/signal-creator-discovery"
```

Create `skills/marketing/signal-creator-discovery/SKILL.md`:

```markdown
---
name: signal-creator-discovery
description: Discover Instagram content creators for Signal AI niches using rotating search with DB-backed tracking
version: 2.0.0
metadata:
  hermes:
    tags: [instagram, creators, scraping, signal-ai, rotation]
    category: marketing
---

# Signal AI Creator Discovery

## When to Use
- When asked to find new content creators for Signal AI
- When asked to discover Instagram creators in specific niches
- When running the daily creator discovery pipeline
- When asked about niche clusters, rotation status, or search history

## Daily Rotation Pipeline

### Step 1: Get Niche Clusters
Call `get_niche_clusters` with no arguments. Returns all current niches from Signal AI's database with associated keywords.

### Step 2: Check Rotation Status
Call `get_rotation_status` with no arguments. Returns all niches sorted by least-recently-searched. Niches that have never been searched appear first with `last_searched: null`.

### Step 3: Pick Today's Niches
Select the **3 least-recently-searched** niches from the rotation status. If the user requests more or fewer, adjust accordingly.

### Step 4: Search for Creators
For each selected niche:
1. Pick 1-2 **specific** keywords from the niche's keyword list. Prefer specific terms over generic ones ("fitness meal prep" not just "fitness").
2. Call `search_instagram_creators` with each keyword.
3. Each call costs 1 ScrapeCreators credit.

### Step 5: Log Results
After searching each niche, call `log_rotation` with:
- The niche name
- All keywords that were used
- Total creators found
- Credits spent (number of search calls made)
- The list of creators discovered (username, follower_count, is_verified)

This records the search in the rotation tracker and upserts creators for dedup tracking.

### Step 6: Report to Chat
Format a summary grouped by niche. For each creator include:
- Username and profile link
- Follower count
- Verified status
- Whether they're NEW (first time seen) or returning (include times_seen count)
- The reel that surfaced them: URL, play count, like count

End the report with:
- Credits spent this run and credits remaining
- Number of new vs. returning creators
- Which niches are next in the rotation

## Manual / Ad-Hoc Usage

These tools are always available, not just during cron:
- "Search for creators in [niche] right now" → skip rotation, search directly
- "What niches haven't been searched this week?" → call get_rotation_status
- "Run 5 niches today" → pick 5 from rotation instead of default 3
- "How many creators have we found?" → can be answered from log_rotation history

When doing manual searches, still call `log_rotation` afterward to keep the rotation tracker accurate.

## Tips
- ScrapeCreators uses Google Search under the hood (IG search requires login). Results may vary.
- Some returned creators may be large accounts posting tangentially about a niche.
- The niche_cluster_cache might be empty if the clustering job hasn't run recently — report this clearly.
- Always check credits_remaining in search responses and mention it in reports.

## Error Handling
If any API call fails, report the error clearly in the chat. Do not silently skip niches.
```

- [ ] **Step 2: Commit**

```bash
git add skills/marketing/signal-creator-discovery/SKILL.md
git commit -m "feat: add Signal AI creator discovery skill for agent guidance"
```

---

## Task 6: Create Docker Compose and Update Env Example

**Files:**
- Create: `docker-compose.yml`
- Modify: `.env.example` (if it exists) or create `.env.signal-ai.example`

- [ ] **Step 1: Create `docker-compose.yml`**

```yaml
# Docker Compose for local development and testing.
# For production, deploy to Railway via GitHub integration.
services:
  hermes:
    build: .
    env_file: .env
    volumes:
      - hermes_data:/opt/data
    restart: unless-stopped
    command: ["hermes", "gateway"]

volumes:
  hermes_data:
```

- [ ] **Step 2: Create `.env.signal-ai.example`**

```bash
# === Signal AI Hermes Agent Environment ===
# Copy this to .env and fill in actual values.

# LLM Provider — OpenRouter
OPENROUTER_API_KEY=<your_openrouter_api_key>

# Signal AI Tools
SIGNAL_DATABASE_URL=postgresql://hermes_agent:<password>@ep-wispy-surf-amaqssxi-pooler.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require
SCRAPECREATORS_API_KEY=<your_scrapecreators_api_key>

# Telegram Gateway
TELEGRAM_BOT_TOKEN=<your_telegram_bot_token>
TELEGRAM_ALLOWED_USERS=<comma_separated_user_ids>
```

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml .env.signal-ai.example
git commit -m "chore: add docker-compose for local dev and Signal AI env example"
```

---

## Task 7: Configure Hermes for OpenRouter

**Files:**
- The Hermes config lives at `/opt/data/config.yaml` at runtime (created by entrypoint from `cli-config.yaml.example`).
- We need to ensure the config template or documentation shows how to set OpenRouter.

- [ ] **Step 1: Create a config override file**

Create `config/signal-ai-config.yaml` to be copied into the volume on first run:

```yaml
# Hermes Agent config for Signal AI
# This file is copied to /opt/data/config.yaml on first boot.

model:
  default: "google/gemini-2.5-flash-preview"
  provider: "openrouter"
  base_url: "https://openrouter.ai/api/v1"

platform_toolsets:
  telegram: [hermes-telegram, signal_ai]
```

Note: The model can be changed later by the user. Gemini 2.5 Flash on OpenRouter is a good cost-effective default for daily cron tasks.

- [ ] **Step 2: Update entrypoint to use our config if present**

This is optional — the user can also manually edit `/opt/data/config.yaml` after first boot via Railway's shell. For now, document it in the README section below.

- [ ] **Step 3: Commit**

```bash
mkdir -p config
git add config/signal-ai-config.yaml
git commit -m "chore: add Signal AI Hermes config template for OpenRouter"
```

---

## Task 8: Deploy to Railway

**Files:** None (CLI operations)

All Railway CLI commands run from `F:/Ultim AI Solutions/signal.ai` where the CLI is already authenticated.

- [ ] **Step 1: Push the feature branch to GitHub**

```bash
cd "F:/Ultim AI Solutions/hermes-agent"
git push -u origin feat/signal-ai-creator-discovery
```

- [ ] **Step 2: Merge to main (or deploy from feature branch)**

```bash
git checkout main
git merge feat/signal-ai-creator-discovery
git push origin main
```

- [ ] **Step 3: Create the Railway service**

```bash
cd "F:/Ultim AI Solutions/signal.ai"
railway service create hermes-agent
```

Expected: New service `hermes-agent` created in project `stellar-rebirth`.

- [ ] **Step 4: Link the service to the GitHub repo**

Use the Railway dashboard or CLI to connect the `hermes-agent` service to your forked GitHub repo. Railway will auto-detect the Dockerfile and build.

```bash
railway link --service hermes-agent
```

Note: If `railway link` requires interactive input, do this in the Railway dashboard instead: Settings → Connect GitHub Repo → select your fork.

- [ ] **Step 5: Attach a persistent volume**

```bash
railway volume create --mount /opt/data
```

Or via dashboard: Service → Volumes → Add Volume → Mount path: `/opt/data`

- [ ] **Step 6: Set environment variables**

```bash
railway variables set \
  OPENROUTER_API_KEY="<user_provides>" \
  SIGNAL_DATABASE_URL="postgresql://hermes_agent:<password>@ep-wispy-surf-amaqssxi-pooler.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require" \
  SCRAPECREATORS_API_KEY="CAKnjl0IVuYoHOuPVJRsvJeIV7T2" \
  TELEGRAM_BOT_TOKEN="<user_provides>" \
  TELEGRAM_ALLOWED_USERS="<user_provides>" \
  RAILWAY_RUN_UID="0"
```

Note: Replace placeholders with actual values. The ScrapeCreators key comes from the signal.ai .env.

- [ ] **Step 7: Trigger deployment**

Railway auto-deploys on push to the connected branch. Verify:

```bash
railway logs --service hermes-agent 2>&1 | head -30
```

Expected: Hermes starts, loads tools, connects to Telegram.

- [ ] **Step 8: Verify the bot responds**

Message the Telegram bot in the group: "What tools do you have?"

Expected: The agent lists its available tools including the 4 Signal AI tools.

---

## Task 9: SQL Setup (User Manual Step)

**Files:** None (user runs SQL in Neon SQL Editor)

This task documents the SQL the user needs to run. Print these as instructions.

- [ ] **Step 1: Print the table creation SQL for the user**

The user runs this in the Neon SQL Editor at https://console.neon.tech:

```sql
-- 1. Create tables
CREATE TABLE rotation_tracker (
    id SERIAL PRIMARY KEY,
    niche_name TEXT NOT NULL,
    searched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    keywords_used TEXT[] NOT NULL,
    creators_found INTEGER NOT NULL DEFAULT 0,
    credits_spent INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_rotation_tracker_niche
    ON rotation_tracker(niche_name, searched_at DESC);

CREATE TABLE discovered_creators (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    niche_name TEXT NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    times_seen INTEGER NOT NULL DEFAULT 1,
    follower_count INTEGER,
    is_verified BOOLEAN DEFAULT FALSE,
    UNIQUE(username, niche_name)
);

CREATE INDEX idx_discovered_creators_username
    ON discovered_creators(username);

-- 2. Create limited-privilege role
CREATE ROLE hermes_agent WITH LOGIN PASSWORD 'CHANGE_THIS_TO_A_STRONG_PASSWORD';
GRANT CONNECT ON DATABASE neondb TO hermes_agent;
GRANT USAGE ON SCHEMA public TO hermes_agent;
GRANT SELECT ON niche_cluster_cache TO hermes_agent;
GRANT SELECT, INSERT, UPDATE ON rotation_tracker TO hermes_agent;
GRANT SELECT, INSERT, UPDATE ON discovered_creators TO hermes_agent;
GRANT USAGE, SELECT ON SEQUENCE rotation_tracker_id_seq TO hermes_agent;
GRANT USAGE, SELECT ON SEQUENCE discovered_creators_id_seq TO hermes_agent;
```

- [ ] **Step 2: User creates the role and updates SIGNAL_DATABASE_URL**

After running the SQL, update the Railway env var:
```
SIGNAL_DATABASE_URL=postgresql://hermes_agent:<password>@ep-wispy-surf-amaqssxi-pooler.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require
```

---

## Task 10: Schedule Daily Cron and Verify End-to-End

**Files:** None (Telegram interaction)

- [ ] **Step 1: Message the bot to schedule the daily cron**

Send this to the Telegram group:

> Every day at 9am UTC, run the Signal AI creator discovery pipeline:
> 1. Get all niche clusters
> 2. Check rotation status to find the 3 least-recently-searched niches
> 3. Search 1-2 keywords per niche for Instagram creators
> 4. Log each search to the rotation tracker
> 5. Send me a summary with creators grouped by niche, flagging new vs returning creators, credits spent, and which niches are next in rotation

- [ ] **Step 2: Verify cron was created**

Message the bot: "List my scheduled tasks" or check via CLI:

```bash
railway shell --service hermes-agent -- hermes cron list
```

- [ ] **Step 3: Trigger a manual test run**

Message the bot: "Run a creator discovery rotation now for 1 niche only, as a test"

Expected: Agent calls all 4 tools in sequence and posts a formatted report.

- [ ] **Step 4: Verify data was written to Neon**

Run in Neon SQL Editor:
```sql
SELECT * FROM rotation_tracker ORDER BY searched_at DESC LIMIT 5;
SELECT * FROM discovered_creators ORDER BY first_seen_at DESC LIMIT 10;
```

Expected: Rows from the test run appear.
