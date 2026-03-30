// Central application state + pub/sub event bus (replaces PySide6 AppState)

import { groupColor } from '../utils/colors.js';
import * as persistence from '../utils/persistence.js';

const AppState = {
  // Data
  blocks: [],
  blocksById: {},
  groups: [],
  groupsById: {},
  employeesByGroup: {},
  deptMap: {},
  coldSeats: {},
  solutions: [],
  activeSolution: null,
  activeDay: 1,

  // Pyodide handle (main thread)
  _pyodide: null,
  _worker: null,
  _listeners: {},

  // ---------- Event bus ----------

  on(event, fn) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(fn);
  },

  off(event, fn) {
    if (!this._listeners[event]) return;
    this._listeners[event] = this._listeners[event].filter(f => f !== fn);
  },

  emit(event, payload) {
    (this._listeners[event] || []).forEach(fn => fn(payload));
  },

  // ---------- Initialisation ----------

  init(pyodide, blocks) {
    this._pyodide = pyodide;
    this.blocks = blocks;
    this.blocksById = Object.fromEntries(blocks.map(b => [b.block_id, b]));
    this.solutions = persistence.listSolutions();
    this.emit('dataLoaded');
    this.emit('solutionListChanged');
  },

  loadEmployeesData(groups, employeesByGroup, deptMap) {
    this.groups = groups;
    this.groupsById = Object.fromEntries(groups.map(g => [g.group_id, g]));
    this.employeesByGroup = employeesByGroup;
    this.deptMap = deptMap;
    this.emit('dataLoaded');
  },

  setColdSeats(coldSeats) {
    this.coldSeats = coldSeats;
  },

  reloadBlocks(blocks) {
    this.blocks = blocks;
    this.blocksById = Object.fromEntries(blocks.map(b => [b.block_id, b]));
    this.emit('dataLoaded');
  },

  // ---------- Solutions ----------

  addSolution(dict) {
    persistence.saveSolution(dict);
    // Insert in score order
    this.solutions.push(dict);
    this.solutions.sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      return (b.created_at || '').localeCompare(a.created_at || '');
    });
    this.emit('solutionListChanged');
  },

  deleteSolution(solutionId) {
    persistence.deleteSolution(solutionId);
    this.solutions = this.solutions.filter(s => s.solution_id !== solutionId);
    if (this.activeSolution && this.activeSolution.solution_id === solutionId) {
      this.setActiveSolution(this.solutions[0] || null);
    }
    this.emit('solutionListChanged');
  },

  setActiveSolution(sol) {
    this.activeSolution = sol;
    this.activeDay = 1;
    this.emit('activeSolutionChanged', sol);
    this.emit('activeDayChanged', 1);
  },

  setActiveDay(day) {
    this.activeDay = day;
    this.emit('activeDayChanged', day);
  },

  // ---------- Helpers ----------

  groupColor(groupId) {
    return groupColor(groupId);
  },

  // Parse employees CSV via main-thread Pyodide
  async parseEmployeesCSV(csvText) {
    if (!this._pyodide) throw new Error('Pyodide not ready');
    const py = this._pyodide;
    py.FS.writeFile('/tmp/employees.csv', csvText);
    await py.runPythonAsync(`
import json
from seating_optimizer.loader import load_employees, get_groups, get_department_map, get_employees_by_group
_employees = load_employees('/tmp/employees.csv')
_groups = get_groups(_employees)
_groups_json = json.dumps([
    {'group_id': g.group_id, 'name': g.name, 'size': g.size, 'departments': list(g.departments)}
    for g in _groups
])
_emp_by_group_json = json.dumps({
    gid: [{'name': e.name, 'employee_id': e.employee_id} for e in emps]
    for gid, emps in get_employees_by_group(_employees).items()
})
_dept_map_json = json.dumps(get_department_map(_groups))
`);
    const groups = JSON.parse(py.globals.get('_groups_json'));
    const employeesByGroup = JSON.parse(py.globals.get('_emp_by_group_json'));
    const deptMap = JSON.parse(py.globals.get('_dept_map_json'));
    return { groups, employeesByGroup, deptMap };
  },

  // Parse cold seats CSV via main-thread Pyodide
  async parseColdSeatsCSV(csvText) {
    if (!this._pyodide) throw new Error('Pyodide not ready');
    const py = this._pyodide;
    py.FS.writeFile('/tmp/cold_seats.csv', csvText);
    await py.runPythonAsync(`
import json
from seating_optimizer.loader import load_cold_seats
_cold_seats_json = json.dumps(load_cold_seats('/tmp/cold_seats.csv'))
`);
    return JSON.parse(py.globals.get('_cold_seats_json'));
  },

  // Parse office map CSV via main-thread Pyodide
  async parseOfficeMapCSV(csvText) {
    if (!this._pyodide) throw new Error('Pyodide not ready');
    const py = this._pyodide;
    py.FS.writeFile('/tmp/office_map_custom.csv', csvText);
    await py.runPythonAsync(`
import json
from seating_optimizer.loader import load_office_map
_blocks_custom = load_office_map('/tmp/office_map_custom.csv')
_blocks_custom_json = json.dumps([
    {'block_id': b.block_id, 'row': b.row, 'col': b.col, 'capacity': b.capacity}
    for b in _blocks_custom
])
`);
    return JSON.parse(py.globals.get('_blocks_custom_json'));
  },
};

export default AppState;
