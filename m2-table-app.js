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

  $("tableAsOf").textContent = `导入快照 ${data.asOf}`;
  $("tableSource").textContent = data.source;
  $("summaryTotal").textContent = data.rowCount;
  $("summaryStacked").textContent = data.rows.filter((row) => row.maStacked).length;
  $("summaryAbove200").textContent = data.rows.filter((row) => row.aboveMa200).length;
  $("summaryNearHigh").textContent = data.rows.filter((row) => row.recommendationClass === "priority").length;
  $("summaryUp").textContent = data.rows.filter((row) => row.pct > 0).length;

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
