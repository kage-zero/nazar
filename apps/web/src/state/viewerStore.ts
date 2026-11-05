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

/** Sizes of the heavier layers, shown under the viewer once they have loaded. */
export interface LayerInfo {
  triangles: number | null;
  splats: number | null;
}

interface ViewerState {
  showGrid: boolean;
  showAxes: boolean;
  showCloud: boolean;
  showMesh: boolean;
  showSplat: boolean;
  showPath: boolean;
  colorBy: ColorBy;
  measuring: boolean;
  picks: Vec3[];
  resetToken: number;
  fitToken: number;
  cloud: ArtifactManifest | null;
  path: ArtifactManifest | null;
  mesh: ArtifactManifest | null;
  splat: ArtifactManifest | null;
  layerInfo: LayerInfo;
  loaded: LoadedCloud | null;
  layerError: string | null;
  toggleGrid: () => void;
  toggleAxes: () => void;
  toggleCloud: () => void;
  toggleMesh: () => void;
  toggleSplat: () => void;
  togglePath: () => void;
  setColorBy: (colorBy: ColorBy) => void;
  toggleMeasure: () => void;
  pick: (p: Vec3) => void;
  requestReset: () => void;
  requestFit: () => void;
  setLayers: (
    cloud: ArtifactManifest | null,
    path: ArtifactManifest | null,
    mesh?: ArtifactManifest | null,
    splat?: ArtifactManifest | null,
  ) => void;
  setLayerInfo: (info: Partial<LayerInfo>) => void;
  setLoaded: (loaded: LoadedCloud | null) => void;
  setLayerError: (message: string | null) => void;
}

export const useViewerStore = create<ViewerState>()((set) => ({
  showGrid: true,
  showAxes: true,
  showCloud: true,
  showMesh: false,
  showSplat: false,
  showPath: true,
  colorBy: 'rgb',
  measuring: false,
  picks: [],
  resetToken: 0,
  fitToken: 0,
  cloud: null,
  path: null,
  mesh: null,
  splat: null,
  layerInfo: { triangles: null, splats: null },
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
  toggleMesh: () => {
    set((s) => ({ showMesh: !s.showMesh }));
  },
  toggleSplat: () => {
    set((s) => ({ showSplat: !s.showSplat }));
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
  setLayers: (cloud, path, mesh = null, splat = null) => {
    set((s) => {
      // The richest result is what the user came to see: when a job's splat (or, failing
      // that, mesh) first arrives, show it and put the plain points aside. All of it stays
      // one click away.
      const newSplat = splat !== null && s.splat?.job_id !== splat.job_id;
      const newMesh = mesh !== null && s.mesh?.job_id !== mesh.job_id;
      const view = newSplat
        ? { showSplat: true, showMesh: false, showCloud: false }
        : newMesh && splat === null
          ? { showMesh: true, showSplat: false, showCloud: false }
          : {};
      const gone = cloud === null && mesh === null && splat === null;
      const layerInfo = {
        triangles: mesh ? s.layerInfo.triangles : null,
        splats: splat ? s.layerInfo.splats : null,
      };
      // Fit the camera once when a job's first geometry arrives; later revisions keep the
      // user's view (brief §9: update the scene without resetting the orbit).
      const firstForJob = cloud !== null && s.cloud?.job_id !== cloud.job_id;
      return {
        ...view,
        cloud,
        path,
        mesh,
        splat,
        layerInfo,
        ...(gone ? { showCloud: true } : {}),
        fitToken: firstForJob ? s.fitToken + 1 : s.fitToken,
        picks: firstForJob || cloud === null ? [] : s.picks,
        loaded: cloud ? s.loaded : null,
      };
    });
  },
  setLayerInfo: (info) => {
    set((s) => ({ layerInfo: { ...s.layerInfo, ...info } }));
  },
  setLoaded: (loaded) => {
    set({ loaded });
  },
  setLayerError: (layerError) => {
    set({ layerError });
  },
}));
