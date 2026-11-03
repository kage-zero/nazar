"""Moving-object masks: YOLO detection + camera-motion-compensated motion check + SAM 2.

Runs INSIDE the main GPU environment (see `_common.py`). For every keyframe:

1. YOLO finds candidates of the classes that can move (person, bicycle, car, motorcycle, bus,
   truck, boat).
2. A detection is a *moving object* only with evidence: the neighbouring keyframes are
   registered to this one with a ground-plane homography (ORB + RANSAC, detections excluded),
   the box is projected into them, and the object must have left that spot (no same-class
   detection overlapping it and the image patch there no longer matches). Detection alone is
   not proof of motion, so parked vehicles are kept. Objects with no usable neighbour are
   "unknown" and are not masked.
3. SAM 2's image predictor turns each moving object's box into a pixel mask.

    python dynamic_runner.py --frames DIR --out DIR --yolo PATH --sam2-ckpt PATH
        --sam2-cfg NAME [--imgsz 960] [--conf 0.25] [--budget-mib 5632]

Writes `masks/NNNN.png` (255 = moving object), `overlays/NNNN.jpg` (debug view: red = masked
moving object, green = kept static object, grey = unknown) and `objects.json`.
"""

import argparse
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from _common import Timer, budget, emit, log, peak, run_main

COCO_MOVABLE = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
    8: "boat",
}
STATIC_IOU = 0.3
STATIC_NCC = 0.6
MASK_DILATE_PX = 5


def iou(a: np.ndarray, b: np.ndarray) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return float(inter / union) if union > 0 else 0.0


def homography(
    gray_a: np.ndarray, gray_b: np.ndarray, boxes: list[np.ndarray]
) -> np.ndarray | None:
    """Image a -> image b, fitted on the background (detections masked out)."""
    keep = np.full(gray_a.shape, 255, np.uint8)
    for x1, y1, x2, y2 in boxes:
        keep[int(y1) : int(y2) + 1, int(x1) : int(x2) + 1] = 0
    orb = cv2.ORB_create(3000)
    ka, da = orb.detectAndCompute(gray_a, keep)
    kb, db = orb.detectAndCompute(gray_b, None)
    if da is None or db is None or len(ka) < 30 or len(kb) < 30:
        return None
    matches = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(da, db)
    if len(matches) < 30:
        return None
    src = np.float32([ka[m.queryIdx].pt for m in matches])
    dst = np.float32([kb[m.trainIdx].pt for m in matches])
    h, inl = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
    if h is None or inl is None or int(inl.sum()) < 25:
        return None
    return h


def warp_box(h: np.ndarray, box: np.ndarray) -> np.ndarray:
    x1, y1, x2, y2 = box
    pts = np.float32([[x1, y1], [x2, y1], [x2, y2], [x1, y2]]).reshape(-1, 1, 2)
    out = cv2.perspectiveTransform(pts, h).reshape(-1, 2)
    return np.array([out[:, 0].min(), out[:, 1].min(), out[:, 0].max(), out[:, 1].max()])


def patch_ncc(img_a: np.ndarray, img_b: np.ndarray, h: np.ndarray, box: np.ndarray) -> float:
    """Does the place the object occupied in a still look the same in b (warped back)?"""
    hh, ww = img_a.shape[:2]
    back = cv2.warpPerspective(img_b, np.linalg.inv(h), (ww, hh))
    x1, y1 = max(0, int(box[0])), max(0, int(box[1]))
    x2, y2 = min(ww, int(box[2]) + 1), min(hh, int(box[3]) + 1)
    if x2 - x1 < 4 or y2 - y1 < 4:
        return 1.0
    a = img_a[y1:y2, x1:x2].astype(np.float32).ravel()
    b = back[y1:y2, x1:x2].astype(np.float32).ravel()
    a, b = a - a.mean(), b - b.mean()
    den = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(a @ b / den) if den > 1e-6 else 1.0


def classify(frames: list[np.ndarray], dets: list[list[dict[str, Any]]]) -> None:
    """Sets `state` on every detection: moving | static | unknown, with the evidence."""
    grays = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]
    for i, objects in enumerate(dets):
        if not objects:
            continue
        boxes = [np.array(o["box"]) for o in objects]
        for o in objects:
            o["state"], o["evidence"] = "unknown", []
        for j in (i - 1, i + 1):
            if not 0 <= j < len(frames):
                continue
            h = homography(grays[i], grays[j], boxes)
            if h is None:
                continue
            hh, ww = grays[j].shape
            for o, box in zip(objects, boxes, strict=True):
                if o["state"] == "static":
                    continue
                wb = warp_box(h, box)
                inside = wb[0] >= 0 and wb[1] >= 0 and wb[2] <= ww and wb[3] <= hh
                if not inside:
                    continue
                overlap = max(
                    (iou(wb, np.array(d["box"])) for d in dets[j] if d["cls"] == o["cls"]),
                    default=0.0,
                )
                ncc = patch_ncc(grays[i], grays[j], h, box)
                o["evidence"].append(
                    {"keyframe": j, "overlap": round(overlap, 3), "patch_ncc": round(ncc, 3)}
                )
                if overlap >= STATIC_IOU or ncc >= STATIC_NCC:
                    o["state"] = "static"
                else:
                    o["state"] = "moving"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--yolo", type=Path, required=True)
    ap.add_argument("--sam2-ckpt", type=Path, required=True)
    ap.add_argument("--sam2-cfg", required=True)
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--budget-mib", type=int, default=0)
    args = ap.parse_args()

    import torch

    timer = Timer()
    budget(args.budget_mib)
    files = sorted(args.frames.glob("*.jpg"))
    frames = [cv2.imread(str(f), cv2.IMREAD_COLOR) for f in files]
    (args.out / "masks").mkdir(parents=True, exist_ok=True)
    (args.out / "overlays").mkdir(parents=True, exist_ok=True)

    from ultralytics import YOLO

    detector = YOLO(str(args.yolo))
    dets: list[list[dict[str, Any]]] = []
    for i, frame in enumerate(frames):
        res = detector.predict(
            frame,
            imgsz=args.imgsz,
            conf=args.conf,
            classes=sorted(COCO_MOVABLE),
            device=0,
            half=True,
            verbose=False,
        )[0]
        boxes = res.boxes.xyxy.cpu().numpy()
        cls = res.boxes.cls.cpu().numpy().astype(int)
        conf = res.boxes.conf.cpu().numpy()
        dets.append(
            [
                {
                    "cls": COCO_MOVABLE[int(c)],
                    "conf": round(float(p), 3),
                    "box": [round(float(v), 1) for v in b],
                }
                for b, c, p in zip(boxes, cls, conf, strict=True)
            ]
        )
        emit(event="progress", step="detect", done=i + 1, total=len(frames))
    detect_s = timer.s()
    del detector
    torch.cuda.empty_cache()

    classify(frames, dets)
    moving_frames = [i for i, objs in enumerate(dets) if any(o["state"] == "moving" for o in objs)]

    from sam2.build_sam import build_sam2
    from sam2.sam2_image_predictor import SAM2ImagePredictor

    predictor = None
    if moving_frames:
        predictor = SAM2ImagePredictor(
            build_sam2(args.sam2_cfg, str(args.sam2_ckpt), device="cuda")
        )
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * MASK_DILATE_PX + 1,) * 2)
    masked_px = 0
    for i, (frame, objs) in enumerate(zip(frames, dets, strict=True)):
        mask = np.zeros(frame.shape[:2], np.uint8)
        moving = [o for o in objs if o["state"] == "moving"]
        if moving and predictor is not None:
            with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
                predictor.set_image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                masks, _, _ = predictor.predict(
                    box=np.array([o["box"] for o in moving], dtype=np.float32),
                    multimask_output=False,
                )
            masks = np.asarray(masks).reshape(len(moving), -1, *frame.shape[:2])[:, 0]
            for o, m in zip(moving, masks, strict=True):
                o["mask_px"] = int((m > 0.5).sum())
                mask |= (m > 0.5).astype(np.uint8) * 255
            mask = cv2.dilate(mask, kernel)
        masked_px += int((mask > 0).sum())
        cv2.imwrite(str(args.out / "masks" / f"{i:04d}.png"), mask)
        over = frame.copy()
        over[mask > 0] = (0.4 * over[mask > 0] + 0.6 * np.array([0, 0, 255])).astype(np.uint8)
        colours = {"moving": (0, 0, 255), "static": (0, 200, 0), "unknown": (160, 160, 160)}
        for o in objs:
            x1, y1, x2, y2 = (int(v) for v in o["box"])
            cv2.rectangle(over, (x1, y1), (x2, y2), colours[o["state"]], 1)
        cv2.imwrite(
            str(args.out / "overlays" / f"{i:04d}.jpg"), over, [cv2.IMWRITE_JPEG_QUALITY, 85]
        )
        emit(event="progress", step="segment", done=i + 1, total=len(frames))

    counts = {
        s: sum(o["state"] == s for objs in dets for o in objs)
        for s in ("moving", "static", "unknown")
    }
    total_px = sum(f.shape[0] * f.shape[1] for f in frames)
    (args.out / "objects.json").write_text(json.dumps({"frames": dets}, indent=1), encoding="utf-8")
    emit(
        event="done",
        detections=sum(len(d) for d in dets),
        objects=counts,
        frames_with_moving_objects=len(moving_frames),
        masked_pixel_share=round(masked_px / max(total_px, 1), 5),
        timings={"detect_s": detect_s, "total_s": timer.s()},
        **peak(),
    )
    log(f"dynamic masks: {counts}")
    return 0


if __name__ == "__main__":
    run_main(main)
