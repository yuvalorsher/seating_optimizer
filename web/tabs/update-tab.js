// Update Tab — resize groups and recompute solution

import AppState from '../state/app-state.js';
import * as persistence from '../utils/persistence.js';
import { exportToPDF } from '../utils/print.js';

let _updatedSolution = null;
let _refreshingCombo = false;

export function init() {
  AppState.on('solutionListChanged', _refreshCombo);

  document.getElementById('upd-solution-select').addEventListener('change', (e) => {
    if (_refreshingCombo) return;
    const sol = AppState.solutions.find(s => s.solution_id === e.target.value);
    if (sol) _loadSolutionSizes(sol);
  });

  document.getElementById('upd-run-btn').addEventListener('click', _runUpdate);
  document.getElementById('upd-save-btn').addEventListener('click', _saveUpdated);
  document.getElementById('upd-export-btn').addEventListener('click', _exportPDF);

  _refreshCombo();
}

function _refreshCombo() {
  _refreshingCombo = true;
  const sel = document.getElementById('upd-solution-select');
  const current = sel.value;
  sel.innerHTML = '<option value="">— Select solution —</option>';
  for (const sol of AppState.solutions) {
    const opt = document.createElement('option');
    opt.value = sol.solution_id;
    opt.textContent = `${sol.solution_id} (${(sol.score * 100).toFixed(1)}%)`;
    sel.appendChild(opt);
  }
  if (current) sel.value = current;
  _refreshingCombo = false;
}

function _loadSolutionSizes(sol) {
  const tbody = document.querySelector('#upd-sizes-table tbody');
  if (!tbody) return;
  tbody.innerHTML = '';
  _updatedSolution = null;
  _setActionsEnabled(false);

  for (const da of sol.day_assignments) {
    const g = AppState.groupsById[da.group_id];
    const currentSize = g ? g.size : 0;
    const tr = tbody.insertRow();
    tr.innerHTML = `
      <td>${da.group_id}</td>
      <td>${currentSize}</td>
      <td><input type="number" min="1" max="200" value="${currentSize}" data-group-id="${da.group_id}" class="size-input" style="width:70px"></td>
    `;
  }
}

async function _runUpdate() {
  const sel = document.getElementById('upd-solution-select');
  const baseSol = AppState.solutions.find(s => s.solution_id === sel.value);
  if (!baseSol) { alert('Select a base solution first.'); return; }
  if (!AppState._worker) { alert('Please run the solver first (to initialize the worker).'); return; }

  // Collect size overrides
  const overrides = {};
  document.querySelectorAll('#upd-sizes-table .size-input').forEach(input => {
    const gid = input.dataset.groupId;
    const newSize = parseInt(input.value);
    const g = AppState.groupsById[gid];
    if (g && newSize !== g.size) {
      overrides[gid] = newSize;
    }
  });

  const runBtn = document.getElementById('upd-run-btn');
  const progress = document.getElementById('upd-progress');
  runBtn.disabled = true;
  progress.style.display = '';
  progress.removeAttribute('value');

  try {
    const result = await new Promise((resolve, reject) => {
      AppState._worker.onmessage = (e) => {
        const msg = e.data;
        if (msg.type === 'update_result') resolve(msg.solution);
        else if (msg.type === 'error') reject(new Error(msg.message));
        else if (msg.type === 'progress') {
          progress.value = msg.current;
          progress.max = msg.total;
        }
      };
      AppState._worker.postMessage({
        type: 'update',
        solutionDict: baseSol,
        sizeOverrides: overrides,
      });
    });

    _updatedSolution = result;
    _renderDiffTable(baseSol, result, overrides);
    _setActionsEnabled(true);
  } catch (err) {
    alert('Update error: ' + err.message);
  } finally {
    runBtn.disabled = false;
    progress.style.display = 'none';
  }
}

function _renderDiffTable(oldSol, newSol, sizeOverrides) {
  const container = document.getElementById('upd-diff-container');
  container.innerHTML = '';

  const tbl = document.createElement('table');
  tbl.className = 'data-table';

  const thead = tbl.createTHead();
  const hr = thead.insertRow();
  ['Group', 'Size', 'Day 1', 'Day 2', 'Block(s) Day 1', 'Block(s) Day 2'].forEach(h => {
    const th = document.createElement('th');
    th.textContent = h;
    hr.appendChild(th);
  });

  const oldDayMap = Object.fromEntries(oldSol.day_assignments.map(da => [da.group_id, da.days]));
  const newDayMap = Object.fromEntries(newSol.day_assignments.map(da => [da.group_id, da.days]));
  const getBlocks = (sol, gid, day) => sol.block_assignments
    .filter(ba => ba.group_id === gid && ba.day === day)
    .map(ba => `${ba.block_id}(${ba.count})`).join(', ');

  const tbody = tbl.createTBody();
  for (const da of newSol.day_assignments) {
    const gid = da.group_id;
    const g = AppState.groupsById[gid];
    const oldDays = oldDayMap[gid] || [];
    const newDays = da.days;
    const [nd1, nd2] = newDays;
    const sizeChanged = gid in sizeOverrides;
    const daysChanged = oldDays.join(',') !== newDays.join(',');
    const oldB1 = getBlocks(oldSol, gid, oldDays[0]);
    const oldB2 = getBlocks(oldSol, gid, oldDays[1]);
    const newB1 = getBlocks(newSol, gid, nd1);
    const newB2 = getBlocks(newSol, gid, nd2);
    const blocksChanged = oldB1 !== newB1 || oldB2 !== newB2;

    const tr = tbody.insertRow();

    const nameCell = tr.insertCell();
    nameCell.textContent = gid;

    const sizeCell = tr.insertCell();
    sizeCell.textContent = g ? (sizeChanged ? `${g.size} → ${sizeOverrides[gid]}` : g.size) : '';
    if (sizeChanged) sizeCell.style.background = '#BEE3F8';

    const d1Cell = tr.insertCell();
    d1Cell.textContent = `Day ${nd1}`;
    if (daysChanged) d1Cell.style.background = '#FED7D7';

    const d2Cell = tr.insertCell();
    d2Cell.textContent = `Day ${nd2}`;
    if (daysChanged) d2Cell.style.background = '#FED7D7';

    const b1Cell = tr.insertCell();
    b1Cell.textContent = newB1 || '—';
    if (blocksChanged) b1Cell.style.background = '#C6F6D5';

    const b2Cell = tr.insertCell();
    b2Cell.textContent = newB2 || '—';
    if (blocksChanged) b2Cell.style.background = '#C6F6D5';
  }

  container.appendChild(tbl);
}

function _setActionsEnabled(enabled) {
  document.getElementById('upd-save-btn').disabled = !enabled;
  document.getElementById('upd-export-btn').disabled = !enabled;
}

function _saveUpdated() {
  if (!_updatedSolution) return;
  AppState.addSolution(_updatedSolution);
  AppState.setActiveSolution(_updatedSolution);
  alert(`Solution ${_updatedSolution.solution_id} saved.`);
}

function _exportPDF() {
  if (!_updatedSolution) return;
  exportToPDF(_updatedSolution, AppState.blocks, AppState.groupsById, AppState.deptMap);
}
