"""Tests of the fabric path, with no Blender: what kind of garment a hanging piece is, what each kind is like, how
the simulated cloth is carried onto bones and kept out of the body, how the cards read the same description, and
which clips are stale.

    python3 scripts/test_fabric.py [--runs runs]

  kinds     cloth.py's kind_of names a hanging piece from how it hangs alone: a long skirt, a short one, an apron,
            a coat's tails, a cape, a hood, a sleeve, a sash, a loose shirt, a collar; a tunic's neckline is not
            a hood. Every kind in its table says all that swing.py and the cards read; the ones with no chains say
            how far they are held
  swing     swing.py: a garment with no description is plain cloth kept out of what it hangs over; a description
            is taken as written and a number given for all wins; a garment is never kept out of the bone it hangs
            from, nor a sleeve out of its own arm. A patch of points carried by a turn and a move is found again;
            a patch of points all in a row, which says nothing of the turn about the row, goes as the bone above
            went and does not flip. A point is in a rod's own frame where it is in the world's
  cards     impostor.py reads one description: a garment the description calls a piece is the dress, wherever it
            hangs from (a cape from the chest); a hood rides; a collar and a loose shirt are held, by their own
            share; a hood is not held back from the head at all; clothing nothing is said of is held by the
            default. A file with no description reads as it always did: chains over the legs are the dress
  survey    fabric_survey.py: a clip with chains and this fabric step's number is current; one with an older
            number, or none, is stale, and says how to bake it again; one with no chains has no loose cloth
  baked     with --runs holding characters whose clips this fabric step baked (their .json records beside the
            clips): every such clip's cloth was simulated, is off the floor, turns inside its limits, and a loop
            closes with no seam; what each wears is written with its kind
"""

import ast
import glob
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

try:
    import numpy as np
except ImportError:  # (as the flat cards' tests do: Blender's own Python has numpy)
    found = sorted(glob.glob("/Applications/Blender.app/Contents/Resources/*/python/bin/python3*"))
    if not found or os.environ.get("FABRIC_TEST_AGAIN"):
        print("skipped: the fabric tests need numpy (Blender's Python has it; none was found)")
        sys.exit(0)
    sys.exit(subprocess.run([found[-1], os.path.abspath(__file__)] + sys.argv[1:], env=dict(os.environ, FABRIC_TEST_AGAIN="1")).returncode)
SKILL = os.path.join(REPO, ".claude", "skills", "tidy-mesh", "scripts")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "impostor"))
import fabric_survey  # noqa: E402
import impostor  # noqa: E402

passed, failed = 0, 0


def check(what, ok, more=""):
    global passed, failed
    passed, failed = passed + bool(ok), failed + (not ok)
    print("    %s  %s%s" % ("ok  " if ok else "FAIL", what, ("  (%s)" % more) if more else ""))


def parts_of(script, *names):
    """Functions out of a skill script (which Blender runs whole) that need only numpy and math, by name; its PARAMS;
    and the plain numbers and names it sets at the top."""
    path = os.path.join(SKILL, script)
    with open(path) as f:
        source = f.read()
    tree = ast.parse(source)
    keep = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    keep += [node for node in tree.body if isinstance(node, ast.Assign) and not any(isinstance(n, (ast.Call, ast.Attribute, ast.Name)) for n in ast.walk(node.value))]
    space = {"np": np, "math": math}
    exec(compile(ast.Module(body=keep, type_ignores=[]), path, "exec"), space)
    return space


def test_kinds():
    cloth = parts_of("cloth.py", "kind_of", "facing_of")
    kind_of, kinds = cloth["kind_of"], cloth["PARAMS"]["kinds"]
    # (the bone it is worn on, all the way round?, which way an open one faces, how far round, how far down, how high its top: shares of the height)
    cases = [
        ("a skirt to the ankle, all round the hips", ("hips", True, None, 1.0, 0.43, 0.54), "skirt"),
        ("a kilt, all round the hips", ("hips", True, None, 1.0, 0.2, 0.55), "short skirt"),
        ("a tunic's hem, round the spine at the belt", ("spine", True, None, 1.0, 0.14, 0.6), "short skirt"),
        ("an apron in front of the hips", ("hips", False, "front", 0.25, 0.15, 0.55), "apron"),
        ("a coat's tails behind the hips", ("spine", False, "back", 0.3, 0.25, 0.6), "tails"),
        ("a coat's open skirts at the sides", ("hips", False, "side", 0.3, 0.25, 0.55), "tails"),
        ("a sash's end, a hand wide", ("hips", False, "side", 0.06, 0.2, 0.55), "sash"),
        ("a cape down the back from the shoulders", ("chest", False, "back", 0.4, 0.45, 0.82), "cape"),
        ("a robe from the shoulders to the shin", ("chest", True, None, 1.0, 0.6, 0.82), "skirt"),
        ("a loose shirt from the shoulders to the belt", ("chest", True, None, 1.0, 0.17, 0.82), "shirt"),
        ("the back of a hood", ("head", False, "back", 0.3, 0.11, 0.9), "hood"),
        ("a collar round the neck", ("neck", True, None, 0.4, 0.04, 0.85), "collar"),
        ("a lapel on the chest", ("chest", False, "front", 0.1, 0.04, 0.8), "collar"),
        ("a loose sleeve", ("forearm_l", True, None, 0.2, 0.1, 0.7), "sleeve"),
    ]
    wrong = [(what, kind_of(*how), want) for what, how, want in cases if kind_of(*how) != want]
    check("a hanging piece is named for how it hangs: %s" % ", ".join(sorted({want for _, _, want in cases})), not wrong, str(wrong))
    check("which way an open piece faces is read off the body, which faces -y", [cloth["facing_of"](a) for a in (-math.pi / 2, math.pi / 2, 0.0, math.pi)] == ["front", "back", "side", "side"])
    check("every kind it can name is in the table of kinds", {want for _, _, want in cases} <= set(kinds), str(sorted({want for _, _, want in cases} - set(kinds))))
    chained = {k: v for k, v in kinds.items() if v.get("chains")}
    needs = ("chains", "every", "bones", "bone_long", "centre", "mass", "bend", "damp", "shape", "swing", "reach", "collide", "floor", "card")
    missing = {k: [n for n in needs if n not in v] for k, v in chained.items() if any(n not in v for n in needs)}
    check("each kind that swings says how many chains, how heavy and stiff it is, how far it may swing and slide, what it is kept out of and how cards show it", not missing and len(chained) >= 8, str(missing))
    check("... sensibly: a long skirt is heavier than an apron and may swing further than a hood; a hood keeps its shape; only a long skirt has a chain at the very front and back",
          kinds["skirt"]["mass"] > kinds["apron"]["mass"] and kinds["skirt"]["swing"] > kinds["hood"]["swing"] and kinds["hood"]["shape"] > kinds["skirt"]["shape"]
          and [k for k, v in chained.items() if v["centre"]] == ["skirt"] and kinds["skirt"]["chains"][0] % 2 == 0)
    check("... kept out of parts of the body there are: legs, arms, trunk, head", all(set(v["collide"]) <= {"legs", "arms", "trunk", "head"} and v["collide"] for v in chained.values()))
    check("... shown by the cards as a piece of their own (what hangs over the legs or from the shoulders) or riding the bone they hang from (a hood, a sleeve, a sash)",
          {k for k, v in chained.items() if v["card"] == "piece"} == {"skirt", "short skirt", "apron", "tails", "cape"} and all(v["card"] in ("piece", "rides") for v in chained.values()))
    held = {k: v for k, v in kinds.items() if not v.get("chains")}
    check("a collar and a loose shirt have no chains: they stay with the body, and say how far the cards hold them back", set(held) == {"collar", "shirt"} and all(v["card"] == "held" and 0 < v["hold"] <= 1 for v in held.values()), str(held))


def test_swing():
    swing = parts_of("swing.py", "about_of", "rods_for", "thick_at", "local_in", "in_rods", "rigid")
    plain = swing["about_of"](None, "hips", {})
    check("a garment with no description is plain cloth, kept out of the legs, arms and trunk if it hangs over the legs",
          plain["collide"] == ["legs", "arms", "trunk"] and plain["mass"] == swing["PLAIN"]["mass"] and plain["floor"] is True)
    check("... and out of the trunk and arms if it hangs from higher", swing["about_of"](None, "head", {})["collide"] == ["trunk", "arms"])
    told = swing["about_of"]({"kind": "hood", "mass": 0.1, "bend": 4.0, "shape": 0.25, "swing": 80, "reach": 0.6, "collide": ["trunk"], "floor": False, "card": "rides"}, "head", {})
    check("a description is taken as written", (told["mass"], told["bend"], told["shape"], told["swing"], told["collide"], told["floor"]) == (0.1, 4.0, 0.25, 80, ["trunk"], False))
    check("... and a number given for every garment wins over it", swing["about_of"]({"mass": 0.1}, "head", {"mass": 0.4, "bend": None})["mass"] == 0.4)
    check("a garment is never kept out of the bone it hangs from", "hips" not in swing["rods_for"](["legs", "trunk"], "hips") and "thigh_l" in swing["rods_for"](["legs", "trunk"], "hips") and "chest" in swing["rods_for"](["legs", "trunk"], "hips"))
    sleeve = swing["rods_for"](["trunk", "arms"], "forearm_l")
    check("... nor a sleeve out of its own arm, though it is out of the other", not any(b in sleeve for b in ("upper_arm_l", "forearm_l", "hand_l")) and "forearm_r" in sleeve and "chest" in sleeve, str(sleeve))

    rng = np.random.default_rng(3)
    a = rng.normal(size=(30, 3)) * 0.1
    angle, axis = 1.1, np.array([0.3, -0.5, 0.8]) / np.linalg.norm([0.3, -0.5, 0.8])
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    turn = np.eye(3) + math.sin(angle) * k + (1 - math.cos(angle)) * k @ k
    move = np.array([0.2, -0.1, 0.4])
    got = swing["rigid"](a, a @ turn.T + move, rng.uniform(0.1, 1.0, size=30))
    check("a patch of cloth carried by a turn and a move: both are found again", np.allclose(got[:3, :3], turn, atol=1e-9) and np.allclose(got[:3, 3], move, atol=1e-9))
    lean = np.eye(4)
    lean[:3, :3], lean[:3, 3] = turn, move
    got = swing["rigid"](a, a @ turn.T + move, np.ones(30), np.zeros(3), lean)
    check("... the same when it also leans on how the bone above was carried, and that agrees", np.allclose(got[:3, :3], turn, atol=1e-9) and np.allclose(got[:3, 3], move, atol=1e-9))
    row = np.array([[x, 0.0, 0.0] for x in np.linspace(-0.1, 0.1, 6)])  # six points in a row along x: nothing says how they turn about x
    spun = np.array([[1, 0, 0], [0, -1, 0], [0, 0, -1.0]])  # ... so half a turn about x fits them as well as none
    got = swing["rigid"](row, row + [0.0, 0.0, -0.05], np.ones(6), np.zeros(3), np.eye(4))
    turned = math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(got[:3, :3]) - 1.0) / 2.0))))
    check("a patch of points all in a row goes much as the bone above went (it turns %.0f degrees to meet it part way), and does not flip over about the row" % turned,
          turned < 20.0 and not np.allclose(got[:3, :3], spun, atol=0.5) and abs(got[2, 3] + 0.05) < 0.01, str(np.round(got, 3).tolist()))
    free = swing["rigid"](row, row + [0.0, 0.0, -0.05], np.ones(6))
    check("... with nothing to lean on, the same row is carried by its move alone or by half a turn about itself, either as well: that is why it leans",
          np.allclose(free[:3, :3] @ np.array([1.0, 0.0, 0.0]), [1.0, 0.0, 0.0], atol=1e-6) and abs(free[2, 3] + 0.05) < 1e-6)

    rods = (np.array([[0.0, 0.0, 1.0]]), np.array([[0.0, 0.0, 0.6]]), np.full((1, 8, 12), 0.08), np.array([[1.0, 0.0, 0.0]]), np.array([[0.0, 1.0, 0.0]]))
    local = swing["local_in"](np.array([[0.05, 0.02, 0.9]]), rods)[0, 0]
    check("a point is in a rod's own frame where it is in the world's: across by its x, along from its head, across by its z", np.allclose(local, [0.05, 0.1, 0.02]), str(local))


def test_cards():
    names = ["hips", "spine", "chest", "neck", "head", "thigh_l", "thigh_r"]
    parents = {"spine": "hips", "chest": "spine", "neck": "chest", "head": "neck", "thigh_l": "hips", "thigh_r": "hips"}
    def chain(slug, hang, count, long):
        for c in range(1, count + 1):
            for b in range(1, long + 1):
                name = "cloth_%s_%d_%d" % (slug, c, b)
                names.append(name)
                parents[name] = "cloth_%s_%d_%d" % (slug, c, b - 1) if b > 1 else hang
    chain("long_skirt", "hips", 8, 4)
    chain("travel_cape", "chest", 3, 4)
    chain("hood", "head", 4, 2)
    fold = lambda n: n if n in ("hips", "spine", "chest", "neck", "head") else "hips"  # noqa: E731
    note = {"garments": [{"gear": "long skirt", "slug": "long_skirt", "kind": "skirt", "parent": "hips", "chains": 8, "card": "piece"},
                         {"gear": "travel cape", "slug": "travel_cape", "kind": "cape", "parent": "chest", "chains": 3, "card": "piece"},
                         {"gear": "hood", "slug": "hood", "kind": "hood", "parent": "head", "chains": 4, "card": "rides"},
                         {"gear": "linen shirt", "slug": "linen_shirt", "kind": "shirt", "parent": "chest", "chains": 0, "card": "held", "hold": 0.5},
                         {"gear": "stiff collar", "slug": "stiff_collar", "kind": "collar", "parent": "neck", "chains": 0, "card": "held", "hold": 0.8}],
            "chains": []}
    garments = impostor.garments_of(names, parents.get, fold, note)
    by = {g["slug"]: g for g in garments}
    check("the cards read every garment off one description: its kind, where it hangs, its chains from the bones' names, and how cards show it",
          set(by) == {"long_skirt", "travel_cape", "hood", "linen_shirt", "stiff_collar"} and len(by["long_skirt"]["chains"]) == 8 and by["long_skirt"]["chains"][0] == ["cloth_long_skirt_1_%d" % b for b in (1, 2, 3, 4)]
          and by["travel_cape"]["parent"] == "chest" and by["hood"]["card"] == "rides" and by["stiff_collar"]["card"] == "held", str(sorted(by)))
    dress = impostor.chains_of(names, parents.get, fold, note)
    check("a garment the description calls a piece is the dress, wherever it hangs from: the skirt from the hips and the cape from the chest, about the hips",
          dress and dress["root"] == "hips" and dress["garments"] == ["long_skirt", "travel_cape"] and len(dress["chains"]) == 11 and dress["kinds"] == ["skirt", "cape"] and not any("hood" in b for b in dress["bones"]))
    check("... a cape alone is a dress too, about the chest: no rule was written for it", impostor.chains_of([n for n in names if "skirt" not in n], parents.get, fold, note)["root"] == "chest")
    old = impostor.chains_of(names, parents.get, fold)
    check("a file with no description reads as it always did: chains over the legs are the dress, the rest ride", old["garments"] == ["long_skirt"] and len(old["chains"]) == 8
          and {g["slug"]: g["card"] for g in impostor.garments_of(names, parents.get, fold)} == {"long_skirt": "piece", "travel_cape": "rides", "hood": "rides"})
    check("... and one with no chains at all has no dress", impostor.chains_of(["hips", "spine"], parents.get, fold, note) is None and impostor.chains_of(["hips"], parents.get, fold) is None)
    check("the neck's piece holds each garment back as it is described: a loose shirt by half, a stiff collar by its own share",
          impostor.hold_of("linen shirt", garments) == 0.5 and impostor.hold_of("gear: stiff collar".split(": ")[1], garments) == 0.8)
    check("... a hood, which rides the head, not at all: it goes with the head", impostor.hold_of("hood", garments) == 0.0)
    check("... and clothing nothing is said of by the default (a tight shirt's collar: cloth is not skin)", impostor.hold_of("wool singlet", garments) == impostor.CLOTH_HOLD and impostor.hold_of("wool singlet", garments, 0.3) == 0.3
          and impostor.hold_of("long skirt", garments) == impostor.CLOTH_HOLD)


def test_survey():
    now = fabric_survey.fabric_now()
    chains = {("ruffled_skirt", "hips"): 8}
    check("swing.py's own number for the way cloth is moved now is read from it", now >= 2)
    check("a clip with chains, moved by this fabric step, is current", fabric_survey.judge(chains, {"swung": {"fabric": now, "simulated": True}}, now) == "current")
    check("... one moved by an older step, or by none, is stale", fabric_survey.judge(chains, {"swung": {"fabric": now - 1}}, now).startswith("stale") and fabric_survey.judge(chains, {"chains": []}, now).startswith("stale")
          and fabric_survey.judge(chains, None, now).startswith("stale"))
    check("... and one with no chains has no loose cloth", fabric_survey.judge({}, None, now) == "no loose cloth")
    check("a stale clip says how it is baked again: its walk, its run, a screen-test motion, a take",
          "just tidy" in fabric_survey.again("midpoly-walk.glb", "runs/x") and "walk" in fabric_survey.again("midpoly-walk.glb", "runs/x") and "screen-play" in fabric_survey.again("lowpoly-screen-kick.glb", "runs/x")
          and "kick" in fabric_survey.again("lowpoly-screen-kick.glb", "runs/x") and "just cast groove" in fabric_survey.again("midpoly-groove.glb", "shots/groove"))
    doc = {"nodes": [{"name": "rig", "children": [1], "extras": {"forge_cloth": json.dumps({"chains": [], "garments": [], "swung": {"fabric": now, "simulated": True}})}}, {"name": "hips", "children": [2, 3]},
                     {"name": "cloth_apron_1_1", "children": [4]}, {"name": "cloth_apron_2_1"}, {"name": "cloth_apron_1_2"}], "animations": [{"name": "walk"}]}
    got = fabric_survey.cloth_of(doc)
    check("a file's chains are counted from its bones, and its skeleton's note read", got[0] == {("apron", "hips"): 2} and got[1]["swung"]["fabric"] == now and got[2] == ["walk"], str(got[0]))


def test_baked(runs):
    now = fabric_survey.fabric_now()
    found = fabric_survey.survey(runs, os.path.join(os.path.dirname(runs), "shots"))
    seen = 0
    for run, mine in sorted(found["characters"].items()):
        current = sorted(name for name, state in mine["clips"].items() if state.startswith("current"))
        if not current:
            continue
        bad, loops = [], 0
        for name in current:
            try:
                with open(os.path.join(runs, run, "profiles", name[:-4] + ".json")) as f:
                    record = json.load(f)
            except (OSError, ValueError):
                continue
            swing, check_ = record.get("swing") or {}, (record.get("swing") or {}).get("check") or {}
            if not swing:
                continue
            seen += 1
            loops += bool(swing.get("loops"))
            wears = (record.get("cloth") or {}).get("garments") or []
            if not (swing.get("simulated") and check_.get("limit_violations") == 0 and (check_.get("hem_below_floor_cm") or 0.0) <= 0.5 and (not swing.get("loops") or check_.get("loop_seam", 1.0) < 1e-5)
                    and wears and all(g.get("kind") and g.get("card") for g in wears)):
                bad.append((name, swing.get("simulated"), check_.get("limit_violations"), check_.get("hem_below_floor_cm"), check_.get("loop_seam")))
        check("%s: %d clips moved by fabric step %d (%d of them loops): the cloth simulated, off the floor, every turn inside its limit, each loop closed with no seam, and each garment written with its kind" % (
            run, len(current), now, loops), not bad, str(bad[:4]))
    if not seen:
        print("    (no clips baked by this fabric step under %s: nothing to check)" % runs)


def main():
    args = sys.argv[1:]
    runs = os.path.abspath(args[args.index("--runs") + 1]) if "--runs" in args else os.path.join(REPO, "runs")
    for name, case in (("kinds", test_kinds), ("swing", test_swing), ("cards", test_cards), ("survey", test_survey)):
        print("  " + name)
        case()
    print("  baked")
    test_baked(runs)
    print("%d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
