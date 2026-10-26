import { Grid, OrbitControls } from '@react-three/drei';
import { Canvas } from '@react-three/fiber';
import { useEffect, useRef, type ComponentRef } from 'react';
import { useViewerStore } from '../state/viewerStore';

const HOME_POSITION = [6, 4.5, 8] as const;

/**
 * R3F scene scaffold. It renders only reference aids (grid, axes) in an empty local frame.
 * Reconstruction layers (point cloud, camera path, mesh, splats) mount here as children
 * once real artifacts exist; nothing in this scene is reconstructed geometry.
 */
export default function ViewerScene() {
  const controls = useRef<ComponentRef<typeof OrbitControls>>(null);
  const showGrid = useViewerStore((s) => s.showGrid);
  const showAxes = useViewerStore((s) => s.showAxes);
  const resetToken = useViewerStore((s) => s.resetToken);

  useEffect(() => {
    if (resetToken > 0) controls.current?.reset();
  }, [resetToken]);

  return (
    <Canvas
      camera={{ position: [...HOME_POSITION], fov: 45, near: 0.05, far: 500 }}
      dpr={[1, 2]}
      gl={{ antialias: true }}
      aria-label="3D viewport: empty local frame with reference grid and axes"
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
      <OrbitControls ref={controls} makeDefault enableDamping dampingFactor={0.1} />
    </Canvas>
  );
}
