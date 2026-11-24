"""A face for pixel art: drawn on purpose, not shrunk from a render. Needs numpy and nothing else.

A head pictured small loses its face. An eye is a centimetre of dark on a face 15 cm wide: on a sheet with a
pixel a centimetre across it is one pixel when it is lucky and none when it is not, the few colours of the
sheet pull it into the skin, and a different one is lost in every picture round the head. So the face is
not left to the render. A character has a recipe (scripts/impostor/faces/<character>.json) that says what
is on the face and where, as someone drawing it by hand would decide: two eyes, the brows, the mouth, a pair
of round spectacles, an eye patch. bake_impostor.py finds each of those on the head's surface once, and this
file draws it into every picture of the head, in whole pixels, never smaller than a size that is sure to show.

Places are in the head bone's own frame, as the picture from straight in front has them: x to the right of
the picture (the character's left), y up from the bone's head, z out of the face toward the eye.

A recipe:

    {"drawn_on": "detailed",               the model whose head the places were read off; the bake leaves the recipe
                                           off any other model of the character, whose features sit elsewhere
     "half_wide": 0.075,                   how far from the middle of the face to its side, metres
     "middle": 0.0,                        where the middle of the face is across (x)
     "colours": {"ink": [28, 23, 33],      names for colours (0 to 255, as the screen has them), or
                 "shade": {"like": "face", "times": [0.8, 0.7, 0.7]}},     ... a wash's found colour, darkened
     "marks": [
       {"name": "face", "kind": "wash", "x": [-0.05, 0.05], "y": [-0.09, 0.01], "colour": "found"},
       {"name": "eye_l", "kind": "block", "at": [0.03, -0.006], "size": [0.016, 0.016], "colour": "ink"},
       {"name": "glass_l", "kind": "ring", "at": [0.039, 0.041], "size": [0.047, 0.047], "rim_m": 0.01, "colour": "rim", "lens": "lens"},
       {"name": "patch", "kind": "disc", "at": [0.059, 0.056], "size": [0.065, 0.065], "colour": "ink"}]}

    wash    every pixel of the head's front inside a box takes one colour ("found": the middle one of the
            colours that are there, seen from the front): the smudges a generated texture has where the eyes should be are
            painted out before the eyes go on. "round": true makes the box an oval. "deep" is how far back
            from the front of the face it reaches (0.04).
    block   a rectangle of whole pixels
    disc    an oval
    ring    an oval rim, "rim_m" thick; "lens" fills the inside (left out: what is there stays)

"same" (optional) says which of the render's colours are one thing and should be one colour on the sheet:
[{"colours": [[84, 74, 65]], "as": [84, 65, 49]}] folds a grey that a texture has in brown hair into the brown.
It is used on the whole sheet, so name only colours that are nowhere else on the character.

"mesh": false on a mark keeps it off the character's mesh (gallery/face-marks.js lays the other marks on a mesh
shown as pixel art): a low-poly head that already models its eyes or its spectacles would get them twice.

Marks are drawn in the order given, later ones over earlier ones. A mark keeps to its own place on the head,
so it turns with it: seen from the side it is narrower, and from behind it is not drawn. Its pixels are only
drawn where the picture's surface is within the mark's "reach" of as far forward as the mark is, 8 cm unless the
mark says: enough that the far eye of a turned face is still drawn, on the flank of the nose that would hide it,
and that spectacles standing proud of the face do not hide the eyes behind them. It also means that something
only 3 to 8 cm in front, seen from above, does not hide a mark: a hat's brim close over the eyes, a fringe. A
character in a hat gives the marks under it "reach": 0.03, and they are hidden as they truly would be.
"""

import json
import math
import os

import numpy as np

FRONT, UP, RIGHT = np.array([0.0, 0.0, 1.0]), np.array([0.0, 1.0, 0.0]), np.array([1.0, 0.0, 0.0])
LEAN = 0.8          # how much the face turns aside toward the cheek: a mark at the edge of the face looks 39 degrees off
SEEN = 0.2          # a mark is drawn while it faces the eye by at least this (cosine)
SQUARE_ON = 0.5     # ... and at its full least size while it faces it by this
REACH_M = 0.08      # a mark's pixels are drawn where the surface is within this of the mark, toward or away, unless the mark
                    # gives a "reach" of its own. Measured on the three dancers, every picture of each head: seen from 45
                    # degrees round the nose stands 5 to 7 cm in front of the far eye, and Roosevelt's spectacles stand 3.5 to
                    # 6 cm proud of his eyes from most sides; those are drawn, as anyone drawing a turned face draws both
                    # eyes. The pirate's brim is 6 cm in front of his eye from above and to one side, which is why his marks
                    # carry a reach of 3 cm
DEEP_M = 0.04       # how far back from the front of the face a wash reaches
LEAST_M = 0.0156    # no mark is narrower or shorter than this: one big pixel of the picture at the crew camera's furthest


def least_for(ppm):
    """The least a mark may measure on a sheet this fine, in its pixels: a size on the head, not a count of pixels,
    so a head pictured at 96 a metre gets 2 and one at 192 gets 3."""
    return max(1, int(math.ceil(LEAST_M * ppm - 0.01)))  # rounded up: a pixel short of the size is a mark that drops out
FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "faces")


def unit(v):
    v = np.asarray(v, dtype=np.float64)
    return v / max(float(np.linalg.norm(v)), 1e-12)


def recipe_for(run):
    """The recipe for a run's character: faces/<the run's name without its date>.json, or None."""
    name = os.path.basename(os.path.normpath(run))
    parts = name.split("-")
    while parts and (parts[0][:1].isdigit() or parts[0][:1] == "T" and parts[0][1:3].isdigit()):
        parts = parts[1:]
    for slug in ("-".join(parts), name):
        path = os.path.join(FOLDER, slug + ".json")
        if os.path.isfile(path):
            with open(path) as f:
                return json.load(f)
    return None


def few_colours(pixels, count, keep=(), apart=16.0 / 255.0):
    """At most `count` colours for a set of pixels: the colours in `keep` first, which are in it whatever the
    pixels are (a face's own colours are not left to chance), then the ones the pixels are most made of.

    The pixels are cut into four times as many boxes of colour as are wanted (split at their middles, widest
    first), and from those the colours are picked one at a time: each time the one that the most pixels are
    furthest from everything picked so far. None is picked within `apart` of another. Picked plainly, most first,
    a render's faint mottling takes slot after slot (eight skins a hair apart, the line's own dark twice) and the
    sheet ends with fewer colours to tell things apart with, not more."""
    chosen = []
    for c in keep:
        c = np.asarray(c, dtype=np.float32)
        if not any(np.abs(c - k).max() < 0.5 / 255.0 for k in chosen):
            chosen.append(c)
    boxes, whole = [np.asarray(pixels, dtype=np.float32)], []
    while boxes and len(boxes) + len(whole) < 4 * count:
        widest = max(range(len(boxes)), key=lambda i: (boxes[i].max(axis=0) - boxes[i].min(axis=0)).max() * math.log(len(boxes[i]) + 1.0))
        box = boxes.pop(widest)
        spread = box.max(axis=0) - box.min(axis=0)
        channel = int(spread.argmax())
        if spread[channel] <= 0.0:
            whole.append(box)
            continue
        middle = np.median(box[:, channel])
        low = box[:, channel] <= middle
        if low.all():  # the middle is the top value (most of the box is one flat colour): split just under it
            low = box[:, channel] < middle
        boxes += [box[low], box[~low]]
    means = np.array([box.mean(axis=0) for box in boxes + whole], dtype=np.float32)
    weight = np.array([len(box) for box in boxes + whole], dtype=np.float64)
    far = np.full(len(means), np.inf) if not chosen else np.min([np.abs(means - c).max(axis=1) for c in chosen], axis=0)
    while len(chosen) < count:
        score = np.where(far >= apart, weight * np.minimum(far, 1.0) ** 2, -1.0)
        best = int(score.argmax())
        if score[best] < 0.0:
            break
        chosen.append(means[best])
        far = np.minimum(far, np.abs(means - means[best]).max(axis=1))
    return np.array(chosen, dtype=np.float32)


def folded(palette, same, near=12.0 / 255.0):
    """What each of the palette's colours is to be drawn as: itself, or, when a recipe's "same" names it (or a colour
    within `near` of it), the colour that rule says it is."""
    out = np.array(palette, dtype=np.float32)
    for i, c in enumerate(palette):
        for rule in same or []:
            if any(np.abs(c - np.asarray(named, dtype=np.float32) / 255.0).max() <= near for named in rule["colours"]):
                out[i] = np.asarray(rule["as"], dtype=np.float32) / 255.0
    return out


def snap(colour, palette, drawn_as=None):
    """Every pixel's colour moved to the nearest of the palette's (or to what that one is to be drawn as)."""
    flat = colour.reshape(-1, 3).astype(np.float32)
    out = np.empty_like(flat)
    final = palette if drawn_as is None else drawn_as
    for start in range(0, len(flat), 65536):
        piece = flat[start:start + 65536]
        out[start:start + 65536] = final[((piece[:, None, :] - palette[None]) ** 2).sum(axis=-1).argmin(axis=1)]
    return out.reshape(colour.shape)


def place(recipe, front_at):
    """The recipe's marks stood on the head: each gets where it is on the surface ("p") and which way the face looks
    there ("n"). front_at(x, y) is how far forward (z) the head's surface is at a place seen from the front, or None
    where there is no head. A mark that misses the head is left out."""
    half, middle = float(recipe.get("half_wide", 0.075)), float(recipe.get("middle", 0.0))
    out = []
    for mark in recipe.get("marks", []):
        mark = dict(mark)
        if mark["kind"] == "wash":
            (x0, x1), (y0, y1) = mark["x"], mark["y"]
            found = [front_at(x0 + (x1 - x0) * i / 4.0, y0 + (y1 - y0) * j / 4.0) for i in range(5) for j in range(5)]
            found = [z for z in found if z is not None]
            if not found:
                continue
            mark["front"] = round(float(max(found)), 4)
        else:
            x, y = mark["at"]
            z = front_at(x, y)
            if z is None:
                continue
            mark["p"] = [round(float(x), 4), round(float(y), 4), round(float(z), 4)]
            mark["n"] = [round(float(c), 4) for c in unit(FRONT + RIGHT * LEAN * (x - middle) / half)]
        out.append(mark)
    return out


def colour_of(name, colours, found):
    """A colour by name, as three numbers 0 to 1: from the recipe's list, or one a wash found, perhaps darkened."""
    spec = colours.get(name, name) if isinstance(name, str) else name
    if isinstance(spec, dict):
        base = colour_of(spec["like"], colours, found)
        return None if base is None else np.clip(base * np.asarray(spec.get("times", [1, 1, 1]), dtype=np.float32), 0.0, 1.0)
    if isinstance(spec, str):
        return found.get(spec)
    return np.asarray(spec, dtype=np.float32) / 255.0


def paint_of(mark, key, colours, found):
    """The colour a mark names under `key`, as three numbers 0 to 1, or None: "found" is what its own wash found."""
    if not mark.get(key):
        return None
    return found.get(mark["name"]) if mark[key] == "found" else colour_of(mark[key], colours, found)


def places(height, view, ppm, anchor):
    """Where every pixel of a picture is on the head, in the bone's frame (rows from the bottom up)."""
    d, r, u = (np.asarray(view[k], dtype=np.float64) for k in "dru")
    tall, wide = height.shape
    xs, ys = np.meshgrid((np.arange(wide) + 0.5 - anchor[0]) / ppm, (np.arange(tall) + 0.5 - anchor[1]) / ppm)
    return xs[..., None] * r + ys[..., None] * u + height[..., None] * d


def washed(mark, where, there):
    """The pixels a wash covers."""
    (x0, x1), (y0, y1) = mark["x"], mark["y"]
    inside = there & (where[..., 0] >= x0) & (where[..., 0] <= x1) & (where[..., 1] >= y0) & (where[..., 1] <= y1) & (where[..., 2] >= mark["front"] - mark.get("deep", DEEP_M))
    if mark.get("round"):
        inside &= ((where[..., 0] - (x0 + x1) / 2.0) / ((x1 - x0) / 2.0)) ** 2 + ((where[..., 1] - (y0 + y1) / 2.0) / ((y1 - y0) / 2.0)) ** 2 <= 1.0
    return inside


def find_colours(marks, colour, height, there, view, ppm, anchor):
    """What each "found" wash finds, from one picture (the one from the front): the middle colour of what is under it."""
    where = places(height, view, ppm, anchor)
    found = {}
    for mark in marks:
        if mark["kind"] == "wash" and mark.get("colour") == "found":
            under = colour[washed(mark, where, there)][:, :3]
            if len(under):
                found[mark["name"]] = np.median(under, axis=0).astype(np.float32)
    return found


def draw(colour, height, there, view, ppm, anchor, marks, colours, found, least_px=3):
    """Draw a face's marks into one picture of the head, in place. colour: rows from the bottom up, 0 to 1; height:
    how far each pixel's surface stands toward the eye, metres; there: where the head is; anchor: where the bone's
    head is in the picture, pixels. least_px: no mark is narrower or shorter than this (one less when it is seen
    well from the side). Returns {mark name: pixels drawn}."""
    d, r, u = (np.asarray(view[k], dtype=np.float64) for k in "dru")
    tall, wide = there.shape
    where = places(height, view, ppm, anchor)
    drawn = {}
    for mark in marks:
        paint = paint_of(mark, "colour", colours, found)
        if mark["kind"] == "wash":
            inside = washed(mark, where, there) if paint is not None else np.zeros_like(there)
            colour[inside, :3] = paint if paint is not None else 0.0
            drawn[mark["name"]] = int(inside.sum())
            continue
        p, n = np.asarray(mark["p"], dtype=np.float64), np.asarray(mark["n"], dtype=np.float64)
        facing = float(n @ d)
        drawn[mark["name"]] = 0
        if facing < SEEN or paint is None:
            continue
        across = unit(np.cross(UP, n))
        w, h = mark["size"]
        ends = [p + across * sx * w / 2.0 + UP * sy * h / 2.0 for sx in (-1, 1) for sy in (-1, 1)]
        px, py = [float(e @ r) * ppm for e in ends], [float(e @ u) * ppm for e in ends]
        wpx = max(least_px if facing >= SQUARE_ON else least_px - 1, int(round(max(px) - min(px))))
        hpx = max(least_px, int(round(max(py) - min(py))))
        x0 = int(round(float(p @ r) * ppm + anchor[0] - wpx / 2.0))
        y0 = int(round(float(p @ u) * ppm + anchor[1] - hpx / 2.0))
        ys, xs = np.meshgrid(np.arange(y0, y0 + hpx), np.arange(x0, x0 + wpx), indexing="ij")
        ok = (xs >= 0) & (xs < wide) & (ys >= 0) & (ys < tall)
        cy, cx = np.clip(ys, 0, tall - 1), np.clip(xs, 0, wide - 1)
        ok &= there[cy, cx] & (np.abs(height[cy, cx] - float(p @ d)) < mark.get("reach", REACH_M))
        # how far out from the middle of the mark each pixel is: 1 at the edge of the oval
        out = np.sqrt(((xs - x0 + 0.5 - wpx / 2.0) / (wpx / 2.0)) ** 2 + ((ys - y0 + 0.5 - hpx / 2.0) / (hpx / 2.0)) ** 2)
        oval = out <= (1.0 if min(wpx, hpx) > 4 else 2.0)  # a mark of a few pixels stays a block: an oval that small is a cross
        if mark["kind"] == "block":
            colour[cy[ok], cx[ok], :3] = paint
            drawn[mark["name"]] = int(ok.sum())
        elif mark["kind"] == "disc":
            colour[cy[ok & oval], cx[ok & oval], :3] = paint
            drawn[mark["name"]] = int((ok & oval).sum())
        elif mark["kind"] == "ring":
            rim = max(1, int(round(mark.get("rim_m", 0.01) * ppm)))
            inner = np.sqrt(((xs - x0 + 0.5 - wpx / 2.0) / max(wpx / 2.0 - rim, 0.5)) ** 2 + ((ys - y0 + 0.5 - hpx / 2.0) / max(hpx / 2.0 - rim, 0.5)) ** 2) <= 1.0
            lens = paint_of(mark, "lens", colours, found)
            if lens is not None:
                colour[cy[ok & oval & inner], cx[ok & oval & inner], :3] = lens
            colour[cy[ok & oval & ~inner], cx[ok & oval & ~inner], :3] = paint
            drawn[mark["name"]] = int((ok & oval & ~inner).sum())
        else:
            raise ValueError("a mark is a wash, a block, a disc or a ring, not %r" % mark["kind"])
    return drawn


def kept_colours(marks, colours, found):
    """The colours a face is drawn in: these go into the sheet's few colours whatever else does."""
    out = []
    for mark in marks:
        for key in ("colour", "lens"):
            paint = paint_of(mark, key, colours, found)
            if paint is not None and not any(np.abs(paint - c).max() < 0.5 / 255.0 for c in out):
                out.append(np.asarray(paint, dtype=np.float32))
    return out


def for_page(marks, colours, found):
    """The marks as the page wants them, to draw the same face on a mesh: each with its place, the way it faces,
    its size and its colours as numbers. Washes are left out (a mesh has no smudges to paint over)."""
    out = []
    for mark in marks:
        if mark["kind"] == "wash" or mark.get("mesh") is False:
            continue
        paint, lens = paint_of(mark, "colour", colours, found), paint_of(mark, "lens", colours, found)
        if paint is None:
            continue
        out.append({"name": mark["name"], "kind": mark["kind"], "p": mark["p"], "n": mark["n"], "size": mark["size"], "rim_m": mark.get("rim_m", 0.01) if mark["kind"] == "ring" else 0.0,
                    "colour": [int(round(float(c) * 255)) for c in paint], "lens": [int(round(float(c) * 255)) for c in lens] if lens is not None else None})
    return out
