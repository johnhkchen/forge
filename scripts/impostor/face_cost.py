"""What pixel cards cost on the tag field with one gallery against another, turn about: two checkouts of this repo
served on two ports (say, before a change and after it), so the page's code and the sheets it picks both count.

    python3 scripts/impostor/face_cost.py out.json before=http://localhost:8030/ after=http://localhost:8028/ [goes]
        [--looks pixel-both] [--ways card-batch,card-far] [--models painted,detailed] [--counts 100,1000]

For Roosevelt's painted and detailed cards in "Pixels, both", drawn all at once and with the search off far away,
a hundred and a thousand runners: the tag page's own timing of one setting (the phone test's: 1080 by 608, poses
shared, 1.2 s to settle and 2.6 s timed), `goes` times each (3), the two galleries taking turns. Writes every go
and the middle one of each setting, with the size of the sheet that was read. Prints COST and MIDDLE lines.
--looks, --ways (the tag page's own names: mesh-batch and mesh-low are the meshes), --models and --counts time
other settings the same way. Needs Chrome; runs it without a window on this machine's own graphics card.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "world"))
import test_walkabout  # noqa: E402  (the gallery in a headless Chrome tab)

RUN = "2026-11-20T14-02-45-roosevelt-wrestler-1890s"
out = sys.argv[1]
bases = dict(a.split("=", 1) for a in sys.argv[2:4])
rounds = int(sys.argv[4]) if len(sys.argv) > 4 and not sys.argv[4].startswith("--") else 3
flag = lambda name, default: sys.argv[sys.argv.index(name) + 1].split(",") if name in sys.argv else default
SETTINGS = [(look, model, way, count) for look in flag("--looks", ["pixel-both"]) for model in flag("--models", ["painted", "detailed"])
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
                got = json.loads(page.value("window.forgeTag.field.timeOnce({ count: %d, way: %s, look: %s, model: %s }, 1.2, 2.6).then((t) => JSON.stringify({ ...t, sheet: window.forgeTag.field.sheet ? window.forgeTag.field.sheet.size : null, folder: window.forgeTag.field.cardFolder || null }))"
                                            % (count, json.dumps(way), json.dumps(look), json.dumps(model)), wait=True))
                rows.append(dict(round=r, gallery=name, look=look, model=model, way=way, count=count, work=got["work"], frame=got["frame"], frame_slow=got["frame_slow"], frames=got["frames"], sheet=got.get("sheet"), folder=got.get("folder")))
                print("COST round %d %-6s %-11s %-8s %-10s %4d: %.1f ms of work, a frame every %.1f ms (slow ones %.1f), sheet %s" % (r, name, look, model, way, count, got["work"], got["frame"], got["frame_slow"], got.get("sheet")), flush=True)
        finally:
            page.close()
        time.sleep(2)
middle = lambda xs: sorted(xs)[len(xs) // 2]
table = {}
plain = SETTINGS and all(s[0] == "pixel-both" for s in SETTINGS)  # as this file first wrote them: no look in the name
for look, model, way, count in SETTINGS:
    for name in bases:
        mine = [x for x in rows if (x["gallery"], x["look"], x["model"], x["way"], x["count"]) == (name, look, model, way, count)]
        table[("%s|%s|%d|%s" % (model, way, count, name)) if plain else ("%s|%s|%s|%d|%s" % (look, model, way, count, name))] = dict(work=middle([x["work"] for x in mine]), low=min(x["work"] for x in mine), high=max(x["work"] for x in mine),
                                                              frame=middle([x["frame"] for x in mine]), frame_slow=max(x["frame_slow"] for x in mine), sheet=mine[0]["sheet"])
json.dump(dict(about="The tag field (%s), 1080 by 608, poses shared, headless Chrome on this Mac's GPU: the gallery before this work and after, turn about, %d goes each; work is the middle go's ms in a frame" % (", ".join(sorted(set(s[0] for s in SETTINGS))), rounds),
               galleries=bases, table=table, rows=rows), open(out, "w"), indent=1)
for k, v in table.items():
    print("MIDDLE %-40s %.1f ms (%.1f to %.1f), frame %.1f, sheet %s" % (k, v["work"], v["low"], v["high"], v["frame"], v["sheet"]))
