/**
 * KSEB Energy Monitor — Dashboard Script
 * Fetches data.json and populates gauge, stat cards, charts, and table.
 */

(async function () {
  'use strict';

  // ── Fetch data ──
  let data;
  try {
    const res = await fetch('data.json');
    data = await res.json();
  } catch (err) {
    console.error('Failed to load data.json:', err);
    document.getElementById('tip-text').textContent =
      'Could not load data. Make sure data.json exists in the parent directory.';
    return;
  }

  // Sort by date ascending
  data.sort((a, b) => a.date.localeCompare(b.date));

  // Rolling window: charts show only the last N days to stay readable
  const CHART_WINDOW = 30;
  const chartData = data.slice(-CHART_WINDOW);
  const chartStart = chartData.length > 0 ? formatDate(chartData[0].date) : '';
  const chartEnd   = chartData.length > 0 ? formatDate(chartData[chartData.length - 1].date) : '';

  const latest = data[data.length - 1];
  const prev = data.length > 1 ? data[data.length - 2] : null;
  const m = latest.metrics;
  const pm = prev ? prev.metrics : null;

  // ── Helpers ──
  function fmt(v, suffix = '') {
    if (v === null || v === undefined) return '—';
    return v + suffix;
  }

  function formatDate(iso) {
    const d = new Date(iso + 'T00:00:00');
    return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
  }

  function calcChange(curr, prev) {
    if (curr == null || prev == null || prev === 0) return null;
    return ((curr - prev) / Math.abs(prev) * 100).toFixed(1);
  }

  function renderChange(el, curr, prev, suffix = '', invert = false) {
    const pct = calcChange(curr, prev);
    if (pct === null) {
      el.innerHTML = '<span class="stat-card__change-label">No prior data</span>';
      return;
    }
    const isUp = parseFloat(pct) >= 0;
    const arrow = isUp ? '▲' : '▼';
    // For dam levels, up = good. For peak, up = bad. `invert` flips color logic.
    const colorClass = invert ? (isUp ? 'change-down' : 'change-up') : (isUp ? 'change-up' : 'change-down');
    el.innerHTML = `
      <div class="stat-card__change-icon"></div>
      <span class="stat-card__change-value ${colorClass}">${arrow} ${Math.abs(pct)}%</span>
      <span class="stat-card__change-label">vs prev day</span>
    `;
  }

  // ── Gauge ──
  const consumption = m.consumption ?? 0;
  // Use a visual scale where 100 MU = full ring (cosmetic only, no stated capacity)
  const visualMax = 100;
  const pct = Math.min((consumption / visualMax) * 100, 100);
  const circumference = 2 * Math.PI * 80; // r=80
  const dashLen = (pct / 100) * circumference;

  const gaugeFill = document.getElementById('gauge-fill');
  // Animate gauge on load
  requestAnimationFrame(() => {
    gaugeFill.setAttribute('stroke-dasharray', `${dashLen} ${circumference}`);
  });

  document.getElementById('gauge-value').textContent = consumption;
  document.getElementById('gauge-sub').textContent = formatDate(latest.date);

  // ── Stat cards — Dam ──
  document.getElementById('dam-now-value').textContent = fmt(m.dam_now, '%');
  document.getElementById('dam-before-value').textContent = fmt(m.dam_before, '%');
  renderChange(document.getElementById('dam-now-change'), m.dam_now, pm?.dam_now);
  renderChange(document.getElementById('dam-before-change'), m.dam_before, pm?.dam_before);

  // ── Stat cards — Peak & Import ──
  document.getElementById('peak-value').textContent = fmt(m.peak, ' MW');
  document.getElementById('import-value').textContent = fmt(m.import, ' MU');
  renderChange(document.getElementById('peak-change'), m.peak, pm?.peak, '', true);
  renderChange(document.getElementById('import-change'), m.import, pm?.import, '', true);

  // ── Chart styling constants (matching reference) ──
  const chartFont = { family: "'JetBrains Mono', monospace", size: 11 };
  const gridColor = '#cbd5e1';
  const tickColor = '#475569';
  const axisLineColor = '#94a3b8';

  const commonScaleOptions = {
    ticks: { font: chartFont, color: tickColor },
    grid: { color: gridColor, drawBorder: true, borderColor: axisLineColor, borderDash: [3, 3] },
    border: { color: axisLineColor },
  };

  // ── Line Chart — Energy Trends ──
  const lineLabels = chartData.map(d => formatDate(d.date));

  // Inject date-range subtitle under the chart title
  const lineCard = document.getElementById('line-chart').closest('.chart-card');
  if (lineCard) {
    const sub = document.createElement('p');
    sub.className = 'chart-range-label';
    sub.textContent = `Showing ${chartData.length} day${chartData.length !== 1 ? 's' : ''} · ${chartStart} – ${chartEnd}`;
    lineCard.querySelector('h3').after(sub);
  }

  new Chart(document.getElementById('line-chart'), {
    type: 'line',
    data: {
      labels: lineLabels,
      datasets: [
        {
          label: 'Consumption (MU)',
          data: chartData.map(d => d.metrics.consumption),
          borderColor: '#475569',
          backgroundColor: 'rgba(71,85,105,.08)',
          borderWidth: 2,
          tension: 0.35,
          pointRadius: 4,
          pointHoverRadius: 6,
          pointBackgroundColor: '#475569',
          fill: true,
        },
        {
          label: 'Production (MU)',
          data: chartData.map(d => d.metrics.production),
          borderColor: '#16a34a',
          backgroundColor: 'rgba(22,163,74,.06)',
          borderWidth: 2,
          tension: 0.35,
          pointRadius: 4,
          pointHoverRadius: 6,
          pointBackgroundColor: '#16a34a',
          fill: true,
        },
        {
          label: 'Import (MU)',
          data: chartData.map(d => d.metrics.import),
          borderColor: '#94a3b8',
          borderWidth: 2,
          borderDash: [5, 4],
          tension: 0.35,
          pointRadius: 3,
          pointHoverRadius: 5,
          pointBackgroundColor: '#94a3b8',
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { font: chartFont, color: tickColor, usePointStyle: true, pointStyle: 'circle', padding: 16 } },
        tooltip: {
          backgroundColor: '#f8fafc',
          titleColor: '#0f172a',
          bodyColor: '#0f172a',
          borderColor: '#94a3b8',
          borderWidth: 2,
          titleFont: { ...chartFont, weight: '600' },
          bodyFont: chartFont,
          cornerRadius: 4,
          padding: 10,
        },
      },
      scales: {
        x: { ...commonScaleOptions },
        y: {
          ...commonScaleOptions, beginAtZero: true,
          title: { display: true, text: 'MU', font: chartFont, color: tickColor },
        },
      },
    },
  });

  // Inject date-range subtitle under the bar chart title
  const barCard = document.getElementById('bar-chart').closest('.chart-card');
  if (barCard) {
    const sub = document.createElement('p');
    sub.className = 'chart-range-label';
    sub.textContent = `Showing ${chartData.length} day${chartData.length !== 1 ? 's' : ''} · ${chartStart} – ${chartEnd}`;
    barCard.querySelector('h3').after(sub);
  }

  // ── Bar Chart — Peak Demand ──
  new Chart(document.getElementById('bar-chart'), {
    type: 'bar',
    data: {
      labels: lineLabels,
      datasets: [
        {
          label: 'Peak (MW)',
          data: chartData.map(d => d.metrics.peak),
          backgroundColor: '#94a3b8',
          hoverBackgroundColor: '#64748b',
          borderRadius: 4,
          maxBarThickness: 80,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#f8fafc',
          titleColor: '#0f172a',
          bodyColor: '#0f172a',
          borderColor: '#94a3b8',
          borderWidth: 2,
          titleFont: { ...chartFont, weight: '600' },
          bodyFont: chartFont,
          cornerRadius: 4,
          padding: 10,
          callbacks: { label: ctx => `${ctx.parsed.y.toLocaleString()} MW` },
        },
      },
      scales: {
        x: { ...commonScaleOptions },
        y: {
          ...commonScaleOptions, beginAtZero: true,
          title: { display: true, text: 'MW', font: chartFont, color: tickColor },
        },
      },
    },
  });

  // ── Metrics Table ──
  const tbody = document.getElementById('metrics-tbody');
  // Show newest first in table
  const reversed = [...data].reverse();
  for (const entry of reversed) {
    const em = entry.metrics;
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${formatDate(entry.date)}</td>
      <td>${fmt(em.consumption)}</td>
      <td>${fmt(em.production)}</td>
      <td>${fmt(em.import)}</td>
      <td>${fmt(em.peak)}</td>
      <td>${fmt(em.peak_time)}</td>
      <td>${fmt(em.dam_now, '%')}</td>
      <td>${fmt(em.dam_before, '%')}</td>
    `;
    tbody.appendChild(tr);
  }

  // ── Tip ──
  const tips = [
    `Latest consumption is ${m.consumption} MU with ${fmt(m.production)} MU production, offsetting ${m.production && m.consumption ? ((m.production / m.consumption) * 100).toFixed(1) : '—'}% of demand.`,
    `Dam storage is at ${fmt(m.dam_now)}%. ${m.dam_now > 30 ? 'Reservoir levels are healthy.' : 'Reservoir levels are below 30% — conservation may be needed.'}`,
    `Peak demand of ${fmt(m.peak)} MW occurred at ${fmt(m.peak_time)}. Shifting heavy loads outside peak hours can reduce strain on the grid.`,
    `Production has been ${m.production > 15 ? 'strong' : 'moderate'} at ${fmt(m.production)} MU. Clear-sky days help maximize solar output.`,
  ];
  document.getElementById('tip-text').textContent = tips[Math.floor(Math.random() * tips.length)];

})();
