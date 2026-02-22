from __future__ import annotations

import argparse
import logging
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Dict, List

from src.fetchers import WebFetcher, discover_fallback_urls, discover_homepage_urls, fetch_mbw_rss_articles, filter_candidate_urls
from src.insights import build_insights
from src.nlp import extract_entities, load_spacy_model
from src.parser import ParsedArticle, build_summary_from_title_excerpt, extract_metadata, is_article_page
from src.report import render_markdown_report, save_csvs
from src.translate import Translator
from src.utils import canonicalize_url, get_cutoff, setup_logging, sorted_counter_dict


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Music industry weekly news insights")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--outdir", type=str, default="output")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--max-per-source", type=int, default=80)
    p.add_argument("--no-translate", action="store_true")
    p.add_argument("--no-cache", action="store_true")
    return p.parse_args()


def _article_to_dict(a: ParsedArticle) -> Dict:
    return {
        "source": a.source,
        "date": a.date,
        "date_missing": a.date_missing,
        "title_en": a.title,
        "title_zh": a.title_zh,
        "url": a.url,
        "excerpt_en": a.excerpt_en,
        "excerpt_zh": a.excerpt_zh,
        "summary_en": a.summary_en,
        "summary_zh": a.summary_zh,
    }


def main() -> None:
    args = parse_args()
    setup_logging(args.verbose)

    outdir = Path(args.outdir)
    run_date = str(date.today())
    cutoff = get_cutoff(args.days)

    counters = {
        "discovered_urls_homepage": 0,
        "discovered_urls_fallback": 0,
        "fetched_pages": 0,
        "kept_articles": 0,
        "fetched_musicweek_pages": 0,
        "retained_musicweek_articles": 0,
        "mbw_rss_entries": 0,
        "skipped_by_reason": Counter(),
        "date_missing_count": 0,
    }

    fetcher = WebFetcher(use_cache=not args.no_cache)

    discovered_home = discover_homepage_urls(fetcher)
    discovered_fb = discover_fallback_urls(fetcher)

    mbw_articles = fetch_mbw_rss_articles(args.days)
    counters["mbw_rss_entries"] = len(mbw_articles)

    counters["discovered_urls_homepage"] = sum(len(v) for v in discovered_home.values())
    counters["discovered_urls_fallback"] = sum(len(v) for v in discovered_fb.values()) + counters["mbw_rss_entries"]

    parsed_articles: List[ParsedArticle] = []

    # MBW is RSS-only (no webpage fetch).
    for item in mbw_articles:
        summary = build_summary_from_title_excerpt(item.get("title_en", ""), item.get("excerpt_en", ""), bullets=2)
        parsed_articles.append(
            ParsedArticle(
                source=item.get("source", "Music Business Worldwide"),
                url=item.get("url", ""),
                title=item.get("title_en", ""),
                date=item.get("date", ""),
                date_missing=bool(item.get("date_missing", False)),
                excerpt_en=item.get("excerpt_en", ""),
                summary_en=summary,
            )
        )
        if item.get("date_missing", False):
            counters["date_missing_count"] += 1

    # Music Week webpage flow.
    mw_candidates = filter_candidate_urls(
        "Music Week",
        set(discovered_home.get("Music Week", set())) | set(discovered_fb.get("Music Week", set())),
    )[: args.max_per_source]

    logging.info("MusicWeek discovered URLs: %s", len(mw_candidates))

    seen_urls = set()
    for url in mw_candidates:
        cu = canonicalize_url(url)
        if cu in seen_urls:
            counters["skipped_by_reason"]["duplicate_url"] += 1
            continue
        seen_urls.add(cu)

        res = fetcher.fetch(cu, use_robots=True)
        if not res:
            counters["skipped_by_reason"]["fetch_failed_or_robots_block"] += 1
            continue

        counters["fetched_pages"] += 1
        counters["fetched_musicweek_pages"] += 1

        md = extract_metadata(res.text if res.text else "")
        ok, reason = is_article_page(md, source="Music Week", url=cu, http_status=res.status_code)
        if not ok:
            counters["skipped_by_reason"][reason] += 1
            continue

        title = (md.get("title") or "").strip()
        excerpt = (md.get("excerpt") or "").strip()
        pub_dt = md.get("published_dt")
        if pub_dt is not None and pub_dt < cutoff:
            counters["skipped_by_reason"]["older_than_window"] += 1
            continue

        date_str = pub_dt.date().isoformat() if pub_dt else ""
        date_missing = pub_dt is None
        if date_missing:
            counters["date_missing_count"] += 1

        summary = build_summary_from_title_excerpt(title, excerpt, bullets=2)
        parsed_articles.append(
            ParsedArticle(
                source="Music Week",
                url=cu,
                title=title,
                date=date_str,
                date_missing=date_missing,
                excerpt_en=excerpt,
                summary_en=summary,
            )
        )
        counters["retained_musicweek_articles"] += 1

    counters["kept_articles"] = len(parsed_articles)

    logging.info("MusicWeek fetched pages: %s", counters["fetched_musicweek_pages"])
    logging.info("MusicWeek retained articles: %s", counters["retained_musicweek_articles"])
    logging.info("MBW RSS entries: %s", counters["mbw_rss_entries"])

    translator = Translator(enabled=not args.no_translate)
    for article in parsed_articles:
        if not args.no_translate and translator.available:
            article.title_zh = translator.translate_text(article.title)
            article.excerpt_zh = translator.translate_text(article.excerpt_en)
            article.summary_zh = translator.translate_text(article.summary_en)

    article_dicts = [_article_to_dict(a) for a in parsed_articles]

    nlp_model = load_spacy_model()
    entities = extract_entities(article_dicts, nlp_model)
    if not args.no_translate and translator.available:
        for e in entities:
            e["entity_zh"] = translator.translate_text(e["entity_en"])

    insights = build_insights(article_dicts, max_insights=10)
    if not args.no_translate and translator.available:
        for item in insights:
            item["insight_zh"] = translator.translate_text(item["insight_en"])

    paths = save_csvs(outdir, run_date, article_dicts, entities, insights)

    counters["skipped_by_reason"] = sorted_counter_dict(dict(counters["skipped_by_reason"]))
    report_path = render_markdown_report(
        outdir=outdir,
        run_date=run_date,
        days=args.days,
        articles=article_dicts,
        entities=entities,
        insights=insights,
        counters=counters,
        translation_available=(translator.available and not args.no_translate),
    )

    logging.info("Run complete. Output files:")
    for k, v in paths.items():
        logging.info("%s: %s", k, v)
    logging.info("report: %s", report_path)

    logging.info("discovered_urls_homepage=%s", counters["discovered_urls_homepage"])
    logging.info("discovered_urls_fallback=%s", counters["discovered_urls_fallback"])
    logging.info("fetched_pages=%s", counters["fetched_pages"])
    logging.info("kept_articles=%s", counters["kept_articles"])
    logging.info("skipped_by_reason=%s", counters["skipped_by_reason"])
    logging.info("mbw_rss_entries=%s", counters["mbw_rss_entries"])
    logging.info("Final kept_articles: %s", counters["kept_articles"])


if __name__ == "__main__":
    main()
