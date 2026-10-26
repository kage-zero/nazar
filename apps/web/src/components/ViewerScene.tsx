import { Grid, OrbitControls } from '@react-three/drei';
import { Canvas } from '@react-three/fiber';
import { useEffect, useRef, type ComponentRef } from 'react';
import { useViewerStore } from '../state/viewerStore';
import { FitToBounds, PointCloudLayer, TrajectoryLayer } from './layers';

const HOME_POSITION = [6, 4.5, 8] as const;

/**
 * R3F scene. Reference aids (grid, axes) are always local-frame helpers, not data.
 * Reconstruction layers mount only when a real artifact manifest exists.
 */
export default function ViewerScene() {
  const controls = useRef<ComponentRef<typeof OrbitControls>>(null);
  const showGrid = useViewerStore((s) => s.showGrid);
  const showAxes = useViewerStore((s) => s.showAxes);
  const showCloud = useViewerStore((s) => s.showCloud);
  const showPath = useViewerStore((s) => s.showPath);
  const resetToken = useViewerStore((s) => s.resetToken);
  const cloud = useViewerStore((s) => s.cloud);
  const path = useViewerStore((s) => s.path);

  useEffect(() => {
    if (resetToken > 0) controls.current?.reset();
  }, [resetToken]);

  return (
    <Canvas
      camera={{ position: [...HOME_POSITION], fov: 45, near: 0.05, far: 500 }}
      dpr={[1, 2]}
      gl={{ antialias: true }}
      aria-label={
        cloud
          ? '3D viewport showing the current point cloud'
          : '3D viewport: empty local frame with reference grid and axes'
      }
      data-testid="viewer-canvas"
    >
      <color attach="background" args={['#000000']} />
      {showGrid && (
        <Grid
          args={[20, 20]}
          cellSize={0.5}
          cellThickness={0.6}
          cellColor="#2f2f2f"
          sectionSize={2.5}
          sectionThickness={1}
          sectionColor="#444444"
          fadeDistance={30}
          infiniteGrid
        />
      )}
      {showAxes && <axesHelper args={[1.5]} />}
      {cloud && showCloud && <PointCloudLayer key={cloud.job_id} manifest={cloud} />}
      {path && showPath && <TrajectoryLayer manifest={path} />}
      {cloud && <FitToBounds bounds={cloud.bounds} />}
      <OrbitControls ref={controls} makeDefault enableDamping dampingFactor={0.1} />
    </Canvas>
  );
}
