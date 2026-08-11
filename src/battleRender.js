// Battlefield rendering. Soldiers and scenery are voxel sprites baked in
// Blender (tools/blender/); the canvas draws ground, shadows, effects and the
// thin layer of command information on top.

import { Y_SQUASH } from './camera.js';
import { FACTIONS } from './data.js';
import { drawUnit, drawProp, drawShadow, walkPose, propSize } from './sprites.js';

const GROUND = {
  open: '#41502f', forest: '#37452b', bridge: '#41502f',
  settlement: '#4a5233', industrial: '#4a473b', fort: '#464f31',
};

let particles = [];
let markers = [];

export function resetBattleFx() { particles = []; markers = []; }

const rnd = (s) => (Math.random() - 0.5) * 2 * s;

function puff(x, y, z, color, size, life, vx = 0, vy = 0, vz = 12) {
  particles.push({ x, y, z, vx, vy, vz, life, maxLife: life, color, size });
}

export function consumeEffects(b) {
  for (const e of b.effects) {
    switch (e.type) {
      case 'steamshot':
        for (let i = 0; i < 6; i++) {
          puff(e.x + rnd(8), e.y + rnd(6), 20, 'rgba(228,228,222,0.75)', 3 + Math.random() * 3, 0.85, rnd(18), rnd(11), 28);
        }
        break;
      case 'hit':
        puff(e.x + rnd(4), e.y + rnd(4), 16, 'rgba(126,32,22,0.5)', 2.6, 0.35, rnd(20), rnd(14), 8);
        break;
      case 'melee':
        if (Math.random() < 0.45) puff(e.x, e.y, 18, 'rgba(232,226,210,0.85)', 1.8, 0.18, rnd(30), rnd(20), 10);
        break;
      case 'death':
        for (let i = 0; i < 4; i++) puff(e.x + rnd(6), e.y + rnd(5), 5, 'rgba(92,82,62,0.5)', 3 + Math.random() * 2, 0.6, rnd(18), rnd(12), 14);
        break;
      case 'charge':
        for (let i = 0; i < 7; i++) puff(e.x + rnd(10), e.y + rnd(7), 3, 'rgba(142,126,96,0.55)', 3.5, 0.6, rnd(30), rnd(18), 8);
        break;
      case 'rally':
        markers.push({ x: e.x, y: e.y, t: 0, ttl: 0.9, kind: 'rally' });
        break;
      case 'order':
        markers.push({ x: e.x, y: e.y, t: 0, ttl: 0.8, kind: e.attackMove ? 'attack' : 'move' });
        break;
      case 'miss':
        puff(e.x, e.y, 2, 'rgba(112,102,76,0.5)', 2.5, 0.4, rnd(10), rnd(8), 6);
        break;
      case 'rout':
        puff(e.x, e.y, 24, 'rgba(220,220,215,0.5)', 3, 0.5, rnd(8), rnd(6), 18);
        break;
    }
  }
}

// ---------------------------------------------------------------- figures

const factionOfUnit = (u, enemyFaction) => u.player ? 'player' : (enemyFaction || 'bandit');

function figureFallback(ctx, cam, u, fac) {
  // Only used if the atlases could not be fetched: readable, not pretty.
  const p = cam.toScreen(u.x, u.y), z = cam.zoom;
  const h = (u.def.cavalry ? 26 : 30) * z;
  ctx.fillStyle = fac.color;
  ctx.fillRect(p.x - 4 * z, p.y - h, 8 * z, h);
  ctx.fillStyle = '#c8b89a';
  ctx.beginPath(); ctx.arc(p.x, p.y - h - 3 * z, 3.5 * z, 0, Math.PI * 2); ctx.fill();
}

function figure(ctx, cam, u, time, enemyFaction) {
  const p = cam.toScreen(u.x, u.y);
  const z = cam.zoom;
  const faction = factionOfUnit(u, enemyFaction);
  const fac = FACTIONS[faction] || FACTIONS.bandit;

  if (u.state === 'dead') {
    // Fallen soldiers settle into the grass and fade slowly.
    const alpha = Math.max(0, 0.7 - (u.deadT || 0) * 0.045);
    if (alpha <= 0) return;
    ctx.globalAlpha = alpha;
    ctx.fillStyle = fac.dark;
    ctx.beginPath();
    ctx.ellipse(p.x, p.y, (u.def.radius + 3) * z, (u.def.radius + 3) * z * 0.42, u.facing, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = 'rgba(40,34,26,0.5)';
    ctx.beginPath();
    ctx.ellipse(p.x, p.y, (u.def.radius + 3) * z, (u.def.radius + 3) * z * 0.42, u.facing, 0, Math.PI * 2);
    ctx.stroke();
    ctx.globalAlpha = 1;
    return;
  }

  const moving = u.state === 'moving' || u.state === 'routing';
  drawShadow(ctx, cam, u.x, u.y, u.def.radius * 1.15, 0.42, 0.3);
  const pose = walkPose(moving, time, u.uid);
  if (!drawUnit(ctx, cam, faction, u.type, u.facing, pose, u.x, u.y)) {
    figureFallback(ctx, cam, u, fac);
  }

  // Boiler lancers vent as their charge builds — machinery under load.
  if (u.type === 'boilerlancer' && u.chargeReady && moving && Math.random() < 0.07) {
    puff(u.x - Math.cos(u.facing) * 8, u.y, 30, 'rgba(225,225,220,0.5)', 2.6, 0.55, rnd(8), rnd(6), 24);
  }

  const top = p.y - (u.def.cavalry ? 46 : 40) * z;

  // veteran chevron
  if (u.vet && u.type !== 'hero') {
    ctx.strokeStyle = '#c9a959';
    ctx.lineWidth = Math.max(1, 1.3 * z);
    ctx.beginPath();
    ctx.moveTo(p.x - 3 * z, top + 3 * z);
    ctx.lineTo(p.x, top);
    ctx.lineTo(p.x + 3 * z, top + 3 * z);
    ctx.stroke();
  }
  // health
  if (u.hp < u.maxHp) {
    const w = 16 * z;
    ctx.fillStyle = 'rgba(0,0,0,0.6)';
    ctx.fillRect(p.x - w / 2, top + 5 * z, w, 2.6 * z);
    const frac = Math.max(0, u.hp / u.maxHp);
    ctx.fillStyle = frac > 0.55 ? '#7ba05b' : frac > 0.25 ? '#c9a959' : '#b5533c';
    ctx.fillRect(p.x - w / 2, top + 5 * z, w * frac, 2.6 * z);
  }
  // wavering / broken
  if (u.type !== 'hero' && u.morale < u.moraleMax * 0.4 && u.state !== 'routing') {
    ctx.fillStyle = `rgba(230,200,90,${0.5 + 0.4 * Math.sin(time * 8)})`;
    ctx.beginPath(); ctx.arc(p.x + 9 * z, top + 2 * z, 1.8 * z, 0, Math.PI * 2); ctx.fill();
  }
  if (u.state === 'routing') {
    ctx.fillStyle = 'rgba(238,238,232,0.9)';
    ctx.font = `700 ${Math.max(8, 9 * z)}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.fillText('!', p.x + 8 * z, top + 3 * z);
  }
}

// ---------------------------------------------------------------- scenery

function drawObstacle(ctx, cam, o) {
  drawShadow(ctx, cam, o.x, o.y, o.r * 0.85, 0.4, 0.26);
  if (!drawProp(ctx, cam, o.sprite || 'rock', o.x, o.y, o.scale || 1)) {
    const p = cam.toScreen(o.x, o.y), z = cam.zoom;
    ctx.fillStyle = '#4a4a44';
    ctx.beginPath(); ctx.ellipse(p.x, p.y - o.r * 0.4 * z, o.r * z, o.r * 0.6 * z, 0, 0, Math.PI * 2); ctx.fill();
  }
}

function drawRect(ctx, cam, r, time) {
  const z = cam.zoom;
  const a = cam.toScreen(r.x, r.y), b = cam.toScreen(r.x + r.w, r.y + r.h);
  if (r.kind === 'river') {
    ctx.fillStyle = '#39586b';
    ctx.fillRect(a.x, a.y, b.x - a.x, b.y - a.y);
    ctx.fillStyle = 'rgba(150,190,208,0.16)';
    for (let i = 0; i < 5; i++) {
      const yy = a.y + ((time * 14 + i * 46) % Math.max(1, b.y - a.y));
      ctx.fillRect(a.x + 6, yy, b.x - a.x - 12, 2);
    }
    ctx.strokeStyle = 'rgba(28,40,46,0.5)'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(a.x, b.y); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(b.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    return;
  }
  if (r.kind === 'wall' || r.kind === 'tower') {
    // Curtain walls are drawn as a run of wall blocks, back to front.
    const sprite = r.kind === 'tower' ? 'tower' : 'wall';
    // Segments abut along the wall's run so the curtain reads as one mass.
    const step = r.kind === 'tower' ? r.h : Math.max(8, propSize('wall').d * 0.8);
    const cx = r.x + r.w / 2;
    for (let yy = r.y + step / 2; yy < r.y + r.h + 1; yy += step) {
      drawShadow(ctx, cam, cx, Math.min(yy, r.y + r.h), 14, 0.4, 0.24);
      drawProp(ctx, cam, sprite, cx, Math.min(yy, r.y + r.h), 1);
    }
    return;
  }
  const sprite = r.sprite || (r.kind === 'house' ? 'house' : r.kind === 'shed' ? 'shed' : r.kind === 'cart' ? 'cart' : null);
  const cx = r.x + r.w / 2, cy = r.y + r.h / 2;
  if (sprite) {
    drawShadow(ctx, cam, cx, r.y + r.h * 0.8, Math.max(r.w, 14) * 0.5, 0.4, 0.26);
    if (drawProp(ctx, cam, sprite, cx, cy, r.scale || 1)) return;
  }
  ctx.fillStyle = '#5d5344';
  ctx.fillRect(a.x, a.y - 24 * z, b.x - a.x, (b.y - a.y) + 24 * z);
}

// ---------------------------------------------------------------- main render

export function renderBattle(ctx, cam, b, dt, time, boxSel) {
  const canvas = ctx.canvas;
  ctx.fillStyle = '#1c1a16';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // field
  {
    const a = cam.toScreen(0, 0), c = cam.toScreen(b.w, b.h);
    ctx.fillStyle = GROUND[b.terrain.kind] || GROUND.open;
    ctx.fillRect(a.x, a.y, c.x - a.x, c.y - a.y);
    ctx.strokeStyle = '#2a3325'; ctx.lineWidth = 5;
    ctx.strokeRect(a.x, a.y, c.x - a.x, c.y - a.y);
  }

  // hills read as broad light patches
  for (const h of b.terrain.hills) {
    const p = cam.toScreen(h.x, h.y);
    ctx.fillStyle = 'rgba(150,146,100,0.16)';
    ctx.beginPath(); ctx.ellipse(p.x, p.y, h.r * cam.zoom, h.r * cam.zoom * Y_SQUASH, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = 'rgba(165,160,110,0.14)';
    ctx.beginPath(); ctx.ellipse(p.x, p.y - h.r * 0.12 * cam.zoom, h.r * 0.6 * cam.zoom, h.r * 0.6 * cam.zoom * Y_SQUASH, 0, 0, Math.PI * 2); ctx.fill();
  }

  // ground decals
  for (const d of b.terrain.decals) {
    const p = cam.toScreen(d.x, d.y);
    if (d.kind === 'bridge') {
      ctx.fillStyle = '#6d5335';
      ctx.fillRect(p.x - (d.w / 2) * cam.zoom, p.y - (d.h / 2) * cam.zoom * Y_SQUASH, d.w * cam.zoom, d.h * cam.zoom * Y_SQUASH);
      ctx.strokeStyle = '#4a3826'; ctx.lineWidth = 3;
      ctx.strokeRect(p.x - (d.w / 2) * cam.zoom, p.y - (d.h / 2) * cam.zoom * Y_SQUASH, d.w * cam.zoom, d.h * cam.zoom * Y_SQUASH);
      // plank lines across the deck
      ctx.strokeStyle = 'rgba(60,44,28,0.5)'; ctx.lineWidth = 1;
      for (let i = 1; i < 8; i++) {
        const px = p.x - (d.w / 2) * cam.zoom + (d.w * cam.zoom) * i / 8;
        ctx.beginPath();
        ctx.moveTo(px, p.y - (d.h / 2) * cam.zoom * Y_SQUASH);
        ctx.lineTo(px, p.y + (d.h / 2) * cam.zoom * Y_SQUASH);
        ctx.stroke();
      }
    } else if (d.kind === 'gate') {
      ctx.fillStyle = 'rgba(112,96,60,0.35)';
      ctx.fillRect(p.x - (d.w / 2) * cam.zoom, p.y - (d.h / 2) * cam.zoom * Y_SQUASH, d.w * cam.zoom, d.h * cam.zoom * Y_SQUASH);
    } else if (d.kind === 'grass') {
      ctx.strokeStyle = 'rgba(120,140,80,0.3)';
      ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(p.x - 4, p.y); ctx.lineTo(p.x + 4, p.y - 3); ctx.stroke();
    } else if (d.kind === 'track') {
      ctx.strokeStyle = 'rgba(150,128,88,0.3)';
      ctx.lineWidth = 6 * cam.zoom;
      ctx.beginPath(); ctx.moveTo(p.x - 40 * cam.zoom, p.y); ctx.lineTo(p.x + 40 * cam.zoom, p.y); ctx.stroke();
    } else if (d.kind === 'fence') {
      drawProp(ctx, cam, 'fence', d.x, d.y, 1);
    }
  }

  // selection rings sit under the figures
  for (const u of b.units) {
    if (!b.selection.has(u.uid) || u.state === 'dead' || u.state === 'fled') continue;
    const p = cam.toScreen(u.x, u.y);
    ctx.strokeStyle = '#c9a959';
    ctx.lineWidth = Math.max(1, 1.6 * cam.zoom);
    ctx.beginPath();
    ctx.ellipse(p.x, p.y + 1, (u.def.radius + 5) * cam.zoom, (u.def.radius + 5) * cam.zoom * 0.45, 0, 0, Math.PI * 2);
    ctx.stroke();
  }

  // order markers
  for (let i = markers.length - 1; i >= 0; i--) {
    const m = markers[i];
    m.t += dt;
    if (m.t > m.ttl) { markers.splice(i, 1); continue; }
    const p = cam.toScreen(m.x, m.y);
    const k = m.t / m.ttl;
    if (m.kind === 'rally') {
      ctx.strokeStyle = `rgba(201,169,89,${0.8 * (1 - k)})`;
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.ellipse(p.x, p.y, 230 * k * cam.zoom, 230 * k * cam.zoom * 0.45, 0, 0, Math.PI * 2);
      ctx.stroke();
    } else {
      ctx.strokeStyle = m.kind === 'attack' ? `rgba(181,83,60,${1 - k})` : `rgba(201,169,89,${1 - k})`;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.ellipse(p.x, p.y, (16 - k * 9) * cam.zoom, (16 - k * 9) * cam.zoom * 0.45, 0, 0, Math.PI * 2);
      ctx.stroke();
    }
  }

  // y-sorted world entities: scenery and figures share one painter's pass
  const drawables = [];
  for (const o of b.terrain.circles) drawables.push({ y: o.y, draw: () => drawObstacle(ctx, cam, o) });
  for (const r of b.terrain.rects) drawables.push({ y: r.y + r.h, draw: () => drawRect(ctx, cam, r, time) });
  for (const u of b.units) {
    if (u.state === 'fled') continue;
    drawables.push({ y: u.y + (u.state === 'dead' ? -100000 : 0), draw: () => figure(ctx, cam, u, time, b.ctx.enemyFaction) });
  }
  drawables.sort((a, c) => a.y - c.y);
  for (const d of drawables) d.draw();

  // projectiles
  for (const p of b.projectiles) {
    const s = cam.toScreen(p.x, p.y, p.z || 0);
    const dirx = p.tx - p.sx, diry = p.ty - p.sy;
    const dl = Math.hypot(dirx, diry) || 1;
    const len = p.pierce ? 12 : 8;
    ctx.strokeStyle = p.pierce ? '#c9a959' : '#d8d2c4';
    ctx.lineWidth = (p.pierce ? 2.4 : 1.4) * Math.max(0.6, cam.zoom);
    ctx.beginPath();
    ctx.moveTo(s.x - dirx / dl * len * cam.zoom, s.y - diry / dl * len * cam.zoom * Y_SQUASH);
    ctx.lineTo(s.x, s.y);
    ctx.stroke();
  }

  // particles
  for (let i = particles.length - 1; i >= 0; i--) {
    const pt = particles[i];
    pt.life -= dt;
    if (pt.life <= 0) { particles.splice(i, 1); continue; }
    pt.x += pt.vx * dt; pt.y += pt.vy * dt; pt.z += pt.vz * dt;
    const s = cam.toScreen(pt.x, pt.y, pt.z);
    const k = pt.life / pt.maxLife;
    ctx.globalAlpha = k;
    ctx.fillStyle = pt.color;
    ctx.beginPath(); ctx.arc(s.x, s.y, pt.size * (2 - k) * cam.zoom, 0, Math.PI * 2); ctx.fill();
    ctx.globalAlpha = 1;
  }

  // drag box
  if (boxSel) {
    ctx.strokeStyle = 'rgba(201,169,89,0.9)';
    ctx.fillStyle = 'rgba(201,169,89,0.08)';
    ctx.lineWidth = 1;
    const x = Math.min(boxSel.x0, boxSel.x1), y = Math.min(boxSel.y0, boxSel.y1);
    ctx.fillRect(x, y, Math.abs(boxSel.x1 - boxSel.x0), Math.abs(boxSel.y1 - boxSel.y0));
    ctx.strokeRect(x, y, Math.abs(boxSel.x1 - boxSel.x0), Math.abs(boxSel.y1 - boxSel.y0));
  }

  // vignette
  const grad = ctx.createRadialGradient(canvas.width / 2, canvas.height / 2, canvas.height * 0.45, canvas.width / 2, canvas.height / 2, canvas.height);
  grad.addColorStop(0, 'rgba(0,0,0,0)');
  grad.addColorStop(1, 'rgba(8,8,6,0.45)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
}
