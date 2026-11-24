"""One part's pictures off a baked sheet, blown up and laid in a row, a row for each sheet given: to look at faces.

    python3 scripts/impostor/head_sheet.py out.png 8 <run>/profiles/detailed-impostor-pixel-faces[:head] ... [--views 8,9,10]

The number is how many times a pixel of a 96-a-metre sheet is blown up; a finer sheet or part is blown up less, so
every row shows its head the same size. Views 8 to 15 are the eight from around at eye height, 8 from the front.
Needs numpy (Blender's Python has it).
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import impostor

args = sys.argv[1:]
views = [8, 9, 10, 11, 12, 13, 14, 15]
if "--views" in args:
    i = args.index("--views"); views = [int(v) for v in args[i + 1].split(",")]; del args[i:i + 2]
out, scale, folders = args[0], int(args[1]), args[2:]
rows = []
for spec in folders:
    folder, _, part = spec.partition(":")
    part = part or "head"
    card = json.load(open(folder + "/impostor.json"))
    s = card["sets"][card["default_views"]]
    sheet = impostor.read_png(folder + "/" + s["color"])
    if sheet.dtype != np.uint8:
        sheet = np.round(np.clip(sheet, 0, 1) * 255).astype(np.uint8)
    pics = []
    for v in views:
        x, y, w, h = s["cells"][part][v][:4]
        # cells are from the sheet's bottom left; find out which way read_png hands rows back
        pic = sheet[y:y + h, x:x + w][::-1]
        k = max(1, int(round(scale * 96.0 / (next(p for p in card["parts"] if p["name"] == part).get("px_per_m") or card["px_per_m"]))))
        pic = np.repeat(np.repeat(pic, k, 0), k, 1)
        pics.append(pic)
    th = max(p.shape[0] for p in pics)
    row = []
    for p in pics:
        pad = np.full((th, p.shape[1] + 8, 4), 255, np.uint8); pad[..., :3] = (120, 160, 120)
        a = p[..., 3:4] / 255.0
        pad[th - p.shape[0]:, 4:4 + p.shape[1], :3] = (p[..., :3] * a + pad[th - p.shape[0]:, 4:4 + p.shape[1], :3] * (1 - a)).astype(np.uint8)
        row.append(pad)
    rows.append(np.concatenate(row, 1))
tw = max(r.shape[1] for r in rows)
full = []
for r in rows:
    pad = np.full((r.shape[0] + 8, tw, 4), 255, np.uint8); pad[..., :3] = (120, 160, 120)
    pad[4:4 + r.shape[0], :r.shape[1]] = r
    full.append(pad)
img = np.concatenate(full, 0)
impostor.write_png(out, img[::-1])
print(out, img.shape)
