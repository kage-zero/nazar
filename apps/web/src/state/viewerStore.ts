import type { ArtifactManifest } from '@nazar/contracts';
import { create } from 'zustand';

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
}

interface ViewerState {
  showGrid: boolean;
  showAxes: boolean;
  showCloud: boolean;
  showPath: boolean;
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
