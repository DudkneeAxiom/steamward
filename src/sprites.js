// Voxel sprite atlases rendered in Blender (see tools/blender/).
//
// Every frame is drawn with the model origin at its centre, so a sprite is
// blitted by centring it on the object's ground position — no per-sprite
// anchor bookkeeping. Sprites are authored at zoom 1, so world pixels and
// sprite pixels are the same thing before the camera scale is applied.

import { Y_SQUASH } from './camera.js';

const BASE = 'assets/';
const FACTIONS = ['player', 'falkmoor', 'brennan', 'bandit', 'neutral'];

let unitSheets = {};      // faction -> HTMLImageElement
let unitMeta = null;      // { cell:[w,h], facings, poses, rows:[...] }
let propSheet = null;
let propMeta = null;
let rowIndex = {};
let loaded = false;

export const isLoaded = () => loaded;

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('failed to load ' + src));
    img.src = src;
  });
}

export async function loadSprites() {
  if (loaded) return true;
  const [uMeta, pMeta] = await Promise.all([
    fetch(BASE + 'units.json').then(r => r.json()),
    fetch(BASE + 'props.json').then(r => r.json()),
  ]);
  unitMeta = uMeta;
  propMeta = pMeta;
  unitMeta.rows.forEach((name, i) => { rowIndex[name] = i; });
  const sheets = await Promise.all([
    ...FACTIONS.map(f => loadImage(`${BASE}units-${f}.png`)),
    loadImage(BASE + 'props.png'),
  ]);
  FACTIONS.forEach((f, i) => { unitSheets[f] = sheets[i]; });
  propSheet = sheets[sheets.length - 1];
  loaded = true;
  return true;
}

// ---------------------------------------------------------------- props

export function propSize(name) {
  const f = propMeta && propMeta.frames[name];
  return f ? { w: f.fw, d: f.fd, h: f.fh } : { w: 20, d: 20, h: 20 };
}

export function hasProp(name) {
  return !!(propMeta && propMeta.frames[name]);
}

// Draw a prop standing on the ground at world (x, y).
export function drawProp(ctx, cam, name, x, y, scale = 1, alpha = 1) {
  if (!loaded) return false;
  const f = propMeta.frames[name];
  if (!f) return false;
  const p = cam.toScreen(x, y);
  const s = cam.zoom * scale;
  const w = f.w * s, h = f.h * s;
  if (alpha !== 1) ctx.globalAlpha = alpha;
  ctx.drawImage(propSheet, f.x, f.y, f.w, f.h, p.x - w / 2, p.y - h / 2, w, h);
  if (alpha !== 1) ctx.globalAlpha = 1;
  return true;
}

// Soft contact shadow so pieces sit on the ground instead of floating.
export function drawShadow(ctx, cam, x, y, rx, squash = 0.42, alpha = 0.3) {
  const p = cam.toScreen(x, y);
  ctx.fillStyle = `rgba(0,0,0,${alpha})`;
  ctx.beginPath();
  ctx.ellipse(p.x, p.y, rx * cam.zoom, rx * cam.zoom * squash, 0, 0, Math.PI * 2);
  ctx.fill();
}

// ---------------------------------------------------------------- units

// facing: world radians (0 = +x). pose: 0 stand, 1/2 walk.
export function drawUnit(ctx, cam, faction, type, facing, pose, x, y, alpha = 1) {
  if (!loaded) return false;
  const sheet = unitSheets[faction] || unitSheets.neutral;
  const row = rowIndex[type];
  if (row === undefined || !sheet) return false;
  const n = unitMeta.facings;
  let f = Math.round(facing / (Math.PI * 2 / n)) % n;
  if (f < 0) f += n;
  const [cw, ch] = unitMeta.cell;
  const sx = ((pose % unitMeta.poses) * n + f) * cw;
  const sy = row * ch;
  const p = cam.toScreen(x, y);
  const s = cam.zoom;
  if (alpha !== 1) ctx.globalAlpha = alpha;
  ctx.drawImage(sheet, sx, sy, cw, ch, p.x - cw * s / 2, p.y - ch * s / 2, cw * s, ch * s);
  if (alpha !== 1) ctx.globalAlpha = 1;
  return true;
}

// A soldier's walk cycle: two step frames while moving, stand otherwise.
export function walkPose(moving, time, seed) {
  if (!moving) return 0;
  return 1 + (Math.floor(time * 7 + seed) % 2);
}

export const Y_SQUASH_REF = Y_SQUASH;
