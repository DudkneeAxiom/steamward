"""Shared foundation for STEAMWARD's 3D asset kits.

Scale contract
--------------
1 Blender unit == 1 game world unit == 10 cm.

    soldier          ~18-20 units tall
    cottage           60 x 50 footprint, ~45 tall
    curtain wall      ~55 tall
    keep             ~200 wide, ~150 tall
    foundry chimney  ~120 tall
    mature tree       70-110 tall

Orientation contract
--------------------
+X is east, +Y is north, +Z is up. Models face +X. Origins sit on the ground
at the footprint centre, so the game places an asset by dropping it at
(x, terrainHeight, y) with no per-asset offsets.

Everything is built from chunky rectangular masses — this is a miniature
diorama, not Minecraft: no uniform cube grid, no pixel textures. Detail comes
from geometry and flat material colour, so the look survives at RTS distance.

Materials are shared across kits (see MATERIALS) so a wooden beam in a
hamlet matches a wooden beam in a foundry. Faction cloth is a marked material
the runtime recolours per faction.
"""

import math
import os

import bpy

# Palette is authored in sRGB — what the eye sees — and converted to linear,
# because Blender's Base Color is linear and skipping that step is what makes
# stylized art look chalky.
MATERIALS = {
    # structure
    'stone':        (0.44, 0.43, 0.40),
    'stone_dark':   (0.31, 0.30, 0.28),
    'stone_light':  (0.57, 0.56, 0.52),
    'plaster':      (0.68, 0.64, 0.54),
    'timber':       (0.30, 0.21, 0.13),
    'timber_light': (0.48, 0.36, 0.21),
    'thatch':       (0.53, 0.43, 0.22),
    'roof_tile':    (0.42, 0.21, 0.15),
    'roof_slate':   (0.26, 0.27, 0.30),
    # industry
    'iron':         (0.27, 0.28, 0.31),
    'iron_dark':    (0.17, 0.18, 0.20),
    'steel':        (0.55, 0.56, 0.57),
    'brass':        (0.72, 0.58, 0.26),
    'copper':       (0.55, 0.35, 0.20),
    'soot':         (0.15, 0.15, 0.15),
    'coal':         (0.08, 0.08, 0.09),
    'ember':        (0.95, 0.45, 0.12),
    # organic
    'skin':         (0.74, 0.58, 0.44),
    'leather':      (0.36, 0.25, 0.15),
    'canvas':       (0.60, 0.56, 0.45),
    'foliage_a':    (0.19, 0.32, 0.15),
    'foliage_b':    (0.25, 0.38, 0.18),
    'foliage_c':    (0.31, 0.42, 0.20),
    'trunk':        (0.28, 0.20, 0.13),
    'grass':        (0.32, 0.42, 0.20),
    'dirt':         (0.36, 0.28, 0.18),
    'crop':         (0.62, 0.55, 0.24),
    'water':        (0.16, 0.30, 0.38),
    # faction cloth — recoloured at runtime; name is the contract
    'cloth':        (0.55, 0.20, 0.20),
}

METALLIC = {'iron', 'iron_dark', 'steel', 'brass', 'copper'}
EMISSIVE = {'ember'}

_mat_cache = {}


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def mat(name):
    """Fetch (or build) a shared material. Unknown names fail loudly rather
    than silently rendering grey."""
    if name in _mat_cache:
        return _mat_cache[name]
    if name not in MATERIALS:
        raise KeyError(f'unknown material {name!r}; add it to MATERIALS')
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes['Principled BSDF']
    r, g, b = (srgb_to_linear(c) for c in MATERIALS[name])
    bsdf.inputs['Base Color'].default_value = (r, g, b, 1.0)
    bsdf.inputs['Roughness'].default_value = 0.42 if name in METALLIC else 0.85
    if 'Metallic' in bsdf.inputs:
        bsdf.inputs['Metallic'].default_value = 0.75 if name in METALLIC else 0.0
    if name in EMISSIVE and 'Emission Color' in bsdf.inputs:
        bsdf.inputs['Emission Color'].default_value = (r, g, b, 1.0)
        bsdf.inputs['Emission Strength'].default_value = 3.0
    _mat_cache[name] = m
    return m


# ---------------------------------------------------------------- primitives

def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for coll in (bpy.data.meshes, bpy.data.curves, bpy.data.armatures):
        for b in list(coll):
            if b.users == 0:
                coll.remove(b)


def empty(name='root'):
    e = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(e)
    return e


def box(x, y, z, w, d, h, material, parent=None, rot=None, bevel=0.0, name=None):
    """A rectangular mass. (x, y) is the centre of the footprint, z its base —
    the way you think when stacking pieces."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z + h / 2.0))
    ob = bpy.context.object
    # a size=1 cube spans -0.5..0.5, so the scale IS the edge length
    ob.scale = (w, d, h)
    if name:
        ob.name = name
    if rot:
        ob.rotation_euler = rot
    ob.data.materials.append(mat(material))
    for p in ob.data.polygons:
        p.use_smooth = False
    if bevel > 0:
        m = ob.modifiers.new('bevel', 'BEVEL')
        m.width = bevel
        m.segments = 1
        m.limit_method = 'ANGLE'
    if parent:
        ob.parent = parent
        ob.matrix_parent_inverse = parent.matrix_world.inverted()
    return ob


def cyl(x, y, z, r, h, material, parent=None, verts=8, rot=None, name=None):
    """A drum: boilers, pressure vessels, chimneys, tree trunks."""
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h,
                                        location=(x, y, z + h / 2.0))
    ob = bpy.context.object
    if name:
        ob.name = name
    if rot:
        ob.rotation_euler = rot
    ob.data.materials.append(mat(material))
    for p in ob.data.polygons:
        p.use_smooth = False
    if parent:
        ob.parent = parent
        ob.matrix_parent_inverse = parent.matrix_world.inverted()
    return ob


def wedge(x, y, z, w, d, h, material, parent=None, rot=None, name=None):
    """A ridged roof mass: a box whose top edge is collapsed to a ridge line
    running along +X."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
    ob = bpy.context.object
    me = ob.data
    # collapse the two top edges in Y toward the centre to make a ridge
    for v in me.vertices:
        if v.co.z > 0:
            v.co.y = 0.0
    ob.scale = (w, d, h)
    ob.location = (x, y, z + h / 2.0)
    if name:
        ob.name = name
    if rot:
        ob.rotation_euler = rot
    ob.data.materials.append(mat(material))
    for p in me.polygons:
        p.use_smooth = False
    if parent:
        ob.parent = parent
        ob.matrix_parent_inverse = parent.matrix_world.inverted()
    return ob


def ramp(x, y, z, w, d, h, material, parent=None, rot=None, name=None):
    """A single-slope mass — lean-to roofs, spoil heaps, earth ramps."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
    ob = bpy.context.object
    for v in ob.data.vertices:
        if v.co.z > 0 and v.co.y > 0:
            v.co.z = -0.5
    ob.scale = (w, d, h)
    ob.location = (x, y, z + h / 2.0)
    if name:
        ob.name = name
    if rot:
        ob.rotation_euler = rot
    ob.data.materials.append(mat(material))
    for p in ob.data.polygons:
        p.use_smooth = False
    if parent:
        ob.parent = parent
        ob.matrix_parent_inverse = parent.matrix_world.inverted()
    return ob


# ---------------------------------------------------------------- assembly

def pitched_roof(cx, cy, base_z, w, d, h, material, parent=None, overhang=4.0,
                 eave='timber'):
    """Roof with eaves, used by every building so rooflines stay consistent."""
    if eave:
        box(cx, cy, base_z, w + overhang * 2, d + overhang * 2, 3, eave, parent)
    return wedge(cx, cy, base_z + 3, w + overhang * 2, d + overhang * 2, h, material, parent)


def rivet_band(cx, cy, z, r, material='iron_dark', parent=None, verts=8):
    return cyl(cx, cy, z, r * 1.06, 2.2, material, parent, verts=verts)


def export_glb(root, path, apply_modifiers=True):
    """Export one asset. Selection-based so kits can share a scene."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')

    def sel(ob):
        ob.select_set(True)
        for c in ob.children:
            sel(c)

    sel(root)
    bpy.context.view_layer.objects.active = root
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format='GLB',
        use_selection=True,
        export_apply=apply_modifiers,
        export_yup=True,                 # three.js is Y-up
        export_materials='EXPORT',
        export_cameras=False,
        export_lights=False,
        export_extras=True,
        export_normals=True,
        export_texcoords=False,
        export_tangents=False,
        export_skins=False,
        export_animations=False,
    )


def preview_render(root, path, px=420, angle=35.0, azimuth=-35.0, margin=1.25):
    """Render one asset to a PNG so its silhouette can actually be looked at
    before it is exported. Cycles on CPU: EEVEE needs a GPU context a headless
    build has no business assuming."""
    import mathutils
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 24
    scene.cycles.use_denoising = False
    scene.render.resolution_x = px
    scene.render.resolution_y = px
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = 'PNG'
    try:
        scene.view_settings.view_transform = 'Standard'
    except (AttributeError, TypeError):
        pass

    w, d, h = bounds(root)
    span = max(w, d, h, 1.0) * margin

    world = bpy.data.worlds.get('World') or bpy.data.worlds.new('World')
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.30, 0.34, 0.38, 1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.5

    for ob in list(bpy.data.objects):
        if ob.type in ('CAMERA', 'LIGHT'):
            bpy.data.objects.remove(ob, do_unlink=True)

    bpy.ops.object.light_add(type='SUN')
    sun = bpy.context.object
    sun.data.energy = 3.0
    sun.data.angle = 0.2
    sun.rotation_euler = (math.radians(52), 0, math.radians(-40))

    bpy.ops.object.camera_add()
    cam = bpy.context.object
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = span
    el, az = math.radians(angle), math.radians(azimuth)
    dist = span * 3
    cam.location = (dist * math.cos(el) * math.sin(az),
                    -dist * math.cos(el) * math.cos(az),
                    dist * math.sin(el) + h * 0.35)
    look = mathutils.Vector((0, 0, h * 0.45)) - mathutils.Vector(cam.location)
    cam.rotation_euler = look.to_track_quat('-Z', 'Y').to_euler()
    scene.camera = cam

    # a ground plane so the piece is not floating in a void
    bpy.ops.mesh.primitive_plane_add(size=span * 4, location=(0, 0, -0.05))
    ground = bpy.context.object
    ground.data.materials.append(mat('grass'))

    os.makedirs(os.path.dirname(path), exist_ok=True)
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(ground, do_unlink=True)


def bounds(root):
    """(w, d, h) footprint of an assembled asset, in game units."""
    bpy.context.view_layer.update()   # object matrices are stale until this
    lo = [1e9] * 3
    hi = [-1e9] * 3
    stack = [root]
    while stack:
        ob = stack.pop()
        stack.extend(ob.children)
        if ob.type != 'MESH':
            continue
        for corner in ob.bound_box:
            v = ob.matrix_world @ __import__('mathutils').Vector(corner)
            for i, c in enumerate((v.x, v.y, v.z)):
                lo[i] = min(lo[i], c)
                hi[i] = max(hi[i], c)
    if lo[0] > hi[0]:
        return (0.0, 0.0, 0.0)
    return tuple(round(hi[i] - lo[i], 2) for i in range(3))
