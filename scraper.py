"""
scraper.py — All scraping logic
Sources:
  1. RSS feeds (Rwanda news sites)
  2. Direct web scraping (Rwanda news sites)
  3. Google News RSS (no API, free)
  4. Twitter/X via Nitter public mirrors (no API key)
  5. Historical Google search scraping

Incremental mode: only fetches new content since last run.
Historical mode:  goes back as far as possible (2015+).
"""
import re, time, logging, hashlib
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlparse, quote_plus
from urllib.request import Request, urlopen
from urllib.error import URLError
import requests
from bs4 import BeautifulSoup

from database import insert_incident, source_id, get_cursor, set_cursor, log_scrape
from nlp import enrich, is_mci_relevant, is_rwanda_relevant, is_civilian_mci

logger = logging.getLogger(__name__)

def should_store(enriched: dict) -> bool:
    """
    Gate before insert_incident().
    Two rules:
      1. Reject articles from blocked sources (BBC, Voice of America, etc.)
      2. Require at least 1 death OR 1 injured
    """
    # Rule 1 — blocked source check
    try:
        from source_registry import is_blocked_source
        if is_blocked_source(
            source_name=enriched.get("source_name", ""),
            title=enriched.get("title", ""),
            url=enriched.get("source_url", ""),
        ):
            return False
    except Exception:
        pass

    # Rule 2 — must have casualties
    deaths  = int(enriched.get("deaths")  or 0)
    injured = int(enriched.get("injured") or 0)
    return deaths > 0 or injured > 0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def safe_get(url, timeout=15, retries=2):
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r.text
            logger.warning(f"HTTP {r.status_code} for {url}")
        except Exception as e:
            logger.warning(f"Fetch attempt {attempt+1} failed for {url}: {e}")
            time.sleep(2)
    return None

def parse_rss(xml_text: str) -> list:
    """Parse RSS/Atom XML manually (no feedparser needed)."""
    items = []
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        # RSS 2.0
        for item in root.findall(".//item"):
            def t(tag): el = item.find(tag); return el.text.strip() if el is not None and el.text else ""
            pub = t("pubDate") or t("dc:date") or ""
            items.append({
                "title":       t("title"),
                "description": re.sub(r"<[^>]+>", "", t("description")),
                "source_url":  t("link") or t("guid"),
                "published_at": pub,
            })

        # Atom
        for entry in root.findall(".//atom:entry", ns):
            def ta(tag): el = entry.find(f"atom:{tag}", ns); return el.text.strip() if el is not None and el.text else ""
            link_el = entry.find("atom:link", ns)
            url = link_el.get("href","") if link_el is not None else ""
            items.append({
                "title":       ta("title"),
                "description": re.sub(r"<[^>]+>","", ta("summary") or ta("content")),
                "source_url":  url,
                "published_at": ta("updated") or ta("published"),
            })
    except Exception as e:
        logger.warning(f"RSS parse error: {e}")
    return items

# ── 1. RSS FEEDS (organised by source tier) ──────────────────────────────────
RSS_SOURCES = [
    # ── TIER 1: OFFICIAL COMMUNICATION ────────────────────────────────────
    {"name": "ReliefWeb Rwanda",      "url": "https://reliefweb.int/country/rwa/rss.xml"},
    {"name": "WHO Rwanda",            "url": "https://www.afro.who.int/countries/rwanda/news/rss.xml"},
    # ── TIER 2: OFFICIAL JOURNALISM ───────────────────────────────────────
    {"name": "The New Times Rwanda",  "url": "https://www.newtimes.co.rw/rss.xml"},
    {"name": "KT Press",              "url": "https://www.ktpress.rw/feed/"},
    {"name": "Igihe",                 "url": "https://igihe.com/feed/"},
    {"name": "Rwanda Broadcasting",   "url": "https://www.rba.co.rw/feed/"},
    # ── TIER 3: OTHER SOURCES (aggregators / international) ───────────────
    {"name": "AllAfrica Rwanda",      "url": "https://allafrica.com/rwanda/"},
]

def scrape_rss(historical=False) -> int:
    added = 0
    for src in RSS_SOURCES:
        start = datetime.utcnow().isoformat()
        seen = 0
        try:
            html = safe_get(src["url"])
            if not html:
                continue
            items = parse_rss(html)
            for item in items:
                seen += 1
                text = f"{item['title']} {item['description']}"
                if not is_rwanda_relevant(text) or not is_mci_relevant(text) or not is_civilian_mci(text):
                    continue
                enriched = enrich({
                    **item,
                    "source_name": src["name"],
                    "media_type":  "news_rss",
                    "is_historical": historical,
                    "source_id": source_id(item.get("source_url",""), item.get("title","")),
                })
                if not should_store(enriched):
                    continue
                if insert_incident(enriched):
                    added += 1
                    logger.info(f"[RSS] {enriched['severity']}★ {enriched['deaths']}💀 {item['title'][:60]}")
        except Exception as e:
            logger.error(f"RSS error [{src['name']}]: {e}")
        log_scrape(src["name"], "historical" if historical else "incremental",
                   start, datetime.utcnow().isoformat(), seen, added)
    return added

# ── 2. GOOGLE NEWS RSS (free, no API) ─────────────────────────────────────────
GOOGLE_NEWS_QUERIES = [
    "Rwanda mass casualty",
    "Rwanda accident killed",
    "Rwanda flood deaths",
    "Rwanda landslide killed",
    "Rwanda explosion deaths",
    "Rwanda bus crash killed",
    "Rwanda fire deaths",
    "Rwanda drowning deaths",
    "Rwanda stampede",
    "Rwanda building collapse",
    "impanuka Rwanda",
    "Rwanda road carnage",
    "Rwanda disaster deaths",
]

def scrape_google_news(historical=False, years_back=10) -> int:
    """
    Google News RSS supports a 'when' param for recent news and
    date ranges via 'after:YYYY-MM-DD before:YYYY-MM-DD' in query.
    For historical: iterates year by year from (current - years_back).
    """
    added = 0
    current_year = datetime.utcnow().year

    if historical:
        year_ranges = [(y, y) for y in range(current_year - years_back, current_year + 1)]
    else:
        year_ranges = [(None, None)]  # no date filter = latest

    for query in GOOGLE_NEWS_QUERIES:
        for (y_start, y_end) in year_ranges:
            start = datetime.utcnow().isoformat()
            seen = 0
            try:
                if y_start:
                    q = f"{query} after:{y_start}-01-01 before:{y_end}-12-31"
                else:
                    q = query

                url = f"https://news.google.com/rss/search?q={quote_plus(q)}&hl=en-RW&gl=RW&ceid=RW:en"
                html = safe_get(url, timeout=20)
                if not html:
                    continue
                items = parse_rss(html)
                for item in items:
                    seen += 1
                    text = f"{item['title']} {item['description']}"
                    if not is_rwanda_relevant(text) or not is_mci_relevant(text) or not is_civilian_mci(text):
                        continue
                    enriched = enrich({
                        **item,
                        "source_name":  "Google News",
                        "media_type":   "google_news",
                        "is_historical": historical or (y_start is not None),
                        "source_id": source_id(item.get("source_url",""), item.get("title","")),
                    })
                    if not should_store(enriched):
                        continue
                    if insert_incident(enriched):
                        added += 1
                        logger.info(f"[GNews] {enriched['severity']}★ {enriched['deaths']}💀 {item['title'][:60]}")
                time.sleep(1.5)  # polite delay
            except Exception as e:
                logger.error(f"Google News error [{query} {y_start}]: {e}")
            log_scrape(f"Google News: {query}", "historical" if historical else "incremental",
                       start, datetime.utcnow().isoformat(), seen, added)
    return added

# ── 3. DIRECT NEWS SITE SCRAPING ─────────────────────────────────────────────
NEWS_SITES = [
    {
        "name":      "The New Times Rwanda",
        "search_url":"https://www.newtimes.co.rw/?s={}",
        "article_selector": "h3.entry-title a, h2.entry-title a, .post-title a",
        "content_selector": ".entry-content p, .article-body p, article p",
        "date_selector":    ".entry-date, .post-date, time",
    },
    {
        "name":       "KT Press Rwanda",
        "search_url": "https://www.ktpress.rw/?s={}",
        "article_selector": "h2.entry-title a, h3.entry-title a",
        "content_selector": ".entry-content p",
        "date_selector":    ".entry-date, time",
    },
    {
        "name":       "Rwanda Today",
        "search_url": "https://rwandatoday.africa/?s={}",
        "article_selector": "h3.entry-title a, h2.td-module-title a",
        "content_selector": ".td-post-content p",
        "date_selector":    "time.entry-date",
    },
]

SCRAPE_QUERIES = [
    "accident killed", "flood deaths", "landslide killed",
    "explosion deaths", "fire killed", "crash deaths",
    "disaster Rwanda", "casualties Rwanda",
]

def scrape_news_sites(historical=False) -> int:
    added = 0
    for site in NEWS_SITES:
        for query in SCRAPE_QUERIES:
            start = datetime.utcnow().isoformat()
            seen = 0
            try:
                url = site["search_url"].format(quote_plus(query))
                html = safe_get(url)
                if not html:
                    continue
                soup = BeautifulSoup(html, "html.parser")
                links = soup.select(site["article_selector"])[:10]
                for link in links:
                    href = link.get("href","")
                    title = link.get_text(strip=True)
                    if not href or not title:
                        continue
                    seen += 1
                    text = f"{title}"
                    if not is_rwanda_relevant(text) or not is_mci_relevant(text) or not is_civilian_mci(text):
                        continue
                    # fetch article content
                    art_html = safe_get(href)
                    full_text, pub_date = "", ""
                    if art_html:
                        art_soup = BeautifulSoup(art_html, "html.parser")
                        paragraphs = art_soup.select(site["content_selector"])
                        full_text = " ".join(p.get_text(strip=True) for p in paragraphs[:8])
                        date_el = art_soup.select_one(site["date_selector"])
                        if date_el:
                            pub_date = date_el.get("datetime","") or date_el.get_text(strip=True)
                    enriched = enrich({
                        "title":        title,
                        "description":  full_text[:400],
                        "full_text":    full_text,
                        "source_name":  site["name"],
                        "source_url":   href,
                        "media_type":   "news_scrape",
                        "published_at": pub_date,
                        "is_historical": historical,
                        "source_id": source_id(href, title),
                    })
                    if not should_store(enriched):
                        continue
                    if insert_incident(enriched):
                        added += 1
                        logger.info(f"[Scrape] {enriched['severity']}★ {enriched['deaths']}💀 {title[:60]}")
                    time.sleep(0.5)
            except Exception as e:
                logger.error(f"Site scrape error [{site['name']} / {query}]: {e}")
            log_scrape(site["name"], "historical" if historical else "incremental",
                       start, datetime.utcnow().isoformat(), seen, added)
    return added

# ── 4. TWITTER / X via Nitter mirrors (no API key) ───────────────────────────
NITTER_MIRRORS = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.1d4.us",
]

TWITTER_QUERIES = [
    "Rwanda accident killed",
    "Rwanda flood deaths",
    "Rwanda landslide killed",
    "Rwanda explosion killed",
    "Rwanda fire deaths",
    "Rwanda crash killed",
    "impanuka Rwanda",
    "Rwanda disaster dead",
    "Rwanda emergency killed",
]

def scrape_nitter(historical=False) -> int:
    added = 0
    mirror = None

    # find a working mirror
    for m in NITTER_MIRRORS:
        try:
            r = requests.get(f"{m}/search?q=Rwanda&f=tweets", headers=HEADERS, timeout=8)
            if r.status_code == 200 and "tweet" in r.text.lower():
                mirror = m
                break
        except:
            continue

    if not mirror:
        logger.warning("[Nitter] No working mirror found. Skipping Twitter scrape.")
        return 0

    for query in TWITTER_QUERIES:
        start = datetime.utcnow().isoformat()
        seen = 0
        try:
            url = f"{mirror}/search?q={quote_plus(query)}&f=tweets"
            html = safe_get(url)
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            tweets = soup.select(".timeline-item, .tweet-body")
            for tweet in tweets[:20]:
                seen += 1
                content_el = tweet.select_one(".tweet-content, .content")
                date_el    = tweet.select_one(".tweet-date a, .date a")
                link_el    = tweet.select_one(".tweet-link, .tweet-date a")
                if not content_el:
                    continue
                text    = content_el.get_text(strip=True)
                pub     = date_el.get("title","") if date_el else ""
                tw_url  = link_el.get("href","") if link_el else ""
                if tw_url and not tw_url.startswith("http"):
                    tw_url = mirror + tw_url

                if not is_rwanda_relevant(text) or not is_mci_relevant(text) or not is_civilian_mci(text):
                    continue

                # Detect official Twitter accounts (Tier 2) vs general (Tier 3)
                tw_lower = tw_url.lower()
                official_handles = ["rwandapolice","moh_rwanda","minema_rwanda",
                                    "rwandagov","paulkagame","rwandahealth",
                                    "rwandarcs","rdfrwanda"]
                source_name = "Twitter/X"
                for handle in official_handles:
                    if f"/{handle}/" in tw_lower or f"@{handle}" in text.lower():
                        source_name = f"Twitter/X — @{handle}"
                        break

                enriched = enrich({
                    "title":        text[:140],
                    "description":  text,
                    "full_text":    text,
                    "source_name":  source_name,
                    "source_url":   tw_url,
                    "media_type":   "twitter",
                    "published_at": pub,
                    "is_historical": historical,
                    "source_id": source_id(tw_url, text[:80]),
                })
                if not should_store(enriched):
                    continue
                if insert_incident(enriched):
                    added += 1
                    logger.info(f"[Nitter] {enriched['severity']}★ {enriched['deaths']}💀 {text[:60]}")
            time.sleep(2)
        except Exception as e:
            logger.error(f"Nitter error [{query}]: {e}")
        log_scrape("Twitter/Nitter", "historical" if historical else "incremental",
                   start, datetime.utcnow().isoformat(), seen, added)
    return added

# ── 5. HISTORICAL DEEP SCRAPE ─────────────────────────────────────────────────
def run_historical_scrape() -> dict:
    """
    Full historical scrape — runs once (or when user triggers it).
    Pulls data from 2015 to present across all sources.
    """
    logger.info("=" * 60)
    logger.info("STARTING HISTORICAL SCRAPE (2015 → present)")
    logger.info("=" * 60)
    results = {}
    results["rss"]         = scrape_rss(historical=True)
    results["google_news"] = scrape_google_news(historical=True, years_back=10)
    results["news_sites"]  = scrape_news_sites(historical=True)
    results["twitter"]     = scrape_nitter(historical=True)
    total = sum(results.values())
    logger.info(f"Historical scrape complete. Total new incidents: {total}")
    logger.info(f"Breakdown: {results}")
    return results

# ── 6. INCREMENTAL REFRESH ────────────────────────────────────────────────────
def run_incremental_scrape() -> dict:
    """
    Incremental refresh — adds only NEW content since last run.
    Safe to call every 30 minutes; dedup prevents double-counting.
    """
    logger.info("Running incremental scrape...")
    results = {}
    results["rss"]         = scrape_rss(historical=False)
    results["google_news"] = scrape_google_news(historical=False)
    results["news_sites"]  = scrape_news_sites(historical=False)
    results["twitter"]     = scrape_nitter(historical=False)
    total = sum(results.values())
    logger.info(f"Incremental scrape complete. New incidents added: {total}")
    return results
