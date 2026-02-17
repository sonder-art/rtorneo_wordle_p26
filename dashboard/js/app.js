/**
 * Wordle Tournament Dashboard — main application logic.
 * Fetches results JSON, renders UI, and manages tournaments via API.
 */

let tournamentData = null;
let roundCharts = [];
let comparisonChart = null;
let logVisible = false;
let statusPollTimer = null;
let currentRunId = null;

const DATA_URL = 'data/tournament_results.json';
const REFRESH_INTERVAL = 30000;
const MEDALS = ['', '\u{1F947}', '\u{1F948}', '\u{1F949}'];

// Preset configurations (only fill form, don't launch)
const PRESETS = {
  quick:    { num_games: 10,  repetitions: 1, shock: 0,    corpus: 'mini' },
  official: { num_games: 100, repetitions: 1, shock: 0,    corpus: 'full' },
  real:     { num_games: 100, repetitions: 3, shock: 0.05, corpus: 'full' },
};

// ── Bootstrap ──────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  loadRuns();
  loadData();
  setInterval(loadData, REFRESH_INTERVAL);
  pollStatus();

  // Update time estimate when form values change
  document.getElementById('num-games').addEventListener('input', updateTimeEstimate);
  document.getElementById('repetitions').addEventListener('input', updateTimeEstimate);
  document.getElementById('shock').addEventListener('input', updateTimeEstimate);
});

async function loadData() {
  try {
    let url = DATA_URL + '?t=' + Date.now();
    if (currentRunId) url += '&run=' + encodeURIComponent(currentRunId);
    const resp = await fetch(url);
    if (!resp.ok) {
      document.getElementById('tournament-info').textContent =
        'Sin datos de torneo. Lanza un torneo desde el panel de control.';
      return;
    }
    tournamentData = await resp.json();
    render();
  } catch (err) {
    // Silent — server might be nginx (no API)
  }
}

// ── Run History ───────────────────────────────────────────

async function loadRuns() {
  try {
    const resp = await fetch('/api/runs?t=' + Date.now());
    if (!resp.ok) return;
    const data = await resp.json();
    const runs = data.runs || [];
    const dropdown = document.getElementById('run-dropdown');
    if (!dropdown) return;

    const prev = dropdown.value;
    dropdown.innerHTML = '<option value="">Ultimo torneo</option>';

    runs.forEach(run => {
      const opt = document.createElement('option');
      opt.value = run.run_id;
      if (run.error) {
        opt.textContent = `${run.run_id} (error)`;
      } else {
        const name = run.name ? `${run.name}` : run.run_id;
        const games = run.num_games || '?';
        const reps = run.repetitions || 1;
        const shock = run.shock_scale ? `${(run.shock_scale * 100).toFixed(0)}%` : '0%';
        const strats = run.num_strategies || '?';
        opt.textContent = `${name} \u2014 ${games}g, ${reps}r, ${shock} shock (${strats} estrat.)`;
      }
      dropdown.appendChild(opt);
    });

    // Restore previous selection if still available
    if (prev && [...dropdown.options].some(o => o.value === prev)) {
      dropdown.value = prev;
    }
  } catch {
    // API not available (nginx mode)
  }
}

function selectRun(runId) {
  currentRunId = runId || null;
  loadData();
}

// ── Time Estimate ─────────────────────────────────────────

function estimateTime(numGames, repetitions) {
  // Heuristic: ~0.5s per game per round (average across strategies with timeout)
  // 6 round configs total
  const totalSeconds = numGames * 6 * repetitions * 0.5;
  if (totalSeconds < 60) return `~${Math.max(5, Math.round(totalSeconds))}s`;
  if (totalSeconds < 3600) return `~${Math.round(totalSeconds / 60)} min`;
  return `~${(totalSeconds / 3600).toFixed(1)} horas`;
}

function updateTimeEstimate() {
  const numGames = parseInt(document.getElementById('num-games').value) || 10;
  const reps = parseInt(document.getElementById('repetitions').value) || 1;
  const el = document.getElementById('time-estimate');
  if (el) el.textContent = `Tiempo estimado: ${estimateTime(numGames, reps)}`;
}

// ── Render ─────────────────────────────────────────────────

function render() {
  if (!tournamentData) return;

  const cfg = tournamentData.config || {};
  const ts = tournamentData.timestamp || '';
  const name = cfg.name || '';
  const runId = tournamentData.run_id || tournamentData.tournament_id || '';
  const label = name ? `${name} (${runId})` : runId;
  document.getElementById('tournament-info').textContent =
    `${label || '\u2014'} | ` +
    `Fecha: ${ts.replace('T', ' ').slice(0, 19)} | ` +
    `Rondas: ${(tournamentData.rounds || []).length} | ` +
    `Juegos: ${cfg.num_games || '?'} | ` +
    `Reps: ${cfg.repetitions || '?'} | ` +
    `Shock: ${cfg.shock_scale || 0}`;

  renderLeaderboard();
  renderRoundTabs();
  renderComparisonControls();
}

// ── Leaderboard ────────────────────────────────────────────

function renderLeaderboard() {
  const tbody = document.querySelector('#leaderboard-table tbody');
  tbody.innerHTML = '';

  const entries = tournamentData.leaderboard || [];
  entries.forEach(e => {
    const tr = document.createElement('tr');
    if (e.rank <= 3) tr.className = 'rank-' + e.rank;
    const medal = e.rank <= 3 ? MEDALS[e.rank] + ' ' : '';
    tr.innerHTML = `
      <td>${medal}${e.rank}</td>
      <td>${e.strategy}</td>
      <td>${e.total_points.toFixed(1)}</td>
      <td>${(e.overall_solve_rate * 100).toFixed(1)}%</td>
      <td>${e.overall_mean_guesses.toFixed(2)}</td>
    `;
    tbody.appendChild(tr);
  });

  document.querySelectorAll('#leaderboard-table th[data-sort]').forEach(th => {
    th.onclick = () => sortLeaderboard(th.dataset.sort);
  });
}

let sortKey = 'rank';
let sortAsc = true;

function sortLeaderboard(key) {
  if (sortKey === key) {
    sortAsc = !sortAsc;
  } else {
    sortKey = key;
    sortAsc = true;
  }

  const entries = tournamentData.leaderboard || [];
  entries.sort((a, b) => {
    let va = a[key], vb = b[key];
    if (typeof va === 'string') return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
    return sortAsc ? va - vb : vb - va;
  });

  renderLeaderboard();
}

// ── Round Tabs ─────────────────────────────────────────────

let activeRoundIdx = 0;

function renderRoundTabs() {
  const container = document.getElementById('round-tabs');
  container.innerHTML = '';

  (tournamentData.rounds || []).forEach((rd, idx) => {
    const tab = document.createElement('div');
    tab.className = 'round-tab' + (idx === activeRoundIdx ? ' active' : '');
    tab.textContent = rd.round_id;
    tab.onclick = () => {
      activeRoundIdx = idx;
      renderRoundTabs();
      renderRoundDetail();
    };
    container.appendChild(tab);
  });

  renderRoundDetail();
}

function renderRoundDetail() {
  const rounds = tournamentData.rounds || [];
  if (!rounds.length) return;

  const rd = rounds[activeRoundIdx];
  const tbody = document.querySelector('#round-table tbody');
  tbody.innerHTML = '';

  const strats = rd.strategies || [];
  const sorted = [...strats].sort((a, b) => a.mean_guesses - b.mean_guesses);

  sorted.forEach(s => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${s.name}</td>
      <td>${s.games_played}</td>
      <td>${s.games_solved}</td>
      <td>${(s.solve_rate * 100).toFixed(1)}%</td>
      <td>${s.mean_guesses.toFixed(2)}</td>
      <td>${s.median_guesses}</td>
      <td>${s.max_guesses}</td>
      <td>${s.timed_out}</td>
    `;
    tbody.appendChild(tr);
  });

  destroyCharts(roundCharts);
  roundCharts = [];
  const chartsDiv = document.getElementById('round-charts');
  chartsDiv.innerHTML = '';

  const maxG = (tournamentData.config || {}).max_guesses || 6;

  sorted.forEach(s => {
    const wrapper = document.createElement('div');
    wrapper.className = 'chart-container';
    const canvas = document.createElement('canvas');
    wrapper.appendChild(canvas);
    chartsDiv.appendChild(wrapper);

    const chart = createDistributionChart(canvas, s.name, s.guess_distribution || {}, maxG);
    roundCharts.push(chart);
  });
}

// ── Strategy Comparison ────────────────────────────────────

function renderComparisonControls() {
  const container = document.getElementById('strategy-checkboxes');
  container.innerHTML = '';

  const allNames = new Set();
  (tournamentData.rounds || []).forEach(rd => {
    (rd.strategies || []).forEach(s => allNames.add(s.name));
  });

  const sorted = [...allNames].sort();
  const leaderboard = tournamentData.leaderboard || [];
  const topNames = new Set(leaderboard.slice(0, 5).map(e => e.strategy));
  const manyStrategies = sorted.length > 6;

  sorted.forEach(name => {
    const label = document.createElement('label');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = name;
    cb.checked = manyStrategies ? topNames.has(name) : true;
    cb.onchange = updateComparison;
    label.appendChild(cb);
    label.appendChild(document.createTextNode(' ' + name));
    container.appendChild(label);
  });

  if (manyStrategies) {
    const hint = document.createElement('small');
    hint.style.color = '#999';
    hint.style.display = 'block';
    hint.style.marginTop = '0.3rem';
    hint.textContent = `Mostrando top 5. Selecciona hasta 6 para mejor visualizacion.`;
    container.appendChild(hint);
  }

  updateComparison();
}

function updateComparison() {
  const checked = [...document.querySelectorAll('#strategy-checkboxes input:checked')]
    .map(cb => cb.value);

  const aggDist = {};
  (tournamentData.rounds || []).forEach(rd => {
    (rd.strategies || []).forEach(s => {
      if (!checked.includes(s.name)) return;
      if (!aggDist[s.name]) aggDist[s.name] = {};
      const dist = s.guess_distribution || {};
      for (const [k, v] of Object.entries(dist)) {
        aggDist[s.name][k] = (aggDist[s.name][k] || 0) + v;
      }
    });
  });

  const strategies = Object.entries(aggDist).map(([name, distribution]) => ({
    name, distribution
  }));

  const canvas = document.getElementById('comparison-chart');
  if (comparisonChart) {
    comparisonChart.destroy();
    comparisonChart = null;
  }

  if (strategies.length > 0) {
    const maxG = (tournamentData.config || {}).max_guesses || 6;
    comparisonChart = createComparisonChart(canvas, strategies, maxG);
  }
}

// ── Tournament Control Panel ───────────────────────────────

/**
 * Presets just fill the form — they don't launch.
 */
function selectPreset(preset) {
  const cfg = PRESETS[preset];
  if (!cfg) return;

  document.getElementById('num-games').value = cfg.num_games;
  document.getElementById('repetitions').value = cfg.repetitions;
  document.getElementById('shock').value = Math.round((cfg.shock || 0) * 100);
  document.getElementById('corpus-mode').value = cfg.corpus || 'full';

  // Highlight active preset
  document.querySelectorAll('.btn-preset').forEach(b => b.classList.remove('active'));
  const btnId = { quick: 'btn-quick', official: 'btn-official', real: 'btn-real' };
  const btn = document.getElementById(btnId[preset]);
  if (btn) btn.classList.add('active');

  updateTimeEstimate();
}

/**
 * Launch uses whatever is currently in the form.
 */
function launchTournament() {
  const config = {
    num_games: parseInt(document.getElementById('num-games').value) || 100,
    repetitions: parseInt(document.getElementById('repetitions').value) || 1,
    shock: (parseInt(document.getElementById('shock').value) || 0) / 100,
    corpus: document.getElementById('corpus-mode').value || 'full',
  };

  // Optional tournament name
  const nameEl = document.getElementById('tournament-name');
  const name = nameEl ? nameEl.value.trim() : '';
  if (name) config.name = name;

  // Show time estimate
  const el = document.getElementById('time-estimate');
  if (el) el.textContent = `Tiempo estimado: ${estimateTime(config.num_games, config.repetitions)}`;

  fetch('/api/tournament', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        setStatus('running', data.error);
      } else {
        setStatus('running', 'Torneo iniciado...');
        startStatusPolling();
      }
    })
    .catch(() => {
      setStatus('error', 'Error: el servidor no soporta lanzar torneos. Usa: python3 dashboard/server.py');
    });
}

function stopTournament() {
  fetch('/api/stop', { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      setStatus('idle', data.message || 'Detenido');
      stopStatusPolling();
      hideProgress();
    })
    .catch(() => {});
}

function toggleLog() {
  const el = document.getElementById('tournament-log');
  logVisible = !logVisible;
  el.style.display = logVisible ? 'block' : 'none';
  const link = document.querySelector('#log-toggle a');
  if (link) link.textContent = logVisible ? 'Ocultar log' : 'Ver log del torneo';
}

// ── Progress Tracking ─────────────────────────────────────

const CANONICAL_ROUNDS = [
  '4-letter uniform', '4-letter frequency',
  '5-letter uniform', '5-letter frequency',
  '6-letter uniform', '6-letter frequency',
];

function parseProgress(lines) {
  const doneRounds = [];
  let currentRound = null;

  for (const line of lines) {
    const roundMatch = line.match(/ROUND:\s+(.+?)(?:\s+\(rep|$)/);
    if (roundMatch) {
      currentRound = roundMatch[1].trim();
    }
    if (line.includes('Elapsed:') && currentRound) {
      doneRounds.push(currentRound);
      currentRound = null;
    }
  }

  let totalRounds = 6;
  for (const line of lines) {
    const configMatch = line.match(/Rounds:\s+(\d+)\s+configs\s+x\s+(\d+)\s+repetition/);
    if (configMatch) {
      totalRounds = parseInt(configMatch[1]) * parseInt(configMatch[2]);
      break;
    }
  }

  return { doneRounds, currentRound, totalRounds };
}

function updateProgress(lines) {
  const { doneRounds, currentRound, totalRounds } = parseProgress(lines);
  const container = document.getElementById('progress-bar-container');

  if (doneRounds.length === 0 && !currentRound) {
    container.style.display = 'none';
    return;
  }

  container.style.display = 'block';
  const pct = Math.round((doneRounds.length / totalRounds) * 100);
  document.getElementById('progress-fill').style.width = pct + '%';
  document.getElementById('progress-text').textContent =
    `${doneRounds.length}/${totalRounds} rondas completadas`;

  const roundsDiv = document.getElementById('progress-rounds');
  roundsDiv.innerHTML = '';
  CANONICAL_ROUNDS.forEach(name => {
    const chip = document.createElement('span');
    chip.className = 'progress-round';
    if (doneRounds.includes(name)) {
      chip.classList.add('done');
      chip.textContent = '\u2713 ' + name;
    } else if (currentRound === name) {
      chip.classList.add('running');
      chip.textContent = '\u25B6 ' + name;
    } else {
      chip.classList.add('pending');
      chip.textContent = name;
    }
    roundsDiv.appendChild(chip);
  });
}

function hideProgress() {
  document.getElementById('progress-bar-container').style.display = 'none';
}

// ── Status Polling ─────────────────────────────────────────

function pollStatus() {
  fetch('/api/status')
    .then(r => r.json())
    .then(data => {
      if (data.state === 'running') {
        setStatus('running', 'Torneo en ejecucion...');
        startStatusPolling();
      } else if (data.state === 'finished') {
        const msg = data.exit_code === 0 ? 'Torneo completado' : `Torneo termino con error (code ${data.exit_code})`;
        setStatus(data.exit_code === 0 ? 'finished' : 'error', msg);
        loadData();
        loadRuns();
      }
    })
    .catch(() => {});
}

function startStatusPolling() {
  if (statusPollTimer) return;
  statusPollTimer = setInterval(async () => {
    try {
      const resp = await fetch('/api/status');
      const data = await resp.json();

      if (data.state === 'running') {
        setStatus('running', `Torneo en ejecucion... (${data.output_line_count || 0} lineas)`);
        const logResp = await fetch('/api/log');
        const logData = await logResp.json();
        const lines = logData.lines || [];
        const logEl = document.getElementById('tournament-log');
        logEl.textContent = lines.join('\n');
        logEl.scrollTop = logEl.scrollHeight;
        document.getElementById('log-toggle').style.display = 'block';
        updateProgress(lines);
      } else if (data.state === 'finished' || data.state === 'stopped') {
        const msg = data.state === 'finished' && data.exit_code === 0
          ? 'Torneo completado'
          : `Torneo ${data.state} (code ${data.exit_code || 0})`;
        setStatus(data.exit_code === 0 ? 'finished' : 'error', msg);
        stopStatusPolling();
        if (data.state === 'finished') hideProgress();
        loadData();
        loadRuns();
      }
    } catch {
      stopStatusPolling();
    }
  }, 2000);
}

function stopStatusPolling() {
  if (statusPollTimer) {
    clearInterval(statusPollTimer);
    statusPollTimer = null;
  }
}

function setStatus(state, text) {
  const container = document.getElementById('tournament-status');
  const textEl = document.getElementById('status-text');
  const stopBtn = document.getElementById('btn-stop');
  const launchBtn = document.getElementById('btn-launch');

  container.className = 'status-' + state;
  textEl.textContent = text;

  if (state === 'running') {
    stopBtn.disabled = false;
    if (launchBtn) launchBtn.disabled = true;
  } else {
    stopBtn.disabled = true;
    if (launchBtn) launchBtn.disabled = false;
  }
}

// ── Utilities ──────────────────────────────────────────────

function destroyCharts(charts) {
  charts.forEach(c => { if (c) c.destroy(); });
}
