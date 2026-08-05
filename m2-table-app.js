(function () {
  const data = window.M2_TABLE_DATA;
  if (!data) return;

  const $ = (id) => document.getElementById(id);
  const pct = (value) => {
    if (!Number.isFinite(Number(value))) return "—";
    const n = Number(value);
    return `${n >= 0 ? "+" : "−"}${Math.abs(n).toFixed(1)}%`;
  };
  const price = (value) => Number.isFinite(Number(value)) ? Number(value).toFixed(2) : "—";
  const amountYi = (value) => Number.isFinite(Number(value)) ? (Number(value) / 100000000).toFixed(1) : "—";
  const count = (value) => Number.isFinite(Number(value)) ? Number(value).toLocaleString("zh-CN") : "—";
  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

  $("tableAsOf").textContent = `导入快照 ${data.asOf}`;
  $("tableSource").textContent = data.source;
  $("summaryTotal").textContent = data.rowCount;
  $("summaryStacked").textContent = data.rows.filter((row) => row.maStacked).length;
  $("summaryAbove200").textContent = data.rows.filter((row) => row.aboveMa200).length;
  $("summaryNearHigh").textContent = data.rows.filter((row) => row.recommendationClass === "priority").length;
  $("summaryUp").textContent = data.rows.filter((row) => row.pct > 0).length;

  const renderAnalysis = () => {
    const nearHigh = data.rows.filter((row) => row.fromHighPct >= -10).length;
    const priority = data.rows.filter((row) => row.recommendationClass === "priority").length;
    const confirmed = data.rows.filter((row) => row.pivot && row.pivot !== "待确认" && row.contractions && row.contractions !== "待确认").length;
    $("flowTotal").textContent = data.rowCount;
    $("flowStacked").textContent = data.rows.filter((row) => row.maStacked).length;
    $("flowAbove200").textContent = data.rows.filter((row) => row.aboveMa200).length;
    $("flowNearHigh").textContent = nearHigh;
    $("flowPriority").textContent = priority;
    $("flowConfirmed").textContent = confirmed;

    const adviceRows = [
      { label: "突破确认后考虑", key: "priority", color: "priority" },
      { label: "不追当日大涨", key: "caution", color: "caution" },
      { label: "等待平台 / 突破", key: "wait", color: "wait" },
      { label: "暂不建议买入", key: "avoid", color: "avoid" },
    ].map((item) => ({ ...item, value: data.rows.filter((row) => row.recommendationClass === item.key).length }));
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
    const sort = $("tableSort").value;
    const rows = data.rows.filter((row) => {
      const matchesSearch = !query || `${row.code} ${row.name}`.toLowerCase().includes(query);
      const matchesFilter = filter === "all"
        || (filter === "stacked" && row.maStacked)
        || (filter === "nearHigh" && row.fromHighPct >= -10)
        || (filter === "priority" && row.recommendationClass === "priority")
        || (filter === "caution" && row.recommendationClass === "caution")
        || (filter === "wait" && row.recommendationClass === "wait")
        || (filter === "avoid" && row.recommendationClass === "avoid")
        || filter === "needsPivot";
      return matchesSearch && matchesFilter;
    });
    const valueOf = (row) => ({
      pct: row.pct,
      fromHigh: row.fromHighPct,
      fromLow: row.fromLowPct,
      amount: row.avgAmount,
      price: row.price,
    }[sort]);
    return rows.sort((a, b) => Number(valueOf(b) ?? -Infinity) - Number(valueOf(a) ?? -Infinity));
  };

  const render = () => {
    const rows = getRows();
    $("visibleCount").textContent = rows.length;
    $("tableBody").innerHTML = rows.map((row, index) => `
      <tr>
        <td>${String(index + 1).padStart(2, "0")}</td>
        <td class="sticky-name name-cell"><strong>${row.name}</strong><small>${row.code} · ${row.exchange}</small></td>
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
        <td>${amountYi(row.marketCap)}</td>
        <td>${price(row.pb)}</td>
        <td>${price(row.pe)}</td>
        <td class="pivot-pending">${row.pivot}</td>
        <td class="contraction-pending">${row.contractions}</td>
      </tr>
    `).join("");
  };

  ["tableSearch", "tableFilter", "tableSort"].forEach((id) => $(id).addEventListener("input", render));
  render();
})();
