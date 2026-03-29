"""
Live Data Ingestion Pipeline — Module 1.

Pulls posts from Reddit (PRAW), Twitter/X (tweepy), YouTube Data API v3,
and RSS feeds. Normalises all content into PostRecord objects and writes
them to the queue (JSONL file per entity for v1; Redis Streams later).

Rate-limit strategy:
  Reddit   : PRAW built-in limiter.  ≤500 posts/subreddit/run.
  Twitter  : 500k tweets/month (Basic).  IDs cached in DedupStore.
  YouTube  : 10k quota/day.  5k/day budgeted per entity.
  All      : Exponential backoff on 429/503, max 5 retries.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import feedparser
import requests as _requests

from app.config import Config
from app.models import PostRecord
from app.services.dedup_store import DedupStore
from app.utils.logger import get_logger

logger = get_logger("ingestion_service")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _anonymize(author_str: str) -> str:
    """One-way hash of author identifier (privacy layer)."""
    return hashlib.sha256(author_str.encode()).hexdigest()[:16]


def _with_backoff(fn: Callable, max_retries: int = 5):
    """
    Call fn with exponential backoff on transient errors (429, 5xx, network).
    Reads Retry-After header when available to honour platform rate limits.
    """
    base_delay = 1.0
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:
            if attempt == max_retries - 1:
                raise

            response = getattr(exc, "response", None)
            status_code = getattr(response, "status_code", None) if response else None

            # Only retry on transient / rate-limit codes
            if status_code and status_code not in (429, 500, 502, 503, 504):
                raise

            # Honour Retry-After header (Twitter, Reddit return this on 429)
            retry_after: float | None = None
            headers = getattr(response, "headers", {}) or {}
            raw = headers.get("Retry-After") or headers.get("retry-after")
            if raw:
                try:
                    retry_after = float(raw)
                except ValueError:
                    pass  # HTTP-date format — fall through to exponential

            wait = retry_after if retry_after is not None else base_delay * (2 ** attempt)
            logger.warning(
                f"Retryable error (attempt {attempt + 1}/{max_retries}): "
                f"{exc}. Retrying in {wait:.1f}s"
            )
            time.sleep(wait)


# ---------------------------------------------------------------------------
# IngestionService
# ---------------------------------------------------------------------------

class IngestionService:
    """
    Pulls live social data and normalises it into PostRecord objects.
    One instance per application; thread-safe.
    """

    def __init__(self, config: type[Config] = Config):
        self.config = config
        self._schedules: dict[str, threading.Thread] = {}
        self._schedule_stop: dict[str, threading.Event] = {}

    # ------------------------------------------------------------------
    # Reddit (RSS — no API key needed, 25 posts per feed)
    # ------------------------------------------------------------------

    def pull_reddit_rss(
        self,
        entity_id: str,
        subreddits: list[str],
        query: str | None = None,
        limit: int = 100,
    ) -> list[PostRecord]:
        """
        Pull Reddit posts via RSS feeds. No API key required.
        If query is provided, uses search RSS for entity-relevant posts.
        Supports multi-subreddit syntax (r/a+b+c).
        """
        import re
        import urllib.parse

        records: list[PostRecord] = []

        # Build feed URLs — batch subreddits in groups for multi-sub feeds
        feed_urls: list[str] = []
        if query:
            # Search across all subreddits combined
            multi = "+".join(s.strip() for s in subreddits if s.strip())
            if multi:
                q = urllib.parse.quote_plus(query)
                feed_urls.append(
                    f"https://www.reddit.com/r/{multi}/search.rss?q={q}&sort=new&restrict_sr=1"
                )
            else:
                q = urllib.parse.quote_plus(query)
                feed_urls.append(
                    f"https://www.reddit.com/search.rss?q={q}&sort=new"
                )
        else:
            # New posts from each subreddit (or combined)
            for sub in subreddits:
                sub = sub.strip()
                if sub:
                    feed_urls.append(f"https://www.reddit.com/r/{sub}/new/.rss")

        for url in feed_urls:
            try:
                resp = _requests.get(url, headers={"User-Agent": "pulse/1.0 (sentiment simulation)"}, timeout=15)
                feed = feedparser.parse(resp.content)
                if feed.bozo and not feed.entries:
                    logger.warning(f"Reddit RSS feed error for {url}: {feed.bozo_exception}")
                    continue

                for entry in feed.entries[:limit]:
                    # Clean HTML from summary
                    summary = entry.get("summary", "")
                    clean_text = re.sub(r"<[^>]+>", " ", summary).strip()
                    clean_text = re.sub(r"\s+", " ", clean_text)

                    title = entry.get("title", "")
                    content = f"{title}\n\n{clean_text}".strip() if clean_text else title

                    entry_id = entry.get("id", "")
                    # Reddit RSS ids look like "t3_xxxxx" — extract the post id
                    post_id = entry_id.split("/")[-1] if "/" in entry_id else entry_id

                    author = entry.get("author", entry.get("author_detail", {}).get("name", "unknown"))

                    published = entry.get("published_parsed")
                    if published:
                        created_at = datetime(*published[:6], tzinfo=timezone.utc)
                    else:
                        created_at = datetime.now(timezone.utc)

                    record = PostRecord(
                        id=f"reddit_rss:{post_id}",
                        platform="reddit",
                        entity_id=entity_id,
                        author_id=_anonymize(str(author)),
                        author_metadata={},
                        content=content,
                        parent_id=None,
                        created_at=created_at,
                        engagement={"likes": 0, "shares": 0, "replies": 0, "views": 0},
                        url=entry.get("link", url),
                        raw={"feed_url": url, "entry_id": entry_id},
                    )
                    records.append(record)

                logger.info(f"Reddit RSS {url}: pulled {len(feed.entries)} posts")
            except Exception as exc:
                logger.error(f"Reddit RSS {url} failed: {exc}")

        return records

    # ------------------------------------------------------------------
    # Reddit (PRAW — requires API key)
    # ------------------------------------------------------------------

    def pull_reddit(
        self,
        entity_id: str,
        subreddits: list[str],
        limit: int = 500,
    ) -> list[PostRecord]:
        """Pull hot + new posts from each subreddit using PRAW."""
        try:
            import praw
        except ImportError:
            logger.error("praw not installed — skipping Reddit pull")
            return []

        if not self.config.REDDIT_CLIENT_ID:
            logger.warning("REDDIT_CLIENT_ID not set — skipping Reddit pull")
            return []

        reddit = praw.Reddit(
            client_id=self.config.REDDIT_CLIENT_ID,
            client_secret=self.config.REDDIT_CLIENT_SECRET,
            user_agent=self.config.REDDIT_USER_AGENT,
        )

        records: list[PostRecord] = []
        per_sub = max(1, limit // max(len(subreddits), 1))

        for sub_name in subreddits:
            try:
                sub = reddit.subreddit(sub_name)
                fetched: list = []

                def _fetch():
                    hot = list(sub.hot(limit=per_sub // 2))
                    new_ = list(sub.new(limit=per_sub // 2))
                    return hot + new_

                submissions = _with_backoff(_fetch)

                seen_ids: set[str] = set()
                for post in submissions:
                    if post.id in seen_ids:
                        continue
                    seen_ids.add(post.id)

                    record = PostRecord(
                        id=f"reddit:{post.id}",
                        platform="reddit",
                        entity_id=entity_id,
                        author_id=_anonymize(str(post.author) if post.author else "deleted"),
                        author_metadata={
                            "karma": getattr(post.author, "link_karma", 0) if post.author else 0,
                            "flair": post.author_flair_text,
                        },
                        content=f"{post.title}\n\n{post.selftext}".strip(),
                        parent_id=None,
                        created_at=datetime.fromtimestamp(post.created_utc, tz=timezone.utc),
                        engagement={
                            "likes": post.score,
                            "shares": 0,
                            "replies": post.num_comments,
                            "views": 0,
                            "upvote_ratio": post.upvote_ratio,
                        },
                        url=f"https://reddit.com{post.permalink}",
                        raw={
                            "id": post.id,
                            "subreddit": sub_name,
                            "upvote_ratio": post.upvote_ratio,
                            "awards": post.total_awards_received,
                        },
                    )
                    records.append(record)

                logger.info(f"Reddit r/{sub_name}: pulled {len(seen_ids)} posts")
            except Exception as exc:
                logger.error(f"Reddit r/{sub_name} failed: {exc}")

        return records

    # ------------------------------------------------------------------
    # Twitter / X
    # ------------------------------------------------------------------

    def pull_twitter(
        self,
        entity_id: str,
        query: str,
        limit: int = 100,
    ) -> list[PostRecord]:
        """Pull recent tweets matching query using tweepy v4."""
        try:
            import tweepy
        except ImportError:
            logger.error("tweepy not installed — skipping Twitter pull")
            return []

        if not self.config.TWITTER_BEARER_TOKEN:
            logger.warning("TWITTER_BEARER_TOKEN not set — skipping Twitter pull")
            return []

        client = tweepy.Client(bearer_token=self.config.TWITTER_BEARER_TOKEN)
        records: list[PostRecord] = []

        try:
            def _fetch():
                return client.search_recent_tweets(
                    query=query,
                    max_results=min(limit, 100),
                    tweet_fields=["created_at", "author_id", "public_metrics", "referenced_tweets"],
                    user_fields=["public_metrics"],
                    expansions=["author_id"],
                )

            response = _with_backoff(_fetch)
            if not response or not response.data:
                return []

            users_by_id = {
                str(u.id): u for u in (response.includes.get("users") or [])
            }

            for tweet in response.data:
                author = users_by_id.get(str(tweet.author_id))
                metrics = tweet.public_metrics or {}
                record = PostRecord(
                    id=f"twitter:{tweet.id}",
                    platform="twitter",
                    entity_id=entity_id,
                    author_id=_anonymize(str(tweet.author_id)),
                    author_metadata={
                        "followers": author.public_metrics.get("followers_count", 0) if author and author.public_metrics else 0,
                    },
                    content=tweet.text,
                    parent_id=None,
                    created_at=tweet.created_at or datetime.now(timezone.utc),
                    engagement={
                        "likes": metrics.get("like_count", 0),
                        "shares": metrics.get("retweet_count", 0),
                        "replies": metrics.get("reply_count", 0),
                        "views": metrics.get("impression_count", 0),
                    },
                    url=f"https://twitter.com/i/web/status/{tweet.id}",
                    raw={"id": str(tweet.id), "metrics": metrics},
                )
                records.append(record)

            logger.info(f"Twitter query '{query}': pulled {len(records)} tweets")
        except Exception as exc:
            logger.error(f"Twitter pull failed: {exc}")

        return records

    # ------------------------------------------------------------------
    # YouTube
    # ------------------------------------------------------------------

    def pull_youtube(
        self,
        entity_id: str,
        video_ids: list[str],
        max_results: int = 100,
    ) -> list[PostRecord]:
        """Pull comments from YouTube videos using Data API v3."""
        try:
            from googleapiclient.discovery import build as yt_build
        except ImportError:
            logger.error("google-api-python-client not installed — skipping YouTube pull")
            return []

        if not self.config.YOUTUBE_API_KEY:
            logger.warning("YOUTUBE_API_KEY not set — skipping YouTube pull")
            return []

        yt = yt_build("youtube", "v3", developerKey=self.config.YOUTUBE_API_KEY)
        records: list[PostRecord] = []

        for video_id in video_ids:
            try:
                def _fetch():
                    return yt.commentThreads().list(
                        part="snippet",
                        videoId=video_id,
                        maxResults=min(max_results, 100),
                        textFormat="plainText",
                    ).execute()

                response = _with_backoff(_fetch)

                for item in response.get("items", []):
                    top = item["snippet"]["topLevelComment"]["snippet"]
                    record = PostRecord(
                        id=f"youtube:{item['id']}",
                        platform="youtube",
                        entity_id=entity_id,
                        author_id=_anonymize(top.get("authorChannelId", {}).get("value", "unknown")),
                        author_metadata={
                            "display_name": top.get("authorDisplayName", ""),
                        },
                        content=top.get("textDisplay", ""),
                        parent_id=f"youtube:video:{video_id}",
                        created_at=datetime.fromisoformat(
                            top["publishedAt"].replace("Z", "+00:00")
                        ),
                        engagement={
                            "likes": top.get("likeCount", 0),
                            "shares": 0,
                            "replies": item["snippet"].get("totalReplyCount", 0),
                            "views": 0,
                        },
                        url=f"https://youtube.com/watch?v={video_id}&lc={item['id']}",
                        raw={"video_id": video_id, "item_id": item["id"]},
                    )
                    records.append(record)

                logger.info(f"YouTube video {video_id}: pulled {len(response.get('items', []))} comments")
            except Exception as exc:
                logger.error(f"YouTube video {video_id} failed: {exc}")

        return records

    # ------------------------------------------------------------------
    # Hacker News (Algolia API — no key required)
    # ------------------------------------------------------------------

    def pull_hackernews(
        self,
        entity_id: str,
        queries: list[str],
        limit: int = 200,
    ) -> list[PostRecord]:
        """Pull stories and comments from Hacker News via Algolia Search API."""
        import urllib.parse

        records: list[PostRecord] = []
        per_query = max(1, limit // max(len(queries), 1))

        for query in queries:
            try:
                # Pull stories
                story_url = (
                    "https://hn.algolia.com/api/v1/search_by_date?"
                    + urllib.parse.urlencode({
                        "query": query,
                        "tags": "story",
                        "hitsPerPage": min(per_query // 2, 200),
                    })
                )
                story_resp = _requests.get(story_url, timeout=15).json()

                for hit in story_resp.get("hits", []):
                    content = hit.get("title", "")
                    story_text = hit.get("story_text") or ""
                    if story_text:
                        content = f"{content}\n\n{story_text}"

                    record = PostRecord(
                        id=f"hn:{hit['objectID']}",
                        platform="hackernews",
                        entity_id=entity_id,
                        author_id=_anonymize(hit.get("author", "unknown")),
                        author_metadata={"username": hit.get("author", "")},
                        content=content.strip(),
                        parent_id=None,
                        created_at=datetime.fromisoformat(
                            hit["created_at"].replace("Z", "+00:00")
                        ) if hit.get("created_at") else datetime.now(timezone.utc),
                        engagement={
                            "likes": hit.get("points") or 0,
                            "shares": 0,
                            "replies": hit.get("num_comments") or 0,
                            "views": 0,
                        },
                        url=hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}",
                        raw={"objectID": hit["objectID"], "source": "story"},
                    )
                    records.append(record)

                # Pull comments
                comment_url = (
                    "https://hn.algolia.com/api/v1/search_by_date?"
                    + urllib.parse.urlencode({
                        "query": query,
                        "tags": "comment",
                        "hitsPerPage": min(per_query // 2, 200),
                    })
                )
                comment_resp = _requests.get(comment_url, timeout=15).json()

                for hit in comment_resp.get("hits", []):
                    comment_text = hit.get("comment_text") or ""
                    if not comment_text:
                        continue

                    record = PostRecord(
                        id=f"hn:{hit['objectID']}",
                        platform="hackernews",
                        entity_id=entity_id,
                        author_id=_anonymize(hit.get("author", "unknown")),
                        author_metadata={"username": hit.get("author", "")},
                        content=comment_text.strip(),
                        parent_id=f"hn:{hit.get('story_id', '')}",
                        created_at=datetime.fromisoformat(
                            hit["created_at"].replace("Z", "+00:00")
                        ) if hit.get("created_at") else datetime.now(timezone.utc),
                        engagement={
                            "likes": hit.get("points") or 0,
                            "shares": 0,
                            "replies": 0,
                            "views": 0,
                        },
                        url=f"https://news.ycombinator.com/item?id={hit['objectID']}",
                        raw={
                            "objectID": hit["objectID"],
                            "story_id": hit.get("story_id"),
                            "story_title": hit.get("story_title", ""),
                            "source": "comment",
                        },
                    )
                    records.append(record)

                logger.info(f"HackerNews query '{query}': pulled {len(records)} items")
            except Exception as exc:
                logger.error(f"HackerNews query '{query}' failed: {exc}")

        return records

    # ------------------------------------------------------------------
    # RSS
    # ------------------------------------------------------------------

    def pull_rss(
        self,
        entity_id: str,
        feed_urls: list[str],
    ) -> list[PostRecord]:
        """Pull headlines + summaries from RSS feeds."""
        records: list[PostRecord] = []

        for url in feed_urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    published = entry.get("published_parsed")
                    if published:
                        created_at = datetime(*published[:6], tzinfo=timezone.utc)
                    else:
                        created_at = datetime.now(timezone.utc)

                    content = entry.get("summary") or entry.get("title", "")
                    entry_id = entry.get("id") or entry.get("link", "") or content[:64]

                    record = PostRecord(
                        id=f"rss:{hashlib.sha256(entry_id.encode()).hexdigest()[:16]}",
                        platform="rss",
                        entity_id=entity_id,
                        author_id=_anonymize(entry.get("author", url)),
                        author_metadata={"feed_url": url},
                        content=f"{entry.get('title', '')}\n\n{content}".strip(),
                        parent_id=None,
                        created_at=created_at,
                        engagement={"likes": 0, "shares": 0, "replies": 0, "views": 0},
                        url=entry.get("link", url),
                        raw={"feed_url": url},
                    )
                    records.append(record)

                logger.info(f"RSS {url}: pulled {len(feed.entries)} entries")
            except Exception as exc:
                logger.error(f"RSS {url} failed: {exc}")

        return records

    # ------------------------------------------------------------------
    # Amazon Reviews (via amazon-buddy npm package)
    # ------------------------------------------------------------------

    def pull_amazon_reviews(
        self,
        entity_id: str,
        asins: list[str],
        limit: int = 200,
    ) -> list[PostRecord]:
        """Pull product reviews from Amazon via amazon-buddy (Node subprocess)."""
        import subprocess as _sp

        records: list[PostRecord] = []
        per_asin = max(1, limit // max(len(asins), 1))

        for asin in asins:
            try:
                # Call amazon-buddy via Node one-liner
                script = (
                    f"const ab = require('amazon-buddy');"
                    f"ab.reviews({{asin:'{asin}',number:{per_asin},country:'US'}})"
                    f".then(r => console.log(JSON.stringify(r)))"
                    f".catch(e => {{ console.error(e); process.exit(1); }})"
                )
                result = _sp.run(
                    ["node", "-e", script],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode != 0:
                    logger.error(f"Amazon {asin}: node error: {result.stderr[:300]}")
                    continue

                data = json.loads(result.stdout)
                reviews = data if isinstance(data, list) else data.get("result", data.get("reviews", []))

                for rev in reviews:
                    rating = rev.get("rating", 3)
                    if isinstance(rating, str):
                        try: rating = float(rating.split(" ")[0])
                        except: rating = 3.0
                    # Map 1-5 stars → -1.0 to +1.0
                    sentiment = ((float(rating) - 1) / 4) * 2 - 1

                    title = rev.get("title", "")
                    body = rev.get("review", "") or rev.get("text", "")
                    content = f"{title}\n\n{body}".strip() if title else body.strip()
                    if not content:
                        continue

                    rev_id = rev.get("id") or hashlib.sha256(content[:100].encode()).hexdigest()[:16]
                    record = PostRecord(
                        id=f"amazon:{rev_id}",
                        platform="amazon",
                        entity_id=entity_id,
                        author_id=_anonymize(rev.get("name", "anonymous")),
                        author_metadata={
                            "verified": rev.get("verified_purchase", False),
                        },
                        content=content,
                        parent_id=f"amazon:asin:{asin}",
                        created_at=datetime.now(timezone.utc),
                        engagement={
                            "likes": rev.get("helpful_votes", 0) or 0,
                            "shares": 0,
                            "replies": 0,
                            "views": 0,
                        },
                        url=f"https://amazon.com/dp/{asin}",
                        raw={
                            "asin": asin,
                            "rating": rating,
                            "sentiment_from_rating": round(sentiment, 3),
                            "verified": rev.get("verified_purchase", False),
                        },
                    )
                    records.append(record)

                logger.info(f"Amazon ASIN {asin}: pulled {len(reviews)} reviews")
            except Exception as exc:
                logger.error(f"Amazon ASIN {asin} failed: {exc}")

        return records

    # ------------------------------------------------------------------
    # App Store Reviews (via app-store-scraper pip package)
    # ------------------------------------------------------------------

    def pull_appstore_reviews(
        self,
        entity_id: str,
        app_ids: list[str],
        limit: int = 200,
    ) -> list[PostRecord]:
        """Pull iOS App Store reviews via app-store-scraper."""
        try:
            from app_store_scraper import AppStore
        except ImportError:
            logger.error("app-store-scraper not installed — run: pip install app-store-scraper")
            return []

        records: list[PostRecord] = []
        per_app = max(1, limit // max(len(app_ids), 1))

        for app_id_str in app_ids:
            try:
                # app_id_str format: "app_name/id123456" or just "id123456"
                parts = app_id_str.strip().split("/")
                if len(parts) == 2:
                    app_name, raw_id = parts[0].strip(), parts[1].strip()
                else:
                    app_name, raw_id = "", parts[0].strip()

                numeric_id = raw_id.replace("id", "")
                app = AppStore(country="us", app_name=app_name or "app", app_id=numeric_id)
                app.review(how_many=per_app)

                for rev in (app.reviews or []):
                    rating = rev.get("rating", 3)
                    sentiment = ((float(rating) - 1) / 4) * 2 - 1

                    title = rev.get("title", "")
                    body = rev.get("review", "")
                    content = f"{title}\n\n{body}".strip() if title else (body or "").strip()
                    if not content:
                        continue

                    created = rev.get("date", datetime.now(timezone.utc))
                    if isinstance(created, str):
                        try: created = datetime.fromisoformat(created)
                        except: created = datetime.now(timezone.utc)

                    rev_id = hashlib.sha256(f"{numeric_id}:{rev.get('userName', '')}:{content[:50]}".encode()).hexdigest()[:16]
                    record = PostRecord(
                        id=f"appstore:{rev_id}",
                        platform="appstore",
                        entity_id=entity_id,
                        author_id=_anonymize(rev.get("userName", "anonymous")),
                        author_metadata={},
                        content=content,
                        parent_id=f"appstore:app:{numeric_id}",
                        created_at=created if hasattr(created, 'isoformat') else datetime.now(timezone.utc),
                        engagement={
                            "likes": 0,
                            "shares": 0,
                            "replies": 1 if rev.get("developerResponse") else 0,
                            "views": 0,
                        },
                        url=f"https://apps.apple.com/us/app/id{numeric_id}",
                        raw={
                            "app_id": numeric_id,
                            "rating": rating,
                            "sentiment_from_rating": round(sentiment, 3),
                        },
                    )
                    records.append(record)

                logger.info(f"App Store {app_id_str}: pulled {len(app.reviews or [])} reviews")
            except Exception as exc:
                logger.error(f"App Store {app_id_str} failed: {exc}")

        return records

    # ------------------------------------------------------------------
    # Google Play Reviews (via google-play-scraper npm package)
    # ------------------------------------------------------------------

    def pull_gplay_reviews(
        self,
        entity_id: str,
        app_ids: list[str],
        limit: int = 200,
    ) -> list[PostRecord]:
        """Pull Google Play reviews via google-play-scraper (Node subprocess)."""
        import subprocess as _sp

        records: list[PostRecord] = []
        per_app = max(1, limit // max(len(app_ids), 1))

        for app_id in app_ids:
            try:
                script = (
                    f"const gplay = require('google-play-scraper');"
                    f"gplay.reviews({{appId:'{app_id}',lang:'en',country:'us',"
                    f"sort:gplay.sort.NEWEST,num:{per_app}}})"
                    f".then(r => console.log(JSON.stringify(r.data)))"
                    f".catch(e => {{ console.error(e); process.exit(1); }})"
                )
                result = _sp.run(
                    ["node", "-e", script],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode != 0:
                    logger.error(f"Google Play {app_id}: node error: {result.stderr[:300]}")
                    continue

                reviews = json.loads(result.stdout)
                if not isinstance(reviews, list):
                    reviews = []

                for rev in reviews:
                    rating = rev.get("score", 3)
                    sentiment = ((float(rating) - 1) / 4) * 2 - 1

                    content = (rev.get("text") or "").strip()
                    if not content:
                        continue

                    rev_id = rev.get("id") or hashlib.sha256(f"{app_id}:{content[:50]}".encode()).hexdigest()[:16]
                    created = rev.get("date")
                    if isinstance(created, str):
                        try: created = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        except: created = datetime.now(timezone.utc)
                    else:
                        created = datetime.now(timezone.utc)

                    record = PostRecord(
                        id=f"gplay:{rev_id}",
                        platform="gplay",
                        entity_id=entity_id,
                        author_id=_anonymize(rev.get("userName", "anonymous")),
                        author_metadata={},
                        content=content,
                        parent_id=f"gplay:app:{app_id}",
                        created_at=created,
                        engagement={
                            "likes": rev.get("thumbsUp", 0) or 0,
                            "shares": 0,
                            "replies": 1 if rev.get("replyText") else 0,
                            "views": 0,
                        },
                        url=f"https://play.google.com/store/apps/details?id={app_id}",
                        raw={
                            "app_id": app_id,
                            "rating": rating,
                            "sentiment_from_rating": round(sentiment, 3),
                        },
                    )
                    records.append(record)

                logger.info(f"Google Play {app_id}: pulled {len(reviews)} reviews")
            except Exception as exc:
                logger.error(f"Google Play {app_id} failed: {exc}")

        return records

    # ------------------------------------------------------------------
    # Queue (v1: JSONL file)
    # ------------------------------------------------------------------

    def enqueue(self, records: list[PostRecord], entity_id: str) -> int:
        """
        Write PostRecord list to the entity's ingestion queue JSONL file.
        Uses DedupStore to skip already-seen records.
        Returns the count of newly enqueued records.
        """
        if not records:
            return 0

        entity_dir = Path(self.config.ENTITIES_DIR) / entity_id / "ingestion"
        entity_dir.mkdir(parents=True, exist_ok=True)

        dedup = DedupStore(entity_dir / "pulled_ids.db")
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        queue_path = entity_dir / f"posts_{date_str}.jsonl"

        new_count = 0
        with queue_path.open("a", encoding="utf-8") as fh:
            for record in records:
                platform, platform_id = record.id.split(":", 1)
                if dedup.is_seen(platform, platform_id):
                    continue
                fh.write(record.model_dump_json() + "\n")
                dedup.mark_seen(platform, platform_id, entity_id)
                new_count += 1

        logger.info(
            f"Enqueued {new_count}/{len(records)} new records for entity {entity_id}"
        )
        return new_count

    def read_queue(self, entity_id: str, limit: int = 20) -> list[dict]:
        """Read the most recent records from the entity's queue files (for preview)."""
        entity_dir = Path(self.config.ENTITIES_DIR) / entity_id / "ingestion"
        if not entity_dir.exists():
            return []

        records: list[dict] = []
        for jsonl_file in sorted(entity_dir.glob("posts_*.jsonl"), reverse=True):
            file_records: list[dict] = []
            with jsonl_file.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            file_records.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            # Newest records are at the end of the file (appended)
            records.extend(reversed(file_records))
            if len(records) >= limit:
                break

        return records[:limit]

    # ------------------------------------------------------------------
    # Pull all sources for an entity
    # ------------------------------------------------------------------

    def pull_entity(
        self,
        entity_id: str,
        sources: list[dict],
        limit: int = 500,
        task=None,
    ) -> dict:
        """
        Pull from all specified sources for an entity. Enqueues results.

        sources: [{"platform": "reddit", "ids": ["basketball", "nba"]}, ...]
        Returns summary dict.
        """
        all_records: list[PostRecord] = []
        errors: list[str] = []

        def _progress(msg: str, pct: int):
            logger.info(msg)
            if task:
                from app.utils.task_manager import task_manager
                task_manager.update(task.task_id, progress=pct)

        total_sources = len(sources)
        for i, source in enumerate(sources):
            platform = source.get("platform", "")
            ids = source.get("ids", [])
            pct = int(((i + 1) / total_sources) * 80)

            try:
                if platform == "reddit":
                    _progress(f"Pulling Reddit: {ids}", pct)
                    # Use PRAW if keys configured, otherwise fall back to RSS
                    if self.config.REDDIT_CLIENT_ID and self.config.REDDIT_CLIENT_ID != "...":
                        records = self.pull_reddit(entity_id, ids, limit)
                    else:
                        logger.info("No Reddit API keys — using RSS fallback")
                        records = self.pull_reddit_rss(entity_id, ids, limit=limit)
                    all_records.extend(records)

                elif platform == "twitter":
                    for q in ids:
                        _progress(f"Pulling Twitter: {q}", pct)
                        records = self.pull_twitter(entity_id, q, limit)
                        all_records.extend(records)

                elif platform == "youtube":
                    _progress(f"Pulling YouTube: {ids}", pct)
                    records = self.pull_youtube(entity_id, ids, limit)
                    all_records.extend(records)

                elif platform == "hackernews":
                    _progress(f"Pulling Hacker News: {ids}", pct)
                    records = self.pull_hackernews(entity_id, ids, limit)
                    all_records.extend(records)

                elif platform == "amazon":
                    _progress(f"Pulling Amazon Reviews: {ids}", pct)
                    records = self.pull_amazon_reviews(entity_id, ids, limit)
                    all_records.extend(records)

                elif platform == "appstore":
                    _progress(f"Pulling App Store Reviews: {ids}", pct)
                    records = self.pull_appstore_reviews(entity_id, ids, limit)
                    all_records.extend(records)

                elif platform == "gplay":
                    _progress(f"Pulling Google Play Reviews: {ids}", pct)
                    records = self.pull_gplay_reviews(entity_id, ids, limit)
                    all_records.extend(records)

                elif platform == "rss":
                    _progress(f"Pulling RSS: {ids}", pct)
                    records = self.pull_rss(entity_id, ids)
                    all_records.extend(records)

                else:
                    errors.append(f"Unknown platform: {platform}")

            except Exception as exc:
                msg = f"Pull failed for {platform}: {exc}"
                logger.error(msg)
                errors.append(msg)

        _progress("Enqueuing records...", 90)
        new_count = self.enqueue(all_records, entity_id)

        return {
            "records_pulled": len(all_records),
            "records_new": new_count,
            "records_duplicate": len(all_records) - new_count,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # Auto-pull: build sources from entity metadata
    # ------------------------------------------------------------------

    def auto_pull(
        self,
        entity_id: str,
        limit: int = 500,
        task=None,
        extra_terms: list[str] | None = None,
    ) -> dict:
        """
        Automatically ingest data from all free sources using the entity's
        name, keywords, and entity_type to generate search queries.
        No user configuration needed. Extra_terms are appended to the search.
        """
        from app.services.entity_store import entity_store

        entity = entity_store.get(entity_id)
        if not entity:
            return {"error": f"Entity {entity_id} not found", "records_pulled": 0, "records_new": 0, "errors": []}

        name = entity.name
        keywords = entity.keywords or []
        # Build search terms: entity name + each keyword + user-provided extras
        search_terms = [name] + [k for k in keywords if k.lower() != name.lower()]
        if extra_terms:
            for t in extra_terms:
                if t.strip() and t.strip().lower() not in [s.lower() for s in search_terms]:
                    search_terms.append(t.strip())

        # Pick relevant subreddits based on entity type
        type_subreddits = {
            "brand":      ["all"],
            "person":     ["all"],
            "influencer": ["all"],
            "company":    ["all", "technology", "business"],
            "product":    ["all", "reviews"],
            "game":       ["all", "gaming", "games"],
            "app":        ["all", "apps"],
        }
        subreddits = type_subreddits.get(entity.entity_type, ["all"])

        # Build sources list for each free platform
        sources: list[dict] = []

        # 1. Reddit (RSS — free, searches all subreddits for entity terms)
        sources.append({"platform": "reddit", "ids": subreddits, "_query": name})

        # 2. Hacker News (free, no key)
        sources.append({"platform": "hackernews", "ids": search_terms[:3]})

        # 3. YouTube (if key configured — search by keywords)
        if self.config.YOUTUBE_API_KEY and self.config.YOUTUBE_API_KEY != "...":
            sources.append({"platform": "youtube_search", "ids": search_terms[:2]})

        # 4. Google News RSS (always free)
        import urllib.parse
        news_feeds = []
        for term in search_terms[:2]:
            q = urllib.parse.quote_plus(term)
            news_feeds.append(f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en")
        sources.append({"platform": "rss", "ids": news_feeds})

        logger.info(f"Auto-pull for entity '{name}': {len(sources)} source groups, terms={search_terms}")

        # Execute pull with the auto-generated sources
        all_records: list[PostRecord] = []
        errors: list[str] = []

        def _progress(msg: str, pct: int):
            logger.info(msg)
            if task:
                from app.utils.task_manager import task_manager
                task_manager.update(task.task_id, progress=pct)

        total = len(sources)
        for i, source in enumerate(sources):
            platform = source["platform"]
            ids = source["ids"]
            pct = int(((i + 1) / total) * 80)

            try:
                if platform == "reddit":
                    _progress(f"Auto: Reddit RSS for '{name}'", pct)
                    query = source.get("_query", name)
                    if self.config.REDDIT_CLIENT_ID and self.config.REDDIT_CLIENT_ID != "...":
                        records = self.pull_reddit(entity_id, ids, limit)
                    else:
                        records = self.pull_reddit_rss(entity_id, ids, query=query, limit=limit)
                    all_records.extend(records)

                elif platform == "hackernews":
                    _progress(f"Auto: Hacker News for {ids}", pct)
                    records = self.pull_hackernews(entity_id, ids, limit)
                    all_records.extend(records)

                elif platform == "youtube_search":
                    _progress(f"Auto: YouTube search for {ids}", pct)
                    records = self._youtube_search(entity_id, ids, limit)
                    all_records.extend(records)

                elif platform == "rss":
                    _progress(f"Auto: RSS/News feeds", pct)
                    records = self.pull_rss(entity_id, ids)
                    all_records.extend(records)

            except Exception as exc:
                msg = f"Auto-pull {platform} failed: {exc}"
                logger.error(msg)
                errors.append(msg)

        _progress("Enqueuing records...", 90)
        new_count = self.enqueue(all_records, entity_id)

        return {
            "records_pulled": len(all_records),
            "records_new": new_count,
            "records_duplicate": len(all_records) - new_count,
            "errors": errors,
            "sources_used": [s["platform"] for s in sources],
        }

    def _youtube_search(
        self,
        entity_id: str,
        queries: list[str],
        limit: int = 100,
    ) -> list[PostRecord]:
        """Search YouTube for videos by keyword, then pull their comments."""
        try:
            from googleapiclient.discovery import build as yt_build
        except ImportError:
            return []

        if not self.config.YOUTUBE_API_KEY or self.config.YOUTUBE_API_KEY == "...":
            return []

        yt = yt_build("youtube", "v3", developerKey=self.config.YOUTUBE_API_KEY)
        video_ids: list[str] = []

        for query in queries:
            try:
                search_resp = yt.search().list(
                    part="id",
                    q=query,
                    type="video",
                    maxResults=5,
                    order="relevance",
                ).execute()
                for item in search_resp.get("items", []):
                    vid = item.get("id", {}).get("videoId")
                    if vid:
                        video_ids.append(vid)
            except Exception as exc:
                logger.error(f"YouTube search '{query}' failed: {exc}")

        if not video_ids:
            return []

        return self.pull_youtube(entity_id, video_ids[:10], limit)

    # ------------------------------------------------------------------
    # Scheduled pull
    # ------------------------------------------------------------------

    def run_scheduled_pull(
        self,
        schedule_id: str,
        entity_id: str,
        sources: list[dict],
        interval_seconds: int,
    ):
        """Run periodic pulls in a background thread."""
        stop_event = threading.Event()
        self._schedule_stop[schedule_id] = stop_event

        def _loop():
            while not stop_event.is_set():
                try:
                    self.pull_entity(entity_id, sources)
                except Exception as exc:
                    logger.error(f"Scheduled pull error: {exc}")
                stop_event.wait(interval_seconds)

        thread = threading.Thread(target=_loop, daemon=True, name=f"sched-{schedule_id}")
        self._schedules[schedule_id] = thread
        thread.start()
        logger.info(f"Started scheduled pull {schedule_id} every {interval_seconds}s for entity {entity_id}")

    def stop_schedule(self, schedule_id: str) -> bool:
        event = self._schedule_stop.get(schedule_id)
        if event:
            event.set()
            return True
        return False


# Module-level singleton
ingestion_service = IngestionService(Config)
