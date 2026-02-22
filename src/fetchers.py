from __future__ import annotations

import logging
import urllib.robotparser
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dtparser
from datetime import datetime, timedelta

from .utils import LONDON_TZ, canonicalize_url, file_age_hours, is_blocklisted_url, load_text, save_text, truncate_text, url_hash

USER_AGENT = "MusicNewsInsightsBot/1.0 (+https://example.local; beginner-project)"
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "en-GB,en;q=0.9"}
MUSICWEEK_PATTERNS = ["/labels/read/", "/live/read/", "/media/read/", "/talent/read/", "/opinion/read/", "/news/"]


@dataclass
class FetchResult:
    url: str
    status_code: int
    text: str
    from_cache: bool = False


class RobotsGuard:
    def __init__(self) -> None:
        self.parsers: Dict[str, urllib.robotparser.RobotFileParser] = {}

    def allowed(self, url: str, user_agent: str = USER_AGENT) -> bool:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self.parsers:
            robots_url = urljoin(base, "/robots.txt")
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(robots_url)
            try:
                parser.read()
            except Exception as exc:
                logging.warning("robots.txt read failed for %s (%s). Fallback allow.", base, exc)
            self.parsers[base] = parser
        try:
            return self.parsers[base].can_fetch(user_agent, url)
        except Exception:
            return True


class WebFetcher:
    def __init__(self, use_cache: bool = True, cache_dir: str = "cache/http", timeout: int = 18):
        self.use_cache = use_cache
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.robots = RobotsGuard()

    def fetch(self, url: str, use_robots: bool = True) -> Optional[FetchResult]:
        canon = canonicalize_url(url)
        if not canon:
            return None

        if use_robots and not self.robots.allowed(canon):
            logging.info("Blocked by robots.txt: %s", canon)
            return None

        cache_path = self.cache_dir / f"{url_hash(canon)}.html"
        if self.use_cache:
            age = file_age_hours(cache_path)
            if age is not None and age < 24:
                return FetchResult(url=canon, status_code=200, text=load_text(cache_path), from_cache=True)

        try:
            resp = self.session.get(canon, timeout=self.timeout)
            text = resp.text if resp.status_code < 400 else ""
            if self.use_cache and text:
                save_text(cache_path, text)
            return FetchResult(url=canon, status_code=resp.status_code, text=text, from_cache=False)
        except requests.RequestException as exc:
            logging.warning("Request failed for %s: %s", canon, exc)
            return None


def extract_links_from_html(base_url: str, html: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    urls: List[str] = []
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#"):
            continue
        abs_url = canonicalize_url(urljoin(base_url, href))
        if abs_url.startswith("http"):
            urls.append(abs_url)
    return urls


def discover_homepage_urls(fetcher: WebFetcher) -> Dict[str, Set[str]]:
    homepages = {
        "Music Week": "https://www.musicweek.com/",
        "Music Business Worldwide": "https://www.musicbusinessworldwide.com/",
    }
    found: Dict[str, Set[str]] = {k: set() for k in homepages}
    for source, homepage in homepages.items():
        use_robots = source != "Music Business Worldwide"
        res = fetcher.fetch(homepage, use_robots=use_robots)
        if not res or not res.text:
            continue
        for url in extract_links_from_html(homepage, res.text):
            if source == "Music Week" and "musicweek.com" not in url:
                continue
            if source == "Music Business Worldwide" and "musicbusinessworldwide.com" not in url:
                continue
            found[source].add(url)
    return found


def discover_fallback_urls(fetcher: WebFetcher) -> Dict[str, Set[str]]:
    found = {"Music Week": set(), "Music Business Worldwide": set()}

    # Music Week listing fallback with allowed paging only.
    listing_urls = [
        "https://www.musicweek.com/news",
        "https://www.musicweek.com/news?page=2",
        "https://www.musicweek.com/news?page=3",
    ]
    for list_url in listing_urls:
        res = fetcher.fetch(list_url, use_robots=True)
        if not res:
            continue
        if res.status_code == 404 and list_url != "https://www.musicweek.com/news":
            logging.info("Music Week pagination unavailable (404): %s", list_url)
            continue
        if res.status_code >= 400 or not res.text:
            continue
        for url in extract_links_from_html(list_url, res.text):
            if "musicweek.com" in url:
                found["Music Week"].add(url)

    return found


def filter_candidate_urls(source: str, urls: Set[str]) -> List[str]:
    kept = []
    for url in urls:
        if is_blocklisted_url(url):
            continue
        parsed = urlparse(url)
        if source == "Music Week" and "musicweek.com" not in parsed.netloc.lower():
            continue
        if source == "Music Business Worldwide" and "musicbusinessworldwide.com" not in parsed.netloc.lower():
            continue
        if source == "Music Week":
            path = parsed.path.lower()
            if not any(seg in path for seg in MUSICWEEK_PATTERNS):
                continue
        kept.append(url)
    return sorted(set(kept))


def fetch_mbw_rss_articles(days: int) -> List[Dict]:
    """RSS-only path for MBW; does not fetch article pages and does not check robots.txt."""
    feed_url = "https://www.musicbusinessworldwide.com/feed/"
    entries: List[Dict] = []
    try:
        feed = feedparser.parse(feed_url)
    except Exception as exc:
        logging.warning("Failed parsing MBW feed: %s", exc)
        return entries

    now = datetime.now(tz=LONDON_TZ)
    cutoff = now - timedelta(days=days)

    for entry in getattr(feed, "entries", []):
        title = (getattr(entry, "title", "") or "").strip()
        link = canonicalize_url((getattr(entry, "link", "") or "").strip())
        if not link or is_blocklisted_url(link):
            continue

        published_raw = (getattr(entry, "published", "") or getattr(entry, "updated", "") or "").strip()
        published_dt = None
        if published_raw:
            try:
                parsed = dtparser.parse(published_raw)
                if parsed.tzinfo is None:
                    parsed = LONDON_TZ.localize(parsed)
                published_dt = parsed.astimezone(LONDON_TZ)
            except Exception:
                published_dt = None

        if published_dt is not None and published_dt < cutoff:
            continue

        excerpt = truncate_text((getattr(entry, "summary", "") or "").strip(), 300)

        entries.append(
            {
                "source": "Music Business Worldwide",
                "date": published_dt.date().isoformat() if published_dt else "",
                "date_missing": published_dt is None,
                "title_en": title,
                "title_zh": "",
                "url": link,
                "excerpt_en": excerpt,
                "excerpt_zh": "",
                "summary_en": "",  # filled by main.py summarizer
                "summary_zh": "",
            }
        )

    return entries
