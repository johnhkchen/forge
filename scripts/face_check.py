"""Measure the faces on a face sheet against the source picture.

    uv run --no-project --python 3.11 --with mediapipe==0.10.14 --with opencv-python-headless --with "numpy<2" \
        python scripts/face_check.py SHEET.json [SHEET.json ...]

SHEET.json is what scripts/face_sheet.py writes next to its picture. For the
picture's head and each version's front tile this finds the face (MediaPipe
Face Mesh, which wants a human face: a troll or a mask gives "no face") and
six landmarks: both eyes, the tip of the nose, both corners of the mouth, the
chin. Then, per version, all as % of the head's height:

  layout   the landmarks against the picture's, after the best slide, turn
           and scale onto them: is the face laid out like the picture's?
  moved    the landmarks against the detailed mesh's, in place (every tile
           is framed by the same box): did this version move the face?
  lopsided left against right, across the line from between the eyes to the
           chin; the picture's own figure is the one to beat
  eyes, mouth   how like the picture that spot looks once laid over it
           (1 = the same picture, 0 = nothing in common), and how sharp it
           is against the picture there ("x0.3" = a third of the detail)

The detector fits a whole face even to a smudge, so `layout` on its own
flatters a blurred face: read it with eyes/mouth. Writes SHEET-check.json.
"""
import json
import os
import sys

import cv2
import mediapipe as mp
import numpy as np

POINTS = {"eye_r": (33, 133), "eye_l": (362, 263), "nose": (4,), "mouth_r": (61,), "mouth_l": (291,), "chin": (152,)}
PAIRS = (("eye_r", "eye_l"), ("mouth_r", "mouth_l"))
SIDE = 512
finder = mp.solutions.face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1, refine_landmarks=True, min_detection_confidence=0.2)


def landmarks(path):
    """The tile, 512 px, and its six landmarks in pixels (None with no face)."""
    image = cv2.resize(cv2.imread(path), (SIDE, SIDE), interpolation=cv2.INTER_CUBIC)
    found = finder.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    if not found.multi_face_landmarks:
        return image, None
    marks = found.multi_face_landmarks[0].landmark
    return image, {name: np.mean([[marks[i].x * SIDE, marks[i].y * SIDE] for i in ids], axis=0) for name, ids in POINTS.items()}


def fit(points, onto):
    """The slide, turn and scale that best lays `points` on `onto` (2x3), least squares."""
    a, b = np.array(points), np.array(onto)
    ma, mb = a.mean(axis=0), b.mean(axis=0)
    a0, b0 = a - ma, b - mb
    u, s, vt = np.linalg.svd(a0.T @ b0)
    turn = (u @ vt).T
    if np.linalg.det(turn) < 0:
        vt[-1] *= -1
        turn = (u @ vt).T
    scale = s.sum() / (a0 ** 2).sum()
    return np.c_[scale * turn, mb - scale * turn @ ma]


def lopsided(p, head_px):
    """Left against right across the line from between the eyes to the chin, % of the head's height."""
    top = (p["eye_r"] + p["eye_l"]) / 2
    down = p["chin"] - top
    down = down / np.linalg.norm(down)
    across = np.array([-down[1], down[0]])
    errors = []
    for right, left in PAIRS:
        r, l = p[right] - top, p[left] - top
        errors.append(abs(abs(r @ across) - abs(l @ across)))  # one side wider than the other
        errors.append(abs(r @ down - l @ down))                # one side higher than the other
    errors.append(abs((p["nose"] - top) @ across))             # the nose off the line
    return 100 * float(np.mean(errors)) / head_px


def patch(gray, points, pad):
    lo = np.min(points, axis=0) - pad
    hi = np.max(points, axis=0) + pad
    x0, y0, x1, y1 = [int(round(v)) for v in (max(lo[0], 0), max(lo[1], 0), min(hi[0], SIDE), min(hi[1], SIDE))]
    return gray[y0:y1, x0:x1]


def alike(a, b):
    a, b = a - a.mean(), b - b.mean()
    under = float(np.sqrt((a ** 2).sum() * (b ** 2).sum()))
    return float((a * b).sum() / under) if under > 1e-6 else 0.0


def detail(a):
    return float(cv2.Laplacian(cv2.GaussianBlur(a, (0, 0), 1.5), cv2.CV_32F).var())


def check(sheet_path):
    with open(sheet_path) as f:
        sheet = json.load(f)
    box = sheet["box"]
    span = max(box[1][i] - box[0][i] for i in range(3)) * 1.3
    head_px = SIDE * (box[1][2] - box[0][2]) / span
    out = {"run": sheet["run"], "rows": []}
    picture = sheet.get("picture", {}).get("tile")
    pic_image, pic = landmarks(picture) if picture else (None, None)
    pic_gray = cv2.cvtColor(pic_image, cv2.COLOR_BGR2GRAY).astype(np.float32) if pic_image is not None else None
    if pic:
        out["rows"].append({"label": "picture", "face": True, "lopsided": round(lopsided(pic, head_px), 2)})
        pad = 0.05 * head_px
        spots = {"eyes": patch(pic_gray, [pic["eye_r"], pic["eye_l"]], 1.6 * pad), "mouth": patch(pic_gray, [pic["mouth_r"], pic["mouth_l"]], pad)}
    else:
        out["rows"].append({"label": "picture", "face": False})
    base = None
    for version in sheet["versions"]:
        for n, tiles in enumerate(version["tiles"]):
            label = version["label"] + (" #%d" % (n + 1) if len(version["tiles"]) > 1 else "")
            image, p = landmarks(tiles["front"])
            row = {"label": label, "face": bool(p)}
            for key in ("shape", "walk"):
                if version.get(key):
                    row[key] = version[key]
            if p:
                row["lopsided"] = round(lopsided(p, head_px), 2)
                names = list(POINTS)
                if base is None:
                    base = p
                else:
                    gone = [np.linalg.norm(p[k] - base[k]) for k in names]
                    row["moved"] = {"typical": round(100 * float(np.mean(gone)) / head_px, 2), "worst": round(100 * float(np.max(gone)) / head_px, 2),
                                    "worst_at": names[int(np.argmax(gone))]}
                if pic:
                    m = fit([p[k] for k in names], [pic[k] for k in names])
                    laid = [m[:, :2] @ p[k] + m[:, 2] for k in names]
                    left = [np.linalg.norm(laid[i] - pic[k]) for i, k in enumerate(names)]
                    row["layout"] = {"typical": round(100 * float(np.mean(left)) / head_px, 2), "worst": round(100 * float(np.max(left)) / head_px, 2),
                                     "worst_at": names[int(np.argmax(left))]}
                    gray = cv2.warpAffine(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32), m, (SIDE, SIDE), borderMode=cv2.BORDER_REPLICATE)
                    pad = 0.05 * head_px
                    mine = {"eyes": patch(gray, [pic["eye_r"], pic["eye_l"]], 1.6 * pad), "mouth": patch(gray, [pic["mouth_r"], pic["mouth_l"]], pad)}
                    for spot in ("eyes", "mouth"):
                        row[spot] = {"like": round(alike(mine[spot], spots[spot]), 2), "sharp": round(detail(mine[spot]) / max(detail(spots[spot]), 1e-6), 2)}
            out["rows"].append(row)
    with open(os.path.splitext(sheet_path)[0] + "-check.json", "w") as f:
        json.dump(out, f, indent=1)
    return out


def cell(row, key, sub="typical"):
    v = row.get(key)
    return "-" if v is None else ("%.1f" % v[sub] if isinstance(v, dict) else "%.1f" % v)


if __name__ == "__main__":
    for path in sys.argv[1:]:
        got = check(path)
        print("FACE-CHECK " + os.path.basename(got["run"]))
        print("  %-16s %-5s %7s %7s %8s %12s %12s %8s %8s %6s" % ("version", "face", "layout", "moved", "lopsided", "eyes", "mouth", "missing", "shape", "walk"))
        for row in got["rows"]:
            spots = ["%.2f x%.1f" % (row[s]["like"], row[s]["sharp"]) if s in row else "-" for s in ("eyes", "mouth")]
            shape, walk = row.get("shape") or {}, row.get("walk") or {}
            print("  %-16s %-5s %7s %7s %8s %12s %12s %8s %8s %6s" % (
                row["label"], "yes" if row["face"] else "NO", cell(row, "layout"), cell(row, "moved"), cell(row, "lopsided"), spots[0], spots[1],
                "-" if "missing_pct" not in shape else "%.0f%%" % shape["missing_pct"],
                "-" if shape.get("off_typical_pct") is None else "%.1f" % shape["off_typical_pct"],
                "-" if "face_bends_pct_of_head" not in walk else "%.1f" % walk["face_bends_pct_of_head"]))
