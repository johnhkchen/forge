# One idea in, one finished 3D object out. `just` lists everything.

set dotenv-load

default:
    @just --list

# Make an object from an idea: brief, picture, mesh, Blender. props: none, held (what a character carries) or all (hats and backpacks too). undress: auto (a real body under clothes that hide it, when the brief says so), none, or the gear to take off ("ruffled skirt, cloak")
make idea props="none" undress="auto":
    baml run make -- --idea "{{idea}}" --props "{{props}}" --undress "{{undress}}"

# Continue a stopped run at its first missing step (props and undress as for make)
resume dir props="none" undress="auto":
    baml run resume -- --dir "{{dir}}" --props "{{props}}" --undress "{{undress}}"

# Only the base body, for a run that has its picture and mesh: draw the character again without the gear named (or what its brief says hides the body), build that, cut the gear out of the clothed mesh. Leaves Blender alone
undress dir gear="auto":
    baml run undress_run -- --dir "{{dir}}" --gear "{{gear}}"

# Pictures of a base body and the clothes cut for it: body, clothes, both, front and quarter, on one sheet (--votes adds garment.py's vote renders)
base-shots body out +garments:
    "{{blender_bin}}" -b --factory-startup -P scripts/base_shots.py -- "{{body}}" "{{out}}" {{garments}} 2>&1 | grep -E '^RESULT|Error|Traceback'

# Only write the briefs for a finished character's props (held, or all); `just resume` each prop's folder to make it
props dir wanted="held":
    baml run props -- --dir "{{dir}}" --wanted "{{wanted}}"

# Only the first step: show the brief Opus would write
brief idea:
    baml run -e 'Describe("{{idea}}")'

# Compile-check and run the offline tests
check:
    baml check
    baml test
    python3 scripts/motion/author_poses.py --check | tail -1
    python3 scripts/motion/test_timeline.py | tail -1
    python3 scripts/motion/test_run_clip.py | tail -1
    python3 scripts/sets/test_sets.py | tail -1
    python3 scripts/world/world.py check | tail -1
    python3 scripts/comic/test_comic.py | tail -1
    python3 scripts/diorama/test_diorama.py | tail -1

# Would the Blender scripts get past the add-on's safe mode? (every skill script, or the files given)
check-safe *files:
    python3 scripts/check_safe.py {{files}}

# Try the Blender tools on real runs, in a background Blender (a few minutes; leaves the open Blender alone)
test-tools runs="runs":
    python3 scripts/test_tools.py "{{runs}}"

# Open Blender (the MCP add-on starts its server on launch)
blender:
    open -a Blender

# Install the MCP add-on into Blender (one time)
blender-addon:
    uvx --python 3.11 mcp-for-blender install-addon

# Create the TRELLIS.2 serverless endpoint on RunPod (one time)
endpoint:
    scripts/create-endpoint.sh

# Is the TRELLIS.2 endpoint up? (workers, queue)
health:
    curl -sS "https://api.runpod.ai/v2/$TRELLIS_ENDPOINT_ID/health" -H "Authorization: Bearer $RUNPOD_API_KEY"; echo

# Create the MotionBricks serverless endpoint on RunPod (one time)
motion-endpoint:
    scripts/create-motion-endpoint.sh

# Is the MotionBricks endpoint up? (workers, queue)
motion-health:
    curl -sS "https://api.runpod.ai/v2/$MOTIONBRICKS_ENDPOINT_ID/health" -H "Authorization: Bearer $RUNPOD_API_KEY"; echo

# Which MotionBricks worker answers, and how long it took to boot (starts one if none is up)
motion-info:
    baml run motion_info

# Prove the endpoint end to end: MotionBricks' own generate_once example, run on the worker
motion-selftest:
    baml run motion_selftest

# Fetch the SOMA skeleton from the worker into motion/soma_skeleton.json (one time)
motion-skeleton:
    baml run motion_skeleton

# Is a standing set sound? Marks on the floor and clear of what is in the way, seats the right height, paths clear, every camera holding its marks, the backdrop filling the view (no set named: every set in sets/)
set-check *sets:
    python3 scripts/sets/standing.py check {{sets}}

# Build a set's block-out (set.glb) and its dressing from sets/<set>/set.json and build.json, in a background Blender
set-build set:
    "{{blender_bin}}" -b --factory-startup -P scripts/sets/build_set.py -- "{{set}}" 2>&1 | grep -E '^SETBUILD|Error|Traceback'

# Have Codex paint a set's backdrop from the words in sets/<set>/backdrop.txt (one picture)
set-backdrop set:
    baml run paint_set_backdrop -- --name "{{set}}"

# Use a finished run's object as a set's geometry: copies one of its versions to sets/<set>/set.glb, moved by x y z so the set's origin is where you want it (the ring: 0 -1.36 0.485 puts the middle of the mat at 0). The run is only read
set-from-run set run profile="game" x="0" y="0" z="0":
    python3 scripts/sets/standing.py adopt "{{set}}" "{{run}}/profiles/{{profile}}.glb" {{x}} {{y}} {{z}}
    python3 scripts/sets/standing.py check "{{set}}" | tail -1

# One picture of an empty set through one of its own cameras, for its card in the gallery (sets/<set>/card.png)
set-card set camera="":
    "{{blender_bin}}" -b --factory-startup -P scripts/sets/set_still.py -- "{{set}}" {{ if camera != "" { "--camera " + camera } else { "" } }} 2>&1 | grep -E '^STILL|Error|Traceback'

# Is the world sound? Every place passes set-check, no two footprints overlap, every toon stands on a mark, and the newest epoch is the world as it is now
world-check:
    python3 scripts/world/world.py check

# Write the reset's places (grass, boxing-house, settlement, spawn) as sets from data, letter their signs, and build each in a background Blender (none named: all four)
world-places *places:
    #!/usr/bin/env bash
    set -euo pipefail
    python3 scripts/world/places.py {{places}}
    python3 scripts/world/signs.py
    for place in $(python3 scripts/world/places.py {{places}} | awk '{print $2}' | tr -d ':'); do
        "{{blender_bin}}" -b --factory-startup -P scripts/sets/build_set.py -- "$place" 2>&1 | grep -E '^SETBUILD|Error|Traceback'
        "{{blender_bin}}" -b --factory-startup -P scripts/sets/set_still.py -- "$place" 2>&1 | grep -E '^STILL|Error|Traceback'
    done

# Bring the light versions of the runs' objects to where the world uses them (the ring, the kettle, the bread, the microphone, the ninja's camera), unpacked so a browser needs no decoder
world-stock runs="runs":
    python3 scripts/world/world.py stock "{{runs}}"

# Stand the world's toons up: each in its pose from world.json, as a small still .glb in world/toons/ (none named: everyone)
world-toons runs="runs" *toons:
    "{{blender_bin}}" -b --factory-startup -P scripts/world/pose_toons.py -- "{{runs}}" {{toons}} 2>&1 | grep -E '^TOON|Error|Traceback'

# Save the world as it is now as an epoch (world/epochs/<name>.json). Old epochs are never edited: when the world changes, save a new one
world-epoch name title="" caption="":
    python3 scripts/world/world.py save-epoch "{{name}}" {{ if title != "" { "--title \"" + title + "\"" } else { "" } }} {{ if caption != "" { "--caption \"" + caption + "\"" } else { "" } }}

# What the gallery's first view of the world fetches (files and MB), and what waits until you come close
world-load:
    python3 scripts/world/world.py load

# Try walking around the world in a headless Chrome at phone size: a scripted walk, what is solid, what places say (add a folder to also take pictures)
world-walk runs="runs" shots="":
    python3 scripts/world/test_walkabout.py "{{runs}}" {{ if shots != "" { "--shots \"" + shots + "\"" } else { "" } }}

# Pictures of the gallery's world view at phone and desktop width, into evidence/world/ (the gallery must be running on that port)
world-shots port="8028" *places:
    python3 scripts/world/shots.py --port {{port}} {{places}}

# BUY HOUSE: Opus designs a house for a toon from their own brief, and it is built as a set in sets/<house name>/ (a new folder each time). Put it in the world by naming it in world.json
buy-house toon runs="runs" wish="":
    baml run buy_house -- --toon "{{toon}}" --runs "{{runs}}" --wish "{{wish}}"

# Build a kept house design again (sets/<house>/design.json), without asking anyone
house-build house runs="runs":
    python3 scripts/world/build_house.py "{{house}}" --runs "{{runs}}" | grep -E '^HOUSE'

# Take the pictures that can hang behind the ninja's stage: one of each place in the world, through that place's own camera (sets/studio/backdrops/)
studio-backdrops:
    python3 scripts/world/world.py backdrops

# Make a shot from its plan in motion/shots/<shot>.json: choreograph, place our poses, generate the motion (in pieces, if a beat is made from a sentence), measure it, film it. A take (a plan with a segment and roles, like studio-guest-entrance) makes every role and films from every camera of its set
shoot shot="hero-rooftop":
    baml run shoot -- --shot "{{shot}}"

# Put a character in a finished shot: its skeleton, limits and planted feet, plus a prop on its sockets (writes into shots/<shot>/). clip names the cut: hero, or hero-mixed for a second cut. For a take, the cast is in its plan: `character` is the folder their runs are in (`just cast studio-guest-entrance runs "" guest-entrance`), and it is filmed from every camera
cast shot character="runs" prop="" clip="hero":
    baml run cast -- --shot "{{shot}}" --character "{{character}}" --prop "{{prop}}" --clip "{{clip}}"

# Copy a shot's clips into the character's own folder, so the gallery shows a Hero button for it (clip as for cast). Never writes over another cut's files
clip-to-gallery shot character clip="hero":
    #!/usr/bin/env bash
    set -euo pipefail
    for version in lowpoly midpoly; do
        for kind in glb json; do
            [ -f "shots/{{shot}}/$version-{{clip}}.$kind" ] && cp "shots/{{shot}}/$version-{{clip}}.$kind" "{{character}}/profiles/$version-{{clip}}.$kind"
        done
    done
    ls "{{character}}/profiles" | grep -- '-{{clip}}\.'

# What Kimodo (text to motion) has fetched onto the volume and loaded, with revisions and timings; the first call on a fresh volume is the one that fetches
text-info:
    baml run text_info

# Point the motion endpoint at another image tag (after the worker image is rebuilt)
motion-image tag:
    #!/usr/bin/env bash
    set -euo pipefail
    image="${MOTIONBRICKS_IMAGE%:*}:{{tag}}"
    curl -sS -X PATCH "https://api.runpod.io/v2/serverless/$MOTIONBRICKS_ENDPOINT_ID" \
      -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
      -d "{\"image\": \"$image\"}" | python3 -c "import sys, json; d = json.load(sys.stdin); print(d.get('id'), d.get('image'), 'version', d.get('version'))"

# Build the pose library (motion/poses.json) from scripts/motion/author_poses.py, checking every pose as a body
poses:
    python3 scripts/motion/author_poses.py

blender_bin := env_var_or_default("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")

# Make tidy-mesh profiles of a finished run, in a background Blender (hero quads web game mobile midpoly lowpoly; walk adds a skeleton and a walk to the last two; run adds a run, once `just runs` has made its clip)
tidy run +profiles:
    #!/usr/bin/env bash
    set -euo pipefail
    src="{{run}}/scene.blend"; [ -f "$src" ] || src="{{run}}/mesh.glb"
    "{{blender_bin}}" -b --factory-startup -P scripts/tidy_profile.py -- "$src" "{{run}}/profiles" {{profiles}} 2>&1 | grep -E '^PROFILE|Error|Traceback'

# Only ask Opus how a run's character walks (weight, stealth, swagger, stiffness); saves nothing
gait run:
    baml run how_it_walks -- --dir "{{run}}"

# A looping run for every character in a folder of runs (each one with a gait.json): one sentence each to Kimodo on the motion worker, cut into a loop, played on the low-poly and mid-poly versions. Says "run skipped: Kimodo not available" and stops cleanly if Kimodo can't be reached
runs dir="runs":
    baml run runs -- --dir "{{dir}}"

# Only show what each character would be asked to run like: its sentence and speed (sends nothing; writes run/ask.json and the request)
run-asks dir="runs":
    python3 scripts/motion/run_clip.py "{{dir}}"/*/ | grep -E '^RUN'

# Picture a walking .glb as a strip of poses (view: side, front or quarter)
walk-strip file out view="side":
    "{{blender_bin}}" -b --factory-startup -P scripts/walk_strip.py -- "{{file}}" "{{out}}" --view {{view}} 2>&1 | grep -E '^STRIP|Error|Traceback'

# Measure a dressed character's .glb (standing or walking): skin through its clothes over the clip, how far they sit off the body, cloth bones
cloth-check +files:
    "{{blender_bin}}" -b --factory-startup -P scripts/cloth_check.py -- {{files}} 2>&1 | grep -E '^CLOTH|Error|Traceback'

# Measure a walking or running character's .glb: where each joint sits in the body around it, how much volume each part keeps over the clip, how much each part shakes
rig-check +files:
    "{{blender_bin}}" -b --factory-startup -P scripts/rig_check.py -- {{files}} 2>&1 | grep -E '^RIG|Error|Traceback'

# Measure a low-poly or mid-poly character's colors against the run's detailed mesh, piece by piece (add --sheet out.png for a picture)
bake-check run +files:
    "{{blender_bin}}" -b --factory-startup -P scripts/bake_check.py -- "{{run}}/scene.blend" {{files}} 2>&1 | grep -E '^BAKE|^SHEET|Error|Traceback'

# Only draw a character's head again, large, from three sides (heads/sheet.png); the next `just tidy` paints the face from it
head-sheet run:
    baml run head_sheet_for -- --dir "{{run}}"

# Picture a character's face in every version of a run, next to its picture: front, three-quarter, side (writes out.png and out.json)
face-sheet run out:
    "{{blender_bin}}" -b --factory-startup -P scripts/face_sheet.py -- "{{run}}" "{{out}}" 2>&1 | grep -E '^FACES|Error|Traceback'

# Measure the faces on a face sheet against the picture: where eyes, nose, mouth and chin sit, how lopsided, how sharp (uv fetches MediaPipe the first time)
face-check +sheets:
    uv run --no-project --python 3.11 --with mediapipe==0.10.14 --with opencv-python-headless --with "numpy<2" python scripts/face_check.py {{sheets}} 2>/dev/null

# For a run from before recipes were kept: rebuild its block-out from the transcript in a background Blender and save the recipe, so `just tidy <run> midpoly` works
recipe run:
    #!/usr/bin/env bash
    set -euo pipefail
    "{{blender_bin}}" -b --factory-startup -P scripts/replay_blockout.py -- "{{run}}" 2>&1 | grep -E '^REPLAY|^replay:'
    cp "{{run}}/replay/lowpoly_build.json" "{{run}}/lowpoly_build.json"

# Give a finished character an anatomical body without asking Claude: landmarks, a body built from them, the run's own head and gear kept. Writes lowpoly.glb and lowpoly_build.json into OUT (never the run's own), e.g. `just auto-body runs/<run> /tmp/new` then copy the two files into a copy of the run and `just tidy` it
auto-body run out *flags:
    "{{blender_bin}}" -b --factory-startup -P scripts/auto_body.py -- "{{run}}" "{{out}}" {{flags}} 2>&1 | grep -E '^AUTOBODY|Error|Traceback'

# Measure low-poly and mid-poly bodies against a run's detailed mesh: landmarks, proportions, outlines, cross-sections (out.png and out.json). Each file is label=path, e.g. low=runs/<run>/profiles/lowpoly.glb
anatomy-check run out +files:
    "{{blender_bin}}" -b --factory-startup -P scripts/anatomy_check.py -- "{{run}}" "{{out}}" {{files}} 2>&1 | grep -E '^ANATOMY|Error|Traceback'

# Install AutoRemesher (MIT, adaptive quad remesher) into tools/ for the profiles (macOS)
autoremesher:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p tools/autoremesher-dl && cd tools/autoremesher-dl
    gh release download 1.2.0 -R huxingyi/autoremesher -p 'autoremesher-1.2.0.dmg' --clobber
    echo "4d3295fa2f87567e6b97a732afff511d82ec73a49825476038ce0997c641e9a7  autoremesher-1.2.0.dmg" | shasum -a 256 -c
    mnt=$(mktemp -d); hdiutil attach -nobrowse -readonly -mountpoint "$mnt" autoremesher-1.2.0.dmg >/dev/null
    rm -rf autoremesher.app; cp -R "$mnt/autoremesher.app" .; hdiutil detach "$mnt" >/dev/null
    ./autoremesher.app/Contents/MacOS/autoremesher --version

# Make a comic from a premise: Opus writes it as panels of data, one background Blender draws every panel in the comic style, code letters it and lays out the page (comics/<name>/page.html and a .png). layout: strip (4 panels) or scroll (6 to 10, for a phone). cast and place narrow what Opus may use ("lincoln, roosevelt", "ring"); canon=no marks a side story, outside the main one
comic premise layout="strip" cast="" place="" name="" runs="runs" canon="yes":
    baml run comic -- --premise "{{premise}}" --layout "{{layout}}" --cast "{{cast}}" --place "{{place}}" --name "{{name}}" --runs "{{runs}}" --canon "{{canon}}"

# Draw and letter a comic again from its comics/<name>/comic.json, after editing it by hand (asks no model anything)
comic-again name runs="runs":
    baml run draw_comic -- --name "{{name}}" --runs "{{runs}}"

# Only letter and lay out a drawn comic again (after changing the lettering or the page, not the pictures)
comic-page name:
    python3 scripts/comic/layout.py "comics/{{name}}"

# What a comic can be made from right now: the cast, each one's poses, clip moments and expressions, the places
comic-kit runs="runs":
    python3 scripts/comic/kit.py --runs "{{runs}}"

# Give a cast member (comics/cast.json) its expressions: draw its head in the comic style, have Codex draw the sheet of eight faces from it (one Codex image), cut the sheet and fit each face to the head. comics/cast/<who>/faces.png shows the fit
expressions who runs="runs":
    #!/usr/bin/env bash
    set -euo pipefail
    fit() { "{{blender_bin}}" -b --factory-startup -P scripts/comic/face_fit.py -- "$1" "{{who}}" --runs "{{runs}}" 2>&1 | grep -E '^FACE|Error|Traceback' | cut -c1-240; }
    fit head
    baml run expression_sheet -- --who "{{who}}" --runs "{{runs}}"
    fit cut
    fit show

# Only cut and fit a cast member's expression sheet again (after changing its face region in comics/cast.json); no Codex
expressions-fit who runs="runs":
    #!/usr/bin/env bash
    set -euo pipefail
    for step in cut show; do "{{blender_bin}}" -b --factory-startup -P scripts/comic/face_fit.py -- "$step" "{{who}}" --runs "{{runs}}" 2>&1 | grep -E '^FACE|Error|Traceback' | cut -c1-240; done

# Before and after: each rigged character file as a plain render and in the comic style, side by side (out/<name>.png)
comic-style out +files:
    "{{blender_bin}}" -b --factory-startup -P scripts/comic/style_stills.py -- "{{out}}" {{files}} 2>&1 | grep -E '^STILLS|Error|Traceback'

# Picture every comic pose (motion/comic_poses.json) on one rigged character, to check a new pose
comic-poses file out:
    "{{blender_bin}}" -b --factory-startup -P scripts/comic/pose_sheet.py -- "{{file}}" "{{out}}" 2>&1 | grep -E '^POSES|Error|Traceback'

# Build a diorama from its plan (dioramas/<name>/diorama.json) in a background Blender: the toons posed and placed on a wooden base, as one light diorama.glb, with its pictures and its card
diorama name runs="runs":
    "{{blender_bin}}" -b --factory-startup -P scripts/diorama/build_diorama.py -- "{{name}}" --runs "{{runs}}" 2>&1 | grep -E '^DIORAMA|Error|Traceback'

# Is a diorama's plan sound? Marks, poses, props and cameras that exist, nobody planned inside anybody (none named: every diorama)
diorama-check *names:
    python3 scripts/diorama/diorama.py check {{names}}

# Try a pose or a camera: quick small pictures of a diorama into dioramas/<name>/draft/, and what the build would measure. Writes nothing else (cameras: one or more, with commas; none: the first)
diorama-draft name cameras="" runs="runs":
    "{{blender_bin}}" -b --factory-startup -P scripts/diorama/build_diorama.py -- "{{name}}" --runs "{{runs}}" --draft {{cameras}} 2>&1 | grep -E '^DIORAMA|Error|Traceback'

# What the gallery's front page fetches for a diorama (files and MB), and what waits for a tap
diorama-load name:
    python3 scripts/diorama/diorama.py load "{{name}}"

# Pictures of the gallery's front page at phone and desktop width, and every byte it fetched, into evidence/diorama/ (the gallery must be running on that port)
diorama-shots port="8028":
    python3 scripts/diorama/shots.py --port {{port}}

# Vendor the b28 clay style kit into the gallery
sync-kit:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p gallery/vendor
    curl -fsSL https://b28.dev/kit/b28-clay.css -o gallery/vendor/b28-clay.css
    grep -q -- '--clay-' gallery/vendor/b28-clay.css || { echo "sync-kit: not the b28 clay kit" >&2; exit 1; }
    echo "vendored gallery/vendor/b28-clay.css"

# Serve the gallery to this Mac and phones on the same Wi-Fi
gallery port="8028" runs="runs" shots="shots":
    python3 scripts/gallery.py --port {{port}} --runs "{{runs}}" --shots "{{shots}}"

# Only brief, picture and mesh (leaves Blender alone); finish with `just resume`
mesh idea undress="auto":
    baml run make_mesh -- --idea "{{idea}}" --undress "{{undress}}"

# Show the Blender code Claude ran in a run's step (polish, parts, lowpoly)
transcript run step:
    python3 scripts/transcript.py "{{run}}" "{{step}}"

blender_startup := env_var("HOME") + "/Library/Application Support/Blender/5.2/scripts/startup"

# Install the Forge tools into Blender (restart Blender afterwards)
forge-addon:
    #!/usr/bin/env bash
    set -euo pipefail
    dir="{{blender_startup}}"
    mkdir -p "$dir/forge_tools"
    cp blender/forge_tools.py "$dir/forge_tools.py"
    rm -f "$dir/forge_tools/"*.py
    cp .claude/skills/tidy-mesh/scripts/*.py "$dir/forge_tools/"
    echo "Installed $(ls "$dir/forge_tools" | wc -l | tr -d ' ') tools into $dir. Restart Blender to load them."

# Remove the Forge tools from Blender
forge-addon-remove:
    rm -rf "{{blender_startup}}/forge_tools.py" "{{blender_startup}}/forge_tools"
