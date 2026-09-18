"""
scraper.py — All scraping logic
Sources:
  1. RSS feeds (Rwanda news sites + humanitarian orgs)
  2. Direct web scraping (Rwanda news sites, paginated)
  3. Google News RSS (no API, free) — expanded queries + year-by-year
  4. ReliefWeb API (free, no key) — primary humanitarian archive
  5. FloodList archive (best historical flood/landslide source)
  6. AllAfrica Rwanda archive (paginated, decade+ of content)
  7. Twitter/X via Nitter public mirrors (no API key)

Incremental mode: only fetches new content since last run.
Historical mode:  goes back as far as possible (2010+).
"""
import re, time, logging, hashlib, json
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
    Rules (in order):
      1. Reject articles from blocked sources (BBC, Voice of America, etc.)
      2. Require at least 1 death OR 1 injured
      3. Claude Rwanda-relevance check (when API key is set)
         — sets enriched["rwanda_verified"] = 1 or 0 in-place
         — fails open (keeps incident) if Claude is unavailable
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
    if not (deaths > 0 or injured > 0):
        return False

    # Rule 3 — Claude Rwanda relevance verification + incident type classification
    import os
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from claude_ai import verify_rwanda_relevance
            result = verify_rwanda_relevance(enriched)
            enriched["rwanda_verified"] = 1 if result["is_rwanda"] else 0

            if not result["is_rwanda"]:
                logger.info(
                    "Rejected non-Rwanda incident: %s — %s",
                    enriched.get("title", "")[:60],
                    result.get("reason", ""),
                )
                return False

            # Apply Claude's incident type — reject if Claude can't assign a real category
            claude_type = result.get("incident_type", "other")
            if claude_type == "violence":
                # Violence (genocide commemorations, attacks, political killings)
                # is out of scope for this public-health accident/disaster system
                logger.info(
                    "Rejected violence-type incident: %s",
                    enriched.get("title", "")[:60],
                )
                return False
            elif claude_type and claude_type != "other":
                enriched["incident_type"] = claude_type
                logger.info(
                    "Claude classified '%s' → %s",
                    enriched.get("title", "")[:60],
                    claude_type,
                )
            else:
                # Claude couldn't determine a valid MCI category — skip this article
                logger.info(
                    "Rejected unclassifiable incident: %s",
                    enriched.get("title", "")[:60],
                )
                return False

        except Exception as exc:
            logger.warning("Rwanda verification skipped: %s", exc)
            enriched["rwanda_verified"] = None  # unverified — show by default

    return True

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

def safe_get_json(url, timeout=15, retries=2):
    for attempt in range(retries):
        try:
            r = requests.get(url, headers={**HEADERS, "Accept": "application/json"}, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            logger.warning(f"HTTP {r.status_code} for {url}")
        except Exception as e:
            logger.warning(f"JSON fetch attempt {attempt+1} failed for {url}: {e}")
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

# ── 1. RSS FEEDS ──────────────────────────────────────────────────────────────
RSS_SOURCES = [
    # ── TIER 1: HUMANITARIAN / OFFICIAL ───────────────────────────────────
    {"name": "ReliefWeb Rwanda",       "url": "https://reliefweb.int/country/rwa/rss.xml"},
    {"name": "WHO AFRO Rwanda",        "url": "https://www.afro.who.int/countries/rwanda/news/rss.xml"},
    {"name": "OCHA Rwanda",            "url": "https://www.unocha.org/country/rwanda/rss.xml"},
    {"name": "PreventionWeb Rwanda",   "url": "https://www.preventionweb.net/feeds/countries/2296"},
    # ── TIER 2: RWANDAN NEWS ──────────────────────────────────────────────
    {"name": "The New Times Rwanda",   "url": "https://www.newtimes.co.rw/rss.xml"},
    {"name": "KT Press Rwanda",        "url": "https://www.ktpress.rw/feed/"},
    {"name": "Igihe",                  "url": "https://igihe.com/feed/"},
    {"name": "Taarifa Rwanda",         "url": "https://taarifa.rw/feed/"},
    {"name": "Rwanda Broadcasting",    "url": "https://www.rba.co.rw/feed/"},
    {"name": "Umuseke",                "url": "https://umuseke.rw/feed/"},
    {"name": "Kigali Today",           "url": "https://kigalitoday.com/feed/"},
    {"name": "Rwanda Focus",           "url": "https://focus.rw/feed/"},
    {"name": "Rwanda Dispatch",        "url": "https://rwandadispatch.com/feed/"},
    {"name": "Rwanda Eye",             "url": "https://rwandaeye.com/feed/"},
    {"name": "The Independent Rwanda", "url": "https://theindependent.co.rw/feed/"},
    {"name": "Imvaho Nshya",           "url": "https://www.imvahonshya.co.rw/feed/"},
    # ── TIER 3: REGIONAL / INTERNATIONAL ─────────────────────────────────
    {"name": "AllAfrica Rwanda",       "url": "https://allafrica.com/tools/headlines/rdf/rwanda/topstories.rdf"},
    {"name": "FloodList",              "url": "https://floodlist.com/feed/"},
    {"name": "Africa News Rwanda",     "url": "https://www.africanews.com/tag/rwanda/rss"},
    {"name": "RFI Africa English",     "url": "https://www.rfi.fr/en/rss/rfi-english-africa.xml"},
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

# ── 2. GOOGLE NEWS RSS ────────────────────────────────────────────────────────
GOOGLE_NEWS_QUERIES = [
    # Road accidents
    "Rwanda road accident killed",
    "Rwanda bus crash killed",
    "Rwanda truck collision deaths",
    "Rwanda matatu accident deaths",
    "Rwanda fatal accident",
    "Rwanda road carnage",
    # Floods & landslides
    "Rwanda flood deaths",
    "Rwanda landslide killed",
    "Rwanda mudslide deaths",
    "Rwanda heavy rains deaths",
    "Rwanda floods casualties",
    # Fires & explosions
    "Rwanda explosion deaths",
    "Rwanda fire killed",
    "Rwanda tanker explosion",
    "Rwanda gas explosion",
    # Disease outbreaks
    "Rwanda outbreak deaths",
    "Rwanda Marburg virus",
    "Rwanda cholera outbreak",
    "Rwanda Ebola",
    "Rwanda disease deaths",
    # Other types
    "Rwanda stampede killed",
    "Rwanda building collapse deaths",
    "Rwanda drowning deaths",
    "Rwanda violence mass casualties",
    # Kinyarwanda / local terms
    "impanuka Rwanda",
    "ibyanuka Rwanda",
    "Rwanda inzira deaths",
    # Generic MCI
    "Rwanda mass casualty",
    "Rwanda disaster deaths",
    "Rwanda emergency deaths",
    "Rwanda casualties",
    "Rwanda tragedy killed",
    # Province / district specific (high-risk areas)
    "Rubavu accident killed",
    "Musanze accident deaths",
    "Huye accident killed",
    "Rusizi flood deaths",
    "Nyamasheke landslide",
]

def scrape_google_news(historical=False, years_back=15) -> int:
    """
    Google News RSS — expanded queries + year-by-year for historical.
    For historical mode: iterates each year individually for better coverage.
    """
    added = 0
    current_year = datetime.utcnow().year

    if historical:
        year_ranges = [(y, y) for y in range(current_year - years_back, current_year + 1)]
    else:
        year_ranges = [(None, None)]

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
                        "source_name":  item.get("source_name") or "Google News",
                        "media_type":   "google_news",
                        "is_historical": historical or (y_start is not None),
                        "source_id": source_id(item.get("source_url",""), item.get("title","")),
                    })
                    if not should_store(enriched):
                        continue
                    if insert_incident(enriched):
                        added += 1
                        logger.info(f"[GNews] {enriched['severity']}★ {enriched['deaths']}💀 {item['title'][:60]}")
                time.sleep(1.5)
            except Exception as e:
                logger.error(f"Google News error [{query} {y_start}]: {e}")
            log_scrape(f"Google News: {query[:40]}", "historical" if historical else "incremental",
                       start, datetime.utcnow().isoformat(), seen, added)
    return added

# ── 3. RELIEFWEB API (free, no key, best humanitarian archive) ─────────────────
RELIEFWEB_BASE = "https://api.reliefweb.int/v1"
RELIEFWEB_APP  = "rwanda-mci-surveillance"

def scrape_reliefweb(historical=False) -> int:
    """
    ReliefWeb REST API — structured humanitarian data back to the 1990s.
    Queries disaster reports, situation reports, and news for Rwanda.
    No API key required.
    """
    added = 0
    page_size = 200

    # Query types: reports (situation reports), news, disasters
    endpoints = [
        {
            "url": f"{RELIEFWEB_BASE}/reports",
            "params": {
                "appname": RELIEFWEB_APP,
                "filter[operator]": "AND",
                "filter[conditions][0][field]": "country.iso3",
                "filter[conditions][0][value]": "RWA",
                "filter[conditions][1][field]": "theme.name",
                "filter[conditions][1][value][]": ["Disaster Management", "Health"],
                "filter[conditions][1][operator]": "OR",
                "fields[include][]": ["title", "date.created", "date.original", "source.name",
                                      "url", "body", "primary_country.name", "disaster.name",
                                      "disaster_type.name"],
                "sort[]": "date.original:desc",
                "limit": page_size,
            },
            "label": "ReliefWeb Reports",
        },
        {
            "url": f"{RELIEFWEB_BASE}/disasters",
            "params": {
                "appname": RELIEFWEB_APP,
                "filter[field]": "country.iso3",
                "filter[value]": "RWA",
                "fields[include][]": ["name", "date.created", "date.event", "glide",
                                      "type.name", "url", "primary_country.name", "description"],
                "sort[]": "date.event:desc",
                "limit": page_size,
            },
            "label": "ReliefWeb Disasters",
        },
    ]

    for ep in endpoints:
        start = datetime.utcnow().isoformat()
        seen = 0
        offset = 0
        max_pages = 10 if historical else 2  # up to 2000 records historically

        while offset // page_size < max_pages:
            try:
                params = {**ep["params"], "offset": offset}
                # Build URL with params
                param_parts = []
                for k, v in params.items():
                    if isinstance(v, list):
                        for val in v:
                            param_parts.append(f"{quote_plus(k)}={quote_plus(str(val))}")
                    else:
                        param_parts.append(f"{quote_plus(k)}={quote_plus(str(v))}")
                full_url = f"{ep['url']}?{'&'.join(param_parts)}"

                data = safe_get_json(full_url, timeout=25)
                if not data:
                    break

                records = data.get("data", [])
                if not records:
                    break

                for rec in records:
                    seen += 1
                    fields = rec.get("fields", {})

                    # Extract fields
                    title = fields.get("title") or fields.get("name") or ""
                    body  = fields.get("body") or fields.get("description") or ""
                    if body:
                        body = re.sub(r"<[^>]+>", " ", body)[:800]

                    date_str = (
                        (fields.get("date") or {}).get("original") or
                        (fields.get("date") or {}).get("event") or
                        (fields.get("date") or {}).get("created") or ""
                    )[:10]

                    source_names = fields.get("source", [])
                    src_name = source_names[0].get("name", "ReliefWeb") if source_names else "ReliefWeb"

                    rw_url   = fields.get("url") or rec.get("href", "")
                    dis_type = ""
                    if fields.get("disaster_type"):
                        dis_type = fields["disaster_type"][0].get("name", "") if fields["disaster_type"] else ""
                    elif fields.get("type"):
                        dis_type = fields["type"][0].get("name", "") if fields["type"] else ""

                    text = f"{title} {body} {dis_type}"
                    if not is_rwanda_relevant(text) or not is_mci_relevant(text):
                        continue

                    enriched = enrich({
                        "title":        title,
                        "description":  body[:400],
                        "full_text":    body,
                        "source_name":  src_name,
                        "source_url":   rw_url,
                        "media_type":   "reliefweb",
                        "published_at": date_str,
                        "is_historical": historical,
                        "source_id": source_id(rw_url, title),
                    })
                    if not should_store(enriched):
                        continue
                    if insert_incident(enriched):
                        added += 1
                        logger.info(f"[ReliefWeb] {enriched['deaths']}💀 {title[:60]}")

                offset += page_size
                if len(records) < page_size:
                    break
                time.sleep(1)

            except Exception as e:
                logger.error(f"ReliefWeb error [{ep['label']} offset={offset}]: {e}")
                break

        log_scrape(ep["label"], "historical" if historical else "incremental",
                   start, datetime.utcnow().isoformat(), seen, added)
    return added

# ── 4. FLOODLIST ARCHIVE (best historical flood/landslide source) ──────────────
def scrape_floodlist(historical=False) -> int:
    """
    FloodList.com — comprehensive historical flood and landslide records for Rwanda.
    Scrapes their tag/country archive with pagination.
    """
    added = 0
    base_url = "https://floodlist.com/tag/rwanda"
    max_pages = 15 if historical else 2
    start = datetime.utcnow().isoformat()
    seen = 0

    for page in range(1, max_pages + 1):
        url = base_url if page == 1 else f"{base_url}/page/{page}"
        try:
            html = safe_get(url, timeout=20)
            if not html:
                break
            soup = BeautifulSoup(html, "html.parser")

            # Article links
            articles = soup.select("article, .post, h2.entry-title a, h1.entry-title a")
            links = []
            for a in soup.select("h2.entry-title a, h1.entry-title a, .entry-title a, article h2 a"):
                href  = a.get("href", "")
                title = a.get_text(strip=True)
                if href and title and "floodlist.com" in href:
                    links.append((href, title))

            if not links:
                break

            for href, title in links:
                seen += 1
                text = title
                if not is_rwanda_relevant(text) or not is_mci_relevant(text):
                    continue

                art_html = safe_get(href, timeout=15)
                full_text, pub_date = "", ""
                if art_html:
                    art_soup = BeautifulSoup(art_html, "html.parser")
                    paras = art_soup.select(".entry-content p, .post-content p, article p")
                    full_text = " ".join(p.get_text(strip=True) for p in paras[:10])
                    date_el = art_soup.select_one("time.entry-date, time[datetime], .entry-date")
                    if date_el:
                        pub_date = date_el.get("datetime", "") or date_el.get_text(strip=True)

                enriched = enrich({
                    "title":        title,
                    "description":  full_text[:400],
                    "full_text":    full_text,
                    "source_name":  "FloodList",
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
                    logger.info(f"[FloodList] {enriched['deaths']}💀 {title[:60]}")
                time.sleep(0.5)

            time.sleep(1.5)
        except Exception as e:
            logger.error(f"FloodList error [page {page}]: {e}")
            break

    log_scrape("FloodList", "historical" if historical else "incremental",
               start, datetime.utcnow().isoformat(), seen, added)
    return added

# ── 5. ALLAFRICA RWANDA ARCHIVE (paginated) ───────────────────────────────────
def scrape_allafrica(historical=False) -> int:
    """
    AllAfrica.com — one of the most comprehensive African news archives.
    Scrapes Rwanda section with keyword-filtered pagination.
    """
    added = 0
    keywords = [
        "accident", "killed", "dead", "flood", "landslide",
        "explosion", "fire", "stampede", "collapse", "drowning",
        "outbreak", "disaster", "casualties", "deaths",
    ]
    base_url = "https://allafrica.com/rwanda/"
    max_pages = 20 if historical else 3
    start_global = datetime.utcnow().isoformat()
    seen = 0

    for page in range(1, max_pages + 1):
        url = base_url if page == 1 else f"{base_url}?page={page}"
        try:
            html = safe_get(url, timeout=20)
            if not html:
                break
            soup = BeautifulSoup(html, "html.parser")

            # AllAfrica article links
            links = []
            for a in soup.select("h3 a, .stories-list a, .headline a, h4 a"):
                href  = a.get("href", "")
                title = a.get_text(strip=True)
                if not href or not title or len(title) < 10:
                    continue
                if not href.startswith("http"):
                    href = "https://allafrica.com" + href
                # Only keep articles likely to be MCI-related
                title_lower = title.lower()
                if any(kw in title_lower for kw in keywords):
                    links.append((href, title))

            if not links:
                break

            for href, title in links:
                seen += 1
                text = title
                if not is_rwanda_relevant(text) or not is_mci_relevant(text):
                    continue

                art_html = safe_get(href, timeout=15)
                full_text, pub_date = "", ""
                if art_html:
                    art_soup = BeautifulSoup(art_html, "html.parser")
                    paras = art_soup.select(".story-body p, .article-content p, article p, #article-body p")
                    full_text = " ".join(p.get_text(strip=True) for p in paras[:8])
                    date_el = art_soup.select_one("time, .date, .pub-date, [itemprop='datePublished']")
                    if date_el:
                        pub_date = date_el.get("datetime", "") or date_el.get_text(strip=True)

                enriched = enrich({
                    "title":        title,
                    "description":  full_text[:400],
                    "full_text":    full_text,
                    "source_name":  "AllAfrica",
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
                    logger.info(f"[AllAfrica] {enriched['deaths']}💀 {title[:60]}")
                time.sleep(0.5)

            time.sleep(2)
        except Exception as e:
            logger.error(f"AllAfrica error [page {page}]: {e}")
            break

    log_scrape("AllAfrica Rwanda", "historical" if historical else "incremental",
               start_global, datetime.utcnow().isoformat(), seen, added)
    return added

# ── 6. DIRECT NEWS SITE SCRAPING (paginated) ──────────────────────────────────
NEWS_SITES = [
    # ── TIER 1: MAJOR RWANDAN ENGLISH OUTLETS ─────────────────────────────
    {
        "name":      "The New Times Rwanda",
        "search_url":"https://www.newtimes.co.rw/?s={}",
        "paginate":  "https://www.newtimes.co.rw/?s={}&paged={}",
        "article_selector": "h3.entry-title a, h2.entry-title a, .post-title a",
        "content_selector": ".entry-content p, .article-body p, article p",
        "date_selector":    ".entry-date, .post-date, time",
    },
    {
        "name":       "KT Press Rwanda",
        "search_url": "https://www.ktpress.rw/?s={}",
        "paginate":   "https://www.ktpress.rw/?s={}&paged={}",
        "article_selector": "h2.entry-title a, h3.entry-title a",
        "content_selector": ".entry-content p",
        "date_selector":    ".entry-date, time",
    },
    {
        "name":       "Taarifa Rwanda",
        "search_url": "https://taarifa.rw/?s={}",
        "paginate":   "https://taarifa.rw/?s={}&paged={}",
        "article_selector": "h2.entry-title a, h3.entry-title a, .post-title a",
        "content_selector": ".entry-content p, .post-content p",
        "date_selector":    "time, .entry-date",
    },
    {
        "name":       "Kigali Today",
        "search_url": "https://kigalitoday.com/?s={}",
        "paginate":   "https://kigalitoday.com/?s={}&paged={}",
        "article_selector": "h2.entry-title a, h3.entry-title a, .post-title a",
        "content_selector": ".entry-content p, .post-content p, article p",
        "date_selector":    "time, .entry-date, .post-date",
    },
    {
        "name":       "Rwanda Focus",
        "search_url": "https://focus.rw/?s={}",
        "paginate":   "https://focus.rw/?s={}&paged={}",
        "article_selector": "h2.entry-title a, h3.entry-title a, .td-module-title a",
        "content_selector": ".entry-content p, .td-post-content p",
        "date_selector":    "time, .entry-date, .td-post-date",
    },
    {
        "name":       "Rwanda Dispatch",
        "search_url": "https://rwandadispatch.com/?s={}",
        "paginate":   "https://rwandadispatch.com/?s={}&paged={}",
        "article_selector": "h2.entry-title a, h3.entry-title a, .post-title a",
        "content_selector": ".entry-content p, .post-content p",
        "date_selector":    "time, .entry-date",
    },
    {
        "name":       "Rwanda Eye",
        "search_url": "https://rwandaeye.com/?s={}",
        "paginate":   "https://rwandaeye.com/?s={}&paged={}",
        "article_selector": "h2.entry-title a, h3.entry-title a, .post-title a",
        "content_selector": ".entry-content p, .post-content p, article p",
        "date_selector":    "time, .entry-date",
    },
    {
        "name":       "The Independent Rwanda",
        "search_url": "https://theindependent.co.rw/?s={}",
        "paginate":   "https://theindependent.co.rw/?s={}&paged={}",
        "article_selector": "h2.entry-title a, h3.entry-title a, .post-title a",
        "content_selector": ".entry-content p, .post-content p, article p",
        "date_selector":    "time, .entry-date, .post-date",
    },
    # ── TIER 2: KINYARWANDA OUTLETS ───────────────────────────────────────
    {
        "name":       "Igihe",
        "search_url": "https://igihe.com/?s={}",
        "paginate":   "https://igihe.com/?s={}&paged={}",
        "article_selector": "h2.entry-title a, h3.entry-title a",
        "content_selector": ".entry-content p",
        "date_selector":    "time, .entry-date",
    },
    {
        "name":       "Umuseke",
        "search_url": "https://umuseke.rw/?s={}",
        "paginate":   "https://umuseke.rw/?s={}&paged={}",
        "article_selector": "h2.entry-title a, h3.entry-title a, .post-title a",
        "content_selector": ".entry-content p, .post-content p",
        "date_selector":    "time, .entry-date",
    },
    {
        "name":       "Imvaho Nshya",
        "search_url": "https://www.imvahonshya.co.rw/?s={}",
        "paginate":   "https://www.imvahonshya.co.rw/?s={}&paged={}",
        "article_selector": "h2.entry-title a, h3.entry-title a, .post-title a",
        "content_selector": ".entry-content p, .post-content p, article p",
        "date_selector":    "time, .entry-date",
    },
    # ── TIER 3: BROADCAST / GOVERNMENT ───────────────────────────────────
    {
        "name":       "Rwanda Broadcasting Agency",
        "search_url": "https://www.rba.co.rw/?s={}",
        "paginate":   "https://www.rba.co.rw/?s={}&paged={}",
        "article_selector": "h2.entry-title a, h3.entry-title a, .post-title a",
        "content_selector": ".entry-content p, .post-content p",
        "date_selector":    "time, .entry-date",
    },
    {
        "name":       "Rwanda Today",
        "search_url": "https://rwandatoday.africa/?s={}",
        "paginate":   "https://rwandatoday.africa/?s={}&paged={}",
        "article_selector": "h3.entry-title a, h2.td-module-title a",
        "content_selector": ".td-post-content p",
        "date_selector":    "time.entry-date",
    },
]

SCRAPE_QUERIES = [
    "accident killed",
    "flood deaths",
    "landslide killed",
    "explosion deaths",
    "fire killed",
    "crash deaths",
    "disaster Rwanda",
    "casualties Rwanda",
    "drowning deaths",
    "stampede",
    "building collapse",
    "outbreak deaths",
]

def scrape_news_sites(historical=False) -> int:
    added = 0
    max_pages = 5 if historical else 1

    for site in NEWS_SITES:
        for query in SCRAPE_QUERIES:
            for page in range(1, max_pages + 1):
                start = datetime.utcnow().isoformat()
                seen = 0
                try:
                    if page == 1:
                        url = site["search_url"].format(quote_plus(query))
                    else:
                        url = site.get("paginate", site["search_url"]).format(quote_plus(query), page)

                    html = safe_get(url)
                    if not html:
                        break
                    soup = BeautifulSoup(html, "html.parser")
                    links = soup.select(site["article_selector"])[:15]
                    if not links:
                        break  # no more results

                    for link in links:
                        href = link.get("href","")
                        title = link.get_text(strip=True)
                        if not href or not title:
                            continue
                        seen += 1
                        text = f"{title}"
                        if not is_rwanda_relevant(text) or not is_mci_relevant(text) or not is_civilian_mci(text):
                            continue
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
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"Site scrape error [{site['name']} / {query} p{page}]: {e}")
                    break
                log_scrape(site["name"], "historical" if historical else "incremental",
                           start, datetime.utcnow().isoformat(), seen, added)
    return added

# ── 7. TWITTER / X via Nitter mirrors (no API key) ───────────────────────────
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

# ── 8. HISTORICAL DEEP SCRAPE ─────────────────────────────────────────────────
def run_historical_scrape() -> dict:
    """
    Full historical scrape — runs once (or when user triggers it).
    Pulls data from 2010 to present across all sources.
    Priority order: ReliefWeb (best archive) → FloodList → Google News
    (year-by-year) → AllAfrica (paginated) → News sites (paginated) → RSS → Twitter
    """
    logger.info("=" * 60)
    logger.info("STARTING HISTORICAL SCRAPE (2010 → present)")
    logger.info("=" * 60)
    results = {}
    results["reliefweb"]  = scrape_reliefweb(historical=True)
    results["floodlist"]  = scrape_floodlist(historical=True)
    results["google_news"]= scrape_google_news(historical=True, years_back=15)
    results["allafrica"]  = scrape_allafrica(historical=True)
    results["news_sites"] = scrape_news_sites(historical=True)
    results["rss"]        = scrape_rss(historical=True)
    results["twitter"]    = scrape_nitter(historical=True)
    total = sum(results.values())
    logger.info(f"Historical scrape complete. Total new incidents: {total}")
    logger.info(f"Breakdown: {results}")
    return results

# ── 9. INCREMENTAL REFRESH ────────────────────────────────────────────────────
def run_incremental_scrape() -> dict:
    """
    Incremental refresh — adds only NEW content since last run.
    Safe to call every 30 minutes; dedup prevents double-counting.
    """
    logger.info("Running incremental scrape...")
    results = {}
    results["reliefweb"]  = scrape_reliefweb(historical=False)
    results["rss"]        = scrape_rss(historical=False)
    results["google_news"]= scrape_google_news(historical=False)
    results["floodlist"]  = scrape_floodlist(historical=False)
    results["allafrica"]  = scrape_allafrica(historical=False)
    results["news_sites"] = scrape_news_sites(historical=False)
    results["twitter"]    = scrape_nitter(historical=False)
    total = sum(results.values())
    logger.info(f"Incremental scrape complete. New incidents added: {total}")
    return results
