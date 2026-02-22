from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
from dateutil import parser as dtparser

from .utils import LONDON_TZ, truncate_text


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
        container = soup.select_one("article") or soup.select_one("main") or soup
        p = container.find("p") if container else None
        if p:
            excerpt = p.get_text(" ", strip=True)

    excerpt = truncate_text(excerpt, 300)
    return {
        "title": title,
        "published_dt": parsed_date,
        "date_raw_found": bool(date_candidates),
        "excerpt": excerpt,
        "soup": soup,
    }


def is_article_page(metadata: Dict[str, Any]) -> Tuple[bool, str]:
    title = (metadata.get("title") or "").lower()
    if any(bad in title for bad in ["password", "login", "subscribe"]):
        return False, "page_title_forbidden"
    has_date = metadata.get("published_dt") is not None or metadata.get("date_raw_found")
    if not has_date:
        return False, "missing_article_date_signals"
    return True, "ok"


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
