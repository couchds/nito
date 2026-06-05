const state = {
  catalog: { animals: [], specs: [] },
  samples: [],
  batchRuns: [],
  jobs: [],
  selectedJobId: "",
  selectedSampleId: "",
};

const elements = {
  statusLine: document.querySelector("#statusLine"),
  refreshButton: document.querySelector("#refreshButton"),
  runForm: document.querySelector("#runForm"),
  runButton: document.querySelector("#runButton"),
  animalSelect: document.querySelector("#animalSelect"),
  sampleCount: document.querySelector("#sampleCount"),
  runCount: document.querySelector("#runCount"),
  jobCount: document.querySelector("#jobCount"),
  catalogPath: document.querySelector("#catalogPath"),
  specGrid: document.querySelector("#specGrid"),
  runList: document.querySelector("#runList"),
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

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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
  state.batchRuns = data.batch_runs || [];
  state.jobs = data.jobs || [];
  render();
}

function render() {
  if (!state.selectedSampleId && state.samples.length) {
    state.selectedSampleId = state.samples[0].sample_id;
  }
  renderAnimals();
  elements.sampleCount.textContent = state.samples.length;
  elements.runCount.textContent = state.batchRuns.length;
  elements.jobCount.textContent = state.jobs.length;
  elements.catalogPath.textContent = state.catalog.path || "";
  elements.statusLine.textContent = `${state.samples.length} samples, ${state.jobs.length} UI jobs`;
  renderSpecs();
  renderRuns();
  renderSamples();
  renderSampleDetail();
  renderJobs();
}

function renderAnimals() {
  const current = elements.animalSelect.value || "all";
  const options = ['<option value="all">All animals</option>'];
  for (const animal of state.catalog.animals || []) {
    options.push(`<option value="${escapeHtml(animal)}">${escapeHtml(animal)}</option>`);
  }
  elements.animalSelect.innerHTML = options.join("");
  elements.animalSelect.value = [...elements.animalSelect.options].some((option) => option.value === current)
    ? current
    : "all";
}

function renderSpecs() {
  const specs = state.catalog.specs || [];
  if (!specs.length) {
    elements.specGrid.innerHTML = '<p class="empty">No prompt specs found.</p>';
    return;
  }
  elements.specGrid.innerHTML = specs
    .map(
      (spec) => `
        <article class="spec-card">
          <h3>${escapeHtml(spec.id)}</h3>
          <p>${escapeHtml(spec.animal_description)}</p>
          <div class="tag-row">
            ${tag(spec.animal_type)}
            ${tag(spec.morphology_type)}
            ${tag(spec.armor_state)}
            ${tag(spec.label_profile)}
          </div>
        </article>
      `,
    )
    .join("");
}

function renderRuns() {
  if (!state.batchRuns.length) {
    elements.runList.innerHTML = '<p class="empty">No batch runs yet.</p>';
    return;
  }
  elements.runList.innerHTML = state.batchRuns
    .slice(0, 8)
    .map((run) => {
      const failures = (run.samples || []).filter((sample) => sample.status === "failed").length;
      return `
        <article class="run-item">
          <div class="item-header">
            <h3>${escapeHtml(run.run_id)}</h3>
            ${tag(run.dry_run ? "dry_run" : failures ? "has_failures" : "completed")}
          </div>
          <p>${run.count} samples started ${formatTime(run.started_at)}</p>
          <div class="tag-row">
            ${tag(`${failures} failed`)}
            ${tag(run.finished_at ? "finished" : "open")}
          </div>
        </article>
      `;
    })
    .join("");
}

function renderSamples() {
  if (!state.samples.length) {
    elements.sampleList.innerHTML = '<p class="empty">No samples yet.</p>';
    elements.sampleDetail.innerHTML = '<p class="empty">No samples yet.</p>';
    return;
  }
  elements.sampleList.innerHTML = state.samples
    .map((sample) => {
      const preview = sample.thumbnail_url
        ? `<a class="sample-preview" href="${sample.thumbnail_url}" target="_blank" rel="noreferrer"><img src="${sample.thumbnail_url}" alt="${escapeHtml(sample.sample_id)} preview"></a>`
        : "";
      const isSelected = sample.sample_id === state.selectedSampleId;
      return `
        <article class="sample-item">
          <div class="sample-title-row">
            ${preview}
            <div>
              <div class="item-header">
                <h3>${escapeHtml(sample.sample_id)}</h3>
                ${tag(sample.status)}
              </div>
              <p>${escapeHtml(sample.animal_type)} / ${escapeHtml(sample.morphology_type)} / ${escapeHtml(sample.armor_state)}</p>
              <div class="tag-row">
                ${sample.face_limit ? tag(`${sample.face_limit} faces`) : ""}
                ${sample.model?.url ? tag("model") : ""}
                ${Object.keys(sample.reference_images || {}).length ? tag("reference") : ""}
                ${Object.keys(sample.multiview_images || {}).length ? tag("multiview") : ""}
                ${Object.keys(sample.review_images || {}).length ? tag("review") : ""}
              </div>
              <button type="button" data-sample-id="${escapeHtml(sample.sample_id)}">${isSelected ? "Selected" : "Preview"}</button>
            </div>
          </div>
        </article>
      `;
    })
    .join("");
}

function orderedEntries(images, preferredOrder) {
  const entries = [];
  const seen = new Set();
  for (const key of preferredOrder) {
    if (images?.[key]) {
      entries.push([key, images[key]]);
      seen.add(key);
    }
  }
  for (const entry of Object.entries(images || {})) {
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
    <h4>Prompts</h4>
    <div class="prompt-list">
      ${sample.prompt ? `<pre class="prompt-block">${escapeHtml(sample.prompt)}</pre>` : ""}
      ${entries
        .map(([label, prompt]) => `<pre class="prompt-block">${escapeHtml(label)}\n${escapeHtml(prompt)}</pre>`)
        .join("")}
    </div>
  `;
}

function renderSampleDetail() {
  const sample = state.samples.find((item) => item.sample_id === state.selectedSampleId) || state.samples[0];
  if (!sample) {
    elements.sampleDetail.innerHTML = '<p class="empty">Select a sample.</p>';
    return;
  }
  state.selectedSampleId = sample.sample_id;
  elements.sampleDetail.innerHTML = `
    <div class="item-header">
      <h3>${escapeHtml(sample.sample_id)}</h3>
      ${tag(sample.status)}
    </div>
    <p class="detail-meta">
      ${escapeHtml(sample.animal_type)} / ${escapeHtml(sample.morphology_type)} / ${escapeHtml(sample.armor_state || "no armor label")}
      ${sample.face_limit ? ` | ${escapeHtml(sample.face_limit)} faces` : ""}
    </p>
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

function formPayload() {
  const formData = new FormData(elements.runForm);
  return {
    count: Number(formData.get("count") || 1),
    samplePrefix: formData.get("samplePrefix") || "ui",
    seed: Number(formData.get("seed") || 0),
    animalType: formData.get("animalType") || "all",
    armorState: formData.get("armorState") || "all",
    faceLimitMin: Number(formData.get("faceLimitMin") || 3000),
    faceLimitMax: Number(formData.get("faceLimitMax") || 8000),
    dryRun: formData.get("dryRun") === "on",
    prepareLabelWork: formData.get("prepareLabelWork") === "on",
    continueOnError: formData.get("continueOnError") === "on",
  };
}

async function startBatch(event) {
  event.preventDefault();
  elements.runButton.disabled = true;
  elements.statusLine.textContent = "Starting job";
  try {
    const job = await fetchJson("/api/run-batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(formPayload()),
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
  document.querySelectorAll(".tab").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.view === viewName);
  });
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("is-active", view.id === `${viewName}View`);
  });
}

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => switchView(button.dataset.view));
});

elements.refreshButton.addEventListener("click", loadState);
elements.runForm.addEventListener("submit", startBatch);
elements.sampleList.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-sample-id]");
  if (!button) return;
  state.selectedSampleId = button.dataset.sampleId;
  renderSamples();
  renderSampleDetail();
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
