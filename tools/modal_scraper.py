#!/usr/bin/env python3
"""
Scraperrr — tools/modal_scraper.py
====================================
Modal cloud job:
  • Scheduled: runs every day at 07:00 UTC (scrape_and_push)
  • On-demand:  HTTP GET /trigger → scrapes + returns fresh JSON
                Called by the dashboard Refresh button on Vercel.

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

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "feedparser>=6.0.11",
        "praw>=7.7.1",
        "requests>=2.31.0",
        "fastapi>=0.110.0",
    )
)

modal_secrets = modal.Secret.from_name("scraperrr-secrets")

# ── Constants ─────────────────────────────────────────────────────────────────
RSS_SOURCES = [
    {"name": "Ben's Bites",    "url": "https://bensbites.substack.com/feed",          "icon": "🍪", "tags": ["AI", "Newsletter"]},
    {"name": "The AI Rundown", "url": "https://rss.beehiiv.com/feeds/2R3C6Bt5wj.xml", "icon": "⚡", "tags": ["AI", "Newsletter"]},
]
REDDIT_SUBREDDITS  = ["artificial", "MachineLearning"]
REDDIT_POST_LIMIT  = 25
TIME_WINDOW_HOURS  = 168
GITHUB_FILE_PATH   = "dashboard/articles.json"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger("scraperrr")


def sha256_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def strip_html(text: str) -> str:
    clean = re.sub(r"<[^>]+>", "", text or "")
    return clean.strip()[:500]


def extract_first_image(html: str) -> Optional[str]:
    """Pull the first <img src=...> out of raw HTML (newsletter content)."""
    if not html:
        return None
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
    return m.group(1) if m else None


def is_within_window(pub_dt: datetime, hours: int = TIME_WINDOW_HOURS) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    if pub_dt.tzinfo is None:
        pub_dt = pub_dt.replace(tzinfo=timezone.utc)
    return pub_dt >= cutoff


def feedparser_date_to_dt(time_struct) -> Optional[datetime]:
    if time_struct is None:
        return None
    try:
        return datetime.fromtimestamp(time.mktime(time_struct), tz=timezone.utc)
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
    import feedparser
    log = logging.getLogger("scraperrr.rss")
    articles = []
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
            # 1. media:thumbnail tag (some feeds)
            media = entry.get("media_thumbnail", [])
            if media:
                article["image_url"] = media[0].get("url")
            # 2. enclosure / link with image mime type
            if not article["image_url"]:
                for lnk in entry.get("links", []):
                    if lnk.get("type", "").startswith("image"):
                        article["image_url"] = lnk.get("href")
                        break
            # 3. first <img> inside RSS HTML content (newsletters)
            if not article["image_url"]:
                raw_html = entry.get("summary", "") or (
                    entry.get("content", [{}])[0].get("value", "")
                )
                article["image_url"] = extract_first_image(raw_html)
            articles.append(article)
        except Exception:
            continue

    log.info(f"  ✓ {len(articles)} articles")
    return articles


def _scrape_reddit() -> list[dict]:
    import praw
    log = logging.getLogger("scraperrr.reddit")
    articles = []
    client_id     = os.environ.get("REDDIT_CLIENT_ID", "")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "")
    user_agent    = os.environ.get("REDDIT_USER_AGENT", "Scraperrr/1.0")

    if not client_id or client_id == "your_reddit_client_id_here":
        log.warning("Reddit creds not set — skipping.")
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
    import requests
    log = logging.getLogger("scraperrr.github")
    token    = os.environ["GITHUB_TOKEN"]
    repo     = os.environ["GITHUB_REPO"]
    api_url  = f"https://api.github.com/repos/{repo}/contents/{GITHUB_FILE_PATH}"
    headers  = {
        "Authorization":        f"token {token}",
        "Accept":               "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    sha = None
    r = requests.get(api_url, headers=headers, timeout=15)
    if r.status_code == 200:
        sha = r.json().get("sha")
    elif r.status_code != 404:
        r.raise_for_status()

    body: dict = {
        "message": f"chore: auto-update articles [{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}]",
        "content": base64.b64encode(
            json.dumps(payload, indent=2, ensure_ascii=False).encode()
        ).decode("ascii"),
        "branch":  "main",
    }
    if sha:
        body["sha"] = sha

    r = requests.put(api_url, headers=headers, json=body, timeout=30)
    r.raise_for_status()
    log.info(f"  ✅ Pushed {payload['total_articles']} articles → GitHub ({GITHUB_FILE_PATH})")


# ── Core scrape logic (shared by both functions) ──────────────────────────────

def _run_scrape() -> dict:
    log = _setup_logging()
    start = time.time()
    log.info("🚀 Scraperrr — Starting scrape")

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

    log.info(f"📦 {len(unique)} unique articles, pushing to GitHub...")
    _push_to_github(payload)
    log.info(f"✅ Done in {time.time() - start:.1f}s")
    return payload


# ── 1. Scheduled job — runs daily at 07:00 UTC ───────────────────────────────

@app.function(
    image=image,
    secrets=[modal_secrets],
    schedule=modal.Cron("0 7 * * *"),
    timeout=300,
)
def scrape_and_push():
    """Daily cron: scrape + push to GitHub."""
    _run_scrape()


# ── 2. Web endpoint — Refresh button on Vercel calls this ─────────────────────

@app.function(
    image=image,
    secrets=[modal_secrets],
    timeout=300,
)
@modal.web_endpoint(method="GET", label="trigger")
def trigger_scrape():
    """
    On-demand HTTP endpoint. Dashboard Refresh button calls this.
    Returns full articles payload so the dashboard can update immediately
    without waiting for a Vercel redeploy.
    CORS headers allow calls from any Vercel domain.
    """
    from fastapi.responses import JSONResponse
    payload = _run_scrape()
    return JSONResponse(
        content={"ok": True, **payload},
        headers={"Access-Control-Allow-Origin": "*"},
    )


# ── Local smoke-test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    _setup_logging()
    log = logging.getLogger("scraperrr")
    log.info("Local mode — scraping RSS only (no Reddit, no GitHub push)")
    articles = []
    for s in RSS_SOURCES:
        articles.extend(_scrape_rss(s))
    log.info(f"Total: {len(articles)} articles")
