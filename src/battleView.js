// The tactical battlefield — the same world, closer.
//
// Same terrain system, same kits, same soldiers as the strategic map, so a
// battle reads as zooming into STEAMWARD rather than entering another game.

import * as THREE from '../vendor/three/three.module.min.js';
import { flatMaterial } from './gfx.js';
import { buildBattleHeightfield, buildTerrainMesh, buildRoadMesh, buildWaterMesh, WATER_LEVEL } from './terrain.js';
import { makeStaticInstances, UNIT_MATERIAL } from './models.js';
import { UnitRenderer } from './unitView.js';
import { FACTIONS } from './data.js';
import { makeRng } from './util.js';

// Which kit pieces dress each battlefield context.
const SCENERY = {
  open: { trees: 26, rocks: 14, bushes: 18 },
  forest: { trees: 150, rocks: 10, bushes: 40 },
  bridge: { trees: 34, rocks: 16, bushes: 14 },
  settlement: { trees: 16, rocks: 6, bushes: 10 },
  industrial: { trees: 8, rocks: 14, bushes: 4 },
  fort: { trees: 22, rocks: 12, bushes: 12 },
};

export class BattleView {
  constructor(gfx, library) {
    this.gfx = gfx;
    this.lib = library;
    this.units = new UnitRenderer(gfx.scene, library);
    this.hf = null;
    this.projectiles = null;
    this.particles = [];
    this._built = false;
  }

  heightAt(x, y) { return this.hf ? this.hf.heightAt(x, y) : 0; }

  build(battle) {
    const gfx = this.gfx;
    gfx.clear();
    const kind = battle.terrain.kind;
    // Industrial fields sit under a dirtier sky; woods are hazier.
    gfx.setSkyMood({
      background: kind === 'industrial' ? 0x8f8b80 : kind === 'forest' ? 0x8aa596 : 0x9ab4c2,
      haze: kind === 'industrial' ? 1.5 : 0.7,
      sunIntensity: kind === 'industrial' ? 0.9 : 1.05,
      skyLight: kind === 'forest' ? 0.4 : 0.46,
    });

    this.hf = buildBattleHeightfield(kind, battle.ctx.seed | 0, battle.w, battle.h);

    const g = new THREE.Group();
    this.group = g;
    gfx.scene.add(g);

    const terrain = new THREE.Mesh(
      buildTerrainMesh(this.hf),
      flatMaterial(0xffffff, { vertexColors: true, side: THREE.DoubleSide }),
    );
    terrain.receiveShadow = true;
    g.add(terrain);
    gfx.setPickables([terrain]);
    this.terrain = terrain;

    if (kind === 'bridge' || kind === 'settlement') {
      const lineY = battle.h / 2;
      const road = new THREE.Mesh(
        buildRoadMesh(this.hf, [[{ x: 0, y: lineY }, { x: battle.w, y: lineY }]], 76),
        flatMaterial(0xffffff, { vertexColors: true, side: THREE.DoubleSide }),
      );
      road.receiveShadow = true;
      g.add(road);
    }

    if (kind === 'bridge') {
      const waterGeo = buildWaterMesh(this.hf);
      if (waterGeo) {
        g.add(new THREE.Mesh(waterGeo, new THREE.MeshLambertMaterial({
          color: 0x2c5568, transparent: true, opacity: 0.88,
        })));
      }
      // the crossing itself
      const deck = new THREE.Mesh(new THREE.BoxGeometry(300, 8, 120), flatMaterial(0x5a4126));
      deck.position.set(battle.w / 2, 26, battle.h / 2);
      deck.castShadow = true; deck.receiveShadow = true;
      g.add(deck);
      for (const side of [-1, 1]) {
        const rail = new THREE.Mesh(new THREE.BoxGeometry(300, 14, 6), flatMaterial(0x6b5133));
        rail.position.set(battle.w / 2, 37, battle.h / 2 + side * 57);
        rail.castShadow = true;
        g.add(rail);
      }
    }

    this._dressBattlefield(g, battle, kind);
    gfx.setBounds(battle.w, battle.h);
    this._buildIndicators();
    this._built = true;
  }

  _place(parent, name, x, z, rot = 0, scale = 1) {
    if (!this.lib.hasProp(name)) return false;
    const asset = this.lib.prop(name);
    const mesh = new THREE.Mesh(asset.body, UNIT_MATERIAL());
    mesh.position.set(x, this.heightAt(x, z), z);
    mesh.rotation.y = rot;
    mesh.scale.setScalar(scale);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    parent.add(mesh);
    if (asset.emissive) {
      const em = new THREE.Mesh(asset.emissive, new THREE.MeshBasicMaterial({ vertexColors: true }));
      em.position.copy(mesh.position);
      em.rotation.y = rot;
      em.scale.setScalar(scale);
      parent.add(em);
    }
    return true;
  }

  _dressBattlefield(parent, battle, kind) {
    const rng = makeRng((battle.ctx.seed | 0) + 5150);
    const W = battle.w, H = battle.h;
    const pines = ['tree_pine_a', 'tree_pine_b', 'tree_pine_c'].filter(n => this.lib.hasProp(n));
    const broads = ['tree_broad_a', 'tree_broad_b', 'tree_broad_c'].filter(n => this.lib.hasProp(n));
    const rocks = ['rock_a', 'rock_b', 'rock_c'].filter(n => this.lib.hasProp(n));
    const bushes = ['bush_a', 'bush_b'].filter(n => this.lib.hasProp(n));
    const plan = SCENERY[kind] || SCENERY.open;
    const byAsset = new Map();
    const add = (name, t) => {
      if (!name) return;
      if (!byAsset.has(name)) byAsset.set(name, []);
      byAsset.get(name).push(t);
    };

    // The simulation's obstacle list is authoritative: scenery is placed to
    // match it exactly, so what blocks a soldier is what you can see.
    for (const c of battle.terrain.circles) {
      let name = null;
      if (c.kind === 'tree') name = rng.chance(0.6) ? rng.pick(pines) : rng.pick(broads);
      else if (c.kind === 'rock') name = rng.pick(rocks);
      else if (c.kind === 'boiler') name = 'boiler_large';
      else if (c.kind === 'spoil') name = 'coal_pile';
      if (!name || !this.lib.hasProp(name)) continue;
      const size = this.lib.propSize(name);
      const want = c.r * 2;
      const scale = size.w > 1 ? Math.max(0.5, Math.min(2.2, want / size.w)) : 1;
      add(name, { x: c.x, y: this.heightAt(c.x, c.y), z: c.y, rot: rng.float(0, 6.28), scale });
    }

    // Wall pieces are authored with their outer face (batter, loops, oversail)
    // toward the enemy; which way that is depends on which side the defender
    // holds, so read it off the wall rects themselves.
    const wallXs = battle.terrain.rects.filter(r => r.kind === 'wall').map(r => r.x + r.w / 2);
    const defenderRight = wallXs.length > 0 && wallXs[0] > W / 2;
    const wallRot = defenderRight ? -Math.PI / 2 : Math.PI / 2;

    for (const r of battle.terrain.rects) {
      const cx = r.x + r.w / 2, cz = r.y + r.h / 2;
      if (r.kind === 'house') this._place(parent, rng.chance(0.5) ? 'cottage_a' : 'cottage_b', cx, cz, rng.pick([0, Math.PI / 2, Math.PI]));
      else if (r.kind === 'shed') this._place(parent, 'workshop_small', cx, cz, rng.float(0, 6.28));
      else if (r.kind === 'cart') this._place(parent, 'cart', cx, cz, rng.float(0, 6.28));
      else if (r.kind === 'tower') this._place(parent, 'tower_square', cx, cz, wallRot);
      else if (r.kind === 'wall') {
        // tile wall segments along the run so the curtain reads as one mass
        const seg = this.lib.hasProp('wall_segment') ? this.lib.propSize('wall_segment').w : 60;
        const n = Math.max(1, Math.round(r.h / seg));
        for (let i = 0; i < n; i++) {
          const z = r.y + (i + 0.5) * (r.h / n);
          this._place(parent, 'wall_segment', cx, z, wallRot);
        }
      }
    }

    // The gate is a passage the sim keeps open, so it can't wear the gatehouse
    // model (whose arch is a 22-unit carriageway). Instead: a tower over each
    // blocked wall end squares off the jambs, banners fly just inside, and
    // siege ladders lean against the outer face away from the gate lane —
    // nothing solid-looking stands on walkable ground.
    for (const d of (battle.terrain.decals || [])) {
      if (d.kind !== 'gate') continue;
      const half = (d.h || 150) / 2;
      const ts = this.lib.hasProp('tower_square') ? this.lib.propSize('tower_square').d : 51;
      const inw = defenderRight ? 1 : -1;
      // One gate tower on the north jamb. At this camera anything tall south
      // of the opening stands in front of it and visually plugs the gap, so
      // the south jamb gets a squared wall end instead, and the garrison's
      // colours fly inside the bailey flanking the gate road — never in the
      // opening itself.
      this._place(parent, 'tower_square', d.x, d.y - (half + ts / 2), wallRot);
      this._place(parent, 'wall_corner', d.x, d.y + half + 24, wallRot);
      for (const s of [-1, 1]) {
        this._place(parent, 'banner_pole', d.x + inw * 70, d.y + s * 64, wallRot);
        this._place(parent, 'siege_ladder', d.x - inw * 20, d.y + s * (half + 165), wallRot);
      }
    }

    if (kind === 'fort' && wallXs.length > 0) {
      // The bailey behind the wall is somebody's post, not bare turf. All of
      // it sits in the quiet margins behind the curtain, off the gate lane.
      const wx = wallXs[0];
      const inw = defenderRight ? 1 : -1;
      this._place(parent, 'tent_a', wx + inw * 96, 210, 0.35);
      this._place(parent, 'tent_b', wx + inw * 152, 264, -0.2);
      this._place(parent, 'weapon_rack', wx + inw * 62, 296, wallRot);
      this._place(parent, 'cart', wx + inw * 88, H - 190, 0.8);
      this._place(parent, 'rubble_pile', wx + inw * 54, H - 252, 0.5);
      this._place(parent, 'tent_a', wx + inw * 142, H - 232, 2.7);
    }

    // Ambient scenery in the margins, away from the fighting lanes.
    const scatter = (names, count, opts = {}) => {
      if (names.length === 0) return;
      for (let i = 0; i < count; i++) {
        const x = rng.float(60, W - 60), z = rng.float(60, H - 60);
        if (!opts.anywhere && x > W * 0.18 && x < W * 0.82 && Math.abs(z - H / 2) < 260) continue;
        if (kind === 'bridge' && Math.abs(x - W / 2) < 230) continue;
        add(rng.pick(names), {
          x, y: this.heightAt(x, z), z,
          rot: rng.float(0, 6.28), scale: rng.float(0.75, 1.3),
        });
      }
    };
    scatter(kind === 'forest' ? [...pines, ...broads] : pines, plan.trees, { anywhere: kind === 'forest' });
    scatter(rocks, plan.rocks, { anywhere: true });
    scatter(bushes, plan.bushes, { anywhere: true });

    if (kind === 'industrial') {
      for (let i = 0; i < 3; i++) {
        const x = rng.float(W * 0.25, W * 0.75), z = rng.float(120, H - 120);
        this._place(parent, rng.chance(0.5) ? 'workshop_small' : 'coal_hopper', x, z, rng.float(0, 6.28));
      }
      this._place(parent, 'steam_crane', W * 0.5, H * 0.22, 0.4);
      for (let i = 0; i < 4; i++) {
        const x = rng.float(W * 0.3, W * 0.7);
        add('pipe_run_straight', { x, y: this.heightAt(x, H * 0.8), z: H * 0.8, rot: 0, scale: 1 });
      }
    }
    if (kind === 'settlement') {
      for (let i = 0; i < 5; i++) {
        const x = rng.float(W * 0.25, W * 0.75), z = rng.pick([H * 0.3, H * 0.78]) + rng.float(-40, 40);
        add('fence_segment', { x, y: this.heightAt(x, z), z, rot: 0, scale: 1 });
      }
      this._place(parent, 'well', W * 0.5, H * 0.42, 0);
    }

    const mat = UNIT_MATERIAL();
    for (const [name, transforms] of byAsset) {
      const asset = this.lib.prop(name);
      if (!asset || !asset.body) continue;
      makeStaticInstances(parent, asset.body, mat, transforms, { receiveShadow: true });
    }
  }

  _buildIndicators() {
    const gfx = this.gfx;
    // Selection rings drawn as one instanced ring mesh.
    this.ringGeo = new THREE.RingGeometry(9, 12, 20).rotateX(-Math.PI / 2);
    this.ringMat = new THREE.MeshBasicMaterial({
      color: 0xd8b464, transparent: true, opacity: 0.95, side: THREE.DoubleSide, depthWrite: false,
    });
    this.rings = new THREE.InstancedMesh(this.ringGeo, this.ringMat, 128);
    this.rings.frustumCulled = false;
    this.rings.count = 0;
    gfx.scene.add(this.rings);

    // Projectiles: small instanced shafts that really travel through the air.
    this.projGeo = new THREE.BoxGeometry(1.6, 1.6, 15);
    this.projMat = new THREE.MeshLambertMaterial({ color: 0xd8d2c4, flatShading: true });
    this.projectiles = new THREE.InstancedMesh(this.projGeo, this.projMat, 256);
    this.projectiles.frustumCulled = false;
    this.projectiles.count = 0;
    gfx.scene.add(this.projectiles);

    this.pierceMat = new THREE.MeshLambertMaterial({ color: 0xc9a959, flatShading: true });
    this.piercers = new THREE.InstancedMesh(new THREE.BoxGeometry(2.4, 2.4, 20), this.pierceMat, 128);
    this.piercers.frustumCulled = false;
    this.piercers.count = 0;
    gfx.scene.add(this.piercers);

    // Steam and dust: instanced quads that expand and fade.
    this.puffGeo = new THREE.SphereGeometry(1, 6, 4);
    this.puffMat = new THREE.MeshBasicMaterial({ color: 0xe4e4de, transparent: true, opacity: 0.55 });
    this.puffs = new THREE.InstancedMesh(this.puffGeo, this.puffMat, 400);
    this.puffs.frustumCulled = false;
    this.puffs.count = 0;
    gfx.scene.add(this.puffs);

    this._m = new THREE.Matrix4();
    this._q = new THREE.Quaternion();
    this._v = new THREE.Vector3();
    this._s = new THREE.Vector3();
  }

  spawnPuff(x, y, z, size, life, color, vel) {
    if (this.particles.length > 360) return;
    this.particles.push({
      x, y, z, size, life, maxLife: life,
      vx: vel ? vel[0] : 0, vy: vel ? vel[1] : 22, vz: vel ? vel[2] : 0,
      color: color || 0xe4e4de,
    });
  }

  consumeEffects(battle) {
    for (const e of battle.effects) {
      const gy = this.heightAt(e.x, e.y);
      switch (e.type) {
        case 'steamshot':
          for (let i = 0; i < 5; i++) {
            this.spawnPuff(e.x + rand(4), gy + 12, e.y + rand(4), 3.2, 0.8, 0xe8e8e2,
              [rand(16), 20 + Math.random() * 14, rand(16)]);
          }
          break;
        case 'charge':
          for (let i = 0; i < 6; i++) {
            this.spawnPuff(e.x + rand(8), gy + 2, e.y + rand(8), 4.5, 0.55, 0xa2917a,
              [rand(24), 10, rand(24)]);
          }
          break;
        case 'death':
          for (let i = 0; i < 3; i++) {
            this.spawnPuff(e.x + rand(5), gy + 3, e.y + rand(5), 3.6, 0.5, 0x8b7f68,
              [rand(12), 8, rand(12)]);
          }
          break;
        case 'hit':
          this.spawnPuff(e.x, gy + 10, e.y, 1.8, 0.25, 0x9a3b28, [rand(14), 12, rand(14)]);
          break;
        case 'rally':
          for (let i = 0; i < 10; i++) {
            const a = i / 10 * Math.PI * 2;
            this.spawnPuff(e.x + Math.cos(a) * 30, gy + 6, e.y + Math.sin(a) * 30, 3, 0.7, 0xd8b464,
              [Math.cos(a) * 30, 16, Math.sin(a) * 30]);
          }
          break;
      }
    }
  }

  update(battle, dt, time) {
    if (!this._built) return;

    // ---- soldiers
    const draws = [];
    for (const u of battle.units) {
      if (u.state === 'fled') continue;
      if (u.state === 'dead' && (u.deadT || 0) > 22) continue;
      draws.push({
        type: u.type, faction: u.player ? 'player' : (battle.ctx.enemyFaction || 'bandit'),
        x: u.x, y: u.y, facing: u.facing,
        moving: u.state === 'moving' || u.state === 'routing',
        routing: u.state === 'routing',
        attackPhase: u.meleeCd > 0 && u.state === 'fighting'
          ? Math.max(0, 1 - u.meleeCd / Math.max(0.001, u.def.meleeRate)) : 0,
        deadT: u.state === 'dead' ? (u.deadT || 0) : undefined,
        phase: (u.uid % 13) * 0.6,
        scale: 1,
      });
    }
    this.units.update(draws, (x, y) => this.heightAt(x, y), time);

    // ---- selection rings
    let n = 0;
    for (const u of battle.units) {
      if (!battle.selection.has(u.uid) || u.state === 'dead' || u.state === 'fled') continue;
      if (n >= 128) break;
      const r = (u.def.radius + 4) / 10;
      this._v.set(u.x, this.heightAt(u.x, u.y) + 1.2, u.y);
      this._s.set(r, 1, r);
      this._m.compose(this._v, new THREE.Quaternion(), this._s);
      this.rings.setMatrixAt(n++, this._m);
    }
    this.rings.count = n;
    this.rings.instanceMatrix.needsUpdate = true;

    // ---- projectiles arc through real space
    let pi = 0, pp = 0;
    for (const p of battle.projectiles) {
      const k = Math.min(1, p.t / p.dur);
      const gy = this.heightAt(p.x, p.y);
      const y = gy + 16 + (p.z || 0);
      const dx = p.tx - p.sx, dz = p.ty - p.sy;
      const yaw = Math.atan2(dx, dz);
      const climb = Math.atan2((p.arc || 0) * 40 * Math.cos(k * Math.PI), Math.hypot(dx, dz) || 1);
      this._q.setFromEuler(new THREE.Euler(-climb, yaw, 0, 'YXZ'));
      this._v.set(p.x, y, p.y);
      this._s.set(1, 1, 1);
      this._m.compose(this._v, this._q, this._s);
      if (p.pierce) { if (pp < 128) this.piercers.setMatrixAt(pp++, this._m); }
      else if (pi < 256) this.projectiles.setMatrixAt(pi++, this._m);
    }
    this.projectiles.count = pi;
    this.projectiles.instanceMatrix.needsUpdate = true;
    this.piercers.count = pp;
    this.piercers.instanceMatrix.needsUpdate = true;

    // ---- particles
    let qi = 0;
    for (let i = this.particles.length - 1; i >= 0; i--) {
      const pt = this.particles[i];
      pt.life -= dt;
      if (pt.life <= 0) { this.particles.splice(i, 1); continue; }
      pt.x += pt.vx * dt; pt.y += pt.vy * dt; pt.z += pt.vz * dt;
      pt.vy -= 12 * dt;
      const k = pt.life / pt.maxLife;
      if (qi < 400) {
        const s = pt.size * (1.8 - k);
        this._v.set(pt.x, pt.y, pt.z);
        this._s.set(s, s, s);
        this._m.compose(this._v, new THREE.Quaternion(), this._s);
        this.puffs.setMatrixAt(qi++, this._m);
      }
    }
    this.puffs.count = qi;
    this.puffs.instanceMatrix.needsUpdate = true;
    this.puffMat.opacity = 0.5;
  }

  dispose() {
    this.units.dispose();
    this.particles.length = 0;
  }
}

const rand = (s) => (Math.random() - 0.5) * 2 * s;
