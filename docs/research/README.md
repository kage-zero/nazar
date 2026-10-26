# Research notes

Each item is marked **Verified** (we observed or ran it, with a date) or **Hypothesis** (still to check against a primary source or experiment).

## Sample input (Verified 2026-10-26, ffprobe/ffmpeg 8.1.1)

Both samples decode fully (`ffmpeg -v error -f null -`) with no errors.

| File                            | Size        | Codec         | Resolution         | FPS                                            | Frames | Duration | Audio |
| ------------------------------- | ----------- | ------------- | ------------------ | ---------------------------------------------- | ------ | -------- | ----- |
| `docs/sample/video/sample1.mp4` | 2,093,802 B | H.264 yuv420p | 640×360            | 25 (constant)                                  | 567    | 22.73 s  | AAC   |
| `docs/sample/video/sample2.mp4` | 1,130,263 B | H.264 yuv420p | 288×360 (portrait) | nominal 30, avg ≈29.97 (15495/517), likely VFR | 1033   | 34.50 s  | AAC   |

Implications:

- Both clips are low resolution, so the model input size and keyframe density matter more than VRAM.
- `sample2` is portrait and probably variable frame rate, so we must use per-frame timestamps, not index/fps.
- No telemetry or calibration files were supplied, so the video-only path is the primary test. Intrinsics are unknown and must be estimated and marked uncertain.

## Development hardware (Verified 2026-10-26)

- **GPU:** NVIDIA GeForce RTX 4050 Laptop, 6141 MiB VRAM, driver 616.92. CUDA 11.8 toolkit is on PATH.
- **OS and toolchain:** Windows 11, Node 26.12.1, pnpm 12.15.0, uv 0.12.13, Python 3.11.9 system plus 3.12.11 via uv, git 2.54.
- **Missing:** Docker, a running PostgreSQL, Redis.
- The 6 GB of VRAM is a hard constraint for local experiments. The college GPU's specs are unknown until Milestone 1.

## College VDI (Verified from the guide, 2026-10-26; nothing tested yet)

See ADR-0003. The guide documents:

- the portal URL and request dialog fields;
- the four session states;
- that "Connect" downloads an RDP/VNC file;
- the SyncHPC Storage module (upload/download).

It documents no SSH, inbound ports, API, sudo or Docker. Support contact: info@syncious.com.

## Model candidates (Hypothesis: licence, weights, version and VRAM all still to verify in Milestones 1/3)

| Role                | Candidate                                        | Source                                         | To verify                                                                                          |
| ------------------- | ------------------------------------------------ | ---------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Multi-view geometry | Fast3R                                           | https://fast3r-3d.github.io/, arXiv 2501.13928 | repo licence, weight licence/gating, pinned torch/CUDA, VRAM at 512px for N views, pose convention |
| Alternatives        | VGGT, MASt3R/MASt3R-SLAM, MapAnything, π³        | official repos                                 | licence (some are non-commercial), sliding-window support, VRAM                                    |
| Depth priors        | Metric3D-v2                                      | arXiv 2404.15506                               | weights hosting, input canonical-camera requirement, units                                         |
| Dynamics            | YOLO (Ultralytics) + SAM2                        | official repos                                 | Ultralytics is AGPL-3.0 (licence impact on distribution); SAM2 Apache-2.0                          |
| Sensor fusion       | GTSAM                                            | gtsam.org                                      | wheel availability for py3.12/Windows/Linux                                                        |
| Gaussian scene      | InstantSplat                                     | instantsplat.github.io                         | licence (3DGS-derived code is often non-commercial research only), input format                    |
| Surface             | SuGaR / Poisson (Open3D)                         | —                                              | SuGaR licence; Poisson is in Open3D (MIT)                                                          |
| Web splat renderer  | e.g. a maintained three.js Gaussian splat viewer | —                                              | maintenance, format compatibility with chosen splat output                                         |

A model-selection matrix with measured results on the sample goes in `docs/research/model-selection.md` in Milestone 3.
