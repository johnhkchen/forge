---
name: tidy-mesh
description: Clean up, optimize, retopologize or resize a generated 3D mesh (TRELLIS.2 output or any messy GLB) in Blender. Use when asked to tidy a mesh, fix its topology, make it lighter or game/web/AR-ready, make LODs or quad topology, bake its materials or textures, or produce a named profile (hero, quads, web, game, mobile, midpoly, lowpoly) of a finished object in runs/. Also for a character's gear that comes off (separate gear meshes, sockets for props), and for giving a low-poly or mid-poly character a skeleton, joint limits and a walk (rig, skin, animate), and a run (the run profile), and for clothes that sit on the body, move with it and swing (drape, cloth, swing), and for skin-tight clothes painted onto a shared body instead of worn as meshes (the painted profile: wrap, paint), and for a real body under clothes that hide it (a base body from a second picture, garments cut out of the clothed mesh: garment, follow) Also for drawing a scene in the comic style (toon shading, ink outlines) and swapping a character's drawn expression (toon, face_swap).
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
shading instead and keeps no texture: the troll is 15 KB. A baked
texture turns muddy at a few hundred triangles. The colors themselves are
then set from the detailed mesh, piece by piece (`"repaint"`; see "Clothes
get their own colors").

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
  A character's body, when it came from a `"body"` piece, is not made
  denser this way: it is built again in mid detail, with more loops where
  it bends and its rings laid on the detailed mesh (see "Anatomy").
- **Then it bakes** the detailed mesh's color, normal map, metal and
  roughness at 1024 px (`bake.py` "onto"), WebP and Draco.
- **A block-out sits off the detailed mesh in places** (a hat brim built
  flat, a mitten for a hand), and a bake that only looks close finds
  nothing there and leaves black. So this bake looks twice, at 2% of the
  object's size and then at 7% for what the first look missed (`"reach":
  [0.02, 0.07]`), and what is still missing takes the block-out's own
  painted color (`"fill": true`). A block-out with gear is baked by
  group instead, which does the same and more: see "Clothes get their own
  colors".

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

## Anatomy: landmarks, and a body built from them

Blocked out by hand, bodies came out as stacked tubes. Measured on eight
characters before this (`scripts/anatomy_check.py`, the same landmark finder
run on the detailed mesh and on each version): hands were the worst region
by far (rings 52% of their own size off the detailed mesh's, a mitten with
no thumb), then necks (34%) and feet (33%), then shoulders (25%), shins,
forearms and thighs (20-21% each); the trunk was closest (ribcage 11%,
pelvis 14%). Of the landmarks, the chest line sat furthest off (5.8% of the
height on average), then ankles, knees and the waist (3.5-4.2%). Elbows had
2 to 4 rings near them on most, and on four characters the skeleton had to
fall back on "the nearest ring" or "the narrowest ring" for an elbow or a
knee. Mid poly was the same body,
rounder: its numbers matched low poly's to within a point.

So the body is a tool's job now, in two halves.

**`landmarks.py` finds where things are.** Pointed at a T-pose mesh facing
-y (the detailed reference, a base body, or a block-out) it returns:

- `landmarks`: one point each for top, chin, neck, neck_base, shoulder,
  armpit, chest, waist, hips, crotch, elbow, wrist, fingertip, knee, ankle,
  heel, toe (the +x side).
- `found`: how each was found. `"shape"` means it shows on the mesh (the
  armpit is where the arm's underside drops away; the crotch where the gap
  between the legs closes; wrist, waist, ankle and neck are narrowest
  rings; hips the widest; the chest the deepest). `"usual proportion"`
  means nothing showed, and the landmark sits where a body with these
  shoulders and this crotch usually has it. Elbows and knees are that more
  often than not: a straight sleeve has no elbow.
- `proportions`: heads tall, leg and arm share of the height, shoulders
  against hips, hand and foot length. They tell the eight apart (the
  villager is 5.5 heads tall, Lincoln 7.9; the troll's arms are 54% of its
  height).
- `girth` (half-width and half-depth at each named ring) and `joints`
  (where shoulder, elbow, wrist, hip, knee and ankle turn).
- and it keeps the body's surface in the scene: 152 rings of 24 distances,
  up the trunk and neck, out one arm and hand, down one leg, along one
  foot. Both sides are read and averaged. Rings are read looking in from
  outside, with walls where a neighbor would get in the way (the arms cut
  off at the armpits, the other leg at the center line), and where
  something else stands three times farther out than the limb's own
  surface (a tail behind a leg) the nearer one is taken.

Give it `"head"`, the box face.py took: the chin is then the box's floor.
A character whose clothes hide its body is read off its base body
(`"object": "Body"`); read off a long skirt it says the crotch can't be
found. About half a second.

**build.py's `"body"` piece builds from them.** `{"name": "body", "body":
"body"}` becomes seven pieces: `body trunk` (a ring between the legs, the
pelvis at its widest, the waist, the ribcage, the upper chest and shoulder
blades, the shoulder line, the slope up to the neck), `body neck`, and
mirrored `body arm` (inside the trunk, shoulder cap, upper arm, three
rings at the elbow, the forearm's belly, its taper, the wrist), `body
hand` (heel of the hand, knuckles, finger mass, tip) with `body thumb`,
`body leg` (ankle, calf, three rings at the knee, thigh, and up inside the
pelvis) and `body foot` (toes, ball, arch, under the ankle, heel). 870 to
890 triangles. They are ordinary lofts in the recipe, so rig.py, drape.py
and the bake read them as before; each ring spells out its own corner
points, laid on the kept surface and pushed out to its true width and
depth, so a six-sided thigh is as wide from the front as the round one.
Settings on the piece: `"landmarks"` and `"girth"` to put one right,
`"follow"` (1 = this character's own surface, 0 = what a body usually
has), `"style"` (`chunky`, `limbs`, `head`), `"under"` (draw it in under
clothes), `"detail"`, `"sides"`.

- **The skeleton lands on the landmarks without being told.** rig.py takes
  rings set closer than the rest for a joint, and the three at each elbow
  and knee are that. On all eight it now finds both by "close rings": the
  elbow on the landmark, the knee on it or within 1.7% of the height
  (rig.py keeps a knee near the middle of the leg). Its wrist is still its
  own (the narrowest ring, or a usual proportion) and sits up to 6% of the
  height from the landmark. The recipe carries `landmarks` and `joints`
  outright, for a rig that reads them instead: rig.py was not changed here.
- **Mid poly asks for the body again** with `"detail": "mid"`
  (`blockout_recipe.mid_parts`): twice the sides, five rings at each elbow
  and knee, one more on the shoulder, and about twice as many along every
  stretch, each laid on the kept surface. That is where pecs, shoulder
  blades, kneecaps and ankle bones come from: the detailed mesh, at the
  density that can show them. The other pieces are made denser as before.
- **`scripts/auto_body.py`** (`just auto-body <run> <out>`) does the whole
  body for a finished run without Claude: landmarks (off the base body
  when there is one), the body, the run's own head, hair and gear back on
  it, drape, export, recipe. It draws the body in where what stays covers
  it. Pieces are told apart by name (torso, arm, leg, hand, foot go);
  `--keep` and `--drop` correct that.
- **`scripts/anatomy_check.py`** (`just anatomy-check`) is the measure:
  landmark distance in % of the height, proportions side by side, shared
  outline front and side, ring-by-ring distance per region, triangles, and
  edge loops at the elbow and knee, with a sheet of overlays and pictures.

Measured on the eight characters, old block-out against a new body with
the old head and gear kept (`scripts/auto_body.py`, then the real
`lowpoly`, `midpoly` and `walk` profiles; sheets in `docs/anatomy/`,
every number in `docs/anatomy/numbers.json`). "Rings off" is the
ring-by-ring distance from the detailed mesh, in % of each ring's size,
averaged over ten regions; "outline" is the share of the two outlines
that overlaps, front / side; "landmarks" is how far the finder's
landmarks on the version sit from those on the detailed mesh, in % of the
height:

| | Low poly, before | Low poly, after | Mid poly, before | Mid poly, after |
|---|---|---|---|---|
| Rings off, mean of 8 | 24.8% | 21.9% | 24.5% (7) | 19.3% |
| ...hands | 52% | 35% | 58% | 33% |
| ...upper arm / forearm | 17% / 20% | 15% / 20% | 18% / 22% | 12% / 19% |
| ...thigh / shin | 20% / 21% | 20% / 19% | 18% / 22% | 16% / 16% |
| ...shoulders / ribcage / pelvis | 25% / 11% / 14% | 21% / 9% / 16% | 23% / 11% / 13% | 16% / 7% / 11% |
| ...neck / foot | 34% / 33% | 37% / 28% | 27% / 33% | 39% / 24% |
| Outline, front / side | 0.879 / 0.869 | 0.875 / 0.862 | 0.878 / 0.871 | 0.888 / 0.872 |
| Landmarks | 2.31% | 2.47% | 2.26% | 2.65% |
| Elbow and knee both found by their rings | 4 of 8 | 8 of 8 | | |
| Triangles, least to most | 976 - 3,119 | 1,256 - 2,568 | 3,640 - 6,732 | 4,670 - 6,908 |

Per character, rings off, low poly before -> after (mid poly after):
troll 20.6 -> 19.2 (17.6), pirate 22.4 -> 16.2 (12.2), ninja 23.2 -> 20.3
(15.5), lizardkin 31.1 -> 27.6 (24.5), Lincoln 19.2 -> 22.8 (21.6),
Roosevelt 18.3 -> 13.5 (12.0), dancer 35.1 -> 31.0 (31.5), villager 28.5
-> 24.4 (19.4). The dancer's body alone, against her base body: landmarks
1.14% of her height off before, 0.75% after (mid poly 1.12% -> 0.61%).
build.py's own shape check on the new block-outs: 1.1% to 3.2% typical,
2.7% to 5.7% worst (a block-out is asked for 2.5% and 8%).

What that says, plainly: the body's own shape is closer, most in the
hands, the limbs and the shoulders, and mid poly now gains from its
triangles where before it only got rounder. The outline and the
landmarks are no better, and on Lincoln they are worse. Reasons:

- **Clothes count as body.** Read off a dressed mesh, the trunk follows
  the cloth: Lincoln's baggy seat becomes a wide pelvis over thin legs,
  which is what the mesh shows and not what a body is. A base body cures
  it (the dancer's hips and legs are her own); `"follow"` under 1 and
  `"girth"` soften it. This is the largest weakness.
- **Old gear on a new body.** The kept gear was built around the old body.
  drape.py lays it on the new one and it comes out a little fuller
  (Roosevelt's singlet stands off his belly; side outlines dropped 0.01).
  Gear Claude builds around the new body in the first place won't.
- **Half the landmarks are guesses on a dressed character.** Elbow, knee
  and often the waist come from "usual proportion". The landmark numbers
  above compare one reading with another, so two guesses that agree look
  good and a real elbow that disagrees with a guess looks bad. Treat that
  row as a smoke alarm, not a score.
- **Necks.** The neck stops inside the head at the narrowest ring; on a
  bearded or hooded head (the pirate, the ninja) that is the beard or the
  hood, and it comes out thick. Necks are the worst region now.
- **Hands and feet are better, not good.** A hand is one mass and a thumb
  block set where thumbs usually are, not where this one is; splayed
  fingers (Lincoln, the lizardkin's claws) make a wide fan. A foot inside
  a shoe is drawn in 2% of the height and its hidden faces are left out,
  so with shoes off it is a small foot.
- **What isn't body is still yours to build.** The troll's back crust, a
  tail, spines, a kilt: the body piece knows nothing of them. A tail
  between the legs or a skirt of armor (the lizardkin) hides the crotch,
  which is then placed by proportion.
- **The "head" style knob only moves points.** The head's texture is still
  baked from the detailed mesh at its real size, so a head grown past
  about 1.15 bakes with gaps.
- **Not tried in the live Blender.** All of this ran in a background
  Blender through `auto_body.py`. The prompt (`CHARACTER_STEPS` in
  `baml_src/4_polish/lowpoly_prompt.baml`) now tells Claude to run
  landmarks.py and paste the body, with a six-point anatomy checklist; no
  run has been made with it yet. Run `just forge-addon` and restart
  Blender first, or the prompt falls back to pasting whole scripts.

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
  glTF extras with `gear`, `kind` and `slot`. After drape.py the body is
  more than one mesh: `body`, and a `body under: <gear>` for the skin each
  piece hides (see "Clothes that sit on the body and move with it"). `"only_this_object"` now
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
  whatever the detailed mesh shows at that spot). So bake.py bakes a
  dressed block-out by group: skin that gear covers copies nothing and
  gets the body's own average skin color, in the same texture (see
  "Clothes get their own colors").
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
  piece; the ankle sits over the foot piece, and the toe bone is moved the
  little it takes to stay inside a thin or pointed toe (the dancer's heeled
  shoe, 0.9 cm sideways); a long piece running out
  behind the hips is a tail and gets 2 to 5 bones. `found_by` in the result
  says which rule placed each.
- **Every joint sits in the middle of its limb.** Each is put at the middle
  of the limb piece's own cross-section there (the arm itself, not the box
  around the arm and the hand, which a thumb pulls off-center). An elbow or
  knee may leave the straight line from shoulder to wrist or hip to ankle
  only front to back, the way it folds, and only a little (3 to 4% of the
  arm, 2.5% of the leg: further, and tights came off the knee), so the two bones still share one hinge axis and it is a
  true one-way hinge. `built_bent_deg` says how far each is folded as the
  character stands; a hinge can't open past how it was built, so an elbow
  goes back by 3% of the arm at most (under 7 degrees of fold, less than
  the easiest walk asks of an elbow). A knee is never placed outside
  the middle of the leg's length (44-56%): the troll's knee rings are lower
  than that, and a leg that lopsided can't take a stride.
- **The neck starts at the collar; the head turns inside the skull.** The
  neck's base is just above the line of the shoulders (2% of the height),
  and the head's pivot is a third of the way from chin to crown, level with
  the ears. Both stand on the neck piece's own center line, front to back.
  Before, the neck started 64 to 127% of the way from the shoulders to the
  chin (under the jaw, or in it) and was 5% of the height long, so a nod
  folded the throat in two. Now it starts 32 to 45% of the way up on most
  characters and is 8 to 9% long. A neck is never longer than 9% of the
  height, so on a character with low shoulders (the ninja) it still starts
  higher (71 to 90%); a head sunk between the shoulders (the troll) gets a
  short neck under the head.
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
- **A capsule for each bone.** Every bone with body around it carries
  `capsule_m` [radius, length]: a rod from the bone's head along it, as
  thick as four fifths of the body's points around it. It rides in the .glb
  as the bone's extras next to `limit_deg`, for a physics engine to build a
  ragdoll from. Nothing here simulates one.
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
   own rest pose. The arm bones are turned from where a true T-pose would
   have them (straight out to the sides), so they point where the motion's
   arms point even on a character built with its arms sloping or bowed. The
   spine, neck and head are turned from the character's own rest, so it
   keeps its own carriage.
2. **Plant the feet**: each leg is solved exactly from hip joint to foot
   (two bones and a hinge), so a planted foot's ball stays where it was put
   and moves back at exactly walking speed. If a planted foot is out of
   reach, the hips come down for the whole loop. The knee points where the
   motion's own knee pointed when the motion says (`"knees"`, which
   `soma_to_plain.py` writes); otherwise where the hips face, part of the
   way to the foot. If the hip can't turn that far, the knee comes round by
   the least that it can. If an ankle hits its limit the heel lifts by the
   least that brings it back inside, found by halving, and starts to lift
   four frames before it must.
3. **Contact**: the real shoes, feet and shins are kept out of the floor
   (see "Contact" below).
4. **Limits**: every turn is clamped to the bone's `limit_deg`; `clamped`
   lists what needed it.
5. **Bake** one key a frame into an action named for the motion, then play
   it back and measure it (`check`). Besides the feet, the floor, the limits
   and the seam, `check` says how far the trunk ended up from what the
   motion wrote (`off_the_motion`: each bone's turn in degrees and the hips'
   place in cm; all zero on a walk or a run), and the most a knee's hinge
   turns about its thigh in one frame (`knee_axis_swing_deg`).

**What the squirming was.** Measured as shake: the part of a point's
acceleration that changes from frame to frame, in mm per frame squared
(`scripts/rig_check.py`). The trunk, head and arms shook exactly as much as
the motion did; the legs shook two to seven times as much. Three causes:

| What | Where | Before | Now |
|---|---|---|---|
| A foot pointing nearly straight down has no "which way it faces", and reading one anyway spun it half a turn in three frames; the knee was aimed by it and went out sideways | every run, the hero shot | a knee's hinge swung 21 to 57 degrees in a frame (120 in the shot); the ninja's knee shook 86 against the motion's 18 | 5 to 7 degrees (13 in the shot); 20 against 18 |
| At an ankle's limit the heel was found by solving round and round from the clamped foot, which could land far from the last frame's answer | the troll's walk and run, deep stances | the troll's knee shook 3.9 times what its foot did (walk) | 2.3 times |
| The hips' rise out of the floor and their shift toward a pinned hand were worked out a frame at a time | the shots | the ninja's head shook 9.2 against the motion's 3.9 | 4.1 |

A fourth, found on the way: the upper arm and forearm were each rolled to
the nearest "up", so on an arm that slopes they did not share a hinge axis,
and the forearm was clamped by a fraction of a degree on every frame of
every run. They now share the elbow's own axis.

So the walk is one source of motion among others. A clip from a motion
model on NVIDIA's SOMA skeleton is the second. Two models write it, both on
the same 30 joints and in the same file format: MotionBricks (the movement
between our own poses) and Kimodo (movement from a sentence). A shot can use
both, a beat from each, joined by `scripts/motion/timeline.py`; by the time
it gets here it is one motion like any other, and a second cut of a shot is
cast under a name of its own (`just cast <shot> <run> <prop run> hero-mixed`).
`scripts/motion/soma_to_plain.py` renames it with `bones.json`,
turns it into the same plain form, and `scripts/motion/apply_shot.py` sends
it through the same steps (`just cast <shot> <run> [prop run]`; README,
"Shots"). A character's run is a third: one sentence, made by Kimodo, cut
into a loop (see "Running" below). It looks joints up by name, so a skeleton with more joints than
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
| Planted foot slides, a step | 0.04 cm | 0.00 | 0.01 | 0.01 |
| Through the floor | 0.02 cm | 0.02 | 0.02 | 0.02 |
| Turns outside a limit | 0 | 0 | 0 | 0 |

The troll is slow, wide and rolling because its build is (bulk four times
the ninja's, thighs 0.4 m thick, arms longer than its legs); the ninja is
narrow, low and quiet mostly because of what Opus said about it. The
lizardkin's tail has five bones.

**Measuring the fit: `just rig-check <file.glb>...`** (`scripts/rig_check.py`)
reads a walking or running file and says, with no reference to how it was
made: how far each joint sits from the middle of the body's cross-section
there (0 is dead center, 100 is on the skin); where the neck starts between
the shoulders and the chin, and where the head turns between chin and crown;
how much volume each part of the body keeps over the clip against standing
in the T-pose; and how much each part shakes. `just walk-strip <file> <out>
front --bones --rest` draws the skeleton inside a see-through body, a bead on
every joint.

What is weak, most visible first:

- **Bending is by nearest bone, and it squeezes the trunk.** No twist
  bones, no corrective shapes: an elbow or knee folds like a paper tube.
  Measured as volume against standing in the T-pose, a torso loses 5 to 10%
  of itself over a walk and 12 to 16% over a run (the dancer 16%, Lincoln
  12%), a thigh piece up to 30% at the hip on the low-poly Lincoln, the
  pirate's boot tops 45%. Most of the trunk's loss is its bottom ring going
  half with each thigh and its shoulders coming down with the arms. Holding
  the trunk's points to the trunk's own bones above the hip joints and
  inside the shoulders was tried: it kept the dancer's loss to 7% and
  Lincoln's to 8%, and the thighs and upper arms then came through the
  clothes over them (5.8 cm of skin through Lincoln's shirt, 3.1 cm through
  the ninja's suit at the groin), because clothes take the weights of the
  body under them. Letting the crease and the shoulder cap fold with the
  limb again cured the clothes and gave the volume back. So it is as it
  was; the cure is weights that blend over a ring's width at the hip and
  shoulder with the clothes weighted to match, or a second "twist" bone
  there. (Skin through clothes on a stride, and kilts that followed the
  thighs in facets, were the top of this list: see "Clothes that sit on the
  body and move with it".)
- **A knee still shakes more than its foot in a walk** (1.4 to 1.6 times,
  the troll 2.3; it was 1.5 to 1.9, the troll 3.9): a leg near straight turns a small move of the foot into a
  large one of the knee, and the walk's feet leave and land with a corner in
  their path. In the runs it is level (0.8 to 1.0).
- **The troll's ankles run out.** Its shins are short, so in late stance
  the ankle hits its limit and the heel comes up as much as 42 degrees;
  it now comes up smoothly (0.02 cm of slide).
- **The troll's head is not found.** With no block-out to name it, its head
  is "the top of the trunk", and its neck and head pivot sit behind the
  face it really has: 51% off the middle of the cut there.
- **Joint finding is rules of thumb.** It expects a T-pose facing -y, two
  legs, arms held out, and pieces built along the axes. A head is "the
  lowest sizeable piece above the arms"; a cape that hangs behind the hips
  could be taken for a tail.
- **One gait.** No start, stop or turn (a run is a clip of its own: see
  "Running"), no uneven ground, and the walk
  stays in place (the speed is in `<version>-walk.json` for whoever moves
  the character).
- **Hands and face don't move**: one bone per hand, none in the face.

## Running: a loop cut from a sentence

The walk is worked out from the build. The run is asked for in words and
then treated like any other motion from outside: the `run` profile writes
`lowpoly-run.glb` / `midpoly-run.glb` (and a `.json` each) beside the walk
files, with the same skeleton, gear, sockets and limits and one looping
animation, `run`, on the spot.

    just runs                                 # every character in runs/ with a gait.json
    just run-asks                             # only show each one's sentence and speed; sends nothing
    just tidy runs/<run folder> run           # only the Blender part, once the clip is there
    just walk-strip runs/<run>/profiles/lowpoly-run.glb strip.png side

**The sentence and the speed** (`scripts/motion/run_clip.py`). Both come
from the brief and the four traits in `gait.json`. Kimodo's sentences are
about "a person", so the brief gives a word on the build (huge, stocky, tall
lanky) and the traits pick one manner of running:

| | Sentence | Speed |
|---|---|---|
| Cave troll | A huge person runs forward in a slow, heavy, lumbering run, with pounding steps and a stiff upper body. | 2.53 m/s |
| Lizardkin | A stocky person runs forward at a steady pace with heavy, solid steps. | 2.86 |
| Pirate | A stocky person runs forward with a confident swagger, shoulders rolling, with heavy steps. | 2.97 |
| Roosevelt | A stocky person runs forward proudly with a straight back and strong, firm steps, pumping the arms. | 3.26 |
| Ninja | A stocky person runs forward stealthily in a low crouch, with light, quick, quiet steps. | 3.42 |
| Lincoln | A tall lanky person runs forward with long, relaxed, loping strides, arms swinging loosely. | 3.79 |

The speed follows the leg, as the walk's does: a Froude number (speed
squared / gravity x leg length) of about 1.7 for an easy run, brought well
down by weight (measured bulk and the `weight` trait, half each) and a
little by stiffness and stealth, never under 0.55, where running turns back
into walking. The clip is made at the model's own size and scaled to the
character by its leg, so the path Kimodo is given runs at that speed times
(the model's leg / the character's leg).

**The jobs: each sentence alone, five takes.** Each sentence goes to Kimodo
as a job of its own: six seconds along a straight line at that speed, about
three seconds of GPU on a warm worker. A job can carry up to eight sentences
as one long motion (`--batch 8` on `run_clip.py`), but each stretch is then
made as a continuation of the one before, and on our six the later
characters came out with still arms and their heads thrown back where the
same sentences sent alone ran properly. So alone is the default.

The same sentence with different dice also gives different runs, some good
and some odd. So each character is made five times (five seeds; every
character has seeds of its own, or all six come back with the very same
beat), and each take is scored on what can be measured: how far apart the
two ends of its best loop are, how steadily the legs repeat, a head tilted
back past 15 degrees or hung past 30, an arm that swings less than 15 cm.
The lowest score is kept. All five scores are written in `clip.json` and
`loop.json`, and `just runs` prints them.

A character's ask (sentence, speed, length, seed, takes) has a
fingerprint; its clip (`<run>/run/clip.json`) is made again only when that
changes, and then only for that character. Requests and answers are kept
by the hash of their content in `runs/.run-cache/`, like a shot's.

**The cut.** The first 45 frames of a stretch (the model settling into the
new pace) and the last 6 are never used. In between: the stride's length
is read off the legs (how far one toe is ahead of the other, compared with
itself later); then every pair of frames a whole number of strides apart
(one to three, give or take 8%) is scored by how unlike the two are, in
where each joint is, how fast it is moving, and which feet are down. The
best pair is the cut; two strides or more are preferred unless a single
stride matches a fifth better. The last 8 frames are eased onto the frames
that led into the first, so the motion arrives at the seam already moving
the right way, and the last frame is made the first exactly. The average
travel over the ground comes out, so it runs in place; the speed is kept
(`<run>/run/loop.json`, and `run` in `<version>-run.json`).

**Onto the character.** `scripts/motion/apply_motion.py` is the one way a
motion from elsewhere gets onto a character; a shot (`apply_shot.py`) and
the run both go through it: drape, rig, cloth, animate, whatever the rig
asks for next (swing.py), export. For the run, feet are planted on the
loop played three times over the ground (so a foot down across the seam is
planted the same at both ends), the middle round is kept, and its travel
is taken out again: a planted foot then slides straight back at exactly
the run's speed, which is what animate.py holds it to. swing.py is told
that speed, and blows a wind that fast at the simulated cloth from the
front, so loose cloth trails back harder than in the walk. A tail,
which no motion model has, gets its motion here as in the walk: each bone
turns as the hips did two frames earlier, more toward the tip, and the
tail is lifted clear of the ground.

**When Kimodo can't be reached** (no endpoint, or the account behind the
worker's Hugging Face token has not been given Meta's Llama 3 yet): `just
runs` says `run skipped: Kimodo not available` with the worker's reason and
ends well; the `run` profile with no clip says the same and writes
nothing; a pipeline run logs it and carries on. Nothing is half-made.

Measured on the six characters (Kimodo-SOMA-RP-v1.2, Nov 2026; low poly,
and mid poly where there is one, came out alike):

| | Troll | Lizardkin | Pirate | Roosevelt | Ninja | Lincoln |
|---|---|---|---|---|---|---|
| Speed | 2.54 m/s | 2.83 | 2.96 | 3.26 | 3.42 | 3.80 |
| Steps a minute | 167 | 164 | 180 | 167 | 180 | 195 |
| Loop | 43 frames, 2 strides | 22, 1 | 20, 1 | 43, 2 | 20, 1 | 37, 2 |
| Take kept, of 5 (its score; the worst) | 5 (3.6; 12.0) | 3 (2.0; 4.8) | 1 (4.0; 5.6) | 1 (5.3; 13.5) | 3 (3.5; 10.1) | 5 (3.4; 9.5) |
| The two ends before easing, joints on average (worst joint) | 2.7 cm (6.6) | 1.9 (5.4) | 3.3 (7.1) | 4.4 (9.7) | 3.2 (7.1) | 2.9 (7.6) |
| Loop seam after | 0 | 0 | 0 | 0 | 0 | 0 |
| Planted foot slides, a step | 0.20 cm | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 |
| Turns outside a limit | 0 | 0 | 0 | 0 | 0 | 0 |
| Through the floor | 0.03 cm | 0.43 (tail tip) | 0.01 | 0.05 | 0.02 | 0.02 |
| Hips lowered so a planted foot reaches | 0.2 cm | 1.5 | 0.0 | 0.0 | 0.0 | 0.0 |
| Hips raised to clear the floor | 1.7 cm | 0.0 | 3.4 | 0.2 | 0.0 | 0.0 |

The ninja's loose cloth (8 bones low poly, 4 mid poly): no turn outside a
limit, 0.05 cm into a leg at the deepest, seam 0, hems travel 16.5 cm (low
poly) and 3.9 cm (mid poly). Skin through its clothes over
the run: 3.1% of covered points (low poly, 3.2 cm deepest; the walk has
1.7%, 1.6 cm) and 1.0% (mid poly). The lizardkin's tail: five bones, lifted
8 degrees, swinging 5.
In every loop the eased frames move no more sharply than the rest of the
loop does (largest joint acceleration at the seam against elsewhere: 6.6
against 8.9 cm a frame squared for the troll, and like that for the rest).

Tried without Kimodo too. `python3 scripts/motion/test_run_clip.py` (in
`just check`) tests the sentence and speed, the jobs, the cache, the takes,
the cut and the run on the spot against a pretend worker that makes a
stick-figure run. `just test-tools` runs the `run` profile for real on the
troll and the lizardkin with that stick figure, and checks that with no
clip it is skipped and nothing fails.

What is weak, most visible first:

- **A sentence steers a little; the dice steer a lot.** Roosevelt's "proudly"
  comes out as an arched back, chin up and the arms swept behind him, in
  the best of five takes. It reads as a strut more than a run. The cure is
  a different sentence for that band of traits in `run_prompt`
  (run_clip.py); `just runs` then makes only his again. The scores catch a
  thrown-back head and a still arm, not "does this look like him".
- **A foot in the air comes up short on short legs.** The troll's hips used
  to come down 10.6 cm so every foot could reach where the motion put it,
  and a heel then went 8 cm through the floor (see "Contact"). Now the hips
  come down only for a planted foot, so a swinging foot stops up to 10.8 cm
  short of its spot (the pirate's 5.8).
- **Everyone runs at about the same beat.** 164 to 195 steps a minute,
  troll and ninja alike: Kimodo runs like a person of ordinary size, and
  the clip is scaled, not re-timed. The troll's speed is right; its legs
  just turn over faster than something that heavy would.
- **A loop is one or two strides.** Seen for long, it repeats.
- **Arms.** Our elbows are one-way hinges, and the shoulders and forearms
  are held to their limits on every frame of a run; no limit is broken,
  but an arm pumps a little flatter than the model drew it.
- **Skin through cloth is about double the walk's** on the ninja's low-poly
  suit, at the hips and knees of a longer stride.
- **Several sentences in one job** (`--batch`) is built and tested but
  gave worse runs; it is kept for when cost matters more.

## Contact: feet, shins and hands stay out of the floor and the set

Every motion a character plays (the walk, a run, a shot) goes through
`animate.py`, and one step of it is about touching things. It tests the
character's real mesh, not its bones: for each leg and hand bone, the
outermost points of whatever mostly follows that bone (shoe, foot, shin,
thigh, hand), about a hundred a bone. Three things showed why:

- **The dancer's heels.** Her shoe's toe reaches 10 cm ahead of the ball of
  the foot; the toe bone is 5 cm long. Toes were let droop by what the bone
  had room for, so the shoe's tip went 0.75 cm through the floor on every
  step.
- **The troll's run.** Its hips were lowered 10.6 cm for the whole loop so
  that a foot in the air could reach where the motion put it. Crouched like
  that, its ankle ran out of bend as the foot came down, the foot tipped
  toes-up, and the heel of a 0.7 m foot went 8 cm under.
- **The ninja's shots.** The motion model can't see the set and has a
  different body: a foot dipped under the roof, a shin crossed the wall, a
  knee sank 13 cm in the landing, the vault hand was 14 cm off the wall top.

What the step does, in the order it tries things:

1. **Hips come down only for a planted foot.** A foot in the air that is
   out of reach comes up short. In a loop the hips come down by one amount
   throughout; in a shot only around the frames that need it.
2. **Toes** fall in line with the foot only as far as their real shape
   clears the floor.
3. **A planted foot whose toes still dig in** (heel up, toes bent as far as
   they go) lowers its heel, if the leg still reaches.
4. **Anything else under the floor lifts the foot straight up**: a heel
   coming down first, a foot in the air. Never sideways, so a planted foot
   does not slide.
5. **A leg inside a block of the set** (a shot's wall) is moved out the
   short way: over the top, or back out the face the hips are on when that
   is more than 2.5 times nearer.
6. **What no place for the foot can cure, the hips cure by rising**: a knee
   in the floor in a deep crouch, a leg folded as far as it goes and still
   under the top of a wall it is passing over. At most 0.3 of the hip
   height.
7. **A hand with a spot** (a shot's plan pins it: the wall top, the roof)
   is put there by solving the arm, and laid flat. The hips move over by up
   to a twentieth of the hip height if the arm is a little short. Past what
   the arm and shoulder can do the hand goes as far as it can; a spot on the
   floor that is out of reach is moved in toward the shoulder. Any hand
   under the floor is lifted out; a hand held on a wall top is lifted at
   most 3% of the hip height, so it stays on its spot.

Each correction comes on and goes off over a few frames (three; eight where
there is a wall to get over; twelve for the hips), wraps around a loop's
seam, and the leg is solved again with it, so joint limits still hold and
the last frame still equals the first. A shot's wall and hand spots ride
along in the motion itself (`"set"`, `"hands"`; `apply_shot.py` writes them
from the shot's plan). `"contact": False` plays a motion as it was written
(`--no-contact` on `apply_shot.py`), which is how the "before" columns below
were measured where the old files did not hold the number.

`contact` in the result says what was done (feet lifted, heels lowered, legs
moved clear, hips raised, hands lifted), and `check` measures the outcome on
the played-back mesh: `through_floor_cm` and `lowest_part` (which bone's
part), `in_the_set` (deepest, and by part), `hand_from_its_spot_cm`,
`planted_foot_strays_cm` (the furthest a planted foot gets from where it
landed, over the ground).

Measured, before and after (low poly; mid poly within 0.05 cm on the walks
and runs):

| Through the floor, cm | Troll | Ninja | Pirate | Lizardkin | Lincoln | Roosevelt | Dancer |
|---|---|---|---|---|---|---|---|
| Walk, before | 0.06 | 0.22 | 0.01 | 0.00 | 0.00 | 0.16 | 0.75 |
| Walk, after | 0.02 | 0.02 | 0.02 | 0.02 | 0.02 | 0.02 | 0.02 |
| Run, before | 8.00 | 0.23 | 4.70 | 2.87 | 0.01 | 0.48 | 1.68 |
| Run, after | 0.03 | 0.02 | 0.01 | 0.43 (tail tip; feet 0.02) | 0.02 | 0.05 | 0.02 |
| Run: hips lowered, before | 10.6 | 0.2 | 2.7 | 3.9 | 0.6 | 2.2 | 0.0 |
| Run: hips lowered, after (raised) | 0.2 (1.7) | 0.0 | 0.0 (3.4) | 1.5 | 0.0 | 0.0 (0.2) | 0.0 |

Planted feet slide 0.2 cm a step in the troll's run and 0.04 in its walk,
0.01 or less everywhere else. No turn is outside a limit and every loop's
seam is 0. The 0.02 is the step's own tolerance.

The ninja's two cuts of the rooftop shot (low poly; mid poly alike):

| | Our poses, before | after | Mixed (text and poses), before | after |
|---|---|---|---|---|
| Through the roof | 12.9 cm (knee, landing) | 0.03 | 12.8 (knee, landing) | 0.20 |
| Legs in the wall | 6.0 cm | 2.9 (a foot, 1 frame; mid poly 0.6) | right through (15, half its thickness) | 7.5 |
| Vault hand from its spot | 13.9 cm | 2.8 | 15.4 | 25.4 |
| A planted foot strays | 2.3 cm | 0.00 | 1.2 | 1.2 |
| Turns outside a limit | 0 | 0 | 0 | 0 |
| Hips raised | | 19 cm (landing) | | 28 (vault and landing) |

(The files made before this step said 15.8 and 24.3 cm of foot slide. Most
of that was one bug in `soma_to_plain.py`: easing a foot toward its next
planted spot also moved the last frames it was held on the spot before.)

What is weak, most visible first:

- **The mixed cut's vault is a run through the wall, and no leg fix makes
  it a vault.** Kimodo plants a foot 12 cm from the wall and carries the
  hips over at 15 to 35 cm above the top. To get the legs over, the hips
  are raised 28 cm (the most allowed) and the feet lifted up to 75 cm.
  Shins still cut 7.5 cm into the wall for six frames, and with the body
  that high the hand cannot reach down to the top: it ends 25 cm from its
  spot, further than before. The cure is a different sentence or a pose
  key for that beat, which means making the motion again.
- **The three-point landing is a two-point landing.** The ninja's legs are
  thicker than the motion model's, so to keep its knee out of the roof the
  hips rise 19 cm, and then its arm (0.72 m) cannot reach the roof: the
  hand hangs 17 to 25 cm above it. Before, the hand was 16 cm off and the
  knee 13 cm into the roof. A fix would treat the knee as something that
  rests on the floor, or plant the back foot further out for this body.
- **Over or back is decided point by point.** A foot that goes into a tall
  wall low down is stopped at the face, then goes over the top once that is
  the nearer way. Fine for a wall crossed near its top; a crossing should be
  decided once.
- **A foot in the air comes up short** where the hips are no longer lowered
  for it: by up to 10.8 cm in the troll's run, 5.8 in the pirate's.
- **A held hand ends its hold badly.** In the vault the body is past the
  hand before the plan lets go; in the last two frames the wrist runs out
  of bend and the fingers go up to 6 cm into the wall top.
- **Points that follow two bones are tested as if they followed one.** It
  costs under 0.2 cm.
- **Tails, hips, elbows and heads are not tested.** The lizardkin's tail tip
  still dips 0.4 cm in its run.

## Sets: a place of our own, built once and shot many times

A shot used to carry its own scenery: the roof, the ledge and the wall were
written inside each hero shot's plan. A **set** takes that out of the shot
and keeps it, the way a TV studio keeps its talk-show stage standing all
season. It lives in `sets/<name>/`:

| File | What it is |
|---|---|
| `set.json` | the floor, what is in the way, marks, paths, cameras, lights, backdrop, slots and dressing |
| `set.glb` | the set to look at. A block-out is enough |
| `backdrop.png`, `backdrop.txt` | the painted picture behind the set, and the words Codex painted it from |
| `build.json` | only for a set built from data: the pieces that are just looked at, and the dressing |
| `dressing/<prop>.glb` | each piece of dressing, standing at 0, 0, 0 |
| `card.png` | one picture of the empty set, for the gallery |

All of it is committed. A set is small (the studio is 25 kB of mesh and one
0.8 MB picture) and a shot cannot be planned, checked or filmed without it,
so it belongs with the code, not in `runs/`. The full-size picture Codex
paints (`backdrop-full.png`) is the one thing left out.

Everything is in metres in the shot's own axes: y up, the ground is x and z,
a heading of 0 faces +z and grows toward +x. A stage faces +z: that is where
its cameras are.

### What set.json holds

```json
"frame": { "origin": [0.0, 0.0, 0.0], "front_deg": 0.0 },
"footprint": { "outline": [[-7.5, -1.5], [6.5, -1.5], [6.5, 10.8], [-7.5, 10.8]] },
"blocks": [{ "name": "desk", "kind": "desk", "center": [2.2, 0.375, 2.1], "size": [1.6, 0.75, 0.7], "heading": 0.0 }],
"marks": {
  "wings":      { "kind": "stand", "at": [-4.7, 2.75], "facing_deg": 90.0, "offstage": true },
  "couch_1":    { "kind": "sit", "at": [0.27, 0.95], "stand_at": [0.27, 1.4], "facing_deg": 10.0,
                  "seat_height_m": 0.46, "seat": "couch seat", "beside": ["couch back", "couch arm right"] },
  "meet_left":  { "kind": "touch", "at": [-0.78, 2.75], "facing_deg": 90.0,
                  "touch": { "hand": "right", "at": [-0.4, 1.05, 2.75] } }
},
"paths": [{ "from": "desk_chair", "to": "meet_right", "via": [[1.1, 1.52], [0.72, 2.3]] }],
"cameras": { "host": { "at": [0.6, 1.35, 8.5], "aim": [2.1, 1.05, 1.2], "lens_mm": 85, "sees": ["desk_chair"] } },
"lights": [{ "name": "key", "kind": "area", "at": [-3.0, 4.6, 7.0], "aim": [0.0, 1.0, 1.6], "power": 320.0 }],
"backdrop": { "image": "backdrop.png", "center": [0.3, 2.3, -1.2], "width_m": 9.0, "height_m": 6.0 },
"slots": { "desk_right": { "at": [2.72, 0.75, 2.05], "heading": -15.0 } },
"dressing": [{ "prop": "mug", "slot": "desk_right", "glb": "dressing/mug.glb" }]
```

- **A set is written in its own frame.** `frame` gives its origin and which
  way its front faces; marks, cameras, blocks, lights and the backdrop are
  all measured from that origin, and `set.glb` is built around it
  (`geometry.move` is 0; `standing.py adopt` bakes a move into a .glb that
  came from a run). `footprint` is the ground it takes up, cameras and all.
  A set.json never says where the set is. A world file can, later: one line
  per set, `{"at": [x, z], "facing_deg": 90}`, and `standing.placed(set, at,
  facing_deg)` turns any point or heading of the set into the world's. A
  shot is planned and filmed in the set's frame, so moving a set changes no
  shot. The ring's footprint has `"open_toward_deg": 90`: its +x side ends
  close to the ropes and is kept clear, for the hall to grow on.
- **Blocks** are written the way a shot's `plan.json` has always carried its
  `set` (name, kind, center, size as across, tall, through, heading), which
  is what `apply_shot.py` hands to `animate.py`'s contact step. So a set's
  blocks reach the contact step with no new code there. Remember what that
  step assumes: **a block is solid from the floor up to its top.** A desk is
  a box, not a table top; keep a seated person's feet out of its footprint.
  `"see_through": true` (ropes) stops a body but not a camera.
- **The floor is y = 0**, always. The ring's floor is its mat, so its
  geometry was moved down by the mat's height when it was taken from the
  run, and `"ground": {"y": -1.36}` says where the hall floor is.
- **A seat mark** names the block sat on and has two spots: `at`, where the
  hips are when seated, and `stand_at`, in front of it. Its own seat and
  whatever is `beside` it (a chair's back, a couch's arm) do not count as in
  its way.
- **Two touch marks that share one hand's spot** are a handshake.

### `just set-check`

`python3 scripts/sets/standing.py check <set>` says what is wrong, in words.
It checks that every mark stands on the floor with 22 cm of room for a body;
that a seat is within 6 cm of the height our `sit` pose is written for (0.46
m), is as high as the block it names, and has its standing spot 25 to 70 cm
in front; that a hand's spot is within an arm's reach and not inside a
block; that two marks sharing a spot face each other 0.7 to 1.05 m apart;
that every path stays on the floor and clear of blocks along the curve
people will really walk; that each camera holds the head, chest and feet of
every mark it says it `sees`, with no block between; that on a stage
(`"stage": "shallow"`) the floor is at most 5 m deep, every camera is out
front and every mark is seen by one; that the backdrop is behind everyone
and fills each camera's view (or a wall does); that dressing stands on slots
that exist; that every block is inside the set's geometry; and that the set
has a frame and a footprint that holds its marks, blocks, floor and cameras,
with its geometry built around its origin.

### Blocking: a shot list names marks

`ShotList` has `start_mark`; a beat has `from`, `to` and `at`; a text beat's
key can say `"where": "start"` or `"end"`. `plan_shot.py` hands a shot list
that names marks to `standing.stage_marks`, which fills in what the rest of
the shot path already reads:

| The shot list says | The set supplies |
|---|---|
| `"to": "meet_left"` on a text beat | the path's ground points (through the set's turning points), `from_m`, `to_m` |
| `"at": "couch_1"` on a poses beat | each move's `at_m` and `facing_deg`: a seated pose over the seat, any other on `stand_at` |
| a key `"where": "end"` | its time, place and the mark's facing, so the walk ends standing the right way round |
| a move that pins `right_hand` at a touch mark | the wrist's spot, written over the pose's own in `plan.json` |
| a seated pose | which block is sat on and over which frames (`plan.json`'s `stage.seats`) |

Then `standing.into_plan` puts the set's blocks into `plan.json` as `set`,
so the cast's contact step gets them. A shot list that names no mark is
passed through untouched, which is how the rooftop shots still plan to the
requests they always did (`python3 scripts/sets/test_sets.py` proves it
against the hashes from before).

Sitting is ours: `stand`, `sit`, `sit_talk`, `shake` and `shake_dip` are in
`author_poses.py` with the rest (`"seated": true` marks the two that sit),
and MotionBricks moves between them. Walking between marks is a Kimodo
sentence held to the set's path, ending in our `stand` pose.

### Segments and takes

`motion/segments/<name>.json` is a routine written once: a shot list per
role, in marks, with `{sentence}` slots for the walks and a `together` list
of beats everyone must reach on the same frame. `scripts/motion/segment.py`
turns a take (`motion/shots/<take>.json`: set, segment, who plays whom) into
`shots/<take>/<role>/shotlist.json` and refuses a template whose roles are
different lengths or whose `together` beats fall out of step. From there
each role is an ordinary shot in its own folder: `plan_shot.py`,
`timeline.py`, `checks.py`, `apply_shot.py` all run on it unchanged.

### Filming: every camera at once

`scripts/motion/render_take.py` stands the set up (`set_contact.stand_up`:
geometry, ground, backdrop, dressing, lights, cameras), brings every role
on, and renders one `.mp4` and one strip per camera. Each character's file
plays the motion at its own size, so each is divided by its
`size_against_soma` there: everyone is brought to the motion model's hip
height, and so onto the same marks, seats and hand spot. The gallery's set
page does the same.

With everyone on the stage it measures what no single character's file can
(`cast-<clip>.json`): how far apart two right palms and wrists are over a
handshake, and how far the lowest point of a seated body is from its seat's
top.

### What the first take measured

`studio-guest-entrance`: Roosevelt walks on, Lincoln gets up from the desk,
they shake hands at centre, both sit. 475 frames, cast on the low-poly
characters with their gear (mid-poly files are made too).

| | Lincoln (host) | Roosevelt (guest) |
|---|---|---|
| size against the motion's body | 1.08 | 0.89 |
| a planted foot strays, at most | 0.003 cm | 0.3 cm |
| foot slide in one step | 0.006 cm | 0.63 cm |
| through the floor | 0.02 cm | 0.28 cm |
| deepest in the set | 0.08 cm (a toe) | 0 |
| turns outside a joint limit | 0 | 0 |
| wrist from its spot in the handshake | 0.0 cm | 7.4 cm (his arm is too short) |
| lowest point over the seat, against its top | 0.7 to 0.9 cm above | 3.2 cm above |
| hips raised to clear the seat, at most | 12.2 cm | 15.9 cm |

Between them, over the 69 frames the hands are held: palms 12.6 cm apart
typically (12.1 to 13.7), wrists 17.3 cm (15.0 to 21.7; planned 14.0). On
the box figures, before casting: every beat ends within 1 cm of its mark
(2.5 cm for one walk), the hips are over the seat within 0.7 cm, wrists 14.6
cm apart. The motion took 34 jobs, 92 seconds of worker time on an RTX 4090.

Two things were learned on the way, and are now how the studio is written.
The first take had the seat blocks as deep as the cushions; Roosevelt's
calves were inside the couch's front, and the contact step lifted his feet
41 cm to get them out. A seat's block now stops 13 cm short of the cushion's
front edge (the rest is only drawn). And the two handshake marks were 76 cm
apart, more than his arms could cover; they are 66 cm apart now.

### The world: every set stands in one place

Nothing is filmed outside the world. `world.json` puts every set down on one
ground at true size, and the gallery shows it whole (README, "World").

- **Where a set stands is never in its set.json.** `world.json` has one line
  per place: `{"set": "grass", "at": [0, 13], "facing_deg": 0}`.
  `standing.placed(set, at, facing_deg)` is all the arithmetic. A shot is
  still planned and filmed in the set's own frame, so moving a place never
  changes a shot made on it.
- **A place can stand inside another.** The ring is `"inside":
  "boxing-house"`, lifted 1.36 m: its own set and page, drawn in the hall as
  a piece of dressing (a light copy far off, the full mesh up close).
- **`just world-check`** after any change to a set that is in the world, or
  to `world.json`: every place passes `set-check`, no two footprints
  overlap, every toon stands on a mark that exists, and the newest epoch is
  the world as it is now. If the world really has changed, save a new epoch
  (`just world-epoch epoch-1 "Title" "Caption"`); don't edit an old one.
- **New in set.json, all optional.** `signs` (small painted flats:
  `{name, image, center, width_m, height_m, heading}`); `detail` on a piece
  of dressing (a heavier file of the same thing, shown up close) and
  `small` (too small to see from far off: loaded up close); `"build":
  false` on a block that only keeps people out of a piece of dressing;
  `floor_y` on a mark that is on a platform; `backdrop_options` (other
  pictures that can hang where the backdrop is) and `groups` (marks used
  together: the stage's `portrait` row).
- **A place built from data** is written by `scripts/world/places.py`
  (edit the place there, not its set.json), then `just world-places
  <place>`. A house is written by `scripts/world/build_house.py` from its
  `design.json`: change the builder or ask for a new design (`just
  buy-house <toon>`), don't edit its set.json by hand. The tests rebuild
  both and compare.
- **A backdrop is a real place.** The studio is the ninja's photo stage.
  What hangs behind its window comes from `backdrop_options`: a picture of
  a place in the world through that place's own camera (`just
  studio-backdrops` retakes them after a place changes). To put another
  place behind a sitter, set `backdrop.image` and `backdrop.place` to one
  of the options.
- **Toons in the world are still.** `just world-toons` freezes each
  low-poly character in the pose `world.json` names (from
  `motion/comic_poses.json`) and writes it with no skeleton. Their pieces
  are kept apart on purpose: joining them loses the colors painted on all
  but one.
- **Keep the first view light.** `python3 scripts/world/test_world.py`
  fails if the overview passes 30 files, 2.5 MB or 30,000 triangles, or if
  anything in it is Draco-packed (`just world-stock` unpacks the copies).
  Anything small or heavy goes behind `small` or `detail`.

### Dioramas: a moment on a base

A diorama is one moment of the story, built from the real files (web
versions, or mid and low poly) and stood on a wooden base: the toys on the basement shelf,
where the portraits and comics are the world as the toons imagine it
(README, "Dioramas"). The newest one opens the gallery's front page.

    just diorama-check <name>                 # the plan, with no Blender
    just diorama-draft <name> [camera,camera] # quick pictures and the measurements; writes only draft/
    just diorama <name>                       # the real build: diorama.glb, stills/, card.png, build.json

- **`dioramas/<name>/diorama.json` is the whole plan.** The set and the
  slice of it to keep, each toon (run, version, pose, mark or spot, what it
  faces and looks at, what it holds, what stands beside it), free props,
  lights, cameras, and the base. `scripts/diorama/diorama.py` says what
  every key means and checks a plan; `build_diorama.py` builds it.
- **Everything is in the set's own axes**, like a shot: metres, y up, z
  toward the front, a heading of 0 facing the front. Use the set's marks
  (the studio's `photographer`, `sitter`, `group_1`..`group_3`) and add
  spots with `at` when a group needs more room.
- **Posing reuses the comics' way.** `scripts/comic/stage.py` brings a
  rigged `<version>-walk.glb` in, strikes a pose (turns of our plain bones
  from the T-pose, as in `motion/comic_poses.json`) or freezes a clip at a
  moment, and stands it on its spot. A pose only this moment needs goes in
  the diorama's own `poses`, not in the comic library. For a right arm,
  write the left side's numbers: `_r` is mirrored for you.
- **Props follow hands, not the other way round.** There is no reaching:
  pose the arm, and the prop is put at the palm (`holds`), the tripod is
  built to stand `under` the camera. To move a prop, move the arm.
- **Read what the build measures** before looking at the picture: pairs in
  each other (triangles that cross), feet off the floor, hand to prop, a
  held prop touching its holder away from the hand, anything over the edge
  of the base, and how much of each head shows from the first camera. A
  build with any of these wrong says so and exits 1.
- **A toon's `version` can be `web`**: the detailed mesh, which has no
  skeleton. `build_diorama.py` binds it to the skeleton of the toon's
  mid-poly file (or low-poly, if that is all there is) before posing:
  nearest-surface weights from the rigged mesh, points in one place welded
  (a web mesh is thousands of patches that only touch), eight rounds of
  smoothing, four bones a point. Read the `bind` lines: worst edge, one in
  a thousand, share over twice. Past 5x, or over 1% past twice, the toon is
  built from its rigged version instead and the build says which. Slivers
  under 2 mm are left out of the figures. To see a bind you doubt, put a
  camera behind the cast (`at`/`aim`) and `just diorama-draft`.
- **Keep it light.** One `.glb`, no skeletons, Draco, WebP, `paint_px`
  1024 for web toons, color only unless `"maps": "all"`, under 6 MB and
  320,000 triangles (`diorama.BUDGET`); the stills are taken before the
  pictures are made small; `python3 scripts/diorama/test_diorama.py` holds the
  kept ones to it. Unlike the world's first view, a diorama is
  Draco-packed, so the page fetches the decoder (about 60 kB) once.
- **A new diorama** gets the next `number`; the highest is the front page
  and the rest go to "Earlier moments". Don't edit a shown diorama into a
  different moment: make a new one, the way epochs are saved.

What is weak: mitten hands and no grip, poses tuned by eye, prop sizes
chosen by hand, one shelf and one wall for a basement, and nothing checks
a pose for an elbow bent the wrong way (`just poses` does that only for
the motion library).

### Adding a set

1. Write `sets/<name>/set.json`. Start from the studio's.
2. Geometry: `just set-build <name>` (boxes from the blocks, plus
   `build.json`), or `just set-from-run <name> runs/<an object> game <x> <y>
   <z>` to use something already made, moved onto the set's origin, or `python3 scripts/sets/standing.py blocks-glb
   <name>` for plain boxes.
3. `just set-backdrop <name>` paints `backdrop.png` from `backdrop.txt`.
4. `just set-check <name>` until it says sound, then `just set-card <name>`.

### What is weak

- **One hip height for everyone.** It is what puts two characters on the
  same marks, and it makes a short-legged character bigger than a
  long-legged one. The cure is to play each at its true size and stretch
  only the travel over the ground, which means changing what
  `soma_to_plain.py` hands `animate.py`; not done.
- **The handshake is two wrists near a spot.** The hands lie flat, palm
  down (that is `animate.py`'s rule for a hand resting on something), there
  is no grip and no pumping, and an arm too short for the spot stops short.
- **A seat only pushes up.** The contact step keeps a body out of the seat's
  block and raises the hips to do it; nothing presses a floating body down
  onto the seat, and a chair's back is not felt at all.
- **The floor is flat.** The ring's steps are a mark at the mat's height,
  and the front ropes have a gap for coming in.
- **People are kept out of the set, not out of each other.**
- **Joins around a turn are rough**: leaving the handshake, the body's speed
  jumps about ten times what is usual for the shot.
- **Fixed cameras only, and no cut.** Three films come out; nothing picks
  between them.
- **Choreograph has only been tried offline with marks** (its prompt and a
  parsed reply). The one take so far came from the segment template.
- **Paths are declared, not found.** A walk between two marks with no path
  in `set.json` is a straight line, and `set-check` only tests the declared
  ones.
- **Filming is slow**: about four minutes a camera for 16 seconds.

## Clothes that sit on the body and move with it

A block-out's gear is tubes and boxes built roughly around the body. Left
like that, trousers are a stiff pipe with a leg loose inside: a gap at
every cuff, a bare thigh through the cloth on every stride (the body and
the gear had their rings at different heights, so they bent differently),
and a kilt that follows the hips like a bucket. Three scripts fix it, in
this order around the rig:

    drape.py     after the last build.py, before export.py; again on any opened .glb
    rig.py
    cloth.py     after rig.py
    walk.py / any motion, then animate.py
    swing.py     after animate.py (animate.py's result says so: "then")

The runner does all of it: `lowpoly` and `midpoly` drape before they bake,
`walk` and `just cast` drape (a version already draped is only read), rig,
dress and swing. In step 4c Claude runs drape.py itself, last thing before
the export.

**`drape.py`: lay each piece on the body.** Every piece of gear is taken
for one of three things; `"pieces"` in the result says which, and why.

- **Tight** (trousers, sleeves, a shirt, wraps, a mask): every point goes
  to the nearest spot on the body, one step off it (`"clearance"`, half a
  percent of the height: about a centimeter on a person). A piece worn over
  another sits a step further out for each layer under it. A point sunk
  deep in the body is left: that is where two pieces were built into each
  other (a trouser leg's top inside the hips). Then, where a corner or an
  edge of the body would still stand out through a flat face of cloth (a
  six-sided leg in an eight-sided wrap), that face is lifted over it.
- **Loose** (a kilt, a skirt, a coat's skirts, a hood, a cape): fitted like
  tight cloth only where it rests on the body. That is down to the belt or
  sash worn around it, if there is one; otherwise down to where the body
  starts to fall away under it (cloth hangs from the widest thing above
  it). Below that line it keeps the hang it was built with, comes along
  with the edge it hangs from, and is pushed out only as far as cloth would
  fall: straight down from the widest part of the body above, never in
  toward the legs.
- **Stiff** (boots, a hat, a buckle, plates, glasses): left as built. A
  small one is carried along with the cloth it sits on. A belt or band (a
  ring with an inside and an outside) has its inside set on what it goes
  around and keeps its thickness.

What a piece is comes from, in order: `"fit"` in drape.py's own PARAMS; the
piece's `"fit"` in build.py (what the block-out prompt now asks Claude to
say); what the file says it was last time; then the piece itself: attached
gear, footwear and small things are stiff, a ring is a band, a name like
kilt, coat or hood is loose, a wide piece whose lower edge stands well off
the body is loose, the rest is tight.

It also cuts a few edge loops, changing no shape (`"rings"`, at most 12%
more triangles): a tight piece gets one where the body under it has a ring
and it has none near, so cloth bends where the body bends; and the body
gets one just inside each end of a piece that covers it, so the skin under
a sleeve is faces of its own and none is half in, half out.

**Skin under clothes is not drawn.** drape.py marks each body face that a
piece of gear hides completely: gear straight out from it and at a slant
four ways, so a face under a hat's brim, or just inside a collar, stays.
export.py writes those faces as meshes of their own, `body under: wool
trousers`, tagged `"under"` with the gear's name (names joined with `|`
where two pieces each hide the face). The rule for a game, and what the
gallery does: show such a mesh only while every gear it names is off.

Why hide rather than shrink the body or keep it and hope: hidden skin
cannot come through, whatever the animation does; the body is still whole
the moment the gear comes off; a dressed character draws fewer triangles;
and it is one line in any engine. Shrinking the body inside its clothes
leaves a body that is the wrong shape when they come off, and still clips
on a deep bend. Of a hanging piece, the last quarter above the hem hides
nothing, because a hem swings clear of the leg.

**`cloth.py`: clothes take the body's weights.** rig.py binds every piece
by its nearest bones, so a trouser leg and the leg inside it, built with
different rings, got different weights and came apart on a stride. Now
each point of tight or loose cloth takes the weights the body has at the
spot right under it. A point with no body close under it, or one whose
nearest body faces the other way (the far side of an armpit), is not
trusted: its weights are spread in across the cloth from the points that
did find the body. (This is the usual way to move weights from a body to
its clothes; see "Robust Skin Weights Transfer via Weight Inpainting",
Abdrashitov and others, 2023.) Hats, buckles and the foot of a boot keep
what rig.py gave them; a boot's shaft goes with the shin.

Then **loose cloth gets bones**: for each hanging piece, chains around it,
each of a few bones from the line it hangs from to the hem, named
`cloth_<gear>_<chain>_<bone>`, children of the bone the piece is worn on
(hips, chest, head; an arm for a loose sleeve; never a leg). Points are
weighted to them more the lower they hang and the further they stand off
the body, so a kilt's side resting on a thigh stays with the thigh. The
bones of a chain are not joined end to end: each carries its own patch of
the cloth and may slide as well as turn (swing.py).

**Every hanging piece is a kind of garment**, worked out from how it hangs
alone, never from its name or who wears it (`kind_of`): the bone its top
is worn on, whether it goes all the way round, which way an open one
faces, how far it drops and how high it starts.

| Kind | It is | Chains x bones | How it moves (weight, stiffness, hold) | Cards |
|---|---|---|---|---|
| skirt | all round the hips (or a robe from the shoulders), 30% of the height or longer | 8 x 4, one at the very front and back | heavy, soft, free | a piece of its own |
| short skirt | all round the hips, shorter: a kilt, a tunic's hem | 4 to 8 x 3 | a little lighter and stiffer | a piece |
| apron | part of the way round, in front | 2 to 4 x 3 | light | a piece |
| tails | part of the way round, behind or at the sides: a coat's | 2 to 4 x 3 | as a short skirt | a piece |
| cape | part of the way round, from the shoulders | 3 to 5 x 4 | soft | a piece |
| hood | from the head | 1 to 4 x 3 | stiff, held to its shape, swings 80 degrees at most | rides the head's card |
| sleeve | from an arm | 1 to 2 x 2 | light | rides the arm's |
| sash | a hand's breadth, from the hips | 1 x 3 | a rag | rides |
| shirt | all round from the shoulders, ending at the waist or hips | none: it stays with the body | | held back from the neck's turn by half |
| collar | too short to swing | none | | held back by half |

The table is `"kinds"` in cloth.py's PARAMS (`"kind": {"<gear>": "<kind>"}`
says otherwise for one piece). What was decided is written on the rig as
one description, `forge_cloth`: each garment's kind, where it hangs from,
its chains, how heavy and stiff it is, what it is kept out of and how flat
cards show it. It rides in every `.glb`, and it is all that swing.py, the
cards (`scripts/impostor/impostor.py`: `garments_of`) and the judges read.
Cloth hangs from the head only if it is on the head: a tunic's neckline
lies by the neck, but the tunic hangs from the chest (the villager's got
four chains from his head, once). And cloth that hangs is never stiff: a
piece its recipe called `"stiff"` that is named for hanging cloth (a
tunic's skirt, an apron) is loose all the same (drape.py).

**`swing.py`: the one fabric step, after any motion.** animate.py bakes
the body and leaves the cloth bones still; its result lists `"then":
["swing.py"]` for a rig that has them, and the runner (or Claude) runs it
next. Every way a motion gets onto a character ends there (the walk, a
run, a shot, a fight, a ride, the screen-test motions), and nothing else
moves cloth.

It simulates each loose garment as the sheet of cloth it is, with
Blender's own cloth simulation, and carries what the cloth does onto the
garment's bones:

1. **The sheet.** The garment's mesh, its points welded; what the body
   carries of it (a waistband) pinned to the body; the body's skin, every
   other piece of clothing and the floor to collide with. Its weight,
   stiffness and hold come from its kind.
2. **The start.** The body is held as it was made while the cloth settles
   on it, then turned into the motion's first pose, so no limb starts
   half through the cloth. A loop is played round three times.
3. **Onto the bones.** Each chain bone gets the turn and the move that
   best carry its own patch of the cloth from where the simulated cloth
   settled to where it is on that frame. Starting from where it settled
   means a garment keeps the shape it was made in while nothing moves it
   (a simulated sheet sags; the garment's tiers do not).
4. **Kept clear.** The garment's own points, skinned as the mesh is, are
   tried against rods as thick as the body is each way round each limb
   (rays to the skin), and a point in a rod is put out on the side the
   simulated cloth is on, not the nearest: over a knee, outside a hand.
   A leg wins over an arm. No point goes under the floor.
5. Each bone's turn and move are brought inside what its kind may do,
   eased with the frames either side, and keyed. A loop's last round is
   faded into the one before it, so it closes with no seam.

What is keyed is only bones (a turn and a move a frame), so a `.glb`
carries it and whatever is skinned to the chains moves by it: the cards'
dress piece needs no baking again when the motion changes. Four to ten
seconds for six seconds of motion on a low-poly or mid-poly character,
skirt or hood alike: most of it is Blender stepping the body the cloth
collides with. A walk or a run loop takes two to four.

Weights on strings (spring bones) were what moved cloth here before. They
were kept out of the legs by pushing each chain out of each leg, and they
could not know how cloth lies over a raised knee or piles on the floor: in
a deep squat the skirt was flung out behind and the thighs were bare. The
simulation was tried against them on the same motions and judged by the
same judge (README: "Fabric"); the old way is gone, not kept beside it.

`scripts/fabric_judge.py` (`just fabric-judge`) measures any finished
`.glb`, any garment against any part of the body.
`scripts/fabric_survey.py` (`just fabric-survey`) lists who wears what and
which clips still play cloth moved by an older fabric step (swing.py
writes its number, `FABRIC`, into every bake).

**Measured** (`scripts/cloth_check.py`; `just test-tools` runs it on all
five). "Through" is body points that gear covers standing still, followed
over every frame of the walk: the share of them that have their cloth
behind them instead of over them, and the deepest. Lincoln, the ninja and
Roosevelt are their own block-outs and recipes; the troll and the pirate
predate gear, so theirs are the recorded block-outs with the gear named
(the pirate with hips narrower than his coat, for the skirts to hang off).

| | | Skin through cloth over the walk (points x frames, deepest), before | after | Cloth off the body where it touches, before | after | Triangles in the file, before | after | drawn dressed | Cloth bones |
|---|---|---|---|---|---|---|---|---|---|
| Lincoln | low | 1,892, 5.8 cm deep | 238, 2.6 cm | 1.8 cm | 1.0 cm | 3,200 | 3,608 | 3,198 | none |
|  | mid | 1,029, 5.8 cm deep | 214, 1.5 cm | 1.7 cm | 1.0 cm | 7,144 | 7,840 | 6,763 | none |
| Ninja | low | 112, 0.9 cm deep | 119, 1.6 cm | 2.4 cm | 1.6 cm | 1,596 | 1,780 | 1,433 | 8 |
|  | mid | 164, 1.0 cm deep | 65, 1.4 cm | 1.6 cm | 0.9 cm | 5,734 | 5,998 | 4,471 | 4 |
| Roosevelt | low | 87, 1.0 cm deep | 0, 0.0 cm | 1.9 cm | 1.3 cm | 1,828 | 2,052 | 1,775 | none |
|  | mid | 306, 2.4 cm deep | 32, 0.5 cm | 1.4 cm | 0.9 cm | 6,280 | 6,600 | 5,470 | none |
| Cave troll | low | 505, 7.8 cm deep | 236, 7.8 cm | 3.8 cm | 1.3 cm | 1,334 | 1,374 | 1,355 | 16 |
|  | mid | 205, 5.4 cm deep | 59, 0.7 cm | 3.8 cm | 1.3 cm | 4,718 | 4,758 | 4,655 | 16 |
| Pirate | low | 105, 0.9 cm deep | 186, 4.7 cm | 1.8 cm | 0.8 cm | 1,654 | 1,856 | 1,229 | 6 |
|  | mid | 167, 1.5 cm deep | 155, 5.0 cm | 1.7 cm | 0.8 cm | 6,038 | 6,598 | 3,984 | 6 |

What is weak, most visible first:

- **A thick, square leg still comes through a low-poly kilt.** The troll's
  thighs are 43 cm across with corners, and it sways 44 cm a stride. Eight
  chains of bones make the kilt an octagon that cuts those corners: up to
  8 cm of thigh through the side at hem height on some frames. The
  mid-poly version, with rounder legs and more points, is clean.
- **The low-poly pirate is no better, and deeper.** 186 point-frames
  against 105, up to 5 cm: skin at the hips where the coat's skirts, the
  belt and the trouser tops overlap, and at an armpit. His old body was a
  thinner copy of the coat, so it moved exactly as the coat did; a body
  with real hips does not.
- **Seams between pieces of one garment.** A sleeve and a jacket are
  separate tubes; in the walk a sliver of skin can show at the armpit on
  the low-poly ninja. Hidden skin only helps where one piece covers a face
  completely.
- **Cloth is thicker than it was.** Lifting flat cloth over a coarse body
  adds up to a centimeter; the low-poly ninja's suit stands 1.6 cm off
  where 0.9 was asked.
- **Loose is all or nothing per piece.** A coat built as one tube hangs
  from its belt, or from its shoulders without one; long sleeves and sash
  ends that hang sideways are not handled. The prompt asks for a coat as a
  tight piece above the belt and a loose one below.
- **No cloth against cloth.** A garment's simulated sheet collides with
  the body, with the other clothes and with the floor, not with itself or
  with another simulated garment (an apron over a swinging skirt would
  pass through it). Arms are in its way now, but a hand still goes into a
  full skirt's flounces (README: "Fabric").
- **Feet inside boots.** A body foot as big as its boot shows through the
  sole from below; stiff gear is not reshaped.
- **The fold at a joint is still a straight bend.** Cloth and skin now
  fold together, with a ring at the same height, but an elbow or knee
  still creases like a paper tube: no twist bones or corrective shapes.
- **Old block-outs are guessed.** Without `"fit"` on the pieces, a coat
  called "torso" is taken for tight cloth. Check `"pieces"`.

## Skin-tight clothes, painted on: the wardrobe's shared body

A singlet, tights or an undershirt lies flat on the skin. As a mesh it is a
second surface a few millimeters off the first, and the two have to bend
exactly alike or skin comes through: on Roosevelt's mid-poly routine it did
on 209 point-frames, 4 cm at the deepest, after every fix above. Painted
into the body's own texture the cloth is the skin's surface. Nothing can
come through it, it costs no triangles, and it can be handed on.

This is an option beside draping, not instead of it. **Loose clothes, boots,
hats, belts and anything whose outline matters keep their meshes** and are
draped as before. Only what a run's `wardrobe.json` names is painted.

    wrap.py     the wardrobe's template body laid on the character's own; its own head kept
    paint.py    the named gear painted into the template's texture and taken off
    rig.py      the template's points take the template's own weights ("template": its .glb)

**The template** (`wardrobe/headless-1.0.glb`, and a .blend to keep
modeling; `wardrobe/README.md` has where it comes from and its license: the
MakeHuman base mesh, CC0, mesh data only) is one body from the collar down:
3,722 points, quads in clean loops, one texture layout, weights for rig.py's
bones. Laid on every character, a spot of its texture is the same spot of
the body on everyone. That is what lets one painted outfit fit them all.

**`wrap.py`** needs rig.py's `"joints"` for the character (run rig.py
first). It carries each template bone to that joint, as long and as thick
as the body is there, then draws the template onto a fine shell of the
character's own body. The character's head is every piece of its body above
the collar; the neck piece comes whole, so it reaches down inside the
collar and no gap shows when the head turns. The template's faces get a
material marked `"template"`: that mark, not a name, is how `rig.py` and
`paint.py` know them, and it travels in a .glb.

**`paint.py`** goes texel by texel. What a texel is goes by its color, not
by which mesh it came from, because a block-out garment is cut rougher than
the real one: its texture shows skin round the neck, the garment under it
where it was built too long, boot tops where it was built down into the
boots; and the body's own texture shows the real strap where the mesh fell
short. Skin that had gear over it is filled in from skin that had none.

**That is only the evidence: each garment is then drawn fresh**, the way a
game paints armor onto a body, because the source's texels are speckled,
lit from one side and ragged at every edge, and copying them (the first
version did) can only be as clean as they are. A garment is a clean region
of the template in its own color:

- on a limb it covers one stretch of the bone, and a hem is a cut straight
  across the limb (`"cuts"`: the singlet's leg at 0.385 of the thigh);
- on the trunk its edge (neckline, armholes, straps) is how much of the
  garment is round each of the template's points, evened out over the mesh,
  made the same left and right unless the source is clearly lopsided, a
  pinched strap let out, corners rounded;
- its color is the middle of its own texels, with the faintest of the old
  bake's broad light and dark (within 4%) and none of its speckle. A
  garment with a second color on much of it (stripes, a band at the hem)
  says so in `"pattern"`, and is drawn plain all the same for now;
- it is its whole shape, also under another painted garment: where its
  mesh lies under the other's it is taken to carry on. They are painted in
  the order they go on (`"painted"`: tights, then singlet), so the tights
  worn alone have no hole.

`"garments"` in the result says, for each, what the source gave, what was
drawn (`"drawn"`) and `"ends"`: how far along each limb it reaches.
`just paint-check --edges <template.glb> <garment.png>` measures how clean
an edge is: its length against the same edge evened out over 2 cm
(`"ragged"`: 1.00 to 1.02 drawn fresh; 1.10 for the singlet copied from
Roosevelt's texels with its edge evened; 1.38 with 9 loose scraps copied as
the meshes had it).

The head keeps its own texture and shape, with two repairs: where gear
that comes off was over it or close by and the texture is not skin (a
collar's shadow down the throat), it is filled in from the skin around;
and below the collar the neck is tucked 7 mm inside the template, because
the template was drawn onto that very surface and two skins in one place
flicker through each other (Lincoln's showed as a black slit down his
throat).

With `"save"` each garment is also written as a picture of its own
(`painted-outfit/wool singlet.png`), and another character wears it with
`"wear"`. A run's `wardrobe.json` says which:

    {"paint": ["wool singlet", "wool tights"]}

    {"take_off": ["linen work shirt", "wool trousers", "leather belt"],
     "wear": [{"name": "wool singlet", "image": "../<roosevelt>/profiles/painted-outfit/wool singlet.png"}]}

**The runner**: `just tidy <run> painted walk rom` makes `painted.glb` from
`midpoly.glb` (skipped with no `wardrobe.json`), then `painted-walk.glb`
and `painted-rom.glb` like the others. `just paint-check <file>` measures a
walking file (`scripts/paint_check.py`).

**Measured** (the real runner on copies of both runs; `just test-tools`):

| | Roosevelt, his own outfit | Lincoln, wearing Roosevelt's |
|---|---|---|
| Skin through, walk / routine (point-frames) | 0 / 0 (as meshes: 2 / 209) | 0 / 0 |
| Collar off the neck: standing, worst in the walk, worst in the routine | 0.83, 0.99, 1.48 cm | 0.20, 0.20, 1.26 cm |
| Feet under the floor, at the lowest | 0.44 cm | 0.32 cm |
| The singlet's leg ends, along the thigh | 37.8% | 37.7% |
| The tights end, along the shin | 11.2% | 10.2% |
| Edge against itself evened out, singlet / tights | 1.005 / 1.003 | the same pictures |
| Triangles in the walking file, drawn dressed | 9,910, 7,836 (as meshes: 6,600, 5,520) | 10,334, 8,718 |

What is weak:

- **It is heavier, not lighter.** The template is 7,402 triangles where the
  mid-poly body was about 4,000, and its fingers and toes are most of the
  difference. The gear's triangles are saved; the body's are not.
- **The shape is fitted, not known.** Where the source is thin (the top of
  a shoulder, where the block-out strap stood off), the strap is a guess
  between its two ends. Edges on the trunk follow the template's mesh,
  about 2.5 cm between points: a neckline comes out a little squarer than
  a tailor would cut it.
- **Plain color only.** Stripes, a band at a hem, a badge: noticed
  (`"pattern"`) but not drawn.
- **Color tells cloth from skin.** A flesh-colored garment cannot be
  trimmed this way; the result warns when most of a garment looks like skin.
- **Under another garment, a garment is where its mesh is.** Roosevelt's
  tights start a quarter of the way down the thigh because his block-out
  tights do; nothing says whether the real ones reach the waist.
- **Skin under clothes is made up.** It is the body's average skin color,
  shaded only near real skin. A character dressed head to toe has little
  to go by.
- **The collar is a step, not a seam.** The head sits inside the collar
  rather than being joined to it; from above, or with a thin neck piece,
  the edge can show.
- **Not in the gallery yet**, and nothing asks for it by itself: no prompt
  writes `wardrobe.json`.

## A real body under clothes that hide it

A long skirt, a robe or a cloak hides the body. TRELLIS.2 sees only the
cloth, so what it puts under it is a guess, and the block-out, the rig and
the walk are all built on that guess. For such a character the pipeline
makes the body for real (`baml_src/2b_undress`) and puts the clothes back
on. Two scripts do the measuring and cutting; both run in a background
Blender, never in the person's.

    garment.py   two pictures and two meshes in; the base body laid on the clothed mesh, each hiding garment cut out
    follow.py    after the finish: the base body and garments make the move stand.py made

What goes in: the clothed picture and its mesh, and a second picture of
the same character with the hiding clothes off (Codex edits the first:
same pose, same framing, plain skin-tight black where the clothes were)
and the mesh TRELLIS.2 makes of that, the base body.

**It checks before it cuts.** `garment.py` stops, and says why with
numbers, when:

- the figure moved between the pictures (an edge of it, head top, hands
  or feet, shifted more than 2% of its height; an edge the garment itself
  reaches, like a hood at the top, is let off), or nearly nothing changed,
  or nearly everything did;
- a mesh, seen from the front, doesn't cover the figure in its own picture
  (under 70%): it isn't framed the way the picture is;
- the base body's uncovered parts (head, arms, feet: whatever lands
  outside the change in the pictures) sit more than 0.8% of the height off
  the clothed mesh typically, or one in ten of them more than 2.5%.

The pipeline then has Codex edit the picture once more, with what went
wrong in the request; a second failure stops the step
(`BaseBodyMisaligned`, with the numbers).

**The framing.** TRELLIS.2 centers the figure and scales it to fill its
box, front toward -Y. So a face at (x, z) lands in the picture at a column
and row worked out from the two outlines' edges: the mesh's box and the
figure's box in the picture. The result's `"view"` says how well that
holds (`overlap_pct`: on the dancer 89% and 88%). The mesh can be mirrored
left to right; it is tried both ways and the one whose colors match the
picture wins.

**The fit.** Two TRELLIS.2 meshes of two pictures with the same framing
come out in the same place at the same size (the dancer's: 0.16% of her
height apart, untouched). When the clothes change the outline (a hood
makes the figure taller, so everything else comes out smaller), they
don't; so the base body is fitted, by size and position only, to the parts
no clothes cover, starting from wherever is closest: as the meshes came,
or where the pictures put them. `"fit"` has the scale, the shift and how
far apart the uncovered parts end up, height band by band.

**The cut: three votes, two agree.**

| Vote | Says "garment" when | Good at | Weak at |
|---|---|---|---|
| picture | the face lands where the two pictures differ | the garment's outline, exactly, up to the waistband | it can't tell front from back from the legs inside, and base clothing changes pixels too (ankles) |
| color | its texture color is one the garment has in the picture and the rest of the figure doesn't | the back, which the picture never saw; cloth that hugs the body | a garment the color of something else on the figure |
| distance | it stands off the base body by more than 1.5% of the height | ruffles, hems, anything that hangs | cloth that hugs the body: cutting by distance alone tore the dancer's upper skirt away |

On the dancer all three agree on 55% of the surface; picture and color
alone keep the 7% that hugs the hips; picture and distance keep the 8.5%
whose color is in doubt (the edges of the polka dots, shadowed folds).
Then:

- the cut grows over its own blurred edge, up to where the colors change:
  a neighbor the picture votes for joins unless its color is clearly the
  rest of the figure's. That is what brings the skirt whole to the
  waistband (6,762 faces on the dancer);
- the edge is evened out, scraps under 1% of the garment are dropped (79
  of them, mostly bits of leg inside the skirt), holes under 1% are closed
  (93);
- garment points that end up under the real body's skin are lifted onto
  it (`"seat"`). The clothed mesh hugged a guessed hip; the real one is a
  little fuller. A TRELLIS.2 mesh is a thin shell with an outer and an
  inner wall, so inside and outside are told apart by counting walls along
  a line, not by which way the nearest face points.

With several garments, each face goes to the one whose `slot` is at its
height (a hood above a robe).

**Read the result.** For each garment: `faces`, `area_pct`, `top` and
`bottom` (shares of the height), `pieces`, `closed_round_its_top_pct`
(100 = a whole waistband) and `other_colors_pct` (scraps of tights or
shoes would show here). `"votes"` has the faces and area each vote claimed
and each combination. `"overlay"` renders the clothed mesh front, quarter
and back with every face in its votes' color: white all three, blue
picture + color, yellow picture + distance, purple color + distance, green
added in cleanup, red dropped. `scripts/base_shots.py` (`just base-shots`)
puts the body, the clothes and both on one sheet above those.

**Where things live.** In the run: `base/image.png`, `base/mesh.glb` (the
second picture and its mesh), `base/body.glb` (the base body laid on the
clothed mesh), `base/cut/<garment>.glb`, `base/cut.json` (the result),
`base/sheet.png`; a failed try is kept in `base/tried-1/` with why. After
the finish, `base/final.glb` and `garments/<garment>.glb` are the same
pieces where the finished object stands.

**Following the finish.** `stand.py` now keeps the whole move it makes
(turn, scale, shift, multiplied up over every run) on the object as
`forge_placed`. `follow.py` opens the run's `scene.blend`, reads it,
checks it by moving the raw mesh onto the finished one (0.000% apart when
the move is right), and applies it to every file in `"follow"`. With no
kept move (a scene from before, or `final.glb` alone) it fits one: 24
quarter turns, sized and centered, closest wins. A turn that isn't a
quarter turn can't be found that way, and it says so instead of writing.

**In the block-out.** When a run has `base/final.glb`, the low-poly prompt
(`base_steps` in `lowpoly_prompt.baml`) has Claude bring it in beside the
reference with `open.py` and `"add": True` as "Body", and each garment as
"Garment: <name>"; measure body pieces on "Body" and each hidden garment
on its own mesh; and pass `"reference": "Reference"` to `build.py`. Gear
and `fit` tags, `drape.py` and the rest are as before.

## Clothes get their own colors: the bake by group

A bake copies whatever the detailed mesh shows nearest each spot. On a
dressed block-out that went wrong in three ways (seen on the troll, and
measured on all six characters):

- **Legs on the kilt.** A block-out's kilt is a little longer and wider
  than the real one. Below the real hem the nearest surface is the leg, so
  the kilt's lower corners were painted leg. A third of the troll's kilt
  was nearer its skin's color than the kilt's.
- **A lining painted with whatever is inside.** The inside of a kilt or a
  coat's skirts faces the legs and copied them, or the mesh's insides.
- **Skin under clothes in the wrong color, and showing.** The skin a piece
  hides was given the flat color Claude painted the body with, which is
  rarely the texture's skin (the troll: a pale gray-green beside olive, 38
  dE apart). And the test for "under gear" was not the one drape.py uses
  to hide faces, so some of those flat faces showed with the clothes on:
  a pale band over the troll's belt, patches on Roosevelt's back.

So when the target has gear, `bake.py` "onto" bakes **by group** (it does
this by itself; `"by_group": False` gives the plain bake):

1. **It works out, point by point, which surface is that piece's own**
   (`plan`). Along each point's normal it lists the detailed mesh's
   surfaces you could see from outside: facing the same way, with air over
   them, so never the far side of a limb or a layer buried in the body.
   It takes the outermost one within 2% of the size, and looks as far as
   the `"reach"` (7%) only when nothing is that close. It never looks past
   the next limb, so a shirt's side doesn't take the arm.
2. **What is under another piece copies nothing.** Skin with gear close
   over it, every body face drape.py hides, a kilt's top under its belt:
   the picture showed the character dressed, so the detailed mesh has the
   piece on top there, not this one.
3. **The part boxes help** (`"parts"`: the runner passes parts.json). A
   box named like a piece of gear ("kilt front" for "hide kilt", "boot_l"
   for "boots") says where that piece is on the detailed mesh. A piece
   with boxes takes a surface outside every gear's box only if it is
   within 1.5% of the size: the leg below the real hem is not.
4. **Where shape can't tell, color does.** A point of gear that found its
   surface deeper than its own lining, or about where the body is under
   cloth that hangs clear of it, is "in doubt". Its pixels are kept only
   if they look more like the rest of the piece than like the body.
5. **The rays start just above the chosen surface.** The bake gets a cage:
   a copy of the target swollen, point by point, to just over what each
   point (and the middle of each face) found. A second quick bake records
   where every ray landed, and a pixel is kept only if that is within 2%
   of the size of where its piece was looking.
6. **Everything else is filled in, never left to chance.** Next to kept
   pixels of the same piece the fill continues their color; further off it
   fades to the piece's average (the color most of its kept pixels agree
   on). Skin under gear gets the body's average for its painted color, so
   with the kilt off the troll's hips are the olive of its legs. If less
   than a quarter of a painted color was copied (a ninja's body, nearly
   all under cloth) the painted color stays. Filled pixels get a flat
   normal.

The result lists each group's `copied_%`. A low one is not a fault: half a
kilt's texture is its lining.

**Flat colors too.** A flat-color low poly bakes nothing, but its colors
were Claude's guesses, and they were far off (the troll 41 dE from its
own texture, the ninja's black suit painted gray). `"repaint": True` (in
the `lowpoly` profile's flat-color steps) runs the same bake at 256 px,
keeps no texture, and sets the painted colors from it: each of the body's
becomes the average found for it (skin, hair), and a piece of gear's all
move by the same amount, so the kilt turns kilt-brown and stripes painted
on trousers stay stripes. Delete that step from `profiles.json` to keep
Claude's colors as painted.

**Measured** with `scripts/bake_check.py` (`just bake-check <run>
<file.glb>...`): the detailed mesh and the version are looked at straight
on from four sides, color only, and compared spot by spot (dE in CIELAB:
under 5 is hard to see, over 25 is another color). "Takes skin" is the
share of a piece nearer the body's color than its own. Before is the
plain bake (two looks and a fill) with flat skin under gear; the pirate,
lizardkin and troll are the recorded block-outs with gear named.

| Mid poly | Takes skin, before | after | Skin under it, dE from the skin that shows, before | after |
|---|---|---|---|---|
| Troll: hide kilt | 33% | 14% | 38 | 1 |
| Troll: rope belt | 41% | 14% | 39 | 4 |
| Troll: iron wrist band | 6% | 1% | 29 | 2 |
| Lizardkin: war-skirt | 36% | 30% | 17 | 8 |
| Lizardkin: leather cuirass | 31% | 27% | 19 | 3 |
| Lizardkin: bronze pauldrons | 5% | 3% | 19 | 2 |
| Lincoln: wool trousers | 3% | 3% | 5 | 1 |
| Lincoln: linen work shirt | 17% | 16% | 5 | 1 |
| Roosevelt: wool singlet | 8% | 6% | 17 | 5 |
| Roosevelt: wool tights | 47% | 47% | 16 | 4 |
| Pirate: navy coat | 8% | 9% | 47 | 47 |
| Pirate: tricorn hat | 24% | 19% | 41 | 46 |
| Ninja: cloth suit | 0% | 0% | 13 | 13 |
| Ninja: hood and mask | 4% | 1% | 17 | 16 |

Where the detailed mesh shows the piece itself, the color was already
close and still is (2 to 7 dE either way), and the share of spots that
are a different color altogether went from 1.5% to 0.5% on the troll and
stayed within half a point on the others. A mid-poly bake takes a second
or two longer.

| Low poly, flat colors, dE all over | as painted | set from the mesh |
|---|---|---|
| Troll | 41 | 8 |
| Pirate | 36 | 18 |
| Ninja | 22 | 7 |
| Lizardkin | 21 | 13 |
| Roosevelt | 13 | 12 |

What is weak, most visible first:

- **Fill is a smear, not cloth.** Where a block-out's kilt hangs below the
  real hem there is nothing to copy, so its lower edge is the kilt's
  colors drawn out and fading to one brown. It reads as kilt, not as
  leather with stitches.
- **A block-out piece that covers skin the real garment doesn't.**
  Roosevelt's tights are built down to his boots; the real ones stop at
  the knee. Tight cloth lies on the body, so shape can't tell and there
  are no boxes for it: the shins of his tights are skin-colored, as
  before (47%). The lizardkin's skirt and cuirass have the same between
  their straps.
- **Skin under gear is one flat color**, with a hard edge where the
  textured skin starts. It is the right color now, and only seen with
  the gear off.
- **A body nearly all under clothes keeps Claude's skin color** under
  them (the pirate, the ninja), which can be far from the face's (47 dE
  on the pirate's recorded block-out).
- **Skin right at a piece's edge can still take the piece.** The troll's
  belly has a strip of rope where the detailed belt is wider than the
  block-out's. The pirate's hands got a little worse (6 to 8 dE).
- **Flat colors lose what Claude did well.** Where its colors were
  already close (Roosevelt) setting them from the mesh changes little
  and makes the singlet a shade purple and the spectacles worse. One
  average per piece also means a piece and the skin can end up close
  (the troll's kilt and legs are both dark olive-brown, as in its
  texture).
- **Names have to match.** "leather brogans" has no box called shoes, so
  Lincoln's shoes go by shape alone.
- **A run's base body and cut garments are not used yet.** Where a run
  has them, each piece could copy from its own garment mesh and the body
  from the base; bake.py still takes one detailed mesh.

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

## Faces in every version: a head sheet, paint, a whole head

"The faces are distorted" turned out to be four different faults, found by
drawing every character's face in every version next to its picture
(`scripts/face_sheet.py`) and measuring it (`scripts/face_check.py`):

| What was wrong | How much (six characters) | Which versions |
|---|---|---|
| **The head came back from the remesh in shreds**: holes where the hair, brow and cheeks were | 27% to 95% of the head's front missing; not one whole head | `web`, `game` (and `quads`, `mobile`) |
| **TRELLIS.2's own face is a smudge**: the shape is about right, the texture is not. Eyes are dark blobs, lips a blur, glasses black discs | laid out like the picture (features within 1-2.4% of the head's height), but the eyes look only 0.33 to 0.79 like the picture's | every version, since all are baked from it |
| **Too few pixels**: one texture for a whole character leaves a face about 60 pixels across at 1024, 15 at 256 | the head is 3-4% of a character's surface, so of its texture | every baked version |
| **The block-out's head is a coarse stand-in** with dark pockets cut for eyes, which fight a baked texture | 5.7% to 11.5% of the head's height off the detailed head; a face detector finds a face on one low-poly head in six | `lowpoly`, `midpoly` |
| The walk bent the jaw: the head piece was blended with the neck bone | the head's points moved 1-3% of its height against the head bone, 11% on the low-poly ninja | the walk clips |

What is done about each, in the tools:

- **A head sheet (pipeline step 2b, `baml_src/2_picture/head_sheet.baml`).**
  For a character, Codex is shown `image.png` and asked for the same head
  again, large, three times side by side: front, three-quarter, side. It is
  saved as `heads/sheet.png`. The face in it is three to four times the
  size it has in the whole-figure picture. `just head-sheet <run>` draws
  one for a run that has none. Nothing waits on it: without one the picture
  itself is used.
- **`face_paint.py` paints the face onto the detailed mesh.** Like a slide
  projector in front of the head: every point that faces front with nothing
  in the way takes the picture's color there, fading out toward the sides,
  under the jaw and behind anything. It finds the head by itself (or takes
  its box), then finds where the picture sits: first by the outline (how
  wide the head is, row by row from the top), then by sliding and scaling
  until the picture's light and dark agree best with the mesh's own
  texture; a smudged eye is still a dark spot in the right place. `"fit"`
  says how well they agree; under 0.45 it paints nothing (the right picture agrees 0.60 to 0.78 on five characters, a wrong one 0.25 to 0.39). The picture's
  colors are toned to the mesh's, so the face doesn't end at a line under
  the chin. The paint is shader nodes (`face paint: ...`) and a point
  attribute, so it reaches a file only through a bake.
- **The runner paints before it bakes.** `scripts/tidy_profile.py` runs
  `face_paint.py` on every character as soon as the scene is open: the head
  sheet's front view if the run has one and it fits, else `image.png`. So
  `hero`, `web`, `game`, `midpoly` and `lowpoly` all bake the painted face.
  `"face"` in `<profile>.json` says what was used and how well it fitted.
- **The head gets a texture of its own.** After the bake, the faces in the
  head's box are taken off as an object, baked onto again by the same
  `bake.py` with the same settings at half the size (512 for a 1024
  profile, 256 for `lowpoly`), and joined back: one mesh, one more
  material. That is five times or more the pixels across a face.
  (`head_texture` in the runner; `bake.py` itself is untouched.)
- **The head is remeshed whole.** On a character, everything from a quarter
  of a head below the chin up (hair and hat with it) is cut off as one
  piece, whatever other parts were marked, and wrapped in one closed skin
  (a voxel remesh: TRELLIS builds hair, lids, lips and teeth in layers that
  no remesher stitches). AutoRemesher remeshes the skin, with at least 12%
  of the profile's quads. And every remeshed piece is now checked for
  tears: if too much of what shows of the original has no remeshed surface
  near it (15% at half a percent of the object's size, or 4% at one
  percent; for a head 8% and 1.5%, since 4% of a head is its chin), the
  next of AutoRemesher's answers is tried, then a wrap of the piece, then
  the wrap itself, reduced and paired into quads where its triangles line
  up. `"parts"` in `<profile>.json` says which way each piece went.
  (Blender's QuadriFlow makes even quads of such a skin and was tried for
  heads: on some it never returns, and a run can't stop it.)
- **The head rides the head bone alone** (`rig.py`): the head piece, and
  what sits wholly on it (hair, a hat, glasses, a mustache), is no longer
  blended with the neck.
- **The block-out's head is told about the texture** (the head and face
  part of `CHARACTER_STEPS`): unless the style is flat colors, `"eyes":
  "flat"`, no eyes, brows or lips as pieces, and glasses or a mustache kept
  as thin and small as on the reference.

Measured (`just face-sheet <run> out.png`, then `just face-check
out.json`). "Missing" is the share of the head's front, seen straight on,
where a version has a hole or sits more than 8% of the head's height
behind the detailed mesh. "Eyes" and "mouth" are how like the picture
those spots look once the face is laid over the picture's (1 is the same
picture). "Face found" is whether a face detector (MediaPipe) sees a face
at all.

| | Head missing, `web` / `game`: before | after | Eyes like the picture: detailed | `web` | `game` | `midpoly` | `lowpoly` | Face found on `lowpoly` | Head bends in the walk, mid / low: before | after |
|---|---|---|---|---|---|---|---|---|---|---|
| Young Lincoln | 82% / 65% | 20% / 5% | 0.60 | 0.22 -> 0.80 | 0.06 -> 0.85 | 0.51 -> 0.75 | none -> 0.64 | no -> yes | 1.0% / 1.0% | 0 / 0 |
| Roosevelt | 27% / 69% | 10% / 1% | 0.33 | 0.30 -> 0.48 | 0.17 -> 0.41 | none -> 0.42 | 0.21 (flat colors, unchanged) | yes | 2.0% / 1.6% | 0 / 0 |
| Flamenco dancer (raw mesh only) | not made | 1% / 2% | 0.61 | 0.85 | 0.82 | | | | | |
| Pirate | 41% / 30% | 23% / 15% | 0.79 | 0.39 -> 0.86 | 0.78 -> 0.88 | | (old block-out, no face) | no | - / 3.8% | - / 0 |
| Shadow ninja (masked) | 43% / 41% | 7% / 1% | 0.51 | 0.49 -> 0.76 | 0.67 -> 0.54 | | | no | 3.0% / 10.8% | 0.1% / 5.3% |
| Cave troll | 45% / 49% | 8% / 21% | | | | | (old block-out, no face) | no | - / 1.3% | - / 0 |
| Lizardkin | 73% / 95% | 1% / 9% | | | | | (old block-out, no face) | no | - / 3.0% | - / 0 |

"none" is a version the detector found no face on. Lincoln, Roosevelt, the
dancer and the ninja were painted from their head sheets (they agree with
the mesh 0.66, 0.67, 0.78 and 0.69); the pirate's sheet did not sit on his
head (0.25: the hat) and he was painted from his first picture (0.61); the
troll and the lizardkin were not painted (no head box, or no agreement) and
gain only from the tear check. The sharpness column of `face-check` says
little at the sheet's size (256 px tiles) and is left out here. The sized
versions run over their quad budget where torn answers were passed over:
`game` came to 4,700 to 9,400 faces for a budget of 4,000.

To look at a run:

    just face-sheet runs/<run> faces.png        # every version, front / three-quarter / side, next to the picture
    just face-check faces.json                  # where eyes, nose, mouth and chin sit, how lopsided, how sharp

What is still weak, most visible first:

- **The detailed `final.glb` keeps its smudged face.** It is exported in
  step 4, before any of this runs; only the versions the runner bakes get
  the paint. `just tidy <run> hero` gives a painted detailed version.
- **It is a front view on a 3D head.** Past about 60 degrees to the side
  the mesh's own texture takes over: ears, temples and the side of the
  nose are still TRELLIS's. The sheet's side view is not used yet.
- **Nostrils and the underside of the nose.** The picture sees a little
  under the nose; straight on, the mesh's nose hides that, so nostrils land
  on the tip.
- **What stands in front of the face is painted flat on it.** Glasses and
  an eye patch are part of the picture, so a mid-poly Roosevelt has glasses
  painted on his face and glasses as a piece in front of them: right from
  the front, doubled from the side, and still painted on when the gear
  comes off. A sheet of the bare head would fix it.
- **The seam under the chin.** The head and the body are remeshed apart
  and meet a quarter of a head down the neck: a line there, and at `game`
  size sometimes a gap of a few millimeters.
- **A head sunk between the shoulders** (the troll) has no neck to find.
  Without a block-out recipe to give its box, nothing is painted and the
  head is not cut off whole.
- **Light streaks at the temples.** Where the sheet's hairline or highlight
  doesn't match the mesh's, a pale stripe is painted at the edge of the
  face (Roosevelt, from the side).
- **Heavier files.** A wrapped piece and a second-choice answer both run
  over budget, and the head's own texture adds 100-150 KB.
- **A drawn sheet is a second drawing.** Codex keeps the face well and
  changes small things: a collar, how far the ears stand out, a closed
  mouth where the picture grins. Where the sheet's outline doesn't sit on
  the mesh's, hair is painted onto forehead or the other way round.
- **The face detector only knows people.** For the troll, the lizardkin
  and the masked ninja, `face-check` has little to say; look at the sheet.
- **Low poly at 256 px** reads as a face now, no more: 0.1 to 0.2 of the
  picture's detail.

## Comics: one drawing hand, frozen poses, swapped faces

A comic panel is a rigged character frozen in a pose, drawn in one style,
with the words laid over it as text. Two skill scripts do the drawing; the
rest is in `scripts/comic/` and `baml_src/10_comic/`.

    just comic "<premise>" strip "lincoln, roosevelt" ring     # Opus writes, Blender draws, code letters
    just comic-again <name>                                    # after editing comics/<name>/comic.json
    just comic-style out/ runs/<run>/profiles/midpoly-walk.glb # before and after, side by side

**`toon.py`: the hand.** Run it on any scene with a camera.

- **Paint.** Every material keeps whatever fed its Base Color and gets a
  "comic paint" node after it: the color is brightened (a texture holds a
  surface's own color, darker than it looks under lamps), its light-to-dark
  is snapped to eight steps counted the way the eye does, and black is
  lifted a little so the ink still shows on black cloth. Textures over 128
  px are read from a smaller copy, which is what turns speckle into flat
  shapes (a head keeps 256). Then one of three flat tones multiplies it,
  picked by how far the surface faces a light that is given as the camera
  sees it (upper left), so every panel is lit from the same side whatever
  the camera does. No lamps, no shadows to flicker, nothing to sample: a
  picture is a fraction of a second.
- **Ink.** Inverted hull, not Freestyle. Each mesh gets a geometry-nodes
  modifier that welds a copy of it, pushes it out along its normals, turns
  it inside out and paints it black, so it shows as a line round the shape
  and wherever one piece passes in front of another. The push grows with
  each point's distance from the camera, so the line is the same width on
  screen near and far; measured on the troll, 3 px at one distance and 3 px
  from twice as far. It costs almost nothing: two mid-poly characters at
  900 px render in 0.13 s with no line and 0.14 to 0.18 s with it.
  Freestyle is the other way to get a line of steady width, and it also
  draws creases inside a piece. It was not compared: set up the plain way
  in a background EEVEE render it drew nothing here ("strokes set empty"),
  and the hull was already good and nearly free, so that is what a comic
  uses. Worth another look if crease lines are wanted.
- **It comes off.** `"undo": True` plugs the old shader back in and removes
  the lines. The old nodes are never deleted.
- Colors in PARAMS (`ink`, `background`) are as you see them on screen.
  With `"background": None` the picture has no background, which is how
  panels are drawn: the page puts a sky or a painted backdrop behind.

**`face_swap.py`: the same body, another face.** A flat drawing of a face
is projected onto the front of the head from an empty parented to the head
bone, like a slide projector that turns with the head. It reaches about
60% of the way back through the head and only onto points that follow the
head bone, so the back of a hood and a hand held up in front are left
alone. It fills the "drawn" input of toon.py's paint, so the face gets the
same tones of light as everything else. Why a projection and not a texture
swap or a flat overlay: the low-poly and mid-poly heads have different
texture layouts and a projection needs neither; and an overlay pasted on
the finished picture cannot turn with the head or go behind an arm.

**Expression sheets** (`just expressions <who>`, one Codex image each):

1. `face_fit.py head` draws the character's own head from the front in the
   comic style (`comics/cast/<who>/head.png`).
2. Codex is shown that and the run's head sheet, and asked for a grid of
   eight of the same head, same size, same place: neutral, happy, angry,
   surprised, sad, smug, talking, shouting. Showing it our picture is what
   makes the drawing fit: it keeps our colors and the 3D head's shape.
3. `face_fit.py cut` finds the head in each cell, lines it up with the 3D
   head by its top and width, cuts the face area out with a soft edge, and
   tones it to the head's own lit skin. A masked face (`"kind": "eyes"` in
   `comics/cast.json`) is lined up by the strip of skin itself, on our head
   and in the drawing, and only that strip is kept.
4. `face_fit.py show` puts each face on the head, front and three-quarter
   (`faces.png`). Look at it. If the face sits wrong, change `region` (or
   `lighten`) in `comics/cast.json` and run `just expressions-fit <who>`,
   which costs no image.

**Poses.** `motion/comic_poses.json` holds thirteen, each a few bones
turned away from the T-pose in the character's own axes, mirrored for the
other side, so one pose fits every character with our bone names. After the
turns the character is set down on its lowest point. `just comic-poses`
pictures them all on one character. A pose can also be `clip@seconds`
(any walk, run or shot clip the character has), or one of the named poses a
shot was built from, such as `hero:land_three_point`: those are read off
the shot's plan and stay where the shot had them, on the shot's own roof
and wall.

**Panels** (`scripts/comic/render_panels.py`, one Blender for a whole
comic). Each character file is brought in once. Per panel: pose, stand at
left, center or right of the place facing left, right, the camera or away
(left and right are turned 28 degrees toward the reader so a face shows),
put the face on, fit the camera to the framing with room at the top for
balloons, draw. It writes where every head and body landed in the picture
(`panels.json`), which is all the lettering needs.

**Through a character's eyes** (`"framing": "pov"`). The camera goes to
the first cast member's eyes: just in front of the middle of its head, as
the head bone has it at that pose or clip moment, with a 21 mm lens, which
is about what one eye takes in. `"look"` aims it: `ahead` is where the head
faces; `down` tips it 52 degrees and leans toward the feet when they are
out in front; `hands` leans toward whichever hands are in front of the face
(one behind the head, as when a sword is drawn over the shoulder, is not
looked at, and the look falls back to ahead). The viewer's own head and
neck are taken out with a Mask modifier on the points those two bones hold,
placed before the ink line so no outline is drawn round the missing head,
and the body is drawn from outside only for that panel, so the camera does
not see the inside of its own chest. Both are undone for the next outside
view; a test checks the two pictures match. `panels.json` notes the eye,
the head's middle and how much of the body is in frame (`pov`). Anyone
else in the panel is stood about 1.7 m in front of the viewer, and left,
right and facing are as the viewer sees them.

A clip made from a shot (`"clips": {"hero": {"shot": "hero-rooftop"}}` in
`comics/cast.json`) belongs to the places built from that shot. There, at
`"at": "there"`, any moment of it (`hero:vault_over`, `hero@3.4`) stays
where the shot had it, so a run of pov panels follows the action across
the place. Opus is shown the clip's length and what happens when.

`"silent": true` on a cast member means no speech: the checks turn down
any line of theirs that is not `"think"`. `"canon": false` in a
`comic.json` marks a side story for the page and the gallery.

**Lettering** (`scripts/comic/lettering.py`, no Blender). A thought from
someone whose head is not in the picture (a pov panel) is a voice: a dark
bar along the bottom with light type and no tail, stacked upward in reading
order. For everything else: For each balloon
it tries spots on a grid and keeps the cheapest one that breaks no rule: no
balloon over any face or another balloon; a tail that ends on the rim of
its speaker's head, leaning toward the mouth, and crosses nobody else's
face; a later balloon never above and left of an earlier one. If the words
don't fit, the type shrinks up to three times, then the panel is reported
as too wordy. Text is measured from the fonts' own letter widths
(`font_widths.json`), so no browser is needed. Comic Neue for balloons,
Bangers for sound effects, both from Google Fonts and kept in
`gallery/vendor/fonts`.

**Sets.** `scripts/comic/kit.py` is the only place that knows what a place
is. `from_set_json` there turns a `sets/<name>/set.json` into marks, named
cameras and backdrop files, and a set of the same name replaces a stand-in.
A panel may name a mark in `at` and a camera in `camera`. The stand-ins
(`STAND_INS`: the ring run's low-poly file, the hero shot's blocks, three
flat colors) carry no marks or cameras on purpose: they are not a set
format. Delete each one when its set exists.

Measured (M-series Mac, EEVEE, 900 px panels): a panel takes 0.15 to 0.6 s
once its characters are in; the first panel of a comic 0.4 to 1.4 s with
loading. The 4-panel strip draws in 1.1 s, the 8-panel episode in 2.2 s.
Lettering and the page take under a second, the .png another second or two
(headless Chrome). An expression sheet is one Codex image, a backdrop one
more. A script is one Opus call of about 6,500 characters in and 1,600 to
2,200 tokens out.

What is weak, worst first:

- **Pov shows what the clip gives it.** Looking down, a third of the
  picture can be the viewer's own chest and shoulders, because the eye is
  in a head that sits low on a stocky body. Looking ahead in the sprint
  nothing of the body is in frame: the arms swing below the view. The head
  bone, not the eyes, decides the direction, and the clip's head hardly
  turns. The painted backdrop only follows the camera up and down, not
  round, so the same skyline is behind every direction he faces.

- **The face is a flat picture.** Past about 60 degrees the far eye slides
  round the cheek. It is painted over real glasses and a real mustache
  (Roosevelt), which doubles them slightly. It is lined up by the head's
  outline, not by where the eyes are, and the block-out heads are 6 to 11%
  off the detailed ones.
- **Poses are stiff.** Mitten hands, no fingers, no weight shift. Nothing
  checks that two characters, or a hand and a body, are not inside each
  other. Only a shot's own clip carries a prop (the ninja's sword).
- **The paint keeps what the texture has**, baked shading and blotches
  included; on the mid-poly characters knees and forearms come out patchy.
  Shrinking the texture to flatten it also lets colors leak a little
  across the seams of the texture.
- **The hull line** breaks where a mesh has a hole or an inside-out face,
  and it draws no crease lines inside a smooth piece.
- **A two-shot with people far apart** is fitted to their width, so the
  heads come out small.
- **Opus picks only left, center and right.** Depth, and who is in front,
  are not in the script.

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
| `landmarks.py` | find a character's landmarks (chin to ankles), its proportions and its body's shape all along, and print it as a `"body"` piece for `build.py` | low poly (characters) |
| `face_paint.py` | lay a picture of the face (the head sheet's front view, or the first picture) over the front of the detailed head, as shader nodes a bake picks up | profiles (characters) |
| `rig.py` | give a T-pose character bones placed from its own build, bind every mesh, set each joint's limits, hang the sockets on bones | walk |
| `walk.py` | work out a walk from the measured build and four traits; leaves it on the rig as a motion | walk |
| `animate.py` | play a motion on the rig: fit it, plant the feet, clamp to the limits, bake keyframes, measure the result | walk |
| `build.py` | block out a low-poly version from a list of lofts, tubes, lumps, boxes and a head; join, color and check it; keep gear as groups, add sockets, keep the recipe | low poly |
| `drape.py` | lay each piece of clothing on the body (tight, loose or stiff), and mark the skin it hides | low poly (dressed characters), profiles, walk |
| `cloth.py` | give clothes the body's weights; give loose cloth chains of bones to hang from; say what kind of garment each hanging piece is | walk |
| `swing.py` | after any baked motion: simulate each loose garment as cloth and carry it onto its bones, clear of the body and the floor (the runner's own: it uses numpy, which the add-on's safe mode refuses) | walk |
| `toon.py` | draw the scene the comic way: flat tones, simplified colors, an ink line that stays the same width on screen | comics |
| `face_swap.py` | put a drawn expression on the front of a rigged character's head; it turns with the head | comics |
| `garment.py` | check a base body against the clothed character (pictures, then meshes), lay it on, and cut each hiding garment out by three votes | base body (background only) |
| `follow.py` | move the base body and garments the way the finish moved the mesh | base body (background only) |

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
just tidy runs/<run folder> run                 # needs the run clip too (`just runs` makes it); adds <version>-run.glb
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
| `bake.py` | "materials": bakes the shader into plain textures; "onto": bakes color, metal, roughness and a normal map from the full mesh onto a lighter one (`"reach"` and `"fill"` for a block-out that sits off the full mesh; by group for one with gear; `"repaint"` for flat colors) | 5–60 s, freezes Blender |
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
- Skin counts as "under gear" where gear lies within 4% of the object's
  size straight out from it, or drape.py hid the face. The edge between
  flat skin and textured skin runs through faces, not along them.

- The base body rests on the second picture keeping the figure still.
  `garment.py` measures that and stops when it didn't; it can't repair it.
- A garment the same color as what is under or beside it (a black coat
  over black leggings) leaves the cut to distance, which loses cloth that
  hugs the body. The edit asks for teal base clothing in that case.
- Several hiding garments are told apart only by the height their slots
  sit at.
- Where garment points were lifted onto a fuller body, the cloth's two
  walls can cross and the surface there looks crumpled up close (the
  dancer's left hip).
- `follow.py`'s fit finds quarter turns only; anything else needs the move
  `stand.py` kept.

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
weights checked both in Blender and in the written file; the run profile, skipped with no clip
and made for real from a stick-figure clip (troll, lizardkin); the fit of the skeleton
(`rig_check.py` on the troll, Lincoln, the dancer and the ninja walking and running, made by
the real runner: where the neck starts and the head turns, joints in the middle of their
limbs, the trunk's volume over each clip, how much a knee shakes against its foot and how far
its hinge swings in a frame); the contact step, each time
against the same motion with it off (the dancer's heels, the troll's real run, and a made-up
wall and post: the leg must clear the wall and the hand land on the post); and the clothes:
drape.py on the troll, then Lincoln, the ninja, Roosevelt, the troll and
the pirate made low poly, mid poly and walking by the real runner and
measured with `scripts/cloth_check.py` over every frame (skin through
cloth, the gap, the cloth bones' limits and seam, triangles). And painted
clothes: Roosevelt's singlet and tights painted on by the real runner and
the same outfit worn by Lincoln, both walking and going through the routine
(no skin through, the collar's gap in motion, feet on the floor, the trim,
each hem in the same place on both). And the base
body: `garment.py` on a made-up figure whose every face is known
(`scripts/base_fixture.py`: the skirt must come out exactly, a shrunk body
be laid back on, a moved picture and a different pose be turned down) and
on the flamenco dancer when her runs are there (the fit, each vote, the
skirt whole to the waistband), then `follow.py` after a finish done the
way the Blender step does it. About ten

cloth, the gap, the cloth bones' limits and seam, triangles); and the
colors: the troll's kilt must not take the color of the leg behind it,
the skin under it must be skin, and its flat colors must be its
texture's (`scripts/bake_check.py`). About eleven
minutes in all. With `--keep DIR`
the face cases leave `lincoln-face-before.png`, `lincoln-face-painted.png`
and `lincoln-faces.png` (Lincoln's face painted from his head sheet, and his
head in the game and mid-poly versions made from a copy of his run, with the
walk), `troll-head-compared.png` and
`pirate-head-compared.png`: front and side of the reference, each head, and
the fitted head as wire over the reference. `just check-safe` checks every script against safe
mode.
