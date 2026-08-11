"""STEAMWARD units kit — the miniature soldiers.

Everything here is a little person about 19 units (1.9 m) tall, built from
chunky masses so the SILHOUETTE carries the read at RTS distance. A player
never sees a face; they see "the one with the slab shield", "the one with the
pole above his head", "the one with a barrel on his back". So the equipment is
deliberately oversized relative to the man, the way a wargame miniature
exaggerates a spear, and each unit owns one strong outline feature:

    levy         soft cap, felling axe shouldered up beside his head, buckler
    spearman     kettle hat brim, a 31-unit pole standing well above the head
    shieldman    a slab of shield — by far the widest outline
    bowman       tall smooth D-curve of a longbow, arrows over the shoulder
    pressurebow  copper reservoir on the back, hose over the shoulder, a short
                 angular recurve bow with a piston carriage on the stock
    rider        horse, sabre curving up over the shoulder
    boilerlancer horse, back boiler with a stack, lance straight out in front
    hero         tallest, long coat, plume, big back banner

Animation contract (the runtime has no skeleton — see src/unitView.js)
---------------------------------------------------------------------
Each moving piece is its own object whose ORIGIN is its pivot, and the runtime
rotates it about that origin:

    leg_l / leg_r    origin at the hip
    arm_l / arm_r    origin at the shoulder
    weapon           origin at the grip, parented under the arm that holds it
    torso            origin at the waist; head, helmet, pack, shield hang off it
    hleg_fl/fr/bl/br origin at the horse's shoulder or hip

Geometry is authored in world coordinates and parented with the parent-inverse
trick from common.box(), so a piece can be written where it visibly belongs
while still ending up in the right part's frame. Limb geometry always overlaps
its socket a little, so a swinging leg buries itself in the pelvis instead of
opening a gap.

The bow units hold the bow in the LEFT hand: the runtime drives the attack with
arm_r, which then reads as the drawing hand pulling back, not as a man beating
someone with a bow.

Nothing mechanical is ornament. On the pressurebow the reservoir feeds a hose,
the hose feeds a piston carriage, the carriage drags the string, the gauge
reads the reservoir and the brace puts the recoil into the shoulder. On the
boilerlancer the boiler burns coal, vents through a stack, and its steam line
runs to the ram cylinder on the lance.
"""

import math
import os

import bpy
import mathutils

import common as c
from common import (box, cyl, empty, clear_scene, export_glb, preview_render,
                    bounds, mat)

R = math.radians
V = mathutils.Vector

# ---------------------------------------------------------------- skeleton
HIP_Z = 8.4          # hip pivot / waist height
SHO_Z = 14.8         # shoulder pivot
SHO_Y = 3.40         # shoulder half-width
HEAD_Z = 16.2        # underside of the head
STANCE = 1.95        # half the distance between the feet


# ---------------------------------------------------------------- helpers

def upd():
    bpy.context.view_layer.update()


def _mk(ob, material, parent, name=None):
    if name:
        ob.name = name
    ob.data.materials.append(mat(material))
    for p in ob.data.polygons:
        p.use_smooth = False
    if parent is not None:
        upd()
        ob.parent = parent
        ob.matrix_parent_inverse = parent.matrix_world.inverted()
    return ob


def part(name, parent, x, y, z):
    """An animated pivot. Authored in world space; the parent inverse means the
    number written here is the number the runtime rotates about."""
    e = empty(name)
    if parent is not None:
        upd()
        e.parent = parent
        e.matrix_parent_inverse = parent.matrix_world.inverted()
    e.location = (x, y, z)
    upd()
    return e


def tool(name, holder):
    """A weapon pivot, built in ITS OWN frame. Bodies are authored in world
    space, but a weapon is easier to think about around its grip (blade up the
    +Z, point down the +X), so it is assembled at the origin and then `place`d
    on the fist — the children ride along with it."""
    return part(name, holder, 0, 0, 0)


def place(e, x, y, z, rot=None):
    e.location = (x, y, z)
    if rot:
        e.rotation_euler = rot
    upd()
    return e


def bx(parent, x0, x1, y0, y1, z0, z1, material, **kw):
    """A box by its two opposite corners — how you think about a body part."""
    return box((x0 + x1) * 0.5, (y0 + y1) * 0.5, min(z0, z1),
               abs(x1 - x0), abs(y1 - y0), abs(z1 - z0), material, parent, **kw)


def seg(parent, p0, p1, w, t, material, name=None):
    """A bar running from p0 to p1: limbs, struts, bow limbs, tails.
    w is its thickness in the plane of the bend, t across it."""
    a, b = V(p0), V(p1)
    d = b - a
    L = max(d.length, 1e-4)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(a + b) / 2.0)
    ob = bpy.context.object
    ob.rotation_euler = d.to_track_quat('Z', 'Y').to_euler()
    ob.scale = (w, t, L)
    return _mk(ob, material, parent, name)


def rod(parent, p0, p1, r, material, verts=6, name=None):
    """A pipe/hose/axle run between two points."""
    a, b = V(p0), V(p1)
    d = b - a
    L = max(d.length, 1e-4)
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=L,
                                        location=(a + b) / 2.0)
    ob = bpy.context.object
    ob.rotation_euler = d.to_track_quat('Z', 'Y').to_euler()
    return _mk(ob, material, parent, name)


def hose(parent, pts, r, material='iron_dark', collar='brass', verts=6):
    """A flexible line with a coupling at each end and a band at each bend —
    it must be obvious that it runs FROM something TO something."""
    for a, b in zip(pts, pts[1:]):
        rod(parent, a, b, r, material, verts=verts)
    for i, p in enumerate(pts):
        rr = r * (1.5 if i in (0, len(pts) - 1) else 1.25)
        hh = r * (1.3 if i in (0, len(pts) - 1) else 0.8)
        d = (V(pts[min(i + 1, len(pts) - 1)]) - V(pts[max(i - 1, 0)]))
        if d.length < 1e-4:
            d = V((0, 0, 1))
        d.normalize()
        rod(parent, V(p) - d * hh, V(p) + d * hh, rr,
            collar if i in (0, len(pts) - 1) else material, verts=verts)


def disc(parent, x, y, z, r, th, material, axis='y', verts=10, name=None):
    """A plate seen face on: shield boards, gauges, wheels."""
    rot = {'y': (R(90), 0, 0), 'x': (0, R(90), 0), 'z': (0, 0, 0)}[axis]
    off = {'y': (0, -th / 2.0, 0), 'x': (-th / 2.0, 0, 0), 'z': (0, 0, -th / 2.0)}[axis]
    return cyl(x + off[0], y + off[1], z + off[2], r, th, material, parent,
               verts=verts, rot=rot, name=name)


def join_as(objs, name):
    """Weld pieces into one named object — the runtime looks the banner up by
    name, so it has to be a single mesh."""
    objs = [o for o in objs if o]
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    objs[0].name = name
    bpy.ops.object.select_all(action='DESELECT')
    return objs[0]


def tri_count(root):
    n = 0
    stack = [root]
    while stack:
        ob = stack.pop()
        stack.extend(ob.children)
        if ob.type == 'MESH':
            n += sum(len(p.vertices) - 2 for p in ob.data.polygons)
    return n


# ---------------------------------------------------------------- body parts

def legs(root, thigh='leather', shin='leather', boot='leather', bulk=1.0,
         stance=STANCE, hip=HIP_Z, greave=None, cuff=None):
    """leg_l / leg_r, pivoting at the hip. The thigh runs a little above the
    pivot so a swung leg digs into the pelvis rather than tearing free."""
    out = []
    for side, nm in ((+1, 'leg_l'), (-1, 'leg_r')):
        p = part(nm, root, 0, side * stance, hip)
        y = side * stance
        b = bulk
        bx(p, -1.15 * b, 1.15 * b, y - 1.15 * b, y + 1.15 * b, 4.1, hip + 0.9, thigh)
        bx(p, -0.92 * b, 0.92 * b, y - 0.95 * b, y + 0.95 * b, 1.5, 4.5, shin)
        if greave:
            bx(p, -1.02 * b, 1.05 * b, y - 1.05 * b, y + 1.05 * b, 1.7, 4.6, greave)
        if cuff:
            bx(p, -1.25 * b, 1.30 * b, y - 1.22 * b, y + 1.22 * b, 3.7, 4.9, cuff)
        bx(p, -1.25, 2.10, y - 1.18, y + 1.18, 0.0, 1.8, boot)   # boot, toe forward
        out.append(p)
    return out


def torso_block(root, jerkin='leather', chest=None, belt='leather',
                bulk=1.0, waist=HIP_Z, sho=SHO_Z, skirt=None, collar=None):
    """The torso pivot plus the trunk built on it: hips, waist, chest.
    Deliberately not a single box — the taper from a narrow waist to a broad
    chest is most of what makes these read as people."""
    t = part('torso', root, 0, 0, waist)
    b = bulk
    chest = chest or jerkin
    bx(t, -1.95 * b, 1.95 * b, -2.80 * b, 2.80 * b, waist - 0.6, waist + 1.6, jerkin)
    bx(t, -2.05 * b, 2.05 * b, -2.92 * b, 2.92 * b, waist + 0.9, waist + 1.9, belt)
    bx(t, -1.85 * b, 1.90 * b, -2.85 * b, 2.85 * b, waist + 1.9, waist + 4.3, jerkin)
    bx(t, -2.05 * b, 2.15 * b, -3.45 * b, 3.45 * b, waist + 4.3, sho + 0.7, chest)
    if skirt:
        for i, (y0, y1) in enumerate(((-3.0, -1.0), (-1.1, 1.1), (1.0, 3.0))):
            bx(t, -2.05 * b, 2.15 * b, y0 * b, y1 * b,
               waist - 2.6 - (i % 2) * 0.5, waist + 1.0, skirt)
    if collar:
        bx(t, -1.5 * b, 1.6 * b, -2.1 * b, 2.1 * b, sho + 0.5, sho + 1.6, collar)
    return t


def head_block(t, base=HEAD_Z, skin='skin', hair='timber', jaw=None, top=None,
               crown=True):
    """Neck, skull, brow and a nose nub — the nose is what tells a player which
    way a 20 pixel tall man is looking. `crown` off when a helmet covers it."""
    top = top or (base + 3.2)
    bx(t, -0.85, 0.85, -1.0, 1.0, base - 1.1, base + 0.3, skin)        # neck
    bx(t, -1.50, 1.55, -1.55, 1.55, base, top, skin)                   # skull
    bx(t, 1.20, 1.95, -0.50, 0.50, base + 1.0, base + 1.8, skin)       # nose
    if crown:
        bx(t, -1.62, 0.30, -1.65, 1.65, top - 0.9, top + 0.45, hair)   # hair
    bx(t, -1.70, -1.20, -1.5, 1.5, base + 0.2, top - 0.6, hair)
    if jaw:
        bx(t, 0.4, 1.7, -1.2, 1.2, base - 0.2, base + 0.9, jaw)
    return top


def arm(t, side, name, hand, upper='cloth', lower='leather', hand_mat='leather',
        pauldron=None, pad=None, bulk=1.0, sho=SHO_Z, sho_y=SHO_Y, bracer=None,
        l1=3.6, l2=3.4):
    """One arm as its own pivot at the shoulder. `hand` is where the fist ends
    up in world space and the elbow is solved for, kicking backward and out —
    an arm reaching forward has to bend the right way or the whole figure reads
    as a doll."""
    y = side * sho_y
    a = part(name, t, 0, y, sho)
    S, H = V((0.0, y, sho)), V(hand)
    u = H - S
    d = max(u.length, 1e-3)
    if d > (l1 + l2) * 0.985:                      # arm straight: pull the hand in
        H = S + u * ((l1 + l2) * 0.985 / d)
        d = (l1 + l2) * 0.985
    u = (H - S) / d
    aa = (l1 * l1 - l2 * l2 + d * d) / (2 * d)
    hh = math.sqrt(max(l1 * l1 - aa * aa, 0.0))
    r = V((-1.0, side * 0.30, -0.20))
    n = (r - u * r.dot(u))
    n = n.normalized() if n.length > 1e-4 else V((0, 0, -1))
    E = S + u * aa + n * hh
    w = 1.85 * bulk
    seg(a, (0.0, y, sho + 0.6), E, w, w, upper)
    seg(a, E, H, w * 0.92, w * 0.92, lower)
    if bracer:
        seg(a, E.lerp(H, 0.34), E.lerp(H, 0.72), w * 1.06, w * 1.06, bracer)
    bx(a, H.x - 0.85, H.x + 0.85, H.y - 0.85, H.y + 0.85, H.z - 0.85, H.z + 0.85,
       hand_mat)
    if pauldron:                                   # cap over the shoulder, flaring out
        lo, hi = y - 1.30, y + 1.30
        lo, hi = (lo, hi + 0.75) if side > 0 else (lo - 0.75, hi)
        bx(a, -1.45, 1.45, lo, hi, sho - 0.35, sho + 1.25, pauldron)
        lo2, hi2 = (y - 1.05, y + 1.55) if side > 0 else (y - 1.55, y + 1.05)
        bx(a, -1.20, 1.20, lo2, hi2, sho - 1.75, sho - 0.30, pauldron)
    if pad:
        bx(a, -1.40, 1.40, y - 1.35, y + 1.35, sho - 0.4, sho + 1.3, pad)
    return a


# ---------------------------------------------------------------- headgear

def helm_cap(t, z, material='leather'):
    """Soft cap: a low dome pulled down over the crown, with a stubby peak.
    No metal anywhere — that absence is the read."""
    bx(t, -1.66, 1.62, -1.72, 1.72, z - 1.15, z + 0.55, material)
    bx(t, -1.25, 1.20, -1.30, 1.30, z + 0.55, z + 1.20, material)
    bx(t, 1.55, 2.55, -1.10, 1.10, z - 1.10, z - 0.55, 'leather')      # peak
    return z + 1.20


def helm_kettle(t, z):
    """Kettle hat: shallow steel bowl on a broad brim. The brim is the point —
    it is the one helmet you can identify from directly above."""
    disc(t, 0, 0, z - 1.30, 2.95, 0.50, 'steel', axis='z', verts=10)
    bx(t, -1.66, 1.62, -1.72, 1.72, z - 1.10, z + 0.45, 'steel')
    bx(t, -1.20, 1.15, -1.25, 1.25, z + 0.45, z + 1.10, 'steel')
    bx(t, -0.38, 0.38, -0.38, 0.38, z + 1.10, z + 1.60, 'iron')        # finial
    return z + 1.60


def helm_nasal(t, z):
    """Conical helm with a nasal bar and a mail neck curtain — the heavy's
    head, blunt and closed up."""
    bx(t, -1.80, 1.75, -1.85, 1.85, z - 1.35, z + 0.35, 'steel')
    bx(t, -1.40, 1.35, -1.45, 1.45, z + 0.35, z + 1.20, 'steel')
    bx(t, -0.60, 0.60, -0.60, 0.60, z + 1.20, z + 1.75, 'steel')       # apex
    bx(t, 1.70, 2.20, -0.48, 0.48, z - 3.30, z - 0.55, 'iron')         # nasal bar
    bx(t, -2.20, -1.45, -1.80, 1.80, z - 3.60, z - 0.30, 'iron_dark')  # neck curtain
    for s in (-1, 1):                                                   # cheeks
        bx(t, -1.95, 1.55, s * 1.30, s * 1.95, z - 2.60, z - 1.10, 'iron_dark')
    return z + 1.75


def helm_sallet(t, z):
    """Compact engine-crew helmet: low steel shell, a vision slit, a tail over
    the neck and ear plates. Reads as armour, not as a knight."""
    bx(t, -1.85, 1.75, -1.82, 1.82, z - 1.45, z + 0.30, 'steel')
    bx(t, -1.40, 1.30, -1.45, 1.45, z + 0.30, z + 0.95, 'steel')
    bx(t, -2.60, -1.70, -1.45, 1.45, z - 2.20, z - 0.15, 'steel')      # neck tail
    bx(t, 1.55, 2.05, -1.50, 1.50, z - 2.30, z - 1.45, 'iron_dark')    # vision slit
    bx(t, 1.60, 2.10, -1.60, 1.60, z - 1.45, z - 0.45, 'steel')        # brow
    for s in (-1, 1):
        bx(t, -1.0, 1.0, s * 1.60, s * 2.15, z - 2.60, z - 1.20, 'iron')  # ear plate
    return z + 0.95


def helm_crested(t, z):
    """The commander: a raised steel skull, a brass comb fore-and-aft, and a
    cloth plume trailing off the back so the outline is unmistakable."""
    bx(t, -1.85, 1.80, -1.88, 1.88, z - 1.35, z + 0.45, 'steel')
    bx(t, -1.45, 1.40, -1.50, 1.50, z + 0.45, z + 1.20, 'steel')
    bx(t, 1.60, 2.35, -1.45, 1.45, z - 1.55, z - 0.45, 'steel')        # brow band
    bx(t, -1.75, 1.75, -0.50, 0.50, z + 0.95, z + 3.10, 'brass')       # comb
    bx(t, -2.35, -1.65, -0.50, 0.50, z + 0.55, z + 2.60, 'brass')
    for i in range(5):                                                  # plume
        bx(t, -2.45 - i * 1.15, -1.35 - i * 1.15, -0.72, 0.72,
           z + 2.55 - i * 0.95, z + 3.25 - i * 0.72, 'cloth')
    return z + 3.10


# ---------------------------------------------------------------- gear

def round_shield(a, x, y, z, r=3.3, face='timber_light', rim='iron', boss='steel'):
    """Buckler / small round board strapped to the forearm."""
    disc(a, x, y, z, r, 0.75, face, axis='y', verts=12)
    disc(a, x, y + 0.30, z, r * 1.04, 0.35, rim, axis='y', verts=12)
    disc(a, x, y + 0.72, z, r * 0.34, 0.85, boss, axis='y', verts=8)
    for k in range(3):                                                  # planking
        ang = k * math.pi / 3.0
        seg(a, (x + math.cos(ang) * r * 0.92, y + 0.5, z + math.sin(ang) * r * 0.92),
            (x - math.cos(ang) * r * 0.92, y + 0.5, z - math.sin(ang) * r * 0.92),
            0.35, 0.25, rim)


def kite_shield(a, x, y, z, w=6.6, h=9.0, face='cloth', rim='timber',
                boss='iron', tilt=R(13)):
    """Shield board hung off the left arm: a broad top that tapers to a point,
    faced in faction cloth so a formation reads as a wall of colour."""
    parts = []
    parts.append(bx(a, x - 0.55, x + 0.55, y - w * 0.30, y + w * 0.70,
                    z, z + h * 0.62, face, rot=(0, 0, tilt)))
    parts.append(bx(a, x - 0.52, x + 0.52, y - w * 0.24, y + w * 0.58,
                    z - h * 0.20, z, face, rot=(0, 0, tilt)))
    parts.append(bx(a, x - 0.50, x + 0.50, y - w * 0.13, y + w * 0.36,
                    z - h * 0.36, z - h * 0.20, face, rot=(0, 0, tilt)))
    bx(a, x + 0.45, x + 0.85, y - w * 0.30, y + w * 0.70,
       z + h * 0.52, z + h * 0.62, rim, rot=(0, 0, tilt))               # top band
    bx(a, x + 0.45, x + 0.80, y - w * 0.06, y + w * 0.10,
       z - h * 0.34, z + h * 0.60, rim, rot=(0, 0, tilt))               # spine
    disc(a, x + 0.9, y + w * 0.20, z + h * 0.30, 1.15, 0.6, boss, axis='x', verts=8)
    return parts


def slab_shield(a, x, y, z, w=9.4, h=13.4, face='cloth'):
    """The shieldman's board — a genuine slab. Wide, long, banded, with a
    rolled top edge and a point at the bottom."""
    tilt = R(10)
    bx(a, x - 0.70, x + 0.70, y - w * 0.30, y + w * 0.70, z, z + h * 0.70,
       face, rot=(0, 0, tilt))
    bx(a, x - 0.66, x + 0.66, y - w * 0.22, y + w * 0.55,
       z - h * 0.16, z, face, rot=(0, 0, tilt))
    bx(a, x - 0.62, x + 0.62, y - w * 0.10, y + w * 0.30,
       z - h * 0.30, z - h * 0.16, face, rot=(0, 0, tilt))
    bx(a, x + 0.60, x + 1.05, y - w * 0.31, y + w * 0.71,
       z + h * 0.60, z + h * 0.70, 'iron', rot=(0, 0, tilt))            # top roll
    for zz in (0.10, 0.42):                                             # cross bands
        bx(a, x + 0.58, x + 0.95, y - w * 0.28, y + w * 0.66,
           z + h * zz, z + h * (zz + 0.07), 'iron', rot=(0, 0, tilt))
    bx(a, x + 0.58, x + 0.98, y + w * 0.14, y + w * 0.26,
       z - h * 0.28, z + h * 0.68, 'iron', rot=(0, 0, tilt))            # spine
    disc(a, x + 1.15, y + w * 0.20, z + h * 0.30, 1.35, 0.7, 'steel', axis='x', verts=8)


def quiver(t, x, y, z, n=5, tube='leather', shaft='timber_light',
           fletch='canvas', pitch=R(16)):
    """Arrows in a back quiver — the fletching over the shoulder is the whole
    point, it is what says 'archer' from behind and above."""
    bx(t, x - 1.15, x + 1.15, y - 1.15, y + 1.15, z, z + 5.2, tube,
       rot=(pitch, 0, 0))
    bx(t, x - 1.25, x + 1.25, y - 1.25, y + 1.25, z + 3.4, z + 4.1, 'iron_dark',
       rot=(pitch, 0, 0))
    for i in range(n):
        ox = (i % 3 - 1) * 0.62
        oy = (i // 3) * 0.7 - 0.35
        top = z + 8.4 + (i % 2) * 0.7
        seg(t, (x + ox, y + oy, z + 3.6), (x + ox * 1.6, y + oy * 1.4 + 0.9, top),
            0.34, 0.34, shaft)
        bx(t, x + ox * 1.5 - 0.16, x + ox * 1.5 + 0.16,
           y + oy * 1.35 + 0.5, y + oy * 1.35 + 1.3, top - 1.5, top, fletch)


def scabbard(t, x, y, z, length=7.0, pitch=R(-24), body='leather'):
    """A sword has to live somewhere when it is not in the hand."""
    top = (x, y, z)
    end = (x + length * math.sin(pitch), y - 0.4, z - length * math.cos(pitch))
    seg(t, top, end, 1.0, 0.7, body)
    seg(t, top, V(top).lerp(V(end), 0.18), 1.15, 0.85, 'iron')
    seg(t, V(top).lerp(V(end), 0.88), end, 1.10, 0.80, 'iron')


def sword(w, length=6.4, blade='steel', guard='iron', grip='leather',
          pommel='brass', wide=1.05):
    """A straight sword standing up out of the fist."""
    bx(w, -0.42, 0.42, -0.42, 0.42, -1.5, 1.1, grip)
    bx(w, -0.55, 0.55, -0.60, 0.60, -2.0, -1.5, pommel)
    bx(w, -0.40, 0.40, -1.65, 1.65, 1.1, 1.75, guard)
    bx(w, -0.30, 0.30, -wide / 2, wide / 2, 1.75, 1.75 + length, blade)
    bx(w, -0.24, 0.24, -wide * 0.34, wide * 0.34, 1.75 + length, 2.6 + length, blade)


def bow_curve(parent, x, z0, z1, y, bulge, material, back=None, segments=7,
              thick=1.45, tip=0.62, width=1.05):
    """A bow at rest: the limbs bow forward away from the string, thick at the
    riser and tapering to the nocks. Returns the two tip points so the string
    can be strung between them."""
    pts = []
    for i in range(segments + 1):
        u = i / segments
        s = math.sin(math.pi * u) ** 0.75
        pts.append((x + bulge * s, y, z0 + (z1 - z0) * u))
    for i in range(segments):
        u = (i + 0.5) / segments
        w = tip + (thick - tip) * math.sin(math.pi * u) ** 0.6
        seg(parent, pts[i], pts[i + 1], w, width, material)
        if back:
            a, b = V(pts[i]), V(pts[i + 1])
            n = V((0, 0, 1)).cross(b - a).normalized() if (b - a).length else V((1, 0, 0))
            seg(parent, a + n * (w * 0.5 + 0.18), b + n * (w * 0.5 + 0.18),
                0.32, width * 0.92, back)
    return pts[0], pts[-1]


# ---------------------------------------------------------------- foot units

def levy():
    """Farmhand pressed into the line: no armour worth the name, a padded
    jacket, a hatchet off the woodpile and a little board shield."""
    root = empty('levy')
    legs(root, thigh='canvas', shin='canvas', boot='leather', bulk=0.94)
    t = torso_block(root, jerkin='canvas', chest='canvas', belt='leather', bulk=0.94)

    # quilted jacket: vertical padding ribs, and a faction hood over the chest
    for yy in (-1.9, -0.65, 0.65, 1.9):
        bx(t, 1.75, 2.20, yy - 0.42, yy + 0.42, HIP_Z + 2.0, SHO_Z + 0.5, 'canvas')
    bx(t, -2.25, 2.30, -3.05, 3.05, SHO_Z - 1.6, SHO_Z + 1.5, 'cloth')      # hood/cape
    bx(t, -2.35, -1.85, -2.6, 2.6, HIP_Z + 3.0, SHO_Z + 0.6, 'cloth')
    bx(t, -1.9, 2.1, -3.0, -2.2, HIP_Z + 0.2, HIP_Z + 1.4, 'leather')       # satchel strap
    bx(t, -2.9, -1.7, -2.9, -1.1, HIP_Z - 1.9, HIP_Z + 0.9, 'canvas')       # bread bag

    hz = head_block(t, base=HEAD_Z - 0.5, jaw='timber', crown=False)
    helm_cap(t, hz)

    al = arm(t, +1, 'arm_l', (2.35, 3.25, 10.45), upper='canvas', lower='canvas',
             bulk=0.92)
    ar = arm(t, -1, 'arm_r', (2.85, -4.05, 13.15), upper='canvas', lower='canvas',
             bulk=0.92)
    round_shield(al, 2.95, 4.45, 11.0, r=3.35)

    # A woodsman's felling axe, carried head-up beside the head: short haft,
    # broad bit, so his outline is a man with a heavy tool, not a soldier.
    w = tool('weapon', ar)
    bx(w, -0.48, 0.48, -0.46, 0.46, -2.8, 5.6, 'timber')                    # haft
    bx(w, -0.64, 0.64, -0.60, 0.60, -3.3, -2.6, 'iron_dark')                # butt
    bx(w, -0.90, 1.10, -0.62, 0.62, 4.6, 7.2, 'iron')                       # eye
    bx(w, 0.90, 2.45, -0.48, 0.48, 4.0, 7.8, 'steel')                       # bit
    bx(w, 2.35, 3.55, -0.40, 0.40, 4.6, 7.2, 'steel')                       # edge
    bx(w, -1.25, -0.70, -0.42, 0.42, 5.1, 6.9, 'steel')                     # poll
    place(w, 3.10, -4.35, 13.35, rot=(R(22), R(-14), 0))
    return root


def spearman():
    """Line infantry: kettle hat, mail-and-jack body, a shield, and a spear
    that stands half again as tall as he does."""
    root = empty('spearman')
    legs(root, thigh='canvas', shin='leather', boot='leather')
    t = torso_block(root, jerkin='canvas', chest='iron', belt='leather',
                    skirt='iron')

    bx(t, 1.90, 2.50, -2.7, 2.7, HIP_Z + 2.4, SHO_Z + 0.5, 'cloth')         # tabard
    bx(t, -2.40, -1.85, -2.5, 2.5, HIP_Z + 2.6, SHO_Z + 0.5, 'cloth')
    bx(t, 2.05, 2.45, -3.3, 3.3, SHO_Z - 1.0, SHO_Z + 0.6, 'iron')          # mail yoke
    bx(t, -0.6, 2.4, -3.5, -2.9, HIP_Z + 3.4, SHO_Z - 0.2, 'leather')       # baldric
    scabbard(t, -1.4, 3.0, HIP_Z + 1.2, length=6.2)

    hz = head_block(t, jaw='iron_dark', crown=False)
    helm_kettle(t, hz)

    al = arm(t, +1, 'arm_l', (2.40, 3.20, 10.5), upper='iron', lower='leather',
             pad='iron')
    ar = arm(t, -1, 'arm_r', (2.55, -3.25, 10.6), upper='iron', lower='leather',
             pad='iron')
    kite_shield(al, 3.05, 3.55, 9.4, w=6.8, h=9.6)

    w = tool('weapon', ar)
    bx(w, -0.44, 0.44, -0.44, 0.44, -7.4, 15.6, 'timber')                   # shaft
    bx(w, -0.58, 0.58, -0.58, 0.58, -7.9, -7.0, 'iron_dark')                # butt spike
    bx(w, -0.60, 0.60, -0.60, 0.60, 3.2, 4.0, 'iron')                       # grip band
    bx(w, -0.62, 0.62, -0.62, 0.62, 15.2, 16.3, 'iron')                     # socket
    bx(w, -0.34, 0.34, -0.90, 0.90, 16.3, 19.4, 'steel')                    # leaf head
    bx(w, -0.28, 0.28, -0.42, 0.42, 19.4, 20.6, 'steel')
    place(w, 2.95, -3.35, 10.6)
    return root


def shieldman():
    """The heavy: a slab of shield, plate over mail, a nasal helm and a short
    sword. Nothing about him is tall — everything about him is WIDE."""
    root = empty('shieldman')
    legs(root, thigh='iron', shin='iron', boot='leather', bulk=1.1,
         greave='steel', stance=2.15)
    t = torso_block(root, jerkin='iron', chest='steel', belt='leather',
                    bulk=1.12, skirt='iron')

    bx(t, 2.25, 2.60, -2.2, 2.2, HIP_Z + 5.0, SHO_Z + 0.5, 'cloth')         # tabard
    bx(t, -2.55, -2.20, -2.2, 2.2, HIP_Z + 4.8, SHO_Z + 0.5, 'cloth')
    bx(t, 2.15, 2.55, -3.6, 3.6, SHO_Z - 0.6, SHO_Z + 0.9, 'steel')         # breast band
    bx(t, 2.20, 2.50, -1.0, 1.0, HIP_Z + 5.0, SHO_Z - 0.6, 'steel')         # placard rib
    scabbard(t, -1.2, 3.4, HIP_Z + 1.4, length=6.6)

    hz = head_block(t, jaw='iron_dark', crown=False)
    helm_nasal(t, hz)

    al = arm(t, +1, 'arm_l', (2.55, 3.35, 10.6), upper='iron', lower='iron',
             pauldron='steel', bulk=1.1, sho_y=3.7)
    ar = arm(t, -1, 'arm_r', (2.55, -3.45, 10.2), upper='iron', lower='iron',
             pauldron='steel', bulk=1.1, sho_y=3.7)
    slab_shield(al, 3.25, 3.75, 8.2, w=9.8, h=14.2)

    w = tool('weapon', ar)
    sword(w, length=5.6, wide=1.35)
    place(w, 2.95, -3.55, 10.3)
    return root


def bowman():
    """Longbow: no shield, a soft cap, and a stave taller than the archer with
    arrows fanning over his shoulder."""
    root = empty('bowman')
    legs(root, thigh='canvas', shin='leather', boot='leather', bulk=0.96)
    t = torso_block(root, jerkin='leather', chest='leather', belt='leather',
                    bulk=0.96)

    bx(t, 1.85, 2.35, -2.6, 2.6, HIP_Z + 1.8, SHO_Z + 0.5, 'cloth')         # jack front
    bx(t, -2.35, -1.85, -2.4, 2.4, HIP_Z + 2.0, SHO_Z + 0.4, 'cloth')
    bx(t, -1.0, 2.3, -3.4, -2.6, HIP_Z + 3.2, SHO_Z + 0.2, 'leather')       # quiver strap
    bx(t, -0.6, 1.6, 2.6, 3.4, HIP_Z + 0.4, HIP_Z + 1.6, 'leather')
    quiver(t, -2.55, -2.15, HIP_Z + 2.6, n=5)

    hz = head_block(t, base=HEAD_Z - 0.2, jaw='timber', crown=False)
    helm_cap(t, hz, 'cloth')                          # the archers' coloured cap

    al = arm(t, +1, 'arm_l', (5.05, 3.15, 11.9), upper='canvas', lower='leather',
             bracer='leather', bulk=0.94)
    ar = arm(t, -1, 'arm_r', (2.35, -3.15, 10.4), upper='canvas', lower='leather',
             bulk=0.94)

    w = tool('weapon', al)                                                  # bow hand
    lo, hi = bow_curve(w, 0.0, -10.6, 12.6, 0.0, 3.1, 'timber_light',
                       segments=7, thick=1.55, tip=0.62, width=1.15)
    seg(w, lo, hi, 0.22, 0.22, 'canvas')                                    # string
    for p in (lo, hi):                                                      # horn nocks
        bx(w, p[0] - 0.42, p[0] + 0.42, -0.42, 0.42, p[2] - 0.45, p[2] + 0.45, 'plaster')
    bx(w, -0.9, 1.5, -0.62, 0.62, -1.1, 1.3, 'leather')                     # grip wrap
    place(w, 5.35, 3.45, 12.0)
    return root


def pressurebow():
    """THE signature unit. A crossbow-strong bow a man could never draw by
    hand, drawn instead by a piston:

        reservoir on the back  ->  outlet valve  ->  armoured hose
        -> piston carriage on the stock  ->  claw that drags the string
        -> sear releases, the string snaps, exhaust vents at the valve

    The gauge reads the reservoir. The brace strut carries the recoil into the
    shoulder plate. The right hand carries the next bolt. Not one part of it is
    decoration, and the limbs and string keep it a BOW.
    """
    root = empty('pressurebow')
    legs(root, thigh='leather', shin='iron', boot='leather', bulk=1.02,
         greave='steel')
    t = torso_block(root, jerkin='iron', chest='steel', belt='leather',
                    bulk=1.04, skirt='iron')

    # --- compact reinforced armour: breastplate, faulds, faction tabard
    bx(t, 2.10, 2.55, -3.2, 3.2, SHO_Z - 1.2, SHO_Z + 0.7, 'steel')
    bx(t, 2.05, 2.45, -3.0, 3.0, HIP_Z + 3.6, SHO_Z - 1.2, 'steel')
    bx(t, 1.95, 2.35, -2.2, 2.2, HIP_Z + 1.9, HIP_Z + 3.6, 'iron')
    bx(t, 2.15, 2.60, -2.0, 2.0, HIP_Z - 2.4, HIP_Z + 2.0, 'cloth')         # tabard
    bx(t, -2.45, -2.05, -2.0, 2.0, HIP_Z - 2.2, HIP_Z + 2.2, 'cloth')
    for s in (-1, 1):                                                        # harness straps
        seg(t, (2.45, s * 1.4, SHO_Z + 0.5), (-2.4, s * 2.2, SHO_Z + 0.2),
            1.45, 0.6, 'leather')

    # --- THE RESERVOIR. A copper pressure vessel slung high on the back so it
    # stands proud of the shoulders: this drum IS the unit's silhouette.
    RX, RZ, RR = -4.45, 8.9, 2.35
    cyl(RX, 0, RZ, RR, 8.8, 'copper', t, verts=10)
    for zz in (RZ + 0.9, RZ + 4.2, RZ + 7.8):
        cyl(RX, 0, zz, RR + 0.16, 0.70, 'iron_dark', t, verts=10)           # rivet bands
    cyl(RX, 0, RZ + 8.8, RR - 0.30, 1.05, 'iron', t, verts=10)              # dome
    cyl(RX, 0, RZ - 0.75, RR + 0.20, 0.80, 'iron_dark', t, verts=10)        # foot ring
    seg(t, (RX + 1.3, -2.2, RZ + 8.2), (-1.9, -2.4, RZ + 6.4), 0.8, 0.7, 'iron')
    seg(t, (RX + 1.3, 2.2, RZ + 8.2), (-1.9, 2.4, RZ + 6.4), 0.8, 0.7, 'iron')
    # pressure gauge on the right shoulder of the drum, where a man can read it
    disc(t, RX + 1.2, -2.45, RZ + 6.2, 1.15, 0.60, 'brass', axis='y', verts=8)
    disc(t, RX + 1.2, -2.90, RZ + 6.2, 0.85, 0.32, 'iron_dark', axis='y', verts=8)
    bx(t, RX + 0.95, RX + 1.45, -3.10, -2.88, RZ + 6.1, RZ + 6.9, 'brass')  # needle
    rod(t, (RX + 1.2, -2.2, RZ + 6.2), (RX + 1.2, -1.0, RZ + 4.6), 0.34, 'brass')
    # outlet and release valve on the crown: the hose leaves here, and the
    # exhaust stub is where the shot dumps its pressure
    cyl(RX, 1.55, RZ + 9.2, 0.78, 1.5, 'brass', t, verts=6)
    seg(t, (RX, 1.55, RZ + 10.5), (RX + 1.6, 3.0, RZ + 10.2), 0.45, 0.45, 'brass')
    rod(t, (RX, 1.55, RZ + 9.9), (RX - 1.9, 1.55, RZ + 10.6), 0.36, 'iron_dark')
    cyl(RX, -1.5, RZ + 9.2, 0.6, 0.9, 'iron', t, verts=6)

    hz = head_block(t, jaw='iron_dark', crown=False)
    helm_sallet(t, hz)

    # --- arms. The left is thrust out straight holding the bow; the right is
    # the loading hand, carrying the next bolt up from the hip case.
    GRIP = V((5.75, 4.70, 11.60))
    al = arm(t, +1, 'arm_l', GRIP, upper='iron', lower='steel',
             pauldron='steel', bulk=1.02, sho_y=3.55)
    ar = arm(t, -1, 'arm_r', (2.55, -3.35, 9.9), upper='iron', lower='steel',
             pauldron='steel', bulk=1.02, sho_y=3.55)
    seg(ar, (1.6, -3.55, 9.4), (4.8, -3.10, 10.6), 0.45, 0.45, 'timber_light')
    bx(ar, 4.6, 5.8, -3.28, -2.84, 10.45, 10.9, 'steel')                    # bolt head
    bx(t, -1.6, 0.9, -3.75, -2.60, HIP_Z - 2.2, HIP_Z + 0.8, 'leather')     # bolt case
    for i in range(3):                                                       # spare bolts
        bx(t, -1.3, 1.6, -3.55 + i * 0.62, -3.25 + i * 0.62,
           HIP_Z + 0.6, HIP_Z + 0.95, 'timber_light')

    # --- the bow. Local +X is downrange. Deep riser, short heavy RECURVED
    # limbs — the outline is angular where the longbow's is a smooth arc, and
    # the string still runs nock to nock, because it is still a bow.
    w = tool('weapon', al)
    bx(w, -0.55, 1.85, -0.80, 0.80, -3.2, 3.6, 'steel')                     # riser
    bx(w, -1.05, 0.65, -1.00, 1.00, -1.7, 1.9, 'iron')                      # grip block
    bx(w, 1.60, 2.30, -0.62, 0.62, -2.4, 2.8, 'brass')                      # sight rib
    LIMB = [(1.60, 2.80), (2.60, 4.60), (1.60, 6.60), (-0.90, 8.00), (-0.35, 9.20)]
    tips = []
    for sgn in (1, -1):
        pts = [(x, 0.0, sgn * z) for x, z in LIMB]
        for i in range(len(pts) - 1):
            u = i / (len(pts) - 2.0)
            wdt = 2.00 - 1.15 * u
            lat = 1.60 - 0.55 * u
            seg(w, pts[i], pts[i + 1], wdt, lat, 'timber_light')
            if i < 2:                                    # steel backing, working limb only
                a, b = V(pts[i]), V(pts[i + 1])
                nrm = V((0, 1, 0)).cross(b - a).normalized()
                seg(w, a + nrm * (wdt * 0.5 + 0.18), b + nrm * (wdt * 0.5 + 0.18),
                    0.40, lat * 0.95, 'steel')
            else:                                        # horn nock at the tip
                bx(w, pts[i + 1][0] - 0.5, pts[i + 1][0] + 0.5, -0.5, 0.5,
                   pts[i + 1][2] - 0.45, pts[i + 1][2] + 0.45, 'iron')
        bx(w, -0.55, 2.30, -1.25, 1.25, sgn * 2.55, sgn * 3.95, 'iron')     # root band
        tips.append(pts[-1])
    seg(w, tips[1], tips[0], 0.32, 0.32, 'canvas')                          # string
    sx = tips[0][0]

    # draw carriage: a pressure cylinder anchored back at the brace, its rod
    # running FORWARD to a claw that holds the string. Admit pressure, the rod
    # retracts and drags the string down the rail; the sear holds it there
    # until the trigger drops it and the limbs do the rest.
    bx(w, -5.10, 0.35, -0.42, 0.42, 1.35, 1.95, 'iron')                     # slide rails
    bx(w, -5.10, 0.35, -0.42, 0.42, -1.95, -1.35, 'iron')
    for cy in (-1.40, 1.40):                             # twin rams, one each side
        rod(w, (-4.05, cy, 0.05), (-1.60, cy, 0.05), 1.05, 'copper', verts=8)
        rod(w, (-4.60, cy, 0.05), (-3.90, cy, 0.05), 1.25, 'brass', verts=8)  # end cap
        rod(w, (-1.80, cy, 0.05), (-1.15, cy, 0.05), 1.18, 'iron_dark', verts=8)
        rod(w, (-1.35, cy, 0.05), (sx - 0.25, cy, 0.05), 0.34, 'steel', verts=6)
        rod(w, (-4.25, cy, 1.15), (-1.80, cy, 1.15), 0.20, 'iron_dark', verts=6)
    bx(w, sx - 0.35, sx + 0.15, -1.65, 1.65, -1.15, 1.15, 'steel')          # claw yoke
    for s in (-1, 1):                                                        # claw fingers
        bx(w, sx - 0.30, sx + 0.75, s * 0.55, s * 1.00, -0.55, 0.55, 'steel')
    bx(w, -3.10, -1.70, -0.60, 0.60, -2.75, -1.45, 'iron_dark')             # sear housing
    seg(w, (-2.40, 0, -2.70), (-1.15, 0, -4.05), 0.55, 0.85, 'brass')       # trigger bar
    rod(w, (-4.30, -1.40, 0.05), (-4.30, 1.40, 0.05), 0.42, 'brass', verts=6)  # manifold
    rod(w, (-4.30, 0, 0.05), (-4.30, 1.95, 0.05), 0.52, 'brass', verts=6)   # inlet port
    place(w, GRIP.x, GRIP.y, GRIP.z, rot=(R(-12), 0, 0))                    # archer's cant

    # --- plumbing and brace, tying machine to man. Both hang off the torso so
    # they stay put while the bow arm moves. The hose loops WIDE of the
    # shoulder on purpose: it is half the unit's read at distance.
    inlet = GRIP + V((-4.30, 1.95, 0.05))
    hose(t, [(RX + 0.9, 1.55, RZ + 9.6), (-2.1, 4.6, RZ + 9.0),
             (1.4, 5.7, RZ + 6.6), (inlet.x - 1.7, inlet.y + 1.0, inlet.z - 0.4),
             (inlet.x, inlet.y, inlet.z)], 0.52, material='leather')
    brace_end = GRIP + V((-5.05, 0, 1.60))
    seg(t, (-0.45, 3.10, SHO_Z + 1.0), (brace_end.x, brace_end.y, brace_end.z),
        0.95, 0.95, 'steel')
    bx(t, -1.55, 0.65, 2.15, 4.10, SHO_Z + 0.6, SHO_Z + 1.75, 'steel')      # brace plate
    return root


def hero():
    """The commander. Taller and straighter than the line, a long coat, a
    crested helm, a sash and a banner on his back — read him across the field."""
    root = empty('hero')
    HH = 9.3                                     # a taller man: hips sit higher
    legs(root, thigh='iron_dark', shin='iron_dark', boot='leather', hip=HH,
         greave='steel', stance=1.85)
    t = torso_block(root, jerkin='cloth', chest='steel', belt='leather',
                    waist=HH, sho=SHO_Z + 1.5, bulk=1.02, collar='cloth')

    SH = SHO_Z + 1.5
    # long coat, flaring and split at the front
    for s in (-1, 1):
        bx(t, -2.0, 2.25, s * 0.55, s * 2.95, HH - 4.0, HH + 1.6, 'cloth',
           rot=(0, 0, s * R(-4)))
        bx(t, -2.1, 1.9, s * 1.5, s * 3.35, HH - 5.2, HH - 3.6, 'cloth')
    bx(t, -2.35, -1.85, -3.0, 3.0, HH - 5.4, HH + 2.2, 'cloth')             # back skirt
    bx(t, 2.15, 2.55, -3.3, 3.3, SH - 1.4, SH + 0.6, 'steel')               # cuirass
    bx(t, 2.05, 2.45, -2.9, 2.9, HH + 3.4, SH - 1.4, 'steel')
    seg(t, (2.55, -3.3, SH + 0.2), (2.35, 2.9, HH + 2.6), 1.55, 0.55, 'leather')
    disc(t, 2.85, 2.2, HH + 3.4, 0.9, 0.5, 'brass', axis='x', verts=8)      # sash clasp
    bx(t, -2.1, 2.3, -3.7, 3.7, SH + 0.3, SH + 1.4, 'leather')              # mantle

    hz = head_block(t, base=HEAD_Z + 1.7, jaw='timber', crown=False)
    helm_crested(t, hz)

    al = arm(t, +1, 'arm_l', (2.35, 3.35, 11.6), upper='cloth', lower='steel',
             pauldron='steel', sho=SH, sho_y=3.5)
    ar = arm(t, -1, 'arm_r', (2.75, -3.35, 12.0), upper='cloth', lower='steel',
             pauldron='steel', sho=SH, sho_y=3.5)
    scabbard(t, -1.2, 3.5, HH + 1.6, length=7.4)

    # back banner: a short staff socketed into the backplate, cross bar, cloth
    staff_x, staff_y = -3.30, -1.6
    seg(t, (staff_x - 1.1, staff_y, HH + 1.2), (staff_x + 0.6, staff_y, HH + 19.6),
        0.75, 0.75, 'timber')
    bx(t, staff_x - 1.9, staff_x + 0.5, staff_y - 1.0, staff_y + 1.0,
       HH + 0.8, HH + 2.8, 'iron')                                          # socket
    bx(t, staff_x - 0.2, staff_x + 1.1, staff_y - 0.5, staff_y + 7.3,
       HH + 18.2, HH + 19.1, 'iron')                                        # cross bar
    bx(t, staff_x + 0.15, staff_x + 0.85, staff_y - 0.4, staff_y + 0.4,
       HH + 19.5, HH + 21.0, 'brass')                                       # finial
    strips = []
    for i in range(6):
        y0 = staff_y + 0.15 + i * 1.18
        off = math.sin(i * 0.95) * 0.7
        strips.append(bx(t, staff_x + 0.30 + off, staff_x + 0.85 + off,
                         y0, y0 + 1.08, HH + 7.4 - (i % 2) * 1.1, HH + 18.2, 'cloth'))
    join_as(strips, 'banner_cloth')
    for s in strips[:1]:
        s.parent = t
        upd()
        s.matrix_parent_inverse = t.matrix_world.inverted()

    w = tool('weapon', ar)
    sword(w, length=8.2, wide=1.15, guard='brass', pommel='brass')
    place(w, 3.15, -3.45, 12.1)
    return root


# ---------------------------------------------------------------- cavalry

def horse(root, heavy=False, cloth=True):
    """Chunky horse masses: barrel, chest, croup, neck, head, tail and four
    legs on their own pivots. Withers at 15, ears about 20."""
    hide = 'iron_dark' if heavy else 'timber'
    hide2 = 'iron' if heavy else 'timber_light'
    b = 1.12 if heavy else 1.0

    bx(root, -7.6, 6.4, -3.2 * b, 3.2 * b, 8.9, 14.9, hide)                 # barrel
    bx(root, 3.4, 7.6, -3.4 * b, 3.4 * b, 9.3, 14.6, hide)                  # chest
    bx(root, -9.8, -6.2, -3.1 * b, 3.1 * b, 9.6, 15.2, hide)                # croup
    bx(root, -7.8, 4.2, -2.7 * b, 2.7 * b, 8.2, 9.4, hide)                  # belly
    seg(root, (6.2, 0, 12.8), (10.4, 0, 18.4), 5.2, 4.0 * b, hide)          # neck
    seg(root, (6.6, 0, 13.6), (10.9, 0, 19.0), 1.3, 4.2 * b, hide2)         # crest
    seg(root, (9.9, 0, 19.0), (12.3, 0, 17.0), 3.6, 3.0, hide)              # skull
    bx(root, 11.9, 14.6, -1.20, 1.20, 15.5, 17.5, hide2)                    # muzzle
    bx(root, 14.2, 14.9, -0.95, 0.95, 15.7, 17.1, 'iron_dark')              # nose
    bx(root, 10.6, 12.4, -1.45, 1.45, 16.6, 18.4, hide)                     # cheek
    for s in (-1, 1):                                                        # ears
        bx(root, 9.7, 10.5, s * 0.55, s * 1.35, 19.4, 21.0, hide2,
           rot=(s * R(-13), 0, 0))
    for i in range(4):                                                       # mane
        seg(root, (7.0 + i * 0.95, 0, 14.0 + i * 1.30), (6.5 + i * 0.95, 0, 15.6 + i * 1.30),
            1.0, 1.7, 'timber')
    bx(root, 9.4, 10.6, -0.8, 0.8, 19.0, 20.2, 'timber')                    # forelock
    seg(root, (-9.5, 0, 15.0), (-11.9, 0, 8.2), 2.6, 2.6, 'timber')         # tail
    seg(root, (-11.9, 0, 8.4), (-12.4, 0, 4.8), 1.8, 1.9, 'timber')
    # bridle: a cheek strap and a rein that actually reaches the rider's hand
    seg(root, (12.6, -1.25, 16.9), (10.7, -1.55, 18.7), 0.45, 0.4, 'leather')
    seg(root, (12.6, 1.25, 16.9), (10.7, 1.55, 18.7), 0.45, 0.4, 'leather')
    bx(root, 12.2, 13.0, -1.35, 1.35, 16.3, 17.0, 'leather')

    for nm, dx, dy, front in (('hleg_fl', 5.1, 2.45, True), ('hleg_fr', 5.1, -2.45, True),
                              ('hleg_bl', -6.3, 2.55, False), ('hleg_br', -6.3, -2.55, False)):
        p = part(nm, root, dx, dy * b, 9.7)
        y = dy * b
        if front:
            seg(p, (dx + 0.3, y, 10.6), (dx - 0.1, y, 5.6), 2.5 * b, 2.3 * b, hide)
            seg(p, (dx - 0.1, y, 5.9), (dx + 0.15, y, 1.5), 1.5 * b, 1.5 * b, hide2)
            bx(p, dx - 0.85, dx + 1.05, y - 1.0, y + 1.0, 0.0, 1.6, 'iron_dark')
        else:
            seg(p, (dx - 0.2, y, 10.9), (dx - 1.5, y, 6.0), 3.2 * b, 2.6 * b, hide)
            seg(p, (dx - 1.5, y, 6.3), (dx + 0.35, y, 1.5), 1.5 * b, 1.5 * b, hide2)
            bx(p, dx - 0.65, dx + 1.25, y - 1.0, y + 1.0, 0.0, 1.6, 'iron_dark')

    # saddle and faction cloth
    if cloth:
        for s in (-1, 1):
            bx(root, -7.0, 4.6, s * 3.15 * b, s * 3.75 * b,
               7.4 if heavy else 8.6, 14.4, 'cloth')
        bx(root, -6.0, 3.4, -3.2 * b, 3.2 * b, 14.6, 15.2, 'cloth')
    bx(root, -3.6, 2.6, -3.0, 3.0, 15.0, 16.0, 'leather')                   # saddle
    bx(root, -4.6, -3.2, -2.5, 2.5, 15.2, 17.4, 'leather')                  # cantle
    bx(root, 2.2, 3.2, -1.6, 1.6, 15.4, 17.0, 'leather')                    # pommel
    for s in (-1, 1):                                                        # stirrup
        seg(root, (0.4, s * 3.1, 15.6), (0.9, s * 3.9, 11.2), 0.7, 0.45, 'leather')
        bx(root, 0.35, 1.45, s * 3.9 - 0.45, s * 3.9 + 0.45, 10.3, 11.3, 'iron')
    return root


def _rider_body(root, seat=15.9, heavy=False, jerk=None):
    """A man sitting a horse: the legs are static (the horse's legs do the
    moving), thighs forward, boots in the stirrups."""
    t = part('torso', root, 0, 0, seat + 0.4)
    jerk = jerk or ('iron' if heavy else 'leather')
    ch = 'steel' if heavy else 'leather'
    sho = seat + 6.6
    bx(t, -1.95, 1.95, -2.75, 2.75, seat - 0.5, seat + 1.7, jerk)
    bx(t, -2.05, 2.05, -2.9, 2.9, seat + 1.0, seat + 2.0, 'leather')
    bx(t, -1.85, 1.9, -2.85, 2.85, seat + 2.0, seat + 4.4, jerk)
    bx(t, -2.05, 2.15, -3.45, 3.45, seat + 4.4, sho + 0.7, ch)
    for s in (-1, 1):                                                        # legs
        seg(t, (0.2, s * 2.9, seat - 0.4), (4.3, s * 3.55, seat - 3.3), 2.1, 2.1, jerk)
        seg(t, (4.3, s * 3.55, seat - 3.1), (3.3, s * 3.9, seat - 6.4), 1.7, 1.7, jerk)
        bx(t, 2.2, 4.6, s * 3.9 - 1.05, s * 3.9 + 1.05, seat - 7.4, seat - 6.0, 'leather')
    return t, sho


def rider():
    """Light horse: a scout with a sabre curving up over his shoulder."""
    root = empty('rider')
    horse(root, heavy=False)
    t, sho = _rider_body(root, seat=15.9, heavy=False, jerk='canvas')

    bx(t, 1.95, 2.45, -2.5, 2.5, 19.6, sho + 0.6, 'cloth')                  # jack
    bx(t, -2.35, -1.90, -2.3, 2.3, 19.4, sho + 0.5, 'cloth')
    seg(t, (2.5, -3.2, sho + 0.4), (2.3, 2.8, 18.4), 1.4, 0.5, 'leather')   # baldric
    bx(t, -3.1, -1.6, -2.4, 2.4, 17.2, 19.0, 'leather')                     # cloak roll

    hz = head_block(t, base=sho + 1.4, jaw='timber', crown=False)
    bx(t, -1.62, 1.60, -1.70, 1.70, hz - 0.3, hz + 0.95, 'steel')           # open helm
    bx(t, -1.25, 1.20, -1.30, 1.30, hz + 0.95, hz + 1.5, 'steel')
    bx(t, 1.45, 2.45, -1.15, 1.15, hz - 0.45, hz + 0.1, 'steel')            # brow peak
    bx(t, -2.3, -1.5, -1.55, 1.55, hz - 1.5, hz + 0.5, 'iron_dark')         # nape

    al = arm(t, +1, 'arm_l', (3.6, 2.6, 19.5), upper='leather', lower='leather',
             sho=sho, sho_y=3.4)
    ar = arm(t, -1, 'arm_r', (3.0, -3.4, 19.8), upper='leather', lower='leather',
             sho=sho, sho_y=3.4)
    for s in (1,):                                                           # reins
        seg(al, (3.9, 2.4, 19.3), (8.0, 1.9, 18.4), 0.3, 0.28, 'leather')
        seg(al, (8.0, 1.9, 18.4), (12.6, 1.35, 17.2), 0.3, 0.28, 'leather')

    w = tool('weapon', ar)
    bx(w, -0.4, 0.4, -0.4, 0.4, -1.5, 1.0, 'leather')                       # grip
    bx(w, -0.6, 0.6, -0.6, 0.6, -2.0, -1.5, 'brass')
    bx(w, -0.35, 1.35, -0.55, 0.55, 1.0, 1.6, 'brass')                      # knuckle bow
    seg(w, (0.9, 0, 1.3), (0.35, 0, 3.4), 0.35, 0.9, 'brass')
    prev = (0.0, 0.0, 1.6)                                                   # curved blade
    for i in range(4):
        nxt = (prev[0] - 0.55 - i * 0.42, 0.0, prev[2] + 2.4)
        seg(w, prev, nxt, 0.32, 1.15 - i * 0.14, 'steel')
        prev = nxt
    seg(w, prev, (prev[0] - 1.5, 0, prev[2] + 1.5), 0.28, 0.7, 'steel')
    place(w, 3.4, -3.5, 20.0)
    return root


def boilerlancer():
    """Heavy horse. A back boiler burns coal, vents through a stack, and its
    steam line runs to a ram cylinder on the lance: at the moment of impact the
    piston drives the lance head forward instead of the rider's shoulder taking
    it. Everything on him is that one idea."""
    root = empty('boilerlancer')
    horse(root, heavy=True)
    # barding: peytral across the chest, flank plates, chanfron on the head
    bx(root, 6.9, 7.9, -3.5, 3.5, 9.6, 14.6, 'steel')
    bx(root, 4.0, 7.4, -3.9, -3.3, 9.8, 14.4, 'iron')
    bx(root, 4.0, 7.4, 3.3, 3.9, 9.8, 14.4, 'iron')
    for s in (-1, 1):
        bx(root, -6.4, 1.6, s * 3.65, s * 4.15, 10.2, 14.2, 'iron')
    bx(root, 10.9, 13.9, -1.35, 1.35, 16.2, 18.6, 'steel', rot=(0, R(38), 0))
    bx(root, 11.2, 12.0, -0.45, 0.45, 18.4, 20.4, 'brass')                  # chanfron spike
    bx(root, -9.9, -6.0, -3.3, 3.3, 15.0, 15.8, 'iron')                     # crupper

    t, sho = _rider_body(root, seat=16.1, heavy=True)
    bx(t, 2.15, 2.60, -3.3, 3.3, sho - 1.4, sho + 0.6, 'steel')             # cuirass
    bx(t, 2.05, 2.50, -2.9, 2.9, 19.8, sho - 1.4, 'steel')
    bx(t, 1.95, 2.40, -2.5, 2.5, 18.4, sho - 1.4, 'cloth')                  # surcoat
    bx(t, -2.45, -2.00, -2.4, 2.4, 18.2, sho - 1.2, 'cloth')
    bx(t, -2.0, 2.2, -3.7, 3.7, sho + 0.4, sho + 1.5, 'steel')              # gorget

    hz = head_block(t, base=sho + 1.5, jaw='iron_dark', crown=False)
    bx(t, -1.85, 1.80, -1.85, 1.85, hz - 0.6, hz + 0.95, 'steel')           # closed helm
    bx(t, -1.45, 1.40, -1.45, 1.45, hz + 0.95, hz + 1.6, 'steel')
    bx(t, 1.55, 2.25, -1.55, 1.55, hz - 1.6, hz - 0.6, 'iron_dark')         # visor slit
    bx(t, 1.60, 2.15, -1.65, 1.65, hz - 0.6, hz + 0.5, 'steel')
    bx(t, -1.6, 1.6, -0.4, 0.4, hz + 1.5, hz + 2.6, 'brass')                # comb

    # --- back boiler: firebox with a coal glow, riveted drum, stack, valve
    bx(t, -4.9, -2.5, -2.0, 2.0, 18.0, 20.0, 'iron_dark')                   # firebox
    bx(t, -5.05, -4.65, -1.2, 1.2, 18.4, 19.5, 'ember')                     # fire door
    bx(t, -5.05, -4.55, -2.05, -1.15, 18.2, 19.9, 'iron')                   # door hinge
    cyl(-3.7, 0, 20.0, 2.45, 6.2, 'copper', t, verts=10)
    for zz in (20.6, 23.2, 25.6):
        cyl(-3.7, 0, zz, 2.60, 0.62, 'iron_dark', t, verts=10)              # rivet bands
    cyl(-3.7, 0, 26.2, 2.15, 0.85, 'iron', t, verts=10)                     # dome
    rod(t, (-3.7, -1.4, 26.6), (-5.1, -1.4, 32.2), 0.78, 'iron', verts=8)   # stack
    rod(t, (-4.95, -1.4, 31.7), (-5.25, -1.4, 33.1), 1.15, 'iron_dark', verts=8)
    cyl(-3.5, 1.5, 27.0, 0.72, 1.5, 'brass', t, verts=6)                    # safety valve
    seg(t, (-3.5, 1.5, 28.3), (-2.0, 2.7, 28.0), 0.42, 0.42, 'brass')
    disc(t, -3.6, -2.65, 24.4, 1.05, 0.55, 'brass', axis='y', verts=8)      # gauge
    disc(t, -3.6, -3.05, 24.4, 0.78, 0.30, 'iron_dark', axis='y', verts=8)
    for s in (-1, 1):                                                        # harness
        seg(t, (2.4, s * 1.3, sho + 0.4), (-2.0, s * 2.0, sho + 0.2), 1.3, 0.5, 'leather')

    al = arm(t, +1, 'arm_l', (3.9, 2.7, 20.1), upper='iron_dark', lower='steel',
             pauldron='steel', sho=sho, sho_y=3.6, bulk=1.06)
    ar = arm(t, -1, 'arm_r', (2.9, -3.7, 20.0), upper='iron_dark', lower='steel',
             pauldron='steel', sho=sho, sho_y=3.6, bulk=1.06)
    seg(al, (4.2, 2.5, 19.9), (8.4, 1.9, 18.6), 0.32, 0.3, 'leather')       # reins
    seg(al, (8.4, 1.9, 18.6), (12.8, 1.35, 17.3), 0.32, 0.3, 'leather')

    # --- the lance, couched level under the right arm
    w = tool('weapon', ar)
    bx(w, -8.6, 16.4, -0.62, 0.62, -0.62, 0.62, 'timber')                   # shaft
    bx(w, -9.2, -8.4, -0.85, 0.85, -0.85, 0.85, 'iron_dark')                # butt
    bx(w, -1.4, -0.6, -0.85, 0.85, -0.85, 0.85, 'iron')                     # grip band
    disc(w, 1.4, 0, 0, 2.15, 1.5, 'steel', axis='x', verts=8)               # vamplate
    disc(w, 2.9, 0, 0, 1.25, 0.7, 'iron', axis='x', verts=8)
    bx(w, 16.2, 19.6, -0.42, 0.42, -0.42, 0.42, 'steel')                    # head
    bx(w, 19.6, 21.4, -0.22, 0.22, -0.22, 0.22, 'steel')
    # ram cylinder: piston along the shaft, rod forward to a collar
    rod(w, (-7.4, -0.1, 1.55), (-2.2, -0.1, 1.55), 1.15, 'iron', verts=8)
    rod(w, (-7.9, -0.1, 1.55), (-7.2, -0.1, 1.55), 1.35, 'brass', verts=8)
    rod(w, (-2.4, -0.1, 1.55), (-1.7, -0.1, 1.55), 1.3, 'iron_dark', verts=8)
    rod(w, (-2.2, -0.1, 1.55), (2.4, -0.1, 1.55), 0.36, 'steel', verts=6)   # piston rod
    bx(w, 2.2, 3.1, -0.95, 0.95, -0.95, 1.95, 'steel')                      # thrust collar
    for xx in (-6.2, -3.4):                                                  # cylinder straps
        bx(w, xx - 0.3, xx + 0.3, -1.0, 1.0, -1.0, 2.3, 'iron_dark')
    rod(w, (-7.7, -0.1, 2.1), (-7.7, -1.4, 2.1), 0.42, 'brass', verts=6)    # inlet
    place(w, 3.3, -3.9, 20.1)

    # steam line from the boiler valve down to that inlet
    grip = V((3.3, -3.9, 20.1))
    inlet = grip + V((-7.7, -1.4, 2.1))
    hose(t, [(-3.3, 2.1, 27.6), (-1.5, 3.6, 25.6), (0.6, -1.2, 23.4),
             (inlet.x - 1.2, inlet.y + 1.0, inlet.z + 1.2),
             (inlet.x, inlet.y, inlet.z)], 0.4, material='copper')
    return root


# ---------------------------------------------------------------- build

ASSETS = {
    'levy': levy,
    'spearman': spearman,
    'shieldman': shieldman,
    'bowman': bowman,
    'pressurebow': pressurebow,
    'rider': rider,
    'boilerlancer': boilerlancer,
    'hero': hero,
}

SHEET_ORDER = ['levy', 'spearman', 'shieldman', 'bowman', 'pressurebow',
               'rider', 'boilerlancer', 'hero']


# ---------------------------------------------------------------- inspection

def shot(path, px=430, span=42.0, elev=27.0, azim=45.0, centre_z=11.0,
         silhouette=False):
    """Render whatever is in the scene with a fixed camera, so every unit can
    be compared at the SAME scale side by side. azim 45 looks at the unit's
    front-right, 135 at its front-left (it faces +X)."""
    import mathutils as mu
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 16 if silhouette else 28
    scene.cycles.use_denoising = False
    scene.render.resolution_x = px
    scene.render.resolution_y = px
    scene.render.image_settings.file_format = 'PNG'
    try:
        scene.view_settings.view_transform = 'Standard'
    except (AttributeError, TypeError):
        pass

    world = bpy.data.worlds.get('World') or bpy.data.worlds.new('World')
    scene.world = world
    world.use_nodes = True
    bgc = (1, 1, 1, 1) if silhouette else (0.34, 0.38, 0.42, 1)
    world.node_tree.nodes['Background'].inputs['Color'].default_value = bgc
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = (
        3.2 if silhouette else 0.95)

    for ob in list(bpy.data.objects):
        if ob.type in ('CAMERA', 'LIGHT'):
            bpy.data.objects.remove(ob, do_unlink=True)
    if not silhouette:
        bpy.ops.object.light_add(type='SUN')            # key, over the front-left
        sun = bpy.context.object
        sun.data.energy = 3.0
        sun.data.angle = 0.25
        sun.rotation_euler = (R(48), 0, R(-125))
        bpy.ops.object.light_add(type='SUN')            # fill, from the camera side
        fill = bpy.context.object
        fill.data.energy = 1.1
        fill.data.angle = 0.6
        fill.rotation_euler = (R(62), 0, R(35))

    bpy.ops.object.camera_add()
    cam = bpy.context.object
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = span
    el, az = R(elev), R(azim)
    dist = span * 3
    cam.location = (dist * math.cos(el) * math.sin(az),
                    -dist * math.cos(el) * math.cos(az),
                    dist * math.sin(el) + centre_z)
    look = mu.Vector((0, 0, centre_z)) - mu.Vector(cam.location)
    cam.rotation_euler = look.to_track_quat('-Z', 'Y').to_euler()
    scene.camera = cam

    bpy.ops.mesh.primitive_plane_add(size=span * 5, location=(0, 0, -0.06))
    ground = bpy.context.object
    if silhouette:
        m = bpy.data.materials.get('__white') or bpy.data.materials.new('__white')
        m.use_nodes = True
        n = m.node_tree.nodes['Principled BSDF']
        n.inputs['Base Color'].default_value = (1, 1, 1, 1)
        ground.data.materials.append(m)
    else:
        ground.data.materials.append(mat('grass'))

    os.makedirs(os.path.dirname(path), exist_ok=True)
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(ground, do_unlink=True)


def blacken():
    """Flatten every material to matte black — the silhouette test."""
    for m in bpy.data.materials:
        if not m.use_nodes or 'Principled BSDF' not in m.node_tree.nodes:
            continue
        if m.name == '__white':
            continue
        n = m.node_tree.nodes['Principled BSDF']
        n.inputs['Base Color'].default_value = (0, 0, 0, 1)
        if 'Metallic' in n.inputs:
            n.inputs['Metallic'].default_value = 0.0
        if 'Emission Strength' in n.inputs:
            n.inputs['Emission Strength'].default_value = 0.0


def montage(paths, out, cols=4):
    from PIL import Image
    ims = [Image.open(p) for p in paths]
    w, h = ims[0].size
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new('RGB', (w * cols, h * rows), (20, 20, 20))
    for i, im in enumerate(ims):
        sheet.paste(im, ((i % cols) * w, (i // cols) * h))
    sheet.save(out)
    return out


def sheets(preview_dir, tag='', **kw):
    """One render per unit with an identical camera, montaged — the only
    honest way to judge relative size and silhouette."""
    silo = kw.pop('silhouette', False)
    paths = []
    for name in SHEET_ORDER:
        clear_scene()
        ASSETS[name]()
        upd()
        if silo:
            blacken()
        p = os.path.join(preview_dir, f'cell{tag}-{name}.png')
        shot(p, silhouette=silo, **kw)
        paths.append(p)
    return montage(paths, os.path.join(preview_dir, f'sheet{tag}.png'))


def pose_test(preview_dir, name='spearman', axis='X', angle=32.0):
    """Rotate every animated part about its own origin and render it, to prove
    the pivots are where the runtime thinks they are."""
    clear_scene()
    root = ASSETS[name]()
    upd()
    swing = {'leg_l': 1, 'leg_r': -1, 'arm_l': -1, 'arm_r': 1, 'weapon': 0.6,
             'hleg_fl': 1, 'hleg_fr': -1, 'hleg_bl': -1, 'hleg_br': 1}
    stack = [root]
    while stack:
        ob = stack.pop()
        stack.extend(ob.children)
        if ob.name in swing:
            a = R(angle) * swing[ob.name]
            ob.rotation_euler = ((a, 0, 0) if axis == 'X' else (0, a, 0))
    upd()
    p = os.path.join(preview_dir, f'pose-{name}-{axis}.png')
    shot(p, span=44)
    return p


def build_all(out_dir, preview_dir=None):
    report = {}
    for name, fn in ASSETS.items():
        clear_scene()
        root = fn()
        upd()
        report[name] = (bounds(root), tri_count(root))
        export_glb(root, os.path.join(out_dir, f'{name}.glb'))
        if preview_dir:
            preview_render(root, os.path.join(preview_dir, f'{name}.png'),
                           px=420, azimuth=45)
    for k, v in report.items():
        print(f'{k:14s} size={v[0]}  tris={v[1]}')
    return report
