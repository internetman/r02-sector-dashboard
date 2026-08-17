(function () {
  const data = window.M2_DATA;
  if (!data) return;

  const $ = (id) => document.getElementById(id);
  const formatPrice = (value) => Number.isFinite(Number(value)) ? Number(value).toFixed(2) : "—";
  const formatAmountYi = (value) => Number.isFinite(Number(value)) ? `${Number(value).toFixed(1)}亿` : "数据不足";
  const formatPlainPct = (value) => Number.isFinite(Number(value)) ? `${Number(value).toFixed(2)}%` : "盘中报价";
  const formatMarketCap = (value) => {
    const number = Number(value);
    if (!Number.isFinite(number)) return "市值 —";
    const yi = number / 100000000;
    return `市值 ${yi >= 1000 ? yi.toFixed(0) : yi.toFixed(1)}亿`;
  };
  const formatPe = (value) => {
    const number = Number(value);
    if (!Number.isFinite(number) || number === 0) return "PE —";
    if (number < 0) return "PE 亏损";
    return `PE ${number.toFixed(1)}`;
  };
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
  const bareCode = (value) => String(value || "").split(".")[0];
  const historyKey = (value) => bareCode(value);
  const marketBoard = (value) => {
    const code = bareCode(value);
    if (/^68[89]/.test(code)) return { label: "科创板", className: "sci" };
    if (/^30[01]/.test(code)) return { label: "创业板", className: "growth" };
    return { label: "普通A股", className: "main" };
  };
  const sectorMap = window.M2_SECTOR_MAP?.items || {};
  const valuationMap = window.M2_VALUATION_MAP?.items || {};
  const sectorInfo = (code) => sectorMap[code] || sectorMap[bareCode(code)] || {
    industry: "行业待补",
    region: "地域待补",
    concepts: [],
    sectorGroup: "其它主题",
  };
  const sectorClass = (value) => {
    const key = String(value || "");
    if (key.includes("半导体")) return "semi";
    if (key.includes("医药")) return "health";
    if (key.includes("资源")) return "resource";
    if (key.includes("新能源") || key.includes("光伏")) return "energy";
    if (key.includes("高端")) return "manufacture";
    if (key.includes("交通")) return "transport";
    if (key.includes("金融")) return "finance";
    if (key.includes("消费")) return "consumer";
    if (key.includes("化工")) return "chemical";
    return "other";
  };
  const sectorLabel = (code) => {
    const info = sectorInfo(code);
    return `${info.sectorGroup || "其它主题"} · ${info.industry || "行业待补"}`;
  };
  const valuationInfo = (code) => valuationMap[code] || valuationMap[bareCode(code)] || {};
  const filterValueFor = (item) => {
    const info = item.sectorInfo || sectorInfo(item.code);
    const board = item.marketBoard || marketBoard(item.code);
    return {
      sectorGroup: info.sectorGroup || "其它主题",
      industry: info.industry || "行业待补",
      board: board.label || "普通A股",
    };
  };
  const setHistory = (code, history) => historyCache.set(historyKey(code), history);
  const getHistory = (code) => historyCache.get(historyKey(code));
  const formatPivot = (value) => Number.isFinite(Number(value)) ? Number(value).toFixed(2) : "待确认";
  const starText = (value) => "★★★★★".slice(0, value) + "☆☆☆☆☆".slice(0, 5 - value);
  const setupRating = (row) => {
    if (row.executionRating) return row.executionRating;
    if (row.recommendationClass === "execute") {
      return { stars: 5, label: "5星 可执行", action: "规则化触发已满足；下单前复核止损、仓位和盘口成交。" };
    }
    if (row.recommendationClass === "priority") {
      return { stars: 4, label: "4星 确认中", action: "等收盘站稳 Pivot、明显放量、止损位明确后才可执行。" };
    }
    if (String(row.recommendation || "").includes("贴近 Pivot")) {
      return { stars: 3, label: "3星 重点盯", action: "接近触发区，等突破与量能；不提前买。" };
    }
    if (row.recommendationClass === "caution") {
      return { stars: 1, label: "1星 不追", action: "涨幅或均线偏离过高，等回踩或新平台。" };
    }
    if (row.recommendationClass === "review") {
      return { stars: 1, label: "1星 待复核", action: "旧观察池保留，先复核趋势和图形。" };
    }
    return { stars: row.currentQualified ? 2 : 1, label: row.currentQualified ? "2星 观察" : "1星 待复核", action: "记录观察，不是买点。" };
  };
  const ratingSortValue = (item) => {
    const stars = Number(item.executionStars || 0);
    const buyRank = Number(item.buyRank || 0);
    const change = Number.parseFloat(String(item.change || "").replace(/[+%]/g, "").replace("−", "-")) || 0;
    return stars * 1000000 + buyRank * 1000 + change;
  };
  const derivePivot = (history) => {
    const rows = (history?.rows || []).filter((row) => finite(row.high) !== null);
    if (!rows.length) return null;
    const contractionWindows = (history.metrics?.contractions || [])
      .map((item) => Number(item.window))
      .filter((value) => Number.isFinite(value) && value >= 5);
    const lookback = contractionWindows.length ? Math.min(...contractionWindows) : (rows.length >= 20 ? 20 : rows.length);
    const sample = rows.slice(-lookback);
    const highRow = sample.reduce((best, row) => finite(row.high) > finite(best.high) ? row : best, sample[0]);
    const pivot = finite(highRow.high);
    if (pivot === null) return null;
    return { price: pivot, date: highRow.date || "", lookback, asOf: history.asOf || rows[rows.length - 1]?.date || "" };
  };
  const applyPivotFromHistory = (item, history) => {
    const pivot = derivePivot(history);
    if (!pivot) return;
    item.pivotPrice = pivot.price;
    item.pivot = formatPivot(pivot.price);
    item.pivotStatus = `${pivot.lookback}日参考买点`;
    item.pivotReason = `参考 Pivot 买点取最近 ${pivot.lookback} 日最高价 ${item.pivot}（${pivot.date}）。只有收盘突破并明显放量才算触发；这里先作为观察上沿。`;
    item.volumeRule = `突破 ${item.pivot} 需明显放量`;
    item.distance = distanceToPivot(item);
  };
  const chartMetric = (item, kind, fallback) => {
    const metrics = getHistory(item.code)?.metrics;
    if (!metrics) return fallback;
    if (kind === "baseAge") return `${metrics.baseDays} 个交易日（算法）`;
    if (kind === "contractions") return `${metrics.contractionCount} 次（算法）`;
    if (kind === "correction") return finite(metrics.baseDepthPct) === null ? fallback : `${metrics.baseDepthPct.toFixed(1)}%（算法）`;
    if (kind === "contractionDetail") return `${metrics.vcpStatus}；需人工确认`;
    return fallback;
  };
  const tableRows = Array.isArray(window.M2_TABLE_DATA?.rows) ? window.M2_TABLE_DATA.rows : [];
  const selectionLabel = String(data.selectionAsOf || data.asOf || "当前快照")
    .replace(/^\d{4}-0?/, "")
    .replace(/ 收盘.*$/, " 收盘")
    .replace(/-0?/, "-");
  const previousCandidates = Array.isArray(data.candidates) ? data.candidates : [];
  const previousByCode = new Map(previousCandidates.map((item) => [bareCode(item.code), item]));
  const buildObservedCandidate = (row, index) => {
    const code = bareCode(row.code);
    const previous = previousByCode.get(code);
    if (previous) {
      return {
        ...previous,
        code,
        name: row.name || previous.name,
        marketBoard: marketBoard(row.code),
        sectorInfo: sectorInfo(row.code),
        marketCap: row.marketCap ?? valuationInfo(row.code).marketCap ?? previous.marketCap ?? null,
        peRatio: row.peRatio ?? valuationInfo(row.code).peRatio ?? previous.peRatio ?? null,
        price: formatPrice(row.price),
        change: formatPct(row.pct),
        stage: row.stageInference || previous.stage,
        state: row.status || previous.state,
        stateClass: row.recommendationClass === "review" ? "review" : "watch",
        sector: row.currentQualified ? sectorLabel(row.code) : `${sectorLabel(row.code)} / 待复核`,
        pivot: row.pivot || previous.pivot,
        pivotPrice: row.pivotPrice || previous.pivotPrice || null,
        pivotLocked: Boolean(row.pivotLocked || previous.pivotLocked),
        pivotStatus: row.pivotStatus || previous.pivotStatus || "待确认",
        pivotReason: row.pivotReason || previous.pivotReason,
        stageReason: row.currentQualified
          ? "当前仍通过 M2-01 观察资格；第二阶段、RS、VCP 和 Pivot 仍需历史 OHLCV / 图形复核。"
          : "历史已进入观察池；当前导出未确认继续合格，保留记录等待收盘或图形复核。",
        volume: formatAmountYi(row.quoteAmountYi),
        volumeLabel: `换手 ${formatPlainPct(row.quoteTurnover)} · 振幅 ${formatPlainPct(row.quoteAmplitude)}`,
        volumeRule: "突破日需明显放量",
        advice: row.recommendation || previous.advice,
        adviceClass: row.recommendationClass || previous.adviceClass,
        adviceReason: row.recommendationReason || previous.adviceReason,
        executionStars: setupRating(row).stars,
        executionLabel: setupRating(row).label,
        executionAction: setupRating(row).action,
        buyRank: row.buyRank || 0,
        action: row.currentQualified
          ? "继续观察；补 RS、历史 OHLCV、Pivot、收缩次数和突破量。未确认前不买。"
          : "保留记录待复核；若收盘后仍不满足趋势 / 位置 / 量价，再人工决定是否移出。",
        note: `${row.transition || "观察池记录"}；${selectionLabel} ${formatPct(row.pct)}，距 52 周高点 ${formatPct(row.fromHighPct)}，距 MA50 ${formatPct(row.priceToMa50Pct)}。`,
        baseAge: "待历史 OHLCV",
        contractions: row.contractions || "待确认",
        contractionDetail: "等待动态历史扫描；i问财导出未包含收缩次数。",
        correction: "待历史 OHLCV",
        priority: index + 1,
        rangeLabel: "形态准备度",
      };
    }
    const caution = row.recommendationClass === "caution";
    const avoid = row.recommendationClass === "avoid";
    return {
      code,
      name: row.name,
      marketBoard: marketBoard(row.code),
      sectorInfo: sectorInfo(row.code),
      marketCap: row.marketCap ?? valuationInfo(row.code).marketCap ?? null,
      peRatio: row.peRatio ?? valuationInfo(row.code).peRatio ?? null,
      sector: sectorLabel(row.code),
      state: row.status || "观察",
      stateClass: row.recommendationClass === "review" ? "review" : "watch",
      stage: row.stageInference || "阶段 2 初筛",
      price: formatPrice(row.price),
      change: formatPct(row.pct),
      volume: formatAmountYi(row.quoteAmountYi),
      volumeLabel: `换手 ${formatPlainPct(row.quoteTurnover)} · 振幅 ${formatPlainPct(row.quoteAmplitude)}`,
      pivot: "待确认",
      distance: "—",
      range: 18,
      rangeLabel: "证据完整度",
      pivotPrice: row.pivotPrice || null,
      pivotLocked: Boolean(row.pivotLocked),
      pivotStatus: row.pivotStatus || "待确认",
      pivotReason: row.pivotReason || "本次导入未包含 Pivot；需补充动态历史 OHLCV 后确认当前平台上沿。",
      stageReason: "均线与位置初筛通过；RS、平台持续时间、收缩顺序和突破量尚未补齐。",
      volumeRule: "突破日需明显放量",
      advice: row.recommendation || (caution ? "不追当日大涨" : avoid ? "等待回到强势区" : "待观察"),
      adviceClass: row.recommendationClass || "wait",
      adviceReason: row.recommendationReason || "趋势初筛通过，但还没有买点确认。",
      executionStars: setupRating(row).stars,
      executionLabel: setupRating(row).label,
      executionAction: setupRating(row).action,
      buyRank: row.buyRank || 0,
      action: row.currentQualified
        ? "补充历史 OHLCV、RS、Pivot、收缩次数和突破量；未确认前不买。"
        : "保留记录待复核；若收盘后仍不满足趋势 / 位置 / 量价，再人工决定是否移出。",
      note: row.transition || "本卡片代表进入 M2 观察阶段，不代表已经形成买点。",
      baseAge: "待历史 OHLCV",
      contractions: "未确认",
      contractionDetail: "等待动态历史扫描；i问财导出未包含收缩次数。",
      correction: "待历史 OHLCV",
      chart: null,
      priority: index + 1,
    };
  };
  if (tableRows.length) {
    data.candidates = tableRows
      .map(buildObservedCandidate)
      .sort((a, b) => ratingSortValue(b) - ratingSortValue(a))
      .map((item, index) => ({ ...item, priority: index + 1 }));
  }
  // The cards are rendered more than once (for example when the OHLCV snapshot
  // arrives after the import table). Keep the chart repaint hook alive so
  // a late card refresh cannot replace a loaded SVG with a loading placeholder.
  let renderDynamicCharts = () => {};
  const renderVcpChart = (container, history, item, large = false) => {
    if (!container) return;
    const rows = history?.rows || [];
    if (rows.length < 20) {
      container.innerHTML = `<div class="chart-loading">动态日K暂不可用<br /><small>本次仅完成趋势初筛，等待历史 OHLCV；不使用旧截图替代</small></div>`;
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
    const pivotLine = pivot === null ? `<text x="${left}" y="${(top - 6).toFixed(1)}" class="pivot-label">Pivot 待确认</text>` : `<line x1="${left}" y1="${yPrice(pivot).toFixed(1)}" x2="${width - right}" y2="${yPrice(pivot).toFixed(1)}" class="pivot-line"/><text x="${left + 5}" y="${(yPrice(pivot) - 5).toFixed(1)}" class="pivot-label">参考 Pivot ${escapeXml(item.pivot)}</text>`;
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

  $("lastSync").textContent = data.quoteGeneratedAt ? `监控报价 ${data.asOf}` : `结构快照 ${data.asOf}`;
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

  const homeCategoryFilter = $("homeCategoryFilter");
  const homeStarFilter = $("homeStarFilter");
  const itemStars = (item) => Number(item.executionStars || setupRating(item).stars || 0);
  const populateHomeFilter = () => {
    if (!homeCategoryFilter) return;
    const option = (kind, value) => `<option value="${kind}:${escapeXml(value)}">${escapeXml(value)}</option>`;
    const sectorGroups = [...new Set(data.candidates.map((item) => filterValueFor(item).sectorGroup))]
      .sort((a, b) => a.localeCompare(b, "zh-CN"));
    const industries = [...new Set(data.candidates.map((item) => filterValueFor(item).industry))]
      .filter((value) => value && value !== "行业待补")
      .sort((a, b) => a.localeCompare(b, "zh-CN"));
    homeCategoryFilter.innerHTML = `
      <option value="all">全部分类</option>
      <optgroup label="行业分类">
        ${sectorGroups.map((value) => option("sector", value)).join("")}
      </optgroup>
      <optgroup label="交易板块">
        ${["科创板", "创业板", "普通A股"].map((value) => option("board", value)).join("")}
      </optgroup>
      <optgroup label="所属行业">
        ${industries.map((value) => option("industry", value)).join("")}
      </optgroup>
    `;
  };
  const populateStarFilter = () => {
    if (!homeStarFilter) return;
    const ratingRows = [5, 4, 3, 2, 1]
      .map((stars) => {
        const count = data.candidates.filter((item) => itemStars(item) === stars).length;
        return { stars, count };
      })
      .filter((item) => item.count > 0);
    homeStarFilter.innerHTML = `<option value="all">全部星级</option>${ratingRows
      .map((item) => `<option value="${item.stars}">${item.stars}星 · ${item.count}只</option>`)
      .join("")}`;
  };
  const filteredCandidates = () => {
    const categoryValue = homeCategoryFilter?.value || "all";
    const starValue = homeStarFilter?.value || "all";
    const [kind, target] = categoryValue.split(":", 2);
    return data.candidates.filter((item) => {
      const fields = filterValueFor(item);
      const categoryMatch = categoryValue === "all"
        || (kind === "sector" && fields.sectorGroup === target)
        || (kind === "board" && fields.board === target)
        || (kind === "industry" && fields.industry === target);
      const starMatch = starValue === "all" || itemStars(item) === Number(starValue);
      return categoryMatch && starMatch;
    });
  };
  const renderCandidates = () => {
    const visibleCandidates = filteredCandidates();
    if ($("homeFilterCount")) {
      $("homeFilterCount").textContent = `${visibleCandidates.length} / ${data.candidates.length}`;
    }
    $("watchGrid").innerHTML = visibleCandidates.length ? visibleCandidates.map((item) => `
    <article class="stock-card ${item.stateClass}">
      <div class="stock-card-head">
        <div class="stock-id"><span class="rank">${String(item.priority).padStart(2, "0")}</span><div><div class="stock-title-line"><h3>${item.name}</h3><span class="board-chip board-${item.marketBoard?.className || "main"}">${item.marketBoard?.label || "普通A股"}</span></div><small>${item.code} · ${item.sector}</small><div class="card-sector-line"><span class="sector-chip sector-${sectorClass(item.sectorInfo?.sectorGroup)}">${item.sectorInfo?.sectorGroup || "其它主题"}</span>${(item.sectorInfo?.concepts || []).slice(0, 2).map((concept) => `<i>${concept}</i>`).join("")}</div></div></div>
        <div class="card-badges">
          <span class="rating-badge stars-${item.executionStars || 2}"><b>${starText(item.executionStars || 2)}</b><small>${item.executionLabel || "2星 观察"}</small></span>
          <span class="state-chip ${item.stateClass}">${item.state}</span>
        </div>
      </div>
      <div class="stock-price-row"><strong>${item.price}</strong><span class="change ${String(item.change).indexOf("−") === 0 || String(item.change).indexOf("-") === 0 ? "down" : "up"}">${item.change}</span><span class="stage-tag">${item.stage}</span></div>
      <div class="pivot-focus ${item.pivotPrice ? "ready" : "pending"}">
        <span>参考 PIVOT 买点 / 平台上沿</span>
        <strong>${item.pivot}</strong>
        <small>${item.pivotStatus || "等待静态日K快照"} · ${item.distance || "—"}</small>
      </div>
      <div class="signal-row"><span>${item.rangeLabel || "形态准备度"}</span><div class="signal-bar"><i style="width:${item.range}%"></i></div><b>${item.range}%</b></div>
      <div class="stock-metrics">
        <div><span>Pivot 状态</span><strong>${item.pivotStatus || "待确认"}</strong></div>
        <div><span>距 Pivot</span><strong>${item.distance}</strong></div>
        <div><span>市值 / PE</span><strong>${formatMarketCap(item.marketCap)}</strong><small>${formatPe(item.peRatio)}</small></div>
        <div><span>成交额 / 换手</span><strong>${item.volume}</strong><small>${item.volumeLabel}</small></div>
      </div>
      <div class="pivot-evidence">
        <div><span>为什么是这个突破点</span><strong>${item.pivotReason}</strong></div>
        <div><span>阶段证据</span><strong>${item.stageReason}</strong></div>
      </div>
      <div class="recommendation-band ${item.adviceClass || "wait"}"><span>M2 建议</span><strong>${item.advice || "等待进一步确认"}</strong><small>${item.adviceReason || "需结合 Pivot、收缩和突破量复核。"}</small><em>${starText(item.executionStars || 2)} ${item.executionLabel || "2星 观察"} · ${item.executionAction || "记录观察，不是买点。"}</em></div>
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
    `).join("") : `<div class="empty-filter-state"><strong>当前筛选没有候选</strong><small>换一个分类或星级继续看，或回到全部。</small></div>`;
    renderDynamicCharts();
  };

  populateHomeFilter();
  populateStarFilter();
  [homeCategoryFilter, homeStarFilter].forEach((control) => control?.addEventListener("input", renderCandidates));
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
    const item = data.candidates.find((candidate) => historyKey(candidate.code) === historyKey(button.dataset.code));
    if (!item) return;
    modalTitle.textContent = button.dataset.name;
    renderVcpChart(modalChart, getHistory(item.code), item, true);
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
      if (container) renderVcpChart(container, getHistory(item.code), item);
    });
  };

  const applySnapshot = (payload) => {
    const allEntries = Object.entries(payload.history || {});
    const candidateCodes = new Set(data.candidates.map((item) => bareCode(item.code)));
    const entries = allEntries.filter(([code]) => candidateCodes.has(bareCode(code)));
    allEntries.forEach(([code, history]) => setHistory(code, history));
    data.candidates.forEach((item) => {
      if (!item.pivotLocked) applyPivotFromHistory(item, getHistory(item.code));
      item.distance = distanceToPivot(item);
    });
    const focus = data.candidates.find((item) => item.name === data.decision.nextFocus) || data.candidates[0];
    if (focus) {
      $("nextPivot").textContent = focus.pivot || "待确认";
      $("nextDistance").textContent = focus.distance || "—";
    }
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
      // This makes the page a display layer and avoids one cold-start request
      // per candidate every time the page is opened.
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
      $("lastSync").textContent = data.quoteGeneratedAt ? `监控报价 ${data.asOf}` : `选股快照 ${payload.asOf || data.asOf}`;
      $("quoteSync").textContent = `图形快照 · ${displayTime(payload.generatedAt)}`;
      $("quoteSync").classList.toggle("stale", expired);
      $("quoteSync").classList.toggle("ready", !expired);
      const statusText = partial ? "选股日K盘中临时" : (expired ? "选股日K已过期" : "选股日K已就绪");
      historySync.textContent = `${statusText} ${payload.asOf || ""} · ${entries.length}/${data.candidates.length}`;
      historySync.classList.toggle("stale", expired);
      historySync.classList.toggle("ready", !expired);
    } catch (error) {
      historySync.textContent = "选股快照读取失败，等待本地刷新";
      historySync.classList.add("stale");
      console.warn("M2 snapshot sync failed", error);
    }
  };

  syncSnapshot();
  // A daily selection snapshot does not need intraday polling. This only lets
  // an already-open page notice a newly uploaded local Session snapshot.
  window.setInterval(syncSnapshot, 30 * 60 * 1000);
})();
