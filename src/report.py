from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Dict, List


def write_csv(path: Path, rows: List[Dict], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    logging.info("Wrote CSV: %s (%d bytes)", path, path.stat().st_size)


def save_csvs(outdir: Path, run_date: str, articles: List[Dict], entities: List[Dict], insights: List[Dict]) -> Dict[str, Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    paths = {
        "articles": outdir / f"articles_{run_date}.csv",
        "entities": outdir / f"entities_{run_date}.csv",
        "insights": outdir / f"insights_{run_date}.csv",
    }

    write_csv(
        paths["articles"],
        articles,
        ["source", "date", "date_missing", "title_en", "title_zh", "url", "excerpt_en", "excerpt_zh", "summary_en", "summary_zh"],
    )
    write_csv(paths["entities"], entities, ["entity_en", "entity_zh", "category", "count"])
    write_csv(paths["insights"], insights, ["insight_en", "insight_zh", "supporting_articles"])
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
    lines.append(f"- skipped_by_reason: {counters.get('skipped_by_reason', {})}")
    lines.append(f"- mbw_rss_entries: {counters.get('mbw_rss_entries', 0)}")
    lines.append("")

    if counters.get("kept_articles", 0) == 0:
        lines.append("## Why no articles were retained")
        lines.append("No articles were retained after discovery and filtering.")
        lines.append("Common causes include robots blocking homepage fetches, unavailable pagination (404), and strict URL/content filters.")
        lines.append("See skipped_by_reason and source-specific counters in logs for details.")
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
