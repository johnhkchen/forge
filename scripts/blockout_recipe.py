"""Tidy a block-out's lowpoly.glb after Claude exports it, and save its recipe.

    python3 scripts/blockout_recipe.py runs/<run>/lowpoly.glb

build.py and export.py run inside the person's Blender in safe mode, which
allows no file access of their own. So what has to outlive the session rides
in the .glb as glTF extras: each node's tag (body, a gear item with its kind
and slot, or a socket) and, on the first mesh, the recipe build.py was given
(every piece as data, plus the head's measured surface).

This reads them back, with plain Python and no Blender:

- writes the recipe as lowpoly_build.json beside the .glb, which the
  `midpoly` profile rebuilds from, denser;
- puts the node names right. Blender keeps object names unique across the
  whole file, so in a session that already holds another run's "body" the
  exporter writes "body.001". The tags say what each node is, so the names
  are set from them: "body", "gear: wool singlet", "socket: hand_right".

It also holds how a recipe is made denser for the mid-poly version
(`denser`), so that can be tried without Blender.

Prints one line of JSON: the groups, the sockets and whether a recipe was
found. A .glb from before gear and recipes (one mesh, no extras) is left as
it is.
"""
import json
import os
import struct
import sys

JSON_CHUNK, GLB_MAGIC = 0x4E4F534A, 0x46546C67


WARDROBE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "tidy-mesh", "wardrobe")


def wardrobe_template(materials):
    """The wardrobe template a character's body is (wrap.py marks the material of the template's faces with its
    name), as the path of that template's .glb, which rig.py reads the body's weights from. None for a
    character with a body of its own. `materials` is bpy.data.materials."""
    for material in materials:
        if material is not None and material.get("template"):
            return os.path.abspath(os.path.join(WARDROBE, material["template"] + ".glb"))
    return None


def read(path):
    """A .glb's JSON document, and the bytes that follow it (the binary chunk)."""
    with open(path, "rb") as f:
        magic, _, _ = struct.unpack("<III", f.read(12))
        size, kind = struct.unpack("<II", f.read(8))
        if magic != GLB_MAGIC or kind != JSON_CHUNK:
            raise ValueError("%s is not a .glb" % path)
        return json.loads(f.read(size)), f.read()


def write(path, doc, rest):
    text = json.dumps(doc, separators=(",", ":")).encode()
    text += b" " * (-len(text) % 4)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", GLB_MAGIC, 2, 20 + len(text) + len(rest)))
        f.write(struct.pack("<II", len(text), JSON_CHUNK))
        f.write(text)
        f.write(rest)


def tag_name(extras):
    """The name a node's tag gives it, or None for an untagged node."""
    kind = (extras or {}).get("forge")
    if kind == "body":  # after drape.py: the faces a gear item hides are a mesh of their own, named for that gear
        under = extras.get("under")
        if under:
            return "body under: " + " + ".join(under.split("|"))  # "under" is the gear's names, joined with |
        return "body"
    if kind == "gear" and extras.get("gear"):
        return "gear: " + extras["gear"]
    if kind == "socket" and extras.get("socket"):
        return "socket: " + extras["socket"]
    return None


def contents(doc):
    """What a block-out file holds: its groups (body and gear, with kind and slot), sockets and recipe."""
    groups, sockets, recipe = [], {}, None
    for node in doc.get("nodes", []):
        extras = node.get("extras") or {}
        name = tag_name(extras)
        if extras.get("forge_build"):
            recipe = json.loads(extras["forge_build"])
        if name and extras["forge"] == "socket":
            sockets[extras["socket"]] = node.get("translation", [0, 0, 0])
        elif name and not extras.get("under"):
            groups.append({k: extras.get(k) for k in ("gear", "kind", "slot") if extras.get(k)} | {"name": name})
    return {"groups": groups, "sockets": sockets, "recipe": recipe}


def tidy_names(doc):
    """Name every tagged node for its tag, and drop the one tag that only meant something inside
    Blender (which object a socket belonged to). Returns how many nodes changed."""
    changed = 0
    for node in doc.get("nodes", []):
        name = tag_name(node.get("extras"))
        if name and "socket_of" in node["extras"]:
            del node["extras"]["socket_of"]
            changed += 1
        if name and node.get("name") != name:
            node["name"] = name
            changed += 1
    return changed

# ---- the recipe, denser: what the mid-poly profile builds from ----

def eased(before, a, b, after, t):
    """A smooth curve through a and b (Catmull-Rom), kept between the two so
    a step in the block-out stays a step and never bulges past either ring."""
    value = 0.5 * (2 * a + (b - before) * t + (2 * before - 5 * a + 4 * b - after) * t * t + (3 * a - before - 3 * b + after) * t ** 3)
    return min(max(value, min(a, b)), max(a, b))


def more_rows(rows, each, wrap, defaults, gap):
    """`rows` (a loft's rings or a tube's points) with `each` - 1 new rows
    eased in between every two that are more than `gap` apart. A row is
    numbers with an optional dict of extras at the end; rows come back with
    every number spelled out."""
    def spelled(row):
        nums = [v for v in row if not isinstance(v, dict)]
        more = row[-1] if isinstance(row[-1], dict) else {}
        nums = nums + [nums[3]] if len(nums) < 5 else nums[:5]
        return nums + [more.get(key, nums[4] if key == "back" else value) for key, value in defaults]

    def written(nums):
        return nums[:5] + [{key: nums[5 + i] for i, (key, _) in enumerate(defaults)}]

    full = [spelled(r) for r in rows]
    count = len(full)
    out = []
    for i in range(count if wrap else count - 1):
        a, b = full[i], full[(i + 1) % count]
        before = full[i - 1] if (wrap or i > 0) else a
        after = full[(i + 2) % count] if (wrap or i + 2 < count) else b
        out.append(written(a))
        if sum((a[k] - b[k]) ** 2 for k in range(3)) ** 0.5 <= gap:
            continue
        for step in range(1, each):
            out.append(written([eased(before[k], a[k], b[k], after[k], step / each) for k in range(len(a))]))
    if not wrap:
        out.append(written(full[-1]))
    return out


def denser(part, sides, rings, size):
    """One piece of the recipe with `sides` times the points around and
    `rings` times the rows along. Square posts (4 sides) stay square, boxes
    stay boxes, bands keep their four rings, rocks and heads are split finer
    (a head also loses its sunk eye sockets)."""
    new = dict(part)
    if "head" in part:
        new["finer"] = part.get("finer", 0) + 1
        new["eyes"] = "flat"  # the baked texture and normal map carry the eyes; a sunk socket is the low-poly look
    elif "lumps" in part:
        new["detail"] = part.get("detail", 1) + 1
    elif "loft" in part or "tube" in part:
        key = "rings" if "loft" in part else "tube"
        around = part.get("sides", 8 if "loft" in part else 6)
        if around > 4:
            new["sides"] = min(around * sides, 32)
        band = "loft" in part and part.get("closed")
        if rings > 1 and not band:
            defaults = [("square", part.get("square", 2))] + ([("back", None), ("slope", 0)] if "loft" in part else [])
            new[key] = more_rows(part[key], rings, bool(part.get("closed")), defaults, 0.01 * size)
    return new


def mid_parts(pieces, sides, rings, size):
    """The whole recipe for the mid-poly version: (parts for build.py, kept body surfaces {name: data}).
    Ordinary pieces are made denser. A body is not: its trunk, arms and legs were written out by a "body"
    piece, so they are dropped and that piece is asked for again with "detail": "mid", which builds it
    with more loops where it bends and its rings laid on the surface landmarks.py kept (the chest, the
    shoulder blades, the kneecaps and ankle bones of the detailed mesh), not only rounder."""
    parts, kept = [], {}
    for piece in pieces:
        if not piece.get("of"):
            parts.append(denser(piece, sides, rings, size))
        elif isinstance(piece.get("body"), dict) and piece["body"].get("spec"):
            parts.append(dict(piece["body"]["spec"], detail="mid"))
            held = piece["body"].get("kept")
            if held:
                kept[held["name"]] = held["data"]
    return parts, kept


# How much denser to try, lightest first: (sides, rings).
DENSER = [(2, 1), (2, 2), (3, 2), (3, 3), (4, 3), (4, 4)]


def main(path):
    doc, rest = read(path)
    renamed = tidy_names(doc)
    if renamed:
        write(path, doc, rest)
    held = contents(doc)
    if held["recipe"]:
        with open(os.path.join(os.path.dirname(os.path.abspath(path)), "lowpoly_build.json"), "w") as f:
            json.dump(held["recipe"], f)
    print(json.dumps({"groups": [g["name"] for g in held["groups"]], "sockets": sorted(held["sockets"]),
                      "recipe": bool(held["recipe"]), "renamed": renamed}))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: blockout_recipe.py runs/<run>/lowpoly.glb")
    main(sys.argv[1])
