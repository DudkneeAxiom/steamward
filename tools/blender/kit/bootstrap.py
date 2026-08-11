"""Bootstrap kit — the minimum needed to prove the 3D pipeline end to end.

These are deliberately simple. The dedicated kits (settlement, industrial,
military, nature, units) export over the top of them by filename; anything they
have not covered yet still renders as a real object rather than a hole.
"""

import math
import os

import bpy

from common import box, cyl, wedge, empty, clear_scene, export_glb, preview_render, mat

R = math.radians


# ---------------------------------------------------------------- soldiers

def _soldier(kind):
    """A miniature soldier with the animation part contract: leg_l/leg_r and
    arm_l/arm_r are separate objects whose origins sit at hip and shoulder."""
    root = empty(kind)

    torso = empty('torso')
    torso.parent = root
    torso.location = (0, 0, 9.5)
    box(0, 0, -1.2, 3.4, 5.0, 6.0, 'cloth', torso)          # body
    box(0, 0, -1.4, 3.6, 5.2, 1.0, 'leather', torso)        # belt
    box(0, 0, 4.8, 3.0, 3.0, 3.0, 'skin', torso)            # head
    if kind != 'levy':
        box(0, 0, 6.4, 3.4, 3.4, 1.5, 'steel', torso)       # helmet
    else:
        box(0, 0, 6.3, 3.3, 3.3, 1.0, 'leather', torso)     # cap

    for side, name in ((-1, 'leg_l'), (1, 'leg_r')):
        leg = empty(name)
        leg.parent = root
        leg.location = (0, side * 1.5, 5.6)
        box(0, 0, -5.6, 1.8, 1.8, 5.6, 'leather', leg)

    arms = {}
    for side, name in ((-1, 'arm_l'), (1, 'arm_r')):
        arm = empty(name)
        arm.parent = torso
        arm.location = (0, side * 3.0, 3.6)
        box(0, 0, -4.4, 1.6, 1.6, 4.4, 'cloth', arm)
        arms[name] = arm

    weapon = empty('weapon')
    weapon.parent = arms['arm_r']
    weapon.location = (0.8, 0, -4.0)

    if kind == 'levy':
        box(0, 0, 0, 0.7, 0.7, 5.0, 'timber', weapon)
        box(0, 0, 4.6, 2.0, 0.9, 1.6, 'steel', weapon)
        box(-1.2, -6.0, -1.0, 0.8, 4.0, 4.0, 'timber_light', torso)
    elif kind == 'spearman':
        box(0, 0, -4.0, 0.7, 0.7, 17.0, 'timber', weapon)
        box(0, 0, 13.0, 0.9, 0.9, 2.6, 'steel', weapon)
        box(-1.2, -6.0, -1.0, 0.9, 4.4, 4.6, 'timber_light', torso)
    elif kind == 'shieldman':
        box(0, 0, 0, 0.7, 0.7, 5.6, 'steel', weapon)
        box(2.4, -4.4, -2.0, 1.0, 6.4, 9.0, 'timber_light', torso)   # big board
        box(3.0, -4.4, 1.6, 0.6, 2.0, 2.0, 'steel', torso)
    elif kind == 'bowman':
        box(0, 0, 0, 0.6, 0.7, 4.0, 'timber_light', weapon)
        box(0, 0, 3.6, 0.6, 0.7, 3.6, 'timber_light', weapon, rot=(R(16), 0, 0))
        box(0, 0, -3.4, 0.6, 0.7, 3.6, 'timber_light', weapon, rot=(R(-16), 0, 0))
        box(-2.0, 2.4, 0.4, 1.4, 1.4, 4.4, 'leather', torso)          # quiver
    elif kind == 'pressurebow':
        # reinforced limbs, draw carriage, reservoir, hose, gauge
        box(0, 0, 0, 0.9, 1.0, 4.4, 'steel', weapon)
        box(0, 0, 4.0, 0.9, 1.0, 4.0, 'steel', weapon, rot=(R(18), 0, 0))
        box(0, 0, -3.8, 0.9, 1.0, 4.0, 'steel', weapon, rot=(R(-18), 0, 0))
        box(1.1, 0, -0.4, 2.6, 1.4, 1.6, 'brass', weapon)             # carriage
        cyl(-2.2, 0, 0.6, 1.6, 5.0, 'iron', torso)                    # reservoir
        cyl(-2.2, 0, 5.6, 1.7, 0.5, 'iron_dark', torso)
        box(-2.2, -1.6, 3.4, 0.9, 0.7, 0.9, 'brass', torso)           # gauge
        box(-0.4, -1.4, 3.0, 3.6, 0.5, 0.5, 'iron_dark', torso)       # hose
        box(0, 0, -1.0, 3.8, 5.4, 2.4, 'iron', torso)                 # breastplate
    elif kind == 'hero':
        box(0, 0, 0, 0.8, 0.8, 6.4, 'steel', weapon)
        box(0, 0, -0.4, 0.8, 2.4, 0.8, 'brass', weapon)
        box(-1.6, 0, -1.6, 0.8, 5.6, 7.0, 'cloth', torso)             # coat
        box(0, 0, 7.6, 1.2, 4.0, 1.2, 'brass', torso)                 # crest
        box(-2.0, 0, 2.0, 0.5, 0.5, 9.0, 'timber', torso)             # banner staff
        b = box(-2.0, 0, 9.0, 0.4, 5.0, 4.0, 'cloth', torso)
        b.name = 'banner_cloth'
    return root


def _horse(root, heavy=False):
    body = 'iron' if heavy else 'leather'
    box(0, 0, 8.0, 15.0, 6.0, 6.5, body, root)                # barrel
    box(7.5, 0, 11.0, 4.0, 4.5, 5.0, body, root)              # neck
    box(9.8, 0, 14.5, 5.5, 4.0, 3.2, body, root)              # head
    box(12.4, 0, 15.0, 1.6, 3.0, 1.8, 'iron_dark', root)
    box(-8.0, 0, 12.0, 2.0, 1.6, 4.0, 'iron_dark', root, rot=(0, R(40), 0))
    for name, dx, dy in (('hleg_fl', 5.0, -2.2), ('hleg_fr', 5.0, 2.2),
                         ('hleg_bl', -5.0, -2.2), ('hleg_br', -5.0, 2.2)):
        leg = empty(name)
        leg.parent = root
        leg.location = (dx, dy, 8.0)
        box(0, 0, -8.0, 2.2, 2.2, 8.0, 'iron_dark' if heavy else 'timber', leg)
    if heavy:
        box(0, 0, 7.0, 15.5, 7.0, 3.0, 'cloth', root)         # caparison


def _cavalry(kind):
    root = empty(kind)
    heavy = kind == 'boilerlancer'
    _horse(root, heavy)

    torso = empty('torso')
    torso.parent = root
    torso.location = (0, 0, 15.5)
    box(0, 0, -1.0, 3.2, 4.6, 5.6, 'cloth', torso)
    box(0, 0, 4.4, 2.8, 2.8, 2.8, 'skin', torso)
    box(0, 0, 6.0, 3.2, 3.2, 1.4, 'steel', torso)
    for side, name in ((-1, 'leg_l'), (1, 'leg_r')):
        leg = empty(name)
        leg.parent = torso
        leg.location = (0, side * 2.6, -1.0)
        box(0, 0, -4.6, 1.8, 1.8, 4.6, 'leather', leg, rot=(R(side * 18), 0, 0))
    arm_r = empty('arm_r')
    arm_r.parent = torso
    arm_r.location = (0, 2.8, 3.2)
    box(0, 0, -4.0, 1.5, 1.5, 4.0, 'cloth', arm_r)
    arm_l = empty('arm_l')
    arm_l.parent = torso
    arm_l.location = (0, -2.8, 3.2)
    box(0, 0, -4.0, 1.5, 1.5, 4.0, 'cloth', arm_l)

    weapon = empty('weapon')
    weapon.parent = arm_r
    weapon.location = (1.0, 0, -3.6)
    if heavy:
        box(9.0, 0, 0, 26.0, 1.1, 1.1, 'timber_light', weapon)   # couched lance
        box(22.5, 0, 0, 3.2, 1.6, 1.6, 'steel', weapon)
        cyl(-3.2, 0, 1.0, 2.0, 5.5, 'iron', torso, rot=(0, 0, 0))  # back boiler
        cyl(-3.2, 0, 6.5, 2.1, 0.6, 'iron_dark', torso)
        box(-3.2, 1.6, 4.0, 0.9, 0.7, 0.9, 'brass', torso)         # valve
        box(0.6, 1.6, 2.0, 5.0, 0.5, 0.5, 'iron_dark', torso)      # feed to brace
        box(2.0, 2.4, 1.4, 1.6, 1.2, 1.2, 'brass', torso)          # piston brace
    else:
        box(0, 0, 2.0, 0.7, 0.7, 6.0, 'steel', weapon, rot=(0, R(35), 0))
    return root


# ---------------------------------------------------------------- scenery

def cottage_a():
    root = empty('cottage_a')
    box(0, 0, 0, 56, 44, 4, 'stone', root)
    box(0, 0, 4, 52, 40, 22, 'plaster', root)
    for dy in (-20, 20):
        box(0, dy, 4, 53, 2, 22, 'timber', root)
    box(0, 0, 26, 60, 48, 3, 'timber', root)
    wedge(0, 0, 29, 60, 48, 18, 'thatch', root)
    box(16, -14, 26, 8, 8, 16, 'stone', root)                 # chimney
    box(-26, 0, 4, 2, 10, 14, 'timber', root)                 # door
    return root


def tent_a():
    root = empty('tent_a')
    wedge(0, 0, 0, 34, 30, 20, 'canvas', root)
    box(0, 0, 20, 1.5, 30, 2, 'timber', root)
    box(17, 0, 0, 1.5, 8, 12, 'leather', root)
    return root


def tree_pine_a():
    root = empty('tree_pine_a')
    cyl(0, 0, 0, 2.6, 26, 'trunk', root, verts=6)
    box(0, 0, 20, 30, 30, 14, 'foliage_a', root)
    box(0, 0, 32, 22, 22, 13, 'foliage_b', root)
    box(0, 0, 43, 14, 14, 12, 'foliage_a', root)
    box(0, 0, 53, 7, 7, 9, 'foliage_c', root)
    return root


def tree_broad_a():
    root = empty('tree_broad_a')
    cyl(0, 0, 0, 3.4, 24, 'trunk', root, verts=6)
    cyl(-4, 2, 18, 2.0, 12, 'trunk', root, verts=5, rot=(0, R(28), 0))
    box(0, 0, 22, 34, 32, 16, 'foliage_b', root)
    box(-8, 4, 30, 22, 22, 12, 'foliage_a', root)
    box(8, -5, 32, 18, 18, 11, 'foliage_c', root)
    return root


def rock_a():
    root = empty('rock_a')
    box(0, 0, 0, 17, 14, 8, 'stone', root, rot=(0, 0, R(18)))
    box(3, -2, 6, 11, 9, 6, 'stone_light', root, rot=(0, R(9), R(-24)))
    box(-6, 4, 0, 8, 7, 4, 'stone_dark', root, rot=(0, 0, R(40)))
    return root


def bush_a():
    root = empty('bush_a')
    box(0, 0, 0, 12, 11, 7, 'foliage_b', root, rot=(0, 0, R(25)))
    box(3, 2, 5, 8, 7, 5, 'foliage_c', root)
    return root


def cart():
    root = empty('cart')
    box(0, 0, 5, 26, 14, 7, 'timber', root)
    box(0, 0, 12, 24, 12, 1.5, 'timber_light', root)
    for dx in (-8, 8):
        for dy in (-8, 8):
            cyl(dx, dy, 0, 5, 1.6, 'timber_light', root, verts=8, rot=(R(90), 0, 0))
    box(16, 0, 8, 12, 1.6, 1.6, 'timber', root)
    return root


def boiler_large():
    root = empty('boiler_large')
    box(0, 0, 0, 26, 22, 4, 'stone', root)
    cyl(0, 0, 4, 10, 26, 'iron', root, verts=10)
    for z in (8, 17, 25):
        cyl(0, 0, z, 10.6, 1.6, 'iron_dark', root, verts=10)
    cyl(0, 0, 30, 10.6, 1.4, 'iron_dark', root, verts=10)
    cyl(-4, 0, 31, 2.6, 14, 'soot', root, verts=8)             # stack
    box(5, 0, 31, 3.0, 3.0, 3.0, 'brass', root)                # relief valve
    box(11, -6, 6, 2.4, 2.4, 16, 'iron_dark', root)            # feed pipe
    box(11, 6, 20, 2.4, 2.4, 2.4, 'brass', root)               # outlet flange
    return root


def wall_segment():
    root = empty('wall_segment')
    box(0, 0, 0, 60, 22, 40, 'stone', root)
    box(0, 0, 0, 62, 24, 5, 'stone_light', root)
    box(0, 0, 40, 62, 24, 4, 'stone_light', root)
    for dx in (-24, -8, 8, 24):
        box(dx, -9, 44, 11, 6, 8, 'stone', root)               # merlons
    box(0, 8, 44, 60, 4, 3, 'stone_dark', root)                # inner kerb
    return root


def tower_round():
    root = empty('tower_round')
    cyl(0, 0, 0, 15, 58, 'stone', root, verts=10)
    cyl(0, 0, 0, 16.5, 5, 'stone_light', root, verts=10)
    cyl(0, 0, 58, 17, 4, 'stone_light', root, verts=10)
    for i in range(8):
        a = i * math.pi / 4
        box(math.cos(a) * 14, math.sin(a) * 14, 62, 6, 6, 8, 'stone', root, rot=(0, 0, a))
    box(15, 0, 30, 2, 3, 9, 'iron_dark', root)                 # arrow slit
    return root


ASSETS = {
    'levy': lambda: _soldier('levy'),
    'spearman': lambda: _soldier('spearman'),
    'shieldman': lambda: _soldier('shieldman'),
    'bowman': lambda: _soldier('bowman'),
    'pressurebow': lambda: _soldier('pressurebow'),
    'hero': lambda: _soldier('hero'),
    'rider': lambda: _cavalry('rider'),
    'boilerlancer': lambda: _cavalry('boilerlancer'),
}

PROPS = {
    'cottage_a': cottage_a, 'tent_a': tent_a,
    'tree_pine_a': tree_pine_a, 'tree_broad_a': tree_broad_a,
    'rock_a': rock_a, 'bush_a': bush_a, 'cart': cart,
    'boiler_large': boiler_large, 'wall_segment': wall_segment,
    'tower_round': tower_round,
}


def build_all(units_dir, props_dir, preview_dir=None):
    for name, builder in ASSETS.items():
        clear_scene()
        root = builder()
        bpy.context.view_layer.update()
        export_glb(root, os.path.join(units_dir, f'{name}.glb'))
        if preview_dir:
            preview_render(root, os.path.join(preview_dir, f'{name}.png'))
    for name, builder in PROPS.items():
        clear_scene()
        root = builder()
        bpy.context.view_layer.update()
        export_glb(root, os.path.join(props_dir, f'{name}.glb'))
        if preview_dir:
            preview_render(root, os.path.join(preview_dir, f'{name}.png'))
    print('bootstrap kit exported')
