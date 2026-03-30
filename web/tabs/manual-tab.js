// Manual Tab — interactive drag-drop seating editor

import AppState from '../state/app-state.js';
import { OfficeGrid } from '../components/office-grid.js';
import { pickFile } from '../utils/file-io.js';
import { groupColor } from '../utils/colors.js';
import * as persistence from '../utils/persistence.js';

// ---- ManualState ----

class ManualState {
  constructor() {
    this.dayAssignments = {};   // {group_id: [day, ...]}
    this.blockAssignments = []; // [{group_id, day, block_id, count}]
  }

  getPendingGroups(day) {
    const seated = new Set(
      this.blockAssignments.filter(ba => ba.day === day).map(ba => ba.group_id)
    );
    return Object.entries(this.dayAssignments)
      .filter(([gid, days]) => days.includes(day) && !seated.has(gid))
      .map(([gid]) => gid);
  }

  getSeatedCount(groupId, day) {
    return this.blockAssignments
      .filter(ba => ba.group_id === groupId && ba.day === day)
      .reduce((s, ba) => s + ba.count, 0);
  }

  getDayView(day) {
    const view = {};
    for (const ba of this.blockAssignments) {
      if (ba.day === day) {
        if (!view[ba.block_id]) view[ba.block_id] = [];
        view[ba.block_id].push([ba.group_id, ba.count]);
      }
    }
    return view;
  }

  assignDay(groupId, day) {
    if (!this.dayAssignments[groupId]) this.dayAssignments[groupId] = [];
    const days = this.dayAssignments[groupId];
    if (!days.includes(day) && days.length < 2) {
      days.push(day);
      days.sort((a, b) => a - b);
    }
  }

  removeDay(groupId, day) {
    if (this.dayAssignments[groupId]) {
      this.dayAssignments[groupId] = this.dayAssignments[groupId].filter(d => d !== day);
      if (!this.dayAssignments[groupId].length) delete this.dayAssignments[groupId];
    }
    this.blockAssignments = this.blockAssignments.filter(
      ba => !(ba.group_id === groupId && ba.day === day)
    );
  }

  seatGroup(groupId, day, blockId, count) {
    const existing = this.blockAssignments.find(
      ba => ba.group_id === groupId && ba.day === day && ba.block_id === blockId
    );
    if (existing) {
      existing.count = count;
    } else {
      this.blockAssignments.push({ group_id: groupId, day, block_id: blockId, count });
    }
  }

  unseatFromBlock(groupId, day, blockId) {
    this.blockAssignments = this.blockAssignments.filter(
      ba => !(ba.group_id === groupId && ba.day === day && ba.block_id === blockId)
    );
  }

  unseatAllBlocks(groupId, day) {
    this.blockAssignments = this.blockAssignments.filter(
      ba => !(ba.group_id === groupId && ba.day === day)
    );
  }

  clearGroup(groupId) {
    delete this.dayAssignments[groupId];
    this.blockAssignments = this.blockAssignments.filter(ba => ba.group_id !== groupId);
  }

  detectCoverPair() {
    const twoDay = Object.entries(this.dayAssignments)
      .filter(([, days]) => days.length === 2)
      .map(([gid]) => gid);
    if (!twoDay.length) return null;

    for (let d1 = 1; d1 <= 4; d1++) {
      for (let d2 = d1 + 1; d2 <= 4; d2++) {
        if (twoDay.every(gid => {
          const days = this.dayAssignments[gid];
          return days.includes(d1) || days.includes(d2);
        })) return [d1, d2];
      }
    }
    return null;
  }

  computeWarnings(groupsById, blocksById, deptMap, coldSeats) {
    const warnings = [];

    // Groups with != 2 days
    for (const [gid, days] of Object.entries(this.dayAssignments)) {
      if (days.length !== 2) {
        warnings.push(`${gid}: assigned ${days.length} day(s) — need exactly 2`);
      }
    }

    // Dept overlap
    for (const [dept, gids] of Object.entries(deptMap || {})) {
      const present = gids.filter(gid => (this.dayAssignments[gid] || []).length === 2);
      for (let i = 0; i < present.length; i++) {
        for (let j = i + 1; j < present.length; j++) {
          const d1 = new Set(this.dayAssignments[present[i]]);
          const d2 = new Set(this.dayAssignments[present[j]]);
          if (![...d1].some(d => d2.has(d))) {
            warnings.push(`Dept '${dept}': ${present[i]} and ${present[j]} share no common day`);
          }
        }
      }
    }

    // Seated count
    for (const [gid, days] of Object.entries(this.dayAssignments)) {
      const g = groupsById[gid];
      if (!g) continue;
      for (const day of days) {
        const seated = this.getSeatedCount(gid, day);
        if (seated !== g.size) {
          const diff = seated - g.size;
          warnings.push(`${gid} Day ${day}: seated ${seated}/${g.size} (${diff >= 0 ? '+' : ''}${diff})`);
        }
      }
    }

    // Block over capacity
    const load = {};
    for (const ba of this.blockAssignments) {
      const key = `${ba.block_id}:${ba.day}`;
      load[key] = (load[key] || 0) + ba.count;
    }
    for (const [key, used] of Object.entries(load)) {
      const [blockId, dayStr] = key.split(':');
      const block = blocksById[blockId];
      if (block && used > block.capacity) {
        warnings.push(`Block ${blockId} Day ${dayStr}: over capacity (${used}/${block.capacity})`);
      }
    }

    // Cold seats
    for (const [gid, requiredBlock] of Object.entries(coldSeats || {})) {
      for (const ba of this.blockAssignments) {
        if (ba.group_id === gid && ba.block_id !== requiredBlock) {
          warnings.push(`Cold-seat: ${gid} in ${ba.block_id}, required ${requiredBlock}`);
          break;
        }
      }
    }

    return warnings;
  }

  toSolutionDict(groupsById) {
    const twoDay = Object.entries(this.dayAssignments).filter(([, d]) => d.length === 2);
    if (!twoDay.length) throw new Error('No groups have 2 days assigned.');

    const cover = this.detectCoverPair() || [0, 0];
    const dayAssignMap = Object.fromEntries(twoDay);
    const score = _computeScore(dayAssignMap, this.blockAssignments);

    return {
      solution_id: Math.random().toString(16).slice(2, 10),
      created_at: new Date().toISOString(),
      cover_pair: cover,
      day_assignments: twoDay.map(([gid, days]) => ({ group_id: gid, days })),
      block_assignments: this.blockAssignments.map(ba => ({ ...ba })),
      score: score.total,
      score_breakdown: { compactness: score.compactness, consistency: score.consistency },
      metadata: { source: 'manual' },
    };
  }

  static fromSolutionDict(dict) {
    const state = new ManualState();
    for (const da of dict.day_assignments) {
      state.dayAssignments[da.group_id] = [...da.days];
    }
    state.blockAssignments = dict.block_assignments.map(ba => ({ ...ba }));
    return state;
  }
}

// Simple JS score computation (port of scorer.py)
function _computeScore(dayAssignMap, blockAssignments) {
  // Compactness
  const groupDayBlocks = {};
  for (const ba of blockAssignments) {
    const key = `${ba.group_id}:${ba.day}`;
    if (!groupDayBlocks[key]) groupDayBlocks[key] = [];
    groupDayBlocks[key].push(ba.block_id);
  }

  let total = 0, single = 0;
  for (const [gid, days] of Object.entries(dayAssignMap)) {
    for (const day of days) {
      total++;
      const blocks = groupDayBlocks[`${gid}:${day}`] || [];
      if (blocks.length === 1) single++;
    }
  }
  const compactness = total > 0 ? single / total : 1.0;

  // Consistency
  let consistent = 0;
  const entries = Object.entries(dayAssignMap);
  for (const [gid, [d1, d2]] of entries) {
    const bs1 = new Set((groupDayBlocks[`${gid}:${d1}`] || []));
    const bs2 = new Set((groupDayBlocks[`${gid}:${d2}`] || []));
    if (bs1.size > 0 && bs2.size > 0 && bs1.size === bs2.size && [...bs1].every(b => bs2.has(b))) {
      consistent++;
    }
  }
  const consistency = entries.length > 0 ? consistent / entries.length : 1.0;

  return {
    total: 0.6 * compactness + 0.4 * consistency,
    compactness,
    consistency,
  };
}

// ---- Tab state ----

let _manualState = new ManualState();
let _activeDay = 1;
let _grid = null;
let _contextMenu = null;
let _contextTarget = null;

export function init() {
  _grid = new OfficeGrid(document.getElementById('manual-grid-container'), {
    interactive: true,
    allowOversize: true,
  });

  _grid.on('drop', _onGridDrop);
  _grid.on('drop-to-pending', _onDropToPending);
  _grid.on('chip-contextmenu', ({ groupId, blockId, clientX, clientY }) => {
    _showChipContextMenu({ clientX, clientY, stopPropagation: () => {} }, groupId, blockId);
  });

  // Day buttons
  document.querySelectorAll('.manual-day-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      _activeDay = parseInt(btn.dataset.day);
      _updateDayButtons();
      _refreshAll();
    });
  });

  // Settings pane
  document.getElementById('manual-load-solution-btn').addEventListener('click', _loadFromSolution);
  document.getElementById('manual-save-btn').addEventListener('click', _saveSolution);
  document.getElementById('manual-clear-btn').addEventListener('click', _clearAll);

  // Context menu
  _contextMenu = document.getElementById('manual-context-menu');
  document.addEventListener('click', () => _hideContextMenu());

  AppState.on('solutionListChanged', _refreshBaseCombo);
  AppState.on('dataLoaded', _refreshAll);

  _refreshBaseCombo();
  _refreshAll();
}

function _updateDayButtons() {
  document.querySelectorAll('.manual-day-btn').forEach(btn => {
    btn.classList.toggle('active', parseInt(btn.dataset.day) === _activeDay);
  });
}

function _refreshAll() {
  _renderGrid();
  _renderPendingPanel();
  _renderGroupPanel();
  _renderWarnings();
}

function _renderGrid() {
  const dayView = _manualState.getDayView(_activeDay);
  _grid.load(AppState.blocks, dayView, AppState.employeesByGroup);
}

function _renderPendingPanel() {
  const panel = document.getElementById('manual-pending-panel');
  panel.innerHTML = '';

  const pending = _manualState.getPendingGroups(_activeDay);
  if (!pending.length) {
    panel.innerHTML = '<span style="color:#718096; font-size:12px;">No pending groups for this day.</span>';
    return;
  }

  for (const gid of pending) {
    const chip = _buildPendingChip(gid);
    panel.appendChild(chip);
  }
}

function _buildPendingChip(groupId) {
  const chip = document.createElement('div');
  chip.className = 'pending-chip';
  chip.dataset.groupId = groupId;
  chip.style.backgroundColor = groupColor(groupId);
  chip.textContent = groupId;

  // Drag chip from pending panel to grid (left-click only)
  chip.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    _startExternalDrag(groupId, null, e.clientX, e.clientY);
  });

  chip.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    _showChipContextMenu(e, groupId, null);
  });

  return chip;
}

// ---- External drag (from pending panel or group panel) ----

let _extDrag = null;
let _extGhost = null;

function _startExternalDrag(groupId, fromBlockId, clientX, clientY) {
  _extDrag = { groupId, fromBlockId };

  const ghost = document.createElement('div');
  ghost.className = 'drag-ghost';
  ghost.style.cssText = `
    position:fixed; pointer-events:none; z-index:9999;
    background:${groupColor(groupId)}; color:#fff;
    padding:4px 8px; border-radius:4px; font-size:12px;
    font-family:system-ui,sans-serif; white-space:nowrap;
    box-shadow:0 2px 8px rgba(0,0,0,0.3); opacity:0.9;
    left:${clientX + 12}px; top:${clientY - 12}px;
  `;
  ghost.textContent = groupId;
  document.body.appendChild(ghost);
  _extGhost = ghost;

  const onMove = (e) => {
    _extGhost.style.left = (e.clientX + 12) + 'px';
    _extGhost.style.top = (e.clientY - 12) + 'px';
  };

  const onUp = (e) => {
    document.removeEventListener('pointermove', onMove);
    document.removeEventListener('pointerup', onUp);
    if (_extGhost) { _extGhost.remove(); _extGhost = null; }

    if (!_extDrag) return;
    const { groupId: gid, fromBlockId } = _extDrag;
    _extDrag = null;

    // Find drop target
    const el = document.elementFromPoint(e.clientX, e.clientY);
    const blockEl = el && el.closest('.grid-block');
    if (blockEl) {
      const toBlockId = blockEl.dataset.blockId;
      _handleDrop(gid, fromBlockId, toBlockId);
    } else {
      const pending = el && el.closest('#manual-pending-panel');
      if (pending && fromBlockId) {
        _manualState.unseatFromBlock(gid, _activeDay, fromBlockId);
        _refreshAll();
      }
    }
  };

  document.addEventListener('pointermove', onMove);
  document.addEventListener('pointerup', onUp);
}

function _onGridDrop({ groupId, fromBlockId, toBlockId }) {
  _handleDrop(groupId, fromBlockId, toBlockId);
}

function _onDropToPending({ groupId, fromBlockId }) {
  if (fromBlockId) {
    _manualState.unseatFromBlock(groupId, _activeDay, fromBlockId);
    _refreshAll();
  }
}

async function _handleDrop(groupId, fromBlockId, toBlockId) {
  const block = AppState.blocksById[toBlockId];
  if (!block) return;

  const g = AppState.groupsById[groupId];
  const defaultCount = g ? g.size : 1;

  // Show count dialog
  const count = await _showCountDialog(groupId, defaultCount, block.capacity);
  if (count === null) return; // cancelled

  if (fromBlockId && fromBlockId !== toBlockId) {
    _manualState.unseatFromBlock(groupId, _activeDay, fromBlockId);
  }

  // Ensure day assignment
  if (!_manualState.dayAssignments[groupId] || !_manualState.dayAssignments[groupId].includes(_activeDay)) {
    _manualState.assignDay(groupId, _activeDay);
  }

  _manualState.seatGroup(groupId, _activeDay, toBlockId, count);
  _refreshAll();
}

function _showCountDialog(groupId, defaultCount, blockCapacity) {
  return new Promise((resolve) => {
    const dialog = document.getElementById('manual-count-dialog');
    const input = document.getElementById('manual-count-input');
    const title = document.getElementById('manual-count-title');

    title.textContent = `How many from "${groupId}"?`;
    input.value = defaultCount;
    input.max = Math.max(defaultCount, blockCapacity);

    dialog.showModal();

    const ok = document.getElementById('manual-count-ok');
    const cancel = document.getElementById('manual-count-cancel');

    const cleanup = () => {
      ok.removeEventListener('click', onOk);
      cancel.removeEventListener('click', onCancel);
      dialog.close();
    };

    const onOk = () => { cleanup(); resolve(Math.max(1, parseInt(input.value) || 1)); };
    const onCancel = () => { cleanup(); resolve(null); };

    ok.addEventListener('click', onOk);
    cancel.addEventListener('click', onCancel);
  });
}

// ---- Group Panel ----

function _renderGroupPanel() {
  const tbody = document.querySelector('#manual-group-table tbody');
  if (!tbody) return;
  tbody.innerHTML = '';

  for (const g of AppState.groups) {
    const gid = g.group_id;
    const days = _manualState.dayAssignments[gid] || [];
    const seated = days.map(d => _manualState.getSeatedCount(gid, d));
    const depts = Array.isArray(g.departments) ? g.departments : Object.keys(g.departments);

    const tr = document.createElement('tr');
    tr.dataset.groupId = gid;
    tr.style.cursor = 'grab';
    tr.innerHTML = `
      <td style="display:flex;align-items:center;gap:6px;">
        <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${groupColor(gid)};flex-shrink:0;"></span>
        ${gid}
      </td>
      <td>${depts.join(', ')}</td>
      <td>${days[0] ? `Day ${days[0]}` : '—'}</td>
      <td>${days[1] ? `Day ${days[1]}` : '—'}</td>
      <td>${seated.join('/')}</td>
    `;

    tr.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      _showGroupContextMenu(e, gid);
    });

    // Make row draggable to grid blocks
    tr.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      _startExternalDrag(gid, null, e.clientX, e.clientY);
    });

    tbody.appendChild(tr);
  }
}

// ---- Context Menus ----

function _showGroupContextMenu(e, groupId) {
  e.stopPropagation();
  _contextTarget = { type: 'group', groupId };
  _buildGroupContextMenu(groupId);
  _positionContextMenu(e.clientX, e.clientY);
}

function _showChipContextMenu(e, groupId, blockId) {
  e.stopPropagation();
  _contextTarget = { type: 'chip', groupId, blockId };
  _buildGroupContextMenu(groupId, blockId);
  _positionContextMenu(e.clientX, e.clientY);
}

function _buildGroupContextMenu(groupId, blockId) {
  _contextMenu.innerHTML = '';

  const days = _manualState.dayAssignments[groupId] || [];

  // Add to day submenu
  const addMenu = document.createElement('div');
  addMenu.className = 'ctx-item ctx-submenu';
  addMenu.innerHTML = 'Add to day ▶';
  const sub = document.createElement('div');
  sub.className = 'ctx-submenu-items';
  for (const d of [1, 2, 3, 4]) {
    const item = document.createElement('div');
    item.className = 'ctx-item';
    item.textContent = `Day ${d}`;
    if (days.includes(d) || days.length >= 2) {
      item.classList.add('ctx-disabled');
    } else {
      item.addEventListener('click', () => {
        _manualState.assignDay(groupId, d);
        _hideContextMenu();
        _refreshAll();
      });
    }
    sub.appendChild(item);
  }
  addMenu.appendChild(sub);
  _contextMenu.appendChild(addMenu);

  // Remove from day
  if (days.length > 0) {
    for (const d of days) {
      const item = document.createElement('div');
      item.className = 'ctx-item';
      item.textContent = `Remove from Day ${d}`;
      item.addEventListener('click', () => {
        _manualState.removeDay(groupId, d);
        _hideContextMenu();
        _refreshAll();
      });
      _contextMenu.appendChild(item);
    }
  }

  // Unseat from block
  if (blockId) {
    const item = document.createElement('div');
    item.className = 'ctx-item';
    item.textContent = `Unseat from ${blockId}`;
    item.addEventListener('click', () => {
      _manualState.unseatFromBlock(groupId, _activeDay, blockId);
      _hideContextMenu();
      _refreshAll();
    });
    _contextMenu.appendChild(item);
  }

  // Clear all
  const clearItem = document.createElement('div');
  clearItem.className = 'ctx-item ctx-danger';
  clearItem.textContent = 'Clear all assignments';
  clearItem.addEventListener('click', () => {
    _manualState.clearGroup(groupId);
    _hideContextMenu();
    _refreshAll();
  });
  _contextMenu.appendChild(clearItem);
}

function _positionContextMenu(x, y) {
  _contextMenu.style.left = x + 'px';
  _contextMenu.style.top = y + 'px';
  _contextMenu.style.display = 'block';
}

function _hideContextMenu() {
  if (_contextMenu) _contextMenu.style.display = 'none';
  _contextTarget = null;
}

// ---- Warnings Bar ----

function _renderWarnings() {
  const bar = document.getElementById('manual-warnings-bar');
  const warnings = _manualState.computeWarnings(
    AppState.groupsById, AppState.blocksById, AppState.deptMap, AppState.coldSeats
  );

  if (!warnings.length) {
    bar.className = 'warnings-bar warnings-ok';
    bar.innerHTML = '<span>✓ All constraints satisfied</span>';
  } else {
    bar.className = 'warnings-bar warnings-warn';
    bar.innerHTML = `
      <details>
        <summary>⚠ ${warnings.length} warning(s)</summary>
        <ul>${warnings.map(w => `<li>${w}</li>`).join('')}</ul>
      </details>
    `;
  }
}

// ---- Load / Save / Clear ----

function _refreshBaseCombo() {
  const sel = document.getElementById('manual-base-solution-select');
  const current = sel.value;
  sel.innerHTML = '<option value="">— New / Empty —</option>';
  for (const sol of AppState.solutions) {
    const opt = document.createElement('option');
    opt.value = sol.solution_id;
    opt.textContent = `${sol.solution_id} (${(sol.score * 100).toFixed(1)}%)`;
    sel.appendChild(opt);
  }
  if (current) sel.value = current;
}

function _loadFromSolution() {
  const sel = document.getElementById('manual-base-solution-select');
  const sol = AppState.solutions.find(s => s.solution_id === sel.value);
  if (!sol) {
    _manualState = new ManualState();
  } else {
    _manualState = ManualState.fromSolutionDict(sol);
  }
  _refreshAll();
}

function _saveSolution() {
  try {
    const dict = _manualState.toSolutionDict(AppState.groupsById);
    AppState.addSolution(dict);
    AppState.setActiveSolution(dict);
    alert(`Solution ${dict.solution_id} saved.`);
  } catch (e) {
    alert('Cannot save: ' + e.message);
  }
}

function _clearAll() {
  if (!confirm('Clear all manual assignments?')) return;
  _manualState = new ManualState();
  _refreshAll();
}
