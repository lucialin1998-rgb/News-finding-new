# Music Industry Weekly News Insights (Beginner-Friendly)

This project scrapes **public** music-industry news from:
- https://www.musicweek.com/
- https://www.musicbusinessworldwide.com/

It then produces:
- Article dataset (English + best-effort Chinese)
- Entity counts (companies/people/organizations)
- Weekly industry insights with supporting evidence
- A bilingual Markdown report

> Legal/ethical design: this project respects robots.txt, does not bypass login/paywalls, and stores only metadata + short excerpts (no full copyrighted text storage).

---

## 1) What you need (Windows-friendly)

- Python 3.10+ (3.11 recommended)
- Internet connection (for scraping + optional translation model download)

---

## 2) Setup (Windows PowerShell)

```powershell
# 1) Go to project folder
cd path\to\News-finding-new

# 2) Create venv
python -m venv .venv

# 3) Activate venv
.\.venv\Scripts\Activate.ps1

# 4) Upgrade pip
python -m pip install --upgrade pip

# 5) Install dependencies
pip install -r requirements.txt

# 6) Download spaCy English model
python -m spacy download en_core_web_sm
```

---

## 3) Run

Basic:

```powershell
python main.py --days 7 --outdir output --verbose
```

Optional flags:

```powershell
python main.py --days 7 --outdir output --max-per-source 80 --no-translate
python main.py --days 7 --outdir output --no-cache
```

---

## 4) Output files

The run creates dated files in `output/`:

- `weekly_report_YYYY-MM-DD.md`
- `articles_YYYY-MM-DD.csv`
- `entities_YYYY-MM-DD.csv`
- `insights_YYYY-MM-DD.csv`

If translation is unavailable, Chinese fields are left empty, and the report clearly states this.

---

## 5) Troubleshooting

### A) `ModuleNotFoundError: en_core_web_sm`
Run:

```powershell
python -m spacy download en_core_web_sm
```

### B) Translation is empty
This project uses **Argos Translate** (free). If the en->zh model download fails, output is still generated in English.

### C) Few or no articles found
The script prints diagnostics:
- discovered_urls_homepage
- discovered_urls_fallback
- fetched_pages
- kept_articles
- skipped_by_reason
- date_missing_count

If zero articles are kept, a diagnostics report is still generated.

### D) Corporate network/proxy issues
Some pages or translation downloads may fail behind firewalls. Retry on another network or disable translation (`--no-translate`).

---

## 6) Notes for beginners

- You can open CSV files in Excel.
- Re-run weekly to get fresh output.
- The tool uses Europe/London time for the “last N days” filter.
