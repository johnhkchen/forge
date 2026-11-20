# Forge

Type an idea, get a finished 3D object: a cleaned-up mesh, a `.blend` file, and a render.

```
just make "a brass diving helmet"
```

## What happens

Each AI does the part it's good at:

1. **Opus writes a short brief.** It picks one object, describes it in a few sentences, and lists its materials and real-world size. (`baml_src/1_describe`)
2. **Codex draws it.** You get one object, centered, on a plain gray background, which is the kind of picture image-to-3D handles well. (`baml_src/2_picture`)
   A character whose clothes hide its body (a long skirt, a robe) is drawn a second time without them, so the body under them can be made, not guessed. See "A real body under the clothes". (`baml_src/2b_undress`)
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
| `mesh.glb`, `mesh.json` | step 3 (raw TRELLIS.2 output, plus timings) |
| `base/image.png`, `base/mesh.glb`, `base/body.glb`, `base/cut/<garment>.glb`, `base/cut.json`, `base/sheet.png` | steps 2 and 3, only for a character whose clothes hide its body: the second picture, the body built from it, that body laid on the clothed mesh, each hiding garment cut out, the numbers, and pictures to judge it by |
| `render.png`, `final.glb`, `scene.blend`, `polish.json` | step 4 |
| `base/final.glb`, `garments/<garment>.glb`, `base/follow.json` | step 4, same characters: the body and garments moved to where the finished object stands |
| `parts.json`, `lowpoly.glb`, `lowpoly.json`, `lowpoly_build.json` | step 4 (the parts, the low-poly block-out, and the recipe it was built from) |
| `profiles/<profile>.glb`, `.png`, `-wire.png`, `.json` | step 5 |
| `gait.json`, `profiles/lowpoly-walk.glb`, `profiles/midpoly-walk.glb` (each with a `.json`) | step 5, characters: how it walks, and the two versions with a skeleton, a walk, and clothes that move with it |
| `run/ask.json`, `run/clip.json`, `run/loop.json`, `profiles/lowpoly-run.glb`, `profiles/midpoly-run.glb` (each with a `.json`) | step 5, characters, when Kimodo can be reached: the sentence and speed, the clip as made, the loop cut from it, and the two versions running |
| `props.json` | step 6 (which prop goes where, and the folder each one was made in) |

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
| `just gait <run folder>` | only ask Opus how the character walks (weight, stealth, swagger, stiffness) |
| `just runs [runs folder]` | give every character that walks a run: one sentence each to Kimodo, cut into a loop, played on its low-poly and mid-poly versions |
| `just run-asks [runs folder]` | only show the sentence and speed each character would be asked to run with; sends nothing |
| `just tidy <run folder> run` | only the Blender part of a run, once its clip is there |
| `just walk-strip <file.glb> <out.png> [side or front]` | a picture of the walk (or the run), eight moments side by side |
| `just bake-check <run folder> <file.glb>…` | measure a dressed character's colors against the detailed mesh: does each piece show its own cloth, and the body skin |
| `just cloth-check <file.glb>…` | measure a dressed character: how much skin comes through its clothes over the walk, how far they sit off the body |
| `just shoot [shot]` | make a shot from its plan in `motion/shots/`: Opus lays it out, our poses are placed, MotionBricks fills in the movement (and Kimodo makes any beat that is a sentence), it is measured and filmed |
| `just cast <shot> <character run> [prop run] [clip]` | put a character (and what it carries) in a finished shot; `clip` names the cut (`hero`, or `hero-mixed` for a second one) |
| `just clip-to-gallery <shot> <character run> [clip]` | copy the shot's clips into the character's folder, so the gallery shows a "Hero" button; a second cut gets a button of its own |
| `just poses` | rebuild the pose library from `scripts/motion/author_poses.py`, checking each pose as a body |
| `just motion-health`, `just motion-info`, `just motion-selftest` | is the motion endpoint up, what is it running, and does it work end to end |
| `just text-info` | what the sentence-to-motion model has fetched and loaded (the first call fetches it) |
| `just recipe <run folder>` | for a run from before recipes were kept: get its block-out's recipe back from the transcript, so `midpoly` can be made |
| `just gallery` | look at every object, raw vs cleaned-up, on this Mac or a phone on the same Wi-Fi |
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
| `lowpoly` | old-school real-time look (think early Warcraft or RuneScape) | a few hundred to ~1,500 triangles, built by Claude from simple shapes | one 256 px texture with shading painted in, or flat colors per part when the style asks |

The quads come from [AutoRemesher](https://github.com/huxingyi/autoremesher) (MIT): mostly rectangular faces in regular loops, a little denser where the shape curves. Install it once with `just autoremesher`. Each profile records how far it strays from the full mesh (`shape` in `<profile>.json`); typically under 1% of the object's size.

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
3. **The poses are ours.** `motion/poses.json` holds thirteen of them (crouch, look left, sneak step, sprint stride, vault, landing, draw, hero stance...), each written by hand in `scripts/motion/author_poses.py` as "hips here, this foot there, that hand on the wall". Each is checked as a body before it is saved: no limb overstretched, no knee bending backwards, feet flat where they stand, weight over the feet. `just poses` rebuilds them.
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

The detailed versions (`hero`, `quads`, `web`, `game`, `mobile`) still have the clothes as part of the body. They come from the picture, and the picture shows the character dressed.

In a Claude Code session here, ask for any of these ("make a game version of the kettle") and Claude uses the skill, either in the background or step by step in your open Blender.
