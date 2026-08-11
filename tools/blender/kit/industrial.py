"""STEAMWARD — industrial infrastructure kit.

Feudal world part-way through an industrial revolution: masonry and timber
carrying riveted iron. Every mechanical part here does a job — a pipe runs from
a thing to a thing, a winch lifts, a wheel winds, a beam pumps. Nothing is
bolted on for flavour.

Scale reminder (see common.py): 1 unit = 10 cm, soldier ~18-20 units.

    foundry_hall        landmark, ~122 tall incl. chimney
    boiler_large        horizontal riveted drum on stone saddles
    boiler_small        vertical boiler
    chimney_stack       standalone tapered brick stack
    pipe_run_straight   60-unit tile, ends flush at x = +/-30
    pipe_run_corner     60x60 tile, ends at (-30, 0) and (0, +30)
    steam_crane         mast + jib + winch + hook + counterweight
    mine_headframe      A-frame, winding wheel, rope down the shaft
    coal_pile, coal_hopper, ore_cart
    water_pump          beam pump lifting water into a trough
    workshop_small      shed, stovepipe, open work bay


A note on the primitive shim
----------------------------
common.box()/wedge() currently emit half the requested w/d/h and seat the base
at z + h/4 rather than z; ramp() is half in XY. Rather than edit a file other
kits are authoring against right now (their numbers are presumably already
compensated by eye), this module measures the primitives once per build and
inverts whatever it finds. bx()/cy()/wg()/rp() therefore take *true* game
units, and keep doing so if common.py is later corrected.
"""

import math
import os
import random

import bpy
from mathutils import Vector, Quaternion

import common as C

TAU = math.pi * 2.0


def rad(d):
    return math.radians(d)


# ----------------------------------------------------------------- calibration

_CAL = {}


def _calibrate():
    """Measure common.py's primitives so this kit can work in true units."""
    if _CAL:
        return
    C.clear_scene()

    def probe(ob, ref_xy, ref_z):
        bpy.context.view_layer.update()
        dx, dy, dz = ob.dimensions
        rec = {'sx': dx / ref_xy, 'sy': dy / ref_xy, 'sz': dz / ref_z,
               'bz': (ob.location.z - dz / 2.0) / ref_z}
        bpy.data.objects.remove(ob, do_unlink=True)
        return rec

    _CAL['box'] = probe(C.box(0, 0, 0, 10, 10, 10, 'stone'), 10.0, 10.0)
    _CAL['wedge'] = probe(C.wedge(0, 0, 0, 10, 10, 10, 'stone'), 10.0, 10.0)
    _CAL['ramp'] = probe(C.ramp(0, 0, 0, 10, 10, 10, 'stone'), 10.0, 10.0)
    _CAL['cyl'] = probe(C.cyl(0, 0, 0, 5, 10, 'stone'), 10.0, 10.0)
    C.clear_scene()


def _args(kind, w, d, h, z0):
    c = _CAL[kind]
    aw, ad, ah = w / c['sx'], d / c['sy'], h / c['sz']
    return aw, ad, ah, z0 - c['bz'] * ah


# ------------------------------------------------------------------ primitives

def bx(x, y, z, w, d, h, m, parent=None, rot=None, name=None):
    """Rectangular mass: (x, y) footprint centre, z the base, true units."""
    aw, ad, ah, az = _args('box', w, d, h, z)
    return C.box(x, y, az, aw, ad, ah, m, parent, rot=rot, name=name)


def wg(x, y, z, w, d, h, m, parent=None, rot=None, name=None):
    """Ridged mass; ridge runs along +X."""
    aw, ad, ah, az = _args('wedge', w, d, h, z)
    return C.wedge(x, y, az, aw, ad, ah, m, parent, rot=rot, name=name)


def rp(x, y, z, w, d, h, m, parent=None, rot=None, name=None):
    """Single-slope mass; high edge at -Y."""
    aw, ad, ah, az = _args('ramp', w, d, h, z)
    return C.ramp(x, y, az, aw, ad, ah, m, parent, rot=rot, name=name)


def cy(x, y, z, r, h, m, parent=None, verts=8, rot=None, name=None):
    c = _CAL['cyl']
    ar, ah = r / c['sx'], h / c['sz']
    return C.cyl(x, y, z - c['bz'] * ah, ar, ah, m, parent, verts=verts,
                 rot=rot, name=name)


def _box_c(w, d, h, m, parent, name=None):
    """A box whose mesh is centred on its own origin, ready to be posed."""
    aw, ad, ah, az = _args('box', w, d, h, -h / 2.0)
    return C.box(0, 0, az, aw, ad, ah, m, parent, name=name)


def _cyl_c(r, h, m, parent, verts, name=None):
    c = _CAL['cyl']
    ar, ah = r / c['sx'], h / c['sz']
    return C.cyl(0, 0, -h / 2.0 - c['bz'] * ah, ar, ah, m, parent, verts=verts,
                 name=name)


def _pose(ob, p0, p1, roll=0.0):
    d = Vector(p1) - Vector(p0)
    q = d.to_track_quat('Z', 'Y')
    if roll:
        q = q @ Quaternion(Vector((0, 0, 1)), roll)
    ob.rotation_euler = q.to_euler()
    ob.location = (Vector(p0) + Vector(p1)) * 0.5
    return ob


def tube(p0, p1, r, m, parent=None, verts=8, name=None):
    """A round member spanning p0 -> p1: pipes, rods, ropes, axles."""
    L = (Vector(p1) - Vector(p0)).length
    if L < 1e-5:
        return None
    return _pose(_cyl_c(r, L, m, parent, verts, name), p0, p1)


def beam(p0, p1, a, b, m, parent=None, roll=0.0, name=None):
    """A rectangular member spanning p0 -> p1, cross-section a x b."""
    L = (Vector(p1) - Vector(p0)).length
    if L < 1e-5:
        return None
    return _pose(_box_c(a, b, L, m, parent, name), p0, p1, roll)


def ring(p, axis, r, t, m, parent=None, verts=8):
    """A short disc centred at p, its axis along `axis`: flanges, rivet bands."""
    a = Vector(axis).normalized()
    ob = _cyl_c(r, t, m, parent, verts)
    ob.rotation_euler = a.to_track_quat('Z', 'Y').to_euler()
    ob.location = Vector(p)
    return ob


def roof(cx, cyy, z, w, d, h, m, parent, overhang=4.0, eave='timber'):
    """Pitched roof with eaves; mirrors common.pitched_roof so rooflines match."""
    if eave:
        bx(cx, cyy, z, w + overhang * 2, d + overhang * 2, 3, eave, parent)
        z += 3
    return wg(cx, cyy, z, w + overhang * 2, d + overhang * 2, h, m, parent)


def _recentre(R, xy=True):
    """Contract: origin on the ground at the footprint centre."""
    bpy.context.view_layer.update()
    lo = [1e9] * 3
    hi = [-1e9] * 3
    for ob in R.children:
        if ob.type != 'MESH':
            continue
        for c in ob.bound_box:
            v = ob.matrix_world @ Vector(c)
            for i in range(3):
                lo[i] = min(lo[i], v[i])
                hi[i] = max(hi[i], v[i])
    if lo[0] > hi[0]:
        return
    dx = -(lo[0] + hi[0]) / 2.0 if xy else 0.0
    dy = -(lo[1] + hi[1]) / 2.0 if xy else 0.0
    dz = -lo[2]
    for ob in R.children:
        ob.location.x += dx
        ob.location.y += dy
        ob.location.z += dz
    bpy.context.view_layer.update()


# ------------------------------------------------------------- sub-assemblies

def rivet_bands(p0, p1, r, n, parent, m='iron_dark', t=2.4, verts=10):
    """Raised riveted seams around a drum, evenly spaced along its axis."""
    v0, v1 = Vector(p0), Vector(p1)
    axis = v1 - v0
    for i in range(n):
        f = (i + 1.0) / (n + 1.0)
        ring(v0 + axis * f, axis, r * 1.05, t, m, parent, verts=verts)


def handwheel(p, axis, r, parent, m='iron_dark', hub='brass'):
    """A wheel a hand turns — only ever put on a valve that shuts something."""
    a = Vector(axis).normalized()
    ring(p, a, r * 0.28, r * 0.5, hub, parent, verts=6)
    u = Vector((0, 0, 1)).cross(a)
    if u.length < 0.2:
        u = Vector((0, 1, 0)).cross(a)
    u.normalize()
    v = a.cross(u).normalized()
    for k in range(2):
        d = u if k == 0 else v
        beam(Vector(p) - d * r, Vector(p) + d * r, r * 0.18, r * 0.18, m, parent)
    ring(p, a, r, r * 0.16, m, parent, verts=8)


def relief_valve(x, y, z, parent, s=1.0, arm=+1.0):
    """Salter safety valve: seat, stem, weighted lever. Lifts at pressure."""
    cy(x, y, z, 2.2 * s, 3.4 * s, 'brass', parent, verts=6)
    cy(x, y, z + 3.4 * s, 1.0 * s, 6.0 * s, 'steel', parent, verts=6)
    bx(x + 5.0 * s * arm, y, z + 8.4 * s, 13 * s, 1.6 * s, 1.6 * s, 'iron_dark',
       parent)
    bx(x + 10.5 * s * arm, y, z + 6.0 * s, 3.4 * s, 3.4 * s, 4.4 * s,
       'iron_dark', parent)


def stub_flange(p, axis, r, parent):
    """Where a pipe run is meant to be bolted onto by the next thing along."""
    ring(p, axis, r * 1.45, 2.6, 'iron_dark', parent, verts=8)
    ring(Vector(p) - Vector(axis).normalized() * 2.0, axis, r * 1.18, 2.0,
         'brass', parent, verts=8)


def vertical_boiler(x, y, z, r, h, parent, flue=14.0, flue_r=None,
                    door_dir=(1, 0, 0)):
    """Small vertical boiler: firebox, riveted shell, dome, uptake flue.
    Returns (dome_top_z, steam_tap_point)."""
    flue_r = flue_r or r * 0.34
    bx(x, y, z, r * 2.5, r * 2.5, 2.0, 'stone_dark', parent)
    cy(x, y, z + 2.0, r * 1.04, h * 0.24, 'iron_dark', parent, verts=10)
    d = Vector(door_dir).normalized()
    bx(x + d.x * r * 0.98, y + d.y * r * 0.98, z + 4.0,
       2.0 if abs(d.x) > 0.5 else r * 0.9, r * 0.9 if abs(d.x) > 0.5 else 2.0,
       r * 0.8, 'iron_dark', parent)
    shell_z = z + 2.0 + h * 0.24
    shell_h = h * 0.76
    cy(x, y, shell_z, r, shell_h, 'iron', parent, verts=10)
    rivet_bands((x, y, shell_z), (x, y, shell_z + shell_h), r, 2, parent)
    # vertical lap seam
    bx(x + r * 0.94, y, shell_z, 1.6, r * 0.5, shell_h, 'iron_dark', parent)
    top = shell_z + shell_h
    cy(x, y, top, r * 0.66, r * 0.42, 'iron', parent, verts=8)
    dome_top = top + r * 0.42
    cy(x, y, dome_top, flue_r, flue, 'soot', parent, verts=6)
    cy(x, y, dome_top + flue, flue_r * 1.5, 2.0, 'iron_dark', parent, verts=6)
    relief_valve(x + r * 0.4, y, dome_top, parent, s=r / 8.0)
    return dome_top, (x - r * 0.9, y, top - 1.0)


def pipe_support(x, y, top_z, parent, axis='x', w=13.0):
    """Short trestle carrying a pipe: stone pad, splayed iron legs, saddle."""
    ax = axis == 'x'
    pw, pd = (9.0, w + 3.0) if ax else (w + 3.0, 9.0)
    bx(x, y, 0, pw, pd, 3.0, 'stone', parent)
    bx(x, y, 3.0, pw - 2.6, pd - 2.6, 1.6, 'stone_light', parent)
    for s in (-1, 1):
        if ax:
            a = (x, y + s * (w * 0.42), 4.6)
            b = (x, y + s * (w * 0.24), top_z - 1.6)
        else:
            a = (x + s * (w * 0.42), y, 4.6)
            b = (x + s * (w * 0.24), y, top_z - 1.6)
        beam(a, b, 2.3, 2.3, 'iron', parent)
    sw, sd = (5.0, w * 0.72) if ax else (w * 0.72, 5.0)
    bx(x, y, top_z - 2.0, sw, sd, 2.0, 'iron', parent)


def coal_lumps(parent, ox, oy, oz, n, spread, hi, seed=3, mats=('coal', 'coal',
                                                               'soot')):
    rnd = random.Random(seed)
    for _ in range(n):
        s = rnd.uniform(0.55, 1.0)
        bx(ox + rnd.uniform(-spread, spread), oy + rnd.uniform(-spread, spread),
           oz + rnd.uniform(0.0, hi * 0.45), 7 * s, 6 * s, 5 * s,
           mats[rnd.randrange(len(mats))], parent,
           rot=(rnd.uniform(-0.4, 0.4), rnd.uniform(-0.4, 0.4),
                rnd.uniform(0, TAU)))


def hopper(parent, ox, oy, leg_h=26.0, w=34.0, body_h=16.0, chute_to=None):
    """Elevated coal bunker: legs, riveted box, V-throat, gate, chute.
    Returns the throat point so a chute can be aimed at something real."""
    half = w * 0.38
    for sx in (-1, 1):
        for sy in (-1, 1):
            bx(ox + sx * half, oy + sy * half, 0, 4.2, 4.2, leg_h, 'iron',
               parent)
    for sy in (-1, 1):  # sway bracing, so the legs are not four lonely sticks
        beam((ox - half, oy + sy * half, 1.0), (ox + half, oy + sy * half,
                                                leg_h - 2.0), 2.0, 2.0, 'iron',
             parent)
        beam((ox + half, oy + sy * half, 1.0), (ox - half, oy + sy * half,
                                                leg_h - 2.0), 2.0, 2.0, 'iron',
             parent)
    throat_z = leg_h - 2.0
    # V-throat: a wedge flipped so the ridge is the bottom of the funnel
    wg(ox, oy, throat_z, w, w, 9.0, 'iron', parent,
       rot=(math.pi, 0, 0))
    bx(ox, oy, throat_z + 9.0, w, w, body_h, 'iron', parent)
    for z in (throat_z + 11.0, throat_z + 9.0 + body_h - 3.5):
        bx(ox, oy, z, w + 1.2, w + 1.2, 2.2, 'iron_dark', parent)
    # open coping rim, so the load inside is visible rather than lidded over
    rim = throat_z + 9.0 + body_h
    coal_lumps(parent, ox, oy, rim - 0.8, 6, w * 0.26, 6, seed=11)
    for s in (-1, 1):
        bx(ox, oy + s * (w / 2 + 1.0), rim - 1.0, w + 5.0, 3.0, 3.4,
           'iron_dark', parent)
        bx(ox + s * (w / 2 + 1.0), oy, rim - 1.0, 3.0, w + 5.0, 3.4,
           'iron_dark', parent)
    # throat, sliding gate and its lever: this is what lets the coal out
    bx(ox, oy, throat_z - 5.0, w * 0.30, w * 0.30, 5.5, 'iron', parent)
    gd = Vector((1.0, 0.0, 0.0))
    if chute_to:
        gv = Vector((chute_to[0] - ox, chute_to[1] - oy, 0.0))
        if gv.length > 1e-4:
            gd = gv.normalized()
    gx, gy = ox + gd.x * w * 0.19, oy + gd.y * w * 0.19
    bx(gx, gy, throat_z - 6.0, 2.6 if abs(gd.x) > 0.5 else w * 0.34,
       w * 0.34 if abs(gd.x) > 0.5 else 2.6, 10.0, 'iron_dark', parent)
    beam((gx, gy, throat_z + 4.0),
         (gx + gd.x * 7.0, gy + gd.y * 7.0, throat_z + 13.0), 2.0, 2.0, 'iron',
         parent)
    # railed timber gallery at the throat: somewhere to stand and work the gate
    gz, go, gl = throat_z + 2.0, w / 2 + 2.0, w + 9.0
    for sd in (-1, 1):
        bx(ox + sd * go, oy, gz, 6.5, gl, 1.8, 'timber_light', parent)
        bx(ox, oy + sd * go, gz, gl, 6.5, 1.8, 'timber_light', parent)
        beam((ox + sd * go, oy - go, gz + 9.5), (ox + sd * go, oy + go, gz + 9.5),
             1.4, 1.4, 'timber', parent)
        beam((ox - go, oy + sd * go, gz + 9.5), (ox + go, oy + sd * go, gz + 9.5),
             1.4, 1.4, 'timber', parent)
        for sd2 in (-1, 1):
            bx(ox + sd * go, oy + sd2 * go, gz + 1.8, 1.6, 1.6, 8.6, 'timber',
               parent)
    throat = (ox, oy, throat_z - 5.0)
    if chute_to:
        p0 = Vector((ox, oy, throat_z - 5.0))
        p1 = Vector(chute_to)
        n = Vector((-(p1.y - p0.y), p1.x - p0.x, 0.0))
        n = n.normalized() if n.length > 1e-4 else Vector((0.0, 1.0, 0.0))
        beam(p0, p1, 10.0, 1.8, 'timber', parent)
        for sd in (-1, 1):
            beam(p0 + n * (sd * 5.0), p1 + n * (sd * 5.0), 1.8, 4.4,
                 'timber_light', parent)
        for f in (0.35, 0.7):
            c = p0.lerp(p1, f)
            beam(c + n * 5.0, c - n * 5.0, 1.6, 1.6, 'timber', parent)
        if p1.z > 6.0:
            bx(p1.x, p1.y, 0, 4.0, 4.0, p1.z - 1.0, 'timber', parent)
    return throat


def octagon_wheel(cx, cyy, cz, r, width, parent, segs=8, rim_t=2.8, spokes=4,
                  rim_m='iron_dark', spoke_m='iron', hub_m='iron'):
    """A wheel that reads as a wheel: chorded rim, hub, spokes. Axle along Y."""
    chord = 2.0 * r * math.sin(math.pi / segs)
    for i in range(segs):
        a = TAU * (i + 0.5) / segs
        px = cx + (r - rim_t * 0.5) * math.cos(a)
        pz = cz + (r - rim_t * 0.5) * math.sin(a)
        ob = _box_c(chord * 1.06, width, rim_t, rim_m, parent)
        ob.location = (px, cyy, pz)
        ob.rotation_euler = (0, -(a + math.pi / 2.0), 0)
    for i in range(spokes):
        a = TAU * i / (spokes * 2.0)
        L = (r - rim_t) * 2.0
        ob = _box_c(width * 0.42, width * 0.5, L, spoke_m, parent)
        ob.location = (cx, cyy, cz)
        ob.rotation_euler = (0, math.pi / 2.0 - a, 0)
    cy(cx, cyy - width * 0.75, cz, r * 0.24, width * 1.5, hub_m, parent,
       verts=8, rot=(math.pi / 2.0, 0, 0))
    return (cx, cyy, cz)


# ------------------------------------------------------------------- assets

def foundry_hall():
    """The landmark. Masonry nave with lower aisles, louvred roof monitor to
    dump furnace heat, a 120-unit chimney fed by a flue duct off the hall, an
    external boiler piped into the building, and a coal hopper chuting fuel
    through the wall. One small ember mouth on the front."""
    _calibrate()
    R = C.empty('foundry_hall')
    HW, HD, WALL = 100.0, 44.0, 58.0

    bx(0, 0, 0, HW + 14, 84, 6, 'stone_dark', R)                     # plinth
    bx(0, 0, 6, HW, HD, WALL - 6, 'stone_light', R)                  # nave
    for sx in (-1, 1):                                               # quoins
        bx(sx * (HW / 2 - 2), 0, 6, 5, HD + 1.5, WALL - 6, 'stone', R)
    bx(0, 0, WALL - 6, HW + 2, HD + 2, 3, 'stone', R)                # cornice

    for sy in (-1, 1):                                               # aisles
        ay = sy * (HD / 2 + 7.5)
        bx(0, ay, 6, HW, 15, 24, 'stone_light', R)
        beam((0, sy * (HD / 2 + 1), 33), (0, sy * (HD / 2 + 16), 26),
             HW + 8, 2.4, 'roof_slate', R)
        for x in (-42, -14, 14, 42):                                 # buttresses
            bx(x, sy * (HD / 2 + 16.5), 6, 8, 5, 22, 'stone', R)
        for x in (-40, -24, -8, 8, 24, 40):                          # clerestory
            bx(x, sy * (HD / 2 - 0.4), 36, 8, 1.6, 12, 'iron_dark', R)
            bx(x, sy * (HD / 2 - 0.4), 48, 9, 2.0, 2.5, 'stone_light', R)

    # roof: eaves overhang in Y only, so the coped stone gables stay visible
    bx(0, 0, WALL - 3, HW, HD + 8, 3, 'timber', R)
    wg(0, 0, WALL, HW, HD + 8, 24, 'roof_slate', R)
    for sx in (-1, 1):
        wg(sx * (HW / 2 + 1), 0, WALL - 3, 6, HD + 10, 28, 'stone_light', R)

    # roof monitor — louvred lantern that lets the furnace heat out
    bx(0, 0, 66, 58, 17, 18, 'timber', R)
    for sy in (-1, 1):
        for z in (69, 74, 79):
            bx(0, sy * 9.0, z, 54, 1.6, 3.0, 'iron_dark', R)
    roof(0, 0, 84, 58, 17, 8, 'roof_slate', R, overhang=3.0, eave='iron_dark')

    # --- chimney, fed by a flue duct out of the hall's west gable
    ch = (-68.0, -12.0)
    bx(ch[0], ch[1], 0, 28, 28, 6, 'stone_dark', R)
    bx(ch[0], ch[1], 6, 24, 24, 5, 'stone', R)
    secs = [(11, 36, 19.4), (47, 34, 17.0), (81, 30, 14.8), (111, 13, 12.8)]
    for i, (z, h, w) in enumerate(secs):
        bx(ch[0], ch[1], z, w, w, h, 'soot' if i == 3 else 'roof_tile', R)
        if i in (1, 2):
            bx(ch[0], ch[1], z, w + 1.5, w + 1.5, 2.4, 'iron_dark', R)
    bx(ch[0], ch[1], 124, 15.6, 15.6, 4.0, 'iron_dark', R)           # cap 128
    bx(-55.0, ch[1], 30, 22, 16, 17, 'stone', R)                     # flue duct
    bx(-55.0, ch[1], 47, 24, 18, 3.0, 'stone_dark', R)
    for x in (-61, -49):
        bx(x, ch[1], 29, 3.2, 18, 19, 'iron_dark', R)
    for sy in (-1, 1):
        beam((-62, ch[1] + sy * 8.5, 30), (-48, ch[1] + sy * 8.5, 30),
             1.6, 1.6, 'iron', R)

    # --- external boiler, piped into the hall
    by_ = -56.0
    bx(-18, by_, 0, 54, 30, 4, 'stone', R)
    for x in (-38, -18, 2):
        bx(x, by_, 4, 9, 26, 8, 'stone_light', R)
    tube((-40, by_, 23), (4, by_, 23), 11.0, 'iron', R, verts=12)
    rivet_bands((-40, by_, 23), (4, by_, 23), 11.0, 3, R, verts=12)
    ring((-40, by_, 23), (1, 0, 0), 11.8, 2.2, 'iron_dark', R, verts=12)
    ring((4, by_, 23), (1, 0, 0), 11.8, 2.2, 'iron_dark', R, verts=12)
    bx(-42.0, by_, 15, 3.0, 13, 14, 'iron_dark', R)                  # fire door
    handwheel((-43.6, by_, 22), (1, 0, 0), 3.4, R)
    bx(-18, by_, 33, 42, 5, 1.6, 'iron_dark', R)                     # top seam
    relief_valve(-30, by_, 33.6, R, s=1.0)
    # steam out: drum -> up -> over the aisle roof -> into the nave wall
    tube((-8, by_, 32), (-8, by_, 46), 3.2, 'iron', R)
    ring((-8, by_, 33), (0, 0, 1), 4.6, 2.4, 'brass', R)
    handwheel((-8, by_ - 5.2, 39), (0, 1, 0), 3.4, R)
    tube((-8, by_ - 2, 46), (-8, -21, 46), 3.2, 'iron', R)
    bx(-8, -21, 40, 7, 7, 8, 'iron_dark', R)
    for s in (-1, 1):                                                # pipe bent
        beam((-8, -34, 46), (-8 + s * 5, -30, 30), 2.2, 2.2, 'iron', R)
    # feedwater in: tank -> pump stub -> check valve on the drum end
    bx(-58, by_ - 4, 0, 18, 18, 20, 'iron', R)
    for z in (3, 16):
        bx(-58, by_ - 4, z, 19.2, 19.2, 2.2, 'timber', R)
    bx(-58, by_ - 4, 20, 19, 19, 1.6, 'timber_light', R)
    tube((-49, by_ - 4, 9), (-41, by_, 9), 2.2, 'iron', R)
    tube((-41, by_, 9), (-41, by_, 19), 2.2, 'iron', R)
    ring((-41, by_, 18), (0, 0, 1), 3.2, 2.4, 'brass', R)
    tube((-41, by_, 19), (-38, by_, 19), 2.2, 'iron', R)

    # --- coal hopper on the north side, chuting through the aisle wall
    hopper(R, 22.0, 56.0, leg_h=26.0, w=30.0, body_h=15.0,
           chute_to=(22.0, 38.0, 9.0))
    bx(22.0, 36.0, 5, 8, 5, 12, 'iron_dark', R)                      # stoke door
    coal_lumps(R, -8, 56, 0, 9, 11, 9, seed=5)
    bx(-8, 68, 0, 30, 3.0, 9, 'timber', R)

    # --- furnace bay on the front, and the casting apron
    bx(59, 0, 6, 18, 36, 40, 'stone_light', R)
    for sy in (-1, 1):
        bx(59, sy * 18.5, 6, 18, 4, 40, 'stone', R)
    roof(59, 0, 46, 18, 36, 9, 'roof_slate', R, overhang=3.0)
    bx(68.4, 0, 6, 3.0, 17, 19, 'iron_dark', R)                      # mouth
    bx(69.4, 0, 8, 1.4, 10, 12, 'ember', R)                          # the ember
    bx(69.0, 0, 25, 5.0, 21, 4.0, 'stone', R)                        # lintel
    bx(83, 0, 0, 26, 40, 2.5, 'stone', R)                            # apron
    for i, (dx, dy) in enumerate(((-4, -10), (2, -6), (-2, 9), (5, 13))):
        bx(83 + dx, dy, 2.5, 12, 4.5, 3.0, 'iron', R,
           rot=(0, 0, 0.25 * (i - 1.5)))
    bx(88, 22, 0, 14, 14, 3.0, 'stone', R)                           # sand bed
    _recentre(R)
    return R


def boiler_large():
    """Horizontal riveted drum on stone saddles: smokebox and uptake at one end,
    feedwater in low, steam out high, safety valve on top."""
    _calibrate()
    R = C.empty('boiler_large')
    z0, r = 26.0, 13.0
    bx(0, 0, 0, 74, 32, 5, 'stone', R)
    for x in (-24, 0, 24):
        bx(x, 0, 5, 9, 29, 6, 'stone_light', R)
        bx(x, 0, 11, 11, 26, 2, 'stone', R)
    tube((-32, 0, z0), (32, 0, z0), r, 'iron', R, verts=12)
    rivet_bands((-32, 0, z0), (32, 0, z0), r, 4, R, t=2.8, verts=12)
    for sx in (-1, 1):
        ring((sx * 32, 0, z0), (1, 0, 0), r * 1.06, 2.4, 'iron_dark', R,
             verts=12)
    bx(0, 0, z0 + r - 1.4, 58, 5.0, 1.6, 'iron_dark', R)             # lap seam

    # smokebox: a slightly fatter drum on the end, its door and uptake
    tube((-40.5, 0, z0), (-31, 0, z0), r * 1.08, 'iron_dark', R, verts=12)
    ring((-40.5, 0, z0), (1, 0, 0), r * 1.14, 2.0, 'iron', R, verts=12)
    ring((-42.2, 0, z0), (1, 0, 0), 8.4, 2.4, 'iron_dark', R, verts=10)
    handwheel((-44.0, 0, z0), (1, 0, 0), 5.0, R)
    cy(-36, 0, z0 + 12, 5.2, 16, 'soot', R, verts=8)
    cy(-36, 0, z0 + 28, 6.8, 2.2, 'iron_dark', R, verts=8)
    relief_valve(9, 0, z0 + r - 0.5, R, s=1.05)

    # steam out: crown flange -> stop valve -> over the end -> stub flange
    ring((22, 0, z0 + r - 1.0), (0, 0, 1), 4.6, 3.0, 'brass', R)
    tube((22, 0, z0 + r - 1), (22, 0, 52), 3.4, 'iron', R)
    handwheel((22, -5.4, 45), (0, 1, 0), 3.6, R)
    tube((22, 0, 52), (44, 0, 52), 3.4, 'iron', R)
    bx(44, 0, 48, 8, 8, 8, 'iron_dark', R)
    tube((44, 0, 52), (44, 0, 34), 3.4, 'iron', R)
    stub_flange((44, 0, 33), (0, 0, -1), 3.4, R)
    pipe_support(44, 0, 30.0, R, axis='y', w=11.0)

    # feedwater in: stub -> check valve -> shell, low and at the side
    tube((44, 11, 8), (33, 11, 8), 2.4, 'iron', R)
    stub_flange((44, 11, 8), (1, 0, 0), 2.4, R)
    tube((33, 11, 8), (33, 11, 19), 2.4, 'iron', R)
    ring((33, 11, 18), (0, 0, 1), 3.4, 2.6, 'brass', R)
    tube((33, 11, 19), (31, 8, 20), 2.4, 'iron', R)
    # water gauge on the end plate, so the stoker can see the level
    bx(33.5, -6, 20, 2.6, 3.4, 12, 'iron_dark', R)
    cy(35.0, -6, 21, 1.0, 10, 'steel', R, verts=6)
    for z in (20.5, 30.0):
        ring((35.0, -6, z), (0, 0, 1), 1.9, 1.6, 'brass', R, verts=6)
    _recentre(R)
    return R


def boiler_small():
    """Vertical boiler on a stone footing — the workhorse unit."""
    _calibrate()
    R = C.empty('boiler_small')
    bx(0, 0, 0, 34, 34, 3, 'stone', R)
    bx(0, 0, 3, 28, 28, 3, 'stone_light', R)
    vertical_boiler(0, 0, 6, 10.0, 34.0, R, flue=17.0)
    # steam out to a stub flange on a trestle
    tube((-9, 0, 36), (-22, 0, 36), 2.8, 'iron', R)
    bx(-22, 0, 32, 7, 7, 7, 'iron_dark', R)
    tube((-22, 0, 36), (-22, 0, 16), 2.8, 'iron', R)
    handwheel((-22, -4.8, 26), (0, 1, 0), 3.2, R)
    stub_flange((-22, 0, 15), (0, 0, -1), 2.8, R)
    pipe_support(-22, 0, 13.0, R, axis='y', w=10.0)
    # feedwater in, into the water space above the firebox, via a check valve
    tube((26, 0, 20), (10, 0, 20), 2.2, 'iron', R)
    stub_flange((26, 0, 20), (1, 0, 0), 2.2, R)
    ring((11, 0, 20), (1, 0, 0), 3.2, 2.4, 'brass', R)
    tube((22, 0, 20), (22, 0, 6), 2.2, 'iron', R)
    pipe_support(22, 0, 6.0, R, axis='x', w=9.0)
    # coal for the firebox, next to the door
    coal_lumps(R, 15, -14, 0, 5, 5, 5, seed=9)
    _recentre(R)
    return R


def chimney_stack():
    """Standalone tapered brick stack with a sooted head and a service ladder."""
    _calibrate()
    R = C.empty('chimney_stack')
    bx(0, 0, 0, 30, 30, 6, 'stone_dark', R)
    bx(0, 0, 6, 25, 25, 12, 'stone', R)
    secs = [(18, 26, 10.6), (44, 24, 9.2), (68, 22, 8.0), (90, 20, 7.0)]
    for i, (z, h, r) in enumerate(secs):
        cy(0, 0, z, r, h, 'roof_tile', R, verts=8)
        if i in (1, 2):
            cy(0, 0, z, r * 1.08, 2.4, 'iron_dark', R, verts=8)
    cy(0, 0, 110, 6.4, 12, 'soot', R, verts=8)
    cy(0, 0, 122, 7.9, 5.0, 'soot', R, verts=8)                      # corbel cap
    cy(0, 0, 127, 7.1, 2.0, 'iron_dark', R, verts=8)
    # flue opening at the base — smoke has to get in from somewhere
    bx(11.8, 0, 6, 3.0, 12, 14, 'iron_dark', R)
    bx(12.0, 0, 20, 4.5, 15, 3.5, 'stone_light', R)
    # ladder, on the leeward side
    for sy in (-1, 1):
        bx(-9.2, sy * 2.8, 18, 1.8, 1.8, 88, 'iron_dark', R)
    for i in range(10):
        bx(-9.2, 0, 22 + i * 8.6, 1.6, 6.4, 1.6, 'iron_dark', R)
    _recentre(R)
    return R


PIPE_R = 4.0
PIPE_Z = 15.0
TILE = 60.0


def _pipe_ends(R, p, axis):
    ring(p, axis, PIPE_R * 1.3, 2.0, 'iron_dark', R)


def pipe_run_straight():
    """A 60-unit tile. Ends flush at x = +/-30 so runs butt end to end."""
    _calibrate()
    R = C.empty('pipe_run_straight')
    tube((-TILE / 2, 0, PIPE_Z), (TILE / 2, 0, PIPE_Z), PIPE_R, 'iron', R)
    for sx in (-1, 1):
        _pipe_ends(R, (sx * (TILE / 2 - 1.0), 0, PIPE_Z), (1, 0, 0))
        pipe_support(sx * 18, 0, PIPE_Z - PIPE_R, R, axis='x')
        bx(sx * 18, 0, PIPE_Z + PIPE_R - 1.4, 1.8, 9.6, 1.6, 'iron_dark', R)
    ring((0, 0, PIPE_Z), (1, 0, 0), PIPE_R * 1.22, 2.4, 'iron_dark', R)
    _recentre(R, xy=False)
    return R


def pipe_run_corner():
    """A 60x60 tile. Comes in west at (-30, 0), leaves north at (0, +30);
    rotate in 90-degree steps for the other three corners."""
    _calibrate()
    R = C.empty('pipe_run_corner')
    tube((-TILE / 2, 0, PIPE_Z), (0, 0, PIPE_Z), PIPE_R, 'iron', R)
    tube((0, 0, PIPE_Z), (0, TILE / 2, PIPE_Z), PIPE_R, 'iron', R)
    bx(0, 0, PIPE_Z - 4.8, 9.0, 9.0, 9.6, 'iron_dark', R,            # cast elbow
       rot=(0, 0, rad(45)))
    ring((-5.6, 0, PIPE_Z), (1, 0, 0), PIPE_R * 1.28, 2.0, 'iron_dark', R)
    ring((0, 5.6, PIPE_Z), (0, 1, 0), PIPE_R * 1.28, 2.0, 'iron_dark', R)
    _pipe_ends(R, (-(TILE / 2 - 1.0), 0, PIPE_Z), (1, 0, 0))
    _pipe_ends(R, (0, TILE / 2 - 1.0, PIPE_Z), (0, 1, 0))
    bx(0, 0, 0, 9, 9, PIPE_Z - 5.6, 'stone', R)                      # corner pier
    bx(0, 0, PIPE_Z - 5.6, 11, 11, 1.6, 'stone_light', R)
    pipe_support(-20, 0, PIPE_Z - PIPE_R, R, axis='x')
    bx(-20, 0, PIPE_Z + PIPE_R - 1.4, 1.8, 9.6, 1.6, 'iron_dark', R)
    pipe_support(0, 20, PIPE_Z - PIPE_R, R, axis='y')
    bx(0, 20, PIPE_Z + PIPE_R - 1.4, 9.6, 1.8, 1.6, 'iron_dark', R)
    _recentre(R, xy=False)
    return R


def steam_crane():
    """A derrick that lifts: boiler -> engine -> crank -> winch drum -> rope over
    the mast head and jib head -> hook. Counterweight over the slew ring."""
    _calibrate()
    R = C.empty('steam_crane')
    cy(0, 0, 0, 17, 3, 'stone', R, verts=8)
    cy(0, 0, 3, 15, 2, 'stone_light', R, verts=8)
    cy(0, 0, 5, 13.5, 2, 'iron', R, verts=12)                        # slew ring
    bx(-6, 0, 7, 40, 26, 4, 'timber_light', R)                       # deck
    for sy in (-1, 1):
        bx(-6, sy * 12.0, 7, 40, 2.4, 3.0, 'timber', R)
        bx(-6, sy * 12.0, 10, 40, 2.0, 2.4, 'iron_dark', R)

    bx(-20, 0, 11, 14, 22, 14, 'stone', R)                           # ballast
    bx(-20, 0, 25, 15, 23, 2.5, 'stone_light', R)
    for sy in (-1, 1):
        bx(-20, sy * 7.5, 11, 15, 2.4, 14, 'iron_dark', R)

    dome, tap = vertical_boiler(-8, 3.0, 11, 6.5, 21, R, flue=12.0)

    # engine: cylinder, piston rod, connecting rod, crank on the drum shaft
    eng_y = -8.5
    tube((-17, eng_y, 16), (-7, eng_y, 16), 3.6, 'iron', R)
    ring((-17, eng_y, 16), (1, 0, 0), 4.4, 2.2, 'iron_dark', R)
    ring((-7, eng_y, 16), (1, 0, 0), 4.4, 2.2, 'iron_dark', R)
    bx(-12, eng_y, 11, 13, 9, 5, 'iron_dark', R)                     # bedplate
    tube((-7, eng_y, 16), (-2, eng_y, 16), 1.2, 'steel', R, verts=6)
    bx(-2, eng_y, 14, 3.4, 4.0, 4.0, 'steel', R)                     # crosshead
    tube((-2, eng_y, 16), (2, -11.2, 19), 1.4, 'steel', R, verts=6)
    # steam line: dome -> stop valve -> engine
    tube((tap[0], tap[1], tap[2]), (-15.5, eng_y, tap[2]), 2.0, 'iron', R)
    tube((-15.5, eng_y, tap[2]), (-15.5, eng_y, 18.5), 2.0, 'iron', R)
    handwheel((-15.5, eng_y, 24), (0, 1, 0), 2.8, R)
    tube((-15.5, eng_y, 18.5), (-16.5, eng_y, 16.5), 2.0, 'iron', R)

    # winch drum with rope on it
    tube((2, -9.0, 16), (2, 9.0, 16), 4.6, 'iron_dark', R, verts=10)
    tube((2, -6.5, 16), (2, 6.5, 16), 5.3, 'canvas', R, verts=10)
    for sy in (-1, 1):
        ring((2, sy * 9.0, 16), (0, 1, 0), 6.4, 1.6, 'iron', R, verts=10)
        bx(2, sy * 11.5, 11, 6, 3.2, 5, 'iron', R)
    tube((2, -12.5, 16), (2, 12.5, 16), 1.5, 'steel', R, verts=6)
    ring((2, -11.2, 16), (0, 1, 0), 3.6, 1.6, 'iron_dark', R, verts=8)
    bx(2, 11.0, 16, 3.0, 2.4, 9.0, 'iron', R)                        # brake lever

    # mast
    bx(8, 0, 11, 6.5, 6.5, 55, 'iron', R)
    bx(8, 0, 34, 8.5, 8.5, 2.6, 'iron_dark', R)
    for sx in (-1, 1):
        for sy in (-1, 1):
            beam((8 + sx * 0.5, sy * 0.5, 28), (8 + sx * 8.5, sy * 9.5, 11),
                 2.2, 2.2, 'iron', R)
    bx(8, 0, 66, 9, 9, 4, 'iron_dark', R)
    octagon_wheel(8, 3.4, 69.0, 3.6, 2.4, R, segs=6, rim_t=1.6, spokes=3)

    # jib: two chords with an open zigzag web, pinned at the deck foot and
    # held up by a topping rope off the mast head
    jl0, jl1 = Vector((12, 0, 13)), Vector((62, 0, 44))
    ju0, ju1 = Vector((12, 0, 24)), Vector((62, 0, 49))
    beam(jl0, jl1, 6.5, 3.2, 'iron', R)
    beam(ju0, ju1, 6.5, 2.8, 'iron', R)
    zig = [(0, 0.10, 1, 0.30), (1, 0.30, 0, 0.50), (0, 0.50, 1, 0.70),
           (1, 0.70, 0, 0.90)]
    for ca, fa, cb, fb in zig:
        a = (jl0.lerp(jl1, fa) if ca == 0 else ju0.lerp(ju1, fa))
        b = (jl0.lerp(jl1, fb) if cb == 0 else ju0.lerp(ju1, fb))
        beam(a, b, 3.2, 1.5, 'iron_dark', R)
    bx(12, 0, 12, 6, 13, 13, 'iron_dark', R)                         # jib pivot
    tube((12, -6.5, 17), (12, 6.5, 17), 1.8, 'steel', R, verts=6)
    bx(62.5, 0, 43, 7, 8.5, 7, 'iron_dark', R)
    octagon_wheel(62.5, 0.0, 46.0, 3.6, 2.4, R, segs=6, rim_t=1.6, spokes=3)

    tube((8, 0, 69), (62.5, 0, 48.5), 0.9, 'iron_dark', R, verts=6)  # topping
    tube((2, 3.4, 21), (8, 3.4, 68), 0.85, 'iron_dark', R, verts=6)  # hoist
    tube((8, 2.4, 69.5), (62.6, 0.4, 47.5), 0.85, 'iron_dark', R, verts=6)
    tube((62.5, 0, 46), (62.5, 0, 20), 0.85, 'iron_dark', R, verts=6)
    bx(62.5, 0, 13, 7, 6, 8, 'iron', R)                              # hook block
    for sy in (-1, 1):
        octagon_wheel(62.5, sy * 2.2, 17.0, 2.4, 1.6, R, segs=6, rim_t=1.2,
                      spokes=3)
    bx(62.5, 0, 7, 2.8, 2.8, 6, 'steel', R)
    bx(64.1, 0, 5.4, 5.0, 2.8, 2.8, 'steel', R)
    bx(66.1, 0, 5.4, 2.6, 2.6, 4.4, 'steel', R)
    _recentre(R)
    return R


def mine_headframe():
    """Pit head. Timber A-frame and rakers carry a winding wheel offset so one
    rope falls plumb down the shaft; the other runs to a steam winder."""
    _calibrate()
    R = C.empty('mine_headframe')
    LEG_TOP = 58.0
    WHEEL = (-13.0, 73.0)

    # shaft collar: timber baulks around a black hole
    for sd in (-1, 1):                                               # bank
        bx(sd * 15.0, 0, 0, 10, 40, 4.5, 'timber_light', R)
        bx(0, sd * 15.0, 0, 40, 10, 4.5, 'timber_light', R)
    bx(0, 0, 0, 22, 22, 1.2, 'soot', R)                              # the shaft
    for sd in (-1, 1):
        bx(sd * 19.0, 0, 0, 4.5, 42, 7.0, 'timber', R)               # collar
        bx(0, sd * 19.0, 0, 42, 4.5, 7.0, 'timber', R)
    for sx in (-1, 1):
        for sy in (-1, 1):
            bx(sx * 18.5, sy * 18.5, 7.0, 6.0, 6.0, 3.5, 'timber', R)

    # front legs lean over the shaft, back rakers take the winder's pull
    for sy in (-1, 1):
        beam((12, sy * 13, 0), (-4, sy * 9, LEG_TOP), 5.4, 5.4, 'timber', R)
        beam((-44, sy * 14, 0), (-20, sy * 9, LEG_TOP - 2), 5.0, 5.0, 'timber', R)
        beam((10, sy * 12.6, 6), (-19, sy * 9.4, LEG_TOP - 4), 3.0, 3.0,
             'timber', R)
    for z in (16.0, 34.0, 50.0):
        f = z / LEG_TOP
        bx(12 + (-4 - 12) * f, 0, z, 5.5, 26, 4.5, 'timber', R)
        bx(-44 + 24 * f, 0, z - 2, 5.0, 26, 4.0, 'timber', R)
    for sy in (-1, 1):                                               # x-bracing
        beam((10, sy * 12.6, 8), (-2, sy * 9.4, 48), 2.6, 2.6, 'timber', R)
        beam((-1, sy * 9.6, 10), (-3.5, sy * 9.2, 50), 2.6, 2.6, 'timber', R)

    bx(-13, 0, LEG_TOP - 4, 26, 28, 5.0, 'timber', R)                # head beam
    for sy in (-1, 1):
        bx(-13, sy * 6.0, LEG_TOP + 1, 7.0, 4.5, 14.0, 'iron_dark', R)
    octagon_wheel(WHEEL[0], 0.0, WHEEL[1], 13.0, 4.4, R, segs=10, rim_t=3.0,
                  spokes=4)
    tube((WHEEL[0], -7.5, WHEEL[1]), (WHEEL[0], 7.5, WHEEL[1]), 1.7, 'steel', R,
         verts=6)

    # ropes: one plumb down the shaft to the cage, one back to the winder
    tube((0, 0, WHEEL[1] - 0.5), (0, 0, 20.5), 0.9, 'iron_dark', R, verts=6)
    tube((-26, 0, WHEEL[1] - 0.5), (-56, 0, 22.0), 0.9, 'iron_dark', R, verts=6)

    # cage standing at bank
    bx(0, 0, 4.5, 12, 12, 1.6, 'timber_light', R)
    for sx in (-1, 1):
        for sy in (-1, 1):
            bx(sx * 5.2, sy * 5.2, 4.5, 1.8, 1.8, 15, 'iron_dark', R)
    for sy in (-1, 1):
        bx(0, sy * 5.6, 8.5, 12, 1.2, 6.0, 'iron_dark', R)
    bx(0, 0, 19.5, 13, 13, 1.6, 'iron_dark', R)
    bx(0, 0, 21.1, 4.0, 4.0, 2.4, 'iron_dark', R)

    # steam winder: drum with rope, engine, engine house
    bx(-56, 0, 0, 26, 30, 6, 'stone', R)
    for sy in (-1, 1):
        bx(-56, sy * 11.5, 6, 8, 4.5, 16, 'iron', R)
    tube((-56, -9.5, 22), (-56, 9.5, 22), 8.0, 'iron_dark', R, verts=10)
    tube((-56, -7, 22), (-56, 7, 22), 8.9, 'canvas', R, verts=10)
    for sy in (-1, 1):
        ring((-56, sy * 9.5, 22), (0, 1, 0), 10.0, 1.8, 'iron', R, verts=10)
    tube((-56, -15, 22), (-56, 15, 22), 1.8, 'steel', R, verts=6)
    ring((-56, -13.5, 22), (0, 1, 0), 5.0, 1.8, 'iron_dark', R, verts=8)
    bx(-56, 13.5, 22, 3.4, 2.6, 11, 'iron', R)                       # brake lever
    tube((-72, -19, 18), (-60, -19, 18), 4.0, 'iron', R)             # cylinder
    ring((-72, -19, 18), (1, 0, 0), 4.9, 2.2, 'iron_dark', R)
    ring((-60, -19, 18), (1, 0, 0), 4.9, 2.2, 'iron_dark', R)
    bx(-66, -19, 12, 15, 10, 6, 'stone_light', R)
    tube((-60, -19, 18), (-56, -19, 18), 1.3, 'steel', R, verts=6)
    tube((-56, -19, 18), (-56, -13.6, 25.5), 1.5, 'steel', R, verts=6)

    bx(-84, 4, 0, 30, 30, 8, 'stone', R)
    bx(-84, 4, 8, 27, 27, 17, 'plaster', R)
    for sx in (-1, 1):
        for sy in (-1, 1):
            bx(-84 + sx * 12.5, 4 + sy * 12.5, 8, 3.4, 3.4, 17, 'timber', R)
    roof(-84, 4, 25, 27, 27, 12, 'roof_slate', R, overhang=3.5)
    cy(-77, -5, 30, 2.6, 22, 'soot', R, verts=6)
    cy(-77, -5, 52, 3.8, 2.2, 'iron_dark', R, verts=6)
    tube((-73, -10, 16), (-73, -14, 16), 2.0, 'iron', R)             # steam feed
    tube((-73, -14, 16), (-73, -14, 24), 2.0, 'iron', R)
    handwheel((-73, -14, 26.6), (0, 0, 1), 2.6, R)
    tube((-73, -14, 24), (-73, -19, 24), 2.0, 'iron', R)
    tube((-73, -19, 24), (-73, -19, 19.5), 2.0, 'iron', R)

    # spoil and pit timber at bank
    coal_lumps(R, 24, -22, 0, 7, 9, 8, seed=17)
    for i in range(3):
        bx(20, 20 + i * 0.0, 0.0 + i * 4.0, 30, 4.0, 4.0, 'timber', R,
           rot=(0, 0, 0.05 * i))
    _recentre(R)
    return R


def coal_pile():
    """A stockpile, not a random blob: retained on two sides by timber boards."""
    _calibrate()
    R = C.empty('coal_pile')
    rnd = random.Random(23)
    heap = [(0.0, 33, 27, 8.0, 'coal'), (5.0, 28, 23, 7.5, 'soot'),
            (9.5, 24, 19, 7.0, 'coal'), (13.5, 19, 15, 6.5, 'coal'),
            (17.0, 14, 11, 6.0, 'soot'), (20.0, 9, 8, 5.0, 'coal')]
    for i, (z, w, d, h) in enumerate([(a, b, c, e) for a, b, c, e, _ in heap]):
        m = heap[i][4]
        bx(rnd.uniform(-2.5, 2.5), rnd.uniform(-2.0, 2.0), z, w, d, h, m, R,
           rot=(rnd.uniform(-0.16, 0.16), rnd.uniform(-0.16, 0.16),
                rnd.uniform(0, TAU)))
    for i in range(6):                                               # spillage
        f = rnd.uniform(0.45, 0.8)
        a = rnd.uniform(0, TAU)
        bx(math.cos(a) * rnd.uniform(15, 20), math.sin(a) * rnd.uniform(13, 17),
           0.0, 9 * f, 8 * f, 5 * f, 'coal' if i % 2 else 'soot', R,
           rot=(rnd.uniform(-0.3, 0.3), rnd.uniform(-0.3, 0.3),
                rnd.uniform(0, TAU)))
    bx(-21, 0, 0, 3.2, 34, 9, 'timber', R)                           # retaining
    bx(0, -18, 0, 42, 3.2, 9, 'timber', R)                           # boards
    for x in (-20, -2, 16):
        bx(x, -18, 0, 3.8, 4.4, 11.5, 'timber', R)
    for y in (-15, 2, 15):
        bx(-21, y, 0, 4.4, 3.8, 11.5, 'timber', R)
    _recentre(R)
    return R


def coal_hopper():
    """Standalone bunker: legs, riveted box, V-throat, gate and lever, chute
    down to where a cart stands, with a stair up to the top."""
    _calibrate()
    R = C.empty('coal_hopper')
    hopper(R, 0.0, 0.0, leg_h=27.0, w=34.0, body_h=17.0,
           chute_to=(22.0, 0.0, 6.0))
    bx(0, 0, 0, 44, 44, 1.6, 'stone', R)
    for sx in (-1, 1):                                               # leg pads
        for sy in (-1, 1):
            bx(sx * 12.9, sy * 12.9, 1.6, 7.5, 7.5, 2.4, 'stone_light', R)
    # stair and landing, so a stoker can reach the top
    for sy in (-1, 1):
        beam((-35, sy * 5.5, 1.0), (-21, sy * 5.5, 27.0), 2.6, 4.6, 'timber', R)
        beam((-35, sy * 5.5, 10.0), (-21, sy * 5.5, 36.0), 1.6, 1.6, 'timber', R)
        bx(-35, sy * 5.5, 1.0, 1.6, 1.6, 9.5, 'timber', R)
        bx(-21, sy * 5.5, 26.0, 1.6, 1.6, 10.0, 'timber', R)
    for i in range(7):
        f = (i + 0.5) / 7.0
        bx(-35 + 14 * f, 0, 1.4 + 25.6 * f, 3.0, 11, 1.4, 'timber_light', R)
    coal_lumps(R, 25, 0, 0, 6, 7, 6, seed=31)
    _recentre(R)
    return R


def ore_cart():
    """Tipping cart on a rail stub: flared tub on trunnions, so it tips."""
    _calibrate()
    R = C.empty('ore_cart')
    bx(0, 0, 0, 46, 24, 1.6, 'dirt', R)
    for i in range(4):
        bx(-15 + i * 10, 0, 1.6, 3.6, 19, 2.0, 'timber_light', R)
    for sy in (-1, 1):
        bx(0, sy * 5.4, 3.6, 46, 1.7, 1.5, 'steel', R)
    WZ = 8.3
    for sx in (-1, 1):                             # wheels stay plain discs —
        for sy in (-1, 1):                         # spokes cannot read at this
            ring((sx * 7.0, sy * 5.4, WZ), (0, 1, 0), 3.2, 1.7,   # size anyway
                 'iron_dark', R)
        tube((sx * 7.0, -6.6, WZ), (sx * 7.0, 6.6, WZ), 0.9, 'steel', R, verts=6)
    bx(0, 0, 10.2, 23, 12, 2.4, 'iron', R)                           # chassis
    # tub: panels flared outward at the rim, not a plain box
    bx(0, 0, 12.6, 20, 10, 1.4, 'iron', R)
    FL = rad(15)
    cz = 13.6 + 5.0 * math.cos(FL)
    cyy = 5.0 + 5.0 * math.sin(FL)
    for sy in (-1, 1):
        beam((-10, sy * cyy, cz), (10, sy * cyy, cz), 10.0, 1.6, 'iron', R,
             roll=rad(90) - sy * FL)
    for sx in (-1, 1):
        beam((sx * cyy * 2.0, -5.4, cz), (sx * cyy * 2.0, 5.4, cz), 10.0, 1.6,
             'iron', R, roll=rad(90) + sx * FL)
    rz = 13.6 + 10.0 * math.cos(FL)
    for sy in (-1, 1):
        bx(0, sy * (5.0 + 10.0 * math.sin(FL)), rz, 22.5, 2.0, 1.6,
           'iron_dark', R)
        bx(sy * (10.0 + 10.0 * math.sin(FL)), 0, rz, 2.0, 13.5, 1.6,
           'iron_dark', R)
    for sy in (-1, 1):                                               # trunnions
        bx(0, sy * 7.0, 10.8, 2.6, 2.6, 4.0, 'iron_dark', R)
    tube((0, -8.2, 13.4), (0, 8.2, 13.4), 1.3, 'steel', R, verts=6)
    bx(-12.6, 0, 11.5, 2.4, 9.0, 8.0, 'iron_dark', R)                # push handle
    bx(-14.2, 0, 18.0, 5.0, 9.0, 2.2, 'iron_dark', R)
    coal_lumps(R, 0, 0, 19.5, 4, 6, 4, seed=41)
    _recentre(R)
    return R


def water_pump():
    """A beam pump. Steam cylinder rocks the beam, the beam works a rod down the
    well, the well discharges through a spout into a trough."""
    _calibrate()
    R = C.empty('water_pump')
    bx(2, 0, 0, 66, 30, 1.6, 'stone', R)

    # the well the water comes from
    cy(18, 0, 0, 10.0, 11, 'stone_light', R, verts=10)
    cy(18, 0, 11, 11.2, 2.6, 'stone', R, verts=10)
    cy(18, 0, 10.4, 8.2, 0.8, 'water', R, verts=10)

    # trestle and rocking beam
    for sy in (-1, 1):
        beam((0, sy * 8.5, 1.6), (0, sy * 3.2, 34.0), 4.6, 4.6, 'timber', R)
        beam((-10, sy * 8.5, 1.6), (0, sy * 4.4, 29.0), 3.0, 3.0, 'timber', R)
        beam((10, sy * 8.5, 1.6), (0, sy * 4.4, 29.0), 3.0, 3.0, 'timber', R)
    bx(0, 0, 34.0, 8.0, 22, 3.5, 'timber_light', R)                  # cap piece
    for sy in (-1, 1):
        bx(0, sy * 5.0, 37.5, 5.0, 3.0, 4.0, 'iron_dark', R)         # bearings
    tube((0, -7.0, 41.0), (0, 7.0, 41.0), 1.8, 'steel', R, verts=6)  # pivot
    beam((-21, 0, 35.5), (21, 0, 46.5), 5.6, 6.4, 'timber', R)
    for sy in (-1, 1):                                               # beam straps
        bx(0, sy * 3.6, 38.2, 9.0, 1.4, 5.6, 'iron_dark', R)

    # power end: steam cylinder pushing the beam's west end up
    bx(-21, 0, 1.6, 16, 16, 6.0, 'stone_light', R)
    tube((-21, 0, 7.6), (-21, 0, 24.0), 5.0, 'iron', R, verts=10)
    ring((-21, 0, 24.0), (0, 0, 1), 6.1, 2.4, 'iron_dark', R, verts=10)
    ring((-21, 0, 7.6), (0, 0, 1), 6.1, 2.4, 'iron_dark', R, verts=10)
    tube((-21, 0, 24.0), (-21, 0, 35.6), 1.5, 'steel', R, verts=6)
    bx(-21, 0, 34.4, 4.0, 7.0, 3.0, 'iron_dark', R)

    # pump rod: beam's east end down through the well head into the water
    tube((19.5, 0, 45.6), (19.5, 0, 5.0), 1.6, 'steel', R, verts=6)
    bx(19.5, 0, 44.6, 4.0, 6.0, 3.0, 'iron_dark', R)
    bx(19.5, 0, 11.0, 6.0, 6.0, 3.0, 'iron_dark', R)                 # stuffing box

    # boiler feeding the cylinder
    vertical_boiler(-40, 0, 1.6, 6.8, 22, R, flue=13.0, door_dir=(-1, 0, 0))
    tube((-40, 0, 24.5), (-40, 0, 30.0), 2.0, 'iron', R)
    tube((-40, 0, 30.0), (-27, 0, 30.0), 2.0, 'iron', R)
    handwheel((-33, 0, 33.2), (0, 0, 1), 2.8, R)
    tube((-33, 0, 30.0), (-33, 0, 33.2), 2.0, 'iron', R)
    tube((-27, 0, 30.0), (-27, 0, 22.0), 2.0, 'iron', R)
    tube((-27, 0, 22.0), (-24.5, 0, 22.0), 2.0, 'iron', R)

    # delivery: rising main off the well head, over, and down a spout
    tube((22, 0, 10.0), (30.0, 0, 10.0), 2.6, 'iron', R)
    tube((30.0, 0, 9.0), (30.0, 0, 23.0), 2.6, 'iron', R)
    tube((30.0, 0, 23.0), (36.0, 0, 23.0), 2.6, 'iron', R)
    tube((36.0, 0, 23.5), (36.0, 0, 17.0), 2.6, 'iron', R)
    ring((36.0, 0, 16.6), (0, 0, 1), 3.6, 1.8, 'brass', R)
    pipe_support(30.0, 0, 8.0, R, axis='x', w=9.0)
    bx(36.0, 0, 7.4, 4.2, 4.2, 9.2, 'water', R)                      # falling water
    for dx, dy in ((-3.0, 1.4), (2.6, -1.8), (0.4, 3.0)):            # splash
        bx(36.0 + dx, dy, 7.0, 2.4, 2.4, 1.8, 'water', R,
           rot=(0, 0, 0.4 * dx))
    bx(36, 0, 1.6, 22, 13, 6.0, 'timber', R)                         # trough
    for sy in (-1, 1):
        bx(36, sy * 5.9, 1.6, 22, 1.8, 8.0, 'timber_light', R)
    for sx in (-1, 1):
        bx(36 + sx * 10.0, 0, 1.6, 1.8, 13, 8.0, 'timber_light', R)
    bx(36, 0, 6.4, 20.0, 10.0, 1.4, 'water', R)
    _recentre(R)
    return R


def workshop_small():
    """Half-timbered shed with a forge flue, an open work bay, anvil, stock rack
    and a grindstone — the small end of the trade."""
    _calibrate()
    R = C.empty('workshop_small')
    W, D = 46.0, 32.0
    bx(0, 0, 0, W + 3, D + 3, 8, 'stone_dark', R)
    bx(0, 0, 8, W, D, 22, 'plaster', R)
    for sx in (-1, 1):                                               # framing
        for sy in (-1, 1):
            bx(sx * (W / 2 - 1.8), sy * (D / 2 - 1.8), 8, 4.0, 4.0, 22,
               'timber', R)
    for sy in (-1, 1):
        bx(0, sy * (D / 2 - 0.6), 19, W, 2.0, 2.6, 'timber', R)
        for x in (-11, 11):
            bx(x, sy * (D / 2 - 0.6), 8, 3.2, 2.0, 22, 'timber', R)
    for sx in (-1, 1):
        bx(sx * (W / 2 - 0.6), 0, 19, 2.0, D, 2.6, 'timber', R)
    roof(0, 0, 30, W, D, 16, 'roof_tile', R, overhang=4.0)

    bx(W / 2 - 0.4, 0, 8, 2.6, 19, 21, 'timber', R)                  # doors
    for z in (12, 24):
        bx(W / 2 + 0.4, 0, z, 1.6, 18, 2.4, 'iron_dark', R)
    bx(W / 2 + 0.6, 0, 29, 4.0, 22, 3.0, 'stone_light', R)

    cy(-13, 7, 36, 2.8, 12, 'iron', R, verts=8)                      # forge flue
    cy(-13, 7, 48, 2.8, 5, 'soot', R, verts=8)
    cy(-13, 7, 53, 4.2, 2.2, 'iron_dark', R, verts=8)

    # work yard: a narrow canopy along the wall, the rest open to the sky so
    # the tools under it actually read from above
    bx(0, -26.0, 0, W + 4, 22, 1.4, 'stone', R)
    for sx in (-1, 1):
        bx(sx * 19.0, -27.0, 1.4, 3.6, 3.6, 24, 'timber', R)
        beam((sx * 19.0, -27.0, 24), (sx * 19.0, -17.0, 29), 2.6, 2.6, 'timber',
             R)
    beam((0, -15.5, 30.5), (0, -28.5, 25.0), W + 4, 2.2, 'roof_slate', R)
    bx(0, -27.0, 24.0, W - 4, 2.6, 2.6, 'timber', R)

    # bench and quench trough, under the canopy
    bx(6, -22, 1.4, 22, 7, 9.0, 'timber', R)
    bx(6, -22, 10.4, 24, 8.5, 1.8, 'timber_light', R)
    for i, dx in enumerate((-6, 0, 7)):
        bx(6 + dx, -22, 12.2, 3.0, 3.0, 2.0 + i, 'iron', R)
    bx(-17, -22, 1.4, 10, 7, 5.0, 'timber', R)
    bx(-17, -22, 5.6, 8.6, 5.8, 1.0, 'water', R)

    # anvil on a stump, out in the open
    cy(-9, -32, 1.4, 4.0, 7.0, 'timber', R, verts=8)
    bx(-9, -32, 8.4, 6.0, 5.0, 2.2, 'iron_dark', R)
    bx(-9, -32, 10.6, 3.6, 3.4, 2.2, 'iron_dark', R)
    bx(-9, -32, 12.8, 10.0, 4.6, 2.8, 'iron_dark', R)
    bx(-15.5, -32, 13.2, 4.6, 3.0, 2.0, 'iron_dark', R)
    # grindstone on a trestle — a wheel that actually grinds
    for sy in (-1, 1):
        beam((13, -32 + sy * 3.6, 1.4), (13, -32 + sy * 1.6, 11.0), 2.4, 2.4,
             'timber', R)
    octagon_wheel(13, -32.0, 11.0, 5.0, 2.6, R, segs=10, rim_t=2.4, spokes=3,
                  rim_m='stone_light', spoke_m='stone_light', hub_m='iron')
    tube((13, -35.0, 11.0), (13, -29.0, 11.0), 1.0, 'steel', R, verts=6)
    beam((13, -35.0, 11.0), (13, -36.6, 14.0), 1.2, 1.2, 'iron_dark', R)
    bx(13, -36.6, 14.0, 1.6, 1.6, 3.4, 'timber', R)                  # crank handle
    # bar stock leaning against the shed's east end
    for sy in (-1, 1):
        beam((25 + sy * 4.0, -8.0, 1.4), (25, -8.0, 13.0), 2.4, 2.4, 'timber', R)
    for i in range(4):
        beam((24.0 + i * 0.9, -14.0, 1.4), (24.0 + i * 0.9, 2.0, 14.0), 1.8,
             1.8, 'iron', R)
    coal_lumps(R, -24, -32, 1.4, 5, 5, 5, seed=53)
    _recentre(R)
    return R


# ----------------------------------------------------------------------- build

ASSETS = {
    'foundry_hall': foundry_hall,
    'boiler_large': boiler_large,
    'boiler_small': boiler_small,
    'chimney_stack': chimney_stack,
    'pipe_run_straight': pipe_run_straight,
    'pipe_run_corner': pipe_run_corner,
    'steam_crane': steam_crane,
    'mine_headframe': mine_headframe,
    'coal_pile': coal_pile,
    'coal_hopper': coal_hopper,
    'ore_cart': ore_cart,
    'water_pump': water_pump,
    'workshop_small': workshop_small,
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


def build_all(out_dir, preview_dir=None, only=None):
    _calibrate()
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
                             px=460, angle=32, azimuth=40)
            C.preview_render(root, os.path.join(preview_dir, name + '-b.png'),
                             px=380, angle=26, azimuth=-145)
        report.append((name, w, d, h, tris))
        print(f'{name:20s} {w:7.1f} x {d:6.1f} x {h:6.1f}   {tris:5d} tris')
    total = sum(r[4] for r in report)
    print(f'{"TOTAL":20s} {total:41d} tris')
    return report


if __name__ == '__main__':
    build_all('/home/user/steamward/assets/models/industrial', '/tmp/prev-industrial')
