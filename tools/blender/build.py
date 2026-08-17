"""Render STEAMWARD's voxel sprite atlases.

    tools/blender/render.sh            # everything
    tools/blender/render.sh units      # just the unit sheets

Outputs into assets/:
    units-<faction>.png + units.json   8 facings x 3 poses per troop type
    props.png + props.json             scenery and buildings

Each frame is rendered with the model origin at the frame centre, so the game
draws a sprite by centring it on the object's ground position.
"""

import json
import math
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
from PIL import Image  # noqa: E402

import lib  # noqa: E402
import models  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OUT = os.path.join(ROOT, 'assets')
PPU = 4.0                       # pixels per voxel at zoom 1
FACINGS = 8
POSES = 3                       # 0 stand, 1/2 walk
PAD = 3                         # px of breathing room around the largest model

# Cloth colour per faction. These are the banner/tabard colours the player
# reads factions by, so they match the palette in src/data.js.
FACTION_CLOTH = {
    'player':   (0.20, 0.46, 0.28),
    'falkmoor': (0.55, 0.15, 0.10),
    'brennan':  (0.20, 0.33, 0.49),
    'bandit':   (0.34, 0.28, 0.18),
    'neutral':  (0.42, 0.40, 0.36),
}

UNIT_ORDER = ['levy', 'spearman', 'shieldman', 'bowman', 'pressurebow',
              'hero', 'rider', 'boilerlancer', 'banner']


def set_cloth(rgb):
    m = lib.material('cloth')
    bsdf = m.node_tree.nodes['Principled BSDF']
    lin = [lib.srgb_to_linear(c) for c in rgb]
    bsdf.inputs['Base Color'].default_value = (lin[0], lin[1], lin[2], 1.0)


def clear_models():
    for ob in list(bpy.data.objects):
        if ob.type in ('MESH', 'EMPTY'):
            bpy.data.objects.remove(ob, do_unlink=True)


def measure_units():
    """One uniform cell for every troop sprite, big enough for the worst case
    (a boiler lancer with its lance swung across the frame)."""
    half_w = half_h = 0.0
    for name, builder in models.UNITS.items():
        for pose in range(POSES):
            clear_models()
            g = builder(pose)
            for facing in range(FACINGS):
                g.rotation_euler = (0, 0, -facing * 2 * math.pi / FACINGS)
                bpy.context.view_layer.update()
                l, r, u, d = lib.scene_extent_px(PPU)
                half_w = max(half_w, l, r)
                half_h = max(half_h, u, d)
    cell_w = int(2 * math.ceil(half_w + PAD))
    cell_h = int(2 * math.ceil(half_h + PAD))
    return cell_w, cell_h


def build_units(tmp):
    lib.reset_scene()
    lib.setup_world()
    lib.setup_lights()
    lib.setup_camera(1.0)
    lib.setup_render(8, 8)
    CELL_W, CELL_H = measure_units()
    print(f'unit cell {CELL_W}x{CELL_H}')
    lib.setup_camera(CELL_W / PPU)
    lib.setup_render(CELL_W, CELL_H)

    meta = {
        'cell': [CELL_W, CELL_H], 'facings': FACINGS, 'poses': POSES,
        'ppu': PPU, 'rows': UNIT_ORDER,
    }
    with open(os.path.join(OUT, 'units.json'), 'w') as f:
        json.dump(meta, f, indent=1)

    for faction, cloth in FACTION_CLOTH.items():
        set_cloth(cloth)
        sheet = Image.new('RGBA', (CELL_W * FACINGS * POSES, CELL_H * len(UNIT_ORDER)))
        for row, name in enumerate(UNIT_ORDER):
            builder = models.UNITS[name]
            n_poses = 1 if name == 'banner' else POSES
            for pose in range(n_poses):
                clear_models()
                g = builder(pose)
                for facing in range(FACINGS):
                    # Game facing 0 is +x; screen y grows downward, so a game
                    # angle maps to a negative rotation about Blender's Z.
                    g.rotation_euler = (0, 0, -facing * 2 * math.pi / FACINGS)
                    path = os.path.join(tmp, f'{faction}_{name}_{pose}_{facing}.png')
                    lib.render_to(path)
                    frame = Image.open(path)
                    sheet.paste(frame, ((pose * FACINGS + facing) * CELL_W, row * CELL_H))
            if n_poses == 1:                       # reuse the single pose
                strip = sheet.crop((0, row * CELL_H, CELL_W * FACINGS, (row + 1) * CELL_H))
                for pose in range(1, POSES):
                    sheet.paste(strip, (pose * FACINGS * CELL_W, row * CELL_H))
        out = os.path.join(OUT, f'units-{faction}.png')
        sheet.save(out, optimize=True)
        print('wrote', out, sheet.size)


def build_props(tmp):
    lib.reset_scene()
    lib.setup_world()
    lib.setup_lights()

    frames, images, footprints = {}, {}, {}
    for name, (builder, scale) in models.PROPS.items():
        clear_models()
        lib.setup_camera(1.0)
        lib.setup_render(8, 8)
        g = builder()
        g.scale = (scale, scale, scale)
        bpy.context.view_layer.update()
        l, r, u, d = lib.scene_extent_px(PPU)
        px_w = int(2 * math.ceil(max(l, r) + PAD))
        px_h = int(2 * math.ceil(max(u, d) + PAD))
        lib.setup_camera(px_w / PPU)
        lib.setup_render(px_w, px_h)
        path = os.path.join(tmp, f'prop_{name}.png')
        lib.render_to(path)
        images[name] = Image.open(path).copy()
        footprints[name] = lib.scene_footprint_px(PPU)

    # Simple shelf packing — a couple of dozen sprites, no need for cleverness.
    pad = 2
    max_w = 1024
    x = y = row_h = 0
    placed = {}
    for name, im in sorted(images.items(), key=lambda kv: -kv[1].height):
        if x + im.width > max_w:
            x = 0
            y += row_h + pad
            row_h = 0
        placed[name] = (x, y, im.width, im.height)
        x += im.width + pad
        row_h = max(row_h, im.height)
    sheet_h = y + row_h
    sheet = Image.new('RGBA', (max_w, sheet_h))
    for name, (px, py, w, h) in placed.items():
        fw, fd, fh = footprints[name]
        frames[name] = {'x': px, 'y': py, 'w': w, 'h': h, 'fw': fw, 'fd': fd, 'fh': fh}
        sheet.paste(images[name], (px, py))

    sheet.save(os.path.join(OUT, 'props.png'), optimize=True)
    with open(os.path.join(OUT, 'props.json'), 'w') as f:
        json.dump({'ppu': PPU, 'frames': frames}, f, indent=1)
    print('wrote props.png', sheet.size, len(frames), 'sprites')


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else 'all'
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='steamward-render-')
    try:
        if what in ('all', 'units'):
            build_units(tmp)
        if what in ('all', 'props'):
            build_props(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


main()
