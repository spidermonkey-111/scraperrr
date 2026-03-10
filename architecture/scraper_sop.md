# 🏗️ Scraper SOP — Standard Operating Procedure

> Layer 1 document. Update this BEFORE changing `tools/scraper.py`.

---

## 🎯 Goal
Collect the latest AI articles (last 24 hours) from:
1. **Ben's Bites** — via Substack RSS feed
2. **The AI Rundown** — via Beehiiv RSS feed
3. **Reddit** — via PRAW API (r/artificial, r/MachineLearning)

Output a single structured JSON file to `.tmp/articles.json`.

---

## 📥 Inputs

| Input | Type | Source |
|---|---|---|
| RSS Feed URLs | Config (hardcoded) | See Integration Registry in `gemini.md` |
| Reddit Credentials | `.env` file | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` |
| Time Window | Config | Last 24 hours from script execution time |

---

## 📤 Output

**File:** `.tmp/articles.json`

**Schema:** See `gemini.md` → Scraper Output Schema

---

## ⚙️ Tool Logic (Step-by-Step)

### Step 1: Load Configuration
- Read `.env` for Reddit credentials
- Define RSS feed URLs as constants
- Set `NOW = datetime.utcnow()` — the 24h window anchor

### Step 2: Scrape Ben's Bites RSS
- Fetch `https://bensbites.substack.com/feed` using `feedparser`
- For each entry:
  - Parse `published_parsed` → convert to UTC datetime
  - Filter: skip if older than 24h
  - Extract: title, link, summary (strip HTML), pub date
  - Generate `id` = SHA-256 hash of the URL
  - Append Article Object to results list

### Step 3: Scrape The AI Rundown RSS
- Fetch `https://rss.beehiiv.com/feeds/2R3C6Bt5wj.xml` using `feedparser`
- Same logic as Step 2

### Step 4: Scrape Reddit (PRAW)
- Connect to Reddit using `praw.Reddit(...)` with env credentials
- For each subreddit in `["artificial", "MachineLearning"]`:
  - Fetch `subreddit.top(time_filter="day", limit=25)`
  - Filter: skip if `post.created_utc` older than 24h
  - Extract: title, url, selftext (first 200 chars as summary), score, num_comments
  - Generate `id` = SHA-256 hash of the post URL
  - Tag with source `"Reddit/r/{subreddit}"`

### Step 5: Deduplicate
- Build a dict keyed by `article["id"]`
- If duplicate id encountered, keep the one with the higher reddit_score (or whichever came first for non-Reddit)

### Step 6: Write Output
- Assemble final JSON object matching the Scraper Output Schema
- Write to `.tmp/articles.json` (create `.tmp/` if not exists)
- Log summary to console: sources checked, total articles, time taken

---

## ⚠️ Error Handling

| Scenario | Behavior |
|---|---|
| RSS feed unreachable | Log warning, skip source, continue |
| Reddit credentials missing | Log warning, skip Reddit, continue |
| Reddit API rate limit | Catch `praw.exceptions.APIException`, wait + retry once, then skip |
| No articles found in 24h | Write empty `articles: []` — do not crash |
| Malformed date field | Skip that article, log the URL |

---

## 🔁 Self-Annealing Notes
*(Updated as bugs are found and fixed)*

| Date | Issue | Fix Applied |
|---|---|---|
| — | — | — |

---

## 🧪 How to Test

```bash
cd Scraperrr
python tools/scraper.py
# Expected: .tmp/articles.json created with >0 articles
# Expected: Console prints summary table
```
