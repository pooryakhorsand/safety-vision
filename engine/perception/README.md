# perception/

Tools shared by every module. They are not modules themselves.

| File | Job |
|------|-----|
| `detector.py` | The detector interface and the backend chooser |
| `backend_ultralytics.py` | YOLO `.pt` (PyTorch) and TensorRT `.engine` files through Ultralytics |
| `backend_onnx.py` | ONNX Runtime backend |
| `tracker.py` | BoT-SORT wrapper (and a small IoU tracker) that gives each person a track ID |
| `reid.py` | Appearance embeddings of person crops, used to merge repeat violations |
