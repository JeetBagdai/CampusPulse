# Bin fill-level model (YOLO11n)

The app runs without this model: bin state comes from the fill sensors, and photo reports are checked by the vision LLM. Training it adds a real CV metric (mAP and a confusion matrix) for the pitch, and lets the live camera classify bins.

## Train it on Google Colab (free T4 GPU, about 20–40 min)

1. Open [colab.research.google.com](https://colab.research.google.com) → **Upload** → `bin_model.ipynb`.
2. **Runtime → Change runtime type → T4 GPU**.
3. Pick a dataset on [Roboflow Universe](https://universe.roboflow.com). Search for *"garbage bin full empty"* or *"overflowing garbage bin"*, and choose one with classes like `empty` / `full` / `overflow`.
   Click **Download dataset → YOLOv8 format → "show download code"**, then paste your workspace, project and version into the notebook. Your Roboflow API key goes into a Colab secret, not into the notebook.
4. Run all cells. When it finishes, download `bin.pt` and copy it to `backend/models/bin.pt`.
5. Save `results.png` and `confusion_matrix.png` from the run folder for the PPT's CV slide.

The backend picks up `models/bin.pt` automatically on its next start. Class names containing `over`, `full` or `empty` are mapped to overflow / full / empty.
