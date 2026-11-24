"""Stills of the cast's heads on the watch page in two looks, from three distances, taken by a headless Chrome:
is a face as clear in "Pixels, both" as it is in bold ink?

    python3 scripts/impostor/clear_shots.py [--base http://localhost:8042/] [--take crew-candy-shop] [--out evidence/clear]
        [--tag after] [--at 24] [--looks joe,pixel-both] [--eyes crew,two,close] [--ratio 1]
        [--sides joe:after,pixel-both:before,pixel-both:after]

The gallery must be running on that port. With the take stopped at --at seconds, for every look and eye it takes

    <tag>-<at>-<eye>-<role>-<look>.png          the picture (for the crew camera, one picture: <tag>-<at>-crew-<look>.png)
    <tag>-<at>-<eye>-<role>-<look>-head.png     the head cut out of it, blown up to 320 pixels

and writes <tag>-<at>-heads.json: where each head was and how many of the picture's pixels a metre is there.

The eyes are the face judge's (judge_faces.py), so a still and a count are of the same picture:
    crew    the set's crew camera
    two     2 m from the head, on the crew camera's side, looking at his chest
    close   1 m from the head, on the crew camera's side

A picture is the page's own, pixel for pixel (read off its canvas, not a photograph of the window).

--sides lays heads that are already there side by side, one row a dancer and eye, one column each look:tag named,
into <out>/sides-<at>-<role>.png (needs numpy: this file runs itself again in Blender's own Python when
this Python has none). --ratio 2 takes the pictures as a screen with two device pixels to a point does.
Prints SHOTS lines.
"""

import base64
import glob
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts", "world"))
sys.path.insert(0, HERE)

HEAD_M = 0.36    # the square cut out round a head, metres
SHOWN_PX = 320   # ... and how big it is shown

# Stand the eye, and say where one of the cast's head is in the picture.
EYE = """(() => {
  const w = window.forgeWatch, v = w.viewer, T = w.THREE, actor = v.cast[%(who)d], kind = %(eye)s;
  const head = new T.Vector3().setFromMatrixPosition(actor.bones.head.matrixWorld);
  head.y += 0.1 / (actor.role.size || 1);
  if (kind === "crew") v.useEye("crew");
  else {
    const crew = v.fixed.crew.position;
    v.useEye("");
    const toward = new T.Vector3(crew.x - head.x, 0, crew.z - head.z).normalize();
    v.free.position.copy(head).addScaledVector(toward, kind === "two" ? 2.0 : 1.0).add(new T.Vector3(0, 0.05, 0));
    v.controls.target.copy(head).add(new T.Vector3(0, kind === "two" ? -0.25 : 0, 0));
    v.controls.update();
  }
  return 1;
})()"""
GRAB = "(() => { const v = window.forgeWatch.viewer; cancelAnimationFrame(v.frame); v.tick(); return v.renderer.domElement.toDataURL('image/png'); })()"
WHERE = """(() => {
  const w = window.forgeWatch, v = w.viewer, T = w.THREE, actor = v.cast[%(who)d], cam = v.camera;
  const box = { width: v.renderer.domElement.width, height: v.renderer.domElement.height };
  const head = new T.Vector3().setFromMatrixPosition(actor.bones.head.matrixWorld);
  head.y += 0.1 / (actor.role.size || 1);
  cam.updateMatrixWorld();
  const ahead = head.clone().applyMatrix4(cam.matrixWorldInverse).z * -1;
  const p = head.clone().project(cam);
  return JSON.stringify({ x: (p.x * 0.5 + 0.5) * box.width, y: (0.5 - p.y * 0.5) * box.height,
    ahead, px_per_m: box.height / (2 * ahead * Math.tan(T.MathUtils.degToRad(cam.fov) / 2)) });
})()"""


def settle(page):
    page.value("new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(() => done(1)))))", wait=True)
    time.sleep(0.4)


def cut_head(path, out, where, ratio=1):
    """The head cut square out of a picture and blown up whole. Needs numpy."""
    import numpy as np
    import impostor
    picture = impostor.read_png(path)[::-1][..., :3]
    half = max(4, int(round(HEAD_M / 2.0 * where["px_per_m"] * ratio)))
    x, y = int(round(where["x"] * ratio)), int(round(where["y"] * ratio))
    cut = np.full((2 * half, 2 * half, 3), 250, dtype=np.uint8)
    y0, y1, x0, x1 = max(0, y - half), min(picture.shape[0], y + half), max(0, x - half), min(picture.shape[1], x + half)
    if y1 > y0 and x1 > x0:
        cut[y0 - (y - half):y1 - (y - half), x0 - (x - half):x1 - (x - half)] = picture[y0:y1, x0:x1]
    index = np.minimum((np.arange(SHOWN_PX) * 2 * half) // SHOWN_PX, 2 * half - 1)
    impostor.write_png(out, cut[index][:, index][::-1])


def sides(out, at, columns, eyes, roles):
    import numpy as np
    import impostor
    for role in roles:
        rows = []
        for eye in eyes:
            cells = []
            for column in columns:
                look, tag = column.split(":")
                path = os.path.join(out, "%s-%s-%s-%s-%s-head.png" % (tag, at, eye, role, look))
                cells.append(impostor.read_png(path)[..., :3] if os.path.isfile(path) else np.full((SHOWN_PX, SHOWN_PX, 3), 250, dtype=np.uint8))
                cells.append(np.full((SHOWN_PX, 8, 3), 255, dtype=np.uint8))
            rows.append(np.concatenate(cells[:-1], axis=1))
            rows.append(np.full((8, rows[0].shape[1], 3), 255, dtype=np.uint8))
        path = os.path.join(out, "sides-%s-%s.png" % (at, role))
        impostor.write_png(path, np.concatenate(rows[:-1][::-1], axis=0))  # read_png has rows from the bottom up: the first eye goes on top
        print("SHOTS %s (down: %s; across: %s)" % (path, ", ".join(eyes), ", ".join(columns)), flush=True)


def main():
    args = sys.argv[1:]
    flag = lambda name, default: args[args.index(name) + 1] if name in args else default
    base, take, out, tag = flag("--base", "http://localhost:8042/"), flag("--take", "crew-candy-shop"), os.path.abspath(flag("--out", os.path.join(REPO, "evidence", "clear"))), flag("--tag", "after")
    at, ratio = flag("--at", "24"), int(flag("--ratio", "1"))
    looks, eyes = flag("--looks", "joe,pixel-both").split(","), flag("--eyes", "crew,two,close").split(",")
    if "--sides" in args:
        return sides(out, at, flag("--sides", "").split(","), eyes, flag("--roles", "frontman,left,right").split(","))
    import test_walkabout  # (the gallery in a headless Chrome tab)
    os.makedirs(out, exist_ok=True)
    page = test_walkabout.Page(base, gpu=True)
    said = {}
    try:
        page.size(1280, 900, ratio, False)
        page.open("#/watch/%s" % take)
        page.until("window.forgeWatch && window.forgeWatch.state().ready && !document.querySelector('.watch-pane .status')", 120)
        page.value("window.forgeWatch.set({ playing: false, time: %s }); 1" % at)
        roles = json.loads(page.value("JSON.stringify(window.forgeWatch.state().cast.map((c) => c.role))"))
        for look in looks:
            page.value("window.forgeWatch.set({ cards: true }); window.forgeWatch.look(%s).then(() => 1)" % json.dumps(look), wait=True)
            for eye in eyes:
                for i, role in enumerate(roles):
                    page.value(EYE % {"who": i, "eye": json.dumps(eye)})
                    settle(page)
                    where = json.loads(page.value(WHERE % {"who": i}))
                    path = os.path.join(out, "%s-%s-%s-%s.png" % (tag, at, eye, look) if eye == "crew" else "%s-%s-%s-%s-%s.png" % (tag, at, eye, role, look))
                    if eye != "crew" or i == 0:
                        with open(path, "wb") as f:
                            f.write(base64.b64decode(page.value(GRAB).split(",", 1)[1]))
                        print("SHOTS %s" % path, flush=True)
                    cut_head(path, os.path.join(out, "%s-%s-%s-%s-%s-head.png" % (tag, at, eye, role, look)), where)
                    said["%s|%s|%s" % (look, eye, role)] = {"away_m": round(where["ahead"], 2), "px_per_m": round(where["px_per_m"], 1)}
        errors = page.value("window.forgeWatch.state().error")
        if errors:
            print("SHOTS the page said: %s" % errors)
    finally:
        page.close()
    with open(os.path.join(out, "%s-%s-heads.json" % (tag, at)), "w") as f:
        json.dump(said, f, indent=1)


if __name__ == "__main__":
    try:
        import numpy  # noqa: F401
    except ImportError:
        found = sorted(glob.glob("/Applications/Blender.app/Contents/Resources/*/python/bin/python3*"))
        if found and not os.environ.get("CLEAR_SHOTS_AGAIN"):
            sys.exit(subprocess.run([found[-1], os.path.abspath(__file__)] + sys.argv[1:], env=dict(os.environ, CLEAR_SHOTS_AGAIN="1")).returncode)
    main()
