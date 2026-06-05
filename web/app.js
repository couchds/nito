const state = {
  catalog: { animals: [], specs: [] },
  samples: [],
  batches: [],
  jobs: [],
  selectedBatchId: "",
  selectedSampleId: "",
  selectedJobId: "",
};

const elements = {
  statusLine: document.querySelector("#statusLine"),
  refreshButton: document.querySelector("#refreshButton"),
  sampleForm: document.querySelector("#sampleForm"),
  createSampleButton: document.querySelector("#createSampleButton"),
  runForm: document.querySelector("#runForm"),
  runButton: document.querySelector("#runButton"),
  sampleMorphologySelect: document.querySelector("#sampleMorphologySelect"),
  bodyPlanExamples: document.querySelector("#bodyPlanExamples"),
  variantTagList: document.querySelector("#variantTagList"),
  batchCount: document.querySelector("#batchCount"),
  sampleCount: document.querySelector("#sampleCount"),
  jobCount: document.querySelector("#jobCount"),
  batchList: document.querySelector("#batchList"),
  batchDetail: document.querySelector("#batchDetail"),
  sampleList: document.querySelector("#sampleList"),
  sampleDetail: document.querySelector("#sampleDetail"),
  jobList: document.querySelector("#jobList"),
  jobLog: document.querySelector("#jobLog"),
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

function sampleById(sampleId) {
  return state.samples.find((sample) => sample.sample_id === sampleId);
}

function isRunning(job) {
  return job?.status === "running";
}

function jobActionLabel(value) {
  const labels = {
    "run-batch": "Batch",
    "generate-reference": "Reference images",
    "submit-tripo": "Tripo model",
    "poll-tripo": "Model download",
    "prepare-label-work": "Blender prep",
    "run-pipeline": "Image + model pipeline",
  };
  return labels[value] || labelText(value || "job");
}

function sampleJobs(sample) {
  return state.jobs.filter((job) => job.payload?.sampleId === sample.sample_id);
}

function latestSampleJob(sample) {
  return sampleJobs(sample)[0] || null;
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
  render();
}

function chooseSelections() {
  if (!state.batches.some((batch) => batch.run_id === state.selectedBatchId)) {
    state.selectedBatchId = state.batches[0]?.run_id || "";
  }
  if (!state.samples.some((sample) => sample.sample_id === state.selectedSampleId)) {
    state.selectedSampleId = state.samples[0]?.sample_id || "";
  }
}

function render() {
  chooseSelections();
  renderLabelSelects();
  elements.batchCount.textContent = state.batches.length;
  elements.sampleCount.textContent = state.samples.length;
  elements.jobCount.textContent = state.jobs.length;
  const runningJobs = state.jobs.filter(isRunning).length;
  const staleJobs = state.jobs.filter((job) => job.status === "stale").length;
  const runningText = runningJobs ? `, ${runningJobs} running` : "";
  const staleText = staleJobs ? `, ${staleJobs} stale` : "";
  elements.statusLine.textContent = `${state.batches.length} batches, ${state.samples.length} samples, ${state.jobs.length} UI jobs${runningText}${staleText}`;
  renderBatches();
  renderBatchDetail();
  renderSamples();
  renderSampleDetail();
  renderJobs();
}

function catalogValues(fieldName) {
  return [...new Set((state.catalog.specs || []).map((spec) => spec[fieldName]).filter(Boolean))].sort();
}

function renderSelectOptions(select, values, fallbackValue, fallbackLabel) {
  const current = select.value || fallbackValue;
  const options = [`<option value="${escapeHtml(fallbackValue)}">${escapeHtml(fallbackLabel)}</option>`];
  for (const value of values) {
    options.push(`<option value="${escapeHtml(value)}">${escapeHtml(labelText(value))}</option>`);
  }
  select.innerHTML = options.join("");
  select.value = [...select.options].some((option) => option.value === current) ? current : fallbackValue;
}

function renderLabelSelects() {
  renderSelectOptions(elements.sampleMorphologySelect, state.catalog.body_plans || catalogValues("morphology_type"), "", "Select body plan");
  renderBodyPlanExamples();
  renderVariantTags();
}

function renderBodyPlanExamples() {
  const selected = elements.sampleMorphologySelect.value;
  const examples = state.catalog.label_schema?.body_plan_examples || {};
  const selectedExamples = examples[selected];
  if (Array.isArray(selectedExamples) && selectedExamples.length) {
    elements.bodyPlanExamples.textContent = `Examples: ${selectedExamples.slice(0, 2).join(", ")}.`;
    return;
  }
  elements.bodyPlanExamples.textContent = "Examples: medium quadruped (dog, cat), hind-leg dominant (frog, rabbit).";
}

function renderVariantTags() {
  const current = new Set(
    [...elements.variantTagList.querySelectorAll("input[name='variantTags']:checked")].map((input) => input.value),
  );
  const tags = state.catalog.variant_tags || [];
  if (!tags.length) {
    elements.variantTagList.innerHTML = '<p class="empty compact-empty">No variant tags configured.</p>';
    return;
  }
  elements.variantTagList.innerHTML = tags
    .map(
      (value) => `
        <label class="check-chip">
          <input name="variantTags" type="checkbox" value="${escapeHtml(value)}" ${current.has(value) ? "checked" : ""}>
          <span>${escapeHtml(labelText(value))}</span>
        </label>
      `,
    )
    .join("");
}

function batchStatus(batch) {
  if (!batch.finished_at) return "open";
  if (batch.failed_count) return "has_failures";
  return batch.dry_run ? "dry_run" : "ready";
}

function renderBatches() {
  if (!state.batches.length) {
    elements.batchList.innerHTML = '<p class="empty">No batches yet.</p>';
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
          <button type="button" data-batch-id="${escapeHtml(batch.run_id)}">View Batch</button>
        </article>
      `;
    })
    .join("");
}

function renderBatchDetail() {
  const batch = state.batches.find((item) => item.run_id === state.selectedBatchId);
  if (!batch) {
    elements.batchDetail.innerHTML = '<p class="empty">Select a batch.</p>';
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
    elements.sampleList.innerHTML = '<p class="empty">No samples yet.</p>';
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
            ${Object.keys(sample.reference_images || {}).length ? tag("reference") : ""}
            ${Object.keys(sample.multiview_images || {}).length ? tag("multiview") : ""}
            ${Object.keys(sample.review_images || {}).length ? tag("review") : ""}
          </div>
          <button type="button" data-sample-id="${escapeHtml(sample.sample_id)}">${buttonLabel}</button>
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
  if (!model.url) {
    return `
      <h4>3D Model</h4>
      <p class="empty">No downloaded GLB/GLTF model for this sample yet.</p>
    `;
  }
  const canEmbed = ["glb", "gltf"].includes(model.type);
  return `
    <h4>3D Model</h4>
    <div class="model-panel">
      ${
        canEmbed
          ? `<model-viewer src="${model.url}" camera-controls auto-rotate shadow-intensity="0.7" exposure="0.9">
              <a href="${model.url}" target="_blank" rel="noreferrer">Open model</a>
            </model-viewer>`
          : `<p class="empty">Preview supports GLB/GLTF. This model is ${escapeHtml(model.type || "unknown")}.</p>`
      }
      <div class="model-actions">
        <a href="${model.url}" target="_blank" rel="noreferrer">Open model</a>
        ${model.remote_url ? `<a href="${model.remote_url}" target="_blank" rel="noreferrer">Source URL</a>` : ""}
      </div>
      <p class="detail-meta">${escapeHtml(model.name || model.file)}</p>
    </div>
  `;
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
  const stateJob = sample.ui_job?.job_id ? sample.ui_job : null;
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
      <div class="next-step-row">
        <button
          class="primary-inline-action"
          type="button"
          data-sample-id="${escapeHtml(sample.sample_id)}"
          data-sample-action="${escapeHtml(nextAction.action || "")}"
          ${nextAction.action ? "" : "disabled"}
        >
          ${escapeHtml(nextAction.label)}
        </button>
        <span>${escapeHtml(nextAction.detail)}</span>
      </div>
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
  const hasModel = Boolean(sample.model?.url);
  const hasBlenderFile = Boolean(sample.label_work_blend);
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
      detail: hasModel ? "GLB ready" : hasModelTask ? "Task submitted" : "Tripo generation",
      state: stepState("model", hasModel, hasRefs),
    },
    {
      key: "blender",
      title: "Blender file",
      detail: hasBlenderFile ? "Review file ready" : "Prep for annotator",
      state: stepState("blender", hasBlenderFile, hasModel),
    },
    {
      key: "skeleton",
      title: "Skeleton",
      detail: hasBlenderFile ? "Manual placement" : "Waiting on Blender file",
      state: hasBlenderFile ? "manual" : "blocked",
    },
  ];
}

function pipelineStep(step, index) {
  return `
    <div class="pipeline-step-wrap">
      ${index ? '<span class="pipeline-edge"></span>' : ""}
      <article class="pipeline-step step-${escapeHtml(step.state)}">
        <span class="step-state-dot" aria-hidden="true"></span>
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
  if (!hasReferenceSet(sample)) {
    return {
      action: "generate-reference",
      label: "Generate Reference Art",
      detail: "Creates front, left, right, and back views.",
    };
  }
  if (!sample.tripo_task_id && !sample.model?.url) {
    return {
      action: "submit-tripo",
      label: "Generate 3D Model",
      detail: "Submits the reference views to Tripo.",
    };
  }
  if (sample.tripo_task_id && !sample.model?.url) {
    return {
      action: "poll-tripo",
      label: "Check / Download Model",
      detail: "Polls the Tripo task and downloads the GLB when ready.",
    };
  }
  if (!sample.label_work_blend) {
    return {
      action: "prepare-label-work",
      label: "Prepare Blender File",
      detail: "Creates the annotator review file.",
    };
  }
  return {
    action: "",
    label: "Ready for Skeleton Placement",
    detail: "Open the Blender file and place the skeleton manually.",
  };
}

function renderSampleDetail() {
  const sample = sampleById(state.selectedSampleId) || state.samples[0];
  if (!sample) {
    elements.sampleDetail.innerHTML = '<p class="empty">Select a sample.</p>';
    return;
  }
  state.selectedSampleId = sample.sample_id;
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
    ${sampleActionPanel(sample)}
    ${modelPanel(sample)}
    ${gallery("Source References", sample.source_images, ["reference"])}
    ${gallery("OpenAI References", sample.reference_images, ["front", "left", "right", "back"])}
    ${gallery("Tripo Multiview", sample.multiview_images, ["front", "left", "right", "back"])}
    ${gallery("Blender Review Renders", sample.review_images, ["front", "left", "right", "rear", "top", "quarter"])}
    ${promptPanel(sample)}
  `;
}

function renderJobs() {
  if (!state.jobs.length) {
    elements.jobList.innerHTML = '<p class="empty">No UI jobs yet.</p>';
    return;
  }
  elements.jobList.innerHTML = state.jobs
    .map(
      (job) => `
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
      `,
    )
    .join("");
}

function samplePayload() {
  const formData = new FormData(elements.sampleForm);
  return {
    prompt: formData.get("prompt") || "",
    samplePrefix: formData.get("samplePrefix") || "sample",
    animalType: "unknown",
    morphologyType: formData.get("morphologyType") || "",
    armorState: formData.get("armorState") || "",
    variantTags: formData.getAll("variantTags"),
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
  elements.createSampleButton.disabled = true;
  elements.statusLine.textContent = "Creating sample";
  try {
    const result = await fetchJson("/api/samples", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(samplePayload()),
    });
    state.selectedSampleId = result.sample_id;
    await loadState();
    renderSampleDetail();
    switchView("sampleDetail");
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
    switchView("jobs");
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
    body: JSON.stringify({}),
  });
  state.selectedSampleId = sampleId;
  state.selectedJobId = job.job_id;
  await loadState();
  await loadJobLog(job.job_id);
  renderSampleDetail();
}

function switchView(viewName) {
  const activeTab = {
    batchDetail: "batches",
    sampleDetail: "samples",
  }[viewName] || viewName;
  document.querySelectorAll(".tab").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.view === activeTab);
  });
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("is-active", view.id === `${viewName}View`);
  });
}

function openSample(sampleId) {
  state.selectedSampleId = sampleId;
  renderSamples();
  renderSampleDetail();
  switchView("sampleDetail");
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-view]");
  if (!button) return;
  switchView(button.dataset.view);
});

elements.refreshButton.addEventListener("click", loadState);
elements.sampleMorphologySelect.addEventListener("change", renderBodyPlanExamples);
elements.sampleForm.addEventListener("submit", createSample);
elements.runForm.addEventListener("submit", startBatch);
elements.batchList.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-batch-id]");
  if (!button) return;
  state.selectedBatchId = button.dataset.batchId;
  renderBatches();
  renderBatchDetail();
  switchView("batchDetail");
});
elements.batchDetail.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-sample-id]");
  if (!button) return;
  openSample(button.dataset.sampleId);
});
elements.sampleList.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-sample-id]");
  if (!button) return;
  openSample(button.dataset.sampleId);
});
elements.sampleDetail.addEventListener("click", async (event) => {
  const actionButtonElement = event.target.closest("button[data-sample-action]");
  if (actionButtonElement) {
    actionButtonElement.disabled = true;
    try {
      await startSampleAction(actionButtonElement.dataset.sampleId, actionButtonElement.dataset.sampleAction);
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
  switchView("jobs");
});
elements.jobList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-job-id]");
  if (!button) return;
  await loadJobLog(button.dataset.jobId);
});

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
