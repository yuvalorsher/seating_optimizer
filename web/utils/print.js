// PDF export via window.print()
// Builds a printable layout in #print-area, triggers browser print dialog

import { groupColor } from './colors.js';

export function exportToPDF(solution, blocks, groupsById, deptMap) {
  const area = document.getElementById('print-area');
  if (!area) return;

  area.innerHTML = '';
  area.appendChild(_buildPrintContent(solution, blocks, groupsById, deptMap));
  window.print();
}

function _buildPrintContent(solution, blocks, groupsById, deptMap) {
  const frag = document.createDocumentFragment();

  // Pages 1–4: one per day
  for (const day of [1, 2, 3, 4]) {
    const dayView = _getDayView(solution, day);
    const page = _buildDayPage(day, dayView, blocks, groupsById);
    frag.appendChild(page);
  }

  // Page 5: summary
  frag.appendChild(_buildSummaryPage(solution, groupsById, deptMap));

  // Page 6+: dept attendance
  frag.appendChild(_buildDeptAttendancePage(solution, groupsById, deptMap));

  return frag;
}

function _getDayView(solution, day) {
  const view = {};
  for (const ba of solution.block_assignments) {
    if (ba.day === day) {
      if (!view[ba.block_id]) view[ba.block_id] = [];
      view[ba.block_id].push([ba.group_id, ba.count]);
    }
  }
  return view;
}

function _buildDayPage(day, dayView, blocks, groupsById) {
  const page = document.createElement('div');
  page.className = 'print-page';

  const title = document.createElement('h2');
  const totalAttending = Object.values(dayView)
    .reduce((s, chips) => s + chips.reduce((a, [, c]) => a + c, 0), 0);
  title.textContent = `Day ${day}  —  ${totalAttending} employees attending`;
  page.appendChild(title);

  // Mini grid
  const grid = _buildMiniGrid(blocks, dayView, groupsById);
  page.appendChild(grid);

  return page;
}

function _buildMiniGrid(blocks, dayView, groupsById) {
  const CELL = 90;
  const GAP = 4;

  if (!blocks.length) return document.createElement('div');

  const maxRow = Math.max(...blocks.map(b => b.row));
  const maxCol = Math.max(...blocks.map(b => b.col));

  const container = document.createElement('div');
  container.style.cssText = `
    display:grid;
    grid-template-columns: repeat(${maxCol + 1}, ${CELL}px);
    grid-template-rows: repeat(${maxRow + 1}, 70px);
    gap: ${GAP}px;
    margin: 12px 0;
  `;

  // Fill grid positions
  const blockMap = Object.fromEntries(blocks.map(b => [`${b.row}-${b.col}`, b]));
  for (let r = 0; r <= maxRow; r++) {
    for (let c = 0; c <= maxCol; c++) {
      const cell = document.createElement('div');
      const block = blockMap[`${r}-${c}`];
      if (block) {
        const chips = dayView[block.block_id] || [];
        const used = chips.reduce((s, [, n]) => s + n, 0);
        cell.style.cssText = `
          background:#fff; border:1px solid #CBD5E0; border-radius:4px;
          padding:3px; font-size:8px; overflow:hidden;
        `;
        const header = document.createElement('div');
        header.style.cssText = 'font-weight:600; color:#4A5568; margin-bottom:2px;';
        header.textContent = `${block.block_id} (${used}/${block.capacity})`;
        cell.appendChild(header);
        for (const [gid, count] of chips) {
          const chip = document.createElement('div');
          chip.style.cssText = `
            background:${groupColor(gid)}; color:#fff;
            border-radius:2px; padding:1px 3px; margin-bottom:1px;
            white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
          `;
          chip.textContent = count > 1 ? `${gid} ×${count}` : gid;
          cell.appendChild(chip);
        }
      } else {
        cell.style.cssText = 'background:#F7FAFC;';
      }
      container.appendChild(cell);
    }
  }
  return container;
}

function _buildSummaryPage(solution, groupsById, deptMap) {
  const page = document.createElement('div');
  page.className = 'print-page';

  const title = document.createElement('h2');
  title.textContent = 'Solution Summary';
  page.appendChild(title);

  // Metrics
  const metrics = document.createElement('div');
  metrics.style.cssText = 'margin-bottom:16px; font-size:13px;';
  metrics.innerHTML = `
    <strong>ID:</strong> ${solution.solution_id} &nbsp;|&nbsp;
    <strong>Score:</strong> ${(solution.score * 100).toFixed(1)}% &nbsp;|&nbsp;
    <strong>Compactness:</strong> ${((solution.score_breakdown?.compactness || 0) * 100).toFixed(1)}% &nbsp;|&nbsp;
    <strong>Consistency:</strong> ${((solution.score_breakdown?.consistency || 0) * 100).toFixed(1)}% &nbsp;|&nbsp;
    <strong>Cover pair:</strong> Days ${solution.cover_pair?.join(' & ')}
  `;
  page.appendChild(metrics);

  // Dept common days table
  const deptDays = _computeDeptCommonDays(solution, deptMap);
  if (Object.keys(deptDays).length) {
    const deptTitle = document.createElement('h3');
    deptTitle.textContent = 'Department Common Days';
    page.appendChild(deptTitle);

    const tbl = _buildTable(
      ['Department', 'Common Day(s)'],
      Object.entries(deptDays).map(([dept, days]) => [dept, days.join(', ')])
    );
    page.appendChild(tbl);
  }

  // Full schedule table
  const schedTitle = document.createElement('h3');
  schedTitle.textContent = 'Group Schedule';
  page.appendChild(schedTitle);

  const schedRows = _buildScheduleRows(solution, groupsById);
  page.appendChild(_buildTable(
    ['Group', 'Dept(s)', 'Size', 'Day 1 → Blocks', 'Day 2 → Blocks', 'Single Block'],
    schedRows
  ));

  return page;
}

function _computeDeptCommonDays(solution, deptMap) {
  const result = {};
  const dayAssignMap = Object.fromEntries(solution.day_assignments.map(da => [da.group_id, da.days]));
  for (const [dept, gids] of Object.entries(deptMap)) {
    const allDays = gids.map(gid => new Set(dayAssignMap[gid] || []));
    if (!allDays.length) continue;
    let common = allDays[0];
    for (const s of allDays.slice(1)) {
      common = new Set([...common].filter(d => s.has(d)));
    }
    if (common.size) result[dept] = [...common].sort();
  }
  return result;
}

function _buildScheduleRows(solution, groupsById) {
  const dayAssignMap = Object.fromEntries(solution.day_assignments.map(da => [da.group_id, da.days]));
  return solution.day_assignments.map(da => {
    const g = groupsById[da.group_id];
    const [d1, d2] = da.days;
    const b1 = solution.block_assignments
      .filter(ba => ba.group_id === da.group_id && ba.day === d1)
      .map(ba => ba.block_id).join(', ');
    const b2 = solution.block_assignments
      .filter(ba => ba.group_id === da.group_id && ba.day === d2)
      .map(ba => ba.block_id).join(', ');
    const bs1 = new Set(solution.block_assignments.filter(ba => ba.group_id === da.group_id && ba.day === d1).map(ba => ba.block_id));
    const bs2 = new Set(solution.block_assignments.filter(ba => ba.group_id === da.group_id && ba.day === d2).map(ba => ba.block_id));
    const single = bs1.size === 1 && bs2.size === 1 && [...bs1][0] === [...bs2][0] ? '✓' : '';
    return [
      da.group_id,
      g ? [...(Array.isArray(g.departments) ? g.departments : Object.keys(g.departments))].join(', ') : '',
      g ? g.size : '',
      `Day ${d1} → ${b1 || '—'}`,
      `Day ${d2} → ${b2 || '—'}`,
      single,
    ];
  });
}

function _buildDeptAttendancePage(solution, groupsById, deptMap) {
  const page = document.createElement('div');
  page.className = 'print-page';

  const title = document.createElement('h2');
  title.textContent = 'Department Attendance';
  page.appendChild(title);

  const dayAssignMap = Object.fromEntries(solution.day_assignments.map(da => [da.group_id, da.days]));

  for (const [dept, gids] of Object.entries(deptMap)) {
    const deptTitle = document.createElement('h3');
    deptTitle.style.cssText = 'margin-top:16px; margin-bottom:4px; font-size:13px;';
    deptTitle.textContent = dept;
    page.appendChild(deptTitle);

    const tbl = document.createElement('table');
    tbl.style.cssText = 'border-collapse:collapse; font-size:11px; margin-bottom:8px;';

    // Header
    const thead = tbl.createTHead();
    const hr = thead.insertRow();
    ['Group', 'Day 1', 'Day 2', 'Day 3', 'Day 4'].forEach(h => {
      const th = document.createElement('th');
      th.style.cssText = 'border:1px solid #CBD5E0; padding:4px 8px; background:#EDF2F7;';
      th.textContent = h;
      hr.appendChild(th);
    });

    const tbody = tbl.createTBody();
    for (const gid of gids) {
      const days = new Set(dayAssignMap[gid] || []);
      const tr = tbody.insertRow();
      // Group name
      const nameTd = tr.insertCell();
      nameTd.style.cssText = 'border:1px solid #CBD5E0; padding:4px 8px; font-weight:500;';
      nameTd.textContent = gid;
      // Days 1–4
      for (const d of [1, 2, 3, 4]) {
        const td = tr.insertCell();
        if (days.has(d)) {
          td.style.cssText = `border:1px solid #CBD5E0; padding:4px 8px; background:${groupColor(gid)};`;
        } else {
          td.style.cssText = 'border:1px solid #CBD5E0; padding:4px 8px; background:#F7FAFC;';
        }
      }
      tbody.appendChild(tr);
    }

    page.appendChild(tbl);
  }

  return page;
}

function _buildTable(headers, rows) {
  const tbl = document.createElement('table');
  tbl.style.cssText = 'border-collapse:collapse; font-size:11px; width:100%; margin-bottom:12px;';

  const thead = tbl.createTHead();
  const hr = thead.insertRow();
  headers.forEach(h => {
    const th = document.createElement('th');
    th.style.cssText = 'border:1px solid #CBD5E0; padding:4px 8px; background:#EDF2F7; text-align:left;';
    th.textContent = h;
    hr.appendChild(th);
  });

  const tbody = tbl.createTBody();
  for (const row of rows) {
    const tr = tbody.insertRow();
    for (const cell of row) {
      const td = tr.insertCell();
      td.style.cssText = 'border:1px solid #CBD5E0; padding:4px 8px;';
      td.textContent = cell;
    }
  }

  return tbl;
}
