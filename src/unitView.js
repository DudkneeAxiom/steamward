// Soldiers on screen.
//
// Every unit is drawn from instanced geometry: one InstancedMesh per
// (type, faction, body part). Animation is procedural — legs and arms are
// separate parts with their own pivots, so a walk cycle is a couple of sine
// waves rather than a skeleton. At RTS distance that reads perfectly and costs
// almost nothing, which is what lets a 40v40 battle run.

import * as THREE from '../vendor/three/three.module.min.js';
import { InstancePool, UNIT_MATERIAL, ANIM_PARTS } from './models.js';

// Soldiers are drawn slightly larger than their real 1.8m so a formation reads
// as a formation at RTS distance — the classic miniature-wargame cheat.
export const UNIT_SCALE = 1.4;

const LEG_PARTS = ['leg_l', 'leg_r'];
const ARM_PARTS = ['arm_l', 'arm_r'];
const HORSE_LEGS = ['hleg_fl', 'hleg_fr', 'hleg_bl', 'hleg_br'];

export class UnitRenderer {
  constructor(scene, library) {
    this.scene = scene;
    this.lib = library;
    this.material = UNIT_MATERIAL();
    this.pools = new Map();        // key -> InstancePool
    this.used = new Set();
    this._root = new THREE.Matrix4();
    this._local = new THREE.Matrix4();
    this._rot = new THREE.Matrix4();
    this._out = new THREE.Matrix4();
    this._pos = new THREE.Vector3();
    this._quat = new THREE.Quaternion();
    this._scale = new THREE.Vector3(1, 1, 1);
    this._up = new THREE.Vector3(0, 1, 0);
    this._tilt = new THREE.Vector3(1, 0, 0);
  }

  _pool(key, geometry) {
    let p = this.pools.get(key);
    if (!p) {
      p = new InstancePool(this.scene, geometry, this.material, { castShadow: true });
      this.pools.set(key, p);
    }
    return p;
  }

  /**
   * units: [{ type, faction, x, y, facing, moving, speed, attackPhase,
   *           deadT, routing, scale }]
   * heightAt(x, y) -> ground height
   */
  update(units, heightAt, time) {
    // Bucket by (type, faction) so each pool is filled in one pass.
    const buckets = new Map();
    for (const u of units) {
      const key = `${u.type}:${u.faction}`;
      let arr = buckets.get(key);
      if (!arr) { arr = []; buckets.set(key, arr); }
      arr.push(u);
    }

    this.used.clear();

    for (const [key, list] of buckets) {
      const [type, faction] = key.split(':');
      const asset = this.lib.unit(type, faction);
      if (!asset) continue;

      const bodyPool = asset.body ? this._pool(`${key}:body`, asset.body) : null;
      if (bodyPool) { bodyPool.begin(list.length); this.used.add(`${key}:body`); }
      const emisPool = asset.emissive ? this._pool(`${key}:emis`, asset.emissive) : null;
      if (emisPool) { emisPool.begin(list.length); this.used.add(`${key}:emis`); }

      const partPools = {};
      for (const name of Object.keys(asset.parts)) {
        const pk = `${key}:${name}`;
        const pool = this._pool(pk, asset.parts[name].geometry);
        pool.begin(list.length);
        partPools[name] = pool;
        this.used.add(pk);
      }

      for (const u of list) {
        const gy = heightAt(u.x, u.y);
        const scale = (u.scale || 1) * UNIT_SCALE;

        // Root: stand on the ground, face the heading. Dead soldiers tip over
        // and settle rather than vanishing.
        this._pos.set(u.x, gy, u.y);
        this._quat.setFromAxisAngle(this._up, -u.facing);
        if (u.deadT !== undefined && u.deadT >= 0) {
          const fall = Math.min(1, u.deadT / 0.55);
          const tip = new THREE.Quaternion().setFromAxisAngle(this._tilt, fall * Math.PI * 0.46);
          this._quat.multiply(tip);
          this._pos.y = gy + 0.6;
        }
        this._scale.set(scale, scale, scale);
        this._root.compose(this._pos, this._quat, this._scale);

        if (bodyPool) bodyPool.push(this._root);
        if (emisPool) emisPool.push(this._root);

        // ---- animation
        const dead = u.deadT !== undefined && u.deadT >= 0;
        const gait = u.moving && !dead ? Math.sin(time * (u.routing ? 15 : 10.5) + u.phase) : 0;
        const idle = dead ? 0 : Math.sin(time * 1.6 + u.phase) * 0.05;
        const swing = gait * (u.routing ? 0.85 : 0.62);
        const attack = dead ? 0 : (u.attackPhase || 0);

        for (const name of Object.keys(asset.parts)) {
          const part = asset.parts[name];
          let angle = 0;
          if (LEG_PARTS.includes(name)) {
            angle = name === 'leg_l' ? swing : -swing;
          } else if (HORSE_LEGS.includes(name)) {
            const back = name.startsWith('hleg_b');
            const left = name.endsWith('l');
            angle = (left ? 1 : -1) * (back ? -1 : 1) * gait * 0.75;
          } else if (ARM_PARTS.includes(name)) {
            // the weapon arm drives the attack; the other counter-swings
            const isWeaponArm = name === 'arm_r';
            angle = isWeaponArm
              ? (-swing * 0.5 + idle) - attack * 1.5
              : (swing * 0.5 + idle);
          } else if (name === 'weapon') {
            angle = -attack * 0.7;
          }
          if (dead) angle *= 0.2;

          this._rot.makeRotationX(angle);
          this._local.copy(part.matrix).multiply(this._rot);
          this._out.multiplyMatrices(this._root, this._local);
          partPools[name].push(this._out);
        }
      }

      if (bodyPool) bodyPool.end();
      if (emisPool) emisPool.end();
      for (const name of Object.keys(partPools)) partPools[name].end();
    }

    // Anything not filled this frame draws zero instances.
    for (const [key, pool] of this.pools) {
      if (!this.used.has(key)) { pool.begin(0); pool.end(); }
    }
  }

  dispose() {
    for (const pool of this.pools.values()) pool.dispose();
    this.pools.clear();
    this.material.dispose();
  }
}
