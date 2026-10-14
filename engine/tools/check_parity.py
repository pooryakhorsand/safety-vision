"""
Check that an exported model finds the same objects as the original .pt model.

    python -m engine.tools.check_parity --reference yolo11x.pt --candidate yolo11x.onnx \
        --backend onnx --video demo.mp4 --frames 100

For every sampled frame the boxes of both models are matched by IoU. The report shows how many
detections match, and the mean confidence difference. Exit code is 1 when the match rate is below --min-match.
"""

from __future__ import annotations

import argparse

from engine.core.config import DetectorConfig, DeviceConfig
from engine.core.frame import Detection
from engine.perception.tracker import iou


def compare(
    reference: list[Detection], candidate: list[Detection], iou_min: float = 0.5
) -> tuple[int, int, list[float]]:
    """Greedy one-to-one match by class and IoU. Returns (matched, reference_total, confidence_differences)."""
    unused = list(candidate)
    matched, diffs = 0, []
    for ref in sorted(reference, key=lambda d: -d.confidence):
        best, best_iou = None, iou_min
        for cand in unused:
            if cand.class_name != ref.class_name:
                continue
            value = iou(ref.box, cand.box)
            if value >= best_iou:
                best, best_iou = cand, value
        if best is not None:
            unused.remove(best)
            matched += 1
            diffs.append(abs(ref.confidence - best.confidence))
    return matched, len(reference), diffs


def sample_frames(video: str, count: int):
    import cv2

    capture = cv2.VideoCapture(video)
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) or count
    step = max(1, total // count)
    for index in range(0, total, step):
        capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = capture.read()
        if ok:
            yield frame
    capture.release()


def main(argv=None) -> int:
    from engine.perception.detector import build_detector

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reference", required=True, help="original .pt model")
    parser.add_argument("--candidate", required=True, help="exported model (.onnx / .engine)")
    parser.add_argument("--backend", choices=["onnx", "tensorrt"], required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--frames", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.30)
    parser.add_argument("--gpu", default="0")
    parser.add_argument("--min-match", type=float, default=0.95, help="required share of matched detections")
    args = parser.parse_args(argv)

    device = DeviceConfig(gpu=args.gpu)
    settings = dict(imgsz=args.imgsz, conf=args.conf)
    reference = build_detector(
        "reference", DetectorConfig(weights=args.reference, backend="ultralytics", **settings), device
    )
    candidate = build_detector(
        "candidate", DetectorConfig(weights=args.candidate, backend=args.backend, **settings), device
    )

    matched = total = extra = 0
    diffs: list[float] = []
    for frame in sample_frames(args.video, args.frames):
        ref, cand = reference.detect([frame])[0], candidate.detect([frame])[0]
        m, t, d = compare(ref, cand)
        matched, total, extra = matched + m, total + t, extra + max(0, len(cand) - m)
        diffs += d

    rate = matched / total if total else 1.0
    mean_diff = sum(diffs) / len(diffs) if diffs else 0.0
    print(f"reference detections : {total}")
    print(f"matched by candidate : {matched} ({rate:.1%})")
    print(f"extra in candidate   : {extra}")
    print(f"mean confidence diff : {mean_diff:.3f}")
    ok = rate >= args.min_match
    print("PASS" if ok else "FAIL: the export does not reproduce the original model well enough")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
