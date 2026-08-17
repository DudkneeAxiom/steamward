"""Shared Blender helpers for STEAMWARD's voxel asset pipeline.

Everything is modelled from unit cubes ("voxels") and rendered with an
orthographic camera whose projection matches the game's 2.5D camera exactly:

    screen_x = world_x
    screen_y = world_y * 0.68 - world_z

An orthographic camera at elevation t projects depth by sin(t) and height by
cos(t). Setting tan(t) = 0.68 gives the right depth/height ratio, and a pixel
aspect of cos(t) restores height to 1:1 with width. Because the camera aims
at the world origin, every sprite's anchor is simply the centre of its frame.

Blender's +Y points away from the camera, which is the game's -Y (up-screen),
so a point (bx, by, bz) lands at bx*PPU right of centre and (by*0.68 + bz)*PPU
above it.
"""

import math
import os
import bpy
from mathutils import Vector

Y_SQUASH = 0.68
ELEV = math.atan(Y_SQUASH)          # 34.22 degrees above the horizon
PIXEL_ASPECT_Y = math.cos(ELEV)

# Palette. `cloth` is a key colour swapped to faction colours at load time.
PALETTE = {
    'cloth':     (1.0, 0.0, 1.0),    # KEY — recoloured per faction in the browser
    'skin':      (0.78, 0.62, 0.47),
    'leather':   (0.42, 0.29, 0.18),
    'wood':      (0.35, 0.25, 0.15),
    'wood_pale': (0.55, 0.42, 0.24),
    'steel':     (0.62, 0.62, 0.60),
    'dark':      (0.20, 0.20, 0.22),
    'brass':     (0.79, 0.66, 0.35),
    'stone':     (0.46, 0.45, 0.42),
    'stone_lit': (0.56, 0.55, 0.51),
    'roof':      (0.47, 0.24, 0.16),
    'thatch':    (0.55, 0.44, 0.22),
    'canvas':    (0.62, 0.58, 0.47),
    'foliage':   (0.20, 0.33, 0.16),
    'foliage2':  (0.26, 0.40, 0.20),
    'coal':      (0.10, 0.10, 0.11),
    'soot':      (0.24, 0.23, 0.22),
    'horse':     (0.36, 0.25, 0.16),
    'horse_dk':  (0.20, 0.19, 0.18),
    'iron':      (0.32, 0.33, 0.36),
    'dirt':      (0.36, 0.31, 0.21),
}

_materials = {}


def srgb_to_linear(c):
    """Palette entries are written as sRGB (what the eye sees); Blender's
    Base Color is linear, and skipping this is what makes voxel art look
    washed out and chalky."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def material(name):
    if name in _materials:
        return _materials[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes['Principled BSDF']
    r, g, b = (srgb_to_linear(c) for c in PALETTE[name])
    bsdf.inputs['Base Color'].default_value = (r, g, b, 1.0)
    bsdf.inputs['Roughness'].default_value = 0.35 if name in ('steel', 'brass', 'iron') else 0.85
    if 'Metallic' in bsdf.inputs:
        bsdf.inputs['Metallic'].default_value = 0.6 if name in ('steel', 'brass', 'iron') else 0.0
    if 'Specular IOR Level' in bsdf.inputs:
        bsdf.inputs['Specular IOR Level'].default_value = 0.25
    _materials[name] = m
    return m


def reset_scene():
    """Wipe objects but keep materials cached across builds."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.cameras, bpy.data.lights):
        for b in list(block):
            if b.users == 0:
                block.remove(b)


def box(x, y, z, w, d, h, mat, parent=None, rot=None):
    """Axis-aligned voxel box. (x, y, z) is the centre of its footprint at its
    base, so z is 'height off the ground' — the way you actually think about
    stacking blocks."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z + h / 2.0))
    ob = bpy.context.object
    ob.scale = (w / 2.0, d / 2.0, h / 2.0)
    ob.data.materials.append(material(mat))
    for p in ob.data.polygons:
        p.use_smooth = False
    if rot:
        ob.rotation_euler = rot
    if parent:
        ob.parent = parent
    return ob


def group(name='model'):
    """Empty used as the parent for a whole model, so it can be spun for facings."""
    e = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(e)
    return e


def setup_world(strength=0.22):
    world = bpy.data.worlds.get('World') or bpy.data.worlds.new('World')
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes['Background']
    bg.inputs['Color'].default_value = (0.55, 0.60, 0.70, 1.0)
    bg.inputs['Strength'].default_value = strength


def setup_lights():
    """Key light from the upper left-front, plus a cool fill, so voxel faces
    read as three distinct tones without blowing out the palette."""
    bpy.ops.object.light_add(type='SUN', location=(-6, -8, 12))
    key = bpy.context.object
    key.data.energy = 2.1
    key.data.angle = 0.3
    key.rotation_euler = (math.radians(48), math.radians(-14), math.radians(-38))

    bpy.ops.object.light_add(type='SUN', location=(8, -6, 6))
    fill = bpy.context.object
    fill.data.energy = 0.7
    fill.data.color = (0.70, 0.79, 0.95)
    fill.rotation_euler = (math.radians(62), 0, math.radians(52))


def setup_camera(view_width_units):
    """Orthographic camera matching the game's projection, aimed at the origin."""
    bpy.ops.object.camera_add(location=(0, 0, 0))
    cam = bpy.context.object
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = view_width_units
    cam.data.sensor_fit = 'HORIZONTAL'
    # Look down at the scene from the -Y side at ELEV above the horizon.
    cam.rotation_euler = (math.pi / 2 - ELEV, 0.0, 0.0)
    d = 60.0
    cam.location = (0.0, -d * math.cos(ELEV), d * math.sin(ELEV))
    bpy.context.scene.camera = cam
    return cam


def setup_render(px_w, px_h, samples=24):
    scene = bpy.context.scene
    # Cycles on CPU: EEVEE needs a GPU context, which a headless build has no
    # business assuming. The geometry is a handful of cubes, so this is cheap.
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = samples
    scene.cycles.use_denoising = False
    scene.cycles.max_bounces = 4
    scene.cycles.diffuse_bounces = 2
    scene.cycles.glossy_bounces = 2
    scene.cycles.transmission_bounces = 0
    scene.cycles.use_fast_gi = True
    scene.render.resolution_x = px_w
    scene.render.resolution_y = px_h
    scene.render.resolution_percentage = 100
    scene.render.pixel_aspect_x = 1.0
    scene.render.pixel_aspect_y = PIXEL_ASPECT_Y
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.filter_size = 1.1
    # Stylized art wants its palette back: AgX (the default) desaturates these
    # colours badly, and the game reads factions by colour.
    try:
        scene.view_settings.view_transform = 'Standard'
        scene.view_settings.look = 'None'
        scene.view_settings.exposure = 0.0
        scene.view_settings.gamma = 1.0
    except (AttributeError, TypeError):
        pass


def scene_extent_px(ppu):
    """Pixels the current scene needs around the origin: (left, right, up, down).

    Sprites are anchored at the model origin, so a frame must reach far enough
    on each side of centre for nothing to clip when the model spins."""
    left = right = up = down = 0.0
    for ob in bpy.data.objects:
        if ob.type != 'MESH':
            continue
        for corner in ob.bound_box:
            v = ob.matrix_world @ Vector(corner)
            x = v.x * ppu
            y = (v.y * Y_SQUASH + v.z) * ppu
            left = min(left, x); right = max(right, x)
            down = min(down, y); up = max(up, y)
    return (-left, right, up, -down)


def scene_footprint_px(ppu):
    """Physical size of the model in game pixels: (width, depth, height).
    The game sizes obstacles from this, so collision follows the art."""
    lo = [1e9, 1e9, 1e9]
    hi = [-1e9, -1e9, -1e9]
    for ob in bpy.data.objects:
        if ob.type != 'MESH':
            continue
        for corner in ob.bound_box:
            v = ob.matrix_world @ Vector(corner)
            for i, c in enumerate((v.x, v.y, v.z)):
                lo[i] = min(lo[i], c)
                hi[i] = max(hi[i], c)
    if lo[0] > hi[0]:
        return (0, 0, 0)
    return tuple(round((hi[i] - lo[i]) * ppu, 1) for i in range(3))


def render_to(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
