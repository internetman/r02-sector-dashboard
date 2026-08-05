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
    const rawPivot = item.pivotPrice;
    if (rawPivot === null || rawPivot === undefined || rawPivot === "") return item.distance || "—";
    const pivot = Number(rawPivot);
    if (!Number.isFinite(price) || !Number.isFinite(pivot) || price <= 0) return item.distance || "—";
    const distance = ((pivot - price) / price) * 100;
    if (Math.abs(distance) < 0.01) return "已到达上沿";
    return distance > 0
      ? `距上沿 +${distance.toFixed(2)}%`
      : `已越过 ${Math.abs(distance).toFixed(2)}%`;
  };
  const historyCache = new Map();
  const escapeXml = (value) => String(value ?? "").replace(/[<>&'"]/g, (char) => ({"<":"&lt;",">":"&gt;","&":"&amp;","'":"&apos;","\"":"&quot;"}[char]));
  const finite = (value) => (value === null || value === undefined || value === "") ? null : (Number.isFinite(Number(value)) ? Number(value) : null);
  const chartPct = (value) => finite(value) === null ? "—" : `${finite(value) >= 0 ? "+" : "−"}${Math.abs(finite(value)).toFixed(1)}%`;
  const chartMetric = (item, kind, fallback) => {
    const metrics = historyCache.get(String(item.code))?.metrics;
    if (!metrics) return fallback;
    if (kind === "baseAge") return `${metrics.baseDays} 个交易日（算法）`;
    if (kind === "contractions") return `${metrics.contractionCount} 次（算法）`;
    if (kind === "correction") return finite(metrics.baseDepthPct) === null ? fallback : `${metrics.baseDepthPct.toFixed(1)}%（算法）`;
    if (kind === "contractionDetail") return `${metrics.vcpStatus}；需人工确认`;
    return fallback;
  };
  // The cards are rendered more than once (for example when a quote snapshot
  // arrives after the history snapshot). Keep the chart repaint hook alive so
  // a late card refresh cannot replace a loaded SVG with a loading placeholder.
  let renderDynamicCharts = () => {};
  const renderVcpChart = (container, history, item, large = false) => {
    if (!container) return;
    const rows = history?.rows || [];
    if (rows.length < 20) {
      container.innerHTML = `<div class="chart-loading">动态日K暂不可用<br /><small>不使用旧截图替代</small></div>`;
      return;
    }
    const width = large ? 1180 : 720;
    const height = large ? 500 : 220;
    const left = large ? 55 : 38;
    const right = large ? 58 : 42;
    const top = large ? 34 : 22;
    const priceHeight = large ? 300 : 122;
    const volumeTop = top + priceHeight + (large ? 38 : 26);
    const volumeHeight = large ? 90 : 30;
    const plotWidth = width - left - right;
    const plotBottom = volumeTop + volumeHeight;
    const n = rows.length;
    const x = (index) => left + (n <= 1 ? 0 : index / (n - 1)) * plotWidth;
    const priceValues = rows.flatMap((row) => [finite(row.high), finite(row.low), finite(row.ma50), finite(row.ma150), finite(row.ma200)]).filter((value) => value !== null);
    const pivot = finite(item.pivotPrice);
    if (pivot !== null) priceValues.push(pivot);
    const rawMin = Math.min(...priceValues);
    const rawMax = Math.max(...priceValues);
    const padding = Math.max((rawMax - rawMin) * 0.08, rawMax * 0.012);
    const minPrice = rawMin - padding;
    const maxPrice = rawMax + padding;
    const yPrice = (value) => top + (maxPrice - value) / (maxPrice - minPrice) * priceHeight;
    const maxVolume = Math.max(...rows.map((row) => finite(row.volume) || 0), 1);
    const yVolume = (value) => volumeTop + volumeHeight - (value / maxVolume) * volumeHeight;
    const candleWidth = Math.max(1, Math.min(7, plotWidth / n * 0.68));
    const grid = [0, 1, 2, 3].map((step) => {
      const value = maxPrice - (maxPrice - minPrice) * step / 3;
      const y = yPrice(value);
      return `<line x1="${left}" y1="${y.toFixed(1)}" x2="${width - right}" y2="${y.toFixed(1)}" class="chart-grid-line"/><text x="${width - right + 7}" y="${(y + 3).toFixed(1)}" class="chart-axis-label">${value.toFixed(2)}</text>`;
    }).join("");
    const candles = rows.map((row, index) => {
      const open = finite(row.open);
      const close = finite(row.close);
      const high = finite(row.high);
      const low = finite(row.low);
      if ([open, close, high, low].some((value) => value === null)) return "";
      const color = close >= open ? "#e87575" : "#5ac7a0";
      const candleX = x(index);
      const bodyY = Math.min(yPrice(open), yPrice(close));
      const bodyHeight = Math.max(1, Math.abs(yPrice(open) - yPrice(close)));
      return `<line x1="${candleX.toFixed(1)}" y1="${yPrice(high).toFixed(1)}" x2="${candleX.toFixed(1)}" y2="${yPrice(low).toFixed(1)}" stroke="${color}" stroke-width="1"/><rect x="${(candleX - candleWidth / 2).toFixed(1)}" y="${bodyY.toFixed(1)}" width="${candleWidth.toFixed(1)}" height="${bodyHeight.toFixed(1)}" fill="${color}" opacity=".9"/>`;
    }).join("");
    const volumes = rows.map((row, index) => {
      const volume = finite(row.volume);
      const open = finite(row.open);
      const close = finite(row.close);
      if (volume === null || open === null || close === null) return "";
      const color = close >= open ? "#e87575" : "#5ac7a0";
      const barHeight = Math.max(1, volumeTop + volumeHeight - yVolume(volume));
      return `<rect x="${(x(index) - candleWidth / 2).toFixed(1)}" y="${yVolume(volume).toFixed(1)}" width="${candleWidth.toFixed(1)}" height="${barHeight.toFixed(1)}" fill="${color}" opacity=".55"/>`;
    }).join("");
    const maLine = (key, color) => {
      const points = rows.map((row, index) => {
        const value = finite(row[key]);
        return value === null ? null : `${x(index).toFixed(1)},${yPrice(value).toFixed(1)}`;
      }).filter(Boolean);
      return points.length > 1 ? `<polyline points="${points.join(" ")}" fill="none" stroke="${color}" stroke-width="${large ? 1.8 : 1.1}" opacity=".95"/>` : "";
    };
    const contractionBoxes = (history.metrics?.contractions || []).map((box) => {
      const start = rows.findIndex((row) => row.date === box.startDate);
      const end = rows.findIndex((row) => row.date === box.endDate);
      if (start < 0 || end < 0) return "";
      const boxX = Math.max(left, x(start) - candleWidth);
      const boxWidth = Math.max(candleWidth * 2, x(end) - x(start) + candleWidth * 2);
      return `<rect x="${boxX.toFixed(1)}" y="${top}" width="${boxWidth.toFixed(1)}" height="${priceHeight}" class="contraction-box"/><text x="${(boxX + 4).toFixed(1)}" y="${(top + 13).toFixed(1)}" class="contraction-label">收缩 ${box.window}日</text>`;
    }).join("");
    const pivotLine = pivot === null ? `<text x="${left}" y="${(top - 6).toFixed(1)}" class="pivot-label">Pivot 待确认</text>` : `<line x1="${left}" y1="${yPrice(pivot).toFixed(1)}" x2="${width - right}" y2="${yPrice(pivot).toFixed(1)}" class="pivot-line"/><text x="${left + 5}" y="${(yPrice(pivot) - 5).toFixed(1)}" class="pivot-label">Pivot ${escapeXml(item.pivot)}</text>`;
    const labels = rows.filter((row, index) => index === 0 || index === rows.length - 1 || index % Math.max(1, Math.floor(rows.length / 5)) === 0).map((row) => {
      const index = rows.indexOf(row);
      return `<text x="${x(index).toFixed(1)}" y="${(plotBottom + 17).toFixed(1)}" class="chart-date-label" text-anchor="middle">${escapeXml(row.date.slice(5))}</text>`;
    }).join("");
    const metrics = history.metrics || {};
    const caption = `${metrics.vcpStatus || "VCP 动态扫描"} · 收缩 ${metrics.contractionCount ?? "—"} 次 · 量缩比 ${metrics.volumeDryUpRatio ?? "—"}`;
    container.innerHTML = `<svg class="vcp-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeXml(item.name)} 动态 VCP 日K图">
      <rect width="${width}" height="${height}" fill="#090f16"/>
      <text x="${left}" y="${(top - 8).toFixed(1)}" class="chart-title-label">${escapeXml(item.name)} · 动态复权日K · ${escapeXml(history.asOf || "")}</text>
      ${grid}
      <line x1="${left}" y1="${volumeTop - 10}" x2="${width - right}" y2="${volumeTop - 10}" class="chart-divider"/>
      ${contractionBoxes}${candles}${volumes}
      ${maLine("ma50", "#98e59b")}${maLine("ma150", "#86b8e7")}${maLine("ma200", "#e8c76d")}
      ${pivotLine}${labels}
      <text x="${left}" y="${(volumeTop - 16).toFixed(1)}" class="chart-legend"><tspan fill="#98e59b">MA50</tspan><tspan fill="#86b8e7"> · MA150</tspan><tspan fill="#e8c76d"> · MA200</tspan><tspan fill="#e87575"> · 上涨</tspan><tspan fill="#5ac7a0"> · 下跌</tspan></text>
    </svg><div class="dynamic-chart-caption">${escapeXml(caption)}</div>`;
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
      <div class="recommendation-band ${item.adviceClass || "wait"}"><span>M2 建议</span><strong>${item.advice || "等待进一步确认"}</strong><small>${item.adviceReason || "需结合 Pivot、收缩和突破量复核。"}</small></div>
      <div class="footprint-grid">
        <div><span>底部时间</span><strong>${chartMetric(item, "baseAge", item.baseAge)}</strong></div>
        <div><span>收缩次数</span><strong>${chartMetric(item, "contractions", item.contractions)}</strong></div>
        <div><span>修正深度</span><strong>${chartMetric(item, "correction", item.correction)}</strong></div>
      </div>
      <div class="structure-note"><span>VCP 动态扫描</span><strong>${chartMetric(item, "contractionDetail", item.contractionDetail)}</strong><small>量能条件：${item.volumeRule}</small></div>
      <button class="chart-thumb dynamic-chart-thumb" type="button" data-code="${item.code}" data-name="${item.name} ${item.code}">
        <div class="dynamic-chart-content"><div class="chart-loading">等待选股快照…</div></div>
        <span>动态 VCP 图 <b>↗</b></span>
      </button>
      <div class="stock-action"><span class="action-mark">↳</span><p>${item.action}</p></div>
      <div class="stock-note">${item.note}</div>
    </article>
    `).join("");
    renderDynamicCharts();
  };

  data.candidates.forEach((item) => {
    item.distance = distanceToPivot(item);
  });
  renderCandidates();

  $("changeLog").innerHTML = data.changes.length
    ? data.changes.map((change) => `<div class="log-item"><span class="log-time">${change.time}</span><p>${change.text}</p></div>`).join("")
    : `<div class="empty-log"><span class="empty-ring"></span><div><strong>今日无状态变化</strong><small>没有新的 B1 / B2，不制造交易信号。</small></div></div>`;

  const modal = $("chartModal");
  const modalChart = $("modalChart");
  const modalTitle = $("modalTitle");
  const closeModal = () => {
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
  };
  $("watchGrid").addEventListener("click", (event) => {
    const button = event.target.closest(".dynamic-chart-thumb");
    if (!button) return;
    const item = data.candidates.find((candidate) => String(candidate.code) === String(button.dataset.code));
    if (!item) return;
    modalTitle.textContent = button.dataset.name;
    renderVcpChart(modalChart, historyCache.get(String(item.code)), item, true);
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
  });
  modal.querySelector(".modal-backdrop").addEventListener("click", closeModal);
  modal.querySelector(".modal-close").addEventListener("click", closeModal);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeModal();
  });

  renderDynamicCharts = () => {
    data.candidates.forEach((item) => {
      const container = document.querySelector(`.dynamic-chart-thumb[data-code="${item.code}"] .dynamic-chart-content`);
      if (container) renderVcpChart(container, historyCache.get(String(item.code)), item);
    });
  };

  const syncHistory = async () => {
    const historySync = $("historySync");
    try {
      const response = await fetch("/api/m2-history?force=1", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      const entries = Object.entries(payload.history || {});
      entries.forEach(([code, history]) => historyCache.set(String(code), history));
      renderCandidates();
      renderDynamicCharts();
      if (!entries.length) throw new Error("没有历史日K数据");
      const stale = payload.sourceStatus === "stale" || payload.sourceStatus === "partial";
      historySync.textContent = `${stale ? "动态日K部分沿用" : "动态日K已同步"} ${entries.length}/${data.candidates.length} · ${payload.generatedAt || ""}`;
      historySync.classList.toggle("stale", stale);
      historySync.classList.toggle("ready", !stale);
    } catch (error) {
      historySync.textContent = "动态日K同步失败，未使用旧截图";
      historySync.classList.add("stale");
      renderDynamicCharts();
      console.warn("M2 history sync failed", error);
    }
  };

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

  const applySnapshot = (payload) => {
    const entries = Object.entries(payload.history || {});
    entries.forEach(([code, history]) => historyCache.set(String(code), history));
    const quotes = new Map((payload.quotes || []).map((quote) => [String(quote.code), quote]));
    data.candidates.forEach((item) => {
      const quote = quotes.get(String(item.code));
      if (!quote) return;
      if (Number.isFinite(Number(quote.price))) item.price = formatPrice(quote.price);
      if (Number.isFinite(Number(quote.pct))) item.change = formatPct(quote.pct);
      item.distance = distanceToPivot(item);
    });
    renderCandidates();
    return entries;
  };

  const displayTime = (value) => {
    const time = value ? new Date(value) : null;
    return time && !Number.isNaN(time.getTime())
      ? time.toLocaleString("zh-CN", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })
      : value || "—";
  };

  const syncSnapshot = async () => {
    const historySync = $("historySync");
    try {
      // The normal path is a static snapshot produced by the local Session.
      // This makes the page a display layer and avoids six cold-start requests
      // every time the page is opened.
      const response = await fetch(`/m2-snapshot.json?ts=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      const entries = applySnapshot(payload);
      if (!entries.length) throw new Error("选股快照没有历史日K");
      const generated = payload.generatedAt ? Date.parse(payload.generatedAt) : NaN;
      const ageHours = Number.isFinite(generated) ? Math.max(0, (Date.now() - generated) / 3600000) : null;
      const maxAgeHours = Number(payload.maxAgeHours || 36);
      const partial = payload.barStatus === "partial";
      const expired = payload.sourceStatus !== "live" || partial || (ageHours !== null && ageHours > maxAgeHours);
      $("lastSync").textContent = `选股快照 ${payload.asOf || data.asOf}`;
      $("quoteSync").textContent = `报价随快照 · ${displayTime(payload.generatedAt)}`;
      $("quoteSync").classList.toggle("stale", expired);
      $("quoteSync").classList.toggle("ready", !expired);
      const statusText = partial ? "选股日K盘中临时" : (expired ? "选股日K已过期" : "选股日K已就绪");
      historySync.textContent = `${statusText} ${payload.asOf || ""} · ${entries.length}/${data.candidates.length}`;
      historySync.classList.toggle("stale", expired);
      historySync.classList.toggle("ready", !expired);
    } catch (error) {
      // Keep an API fallback for development and for the first deployment
      // before the local Session has uploaded its first snapshot.
      try {
        await syncHistory();
        await syncLiveQuotes();
        historySync.textContent = "本地快照未就绪，临时读取数据源";
        historySync.classList.add("stale");
      } catch (fallbackError) {
        historySync.textContent = "选股快照读取失败";
        historySync.classList.add("stale");
        console.warn("M2 snapshot sync failed", error, fallbackError);
      }
    }
  };

  syncSnapshot();
  // A daily selection snapshot does not need intraday polling. This only lets
  // an already-open page notice a newly uploaded local Session snapshot.
  window.setInterval(syncSnapshot, 30 * 60 * 1000);
})();
