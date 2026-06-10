"""
nlp.py — keyword extraction, severity scoring, geo-tagging, date parsing
No external NLP libraries needed — pure Python regex + dictionaries.

Fixes applied:
  - Written number support (two, three, dozen, etc.) in death/injury extraction
  - Named-person killed pattern ("X was killed", "X killed in")
  - Single-victim patterns ("a person killed", "one person dead")
  - Foreign conflict false-positive filter
  - Stronger Rwanda relevance check (district name alone not sufficient
    if article is clearly about a foreign country/conflict)
"""
import re
from datetime import datetime, date

# ── Rwanda geography ──────────────────────────────────────────────────────────
DISTRICTS = {
    # Kigali City
    "gasabo":      ("Kigali City",   -1.8976, 30.1127),
    "kicukiro":    ("Kigali City",   -1.9736, 30.0979),
    "nyarugenge":  ("Kigali City",   -1.9500, 30.0588),
    "kigali":      ("Kigali City",   -1.9441, 30.0619),
    # Northern Province
    "burera":      ("Northern",      -1.4667, 29.8333),
    "gakenke":     ("Northern",      -1.6833, 29.7833),
    "gicumbi":     ("Northern",      -1.5785, 30.0671),
    "musanze":     ("Northern",      -1.4996, 29.6344),
    "rulindo":     ("Northern",      -1.7167, 29.9833),
    "byumba":      ("Northern",      -1.5785, 30.0671),
    # Southern Province
    "gisagara":    ("Southern",      -2.6000, 29.8333),
    "huye":        ("Southern",      -2.5964, 29.7394),
    "butare":      ("Southern",      -2.5973, 29.7394),
    "kamonyi":     ("Southern",      -2.0000, 29.8833),
    "muhanga":     ("Southern",      -2.0756, 29.7514),
    "gitarama":    ("Southern",      -2.0756, 29.7514),
    "nyamagabe":   ("Southern",      -2.4667, 29.4833),
    "nyanza":      ("Southern",      -2.3500, 29.7500),
    "nyaruguru":   ("Southern",      -2.7333, 29.5667),
    "ruhango":     ("Southern",      -2.2162, 29.7784),
    # Eastern Province
    "bugesera":    ("Eastern",       -2.1550, 30.1500),
    "gatsibo":     ("Eastern",       -1.6667, 30.4167),
    "kayonza":     ("Eastern",       -2.0506, 30.6443),
    "kirehe":      ("Eastern",       -2.2667, 30.6833),
    "ngoma":       ("Eastern",       -2.1597, 30.5397),
    "kibungo":     ("Eastern",       -2.1597, 30.5397),
    "nyagatare":   ("Eastern",       -1.2892, 30.3278),
    "rwamagana":   ("Eastern",       -1.9497, 30.4353),
    # Western Province
    "karongi":     ("Western",       -2.0592, 29.3489),
    "kibuye":      ("Western",       -2.0592, 29.3489),
    "ngororero":   ("Western",       -1.8833, 29.5333),
    "nyabihu":     ("Western",       -1.6667, 29.5167),
    "nyamasheke":  ("Western",       -2.3167, 29.1333),
    "rubavu":      ("Western",       -1.6828, 29.3465),
    "gisenyi":     ("Western",       -1.7024, 29.2561),
    "rusizi":      ("Western",       -2.4797, 28.9072),
    "cyangugu":    ("Western",       -2.4797, 28.9072),
    "rutsiro":     ("Western",       -1.9667, 29.4333),
}

PROVINCES = {
    "kigali city":       (-1.9441, 30.0619),
    "northern province": (-1.5500, 29.9000),
    "southern province": (-2.3500, 29.7500),
    "eastern province":  (-1.9000, 30.5000),
    "western province":  (-2.0000, 29.3000),
    "northern":          (-1.5500, 29.9000),
    "southern":          (-2.3500, 29.7500),
    "eastern":           (-1.9000, 30.5000),
    "western":           (-2.0000, 29.3000),
}

RWANDA_CENTROID = (-1.9403, 29.8739)

# ── Written number lookup (for "two killed", "a dozen dead", etc.) ────────────
WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "a dozen": 12, "dozen": 12, "dozens": 24, "scores": 40,
    "hundreds": 150, "several": 3, "a few": 2, "multiple": 3,
}

# ── Foreign conflict / war exclusion terms ──────────────────────────────────
# Articles matching these are about foreign wars or cross-border military activity,
# not civilian mass casualty incidents inside Rwanda.
FOREIGN_CONFLICT_TERMS = [
    "congo", "drc", "democratic republic of the congo",
    "ukraine", "russia", "israel", "gaza", "west bank",
    "syria", "iraq", "afghanistan", "somalia", "sudan", "south sudan",
    "ethiopia", "tigray", "myanmar", "yemen", "mali", "burkina faso",
    "m23", "adf rebels", "fdlr", "warlord", "drone strike",
    "airstrike", "air strike", "missile strike", "nato", "pentagon",
]

# ── War/military/armed-group violence exclusion terms ────────────────────────
# These indicate armed conflict deaths which are OUT OF SCOPE for a civilian
# mass casualty surveillance system (road accidents, floods, disasters, etc.)
WAR_VIOLENCE_TERMS = [
    # Armed groups operating in/around Rwanda
    "fdlr", "m23", "adf", "red-tabara", "fne", "cnrd",
    "interahamwe", "imbonerakure",
    # Military/combat language
    "soldier killed", "soldiers killed", "troops killed",
    "military killed", "combat", "battle", "ambush", "gunfight",
    "crossfire", "shelling", "mortar", "rocket attack",
    "armed group", "rebel", "insurgent", "militia",
    "border clash", "border skirmish", "border shooting",
    "congolese soldier", "rwandan soldier killed in",
    "rdf soldier", "killed in combat", "killed in battle",
    "execution", "assassination", "targeted killing",
    "war crime", "genocide suspect",
    # Intelligence / political violence
    "spy", "espionage", "dissident", "opposition leader killed",
    "political assassination", "death squad",
]

# ── Off-topic / general news exclusion terms ─────────────────────────────────
# Articles that match MCI keywords by accident but are clearly not incidents.
OFF_TOPIC_TERMS = [
    # Technology / business stories
    "drone deliver", "drone delivery", "grocery deliver", "food deliver",
    "blood delivery drone", "medical drone", "delivery service",
    "drone poised", "drone now", "drones are now",
    # Policy / political / governance (no incident)
    "budget", "parliament", "minister appoint", "election result",
    "trade deal", "investment", "gdp", "economic growth",
    "peace deal", "ceasefire agreement", "summit",
    # Sports (unless direct accident)
    "football match", "soccer match", "rugby match", "basketball game",
    "won the match", "lost the match", "tournament winner",
    "gold medal", "silver medal",
    # Entertainment / culture
    "music festival", "concert", "film festival", "award ceremony",
    "best actress", "best actor",
    # Agriculture / environment (unless disaster)
    "crop yield", "harvest season", "fertilizer", "irrigation project",
    "reforestation", "tree planting", "coffee harvest", "tea harvest",
    "crop harvest", "record harvest", "bumper harvest",
]

# ── Incident type keywords ────────────────────────────────────────────────────
INCIDENT_PATTERNS = {
    "road_accident": [
        "road accident", "car accident", "bus accident", "vehicle accident",
        "traffic accident", "collision", "crashed", "overturned", "road crash",
        "bus crash", "truck crash", "motorcycle accident", "head-on", "pile-up",
        "fell into ravine", "fell off bridge", "road carnage", "auto crash",
        "tour du rwanda", "rally accident", "minibus accident",
    ],
    "flood": [
        "flood", "flooding", "flash flood", "inundation", "overflow", "river burst",
        "heavy rain", "torrential rain", "submerged", "swept away", "muddy water",
        "rising waters", "deluge", "mudflow",
    ],
    "landslide": [
        "landslide", "mudslide", "rockslide", "hillslide", "slope collapse",
        "earth movement", "soil erosion", "mountain collapse", "hill collapse",
        "mudflow", "earth slip",
    ],
    "explosion": [
        "explosion", "bomb", "blast", "explosive", "detonation", "grenade",
        "ammunition", "artillery", "shelling", "gas explosion", "cylinder explosion",
    ],
    "fire": [
        "fire", "blaze", "inferno", "burnt", "burned", "arson", "flames",
        "house fire", "market fire", "building fire", "school fire", "church fire",
    ],
    "stampede": [
        "stampede", "crush", "crowd crush", "trampled", "trampling", "overcrowding",
        "crowd surge",
    ],
    "outbreak": [
        "outbreak", "epidemic", "disease", "cholera", "ebola", "plague", "typhoid",
        "meningitis", "malaria outbreak", "food poisoning", "mass poisoning",
        "contamination", "virus", "contagion", "marburg", "mpox", "monkeypox",
    ],
    "drowning": [
        "drowned", "drowning", "capsized", "boat accident", "boat capsize",
        "lake accident", "swimming accident", "river accident", "canoe accident",
    ],
    "building_collapse": [
        "building collapse", "house collapse", "wall collapse", "roof collapse",
        "structure collapse", "collapsed building", "school collapse",
    ],
    "violence": [
        "attack", "shooting", "gunfire", "killed by", "machete", "mob violence",
        "lynched", "stoning", "mass killing", "massacre", "murdered",
    ],
}

# ── Severity weights ──────────────────────────────────────────────────────────
SEVERITY_WEIGHTS = [
    (["catastrophic", "mass grave", "dozens killed", "hundreds killed", "massacre"], 5),
    (["killed", "dead", "died", "fatalities", "death toll", "bodies found"],         4),
    (["explosion", "bombing", "attack", "terror", "landslide", "flood kills"],       4),
    (["mass casualty", "multiple casualties", "mass fatality"],                       4),
    (["crash", "collapsed", "swept away", "capsized"],                               3),
    (["injured", "wounded", "hospitalized", "admitted"],                             3),
    (["outbreak", "epidemic", "disease"],                                            3),
    (["emergency", "evacuation", "disaster", "destroyed"],                           2),
    (["accident", "incident", "fire", "missing"],                                    1),
]

# ── MCI filter keywords (EN + Kinyarwanda) ───────────────────────────────────
MCI_EN = [
    "killed", "dead", "died", "deaths", "fatalities", "casualties", "injured",
    "wounded", "missing", "bodies", "mass casualty", "disaster", "accident",
    "crash", "flood", "landslide", "explosion", "fire", "stampede", "outbreak",
    "epidemic", "collapsed", "drowned", "capsized", "attack", "emergency",
]
MCI_RW = [
    "impanuka", "inkongi", "ibyago", "ubukangurambaga", "indwara",
    "gupfa", "gukomeretsa", "guhunga", "ibibazo", "umuriro",
    "isuri", "inkubi", "imvura", "ifuni", "urupfu",
]
ALL_MCI_KEYWORDS = MCI_EN + MCI_RW


def is_rwanda_relevant(text: str) -> bool:
    """
    Returns True only if the article is genuinely about an incident IN Rwanda.
    Rejects:
      - Foreign conflict articles that only mention Rwanda peripherally
      - Articles matching only via a district name in a foreign context
    """
    t = text.lower()

    has_rwanda_word    = "rwanda" in t or "rwandan" in t
    has_district_match = any(d in t for d in DISTRICTS)

    if not has_rwanda_word and not has_district_match:
        return False

    if has_rwanda_word:
        foreign_hits = sum(1 for term in FOREIGN_CONFLICT_TERMS if term in t)
        if foreign_hits >= 2 and "in rwanda" not in t and "rwanda accident" not in t:
            return False
        return True

    # Only district name matched — reject if any foreign conflict term present
    if any(term in t for term in FOREIGN_CONFLICT_TERMS):
        return False

    return True


def is_civilian_mci(text: str) -> bool:
    """
    Returns True only if the article describes a CIVILIAN mass casualty incident.
    Rejects:
      - War/armed conflict deaths (soldiers, rebels, border clashes)
      - Military operations and combat fatalities
      - Off-topic general news (drone deliveries, politics, sports, etc.)

    This is the second filter gate after is_rwanda_relevant() and is_mci_relevant().
    """
    t = text.lower()

    # ── Reject war/military violence ────────────────────────────────────
    for term in WAR_VIOLENCE_TERMS:
        if term in t:
            return False

    # ── Reject off-topic articles ────────────────────────────────────────
    for term in OFF_TOPIC_TERMS:
        if term in t:
            return False

    # ── Reject cross-border military incidents ───────────────────────────
    # "killed on [the] Rwandan border" with military context
    if "border" in t and any(m in t for m in [
        "soldier", "troops", "military", "armed", "combat", "patrol",
        "security forces", "police operation", "shoot",
    ]):
        # Only reject if death context is military, not civilian
        civilian_signals = ["civilian", "passenger", "bus", "car", "flood",
                            "accident", "fire", "landslide", "pedestrian"]
        if not any(c in t for c in civilian_signals):
            return False

    return True


def is_mci_relevant(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in ALL_MCI_KEYWORDS)


def classify_incident_type(text: str) -> str:
    t = text.lower()
    scores = {}
    for itype, keywords in INCIDENT_PATTERNS.items():
        scores[itype] = sum(1 for kw in keywords if kw in t)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "other"


def calculate_severity(text: str) -> int:
    t = text.lower()
    score = 0
    for keywords, weight in SEVERITY_WEIGHTS:
        if any(kw in t for kw in keywords):
            score = max(score, weight)
    deaths = extract_deaths(text)
    if deaths >= 50:   score = max(score, 5)
    elif deaths >= 20: score = max(score, 4)
    elif deaths >= 5:  score = max(score, 3)
    elif deaths >= 1:  score = max(score, 2)
    return max(1, score)


def _word_num_search(text: str, death_words: list, block_words: list = None) -> int:
    """
    Search for written-out numbers before/after death-related words.
    block_words: pattern2 (killed → word) is skipped if the word is
    immediately followed by a block word (e.g. "six injured" should not
    count as 6 deaths when looking for deaths).
    """
    t = text.lower()
    best = 0
    death_pattern = "|".join(death_words)
    block_pattern = "|".join(block_words) if block_words else None

    for word, num in WORD_TO_NUM.items():
        # pattern1: "two killed", "three people dead"
        if re.search(rf"\b{re.escape(word)}\b\s+(?:people\s+)?(?:{death_pattern})", t):
            best = max(best, num)
        # pattern2: "killed ... six" — but NOT if followed by a block word
        m = re.search(rf"(?:{death_pattern})\W{{1,15}}\b({re.escape(word)})\b", t)
        if m:
            if block_pattern:
                rest = t[m.end():m.end()+25]
                if re.search(rf"\b(?:{block_pattern})\b", rest):
                    continue  # this number belongs to another category
            best = max(best, num)
    return best


def extract_deaths(text: str) -> int:
    """
    Extract the number of deaths from text.
    Handles:
      - Digit numbers: "12 killed", "killed 5 people"
      - Written numbers: "two killed", "a dozen dead"
      - Named individuals: "X was killed" → minimum 1
      - Single victim: "a person killed", "one dead"
      - Implicit: "fatal", "killed" without count → 1
    """
    t = text.lower()
    best = 0

    # ── Pass 1: digit-based patterns ──────────────────────────────────────
    digit_patterns = [
        r"(\d+)\s*(?:people\s+)?(?:killed|dead|died|perished|fatalities?)",
        r"death toll\s*(?:of|rises?\s*to|:)?\s*(\d+)",
        r"(\d+)\s*(?:bodies|corpses)\s*(?:found|recovered|discovered)",
        r"killed\s+(?:at least\s+)?(\d+)",
        r"at least\s+(\d+)\s+(?:people\s+)?(?:killed|dead|died)",
        r"(\d+)\s*deaths?\s+(?:reported|confirmed|recorded|toll)",
        r"claiming\s+(\d+)\s+lives?",
        r"(\d+)\s+lives?\s+(?:lost|claimed|taken)",
        r"(\d+)\s+(?:people\s+)?(?:lost their lives|perished|succumbed)",
        r"toll\s+(?:rises?\s+to\s+)?(\d+)",
        r"(\d+)\s+confirmed\s+dead",
        r"left\s+(\d+)\s+(?:people\s+)?dead",
        r"(\d+)\s+(?:were\s+)?killed\b",
        r"(?:kills?|claims?|left|leaves?)\s+(\d+)\s+(?:people\s+)?(?:dead|killed)?",  # "kills 18", "left 5 dead"
        r"(?:kills?|claims?)\s+(\d+)",   # "crash kills 18 near Bugesera"
    ]
    for p in digit_patterns:
        for m in re.finditer(p, t):
            try:
                best = max(best, int(m.group(1)))
            except:
                pass

    # ── Pass 2: written number patterns (block injury words to avoid confusion) ─
    death_words  = ["killed", "dead", "died", "perished", "fatalities", "deaths"]
    injury_words = ["injured", "wounded", "hurt", "hospitalized", "hospitalised"]
    best = max(best, _word_num_search(text, death_words, block_words=injury_words))

    # ── Pass 3: single/implicit victim signals (run on lowercase) ────────
    single_patterns = [
        r"\b(?:was|were|is|gets?|got|been)\s+killed\b",
        r"\bkilled\s+in\s+(?:the|a|an)\b",
        r"\bfatally\s+(?:injured|wounded|struck)\b",
        r"\b(?:a person|one person|a man|a woman|a child|a motorist|"
        r"a pedestrian|a driver|a passenger|a cyclist|a student|"
        r"a farmer|a worker|a soldier)\s+(?:was\s+)?(?:killed|died|dead)\b",
        r"\bdied\s+(?:on the spot|at the scene|instantly|from (?:his|her|their) injuries)\b",
        r"\bclaimed (?:a|one)\s+life\b",
        r"\bone\s+(?:person|man|woman|child)\s+(?:was\s+)?(?:killed|died|dead)\b",
        r"\b(?:killed|dead)\s+(?:on the spot|at the scene)\b",
        r"\b(?:cyclist|driver|passenger|pedestrian|motorist|student|worker|farmer|soldier|"
        r"officer|journalist|man|woman|child|person|victim|bystander|resident)\s+"
        r"(?:was\s+)?killed\b(?!\s+\d)",
    ]
    for p in single_patterns:
        if re.search(p, t) and best == 0:
            best = 1

    # Headline pattern on original (mixed-case) text:
    # "Willy Ngoma Killed", "John Doe Killed in crash"
    if best == 0 and re.search(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+Killed\b', text):
        best = 1

    return best


def extract_injured(text: str) -> int:
    """
    Extract the number of injured from text.
    Handles digit and written numbers.
    """
    t = text.lower()
    best = 0

    digit_patterns = [
        r"(\d+)\s*(?:people\s+)?(?:injured|wounded|hurt|hospitalized|hospitalised)",
        r"injur(?:ed|ies)\s+(?:at least\s+)?(\d+)",
        r"at least\s+(\d+)\s+(?:people\s+)?(?:injured|wounded|hurt)",
        r"(\d+)\s+(?:others?\s+)?(?:sustained injuries|were injured|were wounded|were hurt)",
        r"(\d+)\s+(?:people\s+)?(?:taken|rushed|admitted)\s+to\s+hospital",
        r"(\d+)\s+(?:survivors?|victims?)\s+(?:injured|wounded|treated)",
        r"leaving\s+(\d+)\s+(?:others?\s+)?(?:injured|wounded|hurt)",
    ]
    for p in digit_patterns:
        for m in re.finditer(p, t):
            try:
                best = max(best, int(m.group(1)))
            except:
                pass

    injury_words = ["injured", "wounded", "hurt", "hospitalized"]
    best = max(best, _word_num_search(text, injury_words))

    return best


def extract_missing(text: str) -> int:
    t = text.lower()
    best = 0
    patterns = [
        r"(\d+)\s*(?:people\s+)?(?:missing|unaccounted|disappeared)",
        r"(\d+)\s+still\s+missing",
        r"search\s+for\s+(\d+)\s+missing",
    ]
    for p in patterns:
        for m in re.finditer(p, t):
            try:
                best = max(best, int(m.group(1)))
            except:
                pass
    missing_words = ["missing", "unaccounted", "disappeared"]
    best = max(best, _word_num_search(text, missing_words))
    return best


def geo_tag(text: str) -> dict:
    t = text.lower()
    for district, (province, lat, lng) in DISTRICTS.items():
        if district in t:
            return {
                "location":  district.title(),
                "district":  district.title(),
                "province":  province,
                "latitude":  lat,
                "longitude": lng,
            }
    for province, (lat, lng) in PROVINCES.items():
        if province in t:
            return {
                "location":  province.title(),
                "district":  "",
                "province":  province.title(),
                "latitude":  lat,
                "longitude": lng,
            }
    return {
        "location":  "Rwanda",
        "district":  "Unknown",
        "province":  "Unknown",
        "latitude":  RWANDA_CENTROID[0],
        "longitude": RWANDA_CENTROID[1],
    }


# ── Date parsing ──────────────────────────────────────────────────────────────
MONTHS = {
    "january":"01","february":"02","march":"03","april":"04",
    "may":"05","june":"06","july":"07","august":"08",
    "september":"09","october":"10","november":"11","december":"12",
    "jan":"01","feb":"02","mar":"03","apr":"04","jun":"06",
    "jul":"07","aug":"08","sep":"09","oct":"10","nov":"11","dec":"12",
}

def parse_date(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        return m.group(1)
    m = re.search(r"(\d{1,2})\s+(january|february|march|april|may|june|july|august|"
                  r"september|october|november|december|jan|feb|mar|apr|jun|jul|aug|"
                  r"sep|oct|nov|dec)\s+(\d{4})", text.lower())
    if m:
        return f"{m.group(3)}-{MONTHS[m.group(2)]}-{int(m.group(1)):02d}"
    m = re.search(r"(january|february|march|april|may|june|july|august|september|"
                  r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|"
                  r"nov|dec)\s+(\d{1,2}),?\s+(\d{4})", text.lower())
    if m:
        return f"{m.group(3)}-{MONTHS[m.group(1)]}-{int(m.group(2)):02d}"
    m = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", text)
    if m:
        y, a, b = m.group(3), int(m.group(1)), int(m.group(2))
        if a <= 12:
            return f"{y}-{a:02d}-{b:02d}"
    return ""


def enrich(raw: dict) -> dict:
    """Take a raw scraped article dict and enrich it with NLP fields."""
    text = f"{raw.get('title','')} {raw.get('description','')} {raw.get('full_text','')}"
    geo  = geo_tag(text)
    return {
        **raw,
        **geo,
        "incident_type": classify_incident_type(text),
        "severity":      calculate_severity(text),
        "deaths":        extract_deaths(text),
        "injured":       extract_injured(text),
        "missing":       extract_missing(text),
        "event_date":    raw.get("event_date") or parse_date(raw.get("published_at","")) or "",
    }
