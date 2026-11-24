"""What cards cost on the tag field with the eye down among the runners, one gallery against another, turn about.

    python3 scripts/impostor/near_cost.py out.json before=http://localhost:8046/ after=http://localhost:8045/ [goes]
        [--looks joe,pixel-both] [--ways card-batch,card-far] [--models painted,detailed] [--counts 100,1000]

face_cost.py times the field from the phone test's eye, which stands well back: nobody is within the 8 m inside
which a runner gets a piece of the real model in each big joint (gallery/tag.js: JOINTS_M), so it cannot say what
those pieces cost. This stands the eye at head height in the middle of the field, looking across it, where the
runners near it fill the picture, and times the same way (1080 by 608, poses shared, 1.2 s to settle, 2.6 s
timed, `goes` times each (3), the galleries taking turns). It also says how many runners had pieces and how many
triangles those were, a typical frame. Writes every go and the middle one of each setting. Prints COST and MIDDLE
lines. Needs Chrome; runs it without a window on this machine's own graphics card.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "world"))
import test_walkabout  # noqa: E402  (the gallery in a headless Chrome tab)

RUN = "2026-11-20T14-02-45-roosevelt-wrestler-1890s"
TIME = """(async () => {
  const f = window.forgeTag.field, wait = (ms) => new Promise((done) => setTimeout(done, ms));
  Object.assign(f.state, { count: %(count)d, way: %(way)s, shared: true, model: %(model)s, paused: false });
  await f.useLook(%(look)s);
  f.measuring = true;
  f.restart();
  f.camera.position.set(0, 1.6, 5);
  f.controls.target.set(0, 0.9, 0);
  f.controls.update();
  await wait(1200);
  for (const list of Object.values(f.times)) list.length = 0;
  const near = [];
  const timer = setInterval(() => { if (f.jointsDrawn) near.push(f.jointsDrawn); }, 100);
  await wait(2600);
  clearInterval(timer);
  f.measuring = false;
  const sorted = (list) => [...list].sort((a, b) => a - b), middle = (list) => (list.length ? sorted(list)[Math.floor(list.length / 2)] : 0);
  return JSON.stringify({ work: middle(f.times.work), frame: middle(f.times.frame), frames: f.times.frame.length, folder: f.cardFolder,
    runners: middle(near.map((n) => n.runners)), triangles: middle(near.map((n) => n.triangles)) });
})()"""
out = sys.argv[1]
bases = dict(a.split("=", 1) for a in sys.argv[2:4])
rounds = int(sys.argv[4]) if len(sys.argv) > 4 and not sys.argv[4].startswith("--") else 3
flag = lambda name, default: sys.argv[sys.argv.index(name) + 1].split(",") if name in sys.argv else default
SETTINGS = [(look, model, way, count) for look in flag("--looks", ["joe", "pixel-both"]) for model in flag("--models", ["painted", "detailed"])
            for way in flag("--ways", ["card-batch", "card-far"]) for count in [int(c) for c in flag("--counts", ["100", "1000"])]]
rows = []
for r in range(rounds):
    for name, base in (list(bases.items()) if r % 2 == 0 else list(bases.items())[::-1]):
        page = test_walkabout.Page(base, gpu=True)
        try:
            page.size(1280, 900, 1, False)
            page.open("#/tag/%s" % RUN)
            page.until("window.forgeTag && window.forgeTag.state().ready", 120)
            page.value("(() => { const f = window.forgeTag.field; f.fixed = [1080, 608]; f.controls.enabled = false; f.layout(); return 1; })()")
            for look, model, way, count in (SETTINGS if r % 2 == 0 else SETTINGS[::-1]):
                got = json.loads(page.value(TIME % {"count": count, "way": json.dumps(way), "look": json.dumps(look), "model": json.dumps(model)}, wait=True))
                rows.append(dict(got, round=r, gallery=name, look=look, model=model, way=way, count=count))
                print("COST round %d %-6s %-11s %-8s %-10s %4d: %.1f ms of work, a frame every %.1f ms; %d runners with pieces, %d triangles" % (r, name, look, model, way, count, got["work"], got["frame"], got["runners"], got["triangles"]), flush=True)
        finally:
            page.close()
        time.sleep(2)
middle = lambda xs: sorted(xs)[len(xs) // 2]
table = {}
for look, model, way, count in SETTINGS:
    for name in bases:
        mine = [x for x in rows if (x["gallery"], x["look"], x["model"], x["way"], x["count"]) == (name, look, model, way, count)]
        table["%s|%s|%s|%d|%s" % (look, model, way, count, name)] = dict(work=middle([x["work"] for x in mine]), low=min(x["work"] for x in mine), high=max(x["work"] for x in mine), frame=middle([x["frame"] for x in mine]),
                                                                       runners=middle([x["runners"] for x in mine]), triangles=middle([x["triangles"] for x in mine]))
json.dump(dict(about="The tag field with the eye among the runners (at 0, 1.6, 5, looking at the middle), 1080 by 608, poses shared, headless Chrome on this Mac's GPU: two galleries turn about, %d goes each; work is the middle go's ms in a frame; runners and triangles are the runners near enough to get pieces of the model in their joints, and those pieces" % rounds,
               galleries=bases, table=table, rows=rows), open(out, "w"), indent=1)
for k, v in table.items():
    print("MIDDLE %-44s %.1f ms (%.1f to %.1f), frame %.1f; %d runners with pieces, %d triangles" % (k, v["work"], v["low"], v["high"], v["frame"], v["runners"], v["triangles"]))
