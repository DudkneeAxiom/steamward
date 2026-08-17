// Asset loading and instancing.
//
// Blender kits export GLB files whose colour lives in materials. For a browser
// RTS that is the wrong shape: hundreds of small meshes with a dozen materials
// each would mean thousands of draw calls. So at load time every asset is
// flattened — material colours are baked into vertex colours and the pieces are
// merged — leaving ONE geometry (plus an optional emissive geometry) per asset.
// Scenery then draws as a single InstancedMesh per asset type, and soldiers as
// one InstancedMesh per animated body part.

import * as THREE from '../vendor/three/three.module.min.js';
import { GLTFLoader } from '../vendor/three/loaders/GLTFLoader.js';
import { mergeGeometries } from '../vendor/three/utils/BufferGeometryUtils.js';

const loader = new GLTFLoader();

// Parts the runtime animates. Anything else is welded into the body.
export const ANIM_PARTS = ['leg_l', 'leg_r', 'arm_l', 'arm_r', 'weapon',
                           'hleg_fl', 'hleg_fr', 'hleg_bl', 'hleg_br'];

const FACTION_CLOTH = {
  player: 0x3f7a4e,
  falkmoor: 0x9c3327,
  brennan: 0x3f628c,
  bandit: 0x6b5a3a,
  neutral: 0x7c7768,
};

export const factionCloth = (f) => FACTION_CLOTH[f] ?? FACTION_CLOTH.neutral;

function isClothMaterial(mat) {
  return !!mat && typeof mat.name === 'string' && mat.name.toLowerCase().startsWith('cloth');
}

function isEmissive(mat) {
  if (!mat || !mat.emissive) return false;
  const e = mat.emissive;
  return (e.r + e.g + e.b) > 0.02 && (mat.emissiveIntensity ?? 1) > 0.01;
}

// Bake a mesh's material colour into per-vertex colours, in the local frame of
// `relativeTo` so pieces can be merged.
function bakedGeometry(mesh, relativeTo, clothColor) {
  const geo = mesh.geometry.clone();
  geo.deleteAttribute('uv');
  geo.deleteAttribute('uv1');
  geo.deleteAttribute('tangent');
  if (geo.index) geo.toNonIndexed && (geo.index = geo.index); // keep as-is; merge handles it

  mesh.updateWorldMatrix(true, false);
  const m = new THREE.Matrix4();
  if (relativeTo) {
    relativeTo.updateWorldMatrix(true, false);
    m.copy(relativeTo.matrixWorld).invert().multiply(mesh.matrixWorld);
  } else {
    m.copy(mesh.matrixWorld);
  }
  geo.applyMatrix4(m);

  const mat = Array.isArray(mesh.material) ? mesh.material[0] : mesh.material;
  const col = new THREE.Color(0xcccccc);
  if (mat && mat.color) col.copy(mat.color);
  if (isClothMaterial(mat) && clothColor !== undefined) col.setHex(clothColor);

  const n = geo.attributes.position.count;
  const arr = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    arr[i * 3] = col.r; arr[i * 3 + 1] = col.g; arr[i * 3 + 2] = col.b;
  }
  geo.setAttribute('color', new THREE.BufferAttribute(arr, 3));
  return geo;
}

function mergeAll(list) {
  const clean = list.filter(Boolean);
  if (clean.length === 0) return null;
  if (clean.length === 1) return clean[0];
  const merged = mergeGeometries(clean, false);
  clean.forEach(g => g.dispose());
  return merged;
}

/**
 * Flatten a loaded GLB into renderable geometry.
 * Returns { body, emissive, parts: {name: {geometry, pivot}}, size }
 */
export function flattenAsset(gltfScene, opts = {}) {
  const clothColor = opts.clothColor;
  const partNodes = new Map();
  if (opts.animated) {
    gltfScene.traverse((o) => {
      if (ANIM_PARTS.includes(o.name)) partNodes.set(o.name, o);
    });
  }

  const inPart = (obj) => {
    let o = obj;
    while (o) {
      if (partNodes.has(o.name)) return partNodes.get(o.name);
      o = o.parent;
    }
    return null;
  };

  const bodyGeos = [], emissiveGeos = [];
  const partGeos = new Map();

  gltfScene.updateWorldMatrix(true, true);
  gltfScene.traverse((o) => {
    if (!o.isMesh) return;
    const mat = Array.isArray(o.material) ? o.material[0] : o.material;
    const owner = inPart(o);
    const geo = bakedGeometry(o, owner || gltfScene, clothColor);
    if (isEmissive(mat) && !owner) emissiveGeos.push(geo);
    else if (owner) {
      if (!partGeos.has(owner.name)) partGeos.set(owner.name, []);
      partGeos.get(owner.name).push(geo);
    } else bodyGeos.push(geo);
  });

  const parts = {};
  for (const [name, geos] of partGeos) {
    const node = partNodes.get(name);
    node.updateWorldMatrix(true, false);
    // Part geometry is baked in the node's own frame, so replaying the node's
    // matrix puts it back — and rotating before that matrix swings the part
    // around its pivot, which is exactly what animation needs.
    parts[name] = {
      geometry: mergeAll(geos),
      matrix: node.matrixWorld.clone(),
      pivot: new THREE.Vector3().setFromMatrixPosition(node.matrixWorld),
    };
  }

  const body = mergeAll(bodyGeos);
  const size = new THREE.Vector3();
  if (body) {
    body.computeBoundingBox();
    body.boundingBox.getSize(size);
  }
  return { body, emissive: mergeAll(emissiveGeos), parts, size };
}

export function loadGLB(url) {
  return new Promise((resolve, reject) => {
    loader.load(url, (g) => resolve(g.scene), undefined,
      (e) => reject(new Error(`failed to load ${url}: ${e && e.message ? e.message : e}`)));
  });
}

/**
 * The asset library: loads a manifest, flattens everything, and hands out
 * geometry. Missing assets are reported once and skipped rather than throwing,
 * so a half-built kit cannot take the game down.
 */
export class AssetLibrary {
  constructor() {
    this.props = new Map();      // name -> { body, emissive, size }
    this.units = new Map();      // `${type}:${faction}` -> { body, emissive, parts, size }
    this.missing = new Set();
    this.manifest = null;
  }

  async load(manifestUrl, factions) {
    const res = await fetch(manifestUrl);
    if (!res.ok) throw new Error(`no asset manifest at ${manifestUrl}`);
    this.manifest = await res.json();
    const base = manifestUrl.replace(/[^/]*$/, '');

    const propEntries = [];
    for (const [category, names] of Object.entries(this.manifest.categories || {})) {
      if (category === 'units') continue;
      for (const name of names) propEntries.push([name, `${base}${category}/${name}.glb`]);
    }

    await Promise.all(propEntries.map(async ([name, url]) => {
      try {
        const scene = await loadGLB(url);
        this.props.set(name, flattenAsset(scene));
      } catch (e) {
        this.missing.add(name);
        console.warn(e.message);
      }
    }));

    const unitNames = (this.manifest.categories || {}).units || [];
    await Promise.all(unitNames.map(async (name) => {
      let scene;
      try {
        scene = await loadGLB(`${base}units/${name}.glb`);
      } catch (e) {
        this.missing.add(name);
        console.warn(e.message);
        return;
      }
      for (const f of factions) {
        // one flatten per faction so cloth colour is baked, keeping every
        // soldier on a single shared material
        const clone = scene.clone(true);
        this.units.set(`${name}:${f}`, flattenAsset(clone, { animated: true, clothColor: factionCloth(f) }));
      }
    }));
    return this;
  }

  prop(name) { return this.props.get(name) || null; }
  unit(type, faction) { return this.units.get(`${type}:${faction}`) || null; }
  hasProp(name) { return this.props.has(name); }
  propSize(name) {
    const p = this.props.get(name);
    return p ? { w: p.size.x, h: p.size.y, d: p.size.z } : { w: 20, h: 20, d: 20 };
  }
}

// ---------------------------------------------------------------- instancing

export const UNIT_MATERIAL = () => new THREE.MeshLambertMaterial({
  vertexColors: true, flatShading: true,
});

/**
 * A pool of InstancedMeshes for one geometry. Instances are rewritten each
 * frame; capacity grows in chunks so we are not reallocating constantly.
 */
export class InstancePool {
  constructor(scene, geometry, material, { castShadow = true, receiveShadow = false } = {}) {
    this.scene = scene;
    this.geometry = geometry;
    this.material = material;
    this.castShadow = castShadow;
    this.receiveShadow = receiveShadow;
    this.mesh = null;
    this.capacity = 0;
    this.count = 0;
    this._m = new THREE.Matrix4();
  }

  _ensure(n) {
    if (this.mesh && n <= this.capacity) return;
    if (this.mesh) {
      this.scene.remove(this.mesh);
      this.mesh.dispose();
    }
    this.capacity = Math.max(16, Math.ceil(n * 1.5));
    this.mesh = new THREE.InstancedMesh(this.geometry, this.material, this.capacity);
    this.mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.mesh.castShadow = this.castShadow;
    this.mesh.receiveShadow = this.receiveShadow;
    this.mesh.frustumCulled = false;
    this.scene.add(this.mesh);
  }

  begin(expected) {
    this._ensure(expected);
    this.count = 0;
  }

  push(matrix) {
    if (this.count >= this.capacity) return;
    this.mesh.setMatrixAt(this.count++, matrix);
  }

  end() {
    if (!this.mesh) return;
    this.mesh.count = this.count;
    this.mesh.instanceMatrix.needsUpdate = true;
  }

  dispose() {
    if (!this.mesh) return;
    this.scene.remove(this.mesh);
    this.mesh.dispose();
    this.mesh = null;
    this.capacity = 0;
  }
}

/** Static scenery: written once, then left alone on the GPU. */
export function makeStaticInstances(scene, geometry, material, transforms, opts = {}) {
  if (!geometry || transforms.length === 0) return null;
  const mesh = new THREE.InstancedMesh(geometry, material, transforms.length);
  const m = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  const s = new THREE.Vector3();
  const p = new THREE.Vector3();
  transforms.forEach((t, i) => {
    p.set(t.x, t.y, t.z);
    q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), t.rot || 0);
    const sc = t.scale || 1;
    s.set(sc * (t.scaleX || 1), sc * (t.scaleY || 1), sc * (t.scaleZ || 1));
    m.compose(p, q, s);
    mesh.setMatrixAt(i, m);
  });
  mesh.instanceMatrix.needsUpdate = true;
  mesh.castShadow = opts.castShadow !== false;
  mesh.receiveShadow = !!opts.receiveShadow;
  scene.add(mesh);
  return mesh;
}
