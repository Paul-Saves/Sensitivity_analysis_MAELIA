const form = document.getElementById("analysis-form");
const runButton = document.getElementById("run-button");
const statusBand = document.getElementById("status-band");
const statusIndicator = document.getElementById("status-indicator");
const summaryGrid = document.getElementById("summary-grid");
const targetTabs = document.getElementById("target-tabs");
const resultsPanel = document.getElementById("results-panel");

let currentManifest = null;
let currentTarget = null;

const targetLabels = {
  N_lixi: "Azote lixivié",
  dCorg: "Carbone organique",
  rdt: "Rendement",
};

const figureLabels = {
  anova_1factor_png: "ANOVA à un facteur",
  anova_2factor_interaction_png: "Interactions à deux facteurs",
  metamodel_performance_png: "Performance du métamodèle",
  sobol_total_png: "Sobol total",
  decision_tree_regions_png: "Régions sensibles",
  decision_tree_png: "Arbre complet",
};

function setStatus(kind, eyebrow, title, text) {
  const className = kind === "running" ? "running" : kind === "done" ? "done" : kind === "error" ? "error" : "";
  statusIndicator.className = `status-indicator ${className}`.trim();
  statusIndicator.textContent = kind === "running" ? "Analyse en cours" : kind === "done" ? "Terminé" : kind === "error" ? "À corriger" : "En attente";
  statusBand.querySelector(".eyebrow").textContent = eyebrow;
  statusBand.querySelector("h2").textContent = title;
  if (text) {
    statusBand.title = text;
  }
}

function showLoading() {
  resultsPanel.innerHTML = `
    <div class="loading-state">
      <div>
        <div class="spinner"></div>
        <h3>Analyse en cours</h3>
        <p>La pipeline entraîne les métamodèles, estime les indices et prépare les figures. Selon la taille du dataset, cela peut prendre un peu de temps.</p>
      </div>
    </div>`;
}

function showError(message) {
  resultsPanel.innerHTML = `
    <div class="error-state">
      <div>
        <div class="empty-visual"></div>
        <h3>Impossible de lancer l'analyse</h3>
        <p>${escapeHtml(message)}</p>
      </div>
    </div>`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function relativeAssetUrl(path) {
  if (!currentManifest || !path) return "";
  const outputDir = currentManifest.output_dir.replace(/\/$/, "");
  let relative = path;
  if (path.startsWith(outputDir)) {
    relative = path.slice(outputDir.length).replace(/^\//, "");
  }
  return `/analyses/${encodeURIComponent(currentManifest.run_id)}/${relative.split("/").map(encodeURIComponent).join("/")}`;
}

function collectPayload() {
  const data = new FormData(form);
  const targets = [...form.querySelectorAll('input[name="targets"]:checked')].map((item) => item.value);
  const payload = {
    log_dir: data.get("log_dir").trim(),
    dataset_path: data.get("dataset_path").trim() || null,
    targets: targets.length ? targets : null,
    n_bins: Number(data.get("n_bins")),
    sobol_n_mc: Number(data.get("sobol_n_mc")),
    tree_max_depth: Number(data.get("tree_max_depth")),
    random_state: Number(data.get("random_state")),
  };
  return payload;
}

function renderSummary(manifest) {
  const targetCount = Object.keys(manifest.targets || {}).length;
  summaryGrid.hidden = false;
  summaryGrid.innerHTML = `
    <div class="metric"><span>Simulations</span><strong>${manifest.n_rows.toLocaleString("fr-FR")}</strong></div>
    <div class="metric"><span>Paramètres</span><strong>${manifest.n_features}</strong></div>
    <div class="metric"><span>Sorties</span><strong>${targetCount}</strong></div>
    <div class="metric"><span>Run</span><strong>${escapeHtml(manifest.run_id.slice(-8))}</strong></div>`;
}

function renderTabs(manifest) {
  const targets = Object.keys(manifest.targets || {});
  targetTabs.hidden = targets.length === 0;
  targetTabs.innerHTML = targets.map((target) => `
    <button class="tab ${target === currentTarget ? "active" : ""}" data-target="${escapeHtml(target)}" type="button">
      ${escapeHtml(targetLabels[target] || target)}
    </button>`).join("");
  targetTabs.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      currentTarget = tab.dataset.target;
      renderTarget(currentTarget);
      renderTabs(currentManifest);
    });
  });
}

function scoreCard(label, value, className) {
  const numeric = Number(value);
  const rendered = Number.isFinite(numeric) ? numeric.toFixed(2) : "-";
  return `<div class="score ${className}"><span>${label}</span><strong>${rendered}</strong></div>`;
}

function figurePanel(artifacts, key, wide = false) {
  const path = artifacts[key];
  if (!path) return "";
  return `
    <section class="figure-panel ${wide ? "wide" : ""}">
      <h3>${figureLabels[key]}</h3>
      <img src="${relativeAssetUrl(path)}" alt="${figureLabels[key]}">
    </section>`;
}

function renderTarget(target) {
  if (!currentManifest || !currentManifest.targets[target]) return;
  const artifacts = currentManifest.targets[target];
  const metrics = artifacts.metamodel_metrics || {};
  const treeMetrics = artifacts.decision_tree_metrics || {};
  resultsPanel.innerHTML = `
    <div class="target-view">
      <div class="score-row">
        ${scoreCard("R² entraînement métamodèle", metrics.R2_train, "train")}
        ${scoreCard("Q² test métamodèle", metrics.Q2_test, "test")}
      </div>
      <div class="score-row">
        ${scoreCard("R² entraînement arbre", treeMetrics.R2_train, "train")}
        ${scoreCard("Q² test arbre", treeMetrics.Q2_test, "test")}
      </div>
      <div class="report-actions">
        <a class="link-button primary" href="/analyses/${encodeURIComponent(currentManifest.run_id)}/report" target="_blank" rel="noreferrer">Ouvrir le rapport complet</a>
        <a class="link-button" href="${relativeAssetUrl(artifacts.decision_tree_regions_csv)}" target="_blank" rel="noreferrer">Voir les régions CSV</a>
        <a class="link-button" href="${relativeAssetUrl(artifacts.decision_tree_rules_txt)}" target="_blank" rel="noreferrer">Voir les règles</a>
      </div>
      <div class="figure-grid">
        ${figurePanel(artifacts, "metamodel_performance_png")}
        ${figurePanel(artifacts, "sobol_total_png")}
        ${figurePanel(artifacts, "anova_1factor_png")}
        ${figurePanel(artifacts, "anova_2factor_interaction_png")}
        ${figurePanel(artifacts, "decision_tree_regions_png", true)}
        ${figurePanel(artifacts, "decision_tree_png", true)}
      </div>
    </div>`;
}

async function runAnalysis(event) {
  event.preventDefault();
  const payload = collectPayload();
  currentManifest = null;
  currentTarget = null;
  summaryGrid.hidden = true;
  targetTabs.hidden = true;
  runButton.disabled = true;
  runButton.innerHTML = '<span class="button-icon">…</span> Analyse en cours';
  setStatus("running", "Calcul", "La pipeline prépare les analyses et les visualisations.");
  showLoading();

  try {
    const response = await fetch("/analyses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (!response.ok) {
      throw new Error(body.detail || "Erreur inconnue pendant l'analyse.");
    }
    currentManifest = body;
    currentTarget = Object.keys(body.targets || {})[0];
    setStatus("done", "Résultats", `Analyse terminée : ${body.n_rows.toLocaleString("fr-FR")} simulations traitées.`);
    renderSummary(body);
    renderTabs(body);
    renderTarget(currentTarget);
  } catch (error) {
    setStatus("error", "Erreur", "L'analyse n'a pas pu être produite.");
    showError(error.message);
  } finally {
    runButton.disabled = false;
    runButton.innerHTML = '<span class="button-icon">▶</span> Lancer l\'analyse';
  }
}

form.addEventListener("submit", runAnalysis);
