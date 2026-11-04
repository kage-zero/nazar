"""Compute profiles: the two supported ways to run the full pipeline.

- `local`: the RTX 4050 Laptop (6 GB). Every GPU runner caps its own PyTorch memory to
  `vram_budget_mib`; slow is acceptable, exceeding the budget is not. A step that cannot fit
  even at its smallest setting is skipped with a reason (only ever on this profile).
- `clg`: the college VDI GPU (30+ GB). Larger models, full resolution, fewer passes.

Every size knob a stage uses lives here, so stages never hard-code per-machine values, and
the processing report records which profile ran.
"""

from dataclasses import asdict, dataclass
from typing import Any

from nazar_contracts import ComputeTarget


@dataclass(frozen=True)
class ComputeProfile:
    name: str
    strict: bool
    """True: every model must run (a failure fails the job). False (local GPU only): a step
    that needs more memory than the budget is skipped with a visible reason."""
    vram_budget_mib: int
    """Upper bound on what one GPU runner may allocate (0 = no cap)."""

    fast3r_max_views: int
    """Views per Fast3R pass (0 = size from free VRAM within the budget)."""

    yolo_weights: str
    yolo_imgsz: int
    sam2_checkpoint: str
    sam2_config: str

    metric3d_models: tuple[str, ...]
    """Metric3D-v2 variants to try, largest first; the first that fits the budget is used."""

    poisson_depth: int
    max_fused_points: int

    splat_iterations: int
    splat_max_gaussians: int
    splat_sh_degree: int

    def report(self) -> dict[str, Any]:
        return asdict(self)


LOCAL = ComputeProfile(
    name="local",
    strict=False,
    vram_budget_mib=5632,  # 5.5 GiB of the 6 GiB card: the rest is the CUDA context + desktop
    fast3r_max_views=0,
    yolo_weights="yolo11s.pt",
    yolo_imgsz=960,
    sam2_checkpoint="sam2.1_hiera_small.pt",
    sam2_config="configs/sam2.1/sam2.1_hiera_s.yaml",
    metric3d_models=("vit_large", "vit_small"),
    poisson_depth=9,
    max_fused_points=600_000,
    splat_iterations=4000,
    splat_max_gaussians=400_000,
    splat_sh_degree=1,
)

CLG = ComputeProfile(
    name="clg",
    strict=True,
    vram_budget_mib=0,
    fast3r_max_views=48,
    yolo_weights="yolo11x.pt",
    yolo_imgsz=1280,
    sam2_checkpoint="sam2.1_hiera_large.pt",
    sam2_config="configs/sam2.1/sam2.1_hiera_l.yaml",
    metric3d_models=("vit_giant2", "vit_large"),
    poisson_depth=10,
    max_fused_points=2_000_000,
    splat_iterations=15000,
    splat_max_gaussians=2_000_000,
    splat_sh_degree=3,
)

PROFILES = {LOCAL.name: LOCAL, CLG.name: CLG}


def for_location(location: ComputeTarget) -> ComputeProfile:
    """The worker's location decides its profile: the college worker runs `clg`."""
    return CLG if location is ComputeTarget.COLLEGE else LOCAL
