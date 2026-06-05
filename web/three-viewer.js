import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const mountedViewers = new WeakMap();
const cameraMemory = new Map();
const REMOTE_LOAD_TIMEOUT_MS = 9000;
const PROXY_LOAD_TIMEOUT_MS = 7000;

class NitoThreeViewport {
  constructor(root) {
    this.root = root;
    this.host = root.querySelector(".three-canvas-host");
    this.status = root.querySelector(".viewer-status");
    this.poster = root.querySelector(".three-poster");
    this.sampleId = root.dataset.sampleId || root.dataset.modelSrc || "model";
    this.modelSrc = root.dataset.modelSrc || "";
    this.fallbackSrc = root.dataset.fallbackSrc || "";
    this.model = null;
    this.modelMaterials = [];
    this.frame = null;
    this.disposed = false;
    this.wireframe = false;

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0xf3f8f6);

    this.camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1000);
    this.renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: false,
      powerPreference: "high-performance",
    });
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setSize(1, 1);
    this.host.appendChild(this.renderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.screenSpacePanning = true;
    this.controls.minDistance = 0.15;
    this.controls.maxDistance = 80;
    this.controls.autoRotateSpeed = 1.1;

    this.grid = new THREE.GridHelper(8, 16, 0x2d7d75, 0xc5d8d2);
    this.grid.material.transparent = true;
    this.grid.material.opacity = 0.55;
    this.scene.add(this.grid);

    this.axes = new THREE.AxesHelper(2.2);
    this.axes.material.depthTest = false;
    this.scene.add(this.axes);

    this.addLights();
    this.bindControls();
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(this.host);
    this.resize();
    this.restoreCamera();
    this.animate();
    this.load();
  }

  addLights() {
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0xaab9b4, 2.2));

    const key = new THREE.DirectionalLight(0xffffff, 2.7);
    key.position.set(4, 7, 6);
    this.scene.add(key);

    const rim = new THREE.DirectionalLight(0xb9fff3, 1.1);
    rim.position.set(-5, 3, -4);
    this.scene.add(rim);
  }

  bindControls() {
    this.root.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-three-action]");
      if (!button) return;
      const action = button.dataset.threeAction;
      if (action === "zoom-in") this.zoom(0.72);
      if (action === "zoom-out") this.zoom(1.38);
      if (action === "reset") this.resetView();
      if (action === "grid") {
        this.grid.visible = !this.grid.visible;
        button.classList.toggle("is-active", this.grid.visible);
      }
      if (action === "wireframe") {
        this.setWireframe(!this.wireframe);
        button.classList.toggle("is-active", this.wireframe);
      }
      if (action === "spin") {
        this.controls.autoRotate = !this.controls.autoRotate;
        button.classList.toggle("is-active", this.controls.autoRotate);
      }
    });
  }

  async load() {
    const candidates = [this.modelSrc, this.fallbackSrc].filter(Boolean);
    if (!candidates.length) {
      this.setStatus("No GLB source available");
      return;
    }

    for (let index = 0; index < candidates.length; index += 1) {
      const src = candidates[index];
      try {
        const timeoutMs = index ? PROXY_LOAD_TIMEOUT_MS : REMOTE_LOAD_TIMEOUT_MS;
        this.setStatus(index ? "Trying local proxy" : "Loading GLB");
        const gltf = await this.loadGltf(src, timeoutMs, (message) => this.setStatus(message));
        this.setModel(gltf.scene);
        this.setStatus("Orbit, pan, and zoom ready");
        this.poster?.classList.add("is-hidden");
        return;
      } catch (error) {
        this.setStatus(index ? "Local proxy did not return a GLB" : "Remote GLB did not respond; trying fallback");
        if (index === candidates.length - 1) {
          this.setStatus("GLB preview failed. The render image is shown until the local GLB is available.");
          this.poster?.classList.remove("is-hidden");
        }
      }
    }
  }

  loadGltf(src, timeoutMs, onProgress) {
    const loader = new GLTFLoader();
    loader.setCrossOrigin("anonymous");
    return new Promise((resolve, reject) => {
      const timeoutId = window.setTimeout(() => {
        reject(new Error(`GLB load timed out after ${timeoutMs}ms`));
      }, timeoutMs);
      loader.load(
        src,
        (gltf) => {
          window.clearTimeout(timeoutId);
          resolve(gltf);
        },
        (event) => {
          if (event.lengthComputable && event.total > 0) {
            const percent = Math.round((event.loaded / event.total) * 100);
            onProgress(`Loading GLB ${percent}%`);
          }
        },
        (error) => {
          window.clearTimeout(timeoutId);
          reject(error);
        },
      );
    });
  }

  setModel(model) {
    if (this.model) {
      this.scene.remove(this.model);
      this.disposeObject(this.model);
    }

    this.model = model;
    this.modelMaterials = [];
    this.scene.add(model);

    model.traverse((child) => {
      if (child.isMesh) {
        child.castShadow = true;
        child.receiveShadow = true;
        const materials = Array.isArray(child.material) ? child.material : [child.material];
        materials.filter(Boolean).forEach((material) => {
          this.modelMaterials.push(material);
          material.wireframe = this.wireframe;
        });
      }
    });

    const box = new THREE.Box3().setFromObject(model);
    const center = box.getCenter(new THREE.Vector3());
    model.position.sub(center);

    const centeredBox = new THREE.Box3().setFromObject(model);
    const size = centeredBox.getSize(new THREE.Vector3());
    const maxDimension = Math.max(size.x, size.y, size.z) || 1;
    const scale = 3.2 / maxDimension;
    model.scale.setScalar(scale);

    const framedBox = new THREE.Box3().setFromObject(model);
    this.grid.position.y = framedBox.min.y;
    this.axes.position.set(framedBox.min.x, framedBox.min.y, framedBox.min.z);
    this.frame = {
      box: framedBox,
      center: framedBox.getCenter(new THREE.Vector3()),
      radius: Math.max(framedBox.getSize(new THREE.Vector3()).length() * 0.5, 1),
    };
    if (!cameraMemory.has(this.sampleId)) {
      this.resetView();
    }
  }

  resetView() {
    if (!this.frame) {
      this.camera.position.set(3, 2, 4);
      this.controls.target.set(0, 0, 0);
      this.controls.update();
      return;
    }
    const { center, radius } = this.frame;
    const distance = radius / Math.sin(THREE.MathUtils.degToRad(this.camera.fov * 0.5));
    this.camera.near = Math.max(0.01, radius / 100);
    this.camera.far = Math.max(100, radius * 80);
    this.camera.updateProjectionMatrix();
    this.camera.position.copy(center).add(new THREE.Vector3(distance * 0.55, distance * 0.34, distance * 0.72));
    this.controls.target.copy(center);
    this.controls.update();
    this.rememberCamera();
  }

  restoreCamera() {
    const saved = cameraMemory.get(this.sampleId);
    if (!saved) {
      this.camera.position.set(3, 2, 4);
      this.controls.target.set(0, 0, 0);
      return;
    }
    this.camera.position.fromArray(saved.position);
    this.controls.target.fromArray(saved.target);
    this.camera.near = saved.near;
    this.camera.far = saved.far;
    this.camera.updateProjectionMatrix();
    this.controls.update();
  }

  rememberCamera() {
    cameraMemory.set(this.sampleId, {
      position: this.camera.position.toArray(),
      target: this.controls.target.toArray(),
      near: this.camera.near,
      far: this.camera.far,
    });
  }

  zoom(factor) {
    const offset = this.camera.position.clone().sub(this.controls.target);
    offset.multiplyScalar(factor);
    this.camera.position.copy(this.controls.target).add(offset);
    this.controls.update();
    this.rememberCamera();
  }

  setWireframe(enabled) {
    this.wireframe = enabled;
    this.modelMaterials.forEach((material) => {
      material.wireframe = enabled;
      material.needsUpdate = true;
    });
  }

  resize() {
    const bounds = this.host.getBoundingClientRect();
    const width = Math.max(1, Math.floor(bounds.width));
    const height = Math.max(1, Math.floor(bounds.height));
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height, false);
  }

  animate() {
    if (this.disposed) return;
    if (!document.body.contains(this.root)) {
      this.dispose();
      return;
    }
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
    this.rememberCamera();
    requestAnimationFrame(() => this.animate());
  }

  setStatus(message) {
    if (this.status) this.status.textContent = message;
  }

  disposeObject(object) {
    object.traverse((child) => {
      if (child.geometry) child.geometry.dispose();
      const materials = Array.isArray(child.material) ? child.material : [child.material];
      materials.filter(Boolean).forEach((material) => material.dispose?.());
    });
  }

  dispose() {
    this.disposed = true;
    this.rememberCamera();
    this.resizeObserver?.disconnect();
    this.controls?.dispose();
    if (this.model) this.disposeObject(this.model);
    this.renderer?.dispose();
    this.renderer?.domElement?.remove();
  }
}

function mountAll(container = document) {
  container.querySelectorAll(".three-editor").forEach((root) => {
    if (mountedViewers.has(root)) return;
    mountedViewers.set(root, new NitoThreeViewport(root));
  });
}

window.NitoThreeViewer = { mountAll };
window.dispatchEvent(new CustomEvent("nito-three-ready"));
