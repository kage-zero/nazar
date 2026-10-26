# Single-Pass Drone Video to Accurate 3D Model Generation System

## Detailed Project Documentation

**Organization:** National Technical Research Organisation (NTRO)\
**Theme:** Robotics and Drones \| **Category:** Software\
**Purpose:** End-to-end technical blueprint for the proposed SIH
project.

> **Status note:** This document describes a proposed architecture.
> Accuracy, runtime, and cost benefits must be demonstrated
> experimentally before being presented as measured results.

## Table of Contents

1.  Executive Summary
2.  Problem Statement and Goals
3.  Inputs, Outputs, and Scope
4.  Challenges and Design Principles
5.  End-to-End Architecture
6.  Module 1 --- Data Preparation
7.  Module 2 --- Fast3R Multi-View Geometry
8.  Module 3 --- Metric3D-v2 Depth Priors
9.  Module 4 --- Dynamic Objects with YOLO and SAM2
10. Module 5 --- GTSAM Sensor Fusion
11. Module 6 --- Open3D and InstantSplat
12. Module 7 --- Surface and Geospatial Processing
13. Module 8 --- Analysis and Confidence
14. Frontend Application
15. Backend and API
16. Database, Storage, and Caching
17. Technology Stack
18. Security, Reliability, and Provenance
19. Feasibility and Viability
20. Risks and Mitigations
21. Evaluation and Testing
22. Implementation Roadmap
23. Deployment Architecture
24. Applications and Benefits
25. Reference Links
26. Demo Plan and Final Recommendations

------------------------------------------------------------------------

# 1. Executive Summary

This project proposes a software system that converts drone video
captured during a single flight pass into a useful 3D representation of
the observed environment. It consumes video and available navigation
metadata, prepares and synchronizes frames, estimates multi-view
geometry and depth, handles dynamic objects, fuses visual estimates with
sensor observations, builds dense 3D representations, extracts surfaces,
transforms coordinates, and presents outputs through an interactive
application.

A single pass often provides less viewpoint diversity than a
conventional mapping mission. Near-straight motion can provide limited
lateral parallax, making depth estimation less constrained. Blur,
compression, low-texture surfaces, occlusions, lighting changes, dynamic
objects, sensor noise, and timing errors can further reduce
reconstruction quality. The proposed solution combines learned
multi-view geometry and metric-depth priors with explicit sensor
constraints and conventional geometry-processing tools.

The pipeline is:

1.  **Data preparation:** FFmpeg and OpenCV ingest video, extract and
    score frames, select keyframes, and synchronize metadata.
2.  **Multi-view geometry:** Fast3R estimates camera poses and
    pointmaps.
3.  **Depth priors:** Metric3D-v2 predicts monocular metric depth and
    surface normals where supported.
4.  **Dynamic-object handling:** YOLO detects objects and SAM2
    segments/tracks them; masks can prevent moving objects from
    contaminating the static reconstruction.
5.  **Metric reconstruction:** GTSAM optimizes visual poses with
    available GPS/GNSS, IMU, barometric-altitude, and RTK/PPK
    constraints.
6.  **Dense reconstruction:** Open3D supports point-cloud processing;
    InstantSplat supports Gaussian-scene reconstruction and
    visualization.
7.  **Surface/geospatial processing:** SuGaR and Poisson reconstruction
    support mesh generation; GDAL/PROJ/PyProj handle coordinate
    transformations.
8.  **Analysis and confidence:** measurements and overlays distinguish
    observed, estimated, and inferred geometry.

The intended deliverables include point clouds, Gaussian scenes, meshes
where supported by the data, camera trajectories, geospatial outputs
when a valid reference is available, measurements, confidence
indicators, and exportable artifacts. A visually convincing rendering is
not by itself proof of metric accuracy. Every result should carry its
coordinate frame, units, provenance, and limitations.

# 2. Problem Statement and Goals

## 2.1 Problem

High-quality aerial reconstruction often benefits from overlapping
images captured from multiple positions and angles. Single-pass footage
may have limited viewpoint diversity. The goal is to recover useful 3D
geometry from this constrained input by combining learned geometry,
depth priors, sensor measurements, and careful quality control.

## 2.2 Primary goals

-   Convert a single-pass drone video and available telemetry into 3D
    deliverables.
-   Improve robustness when viewpoint diversity is limited.
-   Use metric-depth priors as supporting information, not
    unquestionable ground truth.
-   Use sensor observations to constrain trajectory, scale, and
    geographic alignment.
-   Reduce static-scene contamination from moving objects.
-   Provide both analytical geometry and an interactive visual scene.
-   Make coordinate systems, units, confidence, and provenance explicit.
-   Provide a web workflow for upload, processing status, inspection,
    measurement, and export.
-   Evaluate accuracy and performance against independent references
    where possible.

## 2.3 Non-goals and limitations

The system does not guarantee perfect reconstruction of hidden surfaces,
survey-grade accuracy from consumer GPS, real-time performance on all
hardware, or global WGS84 alignment without a suitable global reference.
It does not assume every drone/camera combination is compatible without
testing. Mesh filling does not recover ground truth for unseen areas,
and Gaussian rendering is not automatically suitable for precise
measurements.

# 3. Inputs, Outputs, and Scope

## 3.1 Mandatory inputs

-   **Drone video:** typically 1080p or 4K, depending on the source.
-   **GPS/GNSS coordinates:** time-stamped positions when available.
-   **Flight metadata:** timestamps and available camera/navigation
    records.

## 3.2 Optional inputs

-   **IMU:** angular velocity and acceleration, with timestamps and
    calibration where available.
-   **Barometric altitude:** additional vertical-motion observation.
-   **Camera intrinsics:** focal lengths, principal point, image
    dimensions, and lens-distortion parameters.
-   **RTK/PPK data:** higher-quality GNSS positions when valid
    corrections are available.
-   **Calibration metadata:** camera-to-IMU extrinsics, antenna offsets,
    rolling-shutter details, and coordinate reference information.

The system must tolerate missing optional inputs, record which sources
were used, and explain the expected impact of missing or low-quality
data. Missing values must not be silently fabricated.

## 3.3 Expected outputs

-   Dense or semi-dense 3D point cloud.
-   Gaussian scene for interactive, view-dependent rendering.
-   Mesh or textured mesh when observations support surface extraction.
-   Camera trajectory and camera poses.
-   Georeferenced scene when a valid global reference is available.
-   Measurements such as distances, heights, areas, and selected object
    locations.
-   Confidence labels for observed, estimated, and inferred regions.
-   Exports for GIS, 3D viewers, engineering review, and downstream
    analysis.
-   Processing report with settings, warnings, versions, and coordinate
    metadata.

## 3.4 Define "accuracy" correctly

Evaluate distinct properties separately: - **Relative geometry:**
consistency of local shapes and relative positions. - **Metric
accuracy:** closeness of dimensions to real-world measurements. -
**Trajectory accuracy:** camera position/orientation error against
reference data. - **Geographic accuracy:** alignment to a stated
coordinate reference system. - **Completeness:** how much visible
geometry is represented. - **Visual fidelity:** how convincing the
rendering looks.

These properties are related but not interchangeable.

# 4. Challenges and Design Principles

## 4.1 Limited parallax

Near-collinear motion can make depth weakly constrained. Learned
geometry may help, but it cannot create evidence for surfaces that were
never observed. Confidence should fall when viewpoint diversity is weak.

## 4.2 Video quality

Blur, rolling shutter, compression, exposure changes, shadows,
reflections, and low-texture surfaces can damage estimation.
Preprocessing should be conservative and preserve originals.

## 4.3 Timing and calibration

Video/telemetry clock offsets, incorrect intrinsics, camera-to-IMU
extrinsics, antenna lever arms, and coordinate-convention errors can
cause systematic alignment problems.

## 4.4 Dynamic objects

People, vehicles, animals, moving vegetation, and water violate
static-scene assumptions. Detection is not proof of motion; tracking and
temporal reasoning are needed.

## 4.5 Occlusions

A single pass cannot see every building facade or the ground behind
vegetation. Hidden geometry must be marked as uncertain rather than
presented as observed truth.

## 4.6 Accuracy--latency--compute trade-off

Neural inference, segmentation, point-cloud processing, Gaussian
optimization, and meshing can be GPU- and memory-intensive. Sliding
windows, caching, staged outputs, and configurable quality modes help
control resource use. "Near-real-time" is a target to measure, not a
guaranteed property.

## 4.7 Design principles

1.  Separate analytical geometry from visual rendering.
2.  Treat learned predictions as estimates and use confidence-aware
    fusion.
3.  Record sensor availability and measurement quality.
4.  Define coordinate frames and units at every interface.
5.  Preserve source data and processing provenance.
6.  Mark inferred geometry and avoid claims unsupported by evidence.
7.  Validate components independently before full integration.

# 5. End-to-End Architecture

``` text
DRONE VIDEO + GPS/GNSS + FLIGHT METADATA
                  |
                  v
       1. DATA PREPARATION
        FFmpeg + OpenCV
                  |
                  v
       2. MULTI-VIEW GEOMETRY
                Fast3R
       Camera poses + pointmaps
                  |
         +--------+--------+
         |                 |
         v                 v
  Metric3D-v2          YOLO + SAM2
  depth/normal        object masks/tracks
         |                 |
         +--------+--------+
                  v
       3. METRIC RECONSTRUCTION
        GTSAM + sensor fusion
                  |
                  v
       4. DENSE 3D RECONSTRUCTION
         Open3D + InstantSplat
       Point cloud + Gaussian scene
                  |
                  v
       5. SURFACE / GEO PROCESSING
       SuGaR + Poisson + GDAL/PyProj
                  |
                  v
       6. ANALYSIS & CONFIDENCE
       Measurements + uncertainty labels
                  |
                  v
        WEB VIEWER + EXPORTS
```

This is a conceptual flow, not a strict execution schedule. In practice,
depth priors, object masks, and sensor constraints may feed back into
refinement. Exact integration depends on the selected versions and
supported data formats.

## 5.1 Coordinate-frame policy

The pipeline may involve: - Camera frame. - Drone-body or IMU frame. -
Local reconstruction frame. - ENU (East-North-Up). - ECEF
(Earth-Centered, Earth-Fixed). - Geographic latitude/longitude/height. -
Projected coordinates such as a suitable UTM zone.

Never treat latitude/longitude as Cartesian metres. Record CRS, axis
order, units, datum, and vertical reference. Ellipsoidal GNSS height and
barometric altitude may use different vertical references. A coordinate
transform cannot repair a bad trajectory or calibration.

# 6. Module 1 --- Data Preparation

**Tools:** FFmpeg, OpenCV, NumPy, SciPy, Python.

## Purpose

Create a consistent, quality-controlled frame sequence and synchronized
telemetry timeline.

## Processing steps

1.  **Validate files:** verify video decodability, resolution, frame
    rate, duration, timestamps, and telemetry schema.
2.  **Extract frames:** retain original frame index and timestamp; avoid
    silently changing aspect ratio or orientation.
3.  **Assess quality:** estimate blur, exposure clipping, dark frames,
    duplicates, and severe compression artifacts.
4.  **Normalize cautiously:** apply conservative exposure/color handling
    only where helpful; preserve original frames.
5.  **Stabilize if needed:** record transformations and verify that
    warping has not distorted useful geometry. Stabilization does not
    replace pose estimation.
6.  **Select keyframes:** consider sharpness, temporal spacing, visual
    novelty, viewpoint change, overlap, and sensor availability.
7.  **Synchronize sensors:** normalize timestamps, identify clock
    offsets, interpolate only within defensible intervals, and report
    missing ranges.
8.  **Create manifest:** record selected frames, quality scores,
    timestamps, configuration, calibration, and warnings.

## Inputs

Video, GPS/GNSS logs, flight metadata, optional IMU/barometric/RTK/PPK
logs, and camera calibration.

## Outputs

Prepared frames, frame manifest, synchronized telemetry tables,
calibration metadata, quality scores, and validation logs.

## Failure handling

  -----------------------------------------------------------------------
  Failure                 Detection               Mitigation
  ----------------------- ----------------------- -----------------------
  Corrupt video           Decoder errors          Report affected
                                                  segment; allow partial
                                                  processing

  Severe blur             Quality score and       Exclude or down-weight
                          visual check            frames

  Time mismatch           Trajectory              Validate clock
                          inconsistency           conventions and offsets

  Unknown intrinsics      Missing calibration     Use documented
                                                  estimation path and
                                                  mark uncertainty

  Too few keyframes       Poor viewpoint coverage Relax selection
                                                  thresholds and compare
                                                  results
  -----------------------------------------------------------------------

# 7. Module 2 --- Fast3R Multi-View Geometry

**Tools:** Fast3R, PyTorch, CUDA, NumPy, SciPy.

## Purpose

Estimate multi-view 3D structure and camera poses from selected images.

## Processing

1.  Arrange frames into a sequence or batch supported by the chosen
    Fast3R implementation.
2.  Run inference using the model's expected image preparation.
3.  Retrieve per-view pointmaps and camera-pose estimates.
4.  Preserve confidence/validity outputs if exposed.
5.  Normalize coordinate conventions and map every result to its source
    frame.
6.  Align overlapping geometry into a consistent reconstruction frame.
7.  Produce diagnostics for inconsistent or failed views.

## Key concepts

A **pointmap** associates image pixels with 3D points in a coordinate
frame. It is not automatically a georeferenced point cloud. A **camera
pose** represents position and orientation, but implementations may use
camera-to-world or world-to-camera conventions; this must be checked.

## Limitations

Fast3R alone does not guarantee absolute geographic alignment, perfect
hidden-surface recovery, or survey-grade scale. It may struggle with
blur, repetitive textures, unusual viewpoints, and domain shift. Its
role here is multi-view geometry, not conventional temporal object
tracking.

## Outputs

Pointmaps, camera poses, confidence/validity information where
available, frame associations, coordinate metadata, and diagnostics.

## Integration checklist

-   Confirm output schema and coordinate conventions for the exact model
    version.
-   Test supported image sizes, batching, and VRAM requirements.
-   Compare geometry against scenes with known dimensions.
-   Validate compatibility with Open3D and the InstantSplat adapter.
-   Do not assume InstantSplat directly accepts arbitrary Fast3R outputs
    without conversion.

# 8. Module 3 --- Metric3D-v2 Depth and Normal Priors

**Tools:** Metric3D-v2, PyTorch, CUDA, OpenCV, NumPy.

## Purpose

Provide monocular depth and surface-normal predictions as supporting
priors in weakly constrained regions.

## Processing

1.  Prepare each image according to the selected model's input
    requirements.
2.  Run inference.
3.  Convert depth and normals into the pipeline's representation.
4.  Validate invalid, extreme, or inconsistent values.
5.  Associate each map with its frame and camera.
6.  Compare predictions with Fast3R geometry and sensor-constrained
    results.
7.  Fuse or use the priors as regularization only after reconciling
    scale, units, and confidence.

## Appropriate uses

-   Supporting foreground/background ordering.
-   Creating candidate dense points.
-   Regularizing geometry where multi-view evidence is weak.
-   Checking gross disagreement between depth and pointmaps.
-   Supporting surface-orientation estimation.

## Caution

Metric-depth capability does not imply survey-grade accuracy in every
scene. Error varies with scene type, camera, object scale, and domain
shift. Depth predictions should not automatically override reliable
multi-view or calibrated sensor evidence.

## Outputs

Depth maps, surface-normal maps where available, validity/confidence
metadata, and records of preprocessing and units.

# 9. Module 4 --- Dynamic Objects with YOLO and SAM2

**Tools:** YOLO, SAM2, OpenCV, PyTorch, NumPy.

## Purpose

Reduce moving-object contamination and optionally show dynamic-object
tracks separately from the static scene.

## Processing

1.  Detect relevant objects in selected frames with YOLO.
2.  Initialize masks/tracks with SAM2 using the chosen supported
    workflow.
3.  Propagate masks across frames.
4.  Associate tracks and estimate temporal movement when evidence
    allows.
5.  Generate per-frame masks and track metadata.
6.  Use masks during geometry fusion or Gaussian optimization where
    supported.
7.  Record tracking confidence and failures.

Detection is not proof of motion. A detected car may be parked;
vegetation may move; and camera motion complicates apparent motion. Use
temporal reasoning.

## User options

-   **Exclude from static reconstruction:** mask moving objects to
    reduce ghosting.
-   **Keep as a dynamic annotation:** show a selected position and
    estimated direction/trajectory when tracking is reliable.
-   **Preserve a time-specific observation:** retain an object as seen
    at a selected timestamp without merging multiple positions into a
    false static object.

## Outputs

Masks, track IDs, trajectory estimates where supported, reconstruction
exclusion masks, confidence, and failure flags.

## Limitations

Fast motion, occlusion, low resolution, and poor lighting can break
tracks. Masking an object can expose a hole because the hidden
background was never observed. Do not fabricate that background without
marking it as inferred.

# 10. Module 5 --- Metric Reconstruction with GTSAM

**Tools:** GTSAM, GPS/GNSS, IMU, barometric altitude, RTK/PPK when
available, NumPy, SciPy, PyProj.

## Purpose

Use available sensor measurements to constrain visual poses, reduce
drift, improve metric consistency, and establish geographic alignment
when sufficiently referenced.

## Possible state variables

Depending on data and observability: - Camera/drone poses. - Velocity. -
IMU biases. - Landmark variables. - Calibration or time-offset variables
only when the data supports estimating them. - Global alignment
parameters.

## Potential factors

-   Visual relative-pose constraints.
-   GPS/GNSS position observations.
-   IMU preintegration constraints for calibrated IMU data.
-   Barometric altitude constraints with realistic bias/noise.
-   RTK/PPK positions when correction quality is known.
-   Prior factors and reliable loop-closure constraints where available.

## Workflow

1.  Normalize timestamps and coordinate frames.
2.  Initialize poses from Fast3R.
3.  Build factors from available visual and sensor data.
4.  Set noise models based on realistic measurement quality.
5.  Optimize trajectory and supported variables.
6.  Inspect residuals, outliers, and convergence.
7.  Align/refine pointmaps using optimized poses.
8.  Store diagnostics and uncertainty information where possible.

## Scale and geographic alignment

GNSS, calibrated inertial information, and other metric constraints can
help establish scale and geographic placement. Consumer GPS may be too
noisy for fine building alignment; IMU integration drifts without
constraints; barometric altitude may have bias; RTK/PPK depends on
correction and fix quality. Robust losses and outlier handling are
important.

## GPS-denied operation

Visual geometry and calibrated inertial information may support a
**local reconstruction**. Absolute WGS84 alignment requires a valid
global reference or later registration. The interface must clearly
distinguish local-frame from georeferenced output.

## Outputs

Optimized trajectory, poses, alignment parameters, coordinate metadata,
sensor-use report, residuals, and quality flags.

# 11. Module 6 --- Dense Reconstruction with Open3D and InstantSplat

**Tools:** Open3D, InstantSplat, PyTorch, CUDA, NumPy.

## 11.1 Open3D: analytical point clouds

Open3D supports pointmap/depth conversion, point-cloud filtering, voxel
downsampling, normal estimation, registration, merging, bounding boxes,
and preparation for surface reconstruction.

Important practices: - Preserve point provenance and confidence where
possible. - Check alignment before merging pointmaps. - Keep units and
coordinate frames consistent. - Choose voxel size according to target
detail. - Avoid removing thin structures solely because they are sparse.

## 11.2 InstantSplat: visual scene

InstantSplat is used as a sparse-view Gaussian
reconstruction/optimization component for interactive visualization.

Conceptual steps: 1. Prepare images and camera poses. 2. Initialize the
scene using a supported initialization path. 3. Optimize Gaussian
parameters and supported camera parameters. 4. Render views and compare
them with observed images using the implementation's losses. 5. Save the
scene and renderer metadata. 6. Validate against observed or held-out
frames where possible.

The precise adapter depends on the selected implementation. Confirm
camera conventions, initialization format, point representation, image
preprocessing, and model requirements.

## 11.3 Why keep both?

-   **Point cloud:** filtering, registration, and spatial analysis.
-   **Gaussian scene:** fast, view-dependent visual rendering.
-   **Mesh:** surface-oriented downstream workflows.

A Gaussian scene can look convincing while being unsuitable for precise
measurement. Use validated geometry for metric tasks and show
uncertainty.

## Outputs

Cleaned point cloud, Gaussian scene, diagnostics, intermediate surface
data, coordinate metadata, and provenance.

# 12. Module 7 --- Surface and Geospatial Processing

**Tools:** SuGaR, Poisson Surface Reconstruction, Open3D, GDAL, PROJ,
PyProj, Shapely.

## Purpose

Extract mesh surfaces where supported by evidence, transform
coordinates, and export usable 3D/GIS deliverables.

## SuGaR and Poisson

SuGaR supports surface-oriented extraction from compatible Gaussian
representations. Poisson reconstruction can create smooth surfaces from
oriented points, but may oversmooth details, bridge gaps, or create
surfaces in weakly observed regions. Inspect holes, spikes, normals,
disconnected components, and scale. Surface completion is not proof that
hidden geometry is correct.

## Geospatial processing

-   Choose a local or global coordinate frame appropriate to the
    mission.
-   Use GDAL/PROJ/PyProj for supported transformations.
-   Use ENU for local metric work and a suitable UTM zone or geographic
    CRS where appropriate.
-   Record source/destination CRS, units, axis order, datum, and
    vertical reference.
-   Validate transformations using known points or independent checks.

## Export formats

  -----------------------------------------------------------------------
  Format                  Typical use             Caution
  ----------------------- ----------------------- -----------------------
  PLY                     Point clouds and some   CRS metadata support
                          meshes                  varies

  LAS/LAZ                 GIS point-cloud         Correct scale, offset,
                          exchange                CRS, and classification
                                                  are essential

  OBJ                     Mesh exchange           Textures/materials may
                                                  be separate

  GLB/glTF                Interactive 3D viewing  Not a full GIS metadata
                                                  container

  GeoTIFF                 Raster                  Requires valid
                          elevation/derived       rasterization and CRS
                          products                

  GeoJSON                 Geographic vectors and  Not designed for dense
                          annotations             3D surfaces
  -----------------------------------------------------------------------

## Mesh validation

Check non-finite coordinates, dimensions, units, normals, winding,
disconnected parts, large holes, spikes, and independent dimensional
accuracy. Preserve intermediate outputs for repeatable processing.

# 13. Module 8 --- Analysis, Measurements, and Confidence

## Confidence categories

-   **Observed:** strong direct image evidence and consistent multi-view
    support.
-   **Estimated:** inferred from model predictions or incomplete
    evidence but with some support.
-   **Inferred:** completed or hypothesized where direct observations
    are weak or absent.

These are product labels, not automatically calibrated statistical
probabilities.

## Possible confidence signals

-   Model confidence/validity.
-   Number of supporting views.
-   Viewpoint diversity and parallax.
-   Reprojection and alignment residuals.
-   Agreement between pointmaps and depth priors.
-   Sensor-factor residuals.
-   Image quality and occlusion masks.
-   Distance from strongly observed points.
-   Surface reconstruction support and hole-filling status.

Do not present a single probability unless the confidence calculation is
calibrated and validated.

## Measurements

Potential tools include point-to-point distance, polyline length, height
relative to a defined plane, polygon/mesh area, bounding-box dimensions,
and object position. Show units and quality indicators. Explain when a
measurement is unreliable due to sparse geometry, occlusion, or weak
georeferencing.

## Damage analysis

A future analysis layer may flag visible changes or unusual structural
patterns. It should not assert structural safety/failure without
domain-specific validation, baseline data, and expert interpretation.

# 14. Frontend Application

**Stack:** React, TypeScript, React Three Fiber, Three.js, Drei,
Tailwind CSS, Zustand, MapLibre GL JS, Axios.

## User journey

1.  Create project/mission.
2.  Upload video, telemetry, and optional calibration.
3.  Review validation warnings.
4.  Start processing and monitor stage status.
5.  Open the 3D viewer.
6.  Toggle point cloud, Gaussian scene, mesh, trajectory, dynamic
    tracks, and confidence layers.
7.  Measure geometry and add annotations.
8.  Review sensor usage and processing warnings.
9.  Export outputs and report.

## Suggested screens

-   **Project dashboard:** projects, missions, status, thumbnails,
    recent results.
-   **Upload/setup:** assets, CRS, units, calibration, validation
    summary.
-   **Processing monitor:** current stage, logs, warnings, cancel/retry.
-   **3D viewer:** layer controls, camera path, axes, scale, confidence
    legend, measurements.
-   **Map view:** trajectory and footprint in MapLibre, with CRS clearly
    stated.
-   **Report/export:** output inventory, model versions, settings,
    sensor usage, metrics, warnings, and file formats.

## Frontend design guidance

Use Zustand for small UI state such as selected project, viewer layers,
selected measurement, and active annotations. Avoid putting large point
clouds or textures into global state. Use progressive loading and
level-of-detail for large assets. Clearly distinguish local coordinates
from global coordinates and analytical geometry from visual rendering.

# 15. Backend and API

**Stack:** Python, FastAPI, Pydantic, Celery, SQLAlchemy, WebSocket.

## Responsibilities

-   Validate uploads and mission metadata.
-   Manage projects, missions, jobs, and artifact metadata.
-   Queue long-running work.
-   Report stage progress and errors.
-   Serve authorized artifact metadata and exports.
-   Maintain logs and processing provenance.

GPU inference should not block normal API request handlers. The API
should create a job and return an ID; dedicated workers process it
asynchronously.

## Proposed API surface

These are design suggestions, not existing endpoints.

  Method   Endpoint                        Purpose
  -------- ------------------------------- --------------------------
  POST     `/api/projects`                 Create project
  GET      `/api/projects`                 List authorized projects
  POST     `/api/projects/{id}/missions`   Create mission
  POST     `/api/missions/{id}/assets`     Register/upload assets
  POST     `/api/missions/{id}/validate`   Validate inputs
  POST     `/api/missions/{id}/jobs`       Start reconstruction
  GET      `/api/jobs/{id}`                Read status
  POST     `/api/jobs/{id}/cancel`         Request cancellation
  GET      `/api/missions/{id}/outputs`    List outputs
  POST     `/api/outputs/{id}/exports`     Create export
  WS       `/api/jobs/{id}/events`         Receive progress events

## Suggested job states

`created`, `validating`, `queued`, `preprocessing`, `geometry`,
`depth_priors`, `dynamic_analysis`, `sensor_optimization`,
`dense_reconstruction`, `surface_processing`, `analysis`, `exporting`,
`completed`, `failed`, `cancel_requested`, `cancelled`.

Validate state transitions and retain a human-readable failure reason
and stage logs. Tasks should be idempotent where practical, write
outputs atomically, and checkpoint intermediate results.

# 16. Database, Storage, and Caching

**Stack:** PostgreSQL, PostGIS, Redis, MinIO.

-   **PostgreSQL/SQLAlchemy:** projects, missions, assets, jobs,
    settings, output inventory, annotations, evaluation results.
-   **PostGIS:** trajectories, footprints, geographic annotations,
    spatial metadata with explicit SRIDs.
-   **MinIO:** original video, frames, point clouds, meshes, Gaussian
    scenes, masks, depth maps, reports, and export archives.
-   **Redis:** queue/cache/temporary coordination where appropriate; not
    the only durable store for important records.

Define retention and deletion policies, backups, access control,
encryption, and handling of sensitive mission data. Store large binary
artifacts in object storage rather than ordinary relational rows.

# 17. Technology Stack and Rationale

  -----------------------------------------------------------------------
  Layer                   Technologies            Role
  ----------------------- ----------------------- -----------------------
  Frontend                React, TypeScript       Web UI

  3D viewer               React Three Fiber,      Interactive 3D
                          Three.js, Drei          

  UI/state                Tailwind CSS, Zustand   Styling and UI state

  Map                     MapLibre GL JS          2D geographic context

  HTTP                    Axios                   API calls

  API                     Python, FastAPI,        Typed service layer
                          Pydantic                

  Jobs                    Celery, Redis           Async processing

  ORM/database            SQLAlchemy, PostgreSQL  Metadata

  Spatial DB              PostGIS                 Geographic records

  Video/CV                FFmpeg, OpenCV          Decoding and image
                                                  operations

  Numerical               NumPy, SciPy            Arrays and scientific
                                                  utilities

  AI runtime              PyTorch, CUDA           Neural inference

  Multi-view geometry     Fast3R                  Poses and pointmaps

  Depth priors            Metric3D-v2             Depth and normals

  Detection/tracking      YOLO, SAM2              Masks and tracks

  Sensor optimization     GTSAM                   Factor-graph estimation

  Point cloud             Open3D                  Filtering, fusion,
                                                  registration

  Gaussian scene          InstantSplat            Visual reconstruction

  Surface                 SuGaR, Poisson          Mesh extraction

  Geospatial              GDAL, PROJ, PyProj,     Coordinate operations
                          Shapely                 

  Object storage          MinIO                   Large artifacts

  Deployment              Docker, NVIDIA          Reproducible
                          Container Toolkit       services/GPU access

  Acceleration            CUDA, optionally        GPU execution
                          TensorRT                

  Evaluation              TensorBoard, Open3D,    Diagnostics
                          Python metrics          

  Development             Git, GitHub, VS Code    Collaboration
  -----------------------------------------------------------------------

## Dependency management

Research repositories may require different Python, CUDA, PyTorch,
compiler, and library versions. Pin tested versions, isolate
incompatible components in containers, define file-based interfaces,
test adapters early, and check licenses/model-weight terms. Do not
assume TensorRT supports every model operation.

# 18. Security, Reliability, and Provenance

## Upload security

-   Validate both file extension and content.
-   Enforce size/duration limits.
-   Never execute uploaded content.
-   Generate internal filenames rather than trusting paths.
-   Isolate decoders and workers where practical.
-   Handle malformed videos defensively.

## Access control

-   Check authorization on every project, mission, job, and output.
-   Use short-lived signed links where suitable.
-   Avoid exposing filesystem paths or internal service details.
-   Protect WebSocket channels with the same authorization model.

## Reliability

-   Retry transient errors only.
-   Record stage-specific logs.
-   Check disk and GPU capacity before large jobs.
-   Support cancellation between stages.
-   Write outputs atomically.
-   Keep checksums and a manifest of completed artifacts.

## Provenance

Each output should record source assets, selected frames, model
versions, configuration, coordinate system, units, sensor sources,
warnings, creation time, and checksum.

# 19. Feasibility and Viability

## Feasibility

The project is technically plausible because it combines established
categories of tools: video processing, learned geometry, monocular
depth, object segmentation, factor-graph optimization, point-cloud
processing, Gaussian rendering, mesh extraction, and geospatial
transformation. The hard part is integration: scale assumptions,
coordinate conventions, formats, confidence, and compute requirements
must align.

## Feasibility strategy

-   Start with a small representative dataset.
-   Validate each model independently.
-   Define adapters and unit tests.
-   Build a baseline before adding every optional feature.
-   Add sensor fusion after visual pose outputs are understood.
-   Profile memory and runtime on target hardware.
-   Add mesh extraction and web integration incrementally.

## Viability

-   A single-pass workflow may reduce repeated flights when mission
    conditions permit.
-   Learned geometry and sensor fusion may reduce dependence on
    extensive ground-control infrastructure in suitable scenarios.
-   Interactive 3D review can improve inspection workflows.
-   Standard input formats can support flexible platform integration
    after testing.
-   Confidence/provenance improves transparency.

Viability depends on measured accuracy, runtime, workflow fit, sensor
availability, operator usability, and licensing/deployment constraints.

# 20. Risks and Mitigations

  ---------------------------------------------------------------------------
  Risk                        Potential impact        Mitigation
  --------------------------- ----------------------- -----------------------
  Blur/compression/lighting   Weak geometry           Quality scoring and
                                                      keyframe selection

  Limited parallax            Uncertain depth         Learned geometry, depth
                                                      priors, confidence
                                                      mapping

  Sensor noise/time offset    Drift and misalignment  Calibration, timestamp
                                                      checks, robust factors

  Unknown intrinsics          Distorted estimates     Calibration or
                                                      documented assumptions

  Dynamic objects             Ghosting                Detection, tracking,
                                                      masking, separate
                                                      tracks

  Occlusions                  Missing surfaces        Label unobserved
                                                      regions; avoid false
                                                      completion claims

  Dependency conflicts        Integration delays      Pinned environments and
                                                      containers

  GPU memory limits           Crashes/slow jobs       Sliding windows,
                                                      batching, quality modes

  Gaussian/metric mismatch    Bad measurements        Separate rendering from
                                                      validated geometry

  Mesh artifacts              False surfaces          Normal checks and mesh
                                                      validation

  CRS mistakes                Incorrect map position  Explicit CRS, units,
                                                      datum, independent
                                                      checks

  Unverified speed claims     Unrealistic             Benchmark fixed
                              expectations            workloads and hardware

  Sensitive data              Exposure                Access control,
                                                      encryption, retention
                                                      rules
  ---------------------------------------------------------------------------

# 21. Evaluation and Testing

## Dataset design

Include buildings, roads, terrain, vegetation, infrastructure, and mixed
urban scenes. Vary lighting, blur, compression, flight speed, viewpoint
diversity, dynamic content, and telemetry quality. Use reference
dimensions, surveyed checkpoints, trusted scans, or reference models
where possible.

## Geometry metrics

-   Point-cloud-to-reference distance or a documented Chamfer-distance
    variant.
-   Cloud-to-cloud or cloud-to-mesh distance.
-   Surface completeness within a stated tolerance.
-   Reprojection error.
-   Camera position/orientation error.
-   Dimensional error for known distances.
-   Mesh completeness and artifact counts.

Fix alignment and sampling procedures before comparisons. Keep fitting
data separate from independent validation data.

## Geospatial metrics

-   Horizontal position error.
-   Vertical error with vertical datum stated.
-   Trajectory alignment error.
-   Independent checkpoint residuals.
-   Coordinate-transform consistency.

## Dynamic-object metrics

-   Detection precision/recall.
-   Segmentation IoU.
-   Track continuity and identity switches.
-   Reduction in ghosting compared with unmasked reconstruction.
-   False masking of static structures.

## Performance metrics

-   End-to-end and per-stage runtime.
-   Peak GPU memory and system RAM.
-   Disk footprint.
-   Time to first preview.
-   Maximum tested resolution and frame count.
-   Rendering responsiveness.

Always state hardware, model versions, settings, and whether timing
includes file I/O.

## Ablation experiments

Compare: 1. Fast3R geometry only. 2. Geometry plus Metric3D-v2. 3.
Geometry plus sensor fusion. 4. Geometry plus dynamic-object masking. 5.
Geometry plus depth priors and sensor fusion. 6. Full pipeline. 7.
Point-cloud, Gaussian, and mesh outputs separately.

This identifies which modules actually improve quality and prevents
unsupported attribution.

## Acceptance criteria

Define numeric thresholds only after examining the target use case and
test data. At minimum, inputs should be validated, failures explained,
CRS and units recorded, measurements checked against references,
uncertain regions shown, runtime/memory measured, and exports tested in
downstream applications.

# 22. Implementation Roadmap

## Phase 1 --- Requirements and data contract

Define supported formats, coordinate conventions, metadata schema,
target hardware, sample data, and evaluation method.\
**Deliverable:** input specification and test dataset.

## Phase 2 --- Preprocessing

Implement upload validation, frame extraction, telemetry parsing,
quality scores, and keyframe selection.\
**Deliverable:** reproducible preprocessing service.

## Phase 3 --- Fast3R

Run inference, normalize outputs, visualize pointmaps/poses, and test
memory.\
**Deliverable:** geometry prototype.

## Phase 4 --- Metric3D-v2

Add depth/normal inference, verify units, compare with pointmaps, and
implement conservative fusion.\
**Deliverable:** depth-prior artifacts.

## Phase 5 --- Sensor fusion

Normalize telemetry, build GTSAM factors, inspect residuals, and compare
with visual-only results.\
**Deliverable:** optimized trajectory and diagnostics.

## Phase 6 --- Dynamic objects

Integrate YOLO/SAM2, generate masks/tracks, and measure impact on
reconstruction.\
**Deliverable:** dynamic-object layer.

## Phase 7 --- Dense reconstruction

Fuse pointmaps with Open3D and integrate InstantSplat through a tested
adapter.\
**Deliverable:** point cloud and Gaussian scene.

## Phase 8 --- Surface/geospatial output

Add mesh extraction, CRS-aware transforms, export formats, and
validation.\
**Deliverable:** mesh and export package.

## Phase 9 --- App integration

Build mission management, async jobs, progress updates, 3D viewer, map,
confidence overlays, and exports.\
**Deliverable:** integrated prototype.

## Phase 10 --- Benchmark and harden

Run ablations, profile resources, fix failures, document limitations,
and prepare a reproducible demo.\
**Deliverable:** evaluation report and demo-ready release.

# 23. Deployment Architecture

## Logical services

-   **Frontend:** React web application.
-   **API:** FastAPI for projects, uploads, status, and exports.
-   **Database:** PostgreSQL/PostGIS.
-   **Queue/cache:** Redis where appropriate.
-   **Workers:** Celery CPU/GPU processing workers.
-   **Object storage:** MinIO.
-   **GPU runtime:** NVIDIA drivers, compatible CUDA builds, NVIDIA
    Container Toolkit.
-   **Monitoring:** logs, job metrics, disk/GPU monitoring, error
    reporting.

## Local/offline deployment

Package models and dependencies locally, use local storage/database
services, avoid mandatory cloud calls in the processing path, and
document patch/update procedures. Offline deployment does not guarantee
global geographic accuracy; without a global anchor, label output as
local-frame.

## Scaling

Scale preprocessing and GPU workers separately. Limit concurrency by
VRAM, cache deterministic intermediate results, checkpoint outputs, and
avoid concurrent memory-heavy models without profiling.

# 24. Applications and Benefits

## Defence and strategic intelligence

Rapid 3D mapping for border areas, reconnaissance, and mission planning.
GPS-denied workflows may produce local reconstruction, but global
alignment requires a suitable external reference.

## Disaster response

3D documentation and damage-assessment support, safer remote inspection,
and spatial context for rescue/recovery planning. It should support
rather than replace expert judgment.

## Urban planning and smart cities

3D context for buildings, roads, and urban assets; repeat updates when
missions can be registered consistently.

## Infrastructure inspection

Documentation of bridges, roads, buildings, and assets, with measurement
support where resolution and geometry quality are sufficient.

## Construction monitoring

Dated 3D records and progress comparisons when coordinate registration
and change-detection quality are validated.

## Archaeology

Non-contact documentation of visible structures and terrain, with
uncertain or obscured regions clearly marked.

## Digital twins

3D assets and spatial context for updateable digital-twin workflows,
subject to registration and data-quality requirements.

## Benefits

-   **Social:** faster situational understanding, safer remote
    assessment, and improved spatial awareness.
-   **Economic:** potential reduction in repeat flights and field
    effort; faster review and inspection.
-   **Technological:** modular AI/geometry pipeline, confidence-aware
    outputs, and local deployment option.
-   **Environmental:** fewer repeat operations where feasible,
    non-invasive site documentation, and 3D monitoring of visible
    changes.

These are potential benefits. Their magnitude must be measured against a
defined baseline.

# 25. Reference Links

Verify current papers, repositories, licenses, model weights,
dependencies, and compatibility before deployment.

## Multi-view geometry

-   Fast3R project: https://fast3r-3d.github.io/
-   Fast3R arXiv: https://arxiv.org/html/2501.13928v1
-   Feed-forward 3D reconstruction review:
    https://arxiv.org/pdf/2507.08448

## Sparse-view Gaussian reconstruction

-   InstantSplat project: https://instantsplat.github.io/
-   InstantSplat arXiv: https://arxiv.org/abs/2403.20309
-   NoPoSplat repository: https://github.com/cvg/NoPoSplat
-   NoPoSplat arXiv: https://arxiv.org/abs/2410.24207
-   MapAnything project: https://map-anything.github.io/
-   VolSplat repository: https://github.com/ziplab/VolSplat

## Depth and surface reconstruction

-   Metric3D-v2 arXiv: https://arxiv.org/html/2404.15506v1
-   Metric3D-v2 PubMed record: https://pubmed.ncbi.nlm.nih.gov/39150798/
-   SuGaR project: https://imagine.enpc.fr/\~guedona/sugar/
-   SurfSplatting project: https://surfsplatting.github.io/
-   CVPR poster reference:
    https://cvpr.thecvf.com/virtual/2025/poster/32417

## Supporting tools

-   Open3D: https://www.open3d.org/
-   GTSAM: https://gtsam.org/
-   GDAL: https://gdal.org/
-   PROJ: https://proj.org/
-   PyProj: https://pyproj4.github.io/pyproj/stable/
-   FastAPI: https://fastapi.tiangolo.com/
-   PostgreSQL: https://www.postgresql.org/
-   PostGIS: https://postgis.net/

For each dependency, record its version, license, model-weight terms,
environment, known limitations, and evaluation results. Record whether
it is used as published or adapted.

# 26. Demonstration Plan and Final Recommendations

## Suggested demo sequence

1.  Upload one representative drone video and available telemetry.
2.  Show input validation and sensor availability.
3.  Display extracted keyframes and quality flags.
4.  Show Fast3R camera poses and pointmaps.
5.  Display Metric3D-v2 depth priors and dynamic-object masks.
6.  Show sensor-fusion trajectory and residual diagnostics.
7.  Render the point cloud and Gaussian scene.
8.  Display mesh output and coordinate metadata.
9.  Measure a known reference dimension and show its error.
10. Toggle confidence labels and inspect a weakly observed region.
11. Export a 3D asset and processing report.

## Do not imply

-   A visually realistic scene is automatically survey-grade.
-   Hidden surfaces are recovered as ground truth.
-   GPS-denied output is globally georeferenced without a valid anchor.
-   Near-real-time performance or accuracy improvement is guaranteed
    without measurements.
-   Every optional sensor is available or used in every mission.

## Recommended first milestone

Process one representative video end-to-end through preprocessing,
Fast3R geometry, Metric3D-v2 depth priors, a basic sensor-alignment
path, and a point-cloud preview. Validate coordinate conventions and
dimensions before investing in full Gaussian optimization, mesh
extraction, and the complete web application.

## Final summary

The proposed system combines learned multi-view geometry, depth priors,
dynamic-object handling, sensor-constrained optimization, dense
point-cloud processing, Gaussian rendering, surface extraction,
geospatial transformations, and confidence-aware analysis. Its main
engineering risk is integration across models with different coordinate
conventions, scale assumptions, formats, and runtime requirements. Build
incrementally and judge success by independent geometric accuracy,
geographic alignment, robustness, uncertainty communication, processing
time, and export quality---not by visual appearance alone.
