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
                      corbel=True, solid=False):
    """The same parapet wrapped round a drum tower. `solid` swaps the ring of
    sill blocks for one drum — right for small turrets nobody stands on, and
    a quarter of the triangles."""
    rm = r_out - thick / 2.0
    tang = 2.0 * rm * math.tan(math.pi / n) * 1.08
    if solid:
        cyl(cx, cy, z0 - 1.2, r_out - thick / 2.0, z_sill - z0 + 1.2, material,
            g, verts=n)
        cyl(cx, cy, z_sill, r_out - thick / 2.0 + 0.6, 1.2, cap, g, verts=n)
        for k in range(0, n, 2):
            a = 2 * math.pi * k / n
            px, py = cx + rm * math.cos(a), cy + rm * math.sin(a)
            box(px, py, z_sill + 1.2, thick, tang * 0.62, z_top - z_sill - 1.2,
                material, g, rot=(0, 0, a))
            box(px, py, z_top, thick + 0.9, tang * 0.62 + 0.9, 1.2, cap, g,
                rot=(0, 0, a))
        return
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
    portcullis head, and a ratchet holds the load when the fire is banked.
    Deliberately left open to the sky so the mechanism reads from above."""
    DZ, AX, AY = 58.0, 78.0, -15.0

    for sx in (-1, 1):                                    # gantry
        for py in (-15.0, 8.0):
            bx(g, sx * 17 - 2.1, sx * 17 + 2.1, py - 2.1, py + 2.1, DZ, 84.0, 'timber')
        bx(g, sx * 17 - 2.4, sx * 17 + 2.4, -17.4, 10.4, 84.0, 87.0, 'timber')
        diag(g, sx * 17, -15.0, 74.0, 10.0, 2.0, 'timber', pitch=R(42), yaw=R(90))
        diag(g, sx * 17, 8.0, 74.0, 10.0, 2.0, 'timber', pitch=R(42), yaw=R(-90))
    bx(g, -19.0, 19.0, -17.4, -12.6, 87.0, 89.4, 'timber')
    bx(g, -19.0, 19.0, 5.6, 10.4, 87.0, 89.4, 'timber')

    for sx in (-1, 1):                                    # drum bearings
        bx(g, sx * 13 - 2.3, sx * 13 + 2.3, AY - 3.3, AY + 3.3, DZ, 74.4, 'stone')
        bx(g, sx * 13 - 3.0, sx * 13 + 3.0, AY - 4.0, AY + 4.0, 74.4, 80.4, 'iron_dark')
    cyl_axis(g, 'x', 0, AY, AX, 1.8, 42.0, 'steel', verts=8)       # shaft
    cyl_axis(g, 'x', 0, AY, AX, 4.6, 21.0, 'iron', verts=10)       # drum
    for sx in (-1, 1):                                             # chain falls
        cyl_axis(g, 'x', sx * 6.0, AY, AX, 5.9, 3.4, 'iron_dark', verts=10)
        chain(g, sx * 6.0, AY, DZ - 0.5, AX - 5.5, s=1.6, links=7)
        bx(g, sx * 6 - 2.6, sx * 6 + 2.6, AY - 2.8, AY + 2.8, DZ - 0.8, DZ + 0.6, 'soot')

    cx = -18.4                                            # crank and cylinder
    cyl_axis(g, 'x', cx, AY, AX, 4.9, 2.6, 'iron', verts=10)
    cyl_axis(g, 'x', cx, AY + 3.5, AX, 1.3, 3.2, 'steel', verts=8)
    diag(g, cx, AY + 3.5, AX, 9.0, 1.8, 'steel', pitch=R(-13), yaw=R(90), cross=1.8)
    bx(g, cx - 3.8, cx + 3.8, -6.0, 8.0, DZ, 71.0, 'stone')
    bx(g, cx - 4.4, cx + 4.4, -6.6, 8.6, 71.0, 72.4, 'iron_dark')
    cyl_axis(g, 'y', cx, 1.6, 76.4, 4.0, 11.0, 'iron', verts=10)
    cyl_axis(g, 'y', cx, 7.7, 76.4, 4.5, 2.4, 'steel', verts=10)
    cyl_axis(g, 'y', cx, -3.4, 76.4, 4.5, 2.0, 'steel', verts=10)

    rx = 18.4                                             # ratchet and pawl
    cyl_axis(g, 'x', rx, AY, AX, 5.8, 2.8, 'iron', verts=10)
    bx(g, rx - 1.3, rx + 1.3, AY + 3.2, AY + 5.2, AX + 2.4, AX + 9.0, 'iron')
    diag(g, rx, AY + 4.2, AX + 8.0, 8.6, 1.9, 'iron_dark', pitch=R(-34), yaw=R(-90))

    bx(g, 5.0, 19.5, -3.0, 10.0, DZ, 65.0, 'iron_dark')   # firebox and boiler
    bx(g, 19.5, 20.4, 0.0, 6.0, 59.5, 63.5, 'iron')
    bx(g, 20.4, 20.8, 1.0, 5.0, 60.0, 63.0, 'ember')
    cyl(12.2, 3.5, 65.0, 6.3, 14.0, 'iron', g, verts=10)
    for zz in (67.0, 71.5, 76.0):
        c.rivet_band(12.2, 3.5, zz, 6.3, parent=g, verts=10)
    cyl(12.2, 3.5, 79.0, 3.5, 3.2, 'brass', g, verts=8)   # steam dome
    cyl(12.2, 3.5, 82.2, 2.6, 14.0, 'iron_dark', g, verts=8)
    cyl(12.2, 3.5, 95.0, 3.1, 2.2, 'iron', g, verts=8)
    ramp(12.2, 3.5, 89.0, 15.0, 15.0, 4.0, 'iron_dark', g)     # rain hood
    cyl(12.2, 5.6, 80.8, 1.5, 2.2, 'copper', g, verts=6)       # dome -> engine
    cyl_axis(g, 'y', 12.2, 6.7, 81.6, 1.5, 4.0, 'copper', verts=6)
    cyl_axis(g, 'x', -3.1, 7.7, 81.6, 1.5, 30.6, 'copper', verts=6)
    cyl(cx, 7.7, 78.6, 1.5, 4.2, 'copper', g, verts=6)


def gatehouse():
    """Two flanking towers thrown forward of the curtain, a gate passage under
    a machicolation, timber leaves behind a raised portcullis, and the open
    steam winch on the roof that raised it. 120 wide, so it drops straight
    into the 60-unit wall grid."""
    g = empty('gatehouse')
    rng = random.Random(41)
    GX, GY0, GY1 = 22.0, -20.0, 20.0        # gate block
    MY = -27.0                              # machicolation face
    TY0, TY1 = -34.0, 14.0                  # tower footprint in Y
    PW, SPR = 11.0, 30.0                    # passage half-width, arch springing
    DZ = 58.0

    for (a, b, mer, cor) in ((52.0, 60.0, 55.0, (53.0, 59.0)),
                             (-60.0, -52.0, -55.0, (-53.0, -59.0))):
        curtain(g, 'x', 0.0, -1, a, b, merlons=[mer], corbels=cor)

    for sx in (-1, 1):                       # flanking towers
        a, b = (22.0, 52.0) if sx > 0 else (-52.0, -22.0)
        bx(g, a, b, TY0 - 3.5, TY1 + 3.5, 0, 9.0, 'stone_dark')
        bx(g, a, b, TY0 - 1.8, TY1 + 1.8, 9.0, 14.0, 'stone')
        bx(g, a, b, TY0, TY1, 14.0, 78.0, 'stone')
        for u in (a + 5.0, b - 5.0):         # clasping pilasters
            bx(g, u - 4.0, u + 4.0, TY0 - 1.2, TY0 + 5.0, 14.0, 75.0, 'stone_light')
        bx(g, a - 0.9, b + 0.9, TY0 - 0.9, TY1, 30.0, 31.8, 'stone_dark')
        bx(g, a - 1.5, b + 1.5, TY0 - 1.5, TY1, 66.0, 68.6, 'stone_light')
        for u in (a + 15.0,):
            loop_hole(g, u, TY0, 20.0, '-y')
            loop_hole(g, u, TY0, 38.0, '-y')
            loop_hole(g, u, TY0, 56.0, '-y')
        for v in (-26.0, -12.0, 2.0):
            loop_hole(g, b if sx > 0 else a, v, 30.0, '+x' if sx > 0 else '-x')
        for _ in range(7):
            u = rng.uniform(a + 11, b - 11)
            z = rng.uniform(16, 62)
            bx(g, u - 4.5, u + 4.5, TY0 - 0.6, TY0 + 0.2, z, z + rng.uniform(2.8, 4.0),
               rng.choice(('stone_light', 'stone_dark')))
        battlements(g, a - 2.2, b + 2.2, TY0 - 2.2, TY1, 78.0, 85.0, 96.5,
                    thick=9.0, period=11.0, mer=6.2, corner=10.0, corbel=8.0)

    # gate block: piers either side of the passage, arch head above
    bx(g, -GX, GX, MY - 3.5, GY1 + 3.5, 0, 9.0, 'stone_dark')
    bx(g, -GX, GX, MY - 1.8, GY1 + 1.8, 9.0, 14.0, 'stone')
    for sx in (-1, 1):
        bx(g, sx * PW, sx * GX, GY0, GY1, 0, DZ, 'stone')
        bx(g, sx * PW, sx * (PW + 1.7), GY0 - 0.7, GY1 + 0.7, 0, SPR, 'stone_light')
    arch_head(g, 'x', 0.0, PW, SPR, GY0, GY1, DZ, 'stone', steps=7)
    bx(g, -PW, PW, GY0, GY1, 0, 1.2, 'stone_dark')            # passage paving
    for yv, sgn in ((GY0, -1), (GY1, 1)):                     # voussoirs, both ends
        for k in range(7):
            th = math.pi * (k + 0.5) / 7
            box(math.cos(th) * (PW + 2.9), yv + sgn * 0.8,
                SPR + math.sin(th) * (PW + 2.9) - 2.9, 5.6, 1.8, 5.8,
                'stone_light', g, rot=(0, -th, 0))

    # machicolation over the gate — corbels, a projecting box, murder holes
    for u in (-16.0, -8.0, 0.0, 8.0, 16.0):
        bx(g, u - 2.4, u + 2.4, MY, GY0, 40.0, 46.0, 'stone_light')
    bx(g, -GX, GX, MY, GY0, 46.0, DZ, 'stone')
    for u in (-9.0, 0.0, 9.0):
        bx(g, u - 2.7, u + 2.7, MY + 1.6, GY0 - 1.6, 45.2, 46.8, 'soot')

    # portcullis, hauled up into its slot; the chains that did it are on the roof
    PY = -18.6
    for sx in (-1, 1):
        bx(g, sx * PW, sx * (PW + 1.8), PY - 2.2, PY + 2.2, 0, 46.0, 'stone_dark')
    for i in range(8):
        u = -9.6 + i * 2.74
        bx(g, u - 0.8, u + 0.8, PY - 0.8, PY + 0.8, 18.0, 46.0, 'iron_dark')
        wedge(u, PY, 15.4, 1.8, 1.8, 2.8, 'steel', g, rot=(0, R(180), 0))
    for zz in (19.0, 31.0, 43.0):
        bx(g, -PW, PW, PY - 1.1, PY + 1.1, zz, zz + 1.9, 'iron')

    # gate leaves, hung on pintles, barred
    plank_door(g, -10.8, -0.35, 7.4, 2.6, 0, 34.0, sgn=-1, bands=3)
    plank_door(g, 0.35, 10.8, 7.4, 2.6, 0, 34.0, sgn=-1, bands=3)
    for sx in (-1, 1):
        for zz in (5.0, 28.0):
            bx(g, sx * 10.4, sx * (PW + 1.0), 4.2, 8.4, zz, zz + 3.2, 'iron_dark')
    bx(g, -PW, PW, 6.0, 7.6, 34.0, 40.5, 'timber')
    bx(g, -PW, PW, 3.4, 4.6, 16.0, 19.4, 'iron')              # drawbar

    bx(g, -GX - 0.9, GX + 0.9, MY - 0.9, MY, 46.0, 47.8, 'stone_dark')
    for u in (-15.0, 15.0):
        loop_hole(g, u, MY, 49.0, '-y', w=5.6, h=7.0)
    bx(g, -7.0, 7.0, MY, MY + 1.4, 48.0, 55.0, 'stone_light')   # winch-loft light
    bx(g, -5.2, 5.2, MY + 1.4, MY + 1.9, 49.4, 54.0, 'soot')
    battlements(g, -GX, GX, MY, GY1, DZ, 64.0, 71.5, thick=7.0,
                period=11.0, mer=6.2, corner=9.0)
    _gate_winch(g)
    return g


# ------------------------------------------------------------------- keep

def keep_window(g, x, y, face, w, h, z, style='plain'):
    """A window in a keep wall. The higher the storey, the more glass the lord
    could afford to lose to an arrow, so the style changes with height."""
    ax, sgn = face[1], (1 if face[0] == '+' else -1)

    def put(x0, x1, y0, y1, z0, z1, d0, d1, m):
        if ax == 'y':
            bx(g, x + x0, x + x1, y + sgn * d0, y + sgn * d1, z + z0, z + z1, m)
        else:
            bx(g, x + sgn * d0, x + sgn * d1, y + y0, y + y1, z + z0, z + z1, m)

    put(-w / 2 - 2.4, w / 2 + 2.4, 0, 0, -2.4, h + 2.4, -0.3, 1.3, 'stone_light')
    put(-w / 2, w / 2, 0, 0, 0, h, 1.3, 1.8, 'soot')
    put(-w / 2 - 3.4, w / 2 + 3.4, 0, 0, -3.4, -2.4, -0.3, 2.6, 'stone')   # sill
    if style == 'mullion':
        put(-1.1, 1.1, 0, 0, 0, h, 1.3, 2.2, 'stone_light')
    if style in ('arched', 'mullion'):
        for k in range(4):
            th = math.pi * (k + 0.5) / 4
            r = w / 2 + 2.4
            if ax == 'y':
                box(x + math.cos(th) * r, y + sgn * 0.9,
                    z + h + math.sin(th) * r - 2.1, 4.2, 2.6, 4.2,
                    'stone_light', g, rot=(0, -th, 0))
            else:
                box(x + sgn * 0.9, y + math.cos(th) * r,
                    z + h + math.sin(th) * r - 2.1, 2.6, 4.2, 4.2,
                    'stone_light', g, rot=(th, 0, 0))


def keep():
    """The landmark: a great stone block on a battered plinth, four drum
    turrets clasping the corners, the hall roof and its chimneys riding above
    the battlements, and the entrance lifted a storey up a forebuilding stair
    the way a keep's front door always is."""
    g = empty('keep')
    rng = random.Random(53)
    X0, X1, Y0, Y1 = -85.0, 55.0, -68.0, 68.0
    ZB = 112.0                                   # top of the main wall
    F0, F1, FY = 55.0, 88.0, 26.0                # forebuilding

    bx(g, X0 - 4.5, X1 + 4.5, Y0 - 4.5, Y1 + 4.5, 0, 12.0, 'stone_dark')
    bx(g, X0 - 2.2, X1 + 2.2, Y0 - 2.2, Y1 + 2.2, 12.0, 18.0, 'stone')
    bx(g, X0, X1, Y0, Y1, 18.0, ZB, 'stone')
    for z0, z1 in ((46.0, 49.0), (76.0, 79.0)):  # floor string courses
        bx(g, X0 - 1.6, X1 + 1.6, Y0 - 1.6, Y1 + 1.6, z0, z1, 'stone_light')
    for u in (-52.0, -8.0):                      # pilaster strips
        for v, f in ((Y0, -1), (Y1, 1)):
            bx(g, u - 5.0, u + 5.0, v, v + f * 2.6, 18.0, ZB, 'stone_light')
    for v in (-34.0, 34.0):
        bx(g, X0 - 2.6, X0, v - 5.0, v + 5.0, 18.0, ZB, 'stone_light')
    for _ in range(14):                          # rough coursing
        v, f = rng.choice(((Y0, -1), (Y1, 1)))
        u = rng.uniform(X0 + 8, X1 - 8)
        z = rng.uniform(20, 106)
        bx(g, u - 5.0, u + 5.0, v, v + f * 0.6, z, z + rng.uniform(3.0, 4.4),
           rng.choice(('stone_light', 'stone_dark')))

    for u in (-68.0, -30.0, 8.0, 42.0):          # ground storey: loops only
        for v, f in ((Y0, '-y'), (Y1, '+y')):
            loop_hole(g, u, v, 26.0, f, w=6.0, h=14.0)
    for u in (-68.0, -30.0, 8.0, 42.0):          # first floor
        keep_window(g, u, Y0, '-y', 9.0, 15.0, 54.0)
        keep_window(g, u, Y1, '+y', 9.0, 15.0, 54.0)
    for u in (-64.0, -20.0, 24.0):               # great hall
        keep_window(g, u, Y0, '-y', 15.0, 25.0, 84.0, style='mullion')
        keep_window(g, u, Y1, '+y', 15.0, 25.0, 84.0, style='mullion')
    for v in (-40.0, 0.0, 40.0):
        loop_hole(g, X0, v, 28.0, '-x', w=6.0, h=14.0)
        keep_window(g, X0, v, '-x', 9.0, 15.0, 54.0)
    for v in (-30.0, 30.0):
        keep_window(g, X0, v, '-x', 14.0, 23.0, 84.0, style='arched')

    battlements(g, X0 - 2.6, X1 + 2.6, Y0 - 2.6, Y1 + 2.6, ZB, 118.5, 129.0,
                thick=10.0, period=17.0, mer=9.5, corner=13.0, corbel=18.0)

    for sx, sy in ((X0, Y0), (X0, Y1), (X1, Y0), (X1, Y1)):   # corner turrets
        cyl(sx, sy, 0, 21.5, 12.0, 'stone_dark', g, verts=12)
        cyl(sx, sy, 12.0, 19.6, 6.0, 'stone', g, verts=12)
        cyl(sx, sy, 18.0, 18.0, 110.0, 'stone', g, verts=12)
        cyl(sx, sy, 100.0, 19.3, 2.6, 'stone_light', g, verts=12)
        for zz in (44.0, 84.0):
            a = R(45 if sx > 0 else 135) * (1 if sy > 0 else -1)
            box(sx + math.cos(a) * 17.6, sy + math.sin(a) * 17.6, zz,
                1.8, 5.4, 12.0, 'stone_light', g, rot=(0, 0, a))
            box(sx + math.cos(a) * 18.4, sy + math.sin(a) * 18.4, zz + 2.0,
                0.8, 2.0, 8.0, 'soot', g, rot=(0, 0, a))
        battlements_round(g, sx, sy, 19.6, 8.0, 128.0, 136.0, 152.0, n=8,
                          solid=True)

    # the hall roof and the flues that serve its fires
    bx(g, X0 + 6.0, X1 - 6.0, Y0 + 8.0, Y1 - 8.0, 106.0, 109.0, 'timber')
    wedge(-15.0, 0.0, 109.0, 128.0, 112.0, 35.0, 'roof_slate', g)
    bx(g, -80.0, 50.0, -2.4, 2.4, 141.0, 144.6, 'roof_slate')
    bx(g, -26.0, 4.0, -9.5, 9.5, 136.0, 144.0, 'timber')           # louvre
    ramp(-11.0, 0.0, 144.0, 32.0, 21.0, 5.0, 'roof_slate', g)
    for u in (-58.0, 14.0):                                        # chimneys
        bx(g, u - 8.0, u + 8.0, Y1 - 7.0, Y1 + 4.0, 79.0, 148.0, 'stone')
        bx(g, u - 9.4, u + 9.4, Y1 - 8.4, Y1 + 5.4, 148.0, 151.0, 'stone_light')
        for k in (-3.6, 3.6):
            bx(g, u + k - 2.2, u + k + 2.2, Y1 - 3.0, Y1 + 1.0, 150.0, 151.4, 'soot')

    # forebuilding: the stair, the raised door, and its own battlements
    bx(g, F0, F1 + 1.5, -FY - 3.0, FY + 3.0, 0, 12.0, 'stone_dark')
    bx(g, F0, F1, -FY, FY, 12.0, 68.0, 'stone')
    bx(g, F0, F1 + 1.6, -FY - 1.6, FY + 1.6, 46.0, 49.0, 'stone_light')
    loop_hole(g, F1, -14.0, 54.0, '+x', w=6.0, h=13.0)
    loop_hole(g, F1, 14.0, 54.0, '+x', w=6.0, h=13.0)
    loop_hole(g, 70.0, -FY, 20.0, '-y', w=6.0, h=13.0)
    bx(g, F1 - 1.0, F1 + 2.2, -9.0, 5.0, 0, 20.0, 'stone_light')   # postern
    bx(g, F1 - 1.6, F1 + 2.6, -7.4, 3.4, 0, 17.0, 'soot')
    battlements(g, F0, F1 + 2.4, -FY - 2.4, FY + 2.4, 68.0, 74.0, 82.5,
                thick=8.0, period=12.0, mer=6.5, corner=9.5, sides='nse',
                corbel=9.0)

    SX0, SX1 = F1, F1 + 14.0                                       # entrance stair
    for i in range(11):
        yy = -30.0 + i * 3.1
        bx(g, SX0, SX1, yy, yy + 3.2, 0, 3.0 + i * 2.9, 'stone')
    bx(g, SX0, SX1, 4.1, 20.0, 0, 32.0, 'stone')
    bx(g, SX1 - 2.6, SX1, -30.0, 20.0, 0, 12.0, 'stone_dark')
    box(SX1 - 1.4, -13.0, 15.8, 2.8, 46.0, 3.4, 'stone_light', g, rot=(R(40), 0, 0))
    box(SX1 - 1.4, -13.0, 3.0, 2.8, 44.0, 12.0, 'stone', g, rot=(R(40), 0, 0))
    bx(g, SX1 - 1.4, SX1 + 1.4, 4.1, 20.0, 32.0, 38.0, 'stone_light')
    bx(g, F1 - 1.2, F1 + 2.4, 5.0, 21.0, 32.0, 56.0, 'stone_light')   # the door
    bx(g, F1 - 1.8, F1 + 2.8, 6.6, 19.4, 32.0, 51.0, 'soot')
    for k in range(5):
        th = math.pi * (k + 0.5) / 5
        box(F1 + 0.9, 13.0 + math.cos(th) * 8.8, 51.0 + math.sin(th) * 8.8 - 2.7,
            3.4, 5.2, 5.4, 'stone_light', g, rot=(th, 0, 0))
    bx(g, F1 + 0.4, F1 + 1.9, 7.0, 19.0, 32.0, 50.0, 'timber')
    for zz in (36.0, 44.0):
        bx(g, F1 + 1.9, F1 + 2.5, 7.0, 19.0, zz, zz + 2.2, 'iron')
    return g


# ------------------------------------------------------- bailey buildings

def join_as(objs, name):
    """Weld a set of boxes into one named object — used for the faction banner,
    which the runtime looks up by name to recolour."""
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    objs[0].name = name
    bpy.ops.object.select_all(action='DESELECT')
    return objs[0]


def framed_wall(g, ax, v, u0, u1, z0, z1, bays=5, s=2.4, out=0.9, brace=True):
    """Timber studs, rails and braces on a plastered face."""
    for i in range(bays + 1):
        u = u0 + (u1 - u0) * i / bays
        if ax == 'x':
            bx(g, u - s / 2, u + s / 2, v, v + out, z0, z1, 'timber')
        else:
            bx(g, v, v + out, u - s / 2, u + s / 2, z0, z1, 'timber')
    for zz in (z0, z1 - s):
        if ax == 'x':
            bx(g, u0, u1, v, v + out, zz, zz + s, 'timber')
        else:
            bx(g, v, v + out, u0, u1, zz, zz + s, 'timber')
    if brace:
        for i in range(bays):
            u = u0 + (u1 - u0) * (i + 0.5) / bays
            w = (u1 - u0) / bays * 0.5
            d = 1 if i % 2 == 0 else -1
            if ax == 'x':
                diag(g, u - w * d, 0, z0 + s, math.hypot(2 * w, z1 - z0 - 2 * s),
                     s * 0.8, 'timber', pitch=math.atan2(z1 - z0 - 2 * s, 2 * w * d))
                bpy.context.object.location.y = v + out / 2
            else:
                diag(g, 0, u - w * d, z0 + s,
                     math.hypot(2 * w, z1 - z0 - 2 * s), s * 0.8, 'timber',
                     pitch=math.atan2(z1 - z0 - 2 * s, 2 * w * d), yaw=R(90))
                bpy.context.object.location.x = v + out / 2


def barracks():
    """Long hall for a garrison: stone to the sills, timber frame above, three
    doors onto the bailey, and the flue for the stove that keeps it liveable."""
    g = empty('barracks')
    X, Y = 50.0, 22.0
    bx(g, -X - 3, X + 3, -Y - 3, Y + 3, 0, 7.0, 'stone_dark')
    bx(g, -X - 1.4, X + 1.4, -Y - 1.4, Y + 1.4, 7.0, 9.5, 'stone')
    bx(g, -X, X, -Y, Y, 9.5, 19.0, 'stone')
    bx(g, -X, X, -Y, Y, 19.0, 33.0, 'plaster')
    for v, f in ((-Y, -1), (Y, 1)):
        framed_wall(g, 'x', v if f < 0 else v - 0.9, -X, X, 19.0, 33.0, bays=7)
    for u, f in ((-X, -1), (X, 1)):
        framed_wall(g, 'y', u if f < 0 else u - 0.9, -Y, Y, 19.0, 33.0, bays=3)
    for u in (-30.0, 0.0, 30.0):                       # doors onto the bailey
        bx(g, u - 7.5, u + 7.5, Y - 0.6, Y + 2.2, 9.5, 26.0, 'timber')
        bx(g, u - 6.0, u + 6.0, Y + 1.0, Y + 2.6, 9.5, 24.5, 'soot')
        plank_door(g, u - 5.6, u + 5.6, Y + 1.6, 1.4, 9.5, 24.0, bands=2)
        bx(g, u - 9.0, u + 9.0, Y - 0.6, Y + 6.0, 26.0, 28.4, 'timber')
        bx(g, u - 8.0, u + 8.0, Y + 1.6, Y + 5.0, 0, 9.5, 'stone_dark')
    for u in (-42.0, -16.0, 16.0, 42.0):               # shuttered lights
        for v, f in ((-Y, -1), (Y, 1)):
            bx(g, u - 5.5, u + 5.5, v + f * 0.9, v, 21.0, 29.0, 'soot')
            bx(g, u - 6.6, u + 6.6, v, v + f * 1.2, 20.2, 21.4, 'timber_light')
            bx(g, u - 6.6, u + 6.6, v + f * 1.0, v + f * 1.9, 21.4, 29.0, 'timber')
    for u in (-16.0, 16.0):                             # shields on the wall
        bx(g, u - 5.0, u + 5.0, Y + 0.9, Y + 2.0, 12.0, 22.0, 'cloth')
        bx(g, u - 5.6, u + 5.6, Y + 0.9, Y + 1.4, 12.0, 22.0, 'timber')
        bx(g, u - 1.0, u + 1.0, Y + 2.0, Y + 2.7, 15.5, 18.5, 'iron')
    pitched_roof(0, 0, 33.0, 2 * X, 2 * Y, 14.0, 'roof_slate', g, overhang=3.5)
    bx(g, -44.0, -34.0, -7.0, 7.0, 33.0, 58.0, 'stone')            # stove flue
    bx(g, -45.4, -32.6, -8.4, 8.4, 58.0, 60.6, 'stone_light')
    bx(g, -41.0, -37.0, -3.0, 3.0, 60.6, 62.0, 'soot')
    for sx in (-1, 1):                                  # water butt and bench
        cyl(sx * 46.0, -Y - 6.0, 0, 5.0, 11.0, 'timber_light', g, verts=8)
        cyl(sx * 46.0, -Y - 6.0, 9.0, 5.3, 1.4, 'iron_dark', g, verts=8)
    bx(g, -16.0, 16.0, Y + 8.0, Y + 13.0, 6.5, 8.0, 'timber_light')
    for u in (-14.0, 14.0):
        bx(g, u - 1.6, u + 1.6, Y + 8.6, Y + 12.4, 0, 6.5, 'timber')
    return g


def storehouse_military():
    """Armoury store: stone below, boarded loft above, double doors wide
    enough for a cart, and the hoist beam that swings loads into the loft."""
    g = empty('storehouse_military')
    X, Y = 38.0, 24.0
    bx(g, -X - 3, X + 3, -Y - 3, Y + 3, 0, 8.0, 'stone_dark')
    bx(g, -X, X, -Y, Y, 8.0, 24.0, 'stone')
    bx(g, -X, X, -Y, Y, 24.0, 40.0, 'timber_light')
    for v, f in ((-Y, -1), (Y, 1)):
        framed_wall(g, 'x', v if f < 0 else v - 0.9, -X, X, 24.0, 40.0, bays=4,
                    brace=False)
    for u in (-24.0, 0.0, 24.0):
        bx(g, -X - 0.8, -X + 0.2, u - 2.2, u + 2.2, 8.0, 40.0, 'timber')
    bx(g, X - 1.0, X + 3.0, -15.0, 15.0, 0, 34.0, 'stone_light')   # cart doors
    bx(g, X - 1.6, X + 2.2, -13.0, 13.0, 0, 31.0, 'soot')
    for sy in (-1, 1):
        bx(g, X + 0.6, X + 2.2, sy * 0.4 if sy > 0 else -13.0,
           13.0 if sy > 0 else -0.4, 0, 31.0, 'timber')
        for zz in (5.0, 15.0, 25.0):
            bx(g, X + 2.2, X + 3.0, sy * 0.4 if sy > 0 else -13.0,
               13.0 if sy > 0 else -0.4, zz, zz + 2.4, 'iron')
    bx(g, X - 1.0, X + 4.0, -16.5, 16.5, 34.0, 37.0, 'stone')
    for u in (-9.0, 9.0):                                          # loft light
        bx(g, X - 0.8, X + 1.4, u - 4.0, u + 4.0, 28.0, 36.0, 'soot')
    for u in (-26.0, -13.0, 13.0, 26.0):                           # loft shutters
        for v, f in ((-Y, -1), (Y, 1)):
            bx(g, u - 5.0, u + 5.0, v + f * 1.1, v, 27.0, 35.0, 'soot')
            bx(g, u - 5.6, u + 5.6, v, v + f * 1.6, 27.0, 35.0, 'timber')
    bx(g, X - 2.0, X + 14.0, -2.4, 2.4, 44.0, 47.5, 'timber')      # hoist beam
    bx(g, X - 2.0, X + 4.0, -3.2, 3.2, 40.0, 44.0, 'timber')
    diag(g, X - 1.0, 0, 38.0, 12.0, 2.2, 'timber', pitch=R(34))
    cyl(X + 11.5, 0, 39.0, 0.9, 5.0, 'iron_dark', g, verts=6)
    chain(g, X + 11.5, 0, 39.0, 44.0, s=1.2, links=4)
    bx(g, X + 9.5, X + 13.5, -3.0, 3.0, 33.0, 39.0, 'timber_light')
    pitched_roof(0, 0, 40.0, 2 * X, 2 * Y, 13.0, 'roof_tile', g, overhang=3.5)
    for (u, v, r, h) in ((-X - 8, -14, 4.6, 10.0), (-X - 8, -3, 4.6, 10.0),
                         (-X - 9, 12, 5.0, 11.0)):
        cyl(u, v, 0, r, h, 'timber_light', g, verts=8)
        cyl(u, v, h - 1.4, r + 0.3, 1.4, 'iron_dark', g, verts=8)
    for (u, v, w, rz) in ((X + 12, -22, 9.0, 0.2), (X + 10, -20, 8.0, -0.4)):
        box(u, v, 0, w, w * 0.9, w * 0.8, 'timber_light', g, rot=(0, 0, rz))
    return g


# ------------------------------------------------------------- camp props

def guy_rope(g, x0, y0, z0, x1, y1, s=0.55, peg=True):
    """A guy line from a point on the tent down to a peg, and the peg."""
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(math.hypot(dx, dy), z0)
    diag(g, x1, y1, 0.6, L, s, 'leather',
         pitch=math.atan2(z0 - 0.6, math.hypot(dx, dy)),
         yaw=math.atan2(-dy, -dx))
    if peg:
        box(x1, y1, 0, 1.5, 1.5, 3.4, 'timber', g, rot=(R(12), 0, 0))


def _ridge_tent(g, X, Y, H, bays, seed, flap=True, valance=None):
    """A canvas ridge tent: pole, ridge, sagging bays of canvas, guys, pegs."""
    rng = random.Random(seed)
    EZ = 1.0                                             # eave, just off the turf
    th = math.atan2(Y, H - EZ)
    L = math.hypot(Y, H - EZ) + 1.6
    for i in range(bays):
        u0 = -X + 2 * X * i / bays
        u1 = -X + 2 * X * (i + 1) / bays
        sag = 0.0 if i in (0, bays - 1) else rng.uniform(0.6, 1.4)
        for sy in (-1, 1):
            box((u0 + u1) / 2, sy * Y / 2, (H + EZ) / 2 - L / 2 - sag,
                (u1 - u0) * 0.99, 1.8, L, 'canvas', g, rot=(sy * th, 0, 0))
    for sx in (-1, 1):                                   # ridge and end poles
        bx(g, sx * X - 1.5, sx * X + 1.5, -1.5, 1.5, 0, H + 1.5, 'timber')
    bx(g, -X - 1.0, X + 1.0, -1.3, 1.3, H - 1.0, H + 1.4, 'timber')
    for sx in (-1, 1):
        for sy in (-1, 1):
            guy_rope(g, sx * X, sy * 1.0, H + 1.0, sx * (X + 9.0), sy * 8.0)
            guy_rope(g, sx * (X * 0.35), sy * (Y - 1.0), 3.5,
                     sx * (X * 0.35), sy * (Y + 7.0), s=0.45)
    for i in range(bays * 2):                            # pegged hem
        u = -X + 2 * X * (i + 0.5) / (bays * 2)
        for sy in (-1, 1):
            box(u, sy * (Y + 0.7), 0, 1.2, 1.2, 2.6, 'timber', g)
    if flap:                                             # rolled door flap
        for sy in (-1, 1):
            cyl_axis(g, 'x', X - 0.6, sy * 2.6, 8.0, 2.4, 2.0, 'canvas', verts=6)
            box(X - 1.2, sy * 3.4, 0, 2.0, 3.0, 9.0, 'canvas', g,
                rot=(0, 0, sy * R(9)))
    if valance:
        for sy in (-1, 1):
            bx(g, -X - 0.5, X + 0.5, sy * Y - 1.3, sy * Y + 1.3, 2.2, 5.4, valance)


def tent_a():
    """Common soldier's ridge tent."""
    g = empty('tent_a')
    _ridge_tent(g, 17.0, 11.0, 19.0, 3, seed=61)
    box(14.0, -14.0, 0, 6.0, 5.0, 4.5, 'timber_light', g, rot=(0, 0, R(14)))
    cyl(-13.0, 14.0, 0, 3.6, 7.0, 'timber_light', g, verts=8)
    cyl(-13.0, 14.0, 5.8, 3.9, 1.2, 'iron_dark', g, verts=8)
    return g


def tent_b():
    """Bell tent — a centre pole, a cone of canvas, a rolled door."""
    g = empty('tent_b')
    rng = random.Random(67)
    RB, H = 15.0, 8.0
    cyl(0, 0, 0, RB, H, 'canvas', g, verts=10)
    cone(g, 0, 0, H, RB + 0.6, 2.2, 13.0, 'canvas', verts=10)
    cyl(0, 0, 0, 1.5, H + 15.5, 'timber', g, verts=6)
    cyl(0, 0, H + 15.5, 1.0, 3.4, 'iron', g, verts=6)
    bx(g, -0.8, 0.8, 1.0, 8.5, H + 18.5, H + 23.0, 'cloth')       # pennant
    for k in range(10):                                            # guys and pegs
        a = math.tau * k / 10 + 0.31
        if 1.1 < a < 2.0:
            continue
        guy_rope(g, math.cos(a) * (RB - 1), math.sin(a) * (RB - 1), H + 6.0,
                 math.cos(a) * (RB + 5.5), math.sin(a) * (RB + 5.5), s=0.45)
    for sy in (-1, 1):                                             # door
        box(RB - 1.0, sy * 4.0, 0, 2.2, 3.6, H + 6.0, 'canvas', g,
            rot=(0, 0, sy * R(11)))
    bx(g, RB - 2.4, RB + 1.0, -4.2, 4.2, 0, 1.2, 'dirt')
    cyl(-11.0, -13.0, 0, 3.4, 6.5, 'timber_light', g, verts=8)
    return g


def command_tent():
    """The captain's marquee: bigger, a porch to receive under, a faction
    valance round the eaves and a banner mount at the ridge."""
    g = empty('command_tent')
    _ridge_tent(g, 26.0, 17.0, 27.0, 4, seed=71, flap=False, valance='cloth')
    for sy in (-1, 1):                                   # porch
        bx(g, 34.0, 37.0, sy * 12.5 - 1.6, sy * 12.5 + 1.6, 0, 19.0, 'timber')
        bx(g, 32.0, 39.0, sy * 12.5 - 2.0, sy * 12.5 + 2.0, 17.0, 19.4, 'timber')
        guy_rope(g, 36.0, sy * 12.5, 19.0, 46.0, sy * 16.0, s=0.5)
    bx(g, 24.0, 27.0, -14.0, 14.0, 20.0, 22.4, 'timber')
    box(31.0, 0, 20.0, 15.0, 28.0, 1.7, 'canvas', g, rot=(0, R(11), 0))
    bx(g, 24.0, 25.6, -13.5, 13.5, 4.0, 7.4, 'cloth')
    for sy in (-1, 1):                                   # tied-back door leaves
        box(25.5, sy * 8.5, 0, 2.4, 4.6, 17.0, 'canvas', g, rot=(0, 0, sy * R(13)))
    bx(g, -30.0, -22.0, -3.0, 3.0, 0, 1.4, 'dirt')       # trodden ground
    bx(g, 24.0, 40.0, -8.0, 8.0, 0, 1.0, 'dirt')

    bx(g, -29.0, -26.0, -1.6, 1.6, 0, 58.0, 'timber')    # banner mount
    bx(g, -30.4, -24.6, -3.0, 3.0, 0, 3.2, 'stone_dark')
    bx(g, -30.0, -25.0, -2.2, 2.2, 30.0, 32.0, 'iron_dark')
    bx(g, -29.8, -25.2, -2.0, 17.0, 53.0, 55.2, 'iron')
    wedge(-27.5, 0, 58.0, 3.0, 3.0, 5.0, 'steel', g, rot=(0, 0, R(90)))
    banner = []
    for i in range(5):
        v0 = 1.2 + i * 3.0
        off = math.sin(i * 1.2) * 1.1
        banner.append(bx(g, -28.6 + off, -26.4 + off, v0, v0 + 3.1, 28.0, 53.0,
                         'cloth'))
    join_as(banner, 'banner_cloth')
    for (u, v, r, h) in ((-34.0, 12.0, 4.4, 9.5), (-33.0, 19.0, 4.0, 8.5)):
        cyl(u, v, 0, r, h, 'timber_light', g, verts=8)
        cyl(u, v, h - 1.4, r + 0.3, 1.4, 'iron_dark', g, verts=8)
    return g


def banner_pole():
    """Faction standard. The pole and the cloth are separate objects and the
    cloth is named 'banner_cloth' — the runtime recolours only that."""
    g = empty('banner_pole')
    bx(g, -6.0, 6.0, -6.0, 6.0, 0, 3.0, 'stone_dark')     # footing
    bx(g, -4.4, 4.4, -4.4, 4.4, 3.0, 5.0, 'stone')
    for a in (0.4, 2.5, 4.6):                             # bracing feet
        diag(g, math.cos(a) * 3.2, math.sin(a) * 3.2, 5.0, 9.0, 1.8, 'timber',
             pitch=R(-32), yaw=a)
    bx(g, -1.9, 1.9, -1.9, 1.9, 3.0, 54.0, 'timber')      # pole
    for zz in (10.0, 26.0):
        bx(g, -2.3, 2.3, -2.3, 2.3, zz, zz + 1.8, 'iron_dark')
    bx(g, -1.4, 1.4, -1.4, 1.4, 54.0, 57.0, 'iron')       # finial
    wedge(0, 0, 57.0, 2.8, 2.8, 6.0, 'steel', g, rot=(0, 0, R(90)))
    bx(g, -1.4, 1.4, -1.0, 19.0, 50.0, 52.0, 'iron')      # cross bar
    bx(g, 1.4, 2.0, 17.0, 19.0, 48.0, 52.0, 'iron_dark')
    strips = []
    for i in range(5):                                    # the cloth, waving
        v0 = 1.4 + i * 3.4
        off = math.sin(i * 1.15) * 1.5
        strips.append(bx(g, -1.5 + off, 1.5 + off, v0, v0 + 3.5, 22.0, 50.0, 'cloth'))
        strips.append(bx(g, -1.5 + off, 1.5 + off, v0, v0 + 3.5,
                         17.0 + (i % 2) * 5.0, 22.0, 'cloth'))
    join_as(strips, 'banner_cloth')
    return g


# ------------------------------------------------- field works and wreckage

def stake(g, x, y, h, w=4.6, tilt=0.0, yaw=0.0, material='timber'):
    """A sharpened timber stake: shaft plus an axe-cut chisel point."""
    box(x, y, 0, w, w, h, material, g, rot=(tilt, 0, yaw))
    wedge(x + math.sin(yaw) * 0 - math.sin(tilt) * h, y + math.sin(tilt) * h * 0,
          h - 0.2, w, w, w * 0.95, 'timber_light', g, rot=(tilt, 0, yaw))


def palisade_segment():
    """Tileable timber palisade, exactly 60 along +X. Stakes on a 5-unit
    pitch, rails and bank running the full length so runs butt cleanly."""
    g = empty('palisade_segment')
    rng = random.Random(83)
    for i in range(12):
        x = -27.5 + i * 5.0
        h = 30.0 + rng.uniform(-3.0, 3.6)
        w = 4.4 + rng.uniform(-0.5, 0.7)
        box(x, 0, 0, w, 4.8, h, 'timber', g, rot=(0, 0, rng.uniform(-0.05, 0.05)))
        cone(g, x, 0, h - 0.4, w * 0.72, 0.0, w * 1.9, 'timber_light', verts=4,
             rot=(0, 0, R(45)))
    for zz, dy in ((11.0, 3.2), (23.0, 3.0)):            # rails, inner face
        bx(g, -30.0, 30.0, dy, dy + 2.4, zz, zz + 3.0, 'timber_light')
    ramp(0, 12.0, 0, 60.0, 18.0, 11.0, 'dirt', g)        # earth bank behind
    bx(g, -30.0, 30.0, 3.0, 12.0, 10.0, 11.6, 'dirt')
    for _ in range(7):
        box(rng.uniform(-23, 23), rng.uniform(6.0, 17.0), 0,
            rng.uniform(4, 6), rng.uniform(3, 5), rng.uniform(2.5, 4.5),
            rng.choice(('stone_dark', 'stone', 'dirt')), g,
            rot=(0, 0, rng.uniform(0, 3)))
    for x in (-22.0, -2.0, 18.0):                        # fighting step
        bx(g, x - 1.6, x + 1.6, 12.5, 15.5, 0, 14.0, 'timber')
        diag(g, x, 15.0, 2.0, 14.0, 2.0, 'timber', pitch=R(-52), yaw=R(90))
    bx(g, -30.0, 30.0, 12.0, 20.0, 14.0, 15.6, 'timber_light')
    bx(g, -30.0, 30.0, -3.0, 2.6, 0, 2.2, 'dirt')        # spoil at the foot
    return g


def barricade():
    """Hasty barring of a road: two saltires of sharpened timber lashed under a
    ridge beam, boards nailed across the face, spoil heaped behind. Thrown up
    in an afternoon, not built."""
    g = empty('barricade')
    rng = random.Random(89)
    SY, SZ = 9.5, 21.0
    LL = math.hypot(2 * SY, SZ)
    ang = math.atan2(SZ, 2 * SY)
    for sx in (-1, 1):                                   # crossed stake frames
        x = sx * 13.0
        diag(g, x, -SY, 0, LL + 4.0, 3.4, 'timber', pitch=ang, yaw=R(90))
        diag(g, x, SY, 0, LL + 4.0, 3.4, 'timber', pitch=ang, yaw=R(-90))
        for sy in (-1, 1):
            bx(g, x - 2.6, x + 2.6, sy * (SY + 1.4) - 1.6, sy * (SY + 1.4) + 1.6,
               SZ + 1.0, SZ + 4.6, 'leather')
        bx(g, x - 2.4, x + 2.4, -3.0, 3.0, 9.0, 12.0, 'leather')
    bx(g, -20.0, 20.0, -2.0, 2.0, SZ - 1.0, SZ + 2.6, 'timber')    # ridge beam
    for i in range(5):                                   # boards across the face
        z = 3.0 + i * 3.6
        w = rng.uniform(26.0, 38.0)
        box(rng.uniform(-4.0, 4.0), rng.uniform(-6.0, -4.2), z, w, 2.0, 3.2,
            'timber_light', g, rot=(0, rng.uniform(-0.07, 0.07), 0))
    for i in range(4):                                   # spikes facing the road
        u = -15.0 + i * 10.0
        diag(g, u, -5.0, 7.0 + (i % 2) * 4.0, 15.0, 2.2, 'steel',
             pitch=R(-14), yaw=R(-90))
    ramp(0, 9.0, 0, 42.0, 16.0, 8.0, 'dirt', g, rot=(0, 0, R(180)))
    for _ in range(6):
        box(rng.uniform(-19, 19), rng.uniform(3.0, 14.0), 0,
            rng.uniform(5, 9), rng.uniform(4, 7), rng.uniform(3, 5),
            rng.choice(('stone', 'stone_dark', 'dirt')), g,
            rot=(0, 0, rng.uniform(0, 3)))
    return g


def weapon_rack():
    """Spears racked butt-down between two rails, shields hung on the face.
    The shield faces take the faction colour."""
    g = empty('weapon_rack')
    rng = random.Random(97)
    bx(g, -15.0, 15.0, -6.5, 6.5, 0, 2.4, 'timber')          # butt board
    for sx in (-1, 1):                                        # end frames
        bx(g, sx * 13.5 - 1.8, sx * 13.5 + 1.8, -6.0, -3.0, 0, 23.0, 'timber')
        bx(g, sx * 13.5 - 1.8, sx * 13.5 + 1.8, 3.0, 6.0, 0, 23.0, 'timber')
        bx(g, sx * 13.5 - 1.8, sx * 13.5 + 1.8, -6.0, 6.0, 20.0, 23.0, 'timber')
        bx(g, sx * 13.5 - 2.2, sx * 13.5 + 2.2, -6.4, 6.4, 0, 2.6, 'iron_dark')
    for v in (-4.5, 4.5):                                     # rails
        bx(g, -14.6, 14.6, v - 1.2, v + 1.2, 16.5, 19.0, 'timber_light')
    for i in range(6):                                        # spears
        x = -10.5 + i * 4.2 + rng.uniform(-0.4, 0.4)
        h = 27.0 + rng.uniform(-1.5, 1.8)
        yaw = rng.uniform(-0.05, 0.05)
        box(x, 0, 2.4, 1.4, 1.4, h, 'timber_light', g, rot=(0, 0, yaw))
        cone(g, x, 0, 2.4 + h, 1.5, 0.0, 5.4, 'steel', verts=4, rot=(0, 0, R(45)))
        bx(g, x - 1.0, x + 1.0, -1.1, 1.1, 2.4 + h - 1.4, 2.4 + h + 0.4, 'iron')
    for u in (-8.0, 6.5):                                     # shields
        bx(g, u - 5.4, u + 5.4, -8.6, -7.4, 3.5, 15.5, 'timber')
        bx(g, u - 4.8, u + 4.8, -9.2, -8.6, 4.2, 14.8, 'cloth')
        bx(g, u - 1.2, u + 1.2, -9.6, -9.2, 8.4, 11.4, 'iron')
    return g


def siege_ladder():
    """Scaling ladder pitched against nothing yet: iron-shod feet, hooked head
    to bite the parapet, a spur to stop the foot kicking out."""
    g = empty('siege_ladder')
    e = empty('ladder')
    e.parent = g
    L, W = 70.0, 13.0
    for sy in (-1, 1):
        bx(e, -1.8, 1.8, sy * W / 2 - 1.9, sy * W / 2 + 1.9, 0, L, 'timber')
    for i in range(9):
        z = 5.0 + i * 7.4
        bx(e, -1.4, 1.4, -W / 2, W / 2, z, z + 2.4, 'timber_light')
    for sy in (-1, 1):                                   # iron hooks and shoes
        bx(e, -2.2, 2.2, sy * W / 2 - 2.3, sy * W / 2 + 2.3, L - 4.0, L + 2.0, 'iron')
        diag(e, 1.8, sy * W / 2, L + 1.0, 8.0, 2.0, 'iron_dark', pitch=R(-28))
        bx(e, -2.4, 2.4, sy * W / 2 - 2.3, sy * W / 2 + 2.3, 0, 4.0, 'iron_dark')
        wedge(0, sy * W / 2, -1.6, 4.6, 4.6, 2.0, 'steel', e, rot=(0, R(180), 0))
    bx(e, -2.6, 2.6, -W / 2 - 1.0, W / 2 + 1.0, 20.0, 22.0, 'iron')
    e.rotation_euler = (0, R(-24), 0)
    e.location = (-8.0, 0, 0)
    diag(g, 14.0, 0, 0, 22.0, 2.6, 'timber', pitch=R(44), yaw=R(180))
    return g


def rubble_pile():
    """A stretch of wall that lost: tumbled ashlar, a merlon on its side with
    its coping still attached, snapped roof timbers, dust."""
    g = empty('rubble_pile')
    rng = random.Random(101)
    for _ in range(5):                                   # broken ground
        box(rng.uniform(-13, 13), rng.uniform(-8, 6), 0,
            rng.uniform(14, 24), rng.uniform(12, 20), rng.uniform(1.6, 3.4),
            'dirt', g, rot=(0, 0, rng.uniform(0, 3)))
    box(-7.0, -4.0, 3.4, 6.0, 9.5, 11.0, 'stone', g, rot=(R(72), 0, R(18)))
    box(-7.0, -4.0, 8.6, 7.0, 10.6, 1.4, 'stone_light', g, rot=(R(72), 0, R(18)))
    box(7.0, 2.0, 2.6, 6.0, 9.5, 10.0, 'stone', g, rot=(R(-64), 0, R(-26)))
    for _ in range(13):
        w = rng.uniform(5.0, 11.0)
        box(rng.uniform(-18, 17), rng.uniform(-10, 8), rng.uniform(0, 5.5),
            w, w * rng.uniform(0.6, 0.95), w * rng.uniform(0.45, 0.8),
            rng.choice(('stone', 'stone', 'stone_dark', 'stone_light')), g,
            rot=(rng.uniform(-0.5, 0.5), rng.uniform(-0.4, 0.4),
                 rng.uniform(0, 3.1)))
    for _ in range(4):
        box(rng.uniform(-14, 14), rng.uniform(-9, 6), rng.uniform(1, 6),
            rng.uniform(14, 24), 2.6, 2.6, 'timber', g,
            rot=(0, rng.uniform(-0.3, 0.3), rng.uniform(0, 3.1)))
    for _ in range(6):
        box(rng.uniform(-19, 18), rng.uniform(-12, 8), 0,
            rng.uniform(3, 6), rng.uniform(3, 5), rng.uniform(1.4, 2.6),
            rng.choice(('stone_dark', 'dirt')), g, rot=(0, 0, rng.uniform(0, 3)))
    return g


def broken_cart():
    """Supply cart that did not make it: the near wheel has come off its axle,
    the bed has dropped onto the stub, the shaft is snapped, the load is out."""
    g = empty('broken_cart')
    rng = random.Random(103)
    roll = R(-11)

    for _ in range(4):                                   # churned ground
        box(rng.uniform(-8, 12), rng.uniform(-8, 4), 0, rng.uniform(20, 34),
            rng.uniform(16, 26), 1.2, 'dirt', g, rot=(0, 0, rng.uniform(0, 3)))
    box(0, 1.5, 13.5, 34.0, 20.0, 2.8, 'timber', g, rot=(roll, 0, 0))
    for i in range(4):
        box(0, -7.5 + i * 5.0, 13.9, 33.0, 4.2, 1.4, 'timber_light', g,
            rot=(roll, 0, 0))
    for sy in (-1, 1):                                   # side boards
        box(0, 1.5 + sy * 9.6, 15.3, 33.0, 2.2, 8.5, 'timber', g, rot=(roll, 0, 0))
        box(0, 1.5 + sy * 9.6, 19.1, 34.0, 3.0, 1.8, 'timber_light', g,
            rot=(roll, 0, 0))
    box(-16.0, 1.5, 15.1, 2.4, 19.0, 8.0, 'timber', g, rot=(roll, 0, 0))
    box(0, 1.5, 10.6, 30.0, 18.0, 3.0, 'timber', g, rot=(roll, 0, 0))    # underframe
    cyl_axis(g, 'y', -2.0, 1.5, 10.0, 1.9, 30.0, 'iron_dark', verts=6)  # axle

    cyl_axis(g, 'y', -2.0, -12.8, 12.2, 10.0, 2.6, 'timber_light', verts=12)
    cyl_axis(g, 'y', -2.0, -12.8, 12.2, 10.6, 1.2, 'iron_dark', verts=12)
    cyl_axis(g, 'y', -2.0, -12.8, 12.2, 3.0, 4.0, 'timber', verts=8)
    for k in range(3):
        box(-2.0, -12.8, 12.2, 18.0, 2.2, 1.8, 'timber_light', g,
            rot=(0, 0, 0), name=None)
        bpy.context.object.rotation_euler = (math.pi * k / 3, R(90), 0)
    box(-2.0, 13.5, 0, 8.0, 6.5, 4.0, 'stone_dark', g, rot=(0, 0, 0.4))
    for a in (0.5, 1.9, 3.6):                          # the shattered wheel
        box(-4.0 + math.cos(a) * 7.0, 19.0 + math.sin(a) * 6.0, 0,
            rng.uniform(9, 14), 2.4, 2.2, 'timber_light', g, rot=(0, 0, a))

    cyl(16.0, -22.0, 0, 9.2, 2.4, 'timber_light', g, verts=12)          # loose wheel
    cyl(16.0, -22.0, 0, 9.8, 1.1, 'iron_dark', g, verts=12)
    cyl(16.0, -22.0, 0, 3.0, 3.6, 'timber', g, verts=8)
    for k in range(3):
        box(16.0, -22.0, 1.0, 17.0, 2.2, 1.6, 'timber_light', g,
            rot=(0, 0, math.pi * k / 3))
    for sy in (-1, 1):                                                  # shafts
        diag(g, 16.0, 1.5 + sy * 7.0, 11.0, 20.0, 2.6, 'timber',
             pitch=R(-13), yaw=R(4) * sy)
    wedge(34.0, 6.5, 5.6, 3.0, 3.0, 4.4, 'timber_light', g, rot=(0, R(118), 0))
    for _ in range(4):                                                  # spilled
        box(rng.uniform(4, 22), rng.uniform(-20, -8), 0, rng.uniform(6, 9),
            rng.uniform(5, 8), rng.uniform(4, 7), 'timber_light', g,
            rot=(rng.uniform(0, 0.3), 0, rng.uniform(0, 3)))
    for _ in range(3):
        box(rng.uniform(-12, 6), rng.uniform(-22, -12), 0, rng.uniform(5, 7),
            rng.uniform(4, 6), rng.uniform(3, 5), 'thatch', g,
            rot=(0, 0, rng.uniform(0, 3)))
    return g


# ---------------------------------------------------------------- pipeline

ASSETS = {
    'wall_segment': wall_segment,
    'wall_corner': wall_corner,
    'gatehouse': gatehouse,
    'tower_round': tower_round,
    'tower_square': tower_square,
    'keep': keep,
    'barracks': barracks,
    'storehouse_military': storehouse_military,
    'tent_a': tent_a,
    'tent_b': tent_b,
    'command_tent': command_tent,
    'banner_pole': banner_pole,
    'barricade': barricade,
    'palisade_segment': palisade_segment,
    'weapon_rack': weapon_rack,
    'siege_ladder': siege_ladder,
    'rubble_pile': rubble_pile,
    'broken_cart': broken_cart,
}


def merge_by_material(root, keep=KEEP_NAMES):
    """Join an asset's boxes into one mesh per material — a gatehouse ships as
    ~7 nodes instead of ~500, which is the difference between 7 draw calls and
    500 in a browser. Objects named in `keep` are left alone so the runtime can
    still find the faction banner."""
    groups = {}
    stack = [root]
    while stack:
        ob = stack.pop()
        stack.extend(ob.children)
        if ob.type != 'MESH' or not ob.data.materials:
            continue
        if any(ob.name.startswith(k) for k in keep):
            continue
        groups.setdefault(ob.data.materials[0].name, []).append(ob)
    for name, obs in groups.items():
        if len(obs) < 2:
            obs[0].name = name
            continue
        bpy.ops.object.select_all(action='DESELECT')
        for o in obs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = obs[0]
        bpy.ops.object.join()
        obs[0].name = name
    bpy.ops.object.select_all(action='DESELECT')
    return root


def tri_count(root):
    n = 0
    stack = [root]
    while stack:
        ob = stack.pop()
        stack.extend(ob.children)
        if ob.type == 'MESH':
            for p in ob.data.polygons:
                n += len(p.vertices) - 2
    return n


def build_all(out_dir, preview_dir=None, only=None, merge=True):
    names = [n for n in ASSETS if not only or n in only]
    report = []
    for name in names:
        clear_scene()
        root = ASSETS[name]()
        root.name = name
        if merge:
            merge_by_material(root)
        tris = tri_count(root)
        w, d, h = bounds(root)
        export_glb(root, os.path.join(out_dir, name + '.glb'))
        if preview_dir:
            # +35 looks at the outer face (-Y, where the enemy is), -145 inward
            preview_render(root, os.path.join(preview_dir, name + '.png'),
                           azimuth=35.0)
            preview_render(root, os.path.join(preview_dir, name + '_back.png'),
                           azimuth=-145.0)
        line = f'{name:20s} {tris:6d} tris   {w:6.1f} x {d:6.1f} x {h:6.1f}'
        report.append(line)
        print(line, flush=True)
    return report


def extents(root):
    """(lo, hi) world corners of an assembled group."""
    import mathutils
    bpy.context.view_layer.update()
    lo, hi = [1e9] * 3, [-1e9] * 3
    stack = [root]
    while stack:
        ob = stack.pop()
        stack.extend(ob.children)
        if ob.type != 'MESH':
            continue
        for corner in ob.bound_box:
            v = ob.matrix_world @ mathutils.Vector(corner)
            for i, cc in enumerate((v.x, v.y, v.z)):
                lo[i] = min(lo[i], cc)
                hi[i] = max(hi[i], cc)
    return lo, hi


def preview_fort(path, px=1000, angle=27.0, azimuth=26.0):
    """Assemble the modules into one fort and render it. This is the only
    honest test that the curtain tiles, that the corner turns, and that the
    tower, gatehouse and keep heights agree with each other."""
    clear_scene()
    master = empty('fort')

    def put(fn, x, y, rz=0.0):
        root = fn()
        root.location = (x, y, 0)
        root.rotation_euler = (0, 0, rz)
        root.parent = master

    put(gatehouse, -120.0, 0.0)                  # south front
    put(wall_segment, -30.0, 0.0)
    put(wall_segment, 30.0, 0.0)
    put(wall_corner, 90.0, 0.0)                  # turn north
    put(wall_segment, 90.0, 60.0, R(90))
    put(wall_segment, 90.0, 120.0, R(90))
    put(tower_round, 90.0, 175.0)
    put(tower_square, -205.0, 0.0)               # west end of the stone wall
    put(palisade_segment, -265.0, 0.0)           # and the cheap stuff beyond
    put(palisade_segment, -325.0, 0.0)

    put(keep, -30.0, 135.0)                      # inside the bailey
    put(barracks, -160.0, 75.0)
    put(storehouse_military, 30.0, 215.0)
    put(command_tent, -270.0, 95.0)
    put(tent_a, -320.0, 55.0)
    put(tent_b, -215.0, 150.0)
    put(banner_pole, -175.0, 130.0)
    put(weapon_rack, -120.0, 55.0)
    put(siege_ladder, -60.0, 70.0)
    put(barricade, -335.0, 130.0)
    put(rubble_pile, 40.0, 60.0)
    put(broken_cart, 5.0, 80.0)

    lo, hi = extents(master)
    master.location = (-(lo[0] + hi[0]) / 2.0, -(lo[1] + hi[1]) / 2.0, 0)
    preview_render(master, path, px=px, angle=angle, azimuth=azimuth, margin=1.04)
