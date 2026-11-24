"""Builds the skateboard from its numbers, in a background Blender: world/props/skateboard.glb.

    Blender -b --factory-startup -P scripts/skate/build_board.py

A deck with two kicktails and grip tape on top, two trucks, four wheels and
the eight bolts the feet stand over, from scripts/skate/board.py. It is
built in the board's own frame (x toward the nose, y toward the heel side, z
up, 0 at the middle of the top of the deck), in flat colors painted on the
corners, like the rest of the world's block-outs. About 500 triangles.

Never touches an open Blender.
"""

import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import board  # noqa: E402

GRIP = (0.10, 0.10, 0.11)
MAPLE = (0.72, 0.54, 0.34)
PAINT = (0.50, 0.15, 0.11)   # the underside: barn red
STEEL = (0.62, 0.64, 0.67)
WHEEL = (0.90, 0.87, 0.78)
BOLT = (0.55, 0.56, 0.58)


class Shell:
    def __init__(self):
        self.points, self.faces, self.colors = [], [], []

    def poly(self, corners, color, face=None):
        corners = list(corners)
        if face is not None:
            a, b, c = corners[0], corners[1], corners[2]
            u, v = [b[i] - a[i] for i in range(3)], [c[i] - b[i] for i in range(3)]
            n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            if n[0] * face[0] + n[1] * face[1] + n[2] * face[2] < 0:
                corners.reverse()
        n = len(self.points)
        self.points += corners
        self.faces.append(tuple(range(n, n + len(corners))))
        self.colors.append(color)

    def box(self, lo, hi, color):
        x0, y0, z0 = [min(lo[i], hi[i]) for i in range(3)]
        x1, y1, z1 = [max(lo[i], hi[i]) for i in range(3)]
        self.poly([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)], color, (0, 0, -1))
        self.poly([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], color, (0, 0, 1))
        self.poly([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], color, (0, -1, 0))
        self.poly([(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)], color, (0, 1, 0))
        self.poly([(x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)], color, (-1, 0, 0))
        self.poly([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], color, (1, 0, 0))

    def make(self, name):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(self.points, [], self.faces)
        paint = mesh.color_attributes.new("Col", "BYTE_COLOR", "CORNER")
        for poly, color in zip(mesh.polygons, self.colors):
            for corner in poly.loop_indices:
                paint.data[corner].color = (color[0], color[1], color[2], 1.0)
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        return obj


def build():
    shell = Shell()
    half = board.LONG / 2.0
    xs = sorted({-half, half, -board.KICK_FROM, board.KICK_FROM, -board.ROUND_FROM, board.ROUND_FROM, 0.0}
                | {s * (board.ROUND_FROM + (half - board.ROUND_FROM) * k / 4.0) for s in (-1.0, 1.0) for k in range(1, 4)}
                | {s * board.KICK_FROM * k / 2.0 for s in (-1.0, 1.0) for k in range(1, 2)})
    for a, b in zip(xs, xs[1:]):
        wa, wb, ta, tb = board.half_width_at(a), board.half_width_at(b), board.top_at(a), board.top_at(b)
        under = PAINT if abs(a + b) / 2.0 < board.TRUCK_X - 0.05 else MAPLE
        shell.poly([(a, -wa, ta), (b, -wb, tb), (b, wb, tb), (a, wa, ta)], GRIP, (0, 0, 1))
        shell.poly([(a, -wa, ta - board.THICK), (b, -wb, tb - board.THICK), (b, wb, tb - board.THICK), (a, wa, ta - board.THICK)], under, (0, 0, -1))
        for side in (-1.0, 1.0):
            shell.poly([(a, side * wa, ta - board.THICK), (b, side * wb, tb - board.THICK), (b, side * wb, tb), (a, side * wa, ta)], MAPLE, (0, side, 0))
    for end in (-half, half):
        w, t = board.half_width_at(end), board.top_at(end)
        shell.poly([(end, -w, t - board.THICK), (end, w, t - board.THICK), (end, w, t), (end, -w, t)], MAPLE, (end, 0, 0))
    axle = -board.DECK_TOP + board.WHEEL_R
    for sx in (-1.0, 1.0):
        x = sx * board.TRUCK_X
        shell.box((x - 0.04, -0.028, -board.THICK - 0.012), (x + 0.04, 0.028, -board.THICK), STEEL)          # the baseplate
        shell.box((x - 0.014, -0.02, axle - 0.004), (x + 0.014, 0.02, -board.THICK - 0.012), STEEL)           # the kingpin's block
        shell.box((x - 0.012, -(board.TRACK - 0.01), axle - 0.012), (x + 0.012, board.TRACK - 0.01, axle + 0.012), STEEL)  # the hanger and axle
        for sy in (-1.0, 1.0):
            y0, y1, sides = sy * board.TRACK - board.WHEEL_W / 2.0, sy * board.TRACK + board.WHEEL_W / 2.0, 12
            ring = [(x + board.WHEEL_R * math.cos(2 * math.pi * i / sides), axle + board.WHEEL_R * math.sin(2 * math.pi * i / sides)) for i in range(sides)]
            for (ax, az), (bx, bz) in zip(ring, ring[1:] + ring[:1]):
                shell.poly([(ax, y0, az), (bx, y0, bz), (bx, y1, bz), (ax, y1, az)], WHEEL, (ax + bx - 2 * x, 0, az + bz - 2 * axle))
            shell.poly([(px, y0, pz) for px, pz in ring], WHEEL, (0, -1, 0))
            shell.poly([(px, y1, pz) for px, pz in ring], WHEEL, (0, 1, 0))
    for bx, by, _ in board.bolts():
        shell.poly([(bx - 0.007, by - 0.007, 0.0012), (bx + 0.007, by - 0.007, 0.0012), (bx + 0.007, by + 0.007, 0.0012), (bx - 0.007, by + 0.007, 0.0012)], BOLT, (0, 0, 1))
    return shell.make("skateboard")


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj = build()
    obj["forge"], obj["prop"] = "prop", "skateboard"
    os.makedirs(os.path.dirname(board.GLB), exist_ok=True)
    options = {"filepath": board.GLB, "export_format": "GLB", "use_active_scene": True, "export_apply": True, "export_materials": "NONE", "export_animations": False,
               "export_extras": True, "export_yup": True}
    if "export_vertex_color" in bpy.ops.export_scene.gltf.get_rna_type().properties.keys():
        options["export_vertex_color"] = "ACTIVE"
    bpy.ops.export_scene.gltf(**options)
    board.main()
    print("BOARD built: %d triangles, %.2f m long, %.2f m wide, deck %.1f cm off the ground, %d kB -> %s" % (
        sum(len(p.vertices) - 2 for p in obj.data.polygons), board.LONG, board.WIDE, 100 * board.DECK_TOP, os.path.getsize(board.GLB) // 1000, os.path.relpath(board.GLB, board.REPO)))


main()
