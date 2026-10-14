"""
Export a YOLO .pt model to ONNX and/or TensorRT so the engine can use a faster backend.

    python -m engine.tools.export_models --weights yolo11x.pt --format onnx --imgsz 640
    python -m engine.tools.export_models --weights ppe.pt --format engine --half

Then point the config at the new file and change `backend:` to `onnx` or `tensorrt`.
Run `engine.tools.check_parity` afterwards to make sure the export still detects the same things.
TensorRT engines are tied to the GPU and TensorRT version they were built on: export on the target machine.
"""

from __future__ import annotations

import argparse
from pathlib import Path

FORMATS = {"onnx": "onnx", "engine": "engine"}


def export(weights: str, fmt: str, imgsz: int, half: bool, simplify: bool, device: str) -> Path:
    from ultralytics import YOLO

    model = YOLO(weights)
    result = model.export(format=FORMATS[fmt], imgsz=imgsz, half=half, simplify=simplify, device=device, dynamic=False)
    return Path(result)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--weights", required=True, help="path to the .pt model")
    parser.add_argument("--format", choices=sorted(FORMATS), default="onnx")
    parser.add_argument("--imgsz", type=int, default=640, help="fixed input size (use the size you run with)")
    parser.add_argument("--half", action="store_true", help="FP16 (smaller and faster on most GPUs)")
    parser.add_argument("--no-simplify", action="store_true", help="skip onnx-simplifier")
    parser.add_argument("--device", default="0", help="GPU index, or 'cpu' (TensorRT needs a GPU)")
    args = parser.parse_args(argv)

    if not Path(args.weights).exists():
        parser.error(f"weights not found: {args.weights}")
    if args.format == "engine" and args.device == "cpu":
        parser.error("TensorRT export needs a GPU")
    out = export(args.weights, args.format, args.imgsz, args.half, not args.no_simplify, args.device)
    print(f"exported: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
