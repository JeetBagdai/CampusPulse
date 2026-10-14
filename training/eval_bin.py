"""Image-level evaluation that matches how CampusPulse uses the model: the single most
confident detection per photo decides the bin state. Writes a clean confusion matrix
for the CV slide (bin_confusion_matrix.png) and adds image-level accuracy to bin_metrics.json.

Run from training/:  .venv/Scripts/python eval_bin.py
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from ultralytics import YOLO  # noqa: E402

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "garbage_fill_level"
CLASSES = ["Empty", "Half", "Overflow"]


def main():
    model = YOLO(str(HERE.parent / "backend" / "models" / "bin.pt"))
    matrix = [[0] * 4 for _ in range(3)]  # rows = true, cols = predicted (+ "none")
    for split in ("valid", "test"):
        for img in sorted((DATA / split / "images").glob("*.jpg")):
            lines = (DATA / split / "labels" / (img.stem + ".txt")).read_text().split("\n")
            boxes = [l.split() for l in lines if l.strip()]
            # true label = class of the largest box in the photo
            truth = int(max(boxes, key=lambda b: float(b[3]) * float(b[4]))[0])
            res = model(str(img), conf=0.35, verbose=False)[0]
            pred = int(res.boxes.cls[res.boxes.conf.argmax()]) if len(res.boxes) else 3
            matrix[truth][pred] += 1

    total = sum(map(sum, matrix))
    correct = sum(matrix[i][i] for i in range(3))
    acc = correct / total
    overflow_recall = matrix[2][2] / max(sum(matrix[2]), 1)

    fig, ax = plt.subplots(figsize=(6.2, 5.2), dpi=160)
    cols = CLASSES + ["None"]
    ax.imshow([[v / max(sum(r), 1) for v in r] for r in matrix], cmap="Greens", vmin=0, vmax=1)
    for i in range(3):
        for j in range(4):
            v = matrix[i][j]
            ax.text(j, i, str(v), ha="center", va="center", fontsize=14,
                    color="white" if v / max(sum(matrix[i]), 1) > 0.55 else "#1f2937")
    ax.set_xticks(range(4), cols)
    ax.set_yticks(range(3), CLASSES)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title(f"Bin fill level: {correct}/{total} photos correct ({acc:.0%})", fontsize=12)
    fig.tight_layout()
    fig.savefig(HERE / "bin_confusion_matrix.png")

    mfile = HERE / "bin_metrics.json"
    metrics = json.loads(mfile.read_text(encoding="utf-8"))
    metrics["image_level"] = {"accuracy": round(acc, 3), "correct": correct, "total": total,
                              "overflow_recall": round(overflow_recall, 3), "matrix_rows_true_cols_pred": matrix,
                              "columns": cols}
    mfile.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics["image_level"], indent=2))


if __name__ == "__main__":
    main()
