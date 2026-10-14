# CampusPulse: continuous green audit for college campuses

**Code Clash 2.0 · PS2: AI-Powered Sustainable Campus**

Every Indian college does its green audit (NAAC Criterion 7) once a year, by hand. CampusPulse does it every second. Computer vision and sensors catch energy waste, water leaks, overflowing bins and empty booked rooms. Each issue is shown live on a 3D digital twin and priced in ₹ and CO₂. Generative AI then dispatches the fix on WhatsApp in the staff member's own language and writes the NAAC report.

## What it does

| | Feature |
|---|---|
| 📷 **Computer vision** | Live camera: YOLO11n person count, light state, fan and tap motion. Faces are blurred and nothing is stored. Optional fine-tuned bin model. |
| 🏫 **Digital twin** | 3D campus with 31 rooms, 10 bins and 6 washroom water meters. Live state over WebSocket. Rooms change colour by status. |
| 🧠 **Fusion rules** | Energy waste (empty room with power on), water leak (night flow vs. expected), bin overflow (+ time-to-full forecast), ghost bookings (timetable vs. occupancy). |
| 💬 **WhatsApp work orders** | AI work order sent to the right staff member in **English / हिन्दी / ಕನ್ನಡ**. Staff reply `ACK` / `DONE`, and the twin **verifies the fix** with the next reading. Unanswered P1/P2 issues escalate to the estate manager. |
| 📸 **Student photo reports** | Scan a location QR → photo → vision LLM + CV verify it → duplicates merge → enters the same work-order loop. |
| 🧪 **What-if simulator** | Replays 30 days with and without a policy (auto-off, LED retrofit, leak alerts…) → ₹ saved per month, CO₂ and payback. |
| 📄 **NAAC green audit** | One-click Criterion 7.1 report and weekly report, printable to PDF. |
| 🤖 **Ask your campus** | Copilot with tool calling over live twin data. |
| ✅ **Numeric validator** | The LLM writes words; the engine computes numbers. Any number in AI output that isn't in the data is rejected, and IDs and numbers must survive translation. |

## Architecture

```
React + Three.js twin  ──WebSocket──►  FastAPI
  Cameras · Work orders · What-if        ├─ DataSource (MockSource simulator → swap for MQTT / BMS)
  Reports · Copilot · /report (mobile)   ├─ Twin engine: fusion rules, pricing, lifecycle, escalation
                                         ├─ CV: YOLO11n + OpenCV (CPU)
                                         ├─ GenAI (Groq): work orders, translation, copilot, reports
                                         │    └─ numeric validator
                                         └─ Notifier: Meta WhatsApp Cloud API | Twilio | in-app
```

- **Data:** sensor data is **simulated**, calibrated to real tariffs, the CEA grid emission factor and real fixture wattages (see `backend/app/config.py`). CV inference is real. To use real sensors, write a new `DataSource` class; the engine doesn't change.
- **Privacy:** frames are processed in memory, head regions are blurred, and only counts are kept.
- **Runs on CPU:** no GPU needed.

## Run locally

```bash
# backend
cd backend
python -m venv .venv && .venv/Scripts/activate      # (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env                                  # add GROQ_API_KEY (free at console.groq.com)
python scripts/gen_campus.py                          # regenerate the mock campus (optional)
uvicorn app.main:app --port 8002

# frontend (new terminal)
cd frontend
npm install
npm run dev                                           # http://localhost:5173
```

Press **Ctrl+D** in the app for demo controls: inject scenarios, change speed, jump in time.

## Tests

```bash
cd backend && python -m pytest -q
```

## Deploy (single service)

`Dockerfile` builds the frontend and serves it from FastAPI on port 7860 (Hugging Face Spaces Docker, Render, Railway). Set the `.env` values as the platform's secrets. Then set `PUBLIC_BASE_URL` and `FRONTEND_URL` to the deployed URL, and the Meta webhook to `https://<app>/api/wa/webhook`.

## Team

| Role | Member |
|---|---|
| CV lead | _name_ |
| Backend / twin lead | _name_ |
| Frontend lead | _name_ |
| GenAI + pitch lead | _name_ |
