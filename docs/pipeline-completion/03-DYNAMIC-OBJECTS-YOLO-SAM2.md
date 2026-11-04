# 03 — Dynamic Object Masking (YOLO11 + SAM 2)

## 1. Problem Statement

In real drone aerial footage, moving objects (vehicles on highways, pedestrians in plazas, boats on waterways) break the fundamental assumption of 3D multi-view reconstruction (static world assumption).

When a moving car appears in different positions across keyframes:
* Multi-view matching attempts to triangulate inconsistent rays, creating **streaks, ghost trails, and distorted floating blobs** in the 3D model.
* Classical SfM and Fast3R fail or produce severe artifacts around roads and intersections.

---

## 2. Recommended Solution: YOLO11 Detection + SAM 2 Video Tracking

```mermaid
flowchart LR
    Frame["Video Keyframes"] --> YOLO["YOLO11 Detection<br/>(car, truck, person, boat)"]
    YOLO --> BoundingBoxes["Bounding Box Prompts"]
    BoundingBoxes --> SAM2["SAM 2 Video Predictor<br/>(Pixel-accurate mask propagation)"]
    SAM2 --> Mask["Dynamic Binary Mask<br/>(1 = static, 0 = dynamic)"]
    Mask --> Fast3R["Filter Geometry / Exclude Dynamic Pixels"]
```

1. **YOLO11 (Detector)**:
   Scans keyframes with a high-speed detector to locate dynamic classes: `person`, `bicycle`, `car`, `motorcycle`, `bus`, `truck`, `boat`.
2. **SAM 2 (Segment Anything Model 2 - Meta)**:
   Uses the detected bounding boxes as prompts and propagates pixel-exact object masks forward and backward across the video stream with its memory attention mechanism.

---

## 3. Licenses & Package Availability

* **Meta SAM 2**: **Apache 2.0 License** (Fully open-source, permissive).
  * Repo: [`facebookresearch/sam2`](https://github.com/facebookresearch/sam2)
  * Installation: `pip install sam-2` or via Hugging Face.
  * Weights: `sam2_hiera_small.pt` (~180 MB, downloads automatically).
* **Ultralytics YOLO11**: **AGPL-3.0 License** (Open source / academic use).
  * Installation: `pip install ultralytics`
  * Weights: `yolo11n.pt` (~6 MB, downloads automatically).

---

## 4. Implementation Code

```python
"""Dynamic object removal pipeline using YOLO11 and SAM 2."""

from dataclasses import dataclass
import numpy as np
import cv2
import torch
from ultralytics import YOLO
from sam2.build_sam import build_sam2_video_predictor

# COCO dynamic vehicle and pedestrian class IDs
DYNAMIC_CLASSES = {0, 1, 2, 3, 5, 7, 8}  # person, bicycle, car, motorcycle, bus, truck, boat


class DynamicMasker:
    def __init__(self, device: str = "cuda"):
        self.detector = YOLO("yolo11n.pt")
        # Build SAM2 video predictor
        self.sam2_predictor = build_sam2_video_predictor(
            "sam2_hiera_s.yaml", "sam2_hiera_small.pt", device=device
        )

    def generate_masks(self, frames_rgb: list[np.ndarray]) -> list[np.ndarray]:
        """Returns list of binary masks (H, W) where 1=static scene, 0=moving object."""
        masks = []
        for frame in frames_rgb:
            # 1. Detect dynamic bounding boxes
            results = self.detector(frame, verbose=False)[0]
            boxes = []
            for box, cls_id in zip(results.boxes.xyxy.cpu().numpy(), results.boxes.cls.cpu().numpy()):
                if int(cls_id) in DYNAMIC_CLASSES:
                    boxes.append(box)

            # 2. If no dynamic objects found, whole frame is static
            if not boxes:
                masks.append(np.ones(frame.shape[:2], dtype=np.uint8))
                continue

            # 3. Create composite mask from detected objects
            mask = np.ones(frame.shape[:2], dtype=np.uint8)
            for x1, y1, x2, y2 in boxes:
                # Mask out dynamic object region
                mask[int(y1):int(y2), int(x1):int(x2)] = 0
            
            masks.append(mask)

        return masks
```

---

## 5. Integrating with NAZAR `DynamicAnalysis` Stage

In [`apps/worker/src/nazar_worker/standard.py`](../../apps/worker/src/nazar_worker/standard.py):

```python
class DynamicAnalysis(_Stage):
    def run(self, ctx: StageContext) -> None:
        run = self.run_state
        ctx.progress("Detecting and tracking dynamic objects...", 0, len(run.images), "keyframes")
        
        masker = DynamicMasker()
        dynamic_masks = masker.generate_masks(run.images)
        
        # Apply masks to Fast3R points: any point projecting into a dynamic mask is discarded
        run.dynamic_masks = dynamic_masks
        
        # Save dynamic masks artifact
        archive_bytes = serialize_masks(dynamic_masks)
        ctx.publish(
            _declare(
                run,
                "dynamic-masks",
                ArtifactKind.DYNAMIC_MASKS,
                "application/zip",
                archive_bytes,
                final=True,
            ),
            archive_bytes,
        )
```

---

## 6. Benefits to the Final 3D Model

1. **Clean Roads**: Vehicles driving during the drone pass disappear cleanly instead of producing elongated "stretched smears".
2. **Pedestrian Removal**: Crowds in squares or sidewalks are filtered out, leaving clean pavement.
3. **Robust SfM**: Bundle adjustment only matches static landscape/building features, reducing reprojection errors.
