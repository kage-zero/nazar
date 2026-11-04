# 05 — Hardware & College GPU Deployment

## 1. Hardware Architecture Overview

NAZAR is designed to support two distinct compute tiers:
1. **Local Developer Laptop**:
   * **GPU**: NVIDIA RTX 4050 Laptop (6 GB VRAM).
   * **OS**: Windows 11 (WDDM architecture).
   * **Best For**: Development, video ingestion, preflight quality analysis, CPU SfM baseline, Fast3R on short clips (<30 keyframes), and Open3D surface meshing.
2. **College High-Performance GPU (SyncHPC / SyncVDI)**:
   * **GPU**: NVIDIA A-series / Enterprise GPU (16 GB to 48 GB VRAM).
   * **OS**: Linux (Ubuntu).
   * **Best For**: Long video passes (100+ keyframes in 1–2 passes without chunk drift), InstantSplat CUDA builds, and large-scale Poisson meshing.

---

## 2. Stage-by-Stage Hardware Allocation

| Stage | Recommended Target | Hardware Resource Needed |
| :--- | :--- | :--- |
| **Preflight & Ingestion** | Local Laptop | CPU + FFmpeg (Fast single-pass decode) |
| **YOLO11 + SAM 2** | Local Laptop or College | 2–4 GB VRAM (Lightweight inference) |
| **Fast3R (Short video < 30s)** | Local Laptop | ~3.1 GB VRAM (4 passes of 9 views) |
| **Fast3R (Long video > 30s)** | College GPU | 12+ GB VRAM (Fits full clip without Sim(3) chaining drift) |
| **Open3D Surface Meshing** | Local Laptop | Multi-core CPU + 4 GB RAM (Takes ~2–4 seconds) |
| **InstantSplat / 3DGS** | College GPU | Linux CUDA toolchain + 8–16 GB VRAM |
| **Sensor Sim(3) & Georeferencing** | Local Laptop | CPU numpy/scipy (< 1 second) |

---

## 3. Dealing with Windows 11 Laptop Constraints (RTX 4050 6GB)

When running Fast3R locally on Windows:
1. **WDDM Commit Limit**:
   Windows charges GPU memory allocations against the system **commit limit** (RAM + Windows Pagefile). Fast3R needs ~5–8 GiB of free system commit.
   * *Mitigation*: Ensure your Windows virtual memory (Pagefile) is set to system managed or $\ge 16\text{ GB}$.
2. **Pass Chaining Drift**:
   Because 6 GB VRAM only fits ~9 views per pass, a 78-keyframe clip requires 15 chained passes. Small alignment errors can accumulate along the trajectory.
   * *Solution*: Run long clips on the College GPU where 16–24 GB VRAM fits 40–80 views in 1 or 2 passes.

---

## 4. College VDI Deployment Workflow (SyncHPC)

Follow [`docs/todoCollege.md`](../todoCollege.md) when on the campus network:

```
[Campus Network / SyncHPC Portal (172.32.0.8)]
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
    [Online Mode]           [Offline Bundle Mode]
    • Laptop exposes API    • Laptop runs: nazar-worker bundle export
      (port 8000)             saves var/bundles/mission.zip
    • VDI connects via:     • Upload zip via SyncHPC Storage module
      bash scripts/         • In VDI: nazar-worker bundle run mission.zip
      run-college-worker.sh • Download result.zip back to laptop
    • Real-time WebSocket   • Laptop runs: nazar-worker bundle import
      streaming in browser
```

### Steps to Run Inside the VDI Terminal:
```bash
# 1. Inside Linux VDI session
cd ~/nazar
uv sync --package nazar-worker

# 2. Check GPU capabilities
uv run nazar-worker doctor

# 3. Setup Fast3R on Linux GPU
uv run python scripts/setup_fast3r.py
uv run python scripts/setup_fast3r.py --check

# 4. Connect to laptop API
bash scripts/run-college-worker.sh <LAPTOP_CAMPUS_IP>
```

---

## 5. Security & Secret Handling Rules

* **College credentials never go in the repository**: Log in to `172.32.0.8` through the browser yourself.
* **Redacted Tokens**: The worker token (`NAZAR_WORKER_TOKEN`) is typed interactively with input hidden (`read -s`) and is never echoed to logs or stored in bundle zips.
* **Firewall Cleanup**: If running Online Mode on campus, remember to revert `NAZAR_API_HOST=127.0.0.1` and remove the temporary Windows Firewall rule once testing completes.
