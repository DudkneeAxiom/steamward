// Renderer core: WebGL scene, the 2.5D diorama camera, lighting and picking.
//
// The camera is orthographic and fixed at a shallow overhead angle, which is
// what sells "miniature you could reach into" rather than "first-person world".
// Gameplay still thinks in flat (x, y); this module owns the third dimension.

import * as THREE from '../vendor/three/three.module.min.js';

export const CAM_ELEV = 42 * Math.PI / 180;   // degrees above the horizon
export const CAM_AZIM = 0;                    // looking due north

export class Gfx {
  constructor(canvas) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({
      canvas, antialias: true, powerPreference: 'high-performance',
    });
    // Software rasterisers (headless CI, machines without a GPU) cannot afford
    // soft shadows at full resolution; detect and scale the settings back
    // rather than crawling.
    const dbg = this.renderer.getContext().getExtension('WEBGL_debug_renderer_info');
    const gpuName = dbg ? String(this.renderer.getContext().getParameter(dbg.UNMASKED_RENDERER_WEBGL)) : '';
    this.softwareGL = /swiftshader|llvmpipe|software/i.test(gpuName);
    this.renderer.setPixelRatio(this.softwareGL ? 1 : Math.min(window.devicePixelRatio || 1, 1.75));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = this.softwareGL ? THREE.PCFShadowMap : THREE.PCFSoftShadowMap;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.NoToneMapping;

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x8fa3ad);
    // Distance haze keeps the far edge of the map from reading as a hard cut.
    // With an orthographic camera parked at a fixed distance, fog has to be
    // expressed relative to that distance or it swallows the whole scene.
    this.camDist = 2200;
    this.fogSpread = 1.0;
    this.scene.fog = new THREE.Fog(0x93a6b0, 1400, 3600);

    this.camera = new THREE.OrthographicCamera(-100, 100, 100, -100, -4000, 6000);
    this.target = new THREE.Vector3(0, 0, 0);
    this.viewHeight = 900;          // world units visible vertically
    this.minView = 220;
    this.maxView = 2600;
    this.bounds = null;

    this._buildLights();

    this.raycaster = new THREE.Raycaster();
    this.pickables = [];
    this._ndc = new THREE.Vector2();
    this._groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);

    this.resize();
  }

  _buildLights() {
    // Warm low sun for long readable shadows, cool sky fill so shadowed faces
    // stay legible instead of going black.
    const sun = new THREE.DirectionalLight(0xffeeda, 1.05);
    sun.position.set(-620, 900, 420);
    sun.castShadow = true;
    sun.shadow.mapSize.set(this.softwareGL ? 1024 : 2048, this.softwareGL ? 1024 : 2048);
    // Shadow acne shows up as a grey checkerboard over open ground; a healthy
    // normal bias plus a tight depth range is what keeps it away.
    sun.shadow.bias = -0.0004;
    sun.shadow.normalBias = 3.0;
    const c = sun.shadow.camera;
    c.near = 600; c.far = 2400;
    this.scene.add(sun);
    this.scene.add(sun.target);
    this.sun = sun;

    const sky = new THREE.HemisphereLight(0xa8c4dc, 0x4a4534, 0.45);
    this.scene.add(sky);
    this.hemi = sky;

    const bounce = new THREE.DirectionalLight(0xbcc8d4, 0.15);
    bounce.position.set(500, 300, -600);
    this.scene.add(bounce);
  }

  setSkyMood({ background, haze, sunIntensity, skyLight }) {
    if (background !== undefined) {
      this.scene.background = new THREE.Color(background);
      this.scene.fog.color = new THREE.Color(background);
    }
    // haze > 1 pulls the murk closer (an industrial valley), < 1 pushes it back
    if (haze !== undefined) this.fogSpread = 1 / Math.max(0.25, haze);
    if (sunIntensity !== undefined) this.sun.intensity = sunIntensity;
    if (skyLight !== undefined) this.hemi.intensity = skyLight;
    this._applyCamera();
  }

  resize() {
    const w = this.canvas.clientWidth || window.innerWidth;
    const h = this.canvas.clientHeight || window.innerHeight;
    if (w === this._lastW && h === this._lastH) return;
    this._lastW = w; this._lastH = h;
    this.renderer.setSize(w, h, false);
    this.aspect = w / h;
    this._applyCamera();
  }

  _applyCamera() {
    const hh = this.viewHeight / 2;
    const hw = hh * this.aspect;
    this.camera.left = -hw; this.camera.right = hw;
    this.camera.top = hh; this.camera.bottom = -hh;
    this.camera.updateProjectionMatrix();

    // Sit the camera back along the view direction; ortho depth does the rest.
    const dist = this.camDist;
    const dir = new THREE.Vector3(
      Math.sin(CAM_AZIM) * Math.cos(CAM_ELEV),
      Math.sin(CAM_ELEV),
      Math.cos(CAM_AZIM) * Math.cos(CAM_ELEV),
    );
    this.camera.position.copy(this.target).addScaledVector(dir, dist);
    this.camera.lookAt(this.target);
    this.camera.updateMatrixWorld();

    // Keep the shadow frustum tight around what is actually on screen.
    const span = Math.max(this.viewHeight * this.aspect, this.viewHeight) * 0.62;
    const sc = this.sun.shadow.camera;
    sc.left = -span; sc.right = span; sc.top = span; sc.bottom = -span;
    sc.updateProjectionMatrix();
    // Keep the light a fixed distance from what it lights, so the tight depth
    // range above always contains the scene.
    this.sun.position.set(this.target.x - 780, 1140, this.target.z + 530);
    this.sun.target.position.copy(this.target);
    this.sun.target.updateMatrixWorld();

    // Haze only in the far part of the view, scaled to how far out we are.
    if (this.scene.fog) {
      const depth = this.viewHeight / Math.tan(CAM_ELEV);
      this.scene.fog.near = dist + depth * 0.15 * this.fogSpread;
      this.scene.fog.far = dist + depth * 1.5 * this.fogSpread;
    }
  }

  setBounds(w, h) {
    this.bounds = { w, h };
    this._clampTarget();
  }

  _clampTarget() {
    if (!this.bounds) return;
    // Keep the view over the map: showing a screenful of empty sky beside the
    // world is the fastest way to make a game look unfinished.
    const margin = 140;
    const halfH = this.viewHeight / 2 / Math.sin(CAM_ELEV);
    const halfW = this.viewHeight * this.aspect / 2;
    const axis = (v, half, size) => {
      const lo = half - margin, hi = size - half + margin;
      return lo > hi ? size / 2 : Math.max(lo, Math.min(hi, v));
    };
    this.target.x = axis(this.target.x, halfW, this.bounds.w);
    this.target.z = axis(this.target.z, halfH, this.bounds.h);
  }

  centerOn(x, y) {
    this.target.set(x, 0, y);
    this._clampTarget();
    this._applyCamera();
  }

  // Pan in screen space: dx/dy in pixels.
  pan(dxPx, dyPx) {
    const perPx = this.viewHeight / (this.canvas.clientHeight || 1);
    // screen right is world +x; screen up is world -z at this azimuth
    this.target.x += dxPx * perPx;
    this.target.z += dyPx * perPx / Math.sin(CAM_ELEV);
    this._clampTarget();
    this._applyCamera();
  }

  zoomBy(factor, atX, atY) {
    const before = atX !== undefined ? this.screenToGround(atX, atY) : null;
    this.viewHeight = Math.max(this.minView, Math.min(this.maxView, this.viewHeight / factor));
    this._clampTarget();
    this._applyCamera();
    if (before) {
      const after = this.screenToGround(atX, atY);
      if (after) {
        this.target.x += before.x - after.x;
        this.target.z += before.z - after.z;
        this._clampTarget();
        this._applyCamera();
      }
    }
  }

  get zoom() { return 900 / this.viewHeight; }

  _setRay(px, py) {
    const rect = this.canvas.getBoundingClientRect();
    this._ndc.x = (px / rect.width) * 2 - 1;
    this._ndc.y = -(py / rect.height) * 2 + 1;
    this.raycaster.setFromCamera(this._ndc, this.camera);
  }

  // Screen pixel -> ground point, using real terrain when available so clicks
  // land where the player sees the cursor on a hillside.
  screenToGround(px, py) {
    this._setRay(px, py);
    if (this.pickables.length) {
      const hit = this.raycaster.intersectObjects(this.pickables, false);
      if (hit.length) return hit[0].point.clone();
    }
    const p = new THREE.Vector3();
    return this.raycaster.ray.intersectPlane(this._groundPlane, p) ? p : null;
  }

  // World point -> screen pixels, for HUD anchors.
  worldToScreen(x, y, z) {
    const v = new THREE.Vector3(x, y, z).project(this.camera);
    const rect = this.canvas.getBoundingClientRect();
    return {
      x: (v.x * 0.5 + 0.5) * rect.width,
      y: (-v.y * 0.5 + 0.5) * rect.height,
      depth: v.z,
    };
  }

  setPickables(objs) { this.pickables = objs; }

  clear() {
    // Drop everything except lights, keeping GPU resources tidy between scenes.
    const keep = new Set([this.sun, this.sun.target, this.hemi]);
    for (const child of [...this.scene.children]) {
      if (keep.has(child) || child.isLight) continue;
      this.scene.remove(child);
      disposeTree(child);
    }
    this.pickables = [];
  }

  render() {
    // Layout can settle after construction (fonts, panels), so track the real
    // element size every frame — it is a cheap compare and never a wrong aspect.
    this.resize();
    this.renderer.render(this.scene, this.camera);
  }
}

export function disposeTree(obj) {
  obj.traverse?.((o) => {
    if (o.geometry) o.geometry.dispose();
    const m = o.material;
    if (Array.isArray(m)) m.forEach(x => x.dispose());
    else if (m) m.dispose();
  });
}

// Shared flat-shaded material factory: the diorama look wants colour and form,
// not texture detail.
export function flatMaterial(color, opts = {}) {
  return new THREE.MeshLambertMaterial({
    color,
    vertexColors: !!opts.vertexColors,
    transparent: !!opts.transparent,
    opacity: opts.opacity ?? 1,
    side: opts.side || THREE.FrontSide,
    flatShading: true,
  });
}

export { THREE };
