// Tactical battle simulation. Real soldiers from the strategic layer fight here;
// the result flows back as persistent casualties, experience and territory.

import { TUNE, UNIT_TYPES, OBSTACLE } from './data.js';
import { fitForDuty, isVeteran } from './soldiers.js';
import { clamp, dist, dist2, makeRng, angleLerp } from './util.js';

const W = TUNE.battleW, H = TUNE.battleH, CELL = TUNE.cell;
const GW = Math.ceil(W / CELL), GH = Math.ceil(H / CELL);

// ---------------------------------------------------------------- terrain generation

function genTerrain(kind, rng, defendingSide) {
  // Obstacles: circles {x,y,r,kind} and rects {x,y,w,h,kind}. Hills are soft
  // zones (no blocking). Blocking sizes come from the sprites' own footprints
  // so what you see is what units actually collide with.
  const circles = [], rects = [], hills = [], decals = [];
  const tree = (x, y) => circles.push({ x, y, r: OBSTACLE.tree.r * rng.float(0.85, 1.25), kind: 'tree' });
  const rock = (x, y) => circles.push({ x, y, r: OBSTACLE.rock.r * rng.float(0.8, 1.3), kind: 'rock' });

  const scatter = (n, fn, minX = 120, maxX = W - 120) => {
    for (let i = 0; i < n; i++) {
      const x = rng.float(minX, maxX), y = rng.float(100, H - 100);
      // keep deployment lanes clear
      if (x < W * 0.27 || x > W - W * 0.27) continue;
      fn(x, y);
    }
  };

  if (kind === 'open') {
    scatter(10, tree); scatter(5, rock);
    hills.push({ x: rng.float(W * 0.3, W * 0.7), y: rng.float(300, H - 300), r: rng.float(180, 240) });
    for (let i = 0; i < 14; i++) decals.push({ x: rng.float(0, W), y: rng.float(0, H), kind: 'grass' });
  } else if (kind === 'forest') {
    scatter(46, tree);
    // a rough track through the middle
    for (let i = 0; i < 10; i++) decals.push({ x: rng.float(0, W), y: H / 2 + rng.float(-60, 60), kind: 'track' });
  } else if (kind === 'bridge') {
    // River band down the middle; the bridge is the only crossing.
    const rx = W / 2, half = 95, gapY = H / 2, gapH = 130;
    rects.push({ x: rx - half, y: 0, w: half * 2, h: gapY - gapH / 2, kind: 'river' });
    rects.push({ x: rx - half, y: gapY + gapH / 2, w: half * 2, h: H - gapY - gapH / 2, kind: 'river' });
    decals.push({ x: rx, y: gapY, kind: 'bridge', w: half * 2 + 60, h: gapH });
    scatter(8, tree, 120, rx - 200); scatter(8, tree, rx + 200, W - 120);
  } else if (kind === 'settlement') {
    const lanes = [H * 0.32, H * 0.55, H * 0.78];
    for (let i = 0; i < 7; i++) {
      const x = rng.float(W * 0.3, W * 0.68), y = rng.pick(lanes) + rng.float(-140, -60);
      rects.push({ x, y, w: OBSTACLE.house.w, h: OBSTACLE.house.d, kind: 'house' });
    }
    scatter(6, tree);
    for (let i = 0; i < 6; i++) decals.push({ x: rng.float(W * 0.25, W * 0.75), y: rng.float(150, H - 150), kind: 'fence' });
  } else if (kind === 'industrial') {
    for (let i = 0; i < 5; i++) {
      circles.push({ x: rng.float(W * 0.32, W * 0.68), y: rng.float(200, H - 200), r: OBSTACLE.boiler.r, kind: 'boiler' });
    }
    for (let i = 0; i < 4; i++) {
      rects.push({ x: rng.float(W * 0.3, W * 0.66), y: rng.float(180, H - 240), w: OBSTACLE.shed.w, h: OBSTACLE.shed.d, kind: 'shed' });
    }
    for (let i = 0; i < 5; i++) {
      rects.push({ x: rng.float(W * 0.28, W * 0.7), y: rng.float(160, H - 200), w: OBSTACLE.cart.w, h: OBSTACLE.cart.d, kind: 'cart' });
    }
    for (let i = 0; i < 8; i++) {
      circles.push({ x: rng.float(W * 0.3, W * 0.7), y: rng.float(150, H - 150), r: OBSTACLE.spoil.r, kind: 'spoil' });
    }
  } else if (kind === 'fort') {
    // Defender holds a walled position on their side with a gate gap.
    const wx = defendingSide === 'right' ? W * 0.62 : W * 0.38;
    const gateY = H / 2, gateH = 150;
    const wt = OBSTACLE.wall.thickness;
    const ts = { d: OBSTACLE.tower.size };
    rects.push({ x: wx - wt / 2, y: 120, w: wt, h: gateY - gateH / 2 - 120, kind: 'wall' });
    rects.push({ x: wx - wt / 2, y: gateY + gateH / 2, w: wt, h: H - 120 - (gateY + gateH / 2), kind: 'wall' });
    rects.push({ x: wx - ts.d / 2, y: 80 - ts.d / 2, w: ts.d, h: ts.d, kind: 'tower' });
    rects.push({ x: wx - ts.d / 2, y: H - 110 - ts.d / 2, w: ts.d, h: ts.d, kind: 'tower' });
    scatter(6, tree, 120, wx - 300);
    decals.push({ x: wx, y: gateY, kind: 'gate', w: 30, h: gateH });
  }
  return { circles, rects, hills, decals, kind };
}

function rasterize(terrain) {
  const grid = new Uint8Array(GW * GH); // 0 = passable
  for (const c of terrain.circles) {
    const x0 = Math.max(0, Math.floor((c.x - c.r) / CELL)), x1 = Math.min(GW - 1, Math.floor((c.x + c.r) / CELL));
    const y0 = Math.max(0, Math.floor((c.y - c.r) / CELL)), y1 = Math.min(GH - 1, Math.floor((c.y + c.r) / CELL));
    for (let gy = y0; gy <= y1; gy++) for (let gx = x0; gx <= x1; gx++) {
      const cx = gx * CELL + CELL / 2, cy = gy * CELL + CELL / 2;
      if (dist(cx, cy, c.x, c.y) < c.r + 6) grid[gy * GW + gx] = 1;
    }
  }
  for (const r of terrain.rects) {
    const x0 = Math.max(0, Math.floor(r.x / CELL)), x1 = Math.min(GW - 1, Math.floor((r.x + r.w) / CELL));
    const y0 = Math.max(0, Math.floor(r.y / CELL)), y1 = Math.min(GH - 1, Math.floor((r.y + r.h) / CELL));
    for (let gy = y0; gy <= y1; gy++) for (let gx = x0; gx <= x1; gx++) grid[gy * GW + gx] = 1;
  }
  return grid;
}

// ---------------------------------------------------------------- A* pathfinding

function findPath(grid, sx, sy, tx, ty) {
  let s = cellOf(sx, sy), t = cellOf(tx, ty);
  if (grid[t]) t = nearestOpen(grid, t);
  if (grid[s]) s = nearestOpen(grid, s);
  if (s === t || s < 0 || t < 0) return [{ x: tx, y: ty }];

  const open = [s], came = new Map(), g = new Map([[s, 0]]), f = new Map([[s, hDist(s, t)]]);
  const inOpen = new Set([s]);
  let guard = 0;
  while (open.length > 0 && guard++ < 4000) {
    // smallest-f pop (linear scan is fine at this grid size)
    let bi = 0;
    for (let i = 1; i < open.length; i++) if ((f.get(open[i]) ?? 1e9) < (f.get(open[bi]) ?? 1e9)) bi = i;
    const cur = open.splice(bi, 1)[0];
    inOpen.delete(cur);
    if (cur === t) {
      const cells = [cur];
      let c = cur;
      while (came.has(c)) { c = came.get(c); cells.push(c); }
      cells.reverse();
      const path = smooth(grid, cells).map(i => ({ x: (i % GW) * CELL + CELL / 2, y: Math.floor(i / GW) * CELL + CELL / 2 }));
      path.push({ x: tx, y: ty });
      return path;
    }
    const cx = cur % GW, cy = Math.floor(cur / GW);
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
      if (dx === 0 && dy === 0) continue;
      const nx = cx + dx, ny = cy + dy;
      if (nx < 0 || ny < 0 || nx >= GW || ny >= GH) continue;
      const n = ny * GW + nx;
      if (grid[n]) continue;
      if (dx !== 0 && dy !== 0 && (grid[cy * GW + nx] || grid[ny * GW + cx])) continue; // no corner cutting
      const ng = g.get(cur) + (dx && dy ? 1.414 : 1);
      if (ng < (g.get(n) ?? 1e9)) {
        came.set(n, cur); g.set(n, ng); f.set(n, ng + hDist(n, t));
        if (!inOpen.has(n)) { open.push(n); inOpen.add(n); }
      }
    }
  }
  return [{ x: tx, y: ty }]; // fallback: walk straight, separation will cope
}

const cellOf = (x, y) => clamp(Math.floor(y / CELL), 0, GH - 1) * GW + clamp(Math.floor(x / CELL), 0, GW - 1);
function hDist(a, b) {
  const ax = a % GW, ay = Math.floor(a / GW), bx = b % GW, by = Math.floor(b / GW);
  return Math.hypot(ax - bx, ay - by);
}
function nearestOpen(grid, c) {
  const cx = c % GW, cy = Math.floor(c / GW);
  for (let r = 1; r < 8; r++) {
    for (let dy = -r; dy <= r; dy++) for (let dx = -r; dx <= r; dx++) {
      const nx = cx + dx, ny = cy + dy;
      if (nx < 0 || ny < 0 || nx >= GW || ny >= GH) continue;
      if (!grid[ny * GW + nx]) return ny * GW + nx;
    }
  }
  return -1;
}
function losClear(grid, a, b) {
  const ax = a % GW, ay = Math.floor(a / GW), bx = b % GW, by = Math.floor(b / GW);
  const steps = Math.max(Math.abs(bx - ax), Math.abs(by - ay));
  for (let i = 1; i < steps; i++) {
    const gx = Math.round(ax + (bx - ax) * i / steps), gy = Math.round(ay + (by - ay) * i / steps);
    if (grid[gy * GW + gx]) return false;
  }
  return true;
}
function smooth(grid, cells) {
  if (cells.length <= 2) return cells;
  const out = [cells[0]];
  let i = 0;
  while (i < cells.length - 1) {
    let j = cells.length - 1;
    while (j > i + 1 && !losClear(grid, cells[i], cells[j])) j--;
    out.push(cells[j]);
    i = j;
  }
  return out;
}

// ---------------------------------------------------------------- battle setup

let unitSeq = 1;

function makeUnit(soldier, side, x, y) {
  const def = UNIT_TYPES[soldier.type];
  const vet = isVeteran(soldier);
  const hpMul = vet ? 1.15 : 1;
  return {
    uid: unitSeq++,
    soldier, type: soldier.type, def, side, vet,
    x, y, facing: side === 'left' ? 0 : Math.PI,
    hp: def.hp * hpMul, maxHp: def.hp * hpMul,
    state: 'idle',            // idle | moving | fighting | routing | dead | fled
    orderPos: null, orderTargetUid: null, attackMove: false,
    path: null, pathIdx: 0, repathT: 0, thinkT: Math.random() * 0.4,
    cooldown: 1 + Math.random(), meleeCd: 0,
    morale: def.moraleBase + (vet ? 12 : 0), moraleMax: def.moraleBase + (vet ? 12 : 0),
    chargeT: 0, chargeReady: true, chargeCd: 0,
    vx: 0, vy: 0,
  };
}

function deployLine(units, cx, cy, facing, spacing = 28) {
  // Melee front, ranged behind, cavalry on the wings, hero at the rear-center.
  const melee = units.filter(u => !u.def.range && !u.def.cavalry && u.type !== 'hero');
  const ranged = units.filter(u => u.def.range > 0);
  const cav = units.filter(u => u.def.cavalry);
  const hero = units.filter(u => u.type === 'hero');
  const dir = facing === 0 ? 1 : -1;
  const place = (list, backOff, spread) => {
    const n = list.length;
    if (!n) return;
    const perRow = Math.max(4, Math.ceil(n / 2));
    list.forEach((u, i) => {
      const row = Math.floor(i / perRow), col = i % perRow;
      const rowN = Math.min(perRow, n - row * perRow);
      u.x = clamp(cx - dir * (backOff + row * spacing), 30, W - 30);
      u.y = clamp(cy + (col - (rowN - 1) / 2) * spread, 30, H - 30);
      u.facing = facing;
    });
  };
  place(melee, 0, spacing);
  place(ranged, spacing * 2.2, spacing);
  cav.forEach((u, i) => {
    u.x = clamp(cx - dir * spacing, 30, W - 30);
    u.y = clamp(cy + (i % 2 === 0 ? 1 : -1) * (120 + Math.floor(i / 2) * 26), 30, H - 30);
    u.facing = facing;
  });
  place(hero, spacing * 3.4, spacing);
}

export function startBattle(ctx) {
  // ctx: { playerSoldiers, enemySoldiers, terrain, defending, enemyFaction, locName, seed }
  const rng = makeRng(ctx.seed ?? ((Math.random() * 1e9) | 0));
  const playerSide = ctx.defending && (ctx.terrain === 'fort' || ctx.terrain === 'bridge') ? 'right' : 'left';
  const enemySide = playerSide === 'left' ? 'right' : 'left';
  const terrain = genTerrain(ctx.terrain, rng, ctx.defending ? playerSide : enemySide);
  const grid = rasterize(terrain);

  const b = {
    ctx, terrain, grid, rng,
    w: W, h: H,
    units: [], projectiles: [], effects: [],
    selection: new Set(), groups: {}, formationType: 'line',
    time: 0, state: 'running', result: null,
    aiT: 2, aiMode: ctx.defending ? 'attack' : (ctx.terrain === 'fort' ? 'hold' : 'advance'),
    rallyCd: 0,
    heroWasd: { up: false, down: false, left: false, right: false },
    startCounts: { player: 0, enemy: 0 },
  };

  const pFit = fitForDuty(ctx.playerSoldiers).slice(0, 48);
  const eFit = fitForDuty(ctx.enemySoldiers).slice(0, 48);
  const px = playerSide === 'left' ? W * 0.2 : W * 0.8;
  const ex = enemySide === 'left' ? W * 0.2 : W * 0.8;
  const pUnits = pFit.map(s => makeUnit(s, playerSide, px, H / 2));
  const eUnits = eFit.map(s => makeUnit(s, enemySide, ex, H / 2));
  deployLine(pUnits, px, H / 2, playerSide === 'left' ? 0 : Math.PI);
  deployLine(eUnits, ex, H / 2, enemySide === 'left' ? 0 : Math.PI);
  for (const u of pUnits) u.player = true;
  for (const u of eUnits) u.player = false;
  b.units = [...pUnits, ...eUnits];
  b.startCounts.player = pUnits.length;
  b.startCounts.enemy = eUnits.length;
  b.playerSide = playerSide;

  // nudge everyone off blocked cells
  for (const u of b.units) {
    if (b.grid[cellOf(u.x, u.y)]) {
      const open = nearestOpen(b.grid, cellOf(u.x, u.y));
      if (open >= 0) { u.x = (open % GW) * CELL + CELL / 2; u.y = Math.floor(open / GW) * CELL + CELL / 2; }
    }
  }
  return b;
}

// ---------------------------------------------------------------- queries

export const aliveUnits = (b, player) => b.units.filter(u => u.player === player && u.state !== 'dead' && u.state !== 'fled');
export const fightingUnits = (b, player) => aliveUnits(b, player).filter(u => u.state !== 'routing');
export const heroUnit = (b) => b.units.find(u => u.type === 'hero' && u.player);
export const unitAt = (b, x, y, r = 14) => {
  let best = null, bd = r * r;
  for (const u of b.units) {
    if (u.state === 'dead' || u.state === 'fled') continue;
    const d = dist2(x, y, u.x, u.y);
    if (d < bd) { bd = d; best = u; }
  }
  return best;
};

// ---------------------------------------------------------------- player commands

export function selectOne(b, unit, additive) {
  if (!additive) b.selection.clear();
  if (unit && unit.player && unit.state !== 'routing') b.selection.add(unit.uid);
}

export function selectBox(b, x0, y0, x1, y1, additive) {
  if (!additive) b.selection.clear();
  const xa = Math.min(x0, x1), xb = Math.max(x0, x1), ya = Math.min(y0, y1), yb = Math.max(y0, y1);
  for (const u of aliveUnits(b, true)) {
    if (u.state === 'routing') continue;
    if (u.x >= xa && u.x <= xb && u.y >= ya && u.y <= yb) b.selection.add(u.uid);
  }
}

export function selectSameType(b, unit) {
  if (!unit || !unit.player) return;
  b.selection.clear();
  for (const u of aliveUnits(b, true)) if (u.type === unit.type && u.state !== 'routing') b.selection.add(u.uid);
}

export function selectedUnits(b) {
  return b.units.filter(u => b.selection.has(u.uid) && u.state !== 'dead' && u.state !== 'fled' && u.state !== 'routing');
}

const FORM_SPACING = { line: { gap: 28, ranks: 2 }, deep: { gap: 26, ranks: 4 }, loose: { gap: 44, ranks: 2 } };

// Formation slots can land inside a wall or a boiler. Pull them onto walkable
// ground so a move order is always something a soldier can actually finish.
function snapOpen(b, x, y) {
  const c = cellOf(x, y);
  if (!b.grid[c]) return { x, y };
  const open = nearestOpen(b.grid, c);
  if (open < 0) return { x, y };
  return { x: (open % GW) * CELL + CELL / 2, y: Math.floor(open / GW) * CELL + CELL / 2 };
}

// A group advances at the pace of its slowest soldier, so the commander and
// the cavalry do not arrive alone and get killed ahead of the line.
function groupPace(sel) {
  return sel.length > 1 ? Math.min(...sel.map(u => u.def.speed)) : Infinity;
}

export function commandMove(b, x, y, attackMove = false) {
  const sel = selectedUnits(b);
  if (sel.length === 0) return false;
  const pace = groupPace(sel);
  const form = FORM_SPACING[b.formationType] || FORM_SPACING.line;
  // Face along average approach direction; build slots perpendicular to it.
  let mx = 0, my = 0;
  for (const u of sel) { mx += u.x; my += u.y; }
  mx /= sel.length; my /= sel.length;
  const ang = Math.atan2(y - my, x - mx);
  const perp = ang + Math.PI / 2;
  const n = sel.length;
  const ranks = Math.min(form.ranks + Math.floor(n / 14), 5);
  const perRow = Math.ceil(n / ranks);
  // Sort units along the perpendicular axis so lines don't cross while forming.
  const px = Math.cos(perp), py = Math.sin(perp);
  const ordered = [...sel].sort((a, bU) => (a.x * px + a.y * py) - (bU.x * px + bU.y * py));
  ordered.forEach((u, i) => {
    const row = Math.floor(i / perRow), col = i % perRow;
    const rowN = Math.min(perRow, n - row * perRow);
    const off = (col - (rowN - 1) / 2) * form.gap;
    const back = row * form.gap;
    const tx = clamp(x + px * off - Math.cos(ang) * back, 20, W - 20);
    const ty = clamp(y + py * off - Math.sin(ang) * back, 20, H - 20);
    u.orderPos = snapOpen(b, tx, ty);
    u.orderTargetUid = null;
    u.attackMove = attackMove;
    u.speedCap = pace;
    u.path = null; u.pathIdx = 0;
    if (u.state !== 'routing') u.state = 'moving';
  });
  b.effects.push({ type: 'order', x, y, attackMove });
  return true;
}

export function commandAttack(b, target) {
  const sel = selectedUnits(b);
  if (sel.length === 0 || !target || target.player) return false;
  const pace = groupPace(sel);
  for (const u of sel) {
    u.orderTargetUid = target.uid;
    u.orderPos = null;
    u.attackMove = false;
    u.speedCap = pace;
    u.path = null; u.pathIdx = 0;
    if (u.state !== 'routing') u.state = 'moving';
  }
  b.effects.push({ type: 'order', x: target.x, y: target.y, attackMove: true });
  return true;
}

export function setGroup(b, n) {
  b.groups[n] = [...b.selection];
}
export function recallGroup(b, n) {
  const ids = b.groups[n];
  if (!ids || ids.length === 0) return;
  b.selection.clear();
  for (const id of ids) {
    const u = b.units.find(v => v.uid === id);
    if (u && u.state !== 'dead' && u.state !== 'fled' && u.state !== 'routing') b.selection.add(id);
  }
}

export function rally(b) {
  const hero = heroUnit(b);
  if (!hero || hero.state === 'dead' || b.rallyCd > 0) return false;
  b.rallyCd = 40;
  // A rally that puts troops back in the fight also calls off a withdrawal —
  // otherwise the battle would still resolve as a forfeit.
  b.withdrawing = false;
  for (const u of aliveUnits(b, true)) {
    if (dist(u.x, u.y, hero.x, hero.y) < 230) {
      u.morale = Math.min(u.moraleMax, u.morale + 30);
      if (u.state === 'routing') u.state = 'idle'; // rally can recover breaking troops
    }
  }
  b.effects.push({ type: 'rally', x: hero.x, y: hero.y });
  return true;
}

export function withdraw(b) {
  if (b.state !== 'running') return;
  for (const u of aliveUnits(b, true)) { u.state = 'routing'; u.morale = 0; }
  b.withdrawing = true;
}

// ---------------------------------------------------------------- combat helpers

function damageUnit(b, target, dmg, source, isRanged, fromX, fromY) {
  if (target.state === 'dead' || target.state === 'fled') return;
  let final = dmg;
  if (isRanged && target.def.shieldBlock) {
    // Shields block arrows arriving from the front arc.
    const inc = Math.atan2(target.y - fromY, target.x - fromX);
    let rel = inc - target.facing;
    while (rel > Math.PI) rel -= 2 * Math.PI;
    while (rel < -Math.PI) rel += 2 * Math.PI;
    // arrow's travel direction vs facing: blocked if it comes at the face
    if (Math.abs(rel) > Math.PI / 2) final *= (1 - target.def.shieldBlock);
  }
  // multiplicative armor keeps cheap troops relevant against heavy ones;
  // pressure-driven bolts (def.pierce) punch straight through it
  const armorFac = 1 - Math.min(0.6, target.def.armor * (isRanged ? 0.16 : 0.12));
  if (!(isRanged && source && source.def && source.def.pierce)) final *= armorFac;
  final = Math.max(1, final);
  target.hp -= final;
  b.effects.push({ type: 'hit', x: target.x, y: target.y, ranged: isRanged });
  if (target.hp <= 0) {
    target.state = 'dead';
    target.deadT = 0;
    b.selection.delete(target.uid);
    b.effects.push({ type: 'death', x: target.x, y: target.y, unitType: target.type });
    const killer = source && source.soldier ? source.soldier : null;
    if (killer) { killer.kills++; killer.xp += TUNE.xpKill; }
    // Nearby allies flinch.
    for (const u of b.units) {
      if (u.player !== target.player || u.state === 'dead' || u.state === 'fled') continue;
      if (dist2(u.x, u.y, target.x, target.y) < 110 * 110) u.morale -= u.type === 'hero' ? 0 : 4;
    }
  } else {
    target.morale -= final * 0.25;
  }
}

function fireProjectile(b, shooter, target) {
  const def = shooter.def;
  const lead = def.projSpeed > 0 ? dist(shooter.x, shooter.y, target.x, target.y) / def.projSpeed : 0;
  const tx = target.x + (target.vx || 0) * lead * 0.7;
  const ty = target.y + (target.vy || 0) * lead * 0.7;
  const d = dist(shooter.x, shooter.y, tx, ty) || 1;
  b.projectiles.push({
    x: shooter.x, y: shooter.y, sx: shooter.x, sy: shooter.y,
    tx, ty, t: 0, dur: d / def.projSpeed,
    dmg: def.rangedDmg * (shooter.vet ? 1.15 : 1),
    pierce: !!def.pierce, arc: def.projArc, side: shooter.side, player: shooter.player,
    shooter,
  });
  shooter.cooldown = def.reload * (0.9 + Math.random() * 0.2);
  b.effects.push({ type: def.steamShot ? 'steamshot' : 'shot', x: shooter.x, y: shooter.y });
}

// ---------------------------------------------------------------- enemy AI

function enemyAiThink(b) {
  const foes = fightingUnits(b, true);
  const mine = fightingUnits(b, false);
  if (foes.length === 0 || mine.length === 0) return;
  let fx = 0, fy = 0;
  for (const f of foes) { fx += f.x; fy += f.y; }
  fx /= foes.length; fy /= foes.length;

  const engaged = mine.some(u => u.engagedT > 0);
  const underFire = mine.some(u => u.hitRecently);
  if (b.aiMode === 'hold' && (engaged || underFire || foes.some(f => dist(f.x, f.y, mine[0].x, mine[0].y) < 380))) {
    b.aiMode = 'attack';
  }

  const ranged = mine.filter(u => u.def.range > 0);
  const melee = mine.filter(u => !u.def.range && !u.def.cavalry);
  const cav = mine.filter(u => u.def.cavalry);

  const nearestFoe = (u) => {
    let best = null, bd = 1e12;
    for (const f of foes) { const d = dist2(u.x, u.y, f.x, f.y); if (d < bd) { bd = d; best = f; } }
    return best;
  };

  if (b.aiMode === 'attack' || b.aiMode === 'advance') {
    for (const u of melee) {
      if (u.orderTargetUid) {
        const t = b.units.find(v => v.uid === u.orderTargetUid);
        if (t && t.state !== 'dead' && t.state !== 'fled') continue;
      }
      const f = nearestFoe(u);
      if (f) { u.orderTargetUid = f.uid; u.orderPos = null; u.path = null; u.state = 'moving'; }
    }
    for (const u of ranged) {
      const f = nearestFoe(u);
      if (!f) continue;
      const d = dist(u.x, u.y, f.x, f.y);
      if (d > u.def.range * 0.85) {
        const ang = Math.atan2(f.y - u.y, f.x - u.x);
        u.orderPos = { x: u.x + Math.cos(ang) * (d - u.def.range * 0.75), y: u.y + Math.sin(ang) * (d - u.def.range * 0.75) };
        u.orderTargetUid = null; u.path = null; u.state = 'moving'; u.attackMove = true;
      } else if (d < u.def.range * 0.35) {
        // fall back from the melee line
        const ang = Math.atan2(u.y - f.y, u.x - f.x);
        u.orderPos = { x: clamp(u.x + Math.cos(ang) * 120, 20, W - 20), y: clamp(u.y + Math.sin(ang) * 120, 20, H - 20) };
        u.orderTargetUid = null; u.path = null; u.state = 'moving'; u.attackMove = true;
      }
    }
    // Cavalry hunts the enemy's ranged units.
    const softTargets = foes.filter(f => f.def.range > 0);
    for (const u of cav) {
      if (u.orderTargetUid) {
        const t = b.units.find(v => v.uid === u.orderTargetUid);
        if (t && t.state !== 'dead' && t.state !== 'fled') continue;
      }
      const pool = softTargets.length > 0 ? softTargets : foes;
      let best = null, bd = 1e12;
      for (const f of pool) { const d = dist2(u.x, u.y, f.x, f.y); if (d < bd) { bd = d; best = f; } }
      if (best) { u.orderTargetUid = best.uid; u.orderPos = null; u.path = null; u.state = 'moving'; }
    }
  } else if (b.aiMode === 'hold') {
    // Defensive stance: ranged shoot at will (handled per-unit), melee stand ground.
  }
}

// ---------------------------------------------------------------- per-frame update

export function updateBattle(b, dt, keys) {
  if (b.state !== 'running') return;
  b.time += dt;
  b.rallyCd = Math.max(0, b.rallyCd - dt);

  b.aiT -= dt;
  if (b.aiT <= 0) { b.aiT = 1.1; enemyAiThink(b); }

  // Spatial hash for separation + target queries.
  const hash = new Map();
  const hcell = 52;
  const hkey = (x, y) => ((x / hcell) | 0) * 4096 + ((y / hcell) | 0);
  const alive = b.units.filter(u => u.state !== 'dead' && u.state !== 'fled');
  for (const u of alive) {
    const k = hkey(u.x, u.y);
    if (!hash.has(k)) hash.set(k, []);
    hash.get(k).push(u);
  }
  const neighbors = (x, y) => {
    const out = [];
    const cx = (x / hcell) | 0, cy = (y / hcell) | 0;
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
      const arr = hash.get((cx + dx) * 4096 + (cy + dy));
      if (arr) out.push(...arr);
    }
    return out;
  };

  const hero = heroUnit(b);
  const heroSel = hero && b.selection.size === 1 && b.selection.has(hero.uid);

  // side-wide morale pressure
  const pAlive = aliveUnits(b, true).length, eAlive = aliveUnits(b, false).length;
  const pLossRatio = 1 - pAlive / Math.max(1, b.startCounts.player);
  const eLossRatio = 1 - eAlive / Math.max(1, b.startCounts.enemy);

  for (const u of alive) {
    // a unit killed earlier in this same frame must not act (or un-die)
    if (u.state === 'dead' || u.state === 'fled') continue;
    u.engagedT = Math.max(0, (u.engagedT || 0) - dt);
    u.hitRecently = false;
    u.cooldown = Math.max(0, u.cooldown - dt);
    u.meleeCd = Math.max(0, u.meleeCd - dt);
    u.chargeCd = Math.max(0, u.chargeCd - dt);

    // ---- morale
    if (u.type !== 'hero') {
      const lossRatio = u.player ? pLossRatio : eLossRatio;
      if (lossRatio > 0.5) u.morale -= 1.6 * dt * (lossRatio - 0.5) * 4;
      const sideAlive = u.player ? pAlive : eAlive;
      const foesAlive = u.player ? eAlive : pAlive;
      if (foesAlive > sideAlive * 2) u.morale -= 0.9 * dt;
      // hero steadies nearby friendlies
      if (u.player && hero && hero.state !== 'dead' && dist2(u.x, u.y, hero.x, hero.y) < 160 * 160) {
        u.morale = Math.min(u.moraleMax, u.morale + 2.4 * dt);
        u.morale = Math.max(u.morale, 12); // won't break while the commander stands close
      } else {
        u.morale = Math.min(u.moraleMax, u.morale + 0.7 * dt);
      }
      if (u.morale <= 0 && u.state !== 'routing' && u.state !== 'dead') {
        u.state = 'routing';
        u.orderPos = null; u.orderTargetUid = null; u.path = null;
        b.selection.delete(u.uid);
        b.effects.push({ type: 'rout', x: u.x, y: u.y, player: u.player });
      }
    }

    // ---- decide movement intent
    let desiredX = 0, desiredY = 0;
    let speed = u.def.speed * (u.vet ? 1.05 : 1);
    // Hold formation pace only while executing the order that set it.
    if (u.speedCap && (u.orderPos || u.orderTargetUid)) speed = Math.min(speed, u.speedCap);
    else u.speedCap = 0;

    if (u.state === 'routing') {
      const edgeX = u.side === 'left' ? -60 : W + 60;
      desiredX = edgeX - u.x; desiredY = (H / 2 - u.y) * 0.1;
      speed *= 1.2;
      u.routT = (u.routT || 0) + dt;
      // Broken troops scatter off the field; never let one snag on scenery and
      // hold the whole battle open.
      if (u.x < -30 || u.x > W + 30 || u.routT > 22) { u.state = 'fled'; continue; }
    } else if (u.player && heroSel && u === hero) {
      // direct WASD control
      let kx = 0, ky = 0;
      if (keys['w']) ky -= 1; if (keys['s']) ky += 1;
      if (keys['a']) kx -= 1; if (keys['d']) kx += 1;
      if (kx || ky) {
        const n = Math.hypot(kx, ky);
        desiredX = kx / n * 100; desiredY = ky / n * 100;
        u.orderPos = null; u.orderTargetUid = null; u.path = null;
        u.state = 'moving';
      }
    }

    if (u.state !== 'routing' && !(u === hero && heroSel && (desiredX || desiredY))) {
      // target pursuit
      let target = null;
      if (u.orderTargetUid) {
        target = b.units.find(v => v.uid === u.orderTargetUid);
        if (!target || target.state === 'dead' || target.state === 'fled') {
          u.orderTargetUid = null; target = null;
          if (!u.orderPos) u.state = 'idle';
        }
      }

      // A unit with no standing orders defends itself: it acquires and engages
      // nearby enemies on its own, whatever animation state it happens to be in.
      const unordered = !u.orderPos && !u.orderTargetUid;

      // autonomous target acquisition (attack-move, unordered troops, or ranged units in reach)
      u.thinkT -= dt;
      if (!target && u.thinkT <= 0) {
        u.thinkT = 0.3 + Math.random() * 0.25;
        const aggro = u.type === 'hero' ? 110 : u.def.range > 0 ? u.def.range : (u.attackMove || unordered ? 190 : 60);
        let best = null, bd = aggro * aggro;
        for (const v of neighbors(u.x, u.y)) {
          if (v.player === u.player || v.state === 'dead' || v.state === 'fled') continue;
          const d = dist2(u.x, u.y, v.x, v.y);
          if (d < bd) { bd = d; best = v; }
        }
        if (!best && u.def.range > 0) {
          // ranged scan beyond hash cells
          bd = u.def.range * u.def.range;
          for (const v of alive) {
            if (v.player === u.player) continue;
            const d = dist2(u.x, u.y, v.x, v.y);
            if (d < bd) { bd = d; best = v; }
          }
        }
        if (best && (unordered || u.attackMove || u.def.range > 0)) u.autoTarget = best.uid;
        else u.autoTarget = null;
      }
      const auto = u.autoTarget ? b.units.find(v => v.uid === u.autoTarget && v.state !== 'dead' && v.state !== 'fled') : null;
      const engageTarget = target || auto;

      if (engageTarget) {
        const d = dist(u.x, u.y, engageTarget.x, engageTarget.y);
        const meleeReach = u.def.radius + engageTarget.def.radius + 7;

        if (u.def.range > 0 && d <= u.def.range && d > meleeReach * 1.6) {
          // ranged attack: stand and shoot
          u.facing = angleLerp(u.facing, Math.atan2(engageTarget.y - u.y, engageTarget.x - u.x), 0.2);
          if (u.cooldown <= 0) fireProjectile(b, u, engageTarget);
          u.state = target || u.attackMove ? 'fighting' : u.state === 'moving' && u.orderPos ? 'moving' : 'fighting';
          if (u.orderPos && !u.attackMove && target === null) {
            // keep walking to ordered position while shooting opportunistically
          } else {
            desiredX = 0; desiredY = 0;
            u.path = null;
          }
        } else if (d <= meleeReach) {
          // melee
          u.state = 'fighting';
          u.engagedT = 0.6;
          engageTarget.engagedT = 0.6;
          u.facing = angleLerp(u.facing, Math.atan2(engageTarget.y - u.y, engageTarget.x - u.x), 0.25);
          desiredX = 0; desiredY = 0;
          u.path = null;
          if (u.meleeCd <= 0) {
            u.meleeCd = u.def.meleeRate * (0.9 + Math.random() * 0.2);
            let dmg = u.def.meleeDmg * (u.vet ? 1.15 : 1);
            if (u.def.vsCavalry && engageTarget.def.cavalry) dmg *= u.def.vsCavalry;
            if (u.def.cavalry && u.chargeReady && u.chargeT > 0.5) {
              dmg += u.def.chargeDmg;
              u.chargeReady = false; u.chargeCd = 6;
              b.effects.push({ type: 'charge', x: u.x, y: u.y });
              // spearmen counter the charge itself
              if (engageTarget.def.vsCavalry) damageUnit(b, u, engageTarget.def.meleeDmg * engageTarget.def.vsCavalry * 0.8, engageTarget, false, engageTarget.x, engageTarget.y);
            }
            damageUnit(b, engageTarget, dmg, u, false, u.x, u.y);
            b.effects.push({ type: 'melee', x: (u.x + engageTarget.x) / 2, y: (u.y + engageTarget.y) / 2 });
          }
        } else if (target || u.attackMove || (unordered && d < 220 && !u.def.range)) {
          // close the distance
          const gd = Math.hypot(engageTarget.x - u.x, engageTarget.y - u.y);
          u.repathT -= dt;
          const direct = losClear(b.grid, cellOf(u.x, u.y), cellOf(engageTarget.x, engageTarget.y));
          if (direct) {
            desiredX = (engageTarget.x - u.x) / gd * 100;
            desiredY = (engageTarget.y - u.y) / gd * 100;
            u.path = null;
          } else if (!u.path || u.repathT <= 0) {
            u.path = findPath(b.grid, u.x, u.y, engageTarget.x, engageTarget.y);
            u.pathIdx = 0; u.repathT = 0.8;
          }
          u.state = 'moving';
        }
      }

      // path/order movement when not otherwise engaged
      if (!engageTarget || (u.orderPos && !u.attackMove && !target)) {
        if (u.orderPos) {
          const d = dist(u.x, u.y, u.orderPos.x, u.orderPos.y);
          if (d < 8) {
            u.orderPos = null; u.path = null;
            if (u.state === 'moving') u.state = 'idle';
          } else {
            if (!u.path) {
              const direct = losClear(b.grid, cellOf(u.x, u.y), cellOf(u.orderPos.x, u.orderPos.y));
              u.path = direct ? [{ x: u.orderPos.x, y: u.orderPos.y }] : findPath(b.grid, u.x, u.y, u.orderPos.x, u.orderPos.y);
              u.pathIdx = 0;
            }
          }
        }
      }
      // Walk whatever path we hold — including one found around a building while
      // chasing an enemy — unless something already set a heading this frame.
      if (u.path && u.path.length > 0 && !desiredX && !desiredY) {
        let wp = u.path[u.pathIdx];
        while (wp && dist(u.x, u.y, wp.x, wp.y) < 14) {
          u.pathIdx++;
          wp = u.path[u.pathIdx];
        }
        if (!wp) { u.path = null; }
        else {
          const d = dist(u.x, u.y, wp.x, wp.y) || 1;
          desiredX = (wp.x - u.x) / d * 100;
          desiredY = (wp.y - u.y) / d * 100;
        }
      }
    }

    // charge buildup for cavalry: sustained fast approach primes the lance
    const moving = (desiredX || desiredY);
    if (u.def.cavalry) {
      if (moving && u.chargeCd <= 0) {
        u.chargeT = (u.chargeT || 0) + dt;
        if (u.chargeT > 0.9) u.chargeReady = true;
      } else if (!moving) {
        u.chargeT = 0;
      }
    }

    // Nothing left to do and standing still: drop back to idle so the unit can
    // pick up new work next tick instead of being stranded in a stale state.
    if (!moving && u.state === 'moving' && !u.orderPos && !u.path) u.state = 'idle';

    // ---- integrate movement with separation
    let vx = 0, vy = 0;
    if (moving) {
      const n = Math.hypot(desiredX, desiredY) || 1;
      vx = desiredX / n * speed;
      vy = desiredY / n * speed;
      if (u.state === 'idle') u.state = 'moving';
    }
    // separation
    let sx = 0, sy = 0;
    for (const v of neighbors(u.x, u.y)) {
      if (v === u || v.state === 'dead' || v.state === 'fled') continue;
      const dx = u.x - v.x, dy = u.y - v.y;
      const rr = u.def.radius + v.def.radius + 2;
      const d2v = dx * dx + dy * dy;
      if (d2v < rr * rr && d2v > 0.01) {
        const d = Math.sqrt(d2v);
        const push = (rr - d) / rr * (v.def.mass / (u.def.mass + v.def.mass)) * 60;
        sx += dx / d * push; sy += dy / d * push;
      }
    }
    u.vx = vx; u.vy = vy;
    const prevX = u.x, prevY = u.y;
    let nx = u.x + (vx + sx) * dt;
    let ny = u.y + (vy + sy) * dt;
    const insideWall = b.grid[cellOf(u.x, u.y)];
    if (insideWall) {
      // Shoved inside scenery (crowding at a gate, a wall rasterized over a
      // spawn): walk straight back out instead of being pinned there forever.
      const open = nearestOpen(b.grid, cellOf(u.x, u.y));
      if (open >= 0) {
        const ox = (open % GW) * CELL + CELL / 2, oy = Math.floor(open / GW) * CELL + CELL / 2;
        const d = Math.hypot(ox - u.x, oy - u.y) || 1;
        nx = u.x + (ox - u.x) / d * Math.max(speed, 40) * dt;
        ny = u.y + (oy - u.y) / d * Math.max(speed, 40) * dt;
        u.path = null;
      }
    } else if (u.state !== 'routing' && b.grid[cellOf(nx, ny)]) {
      // obstacle rejection: slide along the blockage (routers push through —
      // they are leaving the field, not navigating it)
      if (!b.grid[cellOf(nx, u.y)]) { ny = u.y; }
      else if (!b.grid[cellOf(u.x, ny)]) { nx = u.x; }
      else { nx = u.x; ny = u.y; u.path = null; }
    }
    u.x = clamp(nx, u.state === 'routing' ? -80 : 12, u.state === 'routing' ? W + 80 : W - 12);
    u.y = clamp(ny, 12, H - 12);
    if (moving && u.state === 'moving') u.facing = angleLerp(u.facing, Math.atan2(vy, vx), 0.18);

    // Watchdog for a soldier trying to move but going nowhere — a bad path, or
    // wedged against scenery. Jostling in a melee or at a gate is normal, so
    // only unengaged units count, and the first response is to drop the order
    // and try again. A unit that cannot get anywhere after several attempts has
    // effectively left the battle, which also guarantees the fight can end.
    if (moving && u.engagedT <= 0 && Math.hypot(u.x - prevX, u.y - prevY) < 0.4) {
      u.stuckT = (u.stuckT || 0) + dt;
      if (u.stuckT > 12) {
        u.stuckT = 0;
        u.stuckCount = (u.stuckCount || 0) + 1;
        u.path = null; u.orderPos = null; u.orderTargetUid = null; u.autoTarget = null;
        u.state = 'idle';
        if (u.stuckCount > 4) { u.state = 'fled'; b.selection.delete(u.uid); }
      }
    } else {
      u.stuckT = 0;
    }
  }

  // ---- projectiles
  for (let i = b.projectiles.length - 1; i >= 0; i--) {
    const p = b.projectiles[i];
    p.t += dt;
    const k = Math.min(1, p.t / p.dur);
    p.x = p.sx + (p.tx - p.sx) * k;
    p.y = p.sy + (p.ty - p.sy) * k;
    p.z = Math.sin(k * Math.PI) * 60 * p.arc;
    if (k >= 1) {
      b.projectiles.splice(i, 1);
      // strike anything close to the impact point
      let best = null, bd = 15 * 15;
      for (const u of alive) {
        if (u.player === p.player || u.state === 'dead' || u.state === 'fled') continue;
        const d = dist2(u.x, u.y, p.tx, p.ty);
        if (d < bd) { bd = d; best = u; }
      }
      if (best) {
        best.hitRecently = true;
        damageUnit(b, best, p.dmg, p.shooter, true, p.sx, p.sy);
      } else {
        b.effects.push({ type: 'miss', x: p.tx, y: p.ty });
      }
    }
  }

  // corpse timers (for render fade)
  for (const u of b.units) if (u.state === 'dead') u.deadT = (u.deadT || 0) + dt;

  // ---- end conditions
  if (b.time > 1.5) {
    const pLeft = aliveUnits(b, true).length;
    const eLeft = aliveUnits(b, false).length;
    if (eLeft === 0 || pLeft === 0 || (b.withdrawing && aliveUnits(b, true).every(u => u.state === 'fled' || u.state === 'routing' && (u.x < 40 || u.x > W - 40)))) {
      finishBattle(b, pLeft, eLeft);
    }
  }
}

function finishBattle(b, pLeft, eLeft) {
  b.state = 'ended';
  // Holding the field is a victory however the battle got there — a withdrawal
  // that turned into a rout of the enemy still won the ground.
  const victory = eLeft === 0 && pLeft > 0;
  const playerFallen = new Set(), enemyFallen = new Set();
  for (const u of b.units) {
    if (u.state === 'dead') (u.player ? playerFallen : enemyFallen).add(u.soldier.id);
  }
  b.result = {
    victory,
    withdrew: !!b.withdrawing && !victory,
    playerFallen, enemyFallen,
    duration: b.time,
    playerSurvivors: b.units.filter(u => u.player && u.state !== 'dead').map(u => u.soldier),
    enemySurvivors: b.units.filter(u => !u.player && u.state !== 'dead').map(u => u.soldier),
  };
}
