from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List

from sklearn.feature_extraction.text import TfidfVectorizer

STOP_TERMS = {
    "music",
    "week",
    "business",
    "worldwide",
    "says",
    "new",
    "will",
    "said",
    "industry",
}


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def build_insights(articles: List[Dict], max_insights: int = 8) -> List[Dict]:
    if not articles:
        return [
            {
                "insight_en": "Insufficient evidence: no articles were retained this week.",
                "insight_zh": "",
                "supporting_articles": "",
            }
        ]

    docs = [_clean_text(" ".join([a.get("title_en", ""), a.get("excerpt_en", ""), a.get("summary_en", "")])) for a in articles]
    docs = [d if d else "empty" for d in docs]

    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
    mat = vectorizer.fit_transform(docs)
    terms = vectorizer.get_feature_names_out()

    top_terms = []
    mean_scores = mat.mean(axis=0).A1
    ranked = sorted(zip(terms, mean_scores), key=lambda x: x[1], reverse=True)
    for term, score in ranked:
        if score <= 0:
            continue
        tokens = set(term.lower().split())
        if tokens & STOP_TERMS:
            continue
        top_terms.append(term)
        if len(top_terms) >= max_insights * 2:
            break

    grouped: Dict[str, List[Dict]] = defaultdict(list)
    for a in articles:
        blob = _clean_text(" ".join([a.get("title_en", ""), a.get("excerpt_en", ""), a.get("summary_en", "")])).lower()
        for term in top_terms:
            if term in blob:
                grouped[term].append(a)

    insights = []
    for term in top_terms:
        supports = grouped.get(term, [])
        if len(supports) < 2:
            continue
        supports = supports[:5]
        refs = [f"{s.get('title_en','')} ({s.get('source','')} | {s.get('date','') or 'date missing'})" for s in supports]
        insight = f"Theme '{term}' appeared across {len(supports)} articles, suggesting sustained weekly attention."
        insights.append(
            {
                "insight_en": insight,
                "insight_zh": "",
                "supporting_articles": " ; ".join(refs),
            }
        )
        if len(insights) >= max_insights:
            break

    if not insights:
        insights.append(
            {
                "insight_en": "Insufficient evidence: article overlap across themes is too limited this week.",
                "insight_zh": "",
                "supporting_articles": "",
            }
        )
    return insights
