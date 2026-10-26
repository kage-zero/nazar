# Master Prompt for Claude Code: Single-Pass Drone Video → Progressive 3D Reconstruction

> **How to use:** Open Claude Code at the root of the project repository, attach/provide the project documents, paste this entire prompt, and let Claude inspect the workspace. The mandatory first checkpoint is intentional: Claude must scaffold the base repository, prepare blank environment-variable placeholders, summarize what needs credentials, and STOP until you fill them and explicitly say **continue**.

---

## 0. Your role and mission

Act as a principal full-stack engineer, 3D reconstruction researcher, GPU systems engineer, product designer, and test engineer working together. You are responsible for delivering a **working, polished, testable end-to-end product**, not merely a proposal, architecture diagram, static mockup, or pile of disconnected code.

The project converts a **single pass of drone video** into a useful 3D reconstruction, optionally strengthened by telemetry and calibration data. The web app must reveal the reconstruction progressively as real pipeline outputs become available, so the user can inspect partial geometry while later reconstruction stages continue. The final product should feel responsive, immersive, trustworthy, and technically honest.

Use informed creativity. Think beyond the most obvious implementation, investigate relevant research and production patterns, compare alternatives, identify integration risks early, and make evidence-based decisions. Do not blindly glue together every paper's repository. The final architecture must be viable on the actual college GPU environment, maintainable by this team, and measurable against real test data.

**Your goal is to keep working in deliberate iterations until the end-to-end acceptance criteria in this prompt are met.** Do not stop just because the first version compiles, one test passes, the UI looks good, or you have written a plan. Do stop at the explicit **Gate 1 credentials checkpoint** described in Section 4, and wait there. After the user fills the values and says `continue`, resume from the recorded implementation status and keep going.

Do not claim that performance, reconstruction accuracy, streaming, testing, or GPU execution works unless you have actually verified it. If a real limitation remains, explain it precisely, preserve all independent progress, and ask only the user decision or access question that is genuinely blocking further work.

## 1. Read and respect the project's source documents first

Before changing code, inspect the repository and read the documents in `docs/` **in full**, not just filenames, summaries, or the first page. Check actual files and nested directories rather than assuming paths or extensions.

At minimum, locate and read:

1. The detailed project description, expected pipeline, architecture, limitations, evaluation metrics, implementation roadmap, and demo plan for **Single-Pass Drone Video to Accurate 3D Model Generation System**.
2. `docs/design.md` (case-insensitive path discovery is fine) as the authoritative product design system. The uploaded style reference may currently be named `DESIGN(1).md`; preserve it and map the real file path rather than overwriting or renaming it blindly.
3. The **SyncVDI / SyncHPC User Guide** PDF, including meaningful screenshots/diagrams that explain session provisioning and connection. Extract and inspect PDF pages if text extraction misses important information.
4. Every asset/video under `docs/sample/video/` (or the exact equivalent found in the repository). Identify its real path, file type, duration, dimensions, frame rate, and whether it decodes correctly. This video is the required representative end-to-end test input.
5. Any other relevant documents, diagrams, sample telemetry, calibration files, API specifications, prior implementation notes, and existing tests already in the repository.

Preserve the source documents. Do not overwrite the supplied documentation with your own rewrite. Add new documentation alongside it, and link it from the README.

### Source-of-truth rules

- The user's explicit requirements in this prompt take precedence over a conflicting assumption in older planning documentation.
- In particular, **video is mandatory and telemetry is optional** for the requested user journey, even if the project brief describes GPS/GNSS as a mandatory input for some configurations. The system must attempt a video-only reconstruction when telemetry is absent. Explain the resulting uncertainty and do not claim geographic alignment or metric accuracy without valid evidence.
- React Three Fiber is a required part of the interactive 3D application.
- The repository must be a Turborepo monorepo, with TypeScript for the web/product layer and Python/FastAPI for the backend.
- The design guide is the authority for visual styling. Do not replace it with a generic dashboard template.
- When documents disagree or the requirements are impossible to reconcile, record the exact disagreement and ask the user one concise, specific question. Do not silently erase requirements.

At the start, provide a concise discovery summary covering: documents found/read, the sample-video path discovered, the current repository state, any existing work that must be preserved, the proposed monorepo layout, the first known integration risks, and any genuinely blocking questions. Do not spend time asking questions already answered by the documents. Make sensible reversible choices and record them in `docs/decisions/`.

## 2. Operating principles: discover, implement, verify, iterate

Follow this loop throughout the entire project:

1. **Inspect:** check the current files, Git status, project conventions, docs, package versions, installed runtimes, and service availability before changing things.
2. **Plan a small vertical slice:** define the behavior, API/data contract, implementation path, and success checks for the next slice.
3. **Implement the real behavior:** favor maintainable, typed code and observable interfaces. Do not use a fake result to make a demo look finished.
4. **Test immediately:** run the smallest relevant unit, type, integration, and browser tests after each meaningful change.
5. **Run the application:** exercise the actual browser, API, WebSocket/event flow, worker, and artifacts where possible.
6. **Inspect evidence:** examine Playwright screenshots, traces, videos, browser console/network errors, API logs, worker logs, and GPU/memory telemetry when relevant.
7. **Fix, then rerun:** investigate the root cause, repair it, and rerun both the failing test and relevant regression suite. Never merely dismiss, skip, or retry a failure without understanding it.
8. **Update project status:** record what works, what failed, what changed, and the next concrete step.

Repeat this loop. **Do not stop after reporting a bug. Fix it. Do not stop after the first green build. Continue through the full user journey.** Do not label a stub, mocked flow, placeholder model, or unexecuted test as complete.

### Questions and autonomy

Use web research, source code, docs, local experiments, and small prototypes to answer technical questions yourself. Ask the user when a decision materially changes the product, requires access/credentials the user alone can provide, or cannot be resolved from available evidence. Batch related blocking questions into one concise message. Avoid asking for permission on routine, reversible engineering decisions.

If a dependency, CUDA version, model license, data format, or service endpoint is unknown, investigate it and record the evidence. Do not pretend a guess is verified. If a long-running or expensive GPU experiment is about to consume significant resources, check the hardware and workload first; do not launch concurrent heavy jobs speculatively.

### Persistent working notes

Maintain these files as work progresses:

- `docs/IMPLEMENTATION_STATUS.md` — current milestone, completed work, test evidence, outstanding work, exact next action, and resume instructions.
- `docs/decisions/ADR-*.md` — important architectural choices, considered alternatives, evidence, and consequences.
- `docs/architecture/` — component boundaries, data flows, API/event contracts, coordinate-frame rules, and deployment diagrams.
- `docs/testing/` — how to run fast tests, browser E2E tests, GPU integration tests, and benchmark tests.
- `docs/research/` — source links, access date, model/version/license checks, VRAM notes, compatibility findings, and experiments. Separate verified facts from hypotheses.
- `docs/ENVIRONMENT_SETUP.md` — required versus optional environment values, local development, college VDI workflow, and safe secret handling.

These notes must let you resume correctly after the user says `continue` or a new Claude Code session starts.

## 3. Technical research and model selection

Use web search when helpful and verify primary sources: the original paper, official repository, official model card, release notes, issue tracker, supported environment files, and license/weights terms. Prefer official and peer-reviewed/author sources over copied blog snippets. Record links and the date checked in the research notes.

The provided project brief identifies these candidates. Evaluate and integrate them where compatible and beneficial:

- **FFmpeg + OpenCV** for video validation, frame extraction, image quality assessment, and preprocessing.
- **Fast3R** for multi-view geometry, camera poses, and pointmaps.
- **Metric3D-v2** for depth and surface-normal priors, treated as supporting evidence rather than unquestionable ground truth.
- **YOLO + SAM2** for detection, temporal segmentation/tracking, and dynamic-object masks where justified.
- **GTSAM** for sensor/trajectory optimization when the required timestamps, calibrations, and observations are available.
- **Open3D** for point-cloud processing, registration, filtering, and analytical geometry.
- **InstantSplat** (or a verified compatible alternative) for a Gaussian scene/visual representation.
- **SuGaR and/or Poisson reconstruction** for meshes when source observations and representation support meaningful surface extraction.
- **GDAL / PROJ / PyProj / Shapely** for valid coordinate transforms and geospatial artifacts.

Also research credible alternatives where they may improve reliability, speed, VRAM use, quality, or compatibility—for example, other feed-forward multi-view geometry or sparse-view reconstruction approaches. Do not choose an alternative only because its demo looks impressive. Compare actual input/output contracts, supported viewpoints, license terms, GPU requirements, installation complexity, integration effort, and testable reconstruction quality.

Create a short model-selection matrix with columns such as: intended role, source URL, model/license status, required hardware/runtime, required input format, output format, known restrictions, integration adapter, and measured result on our sample. Verify that licenses allow the intended use and that pretrained weights are legitimately accessible before downloading or deploying them. Respect gated weights and model terms.

**Do not force every named research component into one process if incompatible dependencies or GPU memory make that unsafe.** Isolate conflicting model stacks into version-pinned Python environments or separate worker processes/containers, connect them through explicit file/API contracts, and test each adapter independently. If you recommend omitting/replacing a requested component, explain the measured or documented reason and ask for a decision when the change is material; do not silently drop it.

## 4. Mandatory Stage 1: scaffold the base Turborepo, then STOP for API keys

This is a hard gate. The first implementation milestone is **only the base repository and safe configuration scaffold**, not the complete reconstruction pipeline.

### 4.1 Inspect before scaffolding

- If the current workspace already contains code, inspect it and preserve useful work. Do not overwrite an existing application simply to conform to a new template.
- Confirm the available Node.js, package manager, Python, `uv`, Git, Docker, and GPU-related toolchain versions where accessible.
- If no existing repo decisions dictate otherwise, use **pnpm workspaces + Turborepo** for JavaScript/TypeScript orchestration and **uv + `pyproject.toml`** for Python dependency management. Commit lockfiles and pin known-compatible dependencies.
- Do not install large research-model dependencies or download large model weights in this stage. Do not consume the college GPU yet.

### 4.2 Create a clean, scalable monorepo foundation

Adapt the layout to any existing repo conventions, but aim for clear boundaries similar to:

```text
.
├── apps/
│   ├── web/                 # React + TypeScript + Vite + React Three Fiber
│   ├── api/                 # FastAPI, API routes, auth/validation, job control
│   └── worker/              # Python job worker and reconstruction adapters
├── packages/
│   ├── ui/                  # reusable product UI components where appropriate
│   ├── contracts/           # shared event/API contract strategy or generated client
│   └── config/              # shared lint/format/TypeScript configuration as useful
├── infra/
│   ├── docker-compose.yml   # optional local PostgreSQL/PostGIS, Redis, MinIO
│   └── ...
├── docs/
│   ├── architecture/
│   ├── decisions/
│   ├── research/
│   ├── testing/
│   ├── IMPLEMENTATION_STATUS.md
│   └── ENVIRONMENT_SETUP.md
├── .env.example
├── .gitignore
├── package.json
├── pnpm-workspace.yaml
├── turbo.json
└── README.md
```

Do not create empty folders or abstractions that add no value. Keep the Python runtime independent from JavaScript dependency installation. Define practical Turbo tasks to run the TypeScript web app and invoke Python commands (with appropriate caching disabled for long-running services). Make local development easy to understand.

### 4.3 Stack and quality baseline

- Web: React, TypeScript strict mode, Vite unless the existing project makes a different framework clearly more appropriate, React Three Fiber, Three.js, Drei, Tailwind CSS, Zustand for small UI state, and a typed API/event client.
- Backend: Python, FastAPI, Pydantic, SQLAlchemy, Alembic migrations, and a job queue design using Celery/Redis or a documented, tested alternative. Never execute long GPU inference synchronously inside ordinary FastAPI request handlers.
- Data and artifacts: PostgreSQL/PostGIS for metadata/spatial records, object storage (MinIO locally if useful) for large artifacts, and Redis for queue/cache/transient coordination—not as the only durable record.
- Quality tools: ESLint, Prettier, strict TypeScript, Python lint/format/type checks, pytest, API contract validation, and Playwright configured for browser E2E.
- Infrastructure: optional local Docker Compose for supporting services. Avoid assuming the college GPU machine has Docker, NVIDIA Container Toolkit, administrative privileges, or unrestricted inbound ports.
- Use a consistent naming convention, structured logging, readable error messages, typed settings, health checks, and a useful root README.

### 4.4 Build only a small but real base UI and health path

At this first stage, implement enough to prove the skeleton works:

- A polished application shell that respects `docs/design.md`.
- An honest empty state for a new mission, a video-upload component shell, and a clearly identified 3D viewport scaffold using React Three Fiber.
- A FastAPI health/readiness endpoint and a simple API connectivity check from the web app.
- Initial typed data/event contracts and explicit TODO boundaries for actual reconstruction stages.
- Unit-test and Playwright scaffolding that can run without downloading neural weights or using GPU credentials.

Do not make a fake progress bar or fabricate a 3D reconstruction in this stage. Clearly label incomplete pipeline capabilities. The purpose is a clean, runnable foundation—not a pretend finished product.

### 4.5 Environment variables and API keys: leave values BLANK

Create a committed **`.env.example`** with empty values for real API keys and any required secret settings. Also create a local ignored `.env` file with the same blank placeholders if that fits the repository workflow. Confirm `.env`, `.env.*` secret variants, credentials, tokens, downloaded weights, and generated mission data are covered by `.gitignore`; allow only explicitly approved example templates to be committed.

Rules:

- Every API-key placeholder must have a **blank value**. For example, `SOME_PROVIDER_API_KEY=`—never use fake-looking keys, real keys found elsewhere, or hard-coded secrets.
- Only add keys for services that the selected architecture actually uses. Separate **required**, **optional**, and **not needed for local development**. Do not invent a third-party API dependency for something available locally/open source.
- Keep non-secret settings separate from secrets. Document purpose and how to obtain each needed value without exposing actual keys.
- Never ask the user to paste secrets into the chat. Ask them to fill the ignored local `.env`/secret manager themselves.
- Never print, log, screenshot, commit, or include secret values in final summaries or `IMPLEMENTATION_STATUS.md`. Validate only whether values are present/valid; redact them in diagnostics.
- Do not confuse the college SyncVDI login credentials with product API keys. Do not embed college login ID/password in code, environment examples, URLs, shell history, tests, screenshots, or source control.
- If no third-party API key is technically required yet, say so honestly, keep the appropriate placeholders blank, and still perform the checkpoint requested by the user. Do not manufacture a requirement just to force a key.

### 4.6 Gate 1 acceptance checks

Before stopping, verify and report actual results for:

1. Monorepo layout and lockfiles created without overwriting supplied docs.
2. JavaScript dependencies installed for the scaffold.
3. Web app starts and renders in a real browser.
4. FastAPI app starts and its health endpoint responds.
5. TypeScript, lint, Python checks, and scaffold unit tests pass—or any failure is fully explained and fixed where possible.
6. Playwright can open the app, render the main screen, and verify that the API health indicator behaves correctly.
7. Environment placeholders are blank; secret files are ignored; no secret values were committed.
8. `docs/IMPLEMENTATION_STATUS.md` records the exact current state and the next step.

### 4.7 Then STOP and wait

Once the scaffold and checks are complete, **do not proceed to full pipeline implementation**. Present:

- What was created and what you actually ran.
- Test results and any remaining scaffold blocker.
- The exact local file(s) the user must fill, plus a list of required and optional variables with **variable names only** and no secret values.
- Any college VDI access facts still needing user input, if any.
- The exact instruction: “Fill the blank values in your local ignored `.env` file (do not paste secrets here), then reply `continue`.”

Then stop the implementation. Do not continue until the user has filled the values and explicitly says `continue`.

### 4.8 Resume protocol after `continue`

When the user replies `continue`:

1. Read `docs/IMPLEMENTATION_STATUS.md`, `docs/ENVIRONMENT_SETUP.md`, the current Git status, and the relevant configuration again.
2. Check required secret/config values safely without echoing them. Test access to required services only after confirming the configuration is present.
3. If a value is still missing and blocks the next planned step, ask only for that missing variable name and explain what functionality it blocks; keep all existing work.
4. Otherwise resume from the recorded next action—do not restart the repo, repeat completed work, or ask the user to repeat requirements already provided.
5. From this point onward, implement and validate the product in vertical slices until acceptance criteria are met or a genuine external blocker remains.

## 5. College GPU and SyncVDI/SyncHPC workflow

Read the supplied SyncVDI/SyncHPC guide in full and follow its actual capabilities. The guide describes a browser portal for requesting/managing workstation sessions and choosing platform, CPU cores, GPU, RAM, and duration; it explains session states (Requested, Ready, Active, Disconnected) and that connecting may download an RDP or VNC file. Treat this as a user-operated, centrally managed remote workstation—not as proof that a documented GPU REST API or SSH service exists.

### GPU access rules

- Have the user sign in and request/connect to the college GPU session themselves through the official portal. Never automate credential entry, scrape saved credentials, or ask them to paste their college password into the chat.
- Prefer the Linux environment for Python/CUDA research code if supported and approved by the college. Verify the chosen deployment, allocated GPU, CPU/RAM, session duration, available storage, network constraints, and installed toolchain with safe read-only diagnostics such as `nvidia-smi`, `python --version`, CUDA/PyTorch checks, disk checks, and port tests.
- Do not assume you can `ssh` into the machine, expose an API port, install system packages, use Docker, use `sudo`, keep a daemon running after logout, or reach it from the web backend. The supplied guide alone does not guarantee any of those. Verify them or ask the user / college support for the approved connection mechanism.
- Do not run expensive reconstructions until GPU identity, free memory, disk capacity, library compatibility, and ability to persist results have been checked.
- Keep a documented boundary between the ordinary API/web tier and the GPU worker tier. If the GPU lives in a VDI session that cannot provide a stable worker endpoint, design a valid manual/agent-run worker protocol or ask what approved persistent access exists; do not silently pretend a web server can reach the VDI.
- Keep source video and intermediate/final artifacts in storage that survives session expiry, or upload completed artifacts safely to approved storage. Do not leave the only copy in a temporary VDI directory.
- Record session assumptions and how to start/stop worker processes. Avoid consuming shared GPU resources when the user is not actively running a requested experiment.

### GPU efficiency and memory safety

GPU memory is a critical constraint. Design for controlled concurrency and graceful degradation:

- Separate CPU preprocessing from GPU inference and post-processing.
- Start with one heavy GPU reconstruction job at a time unless profiling proves higher concurrency is safe. Enforce a queue/worker semaphore so two users or retries cannot allocate full VRAM at once.
- Check memory, image resolution, keyframe count, and expected batch sizes before starting a stage. Use bounded batches/sliding windows, adaptive keyframe selection, mixed precision only when model support and quality tests justify it, and configurable draft/balanced/high-quality modes.
- Load only the models required for the current stage, reuse a resident model if beneficial, and unload large weights between incompatible stages. Avoid keeping several large models on GPU concurrently without measured justification.
- Cache deterministic stage outputs using source checksums + model/version + configuration. Checkpoint completed stages and write artifacts atomically so a failure does not force a full rerun.
- On CUDA OOM: catch the error at the worker boundary, release stage-owned resources, lower batch/window size or resolution, retry a bounded number of times, and record the chosen fallback. Never enter an infinite retry loop or report a successful reconstruction with missing stages.
- Monitor peak VRAM, RAM, CPU, disk, queue time, per-stage time, and time to first preview. Add cancellation and worker-health checks. Keep concurrency and resource use configurable.
- Use profiling to determine whether optional acceleration (such as TensorRT) is supported by each actual model/version. Do not assume all operators convert or that acceleration automatically improves end-to-end speed.

## 6. Product experience and complete user journey

Design and implement the whole user journey, not only the 3D viewport:

1. User creates or opens a mission/project.
2. User uploads **one drone video**. Telemetry and calibration files are optional and can be added separately. Missing telemetry must not prevent video-only processing.
3. The client shows upload progress and basic file information. The server validates content, file size/duration limits, decoder health, video resolution/FPS/duration, and optional metadata format.
4. A preflight screen reports frame-quality concerns (blur, repeated frames, lighting, limited viewpoint diversity), available/missing sensors, detected timestamps/calibration where possible, and the known implications of missing data. Let the user continue if safe, while clearly displaying warnings.
5. User starts reconstruction and receives a job ID promptly. Long GPU jobs execute asynchronously.
6. The processing screen shows the actual current stage, stage-specific progress where measurable, elapsed time, warnings, logs/diagnostics at an appropriate detail level, cancellation, and retry when valid.
7. The 3D viewer becomes useful as soon as the first valid partial geometry is available. It keeps updating as better artifacts arrive; the user can inspect and orbit the partial scene while later stages run.
8. When final reconstruction and required artifact validation finish successfully, show a clear completion state, play a short completion sound subject to browser/audio permission and user settings, and trigger a subtle haptic only if the browser/device genuinely supports it.
9. User inspects, measures, annotates, switches layers, checks uncertainty/provenance, and exports results plus a processing report.

Include empty, uploading, validating, queued, processing, partial-preview-available, completed, failed, cancelled, and reconnecting states. All errors should be actionable and human readable. Do not leave controls enabled when their actions are invalid. Make keyboard navigation, focus states, screen-reader labels, responsive layouts, and reduced-motion preferences part of the implementation.

## 7. Required visual design: follow `docs/design.md`

Treat the supplied design guide as a precise design system, not loose inspiration. It describes a warm-gray, brutalist-editorial showroom style. Apply the actual tokens and hierarchy consistently:

- Canvas/background: warm gray `#e5e5e5`, never default to an all-white page.
- Cards: `#ffffff` flat surfaces against the canvas; inverted areas use `#000000` and white text.
- Core text: carbon black `#000000`; secondary text/slate `#444444`; restrained muted text around `#979797`; ash `#c6c6c6` for necessary rules/disabled states.
- Signature mint `#d1ffca` is reserved for small tags/links/status accents; voltage yellow `#fff100` is a tiny highlight, not a large background fill.
- Display headlines are oversized, condensed, uppercase, tightly tracked, and use around `0.9` line height. Use the specified proprietary font only if it is legitimately available; otherwise use the document's recommended substitute (such as Anton/Bebas Neue/Barlow Condensed Bold) and document the fallback. Use Inter/Söhne-like sans-serif for body and a mono face such as JetBrains Mono for technical metadata.
- Follow the 8px spacing rhythm, generous section gaps, approximate 1200px content maximum, 24–32px card radius, 48px navigation pill, and small 4–8px button radii where relevant.
- Keep surfaces flat: no card/button box shadows and no gradients. Do not add gratuitous decoration, emoji, random accent colors, stock imagery, or an off-the-shelf generic dashboard aesthetic.
- Use strong typography, well-composed empty states, carefully aligned technical metadata, clear information hierarchy, purposeful transitions, and visually calm technical plots.
- The 3D viewport may use a restrained black/inverted scene backdrop if it helps geometry contrast, but it must fit the design system. Keep controls visually coherent with the rest of the app.
- Make desktop the primary analysis workflow while ensuring useful behavior on tablet and mobile. Do not simply shrink the desktop layout until unusable.

Build shared design tokens and reusable primitives rather than copying styles across screens. Compare each browser screenshot with `docs/design.md` and improve the result during every visual testing pass.

## 8. Reconstruction pipeline: true single-pass, with optional telemetry

Implement the pipeline incrementally, using explicit inputs/outputs for every stage and a valid video-only path. The intended stages are:

### Stage A — ingest and data preparation

- Validate upload by decoding actual content, not trusting filename/extension alone. Generate internal filenames and protect paths from traversal.
- Use FFmpeg/OpenCV to inspect and decode frames while preserving source frame indices/timestamps and source video. Do not silently change aspect ratio, distort imagery, or overwrite the original.
- Score blur/sharpness, exposure clipping, darkness, duplicates, severe compression, and useful visual novelty. Select keyframes using quality + temporal spacing + viewpoint novelty + overlap/parallax, not fixed-rate extraction alone.
- Process long clips in bounded chunks and make preprocessing restartable. Record source checksum, settings, frame manifest, skipped frames, warnings, and duration.
- Parse optional telemetry/calibration from the real formats supported by the provided data. Normalize time bases, units, coordinate systems, and axis conventions. Detect likely clock offsets and gaps; never interpolate across unsupported gaps or invent missing readings.
- If telemetry is absent, continue with video-only geometry. Tell the user which outputs remain in a local reconstruction frame, how scale is estimated (if at all), and why global positioning or certain measurements may be unavailable.

### Stage B — early multi-view geometry / first preview

- Integrate Fast3R through an adapter whose input/output schemas, coordinate convention, camera-pose convention, confidence outputs, batching, and memory behavior are tested for the exact pinned version.
- Normalize pointmaps/poses into a documented internal convention and associate each output with source frames and transforms.
- Emit a preview-ready subset as soon as actual valid geometry is available. Do not wait for mesh extraction, all optional analysis, or final exports before rendering a first useful point-cloud preview.
- When Fast3R is unsuitable for a tested input or impossible to run in the available GPU budget, use the research matrix to compare an approved fallback and explain what changed. Never silently substitute dummy points.

### Stage C — depth priors

- Integrate Metric3D-v2 only after verifying its supported inputs, output units, calibration assumptions, pretrained weights and license, and CUDA/PyTorch compatibility.
- Treat monocular depth and normals as confidence-bearing priors. Compare them with multi-view geometry and sensor evidence; reject outliers and handle scale disagreement.
- Add ablation tests to show whether these priors actually help the sample dataset instead of assuming they do.

### Stage D — dynamics and temporal masks

- Use detection and temporal reasoning (YOLO and SAM2, where compatible) to identify moving objects, propagate masks, and optionally retain reliable tracks as separate annotations.
- Detection alone is not evidence of movement. Avoid masking static objects blindly. Show masks/track confidence and allow a supported static-reconstruction exclusion option.
- If masking removes pixels whose background was never observed, label the hole as unobserved/inferred rather than fabricating ground truth.

### Stage E — optional sensor fusion and metric alignment

- Use GTSAM only when telemetry quality, timestamping, calibration, and measurements support a meaningful factor graph. Start from visual estimates, define realistic noise models, inspect residuals/outliers/convergence, and compare visual-only with sensor-fused results.
- Document all frame transformations (camera, body/IMU, local reconstruction, ENU, ECEF, geographic/projected CRS) with correct units, datum, axis order, and vertical reference.
- Never treat latitude/longitude as Cartesian metres. Distinguish ellipsoidal GNSS height from barometric altitude. Do not claim global georeferencing without a valid anchor.
- If telemetry is missing, skip the sensor-fusion stage cleanly and explicitly report why; do not fabricate GPS/IMU data.

### Stage F — point-cloud and visual scene reconstruction

- Use Open3D for analytical point-cloud operations including validity checks, filtering, alignment/registration, normal estimation, and downsampling. Keep analysis geometry separate from visual appearance assets.
- Evaluate InstantSplat or a compatible Gaussian reconstruction route against the actual available inputs and format expectations. Do not assume a model consumes arbitrary Fast3R outputs without conversion. Write and test adapters and any required transforms explicitly.
- Keep Gaussian scene rendering separate from metric measurement claims. A good-looking splat is not proof that dimensions are accurate.
- Preserve intermediate artifacts and manifests; do not make every retry recompute deterministic completed work.

### Stage G — surface and geospatial outputs

- Use SuGaR/Poisson or another justified surface method only where the representation, normals, and data support it. Validate holes, spikes, components, normals, winding, non-finite coordinates, scale, and suspicious gap filling.
- Use GDAL/PROJ/PyProj/Shapely for correctly defined spatial operations, not as a way to hide poor trajectory or calibration.
- Support the outputs justified by the input and test cases: PLY point cloud, GLB/glTF and/or OBJ mesh when valid, LAS/LAZ with correct scale/offset/CRS where supported, and GeoJSON/GeoTIFF only when the output is genuinely geographic/raster data with valid CRS metadata.
- Ensure output metadata includes units, coordinate frame/CRS and vertical datum where relevant, source asset checksum, model/version, configuration, completion status, warnings, and provenance.

### Stage H — confidence, measurements, and report

- Provide transparent categories such as **Observed**, **Estimated**, and **Inferred**, based on support from views, parallax/viewpoint diversity, pointmap/depth agreement, image quality, reprojection/alignment residuals, sensor factors, and distance from directly supported points.
- These are confidence labels, not statistically calibrated probabilities unless calibrated and validated. Do not turn a heuristic into a misleading probability score.
- Measurements must show units and quality warnings. Warn when sparse geometry, occlusion, poor scale, or weak georeferencing makes a measurement unreliable.
- Produce a processing report describing input/sensors used, selected frames, warnings, pipeline stages, model versions, runtime, peak VRAM/RAM where available, output inventory, CRS/units, metrics, and limitations.

## 9. Progressive reconstruction streaming: core product requirement

The app must provide the real equivalent of progressive text streaming for reconstructed 3D data, within the actual capabilities of the algorithms. The user must see geometry as early as valid outputs are produced—not a spinner until everything is complete and not a fake animated placeholder.

### Event-driven processing design

- A job-start API returns a stable job ID quickly; CPU/GPU work runs asynchronously.
- Establish an authenticated WebSocket (or another justified reliable streaming mechanism) for job events. Provide REST polling/reconnect fallback so browser disconnects do not lose the job.
- Define and validate typed event contracts, including events such as `job.created`, `stage.started`, `stage.progress`, `warning`, `artifact.available`, `preview.updated`, `stage.completed`, `job.completed`, `job.failed`, `cancel.requested`, and `job.cancelled`.
- Every event should include the job ID, event sequence/cursor, timestamp, stage, status, and structured metadata appropriate to that event. Progress must correspond to actual work; if exact percentage is not measurable, use stage status/indeterminate progress rather than inventing precision.
- Publish a manifest when each partial artifact is ready. Include artifact type, URI/authorized ID, coordinate frame/transform, units, bounds, point count/LOD, source frame/time range, confidence metadata if available, checksum, and version/revision.
- Stream efficient chunks or LOD/tile updates, not millions of JSON point objects. Consider binary/compressed artifact chunks, chunked file uploads, HTTP range requests, and progressive level-of-detail. Apply backpressure and bounded buffering.
- Version preview revisions so stale chunks are not mistakenly applied after retry/cancellation. Make cancellation and reconnect behavior explicit. Do not expose arbitrary local filesystem paths or raw storage credentials to the browser.
- Save server-side event/job state so a reconnecting client can resume from the last event or reload the current job snapshot.

### Required visible behavior

1. While the video uploads, show real upload progress.
2. As soon as preprocessing emits real results, show selected keyframes/quality feedback.
3. As soon as an initial reconstruction artifact exists, add it to the R3F viewport. Do not wait for optional mask, metric-fusion, splat, mesh, or export stages.
4. As later chunks/refinements arrive, update the same scene smoothly without resetting the user's camera/orbit unnecessarily.
5. Allow users to orbit, pan, zoom, inspect axes/scale, and toggle available layers while processing continues.
6. Make the current stage and new artifact availability obvious without overwhelming users with logs.
7. Once and only once the **complete job** succeeds and final outputs pass validation, play the completion effect and show the final output inventory. A preview becoming available is not job completion.

If a particular model cannot emit meaningful per-frame or incremental geometry, do not pretend it can. Build the earliest honest progressive stage around the first real artifact it produces, and explain the granularity in the UI and technical notes.

## 10. React Three Fiber viewer and immersive interaction

React Three Fiber is mandatory, not a decorative canvas. Build the viewer as a real inspection tool, using Three.js and Drei where appropriate.

Required capabilities, prioritised by actual artifact availability:

- Progressive point-cloud rendering with chunk/LOD updates and a large-cloud performance strategy. Avoid pushing huge geometry buffers through global Zustand state.
- Camera trajectory/path display and frame/camera markers when poses exist.
- Separate toggles for point cloud, Gaussian scene (if compatible renderer is integrated), mesh, camera path, dynamic-object tracks/masks, and confidence overlays.
- Orbit, pan, zoom, fit-to-bounds, reset view, axes/grid, scale indicator, and coordinate-frame label.
- Loading and failure overlays for individual layers so one unavailable asset does not crash the entire viewer.
- Picking/selection for supported annotations and measurement tools such as point-to-point distance, polyline length, height relative to a defined plane, and area where the geometry supports it.
- Clear units, local/global frame distinction, observed/estimated/inferred legend, and explicit warnings when measurement quality is weak.
- Efficient resource disposal when replacing a preview; avoid GPU buffer leaks, unnecessary React rerenders, giant state objects, per-point React components, or full-scene remounts on every message.
- Use workers/off-main-thread processing for expensive client-side transforms where appropriate. Profile frame rate and memory on representative output sizes, and add decimation/LOD when necessary.

For Gaussian splatting, research and select a maintained, compatible rendering path that works with the chosen stack and artifact format. If there is no validated compatible renderer, deliver the useful point-cloud/mesh experience first and document the Gaussian renderer as a separately blocked integration—do not claim support because a button exists.

## 11. Micro-interactions, animation, sound, and haptics

Make the product responsive and satisfying without sacrificing clarity or accessibility:

- Add short, intentional transitions for upload-state changes, stage changes, preview arrival, layer toggles, successful completion, and measurement selection.
- Use spring/opacity/transform motion sparingly and consistently; respect `prefers-reduced-motion` and provide reduced-motion behavior.
- Add a short, locally generated or properly licensed completion tone. Do not depend on remote audio or copyrighted audio. Account for browser autoplay restrictions; enable sound only when user settings/browser rules permit it.
- Use the Vibration API only after capability detection and only on supported devices. Haptics are an enhancement, never a requirement for understanding completion. Do not claim haptics ran on a desktop browser that lacks support.
- Expose simple settings to turn sound/haptics off. Avoid repeating notifications after every partial preview, reconnection, or duplicated event. Use idempotent job-completion notification keyed by job ID.
- Include visible status text and accessible live regions so users who mute sounds or cannot feel haptics receive the same information.
- Keep animation lightweight. Do not add animation packages without a clear product benefit.

## 12. Backend, job lifecycle, persistence, and APIs

Design the FastAPI application as a typed, testable service. Keep upload/metadata request handlers fast and move expensive work to workers.

Expected functional API surface (adapt to existing conventions and document it):

- project/mission create and list
- video/telemetry/calibration upload or registration
- validation/preflight summary
- create/start reconstruction job
- read job snapshot/status/history
- authenticated job events/WebSocket
- request cancellation and supported retry
- list artifacts/outputs and retrieve authorized metadata
- request/download exports and processing report

Use a state machine with explicit transitions similar to:

`created → validating → queued → preprocessing → geometry → depth_priors → dynamic_analysis → sensor_optimization → dense_reconstruction → surface_processing → analysis → exporting → completed`

Support valid skips when optional stages/input are unavailable. Also support `failed`, `cancel_requested`, and `cancelled`. Do not fake a skipped stage as completed successfully; record why it was skipped. Store human-readable failure reasons and structured stage logs. Tasks should be idempotent where practical, use bounded retries, write files atomically, and checkpoint work.

Use PostgreSQL/SQLAlchemy/Alembic for durable metadata, PostGIS for geographic entities with explicit SRIDs, Redis for queued/transient coordination, and MinIO/object storage for large binary artifacts if supported by the deployment. Keep these services configurable and allow tests to run without a real GPU or external keys.

Include authentication and project/job/output authorization at every endpoint and WebSocket subscription if the app has user accounts. Do not assume obscurity of a job ID provides authorization. Validate uploads by extension and content, limit size/duration, prevent path traversal, create internal filenames, isolate decoders/workers where practical, rate-limit expensive operations, and use short-lived access links for large objects when suitable.

## 13. Testing strategy: automated, browser-based, and real-data

Tests are a deliverable, not a final checkbox. Use unit tests, API integration tests, worker tests, browser E2E tests, and GPU end-to-end smoke tests. Keep the CPU-only test suite fast and deterministic; keep real neural inference behind a separately identified integration test profile.

### Unit and contract tests

Test video validation, telemetry parsing, keyframe selection, coordinate transforms, pose convention conversions, artifact manifests, event schema/versioning, state transitions, authorization, retry/cancellation behavior, and output validation. Create regression fixtures for bugs. Test malformed files, absent telemetry, invalid timestamps, wrong coordinate frames, duplicate/out-of-order events, disconnected browsers, cancellation, CUDA OOM fallback, and partial-stage failures.

### FastAPI/worker integration tests

Use temporary test storage/database or isolated containers as appropriate. Test upload → validate → create job → worker stage events → artifacts → output inventory. Test video-only path and telemetry-assisted path separately. Ensure optional dependencies and model weights are not downloaded during ordinary tests.

### Playwright end-to-end tests (required)

Run the application in an actual browser with Playwright. Do not substitute React component tests for E2E. Create flows that cover:

1. Landing/dashboard loads without console errors and the design is coherent at desktop and mobile viewports.
2. Video upload UI handles progress, wrong file types, invalid/corrupt media, size/duration errors, retries, and cancellation.
3. Telemetry is optional; the user can submit a valid video without attaching it. When telemetry is present, the UI accurately identifies what was accepted.
4. Preflight warnings are visible and actionable.
5. Starting a job displays truthful state transitions; progress/events appear from the actual test backend contract.
6. A valid partial point-cloud artifact appears in the R3F viewer before final job completion; later artifact revisions update it without losing user navigation state.
7. Viewer controls, layer toggles, camera reset/fit, scale/frame labels, measurement interactions, and confidence legend work where artifacts support them.
8. Completion state appears only after final job success; completion sound/haptics hooks execute at most once and degrade gracefully when unsupported or blocked.
9. Failure/cancellation/reconnect/retry states remain understandable and do not strand the user.
10. Export/download links, report metadata, and output inventory are correct.
11. Responsive layout, keyboard navigation, focus visibility, reduced-motion, and accessibility basics work.

Use a deterministic **test pipeline adapter** for normal CI E2E so tests are reproducible without GPU or model downloads. It must emit valid, small, real-format fixture artifacts through the same API/event contracts, not bypass the app with fabricated frontend-only state. Explicitly label these tests as test-pipeline mode.

### Use the provided `docs/sample/video` for a real pipeline E2E test

- Locate the exact provided video and confirm that it decodes; do not invent a substitute silently.
- Run the real preprocessing and, when the GPU environment is available, run the real reconstruction pipeline against this sample. Use optional telemetry from `docs/` if provided; also verify the video-only path if no telemetry is present.
- Follow the full browser workflow: upload the sample through the UI, start the job, observe real stage events and artifact creation, inspect progressive geometry in React Three Fiber, wait for the true final state, and verify the output inventory and report.
- Capture Playwright trace/video/screenshots and API/worker logs. Inspect actual downloaded/exported artifacts for non-empty data, parseability, finite coordinates, sensible bounds, coordinate metadata, and a renderable point cloud/mesh.
- Keep expensive GPU E2E tests separately addressable (for example, `test:e2e:gpu`) from the fast deterministic suite. Record hardware, GPU/VRAM, runtime, model versions, settings, time to first preview, final processing duration, and peak memory. Do not present a mocked job as evidence that the real neural pipeline passed.
- If the path is missing or the VDI/GPU cannot access it, search the repository and available mounted workspace accurately, then report the specific blocker. Continue all independent tests and implementation work rather than pretending the test ran.

### Visual QA

After major UI changes, use Playwright screenshots at representative viewport sizes. Check spacing, contrast, typography, overflow, hover/focus/disabled/loading states, and 3D viewport behavior. Compare with `docs/design.md`, make corrections, and re-capture. When a test fails, inspect its trace and network/console output, fix the root cause, and rerun. Keep failure screenshots/traces as CI artifacts; do not commit sensitive videos or real drone data unless approved.

## 14. Performance and accuracy evaluation

Treat “fast” and “accurate” as measurable goals, not marketing claims. The target is a useful first preview as soon as valid geometry exists and a robust complete artifact set in a practical time for the actual GPU.

Record at minimum:

- upload and preprocessing duration
- each model/stage runtime
- queue wait time and total end-to-end runtime
- time to first usable 3D preview
- peak GPU VRAM, system RAM, disk usage, and max tested resolution/frame count
- worker throughput and cancellation/retry outcomes
- rendering frame rate/responsiveness for representative point counts
- export size and successful downstream parsing/rendering

Evaluate geometry independently where reference geometry is available: point-cloud-to-reference distance or a documented Chamfer variant, cloud-to-cloud/cloud-to-mesh distance, completeness at a stated tolerance, reprojection error, camera pose error, dimensions of known objects/distances, and mesh artifacts. Evaluate geospatial horizontal/vertical error only when the reference/vertical datum support it. Do not treat a visual render or a model's self-reported confidence as ground truth.

Run ablations when feasible: geometry only; geometry + depth priors; geometry + valid sensor fusion; geometry + dynamic masks; combined pipeline; point-cloud versus Gaussian versus mesh. Explain which stages improve measurable outputs, and which increase cost without demonstrable gain. Define numerical acceptance thresholds only after assessing target data/use case and documenting the rationale.

## 15. Reliability, deployment, and maintainability

- Use configuration-driven paths and endpoints, structured logs with job/stage correlation IDs, and meaningful exceptions.
- Add `/health` and readiness checks that distinguish API availability from worker, database, queue, storage, and GPU readiness.
- Add graceful service shutdown, bounded worker concurrency, job cancellation, checkpoints, artifact checksums, disk-space checks, and transient-failure retries.
- Support a local/offline development path wherever possible; do not make routine processing depend on unneeded external API calls.
- Provide reproducible setup scripts and pin dependency/model/runtime combinations that have actually been tested. Keep incompatible research components isolated.
- Record the exact minimum system, Python/CUDA/PyTorch, driver, package, and model-weight requirements for the college GPU setup. Do not use a laptop as the only proof that CUDA execution works remotely.
- Provide a deployment path for the web/API services and a separate documented path for the college GPU worker. Clearly state port, authentication, network, file-transfer, session-lifetime, and persistence assumptions. Never expose a GPU worker publicly without authentication and an approved deployment route.
- Include backup/retention/deletion policies for sensitive video and reconstruction outputs. Keep original inputs immutable unless the user explicitly requests deletion.
- Avoid speculative abstractions, duplicated state, hidden magic, broad `any` types, dead code, swallowed exceptions, unbounded memory, and critical paths represented by TODOs.

## 16. Required milestones after Gate 1

After the user says `continue`, work through these milestones, adapting the order when an experiment shows a better path. Each milestone must have a working demo, tests, and a status update.

1. **Environment and hardware validation:** confirm safe access to the college GPU, software versions, limits, storage, and a feasible worker communication method.
2. **Contracts and ingestion:** video upload, optional telemetry parsing, validation, frame extraction, quality scoring, keyframes, manifest, and sample-video test.
3. **First honest reconstruction preview:** integrate Fast3R or a clearly documented tested alternative, produce real pointmap/pose output, display a point cloud using React Three Fiber, and stream artifact availability.
4. **Progressive job infrastructure:** real event channel, reconnect/replay, job state machine, cancellation, checkpointing, artifact manifests, and idempotency.
5. **Depth priors and fusion:** Metric3D-v2 and GTSAM only where supported, with coordinate/scale tests and ablations.
6. **Dynamic objects:** YOLO/SAM2 mask/track integration with confidence and performance tests.
7. **Dense visual representation and surface:** Open3D, InstantSplat/compatible renderer, SuGaR/Poisson as evidence permits; validate resource demands and actual artifact compatibility.
8. **Full inspection workflow:** camera path, layer toggles, measurements, confidence/provenance, geospatial view where valid, exports, and report.
9. **Polish pass:** responsive UI, animation, sound/haptics, accessibility, loading/error/empty states, and design-system consistency.
10. **Full verification and hardening:** browser E2E, real sample video pipeline run, GPU profiling, regression tests, failure handling, docs, and demo walkthrough.

Do not force linear progression when early tests expose a blocker: fix foundational integration contracts before adding another model. Keep the first end-to-end vertical slice working at all times.

## 17. Definition of done — do not declare completion before this

The project is complete only when all applicable items below are true and supported by actual evidence:

### Foundation
- Turborepo monorepo with TypeScript web application and Python/FastAPI backend is documented and reproducible.
- Required local services, environment variables, and college GPU setup are explained; no secrets are tracked or exposed.
- Clean install, lint/type checks, and unit/integration suites run with documented commands.

### Product functionality
- A user can create/open a mission, upload a drone video without telemetry, optionally supply telemetry/calibration, see validation warnings, and start processing.
- A real asynchronous worker runs stages and the UI reflects actual job state.
- The first valid geometry is shown in React Three Fiber before the entire pipeline completes, and subsequent valid results progressively refine the same scene.
- Job reconnect/cancel/failure/retry behavior is sound; no fake progress or fake reconstruction is presented as real.
- Final outputs and report are listed and downloadable; coordinate frame, units, sources, model versions, warnings, and provenance are clear.
- The UI follows `docs/design.md` and includes tested responsive layouts, useful animation, accessible feedback, and graceful optional sound/haptics.

### Verification
- Playwright browser E2E tests run and pass for the main user journey using the deterministic test pipeline.
- The provided sample video has been exercised through actual preprocessing and, when the GPU is available, a real reconstruction run. Clearly distinguish any completed CPU-only checks from GPU/model stages that could not run.
- Progressive artifact rendering, final output parsing/validity, and exports have been inspected—not merely asserted from a mocked API response.
- Real performance, memory, and geometry results are recorded with hardware/model/config context. Unsupported accuracy or speed claims are removed.
- Critical failures have been fixed and regression tests added. No important UI button is inert, no critical route is a placeholder, no known severe console/network error remains, and the README explains how to run and test the product.

If one acceptance item depends on college privileges, unavailable GPU capacity, inaccessible model weights, a missing sample, or another external blocker, do not fake completion. Finish every independent task, document the evidence and exact blocker, ask one concrete question or provide the required action, and resume as soon as unblocked.

## 18. How to report progress to the user

Give short, useful updates at milestone boundaries and when a blocker is discovered. Each update should state what actually changed, what was tested, the result, and what comes next. Avoid vague updates such as “working on it” or claiming the project is almost done without evidence.

At the end of each milestone, provide:

- **Implemented:** concrete files/features/behavior.
- **Verified:** actual commands/tests/browser flows run and pass/fail results.
- **Performance/accuracy evidence:** only measured values, with hardware/config context.
- **Known limitations:** specific remaining issues and their impact.
- **Next step:** the next action in `docs/IMPLEMENTATION_STATUS.md`.

At final completion, provide exact setup/run/test commands, architecture overview, VDI/GPU operating instructions, the actual sample-video test result, model/license/version records, performance/accuracy metrics, artifact/export formats, and any genuine remaining caveats. Do not bury important failures in the final summary.

---

## Final execution instruction

Begin by inspecting the current repository and reading the full `docs/` contents and supplied materials. Ask only genuinely blocking questions that those sources cannot answer. Then implement **Stage 1 only**—the Turborepo/TypeScript + FastAPI scaffold, design-respecting base UI, test foundation, blank environment placeholders, and status/setup documentation. Run the Gate 1 checks, give the user the exact blank environment variables to fill locally, and **STOP**. Wait for the user to fill them and explicitly say `continue`. After that, follow the full iterative implementation and verification loop above until the real end-to-end acceptance criteria are met.
