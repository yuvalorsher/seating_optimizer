// Visualize Tab — display solution on office grid

import AppState from '../state/app-state.js';
import { OfficeGrid } from '../components/office-grid.js';
import { exportToPDF } from '../utils/print.js';
import * as persistence from '../utils/persistence.js';

let _grid = null;
let _refreshingCombo = false;

export function init() {
  _grid = new OfficeGrid(document.getElementById('viz-grid'));

  AppState.on('solutionListChanged', _refreshCombo);
  AppState.on('activeSolutionChanged', _onSolutionChanged);
  AppState.on('activeDayChanged', _onDayChanged);

  // Day buttons
  document.querySelectorAll('.viz-day-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      AppState.setActiveDay(parseInt(btn.dataset.day));
    });
  });

  // Zoom
  document.getElementById('viz-zoom-in').addEventListener('click', () => _grid.zoomIn());
  document.getElementById('viz-zoom-out').addEventListener('click', () => _grid.zoomOut());
  document.getElementById('viz-zoom-fit').addEventListener('click', () => _grid.fitToContainer());

  // Solution select
  document.getElementById('viz-solution-select').addEventListener('change', (e) => {
    if (_refreshingCombo) return;
    const sol = AppState.solutions.find(s => s.solution_id === e.target.value);
    if (sol) AppState.setActiveSolution(sol);
  });

  // Export PDF
  document.getElementById('viz-export-pdf').addEventListener('click', () => {
    if (!AppState.activeSolution) return;
    exportToPDF(AppState.activeSolution, AppState.blocks, AppState.groupsById, AppState.deptMap);
  });

  // Import solution JSON
  document.getElementById('viz-import-btn').addEventListener('click', _importSolution);

  // Legend hover: highlight group in grid
  document.getElementById('viz-legend').addEventListener('mouseenter', (e) => {
    const chip = e.target.closest('[data-group-id]');
    if (chip) _grid.highlightGroup(chip.dataset.groupId);
  }, true);
  document.getElementById('viz-legend').addEventListener('mouseleave', (e) => {
    const chip = e.target.closest('[data-group-id]');
    if (chip) _grid.clearHighlight();
  }, true);

  _refreshCombo();
}

function _refreshCombo() {
  _refreshingCombo = true;
  const sel = document.getElementById('viz-solution-select');
  const current = sel.value;
  sel.innerHTML = '<option value="">— Select solution —</option>';
  for (const sol of AppState.solutions) {
    const opt = document.createElement('option');
    opt.value = sol.solution_id;
    opt.textContent = `${sol.solution_id} (${(sol.score * 100).toFixed(1)}%)`;
    sel.appendChild(opt);
  }
  // Restore selection
  if (AppState.activeSolution) {
    sel.value = AppState.activeSolution.solution_id;
  } else if (current) {
    sel.value = current;
  }
  _refreshingCombo = false;
}

function _onSolutionChanged(sol) {
  _refreshCombo();
  _updateMetricsBar(sol);
  _buildLegend(sol);
  _renderGrid();
  _renderTables(sol);
}

function _onDayChanged() {
  _updateDayButtons();
  _renderGrid();
}

function _updateDayButtons() {
  document.querySelectorAll('.viz-day-btn').forEach(btn => {
    btn.classList.toggle('active', parseInt(btn.dataset.day) === AppState.activeDay);
  });
}

function _updateMetricsBar(sol) {
  const el = document.getElementById('viz-metrics');
  if (!sol) { el.textContent = ''; return; }
  el.innerHTML = `
    <span><strong>Score:</strong> ${(sol.score * 100).toFixed(1)}%</span>
    <span><strong>Compactness:</strong> ${((sol.score_breakdown?.compactness || 0) * 100).toFixed(1)}%</span>
    <span><strong>Consistency:</strong> ${((sol.score_breakdown?.consistency || 0) * 100).toFixed(1)}%</span>
    <span><strong>Cover:</strong> Days ${(sol.cover_pair || []).join(' & ')}</span>
    <span><strong>ID:</strong> ${sol.solution_id}</span>
  `;
}

function _buildLegend(sol) {
  const container = document.getElementById('viz-legend');
  container.innerHTML = '';
  if (!sol) return;

  const groups = [...new Set(sol.day_assignments.map(da => da.group_id))];
  for (const gid of groups) {
    const chip = document.createElement('span');
    chip.className = 'legend-chip';
    chip.dataset.groupId = gid;
    chip.style.backgroundColor = AppState.groupColor(gid);
    chip.textContent = gid;
    chip.title = gid;
    container.appendChild(chip);
  }
}

function _renderGrid() {
  const sol = AppState.activeSolution;
  if (!sol || !AppState.blocks.length) {
    _grid.load([], {});
    return;
  }
  const dayView = _getDayView(sol, AppState.activeDay);
  _grid.load(AppState.blocks, dayView, AppState.employeesByGroup);
  setTimeout(() => _grid.fitToContainer(), 50);
}

function _getDayView(sol, day) {
  const view = {};
  for (const ba of sol.block_assignments) {
    if (ba.day === day) {
      if (!view[ba.block_id]) view[ba.block_id] = [];
      view[ba.block_id].push([ba.group_id, ba.count]);
    }
  }
  return view;
}

function _renderTables(sol) {
  _renderBlockTable(sol);
  _renderGroupTable(sol);
}

function _renderBlockTable(sol) {
  const tbody = document.querySelector('#viz-block-table tbody');
  if (!tbody) return;
  tbody.innerHTML = '';
  if (!sol) return;

  const day = AppState.activeDay;
  const occupancy = {};
  sol.block_assignments.filter(ba => ba.day === day).forEach(ba => {
    occupancy[ba.block_id] = (occupancy[ba.block_id] || 0) + ba.count;
  });

  for (const block of AppState.blocks) {
    const used = occupancy[block.block_id] || 0;
    const tr = tbody.insertRow();
    tr.innerHTML = `<td>${block.block_id}</td><td>${used}/${block.capacity}</td>`;
    if (used > block.capacity) tr.style.color = '#E74C3C';
  }
}

function _renderGroupTable(sol) {
  const tbody = document.querySelector('#viz-group-table tbody');
  if (!tbody) return;
  tbody.innerHTML = '';
  if (!sol) return;

  for (const da of sol.day_assignments) {
    const g = AppState.groupsById[da.group_id];
    const tr = tbody.insertRow();
    const depts = g ? (Array.isArray(g.departments) ? g.departments : Object.keys(g.departments)).join(', ') : '';
    tr.innerHTML = `<td>${da.group_id}</td><td>${depts}</td><td>${g ? g.size : ''}</td><td>${da.days.join(', ')}</td>`;
  }
}

async function _importSolution() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.json';
  input.onchange = async () => {
    const file = input.files[0];
    if (!file) return;
    try {
      const text = await file.text();
      const dict = JSON.parse(text);
      AppState.addSolution(dict);
      AppState.setActiveSolution(dict);
    } catch (e) {
      alert('Failed to import solution: ' + e.message);
    }
  };
  input.click();
}
