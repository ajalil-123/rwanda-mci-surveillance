"""
eval_ai.py — labelled test set for the AI scope gate (verify_rwanda_relevance).

    python jobs.py eval-ai

Run it after any prompt, model or provider change. Each case states whether the
article must be kept (in scope) and, for rejections, the expected category.
Calls the live AI provider (costs a few requests); writes nothing to the database.
"""
import logging
import time

from ai import model_name, provider, verify_rwanda_relevance

logger = logging.getLogger("eval_ai")

# (title, body, expected_in_scope, expected_rejection_category or None)
CASES = [
    # ── must KEEP: specific accidental/natural events inside Rwanda with casualties ──
    ("Five killed as landslide buries houses in Ngororero",
     "Five people died on Tuesday night when a landslide buried three houses in Kabaya Sector, "
     "Ngororero District, after heavy rains. Two others were injured.", True, None),
    ("Bus crash on Huye–Nyamagabe road kills four, injures twelve",
     "A Volcano Express bus overturned near Kitabi in Nyamagabe District, killing four passengers "
     "and injuring twelve, Rwanda National Police said.", True, None),
    ("Fire at Kigali market injures seven traders",
     "Seven traders were hospitalised after fire broke out at a market in Nyarugenge, Kigali.", True, None),
    ("Cholera outbreak kills three in Rubavu",
     "The Rwanda Biomedical Centre confirmed three cholera deaths and 40 cases in Rubavu District "
     "this week.", True, None),
    ("Six drown as boat capsizes on Lake Kivu",
     "Six passengers drowned when a wooden boat capsized on Lake Kivu near Karongi on Sunday.", True, None),
    ("Two dead in building collapse in Gasabo",
     "Two construction workers died when a building under construction collapsed in Kimironko, "
     "Gasabo District.", True, None),
    # ── must REJECT ──
    ("Bus plunges into river near Goma, 14 dead",
     "A passenger bus fell into a river near Goma in North Kivu, DR Congo, killing 14 people.",
     False, "not_in_rwanda"),
    ("Kenya girls' school dormitory fire kills 16",
     "Sixteen students died in a dormitory fire in Nyeri County, Kenya.", False, "not_in_rwanda"),
    ("Kwibuka 32: Rwanda remembers over one million killed in 1994",
     "Rwandans gathered at the Kigali Genocide Memorial to commemorate victims of the 1994 Genocide "
     "against the Tutsi.", False, "commemoration"),
    ("UK charges doctor over Rwanda's 1994 genocide",
     "British prosecutors charged a doctor living in the UK over his alleged role in the 1994 genocide.",
     False, "commemoration"),
    ("Road accidents killed 700 people in Rwanda last year, police say",
     "Rwanda National Police annual figures show 700 road deaths in 2025.", False, "aggregate_report"),
    ("Disasters kill 70 people in nine months — report",
     "Floods and landslides killed 70 people across Rwanda between January and September, MINEMA said.",
     False, "aggregate_report"),
    ("Pig trade quarantine after African swine fever deaths in Bugesera",
     "RAB imposed a quarantine after African swine fever killed hundreds of pigs. No human cases.",
     False, "animals_only"),
    ("President sends condolences to families of Musanze flood victims",
     "The President expressed condolences and pledged support to families affected by last week's floods.",
     False, "reaction_or_statement"),
    ("Stray rockets from DRC fighting kill five in Rubavu",
     "Five people were killed and 30 injured when rockets fired during fighting in eastern DRC landed "
     "in Rubavu town.", False, "intentional_violence"),
    ("Former minister dies in car crash",
     "Former minister Jean Uwimana died in a car crash in Kigali on Monday; the driver survived.",
     False, "individual_death"),
]


def run() -> bool:
    """Runs every case; returns True when all in/out decisions are correct."""
    print(f"AI eval — provider: {provider()} | model: {model_name()} | {len(CASES)} cases\n")
    decision_ok = category_ok = errors = 0
    rejections = sum(1 for c in CASES if not c[2])
    started = time.time()

    for title, body, want_in, want_cat in CASES:
        r = verify_rwanda_relevance({"title": title, "full_text": body, "source_name": "eval"})
        got_in, got_cat = r["is_rwanda"], r["rejection_category"]
        if got_in is None:
            errors += 1
            mark = "ERROR"
        elif got_in == want_in:
            decision_ok += 1
            cat_match = want_in or got_cat == want_cat
            category_ok += (not want_in) and cat_match
            mark = "PASS " if cat_match else "PASS~"  # ~ = right decision, different category
        else:
            mark = "FAIL "
        expect = "keep" if want_in else f"reject/{want_cat}"
        print(f"[{mark}] {title[:58]:<58} expected {expect:<32} got {got_in}/{got_cat} ({r['confidence']:.2f})")
        if mark.strip() in ("FAIL", "PASS~", "ERROR"):
            print(f"         reason: {r['reason'][:140]}")

    answered = len(CASES) - errors
    print(f"\nDecisions correct: {decision_ok}/{answered} answered"
          f" | rejection category correct: {category_ok}/{rejections}"
          f" | provider errors: {errors} | {time.time() - started:.0f}s")
    return decision_ok == answered and errors == 0
