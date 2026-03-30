// App bootstrap: load Pyodide, mount Python package, initialize tabs

import AppState from './state/app-state.js';
import * as persistence from './utils/persistence.js';
import { init as initSolve } from './tabs/solve-tab.js';
import { init as initVisualize } from './tabs/visualize-tab.js';
import { init as initUpdate } from './tabs/update-tab.js';
import { init as initDeptOverlap } from './tabs/dept-overlap-tab.js';
import { init as initManual } from './tabs/manual-tab.js';

const PYODIDE_CDN = 'https://cdn.jsdelivr.net/pyodide/v0.27.0/full/';
const PYTHON_FILES = [
  '__init__.py', 'models.py', 'loader.py', 'constraints.py',
  'scorer.py', 'solver.py', 'updater.py', 'persistence.py',
];

// ---- Tab routing ----

function initTabs() {
  const tabBtns = document.querySelectorAll('[data-tab]');
  const tabPanels = document.querySelectorAll('[data-panel]');

  function activate(name) {
    tabBtns.forEach(btn => btn.classList.toggle('active', btn.dataset.tab === name));
    tabPanels.forEach(panel => {
      panel.style.display = panel.dataset.panel === name ? '' : 'none';
    });
    // Re-fit grid when visualize tab becomes visible
    if (name === 'visualize') {
      setTimeout(() => document.dispatchEvent(new CustomEvent('viz-tab-shown')), 50);
    }
  }

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => activate(btn.dataset.tab));
  });

  // Show first tab
  activate('solve');
}

// ---- Pyodide loading ----

function setLoadingMessage(msg) {
  const el = document.getElementById('loading-message');
  if (el) el.textContent = msg;
}

async function loadPyodideAndPackage() {
  setLoadingMessage('Loading Python runtime…');

  // loadPyodide is injected by the Pyodide script tag
  /* global loadPyodide */
  const pyodide = await loadPyodide({ indexURL: PYODIDE_CDN });

  setLoadingMessage('Mounting Python package…');

  // Create package directory in Pyodide's virtual FS
  try { pyodide.FS.mkdir('/home/pyodide/seating_optimizer'); } catch (e) { /* already exists */ }

  // Fetch and write each Python file
  for (const fname of PYTHON_FILES) {
    const res = await fetch(`python/seating_optimizer/${fname}`);
    if (!res.ok) throw new Error(`Failed to fetch python/seating_optimizer/${fname}: ${res.status}`);
    const text = await res.text();
    pyodide.FS.writeFile(`/home/pyodide/seating_optimizer/${fname}`, text);
  }

  // Ensure /home/pyodide is on sys.path
  await pyodide.runPythonAsync(`
import sys
if '/home/pyodide' not in sys.path:
    sys.path.insert(0, '/home/pyodide')
`);

  return pyodide;
}

async function loadOfficeMap(pyodide) {
  // Check localStorage override first
  const override = persistence.getOfficeMapOverride();
  const csvText = override || await fetch('python/data/office_map.csv').then(r => r.text());

  pyodide.FS.writeFile('/tmp/office_map.csv', csvText);

  await pyodide.runPythonAsync(`
import json
from seating_optimizer.loader import load_office_map
_init_blocks = load_office_map('/tmp/office_map.csv')
_init_blocks_json = json.dumps([
    {'block_id': b.block_id, 'row': b.row, 'col': b.col, 'capacity': b.capacity}
    for b in _init_blocks
])
`);

  return JSON.parse(pyodide.globals.get('_init_blocks_json'));
}

// ---- Main ----

async function main() {
  initTabs();
  initSolve();
  initVisualize();
  initUpdate();
  initDeptOverlap();
  initManual();

  try {
    const pyodide = await loadPyodideAndPackage();
    setLoadingMessage('Loading office map…');
    const blocks = await loadOfficeMap(pyodide);

    // Update office map label
    const hasOverride = !!persistence.getOfficeMapOverride();
    const mapNameEl = document.getElementById('solve-map-name');
    if (mapNameEl) mapNameEl.textContent = hasOverride ? 'Custom (saved)' : 'Default';
    const resetBtn = document.getElementById('solve-reset-map-btn');
    if (resetBtn) resetBtn.style.display = hasOverride ? '' : 'none';

    AppState.init(pyodide, blocks);

    // Remove loading overlay
    const overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.remove();

    // Update status bar
    document.getElementById('app-status').textContent =
      `${blocks.length} blocks loaded · upload employees CSV to run solver`;
  } catch (err) {
    setLoadingMessage('Error: ' + err.message);
    console.error(err);
  }
}

document.addEventListener('DOMContentLoaded', main);
