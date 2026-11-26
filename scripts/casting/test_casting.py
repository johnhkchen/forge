"""Tries casting with no Blender, no browser and no model: the files, the board, the costs, the notes, and the
gallery's casting API on a copy of casting/.

    python3 scripts/casting/test_casting.py

What it shows:
  files        the robot's role and the reel read; every look is a whole character brief; the reel's scenes are
               the ones sides.py plays, and the sides profile is one tidy_profile can make
  board        the stage a role has reached comes from what its candidates have, from breakdown to cast
  costs        a paid step's price comes from the runs' own logs; free steps say free; a revised take costs only
               when a note is about the look
  notes        a note is checked (empty, too long, about what, which take); notes number up; a take answers them
  choices      a stand-in cannot be cast; a headshot must be drawn before it is shortlisted; ids cannot climb out
  reel         each scene finds its clip and its stretch, and says what makes it when it is missing
  chemistry    the crew's take with one dancer swapped plays from the crew's own files and the candidate's
  scores       the judges' rows sum up into the few numbers the page shows
  api          GET /api/casting, a note through POST, a plan that writes nothing, a stranger's page refused
  wider        a look's several pictures, the screen test's best few, the mesh screen's price, a take that starts from its mesh
"""

import http.client
import json
import os
import shutil
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import casting  # noqa: E402

RUN = "2026-01-02T03-04-05-tin-toy-robot"
CAST = ["2026-11-20T14-02-41-young-lincoln-frontier-wrestler", "2026-11-20T14-02-45-roosevelt-wrestler-1890s", "2026-11-20T13-52-46-stocky-pirate-deckhand"]


def check(what, ok, said=""):
    print("    %s  %s%s" % ("ok    " if ok else "FAILED", what, " (%s)" % said if said else ""))
    if not ok:
        raise AssertionError(what)


def write(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(value if isinstance(value, str) else json.dumps(value))


def world():
    """A copy of casting/ beside a small runs/ and shots/ of its own: a robot run with its sides, and the cast."""
    top = tempfile.mkdtemp(prefix="casting-test-")
    shutil.copytree(os.path.join(REPO, "casting"), os.path.join(top, "casting"), ignore=shutil.ignore_patterns("full", ".cast"))
    runs, shots = os.path.join(top, "runs"), os.path.join(top, "shots")
    for i, run in enumerate([RUN] + CAST):
        write(os.path.join(runs, run, "brief.json"), {"name": run[20:].replace("-", " ").title(), "character": True, "size_m": 1.45 + 0.1 * i})
        write(os.path.join(runs, run, "image.png"), "png")
        write(os.path.join(runs, run, "mesh.json"), {"wall_seconds": 100 + 20 * i})
        for k, step in enumerate(casting.FINISH_STEPS):
            write(os.path.join(runs, run, "transcripts", step + ".jsonl"), '{"type": "assistant"}\n{"type": "result", "total_cost_usd": %.2f}\n' % (0.5 + 0.25 * i + 0.1 * k))
    profiles = os.path.join(runs, RUN, "profiles")
    for clip in ("walk", "sides"):
        write(os.path.join(profiles, "lowpoly-%s.glb" % clip), "glb")
    write(os.path.join(profiles, "lowpoly-sides.json"), {"sides": {"scenes": [{"scene": "stand easy", "from": 0, "to": 192}, {"scene": "wave", "from": 192, "to": 285},
                                                                               {"scene": "head turn", "from": 285, "to": 402}, {"scene": "arm overhead", "from": 402, "to": 477},
                                                                               {"scene": "deep squat", "from": 477, "to": 585}]}})
    crew = os.path.join(shots, "crew-candy-shop")
    write(os.path.join(crew, "take.json"), {"title": "The candy-shop routine, three across", "set": "studio"})
    roles = {}
    for role, run in zip(("frontman", "left", "right"), CAST):
        write(os.path.join(crew, role, "lowpoly-crew.glb"), "glb")
        for name in ("motion.json", "plan.json", "shotlist.json"):
            write(os.path.join(crew, role, name), {})
        roles[role] = {"character": "/somewhere/runs/%s/lowpoly.glb" % run, "glb": "%s/lowpoly-crew.glb" % role, "true_size": {"height_m": 1.8}}
    write(os.path.join(crew, "cast-crew.json"), {"set": "studio", "clip": "crew", "seconds": 60.2, "roles": roles})
    return top, casting.Casting(os.path.join(top, "casting"), runs, shots)


def with_candidate(cast, name="tin-toy", **more):
    c = dict({"name": "Tin toy", "stand_in": False, "look": "tin-toy", "status": "shortlisted",
              "takes": [{"n": 1, "run": RUN, "made": "2026-01-02", "how": "From the headshot.", "answers": []}], "notes": []}, **more)
    casting.write_json(cast.candidate_path("robot", name), c)
    return c


def test_files():
    """the robot's role and the reel read, and agree with sides.py and the tidy-mesh profiles"""
    cast = casting.Casting()
    role = cast.role("robot")
    b = role["breakdown"]
    check("the breakdown has its essence, look, silhouette, height and a palette of hex colours",
          all(b.get(k) for k in ("essence", "look", "silhouette", "height_m")) and all(p["hex"].startswith("#") and len(p["hex"]) == 7 for p in b["palette"]))
    check("it says what makes it read as cards, in bold ink and in Pixels, both", all(b.get(k) for k in ("reads_as_cards", "reads_in_bold_ink", "reads_in_pixels_both")))
    check("there are canon options to choose from, and none is chosen", len(role["canon_options"]) >= 3 and role.get("canon_choice") is None)
    check("every look is a whole character brief, drawn in a T-pose", all(l["brief"]["character"] and "T-pose" in l["brief"]["subject"] and l["brief"]["size_m"] > 1 for l in role["looks"]),
          ", ".join(l["id"] for l in role["looks"]))
    check("every look's gear is listed as the pipeline lists it", all(g["kind"] in ("worn", "attached", "held") for l in role["looks"] for g in l["brief"].get("gear") or []))
    check("the line-up and the swapped dancer are cast members", all(os.path.basename(r) for r in role["chemistry"]["line_up"]) and role["chemistry"]["swap"] in ("frontman", "left", "right"))
    with open(os.path.join(REPO, ".claude", "skills", "tidy-mesh", "scripts", "sides.py")) as f:
        sides = f.read()
    scenes = [s["scene"] for s in cast.reel()["sides"] if s.get("scene")]
    check("each scene the reel cuts out of the sides is one sides.py plays", all('("%s",' % s in sides for s in scenes), ", ".join(scenes))
    with open(os.path.join(REPO, ".claude", "skills", "tidy-mesh", "profiles.json")) as f:
        profile = json.load(f)["sides"]
    check("the sides profile is made by sides.py, for the low-poly, mid-poly and painted versions", profile["source"] == "sides.py" and "lowpoly" in profile["of"])
    check("every scene of the reel names a clip the reel says how to make", all(s["clip"] in cast.reel()["clips"] for s in cast.reel()["sides"]))
    check("the stand-ins point at runs and are marked as standing in", all(c.get("stand_in") for c in cast.candidates("robot").values() if not c.get("look")))


def test_board():
    """the furthest stage reached, worked out from the files"""
    top, cast = world()
    for gone in ("candidates", "headshots", "screen"):
        shutil.rmtree(os.path.join(cast.root, "robot", gone), ignore_errors=True)
    for gone in ("screen.json", "mesh-screen.json"):
        if os.path.exists(os.path.join(cast.root, "robot", gone)):
            os.remove(os.path.join(cast.root, "robot", gone))
    os.remove(os.path.join(cast.root, "robot", "baseline.json")) if os.path.exists(os.path.join(cast.root, "robot", "baseline.json")) else None
    check("a breakdown and nothing else is at the breakdown", cast.board("robot")["now"] == "breakdown")
    write(os.path.join(cast.root, "robot", "headshots", "tin-toy.png"), "png")
    check("a drawn headshot is at headshots", cast.board("robot")["now"] == "headshots" and cast.board("robot")["pictured"] == 1)
    casting.write_json(os.path.join(cast.root, "robot", "screen.json"), {"shots": [{"id": "tin-toy", "look": "tin-toy", "scores": {"total": 0.9}, "flags": []}]})
    check("a screened headshot is at the screen test", cast.board("robot")["now"] == "screen" and cast.board("robot")["screened"] == 1)
    cast.shortlist("robot", "tin-toy")
    check("shortlisting it makes a candidate with no take", cast.board("robot")["now"] == "shortlist" and cast.candidate("robot", "tin-toy")["takes"] == [])
    cast.add_take("robot", "tin-toy", os.path.join(cast.runs, RUN))
    check("a take is a tape", cast.board("robot")["now"] == "tapes")
    cast.add_note("robot", "tin-toy", "Try it bigger.", "look")
    check("a note is a callback", cast.board("robot")["now"] == "callbacks")
    cast.set_status("robot", "tin-toy", "cast")
    check("casting it is the last stage", cast.board("robot")["now"] == "cast")
    shutil.rmtree(top)


def test_costs():
    """prices from the runs' own logs; free steps free; a revised take paid only for a note on the look"""
    top, cast = world()
    c = cast.costs()
    # the four runs' three steps: 0.5+0.6+0.7 = 1.8, then 2.55, 3.3, 4.05
    check("Claude in Blender is the lowest, middle and highest of the runs' own logs", (c["finish"]["low"], c["finish"]["high"], c["finish"]["characters"]) == (1.8, 4.05, 4), str(c["finish"]))
    steps = {s["id"]: s for s in cast.steps("robot")}
    check("tape and judge are free; headshots, a take and a revision are paid", not steps["tape"]["paid"] and not steps["judge"]["paid"] and all(steps[k]["paid"] for k in ("headshots", "take", "revise")))
    check("a take costs at least what Claude in Blender costs", steps["take"]["low"] >= c["finish"]["low"] and steps["take"]["high"] >= c["finish"]["high"])
    with_candidate(cast)
    cast.add_note("robot", "tin-toy", "The knees blot in the squat.", "cards")
    plan = cast.plan("revise", "robot", "tin-toy")
    check("a revision answering only a note on the cards is free", plan["paid"] is False and plan["cost"].startswith("Free"), plan["cost"])
    cast.add_note("robot", "tin-toy", "Make the head smaller.", "look")
    plan = cast.plan("revise", "robot", "tin-toy")
    check("one on the look makes it paid, and the plan is a dry run", plan["paid"] is True and plan["dry_run"] and "go" in plan["command"])
    try:
        cast.plan("make-it-so", "robot")
        check("an unknown step is refused", False)
    except ValueError:
        check("an unknown step is refused", True)
    shutil.rmtree(top)


def refused(what, fn):
    try:
        fn()
    except ValueError as e:
        check(what, True, str(e))
        return
    check(what, False)


def test_notes():
    """a note is checked and numbered, and a take answers it"""
    top, cast = world()
    with_candidate(cast)
    refused("an empty note is refused", lambda: cast.add_note("robot", "tin-toy", "   ", "look"))
    refused("a note longer than a thousand characters is refused", lambda: cast.add_note("robot", "tin-toy", "x" * 1001, "look"))
    refused("a note about something else is refused", lambda: cast.add_note("robot", "tin-toy", "Louder.", "sound"))
    refused("a note on a take it has not got is refused", lambda: cast.add_note("robot", "tin-toy", "Louder.", "look", take=7))
    a = cast.add_note("robot", "tin-toy", "Try it bigger.", "look")
    b = cast.add_note("robot", "tin-toy", "The knees blot.", "cards")
    check("notes number up and go on the newest take", (a["id"], b["id"], a["take"]) == (1, 2, 1))
    n = cast.retake("robot", "tin-toy")
    c = cast.candidate("robot", "tin-toy")
    check("a free retake answers the note on the cards and leaves the one on the look open",
          n == 2 and c["notes"][1]["answered_by"] == 2 and c["notes"][0]["answered_by"] is None and cast.look_notes("robot", "tin-toy")[0]["id"] == 1)
    refused("a retake with no open note on moves or cards is refused", lambda: cast.retake("robot", "tin-toy"))
    n = cast.add_take("robot", "tin-toy", os.path.join(cast.runs, RUN), [1])
    check("a paid take answers the note on the look", n == 3 and cast.candidate("robot", "tin-toy")["notes"][0]["answered_by"] == 3 and not cast.look_notes("robot", "tin-toy"))
    refused("a take from a folder that is not a run is refused", lambda: cast.add_take("robot", "tin-toy", "/tmp/nothing-here"))
    shutil.rmtree(top)


def test_choices():
    """stand-ins, headshots and names"""
    top, cast = world()
    with_candidate(cast, "stand-in", stand_in=True, look=None)
    refused("a stand-in cannot be cast in the part", lambda: cast.set_status("robot", "stand-in", "cast"))
    refused("a status that is not one is refused", lambda: cast.set_status("robot", "stand-in", "famous"))
    cast.set_status("robot", "stand-in", "let go")
    check("letting one go keeps it, marked", cast.candidate("robot", "stand-in")["status"] == "let go")
    refused("a headshot not drawn yet cannot be shortlisted", lambda: cast.shortlist("robot", "clerk.9"))
    refused("a look that is not in the role cannot be shortlisted", lambda: cast.shortlist("robot", "dragon"))
    refused("a name that climbs out of casting/ is refused", lambda: cast.candidate("robot", "../../etc"))
    refused("a role that climbs out is refused", lambda: cast.role("../runs"))
    look = cast.add_look("robot", {"name": "Tin Toy Robot", "subject": "A robot in a T-pose.", "character": True})
    check("a look Opus wrote gets an id of its own beside one already taken", look == "tin-toy-robot" and cast.add_look("robot", {"name": "Tin Toy Robot", "subject": "Again."}) == "tin-toy-robot-2")
    shutil.rmtree(top)


def test_reel():
    """each scene's clip and stretch, or what makes it"""
    top, cast = world()
    with_candidate(cast)
    reel = {s["id"]: s for s in cast.reel_for("robot", "tin-toy", cast.candidate("robot", "tin-toy")["takes"][0])}
    check("the wave is the sides clip from frame 192 to 285", reel["wave"]["ready"] and reel["wave"]["glb"].endswith("profiles/lowpoly-sides.glb") and
          (reel["wave"]["from_s"], reel["wave"]["to_s"]) == (192 / 30, 285 / 30))
    check("the walk is the whole walk", reel["walk"]["ready"] and reel["walk"]["from_s"] is None)
    check("the run is missing and says how it is made", not reel["run"]["ready"] and "runs" in reel["run"]["made_by"])
    check("the dance is the swapped dancer's clip in the take's own folder, a stretch of it",
          reel["dance"]["glb"] == "shots/casting/robot/tin-toy-1/right/lowpoly-crew.glb" and not reel["dance"]["ready"] and reel["dance"]["from_s"] == 23.0)
    shutil.rmtree(top)


def test_chemistry():
    """the crew's take with the candidate in one dancer's place"""
    top, cast = world()
    with_candidate(cast)
    take = cast.candidate("robot", "tin-toy")["takes"][0]
    folder = cast.take_dir("robot", "tin-toy", 1)
    write(os.path.join(folder, "right", "lowpoly-crew.glb"), "glb")
    write(os.path.join(folder, "right", "lowpoly-crew.json"), {"size_against_soma": 1.1, "true_size": {"height_m": 1.45}})
    casting.write_chemistry(cast, "robot", "tin-toy", take, os.path.join(cast.shots, "crew-candy-shop"), "right", "lowpoly")
    record = casting.read_json(os.path.join(folder, "cast-crew.json"))
    found = {r: os.path.normpath(os.path.join(folder, p["glb"])) for r, p in record["roles"].items()}
    check("the two who stay play from the crew's own files", found["frontman"] == os.path.join(cast.shots, "crew-candy-shop", "frontman", "lowpoly-crew.glb") and os.path.isfile(found["left"]))
    check("the swapped dancer is the candidate, at its true size", record["roles"]["right"]["character"].split("/runs/")[1].startswith(RUN) and record["roles"]["right"]["true_size"]["height_m"] == 1.45)
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import gallery
    takes = gallery.takes_in(folder, cast.take_id("robot", "tin-toy", 1))
    check("the gallery reads it as a take with all three dancers", len(takes) == 1 and len(takes[0]["roles"]) == 3 and takes[0]["id"] == "casting/robot/tin-toy-1",
          takes[0]["title"] if takes else "none")
    check("its runs are the cast's and the candidate's", sorted(r["run"] for r in takes[0]["roles"]) == sorted(CAST[:2] + [RUN]))
    shutil.rmtree(top)


def test_scores():
    """the judges' rows summed up"""
    seams = {"rows": [{"role": "right", "look": "joe", "body": 1000, "dark": 5, "open": 10, "hole": 2},
                      {"role": "right", "look": "joe", "body": 1000, "dark": 15, "open": 0, "hole": 0},
                      {"role": "left", "look": "joe", "body": 1000, "dark": 999, "open": 999, "hole": 999}]}
    s = casting.sum_seams(seams, "right")
    check("lines and see-through are a thousandth of the body, over the role's rows only", s["joe"] == {"dark": 10.0, "open": 5.0, "holes": 1.0, "frames": 2}, str(s))
    joints = {"rows": [{"role": "right", "look": "joe", "kind": "knee", "likeness": 0.4, "blots": 0.1},
                       {"role": "right", "look": "joe", "kind": "elbow", "likeness": 0.6, "blots": 0.3},
                       {"role": "right", "look": "joe", "kind": "shaft", "likeness": 0.9, "blots": 0.0}]}
    j = casting.sum_joints(joints, "right")
    check("joints are averaged by kind and over all, leaving the shafts out", j["joe"]["knee"]["likeness"] == 0.4 and j["joe"]["all"] == {"likeness": 0.5, "blots": 0.2, "joints": 2}, str(j["joe"]["all"]))
    f = casting.sum_faces({"table": {"crew|joe|right": {"kept": 0.8, "likeness": 0.6}, "crew|joe|all": {"kept": 0.1}}}, "right")
    check("faces are the role's own cells", f == {"joe": {"crew": {"kept": 0.8, "likeness": 0.6}}})
    log = os.path.join(tempfile.mkdtemp(), "judge.log")
    write(log, "Traceback\nKeyError: 'cloth_linen_tunic_1_1'\n")
    check("a judge that stopped for want of a cloth bone is read from its log", casting.missing_bone(log) == "cloth_linen_tunic_1_1")
    check("a face recipe is found by the run's name without its date", casting.face_recipe("/x/runs/" + CAST[2]) and not casting.face_recipe("/x/runs/" + RUN))


def test_api():
    """the gallery's casting API on a copy of the files"""
    top, cast = world()
    with_candidate(cast)
    import gallery
    gallery.CASTING, gallery.RUNS, gallery.SHOTS = cast.root, cast.runs, cast.shots
    server = gallery.ThreadingHTTPServer(("127.0.0.1", 0), gallery.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]

    def ask(method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        data = json.dumps(body).encode() if body is not None else None
        conn.request(method, path, body=data, headers=dict({"Content-Type": "application/json"} if data else {}, **(headers or {})))
        answer = conn.getresponse()
        text = answer.read()
        return answer.status, json.loads(text) if text[:1] in (b"{", b"[") else text

    def files():
        return sorted(os.path.join(d, f) for d, _, fs in os.walk(top) for f in fs)

    try:
        status, roles = ask("GET", "/api/casting")
        robot = next(r for r in roles if r["id"] == "robot")
        check("GET /api/casting has the robot, its board, its steps and the candidate's reel", status == 200 and robot["board"]["now"] and robot["steps"] and
              next(c for c in robot["candidates"] if c["id"] == "tin-toy")["takes"][0]["reel"])
        status, _ = ask("GET", "/casting/robot/role.json")
        check("casting/ is served", status == 200)
        before = files()
        status, said = ask("POST", "/api/casting/robot/plan", {"step": "take", "candidate": "tin-toy"})
        check("a plan says what it costs and writes nothing", status == 200 and said["saved"] is False and said["result"]["dry_run"] and files() == before)
        status, said = ask("POST", "/api/casting/robot/tin-toy/note", {"text": "Warmer eyes.", "about": "look"})
        after = set(files()) ^ set(before)
        check("a note is saved, and the candidate's file is the only one written", status == 200 and said["result"]["id"] == 1 and after <= {cast.candidate_path("robot", "tin-toy")})
        status, said = ask("POST", "/api/casting/robot/tin-toy/note", {"text": "", "about": "look"})
        check("an empty note is refused with a reason", status == 400 and "empty" in said["error"])
        status, said = ask("POST", "/api/casting/robot/tin-toy/note", {"text": "Hi."}, {"Origin": "http://elsewhere.example"})
        check("a page from somewhere else is refused", status == 403)
        status, said = ask("POST", "/api/casting/robot/nobody/status", {"status": "cast"})
        check("a candidate that is not there is not found", status == 404)
        status, said = ask("POST", "/api/casting/robot/tin-toy/spend", {"usd": 100})
        check("nothing else takes a POST", status == 404)
    finally:
        server.shutdown()
        shutil.rmtree(top)


def test_wider():
    """several pictures of a look, the screen test's best few, the mesh screen's plan, and a take that starts from its mesh"""
    top, cast = world()
    for gone in ("candidates", "headshots"):
        shutil.rmtree(os.path.join(cast.root, "robot", gone), ignore_errors=True)
    for name in ("tin-toy.png", "tin-toy.2.png", "tin-toy.3.png", "clerk.png", "clerk.2.png", "clerk.x.png", "notes.txt"):
        write(os.path.join(cast.root, "robot", "headshots", name), "png")
    check("a look's pictures are its first, then .2, .3; a name that is not one is left out",
          [s for s, _, _ in cast.pictures("robot", "tin-toy")] == ["tin-toy", "tin-toy.2", "tin-toy.3"] and [s for s, _, _ in cast.pictures("robot", "clerk")] == ["clerk", "clerk.2"])
    looks = len(cast.role("robot")["looks"])
    check("three of each look draws only what is missing, and new looks add three each",
          cast.to_draw("robot", 0, 3) == looks * 3 - 5 and cast.to_draw("robot", 4, 3) == looks * 3 - 5 + 12 and cast.to_draw("robot", 0, 1) == looks - 2)
    plan = cast.plan("headshots", "robot", more=4, variations=3)
    check("the headshots' plan names the pictures and the Opus ask, and the command carries both", plan["pictures"] == looks * 3 + 7 and "Opus" in plan["cost"] and plan["command"].endswith("go 4 3"), plan["command"])
    rows = [{"id": "clerk.2", "look": "clerk", "scores": {"total": 0.95}, "flags": []}, {"id": "clerk", "look": "clerk", "scores": {"total": 0.94}, "flags": []},
            {"id": "tin-toy.3", "look": "tin-toy", "scores": {"total": 0.93}, "flags": ["something thin rises 12 cm above its head (an antenna?)"]},
            {"id": "tin-toy.2", "look": "tin-toy", "scores": {"total": 0.80}, "flags": []}]
    casting.write_json(os.path.join(cast.root, "robot", "screen.json"), {"shots": rows})
    check("the best few are one a look first, none flagged, then the rest by score", cast.top_shots("robot", 3) == ["clerk.2", "tin-toy.2", "clerk"], ",".join(cast.top_shots("robot", 3)))
    mesh = cast.plan("mesh", "robot", shots=["clerk.2", "tin-toy.2"])
    check("the mesh screen is paid, its price is the meshes', and it starts nothing", mesh["paid"] and mesh["dry_run"] and mesh["high"] == round(2 * cast.costs()["mesh"]["usd"], 2)
          and mesh["command"] == "just casting-mesh-screen robot clerk.2,tin-toy.2 go")
    refused("a mesh screen of a headshot not drawn is refused", lambda: cast.plan("mesh", "robot", shots=["clerk.7"]))
    c = cast.shortlist("robot", "clerk.2")
    check("shortlisting picture 2 makes candidate clerk-2, with its own picture", c["look"] == "clerk" and c["variation"] == 2 and os.path.isfile(cast.candidate_path("robot", "clerk-2"))
          and next(p for p in cast.summary("robot")["candidates"] if p["id"] == "clerk-2")["picture"] == "casting/robot/headshots/clerk.2.png")
    refused("a shot that is not one is refused", lambda: cast.shortlist("robot", "clerk.two"))
    write(os.path.join(cast.runs, RUN, "mesh.glb"), "glb")
    cast.add_mesh("robot", "clerk.2", os.path.join(cast.runs, RUN))
    check("a mesh the screen built is kept, and the candidate's take starts from it", cast.meshes("robot")["clerk.2"]["run"] == RUN and cast.candidate("robot", "clerk-2")["screen_run"] == RUN)
    full, less = cast.plan("take", "robot"), cast.plan("take", "robot", "clerk-2")
    check("so its first take costs a mesh less", round(full["high"] - less["high"], 2) == cast.costs()["mesh"]["usd"], less["cost"])
    check("a mesh built already is said so, not built again", "clerk.2" in (cast.plan("mesh", "robot", shots=["clerk.2"]).get("warning") or ""))
    summary = cast.summary("robot")
    row = next(r for r in summary["screen"]["shots"] if r["id"] == "clerk.2")
    check("the page gets the screen with each row's candidate and mesh", row["candidate"] == "clerk-2" and row["mesh"]["run"] == RUN and
          [p["shot"] for p in next(l for l in summary["looks"] if l["id"] == "clerk")["pictures"]] == ["clerk", "clerk.2"])
    idea = {"brief": {"name": "Stagehand Robot", "subject": "A robot in a T-pose.", "character": True}, "why": "For the crew.", "suits": "crew"}
    look = cast.add_look("robot", idea)
    kept = next(l for l in cast.role("robot")["looks"] if l["id"] == look)
    check("a look Opus wrote keeps its why and the way it could arrive", kept["why"] == "For the crew." and kept["suits"] == "crew" and kept["brief"]["name"] == "Stagehand Robot")
    shutil.rmtree(top)


def test_colourways():
    """a headshot drawn again in other colours: its name, its candidate, what is left to draw"""
    top, cast = world()
    role = cast.role("robot")
    ways = [w for l in role["looks"] for w in l.get("colourways") or []]
    check("every colourway names its headshot and has five swatches, the face plate dark and the eyes light",
          ways and all(w["headshot"].startswith(w["of"] if "." in w["of"] else w["of"] + ".1") and len(w["swatches"]) == 5 for w in ways)
          and all(int(w["swatches"][2]["hex"][1:3], 16) < 0x40 and int(w["swatches"][3]["hex"][1:3], 16) > 0xD0 for w in ways), "%d colourways" % len(ways))
    check("no colourway leads with the cast's navy, browns, greens or the dancer's red (hue and lightness of its lead colour)",
          all(not lead_clashes(w["swatches"][0]["hex"]) for w in ways), ", ".join("%s %s" % (w["id"], w["swatches"][0]["hex"]) for w in ways if lead_clashes(w["swatches"][0]["hex"])))
    check("at most one colourway a robot leans on the brand's palette", all(sum(1 for w in l.get("colourways") or [] if w.get("brand")) <= 1 for l in role["looks"]))
    check("a colourway's name splits into its look, picture and colourway, and makes its own candidate",
          cast.shot("clerk.2-lilac") == ("clerk", 2, "lilac") and casting.candidate_id("clerk", 2, "lilac") == "clerk-2-lilac" and casting.shot_name("clerk", 1, "lilac") == "clerk.1-lilac")
    for gone in ("headshots",):
        shutil.rmtree(os.path.join(cast.root, "robot", gone), ignore_errors=True)
    write(os.path.join(cast.root, "robot", "headshots", "clerk.2.jpg"), "jpg")
    write(os.path.join(cast.root, "robot", "headshots", "clerk.2-lilac.jpg"), "jpg")
    todo = cast.colourways_to_draw("robot")
    check("the colourways left to draw are those whose headshot is drawn and they are not",
          "clerk.2-tangerine" in todo and "clerk.2-lilac" not in todo and not any(t.startswith("builder") for t in todo), ",".join(todo))
    check("the plain pictures of a look leave its colourways out, and they are listed apart",
          [s for s, _, _ in cast.pictures("robot", "clerk")] == ["clerk.2"] and [s for s, _, _, _ in cast.pictures("robot", "clerk", colourways=True)] == ["clerk.2-lilac"])
    c = cast.shortlist("robot", "clerk.2-lilac")
    check("shortlisting a colourway makes its own candidate, with its picture, colourway and why",
          c["colourway"] == "lilac" and c["variation"] == 2 and "lilac" in c["name"] and
          next(p for p in cast.summary("robot")["candidates"] if p["id"] == "clerk-2-lilac")["picture"] == "casting/robot/headshots/clerk.2-lilac.jpg")
    refused("a colourway not written in the breakdown cannot be shortlisted", lambda: cast.shortlist("robot", "clerk.2-plaid"))
    plan = cast.plan("colourways", "robot")
    check("drawing the colourways is a paid step on the plan, Codex only", plan["paid"] and plan["pictures"] == len(todo) and "Opus" in plan["cost"] and plan["command"] == "just casting-colourways robot go")
    looks = {l["id"]: l for l in cast.summary("robot")["looks"]}
    check("the page gets each look's colourways with their pictures", any(w["picture"] for w in looks["clerk"]["colourways"]))
    shutil.rmtree(top)


def lead_clashes(hex_):
    """Whether a lead colour is the cast's: navy (dark blue), brown or linen (dark or pale low-saturation orange),
    green, or red. Hue in degrees, saturation and lightness 0..1."""
    import colorsys
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    hue *= 360
    navy = 200 <= hue <= 250 and light < 0.35
    brown = 15 <= hue <= 45 and (light < 0.4 or sat < 0.3) and not light > 0.9
    green = 75 <= hue <= 165 and sat > 0.2
    red = (hue < 12 or hue > 345) and sat > 0.45
    return navy or brown or green or red


TESTS = [test_files, test_board, test_costs, test_notes, test_choices, test_reel, test_chemistry, test_scores, test_api, test_wider, test_colourways]


def main():
    failed = 0
    for test in TESTS:
        print("%s: %s" % (test.__name__[5:], test.__doc__))
        try:
            test()
        except Exception as e:  # a failed check, or something a check reads that is missing
            failed += 1
            print("    FAILED: %s: %s" % (type(e).__name__, str(e)[:800]))
    print("%d casting case(s) failed" % failed if failed else "all %d casting cases passed" % len(TESTS))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
