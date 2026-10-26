/* eslint-disable */
// GENERATED FILE - do not edit. Source: packages/contracts/python (Pydantic).
// Regenerate with `pnpm contracts:generate`.

/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "ScaleStatus".
 */
export type ScaleStatus = 'unknown' | 'relative' | 'metric_estimated' | 'metric_sensor';
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "FrameType".
 */
export type FrameType = 'local_reconstruction' | 'enu' | 'ecef' | 'geographic' | 'projected';
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "ArtifactKind".
 */
export type ArtifactKind =
  | 'keyframes'
  | 'point_cloud_preview'
  | 'point_cloud'
  | 'camera_trajectory'
  | 'depth_maps'
  | 'dynamic_masks'
  | 'gaussian_scene'
  | 'mesh'
  | 'report'
  | 'export';
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "AssetKind".
 */
export type AssetKind = 'video' | 'telemetry';
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "AssetStatus".
 */
export type AssetStatus =
  'uploading' | 'validating' | 'ready' | 'rejected' | 'failed' | 'cancelled';
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "EventType".
 */
export type EventType =
  | 'job.created'
  | 'stage.started'
  | 'stage.progress'
  | 'stage.completed'
  | 'stage.skipped'
  | 'warning'
  | 'artifact.available'
  | 'preview.updated'
  | 'job.completed'
  | 'job.failed'
  | 'cancel.requested'
  | 'job.cancelled';
export type JobEvent =
  | JobCreated
  | StageStarted
  | StageProgress
  | StageCompleted
  | StageSkipped
  | WarningRaised
  | ArtifactAvailable
  | PreviewUpdated
  | JobCompleted
  | JobFailed
  | CancelRequested
  | JobCancelled;
/**
 * Processing stages. Each value is also the job status while that stage runs.
 *
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "StageName".
 */
export type StageName =
  | 'preprocessing'
  | 'geometry'
  | 'depth_priors'
  | 'dynamic_analysis'
  | 'sensor_optimization'
  | 'dense_reconstruction'
  | 'surface_processing'
  | 'analysis'
  | 'exporting';
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "JobStatus".
 */
export type JobStatus =
  | 'created'
  | 'validating'
  | 'queued'
  | 'preprocessing'
  | 'geometry'
  | 'depth_priors'
  | 'dynamic_analysis'
  | 'sensor_optimization'
  | 'dense_reconstruction'
  | 'surface_processing'
  | 'analysis'
  | 'exporting'
  | 'completed'
  | 'failed'
  | 'cancel_requested'
  | 'cancelled';
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "KeyframeReason".
 */
export type KeyframeReason = 'start' | 'novelty' | 'max_gap' | 'end';
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "FrameFlag".
 */
export type FrameFlag = 'blurry' | 'dark' | 'overexposed' | 'duplicate';
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "WarningSeverity".
 */
export type WarningSeverity = 'info' | 'warning' | 'blocking';
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "CheckStatus".
 */
export type CheckStatus = 'ok' | 'degraded' | 'unavailable' | 'not_configured' | 'not_implemented';

/**
 * Bundle that pulls every public contract into one schema document.
 */
export interface NazarContracts {
  artifact_manifest: ArtifactManifest;
  asset: Asset;
  asset_create: AssetCreate;
  auth_state: AuthState;
  credentials: Credentials;
  event_type: EventType;
  health: HealthResponse;
  job_event: JobEvent;
  job_status: JobStatus;
  mission: Mission;
  mission_create: MissionCreate;
  preflight_report: PreflightReport;
  readiness: ReadinessResponse;
  stage_name: StageName;
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "ArtifactManifest".
 */
export interface ArtifactManifest {
  bounds?: Bounds3D | null;
  byte_size: number;
  checksum_sha256: string;
  created_at: string;
  frame?: CoordinateFrame | null;
  id: string;
  job_id: string;
  kind: ArtifactKind;
  lod?: number | null;
  media_type: string;
  point_count?: number | null;
  provenance: Provenance;
  /**
   * Monotonic per (job, kind); stale revisions are ignored.
   */
  revision: number;
  source_frames?: FrameRange | null;
  /**
   * Column-major 4x4 from artifact-local coords to `frame`.
   */
  transform_to_frame?:
    | [
        number,
        number,
        number,
        number,
        number,
        number,
        number,
        number,
        number,
        number,
        number,
        number,
        number,
        number,
        number,
        number
      ]
    | null;
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "Bounds3D".
 */
export interface Bounds3D {
  /**
   * @minItems 3
   * @maxItems 3
   */
  max: [number, number, number];
  /**
   * @minItems 3
   * @maxItems 3
   */
  min: [number, number, number];
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "CoordinateFrame".
 */
export interface CoordinateFrame {
  /**
   * Axis convention of stored coordinates.
   */
  axes?: string;
  /**
   * EPSG/WKT identifier when georeferenced.
   */
  crs?: string | null;
  scale_status: ScaleStatus;
  type: FrameType;
  /**
   * Linear units of coordinates, e.g. 'metre' or 'unitless'.
   */
  units: string;
  vertical_datum?: string | null;
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "Provenance".
 */
export interface Provenance {
  config_hash?: string | null;
  model?: string | null;
  model_version?: string | null;
  /**
   * Stage adapter that produced the artifact.
   */
  producer: string;
  /**
   * True when produced by the deterministic test pipeline, not a real model.
   */
  test_pipeline: boolean;
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "FrameRange".
 */
export interface FrameRange {
  count: number;
  first_index: number;
  last_index: number;
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "Asset".
 */
export interface Asset {
  byte_size: number;
  created_at: string;
  error: string | null;
  filename: string;
  id: string;
  kind: AssetKind;
  mission_id: string;
  progress: ProcessingProgress | null;
  received_bytes: number;
  sha256: string | null;
  status: AssetStatus;
  updated_at: string;
}
/**
 * Server-side processing phase. Counts are null when the work is not countable.
 *
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "ProcessingProgress".
 */
export interface ProcessingProgress {
  completed?: number | null;
  phase: string;
  total?: number | null;
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "AssetCreate".
 */
export interface AssetCreate {
  byte_size: number;
  filename: string;
  kind: AssetKind;
}
/**
 * `setup_required` is true only while no operator account exists.
 *
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "AuthState".
 */
export interface AuthState {
  setup_required: boolean;
  user: UserPublic | null;
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "UserPublic".
 */
export interface UserPublic {
  email: string;
  id: string;
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "Credentials".
 */
export interface Credentials {
  email: string;
  password: string;
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "HealthResponse".
 */
export interface HealthResponse {
  environment: string;
  service: string;
  status: 'ok';
  time: string;
  version: string;
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "JobCreated".
 */
export interface JobCreated {
  data: JobCreatedData;
  job_id: string;
  schema_version?: 1;
  seq: number;
  stage?: StageName | null;
  status: JobStatus;
  ts: string;
  type: 'job.created';
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "JobCreatedData".
 */
export interface JobCreatedData {
  mission_id: string;
  test_pipeline: boolean;
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "StageStarted".
 */
export interface StageStarted {
  job_id: string;
  schema_version?: 1;
  seq: number;
  stage?: StageName | null;
  status: JobStatus;
  ts: string;
  type: 'stage.started';
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "StageProgress".
 */
export interface StageProgress {
  data: StageProgressData;
  job_id: string;
  schema_version?: 1;
  seq: number;
  stage?: StageName | null;
  status: JobStatus;
  ts: string;
  type: 'stage.progress';
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "StageProgressData".
 */
export interface StageProgressData {
  /**
   * Units of real work done. Null when not measurable.
   */
  completed?: number | null;
  message: string;
  /**
   * Total units. Null means indeterminate progress.
   */
  total?: number | null;
  /**
   * e.g. 'frames', 'keyframes', 'iterations'
   */
  unit?: string | null;
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "StageCompleted".
 */
export interface StageCompleted {
  data: StageCompletedData;
  job_id: string;
  schema_version?: 1;
  seq: number;
  stage?: StageName | null;
  status: JobStatus;
  ts: string;
  type: 'stage.completed';
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "StageCompletedData".
 */
export interface StageCompletedData {
  duration_s: number;
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "StageSkipped".
 */
export interface StageSkipped {
  data: StageSkippedData;
  job_id: string;
  schema_version?: 1;
  seq: number;
  stage?: StageName | null;
  status: JobStatus;
  ts: string;
  type: 'stage.skipped';
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "StageSkippedData".
 */
export interface StageSkippedData {
  reason: string;
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "WarningRaised".
 */
export interface WarningRaised {
  data: WarningData;
  job_id: string;
  schema_version?: 1;
  seq: number;
  stage?: StageName | null;
  status: JobStatus;
  ts: string;
  type: 'warning';
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "WarningData".
 */
export interface WarningData {
  code: string;
  message: string;
  severity: 'info' | 'warning' | 'critical';
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "ArtifactAvailable".
 */
export interface ArtifactAvailable {
  data: ArtifactManifest;
  job_id: string;
  schema_version?: 1;
  seq: number;
  stage?: StageName | null;
  status: JobStatus;
  ts: string;
  type: 'artifact.available';
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "PreviewUpdated".
 */
export interface PreviewUpdated {
  data: PreviewUpdatedData;
  job_id: string;
  schema_version?: 1;
  seq: number;
  stage?: StageName | null;
  status: JobStatus;
  ts: string;
  type: 'preview.updated';
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "PreviewUpdatedData".
 */
export interface PreviewUpdatedData {
  artifact_id: string;
  revision: number;
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "JobCompleted".
 */
export interface JobCompleted {
  data: JobCompletedData;
  job_id: string;
  schema_version?: 1;
  seq: number;
  stage?: StageName | null;
  status: JobStatus;
  ts: string;
  type: 'job.completed';
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "JobCompletedData".
 */
export interface JobCompletedData {
  artifact_ids: string[];
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "JobFailed".
 */
export interface JobFailed {
  data: JobFailedData;
  job_id: string;
  schema_version?: 1;
  seq: number;
  stage?: StageName | null;
  status: JobStatus;
  ts: string;
  type: 'job.failed';
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "JobFailedData".
 */
export interface JobFailedData {
  /**
   * Human-readable, actionable failure reason.
   */
  reason: string;
  retryable: boolean;
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "CancelRequested".
 */
export interface CancelRequested {
  job_id: string;
  schema_version?: 1;
  seq: number;
  stage?: StageName | null;
  status: JobStatus;
  ts: string;
  type: 'cancel.requested';
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "JobCancelled".
 */
export interface JobCancelled {
  job_id: string;
  schema_version?: 1;
  seq: number;
  stage?: StageName | null;
  status: JobStatus;
  ts: string;
  type: 'job.cancelled';
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "Mission".
 */
export interface Mission {
  created_at: string;
  id: string;
  name: string;
  video: Asset | null;
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "MissionCreate".
 */
export interface MissionCreate {
  name: string;
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "PreflightReport".
 */
export interface PreflightReport {
  analysis: AnalysisInfo;
  asset_id: string;
  generated_at: string;
  keyframes: Keyframe[];
  probe: VideoProbe;
  schema_version?: 1;
  series: FrameSeries;
  settings: {
    [k: string]: number | string;
  };
  source_sha256: string;
  summary: PreflightSummary;
  telemetry_present: boolean;
  warnings: PreflightWarning[];
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "AnalysisInfo".
 */
export interface AnalysisInfo {
  decode_errors: number;
  frames_decoded: number;
  height: number;
  processing_s: number;
  timestamps: 'stream' | 'estimated';
  width: number;
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "Keyframe".
 */
export interface Keyframe {
  image: number;
  index: number;
  quality: number;
  reason: KeyframeReason;
  t: number;
}
/**
 * Facts read from the container/stream by ffprobe. `display_*` include rotation.
 *
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "VideoProbe".
 */
export interface VideoProbe {
  average_fps: number | null;
  bit_rate: number | null;
  codec: string;
  container: string;
  display_height: number;
  display_width: number;
  duration_s: number;
  frame_count: number | null;
  has_audio: boolean;
  height: number;
  nominal_fps: number | null;
  pix_fmt: string | null;
  rotation_deg: number;
  variable_frame_rate: boolean;
  width: number;
}
/**
 * Per-frame metrics, column-oriented (one entry per decoded frame, in display order).
 *
 * - `t`: presentation time in seconds from the stream's first frame.
 * - `sharpness`: variance of the Laplacian at analysis resolution (higher = sharper).
 * - `brightness`: mean luma, 0-1.
 * - `change`: mean absolute luma difference to the previous frame, 0-1.
 * - `motion_px`: estimated global image shift to the previous frame, in analysis pixels.
 * - `flags`: per-frame quality flags.
 *
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "FrameSeries".
 */
export interface FrameSeries {
  brightness: number[];
  change: number[];
  flags: FrameFlag[][];
  index: number[];
  motion_px: number[];
  sharpness: number[];
  t: number[];
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "PreflightSummary".
 */
export interface PreflightSummary {
  blurry_frames: number;
  dark_frames: number;
  duplicate_frames: number;
  median_sharpness: number;
  overexposed_frames: number;
  usable_frames: number;
  viewpoint_change: number;
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "PreflightWarning".
 */
export interface PreflightWarning {
  code: string;
  message: string;
  severity: WarningSeverity;
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "ReadinessResponse".
 */
export interface ReadinessResponse {
  checks: ReadinessCheck[];
  ready: boolean;
}
/**
 * This interface was referenced by `NazarContracts`'s JSON-Schema
 * via the `definition` "ReadinessCheck".
 */
export interface ReadinessCheck {
  detail: string;
  name: string;
  required: boolean;
  status: CheckStatus;
}
