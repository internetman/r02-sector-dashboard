(function () {
  const data = window.M2_DATA;
  if (!data) return;

  const $ = (id) => document.getElementById(id);

  $("lastSync").textContent = `数据截至 ${data.asOf}`;
  $("marketStatus").textContent = data.market.status;
  $("marketNote").textContent = data.market.note;
  $("marketStats").innerHTML = data.market.stats.map((item) => `
    <div class="market-stat"><span>${item.label}</span><strong>${item.value}</strong></div>
  `).join("");

  $("decisionTitle").textContent = data.decision.title;
  $("decisionText").textContent = data.decision.text;
  $("nextFocus").textContent = data.decision.nextFocus;
  $("nextPivot").textContent = data.decision.pivot;
  $("nextDistance").textContent = data.decision.distance;
  $("watchCount").textContent = String(data.candidates.length).padStart(2, "0");
  $("watchTrack").style.width = `${Math.min(100, data.candidates.length * 12)}%`;
  $("changeCount").textContent = String(data.changes.length).padStart(2, "0");
  $("changeNote").textContent = data.changes.length ? "状态正在变化" : "今日无状态变化";

  $("watchGrid").innerHTML = data.candidates.map((item) => `
    <article class="stock-card ${item.stateClass}">
      <div class="stock-card-head">
        <div class="stock-id"><span class="rank">0${item.priority}</span><div><h3>${item.name}</h3><small>${item.code} · ${item.sector}</small></div></div>
        <span class="state-chip ${item.stateClass}">${item.state}</span>
      </div>
      <div class="stock-price-row"><strong>${item.price}</strong><span class="change ${item.change.indexOf("−") === 0 ? "down" : "up"}">${item.change}</span><span class="stage-tag">${item.stage}</span></div>
      <div class="signal-row"><span>形态准备度</span><div class="signal-bar"><i style="width:${item.range}%"></i></div><b>${item.range}%</b></div>
      <div class="stock-metrics">
        <div><span>候选 Pivot</span><strong>${item.pivot}</strong></div>
        <div><span>距 Pivot</span><strong>${item.distance}</strong></div>
        <div><span>量比</span><strong>${item.volume}</strong><small>${item.volumeLabel}</small></div>
      </div>
      <div class="footprint-grid">
        <div><span>底部时间</span><strong>${item.baseAge}</strong></div>
        <div><span>收缩次数</span><strong>${item.contractions}</strong></div>
        <div><span>修正深度</span><strong>${item.correction}</strong></div>
      </div>
      <button class="chart-thumb" type="button" data-chart="${item.chart}" data-name="${item.name} ${item.code}">
        <img src="${item.chart}" alt="${item.name} 日K图" loading="lazy" />
        <span>查看高清日K图 <b>↗</b></span>
      </button>
      <div class="stock-action"><span class="action-mark">↳</span><p>${item.action}</p></div>
      <div class="stock-note">${item.note}</div>
    </article>
  `).join("");

  $("changeLog").innerHTML = data.changes.length
    ? data.changes.map((change) => `<div class="log-item"><span class="log-time">${change.time}</span><p>${change.text}</p></div>`).join("")
    : `<div class="empty-log"><span class="empty-ring"></span><div><strong>今日无状态变化</strong><small>没有新的 B1 / B2，不制造交易信号。</small></div></div>`;

  const modal = $("chartModal");
  const modalImage = $("modalImage");
  const modalTitle = $("modalTitle");
  const modalOpenOriginal = $("modalOpenOriginal");
  const closeModal = () => {
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
  };
  document.querySelectorAll(".chart-thumb").forEach((button) => {
    button.addEventListener("click", () => {
      modalImage.src = button.dataset.chart;
      modalImage.alt = `${button.dataset.name} 日K图`;
      modalTitle.textContent = button.dataset.name;
      modalOpenOriginal.href = button.dataset.chart;
      modal.classList.add("open");
      modal.setAttribute("aria-hidden", "false");
    });
  });
  modal.querySelector(".modal-backdrop").addEventListener("click", closeModal);
  modal.querySelector(".modal-close").addEventListener("click", closeModal);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeModal();
  });
})();
