// Dept Overlap Tab — attendance grid by department

import AppState from '../state/app-state.js';

let _refreshingCombo = false;

export function init() {
  AppState.on('solutionListChanged', _refreshCombo);
  AppState.on('activeSolutionChanged', _onSolutionChanged);
  AppState.on('dataLoaded', _refreshDeptSelect);

  document.getElementById('dept-solution-select').addEventListener('change', (e) => {
    if (_refreshingCombo) return;
    const sol = AppState.solutions.find(s => s.solution_id === e.target.value);
    if (sol) _renderGrid(sol, document.getElementById('dept-select').value);
  });

  document.getElementById('dept-select').addEventListener('change', (e) => {
    const sol = _getSelectedSolution();
    if (sol) _renderGrid(sol, e.target.value);
  });

  _refreshCombo();
}

function _refreshCombo() {
  _refreshingCombo = true;
  const sel = document.getElementById('dept-solution-select');
  const current = sel.value;
  sel.innerHTML = '<option value="">— Select solution —</option>';
  for (const sol of AppState.solutions) {
    const opt = document.createElement('option');
    opt.value = sol.solution_id;
    opt.textContent = `${sol.solution_id} (${(sol.score * 100).toFixed(1)}%)`;
    sel.appendChild(opt);
  }
  if (AppState.activeSolution) {
    sel.value = AppState.activeSolution.solution_id;
  } else if (current) {
    sel.value = current;
  }
  _refreshingCombo = false;
}

function _refreshDeptSelect() {
  const sel = document.getElementById('dept-select');
  const current = sel.value;
  sel.innerHTML = '<option value="">— Select department —</option>';
  for (const dept of Object.keys(AppState.deptMap).sort()) {
    const opt = document.createElement('option');
    opt.value = dept;
    opt.textContent = dept;
    sel.appendChild(opt);
  }
  if (current) sel.value = current;
}

function _onSolutionChanged(sol) {
  _refreshCombo();
  _renderGrid(sol, document.getElementById('dept-select').value);
}

function _getSelectedSolution() {
  const id = document.getElementById('dept-solution-select').value;
  return AppState.solutions.find(s => s.solution_id === id) || null;
}

function _renderGrid(sol, dept) {
  const container = document.getElementById('dept-overlap-grid');
  container.innerHTML = '';
  if (!sol || !dept) return;

  const gids = AppState.deptMap[dept] || [];
  if (!gids.length) {
    container.textContent = 'No groups in this department.';
    return;
  }

  const dayAssignMap = Object.fromEntries(sol.day_assignments.map(da => [da.group_id, new Set(da.days)]));

  const tbl = document.createElement('table');
  tbl.className = 'data-table dept-overlap-table';

  const thead = tbl.createTHead();
  const hr = thead.insertRow();
  ['Group', 'Day 1', 'Day 2', 'Day 3', 'Day 4'].forEach(h => {
    const th = document.createElement('th');
    th.textContent = h;
    hr.appendChild(th);
  });

  const tbody = tbl.createTBody();
  for (const gid of gids) {
    const days = dayAssignMap[gid] || new Set();
    const color = AppState.groupColor(gid);
    const tr = tbody.insertRow();
    const nameTd = tr.insertCell();
    nameTd.textContent = gid;
    nameTd.style.fontWeight = '500';

    for (const d of [1, 2, 3, 4]) {
      const td = tr.insertCell();
      td.style.textAlign = 'center';
      if (days.has(d)) {
        td.style.background = color;
        td.style.color = '#fff';
        td.textContent = '●';
      } else {
        td.style.background = '#F7FAFC';
      }
    }
  }

  tbl.appendChild(tbody);
  container.appendChild(tbl);
}
