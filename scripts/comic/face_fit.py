"""A character's expression sheet, before and after Codex draws it. Background Blender, one character at a time.

    Blender -b --factory-startup -P scripts/comic/face_fit.py -- head <who> [--runs runs]
    Blender -b --factory-startup -P scripts/comic/face_fit.py -- cut  <who> [--runs runs]
    Blender -b --factory-startup -P scripts/comic/face_fit.py -- show <who> [--runs runs]

head  draws the character's own head from the front in the comic style (comics/cast/<who>/head.png) and notes
      where the head is in that picture and in the character (head.json). Codex is shown this picture next to the
      head sheet, so what it draws has our look and this head's shape.
cut   takes Codex's sheet (comics/cast/<who>/sheet.png: a grid of the same head with different expressions), finds
      the head in every cell, lines it up with the character's head by its top and its width, and saves each
      expression as faces/<name>.png: see-through except for the face (or, for a masked face, the strip around the
      eyes), toned to the character's own skin. face.json says where each picture sits on the head, for face_swap.py.
show  puts every cut expression on the head and pictures them in a row (faces.png), to check the fit by eye.

Blender only (imports bpy); never touches an open Blender.
"""

import json
import os
import sys

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit  # noqa: E402
import stage  # noqa: E402

HEAD_PX = 640
FACE_PX = 384
MARGIN = 1.3  # the head picture is this much wider than the head


def head_points(character):
    """Every point that follows the head bone, as the character was built."""
    found = []
    for o in character["meshes"]:
        group = o.vertex_groups.get("head")
        if group is None:
            continue
        for v in o.data.vertices:
            if any(g.group == group.index and g.weight > 0.5 for g in v.groups):
                found.append(o.matrix_world @ v.co)
    if not found:
        raise ValueError("nothing follows the head bone")
    return found


def load_pixels(path):
    """A picture as rows from the top, [tall, wide, 4], 0 to 1."""
    image = bpy.data.images.load(path)
    wide, tall = image.size
    grid = np.array(image.pixels[:], dtype=np.float32).reshape(tall, wide, 4)[::-1]
    if image.is_float:  # a 16-bit picture comes in as light, not as seen: bring it back to what the eye sees
        grid[:, :, :3] = np.clip(grid[:, :, :3], 0.0, 1.0) ** (1.0 / 2.2)
    bpy.data.images.remove(image)
    return grid


def save_pixels(grid, path):
    tall, wide = grid.shape[:2]
    image = bpy.data.images.new("out", wide, tall, alpha=True)
    image.alpha_mode = "STRAIGHT"
    image.pixels.foreach_set(np.ascontiguousarray(grid[::-1], dtype=np.float32).ravel())
    image.filepath_raw, image.file_format = path, "PNG"
    image.save()
    bpy.data.images.remove(image)


def setup(who, runs):
    entry = kit.load_cast()[who]
    glb = kit.clip_file(runs, entry, "walk")
    if not glb:
        raise ValueError("no rigged file for %s under %s" % (who, runs))
    scene = stage.fresh_scene()
    character = stage.load_character(glb)
    stage.strike(character, {"bones": {}})
    return entry, scene, character


def front_camera(scene, box):
    cam = stage.add_camera(scene, "head camera")
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = box["span"]
    stage.aim(cam, (box["center"][0], box["front"] - 3.0, box["center"][1]), (box["center"][0], box["front"], box["center"][1]))
    return cam


def measure_head(character):
    points = head_points(character)
    xs, ys, zs = [p.x for p in points], [p.y for p in points], [p.z for p in points]
    wide, tall = max(xs) - min(xs), max(zs) - min(zs)
    return {"center": [(max(xs) + min(xs)) / 2, (max(zs) + min(zs)) / 2], "wide": wide, "tall": tall,
            "front": min(ys), "depth": max(ys) - min(ys), "span": max(wide, tall) * MARGIN}


def head(who, runs):
    entry, scene, character = setup(who, runs)
    box = measure_head(character)
    front_camera(scene, box)
    folder = os.path.join(kit.CAST_DIR, who)
    os.makedirs(folder, exist_ok=True)
    stage.run_script("toon.py", {"path": os.path.join(folder, "head.png"), "size": [HEAD_PX, HEAD_PX], "background": [0.83, 0.83, 0.83],
                                 "line_px": 4.0})
    with open(os.path.join(folder, "head.json"), "w") as f:
        json.dump(box, f, indent=2)
    print("FACE head", os.path.join(folder, "head.png"), json.dumps({k: round(v, 4) if isinstance(v, float) else v for k, v in box.items()}))


def find_head(cell, paper):
    """The drawn head in one cell of the sheet: (left, top, right, bottom) in pixels, from what is not background."""
    apart = np.abs(cell[:, :, :3] - paper).max(axis=2) > 0.09
    rows = np.where(apart.sum(axis=1) > cell.shape[1] * 0.04)[0]
    cols = np.where(apart.sum(axis=0) > cell.shape[0] * 0.04)[0]
    if len(rows) == 0 or len(cols) == 0:
        raise ValueError("a cell of the sheet is empty")
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


def soften(mask, rounds):
    grid = mask.astype(np.float32)
    for _ in range(rounds):
        padded = np.pad(grid, 1, mode="edge")
        grid = (padded[:-2, 1:-1] + padded[2:, 1:-1] + padded[1:-1, :-2] + padded[1:-1, 2:] + padded[1:-1, 1:-1]) / 5.0
    return grid


def resize(grid, wide, tall):
    """Nearest-neighbor is enough here: the cuts are made larger than they are shown."""
    rows = (np.arange(tall) * grid.shape[0] / tall).astype(int)
    cols = (np.arange(wide) * grid.shape[1] / wide).astype(int)
    return grid[rows][:, cols]


def skin_mask(crop):
    """For a masked face: what is skin or eye rather than cloth. Bright, or shut in by bright on all four sides."""
    light = crop[:, :, :3].mean(axis=2)
    bright = light > (np.percentile(light, 25) + np.percentile(light, 85)) / 2
    left = np.maximum.accumulate(bright, axis=1)
    right = np.maximum.accumulate(bright[:, ::-1], axis=1)[:, ::-1]
    above = np.maximum.accumulate(bright, axis=0)
    below = np.maximum.accumulate(bright[::-1], axis=0)[::-1]
    return bright | (left & right & above & below)


def skin_of(patch, low=65, high=95):
    """The skin's color in a patch of face: its lit tone, so brows, eyes, shade and a mustache don't count."""
    flat = patch[:, :, :3].reshape(-1, 3)
    light = flat.mean(axis=1)
    return np.median(flat[(light >= np.percentile(light, low)) & (light <= np.percentile(light, high))], axis=0)


def warm_box(grid):
    """Where skin shows in a picture of a masked head: (left, top, right, bottom) of what is warm and light."""
    r, g, b = grid[:, :, 0], grid[:, :, 1], grid[:, :, 2]
    warm = (r > b * 1.25) & (r > 0.35) & (r - b > 0.12)
    rows = np.where(warm.sum(axis=1) > grid.shape[1] * 0.08)[0]
    cols = np.where(warm.sum(axis=0) > grid.shape[0] * 0.02)[0]
    if len(rows) == 0 or len(cols) == 0:
        return None
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


def cut(who, runs):
    entry = kit.load_cast()[who]
    folder = os.path.join(kit.CAST_DIR, who)
    with open(os.path.join(folder, "head.json")) as f:
        box = json.load(f)
    sheet = load_pixels(os.path.join(folder, "sheet.png"))
    ours = load_pixels(os.path.join(folder, "head.png"))
    columns, rows = kit.SHEET_GRID
    tall, wide = sheet.shape[0] // rows, sheet.shape[1] // columns
    border = np.concatenate([sheet[:6].reshape(-1, 4), sheet[-6:].reshape(-1, 4), sheet[:, :6].reshape(-1, 4), sheet[:, -6:].reshape(-1, 4)])
    paper = np.median(border[:, :3], axis=0)
    region = entry["face"]["region"]
    whole = entry["face"]["kind"] == "whole"
    # Our own head picture: where the head is in it, and the skin's color in the face area.
    per_px = box["span"] / HEAD_PX
    ours_left = HEAD_PX / 2 - box["wide"] / 2 / per_px
    ours_top = HEAD_PX / 2 - box["tall"] / 2 / per_px
    ours_w, ours_h = box["wide"] / per_px, box["tall"] / per_px
    os.makedirs(os.path.join(folder, "faces"), exist_ok=True)
    # A masked face is lined up by the strip of skin itself: where it shows on our head, and where Codex drew it.
    ours_strip = None if whole else warm_box(ours)
    planes, notes = {}, []
    for n, name in enumerate(kit.EXPRESSIONS):
        row, column = n // columns, n % columns
        cell = sheet[row * tall:(row + 1) * tall, column * wide:(column + 1) * wide]
        left, top, right, bottom = find_head(cell, paper)
        head_w, head_h = right - left, bottom - top
        # The face area inside the drawn head, as cast.json gives it.
        fx0, fy0 = left + region[0] * head_w, top + region[1] * head_h
        fx1, fy1 = left + region[2] * head_w, top + region[3] * head_h
        strip = None if whole else warm_box(cell)
        if strip and ours_strip:
            grow_x, grow_y = (strip[2] - strip[0]) * 0.06, (strip[3] - strip[1]) * 0.3
            fx0, fy0, fx1, fy1 = strip[0] - grow_x, strip[1] - grow_y, strip[2] + grow_x, strip[3] + grow_y
        x0, y0, x1, y1 = [int(round(v)) for v in (fx0, fy0, fx1, fy1)]
        crop = cell[max(y0, 0):y1, max(x0, 0):x1].copy()
        ch, cw = crop.shape[:2]
        yy, xx = np.mgrid[0:ch, 0:cw]
        if whole:
            # An oval that fills the area and fades out at its rim.
            r = np.sqrt(((xx - cw / 2) / (cw / 2)) ** 2 + ((yy - ch / 2) / (ch / 2)) ** 2)
            alpha = np.clip((1.0 - r) / 0.16, 0.0, 1.0)
            drawn_skin = skin_of(crop)
            oy0, ox0 = int(ours_top + region[1] * ours_h), int(ours_left + region[0] * ours_w)
            oy1, ox1 = int(ours_top + region[3] * ours_h), int(ours_left + region[2] * ours_w)
            mine = ours[oy0:oy1, ox0:ox1]
            mh, mw = mine.shape[:2]
            own_skin = skin_of(mine, 85, 98)  # our head's lightest skin: what the drawn face's rim will sit against
            tone = np.clip(own_skin / np.maximum(drawn_skin, 0.02), 0.7, 1.4) * float(entry["face"].get("lighten", 1.0))
            crop[:, :, :3] = np.clip(crop[:, :, :3] * tone, 0.0, 1.0)
        else:
            alpha = soften(soften(skin_mask(crop), 2) > 0.25, 3)
            edge = np.minimum(np.minimum(xx, cw - 1 - xx) / (cw * 0.06), np.minimum(yy, ch - 1 - yy) / (ch * 0.12))
            alpha = alpha * np.clip(edge, 0.0, 1.0)
            tone = np.ones(3)
        crop[:, :, 3] = alpha
        scale = FACE_PX / float(max(cw, ch))
        save_pixels(resize(crop, max(1, int(cw * scale)), max(1, int(ch * scale))), os.path.join(folder, "faces", name + ".png"))
        # Line the drawn head up with the character's: same width, tops together, middles together.
        m_per_px = box["wide"] / head_w
        head_top = box["center"][1] + box["tall"] / 2
        center_x = box["center"][0] + ((fx0 + fx1) / 2 - (left + right) / 2) * m_per_px
        center_z = head_top - ((fy0 + fy1) / 2 - top) * m_per_px
        size = [(fx1 - fx0) * m_per_px, (fy1 - fy0) * m_per_px]
        if strip and ours_strip:
            # Strip onto strip: the drawn one, with its border, lands on ours.
            sx = (ours_strip[2] - ours_strip[0]) * per_px / (strip[2] - strip[0])
            sz = max((ours_strip[3] - ours_strip[1]) * per_px / (strip[3] - strip[1]), sx * 0.8)
            center_x = box["center"][0] + ((ours_strip[0] + ours_strip[2]) / 2 - HEAD_PX / 2) * per_px
            center_z = box["center"][1] - ((ours_strip[1] + ours_strip[3]) / 2 - HEAD_PX / 2) * per_px
            size = [(fx1 - fx0) * sx, (fy1 - fy0) * sz]
        planes[name] = {"center": [round(center_x, 4), round(center_z, 4)], "size": [round(size[0], 4), round(size[1], 4)],
                        "front": round(box["front"], 4), "depth": round(box["depth"], 4)}
        notes.append({"expression": name, "head_px": [left, top, right, bottom], "tall_vs_ours": round(head_h * m_per_px / box["tall"], 3),
                      "tone": [round(float(t), 3) for t in tone]})
    with open(os.path.join(folder, "face.json"), "w") as f:
        json.dump({"kind": entry["face"]["kind"], "planes": planes, "fit": notes}, f, indent=2)
    print("FACE cut", who, json.dumps(notes))


def show(who, runs):
    entry, scene, character = setup(who, runs)
    box = measure_head(character)
    front_camera(scene, box)
    folder = os.path.join(kit.CAST_DIR, who)
    with open(os.path.join(folder, "face.json")) as f:
        planes = json.load(f)["planes"]
    stage.run_script("toon.py", {"size": [320, 320], "background": [0.95, 0.93, 0.9]})
    tiles = []
    cam = scene.camera
    for view in ((0.0, -1.0, 0.0), (0.6, -1.0, 0.1)):
        stage.aim(cam, (box["center"][0] + view[0] * 3, box["front"] + view[1] * 3, box["center"][1] + view[2] * 3),
                  (box["center"][0], box["front"] + box["depth"] / 2, box["center"][1]))
        stage.run_script("toon.py", {"size": [320, 320], "background": [0.95, 0.93, 0.9]})
        for name in ["(none)"] + list(planes):
            if name != "(none)":
                stage.run_script("face_swap.py", {"image": os.path.join(folder, "faces", name + ".png"), "plane": planes[name]})
            still = os.path.join(folder, ".still.png")
            scene.render.filepath = still
            bpy.ops.render.render(write_still=True)
            tiles.append(load_pixels(still))
            os.remove(still)
        stage.run_script("face_swap.py", {"off": True})
    per_row = len(planes) + 1
    sheet = np.concatenate([np.concatenate(tiles[i:i + per_row], axis=1) for i in range(0, len(tiles), per_row)], axis=0)
    save_pixels(sheet, os.path.join(folder, "faces.png"))
    print("FACE show", os.path.join(folder, "faces.png"))


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    runs = os.path.join(kit.REPO, "runs")
    if "--runs" in args:
        i = args.index("--runs")
        runs = os.path.abspath(args[i + 1])
        del args[i:i + 2]
    {"head": head, "cut": cut, "show": show}[args[0]](args[1], runs)


main()
