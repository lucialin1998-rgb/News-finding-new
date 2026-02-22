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

from .utils import canonicalize_url, file_age_hours, is_blocklisted_url, is_musicweek_article_like, load_text, save_text, url_hash

USER_AGENT = "MusicNewsInsightsBot/1.0 (+https://example.local; beginner-project)"
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "en-GB,en;q=0.9"}


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

    def fetch(self, url: str) -> Optional[FetchResult]:
        canon = canonicalize_url(url)
        if not canon:
            return None

        if not self.robots.allowed(canon):
            logging.info("Blocked by robots.txt: %s", canon)
            return None

        cache_path = self.cache_dir / f"{url_hash(canon)}.html"
        if self.use_cache:
            age = file_age_hours(cache_path)
            if age is not None and age < 24:
                return FetchResult(url=canon, status_code=200, text=load_text(cache_path), from_cache=True)

        try:
            resp = self.session.get(canon, timeout=self.timeout)
            if resp.status_code >= 400:
                logging.warning("HTTP %s for %s", resp.status_code, canon)
                return FetchResult(url=canon, status_code=resp.status_code, text="", from_cache=False)
            text = resp.text
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
        res = fetcher.fetch(homepage)
        if not res or not res.text:
            continue
        for url in extract_links_from_html(homepage, res.text):
            if source == "Music Week" and "musicweek.com" not in url:
                continue
            if source == "Music Business Worldwide" and "musicbusinessworldwide.com" not in url:
                continue
            found[source].add(url)
    return found


def discover_fallback_urls(fetcher: WebFetcher, pages: int = 4) -> Dict[str, Set[str]]:
    found = {"Music Week": set(), "Music Business Worldwide": set()}

    # MBW RSS fallback
    feed_url = "https://www.musicbusinessworldwide.com/feed/"
    try:
        if fetcher.robots.allowed(feed_url):
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                link = canonicalize_url(getattr(entry, "link", ""))
                if link:
                    found["Music Business Worldwide"].add(link)
    except Exception as exc:
        logging.warning("Failed parsing MBW feed: %s", exc)

    # Music Week listing fallback + pagination
    for page in range(1, pages + 1):
        list_url = "https://www.musicweek.com/news" if page == 1 else f"https://www.musicweek.com/news/page/{page}/"
        res = fetcher.fetch(list_url)
        if not res or not res.text:
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
        if source == "Music Week" and not is_musicweek_article_like(url):
            continue
        kept.append(url)
    return sorted(set(kept))
