"""The screen test: every headshot of a part measured, free and on this Mac, on what its breakdown says matters,
so the shortlist is picked on evidence and only the best few are paid for.

    just casting-screen <role>
    (uv run --no-project --python 3.12 --with pillow --with numpy --with scipy python scripts/casting/screen.py <role>
         [--runs runs] [--root casting])

It reads casting/<role>/role.json and every picture in casting/<role>/headshots/ (tin-toy.png is a look's first
picture, tin-toy.2.png its second), and the cast's own pictures (every character in runs/, each drawn the same way,
front on in a T-pose), and writes:

    casting/<role>/screen.json              every headshot's scores and the numbers behind them, ranked
    casting/<role>/screen/<shot>-crew.png   the figure as the crew camera sees it: its true size at CREW_PX_PER_M
                                            big pixels a metre, every colour snapped to the 32 it is most made of,
                                            as the pixel look draws it
    casting/<role>/screen/<shot>-face.png   its head on the head's own finer grid (HEAD_GRID times finer), the same way
    casting/<role>/screen-contact-sheet.png all of them on one page with their scores, the cast's outlines beside

What it measures, each 0 to 1 (1 is best), from the picture alone:

  builds        TRELLIS can build it: one figure, whole in frame on a plain background, front on (it is as wide on
                the left as on the right), arms straight out in a T (a thin band of arm in the upper half, wide
                apart from the legs)
  stands apart  its outline at the crew camera's size, feet on the same floor, against every cast member's: how
                little it shares with the nearest (1 minus the most it shares), and how square its head is
  face          the head shrunk to the crew camera's grid and snapped to its colours: is there a dark face plate,
                are there two light eyes on it, level, apart, how many pixels wide, how much lighter than the
                plate; and how many bars of the grille are still there
  colours       how much of the figure is the breakdown's five colours, whether its main colour is the one the
                breakdown asks for, and how far its main colour is from every cast member's
  cards         nothing thin or loose: how much of the outline is thinner than THIN_CM (wires, antennae, fingers,
                springs), which is where cards come apart

and flags what the breakdown rules out that a picture can show: shine (chrome, glass, a glow) and something held at
the end of an arm. Each flag takes FLAG_COST off the total. Text, a menacing face and the rest need eyes: see
`vision` in screen.json, when it was asked.

The total is a weighted sum (WEIGHTS). Every number is a measurement of a picture, not of the 3D build: the mesh
screen (casting.py screen-3d) is the next look, and the take's camera test the last.
"""

import json
import math
import os
import re
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

CREW_PX_PER_M = 100     # big pixels a metre through the candy-shop set's crew camera (a face 13 to 18 wide, README "Looks")
HEAD_GRID = 2           # the pixel look draws a head this many times finer than the body (bake_impostor --head-px 2)
PALETTE_COLOURS = 32    # the pixel sheet keeps the 32 colours a character is most made of
WORK_PX = 512           # pictures are measured at this size (the face is cut from the full picture)
BACKGROUND_OFF = 26     # how far (sum of R, G, B off) a pixel may be from the background's own colour and still be it
MATCH_DE = 22           # a colour this close (CIE76) to one of the breakdown's is that colour
THIN_CM = 3             # parts thinner than this are wires and antennae, not limbs
SHAPE_PX = 64           # outlines compared by shape alone are brought to this height
STICKS_UP_CM = 4         # a thin thing rising more than this above the head is an antenna, a stalk
CROWN_CM = 9             # the head (or a hat) starts at the first row this wide; anything narrower above it sticks up
NECK_ROWS = 7            # rows evened out when looking for the neck
HOLE_SHARE = 0.0004     # background inside the figure bigger than this share of the picture is a gap, not a hole to fill
LOOK_PX = 384           # the small copy of each headshot a vision model is shown
KEEP_PX, KEEP_Q = 1024, 90  # the headshot git keeps: a 1024-pixel JPEG (about 65 KB); Codex's PNG stays in headshots/full/
HANGING = ("apron", "skirt", "cape", "cloak", "scarf", "tunic", "tails", "ribbon", "tassel", "robe", "kilt", "hangs", "loose")
HANGS_COST = 0.7         # the cards score of a look whose brief has cloth that hangs
HAZE_OFF, HAZE_SHARE, HAZE_CHROMA = 60, 0.05, 6   # a grey pixel this near the background's colour inside the outline is haze; this much of it is a flag
PIECE_SHARE = 0.03       # a piece of the figure this big against the biggest is part of it; smaller ones are stray bits
SHINE_L, SHINE_C = 93, 9   # lightness and colourfulness of a glint: nearly white, nearly grey
WEIGHTS = {"builds": 0.2, "stands_apart": 0.2, "face": 0.25, "colours": 0.2, "cards": 0.15}
FLAG_COST = 0.1
NAMES = {"builds": "Builds", "stands_apart": "Stands apart", "face": "Face", "colours": "Colours", "cards": "Cards"}


# ---------- pictures ----------

def load(path, size=None):
    img = Image.open(path).convert("RGB")
    if size:
        img = img.resize((size, size), Image.BOX)
    return np.asarray(img).astype(np.float32)


def background(rgb):
    """The background's own colour at every pixel: a smooth fit (a + bx + cy + dx² + ey² + fxy) to the border."""
    h, w, _ = rgb.shape
    edge = max(2, h // 50)
    ys, xs = np.mgrid[0:h, 0:w]
    border = np.zeros((h, w), bool)
    border[:edge], border[-edge:], border[:, :edge], border[:, -edge:] = True, True, True, True
    terms = lambda y, x: np.stack([np.ones_like(x), x, y, x * x, y * y, x * y], -1)
    a = terms(ys[border] / h, xs[border] / w)
    fit = np.linalg.lstsq(a, rgb[border], rcond=None)[0]
    return terms(ys / h, xs / w) @ fit, float(np.abs(rgb[border] - (a @ fit)).sum(-1).mean())


def figure(rgb):
    """The figure: everything not joined to the border through background-coloured pixels, its largest piece, small
    holes filled (a big patch of background inside it, under a headset's band, stays background). Returns (mask, how
    much of what is not background lies outside that piece, how plain the background is)."""
    bg, rough = background(rgb)
    like = np.abs(rgb - bg).sum(-1) < BACKGROUND_OFF
    labels, _ = ndimage.label(like)
    edge = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    outside = np.isin(labels, edge[edge > 0])
    inner = like & ~outside
    holes, n_holes = ndimage.label(inner)
    if n_holes:
        hole_sizes = ndimage.sum(inner, holes, range(1, n_holes + 1))
        outside |= np.isin(holes, 1 + np.where(hole_sizes > HOLE_SHARE * like.size)[0])
    stuff = ~outside
    stuff = ndimage.binary_opening(stuff, iterations=1)
    pieces, n = ndimage.label(stuff)
    if not n:
        return np.zeros_like(stuff), 1.0, rough
    sizes = ndimage.sum(stuff, pieces, range(1, n + 1))
    # the figure is every big piece: a light paint shaded nearly to the background's grey can cut a neck or a thigh
    big = np.where(sizes >= PIECE_SHARE * sizes.max())[0]
    main = np.isin(pieces, 1 + big)
    stray = 1.0 - sizes[big].sum() / max(1.0, sizes.sum())
    filled = ndimage.binary_fill_holes(main)
    return filled & ~(outside & ~main), float(stray), rough


def box(mask):
    rows, cols = np.where(mask.any(1))[0], np.where(mask.any(0))[0]
    return int(rows[0]), int(rows[-1]) + 1, int(cols[0]), int(cols[-1]) + 1


def lab(rgb):
    """sRGB 0..255 to CIE Lab."""
    c = rgb / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ np.array([[0.4124, 0.2126, 0.0193], [0.3576, 0.7152, 0.1192], [0.1805, 0.0722, 0.9505]])
    xyz = xyz / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def hex_rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32)


def palette_of(pixels, n):
    """The n colours a set of pixels is most made of, with their shares (PIL's median cut, as the pixel sheet's)."""
    side = int(math.ceil(math.sqrt(len(pixels))))
    pad = np.zeros((side * side, 3), np.uint8)
    pad[:len(pixels)] = pixels.astype(np.uint8)
    pad[len(pixels):] = pixels[0].astype(np.uint8) if len(pixels) else 0
    img = Image.fromarray(pad.reshape(side, side, 3)).quantize(n, method=Image.Quantize.MEDIANCUT)
    pal = np.array(img.getpalette()[:3 * n], np.float32).reshape(-1, 3)
    counts = np.bincount(np.asarray(img).ravel()[:len(pixels)], minlength=len(pal))
    keep = counts > 0
    return pal[keep], counts[keep] / max(1, counts.sum())


def snap(rgb, pal):
    """Every pixel to the nearest of the palette's colours."""
    d = ((rgb[..., None, :] - pal) ** 2).sum(-1)
    return pal[d.argmin(-1)]


# ---------- one figure, measured ----------

class Figure:
    """A character picture: its outline at the working size, its true height, and the crew camera's view of it."""

    def __init__(self, path, height_m):
        self.path, self.height_m = path, float(height_m)
        self.full = load(path)
        self.rgb = load(path, WORK_PX)
        self.mask, self.stray, self.rough = figure(self.rgb)
        self.bg = background(self.rgb)[0]
        self.top, self.bottom, self.left, self.right = box(self.mask)
        self.tall = self.bottom - self.top
        self.px_per_m = self.tall / self.height_m

    def crew_mask(self):
        """Its outline at its true size through the crew camera, feet at the bottom, centred."""
        crop = self.mask[self.top:self.bottom, self.left:self.right]
        k = CREW_PX_PER_M / self.px_per_m
        h, w = max(1, round(crop.shape[0] * k)), max(1, round(crop.shape[1] * k))
        return np.asarray(Image.fromarray((crop * 255).astype(np.uint8)).resize((w, h), Image.BOX)) > 127

    def crew_picture(self, grid=1, rows=None):
        """The figure (or some of its rows, at the working size) at the crew camera's size times `grid`, its colours
        snapped to the 32 it is most made of. Returns RGBA."""
        top, bottom = rows or (self.top, self.bottom)
        scale = self.full.shape[0] / WORK_PX
        crop_rgb = self.full[int(top * scale):int(bottom * scale), int(self.left * scale):int(self.right * scale)]
        crop_mask = self.mask[top:bottom, self.left:self.right]
        k = grid * CREW_PX_PER_M / self.px_per_m
        h, w = max(1, round(crop_mask.shape[0] * k)), max(1, round(crop_mask.shape[1] * k))
        small = np.asarray(Image.fromarray(crop_rgb.astype(np.uint8)).resize((w, h), Image.BOX)).astype(np.float32)
        alpha = np.asarray(Image.fromarray((crop_mask * 255).astype(np.uint8)).resize((w, h), Image.BOX)) > 127
        pal, _ = palette_of(self.rgb[self.mask], PALETTE_COLOURS)
        out = np.zeros((h, w, 4), np.uint8)
        out[..., :3] = snap(small, pal).astype(np.uint8)
        out[..., 3] = alpha * 255
        return out

    def widths(self):
        return self.mask.sum(1)

    def arms(self):
        """The rows the arms are in: as wide as the figure gets, near enough (a T-pose's widest band)."""
        widths = self.widths()
        span = widths.max()
        rows = np.where(widths >= 0.8 * span)[0]
        return int(rows[0]), int(rows[-1]) + 1, int(span)

    def crown(self):
        """The first row of the head proper: below anything thin that sticks up from it (an antenna, a stalk)."""
        arm_top, _, span = self.arms()
        # only the middle of the picture counts, so hands that turn up at the ends of the arms are not the head
        middle = (self.left + self.right) // 2
        cols = slice(max(0, middle - span // 4), middle + span // 4)
        widths = self.mask[self.top:arm_top, cols].sum(1)
        if not len(widths) or not widths.max():
            return self.top
        # a hat's crown is soon wider than CROWN_CM; a stalk and the ball on it are not
        wide = np.where(widths >= min(0.45 * widths.max(), CROWN_CM / 100 * self.px_per_m))[0]
        return self.top + int(wide[0]) if len(wide) else self.top

    def head(self):
        """The head's rows: from its crown down to the neck (the narrowest row above the arms), or the top 60% of what
        is above the arms when there is no neck."""
        arm_top, _, _ = self.arms()
        # rows evened out over a few, so one ragged row (a JPEG edge, a wisp of shadow) is not taken for the neck
        widths = np.convolve(self.widths(), np.ones(NECK_ROWS) / NECK_ROWS, mode="same")
        top = self.crown()
        above = arm_top - top
        if above < 6:
            return top, top + max(4, self.tall // 5)
        band = widths[top + above // 2:arm_top]
        neck = top + above // 2 + int(np.argmin(band)) if len(band) else arm_top
        head_w = widths[top:neck].max() if neck > top else 0
        if neck >= arm_top - 1 or widths[neck] > 0.85 * head_w:
            neck = top + int(0.6 * above)
        return top, max(top + 4, neck)

    def haze(self):
        """How much of the outline is grey and nearly the background's own colour: a cast shadow, a haze."""
        l = lab(self.rgb)
        near = (np.abs(self.rgb - self.bg).sum(-1) < HAZE_OFF) & (np.hypot(l[..., 1], l[..., 2]) < HAZE_CHROMA)
        return float((near & self.mask).sum() / max(1, self.mask.sum()))

    def sticks_up_cm(self):
        return 100.0 * (self.crown() - self.top) / self.px_per_m


def builds(f):
    """TRELLIS can build it: whole, in frame, on plain ground, front on, arms straight out."""
    h, w = f.mask.shape
    margin = min(f.top, h - f.bottom, f.left, w - f.right) / h
    mirror = f.mask[:, f.left:f.right]
    sym = (mirror & mirror[:, ::-1]).sum() / max(1, (mirror | mirror[:, ::-1]).sum())
    arm_top, arm_bottom, span = f.arms()
    arm_mid = ((arm_top + arm_bottom) / 2 - f.top) / f.tall
    band = (arm_bottom - arm_top) / f.tall
    reach = span / f.tall
    legs = f.widths()[f.bottom - f.tall // 6:f.bottom].max() / max(1, span)
    t_pose = (1.0 if 0.12 <= arm_mid <= 0.55 else 0.3) * min(1.0, reach / 0.8) * (1.0 if band <= 0.22 else 0.4) * (1.0 if legs < 0.7 else 0.4)
    parts = {
        "whole": 1.0 if f.stray < 0.02 else max(0.0, 1 - 10 * f.stray),
        "in_frame": 1.0 if margin >= 0.02 else max(0.0, margin / 0.02),
        "plain_ground": 1.0 if f.rough < 12 else max(0.0, 1 - (f.rough - 12) / 30),
        "front_on": float(np.clip((sym - 0.75) / 0.2, 0, 1)),
        "t_pose": float(t_pose),
    }
    score = 0.15 * parts["whole"] + 0.15 * parts["in_frame"] + 0.1 * parts["plain_ground"] + 0.25 * parts["front_on"] + 0.35 * parts["t_pose"]
    return score, dict(parts, mirror_shared=round(float(sym), 3), arms_at=round(arm_mid, 3), arm_band=round(band, 3),
                       reach=round(reach, 3), feet_width=round(float(legs), 3), stray=round(f.stray, 4), margin=round(margin, 3))


def shared(a, b):
    """How much two outlines at the crew camera's size share, feet on one floor, centred: a sum over a union."""
    h, w = max(a.shape[0], b.shape[0]), max(a.shape[1], b.shape[1])
    def place(m):
        out = np.zeros((h, w), bool)
        x = (w - m.shape[1]) // 2
        out[h - m.shape[0]:, x:x + m.shape[1]] = m
        return out
    pa, pb = place(a), place(b)
    return float((pa & pb).sum() / max(1, (pa | pb).sum()))


def same_height(m, tall=SHAPE_PX):
    """An outline brought to `tall` pixels high: its shape alone, whatever its size."""
    w = max(1, round(m.shape[1] * tall / m.shape[0]))
    return np.asarray(Image.fromarray((m * 255).astype(np.uint8)).resize((w, tall), Image.BOX)) > 127


def stands_apart(f, cast):
    """Half how much its outline shares with each cast member's at their true sizes through the crew camera (so
    being the shortest counts), half how much the shapes alone share, both brought to one height."""
    mine = f.crew_mask()
    shape = same_height(mine)
    against = sorted(((0.5 * shared(mine, c["mask"]) + 0.5 * shared(shape, same_height(c["mask"])), c["name"]) for c in cast), reverse=True)
    top, neck = f.head()
    head = f.mask[top:neck]
    hc = head[:, head.any(0)]
    square = hc.sum() / max(1, hc.size)
    nearest, name = against[0] if against else (0.0, None)
    score = 0.7 * float(np.clip((1 - nearest) / 0.6, 0, 1)) + 0.3 * float(np.clip((square - 0.7) / 0.25, 0, 1))
    return score, {"shares_most_with": name, "shared": round(nearest, 3), "head_square": round(float(square), 3),
                   "crew_px_tall": int(mine.shape[0]), "against": {n: round(s, 3) for s, n in against}}


def lightness(rgb):
    return lab(rgb)[..., 0] / 100.0


def eyes_on(plate, inside, light):
    """The two biggest light pieces in the upper part of a dark plate (holes in it count): [(size, mask)]."""
    py0, py1, px0, px1 = box(plate)
    region = np.zeros_like(plate)
    region[py0:py1, px0:px1] = True
    filled = ndimage.binary_fill_holes(plate) | plate
    bright = region & inside & (light > float(light[plate].mean()) + 0.3) & filled
    bright[py0 + max(1, int(0.7 * (py1 - py0))):] = False
    labels, n = ndimage.label(bright)
    return sorted(([int(s), labels == i + 1] for i, s in enumerate(ndimage.sum(bright, labels, range(1, n + 1)))), key=lambda e: -e[0])[:2]


def face(f):
    """The head at the head's own grid through the crew camera, snapped to the figure's 32 colours: a dark plate,
    two light eyes on it, a grille under them."""
    top, neck = f.head()
    small = f.crew_picture(HEAD_GRID, rows=(top, neck))
    inside = small[..., 3] > 0
    light = lightness(small[..., :3].astype(np.float32))
    numbers = {"head_px_wide": round(float(inside.any(0).sum()) / HEAD_GRID, 1), "plate": False, "eyes": 0}
    dark = inside & (light < 0.32)
    dark = ndimage.binary_closing(dark, iterations=1) & inside
    labels, n = ndimage.label(dark)
    if not n:
        return 0.0, numbers, small
    sizes = ndimage.sum(dark, labels, range(1, n + 1))
    # the plate is the biggest dark piece with two light eyes on it; failing that, the biggest (a headset's band or a
    # hat's shadow can be as big as the plate, and one more dark pixel decides which is bigger)
    biggest = [labels == 1 + int(i) for i in np.argsort(-sizes)[:3] if sizes[i] >= 6]
    if not biggest:
        return 0.0, numbers, small
    plate = next((p for p in biggest if len(eyes_on(p, inside, light)) == 2), biggest[0])
    py0, py1, px0, px1 = box(plate)
    plate_l = float(light[plate].mean())
    eyes = eyes_on(plate, inside, light)
    numbers.update(plate=True, plate_px=int(plate.sum()), eyes=len(eyes))
    if len(eyes) < 2:
        return 0.25 if eyes else 0.1, numbers, small
    boxes = [box(m) for _, m in eyes]
    centres = [((b[0] + b[1]) / 2, (b[2] + b[3]) / 2) for b in boxes]
    level = abs(centres[0][0] - centres[1][0]) <= max(1.5, 0.15 * (py1 - py0))
    apart = abs(centres[0][1] - centres[1][1]) >= 2
    eye_w = min(b[3] - b[2] for b in boxes) / HEAD_GRID
    contrast = min(float(light[m].mean()) for _, m in eyes) - plate_l
    # the grille: light bars across the middle of the plate, under the eyes
    under = max(b[1] for b in boxes)
    cols = slice(px0 + (px1 - px0) // 4, px1 - (px1 - px0) // 4)
    profile = light[under:py1, cols].mean(1) if py1 > under and cols.stop > cols.start else np.zeros(0)
    bars = int(((profile[1:] > plate_l + 0.12) & (profile[:-1] <= plate_l + 0.12)).sum() + (profile[:1] > plate_l + 0.12).sum()) if len(profile) else 0
    numbers.update(level=bool(level), apart=bool(apart), eye_px_wide=round(eye_w, 1), contrast=round(contrast, 3), grille_bars=bars)
    pair = 1.0 if level and apart else 0.5
    score = 0.35 * pair + 0.25 * float(np.clip(eye_w / 3, 0, 1)) + 0.25 * float(np.clip(contrast / 0.45, 0, 1)) + 0.15 * min(bars, 3) / 3
    return score, numbers, small


def colours(f, palette, cast):
    pixels = f.rgb[f.mask]
    want = np.stack([hex_rgb(p["hex"]) for p in palette])
    d = np.sqrt(((lab(pixels)[:, None, :] - lab(want)[None]) ** 2).sum(-1))
    nearest, close = d.argmin(1), d.min(1) < MATCH_DE
    share = {p["name"]: round(float((close & (nearest == i)).mean()), 3) for i, p in enumerate(palette)}
    match = float(close.mean())
    # which breakdown colour most of it is nearest; the first of the breakdown is the one asked to lead: how much of
    # it there is against the most of any, and as it is painted (the mean of its pixels) how far from the cast's
    counts = np.array([(nearest == i).sum() for i in range(len(palette))])
    main_is = palette[int(np.argmax(counts))]["name"]
    lead = float(counts[0] / max(1, counts.max()))
    main = pixels[nearest == 0].mean(0) if counts[0] else pixels.mean(0)
    gaps = []
    for c in cast:
        gaps.append((float(np.sqrt(((lab(main) - lab(c["colours"])) ** 2).sum(-1)).min()), c["name"]))
    gap, closest = min(gaps) if gaps else (100.0, None)
    l = lab(pixels)
    # a glint is whiter than any colour it is painted in (a cream or white body is not a glint)
    glint_l = max(SHINE_L, float(lab(want)[:, 0].max()) + 4)
    shine = float(((l[:, 0] > glint_l) & (np.hypot(l[:, 1], l[:, 2]) < SHINE_C)).mean())
    score = 0.45 * float(np.clip(match / 0.85, 0, 1)) + 0.25 * lead + 0.3 * float(np.clip(gap / 35, 0, 1))
    return score, {"breakdown_share": round(match, 3), "by_colour": share, "main": "#%02x%02x%02x" % tuple(int(v) for v in main),
                   "main_is": main_is, "lead": round(lead, 3), "nearest_cast": closest, "cast_gap": round(gap, 1), "shine": round(shine, 4)}


def cards(f):
    """Thin and loose parts: what of the outline an opening THIN_CM wide takes away, and in how many pieces."""
    r = max(1, int(round(THIN_CM / 100 * f.px_per_m / 2)))
    disc = np.hypot(*np.mgrid[-r:r + 1, -r:r + 1]) <= r
    opened = ndimage.binary_opening(f.mask, structure=disc)
    thin = f.mask & ~opened
    labels, n = ndimage.label(thin)
    sizes = ndimage.sum(thin, labels, range(1, n + 1)) if n else np.zeros(0)
    big = int((sizes > (2 * r) ** 2 * 2).sum())
    share = float(thin.sum() / max(1, f.mask.sum()))
    up = f.sticks_up_cm()
    score = float(np.clip(1 - share / 0.05, 0, 1)) * (0.6 if up > STICKS_UP_CM else 1.0)
    return score, {"thin_share": round(share, 4), "thin_pieces": big, "thin_cm": THIN_CM, "sticks_up_cm": round(up, 1)}


def hangs(brief):
    """The gear a brief lists that is cloth hanging free (an apron, a skirt, a cape): what gets cloth bones in a walk."""
    out = []
    for g in brief.get("gear") or []:
        words = ("%s %s" % (g.get("name", ""), g.get("look", ""))).lower()
        if g.get("kind") == "worn" and any(w in words for w in HANGING) and not any(w in words for w in ("snug", "tight", "close-fitting")):
            out.append(g.get("name") or "cloth")
    return out


def held(f):
    """Something held at the end of an arm: the last tenth of each arm taller than its arm and hand need be."""
    arm_top, arm_bottom, span = f.arms()
    arm = arm_bottom - arm_top
    cols = np.where(f.mask.any(0))[0]
    out = []
    for side, part in (("left", f.mask[:, cols[0]:cols[0] + max(2, span // 10)]), ("right", f.mask[:, cols[-1] - max(2, span // 10):cols[-1] + 1])):
        rows = np.where(part.any(1))[0]
        tall = (rows[-1] - rows[0] + 1) if len(rows) else 0
        out.append((side, tall / max(1, arm)))
    return out


def screen_one(path, palette, cast, height_m):
    f = Figure(path, height_m)
    scores, numbers = {}, {}
    scores["builds"], numbers["builds"] = builds(f)
    scores["stands_apart"], numbers["stands_apart"] = stands_apart(f, cast)
    scores["face"], numbers["face"], face_small = face(f)
    scores["colours"], numbers["colours"] = colours(f, palette, cast)
    scores["cards"], numbers["cards"] = cards(f)
    flags = []
    if numbers["colours"]["shine"] > 0.01:
        flags.append("shine: %.1f%% of it is a white glint (chrome, glass or a glow)" % (100 * numbers["colours"]["shine"]))
    hands = held(f)
    numbers["hands"] = {side: round(r, 2) for side, r in hands}
    for side, ratio in hands:
        if ratio > 2.6:
            flags.append("something held? the %s hand is %.1f times as tall as its arm" % (side, ratio))
    if f.haze() > HAZE_SHARE:
        flags.append("%.0f%% of its outline is grey and nearly the background's colour: a shadow or haze, or paint too pale to cut out cleanly (TRELLIS may build a floor or lose an edge)" % (100 * f.haze()))
    if numbers["cards"]["sticks_up_cm"] > STICKS_UP_CM:
        flags.append("something thin rises %.0f cm above its head (an antenna?)" % numbers["cards"]["sticks_up_cm"])
    total = sum(WEIGHTS[k] * scores[k] for k in WEIGHTS) - FLAG_COST * len(flags)
    return {"scores": {k: round(v, 3) for k, v in dict(scores, total=max(0.0, total)).items()}, "numbers": numbers, "flags": flags}, f, face_small


# ---------- the part, the cast, and the pictures ----------

SHOT = re.compile(r"^(?P<look>[a-z0-9][a-z0-9-]*)(?:\.(?P<n>\d+)(?:-(?P<colourway>[a-z0-9][a-z0-9-]*))?)?$")


def parse_shot(stem):
    """A headshot's name: "clerk" (picture 1), "clerk.2" (picture 2), "clerk.2-lilac" (picture 2 in the lilac
    colourway). Returns (look, n, colourway or None), or None for a name that is not one."""
    m = SHOT.match(stem)
    return (m["look"], int(m["n"] or 1), m["colourway"]) if m else None


def shots_of(folder):
    """(shot id, look, n, file, colourway) for every headshot kept: clerk.jpg is ("clerk", "clerk", 1, ..., None),
    clerk.2.jpg ("clerk.2", ..., 2, ..., None), clerk.2-lilac.jpg ("clerk.2-lilac", "clerk", 2, ..., "lilac")."""
    out = []
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        stem, ext = os.path.splitext(name)
        found = parse_shot(stem) if ext.lower() in (".png", ".jpg") else None
        if found and not any(o[0] == stem for o in out):
            out.append((stem, found[0], found[1], name, found[2]))
    return sorted(out, key=lambda s: (s[1], s[2], s[4] or ""))


def keep(role_id, root):
    """Headshots as git keeps them: Codex's full-size PNG goes to headshots/full/ (out of git), and a JPEG of KEEP_PX
    at quality KEEP_Q beside it is what everything reads. Moves any PNG still at the top into full/ first."""
    folder = os.path.join(root, role_id, "headshots")
    full = os.path.join(folder, "full")
    os.makedirs(full, exist_ok=True)
    made = []
    for name in sorted(os.listdir(folder)):
        stem, ext = os.path.splitext(name)
        if ext.lower() == ".png" and parse_shot(stem):
            os.replace(os.path.join(folder, name), os.path.join(full, name))
    for name in sorted(os.listdir(full)):
        stem, ext = os.path.splitext(name)
        if ext.lower() != ".png" or not parse_shot(stem):
            continue
        kept = os.path.join(folder, stem + ".jpg")
        if os.path.isfile(kept) and os.path.getmtime(kept) >= os.path.getmtime(os.path.join(full, name)):
            continue
        img = Image.open(os.path.join(full, name)).convert("RGB")
        img.resize((KEEP_PX, KEEP_PX), Image.LANCZOS).save(kept, "JPEG", quality=KEEP_Q, optimize=True, progressive=True)
        made.append(stem)
    return made


def the_cast(runs, cache):
    """Every character in runs/ (its brief says character), measured once: its crew-size outline and main colours."""
    found = []
    for run in sorted(os.listdir(runs)) if os.path.isdir(runs) else []:
        try:
            with open(os.path.join(runs, run, "brief.json")) as fh:
                brief = json.load(fh)
        except (OSError, ValueError):
            continue
        picture = os.path.join(runs, run, "image.png")
        if not brief.get("character") or not os.path.isfile(picture) or not brief.get("size_m"):
            continue
        key = os.path.join(cache, run + ".npz")
        if os.path.isfile(key) and os.path.getmtime(key) > os.path.getmtime(picture):
            saved = np.load(key)
            if "crew" in saved:
                found.append({"run": run, "name": brief.get("name") or run, "height_m": brief["size_m"], "mask": saved["mask"],
                              "colours": saved["colours"], "crew": saved["crew"]})
                continue
        f = Figure(picture, brief["size_m"])
        pal, share = palette_of(f.rgb[f.mask], 6)
        main = pal[np.argsort(-share)[:2]]
        crew = f.crew_picture()  # in its own colours, for the colourways' line-up
        os.makedirs(cache, exist_ok=True)
        np.savez_compressed(key, mask=f.crew_mask(), colours=main, crew=crew)
        found.append({"run": run, "name": brief.get("name") or run, "height_m": brief["size_m"], "mask": f.crew_mask(), "colours": main, "crew": crew})
    return found


def colourway_sheet(role, rows, cast, out):
    """Each headshot that has colourways, a row each: its pictures side by side (the one drawn first, then each
    colourway), with total and colour scores and the swatches; then, at the crew camera's own size and feet on one
    floor, the cast in their own colours and the robot in every colourway."""
    groups = {}
    for row in rows:
        of = (row.get("colourway") or {}).get("of")
        if of:
            groups.setdefault(of, []).append(row)
    if not groups:
        return None
    by_id = {r["id"]: r for r in rows}
    ink, soft, blue = (28, 25, 23), (242, 239, 233), (68, 103, 155)
    pic, gap = 210, 14
    crews = [Image.fromarray(c["crew"]) for c in cast]
    lineup_w = sum(c.size[0] for c in crews) + 4 * 190 + gap * (len(crews) + 4)
    row_h = pic + 120 + 300
    width = max(4 * (pic + gap), lineup_w) + 60
    sheet = Image.new("RGB", (width, 90 + row_h * len(groups)), (250, 248, 245))
    draw = ImageDraw.Draw(sheet)
    draw.text((24, 16), "%s: colourways" % role.get("title", role["id"]), fill=ink, font=font(26))
    draw.text((24, 50), "Each robot as first drawn, then in three other colourways. Below each, the cast in their own colours and the robot in every "
              "colourway, at the crew camera's own size, feet on one floor.", fill=ink, font=font(14))
    for g, (of, ways) in enumerate(sorted(groups.items())):
        top = 90 + g * row_h
        draw.rounded_rectangle((14, top, width - 14, top + row_h - 14), 18, fill=soft)
        members = ([by_id[of]] if of in by_id else []) + sorted(ways, key=lambda r: -r["scores"]["total"])
        for i, r in enumerate(members):
            x = 28 + i * (pic + gap)
            im = Image.open(os.path.join(ROOT, r["picture"])).convert("RGB")
            im.thumbnail((pic, pic))
            sheet.paste(im, (x, top + 14))
            name = r["colourway"]["name"] if r.get("colourway") else "As drawn (mustard)"
            draw.text((x, top + pic + 22), name, fill=ink, font=font(16))
            draw.text((x, top + pic + 44), "total %.2f · colours %.2f" % (r["scores"]["total"], r["scores"]["colours"]), fill=ink, font=font(13))
            hexes = r["colourway"]["swatches"] if r.get("colourway") else [p["hex"] for p in (role.get("breakdown") or {}).get("palette") or []]
            for k, h in enumerate(hexes):
                draw.rounded_rectangle((x + k * 26, top + pic + 66, x + k * 26 + 22, top + pic + 88), 5, fill=tuple(int(h.lstrip("#")[j:j + 2], 16) for j in (0, 2, 4)), outline=(190, 184, 174))
            if r.get("flags"):
                draw.text((x, top + pic + 94), "! " + r["flags"][0][:40], fill=(160, 50, 40), font=font(11))
        floor = top + row_h - 40
        x = 28
        figures = [(c["name"].split(" ")[0], im, ink) for c, im in zip(cast, crews)]
        half = len(figures) // 2
        robots = [((r["colourway"]["name"] if r.get("colourway") else "As drawn"), Image.open(os.path.join(ROOT, r["small"])).convert("RGBA"), blue) for r in members]
        for label, im, colour in figures[:half] + robots + figures[half:]:
            im = im.convert("RGBA")
            sheet.paste(im, (x, floor - im.size[1]), im)
            draw.text((x, floor + 4), label[:14], fill=colour, font=font(11))
            x += max(im.size[0], 60) + gap
    sheet.save(out)
    return out


def font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def contact_sheet(role, rows, cast, folder, out):
    """Every headshot on one page, best first: the picture, the crew camera's view of it and its face, its
    rank, total and the five scores as bars, and any flags. Along the top, the cast's outlines at the crew camera's
    size, feet on one floor."""
    cell_w, cell_h, cols = 360, 470, 4
    head_h = 190
    lines = (len(rows) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w + 40, head_h + lines * cell_h + 40), (250, 248, 245))
    draw = ImageDraw.Draw(sheet)
    ink, blue, soft = (28, 25, 23), (68, 103, 155), (242, 239, 233)
    draw.text((20, 14), "%s: screen test of %d headshots" % (role.get("title", role["id"]), len(rows)), fill=ink, font=font(26))
    draw.text((20, 46), "Best first. Builds · Stands apart · Face · Colours · Cards, each out of 1. Beside each picture: the crew camera's view of it, "
              "and its face on the head's grid, both in the pixel look's colours.", fill=ink, font=font(15))
    # the cast and the best headshot side by side, their outlines at their true heights, feet on one floor
    floor, room = head_h - 14, head_h - 14 - 72
    best = rows[0] if rows else None
    figures = [(c["name"].split(" ")[0], c["mask"], (120, 113, 108)) for c in cast]
    if best:
        figures.insert(len(figures) // 2, (best["id"], np.asarray(Image.open(os.path.join(ROOT, best["small"])))[..., 3] > 0, blue))
    k = min(1.0, room / max(m.shape[0] for _, m, _ in figures)) if figures else 1.0
    x = 20
    for name, mask, colour in figures:
        size = (max(1, round(mask.shape[1] * k)), max(1, round(mask.shape[0] * k)))
        m = Image.fromarray((mask * 255).astype(np.uint8)).resize(size, Image.BOX)
        sheet.paste(Image.new("RGB", size, colour), (x, floor - size[1]), m)
        draw.text((x, floor + 1), name[:12], fill=ink, font=font(11))
        x += max(size[0], 64) + 8
    for i, row in enumerate(rows):
        cx, cy = 20 + (i % cols) * cell_w, head_h + (i // cols) * cell_h
        draw.rounded_rectangle((cx, cy, cx + cell_w - 12, cy + cell_h - 12), 16, fill=soft)
        pic = Image.open(os.path.join(ROOT, row["picture"])).convert("RGB")
        pic.thumbnail((200, 200))
        sheet.paste(pic, (cx + 8, cy + 8))
        small = Image.open(os.path.join(ROOT, row["small"])).convert("RGBA")
        small.thumbnail((136, 140), Image.NEAREST)
        sheet.paste(small, (cx + 212, cy + 8 + 140 - small.size[1]), small)
        face_small = Image.open(os.path.join(ROOT, row["face"])).convert("RGBA")
        zoom = max(1, min(136 // max(1, face_small.size[0]), 84 // max(1, face_small.size[1])))
        face_small = face_small.resize((face_small.size[0] * zoom, face_small.size[1] * zoom), Image.NEAREST)
        face_small.thumbnail((136, 84), Image.NEAREST)
        sheet.paste(face_small, (cx + 212, cy + 156), face_small)
        draw.text((cx + 10, cy + 248), "#%d  %s" % (row["rank"], row["id"]), fill=ink, font=font(20))
        draw.text((cx + 10, cy + 270), "%s · total %.2f" % (row["name"], row["scores"]["total"]), fill=ink, font=font(14))
        for k, key in enumerate(WEIGHTS):
            y = cy + 296 + k * 22
            draw.text((cx + 10, y), NAMES[key], fill=ink, font=font(13))
            draw.rounded_rectangle((cx + 120, y + 3, cx + 120 + 180, y + 15), 6, fill=(226, 221, 212))
            draw.rounded_rectangle((cx + 120, y + 3, cx + 120 + max(12, int(180 * row["scores"][key])), y + 15), 6, fill=blue)
            draw.text((cx + 306, y), "%.2f" % row["scores"][key], fill=ink, font=font(13))
        for k, flag in enumerate(row["flags"][:2]):
            draw.text((cx + 10, cy + 412 + k * 18), "! " + flag[:52], fill=(160, 50, 40), font=font(12))
    sheet.save(out)


def screen_role(role_id, root, runs):
    folder = os.path.join(root, role_id)
    with open(os.path.join(folder, "role.json")) as fh:
        role = json.load(fh)
    looks = {l["id"]: l for l in role.get("looks") or []}
    breakdown = role.get("breakdown") or {}
    palette = breakdown.get("palette") or []
    cast = the_cast(runs, os.path.join(folder, "screen", ".cast"))
    colourways = {(l["id"], c["id"]): c for l in looks.values() for c in l.get("colourways") or []}
    # a colourway's picture is measured against its own swatches; one not written in role.json is left out
    shots = [s for s in shots_of(os.path.join(folder, "headshots")) if s[1] in looks and (not s[4] or (s[1], s[4]) in colourways)]
    os.makedirs(os.path.join(folder, "screen"), exist_ok=True)
    rel = lambda p: os.path.relpath(p, ROOT)
    rows = []
    for shot, look, n, name, colourway in shots:
        height = (looks[look].get("brief") or {}).get("size_m") or breakdown.get("height_m") or 1.5
        way = colourways.get((look, colourway))
        found, f, face_small = screen_one(os.path.join(folder, "headshots", name), way["swatches"] if way else palette, cast, height)
        if way:
            found["colourway"] = {"id": way["id"], "name": way["name"], "of": "%s.%d" % (look, n) if n > 1 else look,
                                  "swatches": [s["hex"] for s in way["swatches"]]}
        loose = hangs(looks[look].get("brief") or {})
        if loose:
            # read from the brief, not the picture: cloth that hangs gets cloth bones, and cards come apart there
            found["scores"]["cards"] = round(found["scores"]["cards"] * HANGS_COST, 3)
            found["flags"].append("wears cloth that hangs: %s (from its brief)" % ", ".join(loose))
            found["scores"]["total"] = round(max(0.0, sum(WEIGHTS[k] * found["scores"][k] for k in WEIGHTS) - FLAG_COST * len(found["flags"])), 3)
        small = os.path.join(folder, "screen", shot + "-crew.png")
        Image.fromarray(f.crew_picture()).save(small)
        face_file = os.path.join(folder, "screen", shot + "-face.png")
        t, b, l, r = box(face_small[..., 3] > 0) if (face_small[..., 3] > 0).any() else (0, face_small.shape[0], 0, face_small.shape[1])
        Image.fromarray(face_small[t:b, l:r]).save(face_file)  # the head alone, not the width of its arms
        look_small = os.path.join(folder, "screen", shot + "-look.jpg")
        Image.fromarray(f.full.astype(np.uint8)).resize((LOOK_PX, LOOK_PX), Image.BOX).save(look_small, quality=85)
        rows.append(dict(found, id=shot, look=look, n=n, name=looks[look].get("name") or look, suits=looks[look].get("suits"),
                         picture=rel(os.path.join(folder, "headshots", name)), small=rel(small), face=rel(face_file), look_small=rel(look_small)))
        print("SCREEN %-28s total %.2f  %s" % (shot, found["scores"]["total"], "  ".join("%s %.2f" % (k, found["scores"][k]) for k in WEIGHTS)), flush=True)
    vision = None
    try:
        with open(os.path.join(folder, "screen-vision.json")) as fh:
            vision = json.load(fh)
    except (OSError, ValueError):
        pass
    for row in rows:
        seen = ((vision or {}).get("shots") or {}).get(row["id"])
        if seen:
            row["vision"] = seen
            for broken in seen.get("breaks") or []:
                row["flags"].append("seen: " + broken)
                row["scores"]["total"] = round(max(0.0, row["scores"]["total"] - FLAG_COST), 3)
    rows.sort(key=lambda r: -r["scores"]["total"])
    for i, row in enumerate(rows):
        row["rank"] = i + 1
    out = {"made": time.strftime("%Y-%m-%d %H:%M", time.localtime()), "role": role_id,
           "how": {"crew_px_per_m": CREW_PX_PER_M, "head_grid": HEAD_GRID, "palette_colours": PALETTE_COLOURS, "weights": WEIGHTS,
                   "flag_cost": FLAG_COST, "thin_cm": THIN_CM, "names": NAMES},
           "cast": [{"run": c["run"], "name": c["name"], "height_m": c["height_m"]} for c in cast],
           "vision": {k: v for k, v in (vision or {}).items() if k != "shots"} or None,
           "shots": rows}
    if rows:
        contact_sheet(role, rows, cast, folder, os.path.join(folder, "screen-contact-sheet.png"))
        out["sheet"] = rel(os.path.join(folder, "screen-contact-sheet.png"))
        if colourway_sheet(role, rows, cast, os.path.join(folder, "colourways-contact-sheet.png")):
            out["colourway_sheet"] = rel(os.path.join(folder, "colourways-contact-sheet.png"))
    with open(os.path.join(folder, "screen.json"), "w") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")
    return out


# ---------- the mesh screen's pictures, measured ----------

def alpha_of(path):
    return np.asarray(Image.open(path).convert("RGBA"))


def turnaround(headshot, renders, height_m, out):
    """A mesh's renders (screen_mesh.py) against the headshot it was built from: whether its front is the picture's
    front, how much of the headshot's outline its front keeps, how far its colours moved, and how much of its
    figure is left at the crew camera's size from every side. Writes the turnaround sheet; returns the numbers."""
    f = Figure(headshot, height_m)
    want = same_height(f.crew_mask())
    want_rgb = f.crew_picture()
    found = {}
    for deg in (0, 180):
        r = alpha_of(os.path.join(renders, "crew-%03d-00.png" % deg))
        m = r[..., 3] > 127
        if not m.any():
            continue
        t, b, l, rr = box(m)
        crop = m[t:b, l:rr]
        found[deg] = (shared(want, same_height(crop)), r[t:b, l:rr])
    front = max(found, key=lambda d: found[d][0]) if found else 0
    kept, front_rgba = found.get(front, (0.0, None))
    colour_moved = None
    if front_rgba is not None:
        a = np.asarray(Image.fromarray(front_rgba).resize((want_rgb.shape[1], want_rgb.shape[0]), Image.BOX)).astype(np.float32)
        both = (a[..., 3] > 127) & (want_rgb[..., 3] > 0)
        if both.any():
            colour_moved = float(np.sqrt(((lab(a[..., :3][both]) - lab(want_rgb[..., :3][both].astype(np.float32))) ** 2).sum(-1)).mean())
    sides = []
    for deg in range(0, 360, 45):
        for up in (0, 25):
            path = os.path.join(renders, "crew-%03d-%02d.png" % (deg, up))
            if os.path.isfile(path):
                sides.append(int((alpha_of(path)[..., 3] > 127).sum()))
    # the sheet: eight turns at eye level, then the crew camera's size from eye level and from above
    turns = [Image.open(os.path.join(renders, "turn-%03d.png" % d)).convert("RGBA") for d in range(0, 360, 45)
             if os.path.isfile(os.path.join(renders, "turn-%03d.png" % d))]
    crew_px = Image.open(os.path.join(renders, "crew-000-00.png")).size[0] if os.path.isfile(os.path.join(renders, "crew-000-00.png")) else 160
    cell = max(200, crew_px + 8)
    sheet = Image.new("RGB", (cell * max(1, len(turns)) + 20, cell + 2 * (crew_px + 8) + 40), (250, 248, 245))
    draw = ImageDraw.Draw(sheet)
    draw.text((10, 6), "From all round at eye level; below, at the crew camera's own size (one pixel a pixel), from eye level and from 25 degrees up",
              fill=(28, 25, 23), font=font(14))
    for i, t in enumerate(turns):
        t.thumbnail((cell - 8, cell - 8))
        sheet.paste(t, (10 + i * cell, 28), t)
        for j, up in enumerate((0, 25)):
            path = os.path.join(renders, "crew-%03d-%02d.png" % (i * 45, up))
            if os.path.isfile(path):
                c = Image.open(path).convert("RGBA")
                sheet.paste(c, (10 + i * cell, 28 + cell + j * (crew_px + 8)), c)
    sheet.save(out)
    return {"front_is": "as drawn" if front == 0 else "turned round", "outline_kept": round(kept, 3),
            "colour_moved": round(colour_moved, 1) if colour_moved is not None else None,
            "crew_px_least": min(sides) if sides else None, "crew_px_most": max(sides) if sides else None}


def main(argv):
    flag = lambda name, default: argv[argv.index(name) + 1] if name in argv else default
    words = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or not argv[i - 1].startswith("--"))]
    if not words:
        print(__doc__)
        return 1
    if words[0] == "keep":  # screen.py keep <role>: Codex's PNGs into headshots/full/, a JPEG of each beside them
        made = keep(words[1], os.path.abspath(flag("--root", os.path.join(ROOT, "casting"))))
        print("RESULT " + json.dumps({"kept": made}))
        return 0
    if words[0] == "png":  # screen.py png <picture> <out.png>: a kept JPEG as a PNG, for a run's image.png
        Image.open(words[1]).convert("RGB").save(words[2])
        return 0
    if words[0] == "turn":  # screen.py turn <headshot> <renders dir> <height m> <sheet.png>
        print("RESULT " + json.dumps(turnaround(words[1], words[2], float(words[3]), words[4])))
        return 0
    out = screen_role(words[0], os.path.abspath(flag("--root", os.path.join(ROOT, "casting"))), os.path.abspath(flag("--runs", os.path.join(ROOT, "runs"))))
    print("RESULT " + json.dumps({"shots": len(out["shots"]), "top": [r["id"] for r in out["shots"][:6]], "sheet": out.get("sheet")}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
