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
