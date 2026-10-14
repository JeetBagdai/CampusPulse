"""Crowdsourced photo reports: students photograph a problem, CV + a vision LLM
verify it, duplicates merge into the existing issue, and it enters the normal
work-order loop."""
import asyncio
import base64
import io
import itertools
import time
import uuid

import cv2
import numpy as np
from PIL import Image, ImageOps

from .. import config as cfg
from ..cv import detectors
from ..genai import llm

_tkt = itertools.count(1)
TICKETS: dict[str, dict] = {}
_recent: dict[str, list[float]] = {}
CATEGORY_TO_TYPE = {"leak": "WATER_LEAK", "overflow": "BIN_OVERFLOW", "litter": "LITTER", "lights_on": "ENERGY_WASTE"}
RATE_LIMIT = (5, 600)  # max reports per reporter per 10 minutes


def _clean(image: bytes) -> bytes:
    """EXIF-transpose, strip metadata, downscale to 1024px, blur faces. Returns JPEG bytes."""
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(image))).convert("RGB")
    im.thumbnail((1024, 1024))
    arr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
    arr = detectors.blur_faces(arr, detectors.detect_people(arr))
    ok, buf = cv2.imencode(".jpg", arr, [cv2.IMWRITE_JPEG_QUALITY, 82])
    return buf.tobytes()


def save_photo(image: bytes, prefix: str = "photo") -> str:
    name = f"{prefix}-{uuid.uuid4().hex[:8]}.jpg"
    (cfg.UPLOADS_DIR / name).write_bytes(_clean(image))
    return f"/api/uploads/{name}"


async def classify(jpeg: bytes) -> dict:
    prompt = ("You verify problem reports from a college campus. Look at the photo and return JSON: "
              '{"category": one of ["leak","overflow","litter","lights_on","other","invalid"], '
              '"severity": 1-3, "description": one short sentence of what is visible, "confidence": 0-1}. '
              "leak = running/leaking tap, pipe or water on floor; overflow = overflowing/full dustbin; "
              "litter = garbage lying around; lights_on = lights/fans on in an empty room; "
              "invalid = selfie, meme, blank or unrelated photo.")
    url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
    out = await llm.chat_json([{"role": "user", "content": [{"type": "text", "text": prompt},
                                                            {"type": "image_url", "image_url": {"url": url}}]}],
                              vision=True, max_tokens=1200)
    out["category"] = str(out.get("category", "other")).lower().replace(" ", "_")
    out["confidence"] = float(out.get("confidence", 0))
    return out


def _resolve_target(engine, category: str, loc: str) -> str:
    rooms, bins = engine.room_cfg, engine.bin_cfg
    c = rooms.get(loc) or bins.get(loc) or {}
    if category == "leak" and not (loc in rooms and rooms[loc]["type"] == "washroom"):
        same = [r for r in rooms.values() if r["type"] == "washroom" and r["building"] == c.get("building")]
        same.sort(key=lambda r: abs(r["floor"] - c.get("floor", 1)))
        return same[0]["id"] if same else loc
    if category == "overflow" and loc not in bins:
        same = [b for b in bins.values() if b["building"] == c.get("building")]
        return same[0]["id"] if same else loc
    return loc


async def submit_report(engine, image: bytes, loc: str | None, note: str | None, reporter: str = "student") -> dict:
    now = time.time()
    hist = [t for t in _recent.get(reporter, []) if now - t < RATE_LIMIT[1]]
    if len(hist) >= RATE_LIMIT[0]:
        return {"accepted": False, "reason": "rate_limited",
                "message": "Too many reports in a short time. Please try again in a few minutes."}
    _recent[reporter] = hist + [now]
    if not loc or not (loc in engine.room_cfg or loc in engine.bin_cfg):
        return {"accepted": False, "reason": "no_location",
                "message": "Please include the location code, e.g. send the photo with caption: REPORT E-1WR"}

    ticket = f"TKT-{next(_tkt)}"
    photo = save_photo(image, prefix=ticket)
    jpeg = (cfg.UPLOADS_DIR / photo.rsplit("/", 1)[1]).read_bytes()

    bin_state = None
    if detectors.bin_model() is not None:
        arr = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        bin_state, _ = await asyncio.to_thread(detectors.detect_bin, arr)

    verdict = {"category": "other", "confidence": 0.0, "description": (note or "")[:120], "severity": 2}
    if llm.available():
        try:
            verdict = await classify(jpeg)
        except Exception as e:  # noqa: BLE001
            verdict["error"] = str(e)[:160]
    if bin_state == "overflow" and verdict["category"] in ("other", "litter"):
        verdict.update(category="overflow", confidence=max(verdict["confidence"], 0.7))

    rec = {"ticket": ticket, "loc": loc, "note": note, "photo": photo, "verdict": verdict, "reporter": reporter,
           "created_at": engine.src.now().isoformat(), "issue_id": None, "bin_model": bin_state}
    TICKETS[ticket] = rec
    cat = verdict["category"]
    if cat not in CATEGORY_TO_TYPE or verdict["confidence"] < 0.6:
        rec.update(accepted=False, reason="not_verified")
        return {**rec, "message": f"Thanks. We couldn't confirm a problem in this photo ({ticket}), so it was not "
                                  "raised. Try a clearer photo of the leak, bin or litter."}

    itype = CATEGORY_TO_TYPE[cat]
    target = _resolve_target(engine, cat, loc)
    key = (itype, target)
    existing = engine.issues.get(engine.open_by_key.get(key, ""))
    if existing:
        existing["reports_count"] += 1
        existing["photo"] = existing.get("photo") or photo
        if "citizen" not in existing["detected_by"]:
            existing["detected_by"].append("citizen")
        new_p = engine._priority(itype, existing["rate_inr_hr"], existing["evidence"], existing["reports_count"])
        if new_p < existing["priority"]:
            existing["priority"], existing["priority_icon"] = new_p, ""
        engine.log("report", f"{ticket} merged into {existing['id']} ({existing['reports_count']} reports)")
        issue = existing
    else:
        rate = 0.0
        if itype == "WATER_LEAK":
            rate = 6 * 60 / 1000 * cfg.WATER_INR_PER_KL
        elif itype == "ENERGY_WASTE" and target in engine.room_cfg:
            watts = sum(f["count"] * cfg.FIXTURE_WATTS[f["type"]] for f in engine.room_cfg[target]["fixtures"])
            rate = watts / 1000 * cfg.TARIFF_INR_PER_KWH
        ev = {"detected_by": ["citizen"], "description": verdict.get("description", ""), "ticket": ticket}
        if itype == "BIN_OVERFLOW":
            ev["fill"] = 100
        if itype == "WATER_LEAK":
            ev["excess_lpm"] = 6
        issue = engine.create_issue(itype, target, rate, ev, demo=True, photo=photo, sensor_managed=False,
                                    reporter=reporter)
        engine.log("report", f"{ticket} raised {issue['id']} from a photo report")
    rec.update(accepted=True, issue_id=issue["id"], target=target)
    track = f"{cfg.FRONTEND_URL}/report?ticket={ticket}"
    return {**rec, "message": f"Thanks. {ticket} accepted: {verdict.get('description', '')}\n"
                              f"Assigned as {issue['id']} ({issue['priority']}). Track: {track}"}


def status(engine, ticket: str) -> dict | None:
    rec = TICKETS.get(ticket)
    if not rec:
        return None
    issue = engine.issues.get(rec.get("issue_id") or "")
    return {**rec, "issue": engine.public_issue(issue) if issue else None}
