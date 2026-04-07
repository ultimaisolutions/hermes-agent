# Hermes Agent — Signal AI Creator Discovery

**Date:** 2026-04-07
**Status:** Design approved
**Authors:** Ofek + Claude

---

## 1. Purpose

Deploy a Hermes Agent instance as a marketing tool for Signal AI. The agent discovers Instagram content creators by reading niche clusters from NeonDB and searching via the ScrapeCreators API, then delivers daily rotating reports to a Telegram group chat. The agent is also available for interactive queries and ad-hoc searches via Telegram at any time.

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Railway Project: stellar-rebirth (production)          │
│                                                         │
│  ┌──────────────┐        ┌────────────────────────┐     │
│  │ @signal/api  │        │  hermes-agent           │     │
│  │ (existing)   │        │  (new persistent svc)   │     │
│  └──────────────┘        │                         │     │
│                          │  Telegram Gateway       │     │
│                          │  (always running)       │     │
│                          │                         │     │
│                          │  Hermes Cron Engine     │     │
│                          │  (daily rotation job)   │     │
│                          │                         │     │
│                          │  Volume: /opt/data      │     │
│                          │  config, sessions,      │     │
│                          │  memories, skills       │     │
│                          └────────────────────────┘     │
└─────────────────────────────────────────────────────────┘
                                    │
                                    │ All external, HTTPS
                                    ├──► Neon HTTP API (read niches, rotation tracking)
                                    ├──► ScrapeCreators API (Instagram search)
                                    ├──► OpenRouter (LLM inference)
                                    └──► Telegram Bot API (delivery + interaction)
```

### Key decisions

- Hermes runs as a **new persistent service** in the existing `stellar-rebirth` Railway project.
- All external APIs accessed over public HTTPS. Neon is not on Railway's private network.
- Rotation state and creator history live in **Neon DB** (durable, auditable), not in Hermes memory files.
- Hermes memory (`/opt/data`) is still used for agent session context and general memory — just not as the source of truth for rotation.
- LLM provider: **OpenRouter** (model TBD by user, flexible routing).

## 3. Database Schema

Two new tables in the existing Neon DB (`neondb`). Created manually by the user via Neon SQL Editor.

```sql
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
```

### DB access

A dedicated Neon role with limited permissions:

```sql
CREATE ROLE hermes_agent WITH LOGIN PASSWORD '<strong_password>';
GRANT CONNECT ON DATABASE neondb TO hermes_agent;
GRANT USAGE ON SCHEMA public TO hermes_agent;
GRANT SELECT ON niche_cluster_cache TO hermes_agent;
GRANT SELECT, INSERT, UPDATE ON rotation_tracker TO hermes_agent;
GRANT SELECT, INSERT, UPDATE ON discovered_creators TO hermes_agent;
GRANT USAGE, SELECT ON SEQUENCE rotation_tracker_id_seq TO hermes_agent;
GRANT USAGE, SELECT ON SEQUENCE discovered_creators_id_seq TO hermes_agent;
```

No DELETE, TRUNCATE, or DDL permissions. Connection string uses the **pooler** endpoint with `sslmode=require`.

## 4. Tools

All tools live in a single module: `tools/signal_creators.py`, registered under the `signal_ai` toolset.

### 4.1 get_niche_clusters

- **Direction:** Read
- **API:** Neon HTTP `/sql`
- **Query:** `SELECT value FROM niche_cluster_cache WHERE key = 'current' LIMIT 1`
- **Returns:** List of niches with top keywords
- **Cost:** Free
- **Env:** `SIGNAL_DATABASE_URL`

### 4.2 get_rotation_status

- **Direction:** Read
- **API:** Neon HTTP `/sql`
- **Query:** Gets all niche names from `niche_cluster_cache`, then LEFT JOINs with `rotation_tracker` to find each niche's most recent `searched_at`. Niches with no rotation history appear with `null`. Sorted by `searched_at ASC NULLS FIRST`.
- **Returns:** All niches sorted by least-recently-searched (nulls first), with `days_ago` for each
- **Cost:** Free
- **Env:** `SIGNAL_DATABASE_URL`

Example response:
```json
{
  "niches_total": 12,
  "rotation": [
    {"niche": "ai productivity", "last_searched": null, "days_ago": null},
    {"niche": "ecommerce dropshipping", "last_searched": "2026-04-01", "days_ago": 6},
    {"niche": "fitness meal prep", "last_searched": "2026-04-05", "days_ago": 2}
  ]
}
```

### 4.3 search_instagram_creators

- **Direction:** Read
- **API:** ScrapeCreators `GET /v2/instagram/reels/search?keyword=...`
- **Returns:** Deduplicated creators with engagement metrics and the reel that surfaced them
- **Cost:** 1 ScrapeCreators credit per call
- **Env:** `SCRAPECREATORS_API_KEY`

### 4.4 log_rotation

- **Direction:** Write
- **API:** Neon HTTP `/sql`
- **Actions:**
  1. `INSERT INTO rotation_tracker` — logs the search event
  2. `INSERT INTO discovered_creators ... ON CONFLICT (username, niche_name) DO UPDATE` — upserts creator, increments `times_seen`, updates `last_seen_at` and `follower_count`
- **Parameters:** `niche_name`, `keywords_used`, `creators_found`, `credits_spent`, `creators` (list of creator objects)
- **Cost:** Free
- **Env:** `SIGNAL_DATABASE_URL`

## 5. Toolset & Registration

### model_tools.py

Add `"tools.signal_creators"` to the tool discovery list in `_discover_tools()`.

### toolsets.py

Add toolset definition:
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

Add all 4 tool names to `_HERMES_CORE_TOOLS`.

## 6. Skill

Installed at `/opt/data/skills/marketing/signal-creator-discovery/SKILL.md`.

Teaches the agent:
- How to run the full discovery pipeline (get niches → check rotation → search → log → report)
- To pick 3 least-recently-searched niches per daily run
- To use specific keywords (not generic) from each niche's keyword list
- To flag new vs. returning creators in reports
- To include credits remaining and next-rotation preview
- That it can be triggered manually via Telegram conversation at any time

## 7. Docker & Deployment

### Source: Forked repository

Fork `NousResearch/hermes-agent` to your GitHub account. Changes to the fork:

| File | Action | What |
|------|--------|------|
| `tools/signal_creators.py` | Add | 4 tools + schemas + registration |
| `model_tools.py` | Edit | Add `"tools.signal_creators"` to discovery |
| `toolsets.py` | Edit | Add `signal_ai` toolset + core tools |
| `docker-compose.yml` | Create | Local dev compose file |
| `skills/marketing/signal-creator-discovery/SKILL.md` | Add | Agent skill file (baked into image) |

### docker-compose.yml (local dev)

```yaml
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

### Railway deployment

1. `railway service create` — new service in `stellar-rebirth`
2. Connect to the forked GitHub repo — Railway auto-detects Dockerfile
3. Attach persistent volume at `/opt/data`
4. Set environment variables (see section 8)
5. Start command: `hermes gateway`
6. Set `RAILWAY_RUN_UID=0` if container runs non-root

## 8. Environment Variables (Railway service)

```
# LLM
OPENROUTER_API_KEY=<user_provides>

# Signal AI tools
SIGNAL_DATABASE_URL=postgresql://hermes_agent:<password>@ep-wispy-surf-amaqssxi-pooler.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require
SCRAPECREATORS_API_KEY=<from_signal_ai_env>

# Telegram
TELEGRAM_BOT_TOKEN=<user_provides>
TELEGRAM_ALLOWED_USERS=<user_id_1>,<user_id_2>

# Railway
RAILWAY_RUN_UID=0
```

## 9. Daily Cron Flow

Triggered by Hermes' built-in cron engine (scheduled via Telegram conversation).

1. Agent calls `get_niche_clusters` → gets all niches with keywords
2. Agent calls `get_rotation_status` → gets niches sorted by least recently searched
3. Agent picks the **3 least-recently-searched** niches
4. For each niche:
   a. Picks 1-2 specific keywords from the niche's keyword list
   b. Calls `search_instagram_creators` per keyword
   c. Calls `log_rotation` with results (upserts creators, logs search event)
5. Posts formatted summary to Telegram group

### Telegram report format

```
Creator Discovery — April 7, 2026

Niches searched today: 3 of 12 (rotating)

--- Fitness Meal Prep ---
- @fitchef_jane — 45K followers — NEW
  Reel: 12K plays, 890 likes
- @macro_mike — 120K followers (verified) — seen 3x before
  Reel: 45K plays, 3.2K likes

--- AI Productivity ---
- @toolstack_ai — 8K followers — NEW
  Reel: 5K plays, 320 likes

---
Credits spent: 5 | Remaining: 24,812
New creators: 4 | Returning: 2
Next rotation: ecommerce, crypto, wellness
```

### Error handling

If Neon or ScrapeCreators is down, the agent reports the failure to Telegram with the error details rather than silently skipping.

## 10. Interactive Usage

The Telegram bot is a full conversational interface, not just a cron report channel.

- Ad-hoc searches: "Search for creators in crypto right now"
- Status queries: "What niches haven't been searched this week?"
- Manual rotation: "Run a full rotation of 5 niches"
- Analytics: "How many new creators did we find this month?"
- Strategy: "Which niches have the highest creator density?"
- General conversation about marketing strategy

All 4 tools are available at all times, not just during cron.

## 11. Manual Steps Required

Before deployment, the user must:

1. **Fork** NousResearch/hermes-agent on GitHub
2. **Create OpenRouter API key** at openrouter.ai
3. **Run SQL** in Neon SQL Editor:
   - Create `rotation_tracker` and `discovered_creators` tables (section 3)
   - Create `hermes_agent` role with limited permissions (section 3)
4. **Get Telegram user IDs** for both group members (via @userinfobot)
5. **Add the Telegram bot** to the group chat
6. **Set environment variables** on Railway service (section 8)
7. **Schedule the daily cron** by messaging the bot with the scheduling instruction

## 12. Credit Budget

Each `search_instagram_creators` call costs 1 ScrapeCreators credit.

- 3 niches/day x 2 keywords/niche = 6 credits/day
- Monthly: ~180 credits
- With 25K credits: ~138 months of runway
- Ad-hoc searches add to this but are user-initiated

## 13. Future Considerations

Not in scope for this implementation, but noted:

- **Creator scoring/ranking** — weight creators by engagement rate, follower growth, niche relevance
- **Auto-outreach** — integrate with email/DM tools to contact discovered creators
- **Multi-platform** — extend to TikTok, YouTube via ScrapeCreators' other endpoints
- **Dashboard** — surface discovered creators in the Signal AI web UI
