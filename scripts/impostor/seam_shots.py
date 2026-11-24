"""Pictures of the cast's joints on the watch page, taken by a headless Chrome: is there a line or a hole where
two cards meet?

    python3 scripts/impostor/seam_shots.py [--base http://localhost:8028/] [--take crew-candy-shop] [--out evidence/seams]
        [--tag after] [--at 24] [--eye crew] [--looks pixel-both,pixel-baked,comic,joe]
        [--joints 0:forearm_l,0:shin_r,2:forearm_l,2:shin_l] [--close 2.6] [--near 1.1] [--field RUN] [--model detailed]

The gallery must be running on that port. With the take stopped at --at seconds, for every look it takes:

    <tag>-<at>-<eye>-<look>-cards.png               the whole stage through the set's camera, the cast as cards
    <tag>-<at>-close-<role>-<look>-cards.png        the free eye --close metres from each of the cast
    <tag>-<at>-joint-<role>-<bone>-<look>-cards.png the free eye --near metres from a joint (--joints: which of
                                                    the cast, counted from 0, and which bone's head)
    <tag>-<at>-<eye>-<look>-meshes.png              the same stage with the cast as meshes, to see they are as they were

--field RUN takes the tag field of that run instead (#/tag/RUN, a hundred runners at one moment of the game):

    <tag>-field-<look>-<cards|meshes>.png           the field
    <tag>-field-<look>-<cards|meshes>-close.png     the eye close to one runner

Prints SHOTS lines.
"""

import base64
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts", "world"))
import test_walkabout  # noqa: E402  (the gallery in a headless Chrome tab)

BOX = """(() => {
  const v = window.forgeWatch.viewer;
  v.renderer.domElement.scrollIntoView({ block: "center" });
  const b = v.renderer.domElement.getBoundingClientRect();
  return JSON.stringify([b.left + window.scrollX, b.top + window.scrollY, b.width, b.height]);
})()"""

# The free eye stood close to one of a figure's joints (the head of a bone), on the house's side of it.
JOINT = """(() => {
  const w = window.forgeWatch, v = w.viewer, T = w.THREE, away = %(away)s;
  const at = new T.Vector3().setFromMatrixPosition(v.cast[%(who)d].bones[%(bone)s].matrixWorld);
  const from = (v.fixed.crew || v.free).position.clone().sub(at).setY(0).normalize();
  v.useEye("");
  v.controls.target.copy(at);
  v.free.position.copy(at).addScaledVector(from, away).add(new T.Vector3(0, 0.15 * away, 0));
  v.controls.update();
  return 1;
})()"""


def settle(page):
    page.value("new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(() => done(1)))))", wait=True)
    time.sleep(0.4)


def shoot(page, path, box=BOX):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    box = json.loads(page.value(box))
    got = page.tab.ask("Page.captureScreenshot", format="png", clip={"x": box[0], "y": box[1], "width": box[2], "height": box[3], "scale": 1})
    with open(path, "wb") as f:
        f.write(base64.b64decode(got["data"]))
    print("SHOTS %s" % path, flush=True)


def main():
    args = sys.argv[1:]
    flag = lambda name, default: args[args.index(name) + 1] if name in args else default
    base, take, out, tag = flag("--base", "http://localhost:8028/"), flag("--take", "crew-candy-shop"), os.path.abspath(flag("--out", os.path.join(REPO, "evidence", "seams"))), flag("--tag", "after")
    at, eye, close, near = flag("--at", "24"), flag("--eye", "crew"), float(flag("--close", "2.6")), float(flag("--near", "1.1"))
    looks = flag("--looks", "pixel-both,pixel-baked,comic,joe").split(",")
    joints = [(int(pair.split(":")[0]), pair.split(":")[1]) for pair in flag("--joints", "0:forearm_l,0:shin_r,2:forearm_l,2:shin_l").split(",") if pair]
    page = test_walkabout.Page(base, gpu=True)
    field = flag("--field", "")
    try:
        page.size(1280, 900, 1, False)
        if field:
            page.open("#/tag/%s" % field)
            page.until("window.forgeTag && window.forgeTag.state().ready", 120)
            page.value("(() => { const f = window.forgeTag.field; f.fixed = [1080, 608]; f.layout(); return 1; })()")
            where = BOX.replace("window.forgeWatch.viewer", "window.forgeTag.field")
            for look in looks:
                for way, name in (("card-batch", "cards"), ("mesh-batch", "meshes")):
                    page.value("window.forgeTag.still(100, %s, %s, 600, %s).then(() => 1)" % (json.dumps(way), json.dumps(look), json.dumps(flag("--model", "detailed"))), wait=True)
                    settle(page)
                    shoot(page, os.path.join(out, "%s-field-%s-%s.png" % (tag, look, name)), where)
                    page.value("window.forgeTag.near(0); 1")
                    settle(page)
                    shoot(page, os.path.join(out, "%s-field-%s-%s-close.png" % (tag, look, name)), where)
                    page.value("window.forgeTag.field.controls.reset(); 1")
            return
        page.open("#/watch/%s" % take)
        page.until("window.forgeWatch && window.forgeWatch.state().ready && !document.querySelector('.watch-pane .status')", 120)
        page.value("window.forgeWatch.set({ playing: false, time: %s }); 1" % at)
        roles = json.loads(page.value("JSON.stringify(window.forgeWatch.state().cast.map((c) => c.role))"))
        for look in looks:
            page.value("window.forgeWatch.set({ cards: true }); window.forgeWatch.look(%s).then(() => 1)" % json.dumps(look), wait=True)
            page.value("window.forgeWatch.eye(%s); 1" % json.dumps(eye))
            settle(page)
            shoot(page, os.path.join(out, "%s-%s-%s-%s-cards.png" % (tag, at, eye, look)))
            for i, role in enumerate(roles):
                page.value("window.forgeWatch.near(%d, %s); 1" % (i, close))
                settle(page)
                shoot(page, os.path.join(out, "%s-%s-close-%s-%s-cards.png" % (tag, at, role, look)))
            for i, bone in joints:
                page.value(JOINT % {"who": i, "bone": json.dumps(bone), "away": near})
                settle(page)
                shoot(page, os.path.join(out, "%s-%s-joint-%s-%s-%s-cards.png" % (tag, at, roles[i], bone, look)))
            page.value("window.forgeWatch.set({ cards: false }); window.forgeWatch.eye(%s); 1" % json.dumps(eye))
            settle(page)
            shoot(page, os.path.join(out, "%s-%s-%s-%s-meshes.png" % (tag, at, eye, look)))
        errors = page.value("window.forgeWatch.state().error")
        if errors:
            print("SHOTS the page said: %s" % errors)
    finally:
        page.close()


main()
