(function () {
  const data = window.M2_DATA;
  if (!data) return;

  const $ = (id) => document.getElementById(id);
  const formatPrice = (value) => Number.isFinite(Number(value)) ? Number(value).toFixed(2) : "—";
  const formatPct = (value) => {
    if (!Number.isFinite(Number(value))) return "—";
    const number = Number(value);
    return `${number >= 0 ? "+" : "−"}${Math.abs(number).toFixed(2)}%`;
  };
  const distanceToPivot = (item) => {
    const price = Number.parseFloat(item.price);
    const pivot = Number(item.pivotPrice);
    if (!Number.isFinite(price) || !Number.isFinite(pivot) || price <= 0) return item.distance || "—";
    const distance = ((pivot - price) / price) * 100;
    return `${distance >= 0 ? "" : "−"}${Math.abs(distance).toFixed(2)}%`;
  };

  $("lastSync").textContent = `结构快照 ${data.asOf}`;
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

  const renderCandidates = () => {
    $("watchGrid").innerHTML = data.candidates.map((item) => `
    <article class="stock-card ${item.stateClass}">
      <div class="stock-card-head">
        <div class="stock-id"><span class="rank">0${item.priority}</span><div><h3>${item.name}</h3><small>${item.code} · ${item.sector}</small></div></div>
        <span class="state-chip ${item.stateClass}">${item.state}</span>
      </div>
      <div class="stock-price-row"><strong>${item.price}</strong><span class="change ${String(item.change).indexOf("−") === 0 || String(item.change).indexOf("-") === 0 ? "down" : "up"}">${item.change}</span><span class="stage-tag">${item.stage}</span></div>
      <div class="signal-row"><span>形态准备度</span><div class="signal-bar"><i style="width:${item.range}%"></i></div><b>${item.range}%</b></div>
      <div class="stock-metrics">
        <div><span>候选 Pivot</span><strong>${item.pivot}</strong></div>
        <div><span>距 Pivot</span><strong>${item.distance}</strong></div>
        <div><span>量比（结构快照）</span><strong>${item.volume}</strong><small>${item.volumeLabel}</small></div>
      </div>
      <div class="pivot-evidence">
        <div><span>为什么是这个突破点</span><strong>${item.pivotReason}</strong></div>
        <div><span>阶段证据</span><strong>${item.stageReason}</strong></div>
      </div>
      <div class="footprint-grid">
        <div><span>底部时间</span><strong>${item.baseAge}</strong></div>
        <div><span>收缩次数</span><strong>${item.contractions}</strong></div>
        <div><span>修正深度</span><strong>${item.correction}</strong></div>
      </div>
      <div class="structure-note"><span>收缩计数依据</span><strong>${item.contractionDetail}</strong><small>量能条件：${item.volumeRule}</small></div>
      <button class="chart-thumb" type="button" data-chart="${item.chart}" data-name="${item.name} ${item.code}">
        <img src="${item.chart}" alt="${item.name} 日K图" loading="lazy" />
        <span>查看高清日K图 <b>↗</b></span>
      </button>
      <div class="stock-action"><span class="action-mark">↳</span><p>${item.action}</p></div>
      <div class="stock-note">${item.note}</div>
    </article>
    `).join("");
  };

  renderCandidates();

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

  const syncLiveQuotes = async () => {
    const quoteSync = $("quoteSync");
    try {
      const response = await fetch("/api/m2-watchlist?force=1", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      const quotes = new Map((payload.quotes || []).map((quote) => [String(quote.code), quote]));
      let updated = 0;
      data.candidates.forEach((item) => {
        const quote = quotes.get(String(item.code));
        if (!quote) return;
        if (Number.isFinite(Number(quote.price))) item.price = formatPrice(quote.price);
        if (Number.isFinite(Number(quote.pct))) item.change = formatPct(quote.pct);
        item.distance = distanceToPivot(item);
        updated += 1;
      });
      renderCandidates();
      if (!updated) throw new Error("没有匹配到候选股报价");
      const focus = data.candidates.find((item) => item.name === data.decision.nextFocus);
      if (focus) {
        $("nextPivot").textContent = focus.pivot;
        $("nextDistance").textContent = focus.distance;
      }
      const stale = payload.sourceStatus === "stale";
      quoteSync.textContent = `${stale ? "个股行情沿用上次" : "个股行情已同步"} ${payload.generatedAt || ""}`;
      quoteSync.classList.toggle("stale", stale);
      quoteSync.classList.toggle("ready", !stale);
    } catch (error) {
      quoteSync.textContent = "个股行情同步失败，保留结构快照";
      quoteSync.classList.add("stale");
      console.warn("M2 live quote sync failed", error);
    }
  };

  syncLiveQuotes();
  window.setInterval(syncLiveQuotes, 5 * 60 * 1000);
})();
