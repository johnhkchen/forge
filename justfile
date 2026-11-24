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
    python3 scripts/fight/test_fight.py | tail -1
    "{{blender_bin}}" -b --factory-startup -P scripts/sets/test_marble.py 2>&1 | grep -E '^MARBLE|FAIL'
    python3 scripts/skate/test_skate.py | tail -1
    python3 scripts/world/world.py check | tail -1
    python3 scripts/comic/test_comic.py | tail -1
    python3 scripts/diorama/test_diorama.py | tail -1
    python3 scripts/impostor/test_impostor.py | tail -1
    python3 scripts/casting/test_casting.py | tail -1
    python3 scripts/video/test_video.py 2>/dev/null | tail -1

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

# A World Labs Marble world as a set: its collision mesh in metres, floor at 0, squared up around the middle of the room, colored from its splats; writes sets/<set>/set.glb and set.json (a set.json already there keeps its marks, cameras and turn). The world folder is only read
set-from-marble world set splats="500k":
    "{{blender_bin}}" -b --factory-startup -P scripts/sets/from_marble.py -- "{{world}}" "{{set}}" --splats "{{splats}}" 2>&1 | grep -E '^MARBLE|Error|Traceback'
    python3 scripts/sets/standing.py check "{{set}}" | tail -1

# Put a Marble world of a room inside the building made for it (a set with `room` and `marble_seat`, like casting-office): turned, sized and moved to fit, its picture's eye checked against the set's camera. The building itself is kept
marble-seat world set="casting-office" splats="500k":
    "{{blender_bin}}" -b --factory-startup -P scripts/sets/from_marble.py -- "{{world}}" "{{set}}" --splats "{{splats}}" --seat 2>&1 | grep -E '^MARBLE|Error|Traceback'
    python3 scripts/sets/standing.py check "{{set}}" | tail -1

# Write the casting office's set.json and build.json from its numbers, then build it
casting-office:
    python3 scripts/sets/casting_office.py
    just set-build casting-office

# Pictures of a Marble place's page in the gallery at each sharpness, and how fast it draws on this Mac, into evidence/marble/ (the gallery must be running on that port, started with --marble if the world's files are in another checkout)
marble-shots set port="8028" camera="bar":
    python3 scripts/sets/marble_shots.py "{{set}}" --port {{port}} --camera "{{camera}}"

# The same view twice, side by side: a character on a mark as Blender films the set, and as the gallery shows the splats (evidence/marble/<set>-<camera>-side-by-side.png). who is a character's .glb, held at `second` of its clip
marble-compare set who mark="bar" camera="bar" second="0.5" port="8028":
    mkdir -p evidence/marble
    "{{blender_bin}}" -b --factory-startup -P scripts/sets/set_still.py -- "{{set}}" --camera "{{camera}}" --size 1280x720 --out "{{justfile_directory()}}/evidence/marble/{{set}}-{{camera}}-blender.png" --stand "{{who}}" "{{mark}}" --second {{second}} 2>&1 | grep -E '^STILL|Error|Traceback'
    python3 scripts/sets/marble_shots.py "{{set}}" --port {{port}} --one "/{{camera}}?detail=full_res&bare=1" "evidence/marble/{{set}}-{{camera}}-splats.png"
    ffmpeg -y -loglevel error -i "evidence/marble/{{set}}-{{camera}}-blender.png" -i "evidence/marble/{{set}}-{{camera}}-splats.png" -filter_complex hstack "evidence/marble/{{set}}-{{camera}}-side-by-side.png"
    @echo "COMPARE evidence/marble/{{set}}-{{camera}}-side-by-side.png (left: Blender, right: the splats)"

# A Marble room as diorama pictures for TRELLIS: opened like a doll's house, from high up at three quarters, on white; the painted mesh and the splats through the same cameras, into evidence/marble/diorama/ (the gallery must be running on that port, from this checkout)
marble-diorama set world port="8028":
    "{{blender_bin}}" -b --factory-startup -P scripts/sets/marble_diorama.py -- "{{set}}" "{{world}}" 2>&1 | grep -E '^DIORAMA|Error|Traceback'
    python3 scripts/sets/marble_shots.py "{{set}}" --port {{port}} --views evidence/marble/diorama/views.json

# Lay a mesh (TRELLIS's, made from a picture of the place) over a Marble set and say how far apart the surfaces are: median and 90th percentile, by floor, walls, ceiling and things
marble-fit set mesh out="":
    "{{blender_bin}}" -b --factory-startup -P scripts/sets/fit_to_marble.py -- "{{set}}" "{{mesh}}" {{ if out != "" { "--out \"" + out + "\"" } else { "" } }} 2>&1 | grep -E '^FIT|Error|Traceback'

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

# Stage a fight from its script (scripts/fight/fights/<fight>.json) on two characters' run folders: lay it out on one timeline, bake each fighter, and film it from every camera of its set with hitstop, camera shake and impact flashes (into shots/fight-<fight>/, or out). One background Blender per camera
fight fight left right out="":
    #!/usr/bin/env bash
    set -euo pipefail
    out="{{ if out != "" { out } else { "shots/fight-" + fight } }}"
    mkdir -p "$out"
    "{{blender_bin}}" -b --factory-startup -P scripts/fight/apply_fight.py -- "scripts/fight/fights/{{fight}}.json" "$out" --left "{{left}}" --right "{{right}}" 2>&1 | grep -E '^FIGHT|Error|Traceback'
    rm -f "$out/films.json"
    for camera in $(python3 -c "import json, sys; sys.path.insert(0, 'scripts/sets'); import standing; print(' '.join(standing.load(json.load(open('$out/fight.json'))['set'])['cameras']))"); do
        "{{blender_bin}}" -b --factory-startup -P scripts/fight/film_fight.py -- "$out" --cameras "$camera" 2>&1 | grep -E '^FILM|Error|Traceback' &
    done
    wait

# A character as flat cards, one a bone: cut a rigged version (one with a walk) into rigid parts and picture each from all around, into <run>/profiles/<version>-impostor-<look>-joined/ (the comic look unless told). more: bake_impostor.py's flags (--views 26,62 --px 128; --look pixel or --look joe for the sheet of another look; a pixel sheet of a model that has a face recipe in scripts/impostor/faces/ gets a finer head and a drawn face; --lap, --ball and --smooth-cm for how the joints are cut). The gallery then shows it at #/cards/<run>, and a field of them at #/tag/<run>. Half a minute a view set; never touches the open Blender
impostor run version="painted" *more:
    "{{blender_bin}}" -b --factory-startup -P scripts/impostor/bake_impostor.py -- "{{run}}" "{{version}}" {{ if more == "" { "--views 26,62,114" } else { more } }} 2>&1 | grep -E '^IMPOSTOR|^RESULT \{"folder|Error|Traceback'

# Cards pictured from a character's detailed mesh (final.glb, some 290,000 triangles) instead of a rigged version: the detailed mesh is given that version's skeleton (weights taken from the nearest place on its surface), then pictured as pixel art (96 pixels a metre, the head at 192 with its folds drawn in, into detailed-impostor-pixel-clear/), in the comic look and for bold ink. The cards play the rigged version's clips; the gallery offers it as "Detailed model"
impostor-detailed run from="painted":
    "{{blender_bin}}" -b --factory-startup -P scripts/impostor/rig_detailed.py -- "{{run}}" --from "{{from}}" 2>&1 | grep -E '^RIG|^RESULT|Error|Traceback'
    "{{blender_bin}}" -b --factory-startup -P scripts/impostor/bake_impostor.py -- "{{run}}" detailed --look pixel --px 96 --soften 512 --plays "{{from}}" --title "Detailed model" 2>&1 | grep -E '^IMPOSTOR views .*sheet|Error|Traceback'
    "{{blender_bin}}" -b --factory-startup -P scripts/impostor/bake_impostor.py -- "{{run}}" detailed --views 26 --soften 512 --plays "{{from}}" --title "Detailed model" 2>&1 | grep -E '^IMPOSTOR views .*sheet|Error|Traceback'
    "{{blender_bin}}" -b --factory-startup -P scripts/impostor/bake_impostor.py -- "{{run}}" detailed --look joe --views 26 --soften 512 --plays "{{from}}" --title "Detailed model" 2>&1 | grep -E '^IMPOSTOR views .*sheet|Error|Traceback'
    "{{blender_bin}}" -b --factory-startup -P scripts/impostor/bake_joints.py -- "{{run}}" detailed 2>&1 | grep -E '^JOINTS .*(skinned|necked)|^JOINTS left|Error|Traceback'

# Give a character's flat cards real joints: for every knee, elbow, hip and shoulder a small piece of the model itself, with its skeleton's pull, drawn where the cards step aside; and one more for the neck, the collar and the tops of both shoulders, so the head and arms do not come away from the chest (the cards must be baked first: `just impostor` or `just impostor-detailed`). Writes <version>-impostor-<look>-necked/ beside each set of cards, which the pages read first; the cards' own sheets, and the older -skinned/ pieces, are left alone. more: bake_joints.py's flags (--triangles 320, --zone knee=1.6,..., --leave forearm_l to leave a joint to its cards, --kinds knee,elbow,hip,shoulder for no neck piece, --even 0.03 and --cloth 0.5 for how the neck piece's pull is worked over, --pull rig for the rig's own). Ten seconds; never touches the open Blender
impostor-joints run version="detailed" *more:
    "{{blender_bin}}" -b --factory-startup -P scripts/impostor/bake_joints.py -- "{{run}}" "{{version}}" {{more}} 2>&1 | grep -E '^JOINTS|^RESULT \{"folders|Error|Traceback'

# Does a bent joint read as the joint it is? A take's cast drawn as cards, joint by joint, against the real models posed the same: how well the light and dark there follows the model's (likeness), how much is a dark blot the model has not got, how far the colour is off, and pixels left bare; bold ink and "Pixels, both", through the set's crew camera, from 2 m and from 1 m. Writes joints[-tag].json into out. more: judge_joints.py's flags (--sheets joined for the cards without the pieces in their joints; --at 38 --deep 2 for which moments; --stills asked for pictures)
impostor-knees take="crew-candy-shop" tag="after" out="evidence/knees" *more:
    "{{blender_bin}}" -b --factory-startup -P scripts/impostor/judge_joints.py -- --take "{{take}}" --tag "{{tag}}" --out "{{out}}" {{more}} 2>&1 | grep -E '^JOINTS .*\||^RESULT \{"out|Error|Traceback'

# Do the head and the arms hold to the chest? A take's cast as cards against the real models posed the same, in a disc that holds the neck, the collar and both shoulders, at the moments of the dance where the head is turned furthest, an arm raised highest, a shoulder shrugged most and the chest twisted most, through the set's camera, from 2 m and from 1 m: likeness, blots, pixels left bare and pixels that stick out, and how far the skin there is drawn from where the model has it, in centimetres. Into out as joints-<tag>.json. more: judge_joints.py's flags (--sheets skinned for the cards as they were before the neck piece; --stills yoke for a still of every moment from every eye: the real model, then the cards in each look). No browser; never touches the open Blender
impostor-neck take="crew-candy-shop" tag="after" out="evidence/neck" *more:
    "{{blender_bin}}" -b --factory-startup -P scripts/impostor/judge_joints.py -- --take "{{take}}" --tag "{{tag}}" --out "{{out}}" --kinds neck,shoulder,yoke --at "" {{more}} 2>&1 | grep -E '^JOINTS .*\|(yoke|neck|shoulder)\|(all|asked|turn|raise|shrug|twist)|^RESULT \{"out|Error|Traceback'

# Stills of a take's faces on the watch page (pixel cards, and meshes drawn small), from the set's camera and close on each, and how many pixels each face gets, into out as <tag>-*.png and <tag>-faces.json (the gallery must be running on that port; needs Chrome)
face-shots take="crew-candy-shop" tag="after" port="8028" out="evidence/faces" at="12":
    python3 scripts/impostor/face_shots.py --base "http://localhost:{{port}}/" --take "{{take}}" --tag "{{tag}}" --out "{{out}}" --at "{{at}}" | grep -E '^FACES|Error|Traceback'

# Count how much of each face is left when a take's cast is drawn as cards, against the real models posed the same: eyes, brows, mouth, spectacles, a patch, in bold ink and in "Pixels, both", through the set's crew camera, from 2 m and from 1 m. Writes faces[-tag].json into out. more: judge_faces.py's flags (--pixel old for the pixel look as it was before the head had a grid of its own; --why to say where a face is lost; --stills frontman@24:crew,... for pictures)
impostor-faces take="crew-candy-shop" tag="after" out="evidence/clear" *more:
    "{{blender_bin}}" -b --factory-startup -P scripts/impostor/judge_faces.py -- --take "{{take}}" --tag "{{tag}}" --out "{{out}}" {{more}} 2>&1 | grep -E '^FACES .*\||^RESULT \{"out|Error|Traceback'

# Stills of a take's heads on the watch page in bold ink and in "Pixels, both", through the set's camera, from 2 m and from 1 m, each head cut out and blown up, into out as <tag>-*.png (the gallery must be running on that port; needs Chrome). Then `python3 scripts/impostor/clear_shots.py --sides joe:after,pixel-both:before,pixel-both:after` lays them side by side
clear-shots take="crew-candy-shop" tag="after" port="8028" out="evidence/clear" at="24":
    python3 scripts/impostor/clear_shots.py --base "http://localhost:{{port}}/" --take "{{take}}" --tag "{{tag}}" --out "{{out}}" --at "{{at}}" | grep -E '^SHOTS|Error|Traceback'

# Judge a character's flat cards against the real model, with no browser: the same frames drawn both ways from the same eye, and how far apart they are (outline, colour, gaps at the joints, how often a picture is swapped). Writes judge.json, stills and films into out. clips: name=file.glb pairs; more: any of judge_impostor.py's flags
impostor-judge run version="painted" out="evidence/impostor" *more:
    "{{blender_bin}}" -b --factory-startup -P scripts/impostor/judge_impostor.py -- "{{run}}/profiles/{{version}}-impostor-comic-joined" --out "{{out}}" --clip "walk={{run}}/profiles/{{version}}-walk.glb" {{more}} 2>&1 | grep -E '^JUDGE|^RESULT|Error|Traceback'

# Count what shows at the joints of a take's cast drawn as cards, against the real models posed the same and drawn the same way: dark lines that are not there, and see-through gaps, in every look, from the set's crew camera and from 2 m, in the dance and in a walk. Writes seams[-tag].json into out. more: judge_seams.py's flags (--sheets old for the sheets as they were before the joints were mended; --why to say what the gaps come from; --stills left@24:close,... for pictures)
impostor-seams take="crew-candy-shop" tag="after" out="evidence/seams" *more:
    "{{blender_bin}}" -b --factory-startup -P scripts/impostor/judge_seams.py -- --take "{{take}}" --tag "{{tag}}" --out "{{out}}" {{more}} 2>&1 | grep -E '^SEAMS [a-z]+\||^BENT|^WHY|^RESULT \{"out|Error|Traceback'

# Stills of a take's bent joints from two galleries side by side (say, main's and a branch's): a square round each joint through the set's camera, from 2 m and from 1 m, into out as <joint>-<look>.png (both galleries must be running; needs Chrome). A gallery is its port and a slash; "8045/?joints=cards" is that gallery with the pieces of the real model left out of the joints, so one gallery can be its own before. more: joint_shots.py's flags (--joints knee=1:shin_l@16.25,... --looks joe,pixel-both --stage 42.25)
joint-shots before="8030/" after="8028/" take="crew-candy-shop" out="evidence/joints" *more:
    python3 scripts/impostor/joint_shots.py "before=http://localhost:{{before}}" "after=http://localhost:{{after}}" --take "{{take}}" --out "{{out}}" {{more}} | grep -E '^SHOTS|Error|Traceback'

# Stills of a take's joints on the watch page: the stage from the set's camera, close on each of the cast, and closer still on an elbow and a knee, as cards in every look, and the stage as meshes, into out as <tag>-*.png (the gallery must be running on that port; needs Chrome)
seam-shots take="crew-candy-shop" tag="after" port="8028" out="evidence/seams" at="24":
    python3 scripts/impostor/seam_shots.py --base "http://localhost:{{port}}/" --take "{{take}}" --tag "{{tag}}" --out "{{out}}" --at "{{at}}" | grep -E '^SHOTS|Error|Traceback'

# The flat cards' own tests: the arithmetic, a ball drawn from between its pictures, the page's arithmetic against Python's (in node), and a baked character if runs has one
impostor-test runs="runs":
    python3 scripts/impostor/test_impostor.py "{{runs}}"

# Put a character on the skateboard and have it ride a run on the halfpipe, from its script (scripts/skate/rides/<ride>.json): lay the run out, bake the rider on his board, carry both along the ramp, and film it from every camera of the set (into shots/halfpipe-<ride>/, or out). versions: lowpoly, or lowpoly,midpoly. One background Blender per camera
skate ride character versions="" out="":
    #!/usr/bin/env bash
    set -euo pipefail
    out="{{ if out != "" { out } else { "shots/halfpipe-" + ride } }}"
    mkdir -p "$out"
    "{{blender_bin}}" -b --factory-startup -P scripts/skate/apply_ride.py -- "scripts/skate/rides/{{ride}}.json" "$out" --character "{{character}}" {{ if versions != "" { "--versions " + versions } else { "" } }} 2>&1 | grep -E '^RIDE|Error|Traceback'
    rm -f "$out/films.json" "$out/cast-ride.json"
    for camera in $(python3 -c "import json, sys; sys.path.insert(0, 'scripts/sets'); import standing; print(' '.join(standing.load(json.load(open('$out/ride.json'))['set'])['cameras']))"); do
        "{{blender_bin}}" -b --factory-startup -P scripts/skate/film_ride.py -- "$out" --cameras "$camera" 2>&1 | grep -E '^FILM|Error|Traceback' &
    done
    wait

# Only lay a run out, with no Blender: what each pass turns out to be and what is measured (body: a rider.body.json, or the fight kit's test bodies)
skate-plan ride body="scripts/fight/test_bodies.json" out="shots/halfpipe-plan":
    python3 scripts/skate/ride.py "scripts/skate/rides/{{ride}}.json" "{{body}}" "{{out}}"

# Write the halfpipe's set.json from its numbers (scripts/skate/halfpipe_set.py) and build its geometry from the same numbers, in a background Blender
halfpipe-build:
    python3 scripts/skate/halfpipe_set.py
    "{{blender_bin}}" -b --factory-startup -P scripts/skate/build_halfpipe.py -- halfpipe 2>&1 | grep -E '^HALFPIPE|Error|Traceback'

# Build the skateboard (world/props/skateboard.glb and its card) from scripts/skate/board.py, in a background Blender
skate-board:
    "{{blender_bin}}" -b --factory-startup -P scripts/skate/build_board.py 2>&1 | grep -E '^BOARD|Error|Traceback'

# The halfpipe's and the riding kit's own tests, without Blender: the ramp's cut, wheels on the surface, energy, feet on the bolts, joint limits, grabs, a pose from a clip
skate-test:
    python3 scripts/skate/test_skate.py

# The fight kit's own tests, without Blender: frame data, reactions on the active frame, hitstop, reach, the mat, joint limits, footwork
fight-test:
    python3 scripts/fight/test_fight.py

# Bring a video of yours (a dance, anything with a person moving): copies it to videos/<name>/source.mp4. start and end, in seconds, keep only that stretch. Nothing is downloaded; videos/ stays out of git
video-add file name="" start="" end="":
    python3 scripts/video/clip.py add "{{file}}" "{{name}}" --start "{{start}}" --end "{{end}}"

# Turn a clip into motion for our characters: does whatever comes next (the cuts, the people in each shot, then your choice in the gallery at #/video/<name>, the motion, the shot, a film beside the clip). Run it again to carry on. again=<step> redoes from ready, cuts, people, choice, motion, shot or film; also=1:2 makes person 2 of shot 1 too, for a shot list that asks for them. Finding people and making motion use your GEM-X endpoint on RunPod
video name again="" also="":
    python3 scripts/video/video.py "{{name}}" {{ if again != "" { "--again " + again } else { "" } }} {{ if also != "" { "--also " + also } else { "" } }}

# Where several dancers of one clip stand relative to each other over some seconds (people: their numbers, with commas), read from the picture: where each starts and ends on a stage whose middle is origin (x,z), and the closest any two come
video-formation clip people from to origin="0,0" spread="1.0" travel="1.0":
    python3 scripts/video/formation.py "{{clip}}" --people "{{people}}" --from {{from}} --to {{to}} --origin="{{origin}}" --spread {{spread}} --travel {{travel}}

# Play a shot or a take through with stand-ins for Kimodo and MotionBricks (no RunPod): its video beats are the real thing, everything is where and when it will be, and it says how close people come. Into a folder of your choosing, never shots/
rehearse shot folder:
    python3 scripts/video/rehearse.py "motion/shots/{{shot}}.json" "{{folder}}"

# Film a character you cast in a clip's shot (`just cast video-<name> runs/<character>`) beside the clip, in step: videos/<name>/side-by-side-lowpoly-<clip>.mp4
video-film name clip="hero":
    python3 scripts/video/film.py "videos/{{name}}" "shots/video-{{name}}" --cast "lowpoly-{{clip}}"

# Try everything around the video model with no GPU: a drawn clip, a stand-in for GEM-X, then the film and a character from RUNS in a background Blender (a few minutes)
video-test runs="runs":
    python3 scripts/video/test_video.py --cast "{{runs}}"

# Create the GEM-X serverless endpoint on RunPod, for `just video` (one time)
gemx-endpoint:
    scripts/create-gemx-endpoint.sh

# Is the GEM-X endpoint up? (workers, queue)
gemx-health:
    curl -sS "https://api.runpod.ai/v2/$GEMX_ENDPOINT_ID/health" -H "Authorization: Bearer $RUNPOD_API_KEY"; echo

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

# Make tidy-mesh profiles of a finished run, in a background Blender (hero quads web game mobile midpoly lowpoly; walk adds a skeleton and a walk to the last two; run adds a run, once `just runs` has made its clip; painted makes the mid-poly one again on the wardrobe's shared body with the skin-tight gear its wardrobe.json names painted on)
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

# Measure a painted character's walking .glb (profiles/painted-walk.glb): how far the collar opens on the neck over the clip, the feet against the floor, the body's weights. Or how clean a painted garment's edge is: `just paint-check --edges <template.glb> <garment.png>`
paint-check +files:
    "{{blender_bin}}" -b --factory-startup -P scripts/paint_check.py -- {{files}} 2>&1 | grep -E '^PAINT|^EDGE|Error|Traceback'

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

# Casting (scripts/casting, casting/<role>/): how far each part has come, and everyone trying out for it
casting role="":
    python3 scripts/casting/casting.py status {{role}}

# What a casting step would do and cost, without doing it (step: headshots, take, tape, judge, revise)
casting-plan step role candidate="":
    python3 scripts/casting/casting.py plan "{{step}}" "{{role}}" {{candidate}} | sed '/^RESULT/d'

# PAID (Codex pictures; Opus too with more): a headshot for every look in casting/<role>/role.json that has none, and first `more` new looks written by Opus. Prints the cost and stops unless go is "go"
casting-headshots role go="" more="0":
    #!/usr/bin/env bash
    set -euo pipefail
    python3 scripts/casting/casting.py plan headshots "{{role}}" | sed '/^RESULT/d'
    [ "{{go}}" = "go" ] || { echo "Dry run: nothing was started. To spend it: just casting-headshots {{role}} go"; exit 0; }
    baml run casting_headshots -- --role "{{role}}" --more {{more}}
    python3 scripts/casting/casting.py status "{{role}}"

# PAID (a few dollars: TRELLIS.2, Claude in Blender, Kimodo): a shortlisted headshot built into a character, then its reel taped and its camera test run (both free). Prints the cost and stops unless go is "go"
casting-take role candidate go="":
    #!/usr/bin/env bash
    set -euo pipefail
    python3 scripts/casting/casting.py plan take "{{role}}" "{{candidate}}" | sed '/^RESULT/d'
    [ "{{go}}" = "go" ] || { echo "Dry run: nothing was started. To spend it: just casting-take {{role}} {{candidate}} go"; exit 0; }
    baml run casting_take -- --role "{{role}}" --candidate "{{candidate}}"
    python3 scripts/casting/casting.py tape "{{role}}" "{{candidate}}" | sed '/^RESULT/d'
    python3 scripts/casting/casting.py judge "{{role}}" "{{candidate}}" | sed '/^RESULT/d'

# Free: a take's reel and chemistry read, in background Blender: the sides and the warm-up on its skeleton, its cards, the tag moves, the crew's dance in one dancer's place, a sparring bout (into shots/casting/<role>/<candidate>-<n>/). Skips what is there
casting-tape role candidate:
    python3 scripts/casting/casting.py tape "{{role}}" "{{candidate}}" | sed '/^RESULT/d'

# Free: the camera test, the renderer's judges on a take in the crew's dance, summed up into casting/<role>/candidates/<candidate>/scores-<n>.json (about five minutes). again=yes runs judges already run
casting-judge role candidate again="":
    python3 scripts/casting/casting.py judge "{{role}}" "{{candidate}}" {{ if again != "" { "--again" } else { "" } }} | sed '/^RESULT/d'

# Free: the same judges on the cast member a candidate stands in for (the crew's own take), so a score has something to beat
casting-baseline role:
    python3 scripts/casting/casting.py baseline "{{role}}" | sed '/^RESULT/d'

# A callback: the open notes become new takes. Notes on moves or cards are answered first, free (the same build, taped and judged again); notes on the look are PAID (Opus rewrites the brief, Codex redraws it from the last picture, it is built again) and wait unless go is "go"
casting-revise role candidate go="":
    #!/usr/bin/env bash
    set -euo pipefail
    python3 scripts/casting/casting.py plan revise "{{role}}" "{{candidate}}" | sed '/^RESULT/d'
    if python3 scripts/casting/casting.py has-free-notes "{{role}}" "{{candidate}}"; then
        python3 scripts/casting/casting.py retake "{{role}}" "{{candidate}}" | sed '/^RESULT/d'
        python3 scripts/casting/casting.py tape "{{role}}" "{{candidate}}" | sed '/^RESULT/d'
        python3 scripts/casting/casting.py judge "{{role}}" "{{candidate}}" | sed '/^RESULT/d'
    fi
    if python3 scripts/casting/casting.py has-look-notes "{{role}}" "{{candidate}}"; then
        if python3 scripts/casting/casting.py is-stand-in "{{role}}" "{{candidate}}"; then echo "A stand-in is not rebuilt: its notes on the look stay open."; exit 0; fi
        [ "{{go}}" = "go" ] || { echo "Notes on the look wait: nothing paid was started. To spend it: just casting-revise {{role}} {{candidate}} go"; exit 0; }
        baml run casting_revise -- --role "{{role}}" --candidate "{{candidate}}"
        python3 scripts/casting/casting.py tape "{{role}}" "{{candidate}}" | sed '/^RESULT/d'
        python3 scripts/casting/casting.py judge "{{role}}" "{{candidate}}" | sed '/^RESULT/d'
    fi

# Pictures of the casting pages, every stage, at phone and desktop width, into evidence/casting/ (the gallery must be running on that port; needs Chrome)
casting-shots port="8028" candidate="villager":
    python3 scripts/casting/shots.py --port {{port}} --candidate "{{candidate}}"

# Casting's own tests: the files, the board, the costs, the notes, and the gallery's casting API (no Blender, no models)
casting-test:
    python3 scripts/casting/test_casting.py

# Vendor the b28 clay style kit into the gallery
sync-kit:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p gallery/vendor
    curl -fsSL https://b28.dev/kit/b28-clay.css -o gallery/vendor/b28-clay.css
    grep -q -- '--clay-' gallery/vendor/b28-clay.css || { echo "sync-kit: not the b28 clay kit" >&2; exit 1; }
    echo "vendored gallery/vendor/b28-clay.css"

# Serve the gallery to this Mac and phones on the same Wi-Fi
gallery port="8028" runs="runs" shots="shots" videos="videos":
    python3 scripts/gallery.py --port {{port}} --runs "{{runs}}" --shots "{{shots}}" --videos "{{videos}}"

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
