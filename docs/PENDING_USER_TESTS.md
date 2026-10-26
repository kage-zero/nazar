# Tests waiting for you

These checks need you: your hardware, your college account, your eyes or ears, or a decision. Everything else is covered by automated tests (`pnpm check`, `pnpm test:e2e`).

**How to report.** Tick a box, or paste what you saw (output or a screenshot) under the item. Anything that fails gets fixed right away.

**Never paste passwords, tokens or `.env` values here.** Sensitive output stays redacted, and `nazar-worker doctor` prints none.

_Last updated: 2026-10-27_

## A. College GPU (Milestone 1) — needs your SyncVDI session

You log in yourself. Nothing here automates or stores your college credentials.

- [ ] **A1. Copy and install.** Inside a Linux VDI session, copy the repo (or only `apps/worker` + `packages/contracts`), then run `uv sync --package nazar-worker`.
  - Report whether `uv` and Python 3.12 are available.
  - If they are not, report what *is* installed: `python3 --version`, `which uv conda`.
- [ ] **A2. Doctor.** Run `uv run nazar-worker doctor --workdir <a writable dir>`. Paste the JSON. It shows the GPU model, VRAM, driver/CUDA, disk and CPU, and contains no secrets.
- [ ] **A3. Network.** Can the VDI reach the outside world? Run `curl -sS -o /dev/null -w "%{http_code}\n" https://pypi.org/simple/` and paste the number.
  - This decides ADR-0003 online mode versus bundle mode.
- [ ] **A4. Session limits.** Note the session duration you were offered, and whether the session keeps running after you disconnect (Disconnected state).
- [ ] **A5. Storage.** Note the path and size of your persistent home or storage directory, and whether files survive a new session.

## B. Things to look at in the browser

Run `pnpm dev`, and in a second terminal `pnpm worker`, then open http://127.0.0.1:5173.

- [ ] **B1. Full flow.**
  1. Create a mission.
  2. Upload `docs/sample/video/sample1.mp4`.
  3. Read the preflight.
  4. Press **Run test pipeline**.

  Expected:
  - stages light up one by one;
  - a sparse preview cloud appears and then gets denser;
  - the final cloud and camera path arrive;
  - "Completed" appears with an output list.
- [ ] **B2. Camera is kept.** While the test pipeline runs, orbit or zoom the viewer after the first preview appears. When later revisions arrive, the view should **not** jump back. Only the first preview of a job, or pressing **Fit**, moves the camera.
- [ ] **B3. Completion sound.** With "Completion sound" ticked, you hear one short two-note chime when a job you were watching completes. It does not play again on reload or on reopening the mission.
  - Browsers may block audio until you have clicked on the page; then no sound plays and the page says nothing about sound.
- [ ] **B4. Vibration (phone only).** Open the app on an Android phone on the same network. This needs `NAZAR_WEB_ORIGINS` plus Vite `--host`; ask me and I'll set it up. Expected: a short vibration on completion. On desktops the browser accepts the request but has no motor.
- [ ] **B5. Reconnect.** Start a job, turn Wi-Fi off for about 10 s, then turn it on again. Expected: the badge shows "Reconnecting…", then the job continues with no missing stages.
- [ ] **B7. Real reconstruction.** _(Deferred by you to later.)_ Upload `docs/sample/video/sample1.mp4`, wait for validation, press **Reconstruct**. Expected: preview clouds appear while "Multi-view geometry" runs (about 10–35 s on a laptop), and the final cloud shows the Colosseum's oval ring from above (orbit the view). The camera path forms an arc above the ground. Tags read "CPU baseline" when Fast3R is not configured (see B8 for the GPU path). Try `sample2.mp4` too (78 keyframes, slower).
- [ ] **B8. Reconstruct with Fast3R (this laptop's GPU).**
  1. Run `pnpm gpu:check`. It should end with "Fast3R runtime OK".
  2. Make sure `.env` has `NAZAR_FAST3R_PYTHON` and `NAZAR_FAST3R_WEIGHTS` (the check prints the lines).
  3. Restart `pnpm worker`. Its first lines should say "standard geometry: Fast3R on the GPU".
  4. Reconstruct `sample1.mp4`.

  Expected:
  - the job tag reads "GPU · Fast3R" and the viewer label reads "Fast3R · learned dense geometry";
  - a dense cloud (≈ 270k points) of the Colosseum appears in ≈ 20 s.

  If the job instead shows a "fast3r_fallback" warning, its message gives the reason. "unknown error" or "Memory allocation failure" means Windows ran short of commit memory: close heavy apps, or reboot, and retry.

  The automated version is `NAZAR_E2E_FAST3R=1 pnpm test:e2e` (it uses ports 18765/15174, so your `reelbox` on 8765 is not touched).
- [ ] **B6. Readability.** Is the copy clear? Is anything confusing, cramped, or unclear about being a synthetic test scene?

## C. Decisions only you can make

- [x] **C1. Model licences.** _Answered 2026-10-27: academic, non-commercial work; Fast3R approved._ See `docs/research/model-selection.md`. Fast3R is FAIR **non-commercial** research licence; MASt3R is CC BY-NC-SA plus dataset terms; VGGT's commercial weights are gated behind a form and exclude military use. Confirm NAZAR is non-commercial academic work, and approve Fast3R (or name another), before any weights are downloaded.
- [x] **C3. CPU baseline as the documented fallback.** _Answered 2026-10-27: accepted._ Until the GPU model runs, Reconstruct uses classical SfM: real but sparse geometry, no dense surface. Is that acceptable as the fallback the brief allows ("a clearly documented tested alternative")?
- [ ] **C2. Hosting.** Where should the API live so that the VDI worker can reach it (A3)? Options: your laptop via a tunnel, a small cloud VM, or the college network.

## Done

_Nothing yet._
