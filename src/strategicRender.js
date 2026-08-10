// Strategic map rendering: a feudal-industrial miniature seen from above.

import { WORLD, playerArmy, isSpotted, factionOf } from './campaign.js';
import { LOC_TYPES, FACTIONS } from './data.js';
import { Y_SQUASH } from './camera.js';
import { makeRng } from './util.js';
import { fitForDuty } from './soldiers.js';

// Pre-generate deterministic decoration (trees, field rows) once.
let deco = null;
function buildDeco() {
  const rng = makeRng(1234);
  deco = { trees: [], fieldRows: [], rocks: [] };
  for (const f of WORLD.forests) {
    const n = Math.floor(f.r * f.r / 2600);
    for (let i = 0; i < n; i++) {
      const a = rng.float(0, Math.PI * 2), d = Math.sqrt(rng.float(0, 1)) * f.r * 0.92;
      deco.trees.push({ x: f.x + Math.cos(a) * d, y: f.y + Math.sin(a) * d, s: rng.float(0.7, 1.3) });
    }
  }
  for (const fm of WORLD.farms) {
    for (let i = -3; i <= 3; i++) deco.fieldRows.push({ x: fm.x, y: fm.y + i * fm.r / 4, w: fm.r * 1.5, r: fm.r });
  }
  for (let i = 0; i < 40; i++) deco.rocks.push({ x: rng.float(0, WORLD.w), y: rng.float(0, WORLD.h), s: rng.float(0.5, 1) });
  deco.trees.sort((a, b) => a.y - b.y);
}

function groundEllipse(ctx, cam, x, y, r, fill) {
  const p = cam.toScreen(x, y);
  ctx.fillStyle = fill;
  ctx.beginPath();
  ctx.ellipse(p.x, p.y, r * cam.zoom, r * cam.zoom * Y_SQUASH, 0, 0, Math.PI * 2);
  ctx.fill();
}

function drawTree(ctx, cam, x, y, s) {
  const p = cam.toScreen(x, y);
  const z = cam.zoom;
  ctx.fillStyle = 'rgba(0,0,0,0.25)';
  ctx.beginPath(); ctx.ellipse(p.x, p.y, 7 * s * z, 3.5 * s * z, 0, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = '#4a3826';
  ctx.fillRect(p.x - 1 * z, p.y - 8 * s * z, 2 * z, 8 * s * z);
  ctx.fillStyle = '#39502f';
  ctx.beginPath();
  ctx.moveTo(p.x, p.y - 22 * s * z);
  ctx.lineTo(p.x + 7 * s * z, p.y - 6 * s * z);
  ctx.lineTo(p.x - 7 * s * z, p.y - 6 * s * z);
  ctx.closePath(); ctx.fill();
  ctx.fillStyle = '#455e35';
  ctx.beginPath();
  ctx.moveTo(p.x, p.y - 26 * s * z);
  ctx.lineTo(p.x + 5 * s * z, p.y - 12 * s * z);
  ctx.lineTo(p.x - 5 * s * z, p.y - 12 * s * z);
  ctx.closePath(); ctx.fill();
}

function house(ctx, cam, x, y, w, h, roof = '#8a5238', wall = '#7a6448') {
  const p = cam.toScreen(x, y);
  const z = cam.zoom;
  ctx.fillStyle = 'rgba(0,0,0,0.3)';
  ctx.beginPath(); ctx.ellipse(p.x, p.y + 2 * z, w * 0.8 * z, w * 0.35 * z, 0, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = wall;
  ctx.fillRect(p.x - w / 2 * z, p.y - h * z, w * z, h * z);
  ctx.fillStyle = roof;
  ctx.beginPath();
  ctx.moveTo(p.x - w / 2 * z - 2 * z, p.y - h * z);
  ctx.lineTo(p.x, p.y - (h + w * 0.5) * z);
  ctx.lineTo(p.x + w / 2 * z + 2 * z, p.y - h * z);
  ctx.closePath(); ctx.fill();
}

function tower(ctx, cam, x, y, w, h, color = '#767268') {
  const p = cam.toScreen(x, y);
  const z = cam.zoom;
  ctx.fillStyle = 'rgba(0,0,0,0.3)';
  ctx.beginPath(); ctx.ellipse(p.x, p.y + 2 * z, w * 0.9 * z, w * 0.4 * z, 0, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = color;
  ctx.fillRect(p.x - w / 2 * z, p.y - h * z, w * z, h * z);
  ctx.fillStyle = '#5d5a52';
  // crenellation
  for (let i = 0; i < 3; i++) ctx.fillRect(p.x - w / 2 * z + i * (w / 2.6) * z, p.y - (h + 4) * z, (w / 4) * z, 4 * z);
}

function chimney(ctx, cam, x, y, h, time, active) {
  const p = cam.toScreen(x, y);
  const z = cam.zoom;
  ctx.fillStyle = '#4c4a48';
  ctx.fillRect(p.x - 3 * z, p.y - h * z, 6 * z, h * z);
  ctx.fillStyle = '#6a5a3a';
  ctx.fillRect(p.x - 4 * z, p.y - h * z, 8 * z, 3 * z);
  if (active) {
    for (let i = 0; i < 3; i++) {
      const t = ((time * 0.35 + i / 3) % 1);
      const sx = p.x + Math.sin(time + i * 2.1) * 4 * z * t;
      const sy = p.y - h * z - t * 30 * z;
      ctx.fillStyle = `rgba(160,158,150,${0.35 * (1 - t)})`;
      ctx.beginPath(); ctx.arc(sx, sy, (3 + t * 8) * z, 0, Math.PI * 2); ctx.fill();
    }
  }
}

function banner(ctx, cam, x, y, color, gold = false) {
  const p = cam.toScreen(x, y);
  const z = cam.zoom;
  ctx.strokeStyle = '#3a3128';
  ctx.lineWidth = 1.6 * z;
  ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x, p.y - 26 * z); ctx.stroke();
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(p.x, p.y - 26 * z);
  ctx.lineTo(p.x + 13 * z, p.y - 22 * z);
  ctx.lineTo(p.x, p.y - 17 * z);
  ctx.closePath(); ctx.fill();
  if (gold) {
    ctx.strokeStyle = '#c9a959';
    ctx.lineWidth = 1 * z;
    ctx.stroke();
  }
}

function drawLocation(ctx, cam, loc, time, campaign) {
  const p = cam.toScreen(loc.x, loc.y);
  const z = cam.zoom;
  const fac = FACTIONS[loc.owner] || FACTIONS.neutral;
  const owned = loc.owner === 'player';

  // ground pad
  groundEllipse(ctx, cam, loc.x, loc.y, 52, loc.owner === 'neutral' ? 'rgba(120,110,88,0.25)' : `${fac.color}26`);

  switch (loc.type) {
    case 'camp': {
      // tents
      for (const [dx, dy] of [[-18, 4], [14, 10], [0, -12]]) {
        const q = cam.toScreen(loc.x + dx, loc.y + dy);
        ctx.fillStyle = '#8d7f62';
        ctx.beginPath();
        ctx.moveTo(q.x, q.y - 14 * z); ctx.lineTo(q.x + 10 * z, q.y); ctx.lineTo(q.x - 10 * z, q.y);
        ctx.closePath(); ctx.fill();
        ctx.strokeStyle = '#5d5340'; ctx.lineWidth = 1; ctx.stroke();
      }
      const f = cam.toScreen(loc.x + 2, loc.y + 22);
      ctx.fillStyle = `rgba(230,150,60,${0.6 + 0.3 * Math.sin(time * 6)})`;
      ctx.beginPath(); ctx.arc(f.x, f.y - 3 * z, 3 * z, 0, Math.PI * 2); ctx.fill();
      break;
    }
    case 'hamlet':
      house(ctx, cam, loc.x - 16, loc.y + 6, 20, 12, '#9b7d43');
      house(ctx, cam, loc.x + 14, loc.y + 12, 18, 11, '#9b7d43');
      house(ctx, cam, loc.x + 2, loc.y - 14, 16, 10, '#8a6a3c');
      break;
    case 'market':
      house(ctx, cam, loc.x - 20, loc.y + 4, 24, 16, '#8a5238');
      house(ctx, cam, loc.x + 16, loc.y + 12, 20, 13, '#7d4a34');
      house(ctx, cam, loc.x + 6, loc.y - 16, 18, 12, '#9b7d43');
      // market stall awning
      {
        const q = cam.toScreen(loc.x - 2, loc.y + 24);
        ctx.fillStyle = '#a8433a';
        ctx.fillRect(q.x - 8 * z, q.y - 8 * z, 16 * z, 4 * z);
        ctx.fillStyle = '#d8d2c4';
        ctx.fillRect(q.x - 8 * z, q.y - 4 * z, 16 * z, 1.5 * z);
      }
      break;
    case 'coal': {
      groundEllipse(ctx, cam, loc.x, loc.y + 6, 34, '#3a3633');
      const q = cam.toScreen(loc.x - 12, loc.y - 4);
      ctx.fillStyle = '#2e2b29';
      ctx.beginPath(); ctx.ellipse(q.x, q.y, 14 * z, 9 * z, 0, 0, Math.PI * 2); ctx.fill();
      // head-frame gantry
      const g = cam.toScreen(loc.x + 14, loc.y + 2);
      ctx.strokeStyle = '#5a4a34'; ctx.lineWidth = 2 * z;
      ctx.beginPath();
      ctx.moveTo(g.x - 8 * z, g.y); ctx.lineTo(g.x, g.y - 24 * z); ctx.lineTo(g.x + 8 * z, g.y);
      ctx.stroke();
      ctx.strokeStyle = '#8a8578'; ctx.lineWidth = 1.4 * z;
      ctx.beginPath(); ctx.arc(g.x, g.y - 24 * z, 4 * z, 0, Math.PI * 2); ctx.stroke();
      // cart
      const cq = cam.toScreen(loc.x + 2, loc.y + 20);
      ctx.fillStyle = '#4a3826'; ctx.fillRect(cq.x - 6 * z, cq.y - 5 * z, 12 * z, 5 * z);
      ctx.fillStyle = '#1e1c1a'; ctx.fillRect(cq.x - 5 * z, cq.y - 7 * z, 10 * z, 2.5 * z);
      break;
    }
    case 'foundry': {
      house(ctx, cam, loc.x - 6, loc.y + 8, 34, 16, '#5d4a3a', '#6a5744');
      chimney(ctx, cam, loc.x + 16, loc.y - 2, 34, time, loc.owner !== 'neutral');
      chimney(ctx, cam, loc.x - 22, loc.y - 6, 26, time, loc.owner !== 'neutral');
      // pipework
      const q = cam.toScreen(loc.x - 2, loc.y + 20);
      ctx.strokeStyle = '#45464b'; ctx.lineWidth = 2.4 * z;
      ctx.beginPath(); ctx.moveTo(q.x - 14 * z, q.y); ctx.lineTo(q.x + 16 * z, q.y); ctx.stroke();
      ctx.fillStyle = '#c9a959';
      ctx.fillRect(q.x + 4 * z, q.y - 1.6 * z, 3 * z, 3.2 * z);
      break;
    }
    case 'watch':
      tower(ctx, cam, loc.x, loc.y, 14, 34);
      break;
    case 'fort': {
      const q = cam.toScreen(loc.x, loc.y);
      ctx.fillStyle = 'rgba(0,0,0,0.3)';
      ctx.beginPath(); ctx.ellipse(q.x, q.y + 4 * z, 30 * z, 13 * z, 0, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#767268';
      ctx.fillRect(q.x - 24 * z, q.y - 14 * z, 48 * z, 14 * z);
      tower(ctx, cam, loc.x - 24, loc.y + 2, 12, 24);
      tower(ctx, cam, loc.x + 24, loc.y + 2, 12, 24);
      ctx.fillStyle = '#4a3826';
      ctx.fillRect(q.x - 5 * z, q.y - 10 * z, 10 * z, 10 * z);
      break;
    }
    case 'keep': {
      const q = cam.toScreen(loc.x, loc.y);
      ctx.fillStyle = 'rgba(0,0,0,0.35)';
      ctx.beginPath(); ctx.ellipse(q.x, q.y + 6 * z, 38 * z, 16 * z, 0, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#6d6a62';
      ctx.fillRect(q.x - 32 * z, q.y - 12 * z, 64 * z, 12 * z);
      tower(ctx, cam, loc.x - 30, loc.y + 2, 13, 26);
      tower(ctx, cam, loc.x + 30, loc.y + 2, 13, 26);
      tower(ctx, cam, loc.x, loc.y - 10, 20, 44, '#7d7a70');
      break;
    }
  }

  banner(ctx, cam, loc.x + 34, loc.y - 6, fac.color, owned);

  // capture progress ring
  if (loc.captureProgress > 0 && loc.capturingFaction) {
    ctx.strokeStyle = FACTIONS[loc.capturingFaction].color;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.ellipse(p.x, p.y, 46 * z, 46 * z * Y_SQUASH, 0, -Math.PI / 2, -Math.PI / 2 + loc.captureProgress * Math.PI * 2);
    ctx.stroke();
  }

  // label
  ctx.font = `600 ${Math.max(10, 11 * z)}px "Segoe UI", sans-serif`;
  ctx.textAlign = 'center';
  ctx.fillStyle = 'rgba(0,0,0,0.5)';
  ctx.fillText(loc.name, p.x + 1, p.y + 40 * z + 1);
  ctx.fillStyle = loc.owner === 'player' ? '#cfe3c2' : '#c9c2b0';
  ctx.fillText(loc.name, p.x, p.y + 40 * z);
  const g = fitForDuty(loc.garrison).length;
  if (g > 0) {
    ctx.font = `${Math.max(9, 10 * z)}px "Segoe UI", sans-serif`;
    ctx.fillStyle = fac.color;
    ctx.fillText(`⛨ ${g}`, p.x, p.y + 52 * z);
  }
}

function drawArmy(ctx, cam, army, campaign, selected, time) {
  const p = cam.toScreen(army.x, army.y);
  const z = cam.zoom;
  const fac = factionOf(army);
  const spotted = army.faction === 'player' || isSpotted(campaign, army.x, army.y);
  const count = fitForDuty(army.soldiers).length;

  // destination line for the player
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
    ctx.beginPath(); ctx.ellipse(p.x, p.y + 2 * z, 20 * z * pulse, 9 * z * pulse, 0, 0, Math.PI * 2); ctx.stroke();
  }

  ctx.fillStyle = 'rgba(0,0,0,0.35)';
  ctx.beginPath(); ctx.ellipse(p.x, p.y + 2 * z, 14 * z, 6 * z, 0, 0, Math.PI * 2); ctx.fill();

  if (!spotted) {
    // unidentified column
    ctx.fillStyle = '#55524a';
    ctx.beginPath(); ctx.arc(p.x, p.y - 8 * z, 8 * z, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#2c2a26';
    ctx.font = `700 ${11 * z}px "Segoe UI", sans-serif`;
    ctx.textAlign = 'center';
    ctx.fillText('?', p.x, p.y - 4.5 * z);
    return;
  }

  // little marching figures
  const marching = !!army.dest;
  for (let i = 0; i < Math.min(4, Math.max(2, Math.ceil(count / 4))); i++) {
    const bob = marching ? Math.sin(time * 9 + i * 1.7) * 1.2 : 0;
    const q = cam.toScreen(army.x - 8 + i * 6, army.y + (i % 2) * 5 - 2);
    ctx.fillStyle = fac.dark;
    ctx.fillRect(q.x - 1.6 * z, q.y - (9 + bob) * z, 3.2 * z, 8 * z);
    ctx.fillStyle = '#c8b89a';
    ctx.beginPath(); ctx.arc(q.x, q.y - (10.5 + bob) * z, 1.8 * z, 0, Math.PI * 2); ctx.fill();
  }
  banner(ctx, cam, army.x + 8, army.y + 2, fac.color, army.faction === 'player');

  // strength disc
  ctx.fillStyle = fac.color;
  ctx.beginPath(); ctx.arc(p.x + 16 * z, p.y - 24 * z, 8 * z, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.4)'; ctx.lineWidth = 1; ctx.stroke();
  ctx.fillStyle = '#fff';
  ctx.font = `700 ${9 * z}px "Segoe UI", sans-serif`;
  ctx.textAlign = 'center';
  ctx.fillText(count, p.x + 16 * z, p.y - 21 * z);
}

export function renderStrategic(ctx, cam, campaign, selectedArmy, time) {
  if (!deco) buildDeco();
  const canvas = ctx.canvas;
  ctx.fillStyle = '#33402c';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // world bounds hint
  {
    const a = cam.toScreen(0, 0), b = cam.toScreen(WORLD.w, WORLD.h);
    ctx.fillStyle = '#3b4a33';
    ctx.fillRect(a.x, a.y, b.x - a.x, b.y - a.y);
    ctx.strokeStyle = '#2a3325';
    ctx.lineWidth = 4;
    ctx.strokeRect(a.x, a.y, b.x - a.x, b.y - a.y);
  }

  // hills (soft rings)
  for (const h of WORLD.hills) {
    groundEllipse(ctx, cam, h.x, h.y, h.r, 'rgba(146,142,98,0.16)');
    groundEllipse(ctx, cam, h.x, h.y - h.r * 0.18, h.r * 0.62, 'rgba(160,155,108,0.16)');
  }
  // farms
  for (const f of WORLD.farms) groundEllipse(ctx, cam, f.x, f.y, f.r, 'rgba(148,128,74,0.28)');
  for (const row of deco.fieldRows) {
    const p = cam.toScreen(row.x - row.w / 2, row.y);
    const q = cam.toScreen(row.x + row.w / 2, row.y);
    ctx.strokeStyle = 'rgba(110,95,55,0.35)';
    ctx.lineWidth = 2 * cam.zoom;
    ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); ctx.stroke();
  }
  // forest floors
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

  // trees (behind locations at same y is fine — sorted by y already)
  for (const t of deco.trees) drawTree(ctx, cam, t.x, t.y, t.s);

  // locations
  const locsSorted = [...campaign.locations].sort((a, b) => a.y - b.y);
  for (const loc of locsSorted) drawLocation(ctx, cam, loc, time, campaign);

  // armies
  const armiesSorted = [...campaign.armies].sort((a, b) => a.y - b.y);
  for (const a of armiesSorted) drawArmy(ctx, cam, a, campaign, a === selectedArmy, time);

  // subtle vignette
  const grad = ctx.createRadialGradient(canvas.width / 2, canvas.height / 2, canvas.height * 0.4, canvas.width / 2, canvas.height / 2, canvas.height * 0.95);
  grad.addColorStop(0, 'rgba(0,0,0,0)');
  grad.addColorStop(1, 'rgba(10,10,8,0.4)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
}
