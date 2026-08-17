(function () {
  const data = window.M2_TABLE_DATA;
  if (!data) return;

  const $ = (id) => document.getElementById(id);
  const pct = (value) => {
    if (!Number.isFinite(Number(value))) return "—";
    const n = Number(value);
    return `${n >= 0 ? "+" : "−"}${Math.abs(n).toFixed(1)}%`;
  };
  const plainPct = (value) => Number.isFinite(Number(value)) ? `${Number(value).toFixed(2)}%` : "—";
  const price = (value) => Number.isFinite(Number(value)) ? Number(value).toFixed(2) : "—";
  const amountYi = (value) => Number.isFinite(Number(value)) ? (Number(value) / 100000000).toFixed(1) : "—";
  const pe = (value) => {
    const n = Number(value);
    if (!Number.isFinite(n) || n === 0) return "—";
    if (n < 0) return "亏损";
    return n.toFixed(1);
  };
  const count = (value) => Number.isFinite(Number(value)) ? Number(value).toLocaleString("zh-CN") : "—";
  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
  const bareCode = (value) => String(value || "").split(".")[0];
  const marketBoard = (value) => {
    const code = bareCode(value);
    if (/^68[89]/.test(code)) return { label: "科创板", className: "sci" };
    if (/^30[01]/.test(code)) return { label: "创业板", className: "growth" };
    return { label: "普通A股", className: "main" };
  };
  const sectorMap = window.M2_SECTOR_MAP?.items || {};
  const valuationMap = window.M2_VALUATION_MAP?.items || {};
  const valuationInfo = (row) => valuationMap[row.code] || valuationMap[bareCode(row.code)] || {};
  const sectorInfo = (row) => sectorMap[row.code] || sectorMap[bareCode(row.code)] || {
    industry: "行业待补",
    region: "地域待补",
    concepts: [],
    sectorGroup: "其它主题",
  };
  const sectorSearchText = (row) => {
    const info = sectorInfo(row);
    return `${info.sectorGroup || ""} ${info.industry || ""} ${info.region || ""} ${(info.concepts || []).join(" ")}`;
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
  const renderSectorTags = (row) => {
    const info = sectorInfo(row);
    const concepts = (info.concepts || []).slice(0, 3);
    return `<div class="sector-stack"><div class="sector-line"><span class="sector-chip sector-${sectorClass(info.sectorGroup)}">${info.sectorGroup || "其它主题"}</span><strong>${info.industry || "行业待补"}</strong></div>${concepts.length ? `<div class="concept-line">${concepts.map((item) => `<span>${item}</span>`).join("")}</div>` : ""}</div>`;
  };
  const finite = (value) => (value === null || value === undefined || value === "") ? null : (Number.isFinite(Number(value)) ? Number(value) : null);
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
  const starSortValue = (row) => setupRating(row).stars * 1000000 + Number(row.buyRank || 0) * 1000 + Number(row.pct || 0);
  const pivotDistance = (row, pivot) => {
    const current = finite(row.price);
    if (current === null || !pivot) return "—";
    const distance = (pivot - current) / current * 100;
    if (Math.abs(distance) < 0.01) return "已到上沿";
    return distance > 0 ? `距上沿 +${distance.toFixed(1)}%` : `已越过 ${Math.abs(distance).toFixed(1)}%`;
  };
  const derivePivot = (history) => {
    const rows = (history?.rows || []).filter((item) => finite(item.high) !== null);
    if (!rows.length) return null;
    const contractionWindows = (history.metrics?.contractions || [])
      .map((item) => Number(item.window))
      .filter((value) => Number.isFinite(value) && value >= 5);
    const lookback = contractionWindows.length ? Math.min(...contractionWindows) : (rows.length >= 20 ? 20 : rows.length);
    const sample = rows.slice(-lookback);
    const highRow = sample.reduce((best, item) => finite(item.high) > finite(best.high) ? item : best, sample[0]);
    const pivot = finite(highRow.high);
    if (pivot === null) return null;
    return { price: pivot, date: highRow.date || "", lookback };
  };
  const applySnapshotPivot = (payload) => {
    const history = payload.history || {};
    data.rows.forEach((row) => {
      if (row.pivotLocked) return;
      const itemHistory = history[bareCode(row.code)] || history[row.code];
      const pivot = derivePivot(itemHistory);
      if (!pivot) return;
      row.pivotPrice = pivot.price;
      row.pivot = formatPivot(pivot.price);
      row.pivotStatus = `${pivot.lookback}日参考买点`;
      row.pivotDistance = pivotDistance(row, pivot.price);
      row.pivotReason = `参考 Pivot 买点取最近 ${pivot.lookback} 日最高价 ${row.pivot}（${pivot.date}）；收盘突破并明显放量才算触发。`;
      const countValue = itemHistory?.metrics?.contractionCount;
      if (Number.isFinite(Number(countValue))) row.contractions = `${countValue} 次`;
      row.dataQuality = `${row.pivotStatus}已补；仍缺 RS 与人工图形确认`;
    });
  };

  $("tableAsOf").textContent = data.quoteGeneratedAt ? `监控报价 ${data.asOf}` : `导入快照 ${data.asOf}`;
  $("tableSource").textContent = data.source;
  $("summaryQualifiedLabel").textContent = `${data.selectionAsOf}仍过硬条件`;
  $("deductionAsOf").textContent = data.selectionAsOf;
  $("flowCurrentLabel").textContent = `02 / ${data.closeLabel || "收盘"}`;
  $("periodLabel").textContent = data.periodLabel || "近 20 日";
  $("summaryTotal").textContent = data.rowCount;
  $("summaryStacked").textContent = data.currentQualifiedCount || data.rows.filter((row) => row.currentQualified).length;
  $("summaryAbove200").textContent = data.rows.filter((row) => setupRating(row).stars >= 5).length;
  $("summaryNearHigh").textContent = data.nearPivotCount || 0;
  $("summaryUp").textContent = data.upCount ?? data.rows.filter((row) => row.currentQualified && row.pct > 0).length;

  const populateSectorFilter = () => {
    const select = $("sectorFilter");
    if (!select) return;
    const groups = [...new Set(data.rows.map((row) => sectorInfo(row).sectorGroup || "其它主题"))].sort((a, b) => a.localeCompare(b, "zh-CN"));
    select.innerHTML = `<option value="all">全部板块</option>${groups.map((group) => `<option value="${group}">${group}</option>`).join("")}`;
  };
  populateSectorFilter();

  const renderAnalysis = () => {
    const nearHigh = data.rows.filter((row) => row.fromHighPct >= -10).length;
    $("flowTotal").textContent = data.priorCloseQualified || "—";
    $("flowStacked").textContent = data.importedCount || "—";
    $("flowAbove200").textContent = data.currentQualifiedCount || "—";
    $("flowNearHigh").textContent = data.newSinceClose || 0;
    $("flowPriority").textContent = data.rowCount;
    $("flowConfirmed").textContent = data.rows.filter((row) => !Number.isFinite(Number(row.rsRank))).length;

    const adviceRows = [
      { label: "5星 可执行", key: "star5", color: "priority" },
      { label: "4星 确认中", key: "star4", color: "priority" },
      { label: "3星 重点盯", key: "star3", color: "wait" },
      { label: "待观察", key: "wait", color: "wait" },
      { label: "过热不追，保留观察", key: "caution", color: "caution" },
      { label: "待复核观察", key: "review", color: "review" },
    ].map((item) => ({
      ...item,
      value: data.rows.filter((row) => {
        const rating = setupRating(row);
        if (item.key === "star5") return rating.stars >= 5;
        if (item.key === "star4") return rating.stars === 4;
        if (item.key === "star3") return rating.stars === 3;
        return row.recommendationClass === item.key;
      }).length,
    }));
    const maxAdvice = Math.max(1, ...adviceRows.map((item) => item.value));
    $("adviceChart").innerHTML = adviceRows.map((item) => `
      <div class="bar-row"><span>${item.label}</span><div class="bar-track"><i class="${item.color}" style="width:${Math.max(4, item.value / maxAdvice * 100)}%"></i></div><strong>${item.value}</strong></div>
    `).join("");

    const highRows = data.rows.filter((row) => Number.isFinite(Number(row.fromHighPct))).sort((a, b) => b.fromHighPct - a.fromHighPct).slice(0, 7);
    $("highChart").innerHTML = highRows.map((row) => {
      const position = clamp(100 + Number(row.fromHighPct), 3, 100);
      return `<div class="bar-row"><span>${row.name}</span><div class="bar-track"><i class="near" style="width:${position}%"></i></div><strong>${pct(row.fromHighPct)}</strong></div>`;
    }).join("");

    const maRows = data.rows.filter((row) => Number.isFinite(Number(row.priceToMa200Pct))).sort((a, b) => b.priceToMa200Pct - a.priceToMa200Pct).slice(0, 7);
    const maxMa = Math.max(1, ...maRows.map((row) => Number(row.priceToMa200Pct)));
    $("maChart").innerHTML = maRows.map((row) => `
      <div class="bar-row"><span>${row.name}</span><div class="bar-track"><i class="ma" style="width:${clamp(Number(row.priceToMa200Pct) / maxMa * 100, 4, 100)}%"></i></div><strong>${pct(row.priceToMa200Pct)}</strong></div>
    `).join("");
  };

  renderAnalysis();

  const getRows = () => {
    const query = $("tableSearch").value.trim().toLowerCase();
    const filter = $("tableFilter").value;
    const sectorFilter = $("sectorFilter")?.value || "all";
    const sort = $("tableSort").value;
    const rows = data.rows.filter((row) => {
      const board = marketBoard(row.code).label;
      const info = sectorInfo(row);
      const matchesSearch = !query || `${row.code} ${row.name} ${board} ${sectorSearchText(row)}`.toLowerCase().includes(query);
      const matchesSector = sectorFilter === "all" || info.sectorGroup === sectorFilter;
      const matchesFilter = filter === "all"
        || (filter === "stacked" && row.maStacked)
        || (filter === "nearHigh" && row.fromHighPct >= -10)
        || (filter === "caution" && row.recommendationClass === "caution")
        || (filter === "star5" && setupRating(row).stars >= 5)
        || (filter === "star4" && setupRating(row).stars === 4)
        || (filter === "star3" && setupRating(row).stars === 3)
        || (filter === "priority" && ["execute", "priority"].includes(row.recommendationClass))
        || (filter === "wait" && row.recommendationClass === "wait")
        || (filter === "review" && row.recommendationClass === "review")
        || filter === "needsPivot";
      return matchesSearch && matchesSector && matchesFilter;
    });
    const valueOf = (row) => ({
      stars: starSortValue(row),
      pct: row.pct,
      fromHigh: row.fromHighPct,
      fromLow: row.fromLowPct,
      amount: row.avgAmount,
      marketCap: row.marketCap ?? valuationInfo(row).marketCap,
      pe: row.peRatio ?? valuationInfo(row).peRatio,
      price: row.price,
    }[sort]);
    return rows.sort((a, b) => Number(valueOf(b) ?? -Infinity) - Number(valueOf(a) ?? -Infinity));
  };

  const cleanText = (value) => String(value ?? "").replace(/\s+/g, " ").trim();
  const markdownCell = (value) => cleanText(value).replace(/\|/g, "/") || "—";
  const csvCell = (value) => {
    const text = cleanText(value);
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  const exportStamp = () => (data.asOf || "m2").replace(/[^\d]+/g, "-").replace(/^-|-$/g, "") || "m2";
  const portableRows = (rows) => rows.map((row, index) => ({
    rank: index + 1,
    code: row.code,
    name: row.name,
    marketBoard: marketBoard(row.code).label,
    marketBoardClass: marketBoard(row.code).className,
    sectorGroup: sectorInfo(row).sectorGroup,
    industry: sectorInfo(row).industry,
    region: sectorInfo(row).region,
    concepts: sectorInfo(row).concepts || [],
    exchange: row.exchange,
    sourceDate: row.quoteAsOf || row.dataAsOf,
    observationDate: row.dataAsOf,
    currentQualified: Boolean(row.currentQualified),
    status: row.status,
    setupStars: setupRating(row).stars,
    setupRating: setupRating(row).label,
    setupAction: setupRating(row).action,
    recommendation: row.recommendation,
    recommendationClass: row.recommendationClass,
    recommendationReason: row.recommendationReason,
    price: finite(row.price),
    pct: finite(row.pct),
    ma50: finite(row.ma50),
    ma150: finite(row.ma150),
    ma200: finite(row.ma200),
    maStacked: Boolean(row.maStacked),
    aboveMa50: Boolean(row.aboveMa50),
    priceToMa50Pct: finite(row.priceToMa50Pct),
    priceToMa200Pct: finite(row.priceToMa200Pct),
    ma50ToMa150Pct: finite(row.ma50ToMa150Pct),
    ma150ToMa200Pct: finite(row.ma150ToMa200Pct),
    periodPct: finite(row.periodPct),
    fromHighPct: finite(row.fromHighPct),
    fromLowPct: finite(row.fromLowPct),
    avgAmount: finite(row.avgAmount),
    marketCapYi: Number.isFinite(Number(row.marketCap ?? valuationInfo(row).marketCap)) ? Number((Number(row.marketCap ?? valuationInfo(row).marketCap) / 100000000).toFixed(2)) : null,
    peRatio: finite(row.peRatio ?? valuationInfo(row).peRatio),
    pbRatio: finite(row.pbRatio ?? valuationInfo(row).pbRatio),
    floatMarketCapYi: Number.isFinite(Number(row.floatMarketCap ?? valuationInfo(row).floatMarketCap)) ? Number((Number(row.floatMarketCap ?? valuationInfo(row).floatMarketCap) / 100000000).toFixed(2)) : null,
    quoteAmountYi: finite(row.quoteAmountYi),
    quoteTurnover: finite(row.quoteTurnover),
    quoteAmplitude: finite(row.quoteAmplitude),
    quoteVolumeLots: finite(row.quoteVolumeLots),
    pivot: row.pivot,
    pivotPrice: finite(row.pivotPrice),
    pivotStatus: row.pivotStatus,
    pivotDistance: row.pivotDistance,
    pivotReason: row.pivotReason,
    contractions: row.contractions,
    dataQuality: row.dataQuality,
    transition: row.transition,
  }));
  const exportColumns = [
    ["#", (row) => row.rank],
    ["代码", (row) => row.code],
    ["名称", (row) => row.name],
    ["交易板块", (row) => row.marketBoard],
    ["板块分类", (row) => row.sectorGroup],
    ["所属行业", (row) => row.industry],
    ["概念标签", (row) => (row.concepts || []).join(" / ")],
    ["星级", (row) => `${starText(row.setupStars)} ${row.setupRating}`],
    ["状态", (row) => row.status],
    ["建议", (row) => row.recommendation],
    ["现价", (row) => price(row.price)],
    ["涨跌", (row) => pct(row.pct)],
    ["成交额亿", (row) => row.quoteAmountYi ?? "—"],
    ["换手", (row) => plainPct(row.quoteTurnover)],
    ["振幅", (row) => plainPct(row.quoteAmplitude)],
    ["参考Pivot", (row) => row.pivot],
    ["距Pivot", (row) => row.pivotDistance],
    ["收缩", (row) => row.contractions],
    ["MA50", (row) => price(row.ma50)],
    ["MA150", (row) => price(row.ma150)],
    ["MA200", (row) => price(row.ma200)],
    ["均线结构", (row) => row.maStacked && row.aboveMa50 ? "多头通过" : "待复核"],
    ["距MA50", (row) => pct(row.priceToMa50Pct)],
    ["距MA200", (row) => pct(row.priceToMa200Pct)],
    ["阶段涨幅", (row) => pct(row.periodPct)],
    ["距区间高点", (row) => pct(row.fromHighPct)],
    ["从低点反弹", (row) => pct(row.fromLowPct)],
    ["均额", (row) => count(row.avgAmount)],
    ["市值亿元", (row) => row.marketCapYi ?? "—"],
    ["PE动态", (row) => pe(row.peRatio)],
    ["流通市值亿元", (row) => row.floatMarketCapYi ?? "—"],
    ["报价时点", (row) => row.sourceDate],
    ["观察来源", (row) => row.observationDate],
    ["备注", (row) => `${row.transition || ""} ${row.recommendationReason || ""}`],
  ];
  const markdownExport = (rows) => {
    const portable = portableRows(rows);
    const header = exportColumns.map(([label]) => label);
    const body = portable.map((row) => exportColumns.map(([, value]) => markdownCell(value(row))));
    return [
      `# M2 待观察股票池导出 - ${data.asOf}`,
      "",
      `数据源：${data.source}`,
      data.quoteGeneratedAt ? `行情抓取：${data.quoteGeneratedAt}` : "",
      `导出范围：当前筛选视图 ${rows.length} 行 / 全观察池 ${data.rowCount} 行。`,
      `统计：当前合格 ${data.currentQualifiedCount}；5星可执行 ${data.rows.filter((row) => setupRating(row).stars >= 5).length}；4星确认中 ${data.rows.filter((row) => setupRating(row).stars === 4).length}；3星重点盯 ${data.rows.filter((row) => setupRating(row).stars === 3).length}；盘中上涨 ${data.upCount || 0}。`,
      "",
      "星级说明：5星才代表可执行下单；4星只是进入触发区、必须等收盘确认；3星是重点盯盘；2星普通观察；1星不追或待复核。参考 Pivot 不是买入指令，真正买点仍需 RS、VCP 收缩、收盘突破、明显放量、止损和仓位确认。",
      "",
      `| ${header.join(" | ")} |`,
      `| ${header.map(() => "---").join(" | ")} |`,
      ...body.map((values) => `| ${values.join(" | ")} |`),
      "",
    ].join("\n");
  };
  const csvExport = (rows) => {
    const portable = portableRows(rows);
    const header = exportColumns.map(([label]) => csvCell(label)).join(",");
    const body = portable.map((row) => exportColumns.map(([, value]) => csvCell(value(row))).join(","));
    return [header, ...body].join("\n");
  };
  const jsonExport = (rows) => JSON.stringify({
    asOf: data.asOf,
    source: data.source,
    selectionAsOf: data.selectionAsOf,
    snapshotAsOf: data.snapshotAsOf,
    quoteGeneratedAt: data.quoteGeneratedAt,
    quoteSource: data.quoteSource,
    quoteSourceStatus: data.quoteSourceStatus,
    rowCount: data.rowCount,
    exportedCount: rows.length,
    currentQualifiedCount: data.currentQualifiedCount,
    newSinceClose: data.newSinceClose,
    carryForwardCount: data.carryForwardCount,
    caution: "5星才代表可执行下单；4星只是进入触发区、必须等收盘确认；参考 Pivot 不是买入指令。",
    rows: portableRows(rows),
  }, null, 2);
  const downloadText = (filename, mime, text) => {
    const blob = new Blob([text], { type: `${mime};charset=utf-8` });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };
  const copyText = async (text) => {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  };
  const setExportStatus = (message) => {
    $("exportStatus").textContent = message;
    window.clearTimeout(setExportStatus.timer);
    setExportStatus.timer = window.setTimeout(() => {
      $("exportStatus").textContent = "导出当前视图";
    }, 2600);
  };
  $("copyMarkdown").addEventListener("click", async () => {
    const rows = getRows();
    try {
      await copyText(markdownExport(rows));
      setExportStatus(`已复制 ${rows.length} 行`);
    } catch (error) {
      console.warn("Markdown export copy failed", error);
      downloadText(`m2-watchlist-${exportStamp()}.md`, "text/markdown", markdownExport(rows));
      setExportStatus(`已下载 ${rows.length} 行`);
    }
  });
  $("downloadCsv").addEventListener("click", () => {
    const rows = getRows();
    downloadText(`m2-watchlist-${exportStamp()}.csv`, "text/csv", csvExport(rows));
    setExportStatus(`CSV ${rows.length} 行`);
  });
  $("downloadJson").addEventListener("click", () => {
    const rows = getRows();
    downloadText(`m2-watchlist-${exportStamp()}.json`, "application/json", jsonExport(rows));
    setExportStatus(`JSON ${rows.length} 行`);
  });

  const render = () => {
    const rows = getRows();
    $("visibleCount").textContent = rows.length;
    $("tableBody").innerHTML = rows.map((row, index) => `
      <tr>
        <td>${String(index + 1).padStart(2, "0")}</td>
        <td class="sticky-name name-cell"><div class="name-line"><strong>${row.name}</strong><span class="board-chip board-${marketBoard(row.code).className}">${marketBoard(row.code).label}</span></div><small>${row.code} · ${row.exchange}</small>${renderSectorTags(row)}</td>
        <td class="star-cell star-${setupRating(row).stars}" title="${setupRating(row).action}"><strong>${starText(setupRating(row).stars)}</strong><small>${setupRating(row).label} · ${setupRating(row).action}</small></td>
        <td class="advice-cell ${row.recommendationClass}" title="${row.recommendationReason}"><strong>${row.recommendation}</strong><small>${row.recommendationReason}</small></td>
        <td>${price(row.price)}</td>
        <td class="${row.pct >= 0 ? "pct-up" : "pct-down"}">${pct(row.pct)}</td>
        <td>${price(row.ma50)}</td>
        <td>${price(row.ma150)}</td>
        <td>${price(row.ma200)}</td>
        <td class="${row.maStacked && row.aboveMa50 ? "ma-pass" : "ma-warn"}">${row.maStacked && row.aboveMa50 ? "多头通过" : "待复核"}</td>
        <td class="derived-cell"><strong>高于 MA200 ${pct(row.priceToMa200Pct)}</strong><small>MA50→150 ${pct(row.ma50ToMa150Pct)} · MA150→200 ${pct(row.ma150ToMa200Pct)}</small></td>
        <td class="stage-cell ${row.stageInference === "阶段 2 初筛通过" ? "stage-pass" : "stage-pending"}"><strong>${row.stageInference}</strong><small>${row.periodPct > 0 ? "阶段涨幅为正" : "阶段涨幅待复核"}</small></td>
        <td class="${row.periodPct >= 0 ? "pct-up" : "pct-down"}">${pct(row.periodPct)}</td>
        <td class="${row.fromHighPct >= -10 ? "near-high" : ""}">${pct(row.fromHighPct)}</td>
        <td>${pct(row.fromLowPct)}</td>
        <td>${count(row.avgAmount)}</td>
        <td class="valuation-cell"><strong>${amountYi(row.marketCap ?? valuationInfo(row).marketCap)}</strong><small>总市值</small></td>
        <td class="valuation-cell"><strong>${pe(row.peRatio ?? valuationInfo(row).peRatio)}</strong><small>动态 PE</small></td>
        <td class="trend-pending">${row.ma200Slope || "待复核"}</td>
        <td class="data-warning" title="${row.dataQuality || ""}">${row.dataQuality || "—"}</td>
        <td class="${row.pivotPrice ? "pivot-ready" : "pivot-pending"}" title="${row.pivotReason || ""}"><strong>${row.pivot}</strong><small>${row.pivotStatus || "待确认"} · ${row.pivotDistance || "—"}</small></td>
        <td class="contraction-pending">${row.contractions}</td>
      </tr>
    `).join("");
  };

  ["tableSearch", "tableFilter", "sectorFilter", "tableSort"].forEach((id) => $(id)?.addEventListener("input", render));
  render();

  const syncSnapshot = async () => {
    try {
      const response = await fetch(`/m2-snapshot.json?ts=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      applySnapshotPivot(await response.json());
      renderAnalysis();
      render();
    } catch (error) {
      console.warn("M2 table pivot snapshot failed", error);
    }
  };
  syncSnapshot();
})();
