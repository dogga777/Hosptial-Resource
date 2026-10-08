const $ = (id) => document.getElementById(id);

let hospitals = [];
let recommendations = new Map();
let completedTransfers = [];
let refreshInProgress = false;

async function api(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.text();
    let detail = body;
    try {
      detail = JSON.parse(body).detail || body;
    } catch {
      detail = body;
    }
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return response.json();
}

function escapeHTML(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function formatNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? new Intl.NumberFormat().format(number) : "—";
}

function hours(value) {
  const number = Number(value);
  return value == null || !Number.isFinite(number) ? "No shortage" : `${number.toFixed(1)} hrs`;
}

function setStatus(message, state = "connected") {
  const status = $("status");
  status.className = `status status--${state}`;
  status.querySelector(".status-text").textContent = message;
}

function setTableMessage(message = "") {
  const element = $("tableMessage");
  element.textContent = message;
  element.hidden = !message;
}

function renderSummary(summary) {
  $("hospitalCount").textContent = formatNumber(summary.hospital_count);
  $("stockTotal").textContent = formatNumber(summary.total_stock);
  $("criticalCount").textContent = formatNumber(summary.critical_count);
  $("highCount").textContent = formatNumber(summary.high_count);
  $("hospitalCountLabel").textContent = `${formatNumber(summary.hospital_count)} hospitals`;
}

function renderNetworkScene() {
  const scene = $("networkScene");
  const coordinates = [
    [54, 50], [96, 167], [151, 19], [276, 24], [345, 93], [289, 184],
  ];
  const displayed = hospitals.slice(0, coordinates.length);
  const positions = new Map();

  displayed.forEach((hospital, index) => {
    positions.set(String(hospital.hospital_name ?? ""), coordinates[index]);
  });

  const lines = displayed.map((_, index) => {
    const [x, y] = coordinates[index];
    return `<line x1="200" y1="108" x2="${x}" y2="${y}"></line>`;
  });

  const transfer = [...recommendations.values()][0] ?? completedTransfers[0];
  const donorPosition = positions.get(String(transfer?.from_hospital ?? ""));
  const receiverPosition = positions.get(String(transfer?.to_hospital ?? ""));
  if (donorPosition && receiverPosition) {
    lines.push(
      `<line class="is-transfer" x1="${donorPosition[0]}" y1="${donorPosition[1]}" x2="${receiverPosition[0]}" y2="${receiverPosition[1]}"></line>`,
    );
  }

  const nodes = displayed.map((hospital, index) => {
    const [x, y] = coordinates[index];
    const risk = ["critical", "high", "medium", "low"].includes(hospital.risk)
      ? hospital.risk
      : "low";
    const name = String(hospital.hospital_name ?? "Hospital");
    return `
      <div class="network-node network-node--${risk}" style="left:${x / 4}%;top:${y / 2.2}%;--node-depth:${18 + index * 3}px;--float-delay:${index * -0.45}s">
        <span class="network-node__beacon"></span>
        <span class="network-node__copy"><span class="network-node__name">${escapeHTML(name)}</span><span class="network-node__stock"><b>${escapeHTML(formatNumber(hospital.stock))}</b> cylinders</span></span>
        <span class="network-node__rank">${String(index + 1).padStart(2, "0")}</span>
      </div>
    `;
  }).join("");
  const remaining = Math.max(0, hospitals.length - displayed.length);

  scene.querySelector(".network-links").innerHTML = lines.join("");
  scene.querySelector(".network-nodes").innerHTML = `${nodes}${remaining ? `<span class="network-overflow">+${remaining} more</span>` : ""}`;
  scene.setAttribute(
    "aria-label",
    `3D view of ${hospitals.length} hospitals in the connected network${transfer ? `, with a suggested transfer from ${transfer.from_hospital} to ${transfer.to_hospital}` : ""}`,
  );
}

function renderHospitals() {
  const search = $("hospitalSearch").value.trim().toLowerCase();
  const riskFilter = $("riskFilter").value;
  const visibleHospitals = hospitals.filter((hospital) => {
    const name = String(hospital.hospital_name ?? "").toLowerCase();
    const district = String(hospital.district ?? "").toLowerCase();
    return (!search || name.includes(search) || district.includes(search))
      && (riskFilter === "all" || hospital.risk === riskFilter);
  });

  if (hospitals.length === 0) {
    $("hospitalTable").innerHTML = '<tr><td class="loading-cell" colspan="8">No hospital data is available yet. Seed the demo to get started.</td></tr>';
    return;
  }

  if (visibleHospitals.length === 0) {
    $("hospitalTable").innerHTML = '<tr><td class="loading-cell" colspan="8">No hospitals match these filters.</td></tr>';
    return;
  }

  $("hospitalTable").innerHTML = visibleHospitals.map((hospital) => {
    const name = String(hospital.hospital_name ?? "Unknown");
    const district = String(hospital.district ?? "—");
    const risk = ["critical", "high", "medium", "low"].includes(hospital.risk)
      ? hospital.risk
      : "low";
    const stock = Number(hospital.stock);
    const stockNumber = Number.isFinite(stock) ? stock : 0;
    const consumption = Number(hospital.consumption_rate);
    const consumptionNumber = Number.isFinite(consumption) ? consumption : 0;
    const buffer = stockNumber + consumptionNumber * 24;
    const stockPercent = buffer > 0 ? Math.max(0, Math.min(100, (stockNumber / buffer) * 100)) : 0;
    const timeClass = risk === "critical" ? "time-value--critical" : risk === "high" ? "time-value--high" : "";
    const forecast = Number(hospital.forecast_24h);
    const confidence = Number(hospital.confidence);
    const accuracy = hospital.holdout?.accuracy_percent;
    const initials = name.split(/\s+/).map((part) => part[0]).slice(0, 2).join("").toUpperCase();

    return `
      <tr>
        <td>
          <div class="hospital-cell">
            <span class="hospital-avatar" aria-hidden="true">${escapeHTML(initials)}</span>
            <span><span class="hospital-name">${escapeHTML(name)}</span><br><span class="hospital-district">${escapeHTML(district)}</span></span>
          </div>
        </td>
        <td><span class="stock-value">${formatNumber(stockNumber)}</span><div class="stock-bar ${stockPercent < 25 ? "stock-bar--low" : ""}" aria-label="${Math.round(stockPercent)} percent stock buffer"><span style="width:${stockPercent}%"></span></div></td>
        <td>${formatNumber(consumptionNumber)} <span class="hospital-district">cyl/hr</span></td>
        <td><span class="time-value ${timeClass}">${escapeHTML(hours(hospital.time_to_shortage_hours))}</span></td>
        <td class="${Number.isFinite(forecast) && forecast < 0 ? "forecast-negative" : ""}">${Number.isFinite(forecast) ? formatNumber(forecast) : "—"}</td>
        <td><span class="risk risk--${risk}">${escapeHTML(risk)}</span></td>
        <td><span class="confidence-value">${Number.isFinite(confidence) ? `${formatNumber(confidence)}%` : "—"}</span><div class="confidence-track"><span style="width:${Number.isFinite(confidence) ? Math.max(0, Math.min(100, confidence)) : 0}%"></span></div></td>
        <td><span class="holdout-value">${accuracy == null ? "—" : `${escapeHTML(formatNumber(accuracy))}%`}</span></td>
      </tr>
    `;
  }).join("");
}

function renderRecommendations(items, transfers, uncoveredShortages) {
  recommendations = new Map(items.map((recommendation) => [String(recommendation.priority), recommendation]));
  completedTransfers = transfers;
  $("recommendationCount").textContent = formatNumber(transfers.length + items.length + uncoveredShortages.length);

  const completedMarkup = transfers.map((transfer) => `
    <article class="transfer transfer--complete">
      <div class="transfer-top">
        <h3>${escapeHTML(transfer.from_hospital)} <span aria-hidden="true">→</span> ${escapeHTML(transfer.to_hospital)}</h3>
        <span class="transfer-status">Simulated transfer complete</span>
      </div>
      <p class="transfer-route">
        <span><b>${formatNumber(transfer.quantity)}</b> cylinders moved</span>
        <span>${escapeHTML(transfer.distance_km)} km</span>
        <span>ETA <b>${escapeHTML(transfer.eta_hours)} hrs</b></span>
      </p>
      <p class="transfer-reason">${escapeHTML(transfer.reason)}</p>
    </article>
  `).join("");
  const recommendationsMarkup = items.map((recommendation) => {
    const priority = String(recommendation.priority ?? "—");
    return `
      <article class="transfer">
        <div class="transfer-top">
          <h3>${escapeHTML(recommendation.from_hospital)} <span aria-hidden="true">→</span> ${escapeHTML(recommendation.to_hospital)}</h3>
          <span class="transfer-status transfer-status--ready">Ready to transfer</span>
        </div>
        <p class="transfer-route">
          <span><b>${formatNumber(recommendation.quantity)}</b> cylinders</span>
          <span>${escapeHTML(recommendation.distance_km)} km</span>
          <span>ETA <b>${escapeHTML(recommendation.eta_hours)} hrs</b></span>
        </p>
        <p class="transfer-reason">${escapeHTML(recommendation.reason)}</p>
        <button class="explain-button" type="button" data-explain="${escapeHTML(priority)}">Explain detected need <span aria-hidden="true">→</span></button>
        <p class="explanation" data-explanation="${escapeHTML(priority)}" hidden></p>
      </article>
    `;
  }).join("");
  const uncoveredMarkup = uncoveredShortages.map((shortage) => `
    <article class="transfer transfer--unserved">
      <div class="transfer-top">
        <h3>${escapeHTML(shortage.hospital_name)}</h3>
        <span class="transfer-status transfer-status--unserved">No safe donor</span>
      </div>
      <p class="transfer-reason">Only ${escapeHTML(shortage.hours_remaining)} hours of oxygen remain, but no donor can transfer stock and keep its 12-hour safety reserve.</p>
    </article>
  `).join("");

  if (transfers.length === 0 && items.length === 0 && uncoveredShortages.length === 0) {
    $("recommendations").innerHTML = `
      <div class="empty-state"><span class="empty-icon" aria-hidden="true">✓</span><p>No shortage needs a transfer right now.</p></div>
    `;
    return;
  }

  $("recommendations").innerHTML = `<div class="transfer-list">${completedMarkup}${recommendationsMarkup}${uncoveredMarkup}</div>`;
}

function render(data) {
  hospitals = Array.isArray(data.hospitals) ? data.hospitals : [];
  renderSummary(data.summary ?? {});
  renderHospitals();
  renderRecommendations(
    Array.isArray(data.recommendations) ? data.recommendations : [],
    Array.isArray(data.transfers) ? data.transfers : [],
    Array.isArray(data.uncovered_shortages) ? data.uncovered_shortages : [],
  );
  renderNetworkScene();

  const timestamp = new Date(data.generated_at);
  $("lastUpdated").textContent = Number.isNaN(timestamp.getTime())
    ? "Just now"
    : timestamp.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
  setTableMessage();
  setStatus("Network connected");
}

async function refresh() {
  if (refreshInProgress) return;
  refreshInProgress = true;
  try {
    render(await api("/api/dashboard"));
  } catch (error) {
    setStatus("Connection issue", "error");
    const detail = String(error.message || "Unknown network error").slice(0, 220);
    setTableMessage(`Could not refresh hospital data: ${detail} Check the backend and database connection, then try again.`);
    console.error("Dashboard refresh failed:", error);
    if (hospitals.length === 0) {
      $("hospitalTable").innerHTML = '<tr><td class="loading-cell" colspan="8">Unable to load data. Check the backend connection or seed the demo.</td></tr>';
      $("recommendations").innerHTML = '<div class="empty-state"><span class="empty-icon" aria-hidden="true">!</span><p>Recommendations are unavailable until the network reconnects.</p></div>';
    }
  } finally {
    refreshInProgress = false;
  }
}

async function explainRecommendation(button) {
  const priority = button.dataset.explain;
  const recommendation = recommendations.get(priority);
  const target = document.querySelector(`[data-explanation="${CSS.escape(priority)}"]`);
  if (!recommendation || !target) return;

  button.disabled = true;
  button.textContent = "Preparing explanation…";
  target.hidden = true;

  try {
    const data = await api("/api/gemini/explain", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ recommendation }),
    });
    target.textContent = data.explanation || "No explanation was returned.";
    target.hidden = false;
    button.textContent = "Hide explanation ↑";
    button.dataset.explained = "true";
  } catch (error) {
    target.textContent = "Could not generate an explanation. Please try again.";
    target.hidden = false;
    button.textContent = "Try explanation again →";
    button.dataset.explained = "false";
    console.error("Recommendation explanation failed:", error);
  } finally {
    button.disabled = false;
  }
}

async function runAction(button, url, label) {
  const originalLabel = button.dataset.label;
  button.disabled = true;
  button.textContent = `${label}…`;
  try {
    const result = await api(url, { method: "POST" });
    await refresh();
    const transferred = Array.isArray(result.transfers) ? result.transfers : [];
    if (transferred.length > 0) {
      const message = transferred.map((transfer) =>
        `${transfer.quantity} cylinders moved from ${transfer.from_hospital} to ${transfer.to_hospital}`,
      ).join("; ");
      setStatus(`${transferred.length} transfer${transferred.length === 1 ? "" : "s"} completed`);
      setTableMessage(`Simulated transfer complete: ${message}.`);
    } else if (url === "/api/auto-transfer") {
      setStatus("No transfer needed");
      setTableMessage(result.message || "No shortage with a safe donor surplus was detected.");
    }
  } catch (error) {
    setStatus("Action failed", "error");
    setTableMessage(`${label} failed. Check the backend/database connection and try again.`);
    console.error(`${label} failed:`, error);
  } finally {
    button.disabled = false;
    button.innerHTML = originalLabel;
  }
}

$("hospitalSearch").addEventListener("input", renderHospitals);
$("riskFilter").addEventListener("change", renderHospitals);
$("networkScene").addEventListener("pointermove", (event) => {
  if (event.pointerType !== "mouse" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const bounds = event.currentTarget.getBoundingClientRect();
  const x = (event.clientX - bounds.left) / bounds.width - 0.5;
  const y = (event.clientY - bounds.top) / bounds.height - 0.5;
  event.currentTarget.style.setProperty("--scene-rotate-y", `${x * 8}deg`);
  event.currentTarget.style.setProperty("--scene-rotate-x", `${y * -6}deg`);
});
$("networkScene").addEventListener("pointerleave", (event) => {
  event.currentTarget.style.setProperty("--scene-rotate-x", "0deg");
  event.currentTarget.style.setProperty("--scene-rotate-y", "0deg");
});
$("recommendations").addEventListener("click", (event) => {
  const button = event.target.closest("[data-explain]");
  if (!button) return;
  if (button.dataset.explained === "true") {
    const target = document.querySelector(`[data-explanation="${CSS.escape(button.dataset.explain)}"]`);
    target.hidden = !target.hidden;
    button.textContent = target.hidden ? "Show explanation →" : "Hide explanation ↑";
    return;
  }
  explainRecommendation(button);
});

const seedButton = $("seedBtn");
seedButton.dataset.label = seedButton.innerHTML;
seedButton.addEventListener("click", () => runAction(seedButton, "/api/seed", "Seeding demo"));

const simulateButton = $("simulateBtn");
simulateButton.dataset.label = simulateButton.innerHTML;
simulateButton.addEventListener("click", () => runAction(simulateButton, "/api/simulate", "Simulating"));

const transferButton = $("transferBtn");
transferButton.dataset.label = transferButton.innerHTML;
transferButton.addEventListener("click", () => runAction(transferButton, "/api/auto-transfer", "Detecting"));

refresh();
setInterval(refresh, 5000);
