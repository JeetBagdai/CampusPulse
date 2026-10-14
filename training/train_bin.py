"""Fine-tunes YOLO11n on the Garbage_Fill_Level dataset (Empty / Half / Overflow) and
installs the best weights as backend/models/bin.pt.

Dataset: "Garbage_Fill_Level" by charuka-edirisinghe, Roboflow Universe, CC BY 4.0.
Run from training/:  .venv/Scripts/python train_bin.py
"""
import json
import shutil
from pathlib import Path

from ultralytics import YOLO

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "garbage_fill_level"
RUNS = HERE / "runs"
OUT = HERE.parent / "backend" / "models" / "bin.pt"


def main():
    # Evaluate on valid + test together: both are tiny on their own.
    cfg = HERE / "data" / "bin_data.yaml"
    cfg.write_text(
        f"path: {DATA.as_posix()}\n"
        "train: train/images\n"
        "val: [valid/images, test/images]\n"
        "names: ['Empty', 'Half', 'Overflow']\n",
        encoding="utf-8",
    )

    model = YOLO("yolo11n.pt")
    model.train(data=str(cfg), epochs=80, imgsz=640, batch=16, patience=25, cos_lr=True,
                device=0, workers=4, project=str(RUNS), name="bin", exist_ok=True, plots=True, verbose=False)

    best = YOLO(str(RUNS / "bin" / "weights" / "best.pt"))
    m = best.val(data=str(cfg), split="val", device=0, plots=True, project=str(RUNS), name="bin_eval", exist_ok=True)
    names = best.names
    per_class = {names[int(c)]: {"precision": round(float(m.box.p[i]), 3), "recall": round(float(m.box.r[i]), 3),
                                 "mAP50": round(float(m.box.ap50[i]), 3)}
                 for i, c in enumerate(m.box.ap_class_index)}
    metrics = {"mAP50": round(float(m.box.map50), 3), "mAP50_95": round(float(m.box.map), 3),
               "precision": round(float(m.box.mp), 3), "recall": round(float(m.box.mr), 3), "per_class": per_class,
               "eval_images": "valid + test (40 images)", "dataset": "Garbage_Fill_Level v2 (Roboflow Universe, CC BY 4.0)"}
    (HERE / "bin_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))

    OUT.parent.mkdir(exist_ok=True)
    shutil.copy(RUNS / "bin" / "weights" / "best.pt", OUT)
    for f in ("confusion_matrix.png", "confusion_matrix_normalized.png", "BoxPR_curve.png", "PR_curve.png"):
        src = RUNS / "bin_eval" / f
        if src.exists():
            shutil.copy(src, HERE / f)
    if (RUNS / "bin" / "results.png").exists():
        shutil.copy(RUNS / "bin" / "results.png", HERE / "training_curves.png")
    print(f"installed {OUT}")


if __name__ == "__main__":  # required on Windows: dataloader workers re-import this file
    main()
