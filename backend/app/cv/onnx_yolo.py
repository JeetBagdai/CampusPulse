"""Minimal YOLO (v8/11 head) runner on ONNX Runtime: no PyTorch needed.

Same trained weights as the .pt models, exported with Ultralytics
(`yolo export format=onnx`). Handles letterboxing, box decoding and NMS.
"""
import ast
import os
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort


class OnnxYolo:
    def __init__(self, path: Path):
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = int(os.getenv("ORT_THREADS", "2"))
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])
        inp = self.session.get_inputs()[0]
        self.input_name, self.size = inp.name, int(inp.shape[2])
        meta = self.session.get_modelmeta().custom_metadata_map
        self.names = {int(k): v for k, v in ast.literal_eval(meta.get("names", "{}")).items()}

    def __call__(self, img: np.ndarray, conf: float = 0.4, iou: float = 0.5, classes=None) -> list[tuple]:
        """Returns [(x1, y1, x2, y2, confidence, class_id), ...] in original image pixels."""
        h, w = img.shape[:2]
        s = self.size
        r = min(s / h, s / w)
        nh, nw = round(h * r), round(w * r)
        top, left = (s - nh) // 2, (s - nw) // 2
        canvas = np.full((s, s, 3), 114, np.uint8)
        canvas[top:top + nh, left:left + nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
        x = np.ascontiguousarray(canvas[:, :, ::-1].transpose(2, 0, 1)[None], dtype=np.float32) / 255.0

        out = self.session.run(None, {self.input_name: x})[0][0].T  # (N, 4 + classes)
        scores = out[:, 4:]
        cls = scores.argmax(1)
        best = scores[np.arange(len(cls)), cls]
        keep = best >= conf
        if classes is not None:
            keep &= np.isin(cls, classes)
        boxes, cls, best = out[keep, :4], cls[keep], best[keep]
        if not len(best):
            return []
        # centre-xywh in letterbox space -> corner-xyxy in original image
        x1 = (boxes[:, 0] - boxes[:, 2] / 2 - left) / r
        y1 = (boxes[:, 1] - boxes[:, 3] / 2 - top) / r
        bw, bh = boxes[:, 2] / r, boxes[:, 3] / r
        idx = cv2.dnn.NMSBoxes(np.stack([x1, y1, bw, bh], 1).tolist(), best.tolist(), conf, iou)
        result = []
        for i in np.array(idx).flatten():
            result.append((float(max(0, x1[i])), float(max(0, y1[i])), float(min(w, x1[i] + bw[i])),
                           float(min(h, y1[i] + bh[i])), float(best[i]), int(cls[i])))
        return result
