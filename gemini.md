# 🏛️ gemini.md — Project Constitution

> **This file is law.** All schemas, behavioral rules, and architectural invariants are defined here.
> Only update this file when: a schema changes, a rule is added, or architecture is modified.

---

## 📋 Project Identity

| Field | Value |
|---|---|
| **Project Name** | Scraperrr |
| **Protocol** | B.L.A.S.T. (Blueprint → Link → Architect → Stylize → Trigger) |
| **Architecture** | A.N.T. 3-Layer (Architecture / Navigation / Tools) |
| **System Pilot** | Antigravity |
| **Initialized** | 2026-03-04 |
| **Status** | 🟢 BLUEPRINT APPROVED — BUILDING |

---

## 🎯 North Star

> **Deliver a beautiful, interactive dashboard that aggregates the latest AI news (last 24h) from Ben's Bites, The AI Rundown, and Reddit into one unified view — with persistent article saving via localStorage, auto-refresh every 24 hours, and a future Supabase backend.**

---

## 🗂️ Data Schema

> **STATUS: LOCKED ✅ — Approved 2026-03-04**

### Article Object (Core Entity)
```json
{
  "id": "sha256_hash_of_url",
  "title": "Article or Post Title",
  "summary": "One-sentence or short paragraph summary",
  "url": "https://full-source-url.com/article",
  "published_at": "2026-03-04T08:00:00Z",
  "source": "Ben's Bites | The AI Rundown | Reddit",
  "source_icon": "emoji or icon identifier",
  "tags": ["AI", "LLM", "Agents"],
  "image_url": "https://optional-thumbnail.jpg | null",
  "reddit_score": 1234,
  "reddit_comments": 56,
  "is_saved": false
}
```

### Scraper Output Schema (`.tmp/articles.json`)
```json
{
  "scraped_at": "2026-03-04T12:00:00Z",
  "sources_checked": ["Ben's Bites", "The AI Rundown", "Reddit/r/artificial"],
  "total_articles": 42,
  "articles": [ /* Array of Article Objects */ ]
}
```

### localStorage Payload Schema (Client-side persistence)
```json
{
  "last_fetched": "2026-03-04T12:00:00Z",
  "articles": [ /* Array of Article Objects */ ],
  "saved_ids": ["sha256_id_1", "sha256_id_2"]
}
```

---

## 📐 Architectural Invariants

1. No scripts in `tools/` may be written until the Data Schema above is populated and approved. ✅ DONE
2. All intermediate data lives in `.tmp/` — never committed.
3. Environment variables and API keys live exclusively in `.env`.
4. If logic changes, the corresponding SOP in `architecture/` is updated **before** the code.
5. A project is only "Complete" when the payload reaches its final cloud destination (Supabase — Phase 2).
6. The dashboard is self-contained HTML/CSS/JS — no build tools required in Phase 1.
7. The scraper (`tools/scraper.py`) must be runnable as a standalone script.
8. Deduplication: Articles are identified by SHA-256 hash of their URL — never store duplicates.
9. Time filter: Only articles published within the last 24 hours are surfaced.

---

## 🚦 Behavioral Rules

1. **24-hour freshness gate:** Only display articles published within the last 24 hours.
2. **Deduplication:** Use URL hash as unique ID — never show the same article twice.
3. **Persistence:** User's saved articles survive page refresh via localStorage.
4. **Silent failure:** If a source fails to load, log the error and continue with other sources. Never crash the dashboard.
5. **No polling overload:** Auto-refresh triggers a new scrape at most once every 24 hours.
6. **Saved > Unsaved:** Saved articles are always pinned above the feed, sorted by save time (newest first).
7. **Source labeling:** Every article must display its source name and icon — never anonymous content.
8. **Mobile-responsive:** Dashboard must be usable on mobile screens (min-width: 320px).

---

## 🔧 Integrations Registry

| Service | Status | Key Location | Notes |
|---|---|---|---|
| Ben's Bites (Substack RSS) | ✅ Confirmed | No key needed | `https://bensbites.substack.com/feed` |
| The AI Rundown (Beehiiv RSS) | ✅ Confirmed | No key needed | `https://rss.beehiiv.com/feeds/2R3C6Bt5wj.xml` |
| Reddit (PRAW / JSON API) | 🟡 Needs credentials | `.env` → `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | Subreddits: r/artificial, r/MachineLearning |
| Supabase | ⬜ Phase 2 — Not yet | `.env` → `SUPABASE_URL`, `SUPABASE_KEY` | Future cloud persistence |

---

## 📁 File Structure

```
Scraperrr/
├── gemini.md              # Project Constitution (this file)
├── task_plan.md           # Phase tracker and checklists
├── findings.md            # Research log
├── progress.md            # Execution log
├── .env                   # API Keys/Secrets
├── architecture/
│   └── scraper_sop.md    # SOP for the scraper tool
├── tools/
│   └── scraper.py        # Python scraper (RSS feeds + Reddit)
├── dashboard/
│   ├── index.html        # Main dashboard page
│   ├── style.css         # Design system
│   └── app.js            # Dashboard logic + localStorage
└── .tmp/
    └── articles.json      # Scraper output (ephemeral)
```

---

## 📜 Maintenance Log

| Date | Change | Author |
|---|---|---|
| 2026-03-04 | Project Constitution initialized | System Pilot |
| 2026-03-04 | Data Schema locked — Blueprint approved | System Pilot |
| 2026-03-04 | All source URLs confirmed (RSS + PRAW) | System Pilot |
