# tools/

Command-line helpers for models. Run them from the project root.

| Command | Job |
|---------|-----|
| `python -m engine.tools.export_models` | Export a `.pt` model to ONNX or TensorRT |
| `python -m engine.tools.check_parity` | Check that an export finds the same objects as the original |
| `python -m engine.tools.benchmark` | Measure detector speed on a video |
| `python -m engine.tools.download_models` | Download the general models (person detector, appearance model) |
