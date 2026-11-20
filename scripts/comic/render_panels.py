"""Draws every panel of a comic in one background Blender.

    Blender -b --factory-startup -P scripts/comic/render_panels.py -- comics/<name> [--runs runs] [--only 2,5] [--width 900]

Reads comics/<name>/comic.json. For each panel: the place is brought in (once), each character is brought in
(once per clip), frozen in its pose or at its clip moment, stood on its spot facing its way, given its drawn
face; a camera is fitted to the framing; toon.py draws it. Writes

    comics/<name>/panels/01.png ...   the pictures, with no background (the page puts the sky behind them)
    comics/<name>/panels.json         for the lettering: each picture's size, where every head and body is in it,
                                      the place's sky, and the seconds each took

A panel is cheap because nothing is made for it: a pose is a few turned bones, a clip moment is one frame read
off a clip that already exists, and the look is one shader. Blender only; never touches an open Blender.
"""

import json
import math
import os
import sys
import time

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit  # noqa: E402
import stage  # noqa: E402

LEAN_IN_DEG = 28.0  # "left" and "right" are turned this much toward the reader, so a profile still shows a face
LENS = {"wide": 35.0, "two-shot": 50.0, "single": 62.0, "close-up": 80.0}
ABOVE_DEG = {"wide": 9.0, "two-shot": 4.0, "single": 2.0, "close-up": 0.0}
MARGIN = {"wide": 1.3, "two-shot": 1.2, "single": 1.3, "close-up": 1.55}
HEADROOM = {"wide": 0.16, "two-shot": 0.24, "single": 0.26, "close-up": 0.22}  # of the picture's height, kept clear for balloons
UPPER_BODY = ["spine", "chest", "neck", "head", "upper_arm_l", "upper_arm_r", "forearm_l", "forearm_r", "hand_l", "hand_r"]
BUST = ["chest", "neck", "head"]
BLOCK_COLORS = {"roof": (0.30, 0.31, 0.40), "wall": (0.44, 0.42, 0.52), "ledge": (0.36, 0.36, 0.46)}
LINE_SHARE = 0.0052  # the ink line's width, as a share of the panel's width
THERE_VIEW_DEG = -38.0  # a clip moment kept where its shot has it is seen from this far round its front


def flat_material(name, color):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = tuple(pow(c, 2.2) / 1.5 for c in color) + (1.0,)
    return mat


def shadow_material():
    mat = bpy.data.materials.get("comic ground shadow")
    if mat:
        return mat
    mat = bpy.data.materials.new("comic ground shadow")
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    mix = tree.nodes.new("ShaderNodeMixShader")
    clear = tree.nodes.new("ShaderNodeBsdfTransparent")
    dark = tree.nodes.new("ShaderNodeEmission")
    dark.inputs["Color"].default_value = (0.02, 0.015, 0.04, 1.0)
    mix.inputs[0].default_value = 0.3
    tree.links.new(clear.outputs[0], mix.inputs[1])
    tree.links.new(dark.outputs[0], mix.inputs[2])
    tree.links.new(mix.outputs[0], out.inputs["Surface"])
    mat.surface_render_method = "BLENDED"
    return mat


def ground_shadow(scene, name):
    """A flat dark oval to sit under a character: what a cartoonist draws instead of a cast shadow."""
    points = [(math.cos(i * math.pi / 12), math.sin(i * math.pi / 12), 0.0) for i in range(24)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(points, [], [list(range(24))])
    mesh.materials.append(shadow_material())
    disc = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(disc)
    return disc


class Places:
    """The places a comic uses, each brought in once."""

    def __init__(self, scene, runs):
        self.scene, self.runs = scene, runs
        self.known = kit.places(runs)
        self.loaded = {}

    def get(self, name):
        if name in self.loaded:
            return self.loaded[name]
        record = dict(self.known[name])
        objects, floor = [], 0.0
        backdrop = record.get("backdrop") or {}
        center = record.get("center") or [0.0, 0.0]
        if isinstance(backdrop, list):  # a set: its own .glb files, as they are
            for path in backdrop:
                objects += [o for o in stage.bring_in(path) if o.type == "MESH"]
        elif backdrop.get("run"):
            path = os.path.join(kit.find_run(self.runs, backdrop["run"]), backdrop["file"])
            objects = [o for o in stage.bring_in(path) if o.type == "MESH"]
            middle = self.middle_of(objects)
            center = [middle[0] + center[0], middle[1] + center[1]]
            floor = self.height_at(objects, center)
        elif backdrop.get("shot"):
            folder = os.path.join(kit.data_root(self.runs), "shots", backdrop["shot"])
            plan = kit.read_json(os.path.join(folder, "plan.json"))
            kinds = {block["name"]: block.get("kind", "roof") for block in plan.get("set", [])}
            size = record.get("scale", 1.0)
            for o in stage.bring_in(os.path.join(folder, "motion.glb")):
                if o.name not in kinds:
                    bpy.data.objects.remove(o)
                    continue
                if o.parent is None:
                    o.location, o.scale = o.location * size, o.scale * size
                o.data.materials.clear()
                o.data.materials.append(flat_material("comic block: " + kinds[o.name], BLOCK_COLORS.get(kinds[o.name], BLOCK_COLORS["roof"])))
                objects.append(o)
        record.update(objects=objects, floor=floor, center=center)
        self.loaded[name] = record
        return record

    @staticmethod
    def middle_of(objects):
        """The middle of a backdrop as seen from above, going by its upper third (a ring's posts and ropes, not its steps)."""
        points = [o.matrix_world @ v.co for o in objects for v in o.data.vertices]
        low, high = min(p.z for p in points), max(p.z for p in points)
        upper = [p for p in points if p.z > low + (high - low) * 0.67] or points
        return [(min(p.x for p in upper) + max(p.x for p in upper)) / 2, (min(p.y for p in upper) + max(p.y for p in upper)) / 2]

    @staticmethod
    def height_at(objects, center):
        """The floor a character stands on near a spot: what a drop from above lands on, at nine points around it."""
        hits = []
        for dx in (-0.4, 0.0, 0.4):
            for dy in (-0.4, 0.0, 0.4):
                best = None
                for o in objects:
                    inverse = o.matrix_world.inverted()
                    start = inverse @ Vector((center[0] + dx, center[1] + dy, 1000.0))
                    down = (inverse.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()
                    hit, where, _normal, _face = o.ray_cast(start, down)
                    if hit:
                        z = (o.matrix_world @ where).z
                        best = z if best is None or z > best else best
                if best is not None:
                    hits.append(best)
        hits.sort()
        return hits[len(hits) // 2] if hits else 0.0

    def show_only(self, name):
        for key, record in self.loaded.items():
            for o in record["objects"]:
                o.hide_render = o.hide_viewport = key != name


class Cast:
    """The characters a comic uses, each brought in once per clip, with a ground shadow each."""

    def __init__(self, scene, runs):
        self.scene, self.runs = scene, runs
        self.entries = kit.load_cast()
        self.poses = stage.load_poses()
        self.loaded = {}
        self.moments = {}
        self.faces = {}

    def moments_of(self, who):
        if who not in self.moments:
            self.moments[who] = {m["name"]: m for m in kit.moments_of(self.runs, self.entries[who])}
        return self.moments[who]

    def character(self, who, clip):
        key = (who, clip)
        if key not in self.loaded:
            path = kit.clip_file(self.runs, self.entries[who], clip)
            if not path:
                raise ValueError("%s has no %s file under %s" % (who, clip, self.runs))
            character = stage.load_character(path)
            character["shadow"] = ground_shadow(self.scene, "shadow of %s (%s)" % (who, clip))
            self.loaded[key] = character
        return self.loaded[key]

    def hide_all(self):
        for character in self.loaded.values():
            stage.show(character, False)
            character["shadow"].hide_render = True

    def pose(self, who, ref):
        """The character for this panel, frozen as `ref` asks. Returns (character, what it is, the place a moment belongs to)."""
        moments = self.moments_of(who)
        if ref in self.poses:
            character = self.character(who, "walk")
            stage.strike(character, self.poses[ref])
            return character, {"pose": ref}, None
        if ref in moments:
            moment = moments[ref]
            character = self.character(who, moment["clip"])
            held = stage.freeze(character, moment["second"])
            return character, dict(held, moment=ref), kit.STAND_IN_OF_SHOT.get(moment["shot"])
        at = kit.CLIP_AT.match(ref or "")
        if not at:
            raise ValueError("%s has no pose \"%s\"" % (who, ref))
        character = self.character(who, at.group(1))
        return character, stage.freeze(character, float(at.group(2))), None

    def face(self, who, character, expression):
        """Put the drawn expression on, if this character has one; says what it used."""
        if who not in self.faces:
            path = os.path.join(kit.CAST_DIR, who, "face.json")
            self.faces[who] = kit.read_json(path)["planes"] if os.path.exists(path) else {}
        planes = self.faces[who]
        if not planes:
            return None
        name = expression if expression in planes else "neutral"
        stage.run_script("face_swap.py", {"rig": character["rig"].name, "image": os.path.join(kit.CAST_DIR, who, "faces", name + ".png"),
                                          "plane": planes[name]})
        return name


def toward_of(front_deg, above_deg):
    """The direction from the stage to a camera `front_deg` round it (0 = the camera is at -y) and `above_deg` up."""
    f, a = math.radians(front_deg), math.radians(above_deg)
    return Vector((math.sin(f) * math.cos(a), -math.cos(f) * math.cos(a), math.sin(a)))


def facing_angle(word, front_deg):
    """Where a character looks, as the reader sees it, turned into a heading in the scene (radians)."""
    turn = {"camera": 0.0, "away": 180.0, "right": 90.0 - LEAN_IN_DEG, "left": -(90.0 - LEAN_IN_DEG)}[word]
    return math.radians(front_deg + turn)


def frame_points(framing, characters):
    """What the camera must keep in frame."""
    subject = characters[:1] if framing in ("single", "close-up") else characters
    points = []
    for character in subject:
        head = stage.head_of(character)
        if framing == "wide":
            points += stage.shape_points(character)
        elif framing == "two-shot":
            points += stage.points_of(character, UPPER_BODY) + [head["top"]]
        elif framing == "single":
            points += stage.points_of(character, BUST) + [head["top"]]
            points += [head["center"] + side * head["radius"] * 1.6 for side in (Vector((1, 0, 0)), Vector((-1, 0, 0)), Vector((0, 1, 0)), Vector((0, -1, 0)))]
        else:
            r = head["radius"]
            points += [head["center"] + Vector(offset) * r for offset in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))]
    return points


def draw_panel(scene, cam, panel, number, out, places, cast, width, toon):
    started = time.time()
    place = places.get(panel["place"])
    places.show_only(panel["place"])
    cast.hide_all()
    shape = kit.SHAPES[panel.get("shape", "square")]
    size = (int(width * shape[0]), int(width * shape[1]))
    framing = panel["framing"]
    front_deg = place.get("front_deg", 0.0)
    marks = place.get("marks") or {}
    apart = place.get("apart_m", 1.1)
    members = panel["cast"]
    if len(members) == 1 and members[0].get("at", "center") in kit.SPOTS and framing != "wide":
        apart = 0.0  # alone in a talk panel: stand in the middle whatever spot was named
    posed = []
    for member in members:
        character, what, home = cast.pose(member["who"], member["pose"])
        stage.show(character, True)
        at = member.get("at", "center")
        there = at == kit.THERE and home == panel["place"]
        posed.append((member, character, what, there, at))
    # A moment kept where its shot has it decides where the camera stands; otherwise the place does.
    anchor = next((p for p in posed if p[3]), None)
    if anchor:
        front_deg = math.degrees(stage.facing_now(anchor[1])) + THERE_VIEW_DEG
    front_deg += panel.get("around", 0.0)
    toward = toward_of(front_deg, panel.get("above", ABOVE_DEG[framing]))
    right = Vector((math.cos(math.radians(front_deg)), math.sin(math.radians(front_deg)), 0.0))
    base = Vector((place["center"][0], place["center"][1], 0.0))
    if anchor:
        hips = stage.bone_point(anchor[1], "hips")
        base = Vector((hips.x, hips.y, 0.0))
    characters, notes = [], []
    for member, character, what, there, at in posed:
        floor = place["floor"]
        if there:
            pass  # exactly as the clip has it
        else:
            if at in marks:
                spot = Vector(marks[at]["at"][:2] + [0.0])
                floor = marks[at]["at"][2] if len(marks[at]["at"]) > 2 else floor
            else:
                side = {"left": -1.0, "center": 0.0, "right": 1.0}.get(at, 0.0)
                spot = base + right * side * apart
            facing = facing_angle(member.get("facing", "camera"), front_deg)
            stage.stand_at(character, (spot.x, spot.y), facing, floor if "pose" in what else None)
            if "pose" not in what:
                character["rig"].location.z += floor  # a clip stands on z = 0
                bpy.context.view_layer.update()
        hips = stage.bone_point(character, "hips")
        shadow = character["shadow"]
        shadow.hide_render = False
        reach = max(0.22, (stage.head_of(character)["top"].z - floor) * 0.2)
        shadow.location = (hips.x, hips.y, floor + 0.006)
        shadow.scale = (reach, reach, 1.0)
        characters.append(character)
        notes.append(dict(what, who=member["who"], at=at))
    styled = [o.name for c in characters for o in c["meshes"]] + [o.name for o in place["objects"]]
    stage.run_script("toon.py", dict(toon, objects=styled))  # the paint first: a drawn face goes into it
    for member, character, note in zip(members, characters, notes):
        note["expression"] = cast.face(member["who"], character, member.get("expression") or "neutral")
    cam.data.type = "PERSP"
    named = (place.get("cameras") or {}).get(panel.get("camera") or "")
    if named:  # a set's own camera
        cam.data.lens = named["lens"]
        stage.aim(cam, Vector(named["at"]), Vector(named["look_at"]))
        distance = (Vector(named["at"]) - Vector(named["look_at"])).length
    else:
        cam.data.lens = LENS[framing]
        room = HEADROOM[framing] if (panel.get("lines") or panel.get("caption")) else 0.06
        distance = stage.fit_camera(cam, frame_points(framing, characters), toward, size, margin=MARGIN[framing], pad=(0.0, 0.0, room, 0.0))
        inside = place.get("camera_within_m")
        for _ in range(3):  # a stand-in with ropes or walls round it: widen the lens until the camera is inside them
            if not inside or distance <= inside:
                break
            cam.data.lens = max(18.0, cam.data.lens * inside / distance * 0.97)
            distance = stage.fit_camera(cam, frame_points(framing, characters), toward, size, margin=MARGIN[framing], pad=(0.0, 0.0, room, 0.0))
    bpy.context.view_layer.update()
    path = os.path.join(out, "%02d.png" % number)
    look = dict({"line_px": round(size[0] * LINE_SHARE, 2)}, **toon)  # the line is a share of the panel, so it prints the same at any size
    stage.run_script("toon.py", dict(look, objects=styled, size=list(size), path=path, background=None))
    heads, bodies = {}, {}
    for member, character in zip(members, characters):
        heads[member["who"]] = stage.head_in_picture(scene, cam, character, size)
        spots = [stage.in_picture(scene, cam, p, size)[0] for p in stage.shape_points(character, every=9)]
        bodies[member["who"]] = [min(s[0] for s in spots), min(s[1] for s in spots), max(s[0] for s in spots), max(s[1] for s in spots)]
    return {"file": "panels/%02d.png" % number, "size": list(size), "heads": heads, "bodies": bodies, "sky": place.get("sky"), "sky_image": place.get("sky_image"),
            "place": panel["place"], "framing": framing, "cast": notes, "seconds": round(time.time() - started, 2)}


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    runs, only, width = os.path.join(kit.REPO, "runs"), None, 900
    toon = {}
    for flag in ("--runs", "--only", "--width", "--toon"):
        if flag in args:
            i = args.index(flag)
            value = args[i + 1]
            del args[i:i + 2]
            if flag == "--runs":
                runs = os.path.abspath(value)
            elif flag == "--only":
                only = [int(v) for v in value.split(",")]
            elif flag == "--width":
                width = int(value)
            else:
                toon = json.loads(value)
    folder = os.path.abspath(args[0])
    comic = kit.read_json(os.path.join(folder, "comic.json"))
    wrong = kit.problems(comic, kit.kit(runs))
    if wrong:
        print("PANEL cannot draw this comic: " + "; ".join(wrong))
        sys.exit(1)
    out = os.path.join(folder, "panels")
    os.makedirs(out, exist_ok=True)
    started = time.time()
    scene = stage.fresh_scene()
    cam = stage.add_camera(scene)
    places, cast = Places(scene, runs), Cast(scene, runs)
    record_path = os.path.join(folder, "panels.json")
    drawn = kit.read_json(record_path)["panels"] if only and os.path.exists(record_path) else [None] * len(comic["panels"])
    for number, panel in enumerate(comic["panels"], 1):
        if only and number not in only:
            continue
        drawn[number - 1] = draw_panel(scene, cam, panel, number, out, places, cast, width, toon)
        print("PANEL %d of %d: %s, %s, %.2f s" % (number, len(comic["panels"]), panel["framing"], panel["place"], drawn[number - 1]["seconds"]))
    total = round(time.time() - started, 2)
    with open(record_path, "w") as f:
        json.dump({"panels": drawn, "seconds": total, "width": width, "runs": runs}, f, indent=1)
    print("PANEL all drawn in %.2f s (%.2f s a panel, with loading)" % (total, total / max(1, len([d for d in drawn if d]))))


main()
