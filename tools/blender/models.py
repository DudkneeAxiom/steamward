"""Voxel models for STEAMWARD.

Every figure is built from unit cubes and faces +X. Silhouette is doing the
work here: a spearman must read as a spearman at 36 pixels tall, so weapons
are oversized, shields are slabs, and steam gear is a real backpack with a
gauge on it — machinery that visibly does a job, never decoration.
"""

import math
from lib import box, group

R = math.radians

# ---------------------------------------------------------------- infantry


def _legs(g, pose, mat='dark'):
    """pose: 0 stand, 1 left leg forward, 2 right leg forward."""
    swing = {0: (0.0, 0.0), 1: (0.7, -0.7), 2: (-0.7, 0.7)}[pose]
    box(swing[0], -0.75, 0, 0.9, 0.9, 3.1, mat, g)
    box(swing[1], 0.75, 0, 0.9, 0.9, 3.1, mat, g)


def _torso(g, z=3.1, cloth='cloth'):
    box(0, 0, z, 1.7, 2.5, 3.0, cloth, g)
    box(0, 0, z, 1.8, 2.6, 0.5, 'leather', g)          # belt at the waist
    box(0, 0, z + 2.6, 1.9, 3.0, 0.5, 'leather', g)    # shoulder yoke


def _head(g, z=6.1, helmet='steel'):
    box(0, 0, z, 1.5, 1.5, 1.5, 'skin', g)
    if helmet:
        box(0, 0, z + 1.2, 1.8, 1.8, 0.8, helmet, g)


def _arms(g, pose, z=3.6, cloth='cloth', front_arm_x=0.0):
    swing = {0: (0.0, 0.0), 1: (-0.5, 0.5), 2: (0.5, -0.5)}[pose]
    box(swing[0] + front_arm_x, -1.55, z, 0.9, 0.8, 2.4, cloth, g)
    box(swing[1], 1.55, z, 0.9, 0.8, 2.4, cloth, g)


def _base_infantry(g, pose, helmet='steel'):
    _legs(g, pose)
    _torso(g, 3.1)
    _arms(g, pose)
    _head(g, 6.1, helmet)


def levy(pose):
    g = group('levy')
    _base_infantry(g, pose, helmet=None)
    box(0, 0, 7.3, 1.7, 1.7, 0.5, 'leather', g)        # felt cap, not a helm
    # hatchet: short haft, broad head
    box(1.1, -1.7, 3.4, 0.35, 0.35, 2.6, 'wood', g)
    box(1.1, -1.7, 5.7, 0.9, 0.4, 0.8, 'steel', g)
    # small round shield strapped to the off arm
    box(0.5, 1.9, 4.0, 0.35, 1.8, 1.8, 'wood_pale', g)
    return g


def spearman(pose):
    g = group('spearman')
    _base_infantry(g, pose)
    # spear: long haft angled forward, leaf head — the reason cavalry fears them
    box(1.5, -1.7, 1.4, 0.35, 0.35, 8.0, 'wood', g, rot=(0, R(12), 0))
    box(0.6, -1.7, 9.2, 0.5, 0.45, 1.2, 'steel', g, rot=(0, R(12), 0))
    box(0.6, 1.9, 3.6, 0.35, 1.6, 2.6, 'wood_pale', g)
    return g


def shieldman(pose):
    g = group('shieldman')
    _base_infantry(g, pose)
    # heavy board: a slab the unit hides behind
    box(1.5, 0.1, 2.2, 0.45, 3.2, 4.6, 'wood_pale', g)
    box(1.75, 0.1, 4.0, 0.25, 1.1, 1.1, 'steel', g)     # boss
    box(1.75, 0.1, 2.3, 0.25, 3.0, 0.3, 'steel', g)     # rim bands
    box(1.75, 0.1, 6.4, 0.25, 3.0, 0.3, 'steel', g)
    box(0.2, -1.8, 4.2, 0.35, 0.35, 2.6, 'steel', g)    # short sword
    return g


def bowman(pose):
    g = group('bowman')
    _base_infantry(g, pose, helmet=None)
    box(0, 0, 7.3, 1.7, 1.7, 0.5, 'leather', g)
    # longbow: three segments approximating the limb curve
    box(1.5, -1.4, 2.6, 0.3, 0.35, 3.0, 'wood_pale', g, rot=(R(-14), 0, 0))
    box(1.5, -1.0, 5.4, 0.3, 0.35, 2.6, 'wood_pale', g, rot=(R(16), 0, 0))
    box(1.5, -1.2, 1.6, 0.3, 0.35, 1.2, 'wood_pale', g, rot=(R(24), 0, 0))
    box(-1.3, 0.9, 3.8, 0.7, 0.7, 2.4, 'leather', g)    # quiver
    box(-1.3, 0.9, 6.0, 0.5, 0.5, 0.9, 'steel', g)      # arrow nocks
    return g


def pressurebow(pose):
    """The signature unit. Every mechanical part has a job: reservoir stores
    pressure, hose carries it, carriage draws the string, gauge reads it."""
    g = group('pressurebow')
    _base_infantry(g, pose)
    # back-mounted pressure reservoir + brass gauge
    box(-1.5, 0, 3.4, 1.5, 2.0, 2.8, 'iron', g)
    box(-1.5, 0, 6.2, 1.6, 2.1, 0.4, 'dark', g)
    box(-1.5, -1.1, 5.0, 0.6, 0.4, 0.6, 'brass', g)     # gauge face
    box(-1.5, 1.1, 4.4, 0.5, 0.4, 0.5, 'brass', g)      # release valve
    # hose running from reservoir to the draw carriage
    box(-0.6, -1.3, 4.6, 1.6, 0.3, 0.3, 'dark', g)
    box(0.6, -1.3, 4.1, 0.3, 0.3, 1.2, 'dark', g)
    # reinforced bow arms — thicker and steel-shod
    box(1.6, -1.3, 2.8, 0.45, 0.5, 3.2, 'steel', g, rot=(R(-16), 0, 0))
    box(1.6, -0.8, 5.8, 0.45, 0.5, 2.4, 'steel', g, rot=(R(18), 0, 0))
    # draw carriage on the stock
    box(1.0, -1.3, 3.5, 1.4, 0.6, 0.7, 'brass', g)
    box(0.4, -1.3, 3.6, 0.5, 0.5, 0.5, 'steel', g)
    return g


def hero(pose):
    """A commander, not a superhero: crest, cloak, back banner, plain sword."""
    g = group('hero')
    _legs(g, pose, 'dark')
    _torso(g, 3.2)
    _arms(g, pose, 3.7)
    _head(g, 6.3, 'steel')
    box(0, 0, 7.6, 1.0, 2.2, 0.6, 'brass', g)           # helmet crest
    box(-1.0, 0, 3.4, 0.4, 3.0, 3.4, 'cloth', g)        # cloak
    # back banner on a stave
    box(-1.5, 0, 4.0, 0.3, 0.3, 5.4, 'wood', g)
    box(-1.5, -0.2, 7.6, 0.25, 2.6, 2.0, 'cloth', g)
    box(-1.5, -0.2, 9.6, 0.3, 0.4, 0.4, 'brass', g)
    # sword held out
    box(1.4, -1.7, 4.2, 0.3, 0.3, 3.4, 'steel', g, rot=(0, R(24), 0))
    box(1.1, -1.7, 4.0, 0.35, 1.2, 0.35, 'brass', g)    # crossguard
    return g


# ---------------------------------------------------------------- cavalry


def _horse(g, pose, body='horse', leg='horse_dk', barding=None):
    gait = {0: (0.0, 0.0), 1: (0.6, -0.6), 2: (-0.6, 0.6)}[pose]
    box(0, 0, 2.6, 4.4, 1.8, 2.0, body, g)              # barrel
    box(2.3, 0, 3.2, 1.0, 1.2, 1.6, body, g)            # neck
    box(2.9, 0, 4.2, 1.6, 1.1, 0.9, body, g)            # head
    box(3.5, 0, 4.5, 0.5, 0.9, 0.5, 'dark', g)          # muzzle
    box(2.6, 0, 4.9, 0.4, 0.9, 0.5, body, g)            # ears/mane
    box(-2.3, 0, 3.6, 0.6, 0.5, 1.2, leg, g, rot=(0, R(35), 0))   # tail
    for i, (dx, dy) in enumerate([(1.6, -0.7), (1.6, 0.7), (-1.6, -0.7), (-1.6, 0.7)]):
        box(dx + gait[i % 2], dy, 0, 0.7, 0.7, 2.6, leg, g)
    if barding:
        box(0, 0, 2.4, 4.2, 2.0, 1.4, barding, g)       # flank plates
        box(2.9, 0, 4.2, 1.7, 1.2, 1.0, barding, g)     # chamfron


def _rider_seat(g, cloth='cloth'):
    box(0, 0, 4.6, 1.6, 2.3, 2.6, cloth, g)
    box(0, 0, 4.6, 1.7, 2.4, 0.4, 'leather', g)
    box(0.2, -1.4, 4.9, 0.8, 0.7, 2.0, cloth, g)
    box(0.2, 1.4, 4.9, 0.8, 0.7, 2.0, cloth, g)
    box(0, 0, 7.2, 1.4, 1.4, 1.4, 'skin', g)
    box(0, 0, 8.3, 1.7, 1.7, 0.7, 'steel', g)
    box(0, -1.0, 2.6, 0.7, 0.7, 2.0, 'leather', g)   # legs astride the barrel
    box(0, 1.0, 2.6, 0.7, 0.7, 2.0, 'leather', g)


def rider(pose):
    g = group('rider')
    _horse(g, pose)
    _rider_seat(g)
    box(1.4, -1.5, 5.6, 0.3, 0.3, 2.8, 'steel', g, rot=(0, R(35), 0))  # sabre
    box(0.6, 1.7, 5.2, 0.3, 1.6, 1.6, 'wood_pale', g)                  # buckler
    return g


def boilerlancer(pose):
    """Heavy horse with a back boiler driving a piston-braced lance."""
    g = group('boilerlancer')
    _horse(g, pose, body='horse_dk', leg='dark', barding='iron')
    _rider_seat(g)
    # compact boiler slung behind the saddle, with stack and valve
    box(-1.4, 0, 5.0, 1.4, 1.9, 2.4, 'iron', g)
    box(-1.4, 0, 7.4, 1.5, 2.0, 0.4, 'dark', g)
    box(-1.4, -0.9, 7.8, 0.5, 0.5, 1.0, 'dark', g)      # exhaust stack
    box(-1.4, 0.9, 6.4, 0.5, 0.4, 0.5, 'brass', g)      # valve
    # lance: braced to the shoulder, couched forward
    box(2.6, -1.5, 5.6, 7.0, 0.4, 0.4, 'wood_pale', g, rot=(0, R(-6), 0))
    box(6.2, -1.5, 5.9, 1.2, 0.55, 0.55, 'steel', g, rot=(0, R(-6), 0))
    box(1.0, -1.5, 5.5, 0.8, 0.7, 0.7, 'brass', g)      # piston brace
    box(0.2, -1.5, 5.2, 1.0, 0.4, 0.4, 'dark', g)       # linkage to boiler
    return g


def banner(pose):
    """Faction marker planted on the strategic map — cloth takes the tint."""
    g = group('banner')
    box(0, 0, 0, 1.4, 1.4, 0.4, 'stone', g)
    box(0, 0, 0.4, 0.35, 0.35, 7.0, 'wood', g)
    box(0.1, 0, 4.8, 0.25, 2.8, 2.4, 'cloth', g)
    box(0, 0, 7.4, 0.5, 0.5, 0.5, 'brass', g)
    return g


UNITS = {
    'levy': levy, 'spearman': spearman, 'shieldman': shieldman,
    'bowman': bowman, 'pressurebow': pressurebow, 'hero': hero,
    'rider': rider, 'boilerlancer': boilerlancer, 'banner': banner,
}

# ---------------------------------------------------------------- scenery


def tree_pine():
    g = group('tree_pine')
    box(0, 0, 0, 0.9, 0.9, 2.6, 'wood', g)
    box(0, 0, 2.2, 4.4, 4.4, 1.6, 'foliage', g)
    box(0, 0, 3.6, 3.4, 3.4, 1.6, 'foliage2', g)
    box(0, 0, 5.0, 2.2, 2.2, 1.5, 'foliage', g)
    box(0, 0, 6.3, 1.1, 1.1, 1.1, 'foliage2', g)
    return g


def tree_round():
    g = group('tree_round')
    box(0, 0, 0, 1.0, 1.0, 3.0, 'wood', g)
    box(0, 0, 2.6, 4.6, 4.6, 2.6, 'foliage', g)
    box(0, 0, 5.0, 3.2, 3.2, 1.4, 'foliage2', g)
    box(-1.4, 0.6, 3.0, 1.6, 1.6, 1.6, 'foliage2', g)
    return g


def rock():
    g = group('rock')
    box(0, 0, 0, 3.0, 2.6, 1.4, 'stone', g)
    box(0.6, -0.4, 1.4, 1.8, 1.6, 1.0, 'stone_lit', g)
    box(-1.4, 0.6, 0, 1.4, 1.2, 0.8, 'stone', g)
    return g


def spoil():
    g = group('spoil')
    box(0, 0, 0, 3.4, 2.8, 0.9, 'coal', g)
    box(0.3, 0, 0.9, 2.0, 1.6, 0.8, 'coal', g)
    box(-1.6, 0.7, 0, 1.2, 1.0, 0.5, 'soot', g)
    return g


def cart():
    g = group('cart')
    box(0, 0, 1.0, 4.0, 2.2, 1.4, 'wood', g)
    box(0, 0, 2.4, 3.6, 1.9, 0.5, 'coal', g)
    for dx in (1.3, -1.3):
        box(dx, -1.3, 0, 1.4, 0.35, 1.4, 'wood_pale', g)
        box(dx, 1.3, 0, 1.4, 0.35, 1.4, 'wood_pale', g)
    box(2.6, 0, 1.6, 1.6, 0.4, 0.3, 'wood', g)          # shafts
    return g


def boiler():
    """Industrial-site boiler: riveted drum, stack, pressure valve."""
    g = group('boiler')
    box(0, 0, 0, 3.4, 3.4, 0.5, 'stone', g)
    box(0, 0, 0.5, 3.0, 3.0, 3.6, 'iron', g)
    box(0, 0, 1.2, 3.2, 3.2, 0.35, 'dark', g)           # rivet bands
    box(0, 0, 2.6, 3.2, 3.2, 0.35, 'dark', g)
    box(0, 0, 4.1, 3.2, 3.2, 0.4, 'dark', g)
    box(-0.8, 0, 4.5, 1.0, 1.0, 2.2, 'soot', g)         # stack
    box(1.1, 0, 4.5, 0.6, 0.6, 0.7, 'brass', g)         # relief valve
    box(1.7, -1.2, 1.4, 0.4, 0.4, 2.0, 'dark', g)       # feed pipe
    return g


def shed():
    g = group('shed')
    box(0, 0, 0, 5.0, 4.0, 3.0, 'wood', g)
    box(0, 0, 3.0, 5.6, 4.6, 0.6, 'soot', g)
    box(0, 0, 3.6, 4.2, 3.4, 0.6, 'soot', g)
    box(2.55, 0, 0, 0.3, 1.6, 2.2, 'dark', g)           # doorway
    return g


def house():
    g = group('house')
    box(0, 0, 0, 5.4, 4.4, 3.2, 'canvas', g)
    box(0, 0, 0, 5.6, 4.6, 0.6, 'stone', g)             # stone footing
    box(0, 0, 3.2, 6.0, 5.0, 0.7, 'roof', g)
    box(0, 0, 3.9, 4.6, 3.6, 0.7, 'roof', g)
    box(0, 0, 4.6, 3.0, 2.2, 0.7, 'roof', g)
    box(1.6, -2.3, 4.0, 1.0, 0.9, 1.8, 'stone', g)      # chimney
    box(2.75, 0, 0, 0.25, 1.4, 2.0, 'wood', g)          # door
    box(0.5, -2.25, 1.6, 1.0, 0.2, 1.0, 'dark', g)      # window
    return g


def hall():
    """Foundry hall: long workshop with two stacks and external pipework."""
    g = group('hall')
    box(0, 0, 0, 8.0, 5.0, 3.6, 'stone', g)
    box(0, 0, 3.6, 8.6, 5.6, 0.7, 'soot', g)
    box(0, 0, 4.3, 6.4, 4.2, 0.6, 'soot', g)
    box(-2.4, 0, 4.9, 1.6, 1.6, 4.0, 'soot', g)         # tall stack
    box(-2.4, 0, 8.9, 1.9, 1.9, 0.5, 'dark', g)
    box(1.8, 0, 4.9, 1.2, 1.2, 2.6, 'soot', g)          # short stack
    box(4.2, 0, 0.8, 0.5, 0.5, 3.0, 'dark', g)          # riser pipe
    box(4.2, 0, 3.8, 3.0, 0.5, 0.5, 'dark', g)          # header
    box(4.2, -1.6, 1.6, 0.7, 0.7, 0.7, 'brass', g)      # valve wheel
    box(3.1, -2.6, 0, 1.4, 0.5, 2.0, 'iron', g)         # furnace door
    return g


def headframe():
    """Coal workings: pit head gantry with winding wheel."""
    g = group('headframe')
    box(0, 0, 0, 4.4, 4.0, 0.5, 'dirt', g)
    box(-1.6, -1.6, 0.5, 0.5, 0.5, 6.0, 'wood', g, rot=(0, R(-7), 0))
    box(1.6, -1.6, 0.5, 0.5, 0.5, 6.0, 'wood', g, rot=(0, R(7), 0))
    box(-1.6, 1.6, 0.5, 0.5, 0.5, 6.0, 'wood', g, rot=(0, R(-7), 0))
    box(1.6, 1.6, 0.5, 0.5, 0.5, 6.0, 'wood', g, rot=(0, R(7), 0))
    box(0, 0, 6.4, 3.2, 3.6, 0.6, 'wood_pale', g)
    box(0, 0, 7.0, 0.4, 2.4, 2.4, 'iron', g)            # winding wheel
    box(0, 0, 8.1, 0.6, 0.6, 0.6, 'brass', g)
    box(0, 0, 0.5, 2.2, 2.2, 0.4, 'coal', g)            # the shaft mouth
    return g


def tent():
    g = group('tent')
    box(0, 0, 0, 3.6, 3.2, 1.6, 'canvas', g)
    box(0, 0, 1.6, 2.6, 2.4, 1.0, 'canvas', g)
    box(0, 0, 2.6, 1.4, 1.4, 0.8, 'canvas', g)
    box(0, 0, 3.4, 0.3, 0.3, 1.2, 'wood', g)
    box(1.85, 0, 0, 0.2, 1.2, 1.6, 'dark', g)           # flap opening
    return g


def tower():
    g = group('tower')
    box(0, 0, 0, 3.4, 3.4, 8.0, 'stone', g)
    box(0, 0, 0, 3.8, 3.8, 0.8, 'stone_lit', g)
    box(0, 0, 8.0, 4.0, 4.0, 0.7, 'stone_lit', g)
    for dx, dy in ((-1.5, -1.5), (1.5, -1.5), (-1.5, 1.5), (1.5, 1.5), (0, -1.7), (0, 1.7)):
        box(dx, dy, 8.7, 0.9, 0.9, 0.9, 'stone', g)     # merlons
    box(0, -1.75, 4.4, 0.7, 0.2, 1.2, 'dark', g)        # window slit
    return g


def wall():
    """One segment of a north-south curtain wall. The battlefield stacks these
    along the depth axis, so the long axis runs in Y and X is the thickness."""
    g = group('wall')
    box(0, 0, 0, 2.8, 3.4, 5.2, 'stone', g)
    box(0, 0, 0, 3.0, 3.6, 0.7, 'stone_lit', g)          # plinth
    box(0, 0, 5.2, 3.2, 3.6, 0.6, 'stone_lit', g)        # wall walk
    box(-1.3, 0, 5.8, 0.6, 3.6, 0.9, 'stone', g)         # outer parapet
    box(1.3, 0, 5.8, 0.6, 3.6, 0.5, 'stone', g)          # inner kerb
    box(-1.3, 0, 6.7, 0.6, 1.4, 0.7, 'stone', g)         # merlon
    return g


def gatehouse():
    g = group('gatehouse')
    box(-2.2, 0, 0, 2.0, 2.6, 6.4, 'stone', g)
    box(2.2, 0, 0, 2.0, 2.6, 6.4, 'stone', g)
    box(0, 0, 5.0, 6.4, 2.6, 1.4, 'stone', g)
    box(0, 0, 6.4, 6.6, 2.8, 0.6, 'stone_lit', g)
    box(0, 0, 0, 2.6, 2.2, 4.6, 'wood', g)              # timber gate leaves
    box(0, -1.15, 1.2, 2.6, 0.2, 0.3, 'iron', g)
    box(0, -1.15, 3.2, 2.6, 0.2, 0.3, 'iron', g)
    # steam winch that actually raises the gate
    box(-2.2, -1.5, 6.4, 1.2, 1.2, 1.4, 'iron', g)
    box(-2.2, -1.5, 7.8, 0.5, 0.5, 0.5, 'brass', g)
    box(0, -1.5, 6.8, 3.4, 0.3, 0.3, 'dark', g)         # chain drum shaft
    return g


def keep():
    g = group('keep')
    box(0, 0, 0, 9.0, 7.0, 7.0, 'stone', g)
    box(0, 0, 0, 9.4, 7.4, 0.9, 'stone_lit', g)
    box(0, 0, 7.0, 9.4, 7.4, 0.7, 'stone_lit', g)
    for dx in (-3.6, -1.2, 1.2, 3.6):
        box(dx, -3.4, 7.7, 1.2, 1.0, 1.0, 'stone', g)
        box(dx, 3.4, 7.7, 1.2, 1.0, 1.0, 'stone', g)
    box(-4.4, -3.4, 0, 2.6, 2.6, 10.0, 'stone', g)      # corner turrets
    box(4.4, -3.4, 0, 2.6, 2.6, 10.0, 'stone', g)
    box(-4.4, -3.4, 10.0, 3.0, 3.0, 0.7, 'stone_lit', g)
    box(4.4, -3.4, 10.0, 3.0, 3.0, 0.7, 'stone_lit', g)
    box(0, -3.6, 0, 2.2, 0.4, 3.4, 'wood', g)           # door
    box(-2.4, -3.55, 4.4, 0.8, 0.2, 1.4, 'dark', g)
    box(2.4, -3.55, 4.4, 0.8, 0.2, 1.4, 'dark', g)
    return g


def stall():
    g = group('stall')
    box(0, 0, 0, 3.4, 2.4, 1.6, 'wood', g)
    box(0, 0, 1.6, 3.8, 2.8, 0.4, 'wood_pale', g)
    for dx in (-1.5, 1.5):
        box(dx, -1.2, 2.0, 0.25, 0.25, 2.0, 'wood', g)
        box(dx, 1.2, 2.0, 0.25, 0.25, 2.0, 'wood', g)
    box(0, 0, 4.0, 4.2, 3.2, 0.4, 'roof', g)
    box(0, 0, 1.8, 2.0, 1.4, 0.5, 'thatch', g)          # goods on the counter
    return g


def fence():
    g = group('fence')
    for dx in (-2.0, 0.0, 2.0):
        box(dx, 0, 0, 0.35, 0.35, 1.8, 'wood', g)
    box(0, 0, 1.1, 4.4, 0.25, 0.3, 'wood_pale', g)
    box(0, 0, 0.5, 4.4, 0.25, 0.3, 'wood_pale', g)
    return g


# (builder, scale). Scale sets how the piece reads against a 36px soldier:
# a house is roughly a soldier and a half, a keep towers over everything.
# Frame sizes are measured from the geometry at render time, so growing a
# model never silently clips it.
PROPS = {
    'tree_pine': (tree_pine, 2.4),
    'tree_round': (tree_round, 2.5),
    'rock': (rock, 1.5),
    'spoil': (spoil, 2.0),
    'cart': (cart, 1.6),
    'boiler': (boiler, 1.65),
    'shed': (shed, 2.1),
    'house': (house, 2.2),
    'hall': (hall, 1.9),
    'headframe': (headframe, 1.9),
    'tent': (tent, 1.7),
    'tower': (tower, 2.05),
    'wall': (wall, 1.8),
    'gatehouse': (gatehouse, 2.1),
    'keep': (keep, 2.3),
    'stall': (stall, 1.7),
    'fence': (fence, 2.8),
}
