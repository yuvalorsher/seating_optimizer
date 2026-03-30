// Solve Tab — run solver, display results

import AppState from '../state/app-state.js';
import { pickFile } from '../utils/file-io.js';
import * as persistence from '../utils/persistence.js';

const PYTHON_FILES = [
  '__init__.py', 'models.py', 'loader.py', 'constraints.py',
  'scorer.py', 'solver.py', 'updater.py', 'persistence.py',
];

let _worker = null;
let _workerReady = false;
let _workerCallbacks = {};
let _employeesCsvText = null;
let _coldSeatsCsvText = null;
let _lastSolveResults = [];

export function init() {
  _bindUI();
  AppState.on('solutionListChanged', _refreshResultsList);
  AppState.on('dataLoaded', () => {
    _updateStatusBar();
    _resetWorkerIfNeeded();
  });
  // Static click delegation on the results table (not per-refresh)
  document.getElementById('solve-results-table').addEventListener('click', _onResultAction);
}

function _bindUI() {
  document.getElementById('solve-override-map-btn').addEventListener('click', _pickOfficeMap);
  document.getElementById('solve-reset-map-btn').addEventListener('click', _resetOfficeMap);
  document.getElementById('solve-employees-btn').addEventListener('click', _pickEmployees);
  document.getElementById('solve-cold-seats-btn').addEventListener('click', _pickColdSeats);
  document.getElementById('solve-no-cold-seats').addEventListener('change', _onNoColdSeatsToggle);
  document.getElementById('solve-run-btn').addEventListener('click', _runSolver);
}

function _updateStatusBar() {
  const el = document.getElementById('solve-status-bar');
  if (!el) return;
  const b = AppState.blocks.length;
  const g = AppState.groups.length;
  const e = Object.values(AppState.employeesByGroup).reduce((s, arr) => s + arr.length, 0);
  el.textContent = b > 0 || g > 0
    ? `${b} blocks · ${g} groups · ${e} employees`
    : 'Load employees CSV to begin.';
}

async function _pickOfficeMap() {
  try {
    const { text } = await pickFile('.csv');
    const blocks = await AppState.parseOfficeMapCSV(text);
    persistence.saveOfficeMapOverride(text);
    AppState.reloadBlocks(blocks);
    document.getElementById('solve-map-name').textContent = 'Custom (saved)';
    document.getElementById('solve-reset-map-btn').style.display = '';
    _resetWorkerIfNeeded();
  } catch (e) {
    if (e.message !== 'No file selected') alert('Error loading office map: ' + e.message);
  }
}

function _resetOfficeMap() {
  persistence.clearOfficeMapOverride();
  document.getElementById('solve-map-name').textContent = 'Default';
  document.getElementById('solve-reset-map-btn').style.display = 'none';
  // Reload default blocks from Pyodide
  AppState._pyodide.runPython(`
import json
from seating_optimizer.loader import load_office_map
_reload_blocks = load_office_map('/tmp/office_map.csv')
_reload_blocks_json = json.dumps([
    {'block_id': b.block_id, 'row': b.row, 'col': b.col, 'capacity': b.capacity}
    for b in _reload_blocks
])
`);
  const blocks = JSON.parse(AppState._pyodide.globals.get('_reload_blocks_json'));
  AppState.reloadBlocks(blocks);
  _resetWorkerIfNeeded();
}

async function _pickEmployees() {
  try {
    const { name, text } = await pickFile('.csv');
    _employeesCsvText = text;
    document.getElementById('solve-employees-name').textContent = name;
    const { groups, employeesByGroup, deptMap } = await AppState.parseEmployeesCSV(text);
    AppState.loadEmployeesData(groups, employeesByGroup, deptMap);
    _resetWorkerIfNeeded();
  } catch (e) {
    if (e.message !== 'No file selected') alert('Error loading employees: ' + e.message);
  }
}

async function _pickColdSeats() {
  try {
    const { name, text } = await pickFile('.csv');
    _coldSeatsCsvText = text;
    document.getElementById('solve-cold-seats-name').textContent = name;
    const cs = await AppState.parseColdSeatsCSV(text);
    AppState.setColdSeats(cs);
    _resetWorkerIfNeeded();
  } catch (e) {
    if (e.message !== 'No file selected') alert('Error loading cold seats: ' + e.message);
  }
}

function _onNoColdSeatsToggle(e) {
  const disabled = e.target.checked;
  document.getElementById('solve-cold-seats-btn').disabled = disabled;
  if (disabled) {
    _coldSeatsCsvText = null;
    AppState.setColdSeats({});
    document.getElementById('solve-cold-seats-name').textContent = 'None';
    _resetWorkerIfNeeded();
  }
}

function _resetWorkerIfNeeded() {
  _workerReady = false;
  if (_worker) { _worker.terminate(); _worker = null; }
  AppState._worker = null;
}

async function _ensureWorkerReady() {
  if (_workerReady) return;
  if (!_employeesCsvText) throw new Error('Please upload an employees CSV first.');
  if (!AppState.blocks.length) throw new Error('No office map loaded.');

  // Fetch Python files for worker
  const pyFiles = [];
  for (const fname of PYTHON_FILES) {
    const res = await fetch(`python/seating_optimizer/${fname}`);
    const text = await res.text();
    pyFiles.push([fname, text]);
  }

  const officeMapCsv = persistence.getOfficeMapOverride()
    || await fetch('python/data/office_map.csv').then(r => r.text());

  // Use uploaded cold seats, or fall back to default, or empty
  let coldSeatsCsv = _coldSeatsCsvText;
  if (!coldSeatsCsv) {
    try {
      const res = await fetch('python/data/cold_seats.csv');
      if (res.ok) coldSeatsCsv = await res.text();
    } catch (e) { /* no default cold seats */ }
  }

  _worker = new Worker('./worker/solver.worker.js');
  AppState._worker = _worker;

  await new Promise((resolve, reject) => {
    _worker.onmessage = (e) => {
      const msg = e.data;
      if (msg.type === 'ready') { resolve(); }
      else if (msg.type === 'error') { reject(new Error(msg.message)); }
      else if (msg.type === 'status') {
        _setStatus(msg.text);
      }
    };
    _worker.postMessage({
      type: 'init',
      pyFiles,
      officeMapCsv,
      employeesCsv: _employeesCsvText,
      coldSeatsCsv: coldSeatsCsv || '',
    });
  });

  _workerReady = true;
}

async function _runSolver() {
  const runBtn = document.getElementById('solve-run-btn');
  const progress = document.getElementById('solve-progress');
  const nSolutions = parseInt(document.getElementById('solve-n-solutions').value) || 5;
  const maxIters = parseInt(document.getElementById('solve-max-iters').value) || 20;
  const seedStr = document.getElementById('solve-seed').value.trim();
  const seed = seedStr ? parseInt(seedStr) : Math.floor(Math.random() * 1e9);

  runBtn.disabled = true;
  progress.style.display = '';
  progress.removeAttribute('value');
  _setStatus('Initializing...');

  try {
    await _ensureWorkerReady();

    _lastSolveResults = [];

    const results = await new Promise((resolve, reject) => {
      _worker.onmessage = (e) => {
        const msg = e.data;
        if (msg.type === 'progress') {
          progress.value = msg.current;
          progress.max = msg.total;
        } else if (msg.type === 'solve_result') {
          resolve(msg.solutions);
        } else if (msg.type === 'error') {
          reject(new Error(msg.message));
        }
      };
      _worker.postMessage({ type: 'solve', nSolutions, maxIters, seed });
    });

    _lastSolveResults = results;
    results.forEach(sol => AppState.addSolution(sol));
    _setStatus(`Done — ${results.length} solution(s) found.`);
  } catch (err) {
    alert('Solver error: ' + err.message);
    _setStatus('');
  } finally {
    runBtn.disabled = false;
    progress.style.display = 'none';
  }
}

function _setStatus(text) {
  const el = document.getElementById('solve-status-msg');
  if (el) el.textContent = text;
}

function _refreshResultsList() {
  const tbody = document.querySelector('#solve-results-table tbody');
  if (!tbody) return;
  tbody.innerHTML = '';

  for (const sol of AppState.solutions) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${(sol.score * 100).toFixed(1)}%</td>
      <td>${((sol.score_breakdown?.compactness || 0) * 100).toFixed(1)}%</td>
      <td>${((sol.score_breakdown?.consistency || 0) * 100).toFixed(1)}%</td>
      <td>Days ${(sol.cover_pair || []).join(' & ')}</td>
      <td>
        <button class="btn-sm" data-action="visualize" data-id="${sol.solution_id}">Visualize</button>
        <button class="btn-sm" data-action="export" data-id="${sol.solution_id}">Export</button>
        <button class="btn-sm btn-danger" data-action="delete" data-id="${sol.solution_id}">Delete</button>
      </td>
    `;
    tbody.appendChild(tr);
  }

  // Also render schedule for active solution
  if (AppState.activeSolution) _renderScheduleTable(AppState.activeSolution);
}

function _onResultAction(e) {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  const { action, id } = btn.dataset;
  const sol = AppState.solutions.find(s => s.solution_id === id);
  if (!sol) return;

  if (action === 'visualize') {
    AppState.setActiveSolution(sol);
    document.querySelector('[data-tab="visualize"]').click();
  } else if (action === 'export') {
    persistence.exportSolution(sol);
  } else if (action === 'delete') {
    if (confirm(`Delete solution ${id}?`)) AppState.deleteSolution(id);
  }
}

function _renderScheduleTable(solution) {
  const container = document.getElementById('solve-schedule-container');
  if (!container) return;
  container.innerHTML = '';

  if (!solution) return;

  const tbl = document.createElement('table');
  tbl.className = 'data-table';

  const thead = tbl.createTHead();
  const hr = thead.insertRow();
  ['Group', 'Dept(s)', 'Size', 'Day 1 → Blocks', 'Day 2 → Blocks', 'Single Block']
    .forEach(h => {
      const th = document.createElement('th');
      th.textContent = h;
      hr.appendChild(th);
    });

  const tbody = tbl.createTBody();
  for (const da of solution.day_assignments) {
    const g = AppState.groupsById[da.group_id];
    const [d1, d2] = da.days;
    const getBlocks = (day) => solution.block_assignments
      .filter(ba => ba.group_id === da.group_id && ba.day === day)
      .map(ba => `${ba.block_id}(${ba.count})`)
      .join(', ');
    const bs1 = new Set(solution.block_assignments.filter(ba => ba.group_id === da.group_id && ba.day === d1).map(ba => ba.block_id));
    const bs2 = new Set(solution.block_assignments.filter(ba => ba.group_id === da.group_id && ba.day === d2).map(ba => ba.block_id));
    const single = bs1.size === 1 && bs2.size === 1 && [...bs1][0] === [...bs2][0];

    const tr = tbody.insertRow();
    tr.innerHTML = `
      <td>${da.group_id}</td>
      <td>${g ? (Array.isArray(g.departments) ? g.departments : Object.keys(g.departments)).join(', ') : ''}</td>
      <td>${g ? g.size : ''}</td>
      <td>Day ${d1} → ${getBlocks(d1) || '—'}</td>
      <td>Day ${d2} → ${getBlocks(d2) || '—'}</td>
      <td>${single ? '✓' : ''}</td>
    `;
  }

  const title = document.createElement('h3');
  title.style.cssText = 'margin-top:20px; font-size:14px;';
  title.textContent = `Schedule — Solution ${solution.solution_id}`;
  container.appendChild(title);
  container.appendChild(tbl);
}
