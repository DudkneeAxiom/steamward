"""STEAMWARD settlement kit — feudal village architecture.

Everything here is composed from a handful of shared modules so a hamlet reads
as one place built by one set of hands:

    footing()      stone plinth every building stands on
    shell()        four walls with real thickness and real holes in them
    door()/window() recessed openings with jambs, sills and shutters
    framing()      timber studs, rails and braces — the variable that makes
                   three cottages look like three cottages, not one thrice
    solid_roof()   thatch: a fat wedge that wraps the gables (pitched_roof)
    plane_roof()   tile/slate: two tilted slabs, leaving open gable ends that
                   get their own plastered, timber-framed gable wall

Nothing mechanical is here for flavour: the well's windlass lifts its bucket,
the watchtower's bell raises the alarm, the barn's doors admit a cart.
"""

import math
import os
import random

import bpy

import common as c
from common import (box, cyl, wedge, ramp, empty, clear_scene, export_glb,
                    preview_render, bounds, pitched_roof)

R = math.radians

# side -> (axis the wall runs along, outward sign on the other axis)
_SIDE = {'e': ('y', +1), 'w': ('y', -1), 'n': ('x', +1), 's': ('x', -1)}


# ------------------------------------------------------------------ modules

def face(parent, side, v):
    """Return a placer for one wall face.

    put(u, off, z, lu, lp, h, mat) — u along the wall, off outward from the
    wall centreline, lu size along the wall, lp size through the wall.
    """
    axis, sgn = _SIDE[side]

    def put(u, off, z, lu, lp, h, material, rot=None):
        if axis == 'y':
            return box(v + sgn * off, u, z, lp, lu, h, material, parent, rot=rot)
        return box(u, v + sgn * off, z, lu, lp, h, material, parent, rot=rot)
    return put


def bar(parent, side, v, off, u0, z0, u1, z1, s, material, out=None):
    """A timber laid diagonally on a wall face, from (u0,z0) to (u1,z1)."""
    axis, sgn = _SIDE[side]
    du, dz = u1 - u0, z1 - z0
    L = math.hypot(du, dz)
    mu, mz = (u0 + u1) / 2.0, (z0 + z1) / 2.0
    out = s if out is None else out
    if axis == 'y':
        a = math.atan2(dz, du)
        return box(v + sgn * off, mu, mz - s / 2.0, out, L, s, material, parent,
                   rot=(a, 0, 0))
    b = -math.atan2(dz, du)
    return box(mu, v + sgn * off, mz - s / 2.0, L, out, s, material, parent,
               rot=(0, b, 0))


def cyl_axis(parent, axis, cx, cy, cz, r, length, material, verts=8, yaw=0.0):
    """A drum lying on its side — axles, windlasses, stacked logs. Placed by
    its centre, because `cyl` places by the base of an upright drum and that
    is the wrong end to think from once the thing is rotated."""
    rot = (R(90), 0, yaw) if axis == 'y' else (0, R(90), yaw)
    return cyl(cx, cy, cz - length / 2.0, r, length, material, parent,
               verts=verts, rot=rot)


def wall_run(parent, axis, u0, u1, v, z, height, thick, material, openings=()):
    """A straight wall with genuine holes punched through it."""
    def slab(a, b, zz, hh):
        if b - a <= 1e-3 or hh <= 1e-3:
            return
        if axis == 'x':
            box((a + b) / 2.0, v, zz, b - a, thick, hh, material, parent)
        else:
            box(v, (a + b) / 2.0, zz, thick, b - a, hh, material, parent)

    cur = u0
    for (uc, ow, z0, z1) in sorted(openings, key=lambda o: o[0]):
        a, b = uc - ow / 2.0, uc + ow / 2.0
        slab(cur, a, z, height)
        slab(a, b, z, z0)
        slab(a, b, z + z1, height - z1)
        cur = b
    slab(cur, u1, z, height)


def shell(parent, cx, cy, z, w, d, h, thick, material, holes=None):
    """Four walls round a footprint. E/W walls own the corners so every
    opening shows the wall's depth in its reveal."""
    holes = holes or {}
    hw, hd = w / 2.0, d / 2.0
    wall_run(parent, 'y', cy - hd, cy + hd, cx + hw - thick / 2.0, z, h, thick,
             material, holes.get('e', ()))
    wall_run(parent, 'y', cy - hd, cy + hd, cx - hw + thick / 2.0, z, h, thick,
             material, holes.get('w', ()))
    wall_run(parent, 'x', cx - hw + thick, cx + hw - thick, cy + hd - thick / 2.0,
             z, h, thick, material, holes.get('n', ()))
    wall_run(parent, 'x', cx - hw + thick, cx + hw - thick, cy - hd + thick / 2.0,
             z, h, thick, material, holes.get('s', ()))


def storeyed_shell(parent, cx, cy, z, w, d, h, thick, lower_h, lower_mat,
                   upper_mat, holes=None):
    """Stone below, plaster above — one wall, two materials, and openings that
    survive the change. Facing the stone on as a solid block instead would
    bury every ground-floor door and window behind it."""
    low, up = {}, {}
    for side, hs in (holes or {}).items():
        for (u, ow, z0, z1) in hs:
            if z0 < lower_h:
                low.setdefault(side, []).append((u, ow, z0, min(z1, lower_h)))
            if z1 > lower_h:
                up.setdefault(side, []).append(
                    (u, ow, max(z0, lower_h) - lower_h, z1 - lower_h))
    shell(parent, cx, cy, z, w, d, lower_h, thick, lower_mat, low)
    shell(parent, cx, cy, z + lower_h, w, d, h - lower_h, thick, upper_mat, up)


def footing(parent, cx, cy, w, d, h, material='stone', top='stone_light'):
    box(cx, cy, 0, w, d, h, material, parent)
    if top:
        box(cx, cy, h, w - 1.6, d - 1.6, 1.4, top, parent)
    return h + (1.4 if top else 0.0)


def band(parent, cx, cy, z, w, d, h, material, proud=0.7):
    """A timber rail wrapped round all four walls — sill beam, mid rail, or
    wall plate. Two boxes, not four, so it stays cheap."""
    box(cx, cy, z, w + proud * 2, d - 0.4, h, material, parent)
    box(cx, cy, z, w - 0.4, d + proud * 2, h, material, parent)


def corner_posts(parent, cx, cy, z, w, d, h, s=4.2, material='timber'):
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(cx + sx * (w / 2.0 - s / 2.0 + 0.6), cy + sy * (d / 2.0 - s / 2.0 + 0.6),
                z, s, s, h, material, parent)


def framing(parent, side, v, bays, z, h, style, s=2.6, off=1.0,
            material='timber'):
    """Timber worked into a plaster panel. `bays` are (u0, u1) clear ranges."""
    put = face(parent, side, v)
    for (u0, u1) in bays:
        span = u1 - u0
        if span < 4:
            continue
        if style == 'studs':                       # close studding
            n = max(1, int(span / 9.5))
            for i in range(1, n + 1):
                u = u0 + span * i / (n + 1.0)
                put(u, off, z, s, s + 0.6, h, material)
        elif style == 'cross':                     # St Andrew's cross
            bar(parent, side, v, off, u0 + 1.5, z + 1, u1 - 1.5, z + h - 1, s, material, out=s + 0.6)
            bar(parent, side, v, off, u0 + 1.5, z + h - 1, u1 - 1.5, z + 1, s, material, out=s + 0.6)
        elif style == 'chevron':                   # herringbone pair
            um = (u0 + u1) / 2.0
            bar(parent, side, v, off, u0 + 1.5, z + 1, um, z + h - 1, s, material, out=s + 0.6)
            bar(parent, side, v, off, um, z + h - 1, u1 - 1.5, z + 1, s, material, out=s + 0.6)
            put(um, off, z, s, s + 0.6, h, material)
        elif style == 'brace':                     # post with knee braces
            um = (u0 + u1) / 2.0
            put(um, off, z, s + 0.6, s + 0.6, h, material)
            k = min(span / 2.0 - 2.0, h * 0.55)
            if k > 3:
                bar(parent, side, v, off, um - k, z + h - 1, um - 0.5, z + h - k - 1, s, material, out=s + 0.6)
                bar(parent, side, v, off, um + 0.5, z + h - k - 1, um + k, z + h - 1, s, material, out=s + 0.6)


def door_hood(parent, side, v, u, z, w=17.0, out=8.0, cover='timber'):
    """A hood on brackets over a doorway: it keeps the rain off the threshold,
    and it stops the door disappearing into the shadow under deep eaves."""
    put = face(parent, side, v)
    for sgn in (-1, 1):
        put(u + sgn * (w / 2.0 - 1.6), out / 2.0, z - 5.0, 2.4, out, 5.0, 'timber')
        put(u + sgn * (w / 2.0 - 1.6), out - 1.4, z - 9.0, 2.2, 2.6, 4.0, 'timber')
    put(u, out / 2.0 + 0.5, z, w + 3.0, out + 2.0, 2.6, 'timber')
    put(u, out / 2.0 + 0.5, z + 2.6, w + 1.0, out, 1.8, cover)


def door(parent, side, v, u, z, w=11.0, h=18.0, thick=3.6, step=True,
         leaf='timber_light', ground=0.0):
    """A recessed plank door: dark reveal, boarded leaf, iron straps, timber
    jambs and lintel standing proud, stone threshold."""
    put = face(parent, side, v)
    inner = -thick / 2.0
    put(u, inner + 0.4, z, w, 1.0, h, 'soot')                       # the dark inside
    put(u, thick / 2.0 - 2.6, z + 0.4, w - 1.8, 2.0, h - 1.4, leaf)  # leaf, set back
    for zz in (z + 2.6, z + h - 4.4):                                # ledges
        put(u, thick / 2.0 - 1.7, zz, w - 1.8, 0.9, 1.7, 'timber')
    for zz in (z + 2.6, z + h - 4.4):                                # iron straps
        put(u - w / 2.0 + 2.2, thick / 2.0 - 1.4, zz + 0.2, 3.4, 0.6, 1.3, 'iron_dark')
    put(u + w / 2.0 - 3.0, thick / 2.0 - 1.4, z + h * 0.5, 1.4, 0.9, 1.4, 'iron')  # ring handle
    for sgn in (-1, 1):                                              # jambs
        put(u + sgn * (w / 2.0 + 1.3), 0.9, z, 2.6, thick + 1.8, h + 2.6, 'timber')
    put(u, 0.9, z + h, w + 5.2, thick + 1.8, 2.6, 'timber')          # lintel
    if step and z - ground > 0.5:
        put(u, thick / 2.0 + 1.6, ground, w + 3.0, 5.5, z - ground, 'stone_light')
    elif step:
        put(u, thick / 2.0 + 1.6, ground, w + 3.0, 5.5, 1.6, 'stone_light')


def window(parent, side, v, u, z, w=8.0, h=8.0, thick=3.6, shutters=False,
           mullions=1, sill='stone_light'):
    """Recessed light with a timber frame, mullion bars and a jutting sill."""
    put = face(parent, side, v)
    put(u, -thick / 2.0 + 0.6, z, w, 1.2, h, 'soot')                 # dark interior
    if mullions > 1:                                     # leaded lights, big window
        put(u, thick / 2.0 - 1.2, z, w - 1.2, 0.8, h - 0.6, 'iron_dark')
    for sgn in (-1, 1):
        put(u + sgn * (w / 2.0 + 0.8), 0.7, z - 0.6, 1.8, thick + 1.4, h + 1.8, 'timber')
    put(u, 0.7, z + h, w + 3.6, thick + 1.4, 1.8, 'timber')
    for i in range(mullions):
        um = u - w / 2.0 + w * (i + 1) / (mullions + 1.0)
        put(um, thick / 2.0 - 0.6, z, 1.5, 1.2, h, 'timber')
    put(u, thick / 2.0 + 1.0, z - 1.8, w + 4.4, 4.2, 1.8, sill)
    if shutters:
        for sgn in (-1, 1):
            put(u + sgn * (w / 2.0 + 3.4), 1.6, z + 0.4, 4.4, 1.6, h - 0.8, 'timber_light')


def plane_roof(parent, cx, cy, base_z, w, d, h, material, overhang=4.0,
               thick=3.2, ridge='y', cap='timber'):
    """Two tilted slabs meeting at a ridge. Leaves the gable ends open so a
    gable wall can show, and reads with real roof thickness at the eaves."""
    if ridge == 'x':
        run, length = d / 2.0 + overhang, w + 2 * overhang
    else:
        run, length = w / 2.0 + overhang, d + 2 * overhang
    L = math.hypot(run, h)
    th = math.atan2(h, run)
    nz, ns = run / L, h / L
    for s in (+1, -1):
        c_off = s * (run / 2.0 + thick * ns / 2.0)
        cz = base_z + h / 2.0 + thick * nz / 2.0
        if ridge == 'x':
            box(cx, cy + c_off, cz - thick / 2.0, length, L, thick, material,
                parent, rot=(-s * th, 0, 0))
        else:
            box(cx + c_off, cy, cz - thick / 2.0, L, length, thick, material,
                parent, rot=(0, s * th, 0))
    if cap:
        if ridge == 'x':
            box(cx, cy, base_z + h - 1.0, length, 5.0, 3.0, cap, parent)
        else:
            box(cx, cy, base_z + h - 1.0, 5.0, length, 3.0, cap, parent)


def gable(parent, cx, cy, base_z, span, h, thick, material, ridge='y'):
    """The triangular wall closing a plane_roof end."""
    rot = None if ridge == 'x' else (0, 0, R(90))
    return wedge(cx, cy, base_z, thick, span, h, material, parent, rot=rot)


def gable_frame(parent, side, v, uc, base_z, span, h, off=2.4,
                material='timber', s=2.4):
    """King post plus two braces in a gable triangle. `side` is the face the
    timber sits on, so the two ends of a range can be framed differently."""
    u0, u1 = uc - span / 2.0, uc + span / 2.0
    put = face(parent, side, v)
    put(uc, off, base_z + 1, s, s + 1.0, h - 3.5, material)
    bar(parent, side, v, off, u0 + span * 0.20, base_z + 1.0, uc - 1.0,
        base_z + h * 0.60, s, material, out=s + 1.0)
    bar(parent, side, v, off, uc + 1.0, base_z + h * 0.60, u1 - span * 0.20,
        base_z + 1.0, s, material, out=s + 1.0)


def barge_boards(parent, side, v, uc, base_z, span, h, overhang,
                 out=3.4, material='timber', s=3.0):
    """Boards following the roof edge on a gable — the strongest single line
    on a timber-framed house. Matches plane_roof: eaves land at base_z."""
    half = span / 2.0 + overhang
    bar(parent, side, v, out, uc - half, base_z, uc, base_z + h, s, material, out=s)
    bar(parent, side, v, out, uc, base_z + h, uc + half, base_z, s, material, out=s)


def rafter_tails(parent, cx, cy, z, length, span, n, ridge='y', s=2.2,
                 material='timber', depth=5.0):
    """Beam ends poking out under the eaves — cheap shadow, big readability."""
    for i in range(n):
        u = -length / 2.0 + length * (i + 0.5) / n
        for sgn in (-1, 1):
            if ridge == 'y':
                box(cx + sgn * (span / 2.0 + depth / 2.0 - 0.5), cy + u, z,
                    depth, s, s, material, parent)
            else:
                box(cx + u, cy + sgn * (span / 2.0 + depth / 2.0 - 0.5), z,
                    s, depth, s, material, parent)


def chimney(parent, x, y, base_z, top_z, w=11.0, d=13.0, breast=0.0,
            material='stone', cap='stone'):
    """A stone stack. `breast` gives it the fireplace mass it needs at the
    bottom when it climbs the outside of a gable wall."""
    if breast > 0:
        # the fireplace mass, weathered back in stages as it climbs the gable
        box(x, y, base_z, w + 6.0, d + 5.0, breast * 0.62, material, parent)
        box(x, y, base_z + breast * 0.62, w + 3.6, d + 3.0, breast * 0.38,
            material, parent)
        box(x, y, base_z + breast, w + 1.8, d + 1.6, 4.5, material, parent)
        base_z += breast + 4.5
    mid = base_z + (top_z - base_z) * 0.55
    box(x, y, base_z, w + 1.8, d + 1.4, mid - base_z, material, parent)
    box(x, y, mid, w, d - 1.0, top_z - mid, material, parent)
    box(x, y, top_z - 4.0, w + 2.0, d + 1.6, 1.8, cap, parent)       # corbel course
    box(x, y, top_z - 2.2, w + 3.8, d + 3.2, 2.6, cap, parent)       # cap
    box(x, y, top_z + 0.4, w - 4.5, d - 5.5, 1.2, 'soot', parent)    # flue mouth


def barrel(parent, x, y, z, r=4.0, h=8.5, verts=8):
    cyl(x, y, z, r * 0.93, h, 'timber_light', parent, verts=verts)
    for zz in (z + h * 0.18, z + h * 0.72):
        cyl(x, y, zz, r, h * 0.12, 'iron_dark', parent, verts=verts)


def crate(parent, x, y, z, w=9.0, d=9.0, h=8.0, rz=0.0):
    box(x, y, z, w, d, h, 'timber_light', parent, rot=(0, 0, rz))
    box(x, y, z + h * 0.42, w + 0.5, d + 0.5, 1.4, 'timber', parent, rot=(0, 0, rz))


def sack(parent, x, y, z, s=6.0, rz=0.0, material='thatch'):
    box(x, y, z, s, s * 0.85, s * 0.75, material, parent, rot=(0, 0, rz))
    box(x, y, z + s * 0.75, s * 0.72, s * 0.6, s * 0.3, material, parent,
        rot=(0, 0, rz + 0.25))
    box(x, y, z + s * 1.05, s * 0.3, s * 0.26, s * 0.22, material, parent,
        rot=(0, 0, rz - 0.2))


def ladder(parent, x, y, z, height, lean=R(12), rungs=5, axis='x', sgn=-1,
           w=8.0, s=1.9):
    """A leaning ladder: its top is at (x, y, z+height), its foot kicked out
    by `sgn` along `axis`."""
    run = height * math.tan(lean)
    L = math.hypot(run, height)
    for side in (-1, 1):
        off = side * (w / 2.0 - s / 2.0)
        if axis == 'x':
            box(x + sgn * run / 2.0, y + off, z + height / 2.0 - L / 2.0,
                s, s, L, 'timber_light', parent, rot=(0, sgn * lean, 0))
        else:
            box(x + off, y + sgn * run / 2.0, z + height / 2.0 - L / 2.0,
                s, s, L, 'timber_light', parent, rot=(-sgn * lean, 0, 0))
    for i in range(rungs):
        f = (i + 0.6) / (rungs + 0.4)
        if axis == 'x':
            box(x + sgn * run * (1.0 - f), y, z + height * f - s * 0.4,
                s * 0.9, w, s * 0.8, 'timber_light', parent)
        else:
            box(x, y + sgn * run * (1.0 - f), z + height * f - s * 0.4,
                w, s * 0.9, s * 0.8, 'timber_light', parent)


# ------------------------------------------------------------------ cottages

def cottage_a():
    """Thatched cot: one low range, gable-entry under a deep thatch overhang,
    an external stone stack at the far end. The humblest house in the kit."""
    g = empty('cottage_a')
    W, D, T = 58.0, 42.0, 3.6
    z = footing(g, 0, 0, W + 4, D + 4, 4.2)
    h = 25.0
    holes = {
        'e': [(-4.0, 11.0, 0.0, 17.0), (13.0, 7.0, 10.0, 16.5)],
        'n': [(-11.0, 8.0, 9.5, 16.0), (14.0, 7.0, 10.0, 16.0)],
        's': [(6.0, 7.0, 10.0, 16.0)],
    }
    shell(g, 0, 0, z, W, D, h, T, 'plaster', holes)
    door(g, 'e', W / 2.0 - T / 2.0, -4.0, z, 11.0, 17.0, T, ground=0.0)
    door_hood(g, 'e', W / 2.0 - T / 2.0, -4.0, z + 20.0, 18.0, 8.0)
    window(g, 'e', W / 2.0 - T / 2.0, 13.0, z + 10.0, 7.0, 6.5, T, shutters=True)
    window(g, 'n', D / 2.0 - T / 2.0, -11.0, z + 9.5, 8.0, 6.5, T)
    window(g, 'n', D / 2.0 - T / 2.0, 14.0, z + 10.0, 7.0, 6.0, T, shutters=True)
    window(g, 's', -D / 2.0 + T / 2.0, 6.0, z + 10.0, 7.0, 6.0, T)

    corner_posts(g, 0, 0, z, W, D, h)
    band(g, 0, 0, z, W, D, 2.4, 'timber')            # sill beam
    band(g, 0, 0, z + h - 2.8, W, D, 2.8, 'timber')  # wall plate
    framing(g, 'n', D / 2.0 - T / 2.0, [(-4.0, 9.0), (19.0, 26.0)], z + 3, h - 6, 'brace')
    framing(g, 's', -D / 2.0 + T / 2.0, [(-25.0, -3.0), (12.0, 25.0)], z + 3, h - 6, 'brace')
    framing(g, 'e', W / 2.0 - T / 2.0, [(3.0, 8.0)], z + 3, h - 6, 'studs')

    rafter_tails(g, 0, 0, z + h - 1.0, W - 6, D, 6, ridge='x')
    box(0, 0, z + h - 0.6, W + 10.0, D + 10.0, 2.4, 'thatch', g)   # drip course lip
    pitched_roof(0, 0, z + h + 1.8, W, D, 15.0, 'thatch', g, overhang=4.5,
                 eave='thatch')
    top = z + h + 1.8 + 3 + 15.0
    box(0, 0, top - 2.4, W + 10, 5.5, 2.8, 'thatch', g)          # ridge roll
    for x in (-20, -6, 8, 22):                                    # ridge liggers
        box(x, 0, top - 0.3, 2.0, 8.0, 1.4, 'timber', g)
    chimney(g, -W / 2.0 - 1.5, 0, 0, top + 5.0, 11.5, 14.0, breast=20.0)
    barrel(g, W / 2.0 + 6.0, 14.0, 0)
    return g


def cottage_b():
    """Cross-wing house: two masses at right angles under tiled roofs, stone
    ground floor, framed upper. The one with money in the hamlet."""
    g = empty('cottage_b')
    T = 3.4
    MW, MD, MX = 40.0, 56.0, -13.0     # main range
    CW, CD, CX = 26.0, 34.0, 20.0      # cross wing
    z = footing(g, MX, 0, MW + 4, MD + 4, 4.6)
    footing(g, CX, 0, CW + 4, CD + 4, 4.6)
    h = 25.0
    stone_h = 12.0

    main_holes = {
        'w': [(-8.0, 8.0, 15.0, 22.0), (14.0, 8.0, 15.0, 22.0), (2.0, 7.0, 3.0, 9.5)],
        'n': [(MX - 8.0, 8.0, 15.0, 22.0)],
    }
    wing_holes = {
        'e': [(-1.0, 11.0, 0.0, 18.0), (13.0, 7.0, 15.0, 21.0)],
        's': [(CX - 3.0, 8.0, 4.0, 10.0)],
    }
    # stone to the mid rail, plaster and timber above
    storeyed_shell(g, MX, 0, z, MW, MD, h, T, stone_h, 'stone', 'plaster', main_holes)
    storeyed_shell(g, CX, 0, z, CW, CD, h, T, stone_h, 'stone', 'plaster', wing_holes)
    box(MX, 0, z, MW + 2.0, MD + 2.0, 3.0, 'stone_light', g)      # plinth course
    box(CX, 0, z, CW + 2.0, CD + 2.0, 3.0, 'stone_light', g)
    door(g, 'e', CX + CW / 2.0 - T / 2.0, -1.0, z, 11.0, 18.0, T, ground=0.0)
    door_hood(g, 'e', CX + CW / 2.0 - T / 2.0, -1.0, z + 21.0, 18.0, 9.0, 'roof_tile')
    window(g, 'e', CX + CW / 2.0 - T / 2.0, 13.0, z + 15.0, 7.0, 6.0, T, shutters=True)
    window(g, 'w', MX - MW / 2.0 + T / 2.0, -8.0, z + 15.0, 8.0, 7.0, T, mullions=2)
    window(g, 'w', MX - MW / 2.0 + T / 2.0, 14.0, z + 15.0, 8.0, 7.0, T, mullions=2)
    window(g, 'w', MX - MW / 2.0 + T / 2.0, 2.0, z + 3.0, 7.0, 6.5, T)
    window(g, 'n', MD / 2.0 - T / 2.0, MX - 8.0, z + 15.0, 8.0, 7.0, T, mullions=2)
    window(g, 's', -CD / 2.0 + T / 2.0, CX - 3.0, z + 4.0, 8.0, 6.0, T)

    band(g, MX, 0, z + stone_h, MW, MD, 2.6, 'timber')
    band(g, CX, 0, z + stone_h, CW, CD, 2.6, 'timber')
    band(g, MX, 0, z + h - 3.0, MW, MD, 3.0, 'timber')
    band(g, CX, 0, z + h - 3.0, CW, CD, 3.0, 'timber')
    corner_posts(g, MX, 0, z + stone_h, MW, MD, h - stone_h, 4.0)
    corner_posts(g, CX, 0, z + stone_h, CW, CD, h - stone_h, 4.0)
    up_z, up_h = z + stone_h + 2.6, h - stone_h - 5.6
    framing(g, 'w', MX - MW / 2.0 + T / 2.0, [(-25.0, -13.0), (-3.0, 9.0), (19.0, 26.0)],
            up_z, up_h, 'cross')
    framing(g, 'n', MD / 2.0 - T / 2.0, [(MX - 18.0, MX - 13.0), (MX - 3.0, MX + 17.0)],
            up_z, up_h, 'cross')
    framing(g, 's', -MD / 2.0 + T / 2.0, [(MX - 18.0, MX + 17.0)], up_z, up_h, 'cross')
    framing(g, 'e', CX + CW / 2.0 - T / 2.0, [(4.0, 9.0), (-16.0, -8.0)], up_z, up_h, 'cross')
    framing(g, 'n', CD / 2.0 - T / 2.0, [(CX - 12.0, CX - 1.0)], up_z, up_h, 'cross')

    # main range roof: ridge along Y, open gables
    rz = z + h
    plane_roof(g, MX, 0, rz, MW, MD, 16.5, 'roof_tile', overhang=3.5, ridge='y')
    for sy, side in ((1, 'n'), (-1, 's')):
        gv = sy * (MD / 2.0 - T / 2.0)
        gable(g, MX, gv, rz, MW, 16.5, T, 'plaster', ridge='y')
        gable_frame(g, side, gv, MX, rz, MW, 16.5)
        barge_boards(g, side, gv, MX, rz, MW, 16.5, 3.5)

    # cross wing roof: ridge along X, lower, tucking into the main slope
    wz = z + h - 3.0
    plane_roof(g, CX, 0, wz, CW, CD, 12.5, 'roof_tile', overhang=3.5, ridge='x')
    gv = CX + CW / 2.0 - T / 2.0
    gable(g, gv, 0, wz, CD, 12.5, T, 'plaster', ridge='x')
    gable_frame(g, 'e', gv, 0, wz, CD, 12.5)
    barge_boards(g, 'e', gv, 0, wz, CD, 12.5, 3.5)

    chimney(g, MX + 12.0, 17.0, z + 6.0, rz + 21.0, 9.5, 11.0)
    return g


def cottage_c():
    """Jettied two-storey: narrow footprint, upper floor oversailing on
    joists, close studding, steep tiled roof. Tall where the others are low."""
    g = empty('cottage_c')
    T = 3.4
    GW, GD = 36.0, 46.0
    UW, UD = 44.0, 51.0
    z = footing(g, 0, 0, GW + 4, GD + 4, 4.0)
    gh, uh = 19.0, 17.0

    ground_holes = {
        'e': [(-6.0, 11.0, 0.0, 16.0), (12.0, 8.0, 6.0, 12.5)],
        'w': [(2.0, 8.0, 6.0, 12.5)],
        's': [(-4.0, 8.0, 6.0, 12.5)],
    }
    shell(g, 0, 0, z, GW, GD, gh, T, 'stone_light', ground_holes)
    door(g, 'e', GW / 2.0 - T / 2.0, -6.0, z, 11.0, 16.0, T, ground=0.0)
    window(g, 'e', GW / 2.0 - T / 2.0, 12.0, z + 6.0, 8.0, 6.5, T, shutters=True)
    window(g, 'w', -GW / 2.0 + T / 2.0, 2.0, z + 6.0, 8.0, 6.5, T)
    window(g, 's', -GD / 2.0 + T / 2.0, -4.0, z + 6.0, 8.0, 6.5, T)

    # jetty: joist ends under a bressummer beam carrying the upper floor
    jz = z + gh
    for i in range(7):
        y = -GD / 2.0 + GD * (i + 0.5) / 7.0
        box(GW / 2.0 + 2.2, y, jz - 2.4, 8.0, 2.6, 2.6, 'timber', g)
    box(0, 0, jz, UW, UD, 3.0, 'timber', g)                 # bressummer all round
    uz = jz + 3.0

    upper_holes = {
        'e': [(-3.0, 22.0, 6.0, 12.5)],
        'w': [(0.0, 9.0, 6.0, 12.0)],
        'n': [(-5.0, 9.0, 6.0, 12.0)],
    }
    shell(g, 0, 0, uz, UW, UD, uh, T, 'plaster', upper_holes)
    window(g, 'e', UW / 2.0 - T / 2.0, -3.0, uz + 6.0, 22.0, 6.5, T, mullions=4)
    window(g, 'w', -UW / 2.0 + T / 2.0, 0.0, uz + 6.0, 9.0, 6.0, T, shutters=True)
    window(g, 'n', UD / 2.0 - T / 2.0, -5.0, uz + 6.0, 9.0, 6.0, T)

    corner_posts(g, 0, 0, uz, UW, UD, uh, 4.0)
    band(g, 0, 0, uz + uh - 3.0, UW, UD, 3.0, 'timber')
    framing(g, 'e', UW / 2.0 - T / 2.0, [(-24.0, -15.0), (9.0, 24.0)], uz + 1, uh - 4, 'studs')
    framing(g, 'w', -UW / 2.0 + T / 2.0, [(-24.0, -6.0), (6.0, 24.0)], uz + 1, uh - 4, 'studs')
    framing(g, 'n', UD / 2.0 - T / 2.0, [(-20.0, -11.0), (1.0, 20.0)], uz + 1, uh - 4, 'studs')
    framing(g, 's', -UD / 2.0 + T / 2.0, [(-20.0, 20.0)], uz + 1, uh - 4, 'chevron')

    rz = uz + uh
    rafter_tails(g, 0, 0, rz - 1.0, UD - 8, UW, 6, ridge='y')
    plane_roof(g, 0, 0, rz, UW, UD, 16.5, 'roof_tile', overhang=3.5, ridge='y')
    for sy, side in ((1, 'n'), (-1, 's')):
        gv = sy * (UD / 2.0 - T / 2.0)
        gable(g, 0, gv, rz, UW, 16.5, T, 'plaster', ridge='y')
        barge_boards(g, side, gv, 0, rz, UW, 16.5, 3.5)
        gable_frame(g, side, gv, 0, rz, UW, 16.5)
    chimney(g, 0, -UD / 2.0 - 2.5, 0, rz + 20.0, 8.5, 10.0, breast=gh + 4.0)
    return g


def longhouse():
    """Market-town range: long tiled roof, two stacks, an entry porch, a
    lean-to workshop down the back and dormers in the roof."""
    g = empty('longhouse')
    T = 3.6
    W, D = 48.0, 104.0
    z = footing(g, 0, 0, W + 5, D + 5, 5.0)
    h = 27.0
    stone_h = 11.0
    holes = {
        'e': [(-42.0, 9.0, 15.0, 22.0), (-24.0, 9.0, 15.0, 22.0),
              (-6.0, 12.0, 0.0, 19.0), (12.0, 9.0, 15.0, 22.0),
              (30.0, 9.0, 15.0, 22.0), (44.0, 9.0, 4.0, 10.0)],
        'w': [(-22.0, 9.0, 15.0, 22.0), (0.0, 9.0, 15.0, 22.0), (26.0, 9.0, 15.0, 22.0)],
        'n': [(0.0, 10.0, 15.0, 22.0)],
        's': [(0.0, 10.0, 15.0, 22.0)],
    }
    storeyed_shell(g, 0, 0, z, W, D, h, T, stone_h, 'stone', 'plaster', holes)
    box(0, 0, z, W + 2.2, D + 2.2, 3.2, 'stone_light', g)         # plinth course

    ev = W / 2.0 - T / 2.0
    door(g, 'e', ev, -6.0, z, 12.0, 19.0, T, ground=0.0)
    for u in (-42.0, -24.0, 12.0, 30.0):
        window(g, 'e', ev, u, z + 15.0, 9.0, 7.0, T, mullions=2)
    window(g, 'e', ev, 44.0, z + 4.0, 9.0, 6.0, T, shutters=True)
    for u in (-22.0, 0.0, 26.0):
        window(g, 'w', -ev, u, z + 15.0, 9.0, 7.0, T, mullions=2)
    window(g, 'n', D / 2.0 - T / 2.0, 0.0, z + 15.0, 10.0, 7.0, T, mullions=2)
    window(g, 's', -D / 2.0 + T / 2.0, 0.0, z + 15.0, 10.0, 7.0, T, mullions=2)

    band(g, 0, 0, z + stone_h, W, D, 2.8, 'timber')
    band(g, 0, 0, z + h - 3.2, W, D, 3.2, 'timber')
    corner_posts(g, 0, 0, z + stone_h, W, D, h - stone_h, 4.4)
    up_z, up_h = z + stone_h + 2.8, h - stone_h - 6.0
    framing(g, 'e', ev, [(-52.0, -47.0), (-37.0, -29.0), (-19.0, -13.0), (1.0, 7.0),
                         (17.0, 25.0), (35.0, 39.0), (49.0, 52.0)], up_z, up_h, 'cross')
    framing(g, 'w', -ev, [(-52.0, -27.0), (-17.0, -5.0), (5.0, 21.0), (31.0, 52.0)],
            up_z, up_h, 'cross')
    framing(g, 'n', D / 2.0 - T / 2.0, [(-22.0, -6.0), (6.0, 22.0)], up_z, up_h, 'chevron')
    framing(g, 's', -D / 2.0 + T / 2.0, [(-22.0, -6.0), (6.0, 22.0)], up_z, up_h, 'chevron')

    rz = z + h
    rafter_tails(g, 0, 0, rz - 1.0, D - 10, W, 8, ridge='y')
    plane_roof(g, 0, 0, rz, W, D, 21.0, 'roof_tile', overhang=5.0, ridge='y')
    for sy, side in ((1, 'n'), (-1, 's')):
        gv = sy * (D / 2.0 - T / 2.0)
        gable(g, 0, gv, rz, W, 21.0, T, 'plaster', ridge='y')
        barge_boards(g, side, gv, 0, rz, W, 21.0, 5.0)
        gable_frame(g, side, gv, 0, rz, W, 21.0)

    # dormers on the east slope
    for y in (-30.0, 20.0):
        dx = W / 2.0 - 7.0
        box(dx, y, rz + 3.0, 13.0, 14.0, 10.0, 'plaster', g)
        window(g, 'e', dx + 6.5 - 0.9, y, rz + 5.0, 7.0, 6.0, 1.8, mullions=1)
        plane_roof(g, dx + 1.0, y, rz + 13.0, 9.0, 14.0, 6.0, 'roof_tile',
                   overhang=2.0, ridge='x', thick=2.4, cap='timber')
        gable(g, dx + 5.4, y, rz + 13.0, 18.0, 6.0, 2.0, 'timber', ridge='x')
        barge_boards(g, 'e', dx + 6.0, y, rz + 13.0, 14.0, 6.0, 2.0, s=2.0, out=1.4)

    # entry porch on the east front
    px = W / 2.0
    for sy in (-1, 1):
        box(px + 11.0, -6.0 + sy * 9.0, z, 4.4, 4.4, 21.0, 'timber', g)
        bar(g, 'n', -6.0 + sy * 9.0, 0.0, px + 11.0, z + 14.0, px + 2.0,
            z + 21.0, 2.4, 'timber')
    box(px + 6.5, -6.0, z + 21.0, 17.0, 24.0, 2.8, 'timber', g)
    plane_roof(g, px + 6.5, -6.0, z + 23.8, 15.0, 22.0, 8.5, 'roof_tile',
               overhang=2.5, ridge='x', thick=2.6, cap='timber')
    gable(g, px + 15.6, -6.0, z + 23.8, 27.0, 8.5, 2.6, 'plaster', ridge='x')
    gable_frame(g, 'e', px + 15.6, -6.0, z + 23.8, 24.0, 8.5, s=2.2)
    barge_boards(g, 'e', px + 17.2, -6.0, z + 23.8, 22.0, 8.5, 2.5, s=2.4, out=1.2)
    box(px + 3.0, -6.0, 0, 15.0, 24.0, z, 'stone_light', g)

    # lean-to workshop against the west wall
    lz = z + 1.0
    box(-W / 2.0 - 7.0, 12.0, lz, 14.0, 40.0, 15.0, 'timber', g)
    for i in range(6):
        box(-W / 2.0 - 14.0 + 0.6, 12.0 - 20.0 + 40.0 * (i + 0.5) / 6.0, lz,
            1.8, 3.0, 15.0, 'timber_light', g)
    ramp(-W / 2.0 - 7.5, 12.0, lz + 15.0, 42.0, 16.0, 7.0, 'roof_slate', g,
         rot=(0, 0, R(90)))
    box(-W / 2.0 - 7.5, 12.0, lz + 14.0, 17.0, 42.0, 2.0, 'timber', g)

    chimney(g, -8.0, -D / 2.0 - 2.0, 0, rz + 22.0, 10.0, 12.0, breast=h + 3.0)
    chimney(g, -W / 2.0 + 9.0, 40.0, z + 8.0, rz + 24.0, 10.0, 11.0)
    return g


def storehouse():
    """Barn: stone plinth, boarded timber walls, a midstrey porch with one
    cart door swung open, and an open bay stacked with goods."""
    g = empty('storehouse')
    T = 4.0
    W, D = 70.0, 96.0
    z = footing(g, 0, 0, W + 6, D + 6, 7.0, 'stone', 'stone_dark')
    h = 34.0
    ev = W / 2.0 - T / 2.0
    holes = {
        'e': [(18.0, 28.0, 0.0, 30.0), (-32.0, 30.0, 0.0, 26.0)],
        'w': [(0.0, 9.0, 18.0, 25.0), (-30.0, 9.0, 18.0, 25.0), (30.0, 9.0, 18.0, 25.0)],
        'n': [(0.0, 12.0, 20.0, 27.0)],
        's': [(0.0, 12.0, 20.0, 27.0)],
    }
    shell(g, 0, 0, z, W, D, h, T, 'timber_light', holes)

    # dark framing over the pale boarding — the barn's whole read is this stripe
    for i in range(9):
        y = -D / 2.0 + D * (i + 0.5) / 9.0
        if -47.0 < y < -17.0 or 4.0 < y < 32.0:
            continue
        box(ev + T / 2.0 - 0.6, y, z, 2.4, 4.0, h, 'timber', g)
        box(-ev - T / 2.0 + 0.6, y, z, 2.4, 4.0, h, 'timber', g)
    for i in range(6):
        x = -W / 2.0 + W * (i + 0.5) / 6.0
        box(x, D / 2.0 - 0.6, z, 4.0, 2.4, h, 'timber', g)
        box(x, -D / 2.0 + 0.6, z, 4.0, 2.4, h, 'timber', g)
    for zz in (z + 11.0, z + 23.0):                    # mid rails
        band(g, 0, 0, zz, W, D, 2.6, 'timber', proud=1.0)

    # dark interior behind the two openings
    box(ev - 9.0, 18.0, z, 3.0, 28.0, 30.0, 'soot', g)
    box(ev - 9.0, -32.0, z, 3.0, 30.0, 26.0, 'soot', g)

    # midstrey: the porch that lets a loaded cart in, tall enough for one
    for sy in (-1, 1):
        box(ev + 13.0, 18.0 + sy * 17.5, z, 5.6, 5.6, 33.0, 'timber', g)
        bar(g, 'n', 18.0 + sy * 17.5, 0.0, ev + 13.0, z + 25.0, ev + 3.0,
            z + 33.0, 2.8, 'timber')
    box(ev + 8.0, 18.0, z + 33.0, 18.0, 40.6, 3.6, 'timber', g)
    plane_roof(g, ev + 8.0, 18.0, z + 36.6, 22.0, 35.0, 11.0, 'thatch',
               overhang=3.5, ridge='x', thick=3.4, cap='thatch')
    gable(g, ev + 21.0, 18.0, z + 36.6, 42.0, 11.0, 3.0, 'timber_light', ridge='x')
    gable_frame(g, 'e', ev + 21.0, 18.0, z + 36.6, 40.0, 11.0, s=2.6)
    barge_boards(g, 'e', ev + 22.8, 18.0, z + 36.6, 35.0, 11.0, 3.5, s=3.0, out=1.4)
    box(ev + 7.0, 18.0, 0, 24.0, 38.0, z, 'stone_dark', g)
    # doors: one leaf shut, one swung open
    box(ev - 1.0, 25.0, z, 3.0, 14.0, 29.0, 'timber_light', g)
    for zz in (z + 4.0, z + 22.0):
        box(ev + 0.4, 25.0, zz, 1.6, 13.0, 2.2, 'iron_dark', g)
    box(ev + 5.5, 8.0, z, 14.0, 3.0, 29.0, 'timber_light', g, rot=(0, 0, R(-24)))
    for zz in (z + 4.0, z + 22.0):
        box(ev + 5.5, 8.0, zz, 13.0, 1.6, 2.2, 'iron_dark', g, rot=(0, 0, R(-24)))

    # open bay: posts, beam, and the goods it exists to hold
    for y in (-45.0, -32.0, -19.0):
        box(ev, y, z, 5.0, 5.0, 26.0, 'timber', g)
    box(ev, -32.0, z + 26.0, 5.5, 32.0, 3.2, 'timber', g)
    for y, zz in ((-44.0, 0.0), (-38.0, 0.0), (-25.0, 0.0), (-41.0, 8.4), (-27.0, 8.4)):
        crate(g, ev - 12.0, y, z + zz, 10.0, 9.0, 8.0, R(6 if zz else -4))
    barrel(g, ev - 11.0, -33.0, z)
    barrel(g, ev - 11.0, -18.0, z)
    for y in (-46.0, -40.0):
        sack(g, ev - 22.0, y, z, 7.0, R(12))

    band(g, 0, 0, z + h - 3.4, W, D, 3.4, 'timber')
    rz = z + h
    rafter_tails(g, 0, 0, rz - 1.2, D - 12, W, 8, ridge='y', s=2.6, depth=7.0)
    plane_roof(g, 0, 0, rz, W, D, 26.0, 'thatch', overhang=4.5, ridge='y',
               thick=4.2, cap='thatch')
    box(0, 0, rz + 24.0, 8.0, D + 9.0, 3.4, 'thatch', g)          # ridge roll
    for y in (-34.0, -12.0, 12.0, 34.0):
        box(0, y, rz + 26.6, 7.0, 2.2, 1.4, 'timber', g)
    for sy, side in ((1, 'n'), (-1, 's')):
        gv = sy * (D / 2.0 - T / 2.0)
        gable(g, 0, gv, rz, W, 26.0, T, 'timber_light', ridge='y')
        barge_boards(g, side, gv, 0, rz, W, 26.0, 4.5, s=3.4)
        gable_frame(g, side, gv, 0, rz, W, 26.0, s=2.8)
    return g


# ------------------------------------------------------------------ village

def well():
    """Stone ring, timber frame, windlass. The crank turns the drum, the drum
    winds the rope, the rope lifts the bucket."""
    g = empty('well')
    cyl(0, 0, 0, 11.0, 8.5, 'stone', g, verts=12)
    cyl(0, 0, 8.5, 11.8, 1.6, 'stone', g, verts=12)
    cyl(0, 0, 8.2, 8.6, 0.6, 'soot', g, verts=12)
    for a in (0.3, 1.6, 2.9, 4.3, 5.6):                 # a rough, hand-laid ring
        cyl(math.cos(a) * 10.6, math.sin(a) * 10.6, 8.4, 2.4, 1.9, 'stone_dark',
            g, verts=6)

    for sy in (-1, 1):                                   # frame
        box(0, sy * 9.5, 7.0, 4.6, 4.6, 14.0, 'timber', g)
        bar(g, 'e', 0.0, 0.0, sy * 3.5, 12.0, sy * 9.5, 19.5, 2.4, 'timber')
    box(0, 0, 21.0, 5.2, 25.0, 2.8, 'timber', g)

    wz = 17.5
    cyl_axis(g, 'y', 0, 0, wz, 2.8, 16.0, 'timber_light')       # windlass drum
    for sy in (-1, 1):
        cyl_axis(g, 'y', 0, sy * 7.2, wz, 3.4, 1.8, 'iron_dark')
    box(0, 9.6, wz - 0.9, 1.8, 3.4, 1.8, 'iron', g)      # crank: arm, throw, grip
    box(2.9, 10.4, wz - 0.9, 6.8, 1.8, 1.8, 'iron', g)
    box(5.8, 10.4, wz - 5.0, 1.7, 1.7, 4.6, 'timber_light', g)

    cyl(0, 0, 15.4, 0.5, 2.1, 'leather', g, verts=6)     # rope
    cyl(0, 0, 10.4, 3.6, 5.0, 'timber_light', g, verts=8)  # bucket
    cyl(0, 0, 14.0, 3.9, 1.0, 'iron_dark', g, verts=8)
    box(0, 0, 15.0, 8.0, 0.8, 0.8, 'iron', g)

    box(0, 0, 23.8, 15.0, 4.2, 2.0, 'timber', g)
    plane_roof(g, 0, 0, 25.8, 13.0, 18.0, 5.5, 'roof_tile', overhang=1.8,
               ridge='y', thick=2.0)
    box(-9.5, 1.0, 0, 6.5, 5.5, 2.4, 'stone_dark', g)
    return g


def market_stall():
    """Trestle counter under a striped awning. The cloth stripes take the
    faction colour, so a market reads as somebody's market."""
    g = empty('market_stall')
    OX = -2.0
    for sy in (-1, 1):                                        # back posts, tall
        box(OX - 13.0, sy * 12.5, 0, 3.8, 3.8, 29.0, 'timber', g)
        box(OX + 11.0, sy * 12.5, 0, 3.8, 3.8, 22.0, 'timber', g)
        bar(g, 'n', sy * 12.5, 0.0, OX - 13.0, 22.0, OX - 5.0, 26.5, 2.2, 'timber')
    box(OX - 13.0, 0, 26.5, 4.2, 29.0, 3.0, 'timber', g)      # back plate
    box(OX + 11.0, 0, 17.5, 4.2, 29.0, 3.0, 'timber', g)      # front plate

    # counter: trestles, boards, skirt — pushed forward of the awning's shadow
    for sy in (-1, 1):
        box(OX + 10.0, sy * 10.0, 0, 3.2, 3.2, 12.0, 'timber', g)
        box(OX - 1.0, sy * 10.0, 0, 3.2, 3.2, 12.0, 'timber', g)
    for i in range(4):
        box(OX - 2.0 + i * 4.6, 0, 12.0, 4.4, 27.0, 1.8, 'timber_light', g)
    box(OX + 12.0, 0, 3.5, 1.8, 27.0, 8.5, 'timber', g)

    # awning: alternating cloth and canvas strips, sloping to the front
    run, drop = 24.0, 6.5
    th = math.atan2(drop, run)
    L = math.hypot(run, drop)
    for i in range(6):
        y = -14.0 + 28.0 * (i + 0.5) / 6.0
        m = 'cloth' if i % 2 == 0 else 'canvas'
        box(OX - 2.0, y, 26.5 - drop / 2.0 - 0.7, L, 4.9, 1.5, m, g, rot=(0, th, 0))
    box(OX + 10.0, 0, 20.0, 2.6, 29.0, 2.2, 'timber', g)      # awning bar

    # hanging cloth at the back, and the goods laid out on the boards
    box(OX - 11.4, 0, 5.0, 1.0, 24.0, 16.0, 'cloth', g)
    crate(g, OX + 4.0, -9.0, 13.8, 9.0, 8.0, 6.5, R(8))
    crate(g, OX + 3.5, 9.0, 13.8, 8.0, 8.0, 5.5, R(-6))
    crate(g, OX - 6.0, 9.5, 13.8, 8.0, 7.5, 6.0, R(-13))
    sack(g, OX + 9.0, 1.0, 13.8, 6.0, R(14))
    sack(g, OX + 9.5, -5.5, 13.8, 5.2, R(-20))
    barrel(g, OX - 6.0, -14.0, 0, 4.6, 9.5)
    barrel(g, OX - 6.0, 14.0, 0, 4.6, 9.5)
    for i in range(3):                                        # bolts of cloth
        box(OX + 9.0, 8.5 + i * 0.5, 13.8 + i * 1.9, 9.5, 4.4, 1.9, 'cloth', g,
            rot=(0, 0, R(5 * i - 4)))
    return g


def fence_segment():
    """Post and rail, exactly 60 long, posts every 20 so runs butt cleanly."""
    g = empty('fence_segment')
    rng = random.Random(11)
    for x in (-30.0, -10.0, 10.0):
        h = 19.0 + rng.uniform(-1.6, 1.6)
        tilt = rng.uniform(-0.05, 0.05)
        box(x, 0, 0, 3.8, 3.8, h, 'timber', g, rot=(tilt, 0, 0))
        box(x, 0, h - 1.0, 4.6, 4.6, 1.6, 'timber', g)
    for z, dy in ((7.0, 0.9), (13.5, -0.9)):
        box(0, dy, z, 60.0, 1.8, 2.6, 'timber_light', g)
    bar(g, 'n', 0.0, 1.8, -22.0, 1.0, -30.0, 15.0, 2.2, 'timber')   # post brace
    return g


def fence_corner():
    """A right angle: the run arrives from -X and leaves toward +Y."""
    g = empty('fence_corner')
    box(0, 0, 0, 5.6, 5.6, 25.0, 'timber', g)               # the corner post
    box(0, 0, 24.0, 6.8, 6.8, 2.2, 'timber', g)
    for (x, y) in ((-20.0, 0.0), (0.0, 20.0)):
        box(x, y, 0, 3.8, 3.8, 19.0, 'timber', g)
        box(x, y, 18.0, 4.6, 4.6, 1.6, 'timber', g)
    for z, off in ((7.0, 0.9), (13.5, -0.9)):
        box(-15.0, off, z, 30.0, 1.8, 2.6, 'timber_light', g)
        box(off, 15.0, z, 1.8, 30.0, 2.6, 'timber_light', g)
    # struts holding the corner post against the pull of both runs
    bar(g, 'n', 0.9, 0.0, -11.0, 0.5, -1.5, 18.0, 2.2, 'timber')
    bar(g, 'e', 0.9, 0.0, 11.0, 0.5, 1.5, 18.0, 2.2, 'timber')
    return g


def cart():
    """Two-wheeled farm cart: iron-tyred wheels, plank bed, shafts down to the
    ground where the ox stands."""
    g = empty('cart')
    OX = -8.0
    wz, wr = 9.8, 9.6                               # wheel centre and radius
    bed_z = 13.5
    for sy in (-1, 1):
        y = sy * 11.0
        cyl_axis(g, 'y', OX, y, wz, wr, 2.2, 'iron_dark', verts=10)     # iron tyre
        cyl_axis(g, 'y', OX, y, wz, wr - 1.1, 2.8, 'timber_light', verts=10)
        cyl_axis(g, 'y', OX, y, wz, 2.8, 4.4, 'timber', verts=8)        # nave
        for a in (0.0, 1.05, 2.09):                 # six spokes from three bars
            box(OX, y + sy * 1.7, wz - 0.7, wr * 1.7, 1.6, 1.5,
                'timber_light', g, rot=(0, a, 0))
    cyl_axis(g, 'y', OX, 0, wz, 1.5, 24.0, 'iron_dark', verts=6)
    for sy in (-1, 1):
        box(OX, sy * 8.0, bed_z - 3.0, 34.0, 3.0, 3.0, 'timber', g)
    for i in range(5):
        box(OX - 16.0 + i * 8.0, 0, bed_z, 7.2, 20.0, 1.8, 'timber_light', g)
    for sy in (-1, 1):
        box(OX, sy * 10.4, bed_z + 1.8, 34.0, 1.8, 5.0, 'timber', g)
        for i in range(3):
            box(OX - 12.0 + i * 12.0, sy * 10.4, bed_z + 1.8, 2.4, 2.6, 7.0, 'timber', g)
    box(OX - 17.6, 0, bed_z + 1.8, 1.8, 21.0, 9.0, 'timber', g)
    box(OX + 17.6, 0, bed_z + 1.8, 1.8, 21.0, 4.0, 'timber', g)
    # shafts running forward and down to where the ox stands
    for sy in (-1, 1):
        bar(g, 'n', sy * 7.6, 0.0, OX + 14.0, bed_z - 1.0, OX + 38.0, 3.6, 2.4, 'timber')
    box(OX + 37.0, 0, 2.6, 2.4, 16.0, 2.2, 'timber', g)
    barrel(g, OX - 10.0, -4.5, bed_z + 1.8, 4.6, 9.0)
    sack(g, OX - 1.0, 4.0, bed_z + 1.8, 7.0, R(-14))
    sack(g, OX + 6.0, -3.0, bed_z + 1.8, 6.0, R(20))
    return g


def haystack():
    """A round rick built up in courses and topped off into a cone, on staddle
    stones to keep the rats out. The ladder and fork are how it got there."""
    g = empty('haystack')
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(sx * 8.0, sy * 8.0, 0, 5.5, 5.5, 3.2, 'stone', g)
    cyl(0, 0, 3.2, 14.4, 1.6, 'timber', g, verts=10)         # staddle frame
    # courses: the rick bulges as it is built up, then is drawn into a cone
    cyl(0, 0, 4.6, 14.6, 7.0, 'thatch', g, verts=10)
    cyl(0, 0, 11.2, 16.2, 6.5, 'thatch', g, verts=10, rot=(0, 0, R(18)))
    cyl(0, 0, 17.4, 15.4, 5.0, 'thatch', g, verts=10)
    cyl(0, 0, 22.2, 12.4, 4.6, 'thatch', g, verts=10, rot=(0, 0, R(18)))
    cyl(0, 0, 26.6, 8.4, 4.4, 'thatch', g, verts=10)
    cyl(0, 0, 30.8, 4.0, 4.0, 'thatch', g, verts=8, rot=(0, 0, R(18)))
    # loose hay pulled out at the eaves and scattered at the foot
    rng = random.Random(19)
    for i in range(9):                                       # hay pulled loose
        a = i * 2 * math.pi / 9.0 + 0.3
        box(math.cos(a) * 15.2, math.sin(a) * 15.2, 6.0 + rng.uniform(-1.5, 8.0),
            4.5, 2.4, 1.8, 'thatch', g,
            rot=(0, rng.uniform(-0.45, -0.1), a + rng.uniform(-0.2, 0.2)))
    ladder(g, 15.0, 2.0, 0, 20.0, R(24), 6, axis='x', sgn=1, w=7.0)
    # pitchfork leaning against the rick, tines up in the hay
    bar(g, 'n', -8.0, 0.0, -20.5, 0.0, -13.0, 18.5, 1.8, 'timber_light')
    for dy in (-2.2, 0.0, 2.2):
        box(-12.4, -8.0 + dy, 18.0, 1.0, 1.0, 4.6, 'iron', g, rot=(0, R(-14), 0))
    box(-12.6, -8.0, 17.6, 1.5, 6.4, 1.3, 'iron', g)
    return g


def log_pile():
    """Cordwood between two pairs of stakes, with the block and axe that cut
    it standing alongside."""
    g = empty('log_pile')
    rng = random.Random(5)
    mats = ['trunk', 'timber', 'timber_light']
    rows = [(-9.0, -3.0, 3.0, 9.0), (-6.0, 0.0, 6.0), (-3.0, 3.0)]
    for ri, ys in enumerate(rows):
        z = 3.4 + ri * 5.6
        for y in ys:
            L = 34.0 + rng.uniform(-3.0, 3.0)
            cyl_axis(g, 'x', rng.uniform(-1.5, 1.5), y, z, 3.0, L,
                     mats[rng.randrange(3)], verts=6,
                     yaw=rng.uniform(-0.035, 0.035))
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(sx * 18.5, sy * 12.5, 0, 2.6, 2.6, 19.0, 'timber', g,
                rot=(sy * -0.06, 0, 0))
    cyl(24.0, 12.0, 0, 6.0, 9.0, 'trunk', g, verts=8)          # chopping block
    box(24.0, 12.0, 9.0, 1.6, 1.6, 8.0, 'timber_light', g, rot=(0, R(16), 0))
    box(22.9, 12.0, 15.6, 3.4, 1.5, 2.8, 'iron', g, rot=(0, R(16), 0))
    return g


def crop_row():
    """One tileable 60-unit furrow of standing wheat: a continuous body of
    crop so runs join seamlessly, with stalks breaking the top line."""
    g = empty('crop_row')
    rng = random.Random(3)
    box(0, 0, 0, 60.0, 16.0, 2.0, 'dirt', g)
    box(0, 9.4, 0, 60.0, 3.2, 1.0, 'dirt', g)
    box(0, -9.4, 0, 60.0, 3.2, 1.0, 'dirt', g)
    # the body of the crop in four uneven lengths, so the row is not a slab
    for i, (w, h) in enumerate(((9.5, 3.0), (10.6, 4.0), (9.0, 3.2), (10.2, 4.3))):
        box(-22.5 + i * 15.0, rng.uniform(-0.7, 0.7), 1.2, 15.0, w, h, 'crop', g)
    for i in range(18):                                  # stalks breaking the top
        x = -28.0 + i * 3.3
        h = 5.0 + rng.uniform(0.0, 6.5)
        box(x + rng.uniform(-1.2, 1.2), rng.uniform(-4.4, 4.4),
            3.4 + rng.uniform(0.0, 1.4), 1.7, 1.7, h, 'crop', g,
            rot=(rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3),
                 rng.uniform(-0.8, 0.8)))
    return g


def watchtower_small():
    """Timber lookout on a stone base: braced legs, boarded parapet, a shingle
    roof and the bell that is the whole point of standing up there."""
    g = empty('watchtower_small')
    T = 3.2
    rng = random.Random(23)
    box(0, 0, 0, 34.0, 34.0, 2.6, 'stone_dark', g)          # base course
    shell(g, 0, 0, 2.6, 31.0, 31.0, 13.0, 3.4, 'stone',     # hollow, with a way in
          {'e': [(0.0, 10.0, 0.0, 12.0)]})
    box(13.2, 0, 2.6, 2.4, 10.0, 12.0, 'soot', g)           # the dark of the doorway
    box(15.6, 0, 14.6, 5.5, 14.0, 2.6, 'timber', g)         # door lintel
    for sy in (-1, 1):
        box(15.4, sy * 6.6, 2.6, 3.4, 2.8, 12.0, 'stone_light', g)
    for i in range(7):                                       # rough coursing
        a = i * 2 * math.pi / 7.0 + 0.4
        box(math.cos(a) * 15.0, math.sin(a) * 15.0, rng.uniform(3.0, 11.0),
            6.5, 4.0, 3.2, 'stone_light', g, rot=(0, 0, a))
    bz = 15.6
    box(0, 0, bz, 29.0, 29.0, 3.4, 'stone_dark', g)

    pz = bz + 3.4
    top = pz + 32.0
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(sx * 10.0, sy * 10.0, pz - 2.0, 4.6, 4.6, 34.0, 'timber', g)
    for side, v in (('e', 10.0), ('w', -10.0), ('n', 10.0), ('s', -10.0)):
        bar(g, side, v, 2.6, -10.0, pz + 1.0, 10.0, top - 3.0, 2.6, 'timber')
        bar(g, side, v, 2.6, -10.0, top - 3.0, 10.0, pz + 1.0, 2.6, 'timber')
        bar(g, side, v, 2.0, -10.0, pz + 16.0, 10.0, pz + 16.0, 2.4, 'timber')

    box(0, 0, top, 34.0, 34.0, 3.2, 'timber', g)
    for i in range(5):
        u = -13.0 + i * 6.5
        box(u, 0, top - 2.0, 2.4, 36.0, 2.4, 'timber', g)
    pw = 34.0
    for side, axis, v in (('e', 'y', 16.4), ('w', 'y', -16.4)):
        wall_run(g, axis, -17.0, 17.0, v, top + 3.2, 9.0, 2.6, 'timber',
                 [(-8.0, 5.0, 4.0, 9.0), (2.0, 5.0, 4.0, 9.0)])
    for v in (16.4, -16.4):
        wall_run(g, 'x', -14.0, 14.0, v, top + 3.2, 9.0, 2.6, 'timber',
                 [(-5.0, 5.0, 4.0, 9.0), (5.0, 5.0, 4.0, 9.0)])
    box(0, 0, top + 12.2, 36.0, 36.0, 1.6, 'timber_light', g)

    for sx in (-1, 1):
        for sy in (-1, 1):
            box(sx * 12.0, sy * 12.0, top + 3.2, 3.2, 3.2, 14.5, 'timber', g)
    rz = top + 17.7
    pitched_roof(0, 0, rz, 28.0, 28.0, 10.0, 'roof_slate', g, overhang=3.0,
                 eave='timber')

    # the alarm bell, slung outside the parapet where it can be heard, with
    # its rope dropping to the platform
    bx = 22.5
    box(bx / 2.0, 0, rz + 1.0, 24.0, 4.2, 3.0, 'timber', g)      # projecting beam
    bar(g, 'n', 0.0, 0.0, bx - 8.0, rz + 1.0, bx - 1.0, rz - 2.5, 2.4, 'timber')
    box(bx, 0, rz - 1.8, 2.4, 2.4, 2.8, 'iron_dark', g)
    cyl(bx, 0, rz - 8.2, 4.2, 6.4, 'brass', g, verts=8)
    cyl(bx, 0, rz - 9.0, 5.1, 1.0, 'brass', g, verts=8)
    cyl(bx, 0, rz - 17.0, 0.5, 8.0, 'leather', g, verts=6)       # the bell rope

    ladder(g, 0, -13.0, 0, top - 1.0, R(11), 9, axis='y', sgn=-1, w=8.0)
    return g


ASSETS = {
    'cottage_a': cottage_a,
    'cottage_b': cottage_b,
    'cottage_c': cottage_c,
    'longhouse': longhouse,
    'storehouse': storehouse,
    'well': well,
    'market_stall': market_stall,
    'fence_segment': fence_segment,
    'fence_corner': fence_corner,
    'cart': cart,
    'haystack': haystack,
    'log_pile': log_pile,
    'crop_row': crop_row,
    'watchtower_small': watchtower_small,
}


def merge_by_material(root):
    """Join an asset's boxes into one mesh per material. Geometry and colour
    are identical; what changes is that a cottage ships as ~6 nodes instead of
    ~200, which is the difference between 6 draw calls and 200 in a browser."""
    groups = {}
    stack = [root]
    while stack:
        ob = stack.pop()
        stack.extend(ob.children)
        if ob.type == 'MESH' and ob.data.materials:
            groups.setdefault(ob.data.materials[0].name, []).append(ob)
    for name, obs in groups.items():
        # join into a fresh host with an identity transform: joining into one
        # of the boxes would leave the merged mesh carrying that box's
        # rotation and non-uniform scale, which throws bounds() right off
        host = bpy.data.objects.new(name, bpy.data.meshes.new(name))
        bpy.context.collection.objects.link(host)
        host.parent = root
        host.data.materials.append(obs[0].data.materials[0])
        bpy.ops.object.select_all(action='DESELECT')
        for o in obs:
            o.select_set(True)
        host.select_set(True)
        bpy.context.view_layer.objects.active = host
        bpy.ops.object.join()
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
            # +35 looks at the +X front (where the doors are), -145 at the back
            preview_render(root, os.path.join(preview_dir, name + '.png'),
                           azimuth=35.0)
            preview_render(root, os.path.join(preview_dir, name + '_back.png'),
                           azimuth=-145.0)
        line = f'{name:18s} {tris:6d} tris   {w:6.1f} x {d:6.1f} x {h:6.1f}'
        report.append(line)
        print(line, flush=True)
    return report
