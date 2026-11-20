# Put a wire box around a spot so `look` can frame it.
#
# `look` frames whole objects. Aimed at a tiny marker with a short distance
# it cuts away everything more than a few marker-widths deep, which is why
# close-ups of a head or a hand come out clipped. A box the size of the spot
# fixes that: look(mode="angles", target=["Look: head"]) frames the box and
# keeps its surroundings, with no distance to guess.
#
# The boxes are wire-only and never render. Run with "clear": True when done.
#
# Send this whole file through the blender MCP `execute_blender_code` tool
# after editing PARAMS. Prints RESULT {json}. Instant. Safe-mode compatible.

PARAMS = {
    "spots": {},     # {"head": {"min": [x, y, z], "max": [x, y, z]}, ...} in world meters
    "parts": [],     # or part boxes (parts.json's list): one box per part name
    "clear": False,  # remove every "Look: ..." box first (alone: just tidy up)
}

import bpy
import json
from mathutils import Vector

scene = bpy.context.scene
removed = 0
if PARAMS["clear"]:
    for o in [o for o in bpy.data.objects if o.name.startswith("Look: ")]:
        bpy.data.objects.remove(o, do_unlink=True)
        removed += 1

spots = {}
for name, box in PARAMS["spots"].items():
    spots[name] = (Vector(box["min"]), Vector(box["max"]))
for part in PARAMS["parts"]:
    box = part.get("box", part)
    low, high = Vector(box["min"]), Vector(box["max"])
    if part["name"] in spots:  # several boxes, one part: frame them together
        was = spots[part["name"]]
        low = Vector([min(low[i], was[0][i]) for i in range(3)])
        high = Vector([max(high[i], was[1][i]) for i in range(3)])
    spots[part["name"]] = (low, high)

made = []
for name, (low, high) in spots.items():
    old = bpy.data.objects.get("Look: " + name)
    if old:
        bpy.data.objects.remove(old, do_unlink=True)
    corners = [(x, y, z) for z in (low[2], high[2]) for y in (low[1], high[1]) for x in (low[0], high[0])]
    me = bpy.data.meshes.new("Look: " + name)
    me.from_pydata(corners, [], [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)])
    marker = bpy.data.objects.new("Look: " + name, me)
    scene.collection.objects.link(marker)
    marker.display_type = "WIRE"
    marker.hide_render = True
    marker.hide_select = True
    made.append(marker.name)

print("RESULT " + json.dumps({"targets": made, "removed": removed,
                              "use": "look(mode=\"angles\", target=[\"%s\"])" % (made[0] if made else "Look: ...")}))
