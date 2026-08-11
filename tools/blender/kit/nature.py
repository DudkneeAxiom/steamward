"""STEAMWARD nature kit — vegetation, boulders and terrain edges.

These are the cheapest assets in the game and the most numerous: a forest is
thousands of instances, so every mass here has to earn its triangles. The rule
followed throughout is *silhouette first* — a tree is recognised at RTS
distance by its outline against the ground, not by its detail.

    tree_pine_a/b/c     conifers, 74-105 tall, stacked tapered canopy skirts
    tree_broad_a/b/c    broadleaf, forked trunks, 5-6 overlapping crown lobes
    tree_dead           bare leaning snag and snapped branch stubs
    sapling             a young broadleaf, waist-high on a soldier
    bush_a/b            low scrub, one rounded and one sprawling
    stump               a felled trunk with a pale sawn face and root flare
    rock_a/b/c          angular boulders, faceted, three sizes
    rock_outcrop        bedded formation with a sheer face and ledges
    cliff_face_segment  60 x 60 tile for the edge of raised terrain
    reeds, grass_tuft   riverbank and field scatter, dirt cheap
    log, fallen_tree    deadfall

Shape vocabulary
----------------
common.py gives rectangular masses; trees are not rectangular. Rather than
invent new *materials* this module composes five cheap organic solids on top
of common's primitives and mesh data:

    frustum()  a box whose top face is scaled and slid — conifer skirts,
               tapered trunks, leaning boles, strata beds.        12 tris
    gem()      a ring of verts pinched to an apex above and below — crown
               lobes and bushes. Reads round, costs the same as a cube.
               `ring` sits the girth high so lobes dome, not spike. 12 tris
    boulder()  ring + flat bedded base — rock that sits on ground.  22 tris
    prism()    a tapered n-gon bar between two points — logs, boles   20 tris
    limb()     a tapered square bar between two points — branches, roots
    spike()    a tetrahedron — one blade of grass.                     4 tris

Every asset is seeded from a fixed number, so a rebuild is byte-stable and a
variant keeps its personality between runs. Variants differ by *shape*, not by
scale: pine_a is a even-tiered forest tree, pine_b a crowded spire with a long
bare bole, pine_c a squat leaning edge-of-wood tree; broad_a is round-crowned,
broad_b grew one-sided away from a neighbour, broad_c is a low open-field
spreader. A stand of them should never read as one tree copied.

Placement contract (see common.py): origin on the ground at the footprint
centre. Organic pieces are allowed a unit or two of geometry below z=0 so they
bed into uneven terrain instead of hovering on the high side of a slope.

Note on common.cyl(): its z argument is applied *before* any rotation, so a
cylinder laid on its side ends up floating at half its own length. Anything
horizontal here uses prism()/limb(), which take two endpoints and cannot make
that mistake.
"""

import math
import os
import random

import bpy
import bmesh
from mathutils import Vector

import common as C

R = math.radians
TAU = math.tau


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
            tilt=0.0, shift=(0.0, 0.0), jit=0.0, rng=None, name=None):
    """A box with an independently sized, independently placed top face.

    Wide bottom + narrow top is a conifer skirt or a tapered trunk; equal
    footprints plus a sideways `shift` is a leaning bole; a small `tilt` about
    X gives a bed of rock a geological dip. 12 tris in every case.
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
    if yaw or tilt:
        ob.rotation_euler = (tilt, 0.0, yaw)
    return ob


def gem(x, y, z, rx, ry, h, material, parent=None, sides=6, ring=0.58,
        bz=None, lean=(0.0, 0.0), phase=0.0, jit=0.0, rng=None, name='gem'):
    """A ring of verts pinched to an apex above and below — a chunky rounded
    lobe. `ring` is where the girth sits as a fraction of h: keep it above a
    half so the top cone is shallow and the lobe domes instead of spiking.
    `lean` slides the apex sideways so a crown lobe can reach for the light."""
    if bz is None:
        bz = -h * 0.26
    vs = []
    for i in range(sides):
        a = phase + i * TAU / sides
        jr = 1.0 + (rng.uniform(-jit, jit) if (jit and rng) else 0.0)
        jz = (rng.uniform(-jit, jit) * h * 0.35) if (jit and rng) else 0.0
        vs.append((x + math.cos(a) * rx * jr,
                   y + math.sin(a) * ry * jr,
                   z + ring * h + jz))
    top = len(vs)
    vs.append((x + lean[0], y + lean[1], z + h))
    bot = len(vs)
    vs.append((x + lean[0] * 0.25, y + lean[1] * 0.25, z + bz))
    faces = []
    for i in range(sides):
        j = (i + 1) % sides
        faces.append((i, j, top))
        faces.append((j, i, bot))
    return _mesh(name, vs, faces, material, parent)


def boulder(x, y, z, rx, ry, h, material, parent=None, sides=6, ring=0.52,
            base=0.72, sink=1.2, phase=0.0, tip=(0.0, 0.0), jit=0.24,
            rng=None, name='rock'):
    """Angular rock: a flat bedded base, a girth ring set high, a tilted and
    offset apex. Faceted on purpose — this is a boulder, never a sphere, and
    the offset apex is what stops it reading as a crystal. 22 tris."""
    rng = rng or random.Random(0)
    lo, mid = [], []
    for i in range(sides):
        a = phase + i * TAU / sides
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
        a = phase + i * TAU / 3.0
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
    return _mesh(name, vs, faces, material, parent, loc=tuple(p0),
                 rot=d.to_track_quat('Z', 'Y').to_euler())


def prism(parent, p0, p1, r0, r1, material, sides=6, phase=0.0, name='prism'):
    """A tapered n-gon bar between two points — a felled bole. Unlike cyl()
    this is positioned by its endpoints, so it lies where it is told."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    L = max(d.length, 0.001)
    vs = []
    for r, z in ((r0, 0.0), (r1, L)):
        for i in range(sides):
            a = phase + i * TAU / sides
            vs.append((math.cos(a) * r, math.sin(a) * r, z))
    faces = [tuple(range(sides - 1, -1, -1)),
             tuple(range(sides, sides * 2))]
    for i in range(sides):
        j = (i + 1) % sides
        faces.append((i, j, sides + j, sides + i))
    return _mesh(name, vs, faces, material, parent, loc=tuple(p0),
                 rot=d.to_track_quat('Z', 'Y').to_euler())


# --------------------------------------------------------------------- trees

def _conifer(name, seed, tiers, trunk_r, lean, mats, spur=None):
    """Shared conifer body.

    `tiers` are explicit (base z, width, top fraction, height) skirts stacked
    up a leaning bole, deliberately wider than they are tall: a conifer is
    read from the *steps* between skirts, and tall narrow tiers merge into one
    featureless spike. Each skirt is yawed off its neighbours and its corners
    jittered so the lower edge is ragged, and `spur` hangs one extra broken
    skirt off one side so no two variants share a profile.

    `lean` is the sideways offset of the treetop; every skirt and the bole's
    top face ride that line, which keeps the roots planted while the crown
    tips over.
    """
    g = C.empty(name)
    rng = random.Random(seed)
    lx, ly = lean
    height = tiers[-1][0] + tiers[-1][3]

    bole_top = tiers[-1][0]
    frustum(0, 0, -1.5, trunk_r * 2.2, trunk_r * 2.2,
            trunk_r * 0.9, trunk_r * 0.9, bole_top + 1.5, 'trunk', g,
            shift=(lx * bole_top / height, ly * bole_top / height),
            name='bole')

    for i, (z, w, topf, h) in enumerate(tiers):
        f = z / height
        cx = lx * f + rng.uniform(-1.2, 1.2)
        cy = ly * f + rng.uniform(-1.2, 1.2)
        frustum(cx, cy, z,
                w * rng.uniform(0.95, 1.05), w * rng.uniform(0.95, 1.05),
                w * topf, w * topf, h, mats[i % len(mats)], g,
                yaw=rng.uniform(-0.6, 0.6), jit=w * 0.06, rng=rng,
                name='skirt')

    if spur:
        sz, sw, sh, sa = spur
        f = sz / height
        frustum(lx * f + math.cos(sa) * sw * 0.45,
                ly * f + math.sin(sa) * sw * 0.45, sz,
                sw, sw * 0.8, sw * 0.25, sw * 0.2, sh, mats[0], g,
                yaw=sa, jit=sw * 0.08, rng=rng, name='spur')
    return g


def tree_pine_a():
    """The standard forest conifer: four broad skirts stepping evenly up an
    almost upright bole, with one broken tier jutting north-east."""
    return _conifer(
        'tree_pine_a', 21,
        tiers=((16.0, 42.0, 0.60, 24.0),
               (32.0, 35.0, 0.58, 23.0),
               (47.0, 27.0, 0.55, 22.0),
               (62.0, 20.0, 0.10, 30.0)),
        trunk_r=3.0, lean=(2.5, -1.5),
        mats=('foliage_a', 'foliage_b'),
        spur=(38.0, 22.0, 9.0, R(55)))


def tree_pine_b():
    """Crowded-forest tree that raced its neighbours for light: a long bare
    bole, five narrow tiers bunched into the top third, spindly crest."""
    return _conifer(
        'tree_pine_b', 33,
        tiers=((32.0, 27.0, 0.62, 17.0),
               (43.0, 25.0, 0.60, 16.0),
               (54.0, 21.0, 0.58, 15.0),
               (65.0, 17.0, 0.55, 15.0),
               (77.0, 13.0, 0.10, 28.0)),
        trunk_r=2.6, lean=(-3.0, 2.0),
        mats=('foliage_a', 'foliage_b'),
        spur=(48.0, 16.0, 7.0, R(-130)))


def tree_pine_c():
    """Edge-of-wood tree with room to spread: squat, leaning hard east, three
    heavy skirts with the lowest almost touching the ground."""
    return _conifer(
        'tree_pine_c', 47,
        tiers=((7.0, 52.0, 0.62, 26.0),
               (26.0, 41.0, 0.58, 25.0),
               (45.0, 29.0, 0.12, 29.0)),
        trunk_r=3.6, lean=(8.0, -3.5),
        mats=('foliage_b', 'foliage_c'),
        spur=(18.0, 28.0, 11.0, R(200)))


def _broadleaf(name, seed, trunk_h, trunk_r, lean, forks, lobes, mats):
    """Shared broadleaf body.

    A broadleaf is read from its fork: the bole rises, splits into three or
    four limbs, and the crown lobes sit above the ends of those limbs — with a
    clear band of bare forked timber visible underneath, which is the single
    thing that stops a low-poly tree looking like a lollipop.

    `forks` are (yaw, pitch, length, radius); `lobes` are
    (x, y, z, rx, ry, h, ring, lean_x, lean_y).
    """
    g = C.empty(name)
    rng = random.Random(seed)
    lx, ly = lean

    frustum(0, 0, -1.5, trunk_r * 2.2, trunk_r * 2.4,
            trunk_r * 1.3, trunk_r * 1.3, trunk_h + 1.5, 'trunk', g,
            shift=(lx, ly), name='bole')
    for i in range(3):
        a = i * TAU / 3.0 + 0.5
        limb(g, (0, 0, 5.0),
             (math.cos(a) * trunk_r * 2.4, math.sin(a) * trunk_r * 2.4, -2.0),
             trunk_r * 0.60, trunk_r * 0.38, 'trunk', 'root')

    top = Vector((lx, ly, trunk_h))
    for yaw, pitch, ln, r in forks:
        d = Vector((math.cos(yaw) * math.cos(pitch),
                    math.sin(yaw) * math.cos(pitch), math.sin(pitch))) * ln
        limb(g, tuple(top), tuple(top + d), r, r * 0.5, 'trunk', 'fork')

    for (x, y, z, rx, ry, h, ring, lnx, lny) in lobes:
        gem(x, y, z, rx, ry, h, mats[rng.randrange(len(mats))], g,
            ring=ring, lean=(lnx, lny), phase=rng.uniform(0, 1.0),
            jit=0.15, rng=rng, name='crown')
    return g


def tree_broad_a():
    """A full round-crowned oak — the default deciduous tree. Fork at knee
    height of the crown, five lobes with one shouldered out west and one
    riding high, so the outline is lumpy rather than circular."""
    return _broadleaf(
        'tree_broad_a', 101, 26.0, 3.8, (1.5, 1.0),
        forks=((R(165), R(58), 24.0, 3.0),
               (R(-25), R(64), 27.0, 3.2),
               (R(70), R(60), 19.0, 2.3)),
        lobes=((1, 0, 40, 24, 22, 28, 0.58, 1, 2),
               (-19, 8, 36, 16, 15, 20, 0.56, -4, 1),
               (16, -10, 37, 15, 14, 19, 0.54, 4, -3),
               (-3, -3, 52, 17, 16, 22, 0.60, 0, 0),
               (11, 11, 46, 13, 12, 16, 0.56, 3, 3)),
        mats=('foliage_b', 'foliage_c', 'foliage_b'))


def tree_broad_b():
    """Tall and one-sided: a tree that grew away from a neighbour. Long bole,
    the crown mass shoved east, one heavy limb reaching out low to the west
    with a lobe on the end of it."""
    return _broadleaf(
        'tree_broad_b', 202, 42.0, 3.4, (-3.5, 2.0),
        forks=((R(8), R(54), 30.0, 2.9),
               (R(-155), R(66), 21.0, 2.2),
               (R(-38), R(22), 30.0, 2.6)),
        lobes=((12, 1, 56, 19, 17, 25, 0.58, 4, 0),
               (23, -4, 47, 14, 13, 18, 0.54, 5, -2),
               (2, 7, 66, 15, 14, 20, 0.60, -1, 2),
               (18, 9, 62, 12, 12, 15, 0.56, 2, 2),
               (-22, -12, 44, 13, 12, 16, 0.54, -4, -4)),
        mats=('foliage_b', 'foliage_c'))


def tree_broad_c():
    """Low and spreading — an open-field tree with nothing to compete with.
    Short thick bole, four-way fork near head height, a wide flat crown that
    is broader than the tree is tall."""
    return _broadleaf(
        'tree_broad_c', 303, 18.0, 4.8, (2.0, -1.5),
        forks=((R(145), R(34), 33.0, 3.5),
               (R(-32), R(40), 35.0, 3.5),
               (R(48), R(52), 24.0, 2.7),
               (R(-115), R(46), 23.0, 2.5)),
        lobes=((-26, 16, 26, 19, 17, 20, 0.58, -5, 4),
               (28, -12, 27, 20, 18, 21, 0.58, 6, -3),
               (0, 0, 32, 21, 20, 22, 0.60, 0, 0),
               (14, 19, 24, 15, 14, 16, 0.54, 3, 5),
               (-13, -20, 23, 14, 14, 15, 0.54, -3, -5),
               (4, -2, 43, 12, 11, 13, 0.60, 1, 1)),
        mats=('foliage_b', 'foliage_c', 'foliage_c'))


def tree_dead():
    """Bare, angular and leaning, with the branches snapped short. Three bole
    sections kinked against each other so the trunk is never one straight
    line, and stubs that stop abruptly rather than tapering away."""
    g = C.empty('tree_dead')
    rng = random.Random(404)
    frustum(0, 0, -1.5, 8.4, 9.0, 6.4, 6.0, 26.0, 'deadwood', g,
            shift=(2.5, -1.0), name='bole0')
    frustum(2.5, -1.0, 24.0, 6.4, 6.0, 4.4, 4.2, 22.0, 'deadwood', g,
            shift=(4.0, 1.5), name='bole1')
    frustum(6.5, 0.5, 45.0, 4.4, 4.2, 1.4, 1.4, 19.0, 'deadwood', g,
            shift=(2.5, -1.5), name='bole2')
    for i in range(3):
        a = i * TAU / 3.0 + 0.9
        limb(g, (0, 0, 4.0), (math.cos(a) * 8.5, math.sin(a) * 8.5, -2.0),
             2.5, 1.4, 'deadwood', 'root')
    # snapped branches: base z, yaw, pitch, length, butt radius
    for z, yaw, pitch, ln, r in ((20.0, R(205), R(30), 21.0, 2.2),
                                 (29.0, R(-12), R(22), 25.0, 2.4),
                                 (37.0, R(100), R(44), 14.0, 1.7),
                                 (47.0, R(-100), R(16), 16.0, 1.5),
                                 (54.0, R(155), R(50), 10.0, 1.2)):
        p0 = Vector((2.5 * (z / 45.0) + 0.5, 0.0, z))
        d = Vector((math.cos(yaw) * math.cos(pitch),
                    math.sin(yaw) * math.cos(pitch), math.sin(pitch))) * ln
        limb(g, tuple(p0), tuple(p0 + d), r, r * 0.45, 'deadwood', 'branch')
        if ln > 18.0:                 # a second-order stub off the big two
            m = p0 + d * 0.58
            d2 = Vector((math.cos(yaw + 1.2) * 0.55,
                         math.sin(yaw + 1.2) * 0.55, 0.83)) * (ln * 0.5)
            limb(g, tuple(m), tuple(m + d2), r * 0.55, r * 0.28,
                 'deadwood', 'twig')
    return g


def sapling():
    """Waist-high on a soldier: a whippy stem, one side shoot, two small
    lobes — a tree that has not decided on a shape yet."""
    g = C.empty('sapling')
    rng = random.Random(55)
    frustum(0, 0, -1.0, 2.2, 2.2, 1.0, 1.0, 15.0, 'trunk', g, shift=(1.4, 0.6),
            name='stem')
    limb(g, (0.9, 0.4, 9.0), (-5.0, 2.2, 14.5), 0.8, 0.45, 'trunk', 'shoot')
    gem(1.8, 0.9, 12.5, 7.2, 6.6, 9.5, 'foliage_c', g, ring=0.58,
        lean=(1.5, 0.5), jit=0.18, rng=rng, name='crown')
    gem(-4.4, 2.1, 13.0, 4.8, 4.4, 6.5, 'foliage_b', g, ring=0.56,
        phase=1.1, jit=0.18, rng=rng, name='crown')
    return g


def bush_a():
    """A rounded shrub — three lobes, one clearly dominant."""
    g = C.empty('bush_a')
    rng = random.Random(66)
    gem(0, 0, 0, 10.5, 9.0, 13.0, 'foliage_b', g, ring=0.54, bz=-2.5,
        jit=0.20, rng=rng, name='mass')
    gem(-7.0, 3.5, 0, 6.4, 6.0, 8.5, 'foliage_a', g, ring=0.50, bz=-2.0,
        phase=0.7, jit=0.20, rng=rng, name='mass')
    gem(5.5, -4.5, 0, 5.6, 5.4, 7.0, 'foliage_c', g, ring=0.50, bz=-2.0,
        phase=1.4, jit=0.20, rng=rng, name='mass')
    return g


def bush_b():
    """Sprawling scrub — lower, wider, four lobes at four heights and a pair
    of bare shoots poking out of the top. A different plant, not a small
    bush_a."""
    g = C.empty('bush_b')
    rng = random.Random(77)
    for (x, y, rx, ry, h, m, ph) in ((-8.0, -2.5, 9.0, 7.5, 8.5, 'foliage_c', 0.0),
                                     (6.0, 4.5, 7.5, 7.0, 7.0, 'foliage_b', 0.6),
                                     (3.5, -7.0, 6.5, 6.0, 5.5, 'foliage_b', 1.2),
                                     (-2.5, 6.5, 5.5, 5.0, 4.5, 'foliage_a', 1.9)):
        gem(x, y, 0, rx, ry, h, m, g, ring=0.48, bz=-2.0, phase=ph,
            jit=0.22, rng=rng, name='mass')
    limb(g, (-6.5, -1.5, 5.0), (-10.5, -4.0, 12.5), 0.7, 0.3, 'trunk', 'shoot')
    limb(g, (4.5, 3.5, 4.5), (7.5, 7.0, 11.0), 0.7, 0.3, 'trunk', 'shoot')
    return g


def stump():
    """Felled, not rotted: a pale sawn face, a torn splinter left standing on
    one side where the trunk tore free, roots flaring into the ground."""
    g = C.empty('stump')
    rng = random.Random(88)
    frustum(0, 0, -1.5, 11.5, 10.5, 8.6, 8.0, 8.5, 'trunk', g, name='bole')
    frustum(0, 0, 6.8, 8.6, 8.0, 8.4, 7.8, 0.9, 'timber_light', g, name='cut')
    frustum(2.8, -1.6, 7.2, 3.2, 2.8, 1.0, 0.9, 7.0, 'timber_light', g,
            shift=(1.0, 0.5), name='splinter')
    for i in range(5):
        a = i * TAU / 5.0 + 0.3
        r = 6.5 + rng.uniform(0.0, 2.5)
        limb(g, (0, 0, 3.5), (math.cos(a) * r, math.sin(a) * r, -2.0),
             2.1, 1.1, 'trunk', 'root')
    return g


# --------------------------------------------------------------------- rock

def rock_a():
    """Chest-high boulder with a shed flake leaning against it."""
    g = C.empty('rock_a')
    rng = random.Random(901)
    boulder(0, 0, 0, 12.5, 10.0, 13.0, 'stone', g, ring=0.60, base=0.74,
            tip=(-3.5, 2.0), phase=0.3, jit=0.24, rng=rng)
    boulder(9.5, -6.5, 0, 5.5, 5.0, 6.0, 'stone_dark', g, ring=0.56,
            base=0.78, tip=(2.0, -1.2), phase=1.1, jit=0.26, rng=rng)
    return g


def rock_b():
    """A single low stone, the one you scatter by the hundred."""
    g = C.empty('rock_b')
    rng = random.Random(902)
    boulder(0, 0, 0, 7.5, 6.0, 6.0, 'stone', g, ring=0.58, base=0.80,
            tip=(1.6, 2.0), phase=0.8, jit=0.28, rng=rng)
    return g


def rock_c():
    """A tilted slab shouldering out of the ground with rubble at its foot —
    the big one, taller than a soldier."""
    g = C.empty('rock_c')
    rng = random.Random(903)
    frustum(0, 0, -2.0, 21.0, 14.0, 12.0, 8.0, 24.0, 'stone_light', g,
            shift=(-7.0, 3.5), jit=1.2, rng=rng, name='slab')
    boulder(-2.0, -1.5, 0, 12.0, 9.5, 10.0, 'stone', g, ring=0.60, base=0.74,
            tip=(-4.0, 1.5), phase=0.5, jit=0.22, rng=rng)
    boulder(10.0, 5.5, 0, 5.0, 4.6, 5.0, 'stone_dark', g, ring=0.56,
            base=0.82, phase=1.7, jit=0.28, rng=rng)
    return g


def rock_outcrop():
    """Bedrock breaking the surface.

    One dominant mass sheared off to a sheer face looking -Y, stepping back in
    two ledges toward +Y, with the debris that fell off the face lying at its
    foot. The beds dip a couple of degrees so the formation never reads as a
    stack of even courses.
    """
    g = C.empty('rock_outcrop')
    rng = random.Random(910)
    dip = R(3.0)

    # the sheer face: two big blocks parted by a fracture, ground to full height
    frustum(-11.0, -8.0, -2.0, 27.0, 20.0, 22.0, 15.0, 34.0, 'stone', g,
            shift=(2.0, 3.0), jit=1.4, rng=rng, name='face')
    frustum(14.0, -6.0, -2.0, 18.0, 17.0, 14.0, 12.0, 25.0, 'stone_dark', g,
            shift=(-2.5, 2.5), jit=1.4, rng=rng, name='face')
    # the mass behind, stepping back and up in dipping beds
    frustum(0.0, 10.0, -2.0, 48.0, 26.0, 44.0, 22.0, 22.0, 'stone_dark', g,
            tilt=dip, shift=(1.0, 2.0), jit=1.6, rng=rng, name='bed')
    frustum(-2.0, 16.0, 19.0, 38.0, 20.0, 33.0, 16.0, 15.0, 'stone_light', g,
            tilt=dip, shift=(-2.0, 2.0), jit=1.4, rng=rng, name='bed')
    frustum(3.0, 21.0, 32.0, 25.0, 15.0, 20.0, 11.0, 11.0, 'stone', g,
            tilt=dip, shift=(1.5, 1.5), jit=1.2, rng=rng, name='bed')
    # a ledge shelf jutting from the face, and the topsoil the wind left
    frustum(-8.0, -12.0, 24.0, 20.0, 9.0, 17.0, 7.0, 3.5, 'stone_light', g,
            jit=0.8, rng=rng, name='ledge')
    frustum(2.0, 24.0, 41.0, 20.0, 12.0, 16.0, 10.0, 2.4, 'dirt', g,
            jit=0.7, rng=rng, name='topsoil')
    boulder(-6.0, 19.0, 33.0, 8.0, 7.0, 10.0, 'stone_light', g, ring=0.58,
            base=0.76, tip=(3.0, 2.5), phase=0.9, jit=0.24, rng=rng)
    # talus: what has come off the face
    for (x, y, rx, h, m) in ((-24.0, -22.0, 6.0, 6.0, 'stone'),
                             (-11.0, -26.0, 4.5, 4.5, 'stone_dark'),
                             (6.0, -23.0, 5.5, 5.5, 'stone_light'),
                             (20.0, -18.0, 3.6, 3.6, 'stone')):
        boulder(x, y, 0, rx, rx * 0.85, h, m, g, ring=0.56, base=0.80,
                phase=rng.uniform(0, 1.0), jit=0.28, rng=rng)
    return g


def cliff_face_segment():
    """A 60 x 60 tile for the edge of raised terrain.

    Runs along X, flush at x = -30 and x = +30 so tiles butt without a seam.
    The exposed face looks -Y; the rock body fills 0 <= y <= 22, the side
    buried in the hill, and everything that projects forward of the face stays
    inside |x| < 26 so neighbouring tiles never intersect.

    The hard part of a rock face is *not* looking like masonry. Three things
    do that work here: the beds are of deliberately unequal thickness, they
    batter backwards as they rise (each bed's top face is set further +Y than
    its bottom), and the front is broken by full-height buttresses and a
    fracture so the eye reads vertical jointing across the horizontal beds.
    The soil on top is three separate chunks at three heights, because a
    continuous brown strip along the lip reads as a roof.
    """
    g = C.empty('cliff_face_segment')
    rng = random.Random(920)

    # the hill behind: guarantees the tile is opaque whatever sits in front
    C.box(0, 12.0, -2.0, 60.0, 21.0, 61.0, 'stone_dark', g, name='core')

    # beds — unequal thicknesses, each battering back as it rises
    for (z, h, fy, dep, m) in ((-2.0, 16.0, -6.0, 15.0, 'stone'),
                               (13.0, 11.0, -3.0, 11.0, 'stone_light'),
                               (23.0, 19.0, -5.5, 14.0, 'stone'),
                               (41.0, 8.0, -2.0, 10.0, 'stone_dark'),
                               (48.0, 12.0, -4.0, 12.0, 'stone_light')):
        frustum(0, fy + dep * 0.5, z, 60.0, dep, 60.0, dep * 0.62, h, m, g,
                shift=(0.0, dep * 0.20), name='bed')

    # buttresses and a fracture: vertical jointing read across the beds
    frustum(-17.0, -8.0, -2.0, 17.0, 11.0, 13.0, 8.0, 33.0, 'stone', g,
            shift=(1.5, 3.0), jit=1.3, rng=rng, name='buttress')
    frustum(15.0, -7.0, 8.0, 14.0, 10.0, 11.0, 7.0, 30.0, 'stone_light', g,
            shift=(-1.5, 2.5), jit=1.3, rng=rng, name='buttress')
    frustum(0.0, -9.5, -2.0, 8.0, 8.0, 6.0, 6.0, 21.0, 'stone_dark', g,
            shift=(2.5, 2.5), jit=1.0, rng=rng, name='pillar')

    # shelves where a harder bed has resisted the weather
    for (x, z, w, dep, m) in ((-6.0, 25.0, 26.0, 8.0, 'stone_light'),
                              (17.0, 40.0, 18.0, 6.5, 'stone'),
                              (-21.0, 45.0, 14.0, 6.0, 'stone_dark')):
        frustum(x, -dep * 0.5 + 1.0, z, w, dep, w * 0.88, dep * 0.7, 3.2,
                m, g, jit=0.6, rng=rng, name='ledge')

    # topsoil: three chunks at three heights, not one continuous lip
    for (x, y, w, dep, z, h) in ((-19.0, 4.0, 20.0, 17.0, 57.5, 3.0),
                                 (3.0, 1.5, 18.0, 14.0, 58.5, 2.6),
                                 (21.0, 5.0, 16.0, 16.0, 56.5, 3.4)):
        frustum(x, y, z, w, dep, w * 0.9, dep * 0.85, h, 'dirt', g,
                jit=0.7, rng=rng, name='soil')
    frustum(11.0, -1.0, 55.0, 9.0, 8.0, 7.0, 6.0, 6.0, 'stone', g,
            shift=(0.5, 1.5), jit=0.8, rng=rng, name='crag')

    # scree piled against the foot of the face
    for (x, y, rx, h, m) in ((-22.0, -12.0, 5.5, 5.5, 'stone_dark'),
                             (-9.0, -14.0, 4.0, 4.0, 'stone'),
                             (5.0, -13.0, 6.0, 6.0, 'stone_light'),
                             (18.0, -12.5, 3.6, 3.6, 'stone')):
        boulder(x, y, 0, rx, rx * 0.8, h, m, g, ring=0.56, base=0.80,
                phase=rng.uniform(0, 1.0), jit=0.28, rng=rng)
    return g


# ------------------------------------------------------------------ scatter

def grass_tuft():
    """Five blades, 20 tris, thrown down by the thousand across a field."""
    g = C.empty('grass_tuft')
    rng = random.Random(1001)
    for i in range(5):
        a = i * TAU / 5.0 + rng.uniform(-0.35, 0.35)
        r = rng.uniform(0.8, 2.6)
        spike(math.cos(a) * r, math.sin(a) * r, 1.15,
              rng.uniform(4.0, 7.5), 'grass', g,
              lean=(math.cos(a) * 2.6, math.sin(a) * 2.6), phase=a,
              name='blade')
    return g


def reeds():
    """Riverbank reeds — taller, straighter and gathered tighter than grass.
    Six stalks are real tapered stems so the three seed heads have something
    to sit on; the rest are cheap blades filling the clump out."""
    g = C.empty('reeds')
    rng = random.Random(1002)
    heads = []
    for i in range(6):
        a = i * TAU / 6.0 + rng.uniform(-0.25, 0.25)
        r = rng.uniform(0.6, 3.2)
        h = rng.uniform(13.0, 21.0)
        x, y = math.cos(a) * r, math.sin(a) * r
        lx, ly = math.cos(a) * r * 0.5, math.sin(a) * r * 0.5
        frustum(x, y, -0.5, 1.7, 1.7, 0.8, 0.8, h + 0.5,
                'foliage_c' if i % 2 else 'grass', g, shift=(lx, ly),
                name='stalk')
        heads.append((x + lx, y + ly, h))
    for i in range(4):
        a = i * TAU / 4.0 + 0.8
        r = rng.uniform(2.0, 4.2)
        spike(math.cos(a) * r, math.sin(a) * r, 0.9, rng.uniform(7.0, 12.0),
              'grass', g, lean=(math.cos(a) * 2.0, math.sin(a) * 2.0),
              phase=a, name='blade')
    for (x, y, h) in sorted(heads, key=lambda s: -s[2])[:3]:
        frustum(x, y, h - 4.0, 1.9, 1.9, 0.9, 0.9, 5.0, 'timber_light', g,
                name='head')
    return g


# ----------------------------------------------------------------- deadfall

def log():
    """A bucked length of trunk lying along X, pale sawn ends, one branch stub
    left on it and a stone it has come to rest against."""
    g = C.empty('log')
    rng = random.Random(1101)
    a, b = (-13.0, 0.6, 4.2), (13.0, -0.4, 3.6)
    prism(g, a, b, 4.2, 3.6, 'trunk', name='bole')
    prism(g, (-13.6, 0.6, 4.2), a, 4.0, 4.1, 'timber_light', name='cut')
    prism(g, b, (13.7, -0.4, 3.6), 3.5, 3.4, 'timber_light', name='cut')
    limb(g, (3.5, 0.0, 5.5), (7.0, 5.5, 8.0), 1.3, 0.6, 'trunk', 'stub')
    boulder(-10.5, 6.0, 0, 3.2, 2.8, 3.2, 'stone_dark', g, ring=0.56,
            base=0.82, phase=0.5, jit=0.3, rng=rng)
    return g


def fallen_tree():
    """A whole tree down: the root plate levered out of the ground at the west
    end with soil still on it, the bole kinked where it landed, branches
    snapped off short along its length, the crown end sawn away."""
    g = C.empty('fallen_tree')
    rng = random.Random(1102)

    # root plate — a disc of earth standing on edge, roots clawing out of it
    frustum(-31.0, 0.0, -2.0, 6.0, 25.0, 5.0, 17.0, 21.0, 'dirt', g,
            shift=(-2.5, 0.0), jit=1.3, rng=rng, name='plate')
    for i in range(5):
        a = 0.4 + i * 1.15
        limb(g, (-30.0, 0.0, 8.0),
             (-28.0 + math.cos(a) * 4.0, math.sin(a) * 12.0,
              8.0 + math.sin(a) * 10.0), 1.5, 0.6, 'deadwood', 'root')

    # bole in two kinked sections, thick end at the plate
    k = (-3.0, 1.8, 6.2)
    prism(g, (-28.0, 0.5, 6.0), k, 5.4, 4.7, 'deadwood', name='bole0')
    prism(g, k, (29.0, -2.5, 4.4), 4.7, 3.7, 'deadwood', name='bole1')
    prism(g, (29.0, -2.5, 4.4), (29.9, -2.6, 4.4), 3.6, 3.5, 'timber_light',
          name='cut')

    for (x, y, z, yaw, pitch, ln, r) in ((-14.0, 0.8, 7.0, R(72), R(26), 16.0, 2.0),
                                         (0.0, 1.6, 8.0, R(-108), R(18), 14.0, 1.8),
                                         (14.0, -0.6, 7.0, R(58), R(38), 12.0, 1.5),
                                         (24.0, -2.0, 6.0, R(-72), R(30), 10.0, 1.2)):
        p0 = Vector((x, y, z))
        d = Vector((math.cos(yaw) * math.cos(pitch),
                    math.sin(yaw) * math.cos(pitch), math.sin(pitch))) * ln
        limb(g, tuple(p0), tuple(p0 + d), r, r * 0.5, 'deadwood', 'branch')
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


def _sheet(path, span, top, width=1500, height=470, angle=22.0, azimuth=0.0):
    """Render whatever is in the scene into a wide contact sheet. Takes the
    framing explicitly rather than measuring a root, because the point of a
    sheet is to compare assets side by side at *one* scale."""
    import mathutils
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 20
    scene.cycles.use_denoising = False
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = 'PNG'
    try:
        scene.view_settings.view_transform = 'Standard'
    except (AttributeError, TypeError):
        pass

    world = bpy.data.worlds.get('World') or bpy.data.worlds.new('World')
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes['Background']
    bg.inputs['Color'].default_value = (0.30, 0.34, 0.38, 1)
    bg.inputs['Strength'].default_value = 0.5

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
    aim = top * 0.42
    cam.location = (dist * math.cos(el) * math.sin(az),
                    -dist * math.cos(el) * math.cos(az),
                    dist * math.sin(el) + aim)
    look = mathutils.Vector((0, 0, aim)) - mathutils.Vector(cam.location)
    cam.rotation_euler = look.to_track_quat('-Z', 'Y').to_euler()
    scene.camera = cam

    bpy.ops.mesh.primitive_plane_add(size=span * 4, location=(0, 0, -0.05))
    bpy.context.object.data.materials.append(C.mat('grass'))

    os.makedirs(os.path.dirname(path), exist_ok=True)
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def lineup(names, path, gap=14.0, **kw):
    """Build several assets side by side and render them in one image — the
    only way to tell whether variants actually differ from each other rather
    than merely looking fine in isolation."""
    C.clear_scene()
    roots, sizes = [], []
    for n in names:
        r = ASSETS[n]()
        roots.append(r)
        sizes.append(C.bounds(r))
    total = sum(s[0] for s in sizes) + gap * (len(names) - 1)
    top = max(s[2] for s in sizes)
    x = -total * 0.5
    for r, s in zip(roots, sizes):
        r.location = (x + s[0] * 0.5, 0.0, 0.0)
        x += s[0] + gap
    bpy.context.view_layer.update()
    w = kw.get('width', 1500)
    h = kw.get('height', 470)
    _sheet(path, max(total * 1.04, top * 1.15 * w / float(h)), top, **kw)


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
                             px=440, angle=22, azimuth=35)
        report.append((name, w, d, h, tris))
        print(f'{name:20s} {w:7.1f} x {d:6.1f} x {h:6.1f}   {tris:5d} tris')
    total = sum(r[4] for r in report)
    print(f'{"TOTAL":20s} {total:41d} tris')

    if preview_dir and sheets and not only:
        lineup(['tree_pine_a', 'tree_pine_b', 'tree_pine_c', 'tree_dead',
                'tree_broad_a', 'tree_broad_b', 'tree_broad_c'],
               os.path.join(preview_dir, '_sheet_trees.png'),
               gap=16.0, width=1500, height=470)
        lineup(['sapling', 'bush_a', 'bush_b', 'stump', 'grass_tuft',
                'reeds', 'log', 'fallen_tree'],
               os.path.join(preview_dir, '_sheet_small.png'),
               gap=10.0, width=1500, height=400, angle=26)
        lineup(['rock_b', 'rock_a', 'rock_c', 'rock_outcrop',
                'cliff_face_segment'],
               os.path.join(preview_dir, '_sheet_rock.png'),
               gap=14.0, width=1500, height=520, angle=20)
    return report


if __name__ == '__main__':
    build_all('/home/user/steamward/assets/models/nature', '/tmp/prev-nature')
