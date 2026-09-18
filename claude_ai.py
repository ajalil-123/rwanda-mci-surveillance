"""
claude_ai.py — Claude API integration for Rwanda MCI Surveillance System

Provides three main capabilities:
  1. summarize_incident()   — Generate/refresh AI summary for one incident
  2. data_quality_report()  — Batch quality analysis across many incidents
  3. mci_narrative()        — Public-health narrative for a period's MCI events

Set ANTHROPIC_API_KEY in your environment (or .env / Render env vars).
Optionally set CLAUDE_MODEL to override the default model.
"""

import os
import json
import logging
from datetime import datetime

logger = logging.getLogger("claude_ai")

# Default model — override via CLAUDE_MODEL env var
_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-5")

MCI_THRESHOLD = 3  # deaths >= 3 qualifies as an MCI


def _client():
    """Return an Anthropic client, raising a clear error if not configured."""
    try:
        import anthropic
    except ImportError:
        raise ImportError(
            "anthropic package not installed. Run: pip install anthropic"
        )
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY environment variable is not set."
        )
    return anthropic.Anthropic(api_key=api_key)


def _parse_json(text: str) -> dict:
    """Strip markdown fences and parse JSON from Claude's response."""
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        # Take the first fenced block
        for part in parts[1::2]:
            cleaned = part.lstrip("json").strip()
            if cleaned:
                text = cleaned
                break
    return json.loads(text)


# ── 0. RWANDA RELEVANCE VERIFIER ─────────────────────────────────────────────

def verify_rwanda_relevance(incident: dict) -> dict:
    """
    Use Claude to confirm an incident is genuinely Rwanda-related AND classify its type.

    Returns:
        {
            "is_rwanda":     bool,
            "confidence":    float (0.0–1.0),
            "reason":        str,
            "incident_type": str  — one of the MCI_TYPES or "other" as last resort
        }
    Falls back to True (keep) on API errors so the scraper stays resilient.
    """
    title    = (incident.get("title")       or "")[:200]
    desc     = (incident.get("description") or incident.get("full_text") or "")[:500]
    source   = (incident.get("source_name") or "")
    url      = (incident.get("source_url")  or "")
    district = (incident.get("district")    or "")
    province = (incident.get("province")    or "")

    prompt = f"""You are a data filter for Rwanda's MCI (Mass Casualty Incident) surveillance system.
You must answer TWO questions in one response.

Incident:
- Title: {title}
- Source: {source} ({url})
- Location fields: district="{district}", province="{province}"
- Description: {desc if desc else "N/A"}

QUESTION 1 — Did this incident HAPPEN inside Rwanda?
KEEP (is_rwanda=true) if:
  - The event itself clearly occurred in Rwanda (Kigali, Rwanda provinces, Rwandan districts, etc.)
  - Location is ambiguous but source is a Rwandan outlet and Rwanda is the event location
REJECT (is_rwanda=false) if:
  - The incident occurred in another country, even if reported by an African outlet
  - It is merely a government/official reaction: condolences, ministerial visits, press statements ABOUT an event
  - It is an aggregate report: "X deaths over Y months", annual statistics, roundups
  - It merely mentions Rwanda without Rwanda being the event location (e.g. "Rwanda envoy killed in DRC")
  - It is a press release or charity appeal prompted by an event, not a report of the event itself
  - It is about a specific named individual's death (e.g. "Senator X's husband killed", "Minister Y dies in crash") — person-focused stories are NOT mass casualty events; MCI surveillance tracks incidents affecting multiple people or posing public-safety risk, not individual fatalities regardless of the victim's status
  - It reports casualties among animals, livestock, or wildlife only (e.g. swine fever killing pigs, bird flu in poultry, cattle disease deaths) — this system tracks HUMAN casualties only; animal deaths or quarantines with no human fatalities/injuries are excluded
  - It is a genocide commemoration, remembrance, anniversary, or memorial article (e.g. "Genocide at 32", "World Remembers 1 Million Killed", "Kwibuka", "100 Days of Killings remembered") — these reference historical violence, not a current surveillance incident; reject as is_rwanda=false
  - It is about intentional violence, political killings, criminal attacks, armed conflict, or mob violence — this system covers accidental and natural-disaster MCIs only (road accidents, floods, fires, landslides, disease outbreaks); deliberate violence is out of scope; classify as is_rwanda=false

QUESTION 2 — What is the MCI incident type?
Choose EXACTLY ONE from this list (lowercase, underscore format):
  road_accident, flood, landslide, explosion, fire, stampede, outbreak, drowning, building_collapse
Only use "other" if the event genuinely does not fit any category above.
Note: "violence" has been removed from the list — intentional violence is out of scope for this system.
Base the classification on what actually happened, not the article framing.

Respond ONLY with valid JSON — no prose outside the JSON:
{{"is_rwanda": true, "confidence": 0.0, "reason": "one short sentence", "incident_type": "road_accident"}}"""

    try:
        response = _client().messages.create(
            model=_MODEL,
            max_tokens=180,
            messages=[{"role": "user", "content": prompt}],
        )
        result = _parse_json(response.content[0].text)

        # Validate incident_type against allowed values
        _VALID_TYPES = {
            "road_accident", "flood", "landslide", "explosion", "fire",
            "stampede", "outbreak", "drowning", "building_collapse", "violence", "other",
        }
        raw_type = str(result.get("incident_type", "other")).strip().lower()
        incident_type = raw_type if raw_type in _VALID_TYPES else "other"

        return {
            "is_rwanda":     bool(result.get("is_rwanda", True)),
            "confidence":    float(result.get("confidence", 0.5)),
            "reason":        str(result.get("reason", "")),
            "incident_type": incident_type,
        }
    except Exception as exc:
        # Fail open — don't drop incidents if Claude is unavailable
        logger.warning("verify_rwanda_relevance failed (keeping incident): %s", exc)
        return {
            "is_rwanda":     True,
            "confidence":    0.0,
            "reason":        f"verification error: {exc}",
            "incident_type": incident.get("incident_type") or "other",
        }


# ── 1. INCIDENT SUMMARIZER ────────────────────────────────────────────────────

def summarize_incident(incident: dict) -> dict:
    """
    Generate a quality-checked AI summary for a single incident.

    Args:
        incident: dict from the `incidents` DB table

    Returns:
        {
            "summary":    str,    # 2–3 sentence factual summary
            "confidence": float,  # 0.0–1.0 data quality confidence
            "flags":      list,   # data quality issues found
        }
    """
    title        = incident.get("title", "")
    desc         = (incident.get("description") or incident.get("full_text") or "")[:800]
    deaths       = incident.get("deaths", 0) or 0
    injured      = incident.get("injured", 0) or 0
    missing      = incident.get("missing", 0) or 0
    district     = incident.get("district", "") or "Unknown"
    province     = incident.get("province", "") or ""
    inc_type     = incident.get("incident_type", "") or "other"
    event_date   = (incident.get("event_date") or incident.get("detected_at", ""))[:10]
    is_mci       = deaths >= MCI_THRESHOLD

    prompt = f"""You are an analyst for Rwanda's Mass Casualty Incident (MCI) surveillance system.

Incident record:
- Title: {title}
- Date: {event_date}
- Type: {inc_type}
- Location: {district}{f', {province}' if province else ''}
- Deaths: {deaths} | Injured: {injured} | Missing: {missing}
- Classified as MCI: {'YES (deaths ≥ 3)' if is_mci else 'No'}
- Description: {desc if desc else 'N/A'}

Your tasks:
1. Write a concise 2–3 sentence factual summary suitable for a public-health dashboard.
   - Lead with the date, location, and incident type.
   - State casualties precisely.
   - Mention MCI classification if applicable.
2. Rate data confidence (0.0–1.0):
   - Deduct for: missing district (−0.15), missing date (−0.2), zero casualties with no context (−0.1),
     inconsistent figures (−0.15), "other" type with no detail (−0.1).
3. List any data quality flags as short strings.

Respond ONLY with valid JSON — no prose outside the JSON:
{{
  "summary": "...",
  "confidence": 0.0,
  "flags": []
}}"""

    try:
        response = _client().messages.create(
            model=_MODEL,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        result = _parse_json(response.content[0].text)
        return {
            "summary":    str(result.get("summary", "")),
            "confidence": float(result.get("confidence", 0.5)),
            "flags":      list(result.get("flags", [])),
        }
    except Exception as exc:
        logger.error("summarize_incident failed: %s", exc)
        return {"summary": "", "confidence": 0.0, "flags": [], "error": str(exc)}


# ── 2. DATA QUALITY REPORT ────────────────────────────────────────────────────

def data_quality_report(incidents: list) -> dict:
    """
    Batch data-quality analysis across a list of incident dicts.

    Args:
        incidents: list of dicts from the `incidents` table (any size;
                   internally capped at 50 for the Claude prompt)

    Returns:
        {
            "quality_score":     int (0–100),
            "issues":            list of {issue, severity, count, pct},
            "recommendations":   list of str,
            "executive_summary": str,
            "total_analyzed":    int,
            "generated_at":      str (ISO),
        }
    """
    if not incidents:
        return {
            "quality_score": 0,
            "issues": [],
            "recommendations": ["No incidents provided for analysis."],
            "executive_summary": "Dataset is empty.",
            "total_analyzed": 0,
            "generated_at": datetime.utcnow().isoformat(),
        }

    total     = len(incidents)
    no_dist   = sum(1 for i in incidents if not i.get("district"))
    no_date   = sum(1 for i in incidents if not i.get("event_date"))
    unclassed = sum(1 for i in incidents if not i.get("incident_type") or i.get("incident_type") == "other")
    zero_cas  = sum(1 for i in incidents if (i.get("deaths") or 0) == 0 and (i.get("injured") or 0) == 0)
    no_summ   = sum(1 for i in incidents if not i.get("ai_summary"))
    mci_count = sum(1 for i in incidents if (i.get("deaths") or 0) >= MCI_THRESHOLD)

    # Build compact sample for the prompt
    sample = [
        {
            "id":       inc.get("id"),
            "title":    (inc.get("title") or "")[:80],
            "date":     (inc.get("event_date") or inc.get("detected_at", ""))[:10],
            "type":     inc.get("incident_type"),
            "district": inc.get("district"),
            "deaths":   inc.get("deaths", 0),
            "injured":  inc.get("injured", 0),
            "source":   inc.get("source_name"),
        }
        for inc in incidents[:50]
    ]

    prompt = f"""You are a data quality analyst for Rwanda's MCI (Mass Casualty Incident) surveillance system.

Dataset overview ({total} total incidents):
- Missing district: {no_dist} ({100*no_dist//max(total,1)}%)
- Missing event date: {no_date} ({100*no_date//max(total,1)}%)
- Unclassified type ("other" or blank): {unclassed} ({100*unclassed//max(total,1)}%)
- Zero-casualty records: {zero_cas} ({100*zero_cas//max(total,1)}%)
- Without AI summary: {no_summ} ({100*no_summ//max(total,1)}%)
- Confirmed MCIs (deaths ≥ 3): {mci_count} ({100*mci_count//max(total,1)}%)

Sample records (up to 50):
{json.dumps(sample, indent=2)[:4000]}

Analyse data quality and respond ONLY with valid JSON:
{{
  "quality_score": 0,
  "issues": [
    {{"issue": "...", "severity": "high|medium|low", "count": 0, "pct": 0}}
  ],
  "recommendations": ["..."],
  "executive_summary": "..."
}}

quality_score is 0–100 (100 = perfect). List 3–6 issues and 3 recommendations."""

    try:
        response = _client().messages.create(
            model=_MODEL,
            max_tokens=900,
            messages=[{"role": "user", "content": prompt}],
        )
        result = _parse_json(response.content[0].text)
        result["total_analyzed"] = total
        result["mci_count"]      = mci_count
        result["generated_at"]   = datetime.utcnow().isoformat()
        return result
    except Exception as exc:
        logger.error("data_quality_report failed: %s", exc)
        return {
            "error": str(exc),
            "total_analyzed": total,
            "generated_at": datetime.utcnow().isoformat(),
        }


# ── 3. MCI NARRATIVE ──────────────────────────────────────────────────────────

def mci_narrative(incidents: list, period_label: str = "recent period") -> dict:
    """
    Generate a public-health surveillance narrative for a set of MCI incidents.

    Args:
        incidents:    list of incident dicts — should already be filtered to MCIs
        period_label: human-readable period label, e.g. "Last 30 days"

    Returns:
        {
            "narrative":  str,
            "key_stats":  dict,
            "generated_at": str,
        }
    """
    if not incidents:
        return {
            "narrative":    "No MCI events recorded for this period.",
            "key_stats":    {},
            "generated_at": datetime.utcnow().isoformat(),
        }

    total_deaths  = sum((i.get("deaths")  or 0) for i in incidents)
    total_injured = sum((i.get("injured") or 0) for i in incidents)

    by_type     = {}
    by_district = {}
    for i in incidents:
        t = i.get("incident_type", "other")
        d = i.get("district") or "Unknown"
        by_type[t]     = by_type.get(t, 0) + 1
        by_district[d] = by_district.get(d, 0) + 1

    top_type     = max(by_type,     key=by_type.get)     if by_type     else "unknown"
    top_district = max(by_district, key=by_district.get) if by_district else "unknown"

    # Most severe incidents for the narrative
    top_incidents = sorted(incidents, key=lambda x: x.get("deaths", 0), reverse=True)[:15]
    inc_lines = "\n".join(
        f"- {i.get('event_date','?')}: {(i.get('title','?'))[:70]} "
        f"| {i.get('district','?')} | {i.get('deaths',0)} deaths, {i.get('injured',0)} injured"
        for i in top_incidents
    )

    prompt = f"""You are a public-health analyst writing a surveillance bulletin for Rwanda's Ministry of Health.

Reporting period: {period_label}
Confirmed MCIs (deaths ≥ 3): {len(incidents)}
Total deaths: {total_deaths} | Total injured: {total_injured}
Dominant incident type: {top_type} ({by_type.get(top_type, 0)} events)
Most affected district: {top_district} ({by_district.get(top_district, 0)} events)
Type breakdown: {json.dumps(by_type)}
District breakdown: {json.dumps(dict(sorted(by_district.items(), key=lambda x: -x[1])[:10]))}

Notable incidents (highest death tolls):
{inc_lines}

Write a professional 3–4 paragraph surveillance narrative covering:
1. Overall MCI burden for the period — scale, comparison to expectations
2. Dominant incident types and their geographic distribution
3. Notable individual events with specific details
4. Public-health implications or surveillance recommendations

Use formal, factual language appropriate for a government health bulletin. Do not use bullet points."""

    try:
        response = _client().messages.create(
            model=_MODEL,
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}],
        )
        narrative = response.content[0].text.strip()
        return {
            "narrative":  narrative,
            "key_stats": {
                "total_mci_events":        len(incidents),
                "total_deaths":            total_deaths,
                "total_injured":           total_injured,
                "dominant_type":           top_type,
                "most_affected_district":  top_district,
                "type_breakdown":          by_type,
            },
            "generated_at": datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        logger.error("mci_narrative failed: %s", exc)
        return {
            "error":        str(exc),
            "narrative":    "",
            "generated_at": datetime.utcnow().isoformat(),
        }
