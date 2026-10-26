import { create } from 'zustand';

/**
 * Small viewer UI state only. Geometry buffers never go in here: they live in
 * Three.js objects owned by the layer components (see docs/architecture/overview.md).
 */
interface ViewerState {
  showGrid: boolean;
  showAxes: boolean;
  resetToken: number;
  toggleGrid: () => void;
  toggleAxes: () => void;
  requestReset: () => void;
}

export const useViewerStore = create<ViewerState>()((set) => ({
  showGrid: true,
  showAxes: true,
  resetToken: 0,
  toggleGrid: () => {
    set((s) => ({ showGrid: !s.showGrid }));
  },
  toggleAxes: () => {
    set((s) => ({ showAxes: !s.showAxes }));
  },
  requestReset: () => {
    set((s) => ({ resetToken: s.resetToken + 1 }));
  },
}));
