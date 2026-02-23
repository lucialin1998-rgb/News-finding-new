from __future__ import annotations

import csv
import hashlib
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import pytz

LONDON_TZ = pytz.timezone("Europe/London")

BLOCKLIST_TOKENS = {
    "login",
    "password",
    "reset",
    "subscribe",
    "newsletter",
    "account",
    "cookie",
    "privacy",
    "terms",
    "contact",
}


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s | %(levelname)s | %(message)s")


def now_london() -> datetime:
    return datetime.now(tz=LONDON_TZ)


def get_cutoff(days: int) -> datetime:
    return now_london() - timedelta(days=days)


def truncate_text(text: str, max_len: int = 300) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = re.sub(r"/+", "/", parsed.path).rstrip("/")
    filtered_query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}
    ]
    query = urlencode(filtered_query)
    return urlunparse((scheme, netloc, path, "", query, ""))


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def is_blocklisted_url(url: str) -> bool:
    low = url.lower()
    return any(token in low for token in BLOCKLIST_TOKENS)


def file_age_hours(path: Path) -> Optional[float]:
    if not path.exists():
        return None
    age_seconds = datetime.now().timestamp() - path.stat().st_mtime
    return age_seconds / 3600.0


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sorted_counter_dict(counter_dict: Dict[str, int]) -> Dict[str, int]:
    return dict(sorted(counter_dict.items(), key=lambda x: (-x[1], x[0])))


def write_csv(path: Path, rows: List[Dict], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    logging.info("Wrote CSV: %s (%d bytes)", path, path.stat().st_size)
