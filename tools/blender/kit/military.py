"""STEAMWARD military kit — modular fortification and camp props.

Fort convention
---------------
A curtain wall runs along +X. The ENEMY IS AT -Y: the outer face, the batter,
the arrow loops and the parapet oversail all look south, the wall walk and the
stair piers face +Y into the bailey. Every wall-run piece (wall_segment,
wall_corner, gatehouse) obeys this, so the game can lay a fort out on a 60-unit
grid without per-asset offsets. Free-standing buildings (keep, barracks,
storehouse, tents) keep the usual contract and face +X.

Wall profile — one cross-section shared by every piece
-----------------------------------------------------
        z 57.2  ---- merlon cap (stone_light)
        z 56.0  ---- merlon top
        z 47.2  ---- crenel sill coping
        z 41.0  ---- wall walk paving
        z 40.0  ---- body top / parapet springing
        z 36-40 ---- corbel band, carrying the parapet 2.5 proud of the face
        z 12    ---- top of the battered plinth
        z 0     ---- ground

Merlons sit on a 10-unit period (6 solid, 4 open) anchored so that butting two
segments end to end leaves exactly one crenel across the joint.

Nothing mechanical here is ornament: the gatehouse winch has a boiler that
feeds an engine, an engine that turns a drum, a drum that winds the chain, and
a chain that lifts the portcullis you can see hanging in the arch.
"""

import math
import os
import random

import bpy

import common as c
from common import (box, cyl, wedge, ramp, empty, clear_scene, export_glb,
                    preview_render, bounds, pitched_roof)

R = math.radians

# ------------------------------------------------------------ wall profile
V_BODY = 12.0        # body half-thickness
V_PLIN = 15.5        # batter at the foot
V_PLIN2 = 13.5
V_PAR_O = 16.0       # parapet outer face — oversails the body on corbels
V_PAR_I = 5.0        # parapet inner face
V_KERB = 9.0         # inner kerb: walk is V_KERB..V_PAR_I wide
Z_WALK = 40.0
Z_SILL = 46.5        # top of the crenel sill, i.e. merlon springing
Z_TOP = 57.0
MER = 5.6            # merlon width
PERIOD = 10.0

# objects excluded from the per-material merge so the runtime can find them
KEEP_NAMES = ('banner_cloth',)


# ---------------------------------------------------------------- helpers

def bx(parent, x0, x1, y0, y1, z0, z1, material, **kw):
    """A box given by its two opposite corners — the way you think about
    masonry — rather than by centre and size."""
    return box((x0 + x1) * 0.5, (y0 + y1) * 0.5, z0,
               abs(x1 - x0), abs(y1 - y0), abs(z1 - z0), material, parent, **kw)


def wbx(parent, along, cl, out, u0, u1, v0, v1, z0, z1, material, **kw):
    """A box in wall-local coordinates: u runs along the wall, v is measured
    from the wall centreline outward (positive = toward the enemy)."""
    a, b = cl + out * v0, cl + out * v1
    if along == 'x':
        return bx(parent, u0, u1, min(a, b), max(a, b), z0, z1, material, **kw)
    return bx(parent, min(a, b), max(a, b), u0, u1, z0, z1, material, **kw)


def cyl_axis(parent, axis, cx, cy, cz, r, length, material, verts=8, yaw=0.0):
    """A drum lying on its side — axles, winch drums, cart wheels — placed by
    its centre, because `cyl` places an upright drum by its base."""
    rot = (R(90), 0, yaw) if axis == 'y' else (0, R(90), yaw)
    return cyl(cx, cy, cz - length / 2.0, r, length, material, parent,
               verts=verts, rot=rot)


def cone(parent, x, y, z, r0, r1, h, material, verts=10, rot=None, name=None):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r0, radius2=r1,
                                    depth=h, location=(x, y, z + h / 2.0))
    ob = bpy.context.object
    if name:
        ob.name = name
    if rot:
        ob.rotation_euler = rot
    ob.data.materials.append(c.mat(material))
    for p in ob.data.polygons:
        p.use_smooth = False
    if parent:
        ob.parent = parent
        ob.matrix_parent_inverse = parent.matrix_world.inverted()
    return ob


def chain(parent, x, y, z0, z1, s=1.3, links=5, material='iron_dark'):
    """A hanging chain: a taut line broken by link bumps so it does not read
    as a bar."""
    box(x, y, z0, s, s, z1 - z0, material, parent)
    for i in range(links):
        t = z0 + (i + 0.5) * (z1 - z0) / links
        box(x, y, t - 0.5, s * 2.0, s * 0.7, 1.0, material, parent)


def diag(parent, x, y, z, length, s, material, pitch=0.0, yaw=0.0, cross=None):
    """A timber of given length placed by its low end, tilted by `pitch` from
    horizontal and swung by `yaw`."""
    cross = s if cross is None else cross
    hx = math.cos(pitch) * length / 2.0
    return box(x + hx * math.cos(yaw), y + hx * math.sin(yaw),
               z + math.sin(pitch) * length / 2.0 - s / 2.0,
               length, cross, s, material, parent, rot=(0, -pitch, yaw))


def slant(parent, x, y, z, w, d, h, material, pitch, axis='y'):
    """A sloping slab (stair cheek, roof pitch, ramp of a siege ladder)."""
    rot = (0, -pitch, 0) if axis == 'y' else (pitch, 0, 0)
    return box(x, y, z, w, d, h, material, parent, rot=rot)


# ------------------------------------------------------------ battlements

def battlements(g, x0, x1, y0, y1, z0, z_sill, z_top, thick=9.0,
                period=PERIOD, mer=MER, corner=None, material='stone',
                cap='stone_light', sides='nsew', deck='stone_light',
                corbel=None):
    """Merlons and crenels round a rectangular parapet — the single most
    important silhouette in the game, so every tower, gatehouse and keep in
    this kit gets it from the same place."""
    t = thick
    cnr = thick * 1.3 if corner is None else corner
    zc = z_sill + 1.2
    if deck:
        bx(g, x0 + t, x1 - t, y0 + t, y1 - t, z0 - 1.2, z0 + 0.4, deck)
    if corbel:
        # a corbel every `corbel` units, carrying the parapet proud of the face
        for (a, b, cc, dd, ax) in ((x0, x1, y0, y0 + 2.6, 'x'),
                                   (x0, x1, y1 - 2.6, y1, 'x'),
                                   (y0, y1, x0, x0 + 2.6, 'y'),
                                   (y0, y1, x1 - 2.6, x1, 'y')):
            n = max(1, int((b - a) / corbel))
            for i in range(n):
                u = a + (i + 0.5) * (b - a) / n
                if ax == 'x':
                    bx(g, u - 1.8, u + 1.8, cc, dd, z0 - 4.2, z0, cap)
                else:
                    bx(g, cc, dd, u - 1.8, u + 1.8, z0 - 4.2, z0, cap)

    bands = {'s': (x0, x1, y0, y0 + t), 'n': (x0, x1, y1 - t, y1),
             'w': (x0, x0 + t, y0 + t, y1 - t), 'e': (x1 - t, x1, y0 + t, y1 - t)}
    for s in sides:
        a, b, cc, dd = bands[s]
        bx(g, a, b, cc, dd, z0, z_sill, material)
        bx(g, a - 0.4, b + 0.4, cc - 0.4, dd + 0.4, z_sill, zc, cap)

    for (ax0, ay0) in ((x0, y0), (x1 - cnr, y0), (x0, y1 - cnr), (x1 - cnr, y1 - cnr)):
        bx(g, ax0, ax0 + cnr, ay0, ay0 + cnr, zc, z_top, material)
        bx(g, ax0 - 0.4, ax0 + cnr + 0.4, ay0 - 0.4, ay0 + cnr + 0.4,
           z_top, z_top + 1.2, cap)

    runs = {'s': ('x', x0 + cnr, x1 - cnr, y0, y0 + t),
            'n': ('x', x0 + cnr, x1 - cnr, y1 - t, y1),
            'w': ('y', y0 + cnr, y1 - cnr, x0, x0 + t),
            'e': ('y', y0 + cnr, y1 - cnr, x1 - t, x1)}
    for s in sides:
        ax, a, b, p0, p1 = runs[s]
        L = b - a
        if L < mer + 4.0:
            continue
        n = max(1, int(round(L / period)))
        while n > 1 and L / n < mer + 3.0:
            n -= 1
        for i in range(n):
            u = a + (i + 0.5) * L / n
            if ax == 'x':
                bx(g, u - mer / 2, u + mer / 2, p0, p1, zc, z_top, material)
                bx(g, u - mer / 2 - 0.4, u + mer / 2 + 0.4, p0 - 0.4, p1 + 0.4,
                   z_top, z_top + 1.2, cap)
            else:
                bx(g, p0, p1, u - mer / 2, u + mer / 2, zc, z_top, material)
                bx(g, p0 - 0.4, p1 + 0.4, u - mer / 2 - 0.4, u + mer / 2 + 0.4,
                   z_top, z_top + 1.2, cap)


def battlements_round(g, cx, cy, r_out, thick, z0, z_sill, z_top, n=12,
                      material='stone', cap='stone_light', deck='stone_light',
                      corbel=True):
    """The same parapet wrapped round a drum tower."""
    rm = r_out - thick / 2.0
    tang = 2.0 * rm * math.tan(math.pi / n) * 1.08
    if deck:
        cyl(cx, cy, z0 - 1.2, r_out - thick, 1.6, deck, g, verts=n)
    for k in range(n):
        a = 2 * math.pi * k / n
        px, py = cx + rm * math.cos(a), cy + rm * math.sin(a)
        if corbel:
            box(cx + (r_out - 1.7) * math.cos(a), cy + (r_out - 1.7) * math.sin(a),
                z0 - 4.6, 3.4, tang * 0.32, 4.6, cap, g, rot=(0, 0, a))
            box(cx + (r_out - 1.7) * math.cos(a + math.pi / n),
                cy + (r_out - 1.7) * math.sin(a + math.pi / n),
                z0 - 4.6, 3.4, tang * 0.32, 4.6, cap, g, rot=(0, 0, a + math.pi / n))
        box(px, py, z0, thick, tang, z_sill - z0, material, g, rot=(0, 0, a))
        box(px, py, z_sill, thick + 0.8, tang, 1.2, cap, g, rot=(0, 0, a))
        if k % 2 == 0:                     # merlon over every other bay
            box(px, py, z_sill + 1.2, thick, tang * 0.60, z_top - z_sill - 1.2,
                material, g, rot=(0, 0, a))
            box(px, py, z_top, thick + 0.9, tang * 0.60 + 0.9, 1.2, cap, g,
                rot=(0, 0, a))


# ------------------------------------------------------------------ arches

def arch_head(g, along, uc, half, z_spring, a0, a1, z_top, material,
              steps=6, cap=None):
    """Fill the spandrel above a round-headed opening, then ring it with
    voussoirs so the arch reads as built rather than cut."""
    for i in range(steps):
        zb = z_spring + half * i / steps
        zt = z_spring + half * (i + 1) / steps
        dz = half * (i + 0.5) / steps
        w = math.sqrt(max(half * half - dz * dz, 0.0))
        for (p0, p1) in ((uc - half, uc - w), (uc + w, uc + half)):
            if p1 - p0 < 0.05:
                continue
            if along == 'x':
                bx(g, p0, p1, a0, a1, zb, zt, material)
            else:
                bx(g, a0, a1, p0, p1, zb, zt, material)
    if along == 'x':
        bx(g, uc - half, uc + half, a0, a1, z_spring + half, z_top, material)
    else:
        bx(g, a0, a1, uc - half, uc + half, z_spring + half, z_top, material)
    if cap:
        rm, n = half + 2.6, 7
        for k in range(n):
            th = math.pi * (k + 0.5) / n
            u = uc + rm * math.cos(th)
            zz = z_spring + rm * math.sin(th)
            ln = 2.0 * rm * math.sin(math.pi / (2 * n)) * 2.3
            if along == 'x':
                box(u, (a0 + a1) / 2, zz - ln / 2, 5.2, a1 - a0, ln, cap, g,
                    rot=(0, -th, 0))
            else:
                box((a0 + a1) / 2, u, zz - ln / 2, a1 - a0, 5.2, ln, cap, g,
                    rot=(th, 0, 0))


# ------------------------------------------------------------ curtain wall

def curtain(g, along='x', cl=0.0, out=-1, u0=-30.0, u1=30.0, merlons=(),
            corbels=(), slits=(), piers=(), rough=None, deck=True,
            plinth=True, courses=True, parapet=True):
    """One straight run of curtain wall in the shared profile. Everything that
    must survive a butt joint spans the full u0..u1; everything decorative is
    kept clear of the ends so two runs meet without a seam."""
    W = lambda *a, **k: wbx(g, along, cl, out, *a, **k)

    if plinth:
        W(u0, u1, -V_BODY, V_PLIN, 0, 9, 'stone_dark')
        W(u0, u1, -V_BODY, V_PLIN2, 9, 14, 'stone')
        W(u0, u1, -V_BODY - 1.8, -V_BODY, 0, 6.0, 'stone_dark')
    W(u0, u1, -V_BODY, V_BODY, 14 if plinth else 0, Z_WALK, 'stone')

    if courses:
        W(u0, u1, V_BODY, V_BODY + 0.8, 14.0, 15.4, 'stone_dark')
        W(u0, u1, V_BODY, V_BODY + 1.4, 29.5, 31.6, 'stone_light')
    if rough is not None:
        for _ in range(max(2, int((u1 - u0) / 13))):
            u = rough.uniform(u0 + 6, u1 - 6)
            w = rough.uniform(6.0, 11.0)
            z = rough.uniform(17.0, 27.0)
            W(u - w / 2, u + w / 2, V_BODY, V_BODY + 0.35, z,
              z + rough.uniform(2.6, 3.8),
              rough.choice(('stone_light', 'stone_dark')))

    for u in corbels:                        # the band that carries the oversail
        W(u - 2.1, u + 2.1, V_BODY, V_PAR_O, 33.0, Z_WALK, 'stone_light')
    for u in slits:                          # arrow loop with a splayed jamb
        W(u - 2.8, u + 2.8, V_BODY - 0.2, V_BODY + 1.0, 16.0, 28.0, 'stone_light')
        W(u - 0.85, u + 0.85, V_BODY + 1.0, V_BODY + 1.5, 17.6, 26.4, 'soot')
        W(u - 2.8, u + 2.8, V_BODY + 1.0, V_BODY + 1.6, 28.0, 29.4, 'stone_dark')
    for u in piers:                          # relieving piers under the walk
        W(u - 3.6, u + 3.6, -V_BODY - 3.6, -V_BODY, 0, 34.0, 'stone')
        W(u - 4.4, u + 4.4, -V_BODY - 4.4, -V_BODY, 34.0, 37.0, 'stone_light')
        W(u - 3.0, u + 3.0, -V_BODY - 2.6, -V_BODY, 37.0, Z_WALK, 'stone_dark')

    if deck:
        W(u0, u1, -V_KERB, V_PAR_I, Z_WALK, Z_WALK + 1.0, 'stone_light')
        W(u0, u1, -V_BODY, -V_KERB, Z_WALK, Z_WALK + 4.0, 'stone')
        W(u0, u1, -V_BODY - 0.5, -V_KERB + 0.5, Z_WALK + 4.0, Z_WALK + 5.2,
          'stone_light')
    if parapet:
        W(u0, u1, V_PAR_I, V_PAR_O, Z_WALK, Z_SILL, 'stone')
        W(u0, u1, V_PAR_I - 0.5, V_PAR_O + 0.5, Z_SILL, Z_SILL + 1.2, 'stone_light')
        for u in merlons:
            W(u - MER / 2, u + MER / 2, V_PAR_I, V_PAR_O, Z_SILL + 1.2, Z_TOP, 'stone')
            W(u - MER / 2 - 0.5, u + MER / 2 + 0.5, V_PAR_I - 0.5, V_PAR_O + 0.5,
              Z_TOP, Z_TOP + 1.2, 'stone_light')


def wall_segment():
    """Tileable curtain: exactly 60 along +X, enemy at -Y. Merlons on a 10
    period leave 2 units of crenel at each end, so a butt joint reads as one
    more crenel and a run of these has no seam."""
    g = empty('wall_segment')
    curtain(g, 'x', 0.0, -1, -30.0, 30.0,
            merlons=[-25, -15, -5, 5, 15, 25],
            corbels=[-27 + 6 * i for i in range(10)],
            slits=[-10.0, 10.0], piers=[-20.0, 0.0, 20.0],
            rough=random.Random(7))
    return g


def wall_corner():
    """The same profile turning 90 degrees: the west arm butts a segment at
    x = -30, the north arm butts one at y = +30. Every course is laid as one
    L-shaped band rather than two overlapping runs, so no two solids fight
    over the same face at the quoin."""
    g = empty('wall_corner')
    U = 30.0

    def lband(v0, v1, z0, z1, m):
        """One course carried round the turn: a south leg and an east leg that
        touch without overlapping, whatever the offsets."""
        bx(g, -U, v1, -v1, -v0, z0, z1, m)
        bx(g, v0, v1, -v0, U, z0, z1, m)

    lband(-V_BODY, V_PLIN, 0, 9, 'stone_dark')             # battered foot
    lband(-V_BODY, V_PLIN2, 9, 14, 'stone')
    lband(-V_BODY - 1.8, -V_BODY, 0, 6, 'stone_dark')
    lband(-V_BODY, V_BODY, 14, Z_WALK, 'stone')            # body
    lband(V_BODY, V_BODY + 0.8, 14.0, 15.4, 'stone_dark')  # courses
    lband(V_BODY, V_BODY + 1.4, 29.5, 31.6, 'stone_light')
    lband(-V_KERB, V_PAR_I, Z_WALK, Z_WALK + 1.0, 'stone_light')          # walk
    lband(-V_BODY, -V_KERB, Z_WALK, Z_WALK + 4.0, 'stone')
    lband(-V_BODY - 0.5, -V_KERB + 0.5, Z_WALK + 4.0, Z_WALK + 5.2, 'stone_light')
    lband(V_PAR_I, V_PAR_O, Z_WALK, Z_SILL, 'stone')                      # parapet
    lband(V_PAR_I - 0.5, V_PAR_O + 0.5, Z_SILL, Z_SILL + 1.2, 'stone_light')

    for u in (-27, -21, -15, -9, -3, 3, 9, 13.5):          # corbels, south leg
        bx(g, u - 2.1, u + 2.1, -V_PAR_O, -V_BODY, 33.0, Z_WALK, 'stone_light')
    for u in (-9, -3, 3, 9, 15, 21, 27):                   # corbels, east leg
        bx(g, V_BODY, V_PAR_O, u - 2.1, u + 2.1, 33.0, Z_WALK, 'stone_light')

    rng = random.Random(3)
    for (ax, u) in (('x', -18.0), ('x', -7.0), ('y', 8.0), ('y', 21.0)):
        w = rng.uniform(6.0, 10.0)
        z = rng.uniform(17.0, 27.0)
        m = rng.choice(('stone_light', 'stone_dark'))
        if ax == 'x':
            bx(g, u - w / 2, u + w / 2, -V_BODY - 0.35, -V_BODY, z, z + 3.2, m)
        else:
            bx(g, V_BODY, V_BODY + 0.35, u - w / 2, u + w / 2, z, z + 3.2, m)

    for (ax, u) in (('x', -10.0), ('y', 10.0)):             # arrow loops
        if ax == 'x':
            loop_hole(g, u, -V_BODY, 16.0, '-y', w=5.6, h=12.0, depth=1.0)
        else:
            loop_hole(g, V_BODY, u, 16.0, '+x', w=5.6, h=12.0, depth=1.0)

    for (ax, u) in (('x', -20.0), ('y', 20.0)):             # relieving piers
        if ax == 'x':
            bx(g, u - 3.6, u + 3.6, V_BODY, V_BODY + 3.6, 0, 34.0, 'stone')
            bx(g, u - 4.4, u + 4.4, V_BODY, V_BODY + 4.4, 34.0, 37.0, 'stone_light')
            bx(g, u - 3.0, u + 3.0, V_BODY, V_BODY + 2.6, 37.0, Z_WALK, 'stone_dark')
        else:
            bx(g, -V_BODY - 3.6, -V_BODY, u - 3.6, u + 3.6, 0, 34.0, 'stone')
            bx(g, -V_BODY - 4.4, -V_BODY, u - 4.4, u + 4.4, 34.0, 37.0, 'stone_light')
            bx(g, -V_BODY - 2.6, -V_BODY, u - 3.0, u + 3.0, 37.0, Z_WALK, 'stone_dark')

    zc = Z_SILL + 1.2
    for u in (-25.0, -15.0, -5.0):                          # merlons, south leg
        bx(g, u - MER / 2, u + MER / 2, -V_PAR_O, -V_PAR_I, zc, Z_TOP, 'stone')
        bx(g, u - MER / 2 - 0.5, u + MER / 2 + 0.5, -V_PAR_O - 0.5, -V_PAR_I + 0.5,
           Z_TOP, Z_TOP + 1.2, 'stone_light')
    for u in (5.0, 15.0, 25.0):                             # merlons, east leg
        bx(g, V_PAR_I, V_PAR_O, u - MER / 2, u + MER / 2, zc, Z_TOP, 'stone')
        bx(g, V_PAR_I - 0.5, V_PAR_O + 0.5, u - MER / 2 - 0.5, u + MER / 2 + 0.5,
           Z_TOP, Z_TOP + 1.2, 'stone_light')
    bx(g, 2.0, V_PAR_O, -V_PAR_O, -2.0, zc, Z_TOP, 'stone')          # the quoin
    bx(g, 1.5, V_PAR_O + 0.5, -V_PAR_O - 0.5, -1.5, Z_TOP, Z_TOP + 1.2, 'stone_light')
    bx(g, 2.0, V_PAR_I, -V_PAR_I, -2.0, Z_WALK, zc, 'stone')         # its footing
    return g


# ----------------------------------------------------------------- towers

def loop_hole(g, x, y, z, face, w=5.2, h=12.0, depth=1.2):
    """An arrow loop: a splayed stone surround with a dark slot in it.
    `face` is the outward axis, one of '+x', '-x', '+y', '-y'."""
    ax, sgn = face[1], (1 if face[0] == '+' else -1)
    if ax == 'y':
        bx(g, x - w / 2, x + w / 2, y, y + sgn * depth, z, z + h, 'stone_light')
        bx(g, x - 0.9, x + 0.9, y + sgn * depth, y + sgn * (depth + 0.5),
           z + 1.8, z + h - 1.8, 'soot')
        bx(g, x - w / 2, x + w / 2, y, y + sgn * (depth + 0.6),
           z + h, z + h + 1.5, 'stone_dark')
    else:
        bx(g, x, x + sgn * depth, y - w / 2, y + w / 2, z, z + h, 'stone_light')
        bx(g, x + sgn * depth, x + sgn * (depth + 0.5), y - 0.9, y + 0.9,
           z + 1.8, z + h - 1.8, 'soot')
        bx(g, x, x + sgn * (depth + 0.6), y - w / 2, y + w / 2,
           z + h, z + h + 1.5, 'stone_dark')


def plank_door(g, x0, x1, y, thick, z0, z1, sgn=1, bands=3):
    """A timber leaf: boards, iron banding, studs."""
    bx(g, x0, x1, y, y + sgn * thick, z0, z1, 'timber')
    n = max(2, int((x1 - x0) / 3.4))
    for i in range(n):
        u = x0 + (x1 - x0) * (i + 0.5) / n
        bx(g, u - 0.25, u + 0.25, y + sgn * thick, y + sgn * (thick + 0.4),
           z0, z1, 'timber_light')
    for i in range(bands):
        zz = z0 + (z1 - z0) * (i + 0.55) / (bands + 0.1)
        bx(g, x0, x1, y + sgn * thick, y + sgn * (thick + 0.8), zz, zz + 2.0, 'iron')
        for sx in (x0 + 1.0, x1 - 2.0):
            bx(g, sx, sx + 1.0, y + sgn * (thick + 0.8), y + sgn * (thick + 1.3),
               zz + 0.5, zz + 1.5, 'iron_dark')


def tower_round():
    """Drum tower: battered foot, loops at two fighting levels, corbelled
    battlements well clear of the curtain. Door faces +Y, into the bailey."""
    g = empty('tower_round')
    rng = random.Random(17)
    RB, ZB = 20.0, 66.0
    cyl(0, 0, 0, 24.5, 9.0, 'stone_dark', g, verts=16)
    cyl(0, 0, 9.0, 22.3, 6.0, 'stone', g, verts=16)
    cyl(0, 0, 15.0, RB, ZB - 15.0, 'stone', g, verts=16)
    cyl(0, 0, 55.0, RB + 1.3, 2.4, 'stone_light', g, verts=16)
    cyl(0, 0, 30.0, RB + 0.7, 1.5, 'stone_dark', g, verts=16)

    for _ in range(16):                       # hand-laid coursing
        a = rng.uniform(0, math.tau)
        z = rng.uniform(17.0, 53.0)
        box(math.cos(a) * (RB + 0.1), math.sin(a) * (RB + 0.1), z,
            1.2, rng.uniform(5.0, 9.0), rng.uniform(2.8, 4.0),
            rng.choice(('stone_light', 'stone_dark')), g, rot=(0, 0, a))

    for lvl, off in ((25.0, 30.0), (42.0, 0.0)):
        for k in range(6):
            a = R(off + 60 * k)
            box(math.cos(a) * (RB - 0.4), math.sin(a) * (RB - 0.4), lvl,
                1.6, 5.6, 12.5, 'stone_light', g, rot=(0, 0, a))
            box(math.cos(a) * (RB + 0.7), math.sin(a) * (RB + 0.7), lvl + 2.0,
                0.7, 1.8, 8.5, 'soot', g, rot=(0, 0, a))
            box(math.cos(a) * (RB - 0.4), math.sin(a) * (RB - 0.4), lvl + 12.5,
                1.9, 5.6, 1.5, 'stone_dark', g, rot=(0, 0, a))

    for sx in (-1, 1):                                            # door jambs
        bx(g, sx * 6.2, sx * 8.8, 16.8, 21.8, 0, 20.0, 'stone_light')
    bx(g, -6.2, 6.2, 18.2, 22.2, 0, 20.0, 'soot')
    for k in range(5):                                            # arch head
        th = math.pi * (k + 0.5) / 5
        box(math.cos(th) * 7.5, 19.3, 20.0 + math.sin(th) * 7.5 - 2.7,
            5.2, 5.0, 5.4, 'stone_light', g, rot=(0, -th, 0))
    bx(g, -5.0, 5.0, 18.6, 21.6, 20.0, 25.4, 'soot')
    plank_door(g, -5.6, 5.6, 19.4, 1.6, 0, 19.4, bands=2)

    battlements_round(g, 0, 0, 23.0, 9.0, ZB, 72.5, 84.0, n=12)
    return g


def tower_square():
    """Square corner tower with a stair turret breaking the skyline — the
    turret is how the garrison gets from the bailey up to the wall walk."""
    g = empty('tower_square')
    rng = random.Random(29)
    A, ZB = 21.0, 60.0
    bx(g, -A - 4.5, A + 4.5, -A - 4.5, A + 4.5, 0, 9.0, 'stone_dark')
    bx(g, -A - 2.2, A + 2.2, -A - 2.2, A + 2.2, 9.0, 15.0, 'stone')
    bx(g, -A, A, -A, A, 15.0, ZB, 'stone')
    for s in (-1, 1):                          # clasping corner pilasters
        for t in (-1, 1):
            bx(g, s * A - s * 7.0, s * (A + 1.3), t * A - t * 7.0, t * (A + 1.3),
               15.0, ZB - 2.4, 'stone_light')
    bx(g, -A - 1.4, A + 1.4, -A - 1.4, A + 1.4, 51.0, 53.4, 'stone_light')
    bx(g, -A - 0.7, A + 0.7, -A - 0.7, A + 0.7, 29.0, 30.5, 'stone_dark')
    for _ in range(12):
        f = rng.choice(('-y', '+x', '-x'))
        u = rng.uniform(-13, 13)
        z = rng.uniform(17, 47)
        h = rng.uniform(2.8, 4.0)
        m = rng.choice(('stone_light', 'stone_dark'))
        if f == '-y':
            bx(g, u - 4, u + 4, -A - 0.45, -A + 0.2, z, z + h, m)
        else:
            sg = 1 if f == '+x' else -1
            bx(g, sg * (A + 0.45), sg * (A - 0.2), u - 4, u + 4, z, z + h, m)

    for u in (-10.0, 10.0):
        loop_hole(g, u, -A, 24.0, '-y')
        loop_hole(g, u, -A, 39.0, '-y')
        loop_hole(g, -A, u, 24.0, '-x')
        loop_hole(g, A, u, 32.0, '+x')
    loop_hole(g, -10.0, A, 33.0, '+y')

    bx(g, -8.5, 8.5, A - 0.6, A + 3.0, 0, 25.0, 'stone_light')     # door, +Y
    bx(g, -6.2, 6.2, A - 1.2, A + 3.2, 0, 22.0, 'soot')
    bx(g, -10.0, 10.0, A - 0.6, A + 3.4, 25.0, 27.6, 'stone')
    plank_door(g, -5.6, 5.6, A + 1.0, 1.6, 0, 21.5, bands=2)

    battlements(g, -A - 3.0, A + 3.0, -A - 3.0, A + 3.0, ZB, 66.5, 77.0,
                thick=9.0, period=11.0, mer=6.2, corner=11.0, corbel=6.0)

    tx0, ty0 = 4.0, 4.0                        # stair turret, bailey corner
    bx(g, tx0, tx0 + 18.0, ty0, ty0 + 18.0, ZB - 6.0, 84.0, 'stone')
    bx(g, tx0 - 1.2, tx0 + 19.2, ty0 - 1.2, ty0 + 19.2, 84.0, 86.6, 'stone_light')
    loop_hole(g, tx0 + 9.0, ty0 + 18.0, 70.0, '+y', w=4.6, h=9.0)
    loop_hole(g, tx0 + 18.0, ty0 + 9.0, 75.0, '+x', w=4.6, h=9.0)
    bx(g, tx0 - 1.4, tx0 + 5.0, ty0 + 4.0, ty0 + 14.0, ZB + 4.0, ZB + 18.0, 'soot')
    pitched_roof(tx0 + 9.0, ty0 + 9.0, 86.6, 16.0, 16.0, 10.0, 'roof_slate', g,
                 overhang=1.8, eave='timber')
    return g


# -------------------------------------------------------------- gatehouse

def _gate_winch(g):
    """The machine that lifts the portcullis, and nothing that does not serve
    it: fire heats the boiler, the boiler feeds the cylinder, the cylinder
    cranks the drum, the drum winds two chains down through the deck onto the
    portcullis head, and a ratchet holds the load when the fire is banked."""
    DZ, AX, AY = 58.0, 76.0, -13.0

    for sx in (-1, 1):                                    # posts and plates
        for py in (-16.0, 10.0):
            bx(g, sx * 16 - 2.0, sx * 16 + 2.0, py - 2.0, py + 2.0, DZ, 82.0, 'timber')
        diag(g, sx * 16, -16.0, 74.0, 9.0, 2.0, 'timber', pitch=R(38), yaw=R(90))
    for py in (-16.0, 10.0):
        bx(g, -18.0, 18.0, py - 2.2, py + 2.2, 82.0, 85.0, 'timber')
    pitched_roof(0, -3.0, 85.0, 34.0, 28.0, 9.0, 'roof_slate', g, overhang=2.6)

    for sx in (-1, 1):                                    # drum bearings
        bx(g, sx * 13 - 2.2, sx * 13 + 2.2, AY - 3.2, AY + 3.2, DZ, 72.6, 'stone')
        bx(g, sx * 13 - 2.9, sx * 13 + 2.9, AY - 3.9, AY + 3.9, 72.6, 78.4, 'iron_dark')
    cyl_axis(g, 'x', 0, AY, AX, 1.8, 40.0, 'steel', verts=8)       # shaft
    cyl_axis(g, 'x', 0, AY, AX, 4.6, 21.0, 'iron', verts=10)       # drum
    for sx in (-1, 1):                                             # chain coils
        cyl_axis(g, 'x', sx * 6.0, AY, AX, 5.8, 3.4, 'iron_dark', verts=10)
        chain(g, sx * 6.0, AY, DZ - 0.5, AX - 5.4, s=1.5, links=6)
        bx(g, sx * 6 - 2.4, sx * 6 + 2.4, AY - 2.6, AY + 2.6, DZ - 0.8, DZ + 0.6, 'soot')

    cx = -17.6                                            # crank and cylinder
    cyl_axis(g, 'x', cx, AY, AX, 4.8, 2.4, 'iron', verts=10)
    cyl_axis(g, 'x', cx, AY + 3.4, AX, 1.3, 3.0, 'steel', verts=8)
    diag(g, cx, AY + 3.4, AX, 8.2, 1.7, 'steel', pitch=R(-14), yaw=R(90), cross=1.7)
    bx(g, cx - 3.6, cx + 3.6, -4.0, 10.0, DZ, 70.2, 'stone')
    bx(g, cx - 4.2, cx + 4.2, -4.6, 10.6, 70.2, 71.6, 'iron_dark')
    cyl_axis(g, 'y', cx, 3.6, 74.0, 3.9, 11.0, 'iron', verts=10)
    cyl_axis(g, 'y', cx, 9.7, 74.0, 4.4, 2.4, 'steel', verts=10)
    cyl_axis(g, 'y', cx, -1.4, 74.0, 4.4, 2.0, 'steel', verts=10)

    rx = 17.6                                             # ratchet and pawl
    cyl_axis(g, 'x', rx, AY, AX, 5.6, 2.6, 'iron', verts=10)
    bx(g, rx - 1.2, rx + 1.2, AY + 3.0, AY + 5.0, AX + 2.0, AX + 8.0, 'iron')
    diag(g, rx, AY + 4.0, AX + 7.0, 8.0, 1.8, 'iron_dark', pitch=R(-32), yaw=R(-90))

    bx(g, 6.0, 20.0, 0.0, 12.0, DZ, 65.0, 'iron_dark')    # firebox
    bx(g, 20.0, 20.9, 3.0, 9.0, 59.5, 63.5, 'iron')
    bx(g, 20.9, 21.3, 4.0, 8.0, 60.0, 63.0, 'ember')
    cyl(13.0, 6.0, 65.0, 6.2, 13.0, 'iron', g, verts=10)  # boiler
    for zz in (67.0, 71.0, 75.0):
        c.rivet_band(13.0, 6.0, zz, 6.2, parent=g, verts=10)
    cyl(13.0, 6.0, 78.0, 3.4, 3.2, 'brass', g, verts=8)   # steam dome
    cyl(13.0, 6.0, 81.2, 2.5, 13.0, 'iron_dark', g, verts=8)   # chimney
    cyl(13.0, 6.0, 93.0, 3.0, 2.0, 'iron', g, verts=8)
    cyl(13.0, 8.0, 79.8, 1.5, 2.0, 'copper', g, verts=6)  # dome -> pipe
    cyl_axis(g, 'y', 13.0, 8.8, 80.6, 1.5, 4.0, 'copper', verts=6)
    cyl_axis(g, 'x', -2.3, 9.7, 80.6, 1.5, 30.6, 'copper', verts=6)
    cyl(cx, 9.7, 76.4, 1.5, 4.6, 'copper', g, verts=6)


def gatehouse():
    """Two flanking towers, a gate passage under a machicolation, timber
    leaves behind a portcullis, and the steam winch on the roof that lifts it.
    120 wide so it drops straight into the 60-unit wall grid."""
    g = empty('gatehouse')
    rng = random.Random(41)
    GX, GY0, GY1 = 24.0, -20.0, 20.0        # gate block
    PW, SPR = 11.0, 30.0                    # passage half-width, arch springing
    DZ = 58.0

    for sx in (-1, 1):                       # wall stubs, on the merlon grid
        curtain(g, 'x', 0.0, -1, 50.0 * sx if sx > 0 else -60.0,
                60.0 if sx > 0 else -50.0, merlons=[sx * 55.0],
                corbels=[sx * 52.5, sx * 58.5])

    for sx in (-1, 1):                       # flanking towers
        a, b = (24.0, 50.0) if sx > 0 else (-50.0, -24.0)
        bx(g, a, b, -31.5, 21.5, 0, 9.0, 'stone_dark')
        bx(g, a, b, -29.8, 19.8, 9.0, 14.0, 'stone')
        bx(g, a, b, -28.0, 18.0, 14.0, 76.0, 'stone')
        bx(g, a - 0.8, b + 0.8, -28.8, 18.8, 30.0, 31.6, 'stone_dark')
        bx(g, a - 1.4, b + 1.4, -29.4, 19.4, 65.0, 67.4, 'stone_light')
        for u in (a + 8.0, b - 8.0):
            loop_hole(g, u, -28.0, 22.0, '-y')
            loop_hole(g, u, -28.0, 40.0, '-y')
            loop_hole(g, u, -28.0, 54.0, '-y')
        for v in (-18.0, -4.0, 10.0):
            loop_hole(g, b, v, 36.0, '+x') if sx > 0 else loop_hole(g, a, v, 36.0, '-x')
        for _ in range(6):
            u = rng.uniform(a + 4, b - 4)
            z = rng.uniform(16, 62)
            bx(g, u - 4.5, u + 4.5, -28.5, -27.8, z, z + rng.uniform(2.8, 4.0),
               rng.choice(('stone_light', 'stone_dark')))
        battlements(g, a - 2.0, b + 2.0, -30.0, 20.0, 76.0, 82.0, 92.0,
                    thick=9.0, period=11.0, mer=6.2, corner=10.0, corbel=6.0)

    # gate block: piers either side of the passage, arch head above
    bx(g, -GX, GX, GY0 - 3.5, GY1 + 3.5, 0, 9.0, 'stone_dark')
    bx(g, -GX, GX, GY0 - 1.8, GY1 + 1.8, 9.0, 14.0, 'stone')
    for sx in (-1, 1):
        bx(g, sx * PW, sx * GX, GY0, GY1, 0, DZ, 'stone')
        bx(g, sx * PW, sx * (PW + 1.6), GY0 - 0.6, GY1 + 0.6, 0, SPR, 'stone_light')
    arch_head(g, 'x', 0.0, PW, SPR, GY0, GY1, DZ, 'stone', steps=7)
    bx(g, -PW, PW, GY0, GY1, 0, 1.2, 'stone_dark')            # passage paving
    for yv, sgn in ((GY0, -1), (GY1, 1)):                     # voussoirs, both ends
        for k in range(7):
            th = math.pi * (k + 0.5) / 7
            box(math.cos(th) * (PW + 2.8), yv + sgn * 0.7,
                SPR + math.sin(th) * (PW + 2.8) - 2.9, 5.4, 1.6, 5.8,
                'stone_light', g, rot=(0, -th, 0))

    # machicolation over the gate — corbels, a projecting box, murder holes
    for u in (-16.0, -8.0, 0.0, 8.0, 16.0):
        bx(g, u - 2.3, u + 2.3, -26.0, GY0, 41.0, 46.0, 'stone_light')
    bx(g, -GX, GX, -26.0, GY0, 46.0, DZ, 'stone')
    for u in (-9.0, 0.0, 9.0):
        bx(g, u - 2.6, u + 2.6, -24.6, -21.4, 45.3, 46.7, 'soot')

    # portcullis, hauled up into its slot; you can see the chains that did it
    for sx in (-1, 1):
        bx(g, sx * PW, sx * (PW + 1.7), -14.8, -11.2, 0, 46.0, 'stone_dark')
    for i in range(8):
        u = -9.6 + i * 2.74
        bx(g, u - 0.75, u + 0.75, -13.7, -12.3, 18.0, 46.0, 'iron_dark')
        wedge(u, -13.0, 15.6, 1.7, 1.7, 2.6, 'steel', g, rot=(0, R(180), 0))
    for zz in (19.0, 31.0, 43.0):
        bx(g, -PW, PW, -13.9, -12.1, zz, zz + 1.8, 'iron')

    # gate leaves, hung on pintles, barred
    for sx in (-1, 1):
        plank_door(g, sx * 0.35 if sx > 0 else -10.8, 10.8 if sx > 0 else -0.35,
                   7.4, 2.6, 0, 34.0, sgn=-1, bands=3)
        for zz in (5.0, 28.0):
            bx(g, sx * 10.6, sx * (PW + 0.9), 4.4, 8.2, zz, zz + 3.2, 'iron_dark')
    bx(g, -PW, PW, 6.0, 7.6, 34.0, 40.5, 'timber')
    bx(g, -PW, PW, 3.6, 4.6, 16.0, 19.2, 'iron')              # drawbar

    battlements(g, -GX, GX, -26.0, GY1, DZ, 64.0, 73.0, thick=7.0,
                period=11.0, mer=6.2, corner=9.0)
    _gate_winch(g)
    return g
