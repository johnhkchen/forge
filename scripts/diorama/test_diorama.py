"""Tries the dioramas with no Blender and no model.

    python3 scripts/diorama/test_diorama.py

What it shows:
  plan    every diorama's plan is sound, and a plan that is not is told why: a mark that isn't there, a pose
          nobody wrote, two toons on one spot, a prop nobody holds, a backdrop the stage doesn't have, a
          camera framing someone who isn't in it
  built   what is kept in dioramas/<name>/ is the last build with nothing wrong: one .glb (Draco, WebP,
          inside the budget, every web mesh soundly bound to its borrowed skeleton) with every toon, prop, the set and the base in it, its pictures and its card
  shelf   the gallery's front page gets the newest diorama first, with its epoch, views and pictures

`scripts/test_tools.py` runs the same checks, and builds a diorama for real.
"""

import copy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import diorama  # noqa: E402


def check(label, ok, detail=""):
    print("    %s  %s%s" % ("ok  " if ok else "FAIL", label, ("  (%s)" % (str(detail)[:600],)) if detail and not ok else ""))
    if not ok:
        raise AssertionError(label)


def told(spec, change, words, runs=None):
    """A plan with one thing broken is refused, in words that say what."""
    broken = copy.deepcopy(spec)
    change(broken)
    problems, _ = diorama.check(broken, runs)
    check("told: %s" % words, any(words in line for line in problems), problems)


def test_plan(runs=None):
    names = diorama.names()
    check("there is at least one diorama", bool(names), names)
    for name in names:
        spec = diorama.load(name)
        problems, seen = diorama.check(spec, runs)
        check("%s: the plan is sound%s" % (name, " and every file it needs is in the runs" if runs else ""), not problems, problems)
        check("%s: it has a hero camera and a few other angles, and pictures to take" % name, len(spec["cameras"]) >= 3 and 3 <= len(spec["stills"]) <= 4, list(spec["cameras"]))
        check("%s: it belongs to a saved epoch" % name, bool(seen.get("epoch")), seen)
    spec = diorama.load(names[0])
    first, second = spec["toons"][0], spec["toons"][1]
    told(spec, lambda s: s["toons"][0].update(mark="nowhere"), "has no mark called \"nowhere\"")
    told(spec, lambda s: s["toons"][1].update(pose="moonwalk"), "has no pose \"moonwalk\"")
    told(spec, lambda s: s["toons"][1].update(at=diorama.spot_of(spec, diorama.standing.load(spec["set"]["name"]), first)[0], mark=None, on=None), "standing in each other")
    told(spec, lambda s: s["toons"][1].update(at=[99.0, 99.0], mark=None, on=None), "off the slice of the set")
    told(spec, lambda s: s["props"].update(spare={"built": "teacup"}), "is never held or stood anywhere")
    told(spec, lambda s: s["props"].update(spare={"built": "piano"}), "nothing builds a \"piano\"")
    told(spec, lambda s: s["set"].update(backdrop="the-moon"), "has no backdrop of \"the-moon\"")
    told(spec, lambda s: next(iter(s["cameras"].values())).update(frames=["nobody"]), "frames \"nobody\"")
    told(spec, lambda s: s["toons"][1].update(looks_at=second["toon"]), "looks at")
    told(spec, lambda s: s.update(epoch="epoch-99"), "has not been saved")
    told(spec, lambda s: s.update(stills=["somewhere"]), "stills names the cameras")
    if runs:
        told(spec, lambda s: s["toons"][0].update(run="nobody-at-all"), "in a run named for \"nobody-at-all\"", runs)


def built_checks(spec, record, folder, label):
    """What a finished build must be: used for the kept one, and by test_tools.py for one it has just made."""
    check("%s: the build found nothing wrong" % label, record.get("problems") == [], record.get("problems"))
    measured = record["measured"]
    crossing = {pair: how for pair, how in measured["touching"].items() if not str(how).startswith("at the hand")}
    check("%s: nobody is in anybody, or in a prop that isn't in their hand" % label, not crossing, crossing)
    check("%s: every pair of feet is on its floor (within 1.2 cm)" % label, len(measured["feet_off_floor_cm"]) == len(spec["toons"]) and max(measured["feet_off_floor_cm"].values()) <= 1.2,
          measured["feet_off_floor_cm"])
    held = sum(len(t.get("holds") or []) for t in spec["toons"])
    check("%s: every held prop is in its hand (within 2 cm)" % label, len(measured["hand_to_prop_cm"]) == held and all(v <= 2.0 for v in measured["hand_to_prop_cm"].values()), measured["hand_to_prop_cm"])
    check("%s: everything else stands on the floor or on what is under it (within 1.2 cm)" % label, all(v <= 1.2 for v in measured["prop_off_surface_cm"].values()), measured["prop_off_surface_cm"])
    peeking = {t["toon"] for t in spec["toons"] if t.get("peeks")}
    hidden = {who: share for who, share in measured["seen_from_front"].items() if share < (0.2 if who in peeking else 0.4)}
    check("%s: every face shows from the front" % label, not hidden, hidden)
    path = os.path.join(folder, "diorama.glb")
    check("%s: diorama.glb is there" % label, os.path.isfile(path))
    facts = diorama.glb_facts(path)
    check("%s: the .glb opens: %d meshes, %s triangles" % (label, facts["meshes"], format(facts["triangles"], ",")), facts["meshes"] > 0 and facts["triangles"] > 0, facts)
    check("%s: it is light enough for a phone: %.2f MB (at most %.1f), %s triangles (at most %s)" % (label, facts["bytes"] / 1e6, diorama.BUDGET["bytes"] / 1e6, format(facts["triangles"], ","),
                                                                                                 format(diorama.BUDGET["triangles"], ",")),
          facts["bytes"] <= diorama.BUDGET["bytes"] and facts["triangles"] <= diorama.BUDGET["triangles"], facts)
    check("%s: it is Draco-packed and its pictures are WebP" % label, facts["draco"] and facts["pictures"] == ["image/webp"], facts)
    wanted = ["toon: " + t["toon"] for t in spec["toons"]] + ["prop: " + p for p in spec.get("props") or {}]
    missing = [name for name in wanted if name not in facts["nodes"]]
    check("%s: every toon and prop is in it by name, with the set and the base" % label,
          not missing and any(n.startswith("set:") for n in facts["nodes"]) and any(n.startswith("plinth:") for n in facts["nodes"]), missing or facts["nodes"])
    for who, bind in (record.get("binds") or {}).items():
        wears = record["toons"][who]["version"]
        check("%s: %s's web mesh on its borrowed skeleton: worst edge %.2fx, %.3f%% over twice%s" % (label, who, bind["worst"], bind["over_twice_pct"], "" if bind["sound"] else " (not sound: it wears %s)" % wears),
              (bind["sound"] and wears == "web" and bind["worst"] <= 5.0 and bind["over_twice_pct"] <= 1.0) or (not bind["sound"] and wears != "web"), bind)
    asked = [t["toon"] for t in spec["toons"] if t.get("version") == "web"]
    check("%s: every toon asked for in its web version was bound and measured" % label, sorted(asked) == sorted(record.get("binds") or {}), asked)
    if "opens_again" in record:
        check("%s: Blender opened the file again and counted the same triangles" % label, record["opens_again"]["triangles"] == facts["triangles"], record["opens_again"])
    for name in spec["cameras"]:
        view = (record.get("cameras") or {}).get(name) or {}
        check("%s: the camera \"%s\" is kept as a view the gallery can fly to" % (label, name), len(view.get("at") or []) == 3 and len(view.get("aim") or []) == 3 and view.get("holds_m", 0) > 0, view)
    return facts


def test_built():
    for name in diorama.names():
        spec, record = diorama.load(name), diorama.built(name)
        check("%s: it has been built (just diorama %s)" % (name, name), record is not None)
        built_checks(spec, record, spec["dir"], name)
        stills = [s["camera"] for s in record.get("stills") or []]
        check("%s: a picture through each camera in `stills`, each with a small one" % name,
              stills == spec["stills"] and all(os.path.getsize(os.path.join(spec["dir"], s[k])) > 4000 for s in record["stills"] for k in ("picture", "small")), stills)
        check("%s: a card" % name, os.path.getsize(os.path.join(spec["dir"], "card.png")) > 4000)
        check("%s: the kept build is of the kept plan (same toons, same spots)" % name,
              {t["toon"]: [round(v, 3) for v in diorama.spot_of(spec, diorama.standing.load(spec["set"]["name"]), t)[0]] for t in spec["toons"]} == {who: card["at"] for who, card in record["toons"].items()},
              record["toons"])


def test_shelf():
    shelf = diorama.shelf()
    check("the front page's diorama is the one with the highest number", shelf and shelf[0]["number"] == max(c["number"] for c in shelf), [c["number"] for c in shelf])
    now = shelf[0]
    check("it comes with its title, a one-line caption and its epoch", now["title"] and now["caption"] and now["epoch"]["title"], now)
    check("it comes with its .glb, its views and its pictures", now["glb"] and len(now["views"]) >= 3 and len(now["stills"]) >= 3, now)
    files = diorama.front_page_files(now["name"])
    most = diorama.BUDGET["bytes"] + 300_000
    check("opening the front page fetches one model and the small pictures, under %.1f MB: %.2f MB in %d files" % (most / 1e6, files["first"]["bytes"] / 1e6, files["first"]["files"]),
          files["first"]["bytes"] < most and files["first"]["list"][0] == "diorama.glb", files["first"])


FAILED = []


def main():
    for case in (test_plan, test_built, test_shelf):
        print("%s: %s" % (case.__name__[5:], (case.__doc__ or "").strip()))
        try:
            case()
        except AssertionError as e:
            FAILED.append(str(e))
    print("diorama tests: %s" % ("all passed" if not FAILED else "%d failed: %s" % (len(FAILED), "; ".join(FAILED))))
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
