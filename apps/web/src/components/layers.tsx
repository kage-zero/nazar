import type { ArtifactManifest } from '@nazar/contracts';
import { Line } from '@react-three/drei';
import { useThree } from '@react-three/fiber';
import { useEffect, useState } from 'react';
import { Vector3, type BufferGeometry } from 'three';
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js';
import { jobs } from '../api/jobs';
import { useViewerStore } from '../state/viewerStore';

async function fetchArtifact(id: string, signal: AbortSignal): Promise<ArrayBuffer> {
  const response = await fetch(jobs.artifactUrl(id), { credentials: 'same-origin', signal });
  if (!response.ok) throw new Error(`Artifact request failed (${String(response.status)}).`);
  return response.arrayBuffer();
}

/**
 * Renders one point-cloud artifact. A new revision replaces the geometry in place (the old
 * GPU buffer is disposed); requests for superseded revisions are aborted, so a late response
 * can never overwrite a newer cloud.
 */
export function PointCloudLayer({ manifest }: { manifest: ArtifactManifest }) {
  const [geometry, setGeometry] = useState<BufferGeometry | null>(null);
  const setLoaded = useViewerStore((s) => s.setLoaded);
  const setLayerError = useViewerStore((s) => s.setLayerError);

  useEffect(() => {
    const controller = new AbortController();
    fetchArtifact(manifest.id, controller.signal)
      .then((buffer) => {
        const parsed = new PLYLoader().parse(buffer);
        setGeometry(parsed);
        setLayerError(null);
        setLoaded({
          id: manifest.id,
          kind: manifest.kind,
          revision: manifest.revision,
          points: parsed.getAttribute('position').count,
        });
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setLayerError(err instanceof Error ? err.message : 'Point cloud failed to load.');
      });
    return () => {
      controller.abort();
    };
  }, [manifest.id, manifest.kind, manifest.revision, setLoaded, setLayerError]);

  useEffect(
    () => () => {
      geometry?.dispose();
    },
    [geometry],
  );

  if (!geometry) return null;
  return (
    <points geometry={geometry}>
      <pointsMaterial size={0.06} sizeAttenuation vertexColors />
    </points>
  );
}

interface TrajectoryDoc {
  poses: { position: [number, number, number] }[];
}

/** Camera positions from a `camera_trajectory` artifact, drawn as a path with markers. */
export function TrajectoryLayer({ manifest }: { manifest: ArtifactManifest }) {
  const [points, setPoints] = useState<[number, number, number][] | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchArtifact(manifest.id, controller.signal)
      .then((buffer) => {
        const doc = JSON.parse(new TextDecoder().decode(buffer)) as TrajectoryDoc;
        setPoints(doc.poses.map((p) => p.position));
      })
      .catch(() => undefined);
    return () => {
      controller.abort();
    };
  }, [manifest.id]);

  if (!points || points.length < 2) return null;
  return (
    <group>
      <Line points={points} color="#9effc5" lineWidth={1.5} />
      {points.map((p, i) => (
        <mesh key={i} position={p}>
          <sphereGeometry args={[0.08, 8, 8]} />
          <meshBasicMaterial color="#9effc5" />
        </mesh>
      ))}
    </group>
  );
}

/** Moves the camera to frame the artifact's bounds whenever `fitToken` changes. */
export function FitToBounds({ bounds }: { bounds: ArtifactManifest['bounds'] }) {
  const fitToken = useViewerStore((s) => s.fitToken);
  const camera = useThree((s) => s.camera);
  const controls = useThree((s) => s.controls) as {
    target: Vector3;
    update: () => void;
  } | null;

  useEffect(() => {
    if (!bounds || fitToken === 0) return;
    const min = new Vector3(...bounds.min);
    const max = new Vector3(...bounds.max);
    const center = min.clone().add(max).multiplyScalar(0.5);
    const radius = Math.max(max.distanceTo(min) / 2, 0.5);
    const dir = new Vector3(1, 0.8, 1.2).normalize();
    camera.position.copy(center.clone().add(dir.multiplyScalar(radius * 2.2)));
    camera.lookAt(center);
    if (controls) {
      controls.target.copy(center);
      controls.update();
    }
    // Only an explicit fit request moves the camera; new revisions with new bounds do not.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitToken, camera, controls]);

  return null;
}
