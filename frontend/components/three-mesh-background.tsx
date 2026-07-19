"use client";

/**
 * ThreeMeshBackground — the global animated "agent mesh" backdrop (Requirement 1).
 *
 * A WebGL point cloud of ~75 drifting emerald "stardust" nodes that dynamically
 * connect with line segments when they are close, with smooth mouse parallax.
 * Rendered into a self-contained `fixed inset-0` container so it sits behind the
 * whole app (every route), above the static `artistic-background`/`artistic-grid`
 * gradient layers but below all page content.
 *
 * It is purely decorative: `aria-hidden`, `pointer-events-none`, and the renderer
 * clears with alpha 0 so the obsidian gradient + sub-pixel grid show through. The
 * effect honours `prefers-reduced-motion` by freezing node drift while keeping the
 * static field. All Three.js resources are disposed on unmount to avoid leaks.
 */
import { useEffect, useRef } from "react";
import * as THREE from "three";

const PARTICLE_COUNT = 75;
const MAX_CONNECTIONS = 150;
const LINK_DISTANCE = 10;

/** Procedural radial-gradient circle texture for soft, round glowing nodes. */
function createCircleTexture(): THREE.CanvasTexture {
  const size = 64;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    const grad = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    grad.addColorStop(0, "rgba(255, 255, 255, 1)");
    grad.addColorStop(0.2, "rgba(16, 185, 129, 0.8)");
    grad.addColorStop(0.5, "rgba(16, 185, 129, 0.2)");
    grad.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, size, size);
  }
  return new THREE.CanvasTexture(canvas);
}

export function ThreeMeshBackground() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let width = container.clientWidth || window.innerWidth;
    let height = container.clientHeight || window.innerHeight;

    // SCENE & CAMERA
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x09090b, 0.015);

    const camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 100);
    camera.position.z = 32;

    // RENDERER (transparent so the layout gradient/grid show through)
    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    renderer.setClearColor(0x09090b, 0);
    container.appendChild(renderer.domElement);

    // MOUSE TRACKING WITH INERTIA
    const mouse = { x: 0, y: 0, targetX: 0, targetY: 0 };
    const handleMouseMove = (e: MouseEvent) => {
      mouse.targetX = (e.clientX / window.innerWidth - 0.5) * 12;
      mouse.targetY = -(e.clientY / window.innerHeight - 0.5) * 12;
    };
    window.addEventListener("mousemove", handleMouseMove);

    // PARTICLES (NODES)
    const positions = new Float32Array(PARTICLE_COUNT * 3);
    const velocities: { x: number; y: number; z: number }[] = [];

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      positions[i * 3] = (Math.random() - 0.5) * 50;
      positions[i * 3 + 1] = (Math.random() - 0.5) * 30;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 20;

      velocities.push({
        x: (Math.random() - 0.5) * 0.05,
        y: (Math.random() - 0.5) * 0.05,
        z: (Math.random() - 0.5) * 0.03,
      });
    }

    const particleGeometry = new THREE.BufferGeometry();
    const positionAttr = new THREE.BufferAttribute(positions, 3);
    particleGeometry.setAttribute("position", positionAttr);

    const sparkTexture = createCircleTexture();
    const particleMaterial = new THREE.PointsMaterial({
      size: 1.2,
      sizeAttenuation: true,
      transparent: true,
      opacity: 0.7,
      color: 0x10b981,
      map: sparkTexture,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });

    const pointCloud = new THREE.Points(particleGeometry, particleMaterial);
    scene.add(pointCloud);

    // MESH EDGE CONNECTIONS
    const linePositions = new Float32Array(MAX_CONNECTIONS * 2 * 3);
    const lineGeometry = new THREE.BufferGeometry();
    const lineAttr = new THREE.BufferAttribute(linePositions, 3);
    lineGeometry.setAttribute("position", lineAttr);

    const lineMaterial = new THREE.LineBasicMaterial({
      color: 0x059669,
      transparent: true,
      opacity: 0.18,
      blending: THREE.AdditiveBlending,
    });

    const connectionLines = new THREE.LineSegments(lineGeometry, lineMaterial);
    scene.add(connectionLines);

    // GROUP for mouse parallax rotation
    const meshGroup = new THREE.Group();
    meshGroup.add(pointCloud);
    meshGroup.add(connectionLines);
    scene.add(meshGroup);

    // ANIMATION LOOP
    let animationFrameId = 0;
    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);

      // Smooth camera interpolation based on mouse inertia (parallax).
      mouse.x += (mouse.targetX - mouse.x) * 0.05;
      mouse.y += (mouse.targetY - mouse.y) * 0.05;
      camera.position.x = mouse.x;
      camera.position.y = mouse.y;
      camera.lookAt(scene.position);

      if (!reduceMotion) {
        for (let i = 0; i < PARTICLE_COUNT; i++) {
          const v = velocities[i];
          if (!v) continue;
          const i3 = i * 3;
          const x = (positions[i3] ?? 0) + v.x;
          const y = (positions[i3 + 1] ?? 0) + v.y;
          const z = (positions[i3 + 2] ?? 0) + v.z;

          // Boundary checks (bounce back).
          if (Math.abs(x) > 25) v.x *= -1;
          if (Math.abs(y) > 15) v.y *= -1;
          if (Math.abs(z) > 10) v.z *= -1;

          positions[i3] = x;
          positions[i3 + 1] = y;
          positions[i3 + 2] = z;
        }
        positionAttr.needsUpdate = true;
      }

      // Recalculate dynamic edge lines based on proximity.
      let lineCount = 0;

      for (let i = 0; i < PARTICLE_COUNT; i++) {
        const i3 = i * 3;
        const ax = positions[i3] ?? 0;
        const ay = positions[i3 + 1] ?? 0;
        const az = positions[i3 + 2] ?? 0;

        for (let j = i + 1; j < PARTICLE_COUNT; j++) {
          if (lineCount >= MAX_CONNECTIONS) break;

          const j3 = j * 3;
          const bx = positions[j3] ?? 0;
          const by = positions[j3 + 1] ?? 0;
          const bz = positions[j3 + 2] ?? 0;

          const dx = ax - bx;
          const dy = ay - by;
          const dz = az - bz;
          const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);

          if (dist < LINK_DISTANCE) {
            const idx = lineCount * 6;
            linePositions[idx] = ax;
            linePositions[idx + 1] = ay;
            linePositions[idx + 2] = az;
            linePositions[idx + 3] = bx;
            linePositions[idx + 4] = by;
            linePositions[idx + 5] = bz;
            lineCount++;
          }
        }
      }

      // Push unused connection lines out of view.
      for (let i = lineCount; i < MAX_CONNECTIONS; i++) {
        const idx = i * 6;
        linePositions[idx] = 0;
        linePositions[idx + 1] = 0;
        linePositions[idx + 2] = 0;
        linePositions[idx + 3] = 0;
        linePositions[idx + 4] = 0;
        linePositions[idx + 5] = 0;
      }
      lineAttr.needsUpdate = true;

      renderer.render(scene, camera);
    };

    animate();

    // RESIZE OBSERVER (size from the container, no direct window reads)
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        width = entry.contentRect.width;
        height = entry.contentRect.height;
        renderer.setSize(width, height);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
      }
    });
    resizeObserver.observe(container);

    // CLEAN LIFECYCLE
    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener("mousemove", handleMouseMove);
      resizeObserver.disconnect();

      if (renderer.domElement.parentNode === container) {
        container.removeChild(renderer.domElement);
      }

      particleGeometry.dispose();
      particleMaterial.dispose();
      sparkTexture.dispose();
      lineGeometry.dispose();
      lineMaterial.dispose();
      renderer.dispose();
    };
  }, []);

  return (
    <div
      ref={containerRef}
      aria-hidden="true"
      className="pointer-events-none fixed inset-0"
      style={{ zIndex: 2 }}
    />
  );
}
