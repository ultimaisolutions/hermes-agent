# Signal AI Creator Discovery Integration

**Last Updated:** 2026-04-07  
**Status:** Production-ready  
**Deployment:** Railway (stellar-rebirth project)

---

## Overview

This integration deploys Hermes Agent as a persistent Telegram bot that discovers Instagram content creators using Signal AI's niche clusters. The bot:

- Searches Instagram creators by niche using the ScrapeCreators API
- Tracks search rotation across niches to ensure balanced coverage
- Maintains a database of discovered creators with engagement metrics
- Delivers daily rotating discovery reports to Telegram
- Supports ad-hoc searches and queries via Telegram conversation

**Credit Budget:** ~6 credits/day (3 niches × 2 keywords/niche) = ~180 credits/month. With 25K credits, you have approximately 138 months of runway.

---

## Architecture

```
┌──────────────────────────────────────────────┐
│      Railway Service: hermes-agent            │
│      (Persistent Docker container)            │
│                                               │
│  ┌────────────────┐  ┌────────────────────┐  │
│  │ Telegram       │  │ Hermes Cron Engine │  │
│  │ Gateway        │  │ (Daily discovery)  │  │
│  │ (interactive)  │  └────────────────────┘  │
│  └────────────────┘                          │
│                                               │
│  Signal AI Tools (4):                         │
│  - get_niche_clusters                         │
│  - get_rotation_status                        │
│  - search_instagram_creators                  │
│  - log_rotation                               │
│                                               │
│  Volume: /opt/data (persistent storage)       │
│  Config, sessions, skills                     │
└──────────────────────────────────────────────┘
       │              │              │
       ├─────────────►│              │
       │     Neon HTTP API           │
       │     (Rotation + Creators)   │
       │                             │
       ├─────────────────────────────►
       │         ScrapeCreators API
       │         (Instagram search)
       │
       ├─────────────────────────────►
       │         OpenRouter
       │         (LLM inference)
       │
       └─────────────────────────────►
                Telegram Bot API
```

---

## Setup Instructions

### Prerequisites

- Signal AI NeonDB access with tables created (see Database Setup section)
- ScrapeCreators API key with credits
- OpenRouter API key
- Telegram Bot Token and user IDs
- Railway account with `stellar-rebirth` project

### 1. Database Setup

The integration uses two new tables in your NeonDB instance. Create them via the Neon SQL Editor:

```sql
-- Tracks search history per niche for rotation scheduling
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

-- Tracks unique creators discovered across all niches
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

Create a limited-permission database role:

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

### 2. Environment Variables

Set these on your Railway service. Copy `.env.signal-ai.example` as a template:

```bash
# LLM Provider
OPENROUTER_API_KEY=<your_openrouter_api_key>

# Signal AI Tools
SIGNAL_DATABASE_URL=postgresql://hermes_agent:<password>@ep-<endpoint>-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require
SCRAPECREATORS_API_KEY=<your_scrapecreators_api_key>

# Telegram Gateway
TELEGRAM_BOT_TOKEN=<your_telegram_bot_token>
TELEGRAM_ALLOWED_USERS=<user_id_1>,<user_id_2>

# Railway (if container runs non-root)
RAILWAY_RUN_UID=0
```

**Important:** The `SIGNAL_DATABASE_URL` must use the Neon **pooler** endpoint (ends with `-pooler`), not the direct endpoint. Use the `hermes_agent` role credentials.

### 3. Local Development

For local testing before deploying to Railway:

```bash
# Copy env template and fill in values
cp .env.signal-ai.example .env

# Start services (Hermes in Docker)
docker-compose up

# Or run directly if dependencies installed locally:
pip install -e ".[all]"
hermes gateway
```

### 4. Railway Deployment

1. **Create the service** in the `stellar-rebirth` project:
   ```bash
   railway service create
   ```

2. **Connect to GitHub:** Point to the forked repo with the Signal AI changes

3. **Attach persistent volume:** Railway UI → Variables → add volume at `/opt/data`

4. **Set environment variables:** Copy all values from section 2 above

5. **Configure the service:**
   - Runtime: Docker
   - Build: Dockerfile (auto-detected)
   - Start command: `hermes gateway`

6. **Deploy:** Railway automatically builds and deploys on git push

---

## How to Use

### Daily Automated Discovery

The bot runs a scheduled discovery job daily. To enable:

1. Open a Telegram conversation with your bot
2. Send: `/cronjob schedule --name signal-discovery --every 1d --skill signal-creator-discovery`

The agent will:
1. Fetch all niche clusters and rotation status
2. Pick the 3 least-recently-searched niches
3. Search for creators using specific keywords from each niche
4. Log results to the database
5. Post a formatted discovery report to the group

### Ad-hoc Searches

You can request discoveries anytime in Telegram:

- **"Find creators in crypto right now"** → Agent searches crypto niche immediately
- **"What niches haven't been searched this week?"** → Agent checks rotation status
- **"Run a full rotation of 5 niches"** → Agent searches 5 least-recent niches
- **"How many new creators did we find this month?"** → Agent queries the database

All tools are available 24/7, not just during scheduled runs.

### Telegram Command Reference

```
/start                    - Initialize the bot
/help                     - Show available commands
/cronjob                  - Manage scheduled tasks
/skill_view signal-creator-discovery  - Show discovery workflow
```

### Interpreting Discovery Reports

The daily report format:

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

**Fields:**
- **username** — Creator's Instagram handle
- **followers** — Follower count (approximate)
- **verified** — Checkmark if verified account
- **NEW** — First time discovered in this niche
- **seen Nx before** — Number of prior searches in any niche
- **Reel metrics** — Engagement from the reel that surfaced the creator
- **Credits remaining** — ScrapeCreators account balance

---

## Troubleshooting

### Database Connection Errors

**Error:** `SIGNAL_DATABASE_URL is not set`

**Fix:**
1. Verify the env var is set on the Railway service
2. Check that it uses the pooler endpoint (contains `-pooler`)
3. Confirm the `hermes_agent` role has the correct password

**Error:** `could not connect to server`

**Fix:**
1. Verify the Neon endpoint is correct (check Neon Dashboard)
2. Confirm the role exists: `SELECT 1 FROM pg_roles WHERE rolname='hermes_agent'`
3. Test connectivity: `psql "${SIGNAL_DATABASE_URL}" -c "SELECT 1"`

### ScrapeCreators API Errors

**Error:** `SCRAPECREATORS_API_KEY is not set`

**Fix:**
1. Verify the env var is set on the Railway service
2. Confirm the API key is valid (not expired or revoked)
3. Check your account balance in the ScrapeCreators dashboard

**Error:** `credits_remaining: 0`

**Fix:**
1. Recharge your ScrapeCreators account
2. The bot will pause searches until credits are available
3. Check the Telegram report for the remaining balance

### Telegram Delivery Issues

**Error:** Bot doesn't respond to messages

**Fix:**
1. Verify `TELEGRAM_BOT_TOKEN` is correct
2. Verify the bot is added to the chat group
3. Check that your user ID is in `TELEGRAM_ALLOWED_USERS`
4. Use `@userinfobot` to confirm your Telegram user ID

**Error:** Reports not appearing at scheduled times

**Fix:**
1. Verify the cron schedule was created: `/cronjob list`
2. Check the logs: `railway logs` or Telegram `/help`
3. Confirm the skill exists: `/skill_view signal-creator-discovery`

### Cache/Niche Data Issues

**Error:** `No niche clusters found in cache`

**Fix:**
1. The `niche_cluster_cache` table should be populated by Signal AI's clustering job
2. Manually insert test data if the job hasn't run recently:
   ```sql
   INSERT INTO niche_cluster_cache (key, value) VALUES ('current', '{"clusters":[{"name":"fitness","keywords":["workout","gym"]}]}');
   ```

---

## Performance & Monitoring

### Credit Usage

Each `search_instagram_creators` call costs 1 ScrapeCreators credit:

- **Daily run (default):** 3 niches × 2 keywords = 6 credits
- **Monthly:** ~180 credits
- **Annual:** ~2,160 credits

Monitor remaining credits in:
1. ScrapeCreators dashboard (live balance)
2. Telegram discovery reports (shows remaining after each run)

### Database Monitoring

Key tables to monitor:

```sql
-- Last 10 searches
SELECT niche_name, MAX(searched_at) as last_searched, COUNT(*) as searches
FROM rotation_tracker
GROUP BY niche_name
ORDER BY last_searched DESC LIMIT 10;

-- Unique creators discovered
SELECT niche_name, COUNT(DISTINCT username) as unique_creators
FROM discovered_creators
GROUP BY niche_name;

-- Most-seen creators (returning visitors)
SELECT username, niche_name, times_seen, last_seen_at
FROM discovered_creators
WHERE times_seen > 1
ORDER BY times_seen DESC LIMIT 20;
```

### Container Logs

View logs in Railway dashboard or CLI:

```bash
railway logs --tail 100
```

Look for patterns like:
- `search_instagram_creators` execution time
- Neon HTTP API response times
- Telegram message delivery status

---

## Security & Permissions

### Least-Privilege Database Access

The `hermes_agent` role has minimal permissions:
- **SELECT** on `niche_cluster_cache` — read-only niche definitions
- **SELECT, INSERT, UPDATE** on `rotation_tracker` and `discovered_creators` — write new discoveries only
- **No DELETE, TRUNCATE, or DDL** — audit trail is immutable

All access goes through the Neon HTTP API, not direct socket connections.

### Environment Variables

- **SIGNAL_DATABASE_URL** — Contains database credentials. Treat as a secret.
- **SCRAPECREATORS_API_KEY** — ScrapeCreators credentials. Treat as a secret.
- **OPENROUTER_API_KEY** — LLM credentials. Treat as a secret.
- **TELEGRAM_BOT_TOKEN** — Bot authentication. Treat as a secret.

All are stored securely in Railway's encrypted config and never exposed in logs.

### Audit Trail

Every discovery operation is logged:
1. Search event recorded in `rotation_tracker` (immutable insert)
2. Creator discovery recorded in `discovered_creators` (with first_seen_at timestamp)
3. All timestamps in UTC timezone (Postgres `TIMESTAMPTZ`)

---

## Extending the Integration

### Adding More Tools

To add additional tools (e.g., creator scoring, outreach):

1. Add a new function to `tools/signal_creators.py`
2. Define its OpenAI schema
3. Register it via `registry.register()`
4. Add the tool name to `_HERMES_CORE_TOOLS` in `toolsets.py`
5. Reference it in the skill document

### Custom Report Formatting

The agent uses the `signal-creator-discovery` skill to format reports. To customize:

1. Edit `skills/marketing/signal-creator-discovery/SKILL.md`
2. Update the report format section
3. The skill is reloaded on agent restart (no code change needed)

### Changing the Discovery Schedule

To modify the daily schedule:

1. In Telegram: `/cronjob update --name signal-discovery --every <duration>`
2. Examples: `--every 12h` (twice daily), `--every 1w` (weekly), `--every 3d` (every 3 days)

---

## Support & Documentation

- **Design Spec:** `docs/superpowers/specs/2026-04-07-hermes-signal-ai-creator-discovery-design.md`
- **Implementation Plan:** `docs/superpowers/plans/2026-04-07-hermes-signal-ai-creator-discovery.md`
- **Agent Skill:** `skills/marketing/signal-creator-discovery/SKILL.md`
- **Tool Source:** `tools/signal_creators.py`
- **Unit Tests:** `tests/test_signal_creators.py`

For issues or feature requests, file an issue on the GitHub fork.

---

## Version History

- **2026-04-07** — Initial release. 4 tools, Neon HTTP API, ScrapeCreators integration, Telegram delivery.
