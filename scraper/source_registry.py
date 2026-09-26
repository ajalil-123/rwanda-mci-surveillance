"""
source_registry.py — Source classification per Ministry of Health requirements.

Three tiers (per supervisor's classification):

  TIER 1 — OFFICIAL COMMUNICATION
    Direct government / official institutional sources.
    Highest credibility. Used for verified incident reporting.

  TIER 2 — OFFICIAL JOURNALISM / OFFICIAL SOCIAL MEDIA
    Established Rwandan news outlets + verified official social accounts.
    Credible journalism; data may need brief verification before action.

  TIER 3 — OTHER SOURCES
    Aggregators, international media, unverified social media.
    Use as early signals; verify before acting on casualty figures.
"""

# ── TIER 1: OFFICIAL COMMUNICATION ────────────────────────────────────────────
# Direct government / institutional sources
TIER_1_SOURCES = {
    # Government ministries
    "MINEMA":                      "Ministry of Emergency Management",
    "Ministry of Emergency Management":"Ministry of Emergency Management",
    "Ministry of Health Rwanda":   "Ministry of Health",
    "MoH Rwanda":                  "Ministry of Health",
    "RBC":                         "Rwanda Biomedical Centre",
    "Rwanda Biomedical Centre":    "Rwanda Biomedical Centre",
    # Security / response services
    "Rwanda National Police":      "Rwanda National Police",
    "RNP":                         "Rwanda National Police",
    "Rwanda Defence Force":        "Rwanda Defence Force",
    "RDF":                         "Rwanda Defence Force",
    # International humanitarian (official UN/WHO)
    "ReliefWeb Rwanda":            "UN ReliefWeb",
    "WHO Rwanda":                  "World Health Organization",
    "WHO AFRO":                    "World Health Organization (Africa)",
    "UNICEF Rwanda":               "UNICEF Rwanda",
    # Other government bodies
    "Rwanda Red Cross":            "Rwanda Red Cross Society",
    "MIDIMAR":                     "Disaster Management & Refugee Affairs",
}

# ── TIER 2: OFFICIAL JOURNALISM / OFFICIAL SOCIAL ACCOUNTS ────────────────────
# Established Rwandan news outlets + reputable international journalism
TIER_2_SOURCES = {
    # National news outlets (Rwanda)
    "The New Times Rwanda":   "The New Times (national newspaper)",
    "The New Times":          "The New Times (national newspaper)",
    "KT Press":               "KT Press (national news)",
    "KT Press Rwanda":        "KT Press (national news)",
    "Rwanda Broadcasting":    "RBA (state broadcaster)",
    "RBA":                    "RBA (state broadcaster)",
    "Igihe":                  "Igihe (national news, Kinyarwanda)",
    "Rwanda Today":           "Rwanda Today",
    # Official social accounts
    "Twitter/X — @RwandaPolice":   "Rwanda National Police (official social)",
    "Twitter/X — @MoH_Rwanda":     "Ministry of Health (official social)",
    "Twitter/X — @MINEMA_Rwanda":  "MINEMA (official social)",
    "Twitter/X — @RwandaGov":      "Government of Rwanda (official social)",
    "Twitter/X — @PaulKagame":     "Office of the President (official social)",
}

# ── TIER 3: OTHER SOURCES ─────────────────────────────────────────────────────
# Aggregators, lesser-known international media, unverified social
TIER_3_SOURCES = {
    "Google News":          "Google News (aggregator)",
    "AllAfrica":            "AllAfrica (aggregator)",
    "AllAfrica Rwanda":     "AllAfrica (aggregator)",
    "allAfrica.com":        "AllAfrica (aggregator)",
    "Africanews":           "Africanews (regional)",
    "africanews.com":       "Africanews (regional)",
    "TRT World":            "TRT World (international)",
    "trtworld":             "TRT World (international)",
    "trtworld.com":         "TRT World (international)",
    "Twitter/X":            "Twitter/X (unverified social)",
    "Facebook":             "Facebook (unverified social)",
    "Facebook (simulated)": "Facebook (unverified social)",
    "Twitter (simulated)":  "Twitter/X (unverified social)",
    # Regional / African journalism (placed in Other per supervisor's classification)
    "Daily Monitor":        "Daily Monitor (regional)",
    "The Independent Uganda":"The Independent Uganda (regional)",
    "The Independent Ugan": "The Independent Uganda (regional)",
    "Daily Nation":         "Daily Nation (regional)",
    "The EastAfrican":      "The EastAfrican (regional)",
    "The Guardian":         "The Guardian",
    "The Guardian Nigeria News": "The Guardian Nigeria News",
    "Guardian Nigeria":     "The Guardian Nigeria News",
    "Independent Newspaper Nigeria": "Independent Newspaper Nigeria",
    "Independent Nigeria":  "Independent Newspaper Nigeria",
    # Smaller / less editorial international outlets
    "FloodList":            "FloodList (specialist blog)",
    "Pan African Visions":  "Pan African Visions",
    "pan african visions":  "Pan African Visions",
    "P.M. News":            "P.M. News",
    "The Sun Nigeria":      "The Sun Nigeria",
    "Qatar Tribune":        "Qatar Tribune",
    "Daily Sabah":          "Daily Sabah",
    "Agenzia Nova":         "Agenzia Nova",
    "One News Page":        "One News Page (aggregator)",
    "Oman Observer":        "Oman Observer",
    "5 Dariya News":        "5 Dariya News",
    "The Eastleigh Voice":  "The Eastleigh Voice",
    "تسنیم":                "Tasnim (international)",
    "ChimpReports":         "ChimpReports",
    "Outside Magazine":     "Outside Magazine",
    "CyclingUpToDate":      "Cycling outlet",
    "Sky News":             "Sky News",
}

# ── Tier metadata ─────────────────────────────────────────────────────────────
# Sources excluded entirely — articles from these outlets are rejected at
# scrape time and any existing records will be removed by reprocess_db.py.
BLOCKED_SOURCES = [
    # BBC
    "bbc", "bbc news", "bbc africa", "bbc.com", "bbc.co.uk",
    # Voice of America
    "voice of america", "voanews", "voa news", "voa.com", "voanews.com",
    # Other international wire services / broadcasters (blocked per supervisor)
    "reuters", "reuters.com",
    "associated press", "ap news", "apnews.com",
    "afp", "agence france-presse", "afp.com",
    "france 24", "france24", "france24.com",
    "dw", "deutsche welle", "dw.com",
    "al jazeera", "aljazeera", "aljazeera.com",
]

def is_blocked_source(source_name: str = "", title: str = "", url: str = "") -> bool:
    """
    Returns True if the source should be excluded entirely from scraping/storage.
    Checks source name, article title (for aggregator-extracted publisher),
    and URL (for direct-scraped sources).
    """
    haystacks = [
        (source_name or "").lower(),
        (title or "").lower(),
        (url or "").lower(),
    ]
    for blocked in BLOCKED_SOURCES:
        for h in haystacks:
            if blocked in h:
                return True
    return False


TIER_INFO = {
    1: {
        "code":        "T1",
        "label":       "Official Communication",
        "description": "Direct government and institutional sources",
        "credibility": "Highest",
        "color":       "#3fb950",   # green
        "weight":      1.0,
    },
    2: {
        "code":        "T2",
        "label":       "Official Journalism / Social Media",
        "description": "Established Rwandan news outlets and verified official social accounts",
        "credibility": "High",
        "color":       "#388bfd",   # blue
        "weight":      0.75,
    },
    3: {
        "code":        "T3",
        "label":       "Other Sources",
        "description": "Aggregators, international media, unverified social media",
        "credibility": "Moderate — verify before action",
        "color":       "#d29922",   # amber
        "weight":      0.4,
    },
}


def classify_source(source_name: str) -> int:
    """
    Return the tier (1, 2, or 3) for a given source name.
    Defaults to tier 3 if the source is not recognised.
    Matching is case-insensitive and tolerates partial matches.
    """
    if not source_name:
        return 3

    s = source_name.strip()

    # Exact match first (fastest)
    if s in TIER_1_SOURCES: return 1
    if s in TIER_2_SOURCES: return 2
    if s in TIER_3_SOURCES: return 3

    # Case-insensitive partial match
    s_lower = s.lower()

    for key in TIER_1_SOURCES:
        if key.lower() in s_lower or s_lower in key.lower():
            return 1
    for key in TIER_2_SOURCES:
        if key.lower() in s_lower or s_lower in key.lower():
            return 2
    for key in TIER_3_SOURCES:
        if key.lower() in s_lower or s_lower in key.lower():
            return 3

    # Default — unrecognised source
    return 3


def extract_publisher_from_title(title: str) -> str:
    """
    Google News and similar aggregators format titles as:
      "Article headline - Publisher Name"
    or
      "Article headline | Publisher Name"
    This extracts the publisher portion so we can classify it correctly.
    """
    if not title:
        return ""
    # Try " - " separator first (Google News standard)
    if " - " in title:
        publisher = title.rsplit(" - ", 1)[-1].strip()
        # Clean trailing periods and "..." artifacts
        publisher = publisher.rstrip(".").strip()
        return publisher
    # Try " | " separator (some sources use this)
    if " | " in title:
        return title.rsplit(" | ", 1)[-1].strip()
    # Try "| " (no leading space)
    if "| " in title:
        return title.rsplit("| ", 1)[-1].strip()
    return ""


def classify_from_title_and_source(title: str, source_name: str) -> tuple[int, str]:
    """
    Smart classifier: if source is an aggregator (Google News, etc.),
    extract the real publisher from the article title and classify THAT.
    Returns (tier, effective_source_name) so we can store the real publisher.
    """
    AGGREGATORS = ("google news", "allafrica", "news aggregator")

    if source_name and source_name.lower() in AGGREGATORS:
        publisher = extract_publisher_from_title(title)
        if publisher:
            tier = classify_source(publisher)
            return tier, publisher

    # Not an aggregator — classify the source directly
    return classify_source(source_name), source_name


def get_tier_info(tier: int) -> dict:
    """Return full metadata for a tier number."""
    return TIER_INFO.get(tier, TIER_INFO[3])


def get_official_label(source_name: str) -> str:
    """Return the friendly institutional label for a source, if known."""
    if not source_name:
        return source_name
    s = source_name.strip()
    return (TIER_1_SOURCES.get(s) or
            TIER_2_SOURCES.get(s) or
            TIER_3_SOURCES.get(s) or
            source_name)
