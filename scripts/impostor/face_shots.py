"""Pictures of the cast's faces on the watch page, and how many pixels each face gets, taken by a headless Chrome.

    python3 scripts/impostor/face_shots.py [--base http://localhost:8028/] [--take crew-candy-shop] [--out evidence/faces]
        [--tag after] [--at 57.5] [--eye crew] [--close 1.3]

The gallery must be running on that port. For the take, stopped at --at seconds, it takes:

    <tag>-<eye>-<look>-<cards|meshes>.png           the whole stage through the set's camera
    <tag>-<eye>-<look>-<cards|meshes>-heads.png     each head cut out of that picture and blown up eight times
    <tag>-close-<role>-<look>-<cards|meshes>.png    the free eye --close metres in front of each face

for pixel cards ("Pixels, both") and for meshes drawn small ("Pixels, on screen"), and writes <tag>-faces.json:
for each of the cast, how far the eye is from his head and how many of the picture's big pixels a metre is
there, so how many a face 15 cm wide and an eye 3 cm wide get. Prints FACES lines.
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts", "world"))
sys.path.insert(0, HERE)
import test_walkabout  # noqa: E402  (the gallery in a headless Chrome tab)

FACE_M, EYE_M = 0.15, 0.03
WAYS = (("pixel-both", True), ("pixel-screen", False))

# Where each head is in the picture, how far off, and how big a metre is there in the picture's own big pixels.
HEADS = """(() => {
  const v = window.forgeWatch.viewer, THREE = window.forgeWatch.THREE, cam = v.camera;
  v.renderer.domElement.scrollIntoView({ block: "center" });
  const box = v.renderer.domElement.getBoundingClientRect();
  const size = v.renderer.getDrawingBufferSize(new THREE.Vector2());
  const rows = v.look.screen && v.look.screen.rows ? Math.floor(size.y / Math.max(2, Math.round(size.y / v.look.screen.rows))) : size.y;
  return JSON.stringify({ box: [box.left + window.scrollX, box.top + window.scrollY, box.width, box.height], rows, cast: v.cast.map((c) => {
    const at = new THREE.Vector3().setFromMatrixPosition(c.bones.head.matrixWorld);
    at.y += 0.1 / (c.role.size || 1);
    const away = at.distanceTo(cam.position);
    const p = at.clone().project(cam);
    return { role: c.role.role, x: (p.x * 0.5 + 0.5) * box.width, y: (0.5 - p.y * 0.5) * box.height, away,
      px_per_m: rows / (2 * away * Math.tan(THREE.MathUtils.degToRad(cam.fov) / 2)) };
  }) });
})()"""


def settle(page):
    page.value("new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(() => done(1)))))", wait=True)
    time.sleep(0.4)


def shoot(page, path, box):
    import base64
    os.makedirs(os.path.dirname(path), exist_ok=True)
    got = page.tab.ask("Page.captureScreenshot", format="png", clip={"x": box[0], "y": box[1], "width": box[2], "height": box[3], "scale": 1})
    with open(path, "wb") as f:
        f.write(base64.b64decode(got["data"]))


def heads_strip(path, out, heads, half=44, times=8):
    """Each head cut out of a picture and blown up, side by side. Needs numpy (Blender's Python has it); skipped without."""
    try:
        import numpy as np
        import impostor
    except ImportError:
        return False
    picture = impostor.read_png(path)[::-1][..., :3]
    cuts = []
    for h in heads:
        x, y = int(round(h["x"])), int(round(h["y"]))
        cut = np.zeros((2 * half, 2 * half, 3), dtype=np.uint8)
        y0, y1, x0, x1 = max(0, y - half), min(picture.shape[0], y + half), max(0, x - half), min(picture.shape[1], x + half)
        cut[y0 - (y - half):y1 - (y - half), x0 - (x - half):x1 - (x - half)] = picture[y0:y1, x0:x1]
        cuts.append(np.repeat(np.repeat(cut, times, axis=0), times, axis=1))
        cuts.append(np.full((2 * half * times, 8, 3), 255, dtype=np.uint8))
    impostor.write_png(out, np.concatenate(cuts[:-1], axis=1)[::-1])
    return True


def main():
    args = sys.argv[1:]
    flag = lambda name, default: args[args.index(name) + 1] if name in args else default
    base, take, out, tag = flag("--base", "http://localhost:8028/"), flag("--take", "crew-candy-shop"), os.path.abspath(flag("--out", os.path.join(REPO, "evidence", "faces"))), flag("--tag", "after")
    at, eye, close = float(flag("--at", "57.5")), flag("--eye", "crew"), float(flag("--close", "1.3"))
    page = test_walkabout.Page(base, gpu=True)
    facts = {"take": take, "seconds": at, "eye": eye, "face_m": FACE_M, "eye_m": EYE_M, "views": {}}
    try:
        page.size(1280, 900, 1, False)
        page.open("#/watch/%s" % take)
        page.until("window.forgeWatch && window.forgeWatch.state().ready && !document.querySelector('.watch-pane .status')", 120)
        page.value("window.forgeWatch.set({ playing: false, time: %s }); 1" % at)
        for look, cards in WAYS:
            name = "%s-%s" % (look, "cards" if cards else "meshes")
            page.value("window.forgeWatch.set({ cards: %s }); window.forgeWatch.look(%s).then(() => 1)" % ("true" if cards else "false", json.dumps(look)), wait=True)
            page.value("window.forgeWatch.eye(%s); 1" % json.dumps(eye))
            settle(page)
            heads = json.loads(page.value(HEADS))
            path = os.path.join(out, "%s-%s-%s.png" % (tag, eye, name))
            shoot(page, path, heads["box"])
            heads_strip(path, path[:-4] + "-heads.png", heads["cast"])
            facts["views"]["%s %s" % (eye, name)] = [dict(role=h["role"], away_m=round(h["away"], 2), px_per_m=round(h["px_per_m"], 1), face_px=round(h["px_per_m"] * FACE_M, 1), eye_px=round(h["px_per_m"] * EYE_M, 1)) for h in heads["cast"]]
            for i, h in enumerate(heads["cast"]):
                page.value("window.forgeWatch.face(%d, %s); 1" % (i, close))
                settle(page)
                near = json.loads(page.value(HEADS))
                shoot(page, os.path.join(out, "%s-close-%s-%s.png" % (tag, h["role"], name)), near["box"])
                n = near["cast"][i]
                facts["views"].setdefault("close %s" % name, []).append(dict(role=n["role"], away_m=round(n["away"], 2), px_per_m=round(n["px_per_m"], 1), face_px=round(n["px_per_m"] * FACE_M, 1), eye_px=round(n["px_per_m"] * EYE_M, 1)))
        facts["rows"] = heads["rows"]
    finally:
        page.close()
    with open(os.path.join(out, "%s-faces.json" % tag), "w") as f:
        json.dump(facts, f, indent=1)
    for view, cast in facts["views"].items():
        print("FACES %s: %s" % (view, "; ".join("%s %.1f m off, a face %.0f pixels wide, an eye %.1f" % (c["role"], c["away_m"], c["face_px"], c["eye_px"]) for c in cast)))


main()
