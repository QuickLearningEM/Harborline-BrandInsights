"""Collect public YouTube comments about the brand, competitors, and category terms.

Design notes
- Only public text and counts are stored. Author names and channel IDs of commenters are
  never requested or kept, so commenters cannot be identified.
- The API key is sent in a header, never in the URL, so it cannot leak into logs.
- A quota budget stops collection before the daily API quota is exhausted
  (search.list costs 100 units per call, commentThreads.list costs 1).
"""

import logging

import pandas as pd
import requests

log = logging.getLogger(__name__)

API = "https://www.googleapis.com/youtube/v3"
SEARCH_COST = 100
COMMENTS_COST = 1


class YouTubeError(RuntimeError):
    pass


class QuotaBudgetExceeded(YouTubeError):
    pass


class YouTubeClient:
    def __init__(self, api_key: str, max_quota_units: int = 3000, session=None, timeout: int = 20):
        if not api_key:
            raise YouTubeError("BI_YOUTUBE_API_KEY is not set")
        self._session = session or requests.Session()
        self._session.headers["x-goog-api-key"] = api_key
        self._timeout = timeout
        self.max_quota_units = max_quota_units
        self.units_used = 0

    def _get(self, path: str, cost: int, **params) -> dict | None:
        if self.units_used + cost > self.max_quota_units:
            raise QuotaBudgetExceeded(f"Quota budget of {self.max_quota_units} units reached")
        try:
            resp = self._session.get(f"{API}/{path}", params=params, timeout=self._timeout)
        except requests.RequestException as exc:
            raise YouTubeError(f"Request to {path} failed: {type(exc).__name__}") from None
        self.units_used += cost
        if resp.status_code == 403 and "commentsDisabled" in resp.text:
            return None
        if resp.status_code != 200:
            raise YouTubeError(f"{path} returned HTTP {resp.status_code}")
        return resp.json()

    def search_videos(self, term: str, max_results: int = 10) -> list[dict]:
        data = self._get(
            "search", SEARCH_COST, part="snippet", type="video", q=term,
            maxResults=min(max_results, 50), order="relevance",
        )
        return [
            {"video_id": i["id"]["videoId"], "video_title": i["snippet"]["title"]}
            for i in (data or {}).get("items", [])
        ]

    def fetch_comments(self, video_id: str, max_comments: int = 100) -> list[dict]:
        data = self._get(
            "commentThreads", COMMENTS_COST, part="snippet", videoId=video_id,
            maxResults=min(max_comments, 100), order="relevance", textFormat="plainText",
        )
        rows = []
        for item in (data or {}).get("items", []):
            top = item["snippet"]["topLevelComment"]["snippet"]
            rows.append({
                "comment_id": item["id"],
                "text": top["textDisplay"],
                "like_count": int(top.get("likeCount", 0)),
                "published_at": top["publishedAt"][:10],
            })
        return rows

    def collect(self, terms: list[str], max_videos: int = 5, max_comments: int = 100) -> pd.DataFrame:
        rows: list[dict] = []
        try:
            for term in terms:
                for video in self.search_videos(term, max_videos):
                    for c in self.fetch_comments(video["video_id"], max_comments):
                        rows.append({**c, **video, "channel_id": "n/a", "search_term": term})
        except QuotaBudgetExceeded:
            log.warning("Stopping YouTube collection: quota budget reached")
        log.info("Collected %d comments using %d quota units", len(rows), self.units_used)
        return pd.DataFrame(rows)
