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
    this.labelSrc = root.dataset.labelSrc || "";
    this.model = null;
    this.labelGroup = null;
    this.labelBoneCount = 0;
    this.modelMaterials = [];
    this.frame = null;
    this.meshCount = 0;
    this.disposed = false;
    this.wireframe = false;
    this.labelsVisible = Boolean(this.labelSrc);
    this.modelStatus = "";

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x090c0c);

    this.camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1000);
    this.renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: false,
      powerPreference: "high-performance",
      preserveDrawingBuffer: true,
    });
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.setClearColor(0x090c0c, 1);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setSize(1, 1, false);
    this.renderer.domElement.className = "three-canvas";
    this.host.appendChild(this.renderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.screenSpacePanning = true;
    this.controls.minDistance = 0.15;
    this.controls.maxDistance = 80;
    this.controls.autoRotateSpeed = 1.1;

    this.grid = new THREE.GridHelper(8, 16, 0xb78a45, 0xd8c6a3);
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
    this.resetView();
    this.animate();
    this.load();
  }

  addLights() {
    this.scene.add(new THREE.HemisphereLight(0xfff4de, 0x9b7a48, 2.2));

    const key = new THREE.DirectionalLight(0xffffff, 2.7);
    key.position.set(4, 7, 6);
    this.scene.add(key);

    const rim = new THREE.DirectionalLight(0xffd28a, 1.1);
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
      if (action === "labels") {
        this.setLabelsVisible(!this.labelsVisible);
        button.classList.toggle("is-active", this.labelsVisible);
      }
      if (action === "spin") {
        this.controls.autoRotate = !this.controls.autoRotate;
        button.classList.toggle("is-active", this.controls.autoRotate);
      }
    });

    this.controls.addEventListener("end", () => this.rememberCamera());
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
        await this.loadLabelOverlay();
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
    this.clearLabelOverlay();
    if (this.model) {
      this.scene.remove(this.model);
      this.disposeObject(this.model);
    }

    const sourceBox = new THREE.Box3().setFromObject(model);
    if (sourceBox.isEmpty()) {
      this.setStatus("GLB loaded, but no visible mesh bounds were found");
      return;
    }

    const sourceCenter = sourceBox.getCenter(new THREE.Vector3());
    const sourceSize = sourceBox.getSize(new THREE.Vector3());
    const maxDimension = Math.max(sourceSize.x, sourceSize.y, sourceSize.z) || 1;
    const normalizedRoot = new THREE.Group();
    normalizedRoot.name = "NitoNormalizedModel";
    normalizedRoot.scale.setScalar(3.2 / maxDimension);
    model.position.sub(sourceCenter);
    normalizedRoot.add(model);

    this.model = normalizedRoot;
    this.modelMaterials = [];
    this.meshCount = 0;
    this.scene.add(normalizedRoot);

    normalizedRoot.updateMatrixWorld(true);
    normalizedRoot.traverse((child) => {
      if (child.isMesh) {
        this.meshCount += 1;
        child.castShadow = true;
        child.frustumCulled = false;
        child.receiveShadow = true;
        child.renderOrder = 2;
        child.material = Array.isArray(child.material)
          ? child.material.map((material) => this.createVisibleMaterial(material))
          : this.createVisibleMaterial(child.material);
        const materials = Array.isArray(child.material) ? child.material : [child.material];
        materials.filter(Boolean).forEach((material) => {
          this.modelMaterials.push(material);
          material.wireframe = this.wireframe;
        });
      }
    });

    const framedBox = new THREE.Box3().setFromObject(normalizedRoot);
    this.grid.position.y = framedBox.min.y;
    this.axes.position.set(framedBox.min.x, framedBox.min.y, framedBox.min.z);
    this.frame = {
      box: framedBox,
      center: framedBox.getCenter(new THREE.Vector3()),
      radius: Math.max(framedBox.getSize(new THREE.Vector3()).length() * 0.5, 1),
    };

    this.resetView();
    this.modelStatus = `Orbit, pan, and zoom ready (${this.meshCount} mesh${this.meshCount === 1 ? "" : "es"})`;
    this.setStatus(this.modelStatus);
  }

  createVisibleMaterial(originalMaterial) {
    const source = Array.isArray(originalMaterial) ? originalMaterial[0] : originalMaterial;
    const map = source?.map || null;
    if (map) {
      map.colorSpace = THREE.SRGBColorSpace;
      map.needsUpdate = true;
    }
    const material = new THREE.MeshBasicMaterial({
      color: new THREE.Color(map ? 0xffffff : 0xdce8e3),
      map,
      side: THREE.DoubleSide,
      transparent: false,
      opacity: 1,
      depthTest: true,
    });
    material.name = source?.name ? `${source.name}_nito_visible` : "nito_visible_material";
    material.wireframe = this.wireframe;
    return material;
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
      return false;
    }
    if (this.frame) {
      const savedTarget = new THREE.Vector3().fromArray(saved.target);
      const maxReasonableOffset = this.frame.radius * 4;
      if (savedTarget.distanceTo(this.frame.center) > maxReasonableOffset) {
        cameraMemory.delete(this.sampleId);
        return false;
      }
    }
    this.camera.position.fromArray(saved.position);
    this.controls.target.fromArray(saved.target);
    this.camera.near = saved.near;
    this.camera.far = saved.far;
    this.camera.updateProjectionMatrix();
    this.controls.update();
    return true;
  }

  rememberCamera() {
    if (!this.frame) return;
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

  async loadLabelOverlay() {
    if (!this.labelSrc || !this.frame) return;
    try {
      this.setStatus(`${this.modelStatus || "Model ready"}; loading skeleton labels`);
      const response = await fetch(this.labelSrc, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`Label JSON returned HTTP ${response.status}`);
      }
      const label = await response.json();
      this.setLabelOverlay(label);
    } catch (error) {
      this.clearLabelOverlay();
      this.setStatus(`${this.modelStatus || "Model ready"}; skeleton labels failed to load`);
    }
  }

  setLabelOverlay(label) {
    this.clearLabelOverlay();
    const guideBones = label?.guide_bones && typeof label.guide_bones === "object" ? label.guide_bones : {};
    const bones = Object.entries(guideBones)
      .map(([name, value]) => ({
        name,
        head: this.labelPointToThree(value?.head),
        tail: this.labelPointToThree(value?.tail),
      }))
      .filter((bone) => bone.head && bone.tail && bone.head.distanceToSquared(bone.tail) > 0.000001);

    if (!bones.length) {
      this.setStatus(`${this.modelStatus || "Model ready"}; label file has no drawable bones`);
      return;
    }

    const labelPoints = bones.flatMap((bone) => [bone.head, bone.tail]);
    const labelBox = new THREE.Box3().setFromPoints(labelPoints);
    const labelCenter = labelBox.getCenter(new THREE.Vector3());
    const labelSize = labelBox.getSize(new THREE.Vector3());
    const targetBox = this.frame.box;
    const targetCenter = targetBox.getCenter(new THREE.Vector3());
    const targetSize = targetBox.getSize(new THREE.Vector3());
    const ratios = ["x", "y", "z"]
      .map((axis) => (labelSize[axis] > 0.000001 ? targetSize[axis] / labelSize[axis] : 0))
      .filter((value) => Number.isFinite(value) && value > 0);
    const labelScale = (ratios.length ? Math.min(...ratios) : 1) * 0.94;
    const targetRadius = Math.max(targetSize.length(), 1);
    const boneRadius = THREE.MathUtils.clamp(targetRadius * 0.006, 0.012, 0.04);
    const jointRadius = boneRadius * 2.15;
    const jointPoints = [];

    const transformPoint = (point) => point.clone().sub(labelCenter).multiplyScalar(labelScale).add(targetCenter);
    const group = new THREE.Group();
    group.name = "NitoVerifiedSkeletonOverlay";
    group.visible = this.labelsVisible;

    bones.forEach((bone) => {
      const start = transformPoint(bone.head);
      const end = transformPoint(bone.tail);
      jointPoints.push(start, end);
      const color = this.labelBoneColor(bone.name);
      group.add(this.createBoneCylinder(start, end, boneRadius, color));
    });

    const sphereGeometry = new THREE.SphereGeometry(jointRadius, 16, 10);
    const jointMaterial = new THREE.MeshBasicMaterial({
      color: 0xfff4de,
      depthTest: false,
      transparent: true,
      opacity: 0.96,
    });
    this.uniquePoints(jointPoints).forEach((point) => {
      const joint = new THREE.Mesh(sphereGeometry, jointMaterial);
      joint.position.copy(point);
      joint.renderOrder = 12;
      group.add(joint);
    });

    this.labelGroup = group;
    this.labelBoneCount = bones.length;
    this.scene.add(group);
    this.setStatus(
      `${this.modelStatus || "Model ready"}${this.labelsVisible ? ` + skeleton overlay (${bones.length} bones)` : ""}`,
    );
  }

  labelPointToThree(value) {
    if (!Array.isArray(value) || value.length < 3) return null;
    const [x, y, z] = value.map((item) => Number(item));
    if (![x, y, z].every(Number.isFinite)) return null;
    return new THREE.Vector3(x, z, y);
  }

  labelBoneColor(name) {
    if (name.includes("_left_")) return 0x62d0c4;
    if (name.includes("_right_")) return 0xf0b35f;
    if (name.includes("tail")) return 0x9c8cff;
    if (name.includes("head") || name.includes("neck")) return 0xfff4de;
    return 0xd2a75f;
  }

  createBoneCylinder(start, end, radius, color) {
    const direction = end.clone().sub(start);
    const length = direction.length();
    const geometry = new THREE.CylinderGeometry(radius, radius, length, 14, 1, false);
    const material = new THREE.MeshBasicMaterial({
      color,
      depthTest: false,
      transparent: true,
      opacity: 0.92,
    });
    const cylinder = new THREE.Mesh(geometry, material);
    cylinder.position.copy(start).add(end).multiplyScalar(0.5);
    cylinder.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize());
    cylinder.renderOrder = 11;
    return cylinder;
  }

  uniquePoints(points) {
    const seen = new Set();
    const unique = [];
    points.forEach((point) => {
      const key = point.toArray().map((value) => value.toFixed(4)).join(",");
      if (seen.has(key)) return;
      seen.add(key);
      unique.push(point);
    });
    return unique;
  }

  setLabelsVisible(enabled) {
    this.labelsVisible = enabled;
    if (this.labelGroup) {
      this.labelGroup.visible = enabled;
      this.setStatus(
        `${this.modelStatus || "Model ready"}${enabled && this.labelBoneCount ? ` + skeleton overlay (${this.labelBoneCount} bones)` : ""}`,
      );
    } else if (enabled && this.labelSrc) {
      this.loadLabelOverlay();
    }
  }

  clearLabelOverlay() {
    this.labelBoneCount = 0;
    if (!this.labelGroup) return;
    this.scene.remove(this.labelGroup);
    this.disposeObject(this.labelGroup);
    this.labelGroup = null;
  }

  resize() {
    const bounds = this.host.getBoundingClientRect();
    const width = Math.max(1, Math.floor(bounds.width));
    const height = Math.max(1, Math.floor(bounds.height));
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height, true);
  }

  animate() {
    if (this.disposed) return;
    if (!document.body.contains(this.root)) {
      this.dispose();
      return;
    }
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
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
    this.clearLabelOverlay();
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
