"""Puts a SOMA motion on a plain box mannequin and writes it as a .glb.

    python3 scripts/motion/to_gltf.py <shot folder>          # motion.json -> motion.glb
    python3 scripts/motion/to_gltf.py --poses <out.glb>      # the pose library, one pose a frame

The mannequin is a box per bone, skinned to a real skeleton whose joints carry
the SOMA names, so Blender (or any glTF viewer) opens it as an armature with
an animation, ready to watch or to retarget from. Left-side boxes are blue and
right-side ones cream, so you can tell a left step from a right one.

If the shot folder has a plan.json with a `set` (roof, ledge, wall), those
blocks are written into the same file, standing still.

Plain Python: writes the binary glTF by hand.
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from soma import REPO, Skeleton, X, Y, Z, add, dot, frame, length, qconj, qrot, scale, sub, unit, yaw  # noqa: E402

FPS = 30
# Box thickness (metres) by bone, chosen to read as a body, not to be anatomy.
THICK = {
    "Hips": (0.26, 0.16),
    "Spine1": (0.24, 0.15),
    "Spine2": (0.26, 0.16),
    "Chest": (0.30, 0.17),
    "Neck1": (0.08, 0.08),
    "Neck2": (0.08, 0.08),
    "Shoulder": (0.07, 0.07),
    "Arm": (0.08, 0.08),
    "ForeArm": (0.065, 0.065),
    "Hand": (0.07, 0.03),
    "Leg": (0.12, 0.12),
    "Shin": (0.09, 0.09),
    "Foot": (0.08, 0.05),
}
BLUE, CREAM, INK = (0.267, 0.404, 0.608, 1.0), (0.87, 0.82, 0.72, 1.0), (0.11, 0.098, 0.09, 1.0)
SET_COLORS = {"roof": (0.55, 0.53, 0.5, 1.0), "ledge": (0.66, 0.62, 0.56, 1.0), "wall": (0.72, 0.42, 0.33, 1.0), "mark": (0.9, 0.75, 0.3, 1.0)}


def box(center, half, rotation):
    """24 vertices, their normals and 36 indices for a box."""
    corners, normals = [], []
    faces = [((1, 0, 0), (0, 1, 0), (0, 0, 1)), ((0, 1, 0), (0, 0, 1), (1, 0, 0)), ((0, 0, 1), (1, 0, 0), (0, 1, 0))]
    for n, u, v in faces:
        for sign in (1.0, -1.0):
            for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)) if sign > 0 else ((-1, -1), (-1, 1), (1, 1), (1, -1)):
                local = tuple(half[a] * (sign * n[a] + su * u[a] + sv * v[a]) for a in range(3))
                corners.append(add(center, qrot(rotation, local)))
                normals.append(qrot(rotation, scale(n, sign)))
    indices = []
    for f in range(6):
        b = f * 4
        indices += [b, b + 1, b + 2, b, b + 2, b + 3]
    return corners, normals, indices


def bone_box(a, b, width, depth, side_hint=X):
    """A box from point a to point b, `width` across (toward side_hint) and `depth` thick."""
    along = sub(b, a)
    size = length(along)
    hint = side_hint if abs(dot(unit(along), unit(side_hint))) < 0.95 else Z
    rotation = frame(along, hint)  # local x = along, y = across
    return box(scale(add(a, b), 0.5), (size / 2.0, width / 2.0, depth / 2.0), rotation)


class Glb:
    """Collects buffers, accessors and nodes, then writes one .glb."""

    def __init__(self):
        self.bin = bytearray()
        self.views, self.accessors = [], []
        self.doc = {"asset": {"version": "2.0", "generator": "forge scripts/motion/to_gltf.py"}, "nodes": [], "meshes": [], "materials": []}

    def accessor(self, values, kind: str, fmt: str, component: int, target=None, bounds=False) -> int:
        width = {"SCALAR": 1, "VEC3": 3, "VEC4": 4, "MAT4": 16}[kind]
        flat = [c for v in values for c in (v if width > 1 else (v,))]
        while len(self.bin) % 4:
            self.bin.append(0)
        view = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": struct.calcsize(fmt) * len(flat)}
        if target:
            view["target"] = target
        self.bin += struct.pack(f"<{len(flat)}{fmt}", *flat)
        self.views.append(view)
        acc = {"bufferView": len(self.views) - 1, "componentType": component, "count": len(values), "type": kind}
        if bounds:
            cols = list(zip(*values)) if width > 1 else [flat]
            acc["min"], acc["max"] = [min(c) for c in cols], [max(c) for c in cols]
        self.accessors.append(acc)
        return len(self.accessors) - 1

    def material(self, name: str, color) -> int:
        self.doc["materials"].append(
            {"name": name, "pbrMetallicRoughness": {"baseColorFactor": list(color), "metallicFactor": 0.0, "roughnessFactor": 0.85}, "doubleSided": True}
        )
        return len(self.doc["materials"]) - 1

    def primitive(self, positions, normals, indices, material: int, joints=None) -> dict:
        attrs = {
            "POSITION": self.accessor(positions, "VEC3", "f", 5126, 34962, bounds=True),
            "NORMAL": self.accessor(normals, "VEC3", "f", 5126, 34962),
        }
        if joints is not None:
            attrs["JOINTS_0"] = self.accessor([(j, 0, 0, 0) for j in joints], "VEC4", "B", 5121, 34962)
            attrs["WEIGHTS_0"] = self.accessor([(1.0, 0.0, 0.0, 0.0)] * len(joints), "VEC4", "f", 5126, 34962)
        return {"attributes": attrs, "indices": self.accessor(indices, "SCALAR", "H", 5123, 34963), "material": material}

    def write(self, path: str) -> None:
        while len(self.bin) % 4:
            self.bin.append(0)
        self.doc["buffers"] = [{"byteLength": len(self.bin)}]
        self.doc["bufferViews"], self.doc["accessors"] = self.views, self.accessors
        text = json.dumps(self.doc, separators=(",", ":")).encode()
        text += b" " * (-len(text) % 4)
        with open(path, "wb") as f:
            f.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(text) + 8 + len(self.bin)))
            f.write(struct.pack("<I4s", len(text), b"JSON") + text)
            f.write(struct.pack("<I4s", len(self.bin), b"BIN\0") + bytes(self.bin))


def thickness(joint: str):
    for key, value in THICK.items():
        if joint == key or joint.endswith(key):
            return value
    return None


def mannequin(glb: Glb, sk: Skeleton) -> int:
    """Adds the skeleton's joints as nodes 0..n-1 and the skinned box body. Returns the root joint's node."""
    for i, name in enumerate(sk.joints):
        node = {"name": name, "translation": list(sk.rest_pos[i]), "rotation": list(sk.rest_rot[i])}
        if sk.children[i]:
            node["children"] = sk.children[i]
        glb.doc["nodes"].append(node)
    parts = {"left": ([], [], [], []), "right": ([], [], [], []), "middle": ([], [], [], [])}

    def put(side: str, joint: int, shape) -> None:
        positions, normals, indices, joints = parts[side]
        base = len(positions)
        positions += shape[0]
        normals += shape[1]
        indices += [base + k for k in shape[2]]
        joints += [joint] * len(shape[0])

    wp = sk.rest_world_pos
    for i, name in enumerate(sk.joints):
        side = "left" if name.startswith("Left") else "right" if name.startswith("Right") else "middle"
        size = thickness(name)
        kids = [c for c in sk.children[i] if length(sk.rest_pos[c]) > 0.03]
        if size and kids and name not in ("Hips", "Chest"):
            put(side, i, bone_box(wp[i], wp[kids[0]], size[0], size[1]))
        if name == "Hips":
            put(side, i, box(add(wp[i], (0.0, 0.02, 0.0)), (0.15, 0.09, 0.09), (0.0, 0.0, 0.0, 1.0)))
        if name == "Chest":
            top = wp[sk.index["Neck1"]]
            put(side, i, bone_box(wp[i], top, 0.32, 0.18))
        if name == "Head":
            put(side, i, box(add(wp[i], (0.0, 0.09, 0.02)), (0.085, 0.11, 0.1), (0.0, 0.0, 0.0, 1.0)))
            put("left", i, box(add(wp[i], (0.0, 0.07, 0.135)), (0.02, 0.02, 0.035), (0.0, 0.0, 0.0, 1.0)))  # a nose
        if name.endswith("ToeBase"):
            put(side, i, box(add(wp[i], (0.0, 0.0, 0.035)), (0.045, 0.02, 0.045), (0.0, 0.0, 0.0, 1.0)))

    inverse_bind = []
    for i in range(len(sk.joints)):
        q, p = qconj(sk.rest_world_rot[i]), sk.rest_world_pos[i]
        cx, cy, cz = qrot(q, X), qrot(q, Y), qrot(q, Z)
        t = scale(qrot(q, p), -1.0)
        inverse_bind.append((*cx, 0.0, *cy, 0.0, *cz, 0.0, *t, 1.0))
    glb.doc["skins"] = [
        {"name": "SOMA", "joints": list(range(len(sk.joints))), "skeleton": 0, "inverseBindMatrices": glb.accessor(inverse_bind, "MAT4", "f", 5126)}
    ]
    colors = {"left": ("left side", BLUE), "right": ("right side", CREAM), "middle": ("middle", INK)}
    glb.doc["meshes"].append(
        {
            "name": "SOMA mannequin",
            "primitives": [
                glb.primitive(p, n, ix, glb.material(colors[side][0], colors[side][1]), joints=j)
                for side, (p, n, ix, j) in parts.items()
                if p
            ],
        }
    )
    glb.doc["nodes"].append({"name": "SOMA mannequin", "mesh": len(glb.doc["meshes"]) - 1, "skin": 0})
    return len(glb.doc["nodes"]) - 1


def set_blocks(glb: Glb, blocks: list) -> list:
    """Still blocks: each {name, kind, center [x,y,z], size [x,y,z], heading}."""
    nodes = []
    materials = {}
    for block in blocks:
        kind = block.get("kind", "roof")
        if kind not in materials:
            materials[kind] = glb.material(kind, SET_COLORS.get(kind, SET_COLORS["roof"]))
        half = tuple(v / 2.0 for v in block["size"])
        shape = box((0.0, 0.0, 0.0), half, (0.0, 0.0, 0.0, 1.0))
        glb.doc["meshes"].append({"name": block["name"], "primitives": [glb.primitive(shape[0], shape[1], shape[2], materials[kind])]})
        glb.doc["nodes"].append(
            {
                "name": block["name"],
                "mesh": len(glb.doc["meshes"]) - 1,
                "translation": list(block["center"]),
                "rotation": list(yaw(float(block.get("heading", 0.0)))),
            }
        )
        nodes.append(len(glb.doc["nodes"]) - 1)
    return nodes


def animate(glb: Glb, sk: Skeleton, name: str, roots: list, rotations: list, fps: float = FPS) -> None:
    """One animation: the root's position and every joint's rotation, a key per frame."""
    times = glb.accessor([f / fps for f in range(len(roots))], "SCALAR", "f", 5126, bounds=True)
    samplers = [{"input": times, "output": glb.accessor([tuple(r) for r in roots], "VEC3", "f", 5126), "interpolation": "LINEAR"}]
    channels = [{"sampler": 0, "target": {"node": 0, "path": "translation"}}]
    for j in range(len(sk.joints)):
        keys, last = [], None
        for frame_rot in rotations:
            q = tuple(frame_rot[j])
            # Keep neighbouring keys on the same side of the quaternion sphere,
            # so players that blend them linearly don't take the long way round.
            if last is not None and sum(q[k] * last[k] for k in range(4)) < 0.0:
                q = tuple(-c for c in q)
            keys.append(q)
            last = q
        samplers.append({"input": times, "output": glb.accessor(keys, "VEC4", "f", 5126), "interpolation": "LINEAR"})
        channels.append({"sampler": len(samplers) - 1, "target": {"node": j, "path": "rotation"}})
    glb.doc.setdefault("animations", []).append({"name": name, "samplers": samplers, "channels": channels})


def load_motion(path: str, sk: Skeleton):
    """motion.json -> (root positions, per-frame rotations as [joint][4]), in the skeleton's joint order."""
    with open(path) as f:
        motion = json.load(f)
    order = [motion["joints"].index(name) for name in sk.joints]
    rotations = [[row[4 * j : 4 * j + 4] for j in order] for row in motion["rotations"]]
    return motion, motion["root"], rotations


def write_shot(shot: str) -> str:
    sk = Skeleton.load()
    motion, roots, rotations = load_motion(os.path.join(shot, "motion.json"), sk)
    glb = Glb()
    body = mannequin(glb, sk)
    scene = [0, body]
    plan_path = os.path.join(shot, "plan.json")
    if os.path.exists(plan_path):
        with open(plan_path) as f:
            scene += set_blocks(glb, json.load(f).get("set", []))
    animate(glb, sk, os.path.basename(os.path.normpath(shot)), roots, rotations, motion.get("fps", FPS))
    glb.doc["scenes"], glb.doc["scene"] = [{"name": "shot", "nodes": scene}], 0
    out = os.path.join(shot, "motion.glb")
    glb.write(out)
    return out


def write_poses(out: str, library_path: str) -> str:
    """The pose library as an animation holding each pose for one frame, in a row along X."""
    sk = Skeleton.load()
    with open(library_path) as f:
        library = json.load(f)["poses"]
    glb = Glb()
    body = mannequin(glb, sk)
    roots = [pose["root"] for pose in library.values()]
    rotations = [sk.rotation_list(pose["rotations"]) for pose in library.values()]
    animate(glb, sk, "pose library", roots, rotations, 1.0)
    glb.doc["scenes"], glb.doc["scene"] = [{"name": "poses", "nodes": [0, body]}], 0
    glb.doc["extras"] = {"poses": list(library)}
    glb.write(out)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("shot", nargs="?")
    parser.add_argument("--poses", metavar="OUT_GLB")
    parser.add_argument("--library", default=os.path.join(REPO, "motion", "poses.json"))
    args = parser.parse_args()
    if args.poses:
        print("GLTF", write_poses(args.poses, args.library))
    elif args.shot:
        print("GLTF", write_shot(args.shot))
    else:
        parser.error("give a shot folder, or --poses OUT.glb")


if __name__ == "__main__":
    main()
