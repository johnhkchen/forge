"""Who wears what loose, and which of their clips had their cloth moved the way cloth is moved now. No Blender.

    python3 scripts/fabric_survey.py [--runs runs] [--shots shots] [--out evidence/fabric/survey.json] [--stale]

Cloth moves in one place only: swing.py, the last step of every bake of a motion onto a character (the walk, a run,
a shot, a fight, a ride, the screen-test motions: all of them go through scripts/motion/apply_motion.py or the walk
profile, and both run what the rig asks for after a bake). A clip that was baked before that step last changed
still plays the cloth it was given then. This reads every clip there is (runs/*/profiles/*.glb with a motion in
it, shots/*/*.glb) and says, for each character:

    what it wears loose   each garment the skeleton has chains for, the kind cloth.py said it is (a skirt, an
                          apron, a hood...), where it hangs from and how many chains; and what it holds without
                          chains (a collar, a loose shirt)
    its clips             which fabric step moved the cloth in each (swing.py writes its number, FABRIC, into the
                          skeleton's note with every bake), and which are stale: baked by an older one, or by none

A character with no chains in any clip wears nothing loose (or its loose things were never told from the rest of
it: a block-out built as one mesh has no gear to hang). `--stale` prints only what should be baked again and how.
"""

import ast
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def fabric_now():
    """swing.py's FABRIC: the number of the way cloth is moved now."""
    with open(os.path.join(REPO, ".claude", "skills", "tidy-mesh", "scripts", "swing.py")) as f:
        for node in ast.parse(f.read()).body:
            if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "FABRIC":
                return int(node.value.value)
    return 0


def read_glb(path):
    """A .glb's JSON, or None."""
    try:
        with open(path, "rb") as f:
            if f.read(4) != b"glTF":
                return None
            f.read(8)
            size, _ = struct.unpack("<II", f.read(8))
            return json.loads(f.read(size))
    except (OSError, ValueError, struct.error):
        return None


def cloth_of(doc):
    """What a file says of its loose cloth: (the chains by garment and the bone each hangs from: {(slug, parent):
    count}, the skeleton's own note or None, the names of its motions)."""
    nodes = doc.get("nodes") or []
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}
    chains = {}
    for i, n in enumerate(nodes):
        name = n.get("name", "")
        if name.startswith("cloth_") and i in parent and not nodes[parent[i]].get("name", "").startswith("cloth_"):
            key = (name[len("cloth_"):].rsplit("_", 2)[0], nodes[parent[i]].get("name"))
            chains[key] = chains.get(key, 0) + 1
    note = None
    for n in nodes:
        told = (n.get("extras") or {}).get("forge_cloth")
        if told:
            try:
                note = json.loads(told) if isinstance(told, str) else told
            except ValueError:
                note = None
    return chains, note, [a.get("name") for a in doc.get("animations") or []]


def judge(chains, note, now):
    """One clip's state: "no loose cloth", "current", or why it is stale."""
    if not chains:
        return "no loose cloth"
    swung = (note or {}).get("swung") or {}
    if swung.get("fabric") == now:
        return "current" if swung.get("simulated") else "current (nothing of its own to simulate)"
    if swung.get("fabric"):
        return "stale: moved by fabric step %s, now %s" % (swung["fabric"], now)
    return "stale: moved before the cloth was simulated (weights on strings)"


def survey(runs, shots):
    now = fabric_now()
    out = {"fabric": now, "characters": {}, "takes": {}}
    for run in sorted(os.listdir(runs)) if os.path.isdir(runs) else []:
        profiles = os.path.join(runs, run, "profiles")
        if not os.path.isdir(profiles):
            continue
        mine = {"garments": {}, "clips": {}}
        for name in sorted(os.listdir(profiles)):
            if not name.endswith(".glb"):
                continue
            doc = read_glb(os.path.join(profiles, name))
            if not doc:
                continue
            chains, note, motions = cloth_of(doc)
            if not motions:
                continue
            mine["clips"][name] = judge(chains, note, now)
            version = name.split("-")[0]
            for g in (note or {}).get("garments") or []:
                mine["garments"].setdefault(version, {})["%s (%s)" % (g.get("gear"), g.get("kind"))] = "hangs from the %s on %d chains of %s" % (g.get("parent"), g.get("chains"), g.get("bones_a_chain")) if g.get("chains") else "no chains: held (%s)" % g.get("card")
            if chains and not (note or {}).get("garments"):
                for (slug, parent), count in chains.items():
                    mine["garments"].setdefault(version, {})["%s (kind not written)" % slug] = "hangs from the %s on %d chains" % (parent, count)
        if mine["clips"]:
            out["characters"][run] = mine
    for take in sorted(os.listdir(shots)) if os.path.isdir(shots) else []:
        folder = os.path.join(shots, take)
        if not os.path.isdir(folder):
            continue
        clips = {}
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".glb"):
                continue
            doc = read_glb(os.path.join(folder, name))
            if not doc:
                continue
            chains, note, motions = cloth_of(doc)
            if motions and chains:
                clips[name] = judge(chains, note, now)
        if clips:
            out["takes"][take] = clips
    return out


def again(name, where):
    """How a stale clip is baked again."""
    kind = name[:-4].split("-", 1)[1] if "-" in name else name
    if where.startswith("shots"):
        return "just cast %s <its run> \"\" %s  (or the recipe that made the take: just fight, just skate-ride, the casting tape)" % (os.path.basename(where), kind)
    if kind in ("walk", "rom", "run"):
        return "just tidy %s %s" % (where, kind)
    if kind.startswith("screen-"):
        return "just screen-play %s %s --again" % (os.path.basename(where), kind[len("screen-"):])
    if kind.startswith("hero"):
        return "just cast <the hero shot> %s (then just adopt)" % where
    return "the recipe that made it"


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    flag = lambda name, default: args[args.index(name) + 1] if name in args else default  # noqa: E731
    runs, shots = flag("--runs", os.path.join(REPO, "runs")), flag("--shots", os.path.join(REPO, "shots"))
    found = survey(runs, shots)
    only_stale = "--stale" in args
    stale = 0
    for run, mine in found["characters"].items():
        loose = {k: v for k, v in mine["clips"].items() if v != "no loose cloth"}
        old = {k: v for k, v in loose.items() if v.startswith("stale")}
        stale += len(old)
        if only_stale and not old:
            continue
        print("FABRIC %s: %s" % (run, "nothing loose in any of its %d clips" % len(mine["clips"]) if not loose else "%d clips with loose cloth, %d stale" % (len(loose), len(old))))
        if not only_stale:
            for version, garments in sorted(mine["garments"].items()):
                for garment, how in sorted(garments.items()):
                    print("FABRIC   %s wears: %s, %s" % (version, garment, how))
        for name, state in sorted(old.items()):
            print("FABRIC   %s is %s -> %s" % (name, state, again(name, os.path.join(os.path.basename(runs), run))))
    for take, clips in found["takes"].items():
        old = {k: v for k, v in clips.items() if v.startswith("stale")}
        stale += len(old)
        if only_stale and not old:
            continue
        print("FABRIC take %s: %d films with loose cloth, %d stale" % (take, len(clips), len(old)))
        for name, state in sorted(old.items()):
            print("FABRIC   %s is %s -> %s" % (name, state, again(name, os.path.join("shots", take))))
    out = flag("--out", "")
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w") as f:
            json.dump(found, f, indent=1)
    print("RESULT " + json.dumps({"fabric": found["fabric"], "characters": len(found["characters"]), "takes": len(found["takes"]), "stale": stale, "out": out or None}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
