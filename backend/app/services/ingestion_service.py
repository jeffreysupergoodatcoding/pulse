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
    # Reddit
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
        """Read recent records from the entity's queue files (for preview)."""
        entity_dir = Path(self.config.ENTITIES_DIR) / entity_id / "ingestion"
        if not entity_dir.exists():
            return []

        records: list[dict] = []
        for jsonl_file in sorted(entity_dir.glob("posts_*.jsonl"), reverse=True):
            with jsonl_file.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
                    if len(records) >= limit:
                        break
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
                    records = self.pull_reddit(entity_id, ids, limit)
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
