# College GPU day — checklist (Milestone 1)

_Written 2026-10-28 for the session at college. Claude: read this first when the user says
they are at college, then work through it step by step with them._

**Ground rules**
- You log in to SyncVDI yourself. Never paste the college username, password, OTP or any token
  into the chat or into a file. Claude will not ask for them or automate the login.
- Nothing heavy runs on the college GPU until steps 1–4 below pass. No speculative jobs.
- Paste command *output* only. `nazar-worker doctor` prints no secrets; still check before
  pasting.
- Results go into `docs/PENDING_USER_TESTS.md` (section A) and, at the end,
  `docs/IMPLEMENTATION_STATUS.md` + ADR-0003.

**Before leaving home**
- [ ] Laptop charged; repo up to date (`git log --oneline -1` should show the bundle-mode commit or newer).
- [ ] Decide how code gets into the VDI: `git clone` (needs network, step 3) or a zip of the
      repo on a USB drive / SyncHPC storage. Make the zip without `var/`, `.env`,
      `node_modules`, `.venv`: `git archive -o nazar.zip HEAD`.
- [ ] Optional: copy `var/gpu/weights/Fast3R_ViT_Large_512/` (≈ 2.5 GB) to the same drive, in
      case the VDI cannot download it (step 6).

## 1. Session facts (A4, A5)
- [ ] Start a **Linux** VDI session (GPU profile). Note:
  - session length offered, and whether it survives a disconnect;
  - home/persistent directory path and free space (`df -h ~`), and whether files survive a new
    session.

## 2. Toolchain (A1)
```bash
python3 --version; which uv conda git nvidia-smi
nvidia-smi
```
- [ ] If `uv` is missing and the network allows it: `curl -LsSf https://astral.sh/uv/install.sh | sh`
      (installs into `~/.local/bin`, no root). Otherwise report and we pick conda/pip.

## 3. Network (A3) — decides ADR-0003 online vs bundle mode
```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://pypi.org/simple/
curl -sS -o /dev/null -w "%{http_code}\n" https://huggingface.co
curl -sS -o /dev/null -w "%{http_code}\n" https://github.com
```
- [ ] Paste the three codes (200 / 30x = reachable; an error = blocked).

## 4. Install + doctor (A1, A2)
```bash
cd ~/nazar            # wherever the repo went
uv sync --package nazar-worker
uv run nazar-worker doctor --workdir ~/nazar-work
uv run nazar-worker stages
```
- [ ] Paste the doctor JSON (GPU model, VRAM, driver/CUDA, disk, CPU).

## 5. Can the VDI reach our API? (C2 — hosting)
- [ ] Only if step 3 showed outbound HTTPS works. Options to decide with Claude: laptop via a
      tunnel, a small cloud VM, or the college network. **No tunnel is opened without your
      explicit OK.**
- If outbound is blocked: **bundle mode** (built 2026-10-28, ADR-0003). Prepare at home: start
  the API, create a mission with sample1, press Reconstruct, stop any online worker, then
  `uv run nazar-worker bundle export --out mission.zip` (needs `NAZAR_WORKER_TOKEN` in `.env`).
  Put `mission.zip` on the USB drive with the repo zip. At college:
  ```bash
  uv run nazar-worker bundle run mission.zip --out result.zip   # no network, no token
  ```
  Bring `result.zip` home; then `uv run nazar-worker bundle import result.zip` with the API
  running. The job page fills in with the college run's stages and timings.

## 6. Fast3R on the college GPU (only if 1–4 passed)
```bash
uv run python scripts/setup_fast3r.py          # creates var/gpu/fast3r-env, pinned versions
uv run python scripts/setup_fast3r.py --check  # must end with "Fast3R runtime OK"
```
- The script was developed on Windows; the Linux path (`bin/python`) exists but is untested.
  Paste any error rather than working around it.
- If downloads are blocked, copy the weights folder from the USB drive into
  `var/gpu/weights/Fast3R_ViT_Large_512/`, then `--check --hash`.
- [ ] One measured run on the sample video (no other jobs):
  - online mode: run `uv run nazar-worker run --api <API URL>` with `NAZAR_WORKER_TOKEN` set in
    the shell (type it yourself; never paste it in chat), then press Reconstruct on the laptop;
  - bundle mode: `bundle run` as in step 5 (the result's `geometry` field says fast3r or
    cpu-baseline; stage durations are in the report after import);
  - record: geometry stage time, first preview time, passes, peak VRAM — compare with the laptop
    table in `docs/research/model-selection.md` (sample1: 13.8 s, 4 passes, 3,149 MiB;
    sample2: 50.5 s, 15 passes).

## 7. Wrap-up
- [ ] Note anything that differed from this list.
- [ ] Claude updates: PENDING_USER_TESTS (A1–A5 ticked with results), IMPLEMENTATION_STATUS
      (Milestone 1 report), ADR-0003 (online or bundle mode), model-selection (college numbers).
- [ ] Log out of the VDI session yourself.
