"""Stills of the cast's bent joints on the watch page, from two galleries side by side (say, before a change and
after it), taken by a headless Chrome: does a bent knee, elbow or neck read as solid body?

    python3 scripts/impostor/joint_shots.py before=http://localhost:8030/ after=http://localhost:8044/
        [--take crew-candy-shop] [--out evidence/joints] [--looks joe,pixel-both]
        [--joints knee=1:shin_l@16.25,hip=2:thigh_r@42.25,elbow=0:forearm_r@37.5,neck=2:head@21.5,shoulder=0:upper_arm_r@15.75]
        [--eyes crew,2,1] [--stage 42.25]

Both galleries must be running. Each of --joints is a name, which of the cast (counted from 0), the bone whose
head is the joint, and the second of the take to stop at (judge_seams.py --deep finds where a joint is bent
furthest). For every joint and look, each gallery's picture is taken through each of --eyes (the set's crew
camera, or the free eye that many metres from the joint, on the crew camera's side of it), a square round the
joint is cut out of it and blown up, and the squares are laid out, one row an eye, one column a gallery:

    <joint>-<look>.png                 down: the eyes; across: the galleries, in the order given
    stage-<seconds>-<look>-<name>.png  --stage: the whole stage through the crew camera at that second, each gallery

A picture is the page's own, pixel for pixel (read off its canvas). Needs numpy to cut and lay out: this file
runs itself again in Blender's own Python when this Python has none. Prints SHOTS lines.
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

SQUARE_M = 0.55   # the square cut out round a joint, metres
SHOWN_PX = 420    # ... and how big it is shown

# Stand the eye, and say where the joint is in the picture.
EYE = """(() => {
  const w = window.forgeWatch, v = w.viewer, T = w.THREE, actor = v.cast[%(who)d], kind = %(eye)s;
  const at = new T.Vector3().setFromMatrixPosition(actor.bones[%(bone)s].matrixWorld);
  if (kind === "crew") v.useEye("crew");
  else {
    const crew = v.fixed.crew.position;
    v.useEye("");
    const toward = new T.Vector3(crew.x - at.x, 0, crew.z - at.z).normalize();
    v.free.position.copy(at).addScaledVector(toward, Number(kind)).add(new T.Vector3(0, 0.12 * Number(kind), 0));
    v.controls.target.copy(at);
    v.controls.update();
  }
  return 1;
})()"""
GRAB = "(() => { const v = window.forgeWatch.viewer; cancelAnimationFrame(v.frame); v.tick(); return v.renderer.domElement.toDataURL('image/png'); })()"
WHERE = """(() => {
  const w = window.forgeWatch, v = w.viewer, T = w.THREE, actor = v.cast[%(who)d], cam = v.camera;
  const box = { width: v.renderer.domElement.width, height: v.renderer.domElement.height };
  const at = new T.Vector3().setFromMatrixPosition(actor.bones[%(bone)s].matrixWorld);
  cam.updateMatrixWorld();
  const ahead = at.clone().applyMatrix4(cam.matrixWorldInverse).z * -1;
  const p = at.clone().project(cam);
  return JSON.stringify({ x: (p.x * 0.5 + 0.5) * box.width, y: (0.5 - p.y * 0.5) * box.height,
    px_per_m: box.height / (2 * ahead * Math.tan(T.MathUtils.degToRad(cam.fov) / 2)) });
})()"""


def settle(page):
    page.value("new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(() => done(1)))))", wait=True)
    time.sleep(0.4)


def square(png, where):
    """The square round a joint cut out of a picture (a .png's bytes) and blown up whole: rows from the top down."""
    import numpy as np
    import impostor
    tmp = os.path.join(os.environ.get("TMPDIR", "/tmp"), "joint-shot-%d.png" % os.getpid())
    with open(tmp, "wb") as f:
        f.write(png)
    picture = impostor.read_png(tmp)[::-1][..., :3]
    os.remove(tmp)
    half = max(4, int(round(SQUARE_M / 2.0 * where["px_per_m"])))
    x, y = int(round(where["x"])), int(round(where["y"]))
    cut = np.full((2 * half, 2 * half, 3), 250, dtype=np.uint8)
    y0, y1, x0, x1 = max(0, y - half), min(picture.shape[0], y + half), max(0, x - half), min(picture.shape[1], x + half)
    if y1 > y0 and x1 > x0:
        cut[y0 - (y - half):y1 - (y - half), x0 - (x - half):x1 - (x - half)] = picture[y0:y1, x0:x1]
    index = np.minimum((np.arange(SHOWN_PX) * 2 * half) // SHOWN_PX, 2 * half - 1)
    return cut[index][:, index]


def main():
    import numpy as np
    import impostor
    import test_walkabout  # (the gallery in a headless Chrome tab)
    args = sys.argv[1:]
    flag = lambda name, default: args[args.index(name) + 1] if name in args else default
    galleries = [a.split("=", 1) for a in args if "=" in a and a.split("=", 1)[1].startswith("http")]
    take, out = flag("--take", "crew-candy-shop"), os.path.abspath(flag("--out", os.path.join(REPO, "evidence", "joints")))
    looks, eyes = flag("--looks", "joe,pixel-both").split(","), flag("--eyes", "crew,2,1").split(",")
    joints = []
    for item in flag("--joints", "knee=1:shin_l@16.25,hip=2:thigh_r@42.25,elbow=0:forearm_r@37.5,neck=2:head@21.5,shoulder=0:upper_arm_r@15.75").split(","):
        name, rest = item.split("=")
        who, rest = rest.split(":")
        bone, at = rest.split("@")
        joints.append((name, int(who), bone, at))
    stage = flag("--stage", "")
    os.makedirs(out, exist_ok=True)
    cut = {}
    for gallery, base in galleries:
        page = test_walkabout.Page(base, gpu=True)
        try:
            page.size(1280, 900, 1, False)
            page.open("#/watch/%s" % take)
            page.until("window.forgeWatch && window.forgeWatch.state().ready && !document.querySelector('.watch-pane .status')", 120)
            for look in looks:
                page.value("window.forgeWatch.set({ cards: true, playing: false }); window.forgeWatch.look(%s).then(() => 1)" % json.dumps(look), wait=True)
                for name, who, bone, at in joints:
                    page.value("window.forgeWatch.set({ playing: false, time: %s }); 1" % at)
                    for eye in eyes:
                        page.value(EYE % {"who": who, "bone": json.dumps(bone), "eye": json.dumps(eye)})
                        settle(page)
                        where = json.loads(page.value(WHERE % {"who": who, "bone": json.dumps(bone)}))
                        cut[(name, look, eye, gallery)] = square(base64.b64decode(page.value(GRAB).split(",", 1)[1]), where)
                if stage:
                    page.value("window.forgeWatch.set({ playing: false, time: %s }); window.forgeWatch.eye('crew'); 1" % stage)
                    settle(page)
                    path = os.path.join(out, "stage-%s-%s-%s.png" % (stage, look, gallery))
                    with open(path, "wb") as f:
                        f.write(base64.b64decode(page.value(GRAB).split(",", 1)[1]))
                    print("SHOTS %s" % path, flush=True)
            errors = page.value("window.forgeWatch.state().error")
            if errors:
                print("SHOTS %s said: %s" % (gallery, errors))
        finally:
            page.close()
    for name, _, _, at in joints:
        for look in looks:
            rows = []
            for eye in eyes:
                cells = []
                for gallery, _ in galleries:
                    cells += [cut[(name, look, eye, gallery)], np.full((SHOWN_PX, 8, 3), 255, dtype=np.uint8)]
                rows += [np.concatenate(cells[:-1], axis=1), np.full((8, cells[0].shape[1] * len(galleries) + 8 * (len(galleries) - 1), 3), 255, dtype=np.uint8)]
            path = os.path.join(out, "%s-%s.png" % (name, look))
            impostor.write_png(path, np.concatenate(rows[:-1], axis=0)[::-1])
            print("SHOTS %s (at %s s; down: %s; across: %s)" % (path, at, ", ".join("the crew camera" if e == "crew" else "%s m" % e for e in eyes), ", ".join(g for g, _ in galleries)), flush=True)


if __name__ == "__main__":
    try:
        import numpy  # noqa: F401
    except ImportError:
        found = sorted(glob.glob("/Applications/Blender.app/Contents/Resources/*/python/bin/python3*"))
        if found and not os.environ.get("JOINT_SHOTS_AGAIN"):
            sys.exit(subprocess.run([found[-1], os.path.abspath(__file__)] + sys.argv[1:], env=dict(os.environ, JOINT_SHOTS_AGAIN="1")).returncode)
    main()
