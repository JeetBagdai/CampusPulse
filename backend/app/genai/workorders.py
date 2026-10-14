"""Work orders: deterministic template first (instant, always works), then
optionally enriched by the LLM and translated, both checked by the validator."""
import json
from pathlib import Path

from . import llm
from .validator import check_ids, check_numbers, facts_numbers

I18N = json.loads((Path(__file__).resolve().parent.parent / "i18n.json").read_text(encoding="utf-8"))
LANG_NAME = {"hi": "Hindi", "kn": "Kannada", "en": "English"}
ROLE_FOR = {"ENERGY_WASTE": "electrician", "WATER_LEAK": "plumber", "BIN_OVERFLOW": "housekeeping",
            "LITTER": "housekeeping", "UNDERUSED_BOOKING": "estate_manager"}


def t(key: str, lang: str, **kw) -> str:
    entry = I18N[key]
    return entry.get(lang, entry["en"]).format(**kw)


def type_label(itype: str, lang: str = "en") -> str:
    return I18N["type"].get(itype, {}).get(lang, itype)


def template(issue: dict) -> dict:
    tgt, ev = issue["target_name"], issue.get("evidence", {})
    it = issue["type"]
    if it == "ENERGY_WASTE":
        on = ", ".join(ev.get("fixtures_on", [])) or "fixtures"
        return {"title": f"Switch off {on} in {tgt}",
                "summary": f"{tgt} has been empty for {ev.get('empty_min', 0)} min with {on} running.",
                "steps": [f"Go to {tgt} ({issue['location']}).", f"Switch off {on}.",
                          "Check that no class is about to start; close windows and doors."],
                "safety_note": "Do not touch the main panel with wet hands."}
    if it == "WATER_LEAK":
        return {"title": f"Fix water leak at {tgt}",
                "summary": f"Continuous flow of {ev.get('excess_lpm', 0)} L/min detected at {tgt} with no matching usage.",
                "steps": [f"Go to {tgt} ({issue['location']}).", "Check taps, flush valves and pipe joints for running water.",
                          "Close the isolation valve if the leak cannot be fixed immediately."],
                "safety_note": "Mark the wet floor to prevent slips."}
    if it == "BIN_OVERFLOW":
        return {"title": f"Empty bin {issue['target']} ({tgt})",
                "summary": f"Bin at {tgt} is {ev.get('fill', 0)}% full.",
                "steps": [f"Go to {tgt}.", "Empty the bin and replace the liner.", "Clean any spill around the bin."],
                "safety_note": "Wear gloves."}
    if it == "LITTER":
        return {"title": f"Clean litter at {tgt}", "summary": f"A student reported litter at {tgt}.",
                "steps": [f"Go to {tgt}.", "Collect and segregate the litter (wet / dry).", "Reply with a photo once clean."],
                "safety_note": "Wear gloves."}
    if it == "UNDERUSED_BOOKING":
        return {"title": f"Review booking of {tgt}",
                "summary": f"{tgt} is booked for {ev.get('course', 'a class')} but only {ev.get('occ', 0)} people are present.",
                "steps": ["Confirm with the department whether the class was cancelled.",
                          "Release the slot or move the class to a smaller room.", "Switch off unused fixtures."],
                "safety_note": ""}
    return {"title": issue["title"], "summary": issue["title"], "steps": [], "safety_note": ""}


def _facts(issue: dict, wo: dict) -> dict:
    return {"work_order": wo["id"], "issue_type": issue["type"], "target_id": issue["target"],
            "target_name": issue["target_name"], "location": issue["location"], "priority": issue["priority"],
            "assignee_role": wo["role"], "loss_inr_per_hour": issue["rate_inr_hr"], "evidence": issue.get("evidence", {})}


async def enrich(issue: dict, wo: dict) -> bool:
    """Ask the LLM for a better-written English work order. Keeps the template on any failure."""
    facts = _facts(issue, wo)
    sys = ("You write short, practical maintenance work orders for staff at an Indian college campus. "
           "Return JSON with keys: title (max 8 words), summary (1 sentence), steps (2-4 short imperative steps), "
           "safety_note (short, may be empty). Use ONLY the facts provided. Do not invent numbers, costs or times; "
           "you may only repeat numbers that appear in the facts. Mention the location so staff can find it.")
    try:
        out = await llm.chat_json([{"role": "system", "content": sys},
                                   {"role": "user", "content": json.dumps(facts)}])
        content = {"title": str(out["title"]), "summary": str(out["summary"]),
                   "steps": [str(s) for s in out["steps"]][:4], "safety_note": str(out.get("safety_note", ""))}
    except Exception as e:  # noqa: BLE001
        wo["llm_error"] = str(e)[:200]
        return False
    bad = check_numbers(json.dumps(content, ensure_ascii=False), facts_numbers(facts))
    if bad:
        wo["validator"] = {"rejected_numbers": bad}
        return False
    wo["content"]["en"] = content
    wo["source"] = "llm"
    wo["validator"] = {"ok": True}
    return True


async def translate(wo: dict, lang: str) -> dict:
    """Translate the English content; IDs and numbers must survive or we fall back to English."""
    if lang == "en" or lang in wo["content"]:
        return wo["content"].get(lang, wo["content"]["en"])
    en = wo["content"]["en"]
    sys = (f"Translate the JSON values to simple, polite {LANG_NAME[lang]} for maintenance staff. "
           "Keep the same JSON keys. Keep IDs such as WO-12, E-201, E-1WR, B1-1WR, BIN-05 exactly as written. "
           "Keep every number in Western digits (0-9) exactly as written. Return only JSON.")
    try:
        out = await llm.chat_json([{"role": "system", "content": sys},
                                   {"role": "user", "content": json.dumps(en, ensure_ascii=False)}])
        tr = {"title": str(out["title"]), "summary": str(out["summary"]),
              "steps": [str(s) for s in out["steps"]], "safety_note": str(out.get("safety_note", ""))}
    except Exception:  # noqa: BLE001
        return en
    src, dst = json.dumps(en, ensure_ascii=False), json.dumps(tr, ensure_ascii=False)
    if check_ids(src, dst) or check_numbers(dst, facts_numbers(en)):
        return en
    wo["content"][lang] = tr
    return tr


def message(wo: dict, issue: dict, lang: str) -> str:
    if lang not in wo["content"]:  # no validated translation: send fully in English, not mixed
        lang = "en"
    c = wo["content"][lang]
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(c["steps"], 1))
    lines = [f"{issue['priority']} · {type_label(issue['type'], lang)} · {issue['target']}",
             c["title"], c["summary"], "", f"{t('steps', lang)}:", steps]
    if c.get("safety_note"):
        lines += ["", c["safety_note"]]
    if issue["rate_inr_hr"] > 0:
        lines += ["", t("loss", lang, rate=issue["rate_inr_hr"])]
    lines += ["", t("reply_hint", lang, wo=wo["id"])]
    return "\n".join(lines)
