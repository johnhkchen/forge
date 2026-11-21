"""Lettering: where the balloons, captions and sound effects go on a drawn panel. Plain Python, no Blender.

The words stay text. This works out, for one panel, a box for each balloon and a tail from it to its speaker,
from two things the renderer wrote down: how big the picture is and where each head is in it. Rules it keeps:

  - a balloon never covers a face (any face, not only its speaker's), nor another balloon, nor the caption;
  - a tail points at its speaker's head and stops just short of it, and does not cross anyone else's face;
  - balloons read in order: a later one is never above and to the left of an earlier one;
  - everything stays inside the panel;
  - a thought from someone whose head is not in the picture (a panel seen through their own eyes) is lettered as
    a voice: a dark bar along the bottom, like a film's subtitle, with no tail to point anywhere.

When the words do not fit, the type is made a little smaller, three times at most; after that the panel is
reported as too wordy, which is the script's fault, not the picture's.

`letter(meta, panel)` returns the layout as data; `to_svg(layout, size)` draws it as SVG to lay over the picture.
"""

import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "font_widths.json")) as _f:
    WIDTHS = json.load(_f)["fonts"]

BALLOON_FONT = "Comic Neue"
SFX_FONT = "Bangers"
TYPE = 0.036          # balloon type size, as a share of the panel's width
LINE = 1.16           # line height, in type sizes
PAD = (0.75, 0.5)     # room round the words inside a balloon, in type sizes
EDGE = 0.022          # balloons keep this far from the panel's edge, as a share of its width
FACE_CLEAR = 1.12     # a face is its head circle grown by this
GAP = 0.012           # between balloons, as a share of the width
SHRINKS = 3
INK = "#1c1917"


def text_width(text, size, font=BALLOON_FONT):
    table = WIDTHS[font]
    return sum(table.get(ch, table["default"]) for ch in text) * size


def wrap(text, size, most):
    """Break text into lines no wider than `most` pixels (a single long word gets a line of its own)."""
    lines, line = [], ""
    for word in text.split():
        trial = (line + " " + word).strip()
        if line and text_width(trial, size) > most:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


def best_wrap(text, size, widest):
    """The wrap whose shape is closest to a comfortable balloon: about twice as wide as tall."""
    best = None
    for share in (0.3, 0.38, 0.46, 0.54, 0.62, 0.7, 0.8, 1.0):
        lines = wrap(text, size, widest * share)
        wide = max(text_width(l, size) for l in lines)
        if wide > widest:
            continue
        tall = len(lines) * size * LINE
        off = abs(math.log((wide + 2 * PAD[0] * size) / ((tall + 2 * PAD[1] * size) * 1.9)))
        if best is None or off < best[0]:
            best = (off, lines, wide, tall)
    if best is None:
        lines = wrap(text, size, widest)
        return lines, max(text_width(l, size) for l in lines), len(lines) * size * LINE
    return best[1], best[2], best[3]


def overlap(a, b, gap=0.0):
    """Do two boxes [x, y, w, h] touch, with `gap` between them?"""
    return a[0] < b[0] + b[2] + gap and b[0] < a[0] + a[2] + gap and a[1] < b[1] + b[3] + gap and b[1] < a[1] + a[3] + gap


def box_hits_circle(box, center, radius):
    nx = min(max(center[0], box[0]), box[0] + box[2])
    ny = min(max(center[1], box[1]), box[1] + box[3])
    return (nx - center[0]) ** 2 + (ny - center[1]) ** 2 < radius * radius


def segment_hits_circle(a, b, center, radius):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((center[0] - a[0]) * dx + (center[1] - a[1]) * dy) / length))
    px, py = a[0] + t * dx, a[1] + t * dy
    return (px - center[0]) ** 2 + (py - center[1]) ** 2 < radius * radius


def nearest_on_box(box, point):
    return [min(max(point[0], box[0]), box[0] + box[2]), min(max(point[1], box[1]), box[1] + box[3])]


def tail_for(box, head, size):
    """A tail from the balloon toward the head: [root left, tip, root right]. The tip stops just outside the face."""
    cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
    aim = head.get("mouth") or head["center"]
    # Point at the mouth, but stop on the head's rim: the face itself stays clear.
    dx, dy = cx - head["center"][0], cy - head["center"][1]
    far = math.hypot(dx, dy) or 1.0
    rim = head["radius"] * FACE_CLEAR
    tip = [head["center"][0] + dx / far * rim, head["center"][1] + dy / far * rim]
    toward = [aim[0] * 0.35 + tip[0] * 0.65, aim[1] * 0.35 + tip[1] * 0.65]
    back = math.hypot(toward[0] - head["center"][0], toward[1] - head["center"][1])
    if back >= rim:  # only lean toward the mouth while that keeps the tip off the face
        tip = toward
    # The root sits inside the balloon, on the line from its middle to the tip.
    reach = math.hypot(tip[0] - cx, tip[1] - cy) or 1.0
    ux, uy = (tip[0] - cx) / reach, (tip[1] - cy) / reach
    inset = nearest_on_box([box[0] + box[2] * 0.2, box[1] + box[3] * 0.25, box[2] * 0.6, box[3] * 0.5], tip)
    half = size * 0.32
    return [[round(inset[0] - uy * half, 1), round(inset[1] + ux * half, 1)], [round(tip[0], 1), round(tip[1], 1)],
            [round(inset[0] + uy * half, 1), round(inset[1] - ux * half, 1)]]


def place_one(text_box, speaker, heads, taken, earlier, size, panel, bodies):
    """The best spot for one balloon: the lowest-cost box that breaks no rule, or None."""
    wide, tall = panel
    w, h = text_box
    edge = EDGE * wide
    head = heads.get(speaker)
    step = wide / 28.0
    best = None
    y = edge
    while y + h <= tall - edge:
        x = edge
        while x + w <= wide - edge:
            box = [x, y, w, h]
            ok = not any(box_hits_circle(box, f["center"], f["radius"] * FACE_CLEAR) for f in heads.values())
            ok = ok and not any(overlap(box, t, GAP * wide) for t in taken)
            # Reading order: never above-and-left of a balloon that is read before it.
            ok = ok and not any(y + h / 2 < e[1] + e[3] / 2 - 1 and x + w / 2 < e[0] + e[2] / 2 for e in earlier)
            ok = ok and not any(y + h < e[1] + e[3] * 0.25 for e in earlier)
            tail = None
            if ok and head:
                tail = tail_for(box, head, size)
                root = [(tail[0][0] + tail[2][0]) / 2, (tail[0][1] + tail[2][1]) / 2]
                others = [f for who, f in heads.items() if who != speaker]
                ok = not any(segment_hits_circle(root, tail[1], f["center"], f["radius"] * FACE_CLEAR) for f in others)
                ok = ok and not any(segment_hits_circle(root, tail[1], [t[0] + t[2] / 2, t[1] + t[3] / 2], min(t[2], t[3]) / 2) for t in taken)
            if ok:
                cost = 0.0
                if head:
                    near = nearest_on_box(box, head["center"])
                    away = math.hypot(near[0] - head["center"][0], near[1] - head["center"][1])
                    cost += abs(away - head["radius"] * 1.5) * 1.0          # close to the speaker, not on top of it
                    cost += max(0.0, (y + h) - (head["center"][1] - head["radius"] * 0.6)) * 0.8   # above the face reads best
                    cost += abs((x + w / 2) - head["center"][0]) * 0.25     # roughly over the speaker
                cost += y * 0.12
                for e in earlier:  # the first to speak is read first when its balloon is the higher one
                    cost += max(0.0, (e[1] + e[3] / 2) - (y + h / 2)) * 1.5
                for who, body in (bodies or {}).items():                     # covering a body is allowed, but costs
                    bx = max(0.0, min(x + w, body[2]) - max(x, body[0]))
                    by = max(0.0, min(y + h, body[3]) - max(y, body[1]))
                    cost += bx * by / (w * h) * 60.0
                if best is None or cost < best[0]:
                    best = (cost, box, tail)
            x += step
        y += step
    return best


def letter(meta, panel):
    """Lay out one panel's lettering. `meta` is the panel's entry in panels.json; `panel` its entry in comic.json."""
    wide, tall = meta["size"]
    heads = meta.get("heads") or {}
    problems = []
    lines = panel.get("lines") or []
    layout = None
    for shrink in range(SHRINKS + 1):
        size = wide * TYPE * (0.9 ** shrink)
        taken, caption = [], None
        if panel.get("caption"):
            text = wrap(panel["caption"], size * 0.9, wide * 0.62)
            cw = max(text_width(l, size * 0.9) for l in text) + size * 1.1
            ch = len(text) * size * 0.9 * LINE + size * 0.7
            box = [EDGE * wide, EDGE * wide, cw, ch]
            if any(box_hits_circle(box, f["center"], f["radius"] * FACE_CLEAR) for f in heads.values()):
                box[1] = tall - EDGE * wide - ch  # a face is up there: the caption goes to the bottom
            caption = {"lines": text, "box": [round(v, 1) for v in box], "size": round(size * 0.9, 1)}
            taken.append(box)
        balloons, earlier, failed = [], [], False
        # The voice of whoever's eyes these are: bars stacked up from the bottom, the first one read on top.
        voices = [l for l in lines if l["who"] not in heads and l.get("how", "say") == "think"]
        bottom = tall - EDGE * wide * 1.6
        placed_voices = {}
        for line in reversed(voices):
            type_size = size * 0.95
            words = wrap(line["says"], type_size, wide * 0.8)
            w = max(text_width(l, type_size) for l in words) + 2 * PAD[0] * type_size
            h = len(words) * type_size * LINE + 2 * PAD[1] * 0.7 * type_size
            box = [(wide - w) / 2, bottom - h, w, h]
            if box[1] < tall * 0.45 or any(box_hits_circle(box, f["center"], f["radius"] * FACE_CLEAR) for f in heads.values()):
                failed = True
                break
            bottom = box[1] - GAP * wide
            taken.append(box)
            placed_voices[id(line)] = {"who": line["who"], "how": "voice", "lines": words, "box": [round(v, 1) for v in box], "tail": None,
                                       "size": round(type_size, 1)}
        for line in lines:
            if failed:
                break
            if id(line) in placed_voices:
                balloons.append(placed_voices[id(line)])
                continue
            how = line.get("how", "say")
            type_size = size * (1.14 if how == "shout" else 0.92 if how == "whisper" else 1.0)
            words, tw, th = best_wrap(line["says"], type_size, wide * 0.6)
            w, h = tw + 2 * PAD[0] * type_size, th + 2 * PAD[1] * type_size
            found = place_one((w, h), line["who"], heads, taken, earlier, type_size, (wide, tall), meta.get("bodies"))
            if found is None:
                failed = True
                break
            _, box, tail = found
            taken.append(box)
            earlier.append(box)
            balloons.append({"who": line["who"], "how": how, "lines": words, "box": [round(v, 1) for v in box], "tail": tail,
                             "size": round(type_size, 1)})
        if not failed:
            layout = {"balloons": balloons, "caption": caption, "type": round(size, 1), "shrunk": shrink}
            break
    if layout is None:
        said = sum(len(l["says"]) for l in lines)
        problems.append("too wordy for the picture: %d characters in %d balloons would not fit clear of the faces" % (said, len(lines)))
        layout = {"balloons": [], "caption": None, "type": round(wide * TYPE, 1), "shrunk": SHRINKS}
    layout["sfx"] = place_sfx(panel.get("sfx"), (wide, tall), heads, [b["box"] for b in layout["balloons"]] + ([layout["caption"]["box"]] if layout["caption"] else []))
    layout["problems"] = problems
    return layout


def place_sfx(word, panel, heads, taken):
    """A sound effect goes in whichever corner is emptiest, tilted."""
    if not word:
        return None
    wide, tall = panel
    size = wide * 0.115
    w, h = text_width(word, size, SFX_FONT) * 1.05, size * 1.0
    if w > wide * 0.6:
        size *= wide * 0.6 / w
        w, h = wide * 0.6, size
    edge = wide * 0.05
    best = None
    for n, (x, y, tilt) in enumerate(((wide - w - edge, tall - h - edge, -8), (edge, tall - h - edge, 7), (wide - w - edge, edge, 8), (edge, edge, -7),
                                      (wide / 2 - w / 2, tall - h - edge, -5))):
        box = [x, y, w, h]
        cost = n * 0.01
        cost += sum(4.0 for f in heads.values() if box_hits_circle(box, f["center"], f["radius"] * FACE_CLEAR))
        cost += sum(2.0 for t in taken if overlap(box, t))
        if best is None or cost < best[0]:
            best = (cost, box, tilt)
    return {"word": word, "box": [round(v, 1) for v in best[1]], "size": round(size, 1), "tilt": best[2], "clear": best[0] < 1.0}


def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def balloon_shapes(b, stroke):
    """A balloon as SVG shapes, drawn twice by the caller: once in ink a little fat, once in white on top,
    so the balloon and its tail read as one outline."""
    x, y, w, h = b["box"]
    r = min(w, h) * 0.46
    shapes = ['<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%.1f"/>' % (x, y, w, h, r)]
    tail = b.get("tail")
    if tail and b["how"] == "think":
        # A thought: little bubbles walking from the balloon to the head.
        root = [(tail[0][0] + tail[2][0]) / 2, (tail[0][1] + tail[2][1]) / 2]
        edge = nearest_on_box([x, y, w, h], tail[1])
        for i, t in enumerate((0.22, 0.55, 0.85)):
            cx = edge[0] + (tail[1][0] - edge[0]) * t
            cy = edge[1] + (tail[1][1] - edge[1]) * t
            shapes.append('<circle cx="%.1f" cy="%.1f" r="%.1f"/>' % (cx, cy, b["size"] * (0.34 - 0.08 * i)))
        del root
    elif tail:
        shapes.append('<polygon points="%s"/>' % " ".join("%.1f,%.1f" % (p[0], p[1]) for p in tail))
    return shapes


def to_svg(layout, size):
    """The lettering as one SVG to lay over the picture. The words are text, in the comic font."""
    wide, tall = size
    stroke = max(2.0, wide * 0.0045)
    out = ['<svg class="lettering" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" role="group" aria-label="lettering">' % (wide, tall)]
    cap = layout.get("caption")
    if cap:
        x, y, w, h = cap["box"]
        out.append('<g class="caption"><rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%.1f" fill="#fff3c4" stroke="%s" stroke-width="%.1f"/>'
                   % (x, y, w, h, cap["size"] * 0.25, INK, stroke))
        for i, line in enumerate(cap["lines"]):
            out.append('<text x="%.1f" y="%.1f" font-size="%.1f" font-style="italic">%s</text>'
                       % (x + cap["size"] * 0.55, y + cap["size"] * (0.35 + 0.82) + i * cap["size"] * LINE, cap["size"], esc(line)))
        out.append("</g>")
    for b in layout["balloons"]:
        if b["how"] == "voice":
            x, y, w, h = b["box"]
            out.append('<g class="balloon voice" data-who="%s"><rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%.1f" fill="#1c1917" fill-opacity="0.78"/>'
                       % (esc(b["who"]), x, y, w, h, b["size"] * 0.3))
            first = y + (h - len(b["lines"]) * b["size"] * LINE) / 2 + b["size"] * 0.9
            for i, line in enumerate(b["lines"]):
                out.append('<text class="voice" x="%.1f" y="%.1f" font-size="%.1f" text-anchor="middle" font-style="italic">%s</text>'
                           % (x + w / 2, first + i * b["size"] * LINE, b["size"], esc(line)))
            out.append("</g>")
            continue
        shapes = balloon_shapes(b, stroke)
        dash = ' stroke-dasharray="%.1f %.1f"' % (stroke * 2.2, stroke * 1.8) if b["how"] == "whisper" else ""
        fat = stroke * (3.0 if b["how"] == "shout" else 2.0)
        out.append('<g class="balloon %s" data-who="%s">' % (b["how"], esc(b["who"])))
        out.append('<g fill="%s" stroke="%s" stroke-width="%.1f" stroke-linejoin="round"%s>%s</g>' % (INK, INK, fat, dash, "".join(shapes)))
        out.append('<g fill="#fffdf8">%s</g>' % "".join(shapes))
        x, y, w, h = b["box"]
        first = y + (h - len(b["lines"]) * b["size"] * LINE) / 2 + b["size"] * 0.9
        weight = ' font-style="italic"' if b["how"] == "think" else ""
        for i, line in enumerate(b["lines"]):
            out.append('<text x="%.1f" y="%.1f" font-size="%.1f" text-anchor="middle"%s>%s</text>'
                       % (x + w / 2, first + i * b["size"] * LINE, b["size"], weight, esc(line)))
        out.append("</g>")
    sfx = layout.get("sfx")
    if sfx:
        x, y, w, h = sfx["box"]
        out.append('<text class="sfx" x="%.1f" y="%.1f" font-size="%.1f" text-anchor="middle" transform="rotate(%d %.1f %.1f)" '
                   'fill="#ffd23f" stroke="%s" stroke-width="%.1f" paint-order="stroke" stroke-linejoin="round">%s</text>'
                   % (x + w / 2, y + h * 0.84, sfx["size"], sfx["tilt"], x + w / 2, y + h / 2, INK, stroke * 2.2, esc(sfx["word"])))
    out.append("</svg>")
    return "".join(out)
