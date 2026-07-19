import { useEffect, useRef } from 'react';
import * as THREE from 'three';

export function ThreeMeshBackground() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const container = containerRef.current;
    const width = container.clientWidth;
    const height = container.clientHeight;

    // SCENE & CAMERA
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x09090b, 0.015);

    const camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 100);
    camera.position.z = 32;

    // RENDERER
    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    renderer.setClearColor(0x09090b, 0); // Transparent so background gradient is visible
    container.appendChild(renderer.domElement);

    // MOUSE TRACKING
    const mouse = { x: 0, y: 0, targetX: 0, targetY: 0 };
    const handleMouseMove = (e: MouseEvent) => {
      mouse.targetX = (e.clientX / window.innerWidth - 0.5) * 12;
      mouse.targetY = -(e.clientY / window.innerHeight - 0.5) * 12;
    };
    window.addEventListener('mousemove', handleMouseMove);

    // PARTICLES / NODES
    const particleCount = 75;
    const positions = new Float32Array(particleCount * 3);
    const velocities: { x: number; y: number; z: number }[] = [];
    const sizes = new Float32Array(particleCount);

    for (let i = 0; i < particleCount; i++) {
      // Spawn particles in a wider ellipsoid volume
      positions[i * 3] = (Math.random() - 0.5) * 50;
      positions[i * 3 + 1] = (Math.random() - 0.5) * 30;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 20;

      velocities.push({
        x: (Math.random() - 0.5) * 0.05,
        y: (Math.random() - 0.5) * 0.05,
        z: (Math.random() - 0.5) * 0.03,
      });

      sizes[i] = Math.random() * 2 + 1;
    }

    // Particle Geometry
    const particleGeometry = new THREE.BufferGeometry();
    particleGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    // Particle Material - glowing subtle matrix/mint nodes
    const sparkTexture = createCircleTexture();
    const particleMaterial = new THREE.PointsMaterial({
      size: 1.2,
      sizeAttenuation: true,
      transparent: true,
      opacity: 0.7,
      color: 0x10b981, // Mint/emerald stardust
      map: sparkTexture,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });

    const pointCloud = new THREE.Points(particleGeometry, particleMaterial);
    scene.add(pointCloud);

    // MESH LINE CONNECTIONS
    // Create connection lines between close particles
    const maxConnections = 150;
    const lineIndices = new Uint16Array(maxConnections * 2);
    const linePositions = new Float32Array(maxConnections * 2 * 3);

    const lineGeometry = new THREE.BufferGeometry();
    lineGeometry.setAttribute('position', new THREE.BufferAttribute(linePositions, 3));

    // Glowy green connection lines
    const lineMaterial = new THREE.LineBasicMaterial({
      color: 0x059669, // Emerald green lines
      transparent: true,
      opacity: 0.18,
      blending: THREE.AdditiveBlending,
    });

    const connectionLines = new THREE.LineSegments(lineGeometry, lineMaterial);
    scene.add(connectionLines);

    // HELPER: CREATE CIRCLE TEXTURE FOR PARTICLES
    function createCircleTexture() {
      const size = 64;
      const canvas = document.createElement('canvas');
      canvas.width = size;
      canvas.height = size;
      const ctx = canvas.getContext('2d');
      if (ctx) {
        // Gradient fill
        const grad = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
        grad.addColorStop(0, 'rgba(110, 231, 183, 1)'); // Emerald 300
        grad.addColorStop(0.3, 'rgba(16, 185, 129, 0.8)'); // Emerald 500
        grad.addColorStop(0.6, 'rgba(5, 150, 105, 0.2)'); // Emerald 600
        grad.addColorStop(1, 'rgba(0, 0, 0, 0)');
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, size, size);
      }
      const texture = new THREE.Texture(canvas);
      texture.needsUpdate = true;
      return texture;
    }

    // ANIMATION LOOP
    let animationFrameId: number;
    const clock = new THREE.Clock();

    const animate = () => {
      const delta = clock.getDelta();
      const time = clock.getElapsedTime();

      // Smooth mouse damping
      mouse.x += (mouse.targetX - mouse.x) * 0.05;
      mouse.y += (mouse.targetY - mouse.y) * 0.05;

      // Adjust group coordinate or camera slightly based on mouse
      pointCloud.rotation.y = time * 0.015 + mouse.x * 0.01;
      pointCloud.rotation.x = mouse.y * 0.01;
      connectionLines.rotation.y = pointCloud.rotation.y;
      connectionLines.rotation.x = pointCloud.rotation.x;

      const positionsAttr = particleGeometry.attributes.position as THREE.BufferAttribute;

      // Update particle positions
      for (let i = 0; i < particleCount; i++) {
        const xIdx = i * 3;
        const yIdx = i * 3 + 1;
        const zIdx = i * 3 + 2;

        let posX = positionsAttr.array[xIdx] + velocities[i].x;
        let posY = positionsAttr.array[yIdx] + velocities[i].y;
        let posZ = positionsAttr.array[zIdx] + velocities[i].z;

        // Boundary checks
        if (posX > 25 || posX < -25) velocities[i].x *= -1;
        if (posY > 18 || posY < -18) velocities[i].y *= -1;
        if (posZ > 12 || posZ < -12) velocities[i].z *= -1;

        positionsAttr.array[xIdx] = posX;
        positionsAttr.array[yIdx] = posY;
        positionsAttr.array[zIdx] = posZ;
      }
      positionsAttr.needsUpdate = true;

      // Update lines based on proximity
      let lineCount = 0;
      const linePositionsAttr = lineGeometry.attributes.position as THREE.BufferAttribute;

      for (let i = 0; i < particleCount && lineCount < maxConnections; i++) {
        const x1 = positionsAttr.array[i * 3];
        const y1 = positionsAttr.array[i * 3 + 1];
        const z1 = positionsAttr.array[i * 3 + 2];

        for (let j = i + 1; j < particleCount && lineCount < maxConnections; j++) {
          const x2 = positionsAttr.array[j * 3];
          const y2 = positionsAttr.array[j * 3 + 1];
          const z2 = positionsAttr.array[j * 3 + 2];

          const distSquare = (x1 - x2) ** 2 + (y1 - y2) ** 2 + (z1 - z2) ** 2;
          const limit = 60; // Max connection distance squared

          if (distSquare < limit) {
            const idx = lineCount * 2;
            
            // Point A
            linePositionsAttr.array[idx * 3] = x1;
            linePositionsAttr.array[idx * 3 + 1] = y1;
            linePositionsAttr.array[idx * 3 + 2] = z1;

            // Point B
            linePositionsAttr.array[idx * 3 + 3] = x2;
            linePositionsAttr.array[idx * 3 + 1 + 3] = y2;
            linePositionsAttr.array[idx * 3 + 2 + 3] = z2;

            lineCount++;
          }
        }
      }

      // Hide unused connection line points
      for (let i = lineCount; i < maxConnections; i++) {
        const idx = i * 2;
        linePositionsAttr.array[idx * 3] = 9999;
        linePositionsAttr.array[idx * 3 + 3] = 9999;
      }

      linePositionsAttr.needsUpdate = true;
      renderer.render(scene, camera);
      animationFrameId = requestAnimationFrame(animate);
    };

    animate();

    // RESIZE OBSERVER
    const observer = new ResizeObserver((entries) => {
      for (let entry of entries) {
        const { width, height } = entry.contentRect;
        renderer.setSize(width, height);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
      }
    });
    observer.observe(container);

    // CLEANUP
    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('mousemove', handleMouseMove);
      observer.disconnect();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
      renderer.dispose();
      particleGeometry.dispose();
      particleMaterial.dispose();
      lineGeometry.dispose();
      lineMaterial.dispose();
    };
  }, []);

  return (
    <div
      id="three-shader-canvas-root"
      ref={containerRef}
      className="absolute inset-0 w-full h-full -z-10 bg-[#09090b]"
      style={{ pointerEvents: 'none' }}
    />
  );
}
