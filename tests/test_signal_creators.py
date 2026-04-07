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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
                {
                    "name": "fitness",
                    "keywords": [
                        "workout", "gym", "health", "diet", "protein", "cardio",
                    ],
                },
                {"name": "crypto", "keywords": ["bitcoin", "defi"]},
            ]
        }
        mock_urlopen.return_value = _make_neon_response(
            [[json.dumps(cluster_data)]]
        )

        from tools.signal_creators import get_niche_clusters

        result = json.loads(get_niche_clusters())
        assert result["niche_count"] == 2
        assert result["niches"][0]["name"] == "fitness"
        # Keywords capped at 5
        assert len(result["niches"][0]["keywords"]) == 5

    @patch("urllib.request.urlopen")
    def test_returns_niches_from_list_format(self, mock_urlopen):
        cluster_data = [
            {"name": "ai tools", "keywords": ["chatgpt", "automation"]},
        ]
        mock_urlopen.return_value = _make_neon_response(
            [[json.dumps(cluster_data)]]
        )

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
        # First call: get niches (called internally by get_niche_clusters)
        niches_resp = _make_neon_response([[json.dumps({
            "clusters": [
                {"name": "fitness", "keywords": ["workout"]},
                {"name": "crypto", "keywords": ["bitcoin"]},
                {"name": "ai tools", "keywords": ["chatgpt"]},
            ]
        })]])
        # Second call: get rotation history from rotation_tracker
        rotation_resp = _make_neon_response([
            ["fitness", "2026-04-05T09:00:00Z"],
            ["crypto", "2026-04-01T09:00:00Z"],
        ])
        mock_urlopen.side_effect = [niches_resp, rotation_resp]

        from tools.signal_creators import get_rotation_status

        result = json.loads(get_rotation_status())
        assert result["niches_total"] == 3
        # ai tools has never been searched -> should be first
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
                "owner": {
                    "username": "creator1",
                    "full_name": "Creator One",
                    "follower_count": 5000,
                    "post_count": 100,
                    "is_verified": False,
                },
                "url": "https://instagram.com/reel/1",
                "video_play_count": 1000,
                "like_count": 50,
                "comment_count": 5,
            },
            {
                "owner": {
                    "username": "creator1",
                    "full_name": "Creator One",
                    "follower_count": 5000,
                    "post_count": 100,
                    "is_verified": False,
                },
                "url": "https://instagram.com/reel/2",
                "video_play_count": 2000,
                "like_count": 100,
                "comment_count": 10,
            },
            {
                "owner": {
                    "username": "creator2",
                    "full_name": "Creator Two",
                    "follower_count": 10000,
                    "post_count": 200,
                    "is_verified": True,
                },
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
            {
                "owner": {
                    "username": f"creator{i}",
                    "full_name": "",
                    "follower_count": 100,
                    "post_count": 10,
                    "is_verified": False,
                },
                "url": f"https://instagram.com/reel/{i}",
                "video_play_count": 100,
                "like_count": 10,
                "comment_count": 1,
            }
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
        # 1 call for rotation_tracker INSERT + 1 call per creator upsert = 3
        success_resp_1 = _make_neon_response([])
        success_resp_2 = _make_neon_response([])
        success_resp_3 = _make_neon_response([])
        mock_urlopen.side_effect = [
            success_resp_1,
            success_resp_2,
            success_resp_3,
        ]

        from tools.signal_creators import log_rotation

        result = json.loads(log_rotation(
            niche_name="fitness",
            keywords_used=["workout", "gym"],
            creators_found=2,
            credits_spent=2,
            creators=[
                {
                    "username": "fitguru",
                    "follower_count": 5000,
                    "is_verified": False,
                },
                {
                    "username": "gymrat",
                    "follower_count": 12000,
                    "is_verified": True,
                },
            ],
        ))
        assert result["status"] == "logged"
        assert result["niche_name"] == "fitness"
        assert result["creators_upserted"] == 2

        # 1 rotation insert + 2 creator upserts = 3 calls
        assert mock_urlopen.call_count == 3

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
