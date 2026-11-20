---
name: tidy-mesh
description: Clean up, optimize, retopologize or resize a generated 3D mesh (TRELLIS.2 output or any messy GLB) in Blender. Use when asked to tidy a mesh, fix its topology, make it lighter or game/web/AR-ready, make LODs or quad topology, bake its materials or textures, or produce a named profile (hero, quads, web, game, mobile) of a finished object in runs/.
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
  the underbite, tusks, and skin, socket, beard and hair colors. `"found"`
  says whether each came from the texture, the shape, or a guess.
- **It shows its work.** It draws a wire box with a line at each feature's
  height, `Look: face`. Aim `look` at it: a line that misses its feature
  means that row's height needs setting by hand.
- **`build.py` builds it.** The `"head"` piece goes into `"parts"` like any
  loft. It comes out as 150 to 240 triangles, mirrored across the face's
  center line: a brow ledge, sunk dark sockets with the eye set back in
  them, a nose with a tip and wings, a mouth band, and optional ears and
  tusks. `"kind"` is `"creature"` (heavy brow, scowl, broad nose and mouth)
  or `"human"`. Sizes never drop below what reads at this scale, and
  `"bold"` pushes brow, nose and sockets out farther.
- **Check it up close.** `preview.py` with `"view": "front"` or `"side"`
  and a `"box"` renders a close-up straight on; `match.py` with a `"box"`
  scores that spot alone.

On the troll, from measurements alone: 188 triangles for the head with its
tusks (14% of 1,372), and inside the head box the detailed mesh strays
1.2% from the model typically and 2.0% at worst, against 2.9% and 3.5% for
the hand-built head. A loose box that takes in the chest and shoulders finds
the same features within 2 cm. On the pirate (a person, with a beard, an
eye patch, a hat and a white collar) it finds the eyes under the brim, the
nose and the beard, and builds a 180-triangle head.

Where it goes wrong, and what to do:

- **A hat or helmet.** Seen from the front, a brim hides the forehead and
  is as dark as the eyes. Stop the box at the brim; the hat is its own piece.
- **Hair or a beard over the face, an eye patch.** The dark bands are no
  longer the eyes and mouth. `"found"` will say `"shape"` or `"guess"`;
  look at the guide lines and set the rows by hand.
- **No texture, or eyes no darker than the skin.** It goes by shape alone:
  the nose, chin and tusks are still found, the eyes are placed in the
  hollow above the nose or, failing that, where eyes usually sit. That
  works on a head with clear relief (the troll's built head, measured
  again, lands within 2 cm) and is a guess on a smooth one.
- **A head turned or tipped.** It expects a level head looking straight
  along one axis, which is how the pipeline draws characters.
- **Ears are not found**, only built: add `"ears": True` (or sizes) when the
  description names them. The same goes for horns, which are separate
  pieces (a tube each).
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
| `export.py` | write one object as a GLB and read the file back to prove nothing else came along | finish, low poly |
| `measure.py` | size a part without its neighbors, and slice it into rows of middle and half-width | parts, low poly |
| `split.py` | paint or cut the parts from boxes: several boxes per part, tilted boxes, parts that wrap around | parts |
| `face.py` | find the brow, eyes, nose, mouth and chin on a character's head and print it as a `"head"` piece for `build.py` | low poly (characters) |
| `build.py` | block out a low-poly version from a list of lofts, tubes, lumps, boxes and a head; join, color and check it | low poly |

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
| `bake.py` | "materials": bakes the shader into plain textures; "onto": bakes color, metal, roughness and a normal map from the full mesh onto a lighter one | 5–60 s, freezes Blender |
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
its old head (and the pirate's, if that run is there). With `--keep DIR`
the face cases leave `troll-head-before-after.png` and
`pirate-head-reference-and-built.png` to look at. `just check-safe` checks every script against safe
mode.
