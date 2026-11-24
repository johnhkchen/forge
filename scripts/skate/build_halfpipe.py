"""Builds the halfpipe's geometry from its numbers, in a background Blender: sets/halfpipe/set.glb.

    Blender -b --factory-startup -P scripts/skate/build_halfpipe.py -- [set]

A skateboard rides this surface, so it is built from the same arithmetic the
motion uses (scripts/skate/pipe.py, from the set's "ramp"), not modelled by
eye: every point of the riding surface is `Pipe.at(s)` for some s.

What is built, in the set's own axes (x across, y up, z along):

    the riding surface   plywood sheets, 1.22 m by 2.44 m, laid like bricks;
                         each a slightly different tan, so the sheets read
                         without a texture
    the coping           a steel tube along each lip
    the decks            a platform behind each lip, with a railing at the back
    the ends and backs   the cut-away side of the ramp at each end (the shape
                         the side camera sees), with the frame's ribs showing,
                         and a plain back wall behind each deck

Colors are flat, painted on the corners, with no textures: the look of the
other places in the world. Never touches an open Blender.
"""

import math
import os
import random
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts", "sets"))
import standing  # noqa: E402
from pipe import Pipe  # noqa: E402

SHEET = (1.22, 2.44)   # a sheet of plywood: along the surface, along the ramp
STEP = 0.17            # the curve is built in pieces this long (metres along the surface)
PLY = (0.62, 0.43, 0.25)
SIDE = (0.47, 0.32, 0.19)
RIB = (0.33, 0.22, 0.13)
STEEL = (0.74, 0.76, 0.79)
RAIL = (0.30, 0.31, 0.34)
RAIL_M = 1.1


def to_blender(p):
    return (p[0], -p[2], p[1])


class Shell:
    """Faces and their colors, gathered and then made into one object."""

    def __init__(self):
        self.points, self.faces, self.colors = [], [], []

    def poly(self, corners, color, face=None):
        """One flat face. `face` is the way it must look (x, y, z in the set's axes): the corners are turned round if they say otherwise."""
        corners = list(corners)
        if face is not None:
            a, b, c = corners[0], corners[1], corners[2]
            u, v = [b[i] - a[i] for i in range(3)], [c[i] - b[i] for i in range(3)]
            n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            if n[0] * face[0] + n[1] * face[1] + n[2] * face[2] < 0:
                corners.reverse()
        n = len(self.points)
        self.points += [to_blender(p) for p in corners]
        self.faces.append(tuple(range(n, n + len(corners))))
        self.colors.append(color)

    def quad(self, a, b, c, d, color, face=None):
        self.poly([a, b, c, d], color, face)

    def box(self, lo, hi, color):
        x0, y0, z0 = [min(lo[i], hi[i]) for i in range(3)]
        x1, y1, z1 = [max(lo[i], hi[i]) for i in range(3)]
        self.quad((x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), color, (0, 0, -1))
        self.quad((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1), color, (0, 0, 1))
        self.quad((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1), color, (0, -1, 0))
        self.quad((x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1), color, (0, 1, 0))
        self.quad((x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1), color, (-1, 0, 0))
        self.quad((x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1), color, (1, 0, 0))

    def make(self, name, smooth=False):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(self.points, [], self.faces)
        paint = mesh.color_attributes.new("Col", "BYTE_COLOR", "CORNER")
        for poly, color in zip(mesh.polygons, self.colors):
            for corner in poly.loop_indices:
                paint.data[corner].color = (color[0], color[1], color[2], 1.0)
            poly.use_smooth = smooth
        if smooth:  # one curved skin: its corners are shared, so it shades as a curve
            import bmesh

            bm = bmesh.new()
            bm.from_mesh(mesh)
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
            bm.to_mesh(mesh)
            bm.free()
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        return obj


def tinted(color, rng, by=0.09):
    k = 1.0 + rng.uniform(-by, by)
    warm = rng.uniform(-0.012, 0.012)
    return (min(1.0, color[0] * k + warm), min(1.0, color[1] * k), min(1.0, color[2] * k - warm))


def cuts(lo, hi, step, also=()):
    """Places to cut a stretch into pieces no longer than `step`, with a cut at every one of `also`."""
    marks = sorted({round(lo, 5), round(hi, 5)} | {round(v, 5) for v in also if lo < v < hi})
    out = [marks[0]]
    for a, b in zip(marks, marks[1:]):
        n = max(1, math.ceil((b - a) / step - 1e-6))
        out += [a + (b - a) * (i + 1) / n for i in range(n)]
    return out


def surface(pipe, rng):
    """The riding surface, lip to lip, as sheets of plywood laid like bricks."""
    shell = Shell()
    half = pipe.width / 2.0
    rows = math.ceil(2.0 * pipe.lip / SHEET[0])
    row_at = [-pipe.lip + i * SHEET[0] for i in range(rows)] + [pipe.lip]
    corners = (pipe.half_flat, pipe.half_flat + pipe.arc)
    for r in range(rows):
        s0, s1 = row_at[r], row_at[r + 1]
        shift = (r % 2) * SHEET[1] / 2.0  # every other row starts half a sheet along
        seams = cuts(-half, half, SHEET[1], also=[-half + shift + k * SHEET[1] for k in range(-1, 8)])
        along = cuts(s0, s1, STEP, also=[-corners[1], -corners[0], corners[0], corners[1]])
        for z0, z1 in zip(seams, seams[1:]):
            color = tinted(PLY, rng)
            for a, b in zip(along, along[1:]):
                p, q = pipe.at(a), pipe.at(b)
                shell.quad((p["x"], p["y"], z1), (q["x"], q["y"], z1), (q["x"], q["y"], z0), (p["x"], p["y"], z0), color, (p["normal"][0], p["normal"][1], 0.0))
    return shell.make("riding surface", smooth=True)


def frame(pipe, rng):
    """Everything that is not ridden: the decks, the ends, the backs, the ribs, the railings."""
    shell = Shell()
    half, h, w, e = pipe.width / 2.0, pipe.height, pipe.wall_x, pipe.end_x
    for side in (-1.0, 1.0):
        # The deck's top, in sheets, a shade darker than the surface.
        for z0, z1 in zip(cuts(-half, half, SHEET[1]), cuts(-half, half, SHEET[1])[1:]):
            shell.quad((side * w, h, z0), (side * w, h, z1), (side * e, h, z1), (side * e, h, z0), tinted(SIDE, rng, 0.04), (0, 1, 0))
        # Its back wall.
        for z0, z1 in zip(cuts(-half, half, SHEET[1]), cuts(-half, half, SHEET[1])[1:]):
            shell.quad((side * e, 0.0, z0), (side * e, h, z0), (side * e, h, z1), (side * e, 0.0, z1), tinted(SIDE, rng, 0.04), (side, 0, 0))
        # The railing: posts, a top rail and a middle one.
        for z in cuts(-half + 0.05, half - 0.05, 2.0):
            shell.box((side * e - 0.07 if side > 0 else side * e + 0.01, h, z - 0.03), (side * e - 0.01 if side > 0 else side * e + 0.07, h + RAIL_M, z + 0.03), RAIL)
        for y in (h + RAIL_M, h + 0.55 * RAIL_M):
            shell.box((min(side * e, side * (e - 0.08)), y - 0.04, -half), (max(side * e, side * (e - 0.08)), y, half), RAIL)
    # The two ends: the ramp's cut, flat bottom to deck, as a wall of strips under the curve.
    for end in (-half, half):
        for side in (-1.0, 1.0):
            xs = cuts(pipe.half_flat, e, 0.2, also=[w])
            for a, b in zip(xs, xs[1:]):
                ya = pipe.radius - math.sqrt(max(0.0, pipe.radius ** 2 - (a - pipe.half_flat) ** 2)) if a < w else h
                yb = pipe.radius - math.sqrt(max(0.0, pipe.radius ** 2 - (b - pipe.half_flat) ** 2)) if b < w - 1e-9 else h
                if a >= w - 1e-9:
                    ya = h
                shell.poly([(side * a, 0.0, end), (side * b, 0.0, end), (side * b, yb, end), (side * a, ya, end)], SIDE, (0, 0, end))
        # The frame's ribs showing on each end: uprights every 1.22 m, and the curve's edge.
        for side in (-1.0, 1.0):
            out = 0.02 if end > 0 else -0.02
            for x in cuts(pipe.half_flat + SHEET[0], e, SHEET[0]):
                top = pipe.radius - math.sqrt(max(0.0, pipe.radius ** 2 - (min(x, w) - pipe.half_flat) ** 2)) if x < w else h
                if top < 0.12:
                    continue
                shell.box((side * x - 0.04, 0.0, min(end, end + out)), (side * x + 0.04, top, max(end, end + out)), RIB)
    # Under the flat: a low kick board at each end, so the flat reads as a floor laid on the ground.
    for end in (-half, half):
        shell.box((-pipe.half_flat, -0.02, min(end, end + 0.02 * (1 if end > 0 else -1))), (pipe.half_flat, 0.0, max(end, end + 0.02 * (1 if end > 0 else -1))), RIB)
    return shell.make("frame")


def coping(pipe):
    """The steel tube along each lip."""
    shell = Shell()
    half, sides = pipe.width / 2.0, 10
    for side in (-1.0, 1.0):
        cx, cy = pipe.coping(side)
        ring = [(cx + pipe.coping_r * math.cos(2 * math.pi * i / sides), cy + pipe.coping_r * math.sin(2 * math.pi * i / sides)) for i in range(sides)]
        for (ax, ay), (bx, by) in zip(ring, ring[1:] + ring[:1]):
            shell.quad((ax, ay, -half), (bx, by, -half), (bx, by, half), (ax, ay, half), STEEL, (ax + bx - 2 * cx, ay + by - 2 * cy, 0.0))
        for end in (-half, half):
            shell.poly([(x, y, end) for x, y in ring], STEEL, (0, 0, end))
    return shell.make("coping", smooth=True)


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    st = standing.load(args[0] if args else "halfpipe")
    pipe = Pipe(st["ramp"])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    rng = random.Random(1830)
    made = [surface(pipe, rng), frame(pipe, rng), coping(pipe)]
    out = os.path.join(st["dir"], st["geometry"].get("glb", "set.glb"))
    options = {"filepath": out, "export_format": "GLB", "use_active_scene": True, "export_apply": True, "export_materials": "NONE", "export_animations": False}
    if "export_vertex_color" in bpy.ops.export_scene.gltf.get_rna_type().properties.keys():
        options["export_vertex_color"] = "ACTIVE"
    bpy.ops.export_scene.gltf(**options)
    triangles = sum(len(p.vertices) - 2 for o in made for p in o.data.polygons)
    print("HALFPIPE built %s: %d triangles, %.1f x %.1f x %.1f m, %d kB -> %s" % (
        st["name"], triangles, 2.0 * pipe.end_x, pipe.height + RAIL_M, pipe.width, os.path.getsize(out) // 1000, os.path.relpath(out, REPO)))


main()
