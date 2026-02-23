from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from dateutil import parser as dtparser

from .utils import LONDON_TZ, truncate_text

ARTICLE_PATH_HINTS = ["/read/", "/news/"]


@dataclass
class ParsedArticle:
    source: str
    url: str
    title: str
    date: str
    date_missing: bool
    excerpt_en: str
    summary_en: str
    title_zh: str = ""
    excerpt_zh: str = ""
    summary_zh: str = ""


def _find_jsonld_dates(soup: BeautifulSoup) -> List[str]:
    dates = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = (tag.string or tag.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if isinstance(node, dict):
                val = node.get("datePublished")
                if isinstance(val, str):
                    dates.append(val)
    return dates


def _safe_parse_dt(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = dtparser.parse(value)
        if dt.tzinfo is None:
            dt = LONDON_TZ.localize(dt)
        return dt.astimezone(LONDON_TZ)
    except Exception:
        return None


def _visible_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript"]):
        tag.extract()
    return soup.get_text(" ", strip=True)


def extract_metadata(html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")

    title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    elif soup.title and soup.title.string:
        title = soup.title.string.strip()

    date_candidates: List[str] = []
    m = soup.find("meta", attrs={"property": "article:published_time"})
    if m and m.get("content"):
        date_candidates.append(m["content"].strip())
    date_candidates.extend(_find_jsonld_dates(soup))
    for t in soup.find_all("time"):
        if t.get("datetime"):
            date_candidates.append(t["datetime"].strip())

    parsed_date = None
    for cand in date_candidates:
        parsed_date = _safe_parse_dt(cand)
        if parsed_date:
            break

    excerpt = ""
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        excerpt = og_desc["content"].strip()
    if not excerpt:
        md = soup.find("meta", attrs={"name": "description"})
        if md and md.get("content"):
            excerpt = md["content"].strip()

    if not excerpt:
        container = soup.select_one("main") or soup.select_one("article") or soup
        ps = [p.get_text(" ", strip=True) for p in container.find_all("p")[:2]] if container else []
        ps = [p for p in ps if p]
        if ps:
            excerpt = " ".join(ps)

    if not excerpt:
        excerpt = _visible_text(soup)[:300]

    excerpt = truncate_text(excerpt, 300)
    visible = _visible_text(soup)

    return {
        "title": title,
        "published_dt": parsed_date,
        "excerpt": excerpt,
        "page_text": visible.lower(),
        "body_length": len(visible),
    }


def is_article_page(
    metadata: Dict[str, Any],
    source: str,
    url: str,
    http_status: int,
    final_url: str = "",
) -> Tuple[bool, str, List[str]]:
    if http_status != 200:
        return False, "http_status_not_200", []

    # Emergency bypass for Music Week forbidden token filtering.
    if source == "Music Week":
        path = urlparse(url).path.lower()
        body_length = int(metadata.get("body_length") or 0)
        if body_length > 1000 and any(seg in path for seg in ARTICLE_PATH_HINTS):
            return True, "ok", []
        return False, "musicweek_not_article_like", []

    return True, "ok", []


def split_sentences(text: str) -> List[str]:
    if not text:
        return []
    chunks = re.split(r"(?<=[.!?])\s+", text.strip())
    return [c.strip() for c in chunks if c.strip()]


def build_summary_from_title_excerpt(title: str, excerpt: str, bullets: int = 2) -> str:
    sentences = []
    if title:
        sentences.append(title)
    sentences.extend(split_sentences(excerpt))
    unique = []
    seen = set()
    for s in sentences:
        key = s.lower()
        if key not in seen:
            unique.append(s)
            seen.add(key)
    chosen = unique[: max(2, bullets)] if unique else ["No summary available."]
    return "\n".join([f"- {c}" for c in chosen])
