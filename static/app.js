// State
let currentSnapshot = null;
let currentHorizon = '15m';
let rsChart = null;
let equityChart = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  initCharts();
  fetchLiveSnapshot();
  runBacktest();
  // Polling every 30 seconds
  setInterval(() => fetchLiveSnapshot(false), 30000);
});

/* ==========================================================================
   Live Market Data & Signal Fetching
   ========================================================================== */
async function fetchLiveSnapshot(refresh = false) {
  const refreshBtn = document.getElementById('refreshBtn');
  if (refresh && refreshBtn) {
    refreshBtn.style.opacity = '0.5';
    refreshBtn.innerText = 'Fetching...';
  }

  try {
    const url = `/api/snapshot?refresh=${refresh}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    currentSnapshot = data;
    renderSnapshot(data);
  } catch (err) {
    console.error('Error fetching snapshot:', err);
    document.getElementById('lastSyncTime').innerText = 'Sync failed';
  } finally {
    if (refreshBtn) {
      refreshBtn.style.opacity = '1';
      refreshBtn.innerHTML = '<span class="btn-icon">⚡</span> Refresh Live';
    }
  }
}

function renderSnapshot(data) {
  const { indices, macro, features, signal, timestamp } = data;

  // 1. Sync Time
  const syncDate = new Date(timestamp);
  document.getElementById('lastSyncTime').innerText = `Synced: ${syncDate.toLocaleTimeString()}`;

  // 2. NIFTY 50 Header
  const nifty = indices['NIFTY 50'] || indices['NIFTY 50'.toUpperCase()];
  if (nifty) {
    document.getElementById('headerNiftyPrice').innerText = Number(nifty.last_price).toLocaleString('en-IN', { minimumFractionDigits: 2 });
    const pct = nifty.percent_change || 0;
    const niftyChgEl = document.getElementById('headerNiftyChange');
    niftyChgEl.innerText = `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
    niftyChgEl.className = `badge ${pct >= 0 ? 'positive' : 'negative'}`;
  }

  // 3. INDIA VIX Header
  const vix = indices['INDIA VIX'];
  if (vix) {
    document.getElementById('headerVixPrice').innerText = Number(vix.last_price).toFixed(2);
    const vixPct = vix.percent_change || 0;
    const vixChgEl = document.getElementById('headerVixChange');
    vixChgEl.innerText = `${vixPct >= 0 ? '+' : ''}${vixPct.toFixed(2)}%`;
    vixChgEl.className = `badge ${vixPct <= 0 ? 'positive' : 'negative'}`; // Lower VIX is generally positive
  }

  // 4. Signal & Regime Badge
  if (signal) {
    const score = signal.final_score;
    const regime = signal.regime;
    const scoreEl = document.getElementById('directionalScore');
    scoreEl.innerText = `${score >= 0 ? '+' : ''}${score.toFixed(1)}`;
    scoreEl.style.color = score >= 30 ? 'var(--accent-bullish)' : (score <= -30 ? 'var(--accent-bearish)' : 'var(--accent-warning)');

    // Regime Badges
    const regimeClass = regime.includes('BULLISH') ? 'bullish' : (regime.includes('BEARISH') ? 'bearish' : 'neutral');
    
    const headerRegimeBadge = document.getElementById('headerRegimeBadge');
    headerRegimeBadge.className = `regime-badge ${regimeClass}`;
    document.getElementById('headerRegimeText').innerText = regime.replace('_', ' ');

    const regimeStatusBox = document.getElementById('regimeStatusBox');
    regimeStatusBox.className = `regime-indicator ${regimeClass}`;
    regimeStatusBox.style.color = score >= 30 ? 'var(--accent-bullish)' : (score <= -30 ? 'var(--accent-bearish)' : 'var(--accent-warning)');
    document.getElementById('regimeStatusText').innerText = regime.replace('_', ' ');

    // Agreement Tag
    document.getElementById('signalAgreementTag').innerText = `${Math.round(signal.agreement_ratio * 100)}% Alignment`;

    // Breakdown Bars
    updateBar('fillMom', 'valMom', signal.momentum_score);
    updateBar('fillRs', 'valRs', signal.relative_strength_score);
    updateBar('fillBreadth', 'valBreadth', signal.breadth_score);
    updateBar('fillMacro', 'valMacro', signal.macro_score);
  }

  // 5. Market Breadth
  if (features && features.market_breadth) {
    const b = features.market_breadth;
    document.getElementById('advCount').innerText = b.advancing_sectors || 0;
    document.getElementById('decCount').innerText = b.declining_sectors || 0;
    document.getElementById('unchCount').innerText = b.unchanged_sectors || 0;
    document.getElementById('adRatioTag').innerText = `A/D: ${b.sector_advance_decline_ratio || 0}`;

    const total = (b.advancing_sectors || 0) + (b.declining_sectors || 0) || 1;
    const advPct = ((b.advancing_sectors || 0) / total) * 100;
    document.getElementById('breadthAdvBar').style.width = `${advPct}%`;
    document.getElementById('breadthDecBar').style.width = `${100 - advPct}%`;
  }

  // 6. Macro Grid
  if (macro) {
    renderMacroGrid(macro);
  }

  // 7. Sector Table & Relative Strength Chart
  if (indices && features) {
    renderSectorsTable(indices, features);
    updateRelativeStrengthChart(features);
  }
}

function updateBar(barId, valId, score) {
  const normWidth = Math.max(5, Math.min(95, (score + 100) / 2));
  const barEl = document.getElementById(barId);
  const valEl = document.getElementById(valId);
  if (barEl) {
    barEl.style.width = `${normWidth}%`;
    barEl.style.background = score > 0 ? 'var(--accent-bullish)' : (score < 0 ? 'var(--accent-bearish)' : 'var(--accent-warning)');
  }
  if (valEl) {
    valEl.innerText = `${score >= 0 ? '+' : ''}${score.toFixed(1)}`;
  }
}

function renderMacroGrid(macro) {
  const grid = document.getElementById('macroGrid');
  grid.innerHTML = '';

  const labels = {
    brent_crude: 'Brent Crude',
    wti_crude: 'WTI Crude',
    usd_inr: 'USD / INR',
    sp500: 'S&P 500',
    nasdaq: 'Nasdaq',
    nikkei: 'Nikkei 225',
  };

  for (const [key, item] of Object.entries(macro)) {
    const pct = item.percent_change || 0;
    const isPos = pct >= 0;
    const colorClass = isPos ? 'positive' : 'negative';

    const card = document.createElement('div');
    card.className = 'macro-card-item';
    card.innerHTML = `
      <div>
        <div class="macro-name">${labels[key] || key}</div>
        <div class="macro-ticker">${item.ticker_symbol}</div>
      </div>
      <div class="macro-price-box">
        <div class="macro-price">${Number(item.last_price).toLocaleString('en-US', { minimumFractionDigits: 2 })}</div>
        <div class="macro-pct badge ${colorClass}">${isPos ? '+' : ''}${pct.toFixed(2)}%</div>
      </div>
    `;
    grid.appendChild(card);
  }
}

function renderSectorsTable(indices, features) {
  const tbody = document.getElementById('sectorsTableBody');
  tbody.innerHTML = '';

  const sortedKeys = Object.keys(indices).sort((a, b) => {
    if (a === 'NIFTY 50') return -1;
    if (b === 'NIFTY 50') return 1;
    if (a === 'INDIA VIX') return 1;
    if (b === 'INDIA VIX') return -1;
    return a.localeCompare(b);
  });

  for (const key of sortedKeys) {
    const item = indices[key];
    const pct = item.percent_change || 0;
    const pctColor = pct > 0 ? 'var(--accent-bullish)' : (pct < 0 ? 'var(--accent-bearish)' : 'var(--text-muted)');
    
    // Relative strength
    let rsText = '-';
    let rsColor = 'inherit';
    if (features && features.sector_features && features.sector_features[key]) {
      const rs = features.sector_features[key].relative_strength_vs_nifty;
      if (rs !== null && rs !== undefined) {
        rsText = `${rs >= 0 ? '+' : ''}${rs.toFixed(2)}%`;
        rsColor = rs > 0 ? 'var(--accent-bullish)' : (rs < 0 ? 'var(--accent-bearish)' : 'var(--text-muted)');
      }
    }

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${item.index_name}</td>
      <td class="num">${Number(item.last_price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
      <td class="num" style="color: ${pctColor}">${item.variation >= 0 ? '+' : ''}${Number(item.variation).toFixed(2)}</td>
      <td class="num" style="color: ${pctColor}">${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%</td>
      <td class="num" style="color: ${rsColor}">${rsText}</td>
      <td class="num" style="color: var(--text-muted)">${item.pe ? Number(item.pe).toFixed(1) : '-'}</td>
    `;
    tbody.appendChild(tr);
  }
}

function filterSectors() {
  const query = document.getElementById('sectorSearch').value.toLowerCase();
  const rows = document.querySelectorAll('#sectorsTableBody tr');
  rows.forEach(r => {
    const name = r.cells[0].innerText.toLowerCase();
    r.style.display = name.includes(query) ? '' : 'none';
  });
}

/* ==========================================================================
   Charts (Relative Strength & Equity Curve)
   ========================================================================== */
function initCharts() {
  // 1. Relative Strength Bar Chart
  const rsCtx = document.getElementById('relativeStrengthChart').getContext('2d');
  rsChart = new Chart(rsCtx, {
    type: 'bar',
    data: {
      labels: [],
      datasets: [{
        label: 'Relative Strength vs NIFTY (%)',
        data: [],
        backgroundColor: [],
        borderRadius: 4,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => ` Spread: ${ctx.raw >= 0 ? '+' : ''}${ctx.raw.toFixed(2)}%`
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: '#94a3b8', font: { size: 10 } }
        },
        y: {
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#94a3b8', font: { size: 10 } }
        }
      }
    }
  });

  // 2. Backtest Equity Curve Chart
  const eqCtx = document.getElementById('equityCurveChart').getContext('2d');
  equityChart = new Chart(eqCtx, {
    type: 'line',
    data: {
      labels: [],
      datasets: []
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          position: 'top',
          labels: { color: '#94a3b8', boxWidth: 12, font: { size: 10 } }
        }
      },
      scales: {
        x: {
          display: false,
        },
        y: {
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#94a3b8', font: { size: 10 } }
        }
      }
    }
  });
}

function updateRelativeStrengthChart(features) {
  if (!features || !features.sector_features || !rsChart) return;

  const labels = [];
  const data = [];
  const colors = [];

  for (const [name, feat] of Object.entries(features.sector_features)) {
    if (feat.relative_strength_vs_nifty !== null) {
      labels.push(name.replace('NIFTY ', ''));
      const val = Number(feat.relative_strength_vs_nifty);
      data.push(val);
      colors.push(val >= 0 ? 'rgba(16, 185, 129, 0.85)' : 'rgba(239, 68, 68, 0.85)');
    }
  }

  rsChart.data.labels = labels;
  rsChart.data.datasets[0].data = data;
  rsChart.data.datasets[0].backgroundColor = colors;
  rsChart.update();
}

/* ==========================================================================
   Backtesting Simulation Runner
   ========================================================================== */
function selectHorizon(h) {
  currentHorizon = h;
  const buttons = document.querySelectorAll('#horizonPills .pill-btn');
  buttons.forEach(b => {
    b.classList.toggle('active', b.getAttribute('data-horizon') === h);
  });
  runBacktest();
}

async function runBacktest() {
  const tbody = document.getElementById('backtestMetricsBody');
  tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--text-muted)">Running statistical backtest...</td></tr>';

  try {
    const res = await fetch(`/api/backtest?horizon=${currentHorizon}&source=simulation`);
    const data = await res.json();
    renderBacktestResults(data);
  } catch (err) {
    console.error('Error running backtest:', err);
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--accent-bearish)">Failed to execute backtest</td></tr>';
  }
}

function renderBacktestResults(result) {
  const tbody = document.getElementById('backtestMetricsBody');
  tbody.innerHTML = '';

  const allMetrics = [
    result.sector_model_metrics,
    result.baseline_metrics.random,
    result.baseline_metrics.always_bullish,
    result.baseline_metrics.prev_5m_direction,
    result.baseline_metrics.nifty_momentum,
  ].filter(Boolean);

  allMetrics.forEach((m, idx) => {
    const isModel = idx === 0;
    const tr = document.createElement('tr');
    if (isModel) {
      tr.style.background = 'rgba(6, 182, 212, 0.08)';
      tr.style.fontWeight = '700';
    }

    const pfColor = m.profit_factor >= 1.2 ? 'var(--accent-bullish)' : (m.profit_factor < 1.0 ? 'var(--accent-bearish)' : 'inherit');
    const sharpeColor = m.sharpe_ratio >= 1.0 ? 'var(--accent-bullish)' : (m.sharpe_ratio < 0 ? 'var(--accent-bearish)' : 'inherit');
    const netColor = m.cumulative_return_pct >= 0 ? 'var(--accent-bullish)' : 'var(--accent-bearish)';

    tr.innerHTML = `
      <td>${isModel ? '⭐ ' : ''}${m.strategy_name}</td>
      <td class="num">${m.total_signals}</td>
      <td class="num">${m.win_rate.toFixed(1)}%</td>
      <td class="num">${m.precision.toFixed(1)}%</td>
      <td class="num" style="color: ${pfColor}">${m.profit_factor >= 100 ? '>10.0' : m.profit_factor.toFixed(2)}</td>
      <td class="num">${m.mean_return_pct >= 0 ? '+' : ''}${m.mean_return_pct.toFixed(3)}%</td>
      <td class="num" style="color: var(--accent-bearish)">-${m.max_drawdown_pct.toFixed(2)}%</td>
      <td class="num" style="color: ${sharpeColor}">${m.sharpe_ratio.toFixed(2)}</td>
      <td class="num" style="color: ${netColor}">${m.cumulative_return_pct >= 0 ? '+' : ''}${m.cumulative_return_pct.toFixed(2)}%</td>
    `;
    tbody.appendChild(tr);
  });

  // Render Equity Curve Chart
  if (result.equity_curves && equityChart) {
    const palette = {
      'Sector Model': '#06b6d4',
      'Random': '#64748b',
      'Always Bullish': '#3b82f6',
      '5m Direction': '#f59e0b',
      'NIFTY Momentum': '#a855f7',
    };

    const datasets = Object.entries(result.equity_curves).map(([name, data]) => ({
      label: name,
      data: data,
      borderColor: palette[name] || '#94a3b8',
      borderWidth: name === 'Sector Model' ? 2.5 : 1.2,
      borderDash: name === 'Sector Model' ? [] : [4, 4],
      pointRadius: 0,
      tension: 0.2,
    }));

    const sampleLen = (Object.values(result.equity_curves)[0] || []).length;
    equityChart.data.labels = Array.from({ length: sampleLen }, (_, i) => `T+${i}`);
    equityChart.data.datasets = datasets;
    equityChart.update();
  }
}
