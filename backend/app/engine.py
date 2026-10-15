"""Twin engine: fuses sensor readings, CV observations, timetables and citizen
reports into issues; prices them in INR/kWh/litres/CO2; dispatches work orders;
verifies fixes against the next reading; escalates when nobody responds."""
import asyncio
import itertools
import re
import time
from collections import deque
from datetime import datetime, timedelta

from . import config as cfg
from .datasource.mock import MockSource, load_campus
from .genai import llm
from .genai import workorders as wol
from .notify.base import Feed, mask
from .notify.factory import make_notifier

PRIORITY_ICON = {"P1": "", "P2": "", "P3": ""}  # dashboard draws coloured dots
AVOIDED_HOURS = {"ENERGY_WASTE": 4, "WATER_LEAK": 12, "UNDERUSED_BOOKING": 1, "BIN_OVERFLOW": 0, "LITTER": 0}
THRESHOLD_MIN = {"ENERGY_WASTE": 15, "ENERGY_FAST": 3, "UNDERUSED_BOOKING": 15, "WATER_LEAK": 30, "BIN_OVERFLOW": 1, "CV_TAP": 3, "CV_BIN": 1}
ESCALATE_MIN = {"P1": 15, "P2": 60}
TERMINAL = {"verified", "auto_closed", "closed"}
FIXTURE_LABEL = {"tube_light": "lights", "led_light": "lights", "fan": "fans", "ac": "AC", "projector": "projector",
                 "pc": "PCs", "exhaust": "exhaust fan"}
STATUS_FOR = {"ENERGY_WASTE": "energy", "WATER_LEAK": "water", "UNDERUSED_BOOKING": "underused", "LITTER": "litter",
              "BIN_OVERFLOW": "waste"}
DONE_WORDS = ("done", "fixed", "completed", "हो गया", "ठीक हो", "ಆಯಿತು", "ಮುಗಿದಿದೆ", "ಸರಿಪಡಿಸಲಾಗಿದೆ")
ACK_WORDS = ("ack", "noted", "ok", "on it", "accepted", "ठीक है", "ಸರಿ", "ಒಪ್ಪಿದೆ")


def _money(x: float) -> float:
    return round(x, 1) if x < 100 else round(x)


class Engine:
    def __init__(self):
        self.campus = load_campus()
        self.room_cfg = {r["id"]: r for r in self.campus["rooms"]}
        self.bin_cfg = {b["id"]: b for b in self.campus["bins"]}
        self.bld_cfg = {b["id"]: b for b in self.campus["buildings"]}
        self.staff = {s["role"]: s for s in self.campus["staff"]}
        self.notifier = make_notifier()
        self.feed = Feed()
        self.wa_mode = "demo"  # demo: only demo-flagged issues hit real WhatsApp | all | off
        self.reset()

    # ------------------------------------------------------------------ setup
    def reset(self):
        start = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
        self.src = MockSource(self.campus, start - timedelta(days=30))
        self.src.fast_forward(start)
        self.issues: dict[str, dict] = {}
        self.wos: dict[str, dict] = {}
        self.open_by_key: dict[tuple, str] = {}
        self.timers: dict[tuple, int] = {}
        self.fill_hist = {b: deque(maxlen=90) for b in self.bin_cfg}
        self.saved = {"inr": 0.0, "kwh": 0.0, "l": 0.0, "co2": 0.0}
        self.events: deque = deque(maxlen=60)
        self.recently_fixed: dict[str, datetime] = {}
        self.demo_targets: set[str] = set()
        self.cv_bindings = {"cam-live": self.campus.get("live_room", next(iter(self.room_cfg)))}
        self.cv_last: dict[str, dict] = {}
        self.speed, self.paused = 1, False
        self._iss = itertools.count(1)
        self._wo = itertools.count(1)
        self._tasks: set = set()
        self.conds: dict[tuple, dict] = {}
        self.last = self.src.readings()
        self.log("system", "Simulation started with 30 days of seeded history")

    def log(self, kind: str, text: str):
        self.events.appendleft({"t": self.src.now().isoformat(), "kind": kind, "text": text})

    def name(self, target: str) -> str:
        if target in self.room_cfg:
            return self.room_cfg[target]["name"]
        if target in self.bin_cfg:
            return self.bin_cfg[target]["name"]
        return target

    def location(self, target: str) -> str:
        c = self.room_cfg.get(target) or self.bin_cfg.get(target)
        if not c:
            return ""
        b = self.bld_cfg.get(c["building"])
        return f"{b['name'] if b else 'Outdoor'}, floor {c['floor']}"

    def building_of(self, target: str) -> str:
        c = self.room_cfg.get(target) or self.bin_cfg.get(target) or {}
        return c.get("building", "")

    # ------------------------------------------------------------------- tick
    def tick(self, minutes: int = 1):
        for _ in range(minutes):
            self.src.step(1)
            self._evaluate()

    def _evaluate(self):
        rd = self.last = self.src.readings()
        now = self.src.now()
        conds: dict[tuple, dict] = {}

        for rid, r in rd["rooms"].items():
            rc = self.room_cfg[rid]
            on = sorted({FIXTURE_LABEL[k] for k, v in r["on"].items() if v})
            detected = ["sensor"] + (["cv"] if r["cv_live"] else [])
            conds[("ENERGY_WASTE", rid)] = {
                "active": r["occ"] == 0 and r["power_w"] > 50,
                "rate": r["power_w"] / 1000 * cfg.TARIFF_INR_PER_KWH,
                "evidence": {"occupancy": r["occ"], "empty_min": r["empty_min"], "power_w": r["power_w"],
                             "fixtures_on": on, "detected_by": detected},
                "threshold": "ENERGY_FAST" if (r["cv_live"] or rid in self.demo_targets) else "ENERGY_WASTE"}
            if rc["capacity"]:
                conds[("UNDERUSED_BOOKING", rid)] = {
                    "active": r["scheduled"] and r["occ"] < 0.2 * rc["capacity"],
                    "rate": r["power_w"] / 1000 * cfg.TARIFF_INR_PER_KWH,
                    "evidence": {"course": r["course"], "occ": r["occ"], "capacity": rc["capacity"],
                                 "detected_by": ["timetable", "sensor"] + (["cv"] if r["cv_live"] else [])}}

        for wid, w in rd["washrooms"].items():
            expected = w["floor_occ"] * 0.02
            excess = round(max(0.0, w["flow_lpm"] - expected * 1.6 - 0.3), 1)
            conds[("WATER_LEAK", wid)] = {
                "active": excess > 1.0, "rate": excess * 60 / 1000 * cfg.WATER_INR_PER_KL,
                "evidence": {"flow_lpm": w["flow_lpm"], "expected_lpm": round(expected, 2), "excess_lpm": excess,
                             "detected_by": ["water meter"]}}

        for bid, b in rd["bins"].items():
            self.fill_hist[bid].append(b["fill"])
            conds[("BIN_OVERFLOW", bid)] = {"active": b["fill"] >= 85, "rate": 0.0,
                                            "evidence": {"fill": b["fill"], "detected_by": ["fill sensor"]}}

        # CV-only conditions (live camera bound to a washroom or bin)
        for cam, target in self.cv_bindings.items():
            det = self.cv_last.get(cam)
            fresh = det and time.time() - det["ts"] < 10
            if target in self.room_cfg and self.room_cfg[target]["type"] == "washroom":
                if fresh and det.get("tap_on") and det.get("people", 0) == 0:
                    conds[("WATER_LEAK", target)] = {
                        "active": True, "rate": 6 * 60 / 1000 * cfg.WATER_INR_PER_KL, "threshold": "CV_TAP",
                        "evidence": {"excess_lpm": 6, "tap_running": True, "people": 0, "detected_by": ["cv"]}}
            if target in self.bin_cfg and fresh and det.get("bin_state") == "overflow":
                conds[("BIN_OVERFLOW", target)] = {"active": True, "rate": 0.0, "threshold": "CV_BIN",
                                                   "evidence": {"fill": 100, "detected_by": ["cv"]}}
        self.conds = conds

        for key, c in conds.items():
            itype, target = key
            self.timers[key] = self.timers.get(key, 0) + 1 if c["active"] else 0
            iid = self.open_by_key.get(key)
            issue = self.issues.get(iid) if iid else None
            if c["active"] and not issue and self.timers[key] >= THRESHOLD_MIN[c.get("threshold", itype)]:
                issue = self.create_issue(itype, target, c["rate"], c["evidence"])
            if not issue:
                continue
            if c["active"]:
                issue["rate_inr_hr"] = _money(c["rate"])
                if issue["sensor_managed"]:
                    issue["evidence"].update(c["evidence"])
                self._accrue(issue, c)
            self._lifecycle(issue, c["active"], now)

        # issues without a sensor condition (e.g. citizen litter reports)
        for iid in list(self.open_by_key.values()):
            issue = self.issues[iid]
            if (issue["type"], issue["target"]) not in conds:
                self._lifecycle(issue, issue["status"] != "resolved", now)

        for issue in list(self.issues.values()):
            self._simulated_staff(issue, now)
            self._maybe_escalate(issue, now)

    def _simulated_staff(self, issue: dict, now: datetime):
        """Background (non-demo) issues are handled by simulated staff so the campus doesn't pile up:
        acknowledge after ~5-12 min, fix after ~25-70 min. Demo issues are left to real phones."""
        if issue["demo"] or issue["status"] not in ("assigned", "in_progress") or not issue.get("wo"):
            return
        age = (now - datetime.fromisoformat(issue["created_at"])).total_seconds() / 60
        seed = sum(map(ord, issue["id"]))
        if issue["status"] == "assigned" and age >= 5 + seed % 8:
            self.ack(issue["wo"], via="staff (simulated)")
        elif issue["status"] == "in_progress" and age >= 25 + seed % 46:
            self.resolve(issue["id"], via="staff (simulated)")

    def _accrue(self, issue: dict, c: dict):
        if issue["status"] in TERMINAL:
            return
        issue["loss_inr"] += c["rate"] / 60
        if issue["type"] in ("ENERGY_WASTE", "UNDERUSED_BOOKING"):
            kwh = c["rate"] / cfg.TARIFF_INR_PER_KWH / 60
            issue["loss_kwh"] += kwh
            issue["loss_co2"] += kwh * cfg.GRID_EF_KG_PER_KWH
        elif issue["type"] == "WATER_LEAK":
            issue["loss_l"] += c["evidence"].get("excess_lpm", 0)

    def _lifecycle(self, issue: dict, active: bool, now: datetime):
        st = issue["status"]
        if st in ("open", "assigned", "in_progress") and not active and issue["sensor_managed"]:
            self._close(issue, "closed" if issue["type"] == "UNDERUSED_BOOKING" else "auto_closed", now)
        elif st == "resolved":
            if not active:
                self.verify(issue)
            elif (now - datetime.fromisoformat(issue["resolved_at"])).total_seconds() / 60 >= 3:
                self.reopen(issue)

    def _close(self, issue: dict, status: str, now: datetime):
        issue["status"], issue["closed_at"] = status, now.isoformat()
        self.open_by_key.pop((issue["type"], issue["target"]), None)
        wo = self.wos.get(issue.get("wo"))
        if wo:
            wo["status"] = "closed"
        self.log("closed", f"{issue['id']} {wol.type_label(issue['type'])} at {issue['target']} cleared on its own")

    def _maybe_escalate(self, issue: dict, now: datetime):
        limit = ESCALATE_MIN.get(issue["priority"])
        if not limit or issue["status"] != "assigned" or issue.get("escalated") or not issue.get("assigned_at"):
            return
        if (now - datetime.fromisoformat(issue["assigned_at"])).total_seconds() / 60 < limit:
            return
        issue["escalated"] = True
        wo = self.wos[issue["wo"]]
        text = (f"Escalation: {wo['id']} ({wol.type_label(issue['type'])} at {issue['target']}, {issue['target_name']}) "
                f"not acknowledged in {limit} min by {wo['assignee']}. "
                f"Running loss: ₹{_money(issue['loss_inr'])}.")
        self.log("escalated", f"{wo['id']} escalated to estate manager")
        self._spawn(self._notify("estate_manager", text, real=issue["demo"]))

    # ----------------------------------------------------------------- issues
    def _priority(self, itype: str, rate: float, ev: dict, reports: int = 1) -> str:
        if itype == "ENERGY_WASTE":
            p = "P1" if rate >= 25 else "P2" if rate >= 8 else "P3"
        elif itype == "WATER_LEAK":
            p = "P1" if ev.get("excess_lpm", 0) >= 3 else "P2"
        elif itype == "BIN_OVERFLOW":
            p = "P1" if ev.get("fill", 0) >= 100 else "P2"
        elif itype == "LITTER":
            p = "P2"
        else:
            p = "P3"
        if reports >= 3 and p != "P1":
            p = "P1" if p == "P2" else "P2"
        return p

    def create_issue(self, itype: str, target: str, rate: float, evidence: dict, *, demo: bool = False,
                     photo: str | None = None, sensor_managed: bool = True, reporter: str | None = None) -> dict:
        now = self.src.now()
        demo = demo or target in self.demo_targets or "cv" in evidence.get("detected_by", [])
        self.demo_targets.discard(target)
        prio = self._priority(itype, rate, evidence)
        issue = {
            "id": f"ISS-{next(self._iss)}", "type": itype, "target": target, "target_name": self.name(target),
            "building": self.building_of(target), "location": self.location(target), "title":
                f"{wol.type_label(itype)} · {self.name(target)}", "status": "open", "priority": prio,
            "priority_icon": PRIORITY_ICON[prio], "created_at": now.isoformat(), "rate_inr_hr": _money(rate),
            "loss_inr": 0.0, "loss_kwh": 0.0, "loss_l": 0.0, "loss_co2": 0.0, "evidence": dict(evidence),
            "detected_by": evidence.get("detected_by", []), "demo": demo, "photo": photo,
            "sensor_managed": sensor_managed, "reports_count": 1 if reporter else 0, "escalated": False,
            "saved_inr": 0.0,
        }
        self.issues[issue["id"]] = issue
        self.open_by_key[(itype, target)] = issue["id"]
        self.log("detected", f"{issue['id']} {issue['title']} ({', '.join(issue['detected_by'])})")
        self.dispatch(issue)
        return issue

    def dispatch(self, issue: dict):
        role = wol.ROLE_FOR[issue["type"]]
        staff = self.staff[role]
        wo = {"id": f"WO-{next(self._wo)}", "issue_id": issue["id"], "role": role, "assignee": staff["name"],
              "lang": self.lang_for(role), "content": {"en": wol.template(issue)}, "source": "template",
              "status": "sent", "created_at": self.src.now().isoformat(), "validator": None}
        self.wos[wo["id"]] = wo
        issue.update(wo=wo["id"], status="assigned", assigned_at=self.src.now().isoformat())
        self._spawn(self._send_wo(wo, issue))

    async def _send_wo(self, wo: dict, issue: dict):
        if llm.available() and (issue["demo"] or issue["priority"] == "P1"):
            await wol.enrich(issue, wo)
            if wo["lang"] != "en":
                await wol.translate(wo, wo["lang"])
        text = wol.message(wo, issue, wo["lang"])
        await self._notify(wo["role"], text, real=issue["demo"],
                           buttons=[(f"ACK:{wo['id']}", "Noted"), (f"DONE:{wo['id']}", "Done")], wo=wo["id"])

    async def _notify(self, role: str, text: str, real: bool = False, buttons=None, wo: str | None = None,
                      phone: str | None = None):
        phone = phone or self.notifier.address(role) or cfg.STAFF_PHONES.get(role, "")
        channel, status = "console", "shown in app"
        use_real = (self.wa_mode == "all" or (self.wa_mode == "demo" and real)) and self.notifier.channel != "console"
        if use_real and phone:
            ok, detail = await self.notifier.send(phone, text, buttons)
            channel, status = self.notifier.channel, ("delivered" if ok else f"failed: {detail}")
        self.feed.add("out", role, text, channel, status, phone=mask(phone), wo=wo,
                      buttons=[b[1] for b in buttons] if buttons else [])
        # judges who opened t.me/<bot>?start=judge get a copy of every real (demo) staff message
        observers = getattr(self.notifier, "observers", [])
        if use_real and wo and role in self.staff and observers:
            copy = f"[Copy of message to {self.staff[role]['name']}]\n\n{text}"
            for chat in list(observers)[-20:]:
                if f"tg:{chat}" != phone:
                    await self.notifier.send(f"tg:{chat}", copy, buttons)

    def _spawn(self, coro):
        try:
            task = asyncio.get_running_loop().create_task(coro)
        except RuntimeError:
            coro.close()
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # ------------------------------------------------------------- lifecycle
    def ack(self, wo_id: str, via: str = "app") -> str:
        wo = self.wos.get(wo_id)
        if not wo:
            return "unknown"
        issue = self.issues[wo["issue_id"]]
        if issue["status"] in TERMINAL or issue["status"] == "resolved":
            return "already_clear"
        wo["status"], issue["status"] = "acked", "in_progress"
        issue["acked_at"] = self.src.now().isoformat()
        self.log("ack", f"{wo_id} acknowledged by {wo['assignee']} via {via}")
        return "ack"

    def resolve(self, issue_id: str, via: str = "app", proof: str | None = None) -> str:
        issue = self.issues.get(issue_id)
        if not issue:
            return "unknown"
        if issue["status"] in TERMINAL:
            return "already_clear"
        now = self.src.now()
        issue.update(status="resolved", resolved_at=now.isoformat(), resolved_via=via)
        if proof:
            issue["proof"] = proof
        wo = self.wos.get(issue.get("wo"))
        if wo:
            wo["status"] = "done"
        action = {"ENERGY_WASTE": "fix_room", "UNDERUSED_BOOKING": "fix_room", "WATER_LEAK": "fix_leak",
                  "BIN_OVERFLOW": "empty_bin"}.get(issue["type"])
        if action:
            self.src.act(action, issue["target"])
        self.log("resolved", f"{issue['id']} marked done via {via}; verifying with next reading")
        if (issue["type"], issue["target"]) not in self.conds:
            self.verify(issue)
        return "done_pending"

    def verify(self, issue: dict):
        now = self.src.now()
        hours = AVOIDED_HOURS.get(issue["type"], 0)
        saved = issue["rate_inr_hr"] * hours
        issue.update(status="verified", verified_at=now.isoformat(), saved_inr=_money(saved))
        if issue["type"] in ("ENERGY_WASTE", "UNDERUSED_BOOKING"):
            kwh = saved / cfg.TARIFF_INR_PER_KWH
            self.saved["kwh"] += kwh
            self.saved["co2"] += kwh * cfg.GRID_EF_KG_PER_KWH
        elif issue["type"] == "WATER_LEAK":
            self.saved["l"] += issue["evidence"].get("excess_lpm", 0) * 60 * hours
        self.saved["inr"] += saved
        self.open_by_key.pop((issue["type"], issue["target"]), None)
        self.recently_fixed[issue["target"]] = now
        wo = self.wos.get(issue.get("wo"))
        self.log("verified", f"{issue['id']} verified fixed at {issue['target']} (₹{_money(saved)} saved)")
        if wo:
            wo["status"] = "verified"
            self._spawn(self._notify(wo["role"], wol.t("verified", wo["lang"], target=f"{issue['target']} ({issue['target_name']})",
                                                       saved=_money(saved)), real=issue["demo"], wo=wo["id"]))

    def reopen(self, issue: dict):
        issue["status"] = "assigned"
        issue["reopened"] = issue.get("reopened", 0) + 1
        wo = self.wos.get(issue.get("wo"))
        self.log("reopened", f"{issue['id']} still active after fix; sent back to {wo['assignee'] if wo else 'staff'}")
        if wo:
            wo["status"] = "sent"
            self._spawn(self._notify(wo["role"], wol.t("not_fixed", wo["lang"], target=issue["target"], wo=wo["id"]),
                                     real=issue["demo"], wo=wo["id"]))

    # ------------------------------------------------------- incoming messages
    def lang_for(self, role: str) -> str:
        """The person's chosen language (Telegram /language) or the role default."""
        return self.notifier.lang_for_role(role) or self.staff.get(role, {}).get("lang", "en")

    def roles_for_phone(self, phone: str) -> list[str]:
        return [r for r, p in cfg.STAFF_PHONES.items() if p and p == phone]

    async def incoming(self, phone: str, text: str, button_id: str | None = None, image: bytes | None = None,
                       channel: str = "whatsapp", role_hint: str | None = None) -> str:
        """Handles a staff/student message. Returns the reply key used."""
        known = self.notifier.roles_for_address(phone) or self.roles_for_phone(phone)
        roles = ([role_hint] if role_hint else []) + [r for r in known if r != role_hint]
        role = roles[0] if roles else "student"
        self.feed.add("in", role, text or ("[photo]" if image else ""), channel, phone=mask(phone),
                      photo=bool(image))
        lang = self.lang_for(role) if role in self.staff else "en"
        real = channel != "console"

        m = re.search(r"WO-?\s?(\d+)", text or "", re.I)
        wo_id = f"WO-{m.group(1)}" if m else None
        low = (text or "").lower()
        action = None
        if button_id and ":" in button_id:
            action, wo_id = button_id.split(":", 1)
            action = action.lower()
        elif button_id and button_id.lower() in ("ack", "done"):  # fixed-id buttons: latest work order
            action = button_id.lower()
        elif any(w in low for w in DONE_WORDS):
            action = "done"
        elif any(re.search(rf"(^|\W){re.escape(w)}($|\W)", low) for w in ACK_WORDS):
            action = "ack"

        if image is not None and not action:
            from .intake.citizen import submit_report
            loc = re.search(r"REPORT\s+([A-Z][A-Z0-9]?-\d{1,2}(?:\d{2}|WR)|BIN-\d+)", (text or "").upper())
            result = await submit_report(self, image, loc.group(1) if loc else None, text, reporter=mask(phone) or role)
            await self._notify(role, result["message"], real=real, phone=phone)
            return "report"

        if action and not wo_id:
            mine = [w for w in self.wos.values() if w["role"] in (roles or [role]) and w["status"] in ("sent", "acked")]
            wo_id = mine[-1]["id"] if mine else None
        wo = self.wos.get(wo_id) if wo_id else None
        if not action or not wo:
            await self._notify(role, wol.t("unknown", lang), real=real, phone=phone)
            return "unknown"
        issue = self.issues[wo["issue_id"]]
        if action == "ack":
            key = self.ack(wo_id, via=channel)
            await self._notify(role, wol.t(key, lang, wo=wo_id), real=real, phone=phone, wo=wo_id)
            return key
        if issue["status"] in TERMINAL or issue["status"] == "resolved":
            await self._notify(role, wol.t("already_clear", lang, wo=wo_id), real=real, phone=phone, wo=wo_id)
            return "already_clear"
        proof = None
        if image:
            from .intake.citizen import save_photo
            proof = save_photo(image, prefix=wo_id)
        # tell them we're verifying *before* resolving, so "verified" can't arrive first
        await self._notify(role, wol.t("done_pending", lang, target=issue["target"]), real=real, phone=phone, wo=wo_id)
        return self.resolve(issue["id"], via=channel, proof=proof)

    # -------------------------------------------------------------------- demo
    def inject(self, scenario: str, target: str):
        self.demo_targets.add(target)
        self.src.inject(scenario, target)
        self.log("demo", f"Scenario '{scenario}' injected at {target}")

    def jump(self, hour: int):
        now = self.src.now()
        target = now.replace(hour=hour % 24, minute=0)
        if target <= now:
            target += timedelta(days=1)
        while self.src.now() < target:
            self.tick(1)

    def on_cv(self, cam_id: str, det: dict):
        det = {**det, "ts": time.time()}
        self.cv_last[cam_id] = det
        target = self.cv_bindings.get(cam_id)
        if target in self.src.rooms:
            self.src.set_cv_override(target, det.get("people"), det.get("lights_on"), det.get("fans_on"))

    # ---------------------------------------------------------------- metrics
    def rolling(self, b: str, hours: int = 24) -> dict:
        acc = {"kwh": 0.0, "waste_kwh": 0.0, "water_l": 0.0, "leak_l": 0.0}
        for h in self.src.history[-(hours - 1):]:
            for k in acc:
                acc[k] += h["b"][b][k]
        for k in acc:
            acc[k] += self.src.hour_acc[b][k]
        return acc

    def scores(self) -> dict:
        out = {}
        for b in self.src.buildings:
            r = self.rolling(b)
            energy = 1 - r["waste_kwh"] / max(r["kwh"], 1)
            water = 1 - r["leak_l"] / max(r["water_l"], 1)
            bins = [x for x in self.bin_cfg.values() if x["building"] == b]
            full = sum(1 for x in bins if self.last["bins"][x["id"]]["fill"] >= 85)
            waste = 1 - full / max(len(bins), 1)
            open_n = sum(1 for i in self.open_by_key.values() if self.issues[i]["building"] == b)
            resp = 1 / (1 + 0.15 * open_n)
            out[b] = {"score": round(100 * (0.4 * energy + 0.25 * water + 0.2 * waste + 0.15 * resp)),
                      "energy_eff": round(energy * 100), "water_eff": round(water * 100), "open_issues": open_n,
                      **{k: round(v, 1) for k, v in r.items()}}
        return out

    def kpis(self) -> dict:
        keys = next(iter(self.src.today.values())).keys()
        tot = {k: sum(self.src.today[b][k] for b in self.src.today) for k in keys}
        wasted_inr = tot["waste_kwh"] * cfg.TARIFF_INR_PER_KWH + tot["leak_l"] / 1000 * cfg.WATER_INR_PER_KL
        sc = self.scores()
        return {
            "wasted_inr_today": round(wasted_inr), "kwh_today": round(tot["kwh"], 1),
            "waste_kwh_today": round(tot["waste_kwh"], 1), "water_l_today": round(tot["water_l"]),
            "leak_l_today": round(tot["leak_l"]), "co2_kg_today": round(tot["kwh"] * cfg.GRID_EF_KG_PER_KWH, 1),
            "waste_co2_kg_today": round(tot["waste_kwh"] * cfg.GRID_EF_KG_PER_KWH, 1),
            "open_issues": len(self.open_by_key), "saved_inr": round(self.saved["inr"]),
            "saved_kwh": round(self.saved["kwh"], 1), "saved_l": round(self.saved["l"]),
            "saved_co2": round(self.saved["co2"], 1),
            "score": round(sum(s["score"] for s in sc.values()) / len(sc)),
        }

    def bin_forecast(self, bid: str) -> int | None:
        h = self.fill_hist[bid]
        if len(h) < 30 or h[-1] >= 100:
            return None
        slope = (h[-1] - h[0]) / (len(h) - 1)
        return int((100 - h[-1]) / slope) if slope > 0.01 else None

    # --------------------------------------------------------------- snapshot
    def room_status(self, rid: str) -> str:
        for itype in ("WATER_LEAK", "ENERGY_WASTE", "LITTER", "UNDERUSED_BOOKING"):
            if (itype, rid) in self.open_by_key:
                return STATUS_FOR[itype]
        fixed = self.recently_fixed.get(rid)
        if fixed and (self.src.now() - fixed).total_seconds() < 15 * 60:
            return "fixed"
        r = self.last["rooms"].get(rid)
        if r:
            return "active" if r["occ"] > 0 else "idle"
        w = self.last["washrooms"].get(rid)
        return "active" if w and w["flow_lpm"] > 0.05 else "idle"

    def public_issue(self, i: dict) -> dict:
        out = {k: v for k, v in i.items()}
        for k in ("loss_inr", "loss_kwh", "loss_l", "loss_co2"):
            out[k] = round(i[k], 2)
        return out

    def snapshot(self) -> dict:
        rooms = {}
        for rid in self.room_cfg:
            base = self.last["rooms"].get(rid) or self.last["washrooms"].get(rid) or {}
            rooms[rid] = {**base, "status": self.room_status(rid),
                          "issue": next((iid for (t, tg), iid in self.open_by_key.items() if tg == rid), None)}
        bins = {}
        for bid, b in self.last["bins"].items():
            status = "waste" if ("BIN_OVERFLOW", bid) in self.open_by_key else (
                "fixed" if bid in self.recently_fixed and (self.src.now() - self.recently_fixed[bid]).total_seconds() < 900
                else "ok")
            bins[bid] = {**b, "status": status, "minutes_to_full": self.bin_forecast(bid),
                         "issue": self.open_by_key.get(("BIN_OVERFLOW", bid))}
        active = [i for i in self.issues.values() if i["status"] not in TERMINAL]
        done = sorted([i for i in self.issues.values() if i["status"] in TERMINAL],
                      key=lambda i: i.get("verified_at") or i.get("closed_at") or "", reverse=True)[:20]
        return {
            "clock": self.src.now().isoformat(), "speed": self.speed, "paused": self.paused,
            "kpis": self.kpis(), "buildings": self.scores(), "rooms": rooms, "bins": bins,
            "issues": [self.public_issue(i) for i in active + done],
            "workorders": {w["id"]: w for w in self.wos.values() if w["issue_id"] in {i["id"] for i in active + done}},
            "feed": self.feed.recent(40), "events": list(self.events)[:25],
            "cv": {"bindings": self.cv_bindings,
                   "live": {c: {k: v for k, v in d.items() if k != "annotated"} for c, d in self.cv_last.items()
                            if time.time() - d["ts"] < 10}},
            "channel": self.notifier.channel, "wa_mode": self.wa_mode, "llm": llm.available(),
            "bot": {"username": getattr(self.notifier, "username", None),
                    "linked": sorted(getattr(self.notifier, "chats", {}).keys())},
        }
