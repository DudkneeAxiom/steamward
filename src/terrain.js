// Terrain as actual geography.
//
// A heightfield is built from authored features (hills, a river valley, roads,
// settlement platforms) plus controlled fBm — the noise adds richness, the
// authoring decides where things are. Heights are then quantised into steps, so
// meshing produces flat terraces joined by real vertical cliff faces rather
// than a smooth blob. The result reads as a physically constructed miniature.
//
// The simulation stays 2D: gameplay uses (x, y) exactly as before and the
// renderer looks up ground height to place things in 3D.

import * as THREE from '../vendor/three/three.module.min.js';
import { clamp, makeRng, segDist } from './util.js';

export const STEP = 9;             // vertical quantisation — terrace thickness
export const WATER_LEVEL = 6;

// Ground materials, indexed by the mesher. Colour is picked per cell from the
// biome plus slope, so cliffs show rock and valley floors show mud.
export const BIOME = {
  grass: 0, dirt: 1, rock: 2, farm: 3, soot: 4, sand: 5, road: 6,
};

const BIOME_COLOR = {
  [BIOME.grass]: [0.33, 0.42, 0.21],
  [BIOME.dirt]: [0.36, 0.29, 0.19],
  [BIOME.rock]: [0.44, 0.43, 0.41],
  [BIOME.farm]: [0.50, 0.42, 0.20],
  [BIOME.soot]: [0.22, 0.21, 0.19],
  [BIOME.sand]: [0.52, 0.47, 0.33],
  [BIOME.road]: [0.42, 0.35, 0.24],
};
// A one-step lip is a fold in the ground and should read as shading; only a
// real drop shows bare rock. Colouring every step grey turned the whole map
// into speckle.
const CLIFF_ROCK = [0.42, 0.41, 0.38];

// Vertex colours go to the GPU as linear values, but these are authored as
// sRGB — what the eye sees. Skipping the conversion is what makes ground read
// as washed-out beige instead of earth.
const srgbToLinear = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const toLinear = (rgb) => [srgbToLinear(rgb[0]), srgbToLinear(rgb[1]), srgbToLinear(rgb[2])];
// A shallow step is a fold in the ground: lighting already darkens a vertical
// face, and darkening its colour as well turned every slope into a
// checkerboard. Only a real drop shows bare rock.
const cliffColor = (baseLinear, steps) => {
  if (steps >= 3) return toLinear(CLIFF_ROCK);
  if (steps >= 2) return [baseLinear[0] * 0.85, baseLinear[1] * 0.85, baseLinear[2] * 0.85];
  return baseLinear;
};

// ---------------------------------------------------------------- noise

function valueNoise2D(seed) {
  const rng = makeRng(seed);
  const size = 256;
  const perm = new Uint8Array(size * 2);
  for (let i = 0; i < size; i++) perm[i] = i;
  for (let i = size - 1; i > 0; i--) {
    const j = rng.int(0, i);
    const t = perm[i]; perm[i] = perm[j]; perm[j] = t;
  }
  for (let i = 0; i < size; i++) perm[size + i] = perm[i];
  const grad = new Float32Array(size * 2);
  for (let i = 0; i < size; i++) {
    const a = rng.float(0, Math.PI * 2);
    grad[i * 2] = Math.cos(a);
    grad[i * 2 + 1] = Math.sin(a);
  }
  const fade = (t) => t * t * t * (t * (t * 6 - 15) + 10);
  return (x, y) => {
    const xi = Math.floor(x) & 255, yi = Math.floor(y) & 255;
    const xf = x - Math.floor(x), yf = y - Math.floor(y);
    const u = fade(xf), v = fade(yf);
    const dot = (gi, dx, dy) => grad[gi * 2] * dx + grad[gi * 2 + 1] * dy;
    const aa = perm[perm[xi] + yi], ab = perm[perm[xi] + yi + 1];
    const ba = perm[perm[xi + 1] + yi], bb = perm[perm[xi + 1] + yi + 1];
    const x1 = dot(aa, xf, yf) * (1 - u) + dot(ba, xf - 1, yf) * u;
    const x2 = dot(ab, xf, yf - 1) * (1 - u) + dot(bb, xf - 1, yf - 1) * u;
    return x1 * (1 - v) + x2 * v;
  };
}

function fbm(noise, x, y, octaves, freq, gain = 0.5) {
  let sum = 0, amp = 1, f = freq, norm = 0;
  for (let i = 0; i < octaves; i++) {
    sum += noise(x * f, y * f) * amp;
    norm += amp;
    amp *= gain;
    f *= 2.03;
  }
  return sum / norm;
}

// ---------------------------------------------------------------- heightfield

export class Heightfield {
  // `margin` extends the ground past the playable area so the map never simply
  // stops at a visible edge.
  constructor(w, h, cell, margin = 0) {
    this.w = w; this.h = h; this.cell = cell;
    this.ox = -margin; this.oy = -margin;
    this.cols = Math.ceil((w + margin * 2) / cell) + 1;
    this.rows = Math.ceil((h + margin * 2) / cell) + 1;
    this.height = new Float32Array(this.cols * this.rows);
    this.biome = new Uint8Array(this.cols * this.rows);
    // 0..1 fields blended in the mesher, so a works site or an outcrop shades
    // smoothly instead of switching cell by cell
    this.stain = new Float32Array(this.cols * this.rows);
    this.rock = new Float32Array(this.cols * this.rows);
  }
  // world position of grid sample (i, j)
  wx(i) { return this.ox + i * this.cell; }
  wy(j) { return this.oy + j * this.cell; }
  idx(i, j) {
    return clamp(j, 0, this.rows - 1) * this.cols + clamp(i, 0, this.cols - 1);
  }
  // Bilinear sample so units and props sit smoothly on terraces.
  heightAt(x, y) {
    const fx = clamp((x - this.ox) / this.cell, 0, this.cols - 1.001);
    const fy = clamp((y - this.oy) / this.cell, 0, this.rows - 1.001);
    const i = Math.floor(fx), j = Math.floor(fy);
    const tx = fx - i, ty = fy - j;
    const h00 = this.height[this.idx(i, j)], h10 = this.height[this.idx(i + 1, j)];
    const h01 = this.height[this.idx(i, j + 1)], h11 = this.height[this.idx(i + 1, j + 1)];
    return (h00 * (1 - tx) + h10 * tx) * (1 - ty) + (h01 * (1 - tx) + h11 * tx) * ty;
  }
  biomeAt(x, y) {
    return this.biome[this.idx(Math.round((x - this.ox) / this.cell),
                              Math.round((y - this.oy) / this.cell))];
  }
  slopeAt(x, y) {
    const d = this.cell;
    const hx = this.heightAt(x + d, y) - this.heightAt(x - d, y);
    const hy = this.heightAt(x, y + d) - this.heightAt(x, y - d);
    return Math.hypot(hx, hy) / (2 * d);
  }
}

const quantise = (h) => Math.round(h / STEP) * STEP;

/**
 * Blur the heightfield before quantising. Without this, neighbouring cells
 * land on different steps almost everywhere and the map becomes a staircase of
 * thin cliff faces instead of broad terraces with occasional real drops.
 */
/** Blur an arbitrary per-cell field (rockiness, staining). */
function blurField(field, cols, rows, passes = 1) {
  let src = field;
  let dst = new Float32Array(field.length);
  for (let p = 0; p < passes; p++) {
    for (let j = 0; j < rows; j++) {
      for (let i = 0; i < cols; i++) {
        let sum = 0, n = 0;
        for (let dj = -1; dj <= 1; dj++) {
          for (let di = -1; di <= 1; di++) {
            const ii = clamp(i + di, 0, cols - 1), jj = clamp(j + dj, 0, rows - 1);
            sum += src[jj * cols + ii]; n++;
          }
        }
        dst[j * cols + i] = sum / n;
      }
    }
    const t = src; src = dst; dst = t;
  }
  if (src !== field) field.set(src);
}

function smoothField(hf, passes = 3) {
  const { cols, rows } = hf;
  let src = hf.height;
  let dst = new Float32Array(src.length);
  for (let p = 0; p < passes; p++) {
    for (let j = 0; j < rows; j++) {
      for (let i = 0; i < cols; i++) {
        let sum = 0, n = 0;
        for (let dj = -1; dj <= 1; dj++) {
          for (let di = -1; di <= 1; di++) {
            const ii = clamp(i + di, 0, cols - 1), jj = clamp(j + dj, 0, rows - 1);
            const w = (di === 0 && dj === 0) ? 4 : 1;
            sum += src[jj * cols + ii] * w;
            n += w;
          }
        }
        dst[j * cols + i] = sum / n;
      }
    }
    const t = src; src = dst; dst = t;
  }
  if (src !== hf.height) hf.height.set(src);
}

// Distance to a polyline, used for rivers and roads.
function polyDist(x, y, pts) {
  let best = 1e9;
  for (let i = 0; i < pts.length - 1; i++) {
    const d = segDist(x, y, pts[i].x, pts[i].y, pts[i + 1].x, pts[i + 1].y);
    if (d < best) best = d;
  }
  return best;
}

const smoothstep = (e0, e1, v) => {
  const t = clamp((v - e0) / (e1 - e0), 0, 1);
  return t * t * (3 - 2 * t);
};

/**
 * Strategic-map terrain: real hills, a river in a real valley, roads that lie
 * in the ground, level platforms where settlements stand.
 *
 * spec: { w, h, hills:[{x,y,r}], forests, farms, river:[{x,y}], riverWidth,
 *         roads:[[{x,y}]], locations:[{x,y,type}], seed }
 */
export function buildWorldHeightfield(spec) {
  const cell = spec.cell || 26;
  const hf = new Heightfield(spec.w, spec.h, cell, spec.margin ?? 260);
  const noise = valueNoise2D(spec.seed ?? 1337);
  const detail = valueNoise2D((spec.seed ?? 1337) + 991);

  for (let j = 0; j < hf.rows; j++) {
    for (let i = 0; i < hf.cols; i++) {
      const x = hf.wx(i), y = hf.wy(j);

      // Rolling base country.
      let h = 74 + fbm(noise, x, y, 3, 0.0011) * 66 + fbm(detail, x, y, 2, 0.0032) * 10;

      // Authored highlands rise above it.
      for (const hill of spec.hills) {
        const d = Math.hypot(x - hill.x, y - hill.y);
        if (d < hill.r * 1.35) {
          const t = smoothstep(hill.r * 1.35, hill.r * 0.22, d);
          h += (hill.height || 78) * t;
        }
      }

      // The river cuts a valley: banks fall toward the water, bed sits below
      // it. Everywhere else is floored above the waterline, so water appears in
      // the valley and nowhere else.
      const rd = polyDist(x, y, spec.river);
      const bankW = spec.riverWidth * 2.6;
      let riverT = 0;
      if (rd < bankW) {
        riverT = smoothstep(bankW, spec.riverWidth * 0.45, rd);
        h = h * (1 - riverT) + (WATER_LEVEL - 18) * riverT;
      }
      if (riverT < 0.12) h = Math.max(h, WATER_LEVEL + 12);

      // Ground material is decided in a second pass from the finished terrain;
      // guessing it here (before platforms, roads and terracing) is what made
      // the map look mottled.
      let biome = BIOME.grass;

      // Farmland is worked flat-ish.
      for (const f of spec.farms) {
        const d = Math.hypot(x - f.x, y - f.y);
        if (d < f.r) {
          const t = smoothstep(f.r, f.r * 0.5, d);
          h = h * (1 - t * 0.6) + (h - fbm(detail, x, y, 2, 0.004) * 6) * t * 0.6;
          biome = BIOME.farm;
        }
      }

      if (rd < spec.riverWidth * 0.9) biome = BIOME.sand;
      hf.height[j * hf.cols + i] = h;
      hf.biome[j * hf.cols + i] = biome;
    }
  }

  // Settlements need level ground: pull a platform to one height and remember it.
  const platforms = [];
  for (const loc of spec.locations || []) {
    const r = loc.platform || 108;
    // A settlement platform never sits below the waterline — otherwise
    // flattening the ground floods the place it was meant to level.
    const level = Math.max(quantise(hf.heightAt(loc.x, loc.y)), quantise(WATER_LEVEL + 22));
    platforms.push({ x: loc.x, y: loc.y, r, level, type: loc.type });
    for (let j = 0; j < hf.rows; j++) {
      for (let i = 0; i < hf.cols; i++) {
        const x = hf.wx(i), y = hf.wy(j);
        const d = Math.hypot(x - loc.x, y - loc.y);
        if (d > r * 1.5) continue;
        const t = smoothstep(r * 1.5, r * 0.75, d);
        const k = j * hf.cols + i;
        hf.height[k] = hf.height[k] * (1 - t) + level * t;
        if (loc.type === 'coal' || loc.type === 'foundry') {
          hf.stain[k] = Math.max(hf.stain[k], smoothstep(r * 1.7, r * 0.5, d));
        }
      }
    }
  }

  // Roads lie in the ground: flatten a corridor toward the local route height.
  for (const road of spec.roads) {
    for (let j = 0; j < hf.rows; j++) {
      for (let i = 0; i < hf.cols; i++) {
        const x = hf.wx(i), y = hf.wy(j);
        const d = polyDist(x, y, road);
        if (d > 46) continue;
        const t = smoothstep(46, 16, d);
        const k = j * hf.cols + i;
        // ease toward the average of the corridor so roads don't ripple
        const avg = (hf.height[k] + hf.heightAt(x, y)) * 0.5;
        hf.height[k] = hf.height[k] * (1 - t * 0.85) + avg * t * 0.85;
        if (t > 0.55) hf.biome[k] = BIOME.road;
      }
    }
  }

  // Terrace it. Settlement platforms keep their exact level so buildings never
  // straddle a step.
  smoothField(hf, 5);
  for (let k = 0; k < hf.height.length; k++) {
    hf.height[k] = Math.max(WATER_LEVEL - 18, quantise(hf.height[k]));
  }
  for (const p of platforms) {
    for (let j = 0; j < hf.rows; j++) {
      for (let i = 0; i < hf.cols; i++) {
        const d = Math.hypot(hf.wx(i) - p.x, hf.wy(j) - p.y);
        if (d < p.r * 0.85) hf.height[j * hf.cols + i] = p.level;
      }
    }
  }
  // Exposed stone is a smooth field, not a per-cell decision: steep or high
  // ground turns rocky gradually. Switching cell by cell turned highlands into
  // a grey checkerboard.
  for (let j = 0; j < hf.rows; j++) {
    for (let i = 0; i < hf.cols; i++) {
      const k = j * hf.cols + i;
      const here = hf.height[k];
      let maxDrop = 0;
      for (const [di, dj] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        maxDrop = Math.max(maxDrop, Math.abs(here - hf.height[hf.idx(i + di, j + dj)]));
      }
      hf.rock[k] = Math.max(
        smoothstep(STEP * 1.2, STEP * 3.2, maxDrop),
        smoothstep(150, 230, here),
      );
    }
  }
  blurField(hf.rock, hf.cols, hf.rows, 2);

  hf.platforms = platforms;
  return hf;
}

/**
 * Battlefield terrain — the same visual language at a closer scale, shaped by
 * which strategic terrain the fight happened on.
 */
export function buildBattleHeightfield(kind, seed, w, h) {
  const cell = 20;
  const hf = new Heightfield(w, h, cell, 300);
  const noise = valueNoise2D(seed);
  const detail = valueNoise2D(seed + 77);
  const rng = makeRng(seed);

  const ridge = { x: rng.float(w * 0.35, w * 0.65), y: rng.float(h * 0.25, h * 0.75), r: rng.float(230, 330) };
  const riverX = w / 2, bridgeY = h / 2;

  for (let j = 0; j < hf.rows; j++) {
    for (let i = 0; i < hf.cols; i++) {
      const x = hf.wx(i), y = hf.wy(j);
      let ht = 18 + fbm(noise, x, y, 3, 0.0026) * 22 + fbm(detail, x, y, 2, 0.009) * 5;
      let biome = BIOME.grass;

      if (kind === 'open' || kind === 'fort') {
        // A hill worth holding.
        const d = Math.hypot(x - ridge.x, y - ridge.y);
        ht += 46 * smoothstep(ridge.r, ridge.r * 0.25, d);
      }
      if (kind === 'bridge') {
        const rd = Math.abs(x - riverX);
        const onBridge = Math.abs(y - bridgeY) < 90;
        if (rd < 190 && !onBridge) {
          const t = smoothstep(190, 60, rd);
          ht = ht * (1 - t) + (WATER_LEVEL - 20) * t;
          if (rd < 120) biome = BIOME.sand;
        } else if (rd < 190) {
          // causeway carrying the road across
          const t = smoothstep(190, 60, rd);
          ht = ht * (1 - t) + 22 * t;
          biome = BIOME.road;
        }
      }
      if (kind === 'industrial') {
        // A works yard is trodden earth gone black with coal dust.
        biome = BIOME.dirt;
        hf.stain[j * hf.cols + i] = clamp(0.62 + fbm(detail, x, y, 2, 0.0045) * 1.4, 0.15, 0.95);
        ht = ht * 0.7 + 12;                      // worked flat for machinery
      }
      if (kind === 'settlement') {
        // a lane through the middle
        if (Math.abs(y - h * 0.55) < 46) { biome = BIOME.road; ht = ht * 0.8 + 8; }
      }
      if (kind === 'forest') {
        ht += fbm(detail, x, y, 3, 0.006) * 10;
      }
      hf.height[j * hf.cols + i] = ht;
      hf.biome[j * hf.cols + i] = biome;
    }
  }

  // Deployment zones are level so lines form cleanly.
  for (let j = 0; j < hf.rows; j++) {
    for (let i = 0; i < hf.cols; i++) {
      const x = hf.wx(i);
      const edge = Math.min(x, w - x);
      if (edge < w * 0.16) {
        const t = smoothstep(w * 0.16, w * 0.05, edge);
        const k = j * hf.cols + i;
        hf.height[k] = hf.height[k] * (1 - t) + 20 * t;
      }
    }
  }

  smoothField(hf, 2);
  for (let k = 0; k < hf.height.length; k++) {
    hf.height[k] = Math.max(WATER_LEVEL - 20, quantise(hf.height[k]));
  }
  for (let j = 0; j < hf.rows; j++) {
    for (let i = 0; i < hf.cols; i++) {
      const k = j * hf.cols + i;
      let maxDrop = 0;
      for (const [di, dj] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        maxDrop = Math.max(maxDrop, Math.abs(hf.height[k] - hf.height[hf.idx(i + di, j + dj)]));
      }
      hf.rock[k] = smoothstep(STEP * 1.2, STEP * 3.0, maxDrop);
    }
  }
  blurField(hf.rock, hf.cols, hf.rows, 2);
  return hf;
}

// ---------------------------------------------------------------- meshing

/**
 * Stepped terrain mesh: a flat top quad per cell plus vertical cliff faces
 * wherever neighbouring cells differ in height. Flat-shaded, vertex-coloured.
 */
export function buildTerrainMesh(hf) {
  const cols = hf.cols - 1, rows = hf.rows - 1, cell = hf.cell;
  const positions = [];
  const normals = [];
  const colors = [];

  const H = (i, j) => hf.height[hf.idx(i, j)];
  const B = (i, j) => hf.biome[hf.idx(i, j)];
  const S = (i, j) => hf.stain[hf.idx(i, j)];
  const RK = (i, j) => (hf.rock ? hf.rock[hf.idx(i, j)] : 0);

  const pushTri = (ax, ay, az, bx, by, bz, cx, cy, cz, nx, ny, nz, col) => {
    positions.push(ax, ay, az, bx, by, bz, cx, cy, cz);
    normals.push(nx, ny, nz, nx, ny, nz, nx, ny, nz);
    for (let i = 0; i < 3; i++) colors.push(col[0], col[1], col[2]);
  };

  const SOOT = BIOME_COLOR[BIOME.soot];
  const ROCK = BIOME_COLOR[BIOME.rock];
  const shade = (biome, height, jitter, stain, rock) => {
    const base = (BIOME_COLOR[biome] || BIOME_COLOR[BIOME.grass]).slice();
    // bare stone shows through where the ground is steep or high
    if (rock > 0.01 && biome !== BIOME.road && biome !== BIOME.farm) {
      for (let i = 0; i < 3; i++) base[i] = base[i] * (1 - rock) + ROCK[i] * rock;
    }
    // higher ground dries out; slight per-cell variation stops it reading flat,
    // kept small so the ground never turns into a checkerboard
    const k = 1 + jitter * 0.045 + clamp((height - 60) / 520, -0.04, 0.09);
    const out = [base[0] * k, base[1] * k, base[2] * k];
    if (stain > 0.01) {
      for (let i = 0; i < 3; i++) out[i] = out[i] * (1 - stain) + SOOT[i] * stain;
    }
    return toLinear([clamp(out[0], 0, 1), clamp(out[1], 0, 1), clamp(out[2], 0, 1)]);
  };

  for (let j = 0; j < rows; j++) {
    for (let i = 0; i < cols; i++) {
      const x0 = hf.wx(i), x1 = x0 + cell;
      const z0 = hf.wy(j), z1 = z0 + cell;
      const y = H(i, j);
      const jitter = ((i * 73856093) ^ (j * 19349663)) % 7 / 7 - 0.5;
      const col = shade(B(i, j), y, jitter, S(i, j), RK(i, j));
      // top face (two tris, y-up)
      pushTri(x0, y, z0, x0, y, z1, x1, y, z1, 0, 1, 0, col);
      pushTri(x0, y, z0, x1, y, z1, x1, y, z0, 0, 1, 0, col);

      // cliff faces toward lower neighbours
      const steps = (drop) => Math.round(drop / STEP);
      const east = H(i + 1, j);
      if (east < y) {
        const c = cliffColor(col, steps(y - east));
        pushTri(x1, y, z0, x1, y, z1, x1, east, z1, 1, 0, 0, c);
        pushTri(x1, y, z0, x1, east, z1, x1, east, z0, 1, 0, 0, c);
      }
      const west = H(i - 1, j);
      if (west < y) {
        const c = cliffColor(col, steps(y - west));
        pushTri(x0, y, z1, x0, y, z0, x0, west, z0, -1, 0, 0, c);
        pushTri(x0, y, z1, x0, west, z0, x0, west, z1, -1, 0, 0, c);
      }
      const south = H(i, j + 1);
      if (south < y) {
        const c = cliffColor(col, steps(y - south));
        pushTri(x1, y, z1, x0, y, z1, x0, south, z1, 0, 0, 1, c);
        pushTri(x1, y, z1, x0, south, z1, x1, south, z1, 0, 0, 1, c);
      }
      const north = H(i, j - 1);
      if (north < y) {
        const c = cliffColor(col, steps(y - north));
        pushTri(x0, y, z0, x1, y, z0, x1, north, z0, 0, 0, -1, c);
        pushTri(x0, y, z0, x1, north, z0, x0, north, z0, 0, 0, -1, c);
      }
    }
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geo.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3));
  geo.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  geo.computeBoundingSphere();
  return geo;
}

/**
 * Water surface built only over the cells that actually lie below the
 * waterline. A single map-wide plane would z-fight with every low-lying field;
 * a river should be in its valley and nowhere else.
 */
export function buildWaterMesh(hf, level = WATER_LEVEL) {
  const cols = hf.cols - 1, rows = hf.rows - 1, cell = hf.cell;
  const positions = [], normals = [];
  const H = (i, j) => hf.height[hf.idx(i, j)];
  for (let j = 0; j < rows; j++) {
    for (let i = 0; i < cols; i++) {
      // include a cell if it or any neighbour is submerged, so the water
      // reaches under the bank instead of stopping short of it
      let wet = false;
      for (let dj = 0; dj <= 1 && !wet; dj++) {
        for (let di = 0; di <= 1 && !wet; di++) {
          if (H(i + di, j + dj) < level) wet = true;
        }
      }
      if (!wet) continue;
      const x0 = hf.wx(i), x1 = x0 + cell, z0 = hf.wy(j), z1 = z0 + cell;
      positions.push(x0, level, z0, x0, level, z1, x1, level, z1);
      positions.push(x0, level, z0, x1, level, z1, x1, level, z0);
      for (let k = 0; k < 6; k++) normals.push(0, 1, 0);
    }
  }
  if (positions.length === 0) return null;
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geo.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3));
  geo.computeBoundingSphere();
  return geo;
}

/**
 * A road ribbon that follows the ground — roads belong to the terrain instead
 * of being painted over it.
 */
export function buildRoadMesh(hf, polylines, width = 30) {
  const positions = [], normals = [], colors = [];
  const col = toLinear([0.43, 0.36, 0.25]);
  const colEdge = toLinear([0.36, 0.30, 0.20]);

  for (const line of polylines) {
    // resample so the ribbon follows terraces closely
    const pts = [];
    for (let i = 0; i < line.length - 1; i++) {
      const a = line[i], b = line[i + 1];
      const len = Math.hypot(b.x - a.x, b.y - a.y);
      const n = Math.max(1, Math.ceil(len / 18));
      for (let k = 0; k < n; k++) {
        pts.push({ x: a.x + (b.x - a.x) * k / n, y: a.y + (b.y - a.y) * k / n });
      }
    }
    pts.push(line[line.length - 1]);

    for (let i = 0; i < pts.length - 1; i++) {
      const a = pts[i], b = pts[i + 1];
      const dx = b.x - a.x, dy = b.y - a.y;
      const l = Math.hypot(dx, dy) || 1;
      const nx = -dy / l * width / 2, ny = dx / l * width / 2;
      const ay = hf.heightAt(a.x, a.y) + 0.9;
      const by = hf.heightAt(b.x, b.y) + 0.9;
      const quad = [
        [a.x - nx, ay, a.y - ny], [a.x + nx, ay, a.y + ny],
        [b.x + nx, by, b.y + ny], [b.x - nx, by, b.y - ny],
      ];
      const tris = [[0, 1, 2], [0, 2, 3]];
      for (const t of tris) {
        for (const vi of t) {
          positions.push(quad[vi][0], quad[vi][1], quad[vi][2]);
          normals.push(0, 1, 0);
          const c = (vi === 0 || vi === 3) ? colEdge : col;
          colors.push(c[0], c[1], c[2]);
        }
      }
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geo.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3));
  geo.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  geo.computeBoundingSphere();
  return geo;
}
