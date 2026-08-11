// Strategic map rendering: a feudal-industrial miniature seen from above.
// Ground, water and roads are painted; everything standing on them is a voxel
// sprite baked in Blender (tools/blender/).

import { WORLD, playerArmy, isSpotted, factionOf } from './campaign.js';
import { LOC_TYPES, FACTIONS } from './data.js';
import { Y_SQUASH } from './camera.js';
import { makeRng } from './util.js';
import { fitForDuty } from './soldiers.js';
import { drawProp, drawShadow, drawUnit, walkPose, propSize } from './sprites.js';

// Deterministic scatter so the countryside is the same every session.
let deco = null;
function buildDeco() {
  const rng = makeRng(1234);
  deco = { trees: [], fieldRows: [] };
  for (const f of WORLD.forests) {
    const n = Math.floor(f.r * f.r / 3400);
    for (let i = 0; i < n; i++) {
      const a = rng.float(0, Math.PI * 2), d = Math.sqrt(rng.float(0, 1)) * f.r * 0.92;
      deco.trees.push({
        x: f.x + Math.cos(a) * d, y: f.y + Math.sin(a) * d,
        s: rng.float(0.75, 1.1), sprite: rng.chance(0.55) ? 'tree_pine' : 'tree_round',
      });
    }
  }
  for (const fm of WORLD.farms) {
    for (let i = -3; i <= 3; i++) deco.fieldRows.push({ x: fm.x, y: fm.y + i * fm.r / 4, w: fm.r * 1.5 });
  }
  deco.trees.sort((a, b) => a.y - b.y);
}

function groundEllipse(ctx, cam, x, y, r, fill) {
  const p = cam.toScreen(x, y);
  ctx.fillStyle = fill;
  ctx.beginPath();
  ctx.ellipse(p.x, p.y, r * cam.zoom, r * cam.zoom * Y_SQUASH, 0, 0, Math.PI * 2);
  ctx.fill();
}

function prop(ctx, cam, name, x, y, scale = 1, shadow = 0.5) {
  if (shadow) drawShadow(ctx, cam, x, y, propSize(name).w * 0.42 * scale, 0.4, 0.26);
  drawProp(ctx, cam, name, x, y, scale);
}

// A location's buildings, laid out so each type has its own silhouette.
function locationPieces(loc) {
  switch (loc.type) {
    case 'camp':
      return [['tent', -20, 6, 0.85], ['tent', 16, 14, 0.8], ['tent', 2, -14, 0.8], ['cart', 34, -4, 0.7]];
    case 'hamlet':
      return [['house', -20, 8, 0.75], ['house', 18, 16, 0.7], ['house', 4, -14, 0.65]];
    case 'market':
      return [['house', -26, 4, 0.85], ['house', 22, 14, 0.8], ['house', 6, -18, 0.75],
              ['stall', -4, 26, 0.9], ['cart', 30, 26, 0.7]];
    case 'coal':
      return [['headframe', 6, -6, 0.8], ['spoil', -24, 10, 1.0], ['cart', 24, 18, 0.8], ['shed', -18, -12, 0.6]];
    case 'foundry':
      return [['hall', 0, 0, 0.85], ['boiler', 30, 16, 0.8], ['cart', -32, 20, 0.7]];
    case 'watch':
      return [['tower', 0, 0, 0.85], ['fence', -2, 22, 0.7]];
    case 'fort':
      return [['gatehouse', 0, 2, 0.85], ['tower', -34, 6, 0.7], ['tower', 34, 6, 0.7]];
    case 'keep':
      return [['keep', 0, 0, 0.9], ['tower', -44, 14, 0.7], ['tower', 44, 14, 0.7]];
    default:
      return [];
  }
}

function drawLocation(ctx, cam, loc, time) {
  const p = cam.toScreen(loc.x, loc.y);
  const z = cam.zoom;
  const fac = FACTIONS[loc.owner] || FACTIONS.neutral;

  // ground pad tinted by owner
  groundEllipse(ctx, cam, loc.x, loc.y, 54, loc.owner === 'neutral' ? 'rgba(120,110,88,0.25)' : `${fac.color}26`);
  if (loc.type === 'coal') groundEllipse(ctx, cam, loc.x + 4, loc.y + 4, 30, 'rgba(30,28,26,0.45)');
  if (loc.type === 'foundry') groundEllipse(ctx, cam, loc.x, loc.y + 6, 34, 'rgba(44,40,34,0.35)');

  const pieces = locationPieces(loc);
  pieces.sort((a, b) => a[2] - b[2]);
  for (const [name, dx, dy, s] of pieces) prop(ctx, cam, name, loc.x + dx, loc.y + dy, s);

  // Working industry smokes; idle industry does not.
  if ((loc.type === 'foundry' || loc.type === 'coal') && loc.owner !== 'neutral') {
    const sx = loc.type === 'foundry' ? loc.x - 10 : loc.x + 6;
    for (let i = 0; i < 3; i++) {
      const t = ((time * 0.28 + i / 3) % 1);
      const q = cam.toScreen(sx + Math.sin(time * 0.8 + i * 2.1) * 6 * t, loc.y - 6);
      ctx.fillStyle = `rgba(168,166,158,${0.32 * (1 - t)})`;
      ctx.beginPath();
      ctx.arc(q.x, q.y - (46 + t * 44) * z, (4 + t * 10) * z, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // faction banner
  drawUnit(ctx, cam, loc.owner === 'neutral' ? 'neutral' : loc.owner, 'banner', 0, 0, loc.x + 44, loc.y + 10);

  // capture progress ring
  if (loc.captureProgress > 0 && loc.capturingFaction) {
    ctx.strokeStyle = FACTIONS[loc.capturingFaction].color;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.ellipse(p.x, p.y, 50 * z, 50 * z * Y_SQUASH, 0, -Math.PI / 2, -Math.PI / 2 + loc.captureProgress * Math.PI * 2);
    ctx.stroke();
  }

  // label
  ctx.font = `600 ${Math.max(10, 11 * z)}px "Segoe UI", sans-serif`;
  ctx.textAlign = 'center';
  ctx.fillStyle = 'rgba(0,0,0,0.55)';
  ctx.fillText(loc.name, p.x + 1, p.y + 42 * z + 1);
  ctx.fillStyle = loc.owner === 'player' ? '#cfe3c2' : '#c9c2b0';
  ctx.fillText(loc.name, p.x, p.y + 42 * z);
  const g = fitForDuty(loc.garrison).length;
  if (g > 0) {
    ctx.font = `${Math.max(9, 10 * z)}px "Segoe UI", sans-serif`;
    ctx.fillStyle = fac.color;
    ctx.fillText(`⛨ ${g}`, p.x, p.y + 54 * z);
  }
}

// A marching column: a few figures from the army's actual composition.
function drawArmy(ctx, cam, army, campaign, selected, time) {
  const p = cam.toScreen(army.x, army.y);
  const z = cam.zoom;
  const fac = factionOf(army);
  const spotted = army.faction === 'player' || isSpotted(campaign, army.x, army.y);
  const fit = fitForDuty(army.soldiers);
  const count = fit.length;

  if (army.faction === 'player' && army.dest) {
    const d = cam.toScreen(army.dest.x, army.dest.y);
    ctx.strokeStyle = 'rgba(201,169,89,0.5)';
    ctx.setLineDash([5, 5]);
    ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(d.x, d.y); ctx.stroke();
    ctx.setLineDash([]);
    ctx.strokeStyle = 'rgba(201,169,89,0.8)';
    ctx.beginPath(); ctx.ellipse(d.x, d.y, 8 * z, 8 * z * Y_SQUASH, 0, 0, Math.PI * 2); ctx.stroke();
  }

  if (selected) {
    const pulse = 1 + Math.sin(time * 5) * 0.08;
    ctx.strokeStyle = '#c9a959';
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.ellipse(p.x, p.y + 2 * z, 26 * z * pulse, 12 * z * pulse, 0, 0, Math.PI * 2); ctx.stroke();
  }

  if (!spotted) {
    // Unidentified column: dust and a query marker, no strength given away.
    drawShadow(ctx, cam, army.x, army.y, 14, 0.42, 0.3);
    ctx.fillStyle = '#55524a';
    ctx.beginPath(); ctx.arc(p.x, p.y - 14 * z, 9 * z, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#211f1c';
    ctx.font = `700 ${12 * z}px "Segoe UI", sans-serif`;
    ctx.textAlign = 'center';
    ctx.fillText('?', p.x, p.y - 10 * z);
    return;
  }

  // Facing follows the march order; the column is drawn back to front.
  let facing = 0;
  if (army.dest) facing = Math.atan2(army.dest.y - army.y, army.dest.x - army.x);
  const moving = !!army.dest;
  const shown = Math.min(4, Math.max(2, Math.ceil(count / 3)));
  const types = fit.map(s => s.type);
  const pick = [];
  const hero = types.indexOf('hero');
  if (hero >= 0) pick.push('hero');
  for (const t of ['boilerlancer', 'rider', 'pressurebow', 'shieldman', 'spearman', 'bowman', 'levy']) {
    if (pick.length >= shown) break;
    if (types.includes(t)) pick.push(t);
  }
  while (pick.length < Math.min(shown, types.length)) pick.push(types[pick.length % types.length]);

  const slots = [[-9, -5], [7, -2], [-4, 7], [11, 9]];
  const drawn = pick.map((t, i) => ({ t, dx: slots[i % 4][0], dy: slots[i % 4][1], i }));
  drawn.sort((a, b) => a.dy - b.dy);
  for (const d of drawn) {
    drawShadow(ctx, cam, army.x + d.dx, army.y + d.dy, 8, 0.42, 0.28);
    drawUnit(ctx, cam, army.faction, d.t, facing, walkPose(moving, time, d.i * 3), army.x + d.dx, army.y + d.dy);
  }
  drawUnit(ctx, cam, army.faction, 'banner', 0, 0, army.x + 16, army.y + 2);

  // strength disc
  ctx.fillStyle = fac.color;
  ctx.beginPath(); ctx.arc(p.x + 20 * z, p.y - 34 * z, 9 * z, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.45)'; ctx.lineWidth = 1; ctx.stroke();
  ctx.fillStyle = '#fff';
  ctx.font = `700 ${10 * z}px "Segoe UI", sans-serif`;
  ctx.textAlign = 'center';
  ctx.fillText(count, p.x + 20 * z, p.y - 30.5 * z);
}

export function renderStrategic(ctx, cam, campaign, selectedArmy, time) {
  if (!deco) buildDeco();
  const canvas = ctx.canvas;
  ctx.fillStyle = '#33402c';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  {
    const a = cam.toScreen(0, 0), b = cam.toScreen(WORLD.w, WORLD.h);
    ctx.fillStyle = '#3b4a33';
    ctx.fillRect(a.x, a.y, b.x - a.x, b.y - a.y);
    ctx.strokeStyle = '#2a3325';
    ctx.lineWidth = 4;
    ctx.strokeRect(a.x, a.y, b.x - a.x, b.y - a.y);
  }

  for (const h of WORLD.hills) {
    groundEllipse(ctx, cam, h.x, h.y, h.r, 'rgba(146,142,98,0.16)');
    groundEllipse(ctx, cam, h.x, h.y - h.r * 0.18, h.r * 0.62, 'rgba(160,155,108,0.16)');
  }
  for (const f of WORLD.farms) groundEllipse(ctx, cam, f.x, f.y, f.r, 'rgba(148,128,74,0.28)');
  for (const row of deco.fieldRows) {
    const p = cam.toScreen(row.x - row.w / 2, row.y);
    const q = cam.toScreen(row.x + row.w / 2, row.y);
    ctx.strokeStyle = 'rgba(110,95,55,0.35)';
    ctx.lineWidth = 2 * cam.zoom;
    ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); ctx.stroke();
  }
  for (const f of WORLD.forests) groundEllipse(ctx, cam, f.x, f.y, f.r, 'rgba(42,62,36,0.5)');

  // river
  ctx.lineCap = 'round';
  ctx.strokeStyle = '#39586b';
  ctx.lineWidth = WORLD.riverWidth * cam.zoom * Y_SQUASH;
  ctx.beginPath();
  WORLD.river.forEach((pt, i) => {
    const p = cam.toScreen(pt.x, pt.y);
    i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y);
  });
  ctx.stroke();
  ctx.strokeStyle = 'rgba(140,180,200,0.25)';
  ctx.lineWidth = 3 * cam.zoom;
  ctx.beginPath();
  WORLD.river.forEach((pt, i) => {
    const p = cam.toScreen(pt.x + 8, pt.y);
    i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y);
  });
  ctx.stroke();

  // roads
  for (const road of WORLD.roads) {
    ctx.strokeStyle = 'rgba(150,128,88,0.75)';
    ctx.lineWidth = 5 * cam.zoom;
    ctx.setLineDash([10 * cam.zoom, 7 * cam.zoom]);
    ctx.beginPath();
    road.forEach((pt, i) => {
      const p = cam.toScreen(pt.x, pt.y);
      i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y);
    });
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // bridge deck
  {
    const p = cam.toScreen(WORLD.bridge.x, WORLD.bridge.y);
    ctx.fillStyle = '#6d5335';
    ctx.fillRect(p.x - 46 * cam.zoom, p.y - 9 * cam.zoom, 92 * cam.zoom, 18 * cam.zoom);
    ctx.strokeStyle = '#4a3826';
    ctx.lineWidth = 2;
    ctx.strokeRect(p.x - 46 * cam.zoom, p.y - 9 * cam.zoom, 92 * cam.zoom, 18 * cam.zoom);
  }

  // Everything that stands up is depth-sorted together.
  const standing = [];
  for (const t of deco.trees) standing.push({ y: t.y, draw: () => prop(ctx, cam, t.sprite, t.x, t.y, t.s, 0.4) });
  for (const loc of campaign.locations) standing.push({ y: loc.y, draw: () => drawLocation(ctx, cam, loc, time) });
  for (const a of campaign.armies) standing.push({ y: a.y, draw: () => drawArmy(ctx, cam, a, campaign, a === selectedArmy, time) });
  standing.sort((a, b) => a.y - b.y);
  for (const s of standing) s.draw();

  const grad = ctx.createRadialGradient(canvas.width / 2, canvas.height / 2, canvas.height * 0.4, canvas.width / 2, canvas.height / 2, canvas.height * 0.95);
  grad.addColorStop(0, 'rgba(0,0,0,0)');
  grad.addColorStop(1, 'rgba(10,10,8,0.4)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
}
