const state = {
  catalog: { animals: [], specs: [] },
  settings: { blender_path: "", blender_exists: false },
  samples: [],
  batches: [],
  jobs: [],
  selectedBatchId: "",
  selectedSampleId: "",
  selectedJobId: "",
  initialRouteApplied: false,
};

const legacyBodyPlanAliases = {
  canid: "medium_quadruped",
  feline: "medium_quadruped",
  amphibian: "hind_leg_dominant",
  ungulate: "long_legged_ungulate",
  lagomorph: "hind_leg_dominant",
  reptile_shell: "shell_reptile",
};

const skeletonTypeOptions = [
  {
    bodyPlan: "medium_quadruped",
    schemaId: "mammal_quadruped_v1",
    icon: "mammal",
    title: "Mammal quadruped",
    examples: ["dog", "cat", "river otter"],
    detail: "Balanced spine and four walking limbs for most soft-bodied mammals.",
  },
  {
    bodyPlan: "long_legged_ungulate",
    schemaId: "ungulate_quadruped_v1",
    icon: "ungulate",
    title: "Hoofed runner",
    examples: ["horse", "deer", "ram"],
    detail: "Longer neck, taller limb columns, and hoof-oriented lower chains.",
  },
  {
    bodyPlan: "low_reptile",
    schemaId: "sprawling_quadruped_v1",
    icon: "sprawling",
    title: "Sprawling body",
    examples: ["lizard", "crocodile", "turtle"],
    detail: "Low torso with limbs that angle outward before contacting the ground.",
  },
  {
    bodyPlan: "hind_leg_dominant",
    schemaId: "hopper_quadruped_v1",
    icon: "hopper",
    title: "Hopper / croucher",
    examples: ["frog", "rabbit", "kangaroo-like creature"],
    detail: "Compact front limbs with oversized rear limbs for crouched poses.",
  },
];

const guidePlacementHelp = {
  core: [
    {
      title: "Pelvis",
      role: "Rear torso and hip block. This anchors the rear legs and defines where the spine leaves the rump.",
      head: "Put the head near the rear center of body mass, just forward of the tail base and inside the body volume.",
      tail: "Aim forward into the lumbar back where the rump transitions into the main spine.",
      check: "Avoid tail hair, armor, saddles, and the outer silhouette. This is an internal hip landmark.",
    },
    {
      title: "Spine",
      role: "Middle torso segment. This bridges pelvis to rib cage and controls the main back line.",
      head: "Start from the pelvis tail at the rear or mid back.",
      tail: "End around the middle/front of the rib cage, still on the centerline and inside the body mass.",
      check: "Ignore surface props and fur clumps. Keep the line smooth through the animal core.",
    },
    {
      title: "Chest",
      role: "Front torso and shoulder block. This anchors the front legs and the base of the neck.",
      head: "Start near the front end of the spine.",
      tail: "Place at the withers or upper chest/base-neck area, above and slightly behind the front-leg entry.",
      check: "Think shoulder blade area for dogs/cats and withers for horses. Do not use tack or armor as the landmark.",
    },
    {
      title: "Neck",
      role: "Neck chain from chest to skull. This controls head carriage.",
      head: "Start where the neck rises out of the shoulders.",
      tail: "End near the poll or base of skull, behind the ears and before the muzzle begins.",
      check: "Follow the center of neck volume, not mane, fur outline, reins, or armor.",
    },
    {
      title: "Head",
      role: "Head direction and skull length. This gives the rig a head bone that rotates naturally.",
      head: "Start at the base of skull where the neck ends.",
      tail: "Aim through the center/front of the skull or muzzle direction.",
      check: "Use skull mass, not ears, horns, bridles, nose ornaments, or tiny muzzle details.",
    },
    {
      title: "Tail",
      role: "Bony tail direction. This describes the tail root and main tail line.",
      head: "Start where the tail exits the pelvis/rump.",
      tail: "Aim along the bony tail core. For fluffy tails, ignore the outer fur edge.",
      check: "If there is no clear tail, keep the guide short near the rump instead of inventing length.",
    },
  ],
  limbs: [
    {
      title: "Front upper limb",
      role: "Shoulder to elbow, even when the shoulder is partly hidden inside the torso.",
      head: "Place inside the chest where the front leg enters the body.",
      tail: "Place at the elbow, usually the first major bend below and behind the chest.",
      check: "Do not start on surface shoulder fur, armor straps, or the outside contour.",
    },
    {
      title: "Front lower limb",
      role: "Elbow to wrist/carpus, the long lower front-leg segment.",
      head: "Start at the elbow.",
      tail: "End at the wrist/carpus bend just above the paw or hoof.",
      check: "Do not put the tail at the ground contact. The foot guide handles contact.",
    },
    {
      title: "Front foot / paw / hoof",
      role: "Ground-contact direction from wrist/carpus to toe, pad, or hoof.",
      head: "Start where the lower front limb ends.",
      tail: "End at the front/center of the toe, paw pad, or hoof contact point.",
      check: "Use the point the animation should treat as the planted contact.",
    },
    {
      title: "Rear upper limb",
      role: "Hip to stifle/knee through the thigh.",
      head: "Place at the hip socket area inside the rump, forward/down from the tail base.",
      tail: "Place at the stifle/knee, the forward-facing bend under the flank.",
      check: "This is often hidden by body mass. Do not mistake the hock for the knee.",
    },
    {
      title: "Rear lower limb",
      role: "Stifle/knee to hock/ankle.",
      head: "Start at the rear knee/stifle.",
      tail: "End at the hock, the backward-pointing ankle bend above the rear foot.",
      check: "This usually angles backward/down before the foot reaches the ground.",
    },
    {
      title: "Rear foot / paw / hoof",
      role: "Ground-contact direction from hock/ankle to toe, pad, or hoof.",
      head: "Start at the hock/ankle.",
      tail: "End at the front/center of the rear toe, paw pad, or hoof contact point.",
      check: "Use the animation contact point, not the back of the heel/hock.",
    },
  ],
};

const elements = {
  statusLine: document.querySelector("#statusLine"),
  refreshButton: document.querySelector("#refreshButton"),
  homeActiveJobs: document.querySelector("#homeActiveJobs"),
  homeUnfinishedSamples: document.querySelector("#homeUnfinishedSamples"),
  sampleForm: document.querySelector("#sampleForm"),
  createSampleButton: document.querySelector("#createSampleButton"),
  runForm: document.querySelector("#runForm"),
  runButton: document.querySelector("#runButton"),
  promptInput: document.querySelector("#promptInput"),
  promptNextButton: document.querySelector("#promptNextButton"),
  schemaBackButton: document.querySelector("#schemaBackButton"),
  promptStep: document.querySelector("#promptStep"),
  skeletonStep: document.querySelector("#skeletonStep"),
  skeletonTypeGrid: document.querySelector("#skeletonTypeGrid"),
  sampleMorphologySelect: document.querySelector("#sampleMorphologySelect"),
  bodyPlanSkeletonPreview: document.querySelector("#bodyPlanSkeletonPreview"),
  batchCount: document.querySelector("#batchCount"),
  sampleCount: document.querySelector("#sampleCount"),
  jobCount: document.querySelector("#jobCount"),
  batchList: document.querySelector("#batchList"),
  batchDetail: document.querySelector("#batchDetail"),
  sampleList: document.querySelector("#sampleList"),
  sampleDetail: document.querySelector("#sampleDetail"),
  jobList: document.querySelector("#jobList"),
  jobLog: document.querySelector("#jobLog"),
  settingsForm: document.querySelector("#settingsForm"),
  blenderPathInput: document.querySelector("#blenderPathInput"),
  settingsBlenderStatus: document.querySelector("#settingsBlenderStatus"),
  saveSettingsButton: document.querySelector("#saveSettingsButton"),
};

function formatTime(value) {
  if (!value) return "pending";
  return new Date(value * 1000).toLocaleString();
}

function formatDuration(value) {
  const seconds = Math.max(0, Number(value || 0));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes < 60) return `${minutes}m ${remainingSeconds}s`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
}

function elapsedForJob(job) {
  if (!job) return 0;
  if (job.elapsed_seconds !== undefined && job.elapsed_seconds !== null) {
    return Number(job.elapsed_seconds || 0);
  }
  if (!job.started_at) return 0;
  const end = job.finished_at || Math.floor(Date.now() / 1000);
  return Math.max(0, end - job.started_at);
}

function statusClass(value) {
  return `status-${String(value || "unknown").replace(/[^a-zA-Z0-9_-]/g, "_")}`;
}

function tag(value) {
  return `<span class="tag ${statusClass(value)}">${escapeHtml(value || "unknown")}</span>`;
}

function pagePath(viewName, id = "") {
  if ((viewName === "sampleDetail" || viewName === "samples") && id) {
    return `/samples/${encodeURIComponent(id)}`;
  }
  if ((viewName === "batchDetail" || viewName === "batches") && id) {
    return `/batches/${encodeURIComponent(id)}`;
  }
  const paths = {
    home: "/",
    batches: "/batches",
    batchDetail: "/batches",
    samples: "/samples",
    sampleDetail: "/samples",
    create: "/create",
    jobs: "/jobs",
    settings: "/settings",
  };
  return paths[viewName] || "/";
}

function emptyState(title, detail, actionLabel = "", viewName = "") {
  return `
    <div class="empty-state">
      <span class="empty-mark" aria-hidden="true">N</span>
      <div>
        <strong>${escapeHtml(title)}</strong>
        <p>${escapeHtml(detail)}</p>
        ${
          actionLabel && viewName
            ? `<a class="button-link" href="${escapeHtml(pagePath(viewName))}">${escapeHtml(actionLabel)}</a>`
            : ""
        }
      </div>
    </div>
  `;
}

function labelText(value) {
  return String(value || "unknown").replaceAll("_", " ");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function skeletonLabelSchema() {
  return state.catalog.label_schema || {};
}

function skeletonSchemas() {
  return skeletonLabelSchema().skeleton_schemas || {};
}

function normalizeBodyPlan(bodyPlan) {
  const value = String(bodyPlan || "").trim();
  return legacyBodyPlanAliases[value] || value;
}

function skeletonSchemaIdForBodyPlan(bodyPlan) {
  const mapping = skeletonLabelSchema().body_plan_skeleton_schema || {};
  return mapping[normalizeBodyPlan(bodyPlan)] || "";
}

function skeletonSchemaForId(schemaId) {
  return skeletonSchemas()[schemaId] || null;
}

function skeletonSchemaForSample(sample) {
  const schemaId = sample?.skeleton_schema_id || skeletonSchemaIdForBodyPlan(sample?.body_plan || sample?.morphology_type || "");
  return schemaId ? skeletonSchemaForId(schemaId) : null;
}

function skeletonBoneCount(schema) {
  const names = new Set();
  for (const chain of schema?.chains || []) {
    for (const bone of chain.bones || []) {
      names.add(bone);
    }
  }
  return names.size;
}

function skeletonSchemaCard(schema, options = {}) {
  if (!schema) {
    return `
      <div class="skeleton-schema-card skeleton-schema-empty">
        <strong>No skeleton schema mapped</strong>
        <p>Select a body plan to see the expected bone graph.</p>
      </div>
    `;
  }
  const chains = Array.isArray(schema.chains) ? schema.chains : [];
  const visibleChains = options.compact ? chains.slice(0, 4) : chains;
  const hiddenCount = Math.max(0, chains.length - visibleChains.length);
  const notes = Array.isArray(schema.placement_notes) ? schema.placement_notes : [];
  return `
    <div class="skeleton-schema-card ${options.compact ? "is-compact" : ""}">
      <div class="skeleton-schema-header">
        <div>
          <strong>${escapeHtml(schema.label || "Skeleton schema")}</strong>
          <p>${escapeHtml(schema.summary || "Shared bone graph for this body plan.")}</p>
        </div>
        ${tag(`${skeletonBoneCount(schema)} bones`)}
      </div>
      <div class="skeleton-chain-list">
        ${visibleChains
          .map(
            (chain) => `
              <div class="skeleton-chain">
                <span>${escapeHtml(chain.name || "Chain")}</span>
                <code>${escapeHtml((chain.bones || []).join(" -> "))}</code>
              </div>
            `,
          )
          .join("")}
      </div>
      ${hiddenCount ? `<p class="field-help">+ ${hiddenCount} more chains in this schema.</p>` : ""}
      ${
        !options.compact && notes.length
          ? `<ul class="skeleton-notes">${notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("")}</ul>`
          : ""
      }
      ${options.compact ? skeletonPlacementSummary() : skeletonPlacementGuide()}
    </div>
  `;
}

function skeletonPlacementSummary() {
  return `
    <div class="placement-summary">
      ${skeletonPlacementDiagram(true)}
      <div>
        <strong>Body landmarks</strong>
        <p>Place pelvis, spine, chest, neck, head, and tail inside the body volume, not on fur, tack, or armor.</p>
      </div>
      <div>
        <strong>Limb landmarks</strong>
        <p>Use joint centers for upper/lower limb bones and real toe, paw, or hoof contact points for feet.</p>
      </div>
    </div>
  `;
}

function skeletonPlacementDiagram(isCompact = false) {
  return `
    <figure class="placement-diagram ${isCompact ? "is-compact" : ""}">
      <div class="placement-diagram-stage">
        <img src="/static/quadruped_ref_image_1.webp" alt="" aria-hidden="true" />
        <svg viewBox="0 0 1536 1024" role="img" aria-label="Nito guide bone placement overlay on a side-view quadruped">
          <path class="bone torso" d="M455 495 L620 382 L895 395 L1032 315 L1185 250" />
          <path class="bone tail" d="M455 495 L206 548" />
          <path class="bone front" d="M980 510 L952 655 L970 780 L1084 800" />
          <path class="bone rear" d="M485 510 L410 660 L425 785 L512 804" />
          <path class="bone ghost" d="M928 515 L905 650 L916 782 L1015 800" />
          <path class="bone ghost" d="M548 512 L535 646 L582 770 L668 790" />
          <g class="joint-set">
            <circle cx="455" cy="495" r="16" /><circle cx="620" cy="382" r="16" />
            <circle cx="895" cy="395" r="16" /><circle cx="1032" cy="315" r="16" />
            <circle cx="1185" cy="250" r="16" /><circle cx="206" cy="548" r="16" />
            <circle cx="980" cy="510" r="16" /><circle cx="952" cy="655" r="16" />
            <circle cx="970" cy="780" r="16" /><circle cx="1084" cy="800" r="16" />
            <circle cx="485" cy="510" r="16" /><circle cx="410" cy="660" r="16" />
            <circle cx="425" cy="785" r="16" /><circle cx="512" cy="804" r="16" />
          </g>
          <g class="marker-set">
            <circle cx="455" cy="495" r="23" /><text x="455" y="504">1</text>
            <circle cx="895" cy="395" r="23" /><text x="895" y="404">2</text>
            <circle cx="1185" cy="250" r="23" /><text x="1185" y="259">3</text>
            <circle cx="980" cy="510" r="23" /><text x="980" y="519">4</text>
            <circle cx="485" cy="510" r="23" /><text x="485" y="519">5</text>
            <circle cx="1084" cy="800" r="23" /><text x="1084" y="809">6</text>
          </g>
        </svg>
      </div>
      <figcaption>Place guide bones through internal landmarks. Treat fur and surface details as decoration.</figcaption>
      <div class="placement-diagram-legend" aria-label="Anatomical placement legend">
        <span><b>1</b> Pelvis / hip anchor</span>
        <span><b>2</b> Chest / shoulder block</span>
        <span><b>3</b> Head direction</span>
        <span><b>4</b> Front limb joints</span>
        <span><b>5</b> Rear limb joints</span>
        <span><b>6</b> Foot contact</span>
      </div>
    </figure>
  `;
}

function placementHelpCard(item) {
  return `
    <article class="placement-card">
      <h5>${escapeHtml(item.title)}</h5>
      <p>${escapeHtml(item.role)}</p>
      <dl>
        <dt>Head</dt>
        <dd>${escapeHtml(item.head)}</dd>
        <dt>Tail</dt>
        <dd>${escapeHtml(item.tail)}</dd>
        <dt>Check</dt>
        <dd>${escapeHtml(item.check)}</dd>
      </dl>
    </article>
  `;
}

function skeletonPlacementGuide() {
  return `
    <section class="placement-guide">
      <div class="placement-guide-heading">
        <h5>Guide Placement Help</h5>
        <p>Use these notes while correcting the Nito guide in Blender. The white/orange bone head is the start of the guide bone; the tail is the end point.</p>
      </div>
      ${skeletonPlacementDiagram()}
      <div class="placement-help-section">
        <h6>Body guide bones</h6>
        <div class="placement-grid">
          ${guidePlacementHelp.core.map(placementHelpCard).join("")}
        </div>
      </div>
      <div class="placement-help-section">
        <h6>Limb guide bones</h6>
        <div class="placement-grid">
          ${guidePlacementHelp.limbs.map(placementHelpCard).join("")}
        </div>
      </div>
    </section>
  `;
}

function skeletonTypeIcon(kind) {
  const icons = {
    mammal: `
      <svg viewBox="0 0 64 64" aria-hidden="true">
        <path d="M12 42c4-12 14-19 28-19 8 0 14 3 18 8" />
        <path d="M42 23l7-8 4 11" />
        <path d="M26 43v10M45 39v14M17 45v8M55 36v9" />
        <path d="M9 43c6 2 11 2 17 0" />
      </svg>
    `,
    ungulate: `
      <svg viewBox="0 0 64 64" aria-hidden="true">
        <path d="M14 37c6-13 19-18 35-14 4 1 7 4 9 8" />
        <path d="M46 23l7-9 2 12" />
        <path d="M22 39v16M38 36v19M50 35v20M17 41l-2 14" />
        <path d="M20 55h-7M41 55h-7M53 55h-7" />
      </svg>
    `,
    sprawling: `
      <svg viewBox="0 0 64 64" aria-hidden="true">
        <path d="M10 38c9-10 25-13 41-8 4 1 7 3 9 6" />
        <path d="M51 29l8-5-2 9" />
        <path d="M21 39l-9 9M31 36l-5 12M43 35l7 11M52 37l9 6" />
        <path d="M7 48h9M23 48h7M48 46h8M58 43h5" />
      </svg>
    `,
    hopper: `
      <svg viewBox="0 0 64 64" aria-hidden="true">
        <path d="M17 38c4-10 12-15 24-15 8 0 13 4 15 10" />
        <path d="M43 24l6-7 4 10" />
        <path d="M27 42l-12 12h15M42 39l10 15H37" />
        <path d="M20 41l-8 3M53 35l7 4" />
      </svg>
    `,
  };
  return icons[kind] || icons.mammal;
}

function renderSkeletonTypeChoices() {
  const selected = elements.sampleMorphologySelect.value;
  elements.skeletonTypeGrid.innerHTML = skeletonTypeOptions
    .map((option) => {
      const schema = skeletonSchemaForId(option.schemaId);
      return `
        <button
          class="skeleton-type-card ${selected === option.bodyPlan ? "is-selected" : ""}"
          type="button"
          data-body-plan="${escapeHtml(option.bodyPlan)}"
        >
          <span class="skeleton-type-icon">${skeletonTypeIcon(option.icon)}</span>
          <span class="skeleton-type-copy">
            <strong>${escapeHtml(schema?.label || option.title)}</strong>
            <span>${escapeHtml(option.detail)}</span>
            <small>Examples: ${escapeHtml(option.examples.join(", "))}</small>
          </span>
        </button>
      `;
    })
    .join("");
  elements.createSampleButton.disabled = !selected;
}

function renderSkeletonSchemaPreview() {
  const bodyPlan = elements.sampleMorphologySelect.value;
  const schema = skeletonSchemaForId(skeletonSchemaIdForBodyPlan(bodyPlan));
  elements.bodyPlanSkeletonPreview.innerHTML = skeletonSchemaCard(schema, { compact: true });
}

function setCreateWizardStep(step) {
  const isPrompt = step === "prompt";
  elements.promptStep.classList.toggle("is-active", isPrompt);
  elements.skeletonStep.classList.toggle("is-active", !isPrompt);
  document.querySelectorAll("[data-step-pill]").forEach((pill) => {
    pill.classList.toggle("is-active", pill.dataset.stepPill === step);
  });
}

function chooseSkeletonType(bodyPlan) {
  if (!skeletonTypeOptions.some((option) => option.bodyPlan === bodyPlan)) return;
  elements.sampleMorphologySelect.value = bodyPlan;
  renderSkeletonTypeChoices();
  renderSkeletonSchemaPreview();
}

function continueFromPrompt() {
  const prompt = elements.promptInput.value.trim();
  if (!prompt) {
    elements.promptInput.setCustomValidity("Describe the character before choosing a skeleton.");
    elements.promptInput.reportValidity();
    return;
  }
  elements.promptInput.setCustomValidity("");
  setCreateWizardStep("skeleton");
}

function sampleById(sampleId) {
  return state.samples.find((sample) => sample.sample_id === sampleId);
}

function routeFromLocation() {
  const params = new URLSearchParams(window.location.search);
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  const parts = path.split("/").filter(Boolean);
  if (path === "/" && params.get("view")) {
    const requestedView = params.get("view");
    const allowedViews = new Set(["home", "batches", "samples", "create", "jobs", "settings"]);
    return {
      view: allowedViews.has(requestedView) ? requestedView : "home",
      bodyPlan: params.get("bodyPlan") || "",
      step: params.get("step") || "",
    };
  }
  if (parts[0] === "samples" && parts[1]) {
    return { view: "sampleDetail", sampleId: decodeURIComponent(parts[1]) };
  }
  if (parts[0] === "batches" && parts[1]) {
    return { view: "batchDetail", batchId: decodeURIComponent(parts[1]) };
  }
  if (parts[0] === "samples") return { view: "samples" };
  if (parts[0] === "batches") return { view: "batches" };
  if (parts[0] === "create") return { view: "create" };
  if (parts[0] === "jobs") return { view: "jobs" };
  if (parts[0] === "settings") return { view: "settings" };
  return { view: "home" };
}

function syncRouteSelection(route) {
  if (route.sampleId) {
    state.selectedSampleId = route.sampleId;
  }
  if (route.batchId) {
    state.selectedBatchId = route.batchId;
  }
}

function applyRoute(route = routeFromLocation()) {
  syncRouteSelection(route);
  switchView(route.view);
  if (!state.initialRouteApplied) {
    state.initialRouteApplied = true;
    if (route.bodyPlan) {
      chooseSkeletonType(route.bodyPlan);
    }
    if (route.view === "create" && route.step === "skeleton") {
      setCreateWizardStep("skeleton");
    }
  }
}

function navigateTo(path) {
  window.history.pushState({}, "", path);
  applyRoute();
}

function isRunning(job) {
  return job?.status === "running";
}

function isTrainingReadySample(sample) {
  return Boolean(sample?.training_eligible || sample?.export_verified || sample?.status === "verified_exported");
}

function activeJobs() {
  return state.jobs.filter(isRunning);
}

function unfinishedSamples() {
  return state.samples.filter((sample) => !isTrainingReadySample(sample));
}

function jobActionLabel(value) {
  const labels = {
    "run-batch": "Batch",
    "generate-reference": "Reference images",
    "submit-tripo": "Tripo model",
    "poll-tripo": "Model download",
    "prepare-label-work": "Blender prep",
    "export-verified": "Verified label export",
    "run-pipeline": "Automatic pipeline",
  };
  return labels[value] || labelText(value || "job");
}

function sampleJobs(sample) {
  return state.jobs.filter((job) => job.payload?.sampleId === sample.sample_id);
}

function sampleJobAction(job) {
  return job?.payload?.action || job?.action || "";
}

function jobSupersededByArtifacts(sample, job) {
  if (!job || job.status === "running") return false;
  const action = sampleJobAction(job);
  if (action === "prepare-label-work" && sample.label_work_blend) return true;
  if (action === "poll-tripo" && sample.model?.url) return true;
  if (action === "generate-reference" && hasReferenceSet(sample)) return true;
  if (action === "export-verified" && isTrainingReadySample(sample)) return true;
  return false;
}

function latestSampleJob(sample) {
  return sampleJobs(sample).find((job) => !jobSupersededByArtifacts(sample, job)) || null;
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.error || response.statusText);
  }
  return body;
}

async function loadState() {
  const data = await fetchJson("/api/state");
  state.catalog = data.catalog || { animals: [], specs: [] };
  state.samples = data.samples || [];
  state.batches = data.batches || data.batch_runs || [];
  state.jobs = data.jobs || [];
  state.settings = data.settings || { blender_path: "", blender_exists: false };
  render();
}

function chooseSelections(route = routeFromLocation()) {
  if (!route.batchId && !state.batches.some((batch) => batch.run_id === state.selectedBatchId)) {
    state.selectedBatchId = state.batches[0]?.run_id || "";
  }
  if (!route.sampleId && !state.samples.some((sample) => sample.sample_id === state.selectedSampleId)) {
    state.selectedSampleId = state.samples[0]?.sample_id || "";
  }
}

function render() {
  const route = routeFromLocation();
  syncRouteSelection(route);
  chooseSelections(route);
  renderCreateWizard();
  elements.batchCount.textContent = state.batches.length;
  elements.sampleCount.textContent = state.samples.length;
  elements.jobCount.textContent = state.jobs.length;
  const runningJobs = state.jobs.filter(isRunning).length;
  const staleJobs = state.jobs.filter((job) => job.status === "stale").length;
  const runningText = runningJobs ? `, ${runningJobs} running` : "";
  const staleText = staleJobs ? `, ${staleJobs} stale` : "";
  elements.statusLine.textContent = `${state.batches.length} batches, ${state.samples.length} samples, ${state.jobs.length} UI jobs${runningText}${staleText}`;
  renderHome();
  renderBatches();
  renderBatchDetail();
  renderSamples();
  renderSampleDetail();
  renderJobs();
  renderSettings();
  applyRoute(route);
}

function renderHome() {
  const running = activeJobs();
  elements.homeActiveJobs.innerHTML = running.length
    ? running.map((job) => jobCard(job)).join("")
    : emptyState("No active jobs", "Running reference art, Tripo, and Blender prep jobs will show here.");

  const samples = unfinishedSamples();
  elements.homeUnfinishedSamples.innerHTML = samples.length
    ? samples.map((sample) => sampleCard(sample, { buttonLabel: "Open sample" })).join("")
    : emptyState("No unfinished samples", "Everything is through the pipeline and ready for training.", "Create Sample", "create");
}

function renderCreateWizard() {
  renderSkeletonTypeChoices();
  renderSkeletonSchemaPreview();
}

function renderSettings() {
  if (document.activeElement !== elements.blenderPathInput) {
    elements.blenderPathInput.value = state.settings.blender_path || "";
  }
  elements.settingsBlenderStatus.textContent = state.settings.blender_exists
    ? "Blender path is ready for prep and opening label files."
    : "Set this to blender.exe before opening label files from Nito.";
}

function batchStatus(batch) {
  if (!batch.finished_at) return "open";
  if (batch.failed_count) return "has_failures";
  return batch.dry_run ? "dry_run" : "ready";
}

function renderBatches() {
  if (!state.batches.length) {
    elements.batchList.innerHTML = emptyState(
      "No batches yet",
      "Create prompt-backed samples first, then group them into reusable training sets.",
      "Create Sample",
      "create",
    );
    return;
  }
  elements.batchList.innerHTML = state.batches
    .map((batch) => {
      const faceRange = Array.isArray(batch.face_limit_range) && batch.face_limit_range.length === 2
        ? `${batch.face_limit_range[0]}-${batch.face_limit_range[1]} faces`
        : "";
      return `
        <article class="batch-item">
          <div class="item-header">
            <h3>${escapeHtml(batch.run_id)}</h3>
            ${tag(batchStatus(batch))}
          </div>
          <p>${batch.count || 0} samples | ${formatTime(batch.started_at)}</p>
          <div class="tag-row">
            ${batch.seed ? tag(`seed ${batch.seed}`) : ""}
            ${faceRange ? tag(faceRange) : ""}
            ${batch.failed_count ? tag(`${batch.failed_count} failed`) : tag("0 failed")}
          </div>
          <a class="button-link" href="${escapeHtml(pagePath("batchDetail", batch.run_id))}">View Batch</a>
        </article>
      `;
    })
    .join("");
}

function renderBatchDetail() {
  const batch = state.batches.find((item) => item.run_id === state.selectedBatchId);
  if (!batch) {
    const message = state.selectedBatchId
      ? `Batch not found: ${state.selectedBatchId}`
      : "Select a batch.";
    elements.batchDetail.innerHTML = `<p class="empty">${escapeHtml(message)}</p>`;
    return;
  }
  const sampleIds = batch.sample_ids || [];
  elements.batchDetail.innerHTML = `
    <div class="item-header">
      <h3>${escapeHtml(batch.run_id)}</h3>
      ${tag(batchStatus(batch))}
    </div>
    <p class="detail-meta">
      ${batch.count || 0} samples | started ${formatTime(batch.started_at)} | finished ${formatTime(batch.finished_at)}
    </p>
    <div class="tag-row">
      ${batch.dry_run ? tag("dry run") : tag("live")}
      ${batch.seed ? tag(`seed ${batch.seed}`) : ""}
      ${batch.summary_path ? tag("summary saved") : ""}
    </div>
    <h4>Samples</h4>
    <div class="sample-list batch-sample-list">
      ${
        sampleIds.length
          ? sampleIds.map((sampleId) => batchSampleCard(sampleId)).join("")
          : '<p class="empty">This batch has no sample membership recorded.</p>'
      }
    </div>
  `;
}

function batchSampleCard(sampleId) {
  const sample = sampleById(sampleId);
  if (!sample) {
    return `
      <article class="sample-item">
        <div class="item-header">
          <h3>${escapeHtml(sampleId)}</h3>
          ${tag("missing")}
        </div>
      </article>
    `;
  }
  return sampleCard(sample, { compact: true, buttonLabel: "Open sample" });
}

function renderSamples() {
  if (!state.samples.length) {
    elements.sampleList.innerHTML = emptyState(
      "No samples yet",
      "Create a prompt-backed sample, then run it through the reference and model pipeline.",
      "Create Sample",
      "create",
    );
    return;
  }
  elements.sampleList.innerHTML = state.samples.map((sample) => sampleCard(sample)).join("");
}

function sampleCard(sample, options = {}) {
  const preview = sample.thumbnail_url
    ? `<a class="sample-preview" href="${sample.thumbnail_url}" target="_blank" rel="noreferrer"><img src="${sample.thumbnail_url}" alt="${escapeHtml(sample.sample_id)} preview"></a>`
    : "";
  const batches = sample.batches || [];
  const buttonLabel = options.buttonLabel || "View Sample";
  return `
    <article class="sample-item">
      <div class="sample-title-row">
        ${preview}
        <div>
          <div class="item-header">
            <h3>${escapeHtml(sample.sample_id)}</h3>
            ${tag(sample.status)}
          </div>
          <p>
            ${escapeHtml(labelText(sample.animal_type))}
            / ${escapeHtml(labelText(sample.body_plan || sample.morphology_type))}
            / ${escapeHtml(labelText(sample.armor_state || "armor unspecified"))}
          </p>
          ${sample.prompt ? `<p class="prompt-snippet">${escapeHtml(sample.prompt)}</p>` : ""}
          <div class="tag-row">
            ${batches.length ? tag(`${batches.length} batches`) : tag("unbatched")}
            ${(sample.variant_tags || []).map((value) => tag(value)).join("")}
            ${sample.face_limit ? tag(`${sample.face_limit} faces`) : ""}
            ${sample.model?.url ? tag("model") : ""}
            ${!sample.model?.url && sample.model?.remote_url ? tag("remote model") : ""}
            ${Object.keys(sample.reference_images || {}).length ? tag("reference") : ""}
            ${Object.keys(sample.review_images || {}).length ? tag("review") : ""}
          </div>
          <a class="button-link" href="${escapeHtml(pagePath("sampleDetail", sample.sample_id))}">${escapeHtml(buttonLabel)}</a>
        </div>
      </div>
    </article>
  `;
}

function orderedEntries(value, preferredOrder) {
  const entries = [];
  const seen = new Set();
  for (const key of preferredOrder) {
    if (value?.[key]) {
      entries.push([key, value[key]]);
      seen.add(key);
    }
  }
  for (const entry of Object.entries(value || {})) {
    if (!seen.has(entry[0])) entries.push(entry);
  }
  return entries;
}

function gallery(title, images, preferredOrder) {
  const entries = orderedEntries(images, preferredOrder);
  if (!entries.length) return "";
  return `
    <h4>${escapeHtml(title)}</h4>
    <div class="asset-gallery">
      ${entries
        .map(
          ([label, url]) => `
            <a class="asset-tile" href="${url}" target="_blank" rel="noreferrer">
              <span class="thumb"><img src="${url}" alt="${escapeHtml(label)}"></span>
              <span>${escapeHtml(label)}</span>
            </a>
          `,
        )
        .join("")}
    </div>
  `;
}

function modelPanel(sample) {
  const model = sample.model || {};
  const verifiedLabel = sample.verified_label || {};
  const localUrl = model.url || "";
  const remoteUrl = model.remote_url || "";
  const viewerUrl = model.viewer_url || "";
  const labelUrl = verifiedLabel.url || "";
  const labelMeshUrl = verifiedLabel.mesh_url || "";
  const displayUrl = localUrl || remoteUrl || viewerUrl || labelMeshUrl;
  const previewUrl = model.preview_proxy_url || model.preview_url || "";
  const safeDisplayUrl = escapeHtml(displayUrl);
  const safeRemoteUrl = escapeHtml(remoteUrl);
  const safePreviewUrl = escapeHtml(previewUrl);
  const safeLabelUrl = escapeHtml(labelUrl);
  const safeLabelMeshUrl = escapeHtml(labelMeshUrl);
  const fallbackUrl = !localUrl && remoteUrl && viewerUrl && viewerUrl !== remoteUrl ? viewerUrl : "";
  const safeFallbackUrl = escapeHtml(fallbackUrl);
  const displayType = modelType(model, displayUrl);
  const isRemoteOnly = Boolean(remoteUrl && !localUrl);
  const labelBoneCount = Number(verifiedLabel.bone_count || 0);
  if (!displayUrl) {
    return `
      <h4>3D Model</h4>
      <p class="empty">No downloaded GLB/GLTF model for this sample yet.</p>
      ${labelUrl ? `<p class="detail-meta">Verified label exported: <a href="${safeLabelUrl}" target="_blank" rel="noreferrer">${escapeHtml(verifiedLabel.name || "label JSON")}</a></p>` : ""}
    `;
  }
  const canEmbed = ["glb", "gltf", "obj"].includes(displayType) || Boolean(labelMeshUrl);
  return `
    <h4>3D Model</h4>
    <div class="model-panel ${isRemoteOnly ? "is-remote-only" : ""}">
      ${
        isRemoteOnly
          ? `<div class="model-state-card">
              <div>
                <strong>Tripo model generated</strong>
                <p>The remote GLB is ready, but the local download is missing. Retry the download to prep it for Blender.</p>
              </div>
              <button
                type="button"
                data-sample-id="${escapeHtml(sample.sample_id)}"
                data-sample-action="poll-tripo"
              >
                Retry Download
              </button>
            </div>`
          : ""
      }
      ${
        canEmbed
          ? `<div
              class="three-editor"
              data-sample-id="${escapeHtml(sample.sample_id)}"
              data-model-src="${safeDisplayUrl}"
              data-fallback-src="${safeFallbackUrl}"
              data-label-src="${safeLabelUrl}"
              data-label-mesh-src="${safeLabelMeshUrl}"
              data-poster-src="${safePreviewUrl}"
            >
              <div class="three-toolbar" aria-label="3D model viewport controls">
                <button type="button" data-three-action="zoom-in" title="Zoom in" aria-label="Zoom in">+</button>
                <button type="button" data-three-action="zoom-out" title="Zoom out" aria-label="Zoom out">-</button>
                <button type="button" data-three-action="reset" title="Reset view">Reset</button>
                <button type="button" data-three-action="grid" title="Toggle grid">Grid</button>
                <button type="button" data-three-action="wireframe" title="Toggle wireframe">Wire</button>
                ${labelUrl ? `<button type="button" class="is-active" data-three-action="labels" title="Toggle exported skeleton overlay">Skeleton</button>` : ""}
                <button type="button" data-three-action="spin" title="Toggle auto rotate">Spin</button>
              </div>
              <div class="three-stage">
                <div class="three-canvas-host"></div>
                ${previewUrl ? `<img class="three-poster" src="${safePreviewUrl}" alt="${escapeHtml(sample.sample_id)} Tripo render">` : ""}
                <div class="axis-gizmo" aria-hidden="true">
                  <span class="axis-x">X</span>
                  <span class="axis-y">Y</span>
                  <span class="axis-z">Z</span>
                </div>
                <p class="viewer-status">Loading GLB viewport</p>
              </div>
            </div>`
          : previewUrl
            ? `<a class="model-render-preview" href="${safeRemoteUrl || safePreviewUrl}" target="_blank" rel="noreferrer">
                <img src="${safePreviewUrl}" alt="${escapeHtml(sample.sample_id)} Tripo render">
              </a>`
            : `<p class="empty">Preview supports GLB/GLTF. This model is ${escapeHtml(displayType || "unknown")}.</p>`
      }
      <div class="model-actions">
        <a href="${safeDisplayUrl}" target="_blank" rel="noreferrer">${localUrl ? "Open local model" : "Open remote GLB"}</a>
        ${remoteUrl ? `<a href="${safeRemoteUrl}" target="_blank" rel="noreferrer">Source URL</a>` : ""}
        ${viewerUrl && viewerUrl !== displayUrl ? `<a href="${escapeHtml(viewerUrl)}" target="_blank" rel="noreferrer">Proxy URL</a>` : ""}
        ${previewUrl ? `<a href="${safePreviewUrl}" target="_blank" rel="noreferrer">Open Tripo render</a>` : ""}
        ${labelUrl ? `<a href="${safeLabelUrl}" target="_blank" rel="noreferrer">Open label JSON</a>` : ""}
        ${labelMeshUrl ? `<a href="${safeLabelMeshUrl}" target="_blank" rel="noreferrer">Open label mesh</a>` : ""}
      </div>
      <p class="detail-meta">
        ${escapeHtml(localUrl ? model.name || model.file : "Remote Tripo GLB")}
        ${isRemoteOnly ? " | browser preview may depend on Tripo CORS" : ""}
        ${labelUrl ? ` | verified skeleton overlay${labelBoneCount ? ` (${labelBoneCount} bones)` : ""}` : ""}
        ${labelMeshUrl ? " | viewport uses canonical label mesh for Blender alignment" : ""}
      </p>
    </div>
  `;
}

function modelType(model, url) {
  if (model.type) return model.type;
  try {
    const path = new URL(url, window.location.href).pathname;
    const match = path.match(/\.([a-z0-9]+)$/i);
    return match ? match[1].toLowerCase() : "";
  } catch {
    return "";
  }
}

function hydrateModelViewers(container) {
  window.NitoThreeViewer?.mountAll(container);
}

function promptPanel(sample) {
  const prompts = sample.openai_reference_prompts || {};
  const entries = orderedEntries(prompts, ["front", "left", "right", "back"]);
  if (!sample.prompt && !entries.length) return "";
  return `
    <h4>Prompt</h4>
    <div class="prompt-list">
      ${sample.prompt ? `<pre class="prompt-block">${escapeHtml(sample.prompt)}</pre>` : ""}
      ${entries
        .map(([label, prompt]) => `<pre class="prompt-block">${escapeHtml(label)}\n${escapeHtml(prompt)}</pre>`)
        .join("")}
    </div>
  `;
}

function sampleActionPanel(sample) {
  const jobs = sampleJobs(sample);
  const activeJob = jobs.find(isRunning);
  const latestJob = latestSampleJob(sample);
  const stateJob = sample.ui_job?.job_id && !jobSupersededByArtifacts(sample, sample.ui_job) ? sample.ui_job : null;
  const pipeline = pipelineState(sample, activeJob);
  const statusJob = activeJob || latestJob || stateJob;
  const nextAction = nextPipelineAction(sample, activeJob);
  return `
    <section class="sample-actions">
      <div class="action-header">
        <div>
          <h4>Pipeline</h4>
          <p class="detail-meta">
            ${
              statusJob
                ? `${escapeHtml(jobActionLabel(statusJob.payload?.action || statusJob.action))} ${escapeHtml(statusJob.status)} for ${escapeHtml(formatDuration(elapsedForJob(statusJob)))}`
                : "No UI job has run for this sample."
            }
          </p>
        </div>
        ${statusJob ? `<button type="button" data-job-id="${escapeHtml(statusJob.job_id)}">View Log</button>` : ""}
      </div>
      <div class="pipeline-dag" aria-label="Sample pipeline">
        ${pipeline.map((step, index) => pipelineStep(step, index)).join("")}
      </div>
      <div class="next-step-row ${activeJob ? "is-running" : ""}">
        <button
          class="primary-inline-action ${activeJob ? "is-loading" : ""}"
          type="button"
          data-sample-id="${escapeHtml(sample.sample_id)}"
          data-sample-action="${escapeHtml(nextAction.action || "")}"
          ${nextAction.action ? "" : "disabled"}
        >
          ${activeJob ? '<span class="button-loader" aria-hidden="true"></span>' : ""}
          ${escapeHtml(nextAction.label)}
        </button>
        <span>${escapeHtml(nextAction.detail)}</span>
      </div>
      ${verifiedExportAction(sample, activeJob)}
      ${
        statusJob?.status === "stale"
          ? `<div class="stale-callout">
              <div>
                <strong>Job stopped reporting</strong>
                <p>Reset the stale state to rerun from the last saved artifact.</p>
              </div>
              <button type="button" data-reset-stale="${escapeHtml(sample.sample_id)}">Reset stale state</button>
            </div>`
          : ""
      }
      <div class="tag-row">
        ${activeJob ? tag("running") : ""}
        ${statusJob?.status === "stale" ? tag("stale") : ""}
        ${statusJob ? tag(formatDuration(elapsedForJob(statusJob))) : ""}
        ${latestJob ? tag(`job ${latestJob.job_id}`) : ""}
        ${sample.ui_job?.action ? tag(sample.ui_job.action) : ""}
      </div>
    </section>
  `;
}

function hasReferenceSet(sample) {
  const referenceImages = sample.reference_images || {};
  return ["front", "left", "right", "back"].every((view) => Boolean(referenceImages[view]));
}

function activePipelineStage(sample, activeJob) {
  if (!activeJob) return "";
  const action = activeJob.payload?.action || "";
  if (action === "generate-reference") return "reference";
  if (action === "submit-tripo" || action === "poll-tripo") return "model";
  if (action === "prepare-label-work") return "blender";
  if (action === "export-verified") return "export";
  if (action === "run-pipeline") {
    if (!hasReferenceSet(sample)) return "reference";
    if (!sample.model?.url) return "model";
    return "blender";
  }
  return "";
}

function pipelineState(sample, activeJob) {
  const hasRefs = hasReferenceSet(sample);
  const hasModelTask = Boolean(sample.tripo_task_id);
  const hasRemoteModel = Boolean(sample.model?.remote_url);
  const hasModel = Boolean(sample.model?.url);
  const hasBlenderFile = Boolean(sample.label_work_blend);
  const isVerified = isTrainingReadySample(sample);
  const schema = skeletonSchemaForSample(sample);
  const activeStage = activePipelineStage(sample, activeJob);
  const stepState = (key, complete, ready) => {
    if (activeStage === key) return "running";
    if (complete) return "complete";
    if (ready) return "ready";
    return "blocked";
  };
  return [
    {
      key: "sample",
      title: "Sample",
      detail: "Prompt saved",
      state: "complete",
    },
    {
      key: "reference",
      title: "Reference art",
      detail: hasRefs ? "4 views ready" : "Front, left, right, back",
      state: stepState("reference", hasRefs, true),
    },
    {
      key: "model",
      title: "3D model",
      detail: hasModel ? "Local GLB ready" : hasRemoteModel ? "Remote GLB ready" : hasModelTask ? "Task submitted" : "Tripo generation",
      state: stepState("model", hasModel, hasRefs || hasRemoteModel),
    },
    {
      key: "blender",
      title: "Blender file",
      detail: hasBlenderFile ? "Review file ready" : hasRemoteModel && !hasModel ? "Needs local GLB" : "Prep for annotator",
      state: stepState("blender", hasBlenderFile, hasModel),
    },
    {
      key: "skeleton",
      title: "Skeleton",
      detail: hasBlenderFile
        ? isVerified
          ? "Guide exported"
          : `${schema?.label || "Schema"} placement`
        : schema
          ? `${schema.label} waiting`
          : "Waiting on Blender file",
      state: isVerified ? "complete" : hasBlenderFile ? "manual" : "blocked",
    },
    {
      key: "export",
      title: "Verified label",
      detail: isVerified ? "Ready for training" : "Export after saving Blender edits",
      state: stepState("export", isVerified, hasBlenderFile),
    },
  ];
}

function pipelineStep(step, index) {
  return `
    <div class="pipeline-step-wrap">
      ${index ? '<span class="pipeline-edge"></span>' : ""}
      <article class="pipeline-step step-${escapeHtml(step.state)}">
        ${step.state === "running" ? '<span class="arcane-loader" aria-hidden="true"></span>' : '<span class="step-state-dot" aria-hidden="true"></span>'}
        <div>
          <strong>${escapeHtml(step.title)}</strong>
          <span>${escapeHtml(step.detail)}</span>
        </div>
        ${tag(step.state)}
      </article>
    </div>
  `;
}

function nextPipelineAction(sample, activeJob) {
  if (activeJob) {
    return {
      action: "",
      label: `${jobActionLabel(activeJob.payload?.action)} running`,
      detail: `${formatDuration(elapsedForJob(activeJob))} elapsed`,
    };
  }
  if (!sample.label_work_blend) {
    const hasAnyMachineArtifact = hasReferenceSet(sample) || sample.tripo_task_id || sample.model?.url || sample.model?.remote_url;
    return {
      action: "run-pipeline",
      label: hasAnyMachineArtifact ? "Resume Automatic Pipeline" : "Run Automatic Pipeline",
      detail: "Runs reference art, Tripo generation, model download, and Blender prep, then pauses for skeleton placement.",
    };
  }
  if (isTrainingReadySample(sample)) {
    return {
      action: "",
      label: "Ready for Training",
      detail: "Verified label export is complete.",
    };
  }
  return {
    action: "open-blender",
    label: "Open in Blender",
    detail: "Launch the label-work file and place the skeleton manually.",
  };
}

function verifiedExportAction(sample, activeJob) {
  if (activeJob || !sample.label_work_blend || isTrainingReadySample(sample)) return "";
  return `
    <div class="final-action-row">
      <button
        type="button"
        data-sample-id="${escapeHtml(sample.sample_id)}"
        data-sample-action="export-verified"
      >
        Export Verified Label
      </button>
      <span>Use this after saving the corrected guide in Blender.</span>
    </div>
  `;
}

function sampleDetailKey(sample) {
  const jobs = sampleJobs(sample).map((job) => ({
    job_id: job.job_id,
    action: job.payload?.action || job.action || "",
    status: job.status,
    returncode: job.returncode,
    finished_at: job.finished_at,
  }));
  const uiJob = sample.ui_job
    ? {
        job_id: sample.ui_job.job_id,
        action: sample.ui_job.action,
        status: sample.ui_job.status,
        returncode: sample.ui_job.returncode,
        finished_at: sample.ui_job.finished_at,
      }
    : null;
  return JSON.stringify({
    sample_id: sample.sample_id,
    prompt: sample.prompt,
    status: sample.status,
    animal_type: sample.animal_type,
    body_plan: sample.body_plan,
    morphology_type: sample.morphology_type,
    skeleton_schema_id: sample.skeleton_schema_id,
    armor_state: sample.armor_state,
    variant_tags: sample.variant_tags || [],
    face_limit: sample.face_limit,
    tripo_task_id: sample.tripo_task_id,
    label_work_blend: sample.label_work_blend,
    batches: sample.batches || [],
    model: sample.model || {},
    reference_images: sample.reference_images || {},
    review_images: sample.review_images || {},
    openai_reference_prompts: sample.openai_reference_prompts || {},
    ui_job: uiJob,
    jobs,
  });
}

function skeletonSchemaPanel(sample) {
  const schema = skeletonSchemaForSample(sample);
  const schemaId = sample.skeleton_schema_id || skeletonSchemaIdForBodyPlan(sample.body_plan || sample.morphology_type || "");
  return `
    <section class="skeleton-schema-section">
      <div class="section-heading">
        <h4>Skeleton Schema</h4>
        ${schemaId ? tag(schemaId) : tag("unmapped")}
      </div>
      ${skeletonSchemaCard(schema)}
    </section>
  `;
}

function renderSampleDetail() {
  const sample = state.selectedSampleId ? sampleById(state.selectedSampleId) : state.samples[0];
  if (!sample) {
    const message = state.selectedSampleId
      ? `Sample not found: ${state.selectedSampleId}`
      : "Select a sample.";
    elements.sampleDetail.innerHTML = `<p class="empty">${escapeHtml(message)}</p>`;
    elements.sampleDetail.dataset.sampleId = "";
    elements.sampleDetail.dataset.renderKey = "";
    return;
  }
  state.selectedSampleId = sample.sample_id;
  const renderKey = sampleDetailKey(sample);
  if (
    elements.sampleDetail.dataset.sampleId === sample.sample_id &&
    elements.sampleDetail.dataset.renderKey === renderKey
  ) {
    hydrateModelViewers(elements.sampleDetail);
    return;
  }
  const batches = sample.batches || [];
  elements.sampleDetail.innerHTML = `
    <div class="item-header">
      <h3>${escapeHtml(sample.sample_id)}</h3>
      ${tag(sample.status)}
    </div>
    <p class="detail-meta">
      Animal: ${escapeHtml(labelText(sample.animal_type))}
      | Body plan: ${escapeHtml(labelText(sample.body_plan || sample.morphology_type))}
      | Armor: ${escapeHtml(labelText(sample.armor_state || "unspecified"))}
      ${sample.face_limit ? ` | ${escapeHtml(sample.face_limit)} faces` : ""}
    </p>
    <div class="tag-row">
      ${batches.length ? batches.map((batchId) => tag(batchId)).join("") : tag("unbatched")}
      ${(sample.variant_tags || []).map((value) => tag(value)).join("")}
    </div>
    ${skeletonSchemaPanel(sample)}
    ${sampleActionPanel(sample)}
    ${modelPanel(sample)}
    ${gallery("OpenAI References", sample.reference_images, ["front", "left", "right", "back"])}
    ${gallery("Blender Review Renders", sample.review_images, ["front", "left", "right", "rear", "top", "quarter"])}
    ${promptPanel(sample)}
  `;
  elements.sampleDetail.dataset.sampleId = sample.sample_id;
  elements.sampleDetail.dataset.renderKey = renderKey;
  hydrateModelViewers(elements.sampleDetail);
}

function renderJobs() {
  if (!state.jobs.length) {
    elements.jobList.innerHTML = emptyState(
      "No jobs yet",
      "Pipeline runs will appear here with elapsed time, status, and logs.",
    );
    return;
  }
  elements.jobList.innerHTML = state.jobs.map((job) => jobCard(job)).join("");
}

function jobCard(job) {
  return `
    <article class="job-item">
      <div class="item-header">
        <h3>${escapeHtml(job.job_id)}</h3>
        ${tag(job.status)}
      </div>
      <p>${formatTime(job.started_at)} | ${formatDuration(elapsedForJob(job))} | return code ${job.returncode ?? "pending"}</p>
      <div class="tag-row">
        ${tag(jobActionLabel(job.payload?.action))}
        ${job.payload?.sampleId ? tag(job.payload.sampleId) : ""}
        ${job.payload?.count ? tag(`${job.payload.count} samples`) : ""}
        ${job.payload?.dryRun ? tag("dry_run") : ""}
        ${job.payload?.faceLimit ? tag(`${job.payload.faceLimit} faces`) : ""}
        ${job.status === "stale" ? tag("stale") : ""}
      </div>
      <button type="button" data-job-id="${escapeHtml(job.job_id)}">View Log</button>
    </article>
  `;
}

function inferredArmorState(prompt) {
  const text = String(prompt || "").toLowerCase();
  if (/\bunarmou?red\b|\bwithout armor\b|\bno armor\b/.test(text)) return "unarmored";
  if (/\barmou?red\b|\barmor\b/.test(text)) return "armored";
  return "";
}

function inferredVariantTags(prompt) {
  const text = String(prompt || "").toLowerCase();
  const tags = state.catalog.variant_tags || [];
  return tags.filter((tagName) => {
    const phrase = String(tagName || "").toLowerCase().replaceAll("_", " ");
    return phrase && new RegExp(`\\b${phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`).test(text);
  });
}

function inferredAnimalType(prompt) {
  const text = String(prompt || "").toLowerCase();
  const animals = state.catalog.animals || [];
  return animals.find((animal) => new RegExp(`\\b${String(animal).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "i").test(text)) || "unknown";
}

function samplePayload() {
  const formData = new FormData(elements.sampleForm);
  const prompt = formData.get("prompt") || "";
  return {
    prompt,
    samplePrefix: "nito",
    animalType: inferredAnimalType(prompt),
    morphologyType: formData.get("morphologyType") || "",
    armorState: inferredArmorState(prompt),
    variantTags: inferredVariantTags(prompt),
  };
}

function automaticPipelinePayload() {
  return {
    prepareLabelWork: true,
  };
}

function batchPayload() {
  const formData = new FormData(elements.runForm);
  return {
    count: Number(formData.get("count") || 1),
    samplePrefix: formData.get("samplePrefix") || "ui",
    seed: Number(formData.get("seed") || 0),
    animalType: "all",
    armorState: "all",
    faceLimitMin: Number(formData.get("faceLimitMin") || 3000),
    faceLimitMax: Number(formData.get("faceLimitMax") || 8000),
    dryRun: formData.get("dryRun") === "on",
    prepareLabelWork: formData.get("prepareLabelWork") === "on",
    continueOnError: formData.get("continueOnError") === "on",
  };
}

async function createSample(event) {
  event.preventDefault();
  if (!elements.sampleMorphologySelect.value) {
    elements.statusLine.textContent = "Choose a skeleton type before creating the sample.";
    setCreateWizardStep("skeleton");
    return;
  }
  elements.createSampleButton.disabled = true;
  elements.statusLine.textContent = "Creating sample and starting pipeline";
  try {
    const result = await fetchJson("/api/samples", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(samplePayload()),
    });
    const job = await fetchJson(`/api/samples/${encodeURIComponent(result.sample_id)}/actions/run-pipeline`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(automaticPipelinePayload()),
    });
    state.selectedSampleId = result.sample_id;
    state.selectedJobId = job.job_id;
    await loadState();
    elements.sampleForm.reset();
    elements.sampleMorphologySelect.value = "";
    setCreateWizardStep("prompt");
    renderCreateWizard();
    navigateTo(pagePath("sampleDetail", result.sample_id));
    renderSampleDetail();
    elements.statusLine.textContent = "Pipeline started. Nito will pause when skeleton placement is ready.";
  } catch (error) {
    elements.statusLine.textContent = error.message;
  } finally {
    elements.createSampleButton.disabled = false;
  }
}

async function startBatch(event) {
  event.preventDefault();
  elements.runButton.disabled = true;
  elements.statusLine.textContent = "Starting batch job";
  try {
    const job = await fetchJson("/api/run-batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(batchPayload()),
    });
    state.selectedJobId = job.job_id;
    await loadState();
    await loadJobLog(job.job_id);
    navigateTo("/jobs");
  } catch (error) {
    elements.statusLine.textContent = error.message;
  } finally {
    elements.runButton.disabled = false;
  }
}

async function loadJobLog(jobId) {
  const job = await fetchJson(`/api/jobs/${jobId}`);
  state.selectedJobId = jobId;
  elements.jobLog.textContent = job.log || "No output yet.";
}

async function startSampleAction(sampleId, action) {
  elements.statusLine.textContent = `Starting ${jobActionLabel(action)}`;
  const job = await fetchJson(`/api/samples/${encodeURIComponent(sampleId)}/actions/${encodeURIComponent(action)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(action === "run-pipeline" ? automaticPipelinePayload() : {}),
  });
  state.selectedSampleId = sampleId;
  state.selectedJobId = job.job_id;
  await loadState();
  await loadJobLog(job.job_id);
  renderSampleDetail();
}

async function openBlenderSample(sampleId) {
  elements.statusLine.textContent = "Opening Blender";
  const result = await fetchJson(`/api/samples/${encodeURIComponent(sampleId)}/open-blender`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  elements.statusLine.textContent = `Opened ${result.blend_file}`;
}

async function resetStaleSample(sampleId) {
  elements.statusLine.textContent = "Resetting stale job state";
  await fetchJson(`/api/samples/${encodeURIComponent(sampleId)}/reset-stale`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  state.selectedSampleId = sampleId;
  await loadState();
  renderSampleDetail();
}

async function saveSettings(event) {
  event.preventDefault();
  elements.saveSettingsButton.disabled = true;
  elements.statusLine.textContent = "Saving settings";
  try {
    const settings = await fetchJson("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ blenderPath: elements.blenderPathInput.value }),
    });
    state.settings = settings;
    renderSettings();
    elements.statusLine.textContent = "Settings saved";
  } catch (error) {
    elements.statusLine.textContent = error.message;
  } finally {
    elements.saveSettingsButton.disabled = false;
  }
}

function switchView(viewName) {
  const activePath = pagePath(viewName);
  document.querySelectorAll(".tab").forEach((link) => {
    link.classList.toggle("is-active", link.getAttribute("href") === activePath);
  });
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("is-active", view.id === `${viewName}View`);
  });
}

elements.refreshButton.addEventListener("click", loadState);
elements.promptNextButton.addEventListener("click", continueFromPrompt);
elements.schemaBackButton.addEventListener("click", () => setCreateWizardStep("prompt"));
elements.skeletonTypeGrid.addEventListener("click", (event) => {
  const card = event.target.closest("button[data-body-plan]");
  if (!card) return;
  chooseSkeletonType(card.dataset.bodyPlan);
});
elements.sampleForm.addEventListener("submit", createSample);
if (elements.runForm) {
  elements.runForm.addEventListener("submit", startBatch);
}
elements.settingsForm.addEventListener("submit", saveSettings);
window.addEventListener("nito-three-ready", () => hydrateModelViewers(elements.sampleDetail));
elements.sampleDetail.addEventListener("click", async (event) => {
  const resetButton = event.target.closest("button[data-reset-stale]");
  if (resetButton) {
    resetButton.disabled = true;
    try {
      await resetStaleSample(resetButton.dataset.resetStale);
    } catch (error) {
      elements.statusLine.textContent = error.message;
    } finally {
      resetButton.disabled = false;
    }
    return;
  }
  const actionButtonElement = event.target.closest("button[data-sample-action]");
  if (actionButtonElement) {
    actionButtonElement.disabled = true;
    try {
      if (actionButtonElement.dataset.sampleAction === "open-blender") {
        await openBlenderSample(actionButtonElement.dataset.sampleId);
      } else {
        await startSampleAction(actionButtonElement.dataset.sampleId, actionButtonElement.dataset.sampleAction);
      }
    } catch (error) {
      elements.statusLine.textContent = error.message;
    } finally {
      actionButtonElement.disabled = false;
    }
    return;
  }
  const logButton = event.target.closest("button[data-job-id]");
  if (!logButton) return;
  await loadJobLog(logButton.dataset.jobId);
  navigateTo("/jobs");
});
elements.jobList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-job-id]");
  if (!button) return;
  await loadJobLog(button.dataset.jobId);
});
window.addEventListener("popstate", render);

setInterval(async () => {
  try {
    await loadState();
    if (state.selectedJobId) {
      await loadJobLog(state.selectedJobId);
    }
  } catch (error) {
    elements.statusLine.textContent = error.message;
  }
}, 4000);

loadState().catch((error) => {
  elements.statusLine.textContent = error.message;
});
