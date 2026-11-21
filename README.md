# Forge

Type an idea, get a finished 3D object: a cleaned-up mesh, a `.blend` file, and a render.

```
just make "a brass diving helmet"
```

## What happens

Each AI does the part it's good at:

1. **Opus writes a short brief.** It picks one object, describes it in a few sentences, and lists its materials and real-world size. (`baml_src/1_describe`)
2. **Codex draws it.** You get one object, centered, on a plain gray background, which is the kind of picture image-to-3D handles well. (`baml_src/2_picture`)
   A character whose clothes hide its body (a long skirt, a robe) is drawn a second time without them, so the body under them can be made, not guessed. See "A real body under the clothes". (`baml_src/2b_undress`) A character's head is then drawn again, large, from the front, three-quarter and side, so its face can be painted sharp later. (`baml_src/2_picture`)
3. **TRELLIS.2 turns the picture into a textured mesh.** It runs on your own RunPod endpoint, which scales to zero, so it costs nothing while idle and has no daily cap. (`baml_src/3_mesh`, `worker/`)
4. **Claude finishes it in Blender.** It fixes orientation, size, origin and normals, sets the materials, adds a ground plane, lights and a camera, then renders, checking its own work against the picture as it goes. Then it marks out the object's parts (lid, knob, spout...) and builds a low-poly version from simple shapes; a character's face is measured off the detailed head first, so it keeps its brow, eyes, nose and mouth, and its clothes and armor are built as separate pieces over a whole body, so a game can take them off, then laid on that body so they follow its shape. The work that repeats in every run (bringing the mesh in, measuring a part, staging, exporting) is done by ready-made scripts Claude fills in, not rewritten each time. (`baml_src/4_polish`, `.claude/skills/tidy-mesh`)
5. **Sized versions for wherever it's going.** A background Blender rebuilds the mesh as clean quads and bakes the detail into textures, once per profile (`web`, `game` and `lowpoly` by default; a character also gets `midpoly`). (`baml_src/5_profiles`, `.claude/skills/tidy-mesh`)
   A character's low-poly and mid-poly versions then learn to walk: bones placed from its own shape, joints that stop where a body's do, and a walk worked out from its leg length and bulk, plus one question to Opus about how it carries itself. The troll lumbers; the ninja creeps. Its clothes move with it, and a kilt or a hood swings. Its feet stay on the floor, not in it, whatever its shoes. (`baml_src/7_walk`)
   And to run, when the motion worker can reach Kimodo (see "Running"): one sentence about how this character runs becomes a looping run on the spot. If Kimodo can't be reached the run is skipped with a note and the rest is made as usual. (`baml_src/9_run`)
6. **Props, if you ask.** A character is drawn and built with empty hands. With `props=held`, each thing it carries (an umbrella, a sword) gets a brief of its own and goes through the same steps as a small object, and the character's folder notes which hand it goes in. (`baml_src/6_props`)

The whole pipeline is BAML (the new language, toolchain pinned in `baml.toml`). Steps 1 and 4 go through the `claude` CLI and step 2 through the `codex` CLI, so they use your subscriptions, not metered API keys.

Every run gets its own folder, `runs/<time>-<name>/`:

| File | From |
|---|---|
| `brief.json` | step 1 |
| `image.png` | step 2 |
| `heads/sheet.png` | step 2, characters: the head again, large, from three sides |
| `mesh.glb`, `mesh.json` | step 3 (raw TRELLIS.2 output, plus timings) |
| `base/image.png`, `base/mesh.glb`, `base/body.glb`, `base/cut/<garment>.glb`, `base/cut.json`, `base/sheet.png` | steps 2 and 3, only for a character whose clothes hide its body: the second picture, the body built from it, that body laid on the clothed mesh, each hiding garment cut out, the numbers, and pictures to judge it by |
| `render.png`, `final.glb`, `scene.blend`, `polish.json` | step 4 |
| `base/final.glb`, `garments/<garment>.glb`, `base/follow.json` | step 4, same characters: the body and garments moved to where the finished object stands |
| `parts.json`, `lowpoly.glb`, `lowpoly.json`, `lowpoly_build.json` | step 4 (the parts, the low-poly block-out, and the recipe it was built from) |
| `profiles/<profile>.glb`, `.png`, `-wire.png`, `.json` | step 5 |
| `gait.json`, `profiles/lowpoly-walk.glb`, `profiles/midpoly-walk.glb` (each with a `.json`) | step 5, characters: how it walks, and the two versions with a skeleton, a walk, and clothes that move with it |
| `run/ask.json`, `run/clip.json`, `run/loop.json`, `profiles/lowpoly-run.glb`, `profiles/midpoly-run.glb` (each with a `.json`) | step 5, characters, when Kimodo can be reached: the sentence and speed, the clip as made, the loop cut from it, and the two versions running |
| `props.json` | step 6 (which prop goes where, and the folder each one was made in) |

Sets live outside `runs/`, in `sets/<name>/` (see "Sets"), and are kept with the code.

A step is skipped if its file is already there, so `just resume runs/<folder>` picks up where a run stopped.

## Setup

You need the `baml`, `claude`, `codex`, `uv`, `gh` and `just` CLIs, and Blender. Run `just autoremesher` once for the quad profiles, and `just forge-addon` once (then restart Blender) so Claude's Blender tools are one-liners.

1. **Blender add-on (one time).** Run `just blender-addon`, then `just blender`. The add-on starts its server whenever Blender opens.
2. **TRELLIS.2 worker image.** Push this repo to GitHub. `.github/workflows/worker.yml` builds `worker/` into `ghcr.io/<you>/trellis2-worker`. It only installs prebuilt wheels, so the build is quick and needs no GPU.
3. **RunPod.**
   - Copy `.env.example` to `.env` and fill in your API key and the EU-RO-1 network volume ID.
   - Add a RunPod secret `hf_token`. The DINOv3 image encoder is gated on Hugging Face, so your account needs access to it.
   - Run `just endpoint` and put the new endpoint's ID in `.env`.
4. Run `just check`, then `just make "…"`.
5. **Only for shots** (see "Shots" below): the same push builds `motionbricks_worker/` into `ghcr.io/<you>/motionbricks-worker`. Run `just motion-endpoint`, put the new endpoint's ID in `.env` as `MOTIONBRICKS_ENDPOINT_ID`, then `just motion-selftest`. The first job waits a few minutes while the worker fetches NVIDIA's model onto your volume and gets it ready for the GPU; after that a job takes a couple of seconds.
6. **Only for runs, and for shots with a beat made from a sentence**: the model that reads the sentence is built on Meta's Llama 3, and Meta asks each person to accept its license. Open [the model's page](https://huggingface.co/meta-llama/Meta-Llama-3-8B-Instruct) with the Hugging Face account your `hf_token` secret belongs to, read the license, and ask for access. Once Meta says yes, run `just text-info`: the worker fetches about 17.5 GB onto your volume (once) and says what it loaded. Until then a text beat stops with a message saying exactly this, a run is skipped with "run skipped: Kimodo not available", and everything else works as before. Once it has loaded, `just runs` gives every character its run.

The first job on a fresh endpoint downloads whichever weights the volume doesn't already have, about 17 GB at most. After that, a job takes about a minute on an RTX 4090.

## Commands

| | |
|---|---|
| `just make "<idea>"` | the whole pipeline |
| `just make "<idea>" held` | the same, and then each thing the character carries as an object of its own (`all` adds hats, backpacks and the like) |
| `just resume <run folder>` | continue a stopped run (`just resume <run folder> held` to add its props) |
| `just make "<idea>" none "ruffled skirt"` | the same, and make a real body under the gear you name, whatever the brief says (`none` in its place turns that off) |
| `just undress <run folder> ["<gear>, <gear>"]` | only that: draw the character again without the gear, build the body, cut the gear out. Leaves Blender alone |
| `just base-shots <body.glb> <out.png> <garment.glb>…` | a sheet of pictures: the body, the clothes and both, front and quarter |
| `just props <run folder>` | only write the briefs for a finished character's props; `just resume` each prop's folder to make it |
| `just brief "<idea>"` | only step 1, to try ideas |
| `just check` | compile and run the offline tests |
| `just health` | is the RunPod endpoint up? |
| `just tidy <run folder> <profile>…` | make sized versions: `hero`, `quads`, `web`, `game`, `mobile`, `midpoly`, `lowpoly` |
| `just tidy <run folder> walk` | give a character's low-poly and mid-poly versions a skeleton and a walk |
| `just head-sheet <run folder>` | only draw a character's head sheet (front, three-quarter, side) from its picture; the next `just tidy` paints the face from it |
| `just face-sheet <run folder> <out.png>` | a character's face in every version of the run, next to its picture: front, three-quarter and side |
| `just face-check <out.json>` | measure that sheet: where eyes, nose, mouth and chin sit against the picture, how lopsided, how sharp, and whether a face is found at all |
| `just gait <run folder>` | only ask Opus how the character walks (weight, stealth, swagger, stiffness) |
| `just runs [runs folder]` | give every character that walks a run: one sentence each to Kimodo, cut into a loop, played on its low-poly and mid-poly versions |
| `just run-asks [runs folder]` | only show the sentence and speed each character would be asked to run with; sends nothing |
| `just tidy <run folder> run` | only the Blender part of a run, once its clip is there |
| `just walk-strip <file.glb> <out.png> [side or front]` | a picture of the walk (or the run), eight moments side by side |
| `just bake-check <run folder> <file.glb>…` | measure a dressed character's colors against the detailed mesh: does each piece show its own cloth, and the body skin |
| `just rig-check <file.glb>…` | measure a walking or running character: where each joint sits in the body around it, how much volume each part keeps over the clip, how much each part shakes |
| `just cloth-check <file.glb>…` | measure a dressed character: how much skin comes through its clothes over the walk, how far they sit off the body |
| `just shoot [shot]` | make a shot from its plan in `motion/shots/`: Opus lays it out, our poses are placed, MotionBricks fills in the movement (and Kimodo makes any beat that is a sentence), it is measured and filmed |
| `just cast <shot> <character run> [prop run] [clip]` | put a character (and what it carries) in a finished shot; `clip` names the cut (`hero`, or `hero-mixed` for a second one) |
| `just set-check [set]` | is a standing set sound? Marks on the floor and clear of the furniture, seats the right height, every camera holding its marks (see "Sets") |
| `just set-build <set>`, `just set-backdrop <set>`, `just set-card <set>` | build a set's block-out from its data, have Codex paint its backdrop, take its picture for the gallery |
| `just set-from-run <set> <run folder>` | use an object you already made as a set's geometry |
| `just shoot <take>`, then `just cast <take> runs "" <clip>` | a take on a set with several people in it (`studio-guest-entrance`): every role's motion, then the cast, filmed from every camera of the set |
| `just world-check` | is the world sound: every place a sound set, no footprints overlapping, every toon on a mark, the newest epoch up to date |
| `just buy-house <toon>` | Opus designs a house for a toon from their own brief, and it is built as a set (a new folder each time) |
| `just world-places`, `just world-stock`, `just world-toons` | build the world's places from data, bring in light copies of the runs' objects, stand the toons up in their poses |
| `just world-epoch <name> "<title>" "<caption>"` | save the world as it is now as an epoch |
| `just world-shots <port>` | pictures of the gallery's world view, phone and desktop, into `evidence/world/` |
| `just diorama <name>` | build a diorama from `dioramas/<name>/diorama.json`: the toons posed and placed on a wooden base, as one light `.glb`, with its pictures and its card (see "Dioramas") |
| `just diorama-check [name]` | is a diorama's plan sound, before building it? |
| `just diorama-draft <name> [camera,camera]` | try a pose or a camera: quick small pictures into `dioramas/<name>/draft/`, and what the build would measure. Writes nothing else |
| `just diorama-load <name>`, `just diorama-shots <port>` | what the front page fetches for a diorama; pictures of the front page, phone and desktop, with every byte it loaded, into `evidence/diorama/` |
| `just clip-to-gallery <shot> <character run> [clip]` | copy the shot's clips into the character's folder, so the gallery shows a "Hero" button; a second cut gets a button of its own |
| `just comic "<premise>" [strip or scroll] ["<cast>"] ["<places>"] [name]` | make a comic: Opus writes it, one background Blender draws it, code letters it and lays out the page |
| `just comic-again <name>` | draw and letter `comics/<name>/comic.json` again after editing it by hand; asks no model |
| `just comic-kit` | what a comic can be made from right now: cast, poses, clip moments, expressions, places |
| `just expressions <who>` | give a cast member its eight drawn faces (one Codex image), cut and fitted to its head |
| `just comic-style <out folder> <file.glb>…` | a character before and after the comic style, side by side |
| `just comic-poses <file.glb> <out.png>` | every comic pose on one character, to check a new pose |
| `just poses` | rebuild the pose library from `scripts/motion/author_poses.py`, checking each pose as a body |
| `just motion-health`, `just motion-info`, `just motion-selftest` | is the motion endpoint up, what is it running, and does it work end to end |
| `just text-info` | what the sentence-to-motion model has fetched and loaded (the first call fetches it) |
| `just recipe <run folder>` | for a run from before recipes were kept: get its block-out's recipe back from the transcript, so `midpoly` can be made |
| `just auto-body <run folder> <out folder>` | give a finished character a body with anatomy, without Claude: its landmarks are found, a body is built from them, and its own head and gear go back on. Writes into the out folder, never the run |
| `just anatomy-check <run folder> <out.png> low=<file.glb>…` | measure low-poly and mid-poly bodies against the detailed mesh: landmarks, proportions, outlines, cross-sections, and a sheet to look at |
| `just gallery` | the newest diorama out front, then the world, every object raw vs cleaned-up, and the comics, on this Mac or a phone on the same Wi-Fi |
| `just transcript <run folder> <step>` | read the Blender code Claude ran in a step (`polish`, `parts`, `lowpoly`) |
| `just test-tools` | try the Blender scripts on real runs in a background Blender (your open Blender is left alone) |
| `just check-safe` | check that the Blender scripts will get past the add-on's safe mode |

## Profiles

TRELLIS.2 hands back an even soup of ~300k triangles. The `tidy-mesh` skill (`.claude/skills/tidy-mesh/`) turns it into what a modeler would hand over: real parts only, quads that follow the form, and materials baked into textures a GLB can carry.

| Profile | For | Mesh | Textures |
|---|---|---|---|
| `hero` | close-up renders, printing | 200k triangles, cleaned | 2048 |
| `quads` | keep modeling it | ~15k quads | 2048 + normal map |
| `web` | web pages, product viewers | ~8k quads, Draco | 1024 WebP + normal map |
| `game` | real-time games | ~4k quads, Draco | 1024 WebP + normal map |
| `mobile` | phones, AR | ~3k quads, Draco | 512 WebP + normal map |
| `midpoly` | phone games on today's hardware | the low-poly pieces built again rounder and smooth, about 3,000 to 8,000 triangles, Draco | 1024 WebP + normal map |
| `lowpoly` | old-school real-time look (think early Warcraft or RuneScape) | a few hundred to ~1,500 triangles, built by Claude from simple shapes | one 256 px texture with shading painted in (a character's head has a second one), or flat colors per part when the style asks |

The quads come from [AutoRemesher](https://github.com/huxingyi/autoremesher) (MIT): mostly rectangular faces in regular loops, a little denser where the shape curves. Install it once with `just autoremesher`. Each profile records how far it strays from the full mesh (`shape` in `<profile>.json`); typically under 1% of the object's size.

## Faces

A face is the first thing anyone looks at and the first thing this pipeline got wrong. TRELLIS.2 gets a head's shape about right and its texture wrong: eyes come out as dark smudges, lips as a blur, glasses as black discs. The whole-figure picture can't help much, because the face is a tenth of its height. And the quad remesh used to hand a character's head back in shreds. So, for a character:

- **Codex draws the head again** from the first picture: front, three-quarter and side, each several times larger than the face was (`heads/sheet.png`).
- **The face is painted onto the detailed mesh from the front view**, like a slide projector in front of the head, before any version is baked. The tool finds the head, then slides and scales the picture until it sits on it. If the two don't agree it paints nothing, and falls back to the first picture.
- **The head is rebuilt whole**: cut off under the chin as one piece, wrapped in one skin, and that skin is remeshed. Every remeshed piece is checked for tears, on characters too, and one that comes back torn is wrapped and tried again.
- **The head gets a texture of its own** in each sized version, so a face is a few hundred pixels across, not sixty.
- **In the walk, the head and what sits on it follow the head bone alone**, so the jaw doesn't bend with the neck.

`just face-sheet` draws every version's face next to the picture and `just face-check` measures them. Weak spots: the detailed `final.glb` itself keeps TRELLIS's face (make `hero` for a painted one); the paint is a front view, so ears and temples are still TRELLIS's; glasses and eye patches are painted flat onto the face as well as built; and a head sunk between the shoulders (the troll) isn't found without a block-out to say where it is. More in the skill's notes.

## Bodies with anatomy

Built by hand from tubes, a low-poly body came out as stacked tubes: no shoulder cap, no waist between ribcage and pelvis, no calf, a mitten for a hand, a box for a foot. So the body is no longer built by hand:

- **The landmarks are found, not guessed.** A tool reads the detailed mesh (or the real body under hiding clothes, when the run has one) and finds the chin, neck, shoulders, armpits, chest, waist, hips, crotch, elbows, wrists, knees and ankles, how long the hands and feet are, and the body's own shape all the way along. Where a landmark doesn't show (an elbow inside a straight sleeve) it sits where a body usually has it, and says so.
- **One "body" piece builds the lot**: a trunk with ribcage, waist and pelvis, a neck, arms with a shoulder cap, hands with a thumb, legs with a knee and a calf, feet with a heel and toes. About 900 triangles, with three rings close together at each elbow and knee, which is where the skeleton then puts those joints.
- **Style is a few numbers on that piece**: chunkier, slimmer limbs, a bigger head, or cleaner shapes that follow the picture less closely.
- **Mid poly adds anatomy, not only roundness**: five rings at each elbow and knee and twice as many everywhere else, each laid on the detailed mesh, so the chest, shoulder blades and kneecaps it has come through.
- **The landmarks stay in the recipe** (`lowpoly_build.json`, `landmarks` and `joints`) for whatever needs them next.

Claude now adds the head, hair and gear to that body and checks it against a short anatomy list. `just auto-body <run folder> <out folder>` does the body for a finished run without Claude, keeping its head and gear; `just anatomy-check` measures any version against the detailed mesh (landmarks, proportions, outlines, cross-sections) and draws a sheet. What is weak, and the numbers on eight characters, are in the skill's "Anatomy" section; the sheets are in `docs/anatomy/`.

## Gear comes off

A game needs the pirate without his hat, or in different boots. So on the two versions Claude builds from simple shapes (`lowpoly` and `midpoly`), a character is not one lump:

- **The brief lists the gear**: every piece of clothing, armor and equipment, each marked as worn, attached (a hat, a backpack) or held.
- **The body is built whole.** Take the coat off and there is a chest under it, not a hole.
- **Each gear item is its own mesh in the file**, named `gear: navy coat`, `gear: boots`..., next to `body`, and tagged with its kind and where it goes. Hide one, or swap in another.
- **Five named points say where props attach**: `socket: hand_right`, `socket: hand_left`, `socket: head`, `socket: back`, `socket: hip`.
- **Things carried in a hand are never part of the character.** They are made as objects of their own when you ask (`just make "<idea>" held`), and `props.json` says which hand each goes in.

In the gallery, a character's Low poly and Mid poly versions have a row of its gear (tap a piece to take it off) and a "Where props go" button.

## A real body under the clothes

A long skirt hides the legs. Image-to-3D only sees the skirt, so whatever it puts under it is a guess, and everything built on that guess (the low-poly body, the rig, the walk) inherits it. So for a character whose clothes hide its body, the body is made for real and the clothes go back on:

1. **The brief says what hides the body** (`hidden_by`): a long or full skirt, a robe, a coat past the knee, a hooded cloak. Tight tops and trousers hide nothing and are left alone. You can also name the gear yourself: `just make "<idea>" none "ruffled skirt"`, or `just undress <run folder> "ruffled skirt"` on a run that already has its mesh.
2. **Codex draws the same picture again without it.** It is asked to change one thing: the hiding clothes come off, and what they hid is shown in plain skin-tight black. Everything else stays where it is, to the pixel if it can.
3. **TRELLIS.2 builds that picture too.** That mesh is the base body.
4. **The two are checked against each other, by measuring.** The figure must not have moved between the pictures, and where no clothes cover it (head, arms, feet) the two meshes must agree. On the flamenco dancer they sit 0.14% of her height apart. If they don't line up, the picture is edited once more with what went wrong written into the request; if that fails too, the step stops and prints the numbers, and (unless you named the gear yourself) the run carries on the old way.
5. **Each hiding garment is cut out of the clothed mesh.** Every face gets three votes and is garment when two agree: it lands where the two pictures differ; its color is one the garment has and the rest of the figure doesn't (this reaches the back, which the picture can't see); it stands off the base body. Then the cut is carried up to where the colors change, scraps are dropped and small holes closed. The dancer's skirt comes out whole up to the waistband, with no tights or shoes in it.
6. **After Claude finishes the mesh in Blender, the body and garments make the same move** (turned, sized, stood on the floor) in a background Blender. You see no extra work in yours.
7. **The low-poly version is measured on them.** Claude measures the body pieces on the base body and each hidden garment on its own cut, where before it could only measure cloth and guess.

In the gallery, such a character has a "Without clothes" button on its raw and detailed versions: the body that is really there, and a chip per garment to put it back on. `base/sheet.png` in the run shows the body, the clothes and both, with every face colored by which votes it got.

It costs one more picture and one more mesh (cents, about a minute each). The tools are `garment.py` and `follow.py` in the skill.

**What is weak.** It rests on Codex keeping the figure still while it changes the clothes; it did on the dancer, and the check catches it when it doesn't. A garment the same color as what is under it (a black coat over black leggings) gives the picture and color votes little to go on. Several hiding garments are told apart only by height (a hood above a robe). The detailed versions (`web`, `game`...) are still made from the clothed mesh alone.

## Clothes sit on the body

Built from tubes and boxes, a pair of trousers is a stiff pipe around a leg: a gap at the cuff, a thigh poking through on every stride, and a kilt that swings like a bucket. So after the block-out, and again in every version made from it:

- **Each piece is laid on the body.** Tight things (trousers, sleeves, a shirt, wraps) are moved onto the body under them, a centimeter off it; what is worn over something else sits one step further out. Loose things (a kilt, a coat's skirts, a hood) are fitted only where they rest on the body, down to the belt or to where the body falls away, and keep their hang below that. Boots, hats and buckles keep their shape.
- **Skin under clothes isn't drawn.** The body faces a piece hides are meshes of their own, `body under: wool trousers`, each tagged with the gear that hides it. Show one only while that gear is off. On, no skin can come through, because it isn't there; off, the body is whole. A dressed character also draws fewer triangles than before.
- **Clothes bend with the body.** Every point of cloth gets the same pull from the bones as the skin right under it, so cloth and skin fold together.
- **Loose cloth hangs and swings.** A kilt, a coat's skirts or the back of a hood get a few short chains of bones. After any motion is made (the walk, a shot), each chain is trailed behind the body like weights on strings, kept out of the thighs, held inside its joint limits, and saved as plain keyframes, so it plays anywhere a `.glb` does. The walk still loops without a seam.

- **Clothes carry their own colors.** The detailed mesh is the picture's: one skin, dressed. When its colors are copied onto the pieces, a kilt copies only kilt and the body only skin. Where a piece has nothing of its own to copy (a hem longer than the real one, a lining, the skin under a coat) it is filled with that piece's own colors, not with the leg behind it. Flat-color low-poly versions get their colors the same way, one per piece.

Claude says how each piece is worn when it builds it (`"fit": "tight"`, `"loose"` or `"stiff"`); for older block-outs it is worked out from the piece. The tools are `drape.py`, `cloth.py` and `swing.py` in the skill; `scripts/cloth_check.py` measures a finished file: how much skin comes through over a whole walk, and how far the clothes sit off the body. `scripts/bake_check.py` measures its colors against the detailed mesh, piece by piece.

## Walking

Those two versions also come with a skeleton and a walk (`profiles/lowpoly-walk.glb`, `midpoly-walk.glb`): 21 bones with plain names (`hips`, `thigh_l`, `forearm_r`...), a few more for a tail, each joint with its limits written in the file. Gear pieces follow the same bones (loose cloth has a few of its own, `cloth_...`) and the prop points ride on them. The walk is worked out from the model, not drawn by hand, so each character gets its own. In the gallery, press "Walk" to see it on the spot. `.claude/skills/tidy-mesh/bones.json` says what each bone is called in SOMA (NVIDIA MotionBricks) and Mixamo, so motion from elsewhere fits the same bones; see Running and Shots.

**The skeleton fits the body.** Every joint is put in the middle of its limb's own cross-section. The neck starts at the collar, just above the shoulders, and the head turns about a point inside the skull, level with the ears, so a nod doesn't fold the throat. A knee points where the motion's knee pointed, and a heel that has to lift to spare an ankle lifts smoothly, so the legs don't squirm. Each bone also carries a simple capsule sized from the body around it, for a physics engine to make a ragdoll from. `just rig-check <file.glb>` measures all of it on a finished file: where each joint sits, how much volume each part keeps over the clip, and how much each part shakes.

## Running

A run can't be worked out from a tape measure the way a walk can, so it is asked for in words. `just runs` does it for every character that walks:

1. **A sentence and a speed for each.** Both come from the brief and from the same four traits as the walk. "A huge person runs forward in a slow, heavy, lumbering run, with pounding steps and a stiff upper body" for the troll, at 2.5 m/s; "A stocky person runs forward stealthily in a low crouch, with light, quick, quiet steps" for the ninja, at 3.4. The speed follows the leg's length, as the walk's does. `just run-asks` shows them without sending anything.
2. **Kimodo makes the motion.** That is NVIDIA's sentence-to-motion model, on the same RunPod worker as the shots. Each character gets six seconds along a straight line at its own speed, five times over on different dice, because the same sentence can come out well or oddly. Each take is scored (does the loop close, do the legs keep a steady beat, is the head thrown back, do both arms swing) and the best is kept. About three seconds of GPU a take. A character's clip is kept and only made again if its sentence or speed changes.
3. **The clip is cut into a loop.** Two frames a whole number of strides apart, where the body is most alike (every joint, how fast it is moving, which feet are down), become the two ends. The end is eased into the start, the last frame is made the first again, and the travel over the ground is taken out so it runs on the spot. The speed is written down.
4. **It goes onto the character** the way a shot does: its own skeleton and joint limits, planted feet kept planted, loose cloth swinging at running speed, a tail following the hips. Out come `profiles/lowpoly-run.glb` and `midpoly-run.glb`, with gear and prop points on the bones like the walk files.

In the gallery, a character with a run has a "Run" button beside "Walk", and a "Runs at" line.

What is weak: a sentence steers Kimodo only a little (Roosevelt's "proudly" comes out chin-up with his arms behind him), a foot in the air stops a little short of its spot on the troll's short legs, and everyone's legs turn over at about the same beat. The numbers and the rest are in the skill's "Running" section.

Kimodo needs the access described in Setup, step 6. Without it nothing breaks: `just runs` says "run skipped: Kimodo not available" and why, and a pipeline run carries on without the run. The parts that don't need Kimodo are tested without it (`python3 scripts/motion/test_run_clip.py`, part of `just check`).

## Shots

A walk is one loop. A shot is a few seconds of something happening: the ninja waits on a roof edge, sneaks along a ledge, sprints, vaults a wall, lands, and draws its sword.

```
just shoot hero-rooftop
just cast hero-rooftop runs/<the ninja> runs/<its katana>
```

How a shot gets made:

1. **You write the plan in words**, in `motion/shots/<name>.json`: what happens when, and where the walls and ledges are.
2. **Opus lays it out.** It turns the plan into a shot list: which pose, where along the path, how fast, for how long. It never writes a joint angle. (`Choreograph` in `baml_src/8_motion`)
3. **The poses are ours.** `motion/poses.json` holds eighteen of them (crouch, look left, sneak step, sprint stride, vault, landing, draw, hero stance, and for a set: stand, sit, shake hands...), each written by hand in `scripts/motion/author_poses.py` as "hips here, this foot there, that hand on the wall". Each is checked as a body before it is saved: no limb overstretched, no knee bending backwards, feet flat where they stand, weight over the feet. `just poses` rebuilds them.
4. **MotionBricks fills in the movement between the poses.** That is NVIDIA's motion model, running on a second RunPod endpoint of your own (`motionbricks_worker/`). It also scales to zero.
5. **The result is measured and filmed** on a plain box figure: how far the feet slide, whether anything goes through the floor or the wall, whether the hand is on the wall top, how far each beat ends from where it was planned (`checks.json`, `motion.mp4`, `strip.png`).
6. **`just cast` puts a real character in it.** The motion goes through the same skeleton, joint limits and planted feet as the walk, its clothes sit and swing the same way, and the sword rides on the character's back until the draw, then in its hand. The character's own shoes, shins and hands are kept out of the roof and the wall, and a hand the plan pins (the wall top in the vault) is put on its spot. `just clip-to-gallery` adds a "Hero" button for it in the gallery.

Everything a shot makes lands in `shots/<name>/`. A step whose file is already there is skipped, so you can delete `motion.mp4` to film again without making the motion again.

**A beat from a sentence.** A beat in a shot list can say `"source": "text"` and give one sentence in place of poses: "A person sneaks forward in a low crouch, stepping slowly and quietly along a narrow ledge." NVIDIA's Kimodo makes the motion, in the same worker. We still say where it goes: it is held to the shot's path every frame, it can start in one of our poses, and a hand can be put on a spot (the wall top) at a moment. `hero-rooftop-mixed` is the same shot cut this way: the crouch, the landing and the draw are our poses; the sneak, the run and the vault are three sentences.

**Joining the pieces.** A shot like that is made one beat at a time. Where two beats meet, MotionBricks is shown the last four frames of the first and the first frames of the second, and makes the stretch between them: 17 frames between two beats of ours, 25 after a beat from a sentence (it takes the place of the last 4 or 12 frames of the one and the first 13 of the other). The second beat is then picked up whole and set down where that stretch ended, so nothing jumps. Every request is kept under a fingerprint of its content in `shots/<name>/cache/`: change one beat's sentence and only that beat and the joins at its two ends are made again. `checks.json` says how smooth each join is. (`scripts/motion/timeline.py`; `python3 scripts/motion/test_timeline.py` tries all of it with no GPU.)

**What is ours and what is NVIDIA's.** The poses, the plan and the path are ours. The model that moves between them is NVIDIA's MotionBricks (code Apache-2.0, model under the NVIDIA Open Model Agreement, which allows commercial use). The worker image holds none of NVIDIA's files: on its first boot the worker fetches the pinned release (v0.2.0) onto your network volume. NVIDIA also ships sample motion clips under an evaluation-only license. The worker fetches one of them for `just motion-selftest` and for nothing else; no clip is ever read when a shot is made, and none is in this repo. Kimodo is the same story: its code is Apache-2.0, and the one model the worker uses, Kimodo-SOMA-RP-v1.2, is under the NVIDIA Open Model License (commercial use allowed; its SMPL-X model is research-only and is not used). It reads the sentence with LLM2Vec (MIT) on top of Meta's Llama 3 8B Instruct (Llama 3 Community License: commercial use allowed, with Meta's conditions, and each account must accept it). All of it is fetched onto your volume at pinned revisions and checked by sha256; none of it is in the image, and Kimodo's own sample motions are deleted right after the fetch.

**One motion format.** Whatever makes a motion, it is kept the same way (`motion.json`): 30 frames a second, joints by their SOMA names, and for each frame where the hips are, how each joint is turned, and which feet are down. `scripts/motion/soma_to_plain.py` turns that into what `animate.py` plays on our characters. It looks joints up by name, so a file with more joints than it needs (fingers, say) works too.

**Room for more.** The worker sorts jobs by kind (`inbetween` for MotionBricks, `text` for Kimodo), and each model gets its own Python setup inside the image. Kimodo starts only when a job asks for it, so a shot made only from poses never waits for it. A third model is one more setup, one more file and two lines. In a shot list each beat says where its motion comes from (`poses` or `text`; `walk`, our own walk, is named for later).

**What is weak.** Neither motion model can see the set, so in the raw motion a shin clips the wall and a foot dips under the roof; the checks say by how much. Casting a character cures what moving a leg, an arm or the hips can cure, and pins the feet, which drift while planted. It cannot turn a run through the wall into a vault: in the mixed cut the shins still cut 7.5 cm into the wall and the hand ends 25 cm from the wall top. And in the landing the ninja's hand hangs about 20 cm over the roof, because its knee is kept out of it. The numbers are in the skill's "Contact" section. Our hand-written poses are not what the model learned from, so the motion between them is stiffer than motion capture. A "sprint" that has to fit the roof is closer to a run. A sentence gives you a motion, not the motion: Kimodo knows walking, running, sneaking, fighting and everyday moves well and has seen little parkour, and each sentence is at most ten seconds.

## World

Everything lives in one world, the way toys only ever live in one child's room. The gallery shows it whole: every place on one ground, at true size, like the full miniature set of a stop-motion film. Nothing is filmed anywhere that isn't a place in it.

```
just gallery                    # then open World: #/world/epoch-0
just world-check
just buy-house flamenco-dancer
```

**What stands in it now (Epoch 0).**

| Place | What it is | Who is there |
|---|---|---|
| Theodore's grass | a big plot of open grass, a few trees and rocks, one bench | Roosevelt |
| The boxing house | a timber hall around the ring (the `ring` set stands inside it), a bar, a brew house, a beer garden on the grass | Lincoln, the pirate |
| The settlement | the troll's stone den and the lizardkin's sun house, a fire they share, their stall with the kettle, the teapots and the bread | the troll, the lizardkin |
| The spawn spot | the gachapon machine, the landing ring, the BUY HOUSE pedestal | |
| The ninja's stage | his photo stage (the `studio` set): a sitter's mark, a row for a group, a photographer's mark | the ninja, with his pinhole camera |
| The dancer's house | Casa de la Rosa: the house she asked for, with her stage and her microphone | the dancer |

Around them is the developer's plain grey floor, with a few grey one-metre cubes and a "TODO" or two: what hasn't been built yet.

**`world.json` says where things are, and nothing else does.** Each place is an ordinary set (see Sets, below), and a set never knows where it stands. `world.json` puts each one down with one line, `{"set": "grass", "at": [0, 13], "facing_deg": 0}`: turn the set until its front faces that way, slide its origin there. Marks, cameras, blocks and the mesh all move together. It also says who stands on which mark, in which pose, and where the story's wondrous artifacts are. `just world-check` reads it and says what is wrong in words: two footprints that overlap, a place off the edge of the ground, a toon on a mark that isn't there.

**Epochs.** An epoch is the whole world saved at one moment, with a title and a one-line caption: `world/epochs/epoch-0.json`. When the world changes, `just world-epoch epoch-1 "A title" "A caption"` saves a new file. Old ones are never edited, so the gallery's timeline can step through them like a time-lapse.

**The world view** (`#/world/epoch-0`, or `#/world/epoch-0/boxing-house` to arrive at a place):

- the whole world from a little above; drag to walk round it, pinch or scroll to come closer;
- a name on every place. Tap a place (or its name in the row above) and the camera glides there;
- at a place: who is there, which artifacts, and **Open this place** for its own page with marks, cameras and shots to play. **Marks** is off until you press it;
- a timeline of epochs, with room for the next.

**Walk around.** Press "Walk around" (or open `#/world/epoch-0/walk`) and you are Roosevelt, on Theodore's grass, seen from behind and a little above:

- on a keyboard, WASD or the arrow keys walk and Shift runs; drag to look round, scroll to come closer;
- on a phone, push the thumb stick to walk and push it to its edge to run, or tap the ground to walk there; drag anywhere else to look round;
- the world is solid: walls, furniture, the ring and the other toons are in the way, and the camera never ends up behind a wall. The dancer's stage can be stepped up onto; the ring and the boxing house roof cannot yet (no steps to them);
- walk into a place and a small card names it, says who is there and opens it. Come close to a toon and they say hello. Come close to the gachapon, the BUY HOUSE pedestal, the kettle, the bread, the ninja's camera or the dancer's microphone and the story's line about it shows;
- "Stop walking" goes back to the view from above.

His feet don't slide: the walk and run clips play on the spot and each says how fast it covers the ground (1.31 and 3.26 m/s for him), so the body is moved at exactly the clip's speed times how fast the clip is playing. Standing still is made in the page from the walk itself, with a slow breath. Nothing of this is fetched until you ask to walk: then one script, one style sheet and his two low-poly files, 0.66 MB. "Walking as: Roosevelt" opens a list of every toon that has a walk and a run; the others say "coming soon", and switching one on is adding its name to `READY` in `gallery/walkabout.js`. `just world-walk` tries all of it in a headless Chrome at phone size.

It is made to open fast on a phone. The first view fetches 24 small files, 1.9 MB, about 20,000 triangles in all: each place's block-out, the toons standing still with no skeleton, nothing that needs a decoder. What is small or heavy waits until you come close to its place: the kettle and the bread, the ring's full mesh, the hall's painted wall. The page says how much it has loaded, under the view. `just world-load` lists the files; `just world-shots` takes the pictures in `evidence/world/`.

**The places are built from data.** `scripts/world/places.py` writes each one as a set: boxes for what is in the way, a few simple pieces for what is only looked at (a roof as a stack of boxes, a tree as a trunk and four lumps), flat colors, no textures. `just world-places` builds them in a background Blender. The gachapon and the BUY HOUSE pedestal are built the same way. The ring, the kettle, the bread, the microphone and the ninja's camera are light copies of their runs (`just world-stock`); the toons are their low-poly versions frozen in a pose (`just world-toons`).

**BUY HOUSE.** In the story, a toon who saves enough presses the developer's big round button and gets a house to their own specification. Here that is `just buy-house <toon>`: Opus reads the toon's own brief and what the story says about them, and designs the house they would want, as a floor plan in plain rectangles: its style, its rooms, its colors, where the stage and the microphone go, which way it faces. Code checks the plan (rooms inside the house and not overlapping, one stage, one practice floor, colors that are colors) and, if it can't be built, shows Opus what is wrong and asks once more. Then `scripts/world/build_house.py` turns the plan into a set with marks and cameras, builds it, and checks it. Asking again makes a different house in a folder of its own; `world.json` says which one stands in the world. The dancer's is `sets/casa-de-la-rosa/`: `design.json` is what Opus drew, `design_cost.json` what it cost (one ask, 32 seconds, 3,183 tokens out; the CLI put it at $1.58).

**The ninja's stage.** The studio is the shadow ninja's own photo stage, and what hangs behind its window is always a real place in the world: `backdrop_options` in its `set.json` names the boxing house, the grass, the settlement and the dancer's house, each a picture taken through that place's own camera (`just studio-backdrops`). Its page in the gallery has a row to swap them.

**What is weak.** The places are block-outs: boxes and lumps in flat colors, charming from a distance and plain up close. The hall has no roof and the houses have none either, so you can see in. Toons stand in one pose each and don't move. Marks are flat: a mark on the stage or in the ring knows how high its floor is, but nothing can walk up to it. The world view lights everything with one sun, so a place looks a little different there than on its own page.

## Dioramas

The portraits and the comics are the world the way the toons imagine it. A **diorama** is the other layer: the toys themselves. It is one moment of the story, built from the real game assets and stood on a wooden base with a brass plate, like a collector's piece on a shelf in the basement. Think of the Lego Movie: the world in the child's head, and the table in the basement it is played on. A diorama shows the table.

```
just diorama meet-the-cast        # bind, pose, place, measure, write the .glb and the pictures (about 15 seconds)
just diorama-draft meet-the-cast the_cast,roosevelt     # quick pictures while you change a pose
just gallery                      # the newest diorama opens the front page
```

**The first one is "Meet the cast"** (`dioramas/meet-the-cast/`): the photo session on the ninja's stage, a breath before the shutter.

| Who | Where | Doing what | Version |
|---|---|---|---|
| The ninja | the `photographer` mark | behind his pinhole camera on a little tripod, right hand on it, left hand up: hold still | web |
| Lincoln | the back row, on the band riser | standing very straight, hands folded | web |
| Roosevelt | beside him on the riser | one arm flexed, the other waving at somebody off the base: the only one not looking at the lens | web |
| The dancer | the `sitter` mark, front and centre | a flourish, at her microphone | web |
| The troll | the right end of the row | holding a very small teacup | web |
| The lizardkin | at the troll's side | at attention, carrying the kettle | web |
| The pirate | the `group_1` mark | tipping his tricorn | web |
| The villager | by the wing flat, at the edge | peeking in with a small hello, just arrived | web |

Behind them hangs the boxing house, the one place they all share. Everyone is their **web** version: the detailed mesh with the painted face, about 20,000 to 28,000 triangles each. The camera, the kettle and the microphone are their web versions too.

**A web version has no skeleton, so it borrows one.** Each toon's web mesh is bound to the skeleton of its own mid-poly file (or its low-poly one, for the troll, the lizardkin and the pirate, who have no mid poly). Every point of the web mesh takes the weights of the nearest spot on that rigged mesh, blended across the triangle it lands on. A web mesh comes in thousands of small patches whose borders only touch, so points in the same place are treated as one point (or a seam would open the moment an arm moved), the weights are blended with their neighbours eight times to take the steps out, and each point keeps its four strongest bones. Then the skeleton is posed exactly as before.

The build measures every bind: how many times its own length each edge is pulled to by the pose. A bind is sound if no edge is pulled past 5 times its length and at most 1% of edges past twice; a toon whose bind is not sound is built from its rigged version instead, and the build says so. In "Meet the cast" all eight are sound and nobody fell back:

| Toon | Skeleton from | Worst edge | One edge in a thousand | Edges over twice | Longest pull | (the rigged version's own worst) |
|---|---|---|---|---|---|---|
| Ninja | mid poly | 2.17x | 1.67x | 0.034% | 4.5 cm | 1.86x |
| Lincoln | mid poly | 2.88x | 1.95x | 0.095% | 4.5 cm | 1.69x |
| Roosevelt | mid poly | 2.22x | 1.58x | 0.010% | 2.8 cm | 1.90x |
| Dancer | mid poly | 2.15x | 1.46x | 0.006% | 2.9 cm | 1.79x |
| Troll | low poly | 4.22x | 3.04x | 0.563% | 15.7 cm | 1.98x |
| Lizardkin | low poly | 4.75x | 2.38x | 0.164% | 7.2 cm | 2.04x |
| Pirate | low poly | 3.14x | 1.97x | 0.093% | 6.0 cm | 1.91x |
| Villager | mid poly | 2.03x | 1.41x | 0.005% | 2.4 cm | 2.70x |

The three on low-poly skeletons stretch most, because a low-poly mesh's weights are coarse; the troll's is across his shoulders and back, where his arms come down from the T-pose.

**`diorama.json` is the whole plan**, and it is meant to be edited by hand:

```json
{
 "title": "Meet the cast", "epoch": "epoch-0", "number": 1,
 "caption": "The ninja's first group photo, a breath before the shutter. Everyone is looking at the lens, except Roosevelt.",
 "set": {"name": "studio", "backdrop": "boxing-house", "keep": {"x": [-5.5, 1.15], "z": [-0.2, 6.05], "top_m": 3.5}, "dressing": ["plant"]},
 "poses": {"tip_hat": {"about": "one hand up to the brim of a hat, a small nod", "bones": {"upper_arm_r": [0, 22, -42], "forearm_r": [0, -36, -116]}}},
 "paint_px": 1024, "maps": "color", "prop_px": 512,
 "props": {"camera": {"run": "handmade-pinhole-box-camera", "file": "profiles/web.glb", "scale": 2.0}, "tripod": {"built": "tripod"}, "teacup": {"built": "teacup", "scale": 2.0}},
 "toons": [
  {"toon": "ninja", "run": "shadow-ninja", "version": "web", "pose": "shutter", "mark": "photographer", "looks_at": "dancer",
   "holds": [{"prop": "camera", "hand": "right", "grip": "top"}]},
  {"toon": "roosevelt", "run": "roosevelt-wrestler-1890s", "version": "web", "pose": "flex_and_wave", "at": [-2.6, 1.4], "on": "band riser",
   "faces": "ninja", "looks_at": [6.0, 1.5, 5.5]}
 ],
 "free_props": [{"prop": "tripod", "under": "camera"}],
 "cameras": {"front": {"about": "From the front of the shelf", "round_deg": 24, "above_deg": 17, "lens_mm": 50, "fstop": 5.6, "focus": "dancer"}},
 "stills": ["front", "over_his_shoulder", "the_cast", "roosevelt"],
 "plinth": {"margin_m": 0.3, "height_m": 0.85, "toy_scale": 12}
}
```

- **The set is cut like a cake.** `keep` says which slice of a standing set stays on the base, and `backdrop` names one of the stage's own backdrops (a real place in the world).
- **A toon** names its run, a version (`web`, or `midpoly` or `lowpoly` as they are), a pose, and where it stands: one of the set's marks, or a spot (`at`), maybe `on` something like the riser. It can face somebody (`faces`) and turn its head to somebody or something (`looks_at`). A pose is a name from `motion/comic_poses.json`, one written in the diorama's own `poses`, or a moment of a clip (`"walk@0.4"`).
- **Props go where hands are.** What a toon `holds` is put in that hand; what stands `beside` it is put on the floor next to it. The tripod stands `under` the camera and is built as tall as it needs to be, so the hand, the camera and the tripod always meet.
- **Cameras** are either put somewhere (`at`, `aim`) or given a direction (`round_deg` round the front, `above_deg` up) and backed off until what they frame fits. The first one in `stills` is the hero, and the card.
- **The base** is sized to the slice, with a brass plate that says the title and the epoch. `toy_scale` only sets how soft the background goes in the pictures: a 1:12 toy photographed up close.

**What the build checks**, and refuses to call finished if any fail: nobody stands in anybody else or in the set; every pair of feet is on its floor; every held prop is in its hand and touches its holder only there; everything else stands on the floor or on what is under it; nothing hangs over the edge of the base; and every face shows from the front camera (someone marked `"peeks": true` may be half hidden). The numbers are kept in `build.json`.

**What it writes.** `diorama.glb` is everything on the base in one file with no skeletons: Draco-packed, pictures as WebP, each toon's paint at 1024 px (512 for its head and for props), and the toons' color only (`"maps": "all"` keeps their bump and shine maps too). "Meet the cast" is 243,985 triangles and 3.24 MB; with every map it would be 5.53 MB, for a little more grain in cloth and skin. The pictures are taken first, with every map at full size. `stills/` holds a picture through each camera, taken on a shelf in front of a plain warm wall, with a small copy of each; `card.png` is the first, small.

**The front page** of the gallery opens with the newest diorama (the highest `number`) as the **State of the world**: the thing itself to turn over, at a gentle angle, swaying slowly until you touch it; its title, caption and epoch; a row of other angles to fly to; its pictures. The world card sits beside it (below it on a phone). When a second diorama is made, this one moves down to **Earlier moments**, and each has a page of its own (`#/diorama/<name>`).

Opening the front page cold on a phone fetches 4.5 MB before the first screen is ready: the diorama 3.24 MB and its four small pictures 0.12 MB, three.js and the mesh decoder 0.31 MB, the page and its lists 0.26 MB, fonts 0.08 MB, and 0.47 MB of pictures from further down the page. `just diorama-shots` measures it again and takes the pictures in `evidence/diorama/`.

**What is weak.** Hands are mittens: a prop is put at the palm, nobody grips, and the ninja's hand rests on his camera's rope handle more than on its shutter. Poses are turned bone by bone and tried by eye with `just diorama-draft`; nothing solves an arm to reach a thing. A borrowed skeleton is only as good as the mesh it came from: the troll, the lizardkin and the pirate are bound through low-poly weights and stretch two or three times as much as the others, and a web mesh's back, which no picture ever showed, is rougher than its front. The live file is nearly five times what the low-poly one was (3.24 MB against 0.68). The base's plate is real lettering but small: you have to come close to read it. The camera, the kettle, the cup and the microphone are sized by hand to read as toys (the camera is twice life size). The basement is one shelf and one wall.

## Sets

Desi Arnaz built a set that stayed up, put three cameras on it, and filmed a play a week. Talk shows still work that way, and so do we now: a **set** is a place of our own, built once and shot many times, so a new shot only has to say who stands where.

```
just set-check studio
just shoot studio-guest-entrance
just cast studio-guest-entrance runs "" guest-entrance
```

What a set keeps, in `sets/<name>/set.json`:

- **Its own frame and footprint.** Everything in the file is measured from the set's own origin, with a front (where a stage's cameras are) and an outline of the ground it takes up. Nothing says where the set is in the world, so a set can be picked up and put down as one piece.
- **Marks.** Named spots: a place to stand (`wings`, `monologue`, `centre`), a seat with its height and the spot in front of it you stand on (`desk_chair`, `couch_1`), a place to stand with a spot for a hand (`meet_left` and `meet_right`, which share one spot: a handshake). A shot names marks and never writes a coordinate.
- **Paths.** Which marks people walk between, with a turning point or two where a straight line would cut a corner of the desk. Moves are short, across a shallow stage.
- **Cameras that never move.** Three on the studio: `wide`, `host`, `guest`. One take is filmed from all of them at once, and you pick the cut afterwards.
- **Lights that never move**, so every shot on the set looks like the last one.
- **A backdrop.** What shows through the studio's window is one flat picture, standing a metre and a half behind the glass. Nothing out there is modelled. On the ring it is a painting by Codex; on the studio it is a picture of a real place in the world, and it can be swapped for another (see World).
- **Signs.** Small painted flats that belong to the place: the stall's sign, BUY HOUSE, the hall's painted wall.
- **What is in the way**, as plain boxes: the desk, the couch, the ropes. They are the same boxes a character's legs and hands are kept out of when it is cast.
- **Dressing, kept apart.** The mug, the microphone and the plant are small files of their own standing on named slots, the way a sword rides a character's sockets. Swap one or take it away without touching the set.

`just set-check` reads a set and says what is wrong with it, in words: a mark off the floor or too near the desk for a body, a seat too high for the sitting pose, a path that clips the couch, a camera that cuts off someone's head or has a post in front of it, a backdrop that doesn't fill the view.

**The first three sets** (the places in World, above, are sets too).

| Set | What it is | Made from |
|---|---|---|
| `rooftop` | the roof, ledge and wall of the hero shots | the blocks that used to be written inside each shot. Both hero shots now say `"set": "rooftop"`, and plan to the same requests as before, byte for byte |
| `ring` | the 1890s wrestling ring | the ring object from `runs/`: the floor is the mat, the ropes and posts are in the way, the corners and centre are marks, the steps are the way in |
| `studio` | the ninja's stage: desk and chair, a couch for two, a way on from the wings, a band riser, a sitter's mark and a photographer's, a big window | built from data. `just set-build studio` makes its block-out from the boxes in `set.json` and a few extra pieces in `build.json`, in flat colors, in a background Blender. No TRELLIS, one picture from Codex |

**Blocking by marks.** A beat in a shot list says `"to": "meet_left"` (walk there) or `"at": "couch_1"` (stay there: stand, sit down, get up, shake hands). The set then supplies what a shot used to write by hand: the path over the ground, how far along it each pose stands, which way it faces, how high the seat is, where the hand goes. Sitting is our own `sit` pose reached from our own `stand` pose; walking is one sentence to Kimodo, held to the set's path. A shot list that names no marks works exactly as before.

**Segments.** The things a show does every night are written once, as a segment (`motion/segments/`): a shot list per role, in marks. `guest-entrance` is the first: the guest walks on from the wings, the host gets up from the desk and meets them at centre, they shake hands, both sit. A take of it only says who plays whom:

```json
{ "set": "studio", "segment": "guest-entrance",
  "roles": { "host": "young-lincoln-frontier-wrestler", "guest": "roosevelt-wrestler-1890s" } }
```

A take can also swap a sentence (`"sentences": {"guest_walks_on": "A person strides forward, waving."}`) or a mark (`"marks": {"couch_1": "couch_2"}`). Everything it makes lands in `shots/<name>/`: a folder per role (each an ordinary shot, with its own `checks.json`), then `lowpoly-<clip>-<camera>.mp4` and a strip of stills for every camera, and `cast-<clip>.json` with what was measured.

**The handshake** is the first time two characters touch. Both marks share one spot; each plan puts that character's wrist a palm's length short of it; the same step that puts the ninja's hand on the wall top puts each hand there. With both on the stage, the film step measures how far apart the palms really are.

**In the first take** (Roosevelt and Lincoln, 16 seconds): Lincoln's wrist is on its spot to the millimetre; Roosevelt's arms are shorter and his stops 7.4 cm short, so their palms end up 12.6 cm apart (12.1 to 13.7 over the two seconds they hold it). A planted foot strays 0.3 cm at most, nothing goes more than 3 mm through the floor, and no joint leaves its limits. Seated, Lincoln is within a centimetre of his chair and Roosevelt floats 3.2 cm over the couch. Before any character is cast, the box figures land on their marks within 1 cm and their wrists are 14.6 cm apart against a planned 14. All of the motion took 34 jobs and 92 seconds of an RTX 4090: a few cents.

In the gallery, **Places** has a page per set: the set in 3D with its marks and cameras labelled, a row to look through each fixed camera, its dressing as chips, and a button for each shot filmed there that brings the cast on and plays it.

**What is weak.** Everyone on a set is brought to the same hip height, which is how they all land on the same marks; so short-legged Roosevelt comes out bigger than long-legged Lincoln, who was the taller man. The handshake only puts two wrists near one spot: the hands lie flat the way a hand rests on a wall, nobody grips, nothing pumps, and a short arm comes up short. A seat is a box, solid down to the floor: a body is kept out of it and can float a few centimetres above it, nothing pulls it down onto the cushion, and nothing knows about the chair's back. The floor is flat, so the ring's steps are a mark at mat height and its ropes have a gap where people come in. Where a walk meets a turn (leaving the handshake) the join is the roughest part of the motion. Nothing keeps two people out of each other, only out of the set. The cameras never move and nobody picks the cut: you get three films. Only the template has been shot; Opus has been shown how to block by marks but has not yet laid out a set shot for real. Filming is slow, about four minutes a camera.
## Comics

Webcomics got cheap by a few habits: one drawing "hand" used on everything, the same poses and framings again and again, plain backgrounds, a sheet of faces to swap, and words doing the work. We have 3D characters that can already stand, walk and vault a wall, so a panel is a frozen moment of one of them, drawn in one style. A panel takes about a quarter of a second to draw.

```
just comic "Roosevelt challenges patient young Lincoln to a friendly bout" strip "lincoln, roosevelt" ring
just comic "A very serious ninja crosses a rooftop, less quietly than planned" scroll ninja rooftop
```

How a comic gets made:

1. **Opus writes it as data, not pictures.** A list of panels: the framing, the place, who stands where facing which way, each one's pose and expression, the lines and who says them, a caption, a sound effect. It can only pick from what is on the disk (`just comic-kit` shows it). Code checks every name and that the words fit the room a framing leaves, and asks once more if not. (`baml_src/10_comic`)
2. **One background Blender draws every panel.** Each character is brought in once, frozen in a pose, stood on its spot, given its face, and drawn. (`scripts/comic/render_panels.py`)
3. **Code letters it.** Balloons, tails, captions and sound effects are laid over the picture as real text, not pixels. A tail points at its speaker's head and stops short of the face; no balloon covers a face. (`scripts/comic/lettering.py`)
4. **Code lays out the page.** `comics/<name>/page.html` is one file you can send to someone: a strip on a wide screen, one panel under another on a phone. `strip.png` (or `scroll.png`) is the same thing as a picture.

What a comic is made from:

- **The hand** is `toon.py` in the skill: flat color in three tones of light, each texture simplified to a few steps, and an ink line that stays the same width on screen near and far. The same on every character, prop and set, so low-poly roughness reads as a style. `just comic-style` shows any character before and after.
- **Poses** come from three places: thirteen written by hand for talking (`motion/comic_poses.json`: stand, talk, point, flex, shrug...), any moment of a walk, a run or a shot (`run@0.4`), and the named poses a shot was built from (`hero:vault_over`), which stay where the shot had them.
- **Expressions.** Codex draws each cast member's head eight times (neutral, happy, angry, surprised, sad, smug, talking, shouting), working from the head sheet and from our own comic-style picture of the 3D head, so the drawing has our look and that head's shape. One image per character. A panel projects the face it wants onto the front of the head. A masked character gets only its eyes. `just expressions <who>`.
- **Five framings**: wide, two-shot, single, close-up, and pov. For the first four the camera is fitted to the characters each time, with room left at the top for balloons.
- **Through someone's eyes (pov).** The camera sits at the eyes of the first character in the panel and looks where its head looks at that moment of its clip, or down at its feet, or at its hands (`"look"`). Its own head and neck are left out of the picture; its hands, knees, feet and what it holds are there when it would see them. Its thoughts have no head to point at, so they run along the bottom like a film's subtitles.
- **Someone who never speaks.** `"silent": true` in `comics/cast.json` (the shadow ninja) means that character gets no speech balloons, only thoughts and captions; the script is turned down if it gives them one.
- **A side story.** `"canon": false` in a comic's `comic.json` (`just comic ... canon=no`) keeps it outside the main story; the page and the gallery show a small "Side story" label. `comics/rooftop-ninja` ("First Light") is one: the ninja's rooftop run, seen through his eyes.
- **Places**: the wrestling ring and the shot's rooftop (by night and at dawn) stand in as backdrops, each with a painted picture behind it (one Codex image, reused in every panel); or a flat color for a talk panel. The painted picture is hung so its horizon is level with the camera's, so it slides out of view when a panel looks down.

`comics/<name>/comic.json` is the whole comic. Change a pose or a line by hand and run `just comic-again <name>`: nothing is asked of any model. The gallery has a Comics shelf; open one to read it.

**Sets.** A panel names a place, and optionally one of the place's cameras and marks. Today the places are stand-ins listed in `scripts/comic/kit.py`. When a `sets/<name>/set.json` exists it is used instead, through one function there (`from_set_json`); nothing else in the comics code reads a set file.

**What is weak.** Through his own eyes the ninja sees a lot of his own chest when he looks down, and nothing of himself when he looks ahead while running, because the arms of the clip swing low. A drawn face is a flat picture on a 3D head: fine from the front and three-quarter, wrong in a true profile, and it sits on top of real glasses or a mustache. The hand-written poses are stiff, with mitten hands and no fingers. Nobody holds anything except the ninja's sword in its shot. The lettering measures text by letter widths, not by a browser, so a line can come out a few pixels wider than planned. Two characters are never checked for standing inside each other. More in the skill's "Comics" section.

The detailed versions (`hero`, `quads`, `web`, `game`, `mobile`) still have the clothes as part of the body. They come from the picture, and the picture shows the character dressed.

In a Claude Code session here, ask for any of these ("make a game version of the kettle") and Claude uses the skill, either in the background or step by step in your open Blender.
