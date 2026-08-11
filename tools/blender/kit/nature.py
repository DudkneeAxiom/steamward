"""STEAMWARD nature kit — vegetation, boulders and terrain edges.

These are the cheapest assets in the game and the most numerous: a forest is
thousands of instances, so every mass here has to earn its triangles. The rule
followed throughout is *silhouette first* — a tree is recognised at RTS
distance by its outline against the ground, not by its detail.

    tree_pine_a/b/c     conifers, 74-108 tall, stacked tapered canopy skirts
    tree_broad_a/b/c    broadleaf, forked trunks, 3-6 overlapping crown lobes
    tree_dead           bare leaning trunk and snapped branch stubs
    sapling             a young broadleaf, knee-high to a wall
    bush_a/b            low scrub, one rounded and one sprawling
    stump               a felled trunk with a pale sawn face and root flare
    rock_a/b/c          angular boulders, faceted, three sizes
    rock_outcrop        bedded formation with a vertical face and ledges
    cliff_face_segment  60-long tile for the edge of raised terrain
    reeds, grass_tuft   riverbank and field scatter, dirt cheap
    log, fallen_tree    deadfall

Shape vocabulary
----------------
common.py gives rectangular masses; trees are not rectangular. Rather than
invent new *materials* this module composes three cheap organic solids on top
of common's primitives and mesh data:

    frustum()  a box whose top face is scaled and slid — conifer skirts,
               tapered trunks, leaning boles, strata slabs.  12 tris
    gem()      a ring of verts pinched to an apex above and below — crown
               lobes and bushes. Reads round, costs the same as a cube. 12 tris
    boulder()  ring + flat base ngon — rock that sits on the ground. 22 tris
    spike()    a tetrahedron — one blade of grass or one reed. 4 tris
    limb()     a tapered square bar between two points — branches, roots

Every asset is seeded from a fixed number, so a rebuild is byte-stable and a
variant keeps its personality between runs.

Placement contract (see common.py): origin on the ground at the footprint
centre. Organic pieces are allowed a unit or two of geometry below z=0 so they
bed into uneven terrain instead of hovering on the high side of a slope.
"""

import math
import os
import random

import bpy
import bmesh
from mathutils import Vector

import common as C

R = math.radians


# ------------------------------------------------------------------- solids

def _mesh(name, verts, faces, material, parent=None, loc=(0.0, 0.0, 0.0),
          rot=None):
    """Raw mesh with flat shading, outward normals and common's materials."""
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    ob.location = loc
    if rot:
        ob.rotation_euler = rot
    me.materials.append(C.mat(material))
    for p in me.polygons:
        p.use_smooth = False
    if parent:
        ob.parent = parent
        ob.matrix_parent_inverse = parent.matrix_world.inverted()
    return ob


def frustum(x, y, z, w0, d0, w1, d1, h, material, parent=None, yaw=0.0,
            shift=(0.0, 0.0), jit=0.0, rng=None, name=None):
    """A box with an independently sized, independently placed top face.

    Wide bottom + narrow top is a conifer skirt or a tapered trunk; equal
    footprints plus a sideways `shift` is a leaning bole. 12 tris either way.
    """
    ob = C.box(x, y, z, w0, d0, h, material, parent, name=name)
    fx = (w1 / w0) if w0 else 1.0
    fy = (d1 / d0) if d0 else 1.0
    sx = shift[0] / w0 if w0 else 0.0
    sy = shift[1] / d0 if d0 else 0.0
    for v in ob.data.vertices:
        if v.co.z > 0:
            v.co.x = v.co.x * fx + sx
            v.co.y = v.co.y * fy + sy
        if jit and rng:
            v.co.x += rng.uniform(-jit, jit) / w0
            v.co.y += rng.uniform(-jit, jit) / d0
            v.co.z += rng.uniform(-jit, jit) / h
    if yaw:
        ob.rotation_euler = (0.0, 0.0, yaw)
    return ob


def gem(x, y, z, rx, ry, h, material, parent=None, sides=6, ring=0.40,
        bz=0.0, lean=(0.0, 0.0), phase=0.0, jit=0.0, rng=None, name='gem'):
    """A ring of verts pinched to an apex top and bottom — a chunky rounded
    lobe. `ring` is where the widest girth sits as a fraction of h, `lean`
    slides the apex sideways so a crown lobe can reach for the light."""
    vs = []
    for i in range(sides):
        a = phase + i * math.tau / sides
        jr = 1.0 + (rng.uniform(-jit, jit) if (jit and rng) else 0.0)
        jz = (rng.uniform(-jit, jit) * h * 0.5) if (jit and rng) else 0.0
        vs.append((x + math.cos(a) * rx * jr,
                   y + math.sin(a) * ry * jr,
                   z + ring * h + jz))
    top = len(vs)
    vs.append((x + lean[0], y + lean[1], z + h))
    bot = len(vs)
    vs.append((x + lean[0] * 0.2, y + lean[1] * 0.2, z + bz))
    faces = []
    for i in range(sides):
        j = (i + 1) % sides
        faces.append((i, j, top))
        faces.append((j, i, bot))
    return _mesh(name, vs, faces, material, parent)


def boulder(x, y, z, rx, ry, h, material, parent=None, sides=6, ring=0.42,
            base=0.66, sink=1.2, phase=0.0, tip=(0.0, 0.0), jit=0.22,
            rng=None, name='rock'):
    """Angular rock: a flat bedded base, a girth ring, a tilted apex. Faceted
    on purpose — this is a boulder, never a sphere. 22 tris."""
    rng = rng or random.Random(0)
    lo, mid = [], []
    for i in range(sides):
        a = phase + i * math.tau / sides
        jr = 1.0 + rng.uniform(-jit, jit)
        jb = 1.0 + rng.uniform(-jit, jit)
        lo.append((x + math.cos(a) * rx * base * jb,
                   y + math.sin(a) * ry * base * jb, z - sink))
        mid.append((x + math.cos(a) * rx * jr,
                    y + math.sin(a) * ry * jr,
                    z + ring * h * (1.0 + rng.uniform(-jit, jit))))
    vs = lo + mid
    vs.append((x + tip[0], y + tip[1], z + h))
    top = len(vs) - 1
    faces = [tuple(range(sides - 1, -1, -1))]          # bedded base
    for i in range(sides):
        j = (i + 1) % sides
        faces.append((i, j, sides + j, sides + i))
        faces.append((sides + i, sides + j, top))
    return _mesh(name, vs, faces, material, parent)


def spike(x, y, rb, h, material, parent=None, lean=(0.0, 0.0), phase=0.0,
          name='blade'):
    """One blade: a triangular pyramid, 4 tris. The cheapest thing that still
    has a silhouette."""
    vs = []
    for i in range(3):
        a = phase + i * math.tau / 3.0
        vs.append((x + math.cos(a) * rb, y + math.sin(a) * rb, -0.4))
    vs.append((x + lean[0], y + lean[1], h))
    return _mesh(name, vs, [(0, 1, 2), (0, 1, 3), (1, 2, 3), (2, 0, 3)],
                 material, parent)


def limb(parent, p0, p1, r0, r1, material, name='limb'):
    """A tapered square bar from p0 to p1 — branch, root flare, fork arm."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    L = max(d.length, 0.001)
    vs = [(-r0, -r0, 0), (r0, -r0, 0), (r0, r0, 0), (-r0, r0, 0),
          (-r1, -r1, L), (r1, -r1, L), (r1, r1, L), (-r1, r1, L)]
    faces = [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    rot = d.to_track_quat('Z', 'Y').to_euler()
    return _mesh(name, vs, faces, material, parent, loc=tuple(p0), rot=rot)


# --------------------------------------------------------------------- trees

def _conifer(name, seed, height, layers, base_w, trunk_r, lean, skirt_z,
             mats, taper=0.62, yaws=None):
    """Shared conifer body. `layers` tapered skirts stacked up a leaning bole.

    Each skirt is yawed off its neighbours so the stack never reads as one
    clean pyramid, and each is jittered so the lower edge is ragged. The bole
    leans by sliding the trunk's top face, which keeps the roots planted.
    """
    g = C.empty(name)
    rng = random.Random(seed)
    lx, ly = lean

    # bole — visible below the skirt, tapering and leaning as it climbs
    top = height * 0.94
    frustum(0, 0, -1.0, trunk_r * 2.0, trunk_r * 2.0,
            trunk_r * 0.75, trunk_r * 0.75, top + 1.0, 'trunk', g,
            shift=(lx, ly))
    # a root flare so the trunk meets the ground rather than stopping at it
    for i in range(3):
        a = rng.uniform(0, math.tau)
        limb(g, (0, 0, 3.0),
             (math.cos(a) * trunk_r * 2.1, math.sin(a) * trunk_r * 2.1, -1.5),
             trunk_r * 0.5, trunk_r * 0.34, 'trunk', 'root')

    yaws = yaws or [rng.uniform(-0.5, 0.5) for _ in range(layers)]
    span = height - skirt_z
    for i in range(layers):
        t = i / float(layers - 1) if layers > 1 else 0.0
        w = base_w * (1.0 - taper * t)
        z = skirt_z + span * (i / float(layers)) * 0.97
        lh = span / layers * (2.05 if i < layers - 1 else 2.6)
        topw = w * (0.50 if i < layers - 1 else 0.10)
        # each skirt sits on the lean line, and wobbles off it a little
        cx = lx * (z / height) + rng.uniform(-1.4, 1.4)
        cy = ly * (z / height) + rng.uniform(-1.4, 1.4)
        frustum(cx, cy, z,
                w * rng.uniform(0.94, 1.06), w * rng.uniform(0.94, 1.06),
                topw, topw, lh, mats[i % len(mats)], g,
                yaw=yaws[i % len(yaws)], jit=w * 0.055, rng=rng,
                name='skirt')
    return g


def tree_pine_a():
    """The standard forest conifer: four skirts, upright, dense."""
    return _conifer('tree_pine_a', 21, 92.0, 4, 30.0, 2.6, (1.5, -1.0),
                    17.0, ('foliage_a', 'foliage_b'),
                    yaws=(R(14), R(-31), R(21), R(-9)))


def tree_pine_b():
    """Tall and spare — a crowded-forest tree that raced its neighbours for
    light: five narrow skirts, long bare bole, spindly top."""
    return _conifer('tree_pine_b', 33, 108.0, 5, 23.0, 2.3, (-2.5, 1.5),
                    26.0, ('foliage_a', 'foliage_b'), taper=0.70,
                    yaws=(R(-8), R(26), R(-19), R(35), R(6)))


def tree_pine_c():
    """Short, fat and leaning: an edge-of-wood tree with room to spread. Three
    heavy skirts, wide as it is tall at the base."""
    return _conifer('tree_pine_c', 47, 74.0, 3, 38.0, 3.2, (6.5, -3.0),
                    11.0, ('foliage_b', 'foliage_c'), taper=0.50,
                    yaws=(R(24), R(-14), R(40)))


def _broadleaf(name, seed, trunk_h, trunk_r, lean, forks, lobes, mats,
               sides=6):
    """Shared broadleaf body.

    A broadleaf is read from its fork: the bole rises, splits into two or
    three limbs, and the crown lobes sit on the ends of those limbs rather
    than floating above the trunk. `forks` are (yaw, pitch, length, r) and
    `lobes` are (x, y, z, rx, ry, h, ring, lean_x, lean_y).
    """
    g = C.empty(name)
    rng = random.Random(seed)
    lx, ly = lean

    frustum(0, 0, -1.5, trunk_r * 2.0, trunk_r * 2.2,
            trunk_r * 1.25, trunk_r * 1.25, trunk_h + 1.5, 'trunk', g,
            shift=(lx, ly), name='bole')
    for i in range(4):
        a = i * math.tau / 4.0 + 0.4
        limb(g, (0, 0, 4.5),
             (math.cos(a) * trunk_r * 2.3, math.sin(a) * trunk_r * 2.3, -2.0),
             trunk_r * 0.62, trunk_r * 0.40, 'trunk', 'root')

    top = Vector((lx, ly, trunk_h))
    for yaw, pitch, ln, r in forks:
        d = Vector((math.cos(yaw) * math.cos(pitch),
                    math.sin(yaw) * math.cos(pitch), math.sin(pitch))) * ln
        limb(g, tuple(top), tuple(top + d), r, r * 0.55, 'trunk', 'fork')

    for (x, y, z, rx, ry, h, ring, lnx, lny) in lobes:
        gem(x, y, z, rx, ry, h, mats[rng.randrange(len(mats))], g,
            sides=sides, ring=ring, bz=-h * 0.30, lean=(lnx, lny),
            phase=rng.uniform(0, 1.0), jit=0.16, rng=rng, name='crown')
    return g


def tree_broad_a():
    """A full round-crowned oak — the default deciduous tree. Two-way fork,
    five overlapping lobes with one hanging lower on the west side."""
    return _broadleaf(
        'tree_broad_a', 101, 30.0, 3.6, (1.5, 1.0),
        forks=((R(160), R(62), 22.0, 3.0),
               (R(-25), R(70), 26.0, 3.2),
               (R(75), R(66), 17.0, 2.2)),
        lobes=((2, 1, 42, 22, 20, 34, 0.44, 1, 2),
               (-14, 6, 36, 17, 16, 26, 0.42, -3, 1),
               (13, -8, 39, 16, 15, 25, 0.40, 3, -2),
               (-2, -3, 55, 18, 17, 26, 0.46, 0, 0),
               (7, 9, 50, 14, 13, 21, 0.44, 2, 3)),
        mats=('foliage_b', 'foliage_c', 'foliage_b'))


def tree_broad_b():
    """Tall and one-sided: a tree that grew away from a neighbour. Long bole,
    the crown mass shoved east, one heavy limb reaching out low."""
    return _broadleaf(
        'tree_broad_b', 202, 44.0, 3.2, (-3.5, 2.0),
        forks=((R(10), R(58), 30.0, 2.8),
               (R(-150), R(74), 20.0, 2.2),
               (R(-40), R(28), 26.0, 2.4)),
        lobes=((10, 2, 58, 19, 17, 30, 0.44, 3, 0),
               (20, -3, 46, 15, 14, 23, 0.40, 4, -2),
               (2, 6, 68, 15, 14, 24, 0.48, -1, 2),
               (16, 8, 66, 12, 12, 19, 0.44, 2, 2),
               (-19, -8, 50, 13, 12, 20, 0.40, -4, -3)),
        mats=('foliage_b', 'foliage_c'))


def tree_broad_c():
    """Low and spreading — an open-field tree with nothing to compete with.
    Short thick bole, three-way fork close to the ground, a wide flat crown."""
    return _broadleaf(
        'tree_broad_c', 303, 21.0, 4.6, (2.0, -1.5),
        forks=((R(140), R(40), 30.0, 3.4),
               (R(-30), R(46), 32.0, 3.4),
               (R(45), R(58), 22.0, 2.6),
               (R(-110), R(52), 20.0, 2.4)),
        lobes=((-22, 14, 30, 19, 17, 22, 0.44, -4, 3),
               (24, -10, 31, 20, 18, 23, 0.44, 5, -2),
               (0, 0, 38, 20, 19, 24, 0.46, 0, 0),
               (12, 16, 28, 15, 14, 18, 0.42, 2, 4),
               (-11, -17, 27, 14, 14, 17, 0.42, -2, -4),
               (4, -2, 48, 13, 12, 16, 0.48, 1, 1)),
        mats=('foliage_b', 'foliage_c', 'foliage_c'))


def tree_dead():
    """Bare, angular and leaning, with the branches snapped short. Three bole
    sections kinked against each other so the trunk is never one straight
    line, and stubs that stop rather than taper away."""
    g = C.empty('tree_dead')
    rng = random.Random(404)
    # bole in three kinked sections, each leaning further east
    frustum(0, 0, -1.5, 8.0, 8.6, 6.4, 6.0, 26.0, 'deadwood', g,
            shift=(2.5, -1.0), name='bole0')
    frustum(2.5, -1.0, 24.0, 6.4, 6.0, 4.6, 4.4, 22.0, 'deadwood', g,
            shift=(3.5, 1.5), name='bole1')
    frustum(6.0, 0.5, 45.5, 4.6, 4.4, 1.6, 1.6, 20.0, 'deadwood', g,
            shift=(2.0, -1.0), name='bole2')
    for i in range(4):
        a = rng.uniform(0, math.tau)
        limb(g, (0, 0, 3.0), (math.cos(a) * 8.5, math.sin(a) * 8.5, -2.0),
             2.4, 1.5, 'deadwood', 'root')
    # snapped branches: (base z, yaw, pitch, length, r)
    for z, yaw, pitch, ln, r in ((22.0, R(200), R(34), 20.0, 2.1),
                                 (30.0, R(-15), R(26), 24.0, 2.3),
                                 (40.0, R(95), R(48), 15.0, 1.7),
                                 (48.0, R(-95), R(20), 17.0, 1.6),
                                 (55.0, R(150), R(52), 11.0, 1.3)):
        t = 2.5 + 3.5 * (z / 60.0) * 2.0
        p0 = Vector((t * 0.6, 0.0, z))
        d = Vector((math.cos(yaw) * math.cos(pitch),
                    math.sin(yaw) * math.cos(pitch), math.sin(pitch))) * ln
        limb(g, tuple(p0), tuple(p0 + d), r, r * 0.72, 'deadwood', 'branch')
        if ln > 18.0:                     # a second-order stub off the big two
            m = p0 + d * 0.62
            d2 = Vector((math.cos(yaw + 1.1) * 0.5,
                         math.sin(yaw + 1.1) * 0.5, 0.86)) * (ln * 0.45)
            limb(g, tuple(m), tuple(m + d2), r * 0.62, r * 0.42,
                 'deadwood', 'twig')
    return g


def sapling():
    """Waist-high on a soldier: a whippy stem and two small lobes."""
    g = C.empty('sapling')
    rng = random.Random(55)
    frustum(0, 0, -1.0, 2.0, 2.0, 1.1, 1.1, 15.0, 'trunk', g, shift=(1.2, 0.6))
    limb(g, (0.9, 0.4, 10.0), (-4.5, 2.0, 15.0), 0.8, 0.5, 'trunk', 'branch')
    gem(1.6, 0.8, 12.0, 7.0, 6.4, 11.0, 'foliage_c', g, ring=0.44, bz=-3.0,
        lean=(1.5, 0.5), jit=0.18, rng=rng, name='crown')
    gem(-4.0, 2.0, 13.5, 4.6, 4.4, 7.5, 'foliage_b', g, ring=0.42, bz=-2.0,
        jit=0.18, rng=rng, name='crown')
    return g


def bush_a():
    """A rounded shrub — three lobes, one clearly dominant."""
    g = C.empty('bush_a')
    rng = random.Random(66)
    gem(0, 0, 0, 10.0, 9.0, 14.0, 'foliage_b', g, ring=0.40, bz=-2.0,
        jit=0.20, rng=rng, name='mass')
    gem(-6.5, 3.5, 0, 6.4, 6.0, 9.5, 'foliage_a', g, ring=0.38, bz=-2.0,
        phase=0.7, jit=0.20, rng=rng, name='mass')
    gem(5.0, -4.5, 0, 5.6, 5.4, 8.0, 'foliage_c', g, ring=0.38, bz=-2.0,
        phase=1.4, jit=0.20, rng=rng, name='mass')
    return g


def bush_b():
    """Sprawling scrub — lower, wider, four lobes and a couple of bare shoots
    poking out of the top. Reads as a different plant, not a smaller bush_a."""
    g = C.empty('bush_b')
    rng = random.Random(77)
    for (x, y, rx, ry, h, m, ph) in ((-7.0, -2.0, 8.5, 7.5, 9.0, 'foliage_c', 0.0),
                                     (5.5, 4.0, 7.5, 7.0, 8.0, 'foliage_b', 0.6),
                                     (3.0, -6.5, 6.5, 6.0, 6.5, 'foliage_b', 1.2),
                                     (-2.0, 6.0, 5.5, 5.0, 5.5, 'foliage_a', 1.9)):
        gem(x, y, 0, rx, ry, h, m, g, ring=0.36, bz=-1.8, phase=ph,
            jit=0.22, rng=rng, name='mass')
    limb(g, (-6.0, -1.0, 6.0), (-9.5, -3.5, 13.5), 0.7, 0.35, 'trunk', 'shoot')
    limb(g, (4.0, 3.0, 5.5), (7.0, 6.5, 12.0), 0.7, 0.35, 'trunk', 'shoot')
    return g


def stump():
    """Felled, not rotted: a pale sawn face, a torn splinter left standing on
    one side, and roots flaring into the ground."""
    g = C.empty('stump')
    rng = random.Random(88)
    frustum(0, 0, -1.5, 11.0, 10.0, 8.4, 8.0, 8.0, 'trunk', g, name='bole')
    frustum(0, 0, 6.5, 8.4, 8.0, 8.2, 7.8, 0.9, 'timber_light', g, name='cut')
    frustum(2.6, -1.4, 7.0, 3.0, 2.6, 1.2, 1.0, 6.5, 'timber_light', g,
            shift=(0.8, 0.4), name='splinter')
    for i in range(5):
        a = i * math.tau / 5.0 + 0.3
        r = 6.0 + rng.uniform(0.0, 2.5)
        limb(g, (0, 0, 3.5),
             (math.cos(a) * r, math.sin(a) * r, -2.0), 2.0, 1.2,
             'trunk', 'root')
    return g


# --------------------------------------------------------------------- rock

def rock_a():
    """Waist-high boulder plus a shed flake leaning on it."""
    g = C.empty('rock_a')
    rng = random.Random(901)
    boulder(0, 0, 0, 12.0, 10.0, 15.0, 'stone', g, ring=0.46, base=0.70,
            tip=(-2.5, 1.5), phase=0.3, jit=0.24, rng=rng)
    boulder(9.0, -6.0, 0, 5.5, 5.0, 7.0, 'stone_dark', g, ring=0.40,
            base=0.75, tip=(1.5, -1.0), phase=1.1, jit=0.26, rng=rng)
    return g


def rock_b():
    """A single low stone, the one you scatter by the hundred."""
    g = C.empty('rock_b')
    rng = random.Random(902)
    boulder(0, 0, 0, 7.5, 6.0, 7.0, 'stone', g, sides=6, ring=0.44,
            base=0.78, tip=(1.2, 1.8), phase=0.8, jit=0.28, rng=rng)
    return g


def rock_c():
    """A tilted slab shouldering out of the ground, with rubble at its foot —
    the big one, taller than a soldier."""
    g = C.empty('rock_c')
    rng = random.Random(903)
    frustum(0, 0, -2.0, 20.0, 13.0, 13.0, 9.0, 23.0, 'stone_light', g,
            shift=(-6.0, 3.0), jit=1.1, rng=rng, name='slab')
    boulder(-1.0, -1.0, 0, 12.0, 9.0, 11.0, 'stone', g, ring=0.48, base=0.72,
            tip=(-3.0, 1.0), phase=0.5, jit=0.22, rng=rng)
    boulder(9.5, 5.0, 0, 5.0, 4.6, 5.5, 'stone_dark', g, ring=0.42,
            base=0.80, phase=1.7, jit=0.28, rng=rng)
    return g


def rock_outcrop():
    """Bedrock breaking the surface: a stack of strata sheared off to a
    vertical face looking -Y, stepping back in ledges toward +Y, with the
    debris that fell off it lying at the foot of the face."""
    g = C.empty('rock_outcrop')
    rng = random.Random(910)
    # strata: each bed thinner and set back further, the -Y edge kept sheer
    beds = ((0.0, 0.0, 56.0, 34.0, 11.0, 'stone_dark', 0.0),
            (1.5, 4.0, 52.0, 30.0, 9.0, 'stone', -1.0),
            (-1.0, 8.5, 47.0, 26.0, 8.0, 'stone_light', 1.0),
            (2.5, 13.0, 40.0, 21.0, 7.0, 'stone', 0.5),
            (0.5, 18.0, 30.0, 16.0, 6.5, 'stone_dark', -1.5))
    z = -2.0
    for (x, y, w, d, h, m, sh) in beds:
        frustum(x, y, z, w, d, w * 0.93, d * 0.90, h, m, g,
                shift=(sh, 1.5), jit=1.4, rng=rng, name='bed')
        z += h - 0.8
    # the sheer face itself — a buttress hanging below the upper beds
    frustum(-6.0, -13.0, -2.0, 22.0, 9.0, 19.0, 7.0, 27.0, 'stone', g,
            shift=(1.5, 2.0), jit=1.0, rng=rng, name='face')
    frustum(13.0, -11.0, -2.0, 14.0, 8.0, 12.0, 6.0, 19.0, 'stone_dark', g,
            shift=(-1.0, 1.5), jit=1.0, rng=rng, name='face')
    # a capstone perched on top, and topsoil in the sheltered ledge
    boulder(-3.0, 16.0, z - 1.0, 9.0, 7.5, 12.0, 'stone_light', g, ring=0.44,
            base=0.74, tip=(2.5, 2.0), phase=0.9, jit=0.24, rng=rng)
    frustum(4.0, 20.0, z - 2.5, 18.0, 11.0, 15.0, 9.0, 2.2, 'dirt', g,
            jit=0.6, rng=rng, name='topsoil')
    # talus: what has fallen off the face
    for (x, y, rx, h, m) in ((-20.0, -20.0, 6.0, 7.0, 'stone'),
                             (-9.0, -24.0, 4.5, 5.0, 'stone_dark'),
                             (7.0, -22.0, 5.5, 6.5, 'stone_light'),
                             (19.0, -17.0, 3.6, 4.0, 'stone')):
        boulder(x, y, 0, rx, rx * 0.85, h, m, g, ring=0.42, base=0.78,
                phase=rng.uniform(0, 1.0), jit=0.28, rng=rng)
    return g


def cliff_face_segment():
    """A 60-long tile for the edge of raised terrain.

    Runs along X, flush at x = -30 and x = +30 so tiles butt without a seam.
    The exposed face looks -Y; the rock body fills 0 <= y <= 20, which is the
    side buried in the hill. 60 tall. Horizontal beds of alternating stone
    give the strata, and the face steps in and out between beds so the
    silhouette from the side is a staircase, not a slab. Topsoil caps it.
    """
    g = C.empty('cliff_face_segment')
    rng = random.Random(920)
    # beds: (base z, height, front y, depth, material)
    beds = ((-2.0, 13.0, -3.0, 23.0, 'stone_dark'),
            (10.5, 11.0, 0.0, 20.0, 'stone'),
            (21.0, 9.0, -2.5, 22.5, 'stone_light'),
            (29.5, 12.0, 1.5, 18.5, 'stone'),
            (41.0, 10.0, -1.5, 21.5, 'stone_dark'),
            (50.5, 7.5, 0.5, 19.5, 'stone'))
    for (z, h, fy, dep, m) in beds:
        cy = fy + dep * 0.5
        frustum(0, cy, z, 60.0, dep, 60.0, dep * 0.96, h, m, g,
                shift=(0.0, 0.8), jit=0.0, name='bed')
    # vertical fracture — a chunk of the face that has parted from the rest
    frustum(-17.0, -1.5, -2.0, 17.0, 8.0, 14.0, 6.5, 34.0, 'stone', g,
            shift=(1.5, 1.5), jit=1.2, rng=rng, name='block')
    frustum(19.0, -2.5, -2.0, 13.0, 7.0, 11.0, 6.0, 22.0, 'stone_light', g,
            shift=(-1.0, 1.0), jit=1.2, rng=rng, name='block')
    # ledges: thin shelves projecting out of the face where a bed is harder
    for (x, z, w, dep, m) in ((-9.0, 20.0, 24.0, 7.0, 'stone_light'),
                              (16.0, 35.0, 20.0, 6.0, 'stone'),
                              (-21.0, 44.0, 15.0, 5.5, 'stone_dark')):
        frustum(x, -dep * 0.5 + 1.0, z, w, dep, w * 0.9, dep * 0.8, 3.0,
                m, g, jit=0.5, rng=rng, name='ledge')
    # topsoil lip: rock does not meet grass with a clean edge
    frustum(0, 8.0, 57.0, 60.0, 22.0, 60.0, 21.0, 3.2, 'dirt', g, name='soil')
    # scree that has come off the face and piled against its foot
    for (x, y, rx, h, m) in ((-24.0, -8.0, 5.5, 6.5, 'stone_dark'),
                             (-11.0, -10.0, 4.0, 4.5, 'stone'),
                             (3.0, -9.0, 6.0, 7.0, 'stone_light'),
                             (14.0, -11.0, 3.4, 4.0, 'stone'),
                             (25.0, -7.5, 4.6, 5.0, 'stone_dark')):
        boulder(x, y, 0, rx, rx * 0.8, h, m, g, ring=0.42, base=0.78,
                phase=rng.uniform(0, 1.0), jit=0.28, rng=rng)
    return g


# ------------------------------------------------------------------ scatter

def grass_tuft():
    """Five blades, 20 tris, thrown down by the thousand across a field."""
    g = C.empty('grass_tuft')
    rng = random.Random(1001)
    for i in range(5):
        a = i * math.tau / 5.0 + rng.uniform(-0.3, 0.3)
        r = rng.uniform(0.8, 2.6)
        spike(math.cos(a) * r, math.sin(a) * r, 1.0,
              rng.uniform(4.0, 7.5), 'grass', g,
              lean=(math.cos(a) * 2.4, math.sin(a) * 2.4),
              phase=a, name='blade')
    return g


def reeds():
    """Riverbank reeds — taller, straighter, gathered tighter than grass, with
    three seed heads so the clump reads as a plant and not as tall turf."""
    g = C.empty('reeds')
    rng = random.Random(1002)
    stalks = []
    for i in range(9):
        a = i * math.tau / 9.0 + rng.uniform(-0.2, 0.2)
        r = rng.uniform(0.5, 4.0)
        h = rng.uniform(11.0, 21.0)
        lean = (math.cos(a) * r * 0.55, math.sin(a) * r * 0.55)
        spike(math.cos(a) * r, math.sin(a) * r, 0.85, h,
              'foliage_c' if i % 2 else 'grass', g, lean=lean, phase=a,
              name='stalk')
        stalks.append((math.cos(a) * r + lean[0], math.sin(a) * r + lean[1], h))
    for (x, y, h) in sorted(stalks, key=lambda s: -s[2])[:3]:
        frustum(x, y, h - 3.5, 1.5, 1.5, 0.7, 0.7, 4.5, 'crop', g,
                name='head')
    return g


# ----------------------------------------------------------------- deadfall

def log():
    """A bucked length of trunk lying along X, with pale sawn ends."""
    g = C.empty('log')
    rng = random.Random(1101)
    C.cyl(0, 0, 3.6, 3.6, 27.0, 'trunk', g, verts=6,
          rot=(0, R(90), 0), name='bole')
    for sx in (-1, 1):
        C.cyl(sx * 13.6, 0, 3.6, 3.5, 0.9, 'timber_light', g, verts=6,
              rot=(0, R(90), 0), name='cut')
    limb(g, (4.0, 0.0, 5.0), (7.5, 5.5, 8.5), 1.2, 0.7, 'trunk', 'stub')
    boulder(-11.0, 5.5, 0, 3.0, 2.6, 3.0, 'stone_dark', g, ring=0.42,
            base=0.8, phase=0.5, jit=0.3, rng=rng)
    return g


def fallen_tree():
    """A whole tree down: root plate torn up at the west end, the bole kinked
    where it landed, branches snapped off short along its length."""
    g = C.empty('fallen_tree')
    rng = random.Random(1102)
    # root plate, standing on edge where the tree levered out of the ground
    frustum(-33.0, 0.0, -2.0, 5.0, 24.0, 4.0, 17.0, 20.0, 'dirt', g,
            shift=(-2.0, 0.0), jit=1.2, rng=rng, name='plate')
    for i in range(4):
        a = 0.5 + i * 1.3
        limb(g, (-32.0, 0.0, 7.0),
             (-31.0 + math.cos(a) * 3.0, math.sin(a) * 11.0,
              7.0 + math.sin(a) * 9.0), 1.4, 0.7, 'deadwood', 'root')
    # bole in two kinked sections, thick end at the root plate
    C.cyl(-16.0, 0.6, 5.2, 5.2, 32.0, 'deadwood', g, verts=6,
          rot=(0, R(90), R(4)), name='bole0')
    C.cyl(15.0, -1.2, 4.2, 4.2, 32.0, 'deadwood', g, verts=6,
          rot=(0, R(90), R(-7)), name='bole1')
    C.cyl(30.5, -2.6, 4.0, 3.9, 1.0, 'timber_light', g, verts=6,
          rot=(0, R(90), R(-7)), name='cut')
    for (x, y, z, yaw, pitch, ln, r) in ((-6.0, 0.0, 7.0, R(70), R(28), 15.0, 1.9),
                                         (4.0, 0.0, 7.5, R(-105), R(20), 13.0, 1.7),
                                         (18.0, -1.0, 6.5, R(55), R(40), 11.0, 1.4),
                                         (26.0, -2.0, 6.0, R(-70), R(34), 9.0, 1.2)):
        p0 = Vector((x, y, z))
        d = Vector((math.cos(yaw) * math.cos(pitch),
                    math.sin(yaw) * math.cos(pitch), math.sin(pitch))) * ln
        limb(g, tuple(p0), tuple(p0 + d), r, r * 0.7, 'deadwood', 'branch')
    return g


# ----------------------------------------------------------------------- build

ASSETS = {
    'tree_pine_a': tree_pine_a,
    'tree_pine_b': tree_pine_b,
    'tree_pine_c': tree_pine_c,
    'tree_broad_a': tree_broad_a,
    'tree_broad_b': tree_broad_b,
    'tree_broad_c': tree_broad_c,
    'tree_dead': tree_dead,
    'sapling': sapling,
    'bush_a': bush_a,
    'bush_b': bush_b,
    'stump': stump,
    'rock_a': rock_a,
    'rock_b': rock_b,
    'rock_c': rock_c,
    'rock_outcrop': rock_outcrop,
    'cliff_face_segment': cliff_face_segment,
    'reeds': reeds,
    'grass_tuft': grass_tuft,
    'log': log,
    'fallen_tree': fallen_tree,
}


def tri_count(root):
    n = 0
    stack = [root]
    while stack:
        ob = stack.pop()
        stack.extend(ob.children)
        if ob.type != 'MESH':
            continue
        for p in ob.data.polygons:
            n += max(0, len(p.vertices) - 2)
    return n


def _render_wide(root, path, width=1400, height=460, angle=22.0,
                 azimuth=0.0, margin=1.06):
    """Contact sheet render — the only way to judge whether the variants
    actually differ from one another rather than in isolation."""
    import mathutils
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 20
    scene.cycles.use_denoising = False
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.image_settings.file_format = 'PNG'
    try:
        scene.view_settings.view_transform = 'Standard'
    except (AttributeError, TypeError):
        pass
    w, d, h = C.bounds(root)
    span = max(w, h * width / float(height)) * margin

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
    sun.rotation_euler = (R(52), 0, R(-40))
    bpy.ops.object.camera_add()
    cam = bpy.context.object
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = span
    el, az = R(angle), R(azimuth)
    dist = span * 3
    cam.location = (dist * math.cos(el) * math.sin(az),
                    -dist * math.cos(el) * math.cos(az),
                    dist * math.sin(el) + h * 0.35)
    look = mathutils.Vector((0, 0, h * 0.45)) - mathutils.Vector(cam.location)
    cam.rotation_euler = look.to_track_quat('-Z', 'Y').to_euler()
    scene.camera = cam
    bpy.ops.mesh.primitive_plane_add(size=span * 4, location=(0, 0, -0.05))
    ground = bpy.context.object
    ground.data.materials.append(C.mat('grass'))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def lineup(names, path, spacing=None, **kw):
    """Build several assets side by side and render them in one image."""
    C.clear_scene()
    stage = C.empty('lineup')
    x = 0.0
    widths = []
    roots = []
    for n in names:
        r = ASSETS[n]()
        w, d, h = C.bounds(r)
        widths.append(w)
        roots.append(r)
    gap = spacing or (max(widths) * 0.35 + 8.0)
    total = sum(widths) + gap * (len(names) - 1)
    x = -total * 0.5
    for r, w in zip(roots, widths):
        r.parent = stage
        r.location = (x + w * 0.5, 0.0, 0.0)
        x += w + gap
    bpy.context.view_layer.update()
    _render_wide(stage, path, **kw)


def build_all(out_dir, preview_dir=None, only=None, sheets=True):
    report = []
    for name, fn in ASSETS.items():
        if only and name not in only:
            continue
        C.clear_scene()
        root = fn()
        bpy.context.view_layer.update()
        w, d, h = C.bounds(root)
        tris = tri_count(root)
        C.export_glb(root, os.path.join(out_dir, name + '.glb'))
        if preview_dir:
            C.preview_render(root, os.path.join(preview_dir, name + '.png'),
                             px=440, angle=24, azimuth=35)
        report.append((name, w, d, h, tris))
        print(f'{name:20s} {w:7.1f} x {d:6.1f} x {h:6.1f}   {tris:5d} tris')
    total = sum(r[4] for r in report)
    print(f'{"TOTAL":20s} {total:41d} tris')

    if preview_dir and sheets and not only:
        lineup(['tree_pine_a', 'tree_pine_b', 'tree_pine_c', 'tree_dead',
                'tree_broad_a', 'tree_broad_b', 'tree_broad_c'],
               os.path.join(preview_dir, '_sheet_trees.png'),
               width=1500, height=470)
        lineup(['sapling', 'bush_a', 'bush_b', 'stump', 'grass_tuft',
                'reeds', 'log', 'fallen_tree'],
               os.path.join(preview_dir, '_sheet_small.png'),
               width=1500, height=380, angle=26)
        lineup(['rock_b', 'rock_a', 'rock_c', 'rock_outcrop',
                'cliff_face_segment'],
               os.path.join(preview_dir, '_sheet_rock.png'),
               width=1500, height=520, angle=20)
    return report


if __name__ == '__main__':
    build_all('/home/user/steamward/assets/models/nature', '/tmp/prev-nature')
