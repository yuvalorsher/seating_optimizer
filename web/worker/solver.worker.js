// Web Worker: loads Pyodide and exposes solve/update via postMessage

/* global loadPyodide */

importScripts('https://cdn.jsdelivr.net/pyodide/v0.27.0/full/pyodide.js');

const PYTHON_FILES = [
  '__init__.py', 'models.py', 'loader.py', 'constraints.py',
  'scorer.py', 'solver.py', 'updater.py', 'persistence.py',
];

let pyodide = null;

async function initPyodide(baseUrl, pyFiles) {
  pyodide = await loadPyodide({
    indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.27.0/full/',
  });

  // Mount seating_optimizer package
  try { pyodide.FS.mkdir('/home/pyodide/seating_optimizer'); } catch (e) { /* exists */ }

  for (const [fname, content] of pyFiles) {
    pyodide.FS.writeFile(`/home/pyodide/seating_optimizer/${fname}`, content);
  }

  await pyodide.runPythonAsync(`
import sys
if '/home/pyodide' not in sys.path:
    sys.path.insert(0, '/home/pyodide')
`);
}

async function setupData(officeMapCsv, employeesCsv, coldSeatsCsv) {
  pyodide.FS.writeFile('/tmp/office_map.csv', officeMapCsv);
  pyodide.FS.writeFile('/tmp/employees.csv', employeesCsv);
  // Always write cold seats file; empty if not provided so stale files don't persist
  pyodide.FS.writeFile('/tmp/cold_seats.csv', coldSeatsCsv || 'Group,Block\n');

  await pyodide.runPythonAsync(`
from seating_optimizer.loader import (
    load_office_map, load_employees, get_groups,
    get_employees_by_group, load_cold_seats,
)

_w_blocks = load_office_map('/tmp/office_map.csv')
_w_employees = load_employees('/tmp/employees.csv')
_w_groups = get_groups(_w_employees)
_w_groups_by_id = {g.group_id: g for g in _w_groups}

try:
    _w_cold_seats = load_cold_seats('/tmp/cold_seats.csv')
except Exception:
    _w_cold_seats = {}
`);
}

async function handleSolve(nSolutions, maxIters, seed) {
  // Set up progress reporting
  pyodide.globals.set('_solve_n', nSolutions);
  pyodide.globals.set('_solve_iters', maxIters);
  pyodide.globals.set('_solve_seed', seed);

  await pyodide.runPythonAsync(`
import json
from seating_optimizer.solver import Solver
from seating_optimizer.persistence import solution_to_dict

def _progress_cb(current, total):
    import js, json as _j
    js.postMessage(js.JSON.parse(_j.dumps({'type': 'progress', 'current': current, 'total': total})))

_solver = Solver(
    blocks=_w_blocks,
    groups=_w_groups,
    n_solutions=_solve_n,
    max_iterations_per_cover=_solve_iters,
    seed=_solve_seed if _solve_seed else None,
    cold_seats=_w_cold_seats,
)
_w_solutions = _solver.solve(progress_callback=_progress_cb)
_solutions_json = json.dumps([solution_to_dict(s) for s in _w_solutions])
`);

  const solutions = JSON.parse(pyodide.globals.get('_solutions_json'));
  self.postMessage({ type: 'solve_result', solutions });
}

async function handleUpdate(solutionDict, sizeOverrides) {
  pyodide.globals.set('_upd_solution_json', JSON.stringify(solutionDict));
  pyodide.globals.set('_upd_overrides_json', JSON.stringify(sizeOverrides));

  await pyodide.runPythonAsync(`
import json
from seating_optimizer.updater import SolutionUpdater
from seating_optimizer.persistence import solution_from_dict, solution_to_dict

_upd_solution = solution_from_dict(json.loads(_upd_solution_json))
_upd_overrides = {k: int(v) for k, v in json.loads(_upd_overrides_json).items()}
_updater = SolutionUpdater(_w_blocks, _w_groups_by_id)
_upd_result = _updater.update(_upd_solution, _upd_overrides)
_update_result_json = json.dumps(solution_to_dict(_upd_result))
`);

  const solution = JSON.parse(pyodide.globals.get('_update_result_json'));
  self.postMessage({ type: 'update_result', solution });
}

self.onmessage = async (e) => {
  const msg = e.data;
  try {
    if (msg.type === 'init') {
      self.postMessage({ type: 'status', text: 'Loading Python runtime...' });
      await initPyodide(msg.baseUrl, msg.pyFiles);
      self.postMessage({ type: 'status', text: 'Parsing data...' });
      await setupData(msg.officeMapCsv, msg.employeesCsv, msg.coldSeatsCsv || '');
      self.postMessage({ type: 'ready' });
    } else if (msg.type === 'update_data') {
      await setupData(msg.officeMapCsv, msg.employeesCsv, msg.coldSeatsCsv || '');
      self.postMessage({ type: 'data_ready' });
    } else if (msg.type === 'solve') {
      await handleSolve(msg.nSolutions, msg.maxIters, msg.seed);
    } else if (msg.type === 'update') {
      await handleUpdate(msg.solutionDict, msg.sizeOverrides);
    }
  } catch (err) {
    self.postMessage({ type: 'error', message: err.message || String(err) });
  }
};
