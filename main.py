from __future__ import annotations

import argparse
import logging
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Dict, List

from src.fetchers import WebFetcher, discover_fallback_urls, discover_homepage_urls, filter_candidate_urls
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
        "skipped_by_reason": Counter(),
        "date_missing_count": 0,
    }

    fetcher = WebFetcher(use_cache=not args.no_cache)

    discovered_home = discover_homepage_urls(fetcher)
    discovered_fb = discover_fallback_urls(fetcher)
    counters["discovered_urls_homepage"] = sum(len(v) for v in discovered_home.values())
    counters["discovered_urls_fallback"] = sum(len(v) for v in discovered_fb.values())

    all_candidates: Dict[str, List[str]] = {}
    for source in ["Music Week", "Music Business Worldwide"]:
        merged = set(discovered_home.get(source, set())) | set(discovered_fb.get(source, set()))
        filtered = filter_candidate_urls(source, merged)
        all_candidates[source] = filtered[: args.max_per_source]

    parsed_articles: List[ParsedArticle] = []
    seen_urls = set()

    for source, urls in all_candidates.items():
        logging.info("Processing %s candidate URLs: %d", source, len(urls))
        for url in urls:
            cu = canonicalize_url(url)
            if cu in seen_urls:
                counters["skipped_by_reason"]["duplicate_url"] += 1
                continue
            seen_urls.add(cu)

            res = fetcher.fetch(cu)
            if not res:
                counters["skipped_by_reason"]["fetch_failed_or_robots_block"] += 1
                continue
            counters["fetched_pages"] += 1
            if res.status_code >= 400 or not res.text:
                counters["skipped_by_reason"]["http_error_or_empty"] += 1
                continue

            md = extract_metadata(res.text)
            ok, reason = is_article_page(md)
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
                    source=source,
                    url=cu,
                    title=title,
                    date=date_str,
                    date_missing=date_missing,
                    excerpt_en=excerpt,
                    summary_en=summary,
                )
            )

    counters["kept_articles"] = len(parsed_articles)

    translator = Translator(enabled=not args.no_translate)

    # Translation (best effort)
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

    # Always produce output even if empty
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
    logging.info("date_missing_count=%s", counters["date_missing_count"])


if __name__ == "__main__":
    main()
