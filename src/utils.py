from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional
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
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


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


def is_musicweek_article_like(url: str) -> bool:
    parsed = urlparse(url)
    if "musicweek.com" not in parsed.netloc.lower():
        return True
    path = parsed.path.lower().strip("/")
    if path == "news":
        return False
    if "/news/" in f"/{path}/":
        return True
    # Generic article slug style fallback: has at least two path segments and digits or long slug
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2 and any(c.isdigit() for c in path):
        return True
    if len(parts) >= 2 and len(parts[-1]) >= 12:
        return True
    return False


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


def env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.lower() in {"1", "true", "yes", "on"}


def sorted_counter_dict(counter_dict: Dict[str, int]) -> Dict[str, int]:
    return dict(sorted(counter_dict.items(), key=lambda x: (-x[1], x[0])))
