# College GPU day — checklist (Milestone 1)

_Revised 2026-10-29 at college. Claude: when the user says they are at college, follow this
step by step with them._

**How access works** (from the user's GPU-access email + `docs/SyncAI-VDI User Guide.pdf`)
- The SyncHPC portal is at `https://172.32.0.8/Login`, a **private campus address**: reachable only
  from the college network. The laptop must be on college Wi-Fi/LAN.
- A VDI session is opened with the **TurboVNC viewer** (v3.2, link in the email) on the laptop.
- The whole project stays on the laptop. The VDI only runs the GPU worker.

**Ground rules**
- You log in yourself. The portal username/password are in a private email/PDF: never paste
  them into the chat, a file, or the repo. Claude never asks for them or automates the login.
- Paste command *output* only. Never paste `NAZAR_WORKER_TOKEN`; type it in the VDI yourself.
- Nothing heavy runs on the college GPU until steps 1–5 pass. No speculative jobs.
- Exposing the laptop's API on the campus network (step 6) needs your explicit OK first, and
  only for the duration of the test.

## 1. Laptop prerequisites
- [ ] On the college network: open `https://172.32.0.8/Login` in the browser. A certificate
      warning is expected for an internal IP; continue only if it is the SyncHPC login page.
- [ ] Install TurboVNC viewer 3.2 (Windows installer from the link in the email).
- [ ] Note the laptop's campus IP: `ipconfig` → the Wi-Fi adapter's IPv4 address.

## 2. Start the GPU session (A4, A5)
- [ ] Log in, request a **Linux** workstation **with a GPU**, wait for **Ready**, press
      **Connect**, open the downloaded `.vnc` file with TurboVNC.
- [ ] Note: duration offered, whether it survives Disconnect, home path + free space (`df -h ~`).

## 3. Tools and GPU (A1) — in a VDI terminal
```bash
python3 --version; which uv conda git curl; nvidia-smi
```

## 4. Network from the VDI (A3) — decides how code, weights and jobs move
```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://pypi.org/simple/
curl -sS -o /dev/null -w "%{http_code}\n" https://huggingface.co
curl -sS -o /dev/null -w "%{http_code}\n" https://github.com
ping -c 2 <laptop IP>          # can the VDI see the laptop at all?
```

## 5. Code into the VDI + doctor (A1, A2)
- The repo has no Git remote. On the laptop: `git archive -o nazar.zip HEAD` (no `.env`,
  `var/`, weights). Move it with the portal's **Storage** module (upload from the laptop
  browser, download inside the VDI), then `unzip nazar.zip -d ~/nazar`.
- [ ] If `uv` is missing and PyPI is reachable: `curl -LsSf https://astral.sh/uv/install.sh | sh`
```bash
cd ~/nazar && uv sync --package nazar-worker
uv run nazar-worker doctor --workdir ~/nazar-work   # paste this JSON
```

## 6. Can the VDI reach the laptop's API? (C2 — decides online vs bundle mode)
Only with your OK (it opens the API to the campus network while it runs):
- Laptop: start the API on all interfaces: `NAZAR_API_HOST=0.0.0.0` in `.env`, `pnpm dev`.
  Windows Firewall will ask: allow **Private** only if possible; remove the rule afterwards.
- VDI: `curl -sS http://<laptop IP>:8000/api/health`
  - JSON back → **online mode** (live preview in the laptop browser).
  - Timeout → **bundle mode**: export on the laptop, move `mission.zip` / `result.zip` through
    portal Storage instead of a USB drive (commands in ADR-0003).
- Afterwards: set `NAZAR_API_HOST` back to `127.0.0.1`.

## 7. Fast3R on the college GPU
```bash
uv run python scripts/setup_fast3r.py          # needs PyPI + Hugging Face from the VDI
uv run python scripts/setup_fast3r.py --check  # must end with "Fast3R runtime OK"
```
- Linux path of the script is untested: paste errors, don't work around them.
- If Hugging Face is blocked: upload `var/gpu/weights/Fast3R_ViT_Large_512/` (≈ 2.5 GB) via
  portal Storage, then `--check --hash`.
- [ ] One measured run of sample1:
  - online: `NAZAR_WORKER_TOKEN=<type it> uv run nazar-worker run --api http://<laptop IP>:8000 --modes standard`, then Reconstruct in the laptop browser;
  - bundle: `uv run nazar-worker bundle run mission.zip --out result.zip`, then import on the laptop;
  - record geometry time, passes, peak VRAM (`nvidia-smi`) vs laptop: sample1 13.8 s,
    4 passes, 3,149 MiB.

## 8. Wrap-up
- [ ] Copy results off the VDI (the only copy must never stay in VDI temp storage).
- [ ] Revert `NAZAR_API_HOST`, remove the firewall rule, log out of the VDI yourself.
- [ ] Claude updates PENDING_USER_TESTS (A1–A5), IMPLEMENTATION_STATUS (Milestone 1),
      ADR-0003 (online or bundle), model-selection (college numbers).
