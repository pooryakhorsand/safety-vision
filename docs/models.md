# Models

The repository and the installers contain **no model weights**. There are two kinds of model.

## 1. General models: download them

| Model | Used for | Where it goes |
|-------|----------|---------------|
| Person detector (YOLO11, COCO, class `person`) | Finds people | `detectors.person.weights` |
| Appearance model (OSNet) | Tracking and merging repeat violations | `tracker.reid_weights` and `reid.weights` |

One command downloads both to the paths set in `engine.yaml` (existing files are kept):

```
python -m engine.tools.download_models
python -m engine.tools.download_models --person yolo11m.pt     # a smaller person model
```

Installed app (Windows), from the program folder:

```
runtime\engine\python.exe -m engine.tools.download_models
```

Use a smaller person model (`yolo11m.pt`, `yolo11s.pt`) on weaker GPUs. Check the licence of the models you download: Ultralytics models are AGPL-3.0.

## 2. The PPE model: train your own

Detecting helmets, vests and safety shoes depends on your cameras, your equipment and your site, so this project does not ship a PPE model. Train one with your own images (for example with Ultralytics YOLO) and save the result as `ppe.pt`:

- Installed app: `<data folder>\models\ppe.pt`
- From source: `engine/modules/ppe/weights/ppe.pt`, or any path set in `detectors.equipment.weights`.

**Class names.** The module matches class names by substring (case-insensitive):

| Item | Class names it understands | Event when missing |
|------|----------------------------|--------------------|
| Helmet | `helmet`, `hat` | `no_helmet` |
| Vest | `vest` | `no_vest` |
| Safety shoes | `shoe`, `boot` | `no_safety_shoes` |

A class that starts with `no_` (for example `no_helmet`) means the item is **missing** and counts as a violation. A class without the prefix means the item is **present**. The model must be trained with the explicit `no_` classes: a person for whom nothing is detected is "not seen", not "missing", so a model with only the "present" classes raises no violations. If your model uses other names, edit `modules.ppe.items`, `zones` and `item_colors` in `engine.yaml`.

Tips: include people from all your camera angles and lighting, include both "wearing" and "not wearing" examples, and measure on video that was not used for training before you trust the numbers.

Until `ppe.pt` exists the status bar shows the engine in **error** state and names the missing file.
