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
  elements.statusLine.textContent = `${state.batches.length} batches, ${state.samples.length} samples, ${state.jobs.length} UI jobs`;
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
          <p>${formatTime(job.started_at)} | return code ${job.returncode ?? "pending"}</p>
          <div class="tag-row">
            ${tag(job.payload?.dryRun ? "dry_run" : "live")}
            ${tag(`${job.payload?.count ?? "?"} samples`)}
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
