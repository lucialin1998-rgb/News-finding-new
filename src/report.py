from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd


def save_csvs(outdir: Path, run_date: str, articles: List[Dict], entities: List[Dict], insights: List[Dict]) -> Dict[str, Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    paths = {
        "articles": outdir / f"articles_{run_date}.csv",
        "entities": outdir / f"entities_{run_date}.csv",
        "insights": outdir / f"insights_{run_date}.csv",
    }
    pd.DataFrame(articles).to_csv(paths["articles"], index=False, encoding="utf-8-sig")
    pd.DataFrame(entities).to_csv(paths["entities"], index=False, encoding="utf-8-sig")
    pd.DataFrame(insights).to_csv(paths["insights"], index=False, encoding="utf-8-sig")
    return paths


def render_markdown_report(
    outdir: Path,
    run_date: str,
    days: int,
    articles: List[Dict],
    entities: List[Dict],
    insights: List[Dict],
    counters: Dict,
    translation_available: bool,
) -> Path:
    path = outdir / f"weekly_report_{run_date}.md"

    lines = []
    lines.append(f"# Weekly Music Industry Report ({run_date})")
    lines.append("")
    lines.append(f"Time window: Last {days} days (Europe/London)")
    lines.append("")
    if not translation_available:
        lines.append("> Note: Chinese translation is unavailable for this run. English output is complete; Chinese fields may be empty.")
        lines.append("")

    lines.append("## Diagnostics")
    lines.append(f"- discovered_urls_homepage: {counters.get('discovered_urls_homepage', 0)}")
    lines.append(f"- discovered_urls_fallback: {counters.get('discovered_urls_fallback', 0)}")
    lines.append(f"- fetched_pages: {counters.get('fetched_pages', 0)}")
    lines.append(f"- kept_articles: {counters.get('kept_articles', 0)}")
    lines.append(f"- date_missing_count: {counters.get('date_missing_count', 0)}")
    lines.append(f"- skipped_by_reason: {counters.get('skipped_by_reason', {})}")
    lines.append("")

    lines.append("## Industry Insights (EN)")
    for row in insights:
        lines.append(f"- {row.get('insight_en', '')}")
        supp = row.get("supporting_articles", "")
        if supp:
            lines.append(f"  - Evidence: {supp}")
    lines.append("")

    lines.append("## 行业洞察 (ZH)")
    for row in insights:
        lines.append(f"- {row.get('insight_zh', '')}")
    lines.append("")

    lines.append("## Top Entities")
    for row in entities[:30]:
        lines.append(f"- {row.get('entity_en','')} | {row.get('entity_zh','')} | {row.get('category','')} | {row.get('count',0)}")
    lines.append("")

    lines.append("## Articles")
    if not articles:
        lines.append("No articles retained. Please review diagnostics above.")
    for a in articles:
        lines.append(f"### {a.get('title_en','')} / {a.get('title_zh','')}")
        lines.append(f"- Source: {a.get('source','')}")
        lines.append(f"- Date: {a.get('date','') or 'date missing'}")
        lines.append(f"- URL: {a.get('url','')}")
        lines.append(f"- Excerpt (EN): {a.get('excerpt_en','')}")
        lines.append(f"- 摘要 (ZH): {a.get('excerpt_zh','')}")
        lines.append("- Summary (EN):")
        lines.append(a.get("summary_en", ""))
        lines.append("- 总结 (ZH):")
        lines.append(a.get("summary_zh", ""))
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
