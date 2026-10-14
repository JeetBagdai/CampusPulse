"""Computer-vision detectors. All run on CPU.

- people: YOLO11n (COCO 'person') on ONNX Runtime or PyTorch, OpenCV HOG fallback
- lights: frame brightness vs. per-camera calibration (no training needed)
- fan / tap: frame-difference motion energy inside a region of interest
- bins: fine-tuned YOLO model at models/bin.onnx or bin.pt (see training/)
- privacy: faces + head regions blurred before anything is shown or stored
"""
import base64
import os
import threading
from collections import deque

import cv2
import numpy as np

from ..config import MODELS_DIR

_lock = threading.Lock()
_person = None
_bin = None
_bin_checked = False
_hog = None
# Haar cascades were removed in OpenCV 5; head-region blur from person boxes still applies.
_face = (cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
         if hasattr(cv2, "CascadeClassifier") else None)

DEFAULT_ROIS = {"fan": [0.30, 0.0, 0.40, 0.35], "tap": [0.30, 0.35, 0.40, 0.40]}


# CV_BACKEND: auto (ONNX if the .onnx files exist, else PyTorch) | onnx | torch
CV_BACKEND = os.getenv("CV_BACKEND", "auto").lower()


def _onnx(name: str):
    path = MODELS_DIR / name
    if CV_BACKEND == "torch" or not path.exists():
        return None
    try:
        from .onnx_yolo import OnnxYolo
        return OnnxYolo(path)
    except ImportError:
        return None


def _person_model():
    """('onnx', model) or ('torch', model)."""
    global _person
    if _person is None:
        m = _onnx("people.onnx")
        if m is not None:
            _person = ("onnx", m)
        else:
            from ultralytics import YOLO
            MODELS_DIR.mkdir(exist_ok=True)
            _person = ("torch", YOLO(str(MODELS_DIR / "yolo11n.pt")))
    return _person


def bin_model():
    global _bin, _bin_checked
    if not _bin_checked:
        _bin_checked = True
        m = _onnx("bin.onnx")
        if m is not None:
            _bin = ("onnx", m)
        elif (MODELS_DIR / "bin.pt").exists() and CV_BACKEND != "onnx":
            from ultralytics import YOLO
            _bin = ("torch", YOLO(str(MODELS_DIR / "bin.pt")))
    return _bin


def cv_backend() -> str:
    return _person_model()[0]


def detect_people(img: np.ndarray) -> list[list[float]]:
    """[[x1, y1, x2, y2, conf], ...] in pixels."""
    try:
        kind, model = _person_model()
        with _lock:
            if kind == "onnx":
                return [[x1, y1, x2, y2, c] for x1, y1, x2, y2, c, _ in model(img, conf=0.4, classes=[0])]
            res = model(img, classes=[0], conf=0.4, imgsz=480, verbose=False)[0]
        return [[*map(float, b.xyxy[0].tolist()), float(b.conf[0])] for b in res.boxes]
    except Exception:  # noqa: BLE001 - fall back to HOG if no detector is available
        global _hog
        if _hog is None:
            _hog = cv2.HOGDescriptor()
            _hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        rects, weights = _hog.detectMultiScale(img, winStride=(8, 8))
        return [[x, y, x + w, y + h, float(wt)] for (x, y, w, h), wt in zip(rects, np.ravel(weights)) if wt > 0.5]


def detect_bin(img: np.ndarray) -> tuple[str | None, float]:
    """('empty'|'half'|'full'|'overflow', conf) from the trained bin model, or (None, 0) if no model."""
    loaded = bin_model()
    if loaded is None:
        return None, 0.0
    kind, model = loaded
    best, conf = None, 0.0
    with _lock:
        if kind == "onnx":
            for *_, c, k in model(img, conf=0.35):
                if c > conf:
                    best, conf = model.names[k].lower(), c
        else:
            res = model(img, conf=0.35, verbose=False)[0]
            for b in res.boxes:
                n, c = res.names[int(b.cls[0])].lower(), float(b.conf[0])
                if c > conf:
                    best, conf = n, c
    if best is None:
        return None, 0.0
    for key, label in (("over", "overflow"), ("full", "full"), ("empty", "empty"), ("half", "half")):
        if key in best:
            return label, conf
    return best, conf


def blur_faces(img: np.ndarray, persons: list[list[float]]) -> np.ndarray:
    out = img.copy()
    h, w = out.shape[:2]
    regions = []
    if _face is not None:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        for (x, y, fw, fh) in _face.detectMultiScale(gray, 1.2, 5, minSize=(30, 30)):
            regions.append((x, y, x + fw, y + fh))
    for x1, y1, x2, y2, _ in persons:  # head region = top ~22% of each person box
        regions.append((int(x1), int(y1), int(x2), int(y1 + (y2 - y1) * 0.22)))
    for x1, y1, x2, y2 in regions:
        x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
        if x2 - x1 > 4 and y2 - y1 > 4:
            out[y1:y2, x1:x2] = cv2.GaussianBlur(out[y1:y2, x1:x2], (0, 0), 15)
    return out


def _roi(img_shape, roi):
    h, w = img_shape[:2]
    x, y, rw, rh = roi
    return int(x * w), int(y * h), int((x + rw) * w), int((y + rh) * h)


class CameraState:
    """Per-camera memory: previous frame for motion, calibration for lights, ROIs."""

    def __init__(self):
        self.prev = None
        self.prev_bright = None
        self.motion = {"fan": deque(maxlen=3), "tap": deque(maxlen=3)}
        self.calib: dict[str, float] = {}
        self.rois = dict(DEFAULT_ROIS)
        self.light_on = None

    def light_threshold(self) -> float:
        if "on" in self.calib and "off" in self.calib:
            return (self.calib["on"] + self.calib["off"]) / 2
        return 90.0


def brightness(img: np.ndarray, persons) -> float:
    v = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[:, :, 2].astype(np.float32)
    mask = np.ones(v.shape, bool)
    for x1, y1, x2, y2, _ in persons:
        mask[int(y1):int(y2), int(x1):int(x2)] = False
    return float(v[mask].mean()) if mask.any() else float(v.mean())


def analyse(state: CameraState, jpeg: bytes, want_bin: bool = False) -> dict:
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("could not decode image")
    if img.shape[1] > 640:
        img = cv2.resize(img, (640, int(img.shape[0] * 640 / img.shape[1])))
    persons = detect_people(img)
    bright = brightness(img, persons)
    thr = state.light_threshold()
    if state.light_on is None:
        state.light_on = bright > thr
    elif state.light_on and bright < thr - 4:  # hysteresis
        state.light_on = False
    elif not state.light_on and bright > thr + 4:
        state.light_on = True

    gray = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    motion = {}
    # a big global brightness jump (light switched) is not fan/tap motion: skip that frame pair
    lighting_changed = state.prev_bright is not None and abs(bright - state.prev_bright) > 12
    state.prev_bright = bright
    if lighting_changed:
        motion = {name: (round(sum(h) / len(h), 2) if h else 0.0) for name, h in state.motion.items()}
    elif state.prev is not None and state.prev.shape == gray.shape:
        diff = cv2.absdiff(gray, state.prev)
        for x1, y1, x2, y2, _ in persons:
            diff[int(y1):int(y2), int(x1):int(x2)] = 0
        for name, roi in state.rois.items():
            a, b, c, d = _roi(img.shape, roi)
            score = float(diff[b:d, a:c].mean()) if d > b and c > a else 0.0
            state.motion[name].append(score)
            motion[name] = round(sum(state.motion[name]) / len(state.motion[name]), 2)
    state.prev = gray

    bin_state, bin_conf = detect_bin(img) if want_bin else (None, 0.0)

    shown = blur_faces(img, persons)
    for x1, y1, x2, y2, conf in persons:
        cv2.rectangle(shown, (int(x1), int(y1)), (int(x2), int(y2)), (80, 220, 120), 2)
        cv2.putText(shown, f"person {conf:.2f}", (int(x1), max(12, int(y1) - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (80, 220, 120), 1)
    for name, roi in state.rois.items():
        a, b, c, d = _roi(img.shape, roi)
        cv2.rectangle(shown, (a, b), (c, d), (255, 180, 60), 1)
        cv2.putText(shown, f"{name} roi", (a + 3, b + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 180, 60), 1)
    ok, buf = cv2.imencode(".jpg", shown, [cv2.IMWRITE_JPEG_QUALITY, 70])

    return {
        "people": len(persons), "boxes": [[round(v, 1) for v in p] for p in persons],
        "brightness": round(bright, 1), "light_threshold": round(thr, 1), "lights_on": bool(state.light_on),
        "fan_motion": motion.get("fan"), "fans_on": (motion.get("fan", 0) > 6.0) if "fan" in motion else None,
        "tap_motion": motion.get("tap"), "tap_on": (motion.get("tap", 0) > 5.0) if "tap" in motion else None,
        "bin_state": bin_state, "bin_conf": round(bin_conf, 2),
        "annotated": "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode() if ok else None,
        "size": [img.shape[1], img.shape[0]],
    }
