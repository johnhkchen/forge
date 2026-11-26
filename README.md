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

7. **Only for motion from a video** (see "From a video"): the same push builds `gemx_worker/` into `ghcr.io/<you>/gemx-worker`. Add `GEMX_IMAGE` to `.env` (it is in `.env.example`), run `just gemx-endpoint`, and put the new endpoint's ID in `.env` as `GEMX_ENDPOINT_ID`. It uses the same network volume and the same `hf_token` secret as the others, and adds about 7.5 GB to the volume the first time it boots.

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
| `just screen-motions [go] [ids]`, `just screen-play <run> [ids]` | the screen-test moves: what making them would cost (PAID with `go`, a few cents), and playing them on a character (free). See Screen tests |
| `just tidy <run folder> run` | only the Blender part of a run, once its clip is there |
| `just walk-strip <file.glb> <out.png> [side or front]` | a picture of the walk (or the run), eight moments side by side |
| `just bake-check <run folder> <file.glb>…` | measure a dressed character's colors against the detailed mesh: does each piece show its own cloth, and the body skin |
| `just rig-check <file.glb>…` | measure a walking or running character: where each joint sits in the body around it, how much volume each part keeps over the clip, how much each part shakes |
| `just cloth-check <file.glb>…` | measure a dressed character: how much skin comes through its clothes over the walk, how far they sit off the body |
| `just shoot [shot]` | make a shot from its plan in `motion/shots/`: Opus lays it out, our poses are placed, MotionBricks fills in the movement (and Kimodo makes any beat that is a sentence), it is measured and filmed |
| `just cast <shot> <character run> [prop run] [clip]` | put a character (and what it carries) in a finished shot; `clip` names the cut (`hero`, or `hero-mixed` for a second one) |
| `just video-add <file> [name] [start] [end]` | bring a video of yours (a dance, say): it is copied to `videos/<name>/`, which stays out of git. `start` and `end`, in seconds, keep only that stretch |
| `just video <name>` | turn that clip into motion for the characters: does whatever comes next, and stops where it needs you to choose who to follow (see "From a video") |
| `just video-formation <clip> <people> <from> <to>` | where several dancers of a clip stand relative to each other in those seconds, and the closest any two come |
| `just rehearse <shot or take> <folder>` | play a shot or a take through with stand-ins for the motion models, free, before `just shoot` pays for it |
| `just video-film <name> [clip]` | after `just cast video-<name> ...`: the character beside the clip, in step |
| `just video-test [runs folder]` | try all of that with no GPU: a drawn clip, a stand-in for the model, then the film and a character in a background Blender |
| `just video-stretch video-<name>` | the best 10 to 15 seconds of a clip's dance for a short film: lively, arms up, a turn, still at both ends, clear of any seam (see "A dance, restyled") |
| `just camera-path <shot> [camera]` | what a shot's moving camera sees of the figure, second by second |
| `just omni-film <name>`, `just omni-pack <name>` | draw every picture a restyle needs, then pack them into `exports/omni/<name>/`: films, pictures, prompts, a manifest. Free |
| `just omni-send <export> [edit, frames or generate] [go]` | send a packed segment to Gemini Omni Flash. Without `go` it prints exactly what it would send and what it would cost, and stops |
| `just omni-drift <export> <result.mp4> [go]` | did the restyle keep our dance? GEM-X reads the motion back off it and it is compared with ours. Without `go` it says what it would do and cost |
| `just gemx-endpoint`, `just gemx-health` | create the video worker's endpoint on RunPod (one time); is it up |
| `just set-check [set]` | is a standing set sound? Marks on the floor and clear of the furniture, seats the right height, every camera holding its marks (see "Sets") |
| `just set-build <set>`, `just set-backdrop <set>`, `just set-card <set>` | build a set's block-out from its data, have Codex paint its backdrop, take its picture for the gallery |
| `just set-from-run <set> <run folder>` | use an object you already made as a set's geometry |
| `just casting-office`, `just marble-seat <world folder>` | write and build the ninja's casting office; later, put a Marble world of its room inside it (see "The casting office") |
| `just shoot <take>`, then `just cast <take> runs "" <clip>` | a take on a set with several people in it (`studio-guest-entrance`): every role's motion, then the cast, filmed from every camera of the set |
| `just fight <fight> <left run> <right run>` | stage a fight from its script in `scripts/fight/fights/`: both fighters on one timeline, each baked through the same skeleton and limits as a walk, filmed from every camera of the set with hitstop, camera shake and flashes (see "Fights"). `just fight-test` tries the kit without Blender |
| `just skate <ride> <character run> [versions]` | put a character on the skateboard and have it ride a run on the halfpipe, from its script in `scripts/skate/rides/`: the board kept on the ramp, the rider baked on the board, filmed from every camera of the set (see "The halfpipe"). `just skate-test` tries the kit without Blender; `just skate-plan <ride>` only lays a run out |
| `just halfpipe-build`, `just skate-board` | build the ramp and the skateboard again from their numbers |
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
| `just gallery` | the newest diorama out front, then the world, the comics, the parts being cast, every object raw vs cleaned-up, and the clips you brought, on this Mac or a phone on the same Wi-Fi |
| `just impostor <run folder> [version]` | cut a rigged character into flat cards, one a bone, and picture each part from all around (`profiles/<version>-impostor-comic-joined/`); the gallery shows it at `#/cards/<run>` |
| `just impostor <run folder> painted --look pixel` (or `joe`) | the cards' sheet for another look: pixel art (small, few colours) or bold ink (`profiles/<version>-impostor-<look>-joined/`) |
| `just impostor-detailed <run folder>` | cards pictured from the detailed mesh instead: it is given the painted version's skeleton, then baked as pixel art, in the comic look and for bold ink |
| `just impostor-seams [take] [tag] [out]` | count what shows where two cards meet (dark lines, see-through gaps) against the real models posed the same, in every look; `--sheets old` for how it was, `--why` for what a gap comes from |
| `just seam-shots [take] [tag] [port]` | stills of a take's joints on the watch page: the stage, close on each of the cast, closer on an elbow and a knee, in every look |
| `just casting [role]` | how far each part being cast has come, and everyone trying out for it (see "Casting") |
| `just casting-plan <step> <role> [candidate]` | what a casting step would do and cost; starts nothing |
| `just casting-headshots <role> go`, `just casting-take <role> <candidate> go` | PAID: draw the headshots; build a shortlisted one into a character (then tape and judge it, free). Without `go` they only print the cost |
| `just casting-tape <role> <candidate>`, `just casting-judge <role> <candidate>` | free: a take's reel and chemistry read; its camera test |
| `just casting-revise <role> <candidate> [go]` | your notes become the next take: free for notes on moves or cards, PAID (with `go`) for a note on the look |
| `just tidy <run folder> sides` | the audition sides on a character: standing easy, a wave, a head turn, an arm overhead, a deep squat |
| `just impostor-judge <run folder> [version] [out]` | the same frames drawn as cards and as the real model, and how far apart they are; stills and films into `evidence/impostor/` |
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

## Screen tests

The same handful of moves for everyone in the cast, so any rig, and anyone trying out for a part, can be played through them and compared. Each move is made once from one plain sentence by Kimodo and kept as SOMA motion, so it belongs to no one character. Hand-made poses are stiff; these move the way people move, and push each joint through its range on the way.

```
just screen-motions                 # every job and what it would cost; sends nothing
just screen-motions go              # PAID: make them (a few cents), score every take, keep the best
just screen-play lincoln            # free: play them on a character, then line up everyone who has
just screen-rehearse <folder>       # free: the same with stand-ins for Kimodo, to try screen-play first
```

| Move | Sentence (short) | What it tests |
|---|---|---|
| Stand easy | stands idle, shifting weight foot to foot | holding still (shimmer), hips and ankles side to side |
| Walk out and back | walks forward, turns round, walks back (held to a path 2.4 m out and back) | a quick change of direction, a pivot on a planted foot |
| Jog on the spot | knees high, bent arms pumping | knees to the hip, elbows held bent, both feet off the floor |
| Deep squat | squats as low as it can, holds, stands | knees and hips folded all the way, ankles |
| Reach up | both arms straight up, stretch tall, down again | shoulders overhead, elbows straight |
| Look around | left, right, up, down | the neck alone, turning and nodding |
| Wave, right hand | waves hello with the right hand | a shoulder and elbow high beside the face |
| Wave, left hand | (the right-hand wave's mirror image, free) | the same on the left, for comparing the two sides |
| Pick something up | bends down to the floor | the spine folded forward, a hand to the floor |
| Turn round on the spot | a full circle (held to a heading that goes all the way round) | every side of the body, the feet stepping round |
| Arm circles | big circles, arms out | shoulders through their whole round, behind the body too |
| Forward lunge | a deep lunge and back | one knee deep in front, the other hip stretched open behind |
| Shrug and bow | stands up straight, shrugs, then bows deeply | the collar bones lifted hard, then spine and neck bending |
| Twist side to side | twists the upper body each way | the spine turning on the hips |
| Front kick | a high kick, back to a fighting stance | a hip folded high, balance on one foot |

The list is `motion/library/library.json`: each move's id, sentence, seconds (eight at most), why it is there, the joints it pushes, and what it must be seen to do (`asks`: the hips at least this far down, both hands over the head, at least 300 degrees of turn...). A move that has to get somewhere has a `path` too, keys of [seconds, x, z] or [seconds, x, z, heading] that Kimodo is held to every frame, as a run is held to its line. A `mirror_of` move is not asked for at all: it is another move's kept take, left for right.

**Five takes, the best kept.** As with a run, a sentence gives a motion, not the motion, so each is made five times on different seeds, one sentence a job (`scripts/motion/screen_motions.py`; `baml_src/9_run/screen.baml` sends the jobs). Every take is measured from its joints: a foot the model says is down sliding over the floor, the head flung about or thrown back, not starting and ending standing near the same pose, toes through the floor, and each of its `asks` it misses. A take that does everything asked always beats one that does not. The kept take is `motion/library/<id>/motion.json`, and every take's score and measures are in `scores.json` beside it. `python3 scripts/motion/screen_motions.py status` says what was kept and why.

**What it cost.** The first send was 14 moves, five takes each: 70 jobs, 445 seconds of motion, about 190 s of GPU at 0.9 s a job and 0.28 s a second of motion (the worker's own records of the runs). With the minute the worker idles afterwards that is about $0.08, or $0.09 if the worker has to wake and load the sentence encoder first, at the assumed $0.00031 a GPU second in `casting.py`. A volume that has never run Kimodo would fetch 17.5 GB first (`just text-info`, up to half an hour). The dry run says which applies, and an answer already in the cache (`motion/library/.cache/`, out of git) is never paid for twice.

**Playing them.** `just screen-play <run>` puts every made move on the character's low-poly and mid-poly versions, the same way its run goes on (`scripts/motion/apply_library.py`): its own skeleton and limits, planted feet, swinging cloth, a tail. Out come `profiles/<version>-screen-<id>.glb`, beside its walk. Its cards play the files of the version they ride (the low-poly one for most, the mid-poly one for the flamenco dancer), and the cards page lists them as "Screen test: ...". Each move also gets a line-up for the watch page, `#/watch/screen-<id>`: everyone who has played it, side by side across the studio stage at their own size, each in the version their cards ride (`shots/screen-<id>/`). The renderer's judges read a line-up like any take: `judge_seams.py --take screen-<id> --times ...` and `judge_joints.py --take screen-<id> --at ... --deep 1`. The casting reel names the same files as extra sides (clip kind `library`), and taping a candidate plays any it is missing.

**Tried without paying.** `python3 scripts/motion/test_screen_motions.py` (part of `just check`) makes every move with a stick-figure stand-in in five ways: done well, done by half, with sliding feet, with the head thrown back, never coming back to standing. The scoring keeps the one done well every time. The same stand-ins were played on Lincoln and the pirate in Blender.

**What the first real takes taught.** Ten of the fourteen did all they were asked. The other four were the sentence's fault, not the measures', and every take of each failed the same way: asked to walk "a few steps", turn and walk back, Kimodo walked ten metres in six seconds and turned round at the very end; "turns around in a full circle" gave a half turn (190 to 225 degrees); "waves with the right hand, then the left" waved the right only; "stretches, leaning left and right" raised the arms and never leaned. So the walk and the turn are now held to a path, the wave is the right hand alone with the left made as its mirror image, and the stretch is a plain reach up. Looking at every kept take as a strip of poses found one pass by luck: the shrug and bow's kept take slouched 33 degrees from the first frame and bowed six more, and the old measure counted the slouch. A bow is now measured from where the chest started, and a take only counts as starting or ending standing with its chest upright (within 25 degrees). (`python3 scripts/motion/screen_motions.py rescore` scores the answers on hand again after a measure changes; it sends nothing.)

**What is weak.** The asks' thresholds are still guesses at the edges: the kept look-around nods 25.2 degrees against an ask of 25, and the kept twist turns the chest 22 degrees against 20 (it turns the hips too). The side bend is left out: Kimodo would not lean. Moves with no path may wander a little; that is scored, not prevented. The moves are played in each character's own strides, so a short character's walk out and back covers less ground.

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

**Room for more.** The worker sorts jobs by kind (`inbetween` for MotionBricks, `text` for Kimodo), and each model gets its own Python setup inside the image. Kimodo starts only when a job asks for it, so a shot made only from poses never waits for it. A third model is one more setup, one more file and two lines. In a shot list each beat says where its motion comes from (`poses`, `text`, or `video`: a stretch of a clip, see "From a video"; `walk`, our own walk, is named for later).

**What is weak.** Neither motion model can see the set, so in the raw motion a shin clips the wall and a foot dips under the roof; the checks say by how much. Casting a character cures what moving a leg, an arm or the hips can cure, and pins the feet, which drift while planted. It cannot turn a run through the wall into a vault: in the mixed cut the shins still cut 7.5 cm into the wall and the hand ends 25 cm from the wall top. And in the landing the ninja's hand hangs about 20 cm over the roof, because its knee is kept out of it. The numbers are in the skill's "Contact" section. Our hand-written poses are not what the model learned from, so the motion between them is stiffer than motion capture. A "sprint" that has to fit the roof is closer to a run. A sentence gives you a motion, not the motion: Kimodo knows walking, running, sneaking, fighting and everyday moves well and has seen little parkour, and each sentence is at most ten seconds.

## From a video

A sentence gives you a motion, not the motion. When you want *that* dance, bring the video.

```
just video-add ~/Downloads/dance.mp4 summer-dance
just video summer-dance
```

`just video` does whatever comes next, and you run it again to carry on:

1. **The clip is made ready** on this Mac: the stretch you asked for, at 30 pictures a second. (`just video-add <file> <name> 12 40` keeps seconds 12 to 40.) You bring the file yourself; nothing here downloads a video.
2. **The cuts are found**, also here, with ffmpeg. An edited video jumps between cameras, and each stretch between two jumps is a shot.
3. **Everyone in each shot is found and followed.** This is the first step on your RunPod GPU: the clip is sent to your own endpoint once, and comes back as boxes, one per person per frame.
4. **You choose who to follow.** `just gallery`, then open the clip (`#/video/summer-dance`), on the Mac or your phone. Every shot shows a moment from it with a numbered box on each person. Tap the dancer, on the picture or on their small picture under it; "Skip this shot" leaves a shot out. Once you have tapped them in one shot, whoever wears the same colours in the other shots is offered ("Is it 1? Tap to say yes", or one button for all of them). Someone who looks like a mirror image of someone else is marked "might be a reflection". Say whether the camera stays put or moves, and Save.
5. **Their motion is made**, shot by shot, on the GPU: NVIDIA's GEM-X reads the body's movement off the picture, following the person you chose.
6. **The shots are joined into one motion** and written as a shot, `shots/video-summer-dance/`, like the ones `just shoot` makes. `checks.py` measures it.
7. **It is filmed**: a plain box figure doing the moves, next to the clip, in step, with the clip's sound (`videos/summer-dance/side-by-side.mp4`, and on the clip's page in the gallery).

Then it is a shot like any other:

```
just cast video-summer-dance runs/<character>
just video-film summer-dance
```

The first puts a character in it, through its own skeleton, joint limits and planted feet. The second films that character beside the clip.

Everything a clip makes is in `videos/<name>/` (`clip.mp4`, `shots.json`, `people.json`, `choice.json`, `motion/`), and a step whose file is there is skipped. Choose someone else in one shot and only that shot's motion is made again. `just video <name> cuts` (or `people`, `choice`, `motion`, `shot`, `film`) starts again from that step. If a cut was missed or found twice, fix `cuts` in `shots.json`, set `"by_hand": true`, and run `just video <name> people`.

**A stretch of a clip as one beat of a shot.** A shot list's beat can get its motion from a third place, beside our poses and a sentence: `"source": "video"`. So one shot can use all three, with MotionBricks making the join at every change:

```
{"name": "The routine", "source": "video", "seconds": 16.0,
 "clip": "candy-shop", "shot": 1, "from_s": 4.0, "to_s": 20.0, "at": "monologue", "drift": "flatten"}
```

`from_s` and `to_s` are seconds of the clip, as a player shows them; `shot` is counted from 1, as the clip's page counts. Where the dancer stands is the shot's business, not the video's: `at` a mark of the set they stand on it, facing the way the mark faces, whichever way the camera saw them. What the video keeps is how they move about from there. `"drift": "flatten"` takes out whatever they wandered over the stretch (or the camera crept), so they end on the mark; from one mark `to` another, the stretch is turned to travel that way. A join's tween takes the place of about half a second at each end of a piece, so the beat brings that much more of the clip on either side, and the stretch you asked for stays whole. `motion/shots/solo-candy-shop.json` is an example: wait in the wings (a pose), walk on (a sentence), the routine (the clip), a bow (a sentence), stand (a pose). Once `just video candy-shop` has made the motion:

```
just shoot solo-candy-shop
just cast solo-candy-shop runs/<character>
```

Where a clip was only split for its length (a take of over a minute, not a cut), a beat with no `shot` may run on from one part into the next.

**A crew.** A clip with several dancers can become several characters. `just video candy-shop "" 1:2,1:3,2:2,2:3` also makes the motion for persons 2 and 3 of both shots, and a beat that says `"person": 2` uses it. For them to dance *together* they have to stand to each other as the dancers did, and the motions alone do not say that: each person's comes back in a world of their own, drifting its own way. The picture does say it. So a take's video beats can share a `formation`:

```
"person": 3, "formation": {"people": [1, 2, 3], "at": "centre", "spread": 1.15}
```

The middle of the group goes on that mark, facing the house the way the dancers faced the camera, and each role is placed from it by where their dancer was in the picture: how far off from the height of their box against the height of their pose, how far to the side from where the box is. Only each one's place *in the group* is taken from the picture, smoothed over a few seconds (a camera that pans or zooms moves everyone alike, and is ignored); the quick part of how each one moves is their own motion's. What everyone did alike is not any one dancer's movement, so it is kept apart, as the group's: when everyone's standing foot slides the same way at once, nobody stepped and the picture moved, and that part is thrown out; the rest is the group really going somewhere on its feet, and it is kept. `"travel": 0.7` keeps only that share of it, for a stage too small for all of it. `spread` moves the places apart for characters broader than the dancers. `just video-formation candy-shop 1,2,3 5.4 53.0` prints where each one starts and ends and the closest any two come, which is what the set's marks for the walk on and the bow are written from. (`scripts/video/formation.py`)

`motion/shots/crew-candy-shop.json` is that, as a take on the ninja's stage (the segment `motion/segments/candy-shop-crew.json`): Lincoln out front, Roosevelt on the left of the picture, the pirate on the right. They wait in the wings, walk on one after another, dance 47 seconds of the routine in the clip's own formation (the two at the front change places near the end, as in the clip), bow together and stand easy. It makes no sound: the song is not ours.

```
just rehearse crew-candy-shop /tmp/crew     # free: the whole take with stand-ins for Kimodo and MotionBricks, and how close anyone comes
just shoot crew-candy-shop                  # the real one: 6 sentences and 18 poses-and-joins on RunPod; the routine itself costs nothing
just cast crew-candy-shop runs "" crew      # Lincoln, Roosevelt and the pirate, filmed from the stage's cameras
``` The shot list is written by hand for now; Opus is told the source exists and not to use it. (`scripts/video/beat.py`)

**Feet that are down stay down.** Motion read off a video slides: GEM-X's own feet creep while it says they are planted, a camera that pans or zooms is read as the dancer gliding, and a crew held to its formation is nudged all the time. On a stage that looks like skating. So after the motion is placed, each foot's stances are found (the model says it is down, it is near the floor and not travelling; or it is plainly lying still), and over a stance the foot is held on one spot: the ball if the toes carry it, the heel if only the heel is down, flat if both. A foot up on its ball is free to turn about it, so a pivot is still a pivot. The hips are carried by the feet that are down and each leg is solved to its foot, the knee bending the way it bent. Whatever was sliding the body then shows where it should: the next time a foot comes down, it comes down somewhere new. Drift becomes steps. A foot the model calls down while it is plainly travelling (a slide, a shuffle) is left as the dancer did it. A shot joined from pieces that has a video beat in it is held the same way once it is joined, so that where a dancer stands a hand's width off the mark the beats either side were planned on, the join takes it in a step and not in a slide. This is on for a clip's own shot and for every video beat; `"lock_feet": false` on a beat, or `FORGE_FOOT_LOCK=0` in front of a command, leaves the feet as they came, to compare. `python3 scripts/video/footlock.py <motion.json>` measures any motion both ways. (`scripts/video/footlock.py`)

**Joining across a cut.** A cut is the camera jumping, not the dancer. But each shot's motion comes back in a world of its own: where the dancer stands and which way they face start from nothing every time. So each shot is picked up whole and set down where the last one ended, facing the same way and still moving as it was, and the small jump in pose that is left is eased out over the next 8 frames. Inside a shot nothing is changed. Every frame of the film you kept is one frame of the motion, which is why the two can be watched side by side. `checks.json` lists each cut as a seam, with how big the jump was.

**What is ours and what is NVIDIA's.** The cut finding, the following of people from frame to frame, the choosing and the joining are ours. Reading a body off video is [GEM-X](https://github.com/NVlabs/gem-x) (code Apache-2.0; weights under the NVIDIA Open Model License). It writes the same SOMA skeleton Kimodo does, so its motion goes in where a sentence's does. People are found with the YOLOX person detector GEM-X's own guide points to (an OpenMMLab file, trained on the Human-Art pictures; look at its terms before selling anything made with it). As with the other workers, the image holds none of it: on its first boot the worker fetches GEM-X's code, its three models, the detector and the SOMA body onto your network volume at pinned revisions, checked by hash, and deletes GEM-X's sample films from its copy without reading them. The clips are other people's work: they stay in `videos/` on this Mac (not in git) and on your own volume, where one not used for two weeks is deleted.

**Trying it with no GPU.** `python3 scripts/video/test_video.py` (part of `just check`) draws a clip with cuts at known frames and runs every step on it, with a stand-in for GEM-X behind the worker's real front door: made-up boxes for people, and a made-up dance written the way GEM-X writes motion. `just video-test` also films it and puts a character in it in a background Blender.

**What is weak.**

- *Not yet run on the real model.* The worker has been written from GEM-X's code and guide and tested around a stand-in. The first real job will show whether its answer is read right. Each shot's conversion says how far our figure's hands, toes and head end up from GEM-X's own (`ours_vs_gemx_cm` in `shots/video-<name>/source.json`); a few centimetres is two bodies of different build, a lot means the two skeletons are being read differently.
- *Fast spins.* One camera sees one side of a body. In a spin the model has to guess the far side, and the person detector can lose the dancer for a few frames (their box is then carried through the gap). Expect the facing to wobble or lag in turns.
- *Mirrors.* A reflection is found as a person, which is why you choose. The "might be a reflection" mark is a guess from size, clothes and movement; it will miss some and will mark a second dancer at the back in the same outfit. If the dancer is hidden and only the reflection shows, following the reflection gives you the dance mirrored.
- *Cuts.* A fade or a dissolve can be missed or found twice. A cut that also skips ahead in time joins two unlike poses, and 8 frames of easing will not hide a big one. The dancer's place on the floor is only known inside a shot; across cuts it is carried, not measured, so a long edit drifts from where they really were.
- *A camera that moves.* "The camera stays put" is taken at its word: a pan or a zoom then shows up as the dancer sliding. "The camera moves" has GEM-X guess the camera's turning from the background; it cannot tell a camera that travels. (GEM-X's better answer, ViPE, is not installed.)
- *Several people.* The follower is simple. Two people who cross, in the same clothes, can swap boxes, and then the motion follows the wrong one from there to the end of the shot. Look at the "Early" and "Late" moments of a shot before you save.
- *A clip in a mixed shot.* The joins into and out of a dance are MotionBricks going between a walk and a dance pose in half a second; it has seen little dancing, so expect those to look stiffer than the rest. With `"drift": "keep"`, a dancer who ends a metre from the mark leaves the next join a metre to cover in that half second, and every beat after it stands that far off its plan (`plan_shot.py` says so when it plans). `flatten` spreads the correction evenly, which shows as feet sliding a little all through the stretch.
- *A formation.* How far each dancer is from the camera is read from the height of a box, which is good to a few tens of centimetres, less when the picture cuts off their feet. Left and right is good; front and back is rough. Holding everyone to their place in the group nudges them all the time; with their feet held, the nudging waits for a step, so a dancer can be 10 to 20 cm from their place in the group until they next lift a foot. The group's own travel is kept only as far as the stage has room (`travel`; the candy-shop crew needs 3.4 m of depth for all of it and the ninja's stage has 3, so it keeps 0.7 and still slides as one about 60 cm over the 47 seconds, against 119 before the group's part was told from each dancer's; with all of it, 31). The closest two dancers come is measured on a plain figure's joints, not on your characters' shoulders.
- *Feet and floor.* GEM-X's own floor creeps (up to 85 cm in half a minute on the candy-shop clip), so the floor is taken to be under the lower toe as it was in the few seconds around each frame; a slow rise onto the toes for several seconds would be flattened. Held feet are only as good as the stances found: where the model calls a foot down while it is in fact travelling, it is left alone, and where it misses a planted foot that is also creeping, the creep stays. To keep a nearly straight leg on a held foot the hips come down a little (up to about 10 cm on the candy-shop clip). Floor work (lying, rolling) will sit at the wrong height, because the floor is taken to be where the toes are lowest.
- *Hands and face.* Not read. Fingers stay as they rest.

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
| The halfpipe | a plywood vert ramp, north of the ninja's stage and east of the settlement (the `halfpipe` set) | |

Around them is the developer's plain grey floor, with a few grey one-metre cubes and a "TODO" or two: what hasn't been built yet.

**Planned, not in the story yet.** A place can be built and put down before the story takes it in. It goes under `planned` in `world.json`, in the same one line a place has. `just world-check` checks it like any other place: a sound set, on the ground, on nobody else's footprint. The world page shows it with the world as it is now, its name marked "· planned". An epoch never saves it: when the story takes it in, it moves over to `places` and a new epoch is saved. Planned now: the ninja's casting office, just south of his stage (see The casting office, below).

**`world.json` says where things are, and nothing else does.** Each place is an ordinary set (see Sets, below), and a set never knows where it stands. `world.json` puts each one down with one line, `{"set": "grass", "at": [0, 13], "facing_deg": 0}`: turn the set until its front faces that way, slide its origin there. Marks, cameras, blocks and the mesh all move together. It also says who stands on which mark, in which pose, and where the story's wondrous artifacts are. `just world-check` reads it and says what is wrong in words: two footprints that overlap, a place off the edge of the ground, a toon on a mark that isn't there.

**Epochs.** An epoch is the whole world saved at one moment, with a title and a one-line caption: `world/epochs/epoch-0.json`. When the world changes, `just world-epoch epoch-1 "A title" "A caption"` saves a new file. Old ones are never edited, so the gallery's timeline can step through them like a time-lapse.

**The world view** (`#/world/epoch-0`, or `#/world/epoch-0/boxing-house` to arrive at a place):

- the whole world from a little above; drag to walk round it, pinch or scroll to come closer;
- a name on every place. Tap a place (or its name in the row above) and the camera glides there;
- at a place: who is there, which artifacts, and **Open this place** for its own page with marks, cameras and shots to play. **Marks** is off until you press it;
- a timeline of epochs, with room for the next.

**Walk around.** Press "Walk around" (or open `#/world/epoch-0/walk`) and you are Roosevelt, on Theodore's grass, seen from behind and a little above. The picture fills the screen and the page steps back; over it there is one slim bar, his name on the left and **Done** on the right.

- on a keyboard, WASD or the arrow keys walk and Shift runs; drag to look round, scroll to come closer;
- on a phone, put a thumb down on the lower half and drag: a stick appears under it, push to walk, push to its edge to run. Tap the ground to walk there; drag the upper half to look round;
- the world is solid: walls, furniture, the ring and the other toons are in the way, and the camera never ends up behind a wall. The dancer's stage can be stepped up onto; the ring and the boxing house roof cannot yet (no steps to them);
- arriving at a place, its name and who is there come up at the top for a few seconds; tap that to open the place. Close to a toon, their name shows and they say hello in a line at the bottom. Close to the gachapon, the BUY HOUSE pedestal, the kettle, the bread, the ninja's camera or the dancer's microphone, the story's line about it comes up there too. One line at a time, and nothing stays;
- it follows the phone's dark mode: ink with paper lettering, where by day it is paper with ink;
- "Done" (or Esc) goes back to the view from above.

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
- **Cameras that never move.** Three on the studio: `wide`, `host`, `guest`. One take is filmed from all of them at once, and you pick the cut afterwards. A shot can bring a camera of its own that does move, a push-in say; it is filmed alongside these (see "A dance, restyled").
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
| `casting-office` | the ninja's back room for auditions: a small building with a door, a window and a pitched roof, a backdrop and a taped X inside, a table for three | built from data the same way. `scripts/sets/casting_office.py` writes its `set.json` and `build.json` from a few numbers; `just casting-office` writes them and builds it |

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

## The casting office

The ninja's back room, where he holds auditions. From the outside it is a small building beside his photo stage, in the stage's own colors: off-white walls, steel-blue trim and a steel-blue pitched roof, a little porch over the door. The door faces the stage. Inside is one plain room, the room all nine concept pictures show (`world/marble/casting-office/concepts/round1/`): a backdrop and two stand lamps at the far end with a taped X on open floor, a folding table and three odd chairs at the near end, the box camera on a tripod beside the table, a window in one side wall and the door in the other. A Marble world of that room will fill it later; for now it is boxes in flat colors.

```
just casting-office                      # write set.json and build.json from the numbers, then build it
just set-card casting-office             # its card: the room through the panel's eye
just marble-seat <world folder>          # later: put a Marble world of the room inside it
```

**The size.** The room inside is 6 m long, 5 m across and 3 m to the ceiling, with walls 20 cm thick. Three people stand side by side on the X, 80 cm apart, with room to spare between the lamps. The panel's table is 2.2 m long with a chair behind it for each of three. Outside, with the porch and the roof's overhang, it takes up 7.2 by 7.2 m.

**Where it stands.** At (45, 12.8), facing north (180), just south of the stage, past its desk end. Its footprint runs from 41.4 to 48.6 east and from 8.7 to 15.9 south: 20 cm clear of the stage, well clear of the halfpipe (north of the stage) and of the dancer's house (west of 37.2). It is `planned` in `world.json`, not a place yet: the story hasn't taken it in.

**The way through.** The stage now has a door mark, `office_door`, at the end of the stage by the desk. It leads to the office's `door` mark and that one leads back, so `just set-check` is happy with both. From one to the other is 5 m: off the stage, across the grass, onto the porch and in. The stage itself is unchanged, besides that one mark (it is offstage, so no camera has to hold it).

**Its marks.**

| Mark | What it is for |
|---|---|
| `audition` | the taped X, facing the table, the backdrop behind |
| `lineup_left`, `lineup_right` | either side of the X, for a chemistry read; with the X they are the group `lineup` |
| `panel_1`, `panel_2`, `panel_3` | the three seats at the table, facing the X (the group `panel`) |
| `box_camera` | behind the box camera on its tripod: where the ninja stands to take a test picture |
| `door` | just inside the door, facing in; leads to the stage's `office_door` |
| `porch` | out on the porch, looking toward the stage |

And three cameras: `panel_eye`, seated at the middle of the table 1.2 m up, looking down the room at the X (the eye the concept pictures were drawn from); `lens`, through the box camera; `back`, from up by the backdrop looking back at the table.

**How the Marble room goes in.** `set.json` writes down the room inside the walls (`room`: from -3 to 3 along x, 0 to 3 up, -2.5 to 2.5 across; the middle of the floor is the set's origin, the backdrop end is +x, the door's wall +z) and how a Marble world of it goes in (`marble_seat`). A Marble world's own origin is where the picture was taken from. `just marble-seat` turns it so that eye looks toward the backdrop, then to the nearest quarter turn that squares its walls up with ours; sizes it so the floor Marble measured is the size of our room; slides the middle of that floor onto ours; and then says how far the picture's eye landed from `panel_eye`. If the picture was taken where the concept pictures were, it lands on it. The building's own mesh is kept; the Marble mesh is written beside it as `marble.glb`, and `marble` in `set.json` says how the dots stand in the room, the way the saloon's does. `python3 scripts/sets/test_marble.py` tries all of this on a made-up room a tenth too big and taken 12 degrees askew: it comes back to the inside within 3 cm and its eye lands on `panel_eye`.

**Pictures** (in `evidence/casting-office/`): the world from above with it beside the stage (`overview-desktop.png`), the place itself on the world page (`casting-office-desktop.png`), the room through the panel's eye on its set page (`set-page-panel-eye.png`), a plan from above with the marks named (`plan-marks.png`), and Blender's own view from the porch side (`blender-outside.png`) and from the panel's eye (`blender-panel-eye.png`).

**What is weak.** It is a block-out: the lamps, the table and the box camera are boxes to bump into with a few sticks and cones on top, the backdrop is a flat. The roof and the ceiling are on, so from above the world page can't see in, and a set page's marks are under the roof. The furniture is our guess at the concept pictures; once a Marble world is chosen, the table, chairs and lamps should be moved to where Marble put them. Nothing has been filmed here yet. On the world page the stage's tall back wall stands between you and the porch when you arrive at the place.
## Fights

A fight is animated the way fighting games and WoW do it: a few held poses and fast snaps between them, readable before it is real. Nothing is simulated and nothing is generated; it is our own poses on the `rig.py` skeleton, played by `animate.py` like a walk.

```
just fight first runs/<roosevelt> runs/<lincoln>
```

- **One move set for everyone** (`scripts/fight/moves.py`). Guard with a light bounce, shuffle steps, jab, cross, left hook, uppercut, body shot, haymaker, block, getting up off the mat, and the winner's raised fists. A move is turns of whole body parts, and where a fist has to be somewhere (by the chin, on the other man's jaw) the arm is solved to that spot from this body's own shoulder and arm. So the same jab fits short-armed Roosevelt and long-armed Lincoln. The other stance is the same move in a mirror.
- **Startup, active, recovery.** Every attack has a quick wind-up, a snap out to a fully stretched pose that is held for its active frames, and a slower way back to guard. A jab is 3, 2 and 6 frames; a haymaker 10, 4 and 14.
- **A small menu of reactions**, picked by the blow: the head snaps (light, high), the body folds (light, low), a stagger back three steps, further than the length of his leg (heavy), forearms take it and he is pushed back a little (block), a long fall onto the mat with a small bounce, then lying still (knockdown). Each attack names the reaction it causes; whether it is blocked is the fight script's choice.
- **Fixed spacing.** The ring has two fight marks a metre apart. Each man stands a little to his own left of the line between them, so the two pairs of feet are on two lines and no boot is toe to toe. Before any exchange both men are stepped back onto their marks, and every blow is built to reach across: stretched as far as the move says, with a step in where the arm is short and a rock back where it is long. The fist only has to arrive at its spot, a few centimetres off the face.
- **Hitstop.** On the first active frame the defender's reaction starts and both men freeze: 3 frames for a jab, 5 to 8 for a heavy blow, 12 for the knockout. The film adds a jolt of the camera and a small bright star at the fist for three frames.
- **A fight is a list** (`scripts/fight/fights/first.json`): `{"by": "left", "move": "jab", "result": "blocked"}`, with guard, shuffles and circling between. `schedule.py` lays both men on one timeline and writes one plain motion each, and the list of hits (frame, where, how hard) the film reads.

`apply_fight.py` measures each character (its joints and limits from `rig.py`, and off the mesh how far the face is in front of the head and how thick the body is lying down), lays the fight out for those two bodies, and bakes each through `apply_motion.py`. `film_fight.py` stands the set up as a take does and films it from every camera: `cast-<camera>.mp4` and a strip of twelve stills each. The ring has a fourth camera for this, `fight`, above the top rope, so the ropes cross the legs and not the fists.

- **Fists.** Our hands have no finger bones. For a fight only, each hand gets two more (at the knuckles and halfway down the fingers), the far half of the hand goes over to them, and they are curled under for the whole action. Where the knuckles are is read off the mesh, so a mitten and a hand with real fingers both fold in the right place. No other profile gets them.
- **The cast.** A fight script says which version of each character plays: `"fighters": {"left": {"version": "painted"}}` puts Roosevelt in his painted singlet and tights; `lowpoly` is what anyone plays in if nothing is said.

**The first fight** (Roosevelt in his painted outfit and Lincoln in his low-poly, 24 seconds, 11 blows): they square off and circle, Roosevelt's jab is blocked, Lincoln's lands, they trade, a body shot folds Lincoln, his cross staggers Roosevelt most of a metre back, and an uppercut puts Roosevelt on the mat. Lincoln steps back, raises both fists, and the film ends on that. Measured on the baked characters: every fist is within 0.7 cm of its spot on its contact frame, nothing goes more than 0.3 mm through the mat (a man on his back included), no joint leaves its limits, and `animate.py` clamps Roosevelt's right arm on three frames of his haymaker and one foot on one frame, and nothing of Lincoln's. A second short script, `get-up`, has a man knocked down get back to his feet.

**What is weak.** A fist is the open hand folded twice: it reads at ring distance, but the thumb goes along with the fingers. A man who is hit is pushed, never caught: no clinch, no grabbing. Loose cloth would only swing, not be struck. Nothing checks one body against the other, so a long arm can pass through a guard on the way back. Roosevelt's arms are short, so he steps a long way in to reach Lincoln's head and punches steeply upward.

## The halfpipe

A plywood ramp, a skateboard, and Lincoln on it. Like a fight, a run is our own poses on the `rig.py` skeleton, played by `animate.py`; nothing is simulated beyond a little school physics and nothing is generated.

```
just skate first runs/<young lincoln>
just skate first runs/<young lincoln> lowpoly,midpoly
```

- **The ramp is built from its own numbers** (`scripts/skate/halfpipe_set.py`): a flat bottom 5 m across, a quarter circle of 3.4 m up each side, 30 cm of straight wall on top of that, a steel tube along each top edge, and a platform behind it 3.7 m up; 12 m long. `just halfpipe-build` writes `sets/halfpipe/set.json` and builds `set.glb` from the same arithmetic the riding uses, in sheets of plywood each a slightly different tan. It stands in the world north of the ninja's stage and east of the settlement, at (40.5, -12.5), its open end facing north.
- **The set says what shape it is.** `"ramp"` in its `set.json` holds the numbers and the cut across the ramp, piece by piece. `scripts/skate/pipe.py` reads them and answers what the motion needs: `Pipe.at(s)` is the point `s` metres along the surface from the middle of the flat, and the way the surface runs and faces there; `Pipe.where(x, y)` is the nearest point of the surface to anywhere and how far off it that is; `Pipe.inside(x, y, z)` is how deep a point is in the wood.
- **Marks and cameras like a broadcast.** Marks on both platforms and on the flat (a mark can now say how high its floor is, `floor_y`, and `just set-check` reads it). Four cameras that never move: `side` from out front of the open end, `low` on the flat looking up the right wall, `deck` from the left platform looking down in and across to the right lip, and `across` from the right platform with a long lens on the left lip, so a trick on either wall has a camera that holds its coping.
- **The skateboard** (`scripts/skate/board.py`, `just skate-board`) is a deck with two kicktails, two trucks, four wheels and its eight bolts: `world/props/skateboard.glb`, with a card beside it that says where the bolts, the wheels and the edges are.

**A run is two things, kept apart.**

*The board's ride* (`scripts/skate/ride.py`). The board sits on the surface with both trucks on it, so its up is the way the ramp faces there. Its speed is simple energy: gravity along the surface, a little drag, and pumping, which adds or scrubs a little through each curve: as much as the next trick needs, and no more than 1.3 m/s2. Ask for more air than the speed gives and you get what it gives, with a note; ask with far too little and it is done as a kickturn. Past the top edge the board is in the air, straight up and back under gravity, and turns half way round on the way. At the end he lets it run out across the flat and stands up.

*The rider on it* (`scripts/skate/rider.py`). His poses are written in the board's own frame, so to `animate.py` the deck is simply the floor: both feet planted over the bolts on every frame, legs solved to them, every joint held to its limit. Knees bend into the bottom of each curve and push out of it, he crouches into each air, tucks, and for a grab folds down until his back hand is on the deck by the toe edge. Where an elbow's side would turn a shoulder past its limit, the elbow comes round instead. A shorter-armed body folds further for the same grab.

`apply_ride.py` then puts the two together: the board is bound to a bone under his feet, the way a prop rides a socket, and one more bone, `ride`, above the hips and the board, is keyed to where the ride says the board is. So the file holds the whole run in the set's own place: put it down at the set's origin and it rides the ramp.

- **A ride is a list** (`scripts/skate/rides/first.json`): `{"trick": "kickturn"}`, `{"trick": "air", "height_m": 0.8}`, `{"trick": "air grab", "height_m": 0.9}`, `{"trick": "handplant"}`. One pass is one crossing of the pipe, ending in its trick on the wall he reaches. He turns one way on the right wall and back the other way on the left, so he always comes off a wall nose first.
- **The handplant.** The board carries on up past the edge until its tail is level with his back hand; the hand goes on the coping; the board swings up and over it until it is above his head with its wheels to the sky, turns, and comes back down onto the wall nose first, 60 cm further along. While the hand is down, the board is carried by the hand: on every frame the baked hand is found and the board is put wherever keeps it on its spot.

**The first run** (Lincoln in his low-poly, 28.6 seconds, seven passes): a kickturn, a small air, a grabbed air, a higher one (a metre over the edge, 0.9 s in the air, 9.6 m/s across the flat), a handplant, another grabbed air, a last kickturn, and he rolls to a stop with a hand raised. Measured on the baked file: riding, every wheel is on the surface to within a tenth of a millimetre (in a kickturn the back two stay within 3 mm while the nose lifts); the balls of both feet stay on the deck to a tenth of a millimetre and never move on it; no joint leaves its limits; the planted hand is on its spot on the coping for as long as it is down (the board was moved up to 11 cm to keep it there); and nothing goes more than 5 cm into the ramp, which is that hand and forearm against the coping. `animate.py` clamps his right arm on 49 frames: the handplant, and the reach for the grabs. His mid-poly rides the same run with the same numbers.

**A pose from a video.** A motion read off a clip (see "From a video") knows a floor, and a ramp would fight it. So a ride never takes its path from a clip; a trick can take its body from one:

```json
{"trick": "air", "height_m": 1.0, "pose_from": {"video": "halfpipe", "shot": 8, "from_s": 37.1, "to_s": 38.6}}
```

`shot` is numbered as the clip's page numbers them, and the seconds are on the clip's own clock. On every frame of that stretch the clip's skater is given a board of his own, a frame laid through his two feet; how each part of him is turned, and where his hips are from his feet, is read in that frame, retimed to our trick and eased on and off in place of our pose. Upside down over a coping, that frame is upside down with him, so nothing depends on which way the clip thinks is up. Our feet stay on our bolts and the board's path stays ours (`scripts/skate/video_pose.py`). Four things keep a borrowed pose honest on our ramp:

- *Time.* Our airs are shorter than a real skater's, and a stretch squeezed into a short air plays fast. So a borrowed air is made as high as its stretch needs to play at no more than 1.3 times its own speed (up to 2 m over the edge), if his speed allows; a handplant takes as long as its stretch. Where the speed is not there the result says how fast it had to play, and a plain air or two before it in the script builds the speed.
- *Feet.* The hips are kept where both legs can hold their feet flat on the bolts: no lower than a knee can fold, turned no more than 28 degrees from our own pose.
- *Hands.* A hand the trick itself needs stays ours. In a grab the back hand is solved onto the board's edge on top of the borrowed pose, in a handplant the planting hand onto the coping; if the clip's skater is stood too tall for that, his hips and chest come part of the way back to our own pose, by the least that lets the hand get there. The head, the free arm and how far the legs fold stay the clip's.
- *The ramp.* After the bake, off the surface, the body is looked at where the ride puts it; if any of it is in the wood, board and rider are moved the short way out (`Pipe.way_out`), eased over the frames round it.

`rides/hawk.json` is the run with every trick's body from the clip of a real one (kept out of the films we share: the clip is its makers'). Before these four it sank 47.5 cm into the ramp coming out of the handplant, missed its grab by 125 to 180 cm, played the clip at up to 2.5 times its speed and lifted a foot 2.8 cm off the deck; now nothing but the planted hand and forearm is in the wood (5.2 cm, against the coping), the grabbing hand is 10 to 11 cm from the edge spot (lying on the deck, as in our own grab), the clip plays at 1.0 to 1.27 times, and both feet stay within 0.1 cm of the deck. `"pose_from": {"motion": "<a SOMA motion file>", ...}` does the same with any motion of ours. Until `shots/video-halfpipe/` exists the pass keeps its own pose and says so. `rides/borrowed.json` tries it with a piece Kimodo made standing in for a clip: both fists thrown up, in the air, feet on the board.

`python3 scripts/skate/test_skate.py` (part of `just check`) tries all of it with no Blender: the ramp's cut, wheels on the surface, energy, feet on the bolts, limits, hands, and a made-up clip read the right way up and upside down.

**What is weak.** He rides one line: no carving along the ramp, so a kickturn pivots on the spot. The start is the top of the left wall, not a drop-in from the platform, and nobody climbs the platforms: there are no stairs. Airs go straight up and down; the body does not lean into the turn or spot its landing. In a grab the hand lies on the deck about 8 cm in from the edge, flat, because our hands have no fingers and `animate.py` keeps a hand out of its floor. On the way overhead in the handplant the shoulder is asked for up to 30 degrees more twist than it has for a few frames, and is clamped. Going up for the handplant the hand is not on the coping until the board has risen (the first and last quarter of it). With a pose from a clip: a skater who rides goofy comes out with our left foot forward all the same; a grab is always our back hand on the toe edge, whichever hand and edge the clip's skater used, and his trunk is mostly ours while the hand is down; keeping him out of the ramp can take the planted hand up to 21 cm off the coping for a few frames; and the clip asks his spine, neck and arms for more than their limits on a few dozen frames, which `animate.py` clamps. Loose cloth would hang as if the deck were always level. The wheels do not turn. The side camera has to hold the whole ramp, so he is small in it.

## Flat cards

An experiment: can a toon be a handful of flat pictures instead of a mesh, and still play any motion? It is the cut-up impostor of Aubel, Boulic and Thalmann, done one card per joint as Beacco and others at UPC do it, tried on one character (Roosevelt in his painted outfit) to see whether it is good enough for a sprite-like world.

```
just impostor runs/<roosevelt> painted          # cut him up and picture every part: a minute and a half
just gallery                                    # then open #/cards/<run>, or "See it as flat cards" on his page
just impostor-judge runs/<roosevelt> painted    # the same frames as cards and as the real model, measured
```

- **Cut by bone.** Every face goes to the part whose bones pull on it most: hips, spine, chest (with the shoulders and neck), head, and for each side upper arm, forearm, hand (fingers folded in), thigh, shin, foot (toes folded in). 16 parts. The pull is evened out along the surface first, so the line between two parts is one clean ring. Two parts that meet each reach a little way into the other (0.4 of the ring's radius, and as far as their own bones still pull a good deal, which is how the skin under an arm goes up with the arm), and the part below a joint carries a ball in it: the skin round the ring pulled in onto a ball about the joint, as big as fits inside the body. A bend opens the outside of a joint, and the ball is what shows through ("Where two cards meet", below, has why). He is cut with his arms hanging as they do in his walk, not straight out as the skeleton rests: a part is only exact near the pose it was cut in, and nobody walks in a T.
- **Pictured from all around, ahead of time** (`scripts/impostor/bake_impostor.py`). Each part is laid in its own bone's frame and drawn without perspective from a fixed set of directions: 8 around at three heights plus straight along the bone both ways (26), or 12 around at five heights (62), or 16 around at seven (114). `toon.py` draws them with the tones of light switched off: flat colour, and an ink line round the part. Beside the colour every pixel keeps which way its surface faces and how far it stands toward the eye, and whether it is a pixel of that line. All of one view set goes on two sheets, `views<N>-color.png` and `views<N>-data.png`, with `impostor.json` saying where each picture is.
- **One card a bone** (`gallery/impostor.js`, `impostor-math.js`). The page plays any clip on the skeleton with the mesh hidden. Each bone gets one flat card through its head, square on to you, showing the picture taken from nearest to where you are *as that bone sees you*. 16 cards, 32 triangles, whatever he is doing: a walk, the warm-up routine and the whole fight play from the same 416 pictures.
- **Each pixel slid by its depth.** A picture taken from 20 degrees to one side is wrong by centimetres on a chest. So a card does not lay its picture flat: every pixel looks down a line through the picture and shows the first place where the stored surface is as high as the line (a short search, then halved in on). That turns the picture, foreshortens it and shifts everything by how far it stands out, exactly, as long as you are far off compared with the part. It is what makes 26 pictures a part enough. A line that comes down on the side of something the picture never saw the back of (the rim of a sleeve, the part's own edge) carries on under it to the next surface (and, in sheets baked two surfaces deep, finds what lay behind the first: "Behind the first surface", below); if there is none, and a joint is close by, the pixel is filled all the same ("A bent joint, filled", below). The stored depth also goes to the depth buffer, so cards hide each other pixel by pixel and the ring's ropes pass in front of a leg.
- **One line round the figure, none across it.** Each part is pictured with a line all round it, and a line all round a forearm crosses the arm at the elbow. So the line is not drawn where the picture has it. In the comic look it stands 3 cm behind its part's surface, the way a mesh's ink shell does: the part next door covers it where they meet, and it shows only where nothing of the figure is beside it. In the looks that go by way of a picture of their own (pixels on screen, bold ink) the sheet's line is left out and one line is drawn on the finished picture.
- **Light is worked out, not baked.** The stored facing picks one of the comic's three flat tones from a light fixed to the eye, as `toon.py` does, so a forearm is lit from the same side whichever way it is turned.
- **Judged without a browser** (`scripts/impostor/impostor.py`, `judge_impostor.py`). `impostor.py` is the page's arithmetic and its shader done slowly in Python, a pixel at a time; `test_impostor.py` runs the page's own file in node against it (the same to 14 decimal places) and is part of `just check`. The judge draws each frame both ways from the same eye in the same light and measures the difference.

**The pixel size.** 192 pixels a metre: a pixel is 5 mm, so the comic's 1.4 cm ink line is nearly three pixels wide and survives, and a figure is sharp up to about 350 pixels tall, which is as big as a townsman gets on a 1080p screen. At 128 a metre the sheets are half the size and the line goes soft.

**What it measures** (Roosevelt, 192 px a metre, the eye 4.4 m off and going along with his hips, a pixel 4.4 mm on him, every frame of each clip; `evidence/impostor/judge.json`, `judge-moves.json`, `judge-flat.json`):

| | pictures a part | outline shared (worst frame) | colour off, of 255 | seam, cm (worst) | widest gap, cm | sticks out, cm (worst) | swaps a second | pixels changed on a frame with a swap |
|---|---|---|---|---|---|---|---|---|
| walk, from the front | 26 | 0.979 (0.972) | 4.9 | 1.4 (3.9) | 3.9 | 1.4 (2.2) | 32 | 2.9% |
| walk, from the front | 114 | 0.978 (0.974) | 4.7 | 1.3 (1.3) | 1.3 | 1.5 (3.1) | 78 | 2.8% |
| walk, three-quarter | 26 | 0.970 (0.957) | 6.1 | 1.3 (2.2) | 2.2 | 2.2 (3.9) | 28 | 3.5% |
| walk, three-quarter | 62 | 0.975 (0.966) | 5.6 | 1.4 (2.2) | 2.2 | 2.2 (3.9) | 63 | 3.8% |
| walk, three-quarter | 114 | 0.975 (0.963) | 5.5 | 1.2 (1.3) | 2.2 | 2.0 (3.9) | 80 | 3.5% |
| walk, side-on | 26 | 0.966 (0.958) | 5.4 | 1.6 (2.2) | 3.1 | 3.0 (3.9) | 0 | 0.0% |
| walk, side-on | 114 | 0.968 (0.961) | 4.9 | 1.2 (1.3) | 3.1 | 3.1 (3.9) | 21 | 1.9% |
| walk, from behind | 26 | 0.961 (0.951) | 6.9 | 2.4 (3.9) | 3.9 | 2.2 (3.9) | 57 | 5.0% |
| walk, from behind | 114 | 0.978 (0.973) | 4.4 | 1.4 (2.2) | 2.2 | 2.1 (3.9) | 73 | 3.0% |
| walk, from 25 degrees up | 26 | 0.967 (0.957) | 7.6 | 1.6 (2.2) | 2.2 | 1.7 (3.1) | 39 | 3.9% |
| walk, from 25 degrees up | 62 | 0.976 (0.968) | 6.0 | 1.4 (2.2) | 2.2 | 2.0 (3.9) | 53 | 3.1% |
| walk, from 25 degrees up | 114 | 0.976 (0.966) | 5.9 | 1.4 (2.2) | 2.2 | 1.9 (3.1) | 80 | 4.1% |
| walk, from 45 degrees up | 26 | 0.967 (0.963) | 8.5 | 2.1 (3.1) | 3.1 | 1.9 (3.1) | 32 | 6.5% |
| walk, from 45 degrees up | 62 | 0.974 (0.969) | 7.5 | 1.4 (3.1) | 3.1 | 1.8 (3.1) | 65 | 5.5% |
| walk, from 45 degrees up | 114 | 0.977 (0.970) | 6.8 | 1.4 (2.2) | 2.2 | 1.7 (3.1) | 84 | 4.5% |
| walk, three-quarter, pictures laid flat (no depth) | 26 | 0.942 (0.896) | 12.9 | 3.4 (7.4) | 8.3 | 4.1 (8.3) | 28 | 9.7% |
| walk, three-quarter, pictures laid flat (no depth) | 114 | 0.958 (0.943) | 11.6 | 2.1 (3.1) | 3.9 | 2.8 (4.8) | 80 | 8.4% |
| warm-up routine, three-quarter | 26 | 0.960 (0.936) | 6.9 | 1.8 (4.8) | 5.7 | 3.2 (6.5) | 19 | 4.6% |
| warm-up routine, three-quarter | 62 | 0.968 (0.940) | 5.9 | 1.6 (4.8) | 4.8 | 3.1 (6.5) | 26 | 3.8% |
| the fight, three-quarter | 26 | 0.936 (0.922) | 8.9 | 1.6 (3.9) | 4.8 | 9.4 (13.5) | 17 | 6.3% |
| the fight, three-quarter | 62 | 0.942 (0.927) | 7.8 | 1.4 (3.1) | 3.9 | 9.4 (13.5) | 25 | 6.0% |

Going once round him as he stands mid-stride: 26 pictures a part, 158 swaps in the turn, each changing 5.1% of his pixels, outline 0.963; 62 pictures a part, 234 swaps in the turn, each changing 4.0% of his pixels, outline 0.968; 114 pictures a part, 323 swaps in the turn, each changing 3.6% of his pixels, outline 0.971.

"Outline shared" is how much of the two outlines is common (1.0 is the same shape; the ink line wobbling by one pixel all round costs about 0.02). A gap is body the real model has and the cards do not; a seam is a gap within 12 cm of a joint. A swap is one part changing to its next picture. The two "laid flat" rows are the plain technique, without sliding pixels by their depth: 114 pictures a part laid flat (71 MB) do worse than 26 slid (17 MB).

**What it costs.**

| | cards, 26 a part | cards, 62 | cards, 114 | painted mesh | low-poly mesh |
|---|---|---|---|---|---|
| triangles | 32 | 32 | 32 | 7,848 | 1,695 |
| pictures | 416 | 992 | 1,824 | 3 colour textures | none |
| in memory | 16.7 MB | 38.8 MB | 70.9 MB | 9.4 MB of colour (19.9 with the maps the comic look does not use) | next to nothing |
| to fetch | 3.0 MB | 7.3 MB | 13.4 MB | 0.76 MB | 0.30 MB |

The sheets are per character, not per copy: a hundred Roosevelts share one. But a town of 50 different people is 50 sets of sheets, 835 MB at 26 pictures a part (390 MB at 128 px a metre), where 50 low-poly meshes are a few megabytes. In time the cards are cheap to place (16 small sums a toon a frame) and dear per pixel (with 26 pictures a part the search reads the data sheet 15 to 20 times a pixel, about 12 with 114, where a mesh reads one texture once); a hundred toons 200 pixels tall is some 40 million reads a frame, nothing to a laptop and noticeable on a phone, which can switch the search off for anyone far away. A hundred low-poly toons is 170,000 triangles, which is also nothing.

**What is good.** Front, back and three-quarter, standing and walking, it reads as the same drawing as the model: the face, the singlet's neckline and the tones of light are in the right place even from between two pictures. Any motion plays, at any frame rate, from any angle, with no new pictures. Cards sort against each other and against the set without any drawing order.

**What is weak.**
- **The ink line is rougher** than the model's. It is baked into each picture, so where a part turns away from where it was pictured the line is pieced together from slid pixels and comes out a pixel or two ragged, and thicker in places.
- **Joints.** A typical seam is 1.2 to 1.8 cm; the worst is 2 to 4 cm in a walk (a notch behind a knee, a flap at the hip when the thigh swings back) and 4.8 cm in the warm-up routine, which takes every joint to its limit. The lap that closes a bent joint pokes out when it bends the other way: up to 6.5 cm in the routine. (These are the sheets as first baked. The joints have been cut again since: "Where two cards meet", below.)
- **Hands are open.** The fight curls his fingers with bones the cards do not have, so his fists are flat hands: 9 cm of fingers the real model does not show, 13.5 at worst, and the reason the fight's outline shares only 0.94. A second hand picture, shown when the fingers are curled, would fix it; it is not done.
- **Swapping pictures.** In a walk seen from three-quarters, 28 swaps a second with 26 pictures a part, a frame with a swap changing about 3.5% of his pixels (a pixel-wide shimmer along a limb's edge, not a jump); more pictures swap oftener and no more gently. Without the depth the same swaps change 10%. The worst single frame is in the fight, as he goes down: half his pixels change at once when the chest and hips swap together. Seen dead side-on a walk swaps nothing at all. "Soften the swaps" on the page mixes the two pictures pixel by pixel near the changeover.
- **Thin things in front of others** (his spectacles) smear when slid, and what a picture never saw (the top of his head from a high eye, with only 26) is a hole or a smear.
- **Close up it is wrong.** The sliding is exact only from far off: from 4 m a point 30 cm off its card is drawn up to a degree out. Fine at town distance, not for a close-up. (Mended since: "From more angles", below.)

**The verdict.** Against plain low-poly 3D, for a town of this size: no. The mesh is already cheap (1,695 triangles), costs almost no memory, has no seams and a clean ink line, and the right half of the page shows it can be drawn the same comic way. Cards would start to pay only with thousands on screen, or with detailed models far heavier than ours. Against whole-body sprites in eight directions: yes, clearly. One walk at ten frames a second in eight directions is about 14 MB of pictures at this size (43 MB at the walk's full 30), close to what every motion he will ever have costs as cards, and it still cannot turn smoothly, stand behind a rope, or play the fight. So: keep the toons as meshes drawn the comic way; reach for cards if a crowd scene ever needs hundreds of the same few people, at 128 px a metre with the search off. (Measured since, under Tag below: even a thousand at once cost about the same either way on this Mac.)

Films and stills: `evidence/impostor/` (`walk-quarter-26.mp4`, `fight-quarter-26.mp4`, `rom-quarter-26.mp4`, `turn-walk-26.mp4`, and the same with 62, the walk and the turn with 114 too; each `*-stills.png` is cards, real model, and where they differ; `walk-quarter-26-flat-stills.png` is the walk with the depth left unused).

## Tag

The flat cards timed against meshes, as a crowd: a field of Roosevelts playing tag on the grass. `just gallery`, then `#/tag/<run>` (or "Play tag" on the cards page).

- **The game.** One is "it" (a red ring under him and an arrow over his head) and goes for the nearest runner he may tag. Runners within a few metres bolt, each a little to his own side, dodge when he is close, and stop to catch their breath when they are winded, which is when they get caught. A tag is a tag move for one and a tagged move for the other; the new "it" counts a second before he sets off, and the man who tagged him can't be tagged straight back. It is worked out from a seed in fixed steps, so every way of drawing it sees the same field.
- **The moves come from a table** at the top of `gallery/tag.js`: a name, a `.glb`, which frames, and whether it loops. They are cut from one shot, `shots/tag-moves/painted-tag.glb` (run, dodge, tag, tagged, catching breath, laugh, sprint). A move that travels is brought to the middle, turned to face ahead, and has its travel taken out; `loop: "find"` looks for the cleanest loop inside its frames and measures how fast it covers ground. If the shot is not there, each move falls back on the plain run and walk.
- **Five ways to draw them.** Meshes one by one (every runner his own skinned meshes and ink shell); meshes all at once (one draw a piece for the whole field, the bones read from a picture); cards one by one (the cards page as it is); cards all at once (every card of every runner in one draw: the graphics card picks each card's picture and places it); and that with the search by depth switched off past 12 m. Drawn all at once, a runner within 8 m of the eye also gets a piece of the real model in each big joint ("A knee that bends", below).
- **Skeletons are timed apart**, and can be shared: every move is sampled once, thirty poses a second, into a table the graphics card reads, and a runner is then a place, a heading and a row of it. Or each runner works his own skeleton out every frame. Both are offered to every way of drawing.
- **Measure all** runs every count and way for a few seconds each and shows a table to read or copy; **Measure the looks** does the same for every look. The big number is the work in one frame (skeletons, placing, drawing, and waiting for the graphics card to finish), because frames a second can't go past what the screen shows.

- **Phone test** is the narrow one, built to give the same answer twice: low-poly meshes, painted meshes, cards, and cards with the search off far away; in the comic look and as pixel art; 100, 250, 500 and 1000 runners; poses shared, one seed, one fixed eye. The picture is drawn 1080 by 608 whatever the screen and however the phone is held. Every setting is timed three times, the three spread through the test, and the first is timed again at the end to say whether the phone slowed as it warmed. It takes six and a half minutes, keeps the screen awake where the browser allows, and says at the top, in words, how big a crowd each way holds full speed at and how many times faster cards are than the cheapest meshes; "Copy results" copies every number as JSON.

**Measured on this Mac** (Apple M5, Chrome without a window, a picture of 1080 by 608; `evidence/impostor/tag-measured-mac.md`), ms of work a frame with shared poses:

| runners | 10 | 100 | 250 | 500 | 1000 |
|---|---|---|---|---|---|
| Meshes, one by one | 3.9 | 8.4 | 14.0 | 15.4 | not run |
| Meshes, all at once | 3.4 | 6.2 | 8.3 | 9.0 | 8.7 |
| Cards, one by one | 4.2 | 12.7 | 15.3 | 34.0 | not run |
| Cards, all at once | 3.6 | 7.0 | 6.1 | 7.9 | 12.7 |
| Cards, all at once, search off far away | 2.1 | 4.7 | 5.7 | 4.9 | 6.3 |

About 3 ms of that is there with nobody on the field (the set, and the wait for the graphics card). So: **drawn all at once, a thousand painted Roosevelts cost about the same as cards or as meshes**, 9 to 13 ms, and both hold 60 frames a second; the meshes are 15.7 million triangles a frame and this graphics card does not mind. Cards with the search off far away are the cheapest, 6 ms, about a third less than the meshes. At twice the pixels (2160 by 1216) it is 11.0 for meshes, 12.5 for cards, 8.8 for cards with the search off. What matters far more than cards or meshes is drawing them all at once: one by one, 500 runners are 15 ms as meshes and 34 as cards. And each runner working his own skeleton out adds 7 ms for moving the skeletons at a thousand and 4 to 5 more for handing the bones over, whichever way they are drawn. The numbers wobble by a millisecond or two from run to run (100 runners can read slower than 250): they are for the order of things, not the last digit.

## Looks

Three looks, switchable on the cards page and on the tag field, for cards and meshes alike (`gallery/looks.js`).

- **Comic**: what the comics use.
- **Pixel art**, at two levels. *Baked*: `just impostor <run> painted --look pixel` makes a sheet at 48 pixels a metre, not smoothed, every colour snapped to the 32 this character is most made of, the ink line one pixel wide (a shell behind each part's surface, so the part next door covers it where two meet), read without smoothing. The sheet is 512 by 308: 1.3 MB in memory where the comic one is 16.7, and 0.25 MB to fetch. *On screen*: the whole picture is drawn about 270 rows tall and blown up, so every pixel is square and on one grid; this works on meshes too. Cards drawn this way leave their sheet's line out and get one line on the finished picture, one big pixel wide, just outside the figure and wherever one part of it stands more than 5 cm in front of another. Close up, baked pixels alone are what was feared: each card turns and shears its own pixels, so they come out in mixed sizes at odd angles, and the face is lost. On screen they are clean, and **the mesh drawn small and blown up is the best pixel art here and the cheapest way to it**: it needs no sheet at all. At crowd distance the baked sheet is fine (a runner is a few dozen pixels tall; nobody can see which way his pixels lie), and it is what makes cards cheap: a thousand cost 6 ms where the comic sheet costs 10. *Both* is the two together, with one thing more: the head is pictured finer and drawn on a grid of pixels half the size of the body's, so a face reads ("Faces as clear as bold ink", below).
- **Bold ink** (after Viewtiful Joe): two flat tones with a hard shadow edge, strong colour, a little light on the rim, a thick black line round every figure, and thinner lines inside where one part passes in front of another or the surface folds. The lines are drawn on the finished picture from the depth of every pixel, so their weight is the same on screen however small a runner is, and the same for cards and meshes. The cards' own sheet for it (`--look joe`) has no line round the parts and has the lines inside a part drawn in. Every card pixel says which figure and which part it is, so a small step between two cards of one figure, where they meet at a joint, is not taken for one thing passing in front of another, and a crack between two such cards is filled from the nearer one instead of inked black ("A bent joint, filled", below). The meshes do not use their ink shell in this look: the same pass draws their outside line too, which halves their triangles.

What each look costs, ms of work a frame (shared poses, drawn all at once):

| look | meshes, 100 | meshes, 1000 | cards, 100 | cards, 1000 | cards, search off far, 1000 |
|---|---|---|---|---|---|
| Comic | 6.2 | 9.6 | 7.2 | 10.1 | 7.2 |
| Pixels, baked | 6.1 | 9.3 | 3.8 | 6.3 | 5.1 |
| Pixels, on screen | 4.9 | 9.1 | 5.3 | 8.5 | 5.6 |
| Pixels, both | 5.1 | 8.0 | 3.4 | 5.9 | 5.4 |
| Bold ink | 5.1 | 8.0 | 7.8 | 9.6 | 7.3 |

("Pixels, baked" changes nothing for meshes: they have no sheet.) Stills of every look, close and as a crowd of a hundred, cards and meshes: `evidence/impostor/look-*.png`.

**Cards from the detailed model.** A card costs the same to draw however fine the model it was pictured from, so `just impostor-detailed <run>` pictures the best one there is: `final.glb`, the raw mesh stood up and sized, 290,503 triangles with its own texture. It has no skeleton, so `scripts/impostor/rig_detailed.py` gives it the painted version's: every point takes the bone weights of the nearest place on the painted mesh. The two surfaces are 1.0 cm apart at a typical point, 3.2 cm at the 95th in a hundred and 8.3 cm at worst, so nothing had to be fitted. Both pages then offer "Detailed model" beside "Painted model", and its cards play the same walk, routine, fight and tag moves. He is the same man in a darker navy singlet, with real folds in his boots, modelled muscle and hair. In the comic look (16.4 MB, the same as painted's sheet) the difference shows at once. As pixel art at 48 pixels a metre it does not: there are too few pixels to carry it, close up or far. At 96 a metre (a sheet of 1024 by 568, 4.7 MB in memory, 0.9 MB to fetch) it does, and that is what the recipe bakes. On this Mac a thousand of them cost what a thousand painted cards cost in the comic look (9.1 ms against 9.8); the 96-a-metre pixel sheet costs a little more than the 48 one (7.3 ms against 5.5) because the search by depth walks more pixels, and 5.3 with the search off far away.

**A face drawn on purpose.** In pixel art a face is drawn, not shrunk, and shrinking is what the pixel sheet did. Through the candy-shop set's crew camera a face is 13 to 18 of the picture's big pixels wide and an eye 2.5 to 3.5 (`evidence/faces/before-faces.json`); the sheet's own pixels were about that size too, so an eye was one pixel when it was lucky. What went wrong, measured on the three dancers (`evidence/faces/before-*.png`):

- **The sheet's 32 colours were really 8 to 18.** The cut that picks them gave up at the first box of one flat colour. Roosevelt's whole sheet had 8, none of them dark enough for an eye; Lincoln's eyes took his hair's brown.
- **Eyes were lost or smeared.** TRELLIS paints eyes as smudges; at a pixel a centimetre they are a blot or nothing, and a different blot in each of the 26 pictures round the head.
- **Spectacles broke into dots.** A rim half a centimetre thick is under a pixel.
- Picturing the head twice as fine does not mend it by itself: `evidence/faces/finer-head-alone-against-drawn-face.png` is Lincoln's head at 192 pixels a metre as rendered (top) and with the face drawn (bottom).

So a character can have a recipe, `scripts/impostor/faces/<character>.json`: what is on the face and where, as someone drawing it would decide (`scripts/impostor/pixel_face.py` has the notes). Lincoln: the face painted flat first, then two eyes, brows, the nose's shadow, a mouth. Roosevelt: the band his eyes sit in painted skin, then round spectacles with an eye behind each; the moustache is his texture's own. The pirate: one eye under a brow, a black patch, a mouth. When a recipe fits the model being pictured, `bake_impostor.py --look pixel`:

- pictures the **head twice as fine** as the body (192 pixels a metre on a 96 sheet), with the outline kept as wide as the body's;
- finds each mark on the head's own surface once, from straight in front, and **draws it into every picture of the head in whole pixels**, never smaller than 1.56 cm (one big pixel at the crew camera's furthest): narrower from the side, not at all from behind, and hidden where something stands well in front of it. A turned face keeps its far eye;
- **keeps the face's own colours** in the sheet whatever else is in it, and picks the rest well apart, none within a step of another. A recipe can also say two of the render's colours are one thing (the flat grey band Lincoln's texture has across the back of his dark hair is drawn brown).

(These are the recipes as first drawn. Most of their marks have been taken out again: "Faces as clear as bold ink", below.)

Such a sheet goes into `<version>-impostor-pixel-faces/`, which the pages read in place of the plain one and pages older than this do not read at all. `python3 scripts/impostor/face_shots.py` takes the stills and measures the faces; `head_sheet.py` lays a head's pictures out in a row.

What it costs, the three dancers' sheets before and after: Lincoln 1024 by 540 to 1024 by 612 (4.4 to 5.0 MB in memory, 0.86 to 0.96 MB to fetch), Roosevelt 1024 by 568 to 1024 by 660 (4.7 to 5.4, 0.87 to 1.01), the pirate 1024 by 940 to 1024 by 1200 (7.7 to 9.8, 1.54 to 1.82): his hat is most of his head's pictures. On the tag field on this Mac (1080 by 608, poses shared, three goes each with the gallery as it was and as it is, turn about; `evidence/faces/cost-mac.json`), a thousand Roosevelts from the detailed model as pixel cards went from 7.5 ms of work a frame to 8.1 (the goes ran 7.5 to 8.4 before and 8.0 to 8.5 after), 5.3 to 5.5 with the search off far away, and a hundred from 4.2 to 3.9; every setting still drew a frame every 16.6 ms. The painted model's sheet, which the phone test times, is not changed: its cards took 7.0 ms before and 7.2 after at a thousand, inside what one go differs from the next. No phone has run it since.

**For meshes** ("Pixels, on screen") the bake keeps the marks in `impostor.json` and `gallery/face-marks.js` lays them on the head as small flat patches riding the head bone, each dropped onto the mesh actually shown. Only the pirate uses it, whose low-poly head had no face at all. Lincoln's and Roosevelt's low-poly heads model their own eye sockets and spectacles, and marks laid over those read as a second pair of eyes or do not show, so their recipes keep every mark off the mesh, and their meshes look as they did.

**What is still weak in the faces.**
- **From below.** Lincoln seen from 45 degrees under his chin is still a muddle (`evidence/faces/after-head-sheets-from-below-and-above.png`, top row): the flat paint reaches the front of his face, not the underside of his jaw, where the texture's smears stay, and the marks crowd together. A head thrown back in a dance shows it.
- **Close up the faces are blunt.** A mark is never under 1.56 cm, so from 1.3 m an eye is a block five or six big pixels across and a mouth a bar. (Less so since: most of the marks are gone, and the face is the model's own. "Faces as clear as bold ink", below.)
- **A recipe fits one model.** They were drawn on the detailed heads. On Roosevelt's painted head the same recipe put one spectacle right and broke the other, and the features sat low; why was not found. The bake leaves a recipe off any model but the one it names, so the painted model's pixel cards (the tag field's, and the phone test's) have no drawn face. (They no longer need one to have a face: below.)
- **Something only 3 to 8 cm in front of a mark does not hide it**, unless the mark is told to keep within 3 (the pirate's eye and brow are, for his hat's brim; a fringe or a cap on someone else would need the same).
- The head was not drawn on the screen's own grid of pixels, so its pixels landed between them as it moved. (Done since, below. And the head's outline no longer runs across the throat: "Where two cards meet".)

**Faces as clear as bold ink.** In "Pixels, both" the faces were hard to read, and in bold ink, drawn from the same cards, they were not. `just impostor-faces` measures it without a browser (`scripts/impostor/judge_faces.py`). It stands the detailed model in the take's own poses and draws it twice as fine as the screen, draws the cards from the same eye in both looks, and for every feature of the face (each recipe now lists where the model's own eyes, brows, nose, mouth, spectacles or patch are) says how well the light and dark there follows the model's: 1 is the same shape in the same place, 0 is nothing in common. That is "kept"; "likeness" is the same for the whole face at once. The three dancers, six moments of the dance, three eyes: the set's crew camera (a face is 13 to 17 of the picture's big pixels wide), 2 m from the head (35) and 1 m (70).

What was hiding the faces, through the crew camera (`evidence/clear/faces-before.json`; kept, then likeness; bold ink has 0.74 and 0.67, "Pixels, both" had 0.64 and 0.61):

- **Two grids.** The head's sheet has a pixel every 5 mm and the picture a big pixel every centimetre, so a big pixel lay over 2.1 sheet pixels each way (1.5 to 2.5) and showed one of those four or so: a different one as he moved. Slide the grid half a pixel under the same pose and "kept" changed by 0.13 a feature (0.17 on Lincoln). On a grid twice as fine the same sheet gives 0.68 and 0.70.
- **The line.** One big pixel is a fifteenth of a face, and the line also falls inside the face wherever a hand, a brim or a nose stands 5 cm in front. With no line: 0.67 and 0.69.
- **The faces that were drawn.** Lincoln's face was painted flat with dots and bars on it: likeness 0.44 through the crew camera and still 0.58 from 1 m, where there is no shortage of pixels, against bold ink's 0.60 and 0.66. Roosevelt's drawn rims read as goggles, and the pirate's mouth, a dark bar where the model has a pale lip, kept 0.41 where bold ink's keeps 0.93.
- **Too few skin colours.** The sheets' 32 colours were really 18, 19 and 30, two or three of them skin.
- **Not the cause.** Cutting colours to twelve steps on the finished picture (without it: 0.64 and 0.63). The angle: the eye is typically 15 degrees off the picture of the head it is shown (22 at the 90th in a hundred, 29 at worst), and it is the same for bold ink. Hands and brims: 4 of 108 features were behind something. And drawing a face on purpose was not the mistake at that size: the comic sheet on the same grid, the model's own face with nothing drawn, does worse (0.59 and 0.47).

What was done:

- **The head goes on a grid twice as fine** (`gallery/looks.js`: Screen). The picture is drawn small as before, every card but the heads'; it is copied onto one twice the size, depth and all; the heads' cards are drawn onto that, in front of or behind the body pixel by pixel; and the one line is put on last, still one big pixel wide and outside the head. A head goes there once a metre at it is 40 big pixels (a face five or six wide); further off it stays with the body. A big pixel is now always an even number of the screen's, so a head's pixel is a whole number of them.
- **The head moves a whole pixel at a time.** Its card is slid by part of a fine pixel so the bone's head sits on a corner of one, as a sprite would. "Kept" now changes by 0.004 when the grid is slid.
- **The head is pictured as bold ink pictures it**: at 192 pixels a metre whatever the body's, the model's own texture, and its folds drawn in one pixel wide in the colour under them made dark (a nostril, the jaw, a lock of hair). Roosevelt's painted head too, whose body is at 48: it needs no recipe to have a face.
- **Sixteen colours more for the head alone**, picked from its own pictures.
- **The recipes were cut back** to what the texture lacks: a pupil in each of Lincoln's eye hollows and behind each of Roosevelt's lenses; the pirate's eye, brow and patch. The flat paint, the drawn rims and the drawn mouths are gone.
- **A dark pixel is not dropped.** Where a head's picture is shown smaller than it was taken, a pixel takes the darkest of what it covers when that is clearly darker than its middle and on the same surface.
- These sheets are in `<version>-impostor-pixel-clear/`, which only "Pixels, both" reads. "Pixels, baked" and pages older than this read the sheets they did.

What it is now (`evidence/clear/faces-after.json`): kept, with likeness in brackets.

| | seen from | bold ink | "Pixels, both" before | after | comes and goes, before to after |
|---|---|---|---|---|---|
| Lincoln | crew camera | 0.86 (0.60) | 0.60 (0.44) | 0.81 (0.57) | 0.17 to 0.004 |
| Lincoln | 2 m | 0.83 (0.64) | 0.63 (0.53) | 0.79 (0.63) | 0.07 to 0.001 |
| Lincoln | 1 m | 0.82 (0.66) | 0.60 (0.58) | 0.79 (0.65) | 0.03 to 0.000 |
| Roosevelt | crew camera | 0.67 (0.63) | 0.62 (0.58) | 0.73 (0.67) | 0.12 to 0.006 |
| Roosevelt | 2 m | 0.75 (0.70) | 0.71 (0.76) | 0.82 (0.78) | 0.04 to 0.001 |
| Roosevelt | 1 m | 0.72 (0.65) | 0.69 (0.71) | 0.80 (0.74) | 0.01 to 0.000 |
| the pirate | crew camera | 0.73 (0.77) | 0.68 (0.81) | 0.79 (0.81) | 0.12 to 0.003 |
| the pirate | 2 m | 0.75 (0.77) | 0.75 (0.87) | 0.83 (0.86) | 0.04 to 0.000 |
| the pirate | 1 m | 0.70 (0.66) | 0.70 (0.75) | 0.77 (0.72) | 0.01 to 0.001 |
| all three | crew camera | 0.74 (0.67) | 0.64 (0.61) | 0.78 (0.68) | 0.13 to 0.004 |
| all three | 2 m | 0.77 (0.71) | 0.70 (0.72) | 0.82 (0.76) | 0.05 to 0.001 |
| all three | 1 m | 0.74 (0.66) | 0.67 (0.68) | 0.78 (0.70) | 0.02 to 0.001 |

Stills, bold ink, "Pixels, both" before and after, each head through the crew camera, from 2 m and from 1 m: `evidence/clear/sides-24-<role>.png` and `sides-36-<role>.png` (`just clear-shots`); `*-judged-*.png` are the real model, bold ink and the pixel look with the counted features boxed.

What it costs. The detailed sheets are the size they were (5.0, 5.7 and 9.6 MB in memory; 0.98, 1.08 and 1.91 MB to fetch, where they were 0.98, 1.05 and 1.85), against bold ink's 14.1, 15.7 and 25.6 MB (4.0, 4.0 and 7.2 to fetch). Roosevelt's painted sheet grew from 512 by 360 to 512 by 604: 1.5 to 2.5 MB in memory, 0.28 to 0.45 to fetch, against bold ink's 16.8 and 3.0. The finer picture is one more the size of the screen (5 MB at 1080 by 608), once, however many are on it. On the tag field on this Mac (1080 by 608, poses shared, the gallery as it was and as it is turn about, five goes each; `evidence/clear/cost-mac.json`), ms of work a frame for a hundred and a thousand Roosevelts:

| | "Pixels, both" before | after | bold ink |
|---|---|---|---|
| painted cards | 3.6, 8.1 | 4.3, 8.9 | 7.5, 9.2 |
| painted cards, search off far away | 2.9, 5.0 | 3.3, 4.5 | 3.9, 7.6 |
| detailed cards | 4.7, 8.5 | 5.2, 9.1 | 8.3, 9.4 |
| detailed cards, search off far away | 3.0, 5.5 | 3.6, 6.1 | 3.9, 7.6 |

So about half a millisecond more, most of it the copy onto the finer picture, and still under bold ink at every setting (by little with a thousand drawn all at once, where one go differs from the next by a millisecond). Meshes cost what they did (painted 4.8 and 8.2 in bold ink, low-poly 3.6 and 8.2; a picture with no cards in it skips the finer grid). Every setting drew a frame every 16.7 ms. The copy is as big as the screen only when a big pixel is two of the screen's; on a screen with more pixels to a point it is a quarter of it or less. No phone has run it.

The joints did not slip (`just impostor-seams`, `evidence/seams/seams-clear.json`, the finer picture brought back to big pixels to count): through the crew camera "Pixels, both" has 2.3 pixels bare and shut in where it had 2.4, and 4.6 between two cards where it had 4.9; from 2 m 27.8 and 94.4 where it had 28.4 and 95.1. Line that is not there is a hair up, 1.51 to 1.55% of the figure through the crew camera and 0.80 to 0.84 from 2 m: the line round a head is now on the finer grid. The other three looks count what they counted, to the digit.

What is still weak:

- **Mouths.** A mouth keeps 0.79 through the crew camera where bold ink keeps 0.87: it is a faint thing in these textures, and bold ink's hard shadow under the lip is what shows it there.
- **Lincoln is still a little behind bold ink** (0.81 against 0.86 through the crew camera). His face is mostly light and shade, and the pixel look's shade is gentle.
- **Close up it is blocks.** From 1 m a sheet pixel is five fine pixels across. Bold ink smooths the same sheet. A finer head sheet would mend it and quadruple the pirate's, which is mostly hat.
- **The head's pixels are half the body's**, on purpose. Side by side on a big screen the two sizes can be told.
- **A head crossing 40 pixels a metre** changes grid in one frame.
- **Roosevelt's rims are mottled** grey and green close up: his texture's, now that it is shown.
- **The judge's "kept" is a likeness of light and dark**, not a person reading a face. It ranks these pictures the way the eye does; it would not notice a face that is right and unkind.

The tag field also has the fair opponent: **low-poly meshes** (1,695 triangles and plain colours, all at once: 3.9 ms for a hundred, 8 to 9 for a thousand here) and **meshes near, cards far** (painted meshes within 9 m of the eye, cards beyond; as built it saves nothing, 9.7 ms, because every mesh's points are still sent and only then thrown away). Stills of painted cards, detailed cards, low-poly meshes and painted meshes, close and as a crowd: `evidence/impostor/compare-*.png`.

**What is weak.** Bold ink's fold lines come from depth alone, so thin things far away (a rope) break into dashes, and two cards of one figure more than 9 cm out of step still draw a line between them. The plain baked pixel sheet loses the face (a character with a recipe gets one drawn: "A face drawn on purpose", above). Pixel art on screen shimmers a little as the eye moves, as any picture drawn small does.

## Where two cards meet

The cards showed their joins: a dark line across an arm at the elbow, and here and there the stage showing through between two parts. `just impostor-seams` counts both without a browser (`scripts/impostor/judge_seams.py`). It stands the detailed model in the take's own poses, draws it the comic way from the same eye with its own ink line, and counts in the cards' picture: pixels of ink line well inside the body where the model has nothing dark within 1.2 cm (a line that is not there), and pixels of the model's body the cards leave bare. The three dancers of the candy-shop routine, ten moments of the dance and six of a walk, through the set's crew camera (a figure is about 29,000 pixels of a picture 1080 by 608, 7,300 of the small picture the pixel looks draw) and from 2 m (140,000).

**What it was**, with the sheets and the page as they were (`evidence/seams/seams-before.json`, `seams-before-why.json`):

- **Every part's own outline, all the way round it.** A forearm's outline crosses the arm at the elbow, and it was drawn at the surface's own depth, so it lay on top of the upper arm. In the pixel sheet the line was grown round each picture after the bake, cut end and all. Through the crew camera, 2.5% of a figure's pixels were such a line in "Pixels, both", 1.5% in "Pixels, baked", 1.4% in the comic look and 2.3% in bold ink (which drew its own lines on top of the comic sheet's); two thirds of them within 12 cm of a joint. `evidence/seams/line-at-the-surface-and-behind-it.png` is Roosevelt four ways: the old sheet, and the new one with its line at the surface, 1 cm behind it and 3 cm behind it.
- **The line between two parts was a fringe.** A detailed mesh takes its weights from the nearest place on the low-poly one, so where one part ended and the next began followed the low-poly mesh's triangles: splinters centimetres long. Lincoln's and the pirate's parts met along a line 1.65 times as long as it need be, Roosevelt's 1.2 times. Splinters comb apart when the joint bends, and every one is an edge for a picture to get wrong.
- **A pixel that came down on an edge was dropped.** Sliding a pixel by its depth is a search down a line through the picture. Where that line came down on the side of something (the rim of a sleeve, the part's own cut end) more than 4 cm under its top, the pixel was thrown away, whatever lay beyond. Through the crew camera the cards left 156 pixels of a figure bare in the comic look (0.53% of it): 69 of them shut in by cards on every side, 110 with cards within a centimetre and a half on both sides. The parts as rigid pieces of the real model, with no pictures at all, leave 76 bare, and those are outline, not holes: the model's skin stretches into a web under a raised arm and between spread legs, and rigid parts' does not. With nothing dropped for being far under the surface the cards leave 39. So three quarters of the bare pixels were that test.
- **Not the cause:** the steps of the search (four times as fine, 149 of the 156 are still bare) and the test of the colour sheet's cover (156 of 156).

**What was done.**

- **The cut** (`impostor.py: round_cut`, `bake_impostor.py`). The pull of the bones is evened out along the surface over 2 cm before the cut, so two parts meet along one clean ring. Each reaches 0.4 of the ring's radius into the other, and takes what its own bones still pull on a good deal, as before: that is how the skin under an arm goes up with the arm. And the part below each joint carries a ball: the faces round the ring, pulled in onto a ball about the joint, as big as fits inside the body there (Lincoln's knee has one 8 cm across, his elbow 6). A ball is where it was however the joint turns. It shows only through what a bend opens, in the colours of the skin that was there, it shuts the open end of the limb, and it never pokes out, where a lap long enough to close a bent knee stands out as a spur when the knee is nearly straight.
- **The line.** The colour sheet no longer holds a line. Its pixels are marked in the data sheet and the page paints them. The comic look and "Pixels, baked" stand them 3 cm behind the part's surface, as a mesh's ink shell is, so the part next door covers them. "Pixels, on screen", "Pixels, both" and bold ink leave them out and draw one line on the finished picture: every card pixel writes which figure and which part it is into the picture's fourth channel, and a pixel is inked when the one beside it is a card and this one is something else and further off, or is the same figure and more than 5 cm further (and not just a surface sloping away). In the pixel looks that line is one big pixel wide on the picture's own grid, which the sheet's line never was.
- **The search** goes on under an edge to the next place the line comes down onto the surface, and gives up only when there is none.
- Sheets baked this way go into `<version>-impostor-<look>-joined/`. The pages read those when they are there and the older sheets when they are not; a gallery older than this reads only the older ones, which are left alone.

**What it is now** (`evidence/seams/seams-after.json`). Pixels of one figure in one picture, before and after; the first of each pair of columns is through the crew camera, the second from 2 m:

| look | line that is not there, % of the figure | | bare and shut in by cards | | bare between two cards | |
|---|---|---|---|---|---|---|
| Pixels, both | 2.49 to 1.51 | 2.25 to 0.80 | 13.8 to 2.4 | 76 to 28 | 18.6 to 4.9 | 119 to 95 |
| Pixels, baked | 1.51 to 0.70 | 1.15 to 0.60 | 58 to 48 | 318 to 221 | 97 to 89 | 553 to 480 |
| Comic | 1.38 to 0.95 | 0.98 to 0.62 | 69 to 60 | 323 to 240 | 110 to 97 | 505 to 423 |
| Bold ink | 2.27 to 0.56 | 1.57 to 0.43 | 69 to 60 | 323 to 287 | 110 to 120 | 505 to 711 |

In the walk, from 4.4 m: lines 1.82 to 0.63% in "Pixels, both", 1.27 to 0.43 baked, 0.81 to 0.48 comic, 1.35 to 0.32 bold ink; bare and shut in, 27 to 3.4 pixels in "Pixels, both" and 100 to 80 in the comic look. What is left of the line count is mostly real lines (a sleeve's hem, a collar) that the cards draw more than 1.2 cm from where the model has them. Bold ink has more bare pixels between cards than it had (and 221 bare in all through the crew camera, where it had 156): it used to borrow the comic sheet, whose lines filled the cracks with black.

Roosevelt's painted cards, by the first judge (`just impostor-judge`, 26 pictures a part; `evidence/seams/judge-painted-joined.json`), against the rows of the table under "Flat cards": the walk's seam from the front 1.4 cm (3.9 at worst) to 1.3 (3.1), three-quarter 1.3 (2.2) to 1.2 (1.3), from behind 2.4 (3.9) to 2.2 (3.9), side-on 1.6 (2.2) to 1.7 (2.2); the warm-up routine 1.8 (4.8) to 1.7 (4.8). Outline shared is the same to the third place. One thing is worse: side-on in the walk the cards stick out 4.5 cm (6.6 at worst) where they stuck out 3.0 (3.9).

**What it costs.** The sheets are the size they were: comic 15.4, 16.4 and 28.1 MB in memory for Lincoln, Roosevelt and the pirate before, 15.1, 17.0 and 27.1 now; pixel 5.0, 5.4 and 9.8 before, 5.0, 5.7 and 9.6 now. A bake takes about half as long again (the evening-out). On the tag field on this Mac (1080 by 608, poses shared, the gallery as it was and as it is turn about, three goes each; `evidence/seams/cost-cards-mac.json`, `cost-meshes-mac.json`), ms of work a frame for a hundred and for a thousand Roosevelts:

| look | painted cards | detailed cards | painted cards, search off far away |
|---|---|---|---|
| Comic | 7.9 to 8.1, 9.1 to 9.5 | 7.7 to 8.2, 9.8 to 8.8 | 3.1 to 3.2, 6.2 to 6.6 |
| Pixels, baked | 3.2 to 4.3, 6.8 to 8.9 | 4.1 to 5.3, 9.7 to 9.4 | 2.5 to 2.7, 4.9 to 5.8 |
| Pixels, both | 3.1 to 3.6, 7.1 to 7.9 | 4.3 to 4.8, 8.6 to 8.6 | 2.8 to 2.9, 5.1 to 5.3 |
| Bold ink | 8.2 to 8.0, 9.4 to 9.4 | 7.7 to 7.5, 11.0 to 9.2 | 3.8 to 3.5, 7.3 to 7.5 |

One go differs from the next by up to a millisecond. Inside that, the comic look and bold ink cost what they did; the pixel looks cost half a millisecond to two more with the search on (it now carries on where it used to stop), most in "Pixels, baked" with the painted sheet, 6.8 to 8.9 ms at a thousand. Every setting still drew a frame every 16.7 ms. Meshes are untouched: painted and low-poly meshes in the comic look, drawn small, and in bold ink took 3.7 to 9.7 ms before and 3.8 to 9.6 after, setting for setting within a millisecond. No phone has run the phone test since.

**What is still weak.**
- **The skin does not stretch.** Under a raised arm and between spread legs the real model's skin makes a web; the cards' outline goes in there instead. Most of the pixels still bare are that (147 a figure in the comic look through the crew camera, where the rigid pieces alone leave 69).
- **A lap still pokes out** on the outside of a slight bend, a centimetre or two. The ball does not, but it is only as big as the nearest skin lets it be, so in a joint that sits off the middle of its limb it falls short on the far side. (What a deep bend opens is filled since: "A bent joint, filled", below.)
- **The comic line is still rough** close up: it is pieced together from slid pixels, as it was.
- **Inside one figure the drawn line needs a 5 cm step**, so an arm lying against the chest gets none; a mesh's ink shell draws one at a centimetre and a half.
- **The pirate's knee still shows a dark hollow** from close by: that one is his, the open top of his boot in the detailed model.

Stills, before and after (`evidence/seams/`): the stage through the crew camera in each look as cards (`*-24-crew-<look>-cards.png`) and as meshes (`-meshes.png`); the pirate's bent elbow and knee from 1.1 m (`*-24-joint-right-forearm_l-<look>-cards.png`, `-shin_l-`); each dancer from 2.6 m; `*-judged-<role>-36-close-<look>.png` are cards, the real model, and the cards with the lines that are not there marked red and the bare pixels blue; `after-pieces-*.png` are the rigid pieces against the model (blue: only the model, red: only the pieces); `after-field-*.png` the tag field. `just seam-shots` takes the stills from a running gallery.

## A bent joint, filled

A deep bend still tore the cards: a knee in a high step, an arm raised, a head thrown back. Through the tear you saw the stage, or looked in at the open end of a limb as into a pipe. `just impostor-seams crew-candy-shop bent-after evidence/seams --deep 2` now also counts joint by joint, against how far each joint is bent from the pose the parts were cut in, and adds the moments of the dance where each kind of joint is bent furthest (a knee at 148 degrees, an arm raised 142, a hip at 94, a neck at 69).

**What it was** (`evidence/seams/seams-bent-before.json`; pixels of one figure in one picture, 60 pictures of the three dancers):

- **It is the bend.** In bold ink from 2 m, a joint bent under 30 degrees has 46 pixels of hole or crack to its name; one bent 60 to 90 has 79, and one bent 90 or more has 100. The worst single joints: the pirate's hip at 91 degrees (1,048 pixels of hole and 486 of crack), his other hip at 87 (474 and 354), Roosevelt's hip in a deep knee bend (404 and 222).
- **Three different things were being called a tear.**
  - *A see-through pixel.* A card's pixel looks down a line through its picture. Where that line goes in by the side of something the picture never saw (the cut end of the part, the far side of a sleeve), there is nothing to show, and the pixel is left bare. At a joint the limb does go on there, into the next card, but that card's picture has the same blind side.
  - *A hollow.* Seen from the knee end, a thigh's picture is the inside of a pipe: its far wall, a long way back, with rings where the ball and the lap step. Nothing is see-through, and the judge's bare-pixel counts never saw it.
  - *A crack inked black.* Bold ink draws its thick line just outside anything that stands in front of the stage. A crack two pixels wide between a thigh and a shin got that line from both sides: a black scratch across the knee. The pixel looks did the same with their one-pixel line.
- **Not the cause:** a lap or a ball that grows with the bend. Tried: the room a joint is filled in, made up to 80% bigger at a 90 degree bend, took between a twentieth and a fifth off the bare pixels and added nearly half again to what sticks out.

**What was done.** Nothing was baked again: the sheets are the ones that were there, and what a joint needs is worked out from what their `impostor.json` already says of each joint (where it is, the ring where its two parts meet, the ball the bake found room for).

- **A see-through pixel near a joint is filled** (the card's own shader, `gallery/impostor.js`; `impostor.py: card_pixels`). If the pixel's line found no surface, but did run under the part's own surface inside a ball about the joint as big as the ring where the two parts meet, it is drawn there after all: in the colour of the surface over that place, two centimetres behind it, so anything truly there covers it. Along the side of a limb, away from any joint, nothing is filled: filled everywhere, the outline grows a fringe (2.8 times as much sticking out, measured).
- **Every joint has a ball in it that needs no picture.** The shader works out where the eye's own line through a pixel meets a ball about each of the part's joints (0.8 of the ball the bake found room for, so it is inside the body), and draws it wherever it comes before the picture's surface. That is only where the eye is looking in at a hollow. Both parts at a joint draw the same ball, each in its own colour near the joint (found once, from its own pictures), and the part whose body is behind the ball as you look is the one that shows: look in at the open end of a thigh and the plug is the colour of the thigh. Where a picture has no surface at all no ball is drawn: tried, it showed as a knob beside Lincoln's forearm, where his rolled sleeve is wider than his arm.
- **A crack is filled on the finished picture** (`gallery/looks.js`), in the looks that have one: bold ink and pixels on screen. A pixel that shows the stage, with two cards of one figure close on opposite sides of it, is filled from the nearer of the two and gets no line, when the two are one part or two parts that meet at a joint and stand within 12 cm of each other in depth. Bold ink looks as far off as its thick line reaches (3 pixels), using depths it had already read; the pixel looks look one big pixel either side. Between the legs, between a forearm and the hips, and anything wider is left alone.

All three cost the same however big the screen is, bar the last, which rides on a pass those looks already made.

**What it is now** (`evidence/seams/seams-bent-after.json`). Pixels of one figure in one picture, before to after; the first of each pair is through the crew camera, the second from 2 m:

| look | bare and shut in by cards | | bare between two cards | | sticks out | |
|---|---|---|---|---|---|---|
| Bold ink | 67 to 13 | 313 to 88 | 122 to 34 | 736 to 272 | 426 to 457 | 2,966 to 3,170 |
| Pixels, both | 2.8 to 1.2 | 30 to 23 | 5.7 to 4.2 | 88 to 78 | 172 to 185 | 1,494 to 1,580 |
| Comic | 56 to 32 | 250 to 120 | 94 to 64 | 441 to 259 | 607 to 635 | 4,501 to 4,646 |
| Pixels, baked | 51 to 29 | 232 to 117 | 89 to 59 | 471 to 291 | 793 to 815 | 5,481 to 5,598 |

On the ten moments "Where two cards meet" counted (its table's last word), through the crew camera: bold ink 60 to 9.7 shut in and 120 to 28 between cards, which is under where it stood before the line was moved off the sheet; "Pixels, both" 2.3 to 0.8 and 4.6 to 3.4; the comic look 60 to 36 and 97 to 62; "Pixels, baked" 48 to 28 and 89 to 56. In the walk from 4.4 m bold ink goes 148 to 71 and 207 to 82. Line that is not there: bold ink 0.56 to 0.60% of the figure (a filled pixel stands 2 cm back, and now and then that is a step the thin line takes), "Pixels, both" 1.56 to 1.42%, the other two as they were.

By how far a joint is bent, holes and cracks to a joint, from 2 m:

| bent | under 30 degrees | 30 to 60 | 60 to 90 | 90 and over |
|---|---|---|---|---|
| Bold ink | 46 to 14 | 67 to 24 | 79 to 23 | 100 to 31 |
| Pixels, both | 5.3 to 4.0 | 7.6 to 7.6 | 7.9 to 5.5 | 10.5 to 7.6 |

A deep bend no longer costs three times a slight one, though it still costs twice. By kind, bold ink from 2 m, bent 90 or more: a hip 389 to 2, a knee 27 to 3, an elbow 52 to 21, a shoulder 121 to 59 (the weakest now: an arm raised past the shoulder opens further than its ring); a neck bent 60 or more, 290 to 3.

Roosevelt's painted cards in the tag field's own moves (run, dodge, tag, catching breath; eight moments, `seams-tag-before.json`, `seams-tag-after.json`), from 4.4 m and from 2 m: bold ink 90 to 19 shut in and 128 to 32 between cards, then 160 to 45 and 371 to 121; the comic look 57 to 36 and 68 to 46; "Pixels, baked" 87 to 74 and 153 to 121; "Pixels, both" 10 to 9 and 18 to 15, then 60 to 56 and 103 to 105. His painted pixel sheet has a pixel every 2 cm, and most of its bare pixels are not at a joint at all.

**The faces did not slip** (`just impostor-faces`, `evidence/clear/faces-filled.json` against `faces-after.json`; all three dancers, how much of a face is kept): bold ink 0.744 to 0.742 through the crew camera, 0.774 to 0.771 from 2 m, 0.741 to 0.745 from 1 m; "Pixels, both" 0.776 to 0.777, 0.817 to 0.818, 0.784 to 0.789. The most any one dancer moved is Roosevelt in bold ink from 2 m, 0.749 to 0.743.

**What it costs.** No sheet changed, so nothing more to fetch or hold. On the tag field on this Mac (1080 by 608, poses shared, main's gallery and this one turn about, five goes each; `evidence/joints/cost-mac.json`), ms of work a frame for a hundred and a thousand Roosevelts, before to after:

| | bold ink | "Pixels, both" |
|---|---|---|
| painted cards | 6.7 to 6.0, 8.6 to 10.7 | 4.0 to 4.5, 7.3 to 7.3 |
| painted cards, search off far away | 3.5 to 3.8, 6.0 to 6.4 | 3.0 to 3.4, 5.0 to 5.3 |
| detailed cards | 6.5 to 6.4, 8.3 to 9.5 | 4.6 to 4.9, 7.4 to 8.2 |
| detailed cards, search off far away | 3.4 to 4.5, 7.1 to 6.2 | 3.1 to 3.7, 5.4 to 5.4 |

One go differed from the next by two to four milliseconds on this run, more than most of these differences. What stands above that: a thousand in bold ink with the search on cost one to two milliseconds more (the test for a joint runs at every step of a search that finds nothing), and "Pixels, both" up to one. "Pixels, both" is still the cheaper at every setting. Every setting drew a frame every 16.7 ms. Meshes cost no more (three goes each, `cost-meshes-mac.json`): painted meshes in bold ink 4.6 to 3.4 and 7.3 to 7.1, low-poly 3.0 to 2.9 and 5.9 to 5.3; drawn small, 3.3 to 3.4 and 9.0 to 7.9, low-poly 2.9 to 2.9 and 8.2 to 6.4. No phone has run it; the card's shader now hands seventeen more numbers from each corner to each pixel, which is inside what every phone must allow but nearer the edge of it than before.

**What is still weak.**
- **A hollow is plugged, not skinned.** The ball is one flat colour. Where the real knee has a stripe of trouser running over it, the cards have a plain disc with the part's own rim round it, and bold ink draws that rim. (Mended since for knees, elbows, hips and shoulders: "A knee that bends", below.)
- **The web of skin is still missing** under a raised arm and between spread legs: that is outline, not a hole, and no filling reaches it.
- **Past the ring nothing is filled.** A gap that opens further from the joint than the ring where its parts meet stays open. Those three worst hips went to 0 and 4, 0 and 1, 0 and 13; the pirate's hip at 66 degrees, 53.75 s in, went only from 465 and 548 to 280 and 401.
- **Comic and "Pixels, baked" get the first two only.** They have no finished picture to fill cracks on.
- **Close up the edges are still combed**: within a metre a card's pixels are blocks sheared by their own depth. Nothing here changes that.
- **The pirate's boot tops are open cups** in the detailed model. The ball now sits in the cup, dark as the boot; it is his, not a seam.
- The judge counts bare pixels and lines. It does not count a hollow, so the ball's worth is in the stills, not the table.

Stills (`evidence/joints/`, taken by `just joint-shots`, main's gallery beside this one): `knee-<look>.png`, `elbow-<look>.png`, `neck-<look>.png`, `hip-<look>.png`, `shoulder-<look>.png` are a square round the joint at the moment it is bent furthest, down the page through the crew camera, from 2 m and from 1 m, before on the left and after on the right; `stage-<seconds>-<look>-before.png` and `-after.png` the whole stage. `evidence/seams/bent-after-*.png` are the judge's own: cards, the real model, and the cards with bare pixels marked blue.

## A knee that bends

In a deep squat with the knees toward you, every knee was a dark ringed socket, not a knee. A plugged hollow is not skin. Now every knee, elbow, hip and shoulder has a small piece of the model itself in it, bending as the model bends, and the cards step aside there.

```
just impostor-joints runs/<character> detailed      # the pieces, for cards already baked: ten seconds
just impostor-knees crew-candy-shop after           # does a bent joint read as the joint it is? counted, no browser
just joint-shots "8045/?joints=cards" 8045/ crew-candy-shop evidence/knees   # stills, the cards alone and with the pieces
```

**What it was** (`evidence/knees/before-frontman-38-shin_l-1-joe-parts.png`: the real knee, the cards, the thigh's card alone, the shin's card alone).

- **A card is a picture of a rigid piece, taken as it stood.** Squat facing the eye and you look along the thigh at its cut end, and down into the top of the shin. Neither picture ever saw that from outside. What they hold there is the inside of the trouser leg, the lap each part borrows from the other, and the ball.
- **The dark rings are those insides**, with bold ink's line, or the pixel look's, drawn round each of them.
- **The cloth pulled over a bent kneecap is in no picture.** It only exists when the model bends. No fill colour makes it.

**How it is measured.** `just impostor-seams` counts bare pixels, and a plugged socket has none. So `just impostor-knees` (`scripts/impostor/judge_joints.py`) compares what is drawn. It stands the real model in the take's own poses, draws it twice as fine as the screen, draws the cards from the same eye, and in a disc about each joint says:

- **likeness**: how well the cards' light and dark follows the model's. 1 is the same shapes in the same places, 0 is nothing in common;
- **blots**: how much of the disc is a good deal darker than the model (a ring, a hollow, a scratch);
- **bare**: pixels of the model's body the cards leave uncovered.

It looks at the moment of the squat (38 seconds in, both knees of all three dancers) and at the two moments of the dance where each kind of joint is bent furthest, through the set's crew camera, from 2 m and from 1 m. The same disc laid on the middle of a thigh or an upper arm, where nothing bends, says what cards score when nothing is wrong: 0.4 to 0.6 (the disc reaches the joints at either end, so it moved too: 0.42 to 0.60 from 1 m in bold ink).

**Two ways were tried.**

| | knees, likeness from 1 m | through the crew camera | blots, from 1 m | what it adds |
|---|---|---|---|---|
| the cards as they were | 0.36, 0.39 | 0.47, 0.45 | 16%, 11% | |
| a card of its own for each knee and elbow, pictured bent at 0, 45, 90, 120 and 150 degrees | 0.46, 0.51 | 0.64, 0.66 | 10%, 6% | sheets half as big again: bold ink 14.1 to 20.8 MB, 15.7 to 24.4, 25.6 to 42.6 in memory; pixel art 5.0 to 6.9, 5.7 to 8.5, 9.6 to 14.5 |
| **a piece of the real model in the joint** | 0.73, 0.76 | 0.72, 0.66 | 2%, 2% | 4,000 to 4,700 triangles a dancer and 2 MB in memory, for every big joint |

(Each cell is bold ink, then "Pixels, both".) The bent pictures do read as a knee (`evidence/knees/tried-bent-cards-lincoln-knee.png`). But a knee is seldom at one of the five bends, so the picture is turned to fit and sits a centimetre or two out at each end; they cost the most memory; and they only suit a joint that bends one way, which a hip and a shoulder do not. The pieces won on every count and are what is kept. `bake_impostor.py --bent knee,elbow` still bakes the other, for anyone who wants to look again.

**What was done** (`scripts/impostor/bake_joints.py`; `gallery/impostor.js`: JOINT_VERTEX, skinMeshes).

- **A piece for each big joint.** The model's own surface round the joint, a few hundred triangles, with the skeleton's pull on every point, so it bends exactly as the whole model would. A detailed mesh cannot be cut down directly (a third of a million triangles that fold through each other), so its pieces are cut from the tidy low-poly version the cast already uses, each triangle cut in four, and every point laid onto the detailed surface. In the dance they sit half a millimetre from the real model at a typical point.
- **Painted with the cards' own colours.** Every place on a piece takes the colour its cards show there, from the picture that sees it most squarely, and which way the surface faces from the same place. So a piece is in the look its cards are in (the pixel sheet's few colours, bold ink's tones) and there is no change of colour where they meet. One 512 by 512 picture for colour and one for facing, a look.
- **The cards step aside.** Round each joint is a zone, a ball 1.25 to 1.7 times as wide as the ring where the two parts meet. Inside it a card shows nothing of its outside: no cut end, no lap, no rim. The piece is drawn in the zone and a centimetre and a half past it, under the cards' edge.
- **Never the inside.** A piece is only drawn from outside. A face turned away from the eye is left out, so the inside of a sleeve or a trouser leg cannot show, and nothing draws a line round it.
- **One thing inside another is still the cards'.** A piece is one skin, the outside one. Look down a wide cuff or into a boot top and what you should see is the arm or the leg inside it, which the piece has not got. So inside a zone a card keeps what lies close to its own bone's line (within 0.6 of the ring), stood 3 cm back: the piece covers it everywhere but there.
- **A joint whose piece would not lie down is left alone.** Where the tidy mesh and the detailed one disagree too much (Lincoln's right elbow, under a rolled sleeve) the bake says so and that joint keeps its cards, ball and all. `--leave` does the same by hand, and `scripts/impostor/joints.json` keeps it for a character: the pirate's two elbows are in there. Each is inside a wide cuff, the piece was the cuff's outside, and from 1 m, bent far, it showed as a blade across his forearm, whatever the judge's likeness said.
- The pieces go in `<version>-impostor-<look>-skinned/` beside the cards, which are not baked again: the new folder reads the old sheets where they are. The pages read it first; a gallery older than this does not read it at all. Add `?joints=cards` to a page's address to see the cards without the pieces.
- **On the tag field** only runners within 8 m of the eye get pieces, and only those are handed to the graphics card. Further off a joint is the cards' own, as before.

**What it is now** (`evidence/knees/joints-before.json`, `joints-after.json`). Likeness, then blots, the joints each moment was picked for; before to after:

| look | joint | likeness, crew camera | from 2 m | from 1 m | blots, crew camera | from 1 m | bare pixels, from 1 m |
|---|---|---|---|---|---|---|---|
| Bold ink | knee | 0.47 to 0.72 | 0.40 to 0.73 | 0.36 to 0.73 | 14% to 4% | 16% to 2% | 1,082 to 475 |
| Bold ink | elbow | 0.52 to 0.58 | 0.48 to 0.59 | 0.49 to 0.60 | 9% to 6% | 7% to 3% | 165 to 228 |
| Bold ink | hip | 0.31 to 0.48 | 0.33 to 0.55 | 0.35 to 0.55 | 10% to 5% | 8% to 2% | 104 to 489 |
| Bold ink | shoulder | 0.52 to 0.57 | 0.53 to 0.57 | 0.46 to 0.55 | 11% to 8% | 8% to 4% | 400 to 658 |
| Pixels, both | knee | 0.45 to 0.66 | 0.43 to 0.74 | 0.39 to 0.76 | 11% to 6% | 11% to 2% | 1,131 to 280 |
| Pixels, both | elbow | 0.44 to 0.50 | 0.51 to 0.62 | 0.56 to 0.65 | 9% to 9% | 4% to 2% | 236 to 174 |
| Pixels, both | hip | 0.36 to 0.52 | 0.42 to 0.61 | 0.45 to 0.64 | 9% to 5% | 6% to 2% | 462 to 267 |
| Pixels, both | shoulder | 0.49 to 0.55 | 0.55 to 0.62 | 0.51 to 0.60 | 9% to 8% | 4% to 2% | 469 to 452 |
| Comic | knee | 0.46 to 0.80 | 0.38 to 0.79 | 0.39 to 0.79 | 13% to 3% | 15% to 2% | 639 to 442 |
| Comic | elbow | 0.44 to 0.58 | 0.40 to 0.54 | 0.45 to 0.55 | 10% to 6% | 11% to 6% | 4 to 150 |
| Comic | hip | 0.24 to 0.45 | 0.24 to 0.47 | 0.24 to 0.43 | 10% to 4% | 9% to 3% | 84 to 466 |
| Comic | shoulder | 0.52 to 0.62 | 0.54 to 0.62 | 0.50 to 0.61 | 9% to 5% | 10% to 5% | 184 to 561 |
| Pixels, baked | knee | 0.45 to 0.74 | 0.37 to 0.74 | 0.35 to 0.74 | 11% to 3% | 14% to 2% | 705 to 398 |
| Pixels, baked | elbow | 0.36 to 0.57 | 0.37 to 0.53 | 0.41 to 0.56 | 10% to 5% | 10% to 4% | 39 to 177 |
| Pixels, baked | hip | 0.40 to 0.58 | 0.39 to 0.58 | 0.40 to 0.57 | 8% to 3% | 7% to 3% | 55 to 449 |
| Pixels, baked | shoulder | 0.49 to 0.59 | 0.53 to 0.62 | 0.49 to 0.58 | 8% to 5% | 6% to 4% | 198 to 479 |

Twelve knees and six of each of the others, the three dancers together. Every joint in the dance bent 60 degrees or more, whichever it is: 0.46 to 0.57 through the crew camera and 0.42 to 0.62 from 1 m in bold ink; 0.45 to 0.56 and 0.48 to 0.67 in "Pixels, both". The worst single knee from 1 m was 0.00 in every look and is 0.39 in bold ink and 0.64 in "Pixels, both". A knee now scores above the middle of a thigh. The bare pixels do not all go the right way: a hip, a shoulder and an elbow leave more of the model uncovered from 1 m than they did in most looks, because the lap that used to overshoot there, and happened to cover it, is gone.

**The faces did not slip** (`just impostor-faces`, `evidence/clear/faces-pieces.json` against `faces-filled.json`; all three dancers, how much of a face is kept, through the crew camera, from 2 m and from 1 m): bold ink 0.742, 0.771 and 0.745, each the same to the third place; "Pixels, both" 0.777, 0.818 and 0.789, the same.

**The seams, look by look** (`just impostor-seams crew-candy-shop pieces evidence/seams --deep 2`, `seams-pieces.json` against `seams-bent-after.json`; pixels of one figure in one picture, 60 pictures; the first of each pair through the crew camera, the second from 2 m):

| look | bare and shut in by cards | | bare between two cards | | sticks out | | line that is not there, % | |
|---|---|---|---|---|---|---|---|---|
| Bold ink | 12.7 to 12.4 | 88 to 103 | 34 to 33 | 272 to 299 | 457 to 319 | 3,170 to 2,188 | 0.63 to 0.44 | 0.51 to 0.30 |
| Pixels, both | 1.2 to 0.7 | 23 to 14 | 4.2 to 3.9 | 78 to 55 | 185 to 137 | 1,580 to 1,141 | 1.50 to 1.20 | 0.84 to 0.63 |
| Comic | 32 to 48 | 120 to 292 | 64 to 78 | 259 to 472 | 635 to 464 | 4,646 to 3,408 | 0.91 to 0.92 | 0.67 to 0.76 |
| Pixels, baked | 29 to 28 | 117 to 163 | 59 to 61 | 291 to 380 | 815 to 594 | 5,598 to 4,083 | 0.69 to 1.06 | 0.64 to 1.10 |

What sticks out is down by a quarter to a third in every look: the laps and spurs at the joints are what the cards no longer draw. "Pixels, both" is better on every count, and bold ink has less line and holds its holes through the crew camera, with about a tenth more from 2 m. The comic look and "Pixels, baked" count worse for holes, and that is a real slip in the count: they have no finished picture to fill a crack on, and where a piece meets its cards a crack a pixel wide is a hole. Part of it is the judge's own: it does not draw a piece's ink shell, which the page does, and it shows a slit across the top of Roosevelt's thighs that the page's picture of the same moment does not have (`evidence/knees/slit-judge-roosevelt-18-comic.png`, `slit-page-roosevelt-18-comic.png`). The two looks the watch page opens in, and bold ink, are the ones that held.

**What it costs.** The cards' sheets are not baked again, so they weigh what they did. A character's pieces are one file and two pictures 512 by 512:

| | triangles | joints | to fetch, bold ink | pixel art | in memory |
|---|---|---|---|---|---|
| Lincoln | 4,031 | 7 | 0.63 MB | 0.38 MB | 2.1 MB |
| Roosevelt | 4,741 | 8 | 0.56 MB | 0.37 MB | 2.1 MB |
| the pirate | 4,195 | 6 | 0.75 MB | 0.46 MB | 2.1 MB |
| Roosevelt's painted model (the tag field's) | 2,489 | 8 | 0.41 MB | 0.23 MB | 2.1 MB |

That is 200 to 1,000 triangles a joint, every one pulled by its bones each frame, where a dancer's cards are 32 triangles and no pulling. Baked with half as many (`--triangles 160`: 2,000 to 2,400 a dancer) a knee's likeness from 1 m is 0.70 where it is 0.74 in bold ink, and 0.75 for 0.76 in "Pixels, both", with half as many pixels again left bare (`joints-tried-half-the-triangles.json`). For three dancers the fuller ones were kept.

On the tag field on this Mac (1080 by 608, poses shared, the gallery as it was and as it is turn about, three goes each), ms of work a frame for a hundred and a thousand Roosevelts, before to after:

| | bold ink | "Pixels, both" |
|---|---|---|
| from the phone test's eye, well back (nobody within 8 m: no pieces drawn) | | |
| painted cards | 7.1 to 7.8, 9.6 to 8.6 | 4.7 to 6.8, 7.3 to 7.4 |
| painted cards, search off far away | 4.0 to 4.4, 6.5 to 7.4 | 3.2 to 4.8, 5.6 to 6.0 |
| detailed cards | 6.4 to 7.7, 9.4 to 8.5 | 4.5 to 5.8, 8.1 to 8.7 |
| detailed cards, search off far away | 3.9 to 5.5, 5.9 to 7.0 | 2.9 to 4.8, 5.9 to 6.2 |
| with the eye among the runners (50 of the hundred and 74 of the thousand get pieces) | | |
| painted cards (124,000 and 184,000 triangles of pieces) | 4.9 to 7.8, 8.0 to 9.3 | 2.2 to 3.5, 4.8 to 7.1 |
| painted cards, search off far away | 4.7 to 4.6, 5.5 to 7.1 | 2.3 to 4.0, 3.2 to 5.7 |
| detailed cards (237,000 and 351,000 triangles) | 4.3 to 7.0, 7.3 to 9.4 | 2.4 to 4.7, 5.0 to 6.9 |
| detailed cards, search off far away | 3.3 to 5.9, 5.5 to 7.5 | 2.4 to 4.6, 3.9 to 6.1 |

(`evidence/knees/cost-mac.json`, taken by `face_cost.py`; `cost-near-mac.json`, by `scripts/impostor/near_cost.py`.) One go differed from the next by two to four milliseconds (the judges were running on the same machine while the eye was among the runners), and from the phone test's eye the two galleries draw the same thing, so the first four rows are what one go differs from another by. With the eye among the runners the pieces cost one and a half to three milliseconds a frame. Every setting still drew a frame every 16.7 ms. "Pixels, both" is cheaper than bold ink at every setting with the eye among the runners; from well back two of the eight settings read the other way round by a few tenths of a millisecond, inside what one go differs from the next by. Meshes are untouched. No phone has run it, and a phone is where it will show: earlier tests found a phone held back by triangles and by pulling points about, and seventy runners' pieces are a few hundred thousand of each. The two knobs are how near a runner must be (`JOINTS_M` in `gallery/tag.js`, 8 m) and `--triangles`.

**What is still weak.**

- **A piece is plainer than its cards close up.** It has a few hundred flat triangles under the cards' colours, so from 1 m a trouser cuff has a stepped edge, and the fine folds are painted, not shaped.
- **Where a piece meets its cards there can be a step of a few millimetres**, and a speck or two of the old picture's edge. The line a look draws on the finished picture mostly hides it.
- **Layered clothes are half and half.** The pirate's boot tops are real cups in his model. The piece is their outside and the cards are what is inside, and from some angles the join between the two shows. The boot tops themselves are his, not a seam.
- **Lincoln's right elbow and both of the pirate's have no piece** and bend as they did.
- **Hips and shoulders gain least**, and leave more bare. They were less wrong to begin with; the web of skin under a raised arm is drawn now only as far as the zone reaches; and from 1 m a few hundred more pixels of the model go uncovered round a hip or a shoulder than did.
- **Bent as far as it goes, a piece folds as the model's skin does.** Behind the pirate's knee at 147 degrees a fin of folded skin and a few specks stand out from 1 m (`knee-pirate-deep-joe.png`). A speck of the same kind shows beside his thigh in the squat.
- **The comic look and "Pixels, baked" count more holes than they did** (the table above), and get no line across a piece's own folds, only its outline. Nothing fills a crack for them. A wider overlap between a piece and its cards, or the crack filling the other looks have, would be the next thing to try.
- **Wrists, ankles, the neck and the waist have no pieces.** They bend less, and a hand or a head is most of a zone. (The neck has one since, and it turned out to matter more than its bend: "A neck that holds", below.)
- **The judge's likeness is light and dark, not a person looking.** It ranks these pictures the way the eye does. It would not notice a knee that is right and ugly.
- No phone has run it.

Stills (`evidence/knees/`, taken by `just joint-shots`, the cards alone on the left and with the pieces on the right): `stage-38-<look>.png` is the squat through the crew camera; `knee-<who>-left-<look>.png`, `-right-` and `-deep-` are a square round each knee, down the page through the crew camera, from 2 m and from 1 m; `elbow-`, `hip-` and `shoulder-` the same for the other joints. `before-*` and `after-*` are the judge's own: the real model, then the cards in each look.

## A neck that holds

When a dancer turned his head or threw an arm up, the head and arms went and the neck, the collar and the tops of the shoulders stayed behind with the chest. Now that skin is one more piece of the model itself, pulled by the skeleton, and the chest's card steps aside for it.

```
just impostor-joints runs/<character> detailed      # the pieces, the neck's among them, for cards already baked: ten seconds
just impostor-neck crew-candy-shop after            # do the head and arms hold to the chest? counted, no browser
just joint-shots "8048/?joints=knees" 8048/ crew-candy-shop evidence/neck --square 0.8 --joints turn=0:neck@28.75   # stills, before and after
```

**What it was** (`evidence/neck/turn-lincoln-joe.png`, `twist-lincoln-joe.png`, `raise-roosevelt-joe.png`: before on the left).

- **The skeleton has a neck bone and two collar bones, and no card rode any of them.** The cut gives every bone's skin to one of 16 parts, and the neck bone's and the collar bones' went to the chest. The chest's card rides the chest bone alone.
- **The dance uses all three.** Over the candy-shop routine the neck bone is turned 17 to 21 degrees from rest on average (62 at most) and the head another 15 to 20 on top of it: a turn of the head is shared about half and half between the two, which is roughly how a real neck shares it (half or more of a turn is at the top two bones, the rest spread down). The collar bones are 14 to 17 degrees from rest on average (33 at most), and they lift with the arm: 15 degrees below level with the arm hanging, about level with it raised, which is a real shoulder's rhythm near enough (a raised arm is about two parts arm to one part shoulder blade and collar bone). So nothing had to be made up. The motion was right, and the cards were not listening to it.
- **So the skin of the neck and collar sat in the wrong place.** Measured on the model itself: the chest's card held that skin 2.8 cm from where the model has it on Lincoln, a typical point at a typical one of these moments (6 cm for the worst twentieth of it, 12 cm in his furthest turn), 2.0 cm on Roosevelt, 1.4 cm on the pirate. The head's joint moves 4 to 5 cm against the chest on average and up to 12; an arm's joint 3 to 4 cm and up to 9. The head slid off a neck stump that stood still, and the stump showed behind it; a raised arm lifted its shoulder off a strap that stayed down.
- **The rig's own weights are hard there**, each point of the neck given to one bone alone: all chest and collar, then all neck, then all head from 8 cm up. That is the real model's doing, not the cards', and it is why the real model creases at the neck too.
- **Not the cause:** a missing rule for the collar bone. One was on the list to try (lift the collar a third of what the arm lifts). The clips already do it.

**How it is measured.** `just impostor-neck` (`scripts/impostor/judge_joints.py --kinds neck,shoulder,yoke`) looks at one disc that holds the neck, the collar and both shoulders, at the two moments of the dance where each of four things is asked most: the head turned furthest, an arm raised highest, a collar bone shrugged furthest, the chest twisted furthest against the hips. Three dancers, through the crew camera, from 2 m and from 1 m. It says what the knee judge says (likeness to the real model, blots, pixels of the model left bare), and two things more: pixels that stick out where the model has nothing, and how far the skin there is drawn from where the model has it, in centimetres, measured on the skin and not on a picture.

**What was looked into, and what was kept.**

| | neck and shoulders, likeness from 1 m (bold ink) | skin off, cm | triangles it adds, a dancer |
|---|---|---|---|
| the cards as they were | 0.591 | 2.1 | |
| a piece of the model for the neck and collar, with the rig's own pull | 0.607 | 0.9 | 1,300 to 1,700 |
| ... its pull evened out along the neck, and cloth held back | 0.609 | 0.9 | 1,300 to 1,700 |
| ... its rim, and the shoulders' rims, eased over to the chest bone instead, so piece and card meet without a step | 0.591 | 1.0 | 1,300 to 1,700 |
| **... pull evened out, cloth held back, a third of the triangles: kept** | 0.610 | 1.0 | 364 and 451 |
| a collar bone that follows the arm by rule; a head's turn spread down the neck by rule | not built | | the clips already do both |
| a collar that lags and settles on a spring | not built | | see below |

(All three dancers together; the pirate has no neck piece, so his share of each number does not move.) Having the piece at all is what counts: 0.591 to 0.607. Evening out its pull and holding cloth back add two or three thousandths, which is inside what the judge can tell apart; they are kept because they cost nothing to draw and are the truer thing to do. The rim easing looked right on paper and scored worst: pinning the edge of a shoulder's piece to the chest takes the collar bone's lift out of the skin round the shoulder, which is the very thing that was missing. A raised arm went from 0.554 to 0.539 and a shrug from 0.627 to 0.606. It is still there to try (`--rim 0.3`). The finer piece bought nothing the judge could see, and a phone pays for triangles.

**What was done** (`scripts/impostor/yoke.py`, `bake_joints.py`; `gallery/impostor-math.js`: partBalls).

- **One piece for the neck, the collar and the shoulder tops.** It is the skin the chest's card used to hold inside a ball about the foot of the neck, most of the way out to the arms (15 cm on Lincoln, 18 on Roosevelt), up to where the head's own skin begins. The two shoulders keep the pieces they had; the new one stops a centimetre inside their zones. It is cut from the tidy low-poly model and laid onto the detailed one, like the knees, but with the head's own faces left out of the way, so it does not climb a beard, a jaw or a hat brim.
- **Only the chest's card steps aside**, and for this piece it keeps nothing back. The head's card stays whole: a face is the last thing to hand over to a few hundred triangles, and the faces' scores did not move (below).
- **A neck is not a hinge.** The piece's pull is the rig's, evened out along the surface over about 3 cm, with the head's own points kept as they were. On a neck drawn finely that is a real change: a nod of 50 degrees that folds the rig's neck at two creases of 20 and 30 degrees bends in a curve instead, 9 degrees at the sharpest (`test_impostor.py`). On the piece as kept, whose triangles are 3 to 4 cm across, it is one or two rounds of each point taking after its neighbours: gentle. Each point is then moved, as it rests, so that in the pose the cards were pictured in it stands exactly where it stood: the piece is the cards' own surface there, and only differs from the rig's as the bones leave that pose.
- **Cloth is not skin.** A collar lies on the shoulders and the neck turns inside it. Where the tidy model has clothing as a mesh of its own and it reaches the neck (Lincoln's shirt: 138 points of his piece), those points give half of what the neck and head pull on them to the chest. So Lincoln's open collar follows a turn of his head half as far as his neck does. Roosevelt's singlet is cut low and its straps lie in his shoulders' zones, so none of it is in his neck's piece: his straps go up with his shoulders because the skin between them now does.
- **A piece that will not lie down is left out**, as with any joint. The pirate has no neck to speak of: his head sits in his coat collar, his shoulders' zones nearly meet under his beard, and the tidy model has 24 triangles in between. The bake found that his piece missed 61% of what is there and left it out. Forced in, it scored worse than his cards (0.508 to 0.484), and his cards were the least wrong to begin with (1.4 cm).
- The pieces go in `<version>-impostor-<look>-necked/`, which the pages read first; the `-skinned` folders and every sheet are left alone, and a gallery older than this does not read the new ones at all. Add `?joints=knees` to a page's address to see the pieces as they were, without the neck's.

**What was not built, and why.**

- **A collar bone that follows the arm, and a turn shared down the neck, by rule.** Both were on the list. The motion already has both, measured above; a rule on top would do it twice.
- **Cloth that lags and settles.** `swing.py` in the tidy-mesh skill does this for skirts and hair: bones for the cloth, trailed behind the body like weights on strings, baked into the clip. A collar has no such bones, and a card or a piece is placed afresh every frame with no memory of the last; a thousand runners would each need one. And a shirt collar is a hand's width of stiff cloth: it settles inside a frame or two. What a collar does that a neck does not is stay put, and that needs no clock, only the weights above.

**What it is now** (`evidence/neck/joints-before.json`, `joints-after.json`; the three dancers together, before to after).

| look | from | likeness, neck and shoulders | head turned | arm raised | shrug | twist | bare pixels | sticks out |
|---|---|---|---|---|---|---|---|---|
| Bold ink | crew camera | 0.61 to 0.62 | 0.63 to 0.66 | 0.59 to 0.60 | 0.63 to 0.64 | 0.51 to 0.51 | 34 to 32 | 261 to 252 |
| Bold ink | 2 m | 0.61 to 0.62 | 0.68 to 0.71 | 0.59 to 0.60 | 0.66 to 0.66 | 0.50 to 0.51 | 317 to 227 | 1,331 to 1,276 |
| Bold ink | 1 m | 0.59 to 0.61 | 0.64 to 0.67 | 0.55 to 0.57 | 0.63 to 0.63 | 0.54 to 0.57 | 1,774 to 1,298 | 4,775 to 4,681 |
| Pixels, both | crew camera | 0.65 to 0.66 | 0.68 to 0.69 | 0.62 to 0.62 | 0.65 to 0.64 | 0.63 to 0.64 | 11 to 10 | 439 to 433 |
| Pixels, both | 2 m | 0.70 to 0.71 | 0.76 to 0.77 | 0.69 to 0.69 | 0.72 to 0.72 | 0.65 to 0.66 | 205 to 132 | 1,629 to 1,628 |
| Pixels, both | 1 m | 0.67 to 0.69 | 0.70 to 0.72 | 0.66 to 0.67 | 0.71 to 0.71 | 0.62 to 0.64 | 1,665 to 1,175 | 5,017 to 5,083 |

The skin itself, how far it is drawn from where the model has it (a typical point, and the worst twentieth): Lincoln 2.8 cm (6.1) to 0.9 (2.4); Roosevelt 2.0 (5.2) to 0.6 (1.5); the pirate 1.4 (4.4), unchanged. By what they were doing, all three together: a turned head 2.7 (7.2) to 1.2 (3.7), a twist 2.3 (5.3) to 1.0 (2.6), a shrug 1.8 (4.3) to 0.9 (2.3), a raised arm 1.6 (4.2) to 0.9 (2.4).

Read plainly: the skin is where it should be to within a centimetre where it was two or three out, a quarter to a third fewer pixels of the model are left bare from close by, and the likeness moves by a hundredth or two, most for a turned head. The likeness is a small number because the disc is the whole bust, head and both shoulders, and the piece is a small part of it; the stills say it better. In `turn-lincoln-joe.png` the stump of neck that stood up behind his ear is gone and his collar runs into his neck; in `twist-lincoln-joe.png` his head no longer rides ahead of his shirt; in `raise-roosevelt-joe.png` the singlet's straps go up with his shoulders.

**The knees did not slip** (`just impostor-knees`, `evidence/neck/joints-knees-before.json`, `joints-knees-after.json`; likeness of the joints each moment was picked for, bold ink through the crew camera and from 1 m, then "Pixels, both" the same): a knee 0.72 to 0.72, 0.73 to 0.73, 0.66 to 0.67, 0.76 to 0.76; an elbow 0.58 to 0.58, 0.60 to 0.60, 0.50 to 0.50, 0.65 to 0.65; a hip 0.48 to 0.48, 0.55 to 0.55, 0.52 to 0.52, 0.64 to 0.64; a shoulder 0.57 to 0.59, 0.55 to 0.57, 0.55 to 0.56, 0.60 to 0.62. The knees', elbows' and hips' pieces are the ones they were, to the last triangle; a shoulder gains a little from the skin beside it.

**The faces did not slip** (`just impostor-faces`, `evidence/neck/faces-before.json`, `faces-after.json`; all three dancers, how much of a face is kept, through the crew camera, from 2 m and from 1 m): bold ink 0.742, 0.771, 0.745 to 0.742, 0.771, 0.744; "Pixels, both" 0.777, 0.818, 0.789 to 0.777, 0.819, 0.790.

**The seams** (`just impostor-seams crew-candy-shop after evidence/neck --deep 2`, `seams-before.json`, `seams-after.json`; pixels of one figure in one picture, 60 pictures; the first of each pair through the crew camera, the second from 2 m):

| look | bare and shut in by cards | | bare between two cards | | sticks out | | line that is not there, % | |
|---|---|---|---|---|---|---|---|---|
| Bold ink | 12.4 to 12.1 | 103 to 99 | 33.2 to 31.7 | 299 to 295 | 319 to 319 | 2188 to 2195 | 0.44 to 0.43 | 0.30 to 0.29 |
| Pixels, both | 0.7 to 0.7 | 13.5 to 13.7 | 3.9 to 3.8 | 54.9 to 55.3 | 137 to 138 | 1141 to 1138 | 1.20 to 1.17 | 0.63 to 0.60 |
| Comic | 48.3 to 46.7 | 292 to 283 | 78.0 to 77.0 | 472 to 468 | 464 to 461 | 3408 to 3387 | 0.92 to 0.91 | 0.76 to 0.75 |
| Pixels, baked | 27.6 to 26.7 | 163 to 159 | 60.9 to 59.5 | 380 to 378 | 594 to 592 | 4083 to 4063 | 1.06 to 1.14 | 1.10 to 1.17 |

Nothing moves by more than a few pixels, and nearly all of it the right way. The one slip is "Pixels, baked", whose line that is not there goes from 1.06 to 1.14% of the figure through the crew camera and 1.10 to 1.17 from 2 m. It was not looked into.

**What it costs.** The cards' sheets are not baked again. A dancer's pieces are still one file and two pictures 512 by 512, 2.1 MB in memory:

| | triangles, before | now | points pulled about | joints with a piece | bones that pull on them | to fetch, bold ink |
|---|---|---|---|---|---|---|
| Lincoln | 4,031 | 4,395 | 3,071 to 3,365 | 7 to 8 | 13 of 21, as before | 0.63 to 0.66 MB |
| Roosevelt | 4,741 | 5,192 | 3,249 to 3,641 | 8 to 9 | 15 of 21, as before | 0.56 to 0.61 MB |
| the pirate | 4,195 | 4,195 | 2,961 | 6 | 17 of 21 | 0.75 MB |
| Roosevelt's painted model (the tag field's) | 2,489 | 2,489 | 1,446 | 8 | | 0.41 MB |

So a dancer who has the piece is a tenth heavier in triangles and in points to pull (9% and 10% for Lincoln, 10% and 12% for Roosevelt), and no bone is pulled that was not pulled already: the neck's piece hangs on the chest, the neck, the collar bones and the tops of the arms (Roosevelt's on the head too), and the shoulders' pieces were already pulled by every one of them.

On the tag field on this Mac (1080 by 608, poses shared, this gallery with the neck's piece and without it (`?joints=knees`) turn about, three goes each; `evidence/neck/cost-mac.json` by `face_cost.py`, `cost-near-mac.json` by `near_cost.py`), ms of work a frame for a hundred and a thousand Roosevelts, before to after:

| | bold ink | "Pixels, both" |
|---|---|---|
| from the phone test's eye, well back (nobody within 8 m: no pieces drawn) | | |
| detailed cards | 4.4 to 4.3, 7.5 to 7.8 | 4.0 to 4.2, 5.7 to 6.1 |
| detailed cards, search off far away | 2.2 to 1.9, 3.0 to 4.5 | 1.6 to 2.3, 2.3 to 3.1 |
| painted cards (no neck piece: the same pieces both times) | 4.7 to 4.3, 7.8 to 8.1 | 2.2 to 3.7, 5.4 to 6.1 |
| painted cards, search off far away | 2.1 to 1.9, 3.4 to 3.8 | 1.6 to 1.9, 2.6 to 5.4 |
| with the eye among the runners (50 of the hundred and 74 of the thousand get pieces) | | |
| detailed cards (50 runners: 237,050 to 259,600 triangles of pieces; 74 runners: 350,834 to 384,208) | 6.2 to 5.7, 7.8 to 8.2 | 5.6 to 5.0, 8.9 to 6.0 |
| detailed cards, search off far away | 5.8 to 6.7, 9.2 to 7.1 | 5.6 to 5.0, 6.9 to 5.5 |
| painted cards (no neck piece) | 7.0 to 7.1, 8.3 to 9.3 | 4.9 to 4.0, 7.9 to 6.0 |
| painted cards, search off far away | 6.1 to 7.3, 7.0 to 8.4 | 4.8 to 4.8, 6.1 to 5.4 |
(Five goes each this time. Another piece of work was baking on the same machine throughout, and one go differed from the next by up to five and a half milliseconds, which is more than any of these differences.) From the phone test's eye the two draw the very same thing, since nobody is near enough to get pieces, and the painted cards have no neck piece from any eye: those rows are what one go differs from another by, and they move as much as the rest. With the eye among the runners the neck's piece is 23,000 more triangles in 260,000 for the hundred and 33,000 in 384,000 for the thousand, a tenth, and no cost shows above the noise: six of the eight settings read cheaper with it. Every setting drew a frame every 16.7 ms. "Pixels, both" is the cheaper of the two looks at 28 of the 32 settings by the middle go. The four that read the other way round are three from the eye that stands well back, where no piece is drawn at all (two of them painted cards), and one with the eye among the runners in the gallery without the neck's piece (8.9 against 7.8): none is the neck's doing. Meshes are untouched. No phone has run it. A phone is held back by triangles and by pulling points about, and this is a tenth more of each for a runner within 8 m; the knobs are `--neck-triangles`, `--kinds` without `neck`, and how near a runner must be (`JOINTS_M` in `gallery/tag.js`).

**What is still weak.**

- **The pirate has no neck piece**, and neither has Roosevelt's painted model, the one the tag field opens with: its cards were baked without a joint between head and chest, so there is nothing to hang the piece on until they are baked again. The tag field's detailed cards have it.
- **The piece is plainer than the card it replaced.** A few hundred flat triangles under the cards' colours. The dark folds in the V of Lincoln's open collar are a flat pale patch now, with a white fleck or two where the collar's edge would not lie down on the model; from 1 m it reads as a collar, not as that collar.
- **Where the piece meets the chest's card there can be a step**, a few millimetres as a rule and more in a hard shrug: the piece's rim still follows the collar bones and the card does not. Bold ink draws a short line there now and then (across Roosevelt's chest in `raise-roosevelt-joe.png`). Easing the rim to the chest bone cures the step and costs more than it gives, as measured above; a card for the chest that itself leans a little with the collar bones is the thing not yet tried.
- **A twist is still the worst of the four** (0.51 through the crew camera): most of a twist is at the waist, between the chest's card and the spine's, and the waist has no piece.
- **The head is still one rigid card**, and the piece stops where the head's own skin begins, 8 cm up Lincoln's neck. There the piece goes with the neck bone and the card with the head, and the card laps over it by 2 cm. In a deep nod or a head thrown right back the two part by a centimetre or two under the jaw.
- **Cloth is held back by one number**, half, wherever the tidy model keeps clothing apart from the body. The pirate's coat is part of his body's mesh and gets none of it. Nothing lags or swings.
- **The judge's likeness is light and dark over a whole bust.** It moved by hundredths for a change the eye sees at once; the centimetres on the skin are the better count here, and they are of where the skin is, not of how it looks.
- No phone has run it.

Stills (`evidence/neck/`): `turn-lincoln-<look>.png`, `turn-roosevelt-`, `turn-pirate-`, `raise-roosevelt-`, `shrug-roosevelt-`, `twist-lincoln-` are a square 80 cm across round the foot of the neck on the watch page, down the page through the crew camera, from 2 m and from 1 m, before on the left and after on the right (`just joint-shots`); `stage-28.75-<look>.png` the stage. `before-*` and `after-*` are the judge's own: the real model, then the cards in bold ink and in "Pixels, both".

## Behind the first surface

The pirate's hat had a piece missing: seen from a little below, a wedge of the stage showed through the dip in its brim, where the crown of the hat should be. Every card had the same blind spot. Now a card's pictures go two surfaces deep.

```
just impostor-layered runs/<character>             # the layered sheets and their joint pieces: five minutes
just impostor-layers crew-candy-shop after         # what the layer behind fills, counted, no browser
just gallery                                       # the pages read layered cards first; add ?layers=off to an address to see them without
```

**What was lost, and why** (`evidence/layers/hat-18-close-joe.png`, `after-right-18-close-joe.png`).

- **A picture holds one surface for each pixel: the first its eye met.** From the front the hat's brim hides the crown behind it. Stand a little to one side, or below, and you should see past the brim's edge to the crown. The card's pixel looks down its line through the picture, passes under the brim's edge, and finds nothing: the crown was never pictured there. So it shows the stage.
- **It is the one layer, and nothing else.** Give the same sheet a second layer and change nothing more, and the wedge fills: so it is not the cut, and not the test of the colour sheet's cover. Nothing is thrown away for facing the wrong way either: the bake draws both sides of every face, and from its 26 directions 1.9% of the head's pixels are a face seen from behind (the thin rim of the brim).
- **How much there is behind.** A line through the pirate's head meets a second surface, with air between, at 60% of its pixels, a third at 40% and a fourth at 21%. Nearly all of that is the inside of things: the model is thin shells, a head inside a hat inside a brim, and nobody ever sees the inside of a shell. What an eye a little to one side can see is far less: a fifth as much as the first layer for the pirate, a tenth for Lincoln, a twentieth for Roosevelt, who wears a singlet and no hat.

**What was done** (`scripts/impostor/bake_impostor.py --layers 2`: behind, patches, peel_group; `gallery/impostor.js`: CARD_FRAGMENT; `impostor.py`: card_pixels).

- **Each direction is pictured twice.** The first picture is the one that was there before, pixel for pixel. For the second, a line is followed on through the part from every pixel, and the first surface on it is kept that an eye could ever see: one that faces the picture's own eye, can be seen from outside the part from somewhere up to 40 degrees to one side, and is on the outside of the whole model (a part is cut open at its joints, and through the cut you would see its own inside). Then the part is drawn again with everything in front of those places left out.
- **Specks are dropped.** A patch counts only if, with its thin edges taken off, 3.3 square centimetres are left. A layer's picture is cut down to what it holds, so one stray pixel far off would make it big.
- **It goes on the same two sheets**, beside the first layer's pictures, with a list of its own in `impostor.json` ("behind"). Nothing new to fetch but a taller sheet.
- **The search looks in both.** A card's pixel already walks down a line through its picture looking for where it goes under the surface. It now asks the layer behind at every step too, the same way, and of two surfaces met in one step shows the higher. A layer behind can stand lower than the first ever does, so the search may go on down a few steps more for it alone.
- **One more thing the search learned.** A line can pass under the brim's edge and come down on the crown just where the brim's picture ends and the crown's own begins. That was not counted as landing on anything, because the line was already "under" the picture. Now it is, in pictures that have a layer behind.
- **Tried and left out.** Surfaces that face away from the picture's eye (the strip of a limb just round its edge): a few more pixels filled, a tenth more sticking out round the figure, and the pirate's sheet two thirds bigger where this way makes it a quarter bigger. A third layer: next to nothing in it on these three.
- The sheets are in `<version>-impostor-<look>-layered/`, their joint pieces (with the neck piece) in `-layered-necked/` (older bakes: `-layered-skinned/`, no neck piece). The pages read layered cards with a neck first, then a neck without layers, then layers without a neck. A gallery older than this does not read them at all, and the sheets that were there are not touched.

**What it fills** (`just impostor-layers`, `evidence/layers/layers-after.json`). The three dancers, six moments of the dance, drawn from the sheets one surface deep and from the layered ones, against the real model. Pixels of one figure in one picture, before to after. "Bare" is body the model has and the cards do not; "holes" are the bare pixels shut in by cards on every side; "opened" is what was covered before and is not now.

| look | seen from | bare | holes | filled | opened | sticks out |
|---|---|---|---|---|---|---|
| Bold ink | crew camera | 110 to 92 | 11.9 to 9.1 | 18 | 0.2 | 793 to 804 |
| Bold ink | 2 m from the head | 880 to 752 | 70 to 65 | 130 | 1.2 | 4,019 to 4,098 |
| Bold ink | 1 m | 5,438 to 5,268 | 267 to 222 | 170 | 0 | 7,817 to 7,855 |
| Pixels, both | crew camera | 12.4 to 11.5 | 0.6 to 0.6 | 0.9 | 0 | 316 to 318 |
| Pixels, both | 2 m | 162 to 140 | 8.4 to 8.4 | 22 | 0 | 1,163 to 1,183 |
| Pixels, both | 1 m | 1,231 to 1,206 | 39.6 to 36.1 | 25 | 0 | 2,020 to 2,024 |
| Comic | crew camera | 126 to 114 | 44 to 44 | 12 | 0 | 2,632 to 2,637 |
| Comic | 2 m | 626 to 535 | 160 to 166 | 90 | 0.2 | 9,683 to 9,728 |
| Comic | 1 m | 3,376 to 3,229 | 381 to 330 | 147 | 0 | 19,490 to 19,501 |

Nearly all of it is the pirate, and most of that his hat: round his head in bold ink, 48 bare pixels to 16 through the crew camera, 1,432 to 1,083 from 2 m, 11,230 to 10,856 from 1 m. Lincoln gains a little at his rolled sleeves and collar (17 pixels filled from 2 m). Roosevelt, in a singlet, gains nothing to speak of (3). A third layer was baked for the pirate and counted: the same numbers to the digit.

Over the whole figure, with the eye further back (`just impostor-seams crew-candy-shop layers evidence/seams --deep 2`, `seams-layers.json` against `seams-layers-off.json`, 60 pictures; shut-in holes, then bare pixels between two cards):

| look | crew camera | from 2 m | the walk, from 4.4 m |
|---|---|---|---|
| Bold ink | 12.4 to 9.8, 33 to 24 | 103 to 93, 299 to 268 | 78 to 28, 87 to 30 |
| Pixels, both | 0.7 to 0.6, 3.9 to 3.1 | 13.5 to 13.6, 55 to 55 | 2.2 to 1.6, 3.5 to 2.8 |
| Comic | 48 to 48, 78 to 74 | 292 to 286, 472 to 449 | 83 to 90, 115 to 98 |

The walk in bold ink is where it shows most: an arm swinging past a hip, a thigh past the other, each uncovering what the picture never saw. What sticks out grew by under half a pixel in a hundred, and the line that is not there did not move.

**Nothing slipped.** The first layer is the old sheet, picture for picture (the test holds the two lists against each other), and the pixel sheet keeps its colours: they are picked from the first layer alone. With `--layers off` the seam judge gives `seams-pieces.json` back to the digit.

- **Faces** (`just impostor-faces`, `evidence/clear/faces-layers.json` against `faces-layers-off.json`, which is `faces-pieces.json` again to the digit; how much of a face is kept, crew camera, 2 m, 1 m): bold ink 0.742, 0.771, 0.745 to 0.743, 0.772, 0.749; "Pixels, both" 0.777, 0.818, 0.789 to 0.777, 0.819, 0.793.
- **Knees and the other joints** (`just impostor-knees crew-candy-shop layers evidence/knees --sheets layered-skinned`, `joints-layers.json` against `joints-layers-off.json`, which is `joints-after.json` again): likeness within 0.01 for every kind of joint, look and distance (a knee from 1 m, 0.735 to 0.736 in bold ink and 0.761 to 0.762 in "Pixels, both"; the most any moved is an elbow from 1 m in "Pixels, both", 0.649 to 0.641); blots within a tenth of one in a hundred but an elbow's through the crew camera in bold ink, 8.5% to 8.8%. Bare pixels go down where one thing is inside another: an elbow from 1 m 228 to 192 in bold ink and 174 to 145 in "Pixels, both" (the pirate's cuffs), a shoulder 599 to 558 and 462 to 442.

**What it costs.** Sheets, before to after (in memory; to fetch):

| | bold ink | comic | "Pixels, both" | pictures with a layer behind, of 416 |
|---|---|---|---|---|
| Lincoln | 14.1 to 15.9 MB; 4.0 to 4.3 | 15.1 to 16.4; 4.2 to 4.5 | 5.0 to 5.2; 0.98 to 1.0 | 238 |
| Roosevelt | 15.7 to 16.8; 4.0 to 4.2 | 17.0 to 17.9; 4.2 to 4.4 | 5.7 to 6.0; 1.08 to 1.1 | 144 |
| the pirate | 25.6 to 32.7; 7.2 to 8.3 | 27.1 to 33.3; 7.7 to 8.7 | 9.6 to 11.6; 1.9 to 2.1 | 383 |

A twelfth more for two of them and a quarter more for the pirate, who is all hat, cuffs and coat. A bake takes three to four times as long (the pirate in bold ink, 31 s to 114, with four bakes running at once): every direction is drawn twice, and a line is followed through the model for every pixel in between.

In time, a card whose picture has no layer behind does what it did. One that has reads the data sheet once more a step, and only inside the layer's own small picture. With a dancer filling the picture on the watch page (`scripts/impostor/close_cost.py`, `evidence/layers/cost-close-mac.json`: 1080 by 608, every frame drawn as fast as it will go and waited for, the layers unread and read turn about, three goes each), ms a frame:

| | through the crew camera | 2 m from the pirate's head | 1 m |
|---|---|---|---|
| Bold ink | 1.6 to 1.7 | 2.2 to 2.5 | 1.8 to 2.1 |
| Pixels, both | 1.3 to 1.6 | 1.6 to 1.6 | 1.7 to 1.7 |

(The clock ticks in tenths.) A tenth to three tenths of a millisecond in bold ink, less in "Pixels, both", which stays the cheaper of the two.

On the tag field (`evidence/layers/cost-mac.json`, `cost-near-mac.json`: `face_cost.py` and `near_cost.py`, a hundred and a thousand Roosevelts, painted and detailed cards, all at once and with the search off far away, three goes each) nothing moved outside what one go differs from the next by: bold ink's detailed cards 6.3 to 6.6 ms and 9.3 to 7.3 from the phone test's eye, 8.1 to 8.4 and 10.4 to 9.3 with the eye among the runners; "Pixels, both" 4.9 to 4.3 and 7.3 to 7.0, then 5.8 to 6.2 and 8.7 to 6.7. Every setting drew a frame every 16.7 ms, and "Pixels, both" is under bold ink in all 16 settings after, where it was in 14 before (which says how much one go differs from the next). That is as it should be, because **cards drawn all at once do not read the layer behind**: that way of drawing hands every card's numbers from its corners to its pixels, and seven more would pass what a phone is sure to allow. Drawn one by one, which does read it, a hundred detailed Roosevelts cost 13.8 to 14.0 ms in bold ink and 13.1 to 11.5 in "Pixels, both" (`cost-each-mac.json`). No phone has run any of it.

**What is still weak.**

- **Close up the whole hat sits low.** From 1 m the cards' hat is a few centimetres smaller than the model's all round its top, 10,856 pixels of the pirate's head still bare in bold ink. That is not a missing layer. A card slides its pixels as if the eye were far off, and a brim 25 cm in front of the card is a tenth bigger to an eye 2 m away than the card makes it. Making the pixel's line fan out from the eye, as the eye's own does, would be the thing to try. (Done, and it was the whole of it: "From more angles", below.)
- **A crowd does not get it.** Cards drawn all at once (the tag field's fast ways) show the first layer only.
- **"Pixels, baked" has no layered sheet.** Its sheet was baked by an older recipe that cannot be baked again as it was, and a new one would change its colours. The painted Roosevelt of the tag field has none either: he wears nothing loose.
- **Only what faces the picture's eye is kept.** The far side of a brim's edge, or the strip of a limb just round its outline, still shows as outline falling short.
- **A patch under 3.3 square centimetres is dropped**, and the body of a pixel sheet (a pixel a centimetre) keeps little: its layers are nearly all in the head, which is pictured finer.
- **The comic look's shut-in holes went up in two rows** (160 to 166 from 2 m, 83 to 90 in the walk) while its bare pixels went down: a gap half filled is shut in where it was open.
- **The edge of a layer is not smoothed**: a pixel there takes the one sheet pixel it falls in.
- **One layer behind, 26 directions.** What can only be seen from further round than 40 degrees is in neither picture.

Stills (`evidence/layers/`): `hat-18-<crew|two|close>-<joe|pixel-both>.png` are the pirate's hat off the watch page, before, after, and the pixels that changed in red; `sides-<seconds>-<role>.png` every head through the crew camera, from 2 m and from 1 m, bold ink before and after, then "Pixels, both" before and after; `changed-*.png` the same for more of the figure; `after-<role>-<seconds>-<eye>-<look>.png` are the judge's own: the real model, the cards before, the cards after, and what was filled in green, what is still bare in blue. `scripts/impostor/clear_shots.py --square 0.7` takes the page's.

## From more angles

After the layer behind, the pirate's hat was still wrong close up, and the thought was that the cards needed the model seen from more angles. Four things were built and counted. One of them mended the hat, and it was not more angles.

```
just gallery                                    # the pages now draw this way; add ?fan=off to an address to see them as they were
just impostor-layers crew-candy-shop fan evidence/angles --before-how FAN=0      # the same sheets drawn both ways, counted, no browser
#/watch/crew-candy-shop?head=dots               # (put ?head=dots before the #) every head as a cloud of dots, to look at
```

**What it was.** A card slid its pixels as if the eye were far away: every pixel of a card looked through the picture along the same line. A real eye's lines fan out. From 1 m, a brim 25 cm in front of its card should look a third bigger than the card drew it. So the whole hat sat low and small, and the model's hat stuck out round it: 10,856 pixels of the pirate's head bare in bold ink. Nothing was missing from the pictures. They were being read along the wrong lines.

**What was done: a pixel's line fans out from the eye** (`gallery/impostor-math.js`: fan; `impostor.js`: CARD_FRAGMENT; `tag.js`: CARDS_VERTEX; `scripts/impostor/impostor.py`: fan, card_pixels). The eye's real line through a pixel is still a straight line through the picture, so it is the same search, with a start and a lean of its own for each pixel in place of one lean for the whole card. It costs three numbers a card (where on the card the eye stands square over, and how far off it is) and no more readings of the sheet. The card's corners are pushed out to make room, since what stands toward the eye shows bigger. No sheet was baked again: every sheet there is, layered or not, is drawn this way.

**What it mends** (`just impostor-layers`, `evidence/angles/layers-fan.json`: the three dancers, six moments of the dance, the layered sheets drawn with straight lines and with the fan, against the real model; pixels of one figure in one picture, before to after).

| look | seen from | bare | holes | sticks out | round the pirate's head: bare | ... sticks out |
|---|---|---|---|---|---|---|
| Bold ink | crew camera | 92 to 87 | 9.1 to 7.7 | 804 to 777 | 15.5 to 4.8 | 96 to 69 |
| Bold ink | 2 m from the head | 752 to 318 | 65 to 38 | 4,098 to 3,520 | 1,083 to 39 | 1,825 to 743 |
| Bold ink | 1 m | 5,268 to 485 | 222 to 108 | 7,855 to 6,058 | 10,856 to 458 | 9,387 to 3,019 |
| Pixels, both | crew camera | 11.5 to 10.8 | 0.6 to 0.7 | 318 to 319 | 0.2 to 0 | 53 to 42 |
| Pixels, both | 2 m | 140 to 62 | 8.4 to 4.6 | 1,183 to 1,094 | 181 to 14 | 514 to 265 |
| Pixels, both | 1 m | 1,206 to 139 | 36 to 18 | 2,024 to 1,841 | 2,424 to 127 | 2,483 to 1,081 |
| Comic | crew camera | 114 to 112 | 44 to 42 | 2,637 to 2,675 | 11.7 to 11.8 | 503 to 467 |
| Comic | 2 m | 535 to 348 | 166 to 117 | 9,728 to 9,568 | 469 to 85 | 4,565 to 4,020 |
| Comic | 1 m | 3,229 to 416 | 330 to 188 | 19,501 to 19,987 | 7,111 to 214 | 18,401 to 13,345 |

From 1 m the bare pixels fall by nine tenths in every look, and for the pirate's hat by 24 in 25. Lincoln's whole figure from 1 m in bold ink goes 2,879 to 583 and Roosevelt's 662 to 273. Through the crew camera, which stands well back, the lines hardly fan and little changes, as it should. The layer behind bought 374 pixels of that head from 1 m; this bought 10,398.

**More angles, counted, and set down.** All on the pirate, who has the most to gain, with the fan on, bold ink, three moments (`evidence/angles/layers-*.json`).

- **More directions baked: 62 a part for 26** (`layers-ways62.json`). The sheet goes from 32.7 MB to 76.9 (8.3 MB to fetch becomes 19.8). From 1 m: bare 240 to 167, what sticks out 17,680 to 17,208 (three in a hundred less). From 2 m: bare 302 to 236. Not worth 44 MB a character.
- **The layer behind gathered from many more eyes** (`bake_impostor.py --eyes 15,30,45,60 --eyes-round 12`: 48 eyes out to 60 degrees, where the pages' sheets have 12 out to 40; `layers-eyes48.json`). The sheet grows by a thirtieth and the counts do not move: 240 to 240 bare from 1 m, 302 to 302 from 2 m, 71.3 to 70.7 through the crew camera. The eye is never more than about 30 degrees off the picture it is shown, so what can only be seen from further round is never asked for.
- **The next two directions drawn as well, behind the nearest, to fill what it never saw** (`impostor.py`: AROUND, which the pages do not do; `layers-around.json`, `around-right-18-close-joe.png`). Bare from 1 m 462 to 197, holes 209 to 142; but a tenth more sticks out (14,232 to 15,644), the second pictures speckle through the first on the face, and it is three cards drawn for one.
- **The head as a cloud of dots** (`gallery/dots.js`, `impostor.py`: dots_of, draw_dots; `layers-dots.json`, `dots-right-18-close-joe.png`, the third column of `sides-18-<role>.png`). Every pixel of all 26 pictures of the head, and of the layer behind, is a place on its surface. They are gathered into one cloud, one dot kept for each 5 mm box (the one its picture saw most square-on), and each is drawn as a small flat disc lying on the surface. The pirate's head is 56,525 dots, 1.5 MB, where its pictures are 3.8 MB of his 32.7 MB sheet; Lincoln's 13,050; Roosevelt's 18,892. Counted against cards with the fan on: about the same. From 1 m, bare round the head 310 to 194 and sticking out 3,697 to 3,811; from 2 m, 49 to 60 and 824 to 800. To look at, in bold ink, it is the cleaner of the two close up: nothing swaps as the eye moves, and the hat loses the stipple and stepped edges a searched picture has. It loses the folds bold ink draws into each picture (they have to be left out, or one fold seen by 26 eyes is a scatter of black dots), so the face is softer. It is on the watch page for looking at (`?head=dots`), heads only, and is not what the pages draw.

So the pictures already held the surface. What was wrong was how they were read, and with that right, a card finds nearly all the model has: from 1 m, 485 pixels of a figure of 160,000 are bare.

**What else moved** (the three other judges, the layered sheets with the fan against the same sheets as they were counted before).

- **Joins** (`just impostor-seams crew-candy-shop fan evidence/seams --deep 2`, `seams-fan.json` against `seams-layers.json`; 60 pictures, pixels in all): every count but two is down. Bare pixels between two cards in bold ink 1,459 to 1,320 through the crew camera, 16,103 to 10,627 from 2 m and 536 to 399 in the walk; shut-in holes 586 to 497, 5,578 to 3,388 and 505 to 417. "Pixels, both": bare between cards 188 to 183, 3,278 to 2,354 and 50 to 35. Line that is not there is down in all twelve rows (bold ink through the crew camera 0.44% of the figure to 0.42). The two that rose: shut-in holes in "Pixels, both" through the crew camera, 33 to 34 in 60 pictures, and what sticks out through the crew camera, up by one or two in a hundred in all four looks (bold ink 19,194 to 19,468) while it fell from 2 m and in the walk.
- **Faces** (`just impostor-faces crew-candy-shop fan`, `faces-fan.json` against `faces-layers.json`; how much of a face is kept, crew camera, 2 m, 1 m): bold ink 0.743, 0.772, 0.749 to 0.759, 0.786, 0.785; "Pixels, both" 0.777, 0.819, 0.793 to 0.776, 0.823, 0.812. Likeness is up in all six.
- **Knees and the other joints** (`just impostor-knees crew-candy-shop fan evidence/knees --sheets layered-skinned`, `joints-fan.json` against `joints-layers.json`). Through the crew camera every likeness is within 0.007 of what it was. From 1 m a knee reads better (0.736 to 0.780 in bold ink, 0.762 to 0.773 in "Pixels, both") and so does a hip (0.620 to 0.654; 0.626 to 0.626), and bare pixels fall at every joint (a shoulder 558 to 287, an elbow 192 to 131, a hip 556 to 321, a knee 476 to 328). **One thing slipped: an elbow from 1 m**, likeness 0.599 to 0.569 in bold ink and 0.641 to 0.590 in "Pixels, both" (from 2 m, 0.590 to 0.611 and 0.618 to 0.599), and blots are up a little from 1 m (a hip's 1.8% to 2.6%). Why was not found.
- **The judge had a blind spot of its own**, found here: a card with one corner beside or behind the eye was left out whole, where the graphics card cuts it at the eye and draws the rest. With bigger cards that happened to a chest seen from 1 m off a shoulder (5,531 bare pixels counted where there are 287). It is mended in `impostor.py`. The counts of hats, joins and faces above were made before that, so if anything they count a little too much bare.

**What it costs.** Nothing to fetch and nothing in memory: no sheet changed. In time, a card is bigger close up (its corners make room for what stands toward the eye) and its search a little longer, so there are more pixels to work out. All on this Mac, 1080 by 608, straight lines and the fan turn about, three goes each.

With a dancer filling the picture on the watch page (`scripts/impostor/close_cost.py`, `evidence/angles/cost-close-mac.json`), ms a frame, Lincoln, Roosevelt, the pirate:

| | through the crew camera (all three) | 2 m from the head | 1 m |
|---|---|---|---|
| Bold ink | 1.7 to 2.3 | 2.1, 2.1, 2.6 to 2.3, 2.7, 3.7 | 2.1, 1.6, 2.1 to 2.6, 1.9, 3.7 |
| Pixels, both | 1.6 to 2.0 | 2.4, 1.9, 1.9 to 1.8, 1.8, 2.2 | 1.7, 1.6, 1.8 to 1.9, 1.7, 2.5 |

A quarter to a half of a millisecond for most, and 1.6 more for the pirate from 1 m in bold ink, whose hat now fills the picture as the model's does. "Pixels, both" is the cheaper of the two in every one.

On the tag field with the eye among the runners (`near_cost.py`, `cost-near-mac.json`), ms of work a frame for a hundred and a thousand Roosevelts, drawn all at once:

| | bold ink | "Pixels, both" |
|---|---|---|
| painted cards | 3.7, 11.2 to 4.0, 11.7 | 1.9, 4.4 to 2.1, 4.4 |
| painted cards, search off far away | 3.4, 7.0 to 3.6, 8.2 | 1.8, 3.5 to 2.1, 3.6 |
| detailed cards | 3.5, 10.5 to 3.8, 11.4 | 2.1, 5.5 to 2.3, 5.3 |
| detailed cards, search off far away | 3.2, 7.0 to 3.5, 8.0 | 2.2, 3.9 to 2.4, 4.3 |

A third of a millisecond at a hundred and up to one at a thousand; "Pixels, both" is under bold ink in all eight. From the phone test's eye, which stands well back (`face_cost.py`, `cost-mac.json`), the Mac was busy with other work and one go differed from the next by up to 4 ms, so only the quickest go of each setting says anything: 3.1, 8.1 to 4.0, 8.4 for painted cards in bold ink and 1.7, 3.2 to 2.4, 3.7 in "Pixels, both"; 3.0, 7.5 to 3.9, 8.0 and 2.5, 4.1 to 2.6, 4.3 for detailed cards. By the middle go "Pixels, both" is under bold ink in all eight there too. Every setting drew a frame every 16.7 ms.

The head as dots, against its card with the fan on (`cost-close-dots-mac.json`): the pirate from 1 m 3.8 to 3.4 ms in bold ink and 2.6 to 2.2 in "Pixels, both"; through the crew camera, where three heads are 88,000 dots that cover few pixels, 1.9 to 2.2 and 1.4 to 1.9. Cheaper where a head is big, dearer where it is small.

**The tag field's all-at-once way carries the fan.** That way of drawing hands every card's numbers from its corners to its pixels, and a phone is sure to allow 60 of them. It had 54; the fan makes 57. The layer behind would need 7 more, which is why it is still not there; it could go in as a card of its own, which needs no more numbers, and that is not built.

**What is still weak.**

- **What sticks out is now the bigger miss**: from 1 m in bold ink 6,058 pixels a figure, against 485 bare. The dots have as much of it as the cards, so it is not the search: it is the pictures themselves against a model that bends (a rigid part where the model's skin stretches, a line a pixel wide all round).
- **It costs more close up**, because the cards are bigger: up to 1.6 ms a frame for a hat that fills the picture.
- **An elbow from 1 m reads a little worse** than it did, by the joint judge; nothing else slipped.
- **A card's corners make more room than they need.** The room is worked out from the corners of the picture, not from what is in it, and every pixel of that room is searched before it is thrown away.
- **The dots are an experiment.** One disc size whatever the distance, no folds, the watch page only, and in "Pixels, both" their light and shade come out unlike the cards' (not chased).
- **A crowd still gets no layer behind**, and "Pixels, baked" still has no layered sheet.
- No phone has run any of it.

## A dress

The flamenco dancer is the first of the cast in a long skirt, and a skirt is the one shape the cards had never been asked to hold. Every card belongs to one bone. A skirt spans the hips and both legs, so cut into thigh and shin cards it tore apart between her legs whenever she side-stepped or lunged, and the six chains of bones it really swings on (up to 83 degrees in the dance) were no card's at all. Now a skirt is one piece of its own, swung by its own chains, and it cannot tear.

```
just impostor-detailed runs/<flamenco dancer> midpoly     # her cards, the dress among them
just impostor-layered runs/<flamenco dancer> midpoly      # two surfaces deep, as the pages read them
just impostor-dress groove-flamenco after evidence/dress --ways before=<a run baked with --dress off>:necked,after=:layered-necked
just gallery                                              # #/watch/groove-flamenco, "Cards"
```

**What it was** (`evidence/dress/after-side-1.25-push-joe.png` and the others: the real model, then the cards as they were, the dress's card riding the hips, the dress cut from the model, and the dress as it is now).

- **Torn between the legs.** Cut the old way, the skirt's faces went to whichever bone pulled them most: the top of it to the hips' card, the sides to the thighs' and shins'. In a side-step the two legs' cards go apart and the skirt goes with them, in two halves, with the stage between.
- **Rigid where it should swing.** The chains are not bones any card rides, so what they pulled on folded into the hips' card and hung straight down while the real skirt flew out.
- **A guess under the skirt.** Her detailed mesh is the picture's: one skin, dressed, and what TRELLIS put under a long skirt is a guess. Lift the skirt and there were no legs to show.

**What was weighed.**

| her skirt, eight moments, three eyes | likeness, bold ink | "Pixels, both" | bare pixels, bold ink | torn open, bold ink | torn, "Pixels, both" |
|---|---|---|---|---|---|
| the cards as they were (the skirt among the hips and legs) | 0.25 | 0.26 | 2,853 | 335 | 173 |
| the skirt as one card riding the hips | 0.21 | 0.22 | 3,157 | 314 | 165 |
| one piece, cut down from the detailed skirt itself | 0.38 | 0.39 | 1,250 | 14 | 13 |
| **one piece, the tidy version's skirt laid onto the detailed one: kept** | **0.66** | **0.66** | **288** | **4.9** | **0.7** |

(`evidence/dress/dress-after.json`. Likeness is how well the skirt's light and dark follows the real model's, as the joints' judge counts it: the polka dots, the shadows of the tiers, the hem. Bare is pixels of her the cards leave uncovered within 4 cm of the skirt; torn is the bare ones shut in on every side: the stage seen through her.)

A bell or a cone of cards, one card a chain segment with a picture of the skirt on each, was the other thought. It was not built: neighbouring chains swing apart (one forward, one back, in every turn of the dance), so the cards of a bell part along every seam between them, which is the tear moved from between the legs to between the chains; and a card is rigid, while a skirt's hem bends. Every one-skin way scored far above every card way above, and the knees already showed that a piece of the model beats any picture of a bend (README: "A knee that bends").

The piece cut down from the detailed skirt itself is the truer surface, and lost. Its 194,000 triangles are a TRELLIS mesh of 7,500 scraps welded together; cut down to the size of a joint piece it came apart into islands and holes (8,653 of its 18,260 triangles were scraps), and unwrapped into thousands of little patches whose colour came out in blocks. The tidy version's skirt is one clean skin of 960 triangles, already rigged on the chains: cut each triangle in four, lay every point onto the detailed skirt from outside (as the knees are laid), and it has the tiers' shape, the detailed skirt's colours and a clean unwrap.

**What was done** (`scripts/impostor/rig_detailed.py`, `bake_impostor.py`: chains_of, groups_of; `bake_joints.py`; `impostor.py`: chains_of; `gallery/impostor.js`: skinMeshes).

- **A body under the clothes.** For a character whose clothes hide its body ("A real body under the clothes", above) the detailed model is now the base body with each hiding garment put back on as a mesh of its own, `gear: ruffled skirt`, not the clothed mesh. Weights go kind to kind: the skirt's from the tidy skirt (its chains among them), the body's from the tidy body and the skin under the skirt, never from the skirt. So under the skirt there are legs, in her black tights.
- **Any garment swung by chains that hang over the legs is a dress.** The cut reads the skeleton: bones named as `cloth.py` names its chains (`cloth_<gear>_<chain>_<n>`), whose top hangs from the hips or the spine. A skirt, a dress, a robe, a coat's tails. A hood's chains hang from the head and are left alone: the head's card has the face, and a hood does not tear between the legs. Nothing about her is written down anywhere; any character rigged by `cloth.py` gets it from the same recipe.
- **The dress is a card of its own**, the 17th, riding the bone its chains hang from. The chains' pull on a face counts for the dress, and on a garment that is a mesh of its own the hips' and the legs' pull too. So the thighs' and shins' cards are legs, and the dress's card is the whole skirt as it hangs, from 26 directions, two surfaces deep. Its card is for the crowd and for colour; near by it steps aside.
- **One piece of the model, swung by the chains.** The tidy skirt, 3,840 triangles once cut, pulled by the chains and the hips and the legs exactly as the rigged model is, painted from the dress's own pictures (so the polka dots are the sheet's, in the look's own colours) and drawn the way the knees' pieces are. It is a joint like any other to the pages: its zone is a ball about the hips as big as the dress, in which the dress's card keeps nothing (`"kind": "dress"`, `"about": "hips"`, `"aside": ["dress"]`, `"core_cm": 0`). No new folder and no new look: it is one more piece in `-necked` and `-layered-necked`.
- **Under a skirt the knees lie on the legs.** The knee and hip pieces are cut from the skin the skirt hides (`body under: ruffled skirt` in the tidy version) and laid onto the legs, not the skirt. Cut the old way they were made of skirt and 34 to 37% of them would not lie down.
- **A clip without the chains** (one made for someone else) draws no dress piece, and the dress's card, whose zone is told about the chain's top bone, rides the hips as it is. Every other piece still draws: a bone the clip lacks is stood in for by the nearest above it that it has.

**What it is now**, by what each moment asked (bold ink; "Pixels, both" in brackets; the take's moving camera, the crew camera and 2 m from the skirt together):

| | likeness, before | after | bare, before | after | torn, before | after |
|---|---|---|---|---|---|---|
| the widest lunge (0.75 s, 8.75 s) | 0.25 (0.27) | 0.68 (0.68) | 1,460 (1,047) | 264 (110) | 268 (99) | 4 (0) |
| the widest side-step (0.25 s, 1.25 s) | 0.24 (0.24) | 0.68 (0.66) | 4,183 (3,720) | 231 (76) | 516 (300) | 8 (1) |
| the deepest stance (0 s, 12 s) | 0.39 (0.41) | 0.66 (0.69) | 1,209 (902) | 231 (66) | 118 (36) | 0 (0) |
| the hem flung furthest (3 s at 62 degrees, 9.5 s at 68) | 0.13 (0.14) | 0.61 (0.62) | 4,558 (4,073) | 425 (143) | 438 (258) | 7 (1) |

Through the moving camera, which is what the dance is filmed with: likeness 0.25 to 0.60 in bold ink and 0.23 to 0.61 in "Pixels, both", 42 torn pixels to 5 and 7 to none. In bold ink the worst of the 24 pictures now scores above the best of them before (0.52 against 0.49); in "Pixels, both" not quite (0.47 against 0.54). `evidence/dress/after-<move>-<seconds>-<eye>-<look>.png` are the judge's own; `push-first-mesh-then-cards.png`, `-middle-`, `-last-` are the push-in's first, middle and last pictures off the watch page, her mid-poly mesh as the film was made and her cards now, in bold ink (the cards' alone: `exports/omni/groove-flamenco/cards/`, kept out of git).

**What it costs.** Her sheets are the size anyone's are: bold ink 15.6 MB in memory (21.9 two surfaces deep, against the pirate's 32.7), "Pixels, both" 5.2 (6.6). Her pieces are 9,072 triangles where a dancer's were 4,000 to 5,200, 3,840 of them the dress, and their pictures 1,024 pixels square instead of 512 (a skirt is as much surface as every other piece together): 8.4 MB in memory where the others' are 2.1, 1.6 MB to fetch. `--atlas 512` and `--dress-triangles` are the knobs. Not timed on the tag field or a phone.

**What is still weak.**

- **Her legs came through her skirt** in the widest stances, at the start and the end of the dance (`push-first-mesh-then-cards.png`). That was the swing, not the cards: the real model and her mesh did it too. Mended in "Legs inside the skirt", next.
- **The tiers are softer than the cards'.** The piece is a smooth skin laid onto the ruffles, so the tiers are in its shape only as far as 3,840 triangles reach; their edges come from bold ink's line on depth, wavy where the cards had them crisp. 22% of its area is pulled out more than 2.5 times, or turned over, as it lies onto the flounces, and shows as streaks on the lowest tier close up.
- **The waistband is jagged** close up: where the piece's top edge meets the top's card there is a row of little teeth (`cards/last.png`). (Mostly mended in "Shoulders that hold", below: the skirt is now worn over the body.)
- **The 17th card shares the hips' number** on the finished picture (a figure has numbers for 16), so bold ink draws no line between the skirt and the hips, which is right, and none for a small step between the skirt and a thigh, which mostly is.
- **Only one character has it.** The villager's tunic has four chains from the hips and would be a dress by the same recipe; his mid-poly rig also has four chains named `cloth_linen_tunic_9_*` hanging from his head, which the recipe leaves alone (they are the fault that crashed the joint pieces before; not mended here). The ninja's hood is not a dress. The pirate's coat is cut at the waist and has no chains. Neither the villager nor the ninja has cards to try it on.
- **A crowd gets the rigid card.** On the tag field a runner further than 8 m gets no pieces, and her skirt is then the dress's card riding the hips, which does not tear but does not swing.
- No phone has run it.

## Legs inside the skirt

In her wide stances, lunges and side-steps the flamenco dancer's legs came out through the front of her skirt, on the plain mesh film as much as on the cards. Now the skirt goes over her knees and her legs stay under it.

```
just impostor-legs groove-flamenco after                                         # every frame of the take, measured
just impostor-legs groove-flamenco before evidence/unclip --shots <the old shots folder>
```

**Where the swing lives.** Only in Blender. `swing.py` plays the baked dance through once more and works out where the skirt's six chains of bones go, a frame at a time, and keys them into the take's `.glb`. Everything that draws her reads those keys: Blender's films, the watch page's mesh, her cards' dress piece (it is skinned to the same chains) and the tag field. Nothing in the browser moves the skirt on its own. So one fix in `swing.py` holds everywhere, and her cards did not need baking again: their weights and pictures do not depend on the motion.

**Why the legs got through.** The old swing kept each chain, a line of three bones, out of a rod round each thigh and shin. But the rods were only as thick as the gap between a chain and a leg as she stood when the skirt was made, which near the hip is almost nothing. The cloth between two chains was never tried at all, so a knee slid between two chains straight through the panel. Her hem hangs below the last joint and her flounces stand off the chains, and none of that was tried either. Nothing kept the hem off the floor.

**What it does now** (`swing.py`, for any garment whose chains hang from the hips or the spine: a skirt, a tunic, a coat's tails):

- **Legs as thick as they are.** Each thigh and shin is measured by rays out from the bone to the skin of the body she is rigged with, at eight places along it and twelve ways round, so a thigh is wider front to back than side to side and a shin has its calf. The cloth keeps 1.7 cm off that.
- **The whole skirt kept out, not three lines.** The chains, the panels between neighbouring chains, and every point of the skirt itself, skinned the way the mesh is (part chain, part hips or thigh), are tried against the legs on every frame. Anything inside pushes the joints it hangs on out.
- **Legs stay inside.** Cloth found on the inner side of a leg goes round to the outer side, not further in, because the legs are inside the skirt. The settling before the dance starts brings her legs from standing into the first pose slowly, so the skirt starts outside them.
- **The floor.** No point of the skirt goes below the floor.
- **No shaking.** A push turns only partly into speed, so the cloth slides over a leg instead of bouncing, and each frame's turn is eased with its neighbours.
- **Room to swing.** A skirt's chains may now turn 100 degrees out and 75 sideways (`cloth.py`), because a lifted knee lifts a skirt further than it ever swings by itself. A hood's chains are left as they were.

**What was weighed.** Instead of moving the chains, the skirt could stop holding on to her thighs: the panels that rest on a thigh as made keep part of the thigh's pull. Tried with that pull taken away, every frame clipped and the skirt flew out to 106 degrees on average, so that pull stays, and the chains are pushed with it in mind. More room off the skin (3 cm) clipped less (99 frames) but held the skirt out further still (91 degrees on average); 1.7 cm is the middle of that.

**Before and after**, the whole 14 s push-in, 421 frames (`evidence/unclip/legs-*.json`):

| her mid-poly mesh (what Blender films and the page draws) | before | after |
|---|---|---|
| deepest the skirt goes into a leg | 8.6 cm | 7.4 cm |
| frames where it goes in more than 0.5 cm | 403 | 133 |
| ... more than 2 cm | 391 | 38 |
| frames where a leg's middle goes out through the cloth (not under the hem) | 334 | 1 |
| ... how much of the leg, at most | 60 cm | 0.6 cm |
| hem below the floor | 4.3 cm, 20 frames | 0.03 cm, 1 frame |
| the chains swing, at most (on average) | 81 (34) degrees | 126 (78) degrees |
| the hem shakes, frame to frame | 7.3 mm | 7.5 mm |

Her low-poly model (the gallery's "Model", and the crowd): a leg out through the cloth on 330 frames before, 15 after; deepest 9.2 cm before, 5.1 after; hem below the floor 4.4 cm before, 1.4 after.

**Pictures**: `exports/omni/groove-flamenco/unclipped/` (out of git): the push-in's first, middle and last moments in bold ink, as her mesh (`mesh-*.png`) and as her cards (`cards-*.png`). The old ones are left where they were. Her cards' dress piece is now drawn from both sides, so a skirt flung up shows its inside instead of the set through it.

**What is still weak.**

- **It still brushes her legs.** A third of the frames have some cloth more than half a centimetre into a thigh or shin, mostly a few centimetres at the side of a thigh, from panels that are part chain and part thigh. The worst are around 9.2 s, when her right knee comes up highest.
- **She wears it wider.** Because she stands wide nearly the whole dance, the skirt is held out by her legs most of the time: the most-lifted chain is out 78 degrees on average where it was 34. In the low wide stance at the start it reads as a skirt pushed up over her knees, nearly flat at the sides.
- **Her walk and run are as they were.** The clips she was given before (`profiles/midpoly-walk.glb`, `-run.glb`, which the tag field and the cards page play) were baked with the old swing. Swung again in a scratch copy, her walk went from a leg out through the cloth on 11 of 25 frames to none, and her run from 16 of 18 to 1. They are rebuilt when her walk and run are made again.
- **The villager's tunic** goes through the same code (four chains from the hips), and its walk and run measure the same before and after (5.5 and 4.7 cm into his legs): that is cloth his thighs carry on their own, not the swing.
- **The shot in the main folder is not rebaked.** The new take lives in this branch's own `shots/groove-flamenco/` (`midpoly-groove.glb`, `lowpoly-groove.glb`); `just cast groove-flamenco runs/<the flamenco dancer> "" groove` makes it again anywhere. The mp4 films and Omni's pack were not remade.

## Shoulders that hold

When the flamenco dancer threw an arm overhead, her cards grew a ring of black scraps and skin-coloured chunks round the shoulder, off her body, and the top met the skirt in a row of black teeth. Now the shoulder holds through a full raise and the skirt sits over the top.

```
just impostor runs/<character> ...                                   # cards cut with the shoulder held (the default now; --held 0 cuts as before)
just impostor-joints runs/<character> detailed                       # the pieces: bigger shoulders where the arms are slim, a top painted on cut as skin
just impostor-shoulders groove-flamenco after                        # the neck and shoulders, counted, through the take's own push-in camera too
just impostor-shoulders groove-flamenco before evidence/shoulders --runs <a folder of runs holding the old cards>
```

**What it was** (`exports/omni/groove-flamenco/shoulders/raise-*-before-after.png`, out of git: before on the left). Each part of her was drawn alone and coloured, at the last moment of the push-in (`evidence/shoulders/before-figure-13.75-raise-1.png` is the judge's own).

- **The scraps were the arm's card, not the dress.** A card is cut with the arms hanging. The arm's card takes some of the chest's skin next to it, so the skin under an arm goes up with the arm: everything its bones pull on by a quarter or more, and everything within reach of the line where arm and chest meet. On her that reached 15 to 17 cm down the side of her top. Her model's weights came from a coarser one, so the line between arm and chest is a fringe that runs down her side, not a ring round the shoulder, and the reach followed it. Raise the arm overhead and that card turns about the shoulder like a rigid plate: skin from 15 cm below the shoulder ends up 15 cm above it, in the air. Inside the shoulder's zone (where a piece of the model is drawn and the cards step aside) that never shows; outside it, it is the black ring. Of what her arms borrowed from the chest, 280 and 340 cm² lay outside the zone. Roosevelt's arms borrowed as much and only 1 to 3 cm² of it lay outside, because his zone is wider.
- **Her zone was too small for her shoulders.** A shoulder's zone was 1.35 times the ring where arm meets chest: 12 to 19 cm on the men, 8.5 on her, whose arms are slim. But what stretches when an arm goes up (the cap of the shoulder, the deltoid, the armpit) is as big as the shoulders are wide, not as thick as the arm.
- **The fins were her top's straps, from the wrong model.** Her detailed model is now her base body (the top painted on its skin, black) with the skirt put back as a mesh. The neck and shoulder pieces were still cut from the tidy model's "sleeveless top", whose straps are plates standing off her shoulders by up to 10 cm. Laid onto her skin they tore, and the neck piece keeps a torn strap where the tidy model had it, so they stood out as fins.
- **The teeth at the waist were her body showing through the skirt.** The skirt's piece lies on the skirt, and the skirt's waistband lies on her body within millimetres. The body's cards are pictures read to the nearest pixel, so along the waistband the body came out in front of the skirt in spikes.
- **Not the cause:** the skirt claimed by the chest or shoulders (none of it is in either), the yoke's reach (her neck piece is 13.7 cm, as on the men), or the sheets' colours bleeding.

**What was done.**

- **A shoulder holds what it borrows** (`bake_impostor.py`: HELD, `--held`; `impostor.py`: round_cut). At a shoulder, neither the arm's card nor the chest's takes anything of the other's further than 1.35 rings from the joint, by the pull or by reach. That is the shoulder's zone, so all that it borrows is under the piece. Her cards are baked again with it (every look, one and two surfaces deep). The men's are not: their sheets are as they were.
- **A shoulder is as big as the shoulders are wide** (`yoke.py`: shoulder_zone). Its zone is never less than 0.65 of the way from the joint to the foot of the neck: 9.9 cm on her. On the men the ring's zone is already more (0.69 to 0.72 of the way), so nothing changes for them.
- **A top painted on is skin** (`yoke.py`: cut_from). When the pictured model is a body with some garments put back on it, every garment that was not put back is painted on its skin, and the pieces are cut from the tidy model's skin under that garment ("body under: sleeveless top"), not from the garment. So her neck piece is her skin and moves like skin, and nothing of the straps stands off it. It is not held back from the neck the way Lincoln's collar is: she has no collar. A clothed model of one skin (the men's) is cut from its garments as before.
- **The skirt is worn over the body** (`bake_joints.py`: DRESS_OVER_M; `impostor.py`: draw_skin; `gallery/impostor.js`: JOINT_VERTEX). The skirt's piece wins over a card of the body that is within 1.5 cm of it (`"over_cm"` in impostor.json). It is slid toward the eye along its own line, so it lands on the very same pixels.

**What was weighed, and left off.**

| tried | what it did | kept? |
|---|---|---|
| the shoulder's zone 0.8 of the way to the neck (12.2 cm) | "Pixels, both" better (shoulders from 1 m 0.68 to 0.71), bold ink worse (0.69 to 0.68), more bare | no |
| her pieces cut from the tidy top, as before (`--painted garment`) | likeness 0.03 higher and far fewer bare pixels, but the strap fins come back and more sticks out | no |
| her pieces pulled as her pictured body is where they lie (`--pull pictured`) | the skin drawn further off (0.6 to 0.9 cm), no fewer bare pixels | no |
| inside a zone, a card keeps what is near its own bone's line on its own side of the joint only | for her a little less sticking out, but the men's likeness fell by a hundredth | no |

**How it is measured.** `just impostor-shoulders` is the neck judge (`judge_joints.py`, "A neck that holds") on her take. It adds the take's own moving camera (`--eyes push`) to the crew camera, 2 m and 1 m. The moments are the dance's own: the arm raised highest (10.75 s, both arms up; 13.75 s, the last raise), the collar bone shrugged most (the same two), the head turned most (3.5 s, 4.5 s) and the chest twisted most (0 s, 1 s). Cards are layered, with their pieces, as the pages draw them.

**What it is now** (`evidence/shoulders/joints-before.json`, `joints-after.json`; before to after).

| look | eye | shoulders, likeness | worst shoulder | neck and shoulders, arm raised | blots, shoulders | sticks out, shoulders | bare, shoulders |
|---|---|---|---|---|---|---|---|
| Bold ink | push-in camera | 0.63 to 0.71 | 0.24 to 0.57 | 0.51 to 0.58 | 14% to 10% | 308 to 125 | 19 to 55 |
| Bold ink | crew camera | 0.62 to 0.71 | 0.35 to 0.56 | 0.53 to 0.61 | 15% to 13% | 172 to 91 | 9 to 34 |
| Bold ink | 1 m | 0.62 to 0.68 | 0.39 to 0.55 | 0.63 to 0.70 | 10% to 5% | 3,748 to 1,767 | 286 to 1,122 |
| "Pixels, both" | push-in camera | 0.66 to 0.71 | 0.41 to 0.48 | 0.64 to 0.70 | 17% to 14% | 423 to 253 | 11 to 26 |
| "Pixels, both" | crew camera | 0.59 to 0.70 | 0.37 to 0.59 | 0.62 to 0.71 | 18% to 15% | 275 to 191 | 1 to 7 |
| "Pixels, both" | 1 m | 0.60 to 0.68 | 0.30 to 0.52 | 0.68 to 0.74 | 10% to 6% | 4,346 to 2,379 | 339 to 853 |

The skin of the neck and collar is drawn 0.56 cm from where the model has it, where it was 0.61 (0.63 to 0.56 with an arm raised). A turned head goes 0.66 to 0.76 from 1 m in bold ink. The neck itself, as a joint, is within a hundredth of where it was (0.79 to 0.78 from 1 m in bold ink).

Read plainly: what sticks out round her shoulders is down by a third to three fifths. The dark blots are down by a tenth to a half. The worst single shoulder through the push-in camera scores more than twice what it did (0.24 to 0.57). The price is bare pixels. The ring of scraps used to cover the skin of her side that the real model stretches up with the arm, and that skin is now not drawn. Up to 1,100 pixels round a shoulder from 1 m in bold ink are uncovered, a few dozen through the cameras the dance is filmed with. The chest twisted is the one move that did not get better: likeness the same, and more both bare and sticking out (from 1 m in bold ink, 818 to 3,624 bare and 2,033 to 3,839 sticking out). Why was not found.

**The skirt did not slip** (`evidence/shoulders/dress-shoulders.json`: the dress judge on her skirt, the old cards and the new side by side). Likeness 0.378 to 0.383 in bold ink and 0.432 to 0.432 in "Pixels, both", with the same pixels bare, torn and sticking out. The waistband's teeth are gone (`waist-last-joe-before-after.png`). A small notch is left at one side.

**The men did not change.** Their sheets and pieces are not baked again, and nothing the page draws for them changed. The skirt's "over" is only on a dress. The judges were run with the code as it was and as it is (`evidence/shoulders/joints-men-neck-*.json`, `joints-men-knees-*.json`: `just impostor-neck` and `just impostor-knees` on the candy-shop crew, layered cards with their pieces). Every number is the same to the last digit: likeness, blots, bare, sticking out and the skin's centimetres, for every joint, look and eye. For example, neck and shoulders from 1 m are 0.620 and 0.620 in bold ink, a knee 0.486 and 0.486, a shoulder through the crew camera 0.513 and 0.513.

**What it costs.** Nothing to draw: the same number of cards, and her pieces are 8,790 triangles where they were 9,072. Her sheets are the size they were (bold ink 21.7 MB two surfaces deep, "Pixels, both" 6.6).

**What is still weak.**

- **Her side, overhead.** In the real model the skin of her side goes up with the arm. A card is rigid and her shoulder's piece stops at 9.9 cm, so with an arm high some of that skin is not drawn (the bare pixels above). The chest's card also keeps a little of her armpit where the arm left it, which sticks out as a skin-coloured flap below the raised arm (`raise-last-*-before-after.png`). A bigger shoulder piece was tried and helped one look and not the other.
- **Bold ink scribbles on the raised arm**: the line drawn where the shoulder's piece and the arm's card step apart in depth draws a few short marks inside the upper arm.
- **The chest twisted** reads no better, and leaves more bare and more sticking out.
- **The men's cards are not cut the new way.** Their sheets were left alone. When they are baked again they will be cut with the shoulder held. Their borrowed skin already lies nearly all inside their zones (1 to 3 cm² outside, measured on Roosevelt), so little should change. That is not measured.
- **Her walk and run** play the same cards, and were not looked at.
- No phone has run it.

Pictures (`exports/omni/groove-flamenco/shoulders/`, out of git): `first.png`, `middle.png`, `last.png` are the push-in's first, middle and last moments in bold ink as cards. `raise-last-joe-before-after.png` and `raise-last-pixel-both-before-after.png` are close on her shoulder at the last raise (13.96 s). `raise-both-*` are the same with both arms up (10.75 s). `waist-last-joe-before-after.png` is the waistband. All of them are before on the left, taken off the watch page in a headless Chrome. `evidence/shoulders/after-*` and `before-*` are the judge's own: the real model, then bold ink, then "Pixels, both".

## No flaps

After "Shoulders that hold" the scraps were gone, but three things still showed with her arm overhead. A flap of skin stuck out below the raised arm like a little hand. Short bold-ink marks sat inside the raised upper arm like a tattoo. A dark jagged choker ringed the base of her neck. Now the choker is gone, the tattoo is down to a mark or two, and the flap is a small edge.

```
just impostor runs/<character> ...                   # cards cut with the shoulder and the neck held (the default)
just impostor-joints runs/<character> detailed       # her pieces: the armpit drawn from both sides, the head's card stepping aside up the neck
just impostor-shoulders groove-flamenco after evidence/shoulders-2
```

**Where each one came from.** As before, each card and piece was drawn alone in its own colour at the last raise. Every inked pixel was sorted by why bold ink drew it (an outline, a step in depth, a fold) and between what.

- **The flap under the arm was the chest's card.** It holds a little of the arm's skin next to the joint, so the cards close up when the arm bends. When the arm goes up the collar bone lifts, and the shoulder joint goes up a few centimetres with it. The shoulder's zone (where the cards step aside for the piece) moves with the joint. The arm's skin that the chest's card kept is left behind, outside the zone, and shows. Measured on the model, those pixels are skin the arm's bones pull on wholly, 7 to 8 cm from the joint as the cards were cut: inside the zone then, outside it now.
- **The tattoo was two things.** First, holes in the shoulder's piece. Overhead, the armpit's skin folds over on itself, and the fold's under side faces away from the eye, so it was not drawn. Through each hole the arm's card showed from inside the zone (the bit it keeps near its own bone), and bold ink drew a ring round it. Second, bold ink drew a line where the fold's two layers met.
- **The choker was the head's card.** It had taken the neck's skin down to her collar, because the head's bones pull on it a little (4% or more is enough for the head, chest and hips). With her head tipped back that skin swung forward with the head, and its cut end showed as a dark ragged band. Holding that back left the card's cut end halfway down the neck, and the band moved up with it.

**What was done.**

- **The card above a held joint keeps less** (`bake_impostor.py`: HELD_ABOVE). At a shoulder, the chest's card keeps the arm's skin only within 1.0 ring of the joint (the arm's card keeps the chest's within 1.35, as before). The joint moves off the chest when the arm goes up, so what the chest keeps must sit deeper inside the zone. The head's joint is held the same way now: the head's card takes the neck's skin only near its own joint.
- **The head's card steps aside up the neck** (`yoke.py`: HEAD_ASIDE; `bake_joints.py`). The neck's piece already stood in for the chest's card. Now the head's card also steps aside, in a zone of its own, 0.65 of the way from the foot of the neck to the head's joint (9 cm on her). The neck's piece carries the head's own neck skin up that far. The jaw, the face and the hair stay on the card. Tried at 0.8: it also cut away the bottom of her bun.
- **The armpit drawn from both sides** (`impostor.py`: draw_skin; `gallery/impostor.js`: JOINT_VERTEX, JOINT_FRAGMENT). Inside its zone a shoulder's piece also draws faces turned away (`"sides": 2`), lit as the side the eye sees. Such a face says it is the chest's card, not the arm's, so bold ink draws no line between the fold's two layers. The arm's card keeps nothing in the shoulder's zone (`"cores_cm"`: a shoulder has no wide cuff to look down). Only past the zone (the piece is drawn 1.5 cm further) do faces turned away stay out, because past it they would be the inside of the tube, seen down its cut end.
- **A piece may give a card a zone and a core of its own** (`"zones_cm"`, `"cores_cm"` in impostor.json; `impostor.py`: part_zones; `gallery/impostor-math.js`: partBalls). Both readers do the same, and a test holds them together.

**What was weighed, and left off** (`judge_joints.py` on her take, from the push-in camera and from 1 m, each way against the others).

| tried | what it did | kept? |
|---|---|---|
| both of a shoulder's cards stepping aside right out to the piece's edge | the last flap went, but more of her was left bare and she read less like herself | no |
| the shoulder's piece drawn from outside only, as before | holes, and the ring of ink round each | no |
| the arm's card keeping its core inside the zone | the tattoo's blob | no |
| a shoulder piece's pull evened out along it, as the neck's is (3 and 8 cm) | the folds stayed where they were | no |
| the head's card stepping aside 0.8 of the way up the neck | the bottom of her bun went, more bare | no |
| the head's card left whole (only the cut held) | numbers like the kept way, but the choker came back halfway up her neck | no |

**What it is now** (`evidence/shoulders/joints-after.json` is "Shoulders that hold"; `evidence/shoulders-2/joints-after.json` is this; before to after).

| look | eye | shoulders, likeness | neck, likeness | arm raised, likeness | sticks out, shoulders | bare, shoulders |
|---|---|---|---|---|---|---|
| Bold ink | push-in camera | 0.71 to 0.69 | 0.69 to 0.74 | 0.58 to 0.59 | 125 to 55 | 55 to 63 |
| Bold ink | crew camera | 0.71 to 0.71 | 0.75 to 0.77 | 0.61 to 0.62 | 91 to 55 | 34 to 37 |
| Bold ink | 1 m | 0.68 to 0.68 | 0.78 to 0.79 | 0.70 to 0.70 | 1,767 to 1,072 | 1,122 to 1,298 |
| "Pixels, both" | push-in camera | 0.71 to 0.72 | 0.79 to 0.82 | 0.70 to 0.69 | 253 to 177 | 26 to 28 |
| "Pixels, both" | crew camera | 0.70 to 0.72 | 0.83 to 0.85 | 0.71 to 0.70 | 191 to 158 | 7 to 9 |
| "Pixels, both" | 1 m | 0.68 to 0.70 | 0.86 to 0.87 | 0.74 to 0.76 | 2,379 to 1,656 | 853 to 1,018 |

Round the neck, what sticks out fell from 954 to 549 pixels from 1 m in bold ink, and from 120 to 97 through the push-in camera in "Pixels, both". The dark blots fell in nearly every row. The pixels that stick out (the flaps) fell by a fifth to three fifths.

**What did not get better.** The uncovered pixels went up again, a tenth to a half: from 1 m in bold ink a shoulder 1,122 to 1,298, the neck 313 to 472. The flaps used to cover skin the real model stretches there, the side of her body under the arm and the throat under the jaw, and nothing draws that skin now. Through the cameras the dance is filmed with it is a few pixels a shoulder. The neck's piece also sits further from the model's skin: 0.56 cm at a typical point, now 0.98. Most likely that is the head's own neck skin it now carries, whose pull is evened out along the neck the way the rest of the piece's is, so it bends more gently than the model's does. It was not checked. Through the push-in camera a shoulder in bold ink reads a little less like her (0.71 to 0.69).

**The men did not change.** Their sheets and pieces are not baked again, and nothing new is drawn for them. A piece without `"sides"`, `"zones_cm"` or `"cores_cm"` is drawn as before. `just impostor-neck` and `just impostor-knees` on the candy-shop crew (`evidence/shoulders-2/joints-men-*-after.json` against `evidence/shoulders/`): all 104 rows of the neck's table and all 132 of the knees' are the same to the last digit.

**What it costs.** Her pieces are 9,128 triangles where they were 8,790: the neck's piece carries the skin up to her jaw. The armpit's back faces are drawn only inside the shoulder's zone. Sheets are the same size.

**What is still weak.**

- **A small edge under the raised arm.** The chest's card still keeps a sliver of the arm's skin within a ring of the joint, and from 1 m it shows as a thin outline.
- **Her side under a raised arm, and her throat under the jaw, are partly bare** (above). A piece that reaches down her side as far as the arm's bones pull would draw that stretch. It was not built.
- **A dark spot and one or two short marks** are left in the raised armpit. That is the black of her top's edge on the folded skin, and a fold the bold ink still finds.
- **Black lace-like scraps at her other armpit** with both arms up (`raise-both-joe-before-after.png`, the right of each picture). That is the edge of her top on the shoulder's piece. Not chased.
- **The neck's skin is drawn further off** than before (0.6 to 1.0 cm).
- **The men's cards are not cut the new way** and were not tried with it. When they are baked again, their heads' cards will step aside up their necks too. On Lincoln, whose shirt collar is held back, that has not been looked at.
- No phone has run it.

Pictures (`exports/omni/groove-flamenco/shoulders-2/`, out of git): `first.png`, `middle.png`, `last.png` are the push-in in bold ink as cards. `raise-last-*-before-after.png` are close on the raised shoulder at the last raise, `raise-both-*` with both arms up (10.75 s), and `neck-last-*` close on the neck. Each is in bold ink and in "Pixels, both", with before ("Shoulders that hold") on the left. `evidence/shoulders-2/after-*` are the judge's own: the real model, then bold ink, then "Pixels, both".

## An armpit that holds

After "No flaps", with her arm overhead, the side of her body under the arm was still partly bare, a dark blob and a thin edge sat in the raised armpit, black lace-like scraps and a spike stuck out of her other armpit with both arms up, and a ragged dark line ran under her jaw. Now each shoulder's piece reaches down her side as far as the raised arm really pulls the skin, and across into her chest and back, and the cards step aside under it.

```
just impostor-joints runs/<character> detailed --from joe-layered,pixel-clear-layered,comic-layered   # her pieces, the armpits sized by how far the arm drags the skin
just impostor-shoulders groove-flamenco after evidence/armpit --stills who:raise                       # the counts, and what draws every pixel at the raises
```

**What was bare, and what drew each scrap.** The judge now paints a picture of who draws every pixel (`judge_joints.py --stills who`: each card in its own colour, each piece a darker shade of its card's, the neck's piece yellow, the far side of a piece striped, bold ink's lines black; then the cards faded, with the model's body they leave bare in blue and what sticks out in red). `evidence/armpit/before-who-figure-13.75-raise-1.png` is the last raise from 1 m, `before-who-figure-10.75-raise-1.png` both arms up. Measured on her real model:

- **Her bare side was skin the arm drags and nothing draws.** The rig pulls her side along with the arm: taken through its range, an arm drags 13,000 points of the skin her chest's card holds by more than a centimetre, up to 14 cm, lying up to 16.6 cm from the shoulder joint. Her shoulder's piece stopped at 9.9 cm and the chest's card, being rigid, leaves that skin where it hung. Between the two the real body is stretched up and out, and nothing was there. It is all chest skin: the arm drags none of her spine's skin more than 3.5 cm, and that only 16 to 19 cm away.
- **The dark blob and the thin edge under the raised arm** were three things: the chest's card's own flap of arm skin; the chest's card's "core", a line it keeps through the joint along its own bone, which at a shoulder runs straight down her side; and holes in the shoulder's piece, through which both showed, ringed in ink. The holes were the bake's own doing. Her piece is cut from several of the tidy model's meshes (her skin under the top, under the top and skirt, and bare), whose points were not joined, so a third of the armpit's back came out as an island and was thrown away as a "scrap" (86 triangles a shoulder before; 160 once the piece reached further).
- **The black scraps and the spike at her other armpit were her left arm's card.** Her detailed model took its pull from the tidy model's nearest surface, and on her left shoulder that is the tidy top's strap, which the arm pulls. So that strap of her top belongs to the arm's card, which swings it overhead like a rigid plate: a black band across the armpit, ringed in ink, with its end sticking out past her side. Measured the same way, her chest drags 4,800 points of her left arm's own skin off the arm's card, out to 13.1 cm from the joint (her right: 8.1 cm, inside the zone).
- **The dark line under the jaw** was the head's card and the neck's piece taking turns pixel by pixel under her jaw, where the two lie within millimetres of each other: a hatched band, which bold ink ringed in a ragged line.
- **The neck's piece "1.0 cm off"** was mostly the judge. Since "No flaps" the piece carries the head's own skin up her neck, and the judge matched those points against the nearest of the chest's skin, a centimetre lower and moving with the chest. Matched against the skin they lie on, it was 0.79 cm. But the head's own skin was really off too, 1 to 3 cm, because the piece takes its pull from the tidy model, which gives that skin partly to the neck, where her real model gives it wholly to the head.

**What was done** (`scripts/impostor/yoke.py`: arm_sweep, arm_pose, pose_bones, skin, side_zone; `bake_joints.py`: arm_drag).

- **Each arm is taken through its range and the drag is measured.** From hanging to overhead, out to the side, forward, across the body and back, once with the collar bone still and once lifted a sixth of the raise (43 ways). Every point of her real model is pulled there by its own bones and measured against the card that holds it as the cards were pictured. Nothing is guessed per character: a skeleton, its pull and its cards are all it reads.
- **The chest's card steps aside as far round the shoulder as its skin is dragged more than a centimetre**: 16.5 and 16.6 cm on her, where the shoulder's zone is 9.9 (`"zones_cm"`; a stray point or two far off does not count, and it is never more than 1.8 times the zone). A threshold of 2 or 3 cm gives the same 16 cm: the dragged skin is all in one place. **The arm's card steps aside as far as the chest drags the arm's own skin**: her left arm 13.4 cm, her right the 9.9 it had.
- **The shoulder's piece reaches that far**: the fold, the stretch of her side, and the edge of her top on it, one skin. Cut from the tidy model as before, its points now **welded** where two of the tidy model's meshes meet, so nothing of it is mistaken for a scrap (6 triangles of all her pieces left out, the neck's, where 268 were). Inside it no card keeps a core, and it is drawn from both sides as far as it reaches (`"back_cm"`), so a fold of the stretched side turning away from the eye is not a hole.
- **Its rim is lit by which way the skin itself faces** (`"rim": "surface"`). A point half the arm's and half the chest's is turned half as far as the arm; on her side overhead that left the lit facing 15 to 50 degrees further from the eye than the stretched skin really is, and bold ink's rim light washed the black of her top pale grey. Now the rim follows the drawn surface (on the page, from the triangle's own slope); the colour and the three tones still come from the cards' sheets.
- **The neck's piece is pulled as her real model is where it lies** (`--neck-pull`; it was the tidy model's pull), so the head's own skin up her neck goes with the head. And it is **worn over a card within a centimetre of it**, as the dress is over her body (`"over_cm"`): under the jaw the throat is the piece's and the jaw the card's, with one line between them.
- `judge_joints.py`: the who pictures above, and the neck's skin matched against the skin each point lies on ("off_cm"; the old way is kept as "off_held_cm").

**What was weighed, and left off.**

| tried | what it did | kept? |
|---|---|---|
| a bigger shoulder piece alone, measured on the tidy model's skin | covered her side, but a third of its back was thrown away as a scrap, and the left strap was not found | no: measured on the real model, and welded |
| the chest's card stepping aside only where skin is dragged 2 or 3 cm | about the same 16 cm (measured then on the tidy model) | (1 cm kept) |
| the neck piece's head skin keeping the rig's pull where the head has half of it or more (evened out only below) | no change at all | no |
| the neck piece's pull not evened out | a little worse at a turned head, a little better at a raised arm | no |

**What it is now** (`evidence/armpit/joints-before.json` is b584004's cards, "No flaps", judged with this code; `joints-after.json` is this; before to after).

| look | eye | shoulders, likeness | worst shoulder | neck, likeness | arm raised, likeness | sticks out, shoulders | bare, shoulders | sticks out, neck | bare, neck |
|---|---|---|---|---|---|---|---|---|---|
| Bold ink | push-in camera | 0.71 to 0.84 | 0.53 to 0.64 | 0.74 to 0.77 | 0.62 to 0.84 | 55 to 34 | 63 to 23 | 48 to 50 | 14 to 12 |
| Bold ink | crew camera | 0.73 to 0.82 | 0.59 to 0.71 | 0.77 to 0.78 | 0.64 to 0.81 | 55 to 42 | 37 to 19 | 36 to 38 | 15 to 16 |
| Bold ink | 2 m | 0.71 to 0.82 | 0.58 to 0.56 | 0.79 to 0.80 | 0.72 to 0.85 | 278 to 172 | 280 to 99 | 158 to 156 | 111 to 101 |
| Bold ink | 1 m | 0.68 to 0.81 | 0.54 to 0.52 | 0.79 to 0.80 | 0.71 to 0.84 | 1,072 to 666 | 1,297 to 379 | 548 to 551 | 472 to 424 |
| "Pixels, both" | push-in camera | 0.72 to 0.82 | 0.51 to 0.59 | 0.82 to 0.83 | 0.69 to 0.86 | 177 to 162 | 28 to 4 | 97 to 100 | 11 to 11 |
| "Pixels, both" | crew camera | 0.71 to 0.79 | 0.61 to 0.67 | 0.84 to 0.85 | 0.70 to 0.82 | 157 to 144 | 9 to 1 | 97 to 99 | 4 to 3 |
| "Pixels, both" | 2 m | 0.71 to 0.82 | 0.55 to 0.68 | 0.88 to 0.89 | 0.76 to 0.87 | 560 to 419 | 177 to 26 | 322 to 311 | 65 to 42 |
| "Pixels, both" | 1 m | 0.70 to 0.82 | 0.56 to 0.63 | 0.87 to 0.88 | 0.76 to 0.86 | 1,656 to 1,146 | 1,018 to 180 | 887 to 867 | 393 to 305 |

(Pixels of the screen in the judge's disc, a shoulder or the neck, an average over the moments; "arm raised" is the neck and both shoulders together at 10.75 s and 13.75 s.) Read plainly: round her shoulders what is left uncovered fell by three fifths to nine tenths, from 1 m in bold ink 1,297 pixels to 379, and what sticks out by a tenth to two fifths. She reads more like herself at every eye and in both looks: through the push-in camera the arm raised goes 0.62 to 0.84 in bold ink. The chest twisted, the one move "Shoulders that hold" left worse, is better too: from 1 m in bold ink 3,972 bare pixels to 1,356 and 3,704 sticking out to 902, mostly the neck's new pull. The skin of the neck and collar, measured on the skin: 0.80 cm off where it was 0.79, at a typical point, and 2.2 cm for the worst twentieth where it was 2.5; with a head turned 0.97 to 0.84 and a chest twisted 1.02 to 0.84, but with an arm raised 0.58 to 0.76.

Her knees, elbows and hips (`joints-knees-*.json`) are within a hundredth of what they were at every eye in both looks.

**The men did not change, as they are.** Their pieces are not baked again here, and a piece without `"back_cm"` or `"rim"` is drawn as before. `just impostor-neck` and `just impostor-knees` on the candy-shop crew with b584004's code and with this one (`evidence/armpit/joints-men-*-before.json`, `-after.json`): every row is the same to the last digit but a few, and those few change just as much between two runs of the same code (`joints-men-neck-after-again.json`): the judge's own wobble, at close-up views of nine moments (Lincoln at 28.75, 30 and 35.75 s, Roosevelt at 15.75, 17.5 and 55.75, the pirate at 21.5, 34 and 36; up to 0.13 of likeness on one row). Why was not found. The "off" of the neck's skin now measures each point against the skin it lies on; the old way ("off_held_cm") gives the men's old numbers to the digit.

**Lincoln baked again with the new code** (`just impostor-detailed runs/<Lincoln> lowpoly`, `just impostor-layered ... lowpoly`; nobody had: his cards were from before "Shoulders that hold"). His cards are now cut with the shoulder and the neck held, his head's card steps aside up his neck, and his pieces have armpits: the arm drags 9,000 to 10,000 points of his chest's skin, so his chest's card steps aside 21.4 and 21.2 cm round each shoulder (zones of 12.0 and 12.2; at the cap of 1.8 times), and his arms' 12.9 and 15.0. His right elbow is still left to its cards. `evidence/armpit/joints-lincoln-*-rebaked.json`, against his old cards judged with this code; likeness, then pixels left bare and sticking out, from 1 m in bold ink:

| Lincoln | through the crew camera | from 1 m | bare, from 1 m | sticks out, from 1 m |
|---|---|---|---|---|
| neck and shoulders | 0.56 to 0.68 | 0.61 to 0.72 | 1,690 to 356 | 3,766 to 3,265 |
| shoulders | 0.37 to 0.50 | 0.42 to 0.58 | 2,455 to 296 | 2,763 to 1,577 |
| neck | 0.63 to 0.66 | 0.71 to 0.72 | 101 to 97 | 501 to 397 |
| knees | 0.47 to 0.68 | 0.41 to 0.69 | 2,577 to 344 | 1,350 to 1,326 |
| elbows | 0.45 to 0.43 | 0.68 to 0.73 | 135 to 205 | 538 to 546 |
| hips | 0.50 to 0.49 | 0.61 to 0.60 | 37 to 22 | 1,302 to 1,298 |

In "Pixels, both" the same way round: neck and shoulders 0.68 to 0.77 from 1 m, shoulders 0.43 to 0.61, knees 0.54 to 0.79. What got worse: his elbow through the crew camera (0.45 to 0.43), what sticks out round his knees in "Pixels, both" (1,629 to 1,749 from 1 m), and **his neck's skin, measured on the skin, 0.45 cm off to 0.89**. Part of that is the head's card stepping aside up his neck ("No flaps": 0.79 without it), and the rest is not like for like: his detailed model, the judge's real one, is now rigged from the low-poly version the cast plays, not the painted one, so the skin it is measured against moves differently. With the tidy pull on his neck's piece, as before, it was 1.27. So future bakes of the men are safe to run, and better by nearly every count the judges make, but for that one measure and his elbow; they have not been run for Roosevelt and the pirate.

**What it costs.** Her pieces are 10,067 triangles where they were 9,128: each armpit is 807 and 1,003 where a shoulder was 564 and 569. Still one file (432 KB where it was 405) and one picture 1,024 square for colour and one for facing (1.2 MB to fetch, 1.1 before). The bake takes 35 seconds; the sweep is 43 poses of a third of a million points, twice. On the page, a piece whose rim is lit by its surface works out its slope once a pixel. No sheet is baked again for her.

**What is still weak.**

- **A neck that sticks out a little more.** Round her neck what is uncovered went down at six of the eight eyes, but what sticks out went up by two or three pixels through the cameras the dance is filmed with (48 to 50 through the push-in camera in bold ink), mostly when her chest twists, where the neck now goes with her head and a little past the real outline. 
- **An arm raised: the neck's skin is further off** (0.58 to 0.76 cm), while a turned head and a twist got nearer. The real model's own pull is hard there (each point all chest, all neck or all head), and the piece now follows it.
- **The worst single shoulder from 1 m and 2 m in bold ink is a little lower** (0.54 to 0.52, 0.58 to 0.56). From 1 m that is her left shoulder at 4.5 s, arm down, head turned, where the left armpit's piece now covers 13.4 cm of her arm and is plainer than the arm's card.
- **Her side is drawn by a few hundred flat triangles** under the cards' colours, so close up the edge of her top along her side is softer than the card drew it, and on the left the strap of her top is a soft grey band, not a crisp black one.
- **Under the jaw** there is still a dark band, the jaw's underside as the head's card pictured it, and a short ink squiggle on her throat where bold ink finds a fold in the neck's piece. The hatching is gone.
- **The spine's card** is not dragged far (3.5 cm at most, 16 to 19 cm from the joint) and still does not step aside. The biggest patch left bare under her raised arm from 1 m is just past the lower tip of the piece, at the edge of the spine's card (`after-who-figure-13.75-raise-1.png`).
- **Her walk and run** play the same pieces and were not looked at. No phone has run it.

Pictures (`exports/omni/groove-flamenco/armpit/`, out of git): `first.png`, `middle.png`, `last.png` are the push-in in bold ink as cards. `raise-last-*-before-after.png` are close on the raised shoulder at the last raise (13.96 s), `raise-both-*` with both arms up (10.75 s), and `neck-last-*` close on the neck, each in bold ink and in "Pixels, both", with before ("No flaps") on the left, taken off the watch page. `evidence/armpit/before-who-*` and `after-who-*` are the judge's own: the real model, bold ink, what draws every pixel, and what is bare (blue) and sticks out (red), at the raises and the head turns, from the push-in camera, the crew camera, 2 m and 1 m.

## A place from a world model

The Niantic saloon is the first place we did not build. World Labs' Marble grew it from one picture: an empty Gold Rush saloon in the hold of a beached whaleship. What Marble hands over is kept out of git, in `world/marble/niantic-saloon/`: the place itself as a cloud of soft colored dots ("splats", in four sizes from 100 thousand dots to 4.3 million), a coarse mesh of every surface for bumping into, and a record that says how big it really is.

```
just set-from-marble world/marble/niantic-saloon niantic-saloon
just gallery                    # then open #/marble/niantic-saloon
just marble-compare niantic-saloon shots/tag-moves/painted-tag.glb
just marble-diorama niantic-saloon world/marble/niantic-saloon
just marble-fit niantic-saloon <a mesh TRELLIS made>.glb
```

**Step inside** (`#/marble/niantic-saloon`, or "Step inside" on the place's own page). The gallery draws the dots themselves, with World Labs' open renderer (Spark 0.1.10 from the CDN, the last release that works with our three.js 0.170), at true size with the floor at 0. Roosevelt stands at the bar, 1.78 m, so you can judge how one of ours sits in a place like this. On the page:

- **From the bar / aisle / corner**: the set's own cameras. Drag to look round from there;
- **Walk around**: your own eyes at head height. W A S D or the arrows on a keyboard; on a phone, a thumb on the lower half walks and the upper half looks. Tables, the bar and the walls stop you;
- **How sharp**: Quick (100 thousand dots, 1.3 MB), Sharper (half a million, 7.7 MB, where it starts), Sharpest (all 4.3 million, 66 MB);
- **The room**: as it is, or as Blender films it (the painted mesh, below);
- **What you'd bump into**: Marble's collision mesh, as lines;
- **His shadow**: the floor's own dots are dimmed where he stands. Dots have no surface to lay a shadow on.

The page says how many pictures a second it is drawing. On this Mac (an M5 MacBook Pro) one picture of the bar view at 1280 x 720 takes about 1.5 ms at 100 thousand dots, 2.5 ms at half a million and 14 to 16 ms at all 4.3 million (3, 5 and 21 ms at twice the dots each way, as its own screen has): a steady 60 a second at the first two, and 48 to 60 at the last. A headless Chrome did the measuring; no real phone has been timed yet. `just marble-shots` measures it and takes the pictures in `evidence/marble/`.

The world's files are read from `world/marble/` beside the gallery; from another checkout, start it with `--marble <that checkout>/world/marble`.

**A Marble world as a set.** `just set-from-marble <world folder> <set>` makes `sets/<set>/` (`scripts/sets/from_marble.py`, in a background Blender, which has numpy):

- **metres**: the raw numbers times the record's `metric_scale_factor` (2.003 here);
- **floor at 0**: Marble's frame has y pointing down and the floor `ground_plane_offset` below its origin. The mesh's own floor is then measured and what is left taken off (8 mm here);
- **our axes**: y up, by a half turn about x, the way World Labs' viewer does it;
- **squared up**: turned until the walls run along x and z, the long side along x; the middle of the room is the origin;
- **colors**: the collision mesh has none worth having. It is cut finer (each triangle into four) and every corner takes the color of the nearest solid dots. The `.spz` file is read here in plain numpy.

`set.glb` comes out at 5.3 MB, 239 thousand triangles, small enough to keep. It carries no lighting of its own: the dots' colors already have the lamplight in them, so Blender shows the room as it is and the set's lamps light only who is brought in. `set.json` is written once with a mark in the middle and one camera; after that the marks, paths and cameras are a person's, and making the set again keeps them and the turn. The saloon's were placed from a height map of the dots: at the bar (a hand on its top), beside whoever is there, the aisle, two tables, both doors. `marble` in `set.json` says how the raw files stand in the set, which is how the gallery puts the dots in the same place as the marks.

**Side by side.** `just marble-compare` films a character on a mark in Blender and takes the same view of the dots: `evidence/marble/niantic-saloon-bar-side-by-side.png` and `-corner-`. He lands on the same spot at the same size in both. The room does not look the same: Marble's collision mesh drapes over each table and its chairs as one lump and hangs in folds round the lanterns, so the Blender room is a blurred cast of the real one.

**The way back to a mesh, ready and not run.** The test we want: Marble, a picture, Codex tidying the picture, TRELLIS, and a clean mesh that is still the same room. `just marble-diorama` makes the pictures: the room opened like a doll's house (the ceiling off, and the walls on the camera's side), from high up at three quarters, on white, five views, each as the painted mesh and as the dots through the same camera (`evidence/marble/diorama/`). `just marble-fit <set> <mesh.glb>` is the measuring: it lays a mesh of any size and facing over the set's (sixteen starts, then closest points until it settles) and says how far apart the surfaces are, both ways, as a median and a 90th percentile for the floor, the walls, the ceiling and things. Tried on Marble's own raw collision mesh, it finds the scale to a tenth of a percent and puts the surfaces 2 mm apart.

**Doors.** A mark can be a `door`: a place to stand just inside a way out, that names the set it leads into and the door it comes out at there. `just set-check` wants the two to name each other; `"built": false` says the other side is still to come. The saloon's door leads to `niantic-cove`, which is not built. The casting office's door leads to the ninja's stage, and the stage's leads back.

**A Marble world inside a building of ours.** The saloon is all Marble, walls and all. The casting office goes the other way: we built the building, and a Marble world fills only the room inside it. `just marble-seat <world folder> casting-office` (`from_marble.py --seat`) puts it in by what the set writes down in `room` and `marble_seat`, and leaves the building as it is (see The casting office).

**What is weak.** The painted mesh is only as good as Marble's collision mesh, and that is coarse: fine for where the floor and walls are, poor to look at. Sitting is not marked, because the chairs are part of a lump. The dots look best from standing height; from near the floor they fray. Roosevelt is lit by three lamps we placed by eye, not by the room, and nothing of him shows in the bar's glass. Walking in the saloon is first person only, and the world map does not know the place yet.

## Watch a take as cards

A take that has been cast can be played in the browser, on its set: `#/watch/<take>` ("Watch ... as pixel cards" on the set's page). `gallery/watch.js` stands the set up, brings every role's file on, and plays them from one clock, with Play, a bar to wind it back and forth, the set's own cameras, the shot's own moving ones or a free eye, Cards or Meshes, the looks, and (when the take was cast in both) the low-poly or mid-poly model. Each of the cast whose run has baked cards is drawn as cards riding the skeleton his cast file carries; one with none stays a mesh. A fight's two are stood on their marks as the film stands them.

For the candy-shop routine all three (Lincoln, Roosevelt, the pirate) have cards pictured from their detailed meshes (`just impostor-detailed <run> lowpoly`: the detailed mesh on the low-poly skeleton the cast uses, 96 pixels a metre as pixel art and 192 in the comic look). Their joints have been cut again since ("Where two cards meet", above). The cast's skeletons are the low-poly walk files' own to the last digit for Lincoln and Roosevelt and to a tenth of a millimetre for the pirate; Roosevelt's cards, cut on his painted skeleton, are half a millimetre off, and were kept. The detailed mesh lies 0.8 cm from the low-poly one at a typical point on Lincoln, 1.0 on Roosevelt and 2.2 on the pirate, whose coat and hat are the loosest fit. Stills, cards against meshes from the crew camera and close on each: `evidence/watch/`. All three have a face drawn for the pixel look (Looks, above): stills before and after, at the crew camera and from 1.3 m, cards and meshes, in `evidence/faces/`. Since then "Pixels, both" draws their heads on a finer grid from sheets of their own ("Faces as clear as bold ink", under Looks): `evidence/clear/`. And every knee, elbow, hip and shoulder is a piece of the real model that bends, not two pictures meeting ("A knee that bends", above): `evidence/knees/`.

## Casting

New members of the cast are found the way a casting director finds an actor, on the gallery's Casting page (`#/casting`, or "Casting" under the title). The first part being cast is a robot.

```
just casting                              # where every part stands, and everyone trying out
just casting-plan take robot              # what a step would do and what it costs; starts nothing
just casting-headshots robot go           # PAID: draw the headshots
just casting-take robot tin-toy go        # PAID: build a shortlisted headshot, then tape and judge it (free)
just casting-revise robot tin-toy [go]    # your notes become the next take (free for moves and cards; PAID for the look)
```

| Real casting | Here |
|---|---|
| **The breakdown**: who the part is, the look, the must-haves, where they fit | `casting/<role>/role.json`, written by hand. It also holds the canon options for you to choose from (none goes in canon until you do) and the looks to draw, each a whole brief |
| **Submissions**: headshots, narrowed to a shortlist | one Codex picture a look (`casting/<role>/headshots/`); "Put on the shortlist" makes it a candidate |
| **Sides**: the same short scenes for everyone | the reel (`casting/reel.json`): stand easy, walk, run, a wave, a head turn, an arm overhead, a deep squat, eight seconds of the candy-shop routine, the tag moves, a sparring bout. Chosen to push the cards where they are weakest (knees, shoulders, the neck) |
| **Self-tapes** | each take plays the reel as flat cards beside the real model, in every look (the cards page, inside this one) |
| **Callbacks with adjustments** | "Give a note" (about the look, the moves or the cards). The next take answers it; every take is kept, with its scores |
| **Chemistry reads** | a height chart beside Lincoln, Roosevelt and the pirate; the five colours each is made of beside theirs; the crew's dance with the candidate in the pirate's place, and a sparring bout with Lincoln, both on the watch page |
| **Screen test** | the camera test: the renderer's own judges (`judge_seams`, `judge_joints`, and `judge_faces` once the face has a recipe) on the candidate in the crew's dance, set beside the pirate judged the same way in the same place |
| **Cast** | "Cast in the part". The canon entry, a place in the world and the arrival by gachapon stay yours to write |

**Where things are.** `casting/reel.json` (the sides), `casting/<role>/role.json` (the breakdown), `casting/<role>/candidates/<id>/candidate.json` (status, takes, notes), `candidates/<id>/scores-<n>.json` (a take's camera test, summed up), `casting/<role>/baseline.json` (the cast member it is measured against). A take is a run folder in `runs/`; what the reel needs beyond the run's own clips is made into `shots/casting/<role>/<id>-<n>/` (the tag moves, the crew's dance with one dancer swapped, the bout, the judges' full output), out of git like the rest of `shots/`. `scripts/casting/casting.py` reads and writes all of it, `gallery/casting.js` is the page, `baml_src/12_casting/` the paid steps.

**The sides.** Most of the reel is clips a character already has (its walk, its run, the warm-up of the range-of-motion routine). The wave, the head turn, the arm overhead, the deep squat and standing easy are a new routine of the same kind, `sides.py` in the tidy-mesh skill (`just tidy <run> sides`, four seconds, free): turns of whole body parts, nothing tuned per character, so everyone does exactly the same thing and `animate.py` reports which joints it asked too much of. The squat goes deeper than the warm-up's (0.55 of the hip height against 0.38).

**What it costs.** Each paid step says so before it runs: on the page ("See what it would cost" asks the server and starts nothing; the paid buttons only ever show the command), and in Terminal (the recipes print the plan and stop unless told `go`).

| Step | Paid? | Cost |
|---|---|---|
| Headshots | yes | one Codex picture a look (four looks are written; on your ChatGPT plan). Opus writes more looks only if asked (`more=3`), about $0.05 to $0.20 |
| A first take | yes | about $2.80 to $4.50: Claude finishing it in Blender, measured from the eight characters' own logs ($2.61 to $4.20, typically $3.31; the villager's three steps were $4.20, and the brief, the gait and retries took it to about $7), plus how it walks, about $0.08 of RunPod GPU for the mesh, and a few cents for its run |
| Tape the reel | free | about a minute of background Blender (more the first time: its cards are baked from the detailed mesh, a minute and a half) |
| Camera test | free | about five minutes of background Blender |
| A revised take | notes on moves or cards: free; a note on the look: as a first take | |

The GPU price is an assumption written in `casting.py` (`RUNPOD_USD_PER_S`); check it against your bill.

**Tried with stand-ins.** The villager and the ninja stand in as candidates (`stand_in: true`; they cannot be cast), so every stage can be clicked through without spending. Both were taped and judged for real. Their first bakes, with none of the hand-tuning the crew's cards have had, score well below the pirate, which is the kind of thing the camera test is for (bold ink, crew camera and close: how well a bent joint reads, 1 is the model's own):

| | stray lines ‰ | see-through ‰ | joints | knees |
|---|---|---|---|---|
| the pirate, in his own place | 2.9 | 5.1 | 0.67 | 0.84 |
| the villager in it | 5.1 | 16.7 | 0.42 | 0.36 |
| the ninja in it | 0.6 | 11.3 | 0.50 | 0.49 |

The audition also found a fault before anyone was cast: a character with loose cloth (the villager's tunic) has cloth bones in its walk but not in a shot's clip, and the pieces of the real model that `bake_joints.py` puts in its joints are weighted to them, so the judges stopped. The camera test now judges such a candidate as cards alone and says so on the page. The robot's breakdown asks for nothing loose.

**The robot's breakdown, in short.** A small, earnest toy-shop robot, 1.45 m (the shortest in the cast), a boxy head with two round lamp eyes and a grille mouth on a dark face plate, a barrel chest with one red dial, short round limbs with a real ball at every joint, matte mustard enamel with steel-blue joints, because nobody in the cast wears yellow and three of them wear navy. Rigid parts and real ball joints are what flat cards are made of, so it should read as cards better than anyone; if it does not, that is a note for the cards. Four ways it could arrive in canon are written out for you to choose from: the developer's helper (a capsule nobody ordered), Lincoln's counter, the Square Deal crew's first hire, or the first toon brewed in the teahouse.

Screenshots of every stage, phone and desktop: `evidence/casting/`. `just casting-test` tries the files, the board, the costs, the notes and the API with no Blender and no model.

## A dance, restyled

Fourteen seconds of the groove clip's disco routine, danced by the flamenco dancer in the middle of the ninja's stage, filmed from low down with the camera creeping in, then packed up to be turned into stop-motion by Google's video model, Gemini Omni Flash. Everything up to the paid step is done and free; the paid step waits for you to say `go`.

```
just video-stretch video-groove            # which 10 to 15 seconds to use
just shoot groove-flamenco                 # the stretch, on the stage (costs nothing: the motion is the clip's)
just cast groove-flamenco runs/<the flamenco dancer> "" groove
just omni-film groove-flamenco             # every picture the pack needs (the gallery must be running)
just omni-pack groove-flamenco             # exports/omni/groove-flamenco/
just omni-send exports/omni/groove-flamenco          # what it would send and cost; add go to send it
```

**Which fourteen seconds.** `just video-stretch` scores every 10 to 15 seconds of a clip's motion: how fast the hands and feet move, how much of the time a hand is over the head, how far the body turns, how still it is at the first and last moment, how far it wanders, and how far it is from a seam (where two pieces of the clip's motion were joined; the groove clip has one at 42.47 s, where the hands jump 11.6 cm). Each stretch's ends are moved to the stillest moment nearby. The picker liked 46 to 61 s best, but that one has hands-on-head waves rather than points, ends mid-step travelling sideways, and is 3.5 s from the seam. So it is 68.47 to 82.47 s, the routine's finale, picked by eye from a strip of the candidates (`shots/groove-flamenco/stretch-strip.png` and `stretch.json`, which stay out of git with the clip): a wide low stance, a sway and a side-step out and back with a quarter-turn, then the disco point (a hand thrown up over the head and pulled down across the body) five times, ending on a held point, dead still for half a second, square to the camera. It is 26 seconds from the seam.

**On the stage.** `motion/shots/groove-flamenco.json` is a shot with one beat from the clip, `at` the stage's centre with the window behind her. A beat can now say `"facing_at": "end"`: the stretch is turned so its *last* moment faces the way the mark faces, so the final point is square to the house (she starts 39 degrees off it, as she did in the clip). With `"drift": "flatten"` she ends 1.2 cm from the mark. Her feet are held where they are down, as for every video beat: planted feet stray 0.9 cm at most. Casting her through her own skeleton keeps her skirt on its six chains of bones: it swings up to 83 degrees and its hem travels 1.1 m over the 14 seconds.

**A camera that moves.** A set's cameras never move. A shot can now bring cameras of its own that do, under `moving_cameras` in its plan: a few keys, each a place for the lens, a point it looks at and a lens length, and how to ease into it (`in_out`, the default, `in`, `out`, `linear`, or `hold`). `from` and `to` are shorthand for two keys the shot long. `plan_shot.py` copies them into the shot's `plan.json`; Blender's films (`render_take.py` films them alongside the set's cameras; `render_path.py` films one at any frame rate, a picture at a time) and the watch page (`gallery/camera-path.js`) put the lens in the same place at the same moment, and a test checks the page's sums against Python's. `just camera-path <shot>` says what the camera sees of the figure, second by second. This one, `push_in`:

| | lens off the floor | from her | lens | looking up | in the picture |
|---|---|---|---|---|---|
| start | 38 cm | 5.6 m | 24 mm | 6 degrees | all of her and the stage, the window, couch, desk and riser; she is a third of the height |
| end, 14 s | 50 cm | 2.9 m | 32 mm | 16 degrees | knees to raised hand, the window and the boxing house behind her |

It eases in and out over the whole 14 seconds, so it creeps at first, moves most in the middle and settles as she holds her last point.

**The films** (`just omni-film`, free; into `shots/groove-flamenco/omni/`), all 1280 by 720 at 24 frames a second (what Omni makes, so what goes in is what comes back), silent:

- **Bold ink**, the look you like best, as the gallery draws it: the watch page itself, in a headless Chrome, one picture at a time (`scripts/video/watch_film.py`), so it is the same bold ink the gallery shows, line for line. She is drawn as her mid-poly mesh (the film was made before she had cards; she has them now, with a skirt of its own: "A dress", above). The same page draws the stage with nobody on it, and her alone in white on black (the mask).
- **Plain shaded**, the stage with nobody on it, and **depth** (white half a metre from the lens, black at 12 m), from a background Blender with the set's own lights.
- Her side and back, from her detailed mesh, on the grey her picture stands on (`scripts/video/turnaround.py`), for the reference pictures.

**The pack** (`just omni-pack`, into `exports/omni/groove-flamenco/`, kept out of git): `source.mp4` (bold ink: what is sent), `shaded.mp4`, `plate.mp4` and `plate-shaded.mp4`, `mask.mp4`, `depth.mp4`, `first.png` and `last.png`; `refs/character-sheet.png` (her front, side and back, and her head from three sides, on one 16:9 sheet with no words on it) and `refs/set.png` (the stage from where the push-in ends, nobody on it): the two pictures edit mode takes; `refs-6/`, six pictures for the other two ways of asking; the three prompts; and `manifest.json` (the stretch and why, the frame rate, the camera's keys, the cast and what was measured on her, every file's size and fingerprint, and the licence notes: the dance is a private test, not for publishing; no song anywhere). `motion/restyles/groove-flamenco.json` says how it is all made, prompts included, so it can be made again.

**Sending it.** `just omni-send exports/omni/groove-flamenco [edit|frames|generate] [go]` (`scripts/video/omni.py`, plain Python, no SDK). Without `go` it prints exactly what it would send and what it would cost, and stops; that is all it has done so far. With `go` each file goes up through the Files API, then one request to the Interactions API; what comes back has its sound taken off and lands in `results/` beside a record of the request. The key is `GEMINI_API_KEY` in `.env`; it is not there yet, and the command says so. Three ways of asking:

- **edit** (the default): our film and the two pictures. The prompt asks for warm, handmade stop-motion (felt, clay, painted wood, soft warm light), keeping her motion, timing, framing and the camera move exactly, keeping her looks from the sheet, and quiet room sound only, no music. It names nobody real.
- **frames**: our first and last pictures, and the model makes the 10 seconds between (it makes 3 to 10 seconds that way, so it is not our 14).
- **generate**: six pictures and a prompt with timings (`[0-3s] ...`): a new film of the same idea, with no film of ours to follow.

What it costs (Gemini's price page, read 24 November 2026): video out is 5,792 tokens a second at 720p, $12 a million, so about $0.07 a second. The edit is 14 seconds out, $0.97, plus a cent or two for what goes in and the model's thinking (not published for Omni; the estimate guesses high): **about $1.00**. Generate is the same; frames, 10 seconds, about $0.72.

**Did it keep the dance?** `just omni-drift <export> <result.mp4> [go]` brings what came back in as a clip, has GEM-X read the dancer's motion off it on your RunPod endpoint (about 3.5 minutes of an RTX 4090 for 14 seconds, roughly $0.07; it chooses the dancer itself when only one person is found, and marks the camera as moving), and compares that motion with ours: every joint against the hips, turned to face the same way and brought to the same size, after the shift in time that fits best; and the best shift in each two-second window, so a film that slows down or hurries shows as a shift that grows. `omni.py compare <ours> <theirs>` is that last step alone, free. Not run yet.

**In the gallery** (`#/watch/groove-flamenco`): the take on its stage, starting on the moving camera. Now that she has cards it opens on them, in "Pixels, both" (the look chips switch to bold ink; "Meshes" brings back the mid-poly mesh, and "Model" the low-poly one). `#/restyle/groove-flamenco` plays our film beside what Omni sends back, from one Play button; until something comes back the right side says so, and any of our other passes can go on the left.

**What is weak.**
- *Her hands and face* come from the clip only as far as GEM-X reads them: the hands are not read at all and stay open, and her wrists hit their limits often in the points (clamped on 264 of 421 frames for the left hand). The face is her mid-poly model's, readable from the middle of the push-in on.
- *The skirt* went through her legs (up to 8.6 cm) when she lunged, and its hem dipped 4 cm into the floor in the low stance near the end. Mended: "Legs inside the skirt", above.
- *The side-step* takes her 1.3 m to her right of the mark early on, while the camera is still wide; the end framing is set for where she finishes, not where she wanders.
- *The mask* is her mesh alone; bold ink's outline, about 3 pixels, lies just outside it.
- *The bold ink film* is the page's pictures taken one at a time, so its edges are as smooth as the page's (antialiased, not supersampled).
- *Edit mode's 2 pictures*: Google's page says reference pictures work with editing and allows up to 6 in all; the pack keeps to 2 for editing to be safe. Whether Omni keeps a 14 s film exactly frame for frame is what the drift check is for.
- *Nothing has been sent.* The request follows Google's page as read on 24 November 2026; the first real one will show whether it is read as written.

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
