#!/usr/bin/env python3
"""
Scraperrr — tools/scraper.py
=============================
Layer 3 Tool: Deterministic Python scraper.
Fetches latest AI news from RSS feeds and Reddit,
outputs structured JSON to .tmp/articles.json.

Run: python tools/scraper.py
"""

import os
import json
import hashlib
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from pathlib import Path

import feedparser
from dotenv import load_dotenv

# ── Optional Reddit import (graceful fallback if PRAW not installed) ──────────
try:
    import praw
    PRAW_AVAILABLE = True
except ImportError:
    PRAW_AVAILABLE = False

# ── Setup ─────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("scraperrr")

# Load .env from project root (one level up from tools/)
ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

TMP_DIR = ROOT / ".tmp"
OUTPUT_FILE = TMP_DIR / "articles.json"

# ── Constants ─────────────────────────────────────────────────────────────────
RSS_SOURCES = [
    {
        "name": "Ben's Bites",
        "url": "https://bensbites.substack.com/feed",
        "icon": "🍪",
        "tags": ["AI", "Newsletter"],
    },
    {
        "name": "The AI Rundown",
        "url": "https://rss.beehiiv.com/feeds/2R3C6Bt5wj.xml",
        "icon": "⚡",
        "tags": ["AI", "Newsletter"],
    },
]

REDDIT_SUBREDDITS = ["artificial", "MachineLearning"]
REDDIT_POST_LIMIT = 25
TIME_WINDOW_HOURS = 168  # 7 days — newsletters publish a few times per week


# ── Helpers ───────────────────────────────────────────────────────────────────

def sha256_id(url: str) -> str:
    """Generate a stable unique ID from a URL."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def strip_html(text: str) -> str:
    """Remove HTML tags from a string (simple regex-free version)."""
    import re
    clean = re.sub(r"<[^>]+>", "", text or "")
    return clean.strip()[:500]  # cap summary length


def is_within_window(pub_dt: datetime, hours: int = TIME_WINDOW_HOURS) -> bool:
    """Return True if the datetime is within the last N hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    if pub_dt.tzinfo is None:
        pub_dt = pub_dt.replace(tzinfo=timezone.utc)
    return pub_dt >= cutoff


def feedparser_date_to_dt(time_struct) -> Optional[datetime]:
    """Convert feedparser's time.struct_time to a UTC-aware datetime."""
    if time_struct is None:
        return None
    try:
        ts = time.mktime(time_struct)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        return None


# ── Scrapers ──────────────────────────────────────────────────────────────────

def scrape_rss(source: dict) -> list[dict]:
    """Fetch and parse an RSS feed, returning Article Objects."""
    articles = []
    log.info(f"Fetching RSS: {source['name']} ({source['url']})")

    try:
        feed = feedparser.parse(source["url"])
        if feed.bozo and not feed.entries:
            raise ValueError(f"Feed parse error: {feed.bozo_exception}")
        log.info(f"  → {len(feed.entries)} entries found")
    except Exception as e:
        log.warning(f"  ✗ Failed to fetch {source['name']}: {e}")
        return []

    for entry in feed.entries:
        try:
            pub_dt = feedparser_date_to_dt(
                entry.get("published_parsed") or entry.get("updated_parsed")
            )
            if pub_dt is None:
                log.debug(f"  Skipping (no date): {entry.get('link', '?')}")
                continue
            if not is_within_window(pub_dt):
                continue

            url = entry.get("link", "")
            if not url:
                continue

            summary_raw = (
                entry.get("summary", "")
                or entry.get("content", [{}])[0].get("value", "")
            )

            article = {
                "id": sha256_id(url),
                "title": entry.get("title", "Untitled").strip(),
                "summary": strip_html(summary_raw),
                "url": url,
                "published_at": pub_dt.isoformat(),
                "source": source["name"],
                "source_icon": source["icon"],
                "tags": source["tags"].copy(),
                "image_url": None,
                "reddit_score": None,
                "reddit_comments": None,
                "is_saved": False,
            }

            # Try to extract a thumbnail image
            media = entry.get("media_thumbnail", [])
            if media:
                article["image_url"] = media[0].get("url")
            elif entry.get("links"):
                for lnk in entry.get("links", []):
                    if lnk.get("type", "").startswith("image"):
                        article["image_url"] = lnk.get("href")
                        break

            articles.append(article)
        except Exception as e:
            log.debug(f"  Skipping malformed entry: {e}")
            continue

    log.info(f"  ✓ {len(articles)} articles within {TIME_WINDOW_HOURS//24}-day window")
    return articles


def scrape_reddit() -> list[dict]:
    """Fetch top Reddit posts from AI subreddits using PRAW."""
    articles = []

    if not PRAW_AVAILABLE:
        log.warning("PRAW not installed. Skipping Reddit. Run: pip install praw")
        return []

    client_id = os.getenv("REDDIT_CLIENT_ID", "")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET", "")
    user_agent = os.getenv("REDDIT_USER_AGENT", "Scraperrr/1.0")

    if not client_id or client_id == "your_reddit_client_id_here":
        log.warning("Reddit credentials not set in .env — skipping Reddit.")
        return []

    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
        log.info(f"Reddit API connected (read-only: {reddit.read_only})")
    except Exception as e:
        log.warning(f"Reddit connection failed: {e}")
        return []

    for sub_name in REDDIT_SUBREDDITS:
        log.info(f"Fetching r/{sub_name} top posts (day)...")
        try:
            subreddit = reddit.subreddit(sub_name)
            for post in subreddit.top(time_filter="day", limit=REDDIT_POST_LIMIT):
                try:
                    pub_dt = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
                    if not is_within_window(pub_dt):
                        continue

                    url = post.url
                    summary = post.selftext[:500].strip() if post.selftext else f"Score: {post.score} | Comments: {post.num_comments}"

                    article = {
                        "id": sha256_id(url),
                        "title": post.title.strip(),
                        "summary": summary,
                        "url": f"https://reddit.com{post.permalink}",
                        "published_at": pub_dt.isoformat(),
                        "source": f"Reddit/r/{sub_name}",
                        "source_icon": "🤖",
                        "tags": ["AI", "Reddit", sub_name],
                        "image_url": post.url if post.url.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")) else None,
                        "reddit_score": post.score,
                        "reddit_comments": post.num_comments,
                        "is_saved": False,
                    }
                    articles.append(article)
                except Exception as e:
                    log.debug(f"  Skipping post: {e}")
                    continue

            log.info(f"  ✓ r/{sub_name}: {sum(1 for a in articles if sub_name in a['source'])} posts")
        except Exception as e:
            log.warning(f"  ✗ Failed r/{sub_name}: {e}")
            continue

    return articles


# ── Deduplication ─────────────────────────────────────────────────────────────

def deduplicate(articles: list[dict]) -> list[dict]:
    """Remove duplicates by ID, preserving the first occurrence."""
    seen = {}
    for article in articles:
        aid = article["id"]
        if aid not in seen:
            seen[aid] = article
    return list(seen.values())


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    start = time.time()
    log.info("=" * 60)
    log.info("🚀 Scraperrr — Starting scrape run")
    log.info(f"   Time window: Last {TIME_WINDOW_HOURS} hours")
    log.info("=" * 60)

    all_articles = []
    sources_checked = []

    # RSS Sources
    for source in RSS_SOURCES:
        results = scrape_rss(source)
        all_articles.extend(results)
        sources_checked.append(source["name"])

    # Reddit
    reddit_articles = scrape_reddit()
    all_articles.extend(reddit_articles)
    for sub in REDDIT_SUBREDDITS:
        sources_checked.append(f"Reddit/r/{sub}")

    # Deduplicate
    unique_articles = deduplicate(all_articles)

    # Sort by published_at (newest first)
    unique_articles.sort(key=lambda a: a["published_at"], reverse=True)

    # Assemble output
    output = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "sources_checked": sources_checked,
        "total_articles": len(unique_articles),
        "articles": unique_articles,
    }

    # Write to .tmp/articles.json
    TMP_DIR.mkdir(exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    elapsed = time.time() - start
    log.info("=" * 60)
    log.info(f"✅ Done in {elapsed:.1f}s")
    log.info(f"   Sources:  {len(sources_checked)}")
    log.info(f"   Articles: {len(unique_articles)}")
    log.info(f"   Output:   {OUTPUT_FILE}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
