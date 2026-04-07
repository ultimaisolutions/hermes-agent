# Signal AI Creator Discovery — Developer Codemap

**Last Updated:** 2026-04-07  
**Entry Points:** `tools/signal_creators.py`, `model_tools.py`, `toolsets.py`  
**Test Coverage:** 11 unit tests, 100% of tool functions

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────────┐
│                  Telegram Gateway (gateway/platforms/telegram)  │
│                   (receives /message from Telegram API)         │
└───────────────────────┬──────────────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────────────┐
│         Agent Execution Loop (run_agent.py, agent_loop.py)     │
│     [LLM decides which tools to call based on user request]    │
└───────────────────────┬──────────────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────────────┐
│  Tool Registry & Dispatch (model_tools.handle_function_call)   │
│  [maps tool name → handler function + validation]              │
└───────────────────────┬──────────────────────────────────────────┘
                        │
         ┌──────────────┼──────────────┬────────────────────┐
         ▼              ▼              ▼                    ▼
    ┌─────────┐  ┌─────────┐  ┌─────────────────┐  ┌──────────────┐
    │ get_    │  │ get_    │  │ search_         │  │ log_         │
    │ niche   │  │rotation │  │ instagram_      │  │ rotation     │
    │clusters │  │ status  │  │ creators        │  │              │
    └────┬────┘  └────┬────┘  └────┬────────────┘  └──────┬───────┘
         │            │            │                       │
         └─────┬──────┴────┬───────┴───────────────────────┘
               │           │
               ▼           ▼
         ┌─────────────────────────────┐
         │  Neon HTTP API              │
         │  (postgresql://...)         │
         │                             │
         │  Tables:                    │
         │  - niche_cluster_cache      │
         │  - rotation_tracker         │
         │  - discovered_creators      │
         └─────────────────────────────┘
```

---

## File Structure

### Core Tool Implementation

**`tools/signal_creators.py`** (438 lines)

Provides 4 custom tools for Signal AI creator discovery. Uses Neon's HTTP SQL API and ScrapeCreators REST API.

**Organization:**
- Lines 1–24: Module docstring + imports
- Lines 26–110: OpenAI function schemas (GET_NICHE_CLUSTERS_SCHEMA, GET_ROTATION_STATUS_SCHEMA, SEARCH_INSTAGRAM_CREATORS_SCHEMA, LOG_ROTATION_SCHEMA)
- Lines 113–157: Shared helpers (`_check_neon()`, `_check_scrape()`, `_neon_query()`)
- Lines 159–334: Tool implementations (4 functions)
- Lines 388–437: Registry registration (4 `registry.register()` calls)

**Dependencies:**
- `tools.registry` — Self-registering tool framework
- `urllib`, `base64`, `json` — HTTP and credential encoding (no external libs)
- `datetime`, `os` — Env vars and timestamps

### Tool Schemas

| Tool | Parameters | Returns | Cost | Env Var |
|------|-----------|---------|------|---------|
| **get_niche_clusters** | None | `{niche_count, niches[]}` | Free | SIGNAL_DATABASE_URL |
| **get_rotation_status** | None | `{niches_total, rotation[]}` | Free | SIGNAL_DATABASE_URL |
| **search_instagram_creators** | `keyword` (str), `max_results` (int, default 10) | `{keyword, creators_found, credits_remaining, creators[]}` | 1 credit each | SCRAPECREATORS_API_KEY |
| **log_rotation** | `niche_name`, `keywords_used[]`, `creators_found`, `credits_spent`, `creators[]` | `{status, niche_name, creators_upserted}` | Free | SIGNAL_DATABASE_URL |

### Tool Registration Chain

Tools flow through Hermes' discovery and registration system:

```
tools/signal_creators.py
    ↓
    [4 × registry.register() calls]
    ↓
tools/registry.py [in-memory registry dict]
    ↓
model_tools.py:_discover_tools()
    [imports: "tools.signal_creators"]
    ↓
    get_tool_definitions(enabled_toolsets, ...)
    [filters by toolset: "signal_ai"]
    ↓
toolsets.py:resolve_toolset("hermes-telegram")
    [includes "signal_ai" toolset]
    ↓
    _HERMES_CORE_TOOLS list
    [4 tool names: "get_niche_clusters", ...]
    ↓
hermes_cli/tools_config.py:CONFIGURABLE_TOOLSETS
    [("signal_ai", "📡 Signal AI", "...")]
    ↓
gateway/platforms/telegram.py
    [tool names in schema sent to LLM]
```

### Registration Details

**File: `tools/signal_creators.py` (lines 392–437)**

```python
from tools.registry import registry

registry.register(
    name="get_niche_clusters",
    toolset="signal_ai",
    schema=GET_NICHE_CLUSTERS_SCHEMA,
    handler=lambda args, **kw: get_niche_clusters(),
    check_fn=_check_neon,
    requires_env=["SIGNAL_DATABASE_URL"],
)
# ... 3 more register() calls
```

**Key Parameters:**
- `name` — Tool identifier used by LLM
- `toolset` — Groups tools logically ("signal_ai" for all 4)
- `schema` — OpenAI function-calling format
- `handler` — Callable that executes the tool
- `check_fn` — Predicate to enable/disable tool based on env vars
- `requires_env` — List of env vars that must be set

---

## Integration Points

### 1. model_tools.py

**Location:** `model_tools.py` (near top of file)

**Change:** Add `"tools.signal_creators"` to the module discovery list.

```python
def _discover_tools():
    """Import all tool modules to trigger registry.register() calls."""
    _modules = [
        "tools.web_search",
        "tools.signal_creators",  # <-- ADDED
        # ... other tool modules
    ]
    for mod in _modules:
        __import__(mod)
```

**Effect:** When model_tools.py loads, it imports signal_creators.py, which executes all `registry.register()` calls.

### 2. toolsets.py

**Location:** `toolsets.py` (TOOLSETS dict and _HERMES_CORE_TOOLS list)

**Changes (2):**

**A. Add 4 tool names to _HERMES_CORE_TOOLS:**

```python
_HERMES_CORE_TOOLS = [
    # ... existing tools ...
    # Signal AI creator discovery (gated on SIGNAL_DATABASE_URL / SCRAPECREATORS_API_KEY)
    "get_niche_clusters", "get_rotation_status", "search_instagram_creators", "log_rotation",
]
```

**B. Add signal_ai toolset definition to TOOLSETS dict:**

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

**Effect:** These define which tools are available to which platforms/configurations.

### 3. hermes_cli/tools_config.py

**Location:** `hermes_cli/tools_config.py` (CONFIGURABLE_TOOLSETS list)

**Change:** Add Signal AI to the list shown in the setup CLI:

```python
CONFIGURABLE_TOOLSETS = [
    # ... existing entries ...
    ("signal_ai", "📡 Signal AI", "niche clusters, rotation, creator search, logging"),
]
```

**Effect:** Users see Signal AI as an optional toolset in the `hermes setup tools` menu.

---

## Data Flow Diagrams

### Daily Discovery Rotation

```
┌──────────────────────────────┐
│ Telegram cron job triggers   │ (once per day at scheduled time)
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────────────────┐
│ Agent: "Run creator discovery"           │
└──────────────┬──────────────────────────┘
               │
               ▼ Calls tool #1
     ┌─────────────────────────┐
     │ get_niche_clusters()    │
     │ Neon: SELECT value FROM │
     │ niche_cluster_cache     │
     └──────────┬──────────────┘
                │ Returns: [fitness, crypto, ai tools, ...]
                ▼
     ┌──────────────────────────┐
     │ get_rotation_status()    │  Calls tool #2
     │ Neon: SELECT niche_name, │
     │ MAX(searched_at) FROM    │
     │ rotation_tracker GROUP.. │
     └──────────┬───────────────┘
                │ Returns: [(ai_tools, null), (crypto, 2026-04-01), ...]
                ▼ [Picks top 3 least-recently-searched]
          ┌─────────────────────────────────┐
          │ For niche in [ai_tools, ...]    │
          │                                 │
          │ ┌───────────────────────────┐   │ Calls tool #3
          │ │ search_instagram_creators │   │
          │ │ ScrapeCreators:           │   │
          │ │ GET /v2/instagram/reels/  │   │
          │ │ search?keyword=chatgpt    │   │
          │ └───────────┬───────────────┘   │
          │             │ Returns: [creator1, creator2, ...]
          │             │ costs 1 credit
          │             ▼
          │ ┌────────────────────────────┐  │ Calls tool #4
          │ │ log_rotation(...)          │  │
          │ │ Neon:                      │  │
          │ │ 1. INSERT rotation_tracker │  │
          │ │ 2. INSERT...ON CONFLICT   │  │
          │ │    discovered_creators    │  │
          │ └────────────┬───────────────┘  │
          │              │ Returns: {status: "logged", ...}
          │              ▼
          │ [Next niche in rotation]
          └────────────────────────────────┘
               │ All 3 niches processed
               ▼
┌──────────────────────────────┐
│ Agent formats report         │
│ Posts to Telegram group      │
└──────────────────────────────┘
```

### Creator Deduplication & Tracking

```
ScrapeCreators API returns [reel1, reel2, reel3, ...]
                            └─owner: {username, follower_count, ...}

Tool deduplicates by username:
- reel1.owner.username = "fitchef" → add to creators[]
- reel2.owner.username = "fitchef" → skip (already in set)
- reel3.owner.username = "macro_m" → add to creators[]

Result: 2 unique creators

log_rotation() upserts to DB:
INSERT INTO discovered_creators (username, niche_name, ...)
VALUES ("fitchef", "fitness", 45000, false)
ON CONFLICT (username, niche_name) DO UPDATE SET
  last_seen_at = NOW(),
  times_seen = discovered_creators.times_seen + 1,
  follower_count = EXCLUDED.follower_count,
  is_verified = EXCLUDED.is_verified

Outcome:
- First search in niche: times_seen = 1, new_flag = true
- Subsequent searches: times_seen increments, last_seen_at updates
- Enables "NEW vs RETURNING" logic in report formatting
```

---

## Key Functions

### Tool Implementations

**`get_niche_clusters() → str`** (lines 164–204)

**Purpose:** Fetch cached niche clusters from Neon DB.

**Query:**
```sql
SELECT value FROM niche_cluster_cache WHERE key = 'current' LIMIT 1
```

**Returns (JSON):**
```json
{
  "niche_count": 2,
  "niches": [
    {"name": "fitness", "keywords": ["workout", "gym", "health", "diet", "protein"]},
    {"name": "crypto", "keywords": ["bitcoin"]}
  ]
}
```

**Error Cases:**
- `SIGNAL_DATABASE_URL` not set → `{"error": "SIGNAL_DATABASE_URL is not set"}`
- No cache data → `{"error": "No niche clusters found in cache"}`
- Connection error → `{"error": "..."}`

---

**`get_rotation_status() → str`** (lines 207–266)

**Purpose:** Check rotation tracking for all niches. Returns sorted by least-recently-searched.

**Process:**
1. Calls `get_niche_clusters()` internally to get niche names
2. Queries `rotation_tracker` for max `searched_at` per niche
3. Compares to now in UTC
4. Sorts: never-searched first (null), then oldest first (largest days_ago)

**Query (parameterized):**
```sql
SELECT niche_name, MAX(searched_at) FROM rotation_tracker
WHERE niche_name IN ($1, $2, $3, ...)
GROUP BY niche_name
```

**Returns (JSON):**
```json
{
  "niches_total": 3,
  "rotation": [
    {"niche": "ai tools", "last_searched": null, "days_ago": null},
    {"niche": "crypto", "last_searched": "2026-04-01T09:00:00Z", "days_ago": 6},
    {"niche": "fitness", "last_searched": "2026-04-05T09:00:00Z", "days_ago": 2}
  ]
}
```

---

**`search_instagram_creators(keyword: str, max_results: int = 10) → str`** (lines 269–333)

**Purpose:** Search Instagram reels via ScrapeCreators API. Deduplicates by username.

**Request:**
```
GET https://api.scrapecreators.com/v2/instagram/reels/search?keyword=fitness
Header: x-api-key: <SCRAPECREATORS_API_KEY>
```

**Response (before dedup):**
```json
{
  "reels": [
    {"owner": {"username": "creator1", ...}, "video_play_count": 1000, ...},
    {"owner": {"username": "creator1", ...}, "video_play_count": 2000, ...},
    {"owner": {"username": "creator2", ...}, "video_play_count": 5000, ...}
  ],
  "credits_remaining": 24500
}
```

**Deduplication:** Tracks seen usernames in a set. For each unique creator, builds object with:
- `username`, `full_name`, `follower_count`, `post_count`, `is_verified`
- `profile_url` (constructed: `https://instagram.com/{username}`)
- `discovered_via` (from the first reel that had this creator):
  - `reel_url`, `play_count`, `like_count`, `comment_count`

**Returns (JSON):**
```json
{
  "keyword": "fitness",
  "creators_found": 2,
  "credits_remaining": 24500,
  "creators": [
    {
      "username": "creator1",
      "full_name": "Creator One",
      "follower_count": 5000,
      "is_verified": false,
      "profile_url": "https://instagram.com/creator1",
      "discovered_via": {
        "reel_url": "https://instagram.com/reel/1",
        "play_count": 1000,
        "like_count": 50,
        "comment_count": 5
      }
    },
    ...
  ]
}
```

**Error Cases:**
- `SCRAPECREATORS_API_KEY` not set → `{"error": "SCRAPECREATORS_API_KEY is not set"}`
- API error → `{"error": "..."}`

---

**`log_rotation(niche_name, keywords_used, creators_found, credits_spent, creators) → str`** (lines 336–385)

**Purpose:** Record search in rotation tracker and upsert discovered creators. Enables dedup tracking and rotation scheduling.

**Process:**
1. INSERT into `rotation_tracker` (1 call):
   ```sql
   INSERT INTO rotation_tracker (niche_name, keywords_used, creators_found, credits_spent)
   VALUES ($1, $2, $3, $4)
   ```

2. For each creator, INSERT/UPDATE in `discovered_creators` (1 call per creator):
   ```sql
   INSERT INTO discovered_creators (username, niche_name, follower_count, is_verified)
   VALUES ($1, $2, $3, $4)
   ON CONFLICT (username, niche_name) DO UPDATE SET
     last_seen_at = NOW(),
     times_seen = discovered_creators.times_seen + 1,
     follower_count = EXCLUDED.follower_count,
     is_verified = EXCLUDED.is_verified
   ```

**Returns (JSON):**
```json
{
  "status": "logged",
  "niche_name": "fitness",
  "creators_upserted": 2
}
```

**Error Cases:**
- `SIGNAL_DATABASE_URL` not set → `{"error": "SIGNAL_DATABASE_URL is not set"}`
- SQL error → `{"error": "..."}`

---

### Shared Helpers

**`_check_neon() → bool`** (lines 117–119)

Returns `True` if `SIGNAL_DATABASE_URL` env var is set. Used as `check_fn` for tools that need database access. Hermes automatically disables tools with failing `check_fn`.

**`_check_scrape() → bool`** (lines 122–124)

Returns `True` if `SCRAPECREATORS_API_KEY` env var is set. Used as `check_fn` for ScrapeCreators tool.

**`_neon_query(sql: str, params: Optional[List[Any]]) → Dict[str, Any]`** (lines 127–156)

Executes parameterized SQL against Neon HTTP API.

**Process:**
1. Parse `SIGNAL_DATABASE_URL` (postgresql://user:pass@host/db)
2. Extract: host, user, password
3. Base64 encode credentials
4. POST to `https://{host}/sql`
   - Header: `Authorization: Basic <base64>`
   - Header: `Neon-Connection-String: <db_url>`
   - Body: `{"query": sql, "params": params}`
5. Parse JSON response
6. Return `{"rows": [...], "fields": [...]}`

**Important:** All queries are parameterized (using `$1`, `$2`, etc.) to prevent SQL injection.

---

## Testing Strategy

**File: `tests/test_signal_creators.py`** (311 lines)

**Framework:** pytest with `unittest.mock`

**Test Classes:** 4 (one per tool function)

### Test Coverage

| Tool | Test Cases | Lines |
|------|-----------|-------|
| **get_niche_clusters** | 3 (dict format, list format, empty cache) | 55–114 |
| **get_rotation_status** | 2 (sorted rotation, no history) | 120–159 |
| **search_instagram_creators** | 3 (dedup, max_results, missing API key) | 165–252 |
| **log_rotation** | 2 (happy path, missing env) | 258–310 |
| **Helpers/Fixtures** | 2 fixture functions + 2 mock response builders | 13–48 |

**Total:** 11 test cases, all passing

### Key Testing Patterns

**Mocking HTTP Responses:**

```python
def _make_neon_response(rows, fields=None):
    """Build a mock Neon HTTP API response body."""
    body = json.dumps({"rows": rows, "fields": fields or []}).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp

@patch("urllib.request.urlopen")
def test_example(self, mock_urlopen):
    mock_urlopen.return_value = _make_neon_response([["data"]])
    # ... call tool and assert
```

**Env Var Fixtures:**

```python
@pytest.fixture(autouse=True)
def signal_env(monkeypatch):
    """Set required env vars for all tests."""
    monkeypatch.setenv("SIGNAL_DATABASE_URL", "postgresql://...")
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", "test-api-key")
```

**Deduplication Test:**

```python
def test_returns_deduplicated_creators(self, mock_urlopen):
    reels = [
        {"owner": {"username": "creator1", ...}, ...},
        {"owner": {"username": "creator1", ...}, ...},  # Duplicate
        {"owner": {"username": "creator2", ...}, ...},
    ]
    mock_urlopen.return_value = _make_scrape_response(reels)
    result = json.loads(search_instagram_creators("fitness"))
    assert result["creators_found"] == 2  # Deduplicated
```

---

## External Dependencies

### Neon HTTP SQL API

- **URL:** `https://{neon_endpoint}/sql`
- **Auth:** Basic auth + connection string header
- **Protocol:** HTTPS POST with JSON body
- **Timeout:** 30 seconds per call
- **No external Python libraries** — uses `urllib` (stdlib)

### ScrapeCreators API

- **URL:** `https://api.scrapecreators.com/v2/instagram/reels/search`
- **Auth:** Header `x-api-key`
- **Protocol:** HTTPS GET with query params
- **Timeout:** 30 seconds per call
- **Cost:** 1 credit per search
- **No external Python libraries** — uses `urllib` (stdlib)

### Hermes Framework

- **tools.registry** — Tool registration
- **models** — LLM interface (OpenRouter)
- **gateway.platforms.telegram** — Message delivery
- **cronjob** — Scheduled task management
- **skills** — Agent instruction files

---

## Configuration & Environment

### Required Environment Variables

| Variable | Purpose | Example | Secret? |
|----------|---------|---------|---------|
| `SIGNAL_DATABASE_URL` | Neon connection string | `postgresql://hermes_agent:...@ep-...-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require` | Yes |
| `SCRAPECREATORS_API_KEY` | ScrapeCreators auth | `sk_123abc...` | Yes |
| `OPENROUTER_API_KEY` | LLM provider (OpenRouter) | `sk-or-v1-...` | Yes |
| `TELEGRAM_BOT_TOKEN` | Telegram bot auth | `123456:ABC...` | Yes |
| `TELEGRAM_ALLOWED_USERS` | User ID allowlist | `123,456,789` | No |

### Deployment Configuration Files

**`.env.signal-ai.example`**

Template for local development. Copy to `.env` and fill in values.

**`config/signal-ai-config.yaml`**

Hermes config template for Railway deployment:
```yaml
model:
  default: "google/gemma-4-31b-it"
  provider: "openrouter"
platform_toolsets:
  telegram: [hermes-telegram, signal_ai]
```

**`docker-compose.yml`**

Local dev compose file for testing the integration:
```yaml
services:
  hermes:
    build: .
    env_file: .env
    volumes:
      - hermes_data:/opt/data
    restart: unless-stopped
    command: ["hermes", "gateway"]
```

**`Dockerfile`** (modified)

Changes for Railway deployment:
- Added `sed` to fix CRLF in entrypoint.sh (Windows compatibility)
- Removed `VOLUME` directive (Railway manages externally)
- Changed `CMD` to `["gateway"]` (Telegram gateway mode)

---

## Related Files & Documentation

### Skill Definition

**`skills/marketing/signal-creator-discovery/SKILL.md`**

Teaches the agent the discovery workflow:
- How to fetch niche clusters and rotation status
- Which 3 niches to select per daily run
- How to search with specific keywords
- How to flag NEW vs RETURNING creators
- How to format and deliver reports
- How to handle errors

### Design & Planning Docs

- **`docs/superpowers/specs/2026-04-07-hermes-signal-ai-creator-discovery-design.md`** — Architecture, DB schema, tool specifications
- **`docs/superpowers/plans/2026-04-07-hermes-signal-ai-creator-discovery.md`** — Task breakdown and implementation steps

### User Documentation

- **`docs/SIGNAL_AI_README.md`** — Setup guide, usage instructions, troubleshooting

---

## Development Workflow

### Adding a New Tool

1. **Define the schema** — Add a `SCHEMA` dict with OpenAI function-calling format
2. **Implement the function** — Add a function that returns JSON string
3. **Register with registry** — Call `registry.register()` with name, toolset, schema, handler, check_fn
4. **Add to toolsets.py** — Add tool name to `_HERMES_CORE_TOOLS` and `signal_ai` toolset
5. **Add to tools_config.py** — Update `CONFIGURABLE_TOOLSETS` description if needed
6. **Write tests** — Add test class with 3+ test cases to `tests/test_signal_creators.py`
7. **Update skill** — Document new tool in `skills/marketing/signal-creator-discovery/SKILL.md`

### Testing Locally

```bash
# Install dependencies
pip install -e ".[all]"

# Run tests
pytest tests/test_signal_creators.py -v

# Run with coverage
pytest tests/test_signal_creators.py --cov=tools.signal_creators --cov-report=term-missing

# Manual testing (requires env vars)
cp .env.signal-ai.example .env
# Fill in .env with real credentials
docker-compose up

# Or run directly:
hermes gateway
```

### Deploying to Railway

```bash
# Commit changes
git add tools/signal_creators.py model_tools.py toolsets.py ...
git commit -m "feat: add Signal AI creator discovery tools"

# Push to fork
git push origin feat/signal-ai-creator-discovery

# Create PR or merge to main

# Railway auto-detects on git push
# Watch deployment: railway logs --tail 100
```

---

## Performance Characteristics

### API Call Latencies

| Operation | Typical Latency | Cost |
|-----------|-----------------|------|
| `get_niche_clusters` | 200–500ms | Free |
| `get_rotation_status` | 300–800ms | Free |
| `search_instagram_creators` | 1–3s | 1 credit |
| `log_rotation` (1 creator) | 500–1200ms | Free |
| `log_rotation` (10 creators) | 5–12s (10 upserts) | Free |

### Database Query Performance

- **rotation_tracker**: Indexed on `(niche_name, searched_at DESC)` → O(log n) lookups
- **discovered_creators**: Indexed on `username` → O(log n) lookups by creator
- **niche_cluster_cache**: Single row, direct lookup → O(1)

### Daily Rotation Cost

- 3 niches × 2 keywords = 6 `search_instagram_creators` calls
- 6 calls × 1 credit = 6 credits/day
- ~180 credits/month
- At 25K credits = 138 months runway

---

## Known Limitations & Future Work

### Current Limitations

1. **No creator scoring** — All creators returned equally, regardless of engagement
2. **Instagram-only** — ScrapeCreators API used; other platforms not integrated
3. **Manual niche clustering** — Niches must be pre-loaded in `niche_cluster_cache` by external process
4. **No outreach automation** — Discovered creators not auto-contacted
5. **No web dashboard** — Reports only in Telegram; no analytics UI

### Future Enhancements

1. **Creator ranking** — Score by follower count, engagement rate, niche relevance
2. **Multi-platform** — Extend to TikTok, YouTube via ScrapeCreators endpoints
3. **Auto-outreach** — Integrate email/DM tools to contact creators
4. **Analytics dashboard** — Web UI for discovered creators, trends, niche coverage
5. **Creator profiles** — Store email, collaboration history, rate card
6. **A/B testing** — Compare search strategies, keyword effectiveness
7. **Backfill mode** — Re-search all niches to bootstrap database
8. **Duplicate detection** — Across Instagram handles and name variations

---

## Version History

- **2026-04-07** — Initial release. 4 tools (get_niche_clusters, get_rotation_status, search_instagram_creators, log_rotation). Neon HTTP SQL API + ScrapeCreators integration. Telegram delivery. 11 unit tests.
