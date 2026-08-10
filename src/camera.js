// 2.5D camera: world is a flat plane; the view squashes Y and lifts objects by
// height (z) to read as a tabletop diorama seen from a low angle.

import { clamp } from './util.js';

export const Y_SQUASH = 0.68;

export function makeCamera(canvas) {
  return {
    x: 0, y: 0, zoom: 1,
    minZoom: 0.4, maxZoom: 2.2,
    canvas,
    bounds: null, // {w, h} world size for clamping

    toScreen(wx, wy, wz = 0) {
      return {
        x: (wx - this.x) * this.zoom + this.canvas.width / 2,
        y: (wy - this.y) * this.zoom * Y_SQUASH + this.canvas.height / 2 - wz * this.zoom,
      };
    },
    toWorld(sx, sy) {
      return {
        x: (sx - this.canvas.width / 2) / this.zoom + this.x,
        y: (sy - this.canvas.height / 2) / (this.zoom * Y_SQUASH) + this.y,
      };
    },
    pan(dx, dy) {
      this.x += dx / this.zoom;
      this.y += dy / (this.zoom * Y_SQUASH);
      this.clampToBounds();
    },
    zoomAt(sx, sy, factor) {
      const before = this.toWorld(sx, sy);
      this.zoom = clamp(this.zoom * factor, this.minZoom, this.maxZoom);
      const after = this.toWorld(sx, sy);
      this.x += before.x - after.x;
      this.y += before.y - after.y;
      this.clampToBounds();
    },
    clampToBounds() {
      if (!this.bounds) return;
      // Keep the view over the play area: never show more than `margin` of void.
      const margin = 90;
      const hw = this.canvas.width / (2 * this.zoom);
      const hh = this.canvas.height / (2 * this.zoom * Y_SQUASH);
      const axis = (v, half, size) => {
        const lo = half - margin, hi = size - half + margin;
        return lo > hi ? size / 2 : clamp(v, lo, hi);
      };
      this.x = axis(this.x, hw, this.bounds.w);
      this.y = axis(this.y, hh, this.bounds.h);
    },
    centerOn(wx, wy) {
      this.x = wx; this.y = wy;
      this.clampToBounds();
    },
  };
}
