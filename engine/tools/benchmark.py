"""
Measure detector speed on a video, so you can compare .pt / ONNX / TensorRT on your own GPU.

    python -m engine.tools.benchmark --weights yolo11x.pt --backend ultralytics --video demo.mp4
    python -m engine.tools.benchmark --weights yolo11x.onnx --backend onnx --video demo.mp4

Reports mean latency, 95th percentile and frames per second (the first frames are warm-up and skipped).
"""

from __future__ import annotations

import argparse
import statistics
import time


def summarize(latencies_ms: list[float]) -> dict:
    ordered = sorted(latencies_ms)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    mean = statistics.fmean(ordered)
    return {"frames": len(ordered), "mean_ms": mean, "p95_ms": p95, "fps": 1000.0 / mean if mean else 0.0}


def main(argv=None) -> int:
    import cv2

    from engine.core.config import DetectorConfig, DeviceConfig
    from engine.perception.detector import build_detector

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--weights", required=True)
    parser.add_argument("--backend", choices=["ultralytics", "onnx", "tensorrt"], default="ultralytics")
    parser.add_argument("--video", required=True)
    parser.add_argument("--frames", type=int, default=200)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--gpu", default="0")
    parser.add_argument("--half", action="store_true")
    args = parser.parse_args(argv)

    detector = build_detector(
        "bench",
        DetectorConfig(weights=args.weights, backend=args.backend, imgsz=args.imgsz),
        DeviceConfig(gpu=args.gpu, half=args.half),
    )
    capture = cv2.VideoCapture(args.video)
    latencies, seen = [], 0
    while seen < args.frames + args.warmup:
        ok, frame = capture.read()
        if not ok:
            capture.set(cv2.CAP_PROP_POS_FRAMES, 0)  # loop short videos
            ok, frame = capture.read()
            if not ok:
                break
        start = time.perf_counter()
        detector.detect([frame])
        elapsed = (time.perf_counter() - start) * 1000
        if seen >= args.warmup:
            latencies.append(elapsed)
        seen += 1
    capture.release()
    if not latencies:
        print("no frames could be read")
        return 1
    result = summarize(latencies)
    print(
        f"{args.backend}: {result['frames']} frames · mean {result['mean_ms']:.1f} ms · "
        f"p95 {result['p95_ms']:.1f} ms · {result['fps']:.1f} FPS"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
