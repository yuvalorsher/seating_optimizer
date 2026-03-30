// Solutions & settings persistence via localStorage

import { triggerDownload } from './file-io.js';

const SOL_PREFIX = 'solutions:';
const MAP_KEY = 'office_map_override';

export function saveSolution(dict) {
  localStorage.setItem(SOL_PREFIX + dict.solution_id, JSON.stringify(dict));
}

export function listSolutions() {
  const result = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key && key.startsWith(SOL_PREFIX)) {
      try {
        result.push(JSON.parse(localStorage.getItem(key)));
      } catch (e) { /* skip corrupt entries */ }
    }
  }
  result.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    return (b.created_at || '').localeCompare(a.created_at || '');
  });
  return result;
}

export function deleteSolution(solutionId) {
  localStorage.removeItem(SOL_PREFIX + solutionId);
}

export function exportSolution(dict) {
  triggerDownload(JSON.stringify(dict, null, 2), `solution_${dict.solution_id}.json`);
}

export function saveOfficeMapOverride(csvText) {
  localStorage.setItem(MAP_KEY, csvText);
}

export function getOfficeMapOverride() {
  return localStorage.getItem(MAP_KEY);
}

export function clearOfficeMapOverride() {
  localStorage.removeItem(MAP_KEY);
}
