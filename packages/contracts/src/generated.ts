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
 * via the `definition` "CheckStatus".
 */
export type CheckStatus = 'ok' | 'degraded' | 'unavailable' | 'not_configured' | 'not_implemented';

/**
 * Bundle that pulls every public contract into one schema document.
 */
export interface NazarContracts {
  artifact_manifest: ArtifactManifest;
  event_type: EventType;
  health: HealthResponse;
  job_event: JobEvent;
  job_status: JobStatus;
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
