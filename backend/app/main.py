"""CampusPulse API: REST + WebSocket over the twin engine."""
import asyncio
import io
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import qrcode
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config as cfg
from . import whatif
from .cv import detectors
from .engine import Engine
from .genai import copilot, reports
from .genai import workorders as wol
from .intake import citizen
from .notify.meta_wa import parse_webhook, valid_signature

log = logging.getLogger("campuspulse")
engine = Engine()
clients: set[WebSocket] = set()
cameras: dict[str, detectors.CameraState] = {}
CALIB_FILE = cfg.DATA_DIR / "camera_calibration.json"  # saved light calibration, survives restarts


def camera(cam_id: str) -> detectors.CameraState:
    if cam_id not in cameras:
        state = detectors.CameraState()
        saved = json.loads(CALIB_FILE.read_text()) if CALIB_FILE.exists() else {}
        state.calib = saved.get(cam_id, {})
        cameras[cam_id] = state
    return cameras[cam_id]
latest_frames: dict[str, dict] = {}


async def sim_loop():
    while True:
        await asyncio.sleep(1)
        try:
            if engine.speed > 1 and time.time() - getattr(engine, "speed_set_at", 0) > 120:
                engine.speed = 1  # shared simulation: never leave it fast-forwarded for the next visitor
            if not engine.paused:
                engine.tick(engine.speed)
            if clients:
                payload = json.dumps(engine.snapshot(), default=str)
                for ws in list(clients):
                    try:
                        await ws.send_text(payload)
                    except Exception:  # noqa: BLE001
                        clients.discard(ws)
        except Exception:  # noqa: BLE001
            log.exception("sim loop error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(sim_loop())
    if hasattr(engine.notifier, "poll"):
        asyncio.create_task(engine.notifier.poll(engine))
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, detectors._person_model)  # warm up the detector
    loop.run_in_executor(None, whatif.run, {"auto_off_minutes": 10, "led_retrofit": True, "fix_leaks": True})  # warm cache
    yield
    task.cancel()


app = FastAPI(title="CampusPulse", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/api/uploads", StaticFiles(directory=cfg.UPLOADS_DIR), name="uploads")


# ------------------------------------------------------------------ state
@app.api_route("/api/health", methods=["GET", "HEAD"])
def health():
    return {"ok": True, "channel": engine.notifier.channel, "llm": bool(cfg.GROQ_API_KEY),
            "bin_model": detectors.bin_model() is not None, "cv_backend": detectors.cv_backend()}


@app.get("/api/campus")
def campus():
    return {**engine.campus, "constants": {
        "tariff_inr_per_kwh": cfg.TARIFF_INR_PER_KWH, "tariff_source": cfg.TARIFF_SOURCE,
        "water_inr_per_kl": cfg.WATER_INR_PER_KL, "water_source": cfg.WATER_SOURCE,
        "grid_ef_kg_per_kwh": cfg.GRID_EF_KG_PER_KWH, "grid_ef_source": cfg.GRID_EF_SOURCE}}


@app.get("/api/state")
def state():
    return engine.snapshot()


@app.websocket("/ws/state")
async def ws_state(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        await ws.send_text(json.dumps(engine.snapshot(), default=str))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(ws)


@app.get("/api/history")
def history(hours: int = 48):
    return {"hourly": engine.src.history[-hours:], "daily": engine.src.daily[-30:]}


@app.get("/api/rooms/{room_id}")
def room(room_id: str):
    data = copilot._room(engine, room_id)
    if "error" in data:
        raise HTTPException(404, data["error"])
    return data


# ----------------------------------------------------------------- issues
@app.post("/api/issues/{issue_id}/resolve")
def resolve_issue(issue_id: str):
    return {"result": engine.resolve(issue_id, via="dashboard")}


@app.post("/api/workorders/{wo_id}/ack")
def ack_wo(wo_id: str):
    return {"result": engine.ack(wo_id, via="dashboard")}


@app.get("/api/workorders/{wo_id}")
async def get_wo(wo_id: str, lang: str = "en"):
    wo = engine.wos.get(wo_id)
    if not wo:
        raise HTTPException(404)
    issue = engine.issues[wo["issue_id"]]
    if lang != "en" and lang not in wo["content"]:
        await wol.translate(wo, lang)
    return {**wo, "message": wol.message(wo, issue, lang), "lang_shown": lang if lang in wo["content"] else "en"}


# ------------------------------------------------------------------- demo
class Inject(BaseModel):
    scenario: str
    target: str


@app.post("/api/demo/inject")
def demo_inject(body: Inject):
    engine.inject(body.scenario, body.target)
    return {"ok": True}


def require_admin(key: str | None):
    """Global, destructive controls are team-only on the hosted site (set ADMIN_KEY to use them there)."""
    hosted = bool(os.getenv("RENDER_EXTERNAL_URL"))
    admin_key = os.getenv("ADMIN_KEY", "")
    if hosted and (not admin_key or key != admin_key):
        raise HTTPException(403, "This control is disabled on the public demo")


@app.post("/api/demo/speed")
def demo_speed(x: int = 1, paused: bool | None = None, key: str | None = None):
    # anyone may speed up (max 15x, auto-returns to 1x after 2 min); pausing is team-only
    engine.speed = max(1, min(x, 15))
    engine.speed_set_at = time.time()
    if paused is not None:
        require_admin(key)
        engine.paused = paused
    return {"speed": engine.speed, "paused": engine.paused}


@app.post("/api/demo/jump")
def demo_jump(hour: int, key: str | None = None):
    require_admin(key)
    engine.jump(hour)
    return {"clock": engine.src.now().isoformat()}


@app.post("/api/demo/reset")
def demo_reset(key: str | None = None):
    require_admin(key)
    engine.reset()
    return {"ok": True}


@app.post("/api/demo/wa-mode")
def wa_mode(mode: str, key: str | None = None):
    require_admin(key)
    if mode not in ("demo", "all", "off"):
        raise HTTPException(400, "mode must be demo | all | off")
    engine.wa_mode = mode
    return {"wa_mode": mode}


# --------------------------------------------------------------------- CV
@app.post("/api/cv/frame")
async def cv_frame(file: UploadFile = File(...), cam_id: str = Form("cam-live")):
    data = await file.read()
    state = camera(cam_id)
    target = engine.cv_bindings.get(cam_id, "")
    want_bin = target in engine.bin_cfg
    try:
        det = await asyncio.to_thread(detectors.analyse, state, data, want_bin)
    except ValueError as e:
        raise HTTPException(400, str(e))
    annotated = det.pop("annotated")
    engine.on_cv(cam_id, det)
    latest_frames[cam_id] = {"annotated": annotated}
    return {**det, "annotated": annotated, "target": target}


class Bind(BaseModel):
    cam_id: str
    target: str


@app.post("/api/cv/bind")
def cv_bind(body: Bind):
    if body.target not in engine.room_cfg and body.target not in engine.bin_cfg:
        raise HTTPException(400, "unknown target")
    engine.cv_bindings[body.cam_id] = body.target
    return {"bindings": engine.cv_bindings}


@app.post("/api/cv/calibrate")
def cv_calibrate(cam_id: str, state: str):
    last = engine.cv_last.get(cam_id)
    if not last or state not in ("on", "off"):
        raise HTTPException(400, "send frames first; state must be on|off")
    cam = camera(cam_id)
    cam.calib[state] = last["brightness"]
    cam.light_on = None
    saved = json.loads(CALIB_FILE.read_text()) if CALIB_FILE.exists() else {}
    saved[cam_id] = cam.calib
    CALIB_FILE.write_text(json.dumps(saved, indent=1))
    return {"calib": cam.calib, "threshold": cam.light_threshold()}


@app.get("/api/cv/calibration")
def cv_calibration(cam_id: str = "cam-live"):
    cam = camera(cam_id)
    return {"calib": cam.calib, "threshold": cam.light_threshold(), "calibrated": len(cam.calib) == 2}


# ----------------------------------------------------------------- GenAI
class Policy(BaseModel):
    auto_off_minutes: int | None = None
    led_retrofit: bool = False
    fix_leaks: bool = False
    consolidate: bool = False
    extra_pickup: bool = False


@app.post("/api/whatif")
async def run_whatif(p: Policy):
    return await asyncio.to_thread(whatif.run, p.model_dump())


class Chat(BaseModel):
    messages: list[dict]


@app.post("/api/copilot")
async def ask_copilot(body: Chat):
    try:
        return await copilot.ask(engine, body.messages)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"copilot unavailable: {e}")


_report_cache: dict[str, tuple[str, dict]] = {}  # kind -> (simulated date, report)


@app.get("/api/reports/{kind}")
async def get_report(kind: str):
    """Latest report for today's simulated date; generated on first request, then cached."""
    if kind not in ("weekly", "naac"):
        raise HTTPException(404)
    today = engine.src.now().date().isoformat()
    cached = _report_cache.get(kind)
    if cached and cached[0] == today:
        return {**cached[1], "cached": True}
    return await make_report(kind)


@app.post("/api/reports/{kind}")
async def make_report(kind: str):
    if kind not in ("weekly", "naac"):
        raise HTTPException(404)
    report = await reports.generate(engine, kind)
    _report_cache[kind] = (engine.src.now().date().isoformat(), report)
    return report


# --------------------------------------------------------- citizen reports
@app.post("/api/citizen-reports")
async def citizen_report(request: Request, photo: UploadFile = File(...), loc: str = Form(...), note: str = Form("")):
    data = await photo.read()
    if len(data) > 12 * 1024 * 1024:
        raise HTTPException(413, "photo too large")
    reporter = request.client.host if request.client else "web"
    return await citizen.submit_report(engine, data, loc.strip().upper(), note, reporter=reporter)


@app.get("/api/citizen-reports/{ticket}")
def citizen_status(ticket: str):
    data = citizen.status(engine, ticket.upper())
    if not data:
        raise HTTPException(404)
    return data


@app.get("/api/locations")
def locations():
    rooms = [{"id": r["id"], "name": r["name"], "building": r["building"], "floor": r["floor"], "type": r["type"]}
             for r in engine.campus["rooms"]]
    bins = [{"id": b["id"], "name": b["name"], "building": b["building"], "floor": b["floor"], "type": "bin"}
            for b in engine.campus["bins"]]
    return rooms + bins


@app.get("/api/qr")
def qr(loc: str, base: str | None = None):
    url = f"{(base or cfg.FRONTEND_URL).rstrip('/')}/report?loc={loc}"
    img = qrcode.make(url, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png", headers={"X-Report-Url": url})


# ---------------------------------------------------------------- WhatsApp
@app.get("/api/wa/webhook")
def wa_verify(request: Request):
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == cfg.META["verify_token"] and cfg.META["verify_token"]:
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403)


@app.post("/api/wa/webhook")
async def wa_webhook(request: Request):
    body = await request.body()
    if not valid_signature(body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(403)
    for m in parse_webhook(json.loads(body or b"{}")):
        image = await engine.notifier.fetch_media(m["media_id"]) if m["media_id"] else None
        asyncio.create_task(engine.incoming(m["from"], m["text"], m["button_id"], image, channel=engine.notifier.channel))
    return {"ok": True}


@app.post("/api/wa/twilio")
async def wa_twilio(request: Request):
    form = await request.form()
    phone = str(form.get("From", "")).replace("whatsapp:", "")
    image = None
    if int(form.get("NumMedia", 0) or 0) > 0:
        image = await engine.notifier.fetch_media(str(form.get("MediaUrl0")))
    button = str(form.get("ButtonPayload", "")) or None  # quick-reply tap, e.g. "DONE:WO-5"
    asyncio.create_task(engine.incoming(phone, str(form.get("Body", "")), button, image, channel="whatsapp-twilio"))
    return PlainTextResponse("<Response></Response>", media_type="application/xml")


class SimMsg(BaseModel):
    role: str
    text: str = ""
    button_id: str | None = None


@app.post("/api/wa/simulate")
async def wa_simulate(body: SimMsg):
    """In-app phone mock-up: same handler as real WhatsApp, replies stay in the app."""
    phone = cfg.STAFF_PHONES.get(body.role, "")
    key = await engine.incoming(phone, body.text, body.button_id, None, channel="console", role_hint=body.role)
    return {"result": key}


@app.get("/api/wa/feed")
def wa_feed():
    return engine.feed.recent(80)


# ---------------------------------------- serve built frontend (single deploy)
DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.api_route("/{path:path}", methods=["GET", "HEAD"])  # HEAD: uptime monitors
    def spa(path: str):
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
