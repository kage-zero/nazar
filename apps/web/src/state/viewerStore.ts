import type { ArtifactManifest } from '@nazar/contracts';
import { create } from 'zustand';
import type { ConfidenceCounts } from '../lib/confidence';
import { addPick, type Vec3 } from '../lib/measure';

/**
 * Small viewer UI state only. Geometry buffers never go in here: they live in
 * Three.js objects owned by the layer components (see docs/architecture/overview.md).
 * Artifact manifests are a few hundred bytes of metadata, so they are fine here.
 */
export interface LoadedCloud {
  id: string;
  kind: ArtifactManifest['kind'];
  revision: number;
  points: number;
  /** Per-class counts when the cloud carries confidence labels (final clouds), else null. */
  confidence: ConfidenceCounts | null;
}

export type ColorBy = 'rgb' | 'confidence';

interface ViewerState {
  showGrid: boolean;
  showAxes: boolean;
  showCloud: boolean;
  showPath: boolean;
  colorBy: ColorBy;
  measuring: boolean;
  picks: Vec3[];
  resetToken: number;
  fitToken: number;
  cloud: ArtifactManifest | null;
  path: ArtifactManifest | null;
  loaded: LoadedCloud | null;
  layerError: string | null;
  toggleGrid: () => void;
  toggleAxes: () => void;
  toggleCloud: () => void;
  togglePath: () => void;
  setColorBy: (colorBy: ColorBy) => void;
  toggleMeasure: () => void;
  pick: (p: Vec3) => void;
  requestReset: () => void;
  requestFit: () => void;
  setLayers: (cloud: ArtifactManifest | null, path: ArtifactManifest | null) => void;
  setLoaded: (loaded: LoadedCloud | null) => void;
  setLayerError: (message: string | null) => void;
}

export const useViewerStore = create<ViewerState>()((set) => ({
  showGrid: true,
  showAxes: true,
  showCloud: true,
  showPath: true,
  colorBy: 'rgb',
  measuring: false,
  picks: [],
  resetToken: 0,
  fitToken: 0,
  cloud: null,
  path: null,
  loaded: null,
  layerError: null,
  toggleGrid: () => {
    set((s) => ({ showGrid: !s.showGrid }));
  },
  toggleAxes: () => {
    set((s) => ({ showAxes: !s.showAxes }));
  },
  toggleCloud: () => {
    set((s) => ({ showCloud: !s.showCloud }));
  },
  togglePath: () => {
    set((s) => ({ showPath: !s.showPath }));
  },
  setColorBy: (colorBy) => {
    set({ colorBy });
  },
  toggleMeasure: () => {
    set((s) => ({ measuring: !s.measuring, picks: [] }));
  },
  pick: (p) => {
    set((s) => (s.measuring ? { picks: addPick(s.picks, p) } : {}));
  },
  requestReset: () => {
    set((s) => ({ resetToken: s.resetToken + 1 }));
  },
  requestFit: () => {
    set((s) => ({ fitToken: s.fitToken + 1 }));
  },
  setLayers: (cloud, path) => {
    set((s) => {
      // Fit the camera once when a job's first geometry arrives; later revisions keep the
      // user's view (brief §9: update the scene without resetting the orbit).
      const firstForJob = cloud !== null && s.cloud?.job_id !== cloud.job_id;
      return {
        cloud,
        path,
        fitToken: firstForJob ? s.fitToken + 1 : s.fitToken,
        picks: firstForJob || cloud === null ? [] : s.picks,
        loaded: cloud ? s.loaded : null,
      };
    });
  },
  setLoaded: (loaded) => {
    set({ loaded });
  },
  setLayerError: (layerError) => {
    set({ layerError });
  },
}));
