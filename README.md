# CampusPulse: continuous green audit for college campuses

**Code Clash 2.0 · PS2: AI-Powered Sustainable Campus**

Every Indian college does its green audit (NAAC Criterion 7) once a year, by hand. CampusPulse does it continuously, on a live digital twin of **Dayananda Sagar University, Harohalli**. Computer vision and sensors catch energy waste, water leaks, overflowing bins and underused bookings. Each issue is priced in ₹ and CO₂, sent to the right staff member's phone in their language, verified when fixed, and rolled into a NAAC-ready report.

## What it does

| Feature | Details |
|---|---|
| **Digital twin of DSU Harohalli** | Real building outlines, floors, roads and grounds from OpenStreetMap. 65 simulated rooms and 12 bins placed inside 10 monitored buildings. Live state over WebSocket. |
| **Computer vision** | Live camera: YOLO11n people count, light state (calibrated per room), fan motion. Faces are blurred and nothing is stored. |
| **Trained bin model** | YOLO11n fine-tuned on Garbage_Fill_Level (Empty / Half / Overflow): **90% of held-out photos correct, mAP50 0.898**. See `training/`. |
| **Detection rules** | Energy waste (empty room, power on), water leak (flow vs. expected), bin overflow (+ time-to-full forecast), underused booking (timetable vs. occupancy). |
| **Staff work orders** | AI-written work order sent on **Telegram** to the right role, in **English / हिन्दी / ಕನ್ನಡ** (each person chooses). Staff tap **Noted / Done**, and the twin **verifies the fix** with the next reading. Unanswered P1/P2 issues escalate to the Estate Manager. WhatsApp (Meta Cloud API, Twilio) uses the same notifier interface. |
| **Student photo reports** | Scan a location QR → photo → trained model + vision LLM verify it → duplicates merge → same work-order loop. |
| **What-if simulator** | Replays 30 days with and without a policy (auto-off, LED retrofit, leak alerts, releasing underused bookings) → ₹ per month, CO₂ and payback. |
| **NAAC green audit** | Criterion 7.1 report and weekly report generated from live data, printable to PDF. |
| **Ask your campus** | Copilot with tool calling over live twin data. |
| **Numeric validator** | The LLM writes words; the engine computes numbers. AI text with a number not in the data is replaced by a template; IDs and numbers must survive translation. |

## Architecture

```
React + Three.js twin ──WebSocket──► FastAPI
  Work orders · Cameras · What-if    ├─ DataSource (simulator → swap for MQTT / BMS meters)
  Reports · Copilot · /report        ├─ Twin engine: detection rules, pricing, lifecycle, escalation
                                     ├─ CV: YOLO11n (people + bin model) on ONNX Runtime or PyTorch
                                     ├─ GenAI (Groq): work orders, translation, copilot, reports + validator
                                     └─ Notifier: Telegram | Meta WhatsApp Cloud API | Twilio | in-app
```

- **Data:** building geometry is real (© OpenStreetMap contributors, ODbL). Rooms, sensors and readings are **simulated**, priced with tariff, water-rate and CEA grid-emission constants in `backend/app/config.py`. CV inference is real. To connect real meters, write a new `DataSource`; the engine doesn't change.
- **Privacy:** camera frames are processed in memory, head regions are blurred, and only counts are kept.
- **Runs on CPU:** no GPU needed (ONNX Runtime, ~50–60 ms per frame).

## Run locally

```bash
# backend
cd backend
python -m venv .venv && .venv/Scripts/activate      # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt                       # or requirements-render.txt for the slim ONNX-only setup
cp .env.example .env                                  # add GROQ_API_KEY (free at console.groq.com) and optionally TELEGRAM_BOT_TOKEN
uvicorn app.main:app --port 8002

# frontend (new terminal)
cd frontend
npm install
npm run dev                                           # http://localhost:5173
```

Press **Ctrl+D** in the app for demo controls: inject scenarios, change speed, jump in time.

`CV_BACKEND` selects the vision runtime: `auto` (default: ONNX if `backend/models/*.onnx` exist, else PyTorch), `onnx` or `torch`.

## Deploy (Render, free tier)

`render.yaml` + `Dockerfile.render` deploy the whole app as one service (the backend serves the built frontend), using ONNX Runtime so it fits in 512 MB.
Render → **New → Blueprint** → this repo, then set the secrets `GROQ_API_KEY`, `TELEGRAM_BOT_TOKEN` and optionally `TELEGRAM_CHATS` (saved role links).
`Dockerfile` is the full PyTorch image; git tag `v1-pytorch` is the version before the ONNX switch.

## Tests

```bash
cd backend && python -m pytest -q
```

## Credits

- Map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors (ODbL).
- Bin dataset: *Garbage_Fill_Level* by charuka-edirisinghe, Roboflow Universe (CC BY 4.0).
- YOLO11 by Ultralytics.

## Team

| Role | Member |
|---|---|
| CV lead | _name_ |
| Backend / twin lead | _name_ |
| Frontend lead | _name_ |
| GenAI + pitch lead | _name_ |
