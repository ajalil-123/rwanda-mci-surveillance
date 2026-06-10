# Rwanda MCI Surveillance System v2
## Automated Historical + Real-Time Mass Casualty Incident Monitoring

---

## Quick Start (Windows)

1. Double-click **START.bat** — it installs everything and launches the server
2. Open **http://localhost:5050** in your browser
3. The system automatically scrapes historical data (2015–present) on first run
4. Every 30 minutes it refreshes with new content

---

## Files

```
mci_system/
├── app.py          ← Flask server + API routes
├── database.py     ← SQLite schema, dedup, helpers
├── nlp.py          ← Keyword detection, severity scoring, geo-tagging
├── scraper.py      ← All scraping: RSS, Google News, news sites, Twitter/Nitter
├── analytics.py    ← Trends, hotspots, seasonal patterns, predictions
├── index.html      ← Full dashboard (map + analytics + predictions)
├── requirements.txt
├── START.bat       ← Windows one-click launcher
└── data/
    └── mci_rwanda.db  ← SQLite database (created automatically)
```

---

## Data Sources

| Source | Type | Notes |
|--------|------|-------|
| Google News RSS | Free | Best historical coverage, goes back years |
| The New Times Rwanda | RSS + scrape | Rwanda's main English paper |
| KT Press | RSS + scrape | Rwanda news |
| Igihe | RSS | Kinyarwanda content |
| Rwanda Broadcasting (RBA) | RSS | State broadcaster |
| ReliefWeb Rwanda | RSS | UN/NGO humanitarian reports |
| Twitter/X via Nitter | Scrape | No API key needed |
| Rwanda Today | Scrape | English news |

---

## How Incremental Scraping Works

- **First run**: Scrapes all historical data (2015–present) using year-by-year Google News queries
- **Every refresh**: Only adds NEW content — all records have a `source_id` hash (URL + title) for deduplication
- **Database never loses old data** — re-running a scrape only adds new incidents

---

## Dashboard Features

### Map
- All historical incidents plotted on Rwanda map
- Marker size scales with death count
- Colour = severity (green → red → purple)
- Filter by severity and incident type
- "All History" / "Recent 72h" / "Deaths Only" modes

### Analytics
- Deaths by incident type (bar chart)
- District hotspots (top 10 by deaths)
- Province comparison
- Full hotspot table with risk scores

### Trends
- Monthly incidents & deaths (2015–present) with 3-month rolling average
- Yearly summary
- Seasonal pattern (which months are most dangerous)
- Incident types stacked by year

### Predictions
- Next-month forecast (incidents + deaths) using weighted moving average + seasonal adjustment
- Top 5 high-risk districts for the next 30 days
- Confidence level based on amount of historical data

---

## Adding Your Anthropic API Key (Optional)

The system works without it (rule-based NLP), but adding an API key enables AI-powered summaries:

```bat
set ANTHROPIC_API_KEY=your_key_here
python app.py
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError` | Run `pip install flask requests beautifulsoup4` |
| Map tiles not loading | Check internet connection |
| No incidents after startup | Wait 1–2 minutes; historical scrape runs in background |
| Nitter mirrors down | Twitter scraping skipped; RSS + Google News still work |
| Port 5050 in use | Change `port=5050` in `app.py` |
