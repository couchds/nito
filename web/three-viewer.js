import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const mountedViewers = new WeakMap();
const cameraMemory = new Map();
const REMOTE_LOAD_TIMEOUT_MS = 9000;
const PROXY_LOAD_TIMEOUT_MS = 7000;

const LEG_SIDES = ["front_left", "front_right", "rear_left", "rear_right"];

// Canonical guide topology. Joints are shared between connected bones so a
// drag keeps every chain attached, matching the trainer's reconstruction.
const GUIDE_JOINT_SPECS = [
  ["pelvis_head", "qwg_guide_pelvis", "head"],
  ["pelvis_tail", "qwg_guide_pelvis", "tail"],
  ["spine_tail", "qwg_guide_spine", "tail"],
  ["chest_tail", "qwg_guide_chest", "tail"],
  ["neck_tail", "qwg_guide_neck", "tail"],
  ["head_tail", "qwg_guide_head", "tail"],
  ["tail_head", "qwg_guide_tail", "head"],
  ["tail_tail", "qwg_guide_tail", "tail"],
  ...LEG_SIDES.flatMap((side) => [
    [`${side}_upper_head`, `qwg_guide_${side}_upper`, "head"],
    [`${side}_mid`, `qwg_guide_${side}_upper`, "tail"],
    [`${side}_lower`, `qwg_guide_${side}_lower`, "tail"],
    [`${side}_foot`, `qwg_guide_${side}_foot`, "tail"],
  ]),
];

const GUIDE_EDITOR_BONES = {
  qwg_guide_pelvis: ["pelvis_head", "pelvis_tail"],
  qwg_guide_spine: ["pelvis_tail", "spine_tail"],
  qwg_guide_chest: ["spine_tail", "chest_tail"],
  qwg_guide_neck: ["chest_tail", "neck_tail"],
  qwg_guide_head: ["neck_tail", "head_tail"],
  qwg_guide_tail: ["tail_head", "tail_tail"],
};
LEG_SIDES.forEach((side) => {
  GUIDE_EDITOR_BONES[`qwg_guide_${side}_upper`] = [`${side}_upper_head`, `${side}_mid`];
  GUIDE_EDITOR_BONES[`qwg_guide_${side}_lower`] = [`${side}_mid`, `${side}_lower`];
  GUIDE_EDITOR_BONES[`qwg_guide_${side}_foot`] = [`${side}_lower`, `${side}_foot`];
});

const GUIDE_JOINT_HINTS = {
  pelvis_head: "Hip block, just forward of the tail base, inside the body.",
  pelvis_tail: "Lumbar back where the rump joins the spine.",
  spine_tail: "Middle/front of the rib cage on the centerline.",
  chest_tail: "Withers / upper chest at the base of the neck.",
  neck_tail: "Base of skull, behind the ears.",
  head_tail: "Through the center of the skull or muzzle.",
  tail_head: "Where the tail exits the rump.",
  tail_tail: "Along the bony tail core; ignore fur.",
  upper_head: "Inside the body where the leg enters the torso.",
  mid: "Elbow (front) or stifle/knee (rear): the first big bend.",
  lower: "Wrist/carpus (front) or hock/ankle (rear), above the foot.",
  foot: "Toe/hoof ground-contact direction.",
};

function guideJointLabel(name) {
  return name.replace(/_/g, " ");
}

function guideJointHint(name) {
  if (GUIDE_JOINT_HINTS[name]) return GUIDE_JOINT_HINTS[name];
  const suffix = ["upper_head", "mid", "lower", "foot"].find((part) => name.endsWith(part));
  return suffix ? GUIDE_JOINT_HINTS[suffix] : "";
}

function mirrorJointName(name) {
  if (name.includes("_left_")) return name.replace("_left_", "_right_");
  if (name.includes("_right_")) return name.replace("_right_", "_left_");
  return "";
}

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
    this.labelMeshSrc = root.dataset.labelMeshSrc || "";
    this.guideApiUrl = root.dataset.guideApi || "";
    this.editor = null;
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
    this.modelCoordinateTransform = null;
    this.labelCoordinatesMatchModel = false;

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
      if (action === "edit") {
        this.toggleSkeletonEditor(button);
      }
    });

    this.root.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-editor-action]");
      if (!button || !this.editor) return;
      this.handleEditorAction(button.dataset.editorAction, button);
    });

    this.controls.addEventListener("end", () => this.rememberCamera());

    // Capture phase so joint drags win over OrbitControls' own pointer handlers.
    const canvas = this.renderer.domElement;
    canvas.addEventListener("pointerdown", (event) => this.onEditorPointerDown(event), { capture: true });
    canvas.addEventListener("pointermove", (event) => this.onEditorPointerMove(event), { capture: true });
    canvas.addEventListener("pointerup", (event) => this.onEditorPointerUp(event), { capture: true });
    canvas.addEventListener("pointerleave", (event) => this.onEditorPointerUp(event), { capture: true });
    this.editorKeyHandler = (event) => {
      if (!this.editor) return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
        event.preventDefault();
        this.editorUndo();
      }
    };
    window.addEventListener("keydown", this.editorKeyHandler);
  }

  async load() {
    const candidates = [this.labelMeshSrc, this.modelSrc, this.fallbackSrc].filter(Boolean);
    if (!candidates.length) {
      this.setStatus("No 3D model source available");
      return;
    }

    for (let index = 0; index < candidates.length; index += 1) {
      const src = candidates[index];
      try {
        const timeoutMs = index ? PROXY_LOAD_TIMEOUT_MS : REMOTE_LOAD_TIMEOUT_MS;
        const isLabelMesh = src === this.labelMeshSrc;
        this.setStatus(isLabelMesh ? "Loading canonical label mesh" : index ? "Trying local proxy" : "Loading GLB");
        const model = await this.loadModel(src, timeoutMs, (message) => this.setStatus(message));
        this.setModel(model, { coordinatesMatchLabel: isLabelMesh });
        await this.loadLabelOverlay();
        this.poster?.classList.add("is-hidden");
        return;
      } catch (error) {
        this.setStatus(index ? "Model fallback did not load" : "Primary 3D source did not load; trying fallback");
        if (index === candidates.length - 1) {
          this.setStatus("3D preview failed. The render image is shown until a loadable model is available.");
          this.poster?.classList.remove("is-hidden");
        }
      }
    }
  }

  loadModel(src, timeoutMs, onProgress) {
    const extension = this.modelExtension(src);
    if (extension === "obj") {
      return this.loadObj(src, timeoutMs, onProgress);
    }
    return this.loadGltf(src, timeoutMs, onProgress).then((gltf) => gltf.scene);
  }

  modelExtension(src) {
    try {
      return new URL(src, window.location.href).pathname.split(".").pop().toLowerCase();
    } catch (error) {
      return src.split("?")[0].split(".").pop().toLowerCase();
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

  loadObj(src, timeoutMs, onProgress) {
    return new Promise((resolve, reject) => {
      const controller = new AbortController();
      const timeoutId = window.setTimeout(() => {
        controller.abort();
        reject(new Error(`OBJ load timed out after ${timeoutMs}ms`));
      }, timeoutMs);
      fetch(src, { cache: "no-store", signal: controller.signal })
        .then((response) => {
          if (!response.ok) throw new Error(`OBJ returned HTTP ${response.status}`);
          onProgress("Loading canonical label mesh");
          return response.text();
        })
        .then((text) => {
          window.clearTimeout(timeoutId);
          resolve(this.parseObj(text));
        })
        .catch((error) => {
          window.clearTimeout(timeoutId);
          reject(error);
        });
    });
  }

  parseObj(text) {
    const vertices = [];
    const positions = [];
    const lines = text.split(/\r?\n/);

    const resolveIndex = (token) => {
      const rawIndex = Number.parseInt(token.split("/")[0], 10);
      if (!Number.isFinite(rawIndex) || rawIndex === 0) return -1;
      return rawIndex > 0 ? rawIndex - 1 : vertices.length + rawIndex;
    };

    lines.forEach((line) => {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) return;
      const parts = trimmed.split(/\s+/);
      if (parts[0] === "v" && parts.length >= 4) {
        vertices.push(this.blenderPointToThree(parts.slice(1, 4)));
      }
      if (parts[0] === "f" && parts.length >= 4) {
        const faceIndices = parts.slice(1).map(resolveIndex).filter((index) => vertices[index]);
        for (let index = 1; index < faceIndices.length - 1; index += 1) {
          [faceIndices[0], faceIndices[index], faceIndices[index + 1]].forEach((vertexIndex) => {
            positions.push(...vertices[vertexIndex].toArray());
          });
        }
      }
    });

    if (!positions.length) {
      throw new Error("OBJ did not contain drawable faces");
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geometry.computeVertexNormals();
    geometry.computeBoundingBox();

    const mesh = new THREE.Mesh(
      geometry,
      new THREE.MeshStandardMaterial({
        color: 0xdce8e3,
        roughness: 0.74,
        metalness: 0.02,
        side: THREE.DoubleSide,
      }),
    );
    mesh.name = "NitoCanonicalLabelMesh";
    const group = new THREE.Group();
    group.name = "NitoCanonicalLabelMeshRoot";
    group.add(mesh);
    return group;
  }

  setModel(model, options = {}) {
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
    const modelScale = 3.2 / maxDimension;
    const normalizedRoot = new THREE.Group();
    normalizedRoot.name = "NitoNormalizedModel";
    normalizedRoot.scale.setScalar(modelScale);
    model.position.sub(sourceCenter);
    normalizedRoot.add(model);

    this.model = normalizedRoot;
    this.modelMaterials = [];
    this.meshCount = 0;
    this.modelCoordinateTransform = {
      center: sourceCenter.clone(),
      scale: modelScale,
    };
    this.labelCoordinatesMatchModel = Boolean(options.coordinatesMatchLabel);
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
    this.modelStatus = `${this.labelCoordinatesMatchModel ? "Canonical label mesh ready" : "Orbit, pan, and zoom ready"} (${this.meshCount} mesh${this.meshCount === 1 ? "" : "es"})`;
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
        head: this.blenderPointToThree(value?.head),
        tail: this.blenderPointToThree(value?.tail),
      }))
      .filter((bone) => bone.head && bone.tail && bone.head.distanceToSquared(bone.tail) > 0.000001);

    if (!bones.length) {
      this.setStatus(`${this.modelStatus || "Model ready"}; label file has no drawable bones`);
      return;
    }

    const targetBox = this.frame.box;
    const targetSize = targetBox.getSize(new THREE.Vector3());
    const targetRadius = Math.max(targetSize.length(), 1);
    const boneRadius = THREE.MathUtils.clamp(targetRadius * 0.006, 0.012, 0.04);
    const jointRadius = boneRadius * 2.15;
    const jointPoints = [];
    const transformPoint = this.labelCoordinatesMatchModel && this.modelCoordinateTransform
      ? (point) => point
          .clone()
          .sub(this.modelCoordinateTransform.center)
          .multiplyScalar(this.modelCoordinateTransform.scale)
      : this.approximateLabelTransform(bones);
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

  approximateLabelTransform(bones) {
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
    return (point) => point.clone().sub(labelCenter).multiplyScalar(labelScale).add(targetCenter);
  }

  blenderPointToThree(value) {
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

  canonicalToScene(point) {
    const { center, scale } = this.modelCoordinateTransform;
    return new THREE.Vector3(point.x, point.z, point.y).sub(center).multiplyScalar(scale);
  }

  sceneToCanonical(vector) {
    const { center, scale } = this.modelCoordinateTransform;
    const model = vector.clone().divideScalar(scale).add(center);
    return new THREE.Vector3(model.x, model.z, model.y);
  }

  async toggleSkeletonEditor(button) {
    if (this.editor) {
      this.disableSkeletonEditor();
      button?.classList.remove("is-active");
      return;
    }
    const enabled = await this.enableSkeletonEditor();
    button?.classList.toggle("is-active", enabled);
  }

  async enableSkeletonEditor() {
    if (!this.guideApiUrl) return false;
    if (!this.frame || !this.modelCoordinateTransform || !this.labelCoordinatesMatchModel) {
      this.setStatus("Skeleton editing needs the canonical mesh; wait for it to load or run guide extraction.");
      return false;
    }
    this.setStatus("Loading editable skeleton");
    let payload;
    try {
      const response = await fetch(this.guideApiUrl, { cache: "no-store" });
      payload = await response.json();
      if (!response.ok) throw new Error(payload?.error || `Guide returned HTTP ${response.status}`);
    } catch (error) {
      this.setStatus(`Skeleton editor failed to load: ${error.message}`);
      return false;
    }

    const joints = this.jointsFromGuideBones(payload.guide_bones);
    if (!joints) {
      this.setStatus("Guide JSON is missing required bones; cannot edit.");
      return false;
    }

    this.controls.autoRotate = false;
    if (this.labelGroup) this.labelGroup.visible = false;

    this.editor = {
      joints,
      initialJoints: this.cloneJoints(joints),
      undoStack: [],
      mirror: true,
      dirty: false,
      source: payload.source || "",
      dragJoint: "",
      dragPlane: new THREE.Plane(),
      hoverJoint: "",
      group: null,
      jointMeshes: new Map(),
      boneMeshes: new Map(),
      raycaster: new THREE.Raycaster(),
      pointer: new THREE.Vector2(),
    };
    this.buildEditorGroup();
    this.buildEditorPanel();
    this.updateEditorStatus(
      payload.source === "web_edits" ? "Loaded saved browser edits." : `Loaded ${payload.source || "candidate"} guide.`,
    );
    this.setStatus("Skeleton editing: drag joints, use the view buttons, then save.");
    return true;
  }

  disableSkeletonEditor() {
    if (!this.editor) return;
    if (this.editor.group) {
      this.scene.remove(this.editor.group);
      this.disposeObject(this.editor.group);
    }
    this.root.querySelector("[data-editor-panel]")?.remove();
    this.renderer.domElement.style.cursor = "";
    this.editor = null;
    this.controls.enabled = true;
    if (this.labelGroup) this.labelGroup.visible = this.labelsVisible;
    this.setStatus(this.modelStatus || "Model ready");
  }

  jointsFromGuideBones(guideBones) {
    if (!guideBones || typeof guideBones !== "object") return null;
    const joints = new Map();
    for (const [jointName, boneName, endpoint] of GUIDE_JOINT_SPECS) {
      const values = guideBones?.[boneName]?.[endpoint];
      if (!Array.isArray(values) || values.length < 3 || !values.every((value) => Number.isFinite(Number(value)))) {
        return null;
      }
      joints.set(jointName, new THREE.Vector3(Number(values[0]), Number(values[1]), Number(values[2])));
    }
    return joints;
  }

  serializeGuideBones() {
    const bones = {};
    for (const [boneName, [headJoint, tailJoint]] of Object.entries(GUIDE_EDITOR_BONES)) {
      const head = this.editor.joints.get(headJoint);
      const tail = this.editor.joints.get(tailJoint);
      bones[boneName] = {
        head: [head.x, head.y, head.z].map((value) => Number(value.toFixed(6))),
        tail: [tail.x, tail.y, tail.z].map((value) => Number(value.toFixed(6))),
      };
    }
    return bones;
  }

  cloneJoints(joints) {
    const copy = new Map();
    joints.forEach((value, key) => copy.set(key, value.clone()));
    return copy;
  }

  buildEditorGroup() {
    const editor = this.editor;
    if (editor.group) {
      this.scene.remove(editor.group);
      this.disposeObject(editor.group);
    }
    const group = new THREE.Group();
    group.name = "NitoSkeletonEditor";
    const targetRadius = Math.max(this.frame.box.getSize(new THREE.Vector3()).length(), 1);
    const boneRadius = THREE.MathUtils.clamp(targetRadius * 0.005, 0.01, 0.035);
    const jointRadius = boneRadius * 2.6;
    editor.jointRadius = jointRadius;

    editor.boneMeshes.clear();
    const unitCylinder = new THREE.CylinderGeometry(boneRadius, boneRadius, 1, 12, 1, false);
    for (const boneName of Object.keys(GUIDE_EDITOR_BONES)) {
      const material = new THREE.MeshBasicMaterial({
        color: this.labelBoneColor(boneName),
        depthTest: false,
        transparent: true,
        opacity: 0.85,
      });
      const mesh = new THREE.Mesh(unitCylinder, material);
      mesh.renderOrder = 11;
      group.add(mesh);
      editor.boneMeshes.set(boneName, mesh);
    }

    editor.jointMeshes.clear();
    const sphereGeometry = new THREE.SphereGeometry(jointRadius, 18, 12);
    editor.joints.forEach((_, jointName) => {
      const material = new THREE.MeshBasicMaterial({
        color: this.editorJointColor(jointName),
        depthTest: false,
        transparent: true,
        opacity: 0.95,
      });
      const mesh = new THREE.Mesh(sphereGeometry, material);
      mesh.renderOrder = 13;
      mesh.userData.jointName = jointName;
      group.add(mesh);
      editor.jointMeshes.set(jointName, mesh);
    });

    editor.group = group;
    this.scene.add(group);
    this.refreshEditorScene();
  }

  editorJointColor(jointName) {
    if (jointName.includes("_left_") || jointName.startsWith("front_left") || jointName.startsWith("rear_left")) {
      return 0x4fd9c8;
    }
    if (jointName.includes("_right_") || jointName.startsWith("front_right") || jointName.startsWith("rear_right")) {
      return 0xf2a64d;
    }
    return 0xf5e9cf;
  }

  refreshEditorScene() {
    const editor = this.editor;
    if (!editor?.group) return;
    editor.joints.forEach((canonical, jointName) => {
      editor.jointMeshes.get(jointName).position.copy(this.canonicalToScene(canonical));
    });
    const up = new THREE.Vector3(0, 1, 0);
    for (const [boneName, [headJoint, tailJoint]] of Object.entries(GUIDE_EDITOR_BONES)) {
      const mesh = editor.boneMeshes.get(boneName);
      const start = editor.jointMeshes.get(headJoint).position;
      const end = editor.jointMeshes.get(tailJoint).position;
      const direction = end.clone().sub(start);
      const length = Math.max(direction.length(), 0.0001);
      mesh.position.copy(start).add(end).multiplyScalar(0.5);
      mesh.scale.set(1, length, 1);
      mesh.quaternion.setFromUnitVectors(up, direction.normalize());
    }
  }

  buildEditorPanel() {
    this.root.querySelector("[data-editor-panel]")?.remove();
    const panel = document.createElement("div");
    panel.className = "skeleton-editor";
    panel.dataset.editorPanel = "true";
    panel.innerHTML = `
      <div class="skeleton-editor-row">
        <strong>Skeleton editor</strong>
        <span class="editor-joint-label" data-editor-joint>Hover a joint</span>
      </div>
      <div class="skeleton-editor-row skeleton-editor-actions">
        <span class="editor-view-buttons">
          <button type="button" data-editor-action="view-left" title="Left profile">Left</button>
          <button type="button" data-editor-action="view-right" title="Right profile">Right</button>
          <button type="button" data-editor-action="view-front" title="Front view">Front</button>
          <button type="button" data-editor-action="view-rear" title="Rear view">Rear</button>
          <button type="button" data-editor-action="view-top" title="Top view">Top</button>
        </span>
        <button type="button" class="is-active" data-editor-action="mirror" title="Mirror left/right leg edits">Mirror</button>
        <button type="button" data-editor-action="undo" title="Undo (Ctrl+Z)">Undo</button>
        <button type="button" data-editor-action="revert" title="Revert to the loaded guide">Revert</button>
        <button type="button" class="editor-save" data-editor-action="save" title="Save skeleton edits">Save Skeleton</button>
      </div>
      <p class="editor-status" data-editor-status></p>
    `;
    this.root.appendChild(panel);
  }

  handleEditorAction(action, button) {
    if (action.startsWith("view-")) {
      this.applyEditorViewPreset(action.slice(5));
      return;
    }
    if (action === "mirror") {
      this.editor.mirror = !this.editor.mirror;
      button.classList.toggle("is-active", this.editor.mirror);
      this.updateEditorStatus(this.editor.mirror ? "Mirroring left/right leg edits." : "Mirroring off.");
      return;
    }
    if (action === "undo") {
      this.editorUndo();
      return;
    }
    if (action === "revert") {
      this.pushEditorUndo();
      this.editor.joints = this.cloneJoints(this.editor.initialJoints);
      this.editor.dirty = false;
      this.refreshEditorScene();
      this.updateEditorStatus("Reverted to the loaded guide.");
      return;
    }
    if (action === "save") {
      this.saveEditorGuide(button);
    }
  }

  applyEditorViewPreset(name) {
    if (!this.frame) return;
    const { center, radius } = this.frame;
    const distance = (radius / Math.sin(THREE.MathUtils.degToRad(this.camera.fov * 0.5))) * 1.05;
    // Canonical: +X is the animal's left, +Y is forward (three.js +Z), +Z is up (three.js +Y).
    const directions = {
      left: new THREE.Vector3(1, 0.02, 0),
      right: new THREE.Vector3(-1, 0.02, 0),
      front: new THREE.Vector3(0, 0.02, 1),
      rear: new THREE.Vector3(0, 0.02, -1),
      top: new THREE.Vector3(0, 1, 0.02),
    };
    const direction = directions[name];
    if (!direction) return;
    this.camera.position.copy(center).add(direction.clone().normalize().multiplyScalar(distance));
    this.controls.target.copy(center);
    this.controls.update();
    this.rememberCamera();
  }

  pickEditorJoint(event) {
    const editor = this.editor;
    const bounds = this.renderer.domElement.getBoundingClientRect();
    editor.pointer.set(
      ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
      -((event.clientY - bounds.top) / bounds.height) * 2 + 1,
    );
    editor.raycaster.setFromCamera(editor.pointer, this.camera);
    const hits = editor.raycaster.intersectObjects([...editor.jointMeshes.values()], false);
    return hits.length ? hits[0].object.userData.jointName : "";
  }

  onEditorPointerDown(event) {
    if (!this.editor || event.button !== 0) return;
    const jointName = this.pickEditorJoint(event);
    if (!jointName) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    this.renderer.domElement.setPointerCapture?.(event.pointerId);
    this.pushEditorUndo();
    this.editor.dragJoint = jointName;
    this.controls.enabled = false;
    const jointScene = this.editor.jointMeshes.get(jointName).position;
    const normal = this.camera.getWorldDirection(new THREE.Vector3());
    this.editor.dragPlane.setFromNormalAndCoplanarPoint(normal, jointScene);
    this.showEditorJoint(jointName);
  }

  onEditorPointerMove(event) {
    const editor = this.editor;
    if (!editor) return;
    if (!editor.dragJoint) {
      const hover = this.pickEditorJoint(event);
      if (hover !== editor.hoverJoint) {
        editor.hoverJoint = hover;
        this.renderer.domElement.style.cursor = hover ? "grab" : "";
        if (hover) this.showEditorJoint(hover);
      }
      return;
    }
    event.preventDefault();
    event.stopImmediatePropagation();
    const bounds = this.renderer.domElement.getBoundingClientRect();
    editor.pointer.set(
      ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
      -((event.clientY - bounds.top) / bounds.height) * 2 + 1,
    );
    editor.raycaster.setFromCamera(editor.pointer, this.camera);
    const hit = new THREE.Vector3();
    if (!editor.raycaster.ray.intersectPlane(editor.dragPlane, hit)) return;
    const canonical = this.sceneToCanonical(hit);
    editor.joints.get(editor.dragJoint).copy(canonical);
    if (editor.mirror) {
      const counterpart = mirrorJointName(editor.dragJoint);
      if (counterpart && editor.joints.has(counterpart)) {
        editor.joints.get(counterpart).set(-canonical.x, canonical.y, canonical.z);
      }
    }
    editor.dirty = true;
    this.refreshEditorScene();
  }

  onEditorPointerUp(event) {
    if (!this.editor) return;
    if (this.editor.dragJoint) {
      this.renderer.domElement.releasePointerCapture?.(event.pointerId);
      this.editor.dragJoint = "";
      this.controls.enabled = true;
      this.updateEditorStatus("Unsaved skeleton edits. Save before exporting.");
    }
  }

  pushEditorUndo() {
    const editor = this.editor;
    editor.undoStack.push(this.cloneJoints(editor.joints));
    if (editor.undoStack.length > 60) editor.undoStack.shift();
  }

  editorUndo() {
    const editor = this.editor;
    if (!editor?.undoStack.length) {
      this.updateEditorStatus("Nothing to undo.");
      return;
    }
    editor.joints = editor.undoStack.pop();
    editor.dirty = true;
    this.refreshEditorScene();
    this.updateEditorStatus("Undid the last edit.");
  }

  async saveEditorGuide(button) {
    const editor = this.editor;
    button.disabled = true;
    this.updateEditorStatus("Saving skeleton edits");
    try {
      const response = await fetch(this.guideApiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ guide_bones: this.serializeGuideBones() }),
      });
      const payload = await response.json();
      if (!response.ok || payload?.error) throw new Error(payload?.error || `Save returned HTTP ${response.status}`);
      editor.dirty = false;
      editor.initialJoints = this.cloneJoints(editor.joints);
      this.updateEditorStatus("Skeleton saved. Export Verified Label is now Blender-free.");
      window.dispatchEvent(new CustomEvent("nito-guide-saved", { detail: { sampleId: this.sampleId } }));
    } catch (error) {
      this.updateEditorStatus(`Save failed: ${error.message}`);
    } finally {
      button.disabled = false;
    }
  }

  showEditorJoint(jointName) {
    const label = this.root.querySelector("[data-editor-joint]");
    if (!label) return;
    const hint = guideJointHint(jointName);
    label.textContent = hint ? `${guideJointLabel(jointName)} - ${hint}` : guideJointLabel(jointName);
  }

  updateEditorStatus(message) {
    const status = this.root.querySelector("[data-editor-status]");
    if (status) status.textContent = message;
  }

  hasUnsavedEdits() {
    // Any open editor counts: re-rendering the page would tear down the session.
    return Boolean(this.editor);
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
    window.removeEventListener("keydown", this.editorKeyHandler);
    this.disableSkeletonEditor();
    activeViewers.delete(this);
    this.rememberCamera();
    this.resizeObserver?.disconnect();
    this.controls?.dispose();
    this.clearLabelOverlay();
    if (this.model) this.disposeObject(this.model);
    this.renderer?.dispose();
    this.renderer?.domElement?.remove();
  }
}

const activeViewers = new Set();

function mountAll(container = document) {
  container.querySelectorAll(".three-editor").forEach((root) => {
    if (mountedViewers.has(root)) return;
    const viewer = new NitoThreeViewport(root);
    mountedViewers.set(root, viewer);
    activeViewers.add(viewer);
  });
}

function hasActiveEdits() {
  for (const viewer of activeViewers) {
    if (document.body.contains(viewer.root) && viewer.hasUnsavedEdits()) return true;
  }
  return false;
}

window.NitoThreeViewer = { mountAll, hasActiveEdits };
window.dispatchEvent(new CustomEvent("nito-three-ready"));
