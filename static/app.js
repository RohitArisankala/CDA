const form = document.getElementById("researchForm");
const submitButton = document.getElementById("submitButton");
const stagesContainer = document.getElementById("stages");
const reportsList = document.getElementById("reportsList");
const jobSummary = document.getElementById("jobSummary");
const jobResult = document.getElementById("jobResult");
const jobError = document.getElementById("jobError");
const downloadCard = document.getElementById("downloadCard");
const reportCount = document.getElementById("reportCount");
const locationInput = form.elements.location;
const titleInput = form.elements.title;

let currentJobId = null;
let pollTimer = null;

locationInput.addEventListener("input", () => {
  const value = locationInput.value.trim();
  if (value && (!titleInput.value || titleInput.value.startsWith("Pharmacy Companies In "))) {
    titleInput.value = `Pharmacy Companies In ${value}`;
  }
});

function renderStages(stages = []) {
  stagesContainer.innerHTML = "";
  stages.forEach((stage, index) => {
    const card = document.createElement("div");
    card.className = `stage-card ${stage.status}`;
    card.innerHTML = `
      <div class="stage-index">${index + 1}</div>
      <div>
        <div class="stage-head">
          <h3>${stage.label}</h3>
          <span class="status-pill ${stage.status}">${stage.status}</span>
        </div>
        <p class="stage-message">${stage.message}</p>
      </div>
    `;
    stagesContainer.appendChild(card);
  });
}

function renderReports(reports) {
  reportCount.textContent = reports.length;
  if (!reports.length) {
    reportsList.innerHTML = '<div class="empty-state">No Word reports yet. Run your first research job to create one.</div>';
    return;
  }

  reportsList.innerHTML = "";
  reports.forEach((report) => {
    const card = document.createElement("div");
    card.className = "report-card";
    card.innerHTML = `
      <div>
        <h3 class="report-title">${report.title}</h3>
        <p class="report-meta">${report.modified_at.replace("T", " ")} · ${report.size_kb} KB</p>
      </div>
      <div class="report-actions">
        <span class="report-badge">.docx</span>
        <a class="secondary-btn" href="/downloads/${encodeURIComponent(report.filename)}">Download File</a>
      </div>
    `;
    reportsList.appendChild(card);
  });
}

async function loadReports() {
  const response = await fetch("/api/reports");
  const data = await response.json();
  renderReports(data.reports || []);
}

function setJobState(job) {
  renderStages(job.stages || []);
  jobSummary.textContent = `${job.title} · Live search`;

  if (job.status === "completed" && job.report) {
    jobResult.classList.remove("hidden");
    jobResult.innerHTML = `Search complete for <strong>${job.location || job.report.query}</strong>. The Word output file is ready with <strong>${job.report.company_count}</strong> companies.`;
    downloadCard.classList.remove("hidden");
    downloadCard.innerHTML = `
      <div>
        <h3 class="download-title">${job.report.filename}</h3>
        <p class="download-meta">Generated ${job.report.generated_at.replace("T", " ")} for location: ${job.report.query}</p>
      </div>
      <a class="download-btn" href="/downloads/${encodeURIComponent(job.report.filename)}">Download Word File</a>
    `;
    jobError.classList.add("hidden");
    submitButton.disabled = false;
    submitButton.textContent = "Start Searching";
  } else if (job.status === "failed") {
    jobError.classList.remove("hidden");
    jobError.textContent = job.error || "The job failed.";
    jobResult.classList.add("hidden");
    downloadCard.classList.add("hidden");
    submitButton.disabled = false;
    submitButton.textContent = "Start Searching";
  } else {
    jobResult.classList.add("hidden");
    downloadCard.classList.add("hidden");
    jobError.classList.add("hidden");
  }
}

async function pollJob(jobId) {
  const response = await fetch(`/api/jobs/${jobId}`);
  const job = await response.json();
  setJobState(job);

  if (job.status === "completed" || job.status === "failed") {
    clearInterval(pollTimer);
    pollTimer = null;
    await loadReports();
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(form);
  const payload = Object.fromEntries(formData.entries());
  payload.max_results = Number(payload.max_results);

  submitButton.disabled = true;
  submitButton.textContent = "Searching...";
  jobSummary.textContent = "Starting location-based pharmacy search...";
  jobResult.classList.add("hidden");
  jobError.classList.add("hidden");
  downloadCard.classList.add("hidden");

  const response = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const job = await response.json();

  if (!response.ok) {
    submitButton.disabled = false;
    submitButton.textContent = "Start Searching";
    jobError.classList.remove("hidden");
    jobError.textContent = job.error || "Unable to start the research job.";
    return;
  }

  currentJobId = job.id;
  setJobState(job);

  if (pollTimer) {
    clearInterval(pollTimer);
  }
  pollTimer = setInterval(() => pollJob(currentJobId), 1200);
});

renderStages([
  { label: "Search Companies", status: "pending", message: "Waiting to start." },
  { label: "Research Details", status: "pending", message: "Waiting to start." },
  { label: "Clean And Merge", status: "pending", message: "Waiting to start." },
  { label: "Generate Word File", status: "pending", message: "Waiting to start." },
  { label: "Ready To Download", status: "pending", message: "Waiting to start." },
]);

loadReports();
