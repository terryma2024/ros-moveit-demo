import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { PLYLoader } from "three/examples/jsm/loaders/PLYLoader.js";

import type {
  CaptureResponse,
  RenderedPointCloudMetadata,
  TaskArtifact,
} from "@/api/task-types";
import { Button } from "@/components/ui/button";

const MAX_DISPLAY_POINTS = 400_000;
const BACKGROUND_RGB: [number, number, number] = [0.02, 0.03, 0.05];

export type CloudLoadSummary = Pick<
  RenderedPointCloudMetadata,
  "original_point_count" | "displayed_point_count" | "sampling_rule" | "sampling_stride"
>;

export type PointCloudSnapshot = {
  blob: Blob;
  view_matrix: number[];
  projection_matrix: number[];
  viewport_px: [number, number];
};

export type PointCloudRenderer = {
  load(payload: ArrayBuffer, colorMode: "rgb" | "uniform"): Promise<CloudLoadSummary>;
  setPointSize(size: number): void;
  setColorMode(mode: "rgb" | "uniform"): void;
  resetView(): void;
  snapshot(): Promise<PointCloudSnapshot>;
  dispose(): void;
};

export type PointCloudViewerApi = {
  fetchArtifact(artifactId: string): Promise<ArrayBuffer>;
  uploadRenderedImage(
    captureId: string,
    png: Blob,
    metadata: RenderedPointCloudMetadata,
  ): Promise<unknown>;
  artifactUrl?(artifactId: string): string;
};

function sampledGeometry(source: THREE.BufferGeometry): { geometry: THREE.BufferGeometry; summary: CloudLoadSummary } {
  const position = source.getAttribute("position");
  if (!position || position.count <= 0) throw new Error("PLY_POSITION_MISSING");
  const original = position.count;
  const stride = original > MAX_DISPLAY_POINTS ? Math.ceil(original / MAX_DISPLAY_POINTS) : 1;
  if (stride === 1) {
    return {
      geometry: source,
      summary: {
        original_point_count: original,
        displayed_point_count: original,
        sampling_rule: "all",
        sampling_stride: 1,
      },
    };
  }
  const count = Math.ceil(original / stride);
  const geometry = new THREE.BufferGeometry();
  for (const name of ["position", "color"] as const) {
    const attribute = source.getAttribute(name);
    if (!attribute) continue;
    const values = new Float32Array(count * attribute.itemSize);
    let destination = 0;
    for (let index = 0; index < original; index += stride) {
      for (let component = 0; component < attribute.itemSize; component += 1) {
        values[destination++] = attribute.getComponent(index, component);
      }
    }
    geometry.setAttribute(name, new THREE.BufferAttribute(values, attribute.itemSize));
  }
  source.dispose();
  return {
    geometry,
    summary: {
      original_point_count: original,
      displayed_point_count: count,
      sampling_rule: "fixed-stride",
      sampling_stride: stride,
    },
  };
}

function disposeObject(object: THREE.Object3D): void {
  object.traverse((child) => {
    const mesh = child as THREE.Mesh;
    mesh.geometry?.dispose();
    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    materials.filter(Boolean).forEach((material) => material.dispose());
  });
}

export function createThreePointCloudRenderer(
  host: HTMLElement,
  cupCenter?: [number, number, number],
): PointCloudRenderer {
  const width = Math.max(host.clientWidth, 640);
  const height = Math.max(Math.round(width * 0.625), 400);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(...BACKGROUND_RGB);
  const camera = new THREE.PerspectiveCamera(48, width / height, 0.001, 20);
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(width, height);
  host.appendChild(renderer.domElement);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  const axes = new THREE.AxesHelper(0.1);
  scene.add(axes);
  let points: THREE.Points | undefined;
  let pointSize = 0.0025;
  let colorMode: "rgb" | "uniform" = "rgb";
  let homeCenter = new THREE.Vector3();
  let homeRadius = 0.25;

  if (cupCenter) {
    const marker = new THREE.Mesh(
      new THREE.SphereGeometry(0.007, 18, 12),
      new THREE.MeshBasicMaterial({ color: 0xff3366 }),
    );
    marker.position.fromArray(cupCenter);
    marker.name = "cup-center";
    scene.add(marker);
  }

  const material = () => new THREE.PointsMaterial({
    size: pointSize,
    sizeAttenuation: true,
    vertexColors: colorMode === "rgb" && Boolean(points?.geometry.getAttribute("color")),
    color: colorMode === "uniform" ? 0x55d7ff : 0xffffff,
  });
  const resetView = () => {
    camera.position.set(
      homeCenter.x + homeRadius * 1.4,
      homeCenter.y - homeRadius * 1.8,
      homeCenter.z + homeRadius * 1.2,
    );
    camera.near = Math.max(homeRadius / 1000, 0.001);
    camera.far = Math.max(homeRadius * 30, 5);
    camera.updateProjectionMatrix();
    controls.target.copy(homeCenter);
    controls.update();
  };
  renderer.setAnimationLoop(() => {
    controls.update();
    renderer.render(scene, camera);
  });

  return {
    async load(payload, nextColorMode) {
      if (points) {
        scene.remove(points);
        disposeObject(points);
      }
      colorMode = nextColorMode;
      const parsed = new PLYLoader().parse(payload);
      const sampled = sampledGeometry(parsed);
      sampled.geometry.computeBoundingSphere();
      sampled.geometry.computeBoundingBox();
      points = new THREE.Points(sampled.geometry, material());
      scene.add(points);
      const sphere = sampled.geometry.boundingSphere;
      if (sphere) {
        homeCenter = sphere.center.clone();
        homeRadius = Math.max(sphere.radius, 0.05);
      }
      resetView();
      return sampled.summary;
    },
    setPointSize(size) {
      pointSize = size;
      const active = points?.material as THREE.PointsMaterial | undefined;
      if (active) {
        active.size = size;
        active.needsUpdate = true;
      }
    },
    setColorMode(mode) {
      colorMode = mode;
      if (!points) return;
      const previous = points.material as THREE.Material;
      points.material = material();
      previous.dispose();
    },
    resetView,
    async snapshot() {
      controls.update();
      renderer.render(scene, camera);
      const blob = await new Promise<Blob>((resolve, reject) => {
        renderer.domElement.toBlob((value) => value ? resolve(value) : reject(new Error("PNG_CAPTURE_FAILED")), "image/png");
      });
      return {
        blob,
        view_matrix: camera.matrixWorldInverse.toArray(),
        projection_matrix: camera.projectionMatrix.toArray(),
        viewport_px: [renderer.domElement.width, renderer.domElement.height],
      };
    },
    dispose() {
      renderer.setAnimationLoop(null);
      controls.dispose();
      scene.traverse((child) => { if (child !== scene) disposeObject(child); });
      renderer.dispose();
      renderer.domElement.remove();
    },
  };
}

function artifactFor(capture: CaptureResponse, selection: "full" | "cup"): TaskArtifact | undefined {
  const name = selection === "full" ? "full-cloud.ply" : "cup-cloud.ply";
  return capture.artifacts.find((artifact) => artifact.name === name);
}

export function PointCloudViewer({
  capture,
  api,
  rendererFactory = createThreePointCloudRenderer,
}: {
  capture: CaptureResponse;
  api: PointCloudViewerApi;
  rendererFactory?: (host: HTMLElement, center?: [number, number, number]) => PointCloudRenderer;
}) {
  const host = useRef<HTMLDivElement>(null);
  const renderer = useRef<PointCloudRenderer>();
  const [selection, setSelection] = useState<"full" | "cup">("full");
  const [pointSize, setPointSize] = useState(0.0025);
  const [colorMode, setColorMode] = useState<"rgb" | "uniform">("rgb");
  const [loadSummary, setLoadSummary] = useState<CloudLoadSummary>();
  const [status, setStatus] = useState("Loading point cloud…");
  const center = useMemo(() => {
    const value = capture.summary.cup_center_xyz;
    return Array.isArray(value) && value.length === 3 && value.every((item) => typeof item === "number")
      ? value as [number, number, number]
      : undefined;
  }, [capture.summary]);

  useEffect(() => {
    if (!host.current) return;
    const instance = rendererFactory(host.current, center);
    renderer.current = instance;
    return () => {
      instance.dispose();
      renderer.current = undefined;
    };
  }, [capture.capture_id, rendererFactory, center]);

  useEffect(() => {
    let active = true;
    const artifact = artifactFor(capture, selection);
    if (!artifact || !renderer.current) {
      setStatus(`${selection} point cloud unavailable`);
      return;
    }
    setStatus(`Loading ${artifact.name}…`);
    api.fetchArtifact(artifact.artifact_id)
      .then((payload) => renderer.current?.load(payload, colorMode))
      .then((summary) => {
        if (!active || !summary) return;
        setLoadSummary(summary);
        setStatus(`${summary.displayed_point_count.toLocaleString()} points displayed`);
      })
      .catch((error) => { if (active) setStatus(`Point cloud failed: ${String(error)}`); });
    return () => { active = false; };
  }, [api, capture, colorMode, selection]);

  const save = async () => {
    const artifact = artifactFor(capture, selection);
    if (!artifact || !renderer.current || !loadSummary) return;
    setStatus("Saving rendered evidence…");
    try {
      const shot = await renderer.current.snapshot();
      await api.uploadRenderedImage(capture.capture_id, shot.blob, {
        source_artifact_id: artifact.artifact_id,
        source_sha256: artifact.sha256,
        view_matrix: shot.view_matrix,
        projection_matrix: shot.projection_matrix,
        point_size: pointSize,
        color_mode: colorMode,
        background_rgb: BACKGROUND_RGB,
        viewport_px: shot.viewport_px,
        ...loadSummary,
        captured_at: new Date().toISOString(),
      });
      setStatus("Rendered point-cloud evidence saved");
    } catch (error) {
      setStatus(`Save failed: ${String(error)}`);
    }
  };

  return <section className="space-y-3" aria-label="Point-cloud viewer">
    <div className="flex flex-wrap items-end gap-3">
      <label className="grid gap-1 text-xs text-slate-400">Point cloud
        <select className="h-9 rounded border border-slate-700 bg-slate-950 px-2 text-sm text-slate-100" value={selection} onChange={(event) => setSelection(event.target.value as "full" | "cup")}>
          <option value="full">Full scene</option><option value="cup">Cup crop</option>
        </select>
      </label>
      <label className="grid gap-1 text-xs text-slate-400">Color
        <select className="h-9 rounded border border-slate-700 bg-slate-950 px-2 text-sm text-slate-100" value={colorMode} onChange={(event) => { const mode = event.target.value as "rgb" | "uniform"; setColorMode(mode); renderer.current?.setColorMode(mode); }}>
          <option value="rgb">RGB</option><option value="uniform">Uniform</option>
        </select>
      </label>
      <label className="grid gap-1 text-xs text-slate-400">Point size
        <input aria-label="Point size" type="range" min="0.001" max="0.012" step="0.0005" value={pointSize} onChange={(event) => { const size = Number(event.target.value); setPointSize(size); renderer.current?.setPointSize(size); }} />
      </label>
      <Button type="button" variant="outline" onClick={() => renderer.current?.resetView()}>Reset view</Button>
      <Button type="button" disabled={!loadSummary} onClick={save}>Save point-cloud screenshot</Button>
      {api.artifactUrl && artifactFor(capture, selection) && <a className="text-sm text-cyan-400 underline" download href={api.artifactUrl(artifactFor(capture, selection)!.artifact_id)}>Download PLY</a>}
    </div>
    <div ref={host} className="min-h-[400px] overflow-hidden rounded border border-slate-700 bg-slate-950" />
    <p aria-live="polite" className="text-xs text-slate-400">{status}</p>
  </section>;
}
