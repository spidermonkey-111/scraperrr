#!/usr/bin/env python3
"""
Scraperrr — tools/modal_scraper.py
====================================
Modal cloud job: runs the scraper every 24 hours and pushes the
resulting articles.json to GitHub so Vercel always serves fresh data.

Deploy:   python -m modal deploy tools/modal_scraper.py
Run now:  python -m modal run tools/modal_scraper.py::scrape_and_push
Logs:     https://modal.com/apps/scraperrr-scraper
"""

import base64
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import modal

# ── Modal App ─────────────────────────────────────────────────────────────────
app = modal.App("scraperrr-scraper")

# Docker image with all required deps
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "feedparser>=6.0.11",
        "praw>=7.7.1",
        "requests>=2.31.0",
    )
)

# ── Secrets (set these in Modal dashboard → Secrets) ──────────────────────────
# Required:  GITHUB_TOKEN   — fine-grained PAT with Contents: Read & Write
# Required:  GITHUB_REPO    — e.g.  spidermonkey-111/scraperrr
# Optional:  REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
modal_secrets = modal.Secret.from_name("scraperrr-secrets")


# ── Constants (same as scraper.py) ────────────────────────────────────────────
RSS_SOURCES = [
    {"name": "Ben's Bites",    "url": "https://bensbites.substack.com/feed",          "icon": "🍪", "tags": ["AI", "Newsletter"]},
    {"name": "The AI Rundown", "url": "https://rss.beehiiv.com/feeds/2R3C6Bt5wj.xml", "icon": "⚡", "tags": ["AI", "Newsletter"]},
]
REDDIT_SUBREDDITS  = ["artificial", "MachineLearning"]
REDDIT_POST_LIMIT  = 25
TIME_WINDOW_HOURS  = 168   # 7 days — newsletters publish a few times per week
GITHUB_FILE_PATH   = "dashboard/articles.json"   # path inside the repo


# ── Helpers ───────────────────────────────────────────────────────────────────

def sha256_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def strip_html(text: str) -> str:
    clean = re.sub(r"<[^>]+>", "", text or "")
    return clean.strip()[:500]


def is_within_window(pub_dt: datetime, hours: int = TIME_WINDOW_HOURS) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    if pub_dt.tzinfo is None:
        pub_dt = pub_dt.replace(tzinfo=timezone.utc)
    return pub_dt >= cutoff


def feedparser_date_to_dt(time_struct) -> Optional[datetime]:
    if time_struct is None:
        return None
    try:
        ts = time.mktime(time_struct)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        return None


def deduplicate(articles: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for a in articles:
        if a["id"] not in seen:
            seen[a["id"]] = a
    return list(seen.values())


# ── Scrapers ──────────────────────────────────────────────────────────────────

def _scrape_rss(source: dict) -> list[dict]:
    import feedparser  # inside image
    articles = []
    log = logging.getLogger("scraperrr.rss")
    log.info(f"RSS → {source['name']}")
    try:
        feed = feedparser.parse(source["url"])
        if feed.bozo and not feed.entries:
            raise ValueError(feed.bozo_exception)
    except Exception as e:
        log.warning(f"  ✗ {source['name']}: {e}")
        return []

    for entry in feed.entries:
        try:
            pub_dt = feedparser_date_to_dt(
                entry.get("published_parsed") or entry.get("updated_parsed")
            )
            if pub_dt is None or not is_within_window(pub_dt):
                continue
            url = entry.get("link", "")
            if not url:
                continue
            summary_raw = entry.get("summary", "") or (
                entry.get("content", [{}])[0].get("value", "")
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
            media = entry.get("media_thumbnail", [])
            if media:
                article["image_url"] = media[0].get("url")
            articles.append(article)
        except Exception:
            continue

    log.info(f"  ✓ {len(articles)} articles")
    return articles


def _scrape_reddit() -> list[dict]:
    import praw  # inside image
    log = logging.getLogger("scraperrr.reddit")
    articles = []

    client_id     = os.environ.get("REDDIT_CLIENT_ID", "")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "")
    user_agent    = os.environ.get("REDDIT_USER_AGENT", "Scraperrr/1.0")

    if not client_id or client_id == "your_reddit_client_id_here":
        log.warning("Reddit creds not set — skipping Reddit.")
        return []

    try:
        reddit = praw.Reddit(client_id=client_id, client_secret=client_secret, user_agent=user_agent)
    except Exception as e:
        log.warning(f"Reddit connect failed: {e}")
        return []

    for sub_name in REDDIT_SUBREDDITS:
        log.info(f"Reddit → r/{sub_name}")
        try:
            for post in reddit.subreddit(sub_name).top(time_filter="day", limit=REDDIT_POST_LIMIT):
                pub_dt = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
                if not is_within_window(pub_dt):
                    continue
                url = post.url
                summary = post.selftext[:500].strip() if post.selftext else f"Score: {post.score} | Comments: {post.num_comments}"
                articles.append({
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
                })
        except Exception as e:
            log.warning(f"  ✗ r/{sub_name}: {e}")

    log.info(f"  ✓ {len(articles)} Reddit posts")
    return articles


# ── GitHub Push ───────────────────────────────────────────────────────────────

def _push_to_github(payload: dict) -> None:
    """Commit articles.json to GitHub via the Contents API."""
    import requests  # inside image
    log = logging.getLogger("scraperrr.github")

    token = os.environ["GITHUB_TOKEN"]
    repo  = os.environ["GITHUB_REPO"]   # e.g. spidermonkey-111/scraperrr
    path  = GITHUB_FILE_PATH

    api_url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept":        "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Get current file SHA (required for updates)
    sha = None
    r = requests.get(api_url, headers=headers, timeout=15)
    if r.status_code == 200:
        sha = r.json().get("sha")
        log.info(f"  Existing file SHA: {sha[:8]}...")
    elif r.status_code != 404:
        r.raise_for_status()

    content_b64 = base64.b64encode(
        json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")

    body: dict = {
        "message": f"chore: auto-update articles.json [{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}]",
        "content": content_b64,
        "branch":  "main",
    }
    if sha:
        body["sha"] = sha

    r = requests.put(api_url, headers=headers, json=body, timeout=30)
    r.raise_for_status()
    log.info(f"  ✅ Pushed {payload['total_articles']} articles to GitHub ({repo}/{path})")


# ── Modal Scheduled Function ───────────────────────────────────────────────────

@app.function(
    image=image,
    secrets=[modal_secrets],
    schedule=modal.Cron("0 7 * * *"),   # 07:00 UTC daily (adjust to taste)
    timeout=300,
)
def scrape_and_push():
    """Runs every 24 hours: scrape RSS + Reddit → push articles.json to GitHub."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("scraperrr")
    start = time.time()

    log.info("=" * 60)
    log.info("🚀 Scraperrr Modal Job — Starting")
    log.info(f"   Time window: last {TIME_WINDOW_HOURS}h")
    log.info("=" * 60)

    all_articles: list[dict] = []
    sources_checked: list[str] = []

    for source in RSS_SOURCES:
        all_articles.extend(_scrape_rss(source))
        sources_checked.append(source["name"])

    reddit_articles = _scrape_reddit()
    all_articles.extend(reddit_articles)
    for sub in REDDIT_SUBREDDITS:
        sources_checked.append(f"Reddit/r/{sub}")

    unique = deduplicate(all_articles)
    unique.sort(key=lambda a: a["published_at"], reverse=True)

    payload = {
        "scraped_at":      datetime.now(timezone.utc).isoformat(),
        "sources_checked": sources_checked,
        "total_articles":  len(unique),
        "articles":        unique,
    }

    log.info(f"📦 {len(unique)} unique articles from {len(sources_checked)} sources")

    _push_to_github(payload)

    elapsed = time.time() - start
    log.info(f"✅ Done in {elapsed:.1f}s")


# ── Local entry-point ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Quick local smoke-test (does NOT push to GitHub)
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger("scraperrr")
    log.info("Running locally (no GitHub push)...")
    articles = []
    for s in RSS_SOURCES:
        articles.extend(_scrape_rss(s))
    log.info(f"Total: {len(articles)} articles (Reddit skipped in local mode)")
