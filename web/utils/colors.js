// Stable group → color mapping (port of AppState.group_color)
// Uses djb2 hash for determinism across sessions

const DEPT_COLORS = [
  "#4A90D9", "#27AE60", "#F5A623", "#D0021B",
  "#9B59B6", "#1ABC9C", "#E67E22", "#2C3E50",
  "#E74C3C", "#3498DB", "#2ECC71", "#F39C12",
];
export const DEFAULT_COLOR = "#888888";

const _cache = new Map();

function djb2(str) {
  let hash = 5381;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) + hash) + str.charCodeAt(i);
    hash |= 0; // 32-bit int
  }
  return Math.abs(hash);
}

export function groupColor(groupId) {
  if (!_cache.has(groupId)) {
    const idx = djb2(groupId) % DEPT_COLORS.length;
    _cache.set(groupId, DEPT_COLORS[idx]);
  }
  return _cache.get(groupId);
}
