// The strategic world as a physical place.
//
// Terrain, water, roads and every standing object are real geometry. Static
// scenery is built once into instanced meshes; only armies and indicators are
// touched per frame.

import * as THREE from '../vendor/three/three.module.min.js';
import { flatMaterial } from './gfx.js';
import { buildWorldHeightfield, buildTerrainMesh, buildRoadMesh, buildWaterMesh, WATER_LEVEL } from './terrain.js';
import { makeStaticInstances, UNIT_MATERIAL } from './models.js';
import { UnitRenderer } from './unitView.js';
import { WORLD, isSpotted, byKey } from './campaign.js';
import { LOC_TYPES, FACTIONS } from './data.js';
import { makeRng, dist } from './util.js';
import { fitForDuty } from './soldiers.js';

// How each kind of place is built out of the settlement/military/industrial
// kits. Positions are local offsets in world units; a location is a PLACE, not
// a single oversized icon building.
const LOC_PLANS = {
  camp: [
    ['tent_a', -46, 18, 0.4], ['tent_b', 30, 34, -0.3], ['tent_a', 8, -30, 1.9],
    ['command_tent', -12, -6, 0.1], ['cart', 62, 6, 0.8], ['log_pile', -70, -22, 0.2],
  ],
  hamlet: [
    ['cottage_a', -48, 16, 0.2], ['cottage_b', 34, 36, -1.6], ['cottage_c', 18, -34, 3.0],
    ['well', -6, 2, 0], ['fence_segment', -80, -14, 0.1], ['fence_segment', -20, -46, 1.6],
    ['haystack', 62, -20, 0], ['cart', -66, 40, 0.6],
  ],
  market: [
    ['longhouse', -54, 10, 0], ['cottage_a', 44, 40, -1.5], ['cottage_c', 30, -40, 3.1],
    ['storehouse', -30, -46, 0.2], ['market_stall', 8, 30, 0], ['market_stall', 44, 8, 1.6],
    ['well', -4, -8, 0], ['cart', 70, 30, 0.4], ['crop_row', -90, 44, 0],
  ],
  coal: [
    ['mine_headframe', 6, -10, 0], ['coal_pile', -48, 22, 0], ['ore_cart', 44, 26, 0.5],
    ['workshop_small', -50, -34, 0.1], ['coal_hopper', 40, -30, 0], ['water_pump', -14, 44, 0.2],
    ['boiler_small', 62, -4, 1.5],
  ],
  foundry: [
    ['foundry_hall', -8, -6, 0], ['boiler_large', 58, 28, 0], ['chimney_stack', -62, 30, 0],
    ['coal_pile', 46, -34, 0], ['pipe_run_straight', 20, 34, 0], ['pipe_run_straight', 80, 34, 0],
    ['steam_crane', -66, -30, 0.6], ['ore_cart', 70, 6, 0.3],
  ],
  watch: [
    ['tower_round', 0, 0, 0], ['barracks', -50, 26, 0.1], ['palisade_segment', 44, 16, 1.57],
    ['palisade_segment', 44, -44, 1.57], ['tent_a', -40, -28, 0.5],
  ],
  fort: [
    ['gatehouse', 0, 46, 0], ['wall_segment', -60, 46, 0], ['wall_segment', 60, 46, 0],
    ['tower_square', -96, 46, 0], ['tower_square', 96, 46, 0],
    ['wall_segment', -96, -14, 1.5708], ['wall_segment', 96, -14, 1.5708],
    ['barracks', -40, -22, 0], ['storehouse_military', 44, -26, 0],
    ['weapon_rack', 6, 6, 0.4],
  ],
  keep: [
    ['keep', 0, -10, 0], ['wall_segment', -70, 62, 0], ['wall_segment', -10, 62, 0],
    ['wall_segment', 50, 62, 0], ['gatehouse', 110, 62, 0],
    ['tower_round', -108, 58, 0], ['tower_round', 150, 30, 0],
    ['barracks', -104, -20, 0], ['storehouse_military', 96, -30, 0], ['cart', 60, 40, 0.7],
  ],
};

// Fallbacks so a place is never empty if a kit asset is missing.
const PLAN_SUBSTITUTES = {
  cottage_b: 'cottage_a', cottage_c: 'cottage_a', longhouse: 'cottage_a',
  storehouse: 'cottage_a', storehouse_military: 'barracks', barracks: 'cottage_a',
  tent_b: 'tent_a', command_tent: 'tent_a', tower_square: 'tower_round',
  workshop_small: 'storehouse', boiler_small: 'boiler_large', ore_cart: 'cart',
  coal_hopper: 'coal_pile', pipe_run_straight: null, palisade_segment: 'fence_segment',
  weapon_rack: null, log_pile: null, haystack: null, crop_row: null, well: null,
  water_pump: null, steam_crane: null, market_stall: null, chimney_stack: null,
};

export class WorldView {
  constructor(gfx, library) {
    this.gfx = gfx;
    this.lib = library;
    this.group = new THREE.Group();
    this.hf = null;
    this.units = new UnitRenderer(gfx.scene, library);
    this.dynamic = new THREE.Group();
    this.locationLevels = new Map();
    this._built = false;
  }

  heightAt(x, y) {
    return this.hf ? this.hf.heightAt(x, y) : 0;
  }

  build(campaign) {
    const gfx = this.gfx;
    gfx.clear();
    gfx.setSkyMood({ background: 0x93aec0, haze: 0.85, sunIntensity: 1.05, skyLight: 0.45 });

    this.hf = buildWorldHeightfield({
      w: WORLD.w, h: WORLD.h, cell: 26, seed: 20260811,
      hills: WORLD.hills.map(h => ({ ...h, height: h.height || 150 })),
      forests: WORLD.forests, farms: WORLD.farms,
      river: WORLD.river, riverWidth: WORLD.riverWidth,
      roads: WORLD.roads,
      locations: campaign.locations.map(l => ({
        x: l.x, y: l.y, type: l.type,
        platform: l.type === 'keep' ? 190 : l.type === 'fort' ? 150 : 118,
      })),
    });

    this._locPositions = campaign.locations.map(l => ({ x: l.x, y: l.y }));

    const g = new THREE.Group();
    this.group = g;
    gfx.scene.add(g);

    // ---- ground
    // DoubleSide on the ground: a terrace seam viewed edge-on must never let
    // the sky through, and one extra face on a single mesh costs nothing.
    const terrain = new THREE.Mesh(
      buildTerrainMesh(this.hf),
      flatMaterial(0xffffff, { vertexColors: true, side: THREE.DoubleSide }),
    );
    terrain.receiveShadow = true;
    terrain.castShadow = false;
    g.add(terrain);
    gfx.setPickables([terrain]);
    this.terrain = terrain;

    // ---- roads laid into the ground
    const roads = new THREE.Mesh(
      buildRoadMesh(this.hf, WORLD.roads, 34),
      flatMaterial(0xffffff, { vertexColors: true, side: THREE.DoubleSide }),
    );
    roads.receiveShadow = true;
    g.add(roads);

    // ---- water, only where the ground actually lies below the waterline
    const waterGeo = buildWaterMesh(this.hf);
    if (waterGeo) {
      const water = new THREE.Mesh(waterGeo, new THREE.MeshLambertMaterial({
        color: 0x2c5568, transparent: true, opacity: 0.88, flatShading: true,
      }));
      g.add(water);
      this.water = water;
    }

    // ---- the bridge deck actually spans the river
    this._buildBridge(g);

    // ---- vegetation, rocks, farmland
    this._scatterNature(g);

    // ---- settlements
    this.locationMeshes = new Map();
    for (const loc of campaign.locations) this._buildLocation(g, loc);

    // ---- dynamic layer (armies, rings, banners)
    gfx.scene.add(this.dynamic);
    this._buildIndicators();

    gfx.setBounds(WORLD.w, WORLD.h);
    this._built = true;
  }

  _place(parent, assetName, x, z, rotY, scale = 1) {
    let name = assetName;
    while (name && !this.lib.hasProp(name)) name = PLAN_SUBSTITUTES[name] ?? null;
    if (!name) return null;
    const asset = this.lib.prop(name);
    const y = this.heightAt(x, z);
    const mats = [];
    if (asset.body) {
      const mesh = new THREE.Mesh(asset.body, UNIT_MATERIAL());
      mesh.position.set(x, y, z);
      mesh.rotation.y = rotY;
      mesh.scale.setScalar(scale);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      parent.add(mesh);
      mats.push(mesh);
    }
    if (asset.emissive) {
      const em = new THREE.Mesh(asset.emissive, new THREE.MeshBasicMaterial({ vertexColors: true }));
      em.position.set(x, y, z);
      em.rotation.y = rotY;
      em.scale.setScalar(scale);
      parent.add(em);
      mats.push(em);
    }
    return mats;
  }

  _buildLocation(parent, loc) {
    const plan = LOC_PLANS[loc.type] || [];
    const group = new THREE.Group();
    parent.add(group);
    for (const [asset, dx, dz, rot, scale] of plan) {
      this._place(group, asset, loc.x + dx, loc.y + dz, rot || 0, scale || 1);
    }
    this.locationMeshes.set(loc.key, group);
    this.locationLevels.set(loc.key, this.heightAt(loc.x, loc.y));
  }

  _buildBridge(parent) {
    const b = WORLD.bridge;
    const deckY = Math.max(this.heightAt(b.x - 110, b.y), this.heightAt(b.x + 110, b.y)) + 4;
    const deck = new THREE.Mesh(
      new THREE.BoxGeometry(230, 7, 54),
      flatMaterial(0x5a4126),
    );
    deck.position.set(b.x, deckY, b.y);
    deck.castShadow = true; deck.receiveShadow = true;
    parent.add(deck);
    // parapets and piers, so it reads as a structure crossing a gap
    for (const side of [-1, 1]) {
      const rail = new THREE.Mesh(new THREE.BoxGeometry(230, 11, 5), flatMaterial(0x6b5133));
      rail.position.set(b.x, deckY + 8, b.y + side * 25);
      rail.castShadow = true;
      parent.add(rail);
    }
    for (const dx of [-70, 0, 70]) {
      const pier = new THREE.Mesh(new THREE.BoxGeometry(22, 60, 46), flatMaterial(0x4a4843));
      pier.position.set(b.x + dx, deckY - 32, b.y);
      pier.castShadow = true; pier.receiveShadow = true;
      parent.add(pier);
    }
  }

  _scatterNature(parent) {
    const rng = makeRng(4242);
    const pineNames = ['tree_pine_a', 'tree_pine_b', 'tree_pine_c'].filter(n => this.lib.hasProp(n));
    const broadNames = ['tree_broad_a', 'tree_broad_b', 'tree_broad_c'].filter(n => this.lib.hasProp(n));
    const rockNames = ['rock_a', 'rock_b', 'rock_c'].filter(n => this.lib.hasProp(n));
    const bushNames = ['bush_a', 'bush_b'].filter(n => this.lib.hasProp(n));
    const cropNames = ['crop_row'].filter(n => this.lib.hasProp(n));
    const byAsset = new Map();
    const add = (name, t) => {
      if (!name) return;
      if (!byAsset.has(name)) byAsset.set(name, []);
      byAsset.get(name).push(t);
    };

    // Forests: dense at the core, thinning at the edge, with clearings.
    for (const f of WORLD.forests) {
      const area = Math.PI * f.r * f.r;
      const n = Math.floor(area / 5200);
      const names = rng.chance(0.6) ? pineNames : broadNames;
      if (names.length === 0) break;
      for (let i = 0; i < n; i++) {
        const a = rng.float(0, Math.PI * 2);
        const d = Math.sqrt(rng.float(0, 1)) * f.r;
        const x = f.x + Math.cos(a) * d, z = f.y + Math.sin(a) * d;
        if (x < 20 || z < 20 || x > WORLD.w - 20 || z > WORLD.h - 20) continue;
        // thin out at the fringe, leave the occasional clearing
        const edge = d / f.r;
        if (rng.float(0, 1) < edge * 0.7) continue;
        if (this._nearLocation(x, z, 150)) continue;
        const name = rng.chance(0.78) ? rng.pick(names) : rng.pick([...pineNames, ...broadNames]);
        add(name, {
          x, y: this.heightAt(x, z), z,
          rot: rng.float(0, Math.PI * 2),
          scale: rng.float(0.78, 1.28),
        });
      }
      for (let i = 0; i < n / 9; i++) {
        const a = rng.float(0, Math.PI * 2), d = Math.sqrt(rng.float(0, 1)) * f.r;
        const x = f.x + Math.cos(a) * d, z = f.y + Math.sin(a) * d;
        if (this._nearLocation(x, z, 150)) continue;
        add(rng.pick(bushNames), { x, y: this.heightAt(x, z), z, rot: rng.float(0, 6.28), scale: rng.float(0.8, 1.3) });
      }
    }

    // Rocky ground on the steep parts of the highlands.
    for (const h of WORLD.hills) {
      const n = Math.floor(h.r / 9);
      for (let i = 0; i < n; i++) {
        const a = rng.float(0, Math.PI * 2), d = Math.sqrt(rng.float(0, 1)) * h.r;
        const x = h.x + Math.cos(a) * d, z = h.y + Math.sin(a) * d;
        if (x < 20 || z < 20 || x > WORLD.w - 20 || z > WORLD.h - 20) continue;
        if (this._nearLocation(x, z, 140)) continue;
        const slope = this.hf.slopeAt(x, z);
        if (slope < 0.12 && rng.chance(0.7)) continue;
        add(rng.pick(rockNames), {
          x, y: this.heightAt(x, z), z,
          rot: rng.float(0, Math.PI * 2), scale: rng.float(0.7, 1.6),
        });
      }
    }

    // Farmland: rows of crops, aligned like worked fields.
    for (const f of WORLD.farms) {
      if (cropNames.length === 0) break;
      const rows = Math.floor(f.r / 26);
      const ang = rng.float(0, Math.PI);
      for (let r = -rows; r <= rows; r++) {
        for (let c = -rows; c <= rows; c++) {
          const ox = c * 62, oz = r * 30;
          const x = f.x + ox * Math.cos(ang) - oz * Math.sin(ang);
          const z = f.y + ox * Math.sin(ang) + oz * Math.cos(ang);
          if (dist(x, z, f.x, f.y) > f.r * 0.92) continue;
          if (this._nearLocation(x, z, 120)) continue;
          add('crop_row', { x, y: this.heightAt(x, z), z, rot: ang, scale: rng.float(0.9, 1.1) });
        }
      }
    }

    // River banks: reeds where the water meets the land.
    if (this.lib.hasProp('reeds')) {
      for (let i = 0; i < WORLD.river.length - 1; i++) {
        const a = WORLD.river[i], b = WORLD.river[i + 1];
        const steps = Math.ceil(dist(a.x, a.y, b.x, b.y) / 40);
        for (let s = 0; s < steps; s++) {
          const t = s / steps;
          const cx = a.x + (b.x - a.x) * t, cz = a.y + (b.y - a.y) * t;
          for (const side of [-1, 1]) {
            const x = cx + side * rng.float(WORLD.riverWidth * 0.55, WORLD.riverWidth * 0.85);
            add('reeds', { x, y: this.heightAt(x, cz), z: cz, rot: rng.float(0, 6.28), scale: rng.float(0.8, 1.2) });
          }
        }
      }
    }

    const mat = UNIT_MATERIAL();
    this.natureMeshes = [];
    for (const [name, transforms] of byAsset) {
      const asset = this.lib.prop(name);
      if (!asset || !asset.body) continue;
      const mesh = makeStaticInstances(parent, asset.body, mat, transforms, { receiveShadow: true });
      if (mesh) this.natureMeshes.push(mesh);
    }
  }

  // Keep scenery out of the space settlements occupy.
  _nearLocation(x, z, r) {
    if (!this._locPositions) return false;
    for (const p of this._locPositions) {
      if (dist(x, z, p.x, p.y) < r) return true;
    }
    return false;
  }

  // ---- indicators: selection, capture progress, ownership banners

  _buildIndicators() {
    this.selRing = new THREE.Mesh(
      new THREE.RingGeometry(26, 34, 32),
      new THREE.MeshBasicMaterial({ color: 0xd8b464, transparent: true, opacity: 0.9, side: THREE.DoubleSide }),
    );
    this.selRing.rotation.x = -Math.PI / 2;
    this.selRing.visible = false;
    this.dynamic.add(this.selRing);

    this.captureRing = new THREE.Mesh(
      new THREE.RingGeometry(64, 76, 48, 1, 0, 0.1),
      new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.85, side: THREE.DoubleSide }),
    );
    this.captureRing.rotation.x = -Math.PI / 2;
    this.captureRing.visible = false;
    this.dynamic.add(this.captureRing);

    this.destMarker = new THREE.Mesh(
      new THREE.RingGeometry(14, 19, 24),
      new THREE.MeshBasicMaterial({ color: 0xd8b464, transparent: true, opacity: 0.7, side: THREE.DoubleSide }),
    );
    this.destMarker.rotation.x = -Math.PI / 2;
    this.destMarker.visible = false;
    this.dynamic.add(this.destMarker);

    // Ownership discs under each settlement, tinted by faction.
    this.ownerDiscs = new Map();
  }

  ownerDisc(loc) {
    let disc = this.ownerDiscs.get(loc.key);
    if (!disc) {
      disc = new THREE.Mesh(
        new THREE.RingGeometry(104, 112, 44),
        new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.35, side: THREE.DoubleSide }),
      );
      disc.rotation.x = -Math.PI / 2;
      this.dynamic.add(disc);
      this.ownerDiscs.set(loc.key, disc);
    }
    return disc;
  }

  /** Per-frame: armies, banners and indicators. */
  update(campaign, selectedArmy, time) {
    if (!this._built) return;

    const unitDraws = [];
    for (const army of campaign.armies) {
      const spotted = army.faction === 'player' || isSpotted(campaign, army.x, army.y);
      const fit = fitForDuty(army.soldiers);
      if (fit.length === 0) continue;
      const facing = army.dest
        ? Math.atan2(army.dest.y - army.y, army.dest.x - army.x)
        : 0;
      const moving = !!army.dest;
      if (!spotted) {
        // Unidentified column: a few generic figures, no strength given away.
        for (let i = 0; i < 3; i++) {
          unitDraws.push({
            type: 'levy', faction: 'neutral',
            x: army.x + (i - 1) * 16, y: army.y + (i % 2) * 14,
            facing, moving, phase: i * 2.1, scale: 1,
          });
        }
        continue;
      }
      // Draw a marching column that reflects what the army actually contains.
      const types = fit.map(s => s.type);
      const shown = Math.min(6, types.length);
      const slots = [[0, 0], [-24, 12], [24, 14], [-14, -18], [16, -20], [-38, -4]];
      const order = [];
      const hero = types.indexOf('hero');
      if (hero >= 0) order.push('hero');
      for (const t of ['boilerlancer', 'rider', 'pressurebow', 'shieldman', 'spearman', 'bowman', 'levy']) {
        if (order.length >= shown) break;
        if (types.includes(t)) order.push(t);
      }
      while (order.length < shown) order.push(types[order.length % types.length]);
      order.forEach((t, i) => {
        unitDraws.push({
          type: t, faction: army.faction,
          x: army.x + slots[i % 6][0], y: army.y + slots[i % 6][1],
          facing, moving, phase: i * 1.7, scale: 1,
        });
      });
    }

    this.units.update(unitDraws, (x, y) => this.heightAt(x, y), time);

    // ownership rings
    for (const loc of campaign.locations) {
      const disc = this.ownerDisc(loc);
      const fac = FACTIONS[loc.owner] || FACTIONS.neutral;
      disc.material.color.set(fac.color);
      disc.material.opacity = loc.owner === 'neutral' ? 0.12 : 0.34;
      disc.position.set(loc.x, this.heightAt(loc.x, loc.y) + 1.2, loc.y);
      const r = loc.type === 'keep' ? 1.7 : loc.type === 'fort' ? 1.35 : 1;
      disc.scale.setScalar(r);
    }

    // selection + destination
    if (selectedArmy) {
      const y = this.heightAt(selectedArmy.x, selectedArmy.y);
      this.selRing.visible = true;
      this.selRing.position.set(selectedArmy.x, y + 1.6, selectedArmy.y);
      const pulse = 1 + Math.sin(time * 4) * 0.05;
      this.selRing.scale.setScalar(pulse);
      if (selectedArmy.dest) {
        this.destMarker.visible = true;
        this.destMarker.position.set(
          selectedArmy.dest.x,
          this.heightAt(selectedArmy.dest.x, selectedArmy.dest.y) + 1.6,
          selectedArmy.dest.y,
        );
      } else this.destMarker.visible = false;
    } else {
      this.selRing.visible = false;
      this.destMarker.visible = false;
    }

    // capture progress
    const capturing = campaign.locations.find(l => l.captureProgress > 0 && l.capturingFaction);
    if (capturing) {
      this.captureRing.visible = true;
      this.captureRing.geometry.dispose();
      this.captureRing.geometry = new THREE.RingGeometry(
        64, 78, 48, 1, Math.PI / 2, -capturing.captureProgress * Math.PI * 2);
      this.captureRing.material.color.set(FACTIONS[capturing.capturingFaction].color);
      this.captureRing.position.set(
        capturing.x, this.heightAt(capturing.x, capturing.y) + 2.2, capturing.y);
    } else {
      this.captureRing.visible = false;
    }
  }

  dispose() {
    this.units.dispose();
  }
}
