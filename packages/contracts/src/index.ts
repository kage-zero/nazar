import constants from '../schema/constants.json' with { type: 'json' };
import type { JobStatus, StageName } from './generated';

export type * from './generated';

export const EVENT_SCHEMA_VERSION: number = constants.eventSchemaVersion;

/** Processing stages in execution order. */
export const PIPELINE_STAGES = constants.pipelineStages as readonly StageName[];

export const TERMINAL_STATUSES = constants.terminalStatuses as readonly JobStatus[];

const allowedTransitions = constants.allowedTransitions as Record<JobStatus, readonly JobStatus[]>;

export function canTransition(current: JobStatus, target: JobStatus): boolean {
  return allowedTransitions[current].includes(target);
}
