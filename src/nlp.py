from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Dict, List, Tuple

import spacy

COMPANY_HINTS = {
    "universal music",
    "sony music",
    "warner music",
    "spotify",
    "apple music",
    "youtube",
    "tiktok",
    "amazon music",
    "believe",
    "beggars",
}


def load_spacy_model():
    try:
        return spacy.load("en_core_web_sm")
    except Exception as exc:
        logging.error("Failed to load spaCy model en_core_web_sm: %s", exc)
        raise


def normalize_entity(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text


def label_entity(name: str, spacy_label: str) -> str:
    low = name.lower()
    if spacy_label == "PERSON":
        return "Person"
    if any(hint in low for hint in COMPANY_HINTS):
        return "Company"
    if spacy_label == "ORG":
        return "Organization"
    return "Organization"


def extract_entities(articles: List[Dict], nlp_model) -> List[Dict]:
    counter: Counter[Tuple[str, str]] = Counter()

    for a in articles:
        text = " ".join([a.get("title_en", ""), a.get("excerpt_en", ""), a.get("summary_en", "")]).strip()
        if not text:
            continue
        doc = nlp_model(text)
        for ent in doc.ents:
            if ent.label_ not in {"ORG", "PERSON"}:
                continue
            name = normalize_entity(ent.text)
            if len(name) < 2:
                continue
            category = label_entity(name, ent.label_)
            counter[(name, category)] += 1

    rows = [
        {"entity_en": name, "category": category, "count": count, "entity_zh": ""}
        for (name, category), count in sorted(counter.items(), key=lambda x: (-x[1], x[0][0]))
    ]
    return rows
