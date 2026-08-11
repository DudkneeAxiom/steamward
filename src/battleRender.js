// Battlefield rendering. Soldiers are small stylized figures whose silhouettes
// telegraph their job: spears read long, shields read wide, pressure gear reads heavy.

import { Y_SQUASH } from './camera.js';
import { FACTIONS } from './data.js';

const GROUND = {
  open: '#41502f', forest: '#37452b', bridge: '#41502f',
  settlement: '#4a5233', industrial: '#4a473b', fort: '#464f31',
};

let particles = [];
let markers = [];

export function resetBattleFx() { particles = []; markers = []; }

function puff(x, y, z, color, size, life, vx = 0, vy = 0, vz = 12) {
  particles.push({ x, y, z, vx, vy, vz, life, maxLife: life, color, size });
}

export function consumeEffects(b) {
  for (const e of b.effects) {
    switch (e.type) {
      case 'steamshot':
        for (let i = 0; i < 5; i++) puff(e.x + rnd(8), e.y + rnd(6), 14, 'rgba(225,225,220,0.7)', 3 + Math.random() * 3, 0.8, rnd(16), rnd(10), 26);
        break;
      case 'shot': break;
      case 'hit':
        puff(e.x + rnd(4), e.y + rnd(4), 10, 'rgba(120,30,20,0.5)', 2.5, 0.35, rnd(20), rnd(14), 8);
        break;
      case 'melee':
        if (Math.random() < 0.4) puff(e.x, e.y, 12, 'rgba(230,225,210,0.8)', 1.6, 0.18, rnd(30), rnd(20), 10);
        break;
      case 'death':
        for (let i = 0; i < 4; i++) puff(e.x + rnd(6), e.y + rnd(5), 4, 'rgba(90,80,60,0.5)', 3 + Math.random() * 2, 0.6, rnd(18), rnd(12), 14);
        break;
      case 'charge':
        for (let i = 0; i < 6; i++) puff(e.x + rnd(10), e.y + rnd(7), 3, 'rgba(140,125,95,0.55)', 3.5, 0.55, rnd(30), rnd(18), 8);
        break;
      case 'rally':
        markers.push({ x: e.x, y: e.y, t: 0, ttl: 0.9, kind: 'rally' });
        break;
      case 'order':
        markers.push({ x: e.x, y: e.y, t: 0, ttl: 0.8, kind: e.attackMove ? 'attack' : 'move' });
        break;
      case 'miss':
        puff(e.x, e.y, 2, 'rgba(110,100,75,0.5)', 2.5, 0.4, rnd(10), rnd(8), 6);
        break;
      case 'rout':
        puff(e.x, e.y, 16, 'rgba(220,220,215,0.5)', 3, 0.5, rnd(8), rnd(6), 18);
        break;
    }
  }
}

const rnd = (s) => (Math.random() - 0.5) * 2 * s;

// ---------------------------------------------------------------- figures

function figure(ctx, cam, u, time, enemyFaction) {
  const p = cam.toScreen(u.x, u.y);
  const z = cam.zoom;
  const fac = u.player ? FACTIONS.player : FACTIONS[enemyFaction] || FACTIONS.bandit;
  const dead = u.state === 'dead';
  const cosF = Math.cos(u.facing), sinF = Math.sin(u.facing);
  const moving = u.state === 'moving' || u.state === 'routing';
  const bob = moving ? Math.sin(time * 11 + u.uid * 1.3) * 1.3 : 0;

  if (dead) {
    // fallen figure fades into the field
    const alpha = Math.max(0, 0.75 - (u.deadT || 0) * 0.05);
    if (alpha <= 0) return;
    ctx.globalAlpha = alpha;
    ctx.fillStyle = fac.dark;
    ctx.beginPath(); ctx.ellipse(p.x, p.y, 8 * z, 3.4 * z, u.facing, 0, Math.PI * 2); ctx.fill();
    ctx.globalAlpha = 1;
    return;
  }

  const H = (u.type === 'hero' ? 19 : u.def.cavalry ? 13 : 15) * z;

  // shadow
  ctx.fillStyle = 'rgba(0,0,0,0.32)';
  ctx.beginPath(); ctx.ellipse(p.x, p.y + 1.5 * z, u.def.radius * 1.1 * z, u.def.radius * 0.5 * z, 0, 0, Math.PI * 2); ctx.fill();

  if (u.def.cavalry) {
    // horse: body ellipse along facing, legs, then rider
    ctx.fillStyle = u.type === 'boilerlancer' ? '#3d3a38' : '#6a5138';
    ctx.beginPath();
    ctx.ellipse(p.x, p.y - 6 * z + bob * 0.4, 11 * z, 5 * z, Math.atan2(sinF * Y_SQUASH, cosF), 0, Math.PI * 2);
    ctx.fill();
    // head
    ctx.beginPath();
    ctx.arc(p.x + cosF * 12 * z, p.y + sinF * 5 * z - 9 * z + bob * 0.4, 2.6 * z, 0, Math.PI * 2);
    ctx.fill();
    // legs
    ctx.strokeStyle = '#4a3826'; ctx.lineWidth = 1.6 * z;
    for (const s of [-1, 1]) {
      const lx = p.x + cosF * 6 * z * s, gallop = moving ? Math.sin(time * 13 + u.uid + s) * 2 : 0;
      ctx.beginPath(); ctx.moveTo(lx, p.y - 5 * z); ctx.lineTo(lx + gallop * z, p.y + 1 * z); ctx.stroke();
    }
    // rider torso
    ctx.fillStyle = fac.color;
    ctx.fillRect(p.x - 2.2 * z, p.y - H - 2 * z + bob, 4.4 * z, 7 * z);
    ctx.fillStyle = '#c8b89a';
    ctx.beginPath(); ctx.arc(p.x, p.y - H - 3.5 * z + bob, 2.2 * z, 0, Math.PI * 2); ctx.fill();
    if (u.type === 'boilerlancer') {
      // back boiler + lance
      ctx.fillStyle = '#45464b';
      ctx.fillRect(p.x - cosF * 5 * z - 2.4 * z, p.y - H - 1 * z + bob, 4.8 * z, 5.5 * z);
      ctx.fillStyle = '#c9a959';
      ctx.fillRect(p.x - cosF * 5 * z - 1 * z, p.y - H - 2.2 * z + bob, 2 * z, 1.6 * z);
      ctx.strokeStyle = '#8a8578'; ctx.lineWidth = 1.8 * z;
      ctx.beginPath();
      ctx.moveTo(p.x - cosF * 4 * z, p.y - H + 3 * z + bob);
      ctx.lineTo(p.x + cosF * 18 * z, p.y + sinF * 8 * z - H + 5 * z + bob);
      ctx.stroke();
      if (u.chargeReady && moving) puffIf(u, time, p, z);
    } else {
      // scout sabre
      ctx.strokeStyle = '#9a958a'; ctx.lineWidth = 1.2 * z;
      ctx.beginPath();
      ctx.moveTo(p.x + cosF * 3 * z, p.y - H + 2 * z + bob);
      ctx.lineTo(p.x + cosF * 10 * z, p.y + sinF * 4 * z - H + 1 * z + bob);
      ctx.stroke();
    }
  } else {
    // infantry: legs, torso, head
    ctx.strokeStyle = '#3a3128'; ctx.lineWidth = 1.6 * z;
    const step = moving ? Math.sin(time * 12 + u.uid) * 2.4 : 1.2;
    ctx.beginPath();
    ctx.moveTo(p.x - step * z * 0.5, p.y); ctx.lineTo(p.x - 1 * z, p.y - 6 * z);
    ctx.moveTo(p.x + step * z * 0.5, p.y); ctx.lineTo(p.x + 1 * z, p.y - 6 * z);
    ctx.stroke();
    ctx.fillStyle = u.type === 'hero' ? '#3a3f36' : fac.color;
    ctx.fillRect(p.x - 2.6 * z, p.y - H + bob, 5.2 * z, H - 5 * z);
    // head
    ctx.fillStyle = '#c8b89a';
    ctx.beginPath(); ctx.arc(p.x, p.y - H - 1.5 * z + bob, 2.4 * z, 0, Math.PI * 2); ctx.fill();
    // helmet hint
    ctx.fillStyle = u.type === 'hero' ? '#c9a959' : '#5d5a52';
    ctx.beginPath(); ctx.arc(p.x, p.y - H - 2.2 * z + bob, 2.2 * z, Math.PI, 0); ctx.fill();

    switch (u.type) {
      case 'spearman':
        ctx.strokeStyle = '#8a7450'; ctx.lineWidth = 1.3 * z;
        ctx.beginPath();
        ctx.moveTo(p.x - cosF * 4 * z, p.y - 4 * z);
        ctx.lineTo(p.x + cosF * 16 * z, p.y + sinF * 7 * z - 14 * z);
        ctx.stroke();
        ctx.fillStyle = '#9a958a';
        ctx.beginPath(); ctx.arc(p.x + cosF * 16 * z, p.y + sinF * 7 * z - 14 * z, 1.2 * z, 0, Math.PI * 2); ctx.fill();
        break;
      case 'shieldman': {
        ctx.fillStyle = '#6d5335';
        const sx = p.x + cosF * 5 * z, sy = p.y + sinF * 2.5 * z - H + 2 * z + bob;
        ctx.fillRect(sx - 2 * z, sy, 4 * z, 9 * z);
        ctx.strokeStyle = '#45464b'; ctx.lineWidth = 0.8 * z;
        ctx.strokeRect(sx - 2 * z, sy, 4 * z, 9 * z);
        break;
      }
      case 'bowman':
        ctx.strokeStyle = '#8a7450'; ctx.lineWidth = 1.2 * z;
        ctx.beginPath();
        ctx.arc(p.x + cosF * 5 * z, p.y + sinF * 2 * z - H + 4 * z + bob, 5 * z, u.facing - 1.2, u.facing + 1.2);
        ctx.stroke();
        break;
      case 'pressurebow': {
        // reservoir backpack with brass gauge + reinforced bow
        ctx.fillStyle = '#45464b';
        ctx.fillRect(p.x - cosF * 5 * z - 2.2 * z, p.y - H + 1 * z + bob, 4.4 * z, 6.5 * z);
        ctx.fillStyle = '#c9a959';
        ctx.beginPath(); ctx.arc(p.x - cosF * 5 * z, p.y - H + 2.4 * z + bob, 1.1 * z, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = '#2e2b29'; ctx.lineWidth = 0.8 * z;
        ctx.beginPath();
        ctx.moveTo(p.x - cosF * 5 * z, p.y - H + 5 * z + bob);
        ctx.quadraticCurveTo(p.x, p.y - H + 8 * z, p.x + cosF * 5 * z, p.y - H + 5 * z + bob);
        ctx.stroke();
        ctx.strokeStyle = '#6d6a62'; ctx.lineWidth = 1.7 * z;
        ctx.beginPath();
        ctx.arc(p.x + cosF * 5.5 * z, p.y + sinF * 2 * z - H + 4 * z + bob, 6 * z, u.facing - 1.1, u.facing + 1.1);
        ctx.stroke();
        break;
      }
      case 'hero': {
        // back banner
        ctx.strokeStyle = '#3a3128'; ctx.lineWidth = 1.1 * z;
        ctx.beginPath();
        ctx.moveTo(p.x - cosF * 3 * z, p.y - H + 2 * z);
        ctx.lineTo(p.x - cosF * 3 * z, p.y - H - 12 * z);
        ctx.stroke();
        ctx.fillStyle = FACTIONS.player.banner;
        ctx.beginPath();
        ctx.moveTo(p.x - cosF * 3 * z, p.y - H - 12 * z);
        ctx.lineTo(p.x - cosF * 3 * z + 8 * z, p.y - H - 9.5 * z);
        ctx.lineTo(p.x - cosF * 3 * z, p.y - H - 7 * z);
        ctx.closePath(); ctx.fill();
        // sword
        ctx.strokeStyle = '#b8b4a8'; ctx.lineWidth = 1.4 * z;
        ctx.beginPath();
        ctx.moveTo(p.x + cosF * 4 * z, p.y - 8 * z);
        ctx.lineTo(p.x + cosF * 11 * z, p.y + sinF * 5 * z - 13 * z);
        ctx.stroke();
        break;
      }
      default: // levy: hatchet
        ctx.strokeStyle = '#8a7450'; ctx.lineWidth = 1.1 * z;
        ctx.beginPath();
        ctx.moveTo(p.x + cosF * 3 * z, p.y - 7 * z);
        ctx.lineTo(p.x + cosF * 8 * z, p.y + sinF * 3 * z - 11 * z);
        ctx.stroke();
    }
  }

  // veteran chevron
  if (u.vet && u.type !== 'hero') {
    ctx.strokeStyle = '#c9a959'; ctx.lineWidth = 1.2 * z;
    ctx.beginPath();
    ctx.moveTo(p.x - 2.5 * z, p.y - H - 5.5 * z);
    ctx.lineTo(p.x, p.y - H - 7.5 * z);
    ctx.lineTo(p.x + 2.5 * z, p.y - H - 5.5 * z);
    ctx.stroke();
  }

  // hp bar when hurt
  if (u.hp < u.maxHp) {
    const w = 14 * z;
    ctx.fillStyle = 'rgba(0,0,0,0.55)';
    ctx.fillRect(p.x - w / 2, p.y - H - 5 * z, w, 2.4 * z);
    const frac = Math.max(0, u.hp / u.maxHp);
    ctx.fillStyle = frac > 0.55 ? '#7ba05b' : frac > 0.25 ? '#c9a959' : '#b5533c';
    ctx.fillRect(p.x - w / 2, p.y - H - 5 * z, w * frac, 2.4 * z);
  }
  // wavering morale marker
  if (u.type !== 'hero' && u.morale < u.moraleMax * 0.4 && u.state !== 'routing') {
    ctx.fillStyle = `rgba(230,200,90,${0.5 + 0.4 * Math.sin(time * 8)})`;
    ctx.beginPath(); ctx.arc(p.x + 8 * z, p.y - H - 6 * z, 1.6 * z, 0, Math.PI * 2); ctx.fill();
  }
  if (u.state === 'routing') {
    ctx.fillStyle = 'rgba(235,235,230,0.85)';
    ctx.font = `700 ${8 * z}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.fillText('!', p.x + 7 * z, p.y - H - 5 * z);
  }
}

// occasional steam wisp from primed boiler lancers
function puffIf(u, time, p, z) {
  if (Math.random() < 0.06) puff(u.x - Math.cos(u.facing) * 8, u.y, 18, 'rgba(225,225,220,0.5)', 2.5, 0.5, rnd(8), rnd(6), 22);
}

// ---------------------------------------------------------------- terrain pieces

function drawObstacle(ctx, cam, o, time) {
  const z = cam.zoom;
  if (o.kind === 'tree') {
    const p = cam.toScreen(o.x, o.y);
    ctx.fillStyle = 'rgba(0,0,0,0.28)';
    ctx.beginPath(); ctx.ellipse(p.x, p.y, o.r * 0.7 * z, o.r * 0.3 * z, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#4a3826';
    ctx.fillRect(p.x - 1.6 * z, p.y - 14 * z, 3.2 * z, 14 * z);
    ctx.fillStyle = '#39502f';
    ctx.beginPath();
    ctx.moveTo(p.x, p.y - (26 + o.r) * z);
    ctx.lineTo(p.x + o.r * 0.75 * z, p.y - 8 * z);
    ctx.lineTo(p.x - o.r * 0.75 * z, p.y - 8 * z);
    ctx.closePath(); ctx.fill();
    ctx.fillStyle = '#455e35';
    ctx.beginPath();
    ctx.moveTo(p.x, p.y - (30 + o.r) * z);
    ctx.lineTo(p.x + o.r * 0.5 * z, p.y - 16 * z);
    ctx.lineTo(p.x - o.r * 0.5 * z, p.y - 16 * z);
    ctx.closePath(); ctx.fill();
  } else if (o.kind === 'rock' || o.kind === 'spoil') {
    const p = cam.toScreen(o.x, o.y);
    ctx.fillStyle = o.kind === 'rock' ? '#6d6a62' : '#33302d';
    ctx.beginPath();
    ctx.ellipse(p.x, p.y - o.r * 0.3 * z, o.r * 0.9 * z, o.r * 0.55 * z, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = o.kind === 'rock' ? '#7d7a70' : '#403c38';
    ctx.beginPath();
    ctx.ellipse(p.x - o.r * 0.2 * z, p.y - o.r * 0.5 * z, o.r * 0.5 * z, o.r * 0.3 * z, 0, 0, Math.PI * 2);
    ctx.fill();
  } else if (o.kind === 'boiler') {
    const p = cam.toScreen(o.x, o.y);
    ctx.fillStyle = 'rgba(0,0,0,0.3)';
    ctx.beginPath(); ctx.ellipse(p.x, p.y, o.r * z, o.r * 0.45 * z, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#45464b';
    ctx.fillRect(p.x - o.r * 0.8 * z, p.y - o.r * 1.6 * z, o.r * 1.6 * z, o.r * 1.6 * z);
    ctx.fillStyle = '#54555c';
    ctx.beginPath(); ctx.ellipse(p.x, p.y - o.r * 1.6 * z, o.r * 0.8 * z, o.r * 0.35 * z, 0, 0, Math.PI * 2); ctx.fill();
    // rivets + brass valve
    ctx.fillStyle = '#2e2f33';
    for (let i = 0; i < 3; i++) ctx.fillRect(p.x - o.r * 0.8 * z, p.y - o.r * (0.4 + i * 0.5) * z, o.r * 1.6 * z, 1.2 * z);
    ctx.fillStyle = '#c9a959';
    ctx.fillRect(p.x - 2 * z, p.y - o.r * 1.85 * z, 4 * z, 4 * z);
    if (Math.random() < 0.02) puff(o.x, o.y - 4, o.r * 1.9, 'rgba(225,225,220,0.45)', 3, 0.9, rnd(6), rnd(4), 20);
  }
}

function drawRect(ctx, cam, r, time) {
  const z = cam.zoom;
  const a = cam.toScreen(r.x, r.y), b = cam.toScreen(r.x + r.w, r.y + r.h);
  if (r.kind === 'river') {
    ctx.fillStyle = '#39586b';
    ctx.fillRect(a.x, a.y, b.x - a.x, b.y - a.y);
    ctx.fillStyle = 'rgba(140,180,200,0.18)';
    for (let i = 0; i < 4; i++) {
      const yy = a.y + ((time * 12 + i * 40) % (b.y - a.y));
      ctx.fillRect(a.x + 6, yy, b.x - a.x - 12, 2);
    }
  } else if (r.kind === 'house' || r.kind === 'shed') {
    const h = (r.kind === 'house' ? 34 : 26) * z;
    ctx.fillStyle = 'rgba(0,0,0,0.28)';
    ctx.beginPath();
    ctx.ellipse((a.x + b.x) / 2, b.y, (b.x - a.x) * 0.62, 7, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = r.kind === 'house' ? '#7a6448' : '#5d5344';
    ctx.fillRect(a.x, a.y - h, b.x - a.x, (b.y - a.y) + h);
    ctx.fillStyle = r.kind === 'house' ? '#8a5238' : '#4c4a48';
    ctx.beginPath();
    ctx.moveTo(a.x - 3 * z, a.y - h);
    ctx.lineTo((a.x + b.x) / 2, a.y - h - 16 * z);
    ctx.lineTo(b.x + 3 * z, a.y - h);
    ctx.closePath(); ctx.fill();
  } else if (r.kind === 'wall' || r.kind === 'tower') {
    const h = (r.kind === 'tower' ? 44 : 32) * z;
    const w = b.x - a.x;
    // stone curtain wall: solid band with lit/shadow edges, buttresses, merlons
    ctx.fillStyle = '#54514a';
    ctx.fillRect(a.x, a.y - h, w, (b.y - a.y) + h);
    ctx.fillStyle = '#6b675f';
    ctx.fillRect(a.x, a.y - h, Math.max(3, w * 0.3), (b.y - a.y) + h);
    ctx.fillStyle = '#3c3a35';
    ctx.fillRect(b.x - Math.max(2, w * 0.18), a.y - h, Math.max(2, w * 0.18), (b.y - a.y) + h);
    // buttress blocks give the wall rhythm without reading as rungs
    ctx.fillStyle = '#615d55';
    for (let y = a.y - h + 30 * z; y < b.y - 20 * z; y += 105 * z) {
      ctx.fillRect(a.x - 4 * z, y, w + 8 * z, 16 * z);
    }
    // merlons along the parapet line
    ctx.fillStyle = '#7d786e';
    for (let y = a.y - h + 6 * z; y < b.y - 4; y += 24 * z) {
      ctx.fillRect(a.x + w * 0.3, y, w * 0.4, 6 * z);
    }
  } else if (r.kind === 'cart') {
    ctx.fillStyle = '#4a3826';
    ctx.fillRect(a.x, a.y - 10 * z, b.x - a.x, (b.y - a.y) + 10 * z);
    ctx.fillStyle = '#2e2b29';
    ctx.fillRect(a.x + 2, a.y - 13 * z, b.x - a.x - 4, 5 * z);
    ctx.strokeStyle = '#3a3128'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(a.x + 6 * z, b.y, 5 * z, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.arc(b.x - 6 * z, b.y, 5 * z, 0, Math.PI * 2); ctx.stroke();
  }
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

  // hills
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
    } else if (d.kind === 'gate') {
      ctx.fillStyle = 'rgba(110,95,60,0.4)';
      ctx.fillRect(p.x - (d.w / 2) * cam.zoom, p.y - (d.h / 2) * cam.zoom * Y_SQUASH, d.w * cam.zoom, d.h * cam.zoom * Y_SQUASH);
    } else if (d.kind === 'grass' || d.kind === 'track') {
      ctx.strokeStyle = d.kind === 'grass' ? 'rgba(120,140,80,0.3)' : 'rgba(150,128,88,0.35)';
      ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(p.x - 4, p.y); ctx.lineTo(p.x + 4, p.y - 3); ctx.stroke();
    } else if (d.kind === 'fence') {
      ctx.strokeStyle = '#5d4a34'; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(p.x - 18 * cam.zoom, p.y); ctx.lineTo(p.x + 18 * cam.zoom, p.y); ctx.stroke();
      for (let i = -1; i <= 1; i++) {
        ctx.beginPath(); ctx.moveTo(p.x + i * 14 * cam.zoom, p.y + 2); ctx.lineTo(p.x + i * 14 * cam.zoom, p.y - 8 * cam.zoom); ctx.stroke();
      }
    }
  }

  // selection rings under figures
  for (const u of b.units) {
    if (!b.selection.has(u.uid) || u.state === 'dead' || u.state === 'fled') continue;
    const p = cam.toScreen(u.x, u.y);
    ctx.strokeStyle = '#c9a959';
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.ellipse(p.x, p.y + 1, (u.def.radius + 4) * cam.zoom, (u.def.radius + 4) * cam.zoom * 0.45, 0, 0, Math.PI * 2);
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
      ctx.ellipse(p.x, p.y, (14 - k * 8) * cam.zoom, (14 - k * 8) * cam.zoom * 0.45, 0, 0, Math.PI * 2);
      ctx.stroke();
    }
  }

  // y-sorted world entities: obstacles + units
  const drawables = [];
  for (const o of b.terrain.circles) drawables.push({ y: o.y, draw: () => drawObstacle(ctx, cam, o, time) });
  for (const r of b.terrain.rects) drawables.push({ y: r.y + r.h, draw: () => drawRect(ctx, cam, r, time) });
  for (const u of b.units) {
    if (u.state === 'fled') continue;
    drawables.push({ y: u.y + (u.state === 'dead' ? -1000 : 0), draw: () => figure(ctx, cam, u, time, b.ctx.enemyFaction) });
  }
  drawables.sort((a, c) => a.y - c.y);
  for (const d of drawables) d.draw();

  // projectiles
  for (const p of b.projectiles) {
    const s = cam.toScreen(p.x, p.y, p.z || 0);
    const dirx = p.tx - p.sx, diry = p.ty - p.sy;
    const dl = Math.hypot(dirx, diry) || 1;
    const len = p.pierce ? 10 : 7;
    ctx.strokeStyle = p.pierce ? '#c9a959' : '#d8d2c4';
    ctx.lineWidth = p.pierce ? 2.2 : 1.3;
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
