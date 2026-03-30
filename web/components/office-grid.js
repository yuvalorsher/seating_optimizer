// SVG-based office grid renderer
// Supports read-only (Visualize/DeptOverlap) and interactive (Manual) modes

import { groupColor } from '../utils/colors.js';

const CELL_W = 150;
const CELL_H = 130;
const CELL_GAP = 6;
const HEADER_H = 36;
const CAP_BAR_H = 8;
const CHIP_H = 20;
const CHIP_PAD = 4;
const CHIP_MARGIN = 3;
const SVG_NS = 'http://www.w3.org/2000/svg';

// Build {block_id: total_occupied} for a day view
function buildOccupancy(dayView) {
  const occ = {};
  for (const [blockId, chips] of Object.entries(dayView || {})) {
    occ[blockId] = chips.reduce((s, [, c]) => s + c, 0);
  }
  return occ;
}

function capBarColor(used, capacity) {
  const ratio = used / capacity;
  if (ratio > 1) return '#E74C3C';
  if (ratio > 0.85) return '#F5A623';
  return '#27AE60';
}

export class OfficeGrid {
  /**
   * @param {HTMLElement} container
   * @param {object} opts
   * @param {boolean} [opts.interactive] — enable drag-drop (Manual tab)
   * @param {boolean} [opts.allowOversize] — allow over-capacity drops without blocking
   */
  constructor(container, opts = {}) {
    this.container = container;
    this.interactive = opts.interactive || false;
    this.allowOversize = opts.allowOversize || false;

    this._blocks = [];
    this._blocksById = {};
    this._dayView = {};
    this._employeesByGroup = {};
    this._highlightGroupId = null;
    this._scale = 1;

    // Drag state (interactive mode)
    this._drag = null;
    this._ghost = null;
    this._docListenersAdded = false;

    // Event listeners: {event: [fn]}
    this._evtListeners = {};

    container.style.overflow = 'auto';
    container.style.position = 'relative';
  }

  on(event, fn) {
    if (!this._evtListeners[event]) this._evtListeners[event] = [];
    this._evtListeners[event].push(fn);
  }

  _emit(event, payload) {
    (this._evtListeners[event] || []).forEach(fn => fn(payload));
  }

  /**
   * Render the grid for a given day.
   * @param {Array} blocks — [{block_id, row, col, capacity}]
   * @param {object} dayView — {block_id: [[group_id, count], ...]}
   * @param {object} [employeesByGroup] — {group_id: [{name},...]}
   */
  load(blocks, dayView, employeesByGroup = {}) {
    this._blocks = blocks;
    this._blocksById = Object.fromEntries(blocks.map(b => [b.block_id, b]));
    this._dayView = dayView || {};
    this._employeesByGroup = employeesByGroup;
    this._rebuild();
  }

  highlightGroup(groupId) {
    this._highlightGroupId = groupId;
    // Apply highlight class to matching chips
    this.container.querySelectorAll('.grid-chip').forEach(el => {
      el.classList.toggle('chip-highlight', el.dataset.groupId === groupId);
      el.classList.toggle('chip-dim', groupId && el.dataset.groupId !== groupId);
    });
  }

  clearHighlight() {
    this._highlightGroupId = null;
    this.container.querySelectorAll('.grid-chip').forEach(el => {
      el.classList.remove('chip-highlight', 'chip-dim');
    });
  }

  zoomIn() { this._setScale(Math.min(this._scale * 1.25, 3)); }
  zoomOut() { this._setScale(Math.max(this._scale / 1.25, 0.3)); }
  fitToContainer() {
    if (!this._svg) return;
    const cw = this.container.clientWidth;
    const ch = this.container.clientHeight;
    const svgW = parseInt(this._svg.getAttribute('width'));
    const svgH = parseInt(this._svg.getAttribute('height'));
    if (!svgW || !svgH) return;
    const s = Math.min(cw / svgW, ch / svgH, 1);
    this._setScale(Math.max(s, 0.3));
  }

  _setScale(s) {
    this._scale = s;
    if (this._svgWrapper) {
      this._svgWrapper.style.transform = `scale(${s})`;
      this._svgWrapper.style.transformOrigin = 'top left';
      const svgW = parseInt(this._svg.getAttribute('width'));
      const svgH = parseInt(this._svg.getAttribute('height'));
      this._svgWrapper.style.width = svgW + 'px';
      this._svgWrapper.style.height = svgH + 'px';
      this.container.style.minWidth = Math.ceil(svgW * s) + 'px';
      this.container.style.minHeight = Math.ceil(svgH * s) + 'px';
    }
  }

  _rebuild() {
    this.container.innerHTML = '';
    if (!this._blocks.length) {
      this.container.innerHTML = '<p style="color:#888;padding:16px">No blocks loaded.</p>';
      return;
    }

    const maxRow = Math.max(...this._blocks.map(b => b.row));
    const maxCol = Math.max(...this._blocks.map(b => b.col));
    const svgW = (maxCol + 1) * (CELL_W + CELL_GAP) - CELL_GAP;
    const svgH = (maxRow + 1) * (CELL_H + CELL_GAP) - CELL_GAP;

    const wrapper = document.createElement('div');
    wrapper.style.display = 'inline-block';
    this._svgWrapper = wrapper;

    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('width', svgW);
    svg.setAttribute('height', svgH);
    this._svg = svg;

    const occupancy = buildOccupancy(this._dayView);

    for (const block of this._blocks) {
      const x = block.col * (CELL_W + CELL_GAP);
      const y = block.row * (CELL_H + CELL_GAP);
      const chips = this._dayView[block.block_id] || [];
      const used = occupancy[block.block_id] || 0;
      const g = this._buildBlockGroup(block, x, y, chips, used);
      svg.appendChild(g);
    }

    wrapper.appendChild(svg);
    this.container.appendChild(wrapper);

    if (this.interactive) {
      this._setupDragDrop(svg);
    }

    // Reapply highlight
    if (this._highlightGroupId) {
      this.highlightGroup(this._highlightGroupId);
    }
  }

  _buildBlockGroup(block, x, y, chips, used) {
    const g = document.createElementNS(SVG_NS, 'g');
    g.setAttribute('transform', `translate(${x},${y})`);
    g.dataset.blockId = block.block_id;
    g.classList.add('grid-block');

    // Background rect
    const bg = document.createElementNS(SVG_NS, 'rect');
    bg.setAttribute('width', CELL_W);
    bg.setAttribute('height', CELL_H);
    bg.setAttribute('rx', 8);
    bg.setAttribute('ry', 8);
    bg.setAttribute('fill', '#FFFFFF');
    bg.setAttribute('stroke', '#CBD5E0');
    bg.setAttribute('stroke-width', 1.5);
    g.appendChild(bg);

    // Block ID label
    const label = document.createElementNS(SVG_NS, 'text');
    label.setAttribute('x', 8);
    label.setAttribute('y', 16);
    label.setAttribute('font-size', '11');
    label.setAttribute('font-family', 'system-ui, sans-serif');
    label.setAttribute('fill', '#4A5568');
    label.setAttribute('font-weight', '600');
    label.textContent = block.block_id;
    g.appendChild(label);

    // Capacity label
    const capLabel = document.createElementNS(SVG_NS, 'text');
    capLabel.setAttribute('x', CELL_W - 8);
    capLabel.setAttribute('y', 16);
    capLabel.setAttribute('font-size', '10');
    capLabel.setAttribute('font-family', 'system-ui, sans-serif');
    capLabel.setAttribute('fill', '#718096');
    capLabel.setAttribute('text-anchor', 'end');
    capLabel.textContent = `${used}/${block.capacity}`;
    g.appendChild(capLabel);

    // Capacity bar background
    const barBg = document.createElementNS(SVG_NS, 'rect');
    barBg.setAttribute('x', 0);
    barBg.setAttribute('y', HEADER_H - CAP_BAR_H);
    barBg.setAttribute('width', CELL_W);
    barBg.setAttribute('height', CAP_BAR_H);
    barBg.setAttribute('fill', '#EDF2F7');
    g.appendChild(barBg);

    // Capacity bar fill
    if (used > 0) {
      const fillW = Math.min(used / block.capacity, 1) * CELL_W;
      const barFill = document.createElementNS(SVG_NS, 'rect');
      barFill.setAttribute('x', 0);
      barFill.setAttribute('y', HEADER_H - CAP_BAR_H);
      barFill.setAttribute('width', fillW);
      barFill.setAttribute('height', CAP_BAR_H);
      barFill.setAttribute('fill', capBarColor(used, block.capacity));
      g.appendChild(barFill);
    }

    // Separator line
    const line = document.createElementNS(SVG_NS, 'line');
    line.setAttribute('x1', 0);
    line.setAttribute('y1', HEADER_H);
    line.setAttribute('x2', CELL_W);
    line.setAttribute('y2', HEADER_H);
    line.setAttribute('stroke', '#E2E8F0');
    line.setAttribute('stroke-width', 1);
    g.appendChild(line);

    // Drop zone indicator (interactive mode)
    if (this.interactive) {
      const dropZone = document.createElementNS(SVG_NS, 'rect');
      dropZone.setAttribute('width', CELL_W);
      dropZone.setAttribute('height', CELL_H);
      dropZone.setAttribute('rx', 8);
      dropZone.setAttribute('ry', 8);
      dropZone.setAttribute('fill', 'none');
      dropZone.setAttribute('stroke', 'none');
      dropZone.setAttribute('stroke-width', 3);
      dropZone.classList.add('drop-zone');
      dropZone.dataset.blockId = block.block_id;
      g.appendChild(dropZone);
    }

    // Chips
    let chipY = HEADER_H + CHIP_MARGIN;
    for (const [groupId, count] of chips) {
      if (chipY + CHIP_H > CELL_H - CHIP_MARGIN) break; // no more space visible

      const color = groupColor(groupId);
      const chipG = this._buildChip(groupId, count, color, 0, chipY, CELL_W, block.block_id);
      g.appendChild(chipG);
      chipY += CHIP_H + 2;
    }

    return g;
  }

  _buildChip(groupId, count, color, x, y, width, blockId) {
    const g = document.createElementNS(SVG_NS, 'g');
    g.setAttribute('transform', `translate(${x + CHIP_PAD},${y})`);
    g.classList.add('grid-chip');
    g.dataset.groupId = groupId;
    g.dataset.blockId = blockId || '';
    if (this.interactive) g.dataset.draggable = 'true';

    const chipW = width - CHIP_PAD * 2;

    const rect = document.createElementNS(SVG_NS, 'rect');
    rect.setAttribute('width', chipW);
    rect.setAttribute('height', CHIP_H - 2);
    rect.setAttribute('rx', 4);
    rect.setAttribute('ry', 4);
    rect.setAttribute('fill', color);
    rect.setAttribute('opacity', 0.85);
    g.appendChild(rect);

    const text = document.createElementNS(SVG_NS, 'text');
    text.setAttribute('x', chipW / 2);
    text.setAttribute('y', (CHIP_H - 2) / 2 + 1);
    text.setAttribute('font-size', '10');
    text.setAttribute('font-family', 'system-ui, sans-serif');
    text.setAttribute('fill', '#FFFFFF');
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('dominant-baseline', 'middle');
    text.setAttribute('pointer-events', 'none');
    const label = count > 1 ? `${groupId} ×${count}` : groupId;
    text.textContent = label.length > 20 ? label.slice(0, 18) + '…' : label;
    g.appendChild(text);

    // Tooltip: employee names
    const employees = (this._employeesByGroup[groupId] || []).map(e => e.name);
    if (employees.length) {
      const title = document.createElementNS(SVG_NS, 'title');
      title.textContent = employees.join(', ');
      g.appendChild(title);
    }

    return g;
  }

  // ---- Drag & Drop (interactive mode) ----

  _setupDragDrop(svg) {
    svg.addEventListener('pointerdown', (e) => this._onPointerDown(e));
    if (!this._docListenersAdded) {
      document.addEventListener('pointermove', (e) => this._onPointerMove(e));
      document.addEventListener('pointerup', (e) => this._onPointerUp(e));
      this._docListenersAdded = true;
    }
  }

  _onPointerDown(e) {
    const chip = e.target.closest('.grid-chip[data-draggable]');
    if (!chip) return;

    e.preventDefault();
    const groupId = chip.dataset.groupId;
    const fromBlockId = chip.dataset.blockId || null;

    this._drag = { groupId, fromBlockId };

    // Create ghost element
    const ghost = document.createElement('div');
    ghost.className = 'drag-ghost';
    ghost.style.cssText = `
      position:fixed; pointer-events:none; z-index:9999;
      background:${groupColor(groupId)}; color:#fff;
      padding:4px 8px; border-radius:4px; font-size:12px;
      font-family:system-ui,sans-serif; white-space:nowrap;
      box-shadow:0 2px 8px rgba(0,0,0,0.3); opacity:0.9;
    `;
    ghost.textContent = groupId;
    document.body.appendChild(ghost);
    this._ghost = ghost;

    this._updateGhost(e.clientX, e.clientY);
    this._svg.setPointerCapture(e.pointerId);
  }

  _onPointerMove(e) {
    if (!this._drag) return;
    this._updateGhost(e.clientX, e.clientY);

    // Highlight potential drop target
    const el = document.elementFromPoint(e.clientX, e.clientY);
    const dropZone = el && el.closest('[data-block-id]');
    this._svg.querySelectorAll('.drop-zone').forEach(dz => {
      dz.setAttribute('stroke', 'none');
    });
    if (dropZone) {
      const blockId = dropZone.dataset.blockId;
      const dz = this._svg.querySelector(`.drop-zone[data-block-id="${blockId}"]`);
      if (dz) dz.setAttribute('stroke', '#4A90D9');
    }
  }

  _onPointerUp(e) {
    if (!this._drag) return;
    const { groupId, fromBlockId } = this._drag;
    this._drag = null;

    if (this._ghost) {
      this._ghost.remove();
      this._ghost = null;
    }

    this._svg.querySelectorAll('.drop-zone').forEach(dz => dz.setAttribute('stroke', 'none'));

    const el = document.elementFromPoint(e.clientX, e.clientY);
    const target = el && el.closest('.grid-block');

    if (target) {
      const toBlockId = target.dataset.blockId;
      this._emit('drop', { groupId, fromBlockId, toBlockId });
    } else if (el) {
      // Check if dropped on pending panel
      const pendingArea = el.closest('[data-pending-drop]');
      if (pendingArea) {
        this._emit('drop-to-pending', { groupId, fromBlockId });
      }
    }
  }

  _updateGhost(x, y) {
    if (!this._ghost) return;
    this._ghost.style.left = (x + 12) + 'px';
    this._ghost.style.top = (y - 12) + 'px';
  }
}
