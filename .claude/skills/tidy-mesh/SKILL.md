---
name: tidy-mesh
description: Clean up, optimize, retopologize or resize a generated 3D mesh (TRELLIS.2 output or any messy GLB) in Blender. Use when asked to tidy a mesh, fix its topology, make it lighter or game/web/AR-ready, make LODs or quad topology, bake its materials or textures, or produce a named profile (hero, quads, web, game, mobile, midpoly, lowpoly) of a finished object in runs/. Also for a character's gear that comes off (separate gear meshes, sockets for props), and for giving a low-poly or mid-poly character a skeleton, joint limits and a walk (rig, skin, animate).
---

# tidy-mesh

Turns a raw generated mesh into something a 3D modeler would hand over: real
parts only, clean quad topology that follows the form, materials baked into
textures a GLB can carry, at the size the job needs.

## What is wrong with a raw TRELLIS.2 mesh

Measured on a real run (`runs/*-iron-kettle/mesh.glb`):

- **An even soup of ~300k triangles** with no edge loops. TRELLIS.2 builds the
  surface from voxels, so density ignores the form: flat sides get as many
  triangles as the lid rim.
- **It looks like 1,300 pieces with 42k open edges.** That is mostly glTF's
  fault: it splits vertices along every texture seam. Welding them (clean.py)
  reveals the real topology: a handful of parts (body, handle, lid knob…)
  plus a few floating specks and a few dozen non-manifold edges.
- **Materials are one baked atlas** (base color plus metallic/roughness) with
  lighting partly baked in. Metallic is often wrong across the whole object.
- **Size is normalized to about 1 m**; the real size comes from the brief.
- **Shader-node fixes don't survive export.** Anything done with color ramps,
  mixes or bump nodes in Blender is dropped by the GLB exporter unless baked
  (bake.py, mode "materials").

## Profiles: pick by what the object is for

| Profile | For | Mesh | Textures | Shape error, typical / worst (kettle) |
|---|---|---|---|---|
| `hero` | close-up renders, printing | cleaned, 200k triangles | 2048, materials baked | — |
| `quads` | keep modeling it | ~15k adaptive quads | 2048 + normal map | 0.26% / 2.4% |
| `web` | web pages, product viewers | ~8k adaptive quads, Draco | 1024 WebP + normal map | 0.36% / 2.4% |
| `game` | real-time games | ~4k adaptive quads, Draco | 1024 WebP + normal map | 0.51% / 2.2% |
| `mobile` | phones, AR | ~3k adaptive quads, Draco | 512 WebP + normal map | 0.89% / 2.7% |
| `midpoly` | phone games on today's hardware | the block-out's pieces built again rounder and smooth, 3,000-8,000 triangles, Draco | 1024 WebP + normal map | about the block-out's own (2-2.5% / 4-7% on four characters) |
| `lowpoly` | old-school real-time look (think early Warcraft) | 300-800 triangles Claude blocks out from simple shapes | one 256 px WebP: color with soft shadows baked in | see `lowpoly.json` |

**What a good result looks like.** Mostly rectangular quads (~99%) in
regular loops (most vertices with four edges), a little denser where the
shape curves (spout, knob, rims) and larger on flat areas. That is normal,
editable modeling topology. We do not chase the last percent of shape error
with exotic geometry: slivers and triangle fans are harder to edit than a
tip that is a millimetre short. The worst spot on the kettle (~2.4%) is
where the handle's metal straps tuck into the handle, which barely shows.

**How:** the light profiles use AutoRemesher (MIT,
github.com/huxingyi/autoremesher, `just autoremesher` installs it into
`tools/`), which sizes quads to the curvature (`adaptivity`). It runs only in
the background runner, not over MCP. Its quad target is a starting point, so
the runner re-runs it until the count is within 10%. Without it installed,
profiles fall back to `retopo.py` (QuadriFlow: even quad size, so thin tips
come out a quad short) and say so in `<profile>.json`. Below ~3k quads the
thin handle brackets start to break up on an object like the kettle.

Not used, and why (researched Nov 2026): shape-aware triangle decimation
(faithful but slivers, hard to edit); QuadWild (prebuilt only as a 2023
build); Exoside Quad Remesher (licence forbids automated use); open AI
"artist mesh" models (triangles only, drop small parts); cloud retopology
(Tencent Smart Topology, Meshy remesh) is a possible future comparison.

## The Forge add-on: tools as one line

The Blender MCP runs every call in a fresh namespace, so without help Claude
pastes a whole tool script into each call. `just forge-addon` installs
`blender/forge_tools.py` into Blender's `scripts/startup` folder with copies of
these scripts (restart Blender once; re-run it after changing a script). Then
a tool is one line:

    bpy.ops.forge.run(tool="measure", params=json.dumps({...}))
    print(bpy.context.scene["forge_result"])

It runs only the bundled scripts, by name, with data-only settings. The
pipeline prompts switch automatically (`baml_src/4_polish/tools.baml`):
with the add-on installed they carry each tool's instructions and PARAMS
(about a quarter of the text), otherwise the whole scripts. If a script
here has changed since the add-on was installed, Blender still holds the
old copy, so the prompts go back to whole scripts until `just forge-addon`
is run again.
`just forge-addon-remove` uninstalls it.

## Low poly: built, not reduced

Below ~1,000 triangles every reduction method fails on a real object (on the
kettle: shape-aware reduction crumples it, AutoRemesher drops the handle and
spout). Early real-time artists didn't reduce, they blocked models out from
simple shapes and painted the shading into one small texture. So does this
tier: pipeline step 4c (`BlockOut`, `baml_src/4_polish`) has Claude measure
each part (`measure.py`), build the object in a "Low poly" scene from lofts
of 6-12 sides, tubes, lumps and boxes (`build.py`, which also checks the
shape), look at it, and export `runs/<run>/lowpoly.glb` (`export.py`). The `lowpoly` profile brings it in (`blockout`
step) and bakes the detailed mesh's color with its ambient occlusion
multiplied in (`bake.py` `"ao": true`) into one 256 px texture: no normal,
metal or roughness maps. Without `lowpoly.glb` the profile is skipped.

If the brief's `lowpoly_style` asks for flat colors (old-school RuneScape
and the like), the profile keeps Claude's per-part vertex colors and faceted
shading instead and bakes nothing: the troll is 15 KB with no textures. A
baked texture turns muddy at a few hundred triangles.

## Mid poly: the block-out, built again denser

A phone today draws a few thousand triangles per character without
noticing, and a normal map does the rest. `midpoly` is for that: rounder
than the low-poly version and textured from the detailed mesh, but still a
handful of simple pieces a rigger can follow. It costs no extra time in
Blender with Claude: it is made from what Claude already built.

- **The block-out leaves a recipe.** `build.py` keeps every piece as it was
  asked for (rings, tubes, the head's rows and its measured surface), and
  `export.py` writes that into `lowpoly.glb` as glTF extras. The tools run
  in safe mode and can't write a file of their own, so the .glb carries it;
  right after step 4c `scripts/blockout_recipe.py` copies it out as
  `runs/<run>/lowpoly_build.json`.
- **The runner builds the recipe again** (`rebuild` step in
  `scripts/tidy_profile.py`): twice the points around every loft and tube,
  a new ring eased in between every two (on a smooth curve through the
  rings, never bulging past either one), rocks and heads split in four,
  smooth shading with edges sharper than 40 degrees kept crisp. If that
  lands outside 3,000-8,000 triangles it tries a lighter or heavier mix.
  Square posts stay square, belts keep their four rings, boxes stay boxes.
  A head loses its sunk eye sockets: here the texture carries the eyes.
- **Then it bakes** the detailed mesh's color, normal map, metal and
  roughness at 1024 px (`bake.py` "onto"), WebP and Draco.
- **A block-out sits off the detailed mesh in places** (a hat brim built
  flat, a mitten for a hand), and a bake that only looks close finds
  nothing there and leaves black. So this bake looks twice, at 2% of the
  object's size and then at 7% for what the first look missed (`"reach":
  [0.02, 0.07]`), and what is still missing takes the block-out's own
  painted color (`"fill": true`).

Measured on the four characters (`just test-tools`; the pirate, ninja and
lizardkin with a body added under their gear, so their block-outs are
heavier than the ones Claude made):

| | Block-out | Mid poly | Strays, typical / worst | Low poly strays | File | Made in |
|---|---|---|---|---|---|---|
| Cave troll | 1,380 triangles | 5,064 | 2.51% / 4.44% | 2.39% / 4.55% | 0.3 MB | 8 s |
| Lizardkin | 1,166 | 4,432 | 2.36% / 4.35% | 2.36% / 4.77% | 0.4 MB | 9 s |
| Pirate | 1,574 | 5,958 | 2.50% / 6.62% | 2.55% / 7.23% | 0.3 MB | 8 s |
| Ninja | 2,078 | 4,166 | 1.80% / 4.83% | 1.77% / 4.83% | 0.3 MB | 9 s |

It is no closer to the detailed mesh than the block-out: the rings are
where Claude put them, and rounding between them doesn't move them. What
changes is the outline (no corners on a limb), the shading, and the
texture. A run from before recipes were kept has none: `just recipe
<run>` plays its transcript again in a background Blender to get one.

## Gear comes off: separate gear, a whole body, sockets

A game takes a character's coat off, or swaps its boots. If the coat is
the torso there is nothing under it. So in the block-out (and the mid-poly
version made from it):

- **The brief lists the gear** (`gear` in `brief.json`): name, kind (worn,
  attached, held), slot, look.
- **Claude builds two layers** (`gear_steps` in
  `baml_src/4_polish/lowpoly_prompt.baml`): the body whole, skin under the
  clothes too, then each worn or attached item as its own piece or pieces
  with `"gear": "<item's name>"`. Pieces without `"gear"` are the body.
  The list goes to `build.py` once as `"gear"`; a piece naming gear that
  isn't on it is refused.
- **`build.py` keeps one object** to look at and check, and marks each face
  with its group. Its result lists the `groups` and `gear_not_built`.
- **`export.py` writes the groups apart**: one mesh per group, named
  `body`, `gear: wool singlet`, `gear: boots`..., each gear mesh tagged in
  glTF extras with `gear`, `kind` and `slot`. `"only_this_object"` now
  means "these meshes and nothing else".
- **Sockets**: `"sockets": True` adds five empties, `socket: hand_right`,
  `hand_left`, `head`, `back`, `hip`, worked out from the body pieces of
  the T-pose (the middle of each palm, the top of the head, between the
  shoulder blades, the left hip at belt height). The character faces -y,
  so its right hand is the one at -x. One that lands wrong is moved with
  `"sockets": {"head": [x, y, z]}`. They are positions only, with no
  turn of their own.
- **Names in a busy Blender.** Blender keeps object names unique across
  the whole file, so in a session that already holds another run's `body`
  the exporter writes `body.001`. The tags say what each node is, and
  `scripts/blockout_recipe.py` sets the names from them.
- **Under a bake, the body would look like the coat** (a bake copies
  whatever the detailed mesh shows at that spot). The runner gives body
  faces that gear covers a plain material in the color Claude painted the
  piece (`skin_under_gear`), so `midpoly`'s body is skin where it was hidden.
- **Held things are not on the character at all.** The picture shows empty
  hands. Pipeline step 6 (`baml_src/6_props`, off unless asked) writes a
  brief for each held item, starts a run folder for it, and saves
  `props.json` in the character's run: which gear item, which socket, the
  prop's folder, and where on the prop the hand goes (`grip`, in words).
  The prop's run is an ordinary run.
- **The gallery** reads the gear and sockets from `<profile>.json` and
  shows a chip per gear piece and a "Where props go" button.

The detailed versions (`hero`, `quads`, `web`, `game`, `mobile`) keep the
gear fused to the body: they are the picture's mesh, and the picture shows
the character dressed. (A later idea, not built: draw the character a
second time undressed, by editing the picture, and make a body from that.)

What it doesn't do yet: the sockets have no rotation, a prop has no grip
point of its own in its file (only the words in `props.json`), and nothing
checks that the body really is whole under each gear piece: look with the
gear hidden.

## Walking: a skeleton, joint limits and a walk that fits the build

The low-poly and mid-poly characters are a handful of simple pieces in a
T-pose, which is the easiest thing there is to put bones in. The `walk`
profile does it: it takes `profiles/lowpoly.glb` and `profiles/midpoly.glb`
and writes each again as `lowpoly-walk.glb` / `midpoly-walk.glb`, with a
skeleton, every mesh bound to it, limits on every joint and one looping
animation, `walk`. Nothing is tuned by hand per character. Three scripts,
run in this order (the runner does it; so can Claude over MCP):

    just tidy runs/<run folder> walk          # after lowpoly (and midpoly) exist
    just walk-strip runs/<run>/profiles/lowpoly-walk.glb strip.png side

**`rig.py`: bones from the model.** One set of names on every character, so
an animation made for one fits all:

    hips > spine > chest > neck > head
    chest > shoulder_l > upper_arm_l > forearm_l > hand_l      (and _r)
    hips > thigh_l > shin_l > foot_l > toe_l                   (and _r)
    hips > tail_1 > tail_2 ...                                 only with a tail

- **Where the joints go is read off the pieces.** With the block-out's
  recipe (`lowpoly_build.json`) it reads the pieces as they were asked for;
  without one it finds each connected piece in the mesh and gathers its
  points back into rings. Either way: the hands' reach and height give the
  arm line; the trunk's width there gives the shoulders; the wrist is the
  narrowest ring before the hand; the elbow and knee are where rings were
  set close together for bending (or the narrowest ring, or the ring
  nearest where the joint usually is); the hip is at the top of the leg
  piece; the ankle sits over the foot piece; a long piece running out
  behind the hips is a tail and gets 2 to 5 bones. `found_by` in the result
  says which rule placed each.
- **Elbows and knees sit on the straight line** from shoulder to wrist and
  hip to ankle, so they are true one-way hinges. A knee is never placed
  outside the middle of the leg (44-56%): the troll's knee rings are lower
  than that, and a leg that lopsided can't take a stride.
- **Binding.** It tries Blender's automatic weights first and keeps them
  only if every point got a weight. On block-outs they don't hold: the
  pieces overlap and hide each other, and Blender left every point of all
  six test characters unweighted. The fallback, by piece: each connected
  piece goes to the limb most of its points are nearest; a small piece (a
  buckle, a tusk, a hand) follows one bone rigidly; a longer one blends
  from bone to bone over about one limb-width at each joint. A skirt or
  belt around both legs stays half with the hips. The sole is all foot
  behind the ball and all toe ahead of it. At most four bones a point.
  `weights` and `why_not_automatic` in the result say what happened.
- **Limits** go on as Limit Rotation constraints and ride on each bone as
  `limit_deg` (in the .glb too, as glTF extras): knee 0-150 and elbow 0-150
  one way only; hip 120 forward, 30 back, 40 out and 40 of twist; shoulder,
  spine, neck, wrist, ankle and toes their usual reach. They are scaled by
  the build: the troll's joints get 0.81 of a person's reach, the ninja's
  1.10 (`flexibility`; hinges keep their full fold).
- **Sockets** are hung on their bones (hands, head, chest, hips), so a prop
  put there follows. Gear meshes stay separate and tagged.
- It also **measures the build** (`measure`): leg, arm and foot length, hip
  and thigh width, how wide the body is at each height, and bulk (volume
  over height cubed).

**`walk.py`: the gait, from those measurements.** Plus four traits from 0
to 1 that a tape measure can't tell: weight, stealth, swagger, stiffness.
The pipeline asks Opus for them once per character from its brief
(`HowItWalks` in `baml_src/7_walk`, saved as `gait.json`; `just gait
runs/<run>` shows the answer without saving). Without them they are guessed
from bulk alone.

- **Speed from leg length.** Walkers of any size move alike at the same
  Froude number, speed squared over gravity times leg length; 0.25 is an
  easy human walk, and weight and stealth bring it down. Stride follows
  (stride / leg = 2.3 x Froude^0.3), cadence is speed over stride, slowed
  again by weight. The loop is rounded to whole frames and the speed set to
  match.
- **Stance** near the hip joints, wider with weight and swagger, never
  narrower than the thighs are thick. **Bob** like an upside-down pendulum
  over each planted foot. **Sway** a share of the stance that grows with
  weight.
- **Arms** hang just clear of the body (from its measured width) and swing
  against the legs. **Spine** leans and twists against the hips. A **tail**
  repeats the hips' turn a moment late, more toward its tip, and is lifted
  clear of the floor.
- **Feet**: heavy ones land flat and toe out; light ones peel off the heel;
  stealthy ones land on the ball and lift higher.

**`animate.py`: fit, plant, clamp, bake.** walk.py only writes a motion:
where the hips go, where the ball of each foot is and whether it is
planted, and how far each bone has turned from the T-pose, in units of the
hip height. animate.py is what plays any such motion on a character:

1. **Fit**: scale by this character's hip height, turn each bone from its
   own rest pose.
2. **Plant the feet**: each leg is solved exactly from hip joint to foot
   (two bones and a hinge), so a planted foot's ball stays on the floor and
   moves back at exactly walking speed. If the legs can't reach, the hips
   come down for the whole loop. If an ankle hits its limit the heel lifts
   and the leg is solved again.
3. **Limits**: every turn is clamped to the bone's `limit_deg`; `clamped`
   lists what needed it.
4. **Bake** one key a frame into an action named for the motion, then play
   it back and measure it (`check`).

So the walk is one source of motion among others. A clip from a motion
model on NVIDIA's SOMA skeleton is the second. Two models write it, both on
the same 30 joints and in the same file format: MotionBricks (the movement
between our own poses) and Kimodo (movement from a sentence). A shot can use
both, a beat from each, joined by `scripts/motion/timeline.py`; by the time
it gets here it is one motion like any other, and a second cut of a shot is
cast under a name of its own (`just cast <shot> <run> <prop run> hero-mixed`).
`scripts/motion/soma_to_plain.py` renames it with `bones.json`,
turns it into the same plain form, and `scripts/motion/apply_shot.py` sends
it through the same four steps (`just cast <shot> <run> [prop run]`; README,
"Shots"). It looks joints up by name, so a skeleton with more joints than
the table needs is fine. Three things it does that the walk has no need of:
our elbows are one-way hinges, so the two arm bones are set from where the
shoulder, elbow and wrist are rather than from the model's own share of
twist; a foot the model calls down is pinned to one spot for as long as it
is (nearly) still; and a prop gets a bone of its own, `prop`, keyed to sit
on whichever socket holds it. A Mixamo importer is still not built.

`export.py` with `"rig": true` writes the skeleton, its meshes, the sockets
on their bones and the action as one .glb (not Draco-packed: at this size
it saves little, and plain files can be checked without a decoder).

Measured on four characters (`just test-tools`, traits from Opus in
`scripts/test_gaits.json`):

| | Cave troll | Ninja | Pirate | Lizardkin |
|---|---|---|---|---|
| Leg (hip height) | 0.99 m | 0.88 m | 0.77 m | 0.89 m |
| Arm / leg | 1.39 | 0.82 | 0.88 | 0.85 |
| Bulk | 0.169 | 0.039 | 0.060 | 0.089 |
| Weight, stealth, swagger, stiffness | .95 .05 .6 .7 | .35 .8 .12 .2 | .6 .15 .7 .35 | .65 .25 .45 .5 |
| Speed | 0.93 m/s | 1.26 | 1.14 | 1.10 |
| Stride | 1.11 m | 1.17 | 1.03 | 1.10 |
| Steps a minute | 100 | 129 | 133 | 120 |
| Feet apart | 0.83 m | 0.21 | 0.29 | 0.41 |
| Bob / sway | 10.8 / 43.9 cm | 4.8 / 3.7 | 8.0 / 11.5 | 8.9 / 16.2 |
| Arm swing, hands travel | 16 deg, 0.78 m | 10 deg, 0.24 m | 22 deg, 0.51 m | 16 deg, 0.42 m |
| Planted foot slides, a step | 0.14 cm | 0.01 | 0.01 | 0.02 |
| Through the floor | 0.06 cm | 0.01 | 0.01 | 0.00 |
| Turns outside a limit | 0 | 0 | 0 | 0 |

The troll is slow, wide and rolling because its build is (bulk four times
the ninja's, thighs 0.4 m thick, arms longer than its legs); the ninja is
narrow, low and quiet mostly because of what Opus said about it. The
lizardkin's tail has five bones.

What is weak, most visible first:

- **Skin shows through clothes on a stride.** The body and a gear piece
  over it have their rings at different heights, so they bend differently;
  on the wrestlers a bare thigh pokes through the trousers. The fix is to
  hide the body's faces under gear while it is worn (the runner already
  knows which they are: `skin_under_gear`).
- **Bending is by nearest bone.** No twist bones, no corrective shapes:
  an elbow or knee folds like a paper tube, and a kilt follows the thighs
  in facets.
- **The troll's ankles run out.** Its shins are short, so in late stance
  the ankle hits its limit and the heel comes up as much as 42 degrees;
  on one frame a foot and its toes are clamped (0.14 cm of slide).
- **Joint finding is rules of thumb.** It expects a T-pose facing -y, two
  legs, arms held out, and pieces built along the axes. A head is "the
  lowest sizeable piece above the arms"; a cape that hangs behind the hips
  could be taken for a tail.
- **One gait.** No start, stop, turn or run, no uneven ground, and the walk
  stays in place (the speed is in `<version>-walk.json` for whoever moves
  the character).
- **Hands and face don't move**: one bone per hand, none in the face.

## Faces: a character's head is measured, not guessed

Left to itself, Claude spends a low-poly character's triangles on the
outline and builds the head as one more loft. The first troll's head was 54
triangles of 1,254: no brow, eyes, nose or mouth, only tusks, and from the
front it read as a notch in the chest. On a character the face is what
people look at, and old RuneScape models show how little it takes: a brow
that overhangs, dark eye sockets, a wedge of a nose, a mouth line, and flat
colors doing the rest.

So step 4c gives a character two extra things (`CHARACTER_STEPS` in
`baml_src/4_polish/lowpoly_prompt.baml`): a stated share of the triangles
for the head and face (15-25%), and `face.py`.

- **`face.py` finds the face.** Give it the head's box and which way the
  face looks. It looks at the head front-on, 44 rows by 12 lanes a side,
  and reads how far forward the surface is and how dark the texture is.
  Eyes and mouth are the dark bands; brow, nose and chin are where the
  profile sticks out; tusks are a lane that juts out beside the mouth. It
  prints a whole `"head"` piece: six rows of `[height, front of the face,
  half-width]` (chin, mouth, nose, eyes, brow, top), eye and mouth sizes,
  the underbite, tusks, ears, and skin, socket, beard and hair colors.
  `"found"` says whether each came from the texture, the shape, or a guess.
- **It keeps the head's surface.** The same look, plus one from behind,
  is stored in the scene under the piece's name: how far forward the front
  is, how far back the back is, and how wide the head is, row by row. The
  piece's `"scan"` points at it.
- **It shows its work.** It draws a wire box with a line at each feature's
  height, `Look: face`. Aim `look` at it: a line that misses its feature
  means that row's height needs setting by hand.
- **`build.py` lays the head on that surface, then cuts the face into it.**
  The `"head"` piece goes into `"parts"` like any loft. Its ten rings sit at
  the feature heights; each ring's points are put on the stored surface, so
  the outline, the skull, the cheeks and the jaw are the reference's. Where
  the head is sunk into the body, its sides run straight back into it.
  Then the features: sockets set in and painted dark, the nose's tip, the
  mouth band, tusks and ears where face.py found them. Brow and nose are
  only pushed out when the reference's own wouldn't read. 150 to 240
  triangles, mirrored across the face's center line (the two halves of the
  reference are averaged). Without `"scan"` it builds a plain head from the
  rows alone, which has the features at the right heights on a box-like
  shape.
- **Check it up close.** `preview.py` with `"view": "front"` or `"side"`
  and a `"box"` renders a close-up straight on, and `"over"` draws a second
  object on top as wire. `match.py` with a `"box"` scores that spot alone,
  and compares outlines and surfaces there: how much of the two shadows is
  shared, how far apart their edges are, and how far apart the surfaces are
  toward the viewer.

How well it follows the reference, head alone, front / side (`just
test-tools`, which also leaves the pictures):

| Troll's head | Triangles | Outline shared | Edges off | Surface off | Reference strays, head box |
|---|---|---|---|---|---|
| hand-built loft | 54 + 16 | 80% / 30% | 4.7 / 11.6 cm | 14.4 / 10.9 cm | 2.77% / 3.45% |
| plain (rows alone) | 188 | 83% / 89% | 3.1 / 1.2 cm | 3.5 / 5.3 cm | 1.75% / 3.23% |
| laid on the surface | 196 | 91% / 90% | 1.6 / 1.2 cm | 2.2 / 1.5 cm | 1.11% / 1.71% |

The pirate (a person, with a beard, an eye patch, a hat and a white
collar): 188 triangles; surface off 1.5 / 2.1 cm against 2.7 / 2.5 for the
plain head; side outline 91% shared against 82%. A loose box that takes in
the troll's chest and shoulders finds the same features within 2 cm.

What still doesn't follow the reference:

- **Between the rings.** Ten rings and five to seven points a side: warts,
  lips, nostrils and the curve between two rings are gone. The eye sockets
  are deliberately deeper than the reference's.
- **The top of the skull** is one point above the last ring, a low pyramid
  where the reference is a dome.
- **Whatever else is in the box.** The pirate's collar sits beside his
  beard, so the jaw's ring is as wide as the collar. Stop the box above it.
- **Tusks and ears are simple spikes** at the measured place and length,
  not the reference's curved ones.

Where it goes wrong, and what to do:

- **A hat or helmet.** Seen from the front, a brim hides the forehead and
  is as dark as the eyes. Stop the box at the brim; the hat is its own piece.
- **Hair or a beard over the face, an eye patch.** The dark bands are no
  longer the eyes and mouth. `"found"` will say `"shape"` or `"guess"`;
  look at the guide lines and set the rows by hand.
- **No texture, or eyes no darker than the skin.** It goes by shape alone:
  the nose, chin and tusks are still found, the eyes are placed in the
  hollow above the nose or, failing that, where eyes usually sit: a guess
  on a smooth head, so check the guide lines.
- **A head turned or tipped.** It expects a level head looking straight
  along one axis, which is how the pipeline draws characters.
- **Ears hidden by hair, and horns.** Ears are found when they stand out
  beside the head at eye height; otherwise add `"ears": True` (or sizes)
  when the description names them. Horns are separate pieces (a tube each).
- **Colors come from the texture, baked shadows and all.** Use the head's
  `"color"` for the body's skin too, or the head will not match it.

## Parts: remesh the pieces a modeler would build separately

TRELLIS.2 fuses touching parts into one surface: the kettle's lid, knob and
spout are one piece with its body, which is 93% of the mesh. One remesh over
all of it makes every part share one quad layout. Nothing in the mesh says
where a part ends (we tried cutting along creases: TRELLIS blends the joins
too softly), so someone who knows what the object is has to say.

That's Claude, in pipeline step 4b (`FindParts`, in `baml_src/4_polish`): in
a "Parts" scene of the live Blender it places one box per part (or a few
with the same name, or a tilted one, where a straight box can't follow it),
checks them with `split.py` in "color" mode and `look`, and saves the boxes
as `runs/<run>/parts.json`. The profile runner then cuts with `split.py`
("split" mode: each part becomes its own piece, its cut opening capped
inside the joint) and remeshes every piece on its own budget, which grows
with area^0.75 so thin parts aren't starved. Delete `parts.json` to go back
to one remesh; `just resume` asks Claude again.

To do it by hand in the live Blender: run `split.py` in "color" mode with
your boxes, `look`, adjust, then write the boxes to `parts.json`
(`{"parts": [{"name", "why", "min", "max"}], "notes"}`; a part may add
`"turn": [x, y, z]` degrees to tilt its box and `"wraps": true` if it goes
all the way around, like a belt, so the legs below it stay body).

## The bench: tools for the three Blender steps

In pipeline steps 4, 4b and 4c Claude used to write the same Blender code
again in every run, and about one call in seven failed on the way (17 of
117 in the cave-troll run, 13 of them refused by safe mode). These scripts
are that work, done once. Each step's prompt carries the ones it uses
(`baml_src/4_polish/tools.baml`).

| Script | Use it to | Step |
|---|---|---|
| `open.py` | bring a .glb in as one named object, in a scene of its own, and print its size | all three |
| `stand.py` | turn it to face front, scale it to its real size, rest it on the floor, weld it, shade it smooth | finish |
| `retouch.py` | change metal, sheen, color or grain all over or in one area (a place, a color range, or both); say what the texture is like there | finish |
| `frame.py` | put a wire box around a spot so `look` can frame a close-up without clipping | finish, parts |
| `stage.py` | add the floor, three lights, sky and a camera that fits the object; set the render | finish |
| `export.py` | write one object as a GLB and read the file back to prove nothing else came along; a block-out with gear goes out as one mesh per group plus its sockets | finish, low poly |
| `measure.py` | size a part without its neighbors, and slice it into rows of middle and half-width | parts, low poly |
| `split.py` | paint or cut the parts from boxes: several boxes per part, tilted boxes, parts that wrap around | parts |
| `face.py` | find the brow, eyes, nose, mouth and chin on a character's head and print it as a `"head"` piece for `build.py` | low poly (characters) |
| `rig.py` | give a T-pose character bones placed from its own build, bind every mesh, set each joint's limits, hang the sockets on bones | walk |
| `walk.py` | work out a walk from the measured build and four traits; leaves it on the rig as a motion | walk |
| `animate.py` | play a motion on the rig: fit it, plant the feet, clamp to the limits, bake keyframes, measure the result | walk |
| `build.py` | block out a low-poly version from a list of lofts, tubes, lumps, boxes and a head; join, color and check it; keep gear as groups, add sockets, keep the recipe | low poly |

How they fit together:

- **Measure, then build.** `measure.py` prints rows of `[position, middle,
  middle, half-width, half-width]`. Those are the `"rings"` of a `build.py`
  loft, so a measured part goes straight in. On the kettle, seven pieces
  built from rows nobody touched come out at 806 triangles, 3.0% off
  typically; Claude's hand-tuned one was 790 and 2.3%.
- **One call per round.** `build.py` keeps every piece in the scene, hidden.
  The next call sends only the pieces that change and gets back the triangle
  count, how far the shape strays (the same numbers `match.py` gives), where
  the detailed mesh pokes out most, and which piece sticks out where.
- **Areas, not the whole surface.** `retouch.py` picks an area by where it
  is, how light, how colorful, or what hue, so "the dark band on that wrist"
  is a box plus a darkness range. `"show"` paints the area red to check it.
  Every number ends up in a Value node named `retouch: <area>.<setting>`, so
  a later nudge is one line, not the whole script again.
- **Exports hold one thing.** Blender's glTF exporter writes every scene in
  the file unless told `use_active_scene=True`; "selected only" is not
  enough. Two runs hit it: the kettle's `lowpoly.glb` picked up two meshes
  from other scenes, the troll's the whole 293k-triangle reference.
  `export.py` sets it and reads the file back (`"only_this_object": true`).
- **Close-ups need a box.** `look` only draws what lies within a few
  target-widths of its target. Aimed at a tiny marker it cuts the rest away.
  `frame.py` makes the target the size of the spot; pass no distance.

### Nothing carries over between calls

The add-on runs every `execute_blender_code` call as
`exec(code, {"bpy": bpy})` (`addon.py`, `execute_code`): a brand-new
namespace each time. A function or variable from one call is gone in the
next, and safe mode closes the places code could be kept (`bpy.data.texts`,
`bpy.app.driver_namespace`, handlers). So:

- every tool is one whole script, sent each time with its `PARAMS` edited.
  The comments above `PARAMS` are the instructions; Claude reads them and
  sends from `PARAMS = {` down;
- what has to last lives in the Blender file: `build.py`'s pieces are hidden
  objects, `retouch.py`'s numbers are nodes, `open.py` tags the scene it made;
- the scripts are kept short and each does a lot per call, because the cost
  of a call is now mostly retyping the script.

### Safe mode

`scripts/check_safe.py` (`just check-safe`) reads a script the way the
add-on's safe mode does and lists what it would refuse. Run it on anything
you add here. The rules that catch people out: no `lambda`, no classes, no
numpy, no `import x as y`, no variable named after a builtin (`min`, `max`,
`type`, `id`), no calling a function that was passed in as an argument,
`getattr` only with a literal name.

## Run a profile (default: in the background)

Heavy steps (retopology, baking) lock Blender's window while they run, so by
default run them in a separate background Blender, which never touches the
person's open session:

```
just tidy runs/<run folder> web game        # one or more profiles
just tidy runs/<run folder> hero quads web game mobile
just tidy runs/<run folder> lowpoly midpoly     # need the block-out (lowpoly.glb); midpoly also its recipe
just tidy runs/<run folder> walk                # needs lowpoly (and midpoly) made first; adds <version>-walk.glb
```

Each profile's `<profile>.json` records `shape` (from match.py): how far the
light mesh strays from the full one. Read it, not just the previews.

This reads the run's `scene.blend` (with Claude's material fixes; falls back
to `mesh.glb`) and writes into `runs/<run>/profiles/`: `<profile>.glb`,
`<profile>.blend` (GLB can only store triangles, so the real quads live
here), a preview `<profile>.png`, a wireframe preview `<profile>-wire.png`, and
`<profile>.json` with what every step did. About 10 s per profile, 20 s for
`quads`. **Always look at both previews** before saying a profile is good.

To show a result in the live Blender, import it over MCP
(`bpy.ops.import_scene.gltf(filepath=...)`): that is light.

## Work in the live Blender (when the person wants to watch or steer)

The scripts in `scripts/` are the same steps, written to be sent whole
through the blender MCP `execute_blender_code` tool. Read the file, edit the
`PARAMS` block at the top, send it, and read the `RESULT {json}` line it
prints. They use only bpy, bmesh, mathutils and a few plain-Python modules,
so they pass the add-on's safe mode (`just check-safe`).

| Script | Does | Cost in live Blender |
|---|---|---|
| `inspect.py` | measures everything below, changes nothing | instant |
| `clean.py` | welds seams, deletes specks and loose bits, closes small holes, fixes normals, smooth shading with sharp edges | ~2 s |
| `decimate.py` | shape-aware reduction to a triangle budget, keeping UVs; `as_copy` + `quadify` make a light "(light)" copy to bake onto | a few s |
| `match.py` | how far a light mesh strays from the full one, and where (both directions, % of size); `"box"` scores one spot alone | ~2 s |
| `retopo.py` | rebuilds each part as quads with QuadriFlow, on the part's own repaired surface when it can (voxel remesh only as a fallback for big parts), shrinkwrapped back onto the original; `routes` says which way each part went | 5–30 s, freezes Blender |
| `bake.py` | "materials": bakes the shader into plain textures; "onto": bakes color, metal, roughness and a normal map from the full mesh onto a lighter one (`"reach"` and `"fill"` for a block-out that sits off the full mesh) | 5–60 s, freezes Blender |
| `export.py` | writes one object as GLB (WebP, Draco optional), from the open scene only, and reads it back to check | ~1 s |
| `preview.py` | renders a quick three-quarter PNG, optionally with wireframe; `"view"` and `"box"` make a straight-on close-up | ~2 s |
| `split.py` | splits an object into named parts from boxes ("color" mode just paints them, to check the boxes) | ~1 s |
| `lineup.py` | shows a run's raw mesh and its profiles side by side in a new "Profiles" scene, labelled, wireframe on | ~2 s |

Rules for the live session:

- **Every call freezes the person's Blender until it returns.** Warn before
  `retopo.py` or `bake.py`, or run them in the background instead.
- Check with `look` using shading `"material"` or `"solid"`; `"rendered"`
  runs Cycles and is slow.
- Order: `inspect` → `clean` → (`decimate` or `retopo`) → `match` → `bake`
  → `export`. Run `inspect` again after each step and compare.
- Judge shape with `match.py`: under ~0.5% worst error is invisible at
  normal distance; over ~1.5% shows in the silhouette.
- Keep the full mesh: `retopo.py` and `bake.py` hide it rather than delete it.

## Reading inspect.py

- `pieces` / `largest_pieces`: real separate parts after welding. A handle or
  lid can be its own part; specks are tiny in both share and size.
- `seam_split_vertices`: vertices glTF duplicated along seams. Not a defect;
  clean.py welds them.
- `non_manifold_edges`, `boundary_edges`: holes and tangles. Small numbers
  are normal for TRELLIS output; a mug's mouth is a legitimate boundary.
- `unapplied_transform`, `bottom_z`, `origin`: whether it is ready to place.
- `materials[].principled`: what is textured vs. a flat value, and whether
  there is a normal map.

## Known limits

- Thin straps and brackets are the weak spot at every size (~2.4% on the
  kettle's handle brackets); below ~3k quads they break up. Raise the
  profile's `quads` for objects with fine detail.
- In the live Blender (MCP) there is no AutoRemesher: `retopo.py` gives even
  QuadriFlow quads, which lose about one quad at thin tips. For adaptive
  quads, run the profile in the background and import the result.
- QuadriFlow refuses some parts that pass every manifold check we can run;
  retopo.py then falls back to a fine voxel remesh (big parts) or plain
  reduction (small parts) and says so in `routes`. The voxel route's error
  varies with `detail`; 450 measured steadiest.
- At very low budgets a bake can miss parts of the surface, which shows as
  black patches. bake.py widens its reach for coarse meshes; if patches
  remain, raise the budget.
- For close-up renders, `hero` (the cleaned dense mesh) stays the most
  faithful.
- `midpoly` is as true to the shape as its block-out and no truer. Where
  the block-out is far off (a tricorn's turned-up brim built flat), the
  texture there is borrowed from farther away or is the block-out's flat
  color.
- A body face counts as "under gear" when gear lies within 4% of the
  object's size straight out from it. A face only partly covered (a neck
  at a collar) goes one way or the other, so the edge is stepped.

## Testing a script change

```
blender -b --factory-startup -P scripts/tidy_headless.py -- MESH.glb \
  .claude/skills/tidy-mesh/scripts/clean.py .claude/skills/tidy-mesh/scripts/inspect.py \
  --params '{"inspect.py": {}}'
```

runs scripts against a GLB with no live Blender, each in a fresh namespace
as over MCP. Re-run the five profiles on the kettle run and compare previews
before calling a change done.

`just test-tools` (`scripts/test_tools.py`) tries the bench tools on the
cave-troll and iron-kettle runs the same way, about a minute: the troll's
import and cleanup, its part sizes against `parts.json`, both block-outs
rebuilt, each exported file opened to count what is in it, old part plans
cut exactly as before, and the troll's face measured and rebuilt next to
its old head (and the pirate's, if that run is there); the troll's gear
written apart with its sockets; and the `midpoly` profile made for real on
copies of the troll, lizardkin, pirate and ninja runs (the last three from
their recorded block-outs in `scripts/test_blockouts.json`); and the walk: each of the four
rigged, walked and exported, with the foot slide, floor, limits, loop and
weights checked both in Blender and in the written file. A few minutes
in all. With `--keep DIR`
the face cases leave `troll-head-compared.png` and
`pirate-head-compared.png`: front and side of the reference, each head, and
the fitted head as wire over the reference. `just check-safe` checks every script against safe
mode.
