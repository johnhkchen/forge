// Motion, start to finish, for one shot:
//
//   1. Opus choreographs: the plan in words becomes a shot list   (Choreograph)
//   2. Code stands our own poses along the path                   (scripts/motion/plan_shot.py)
//   3. MotionBricks fills in the movement between them, on RunPod  (motionbricks.baml)
//   4. Code measures the result and puts it on a box mannequin    (checks.py, to_gltf.py)
//   5. A background Blender films it                              (render_shot.py)
//
// A shot's plan lives in motion/shots/<name>.json (the brief, the beats, the
// set). Everything a shot makes goes into shots/<name>/, and a step whose
// file is already there is skipped, so a shot can be picked up where it
// stopped, or re-filmed without paying for the motion again.
//
//   baml run shoot -- --shot hero-rooftop

const SHOTS_DIR = "shots";
const SHOT_PLANS = "motion/shots";
const POSE_LIBRARY = "motion/poses.json";
const MOTION_SCRIPTS = "scripts/motion";
const MOTION_FPS = 30.0;
// How far a beat's moves may add up from the beat's planned length.
const BEAT_SLACK_SECONDS = 0.25;
const RENDER_TIMEOUT_MINUTES = 30;

/// motion/shots/<name>.json. (Its `set` is read by plan_shot.py, not here.)
class ShotBrief {
    name: string,
    brief: string,
    beats: BeatPlan[],
}

class ShotFailed {
    step: string,
    reason: string,

    implements baml.ToString {
        function to_string(self) -> string {
            `the shot stopped at ${self.step}: ${self.reason}`
        }
    }
}

/// How many frames a move plays for.
function move_frames(move: Move) -> int {
    4 * move.tokens - 7 - move.early_frames
}

function beat_seconds(beat: ShotBeat) -> float {
    let frames = beat.moves.reduce(
        (total, m) -> {
            total + move_frames(m)
        },
        0,
    );
    frames / MOTION_FPS
}

/// What is wrong with a shot list, in words Opus can act on. Empty when it is sound.
function shot_problems(shot: ShotList) -> string[] {
    let problems: string[] = [];
    if (shot.path.length() < 2) {
        problems.push("the path needs at least 2 points");
    }
    let moves = shot.beats.flat_map((b) -> {
        b.moves
    });
    if (!moves) {
        problems.push("there are no moves");
    }
    for (let beat in shot.beats) {
        if (beat.source != "poses") {
            problems.push(
                `beat "${beat.name}": only "poses" beats can be made so far, not "${beat.source}"`,
            );
        }
        let seconds = beat_seconds(beat);
        if ((seconds - beat.seconds).abs() > BEAT_SLACK_SECONDS) {
            problems.push(
                `beat "${beat.name}" should last ${beat.seconds} s but its moves add up to ${seconds} s`,
            );
        }
        for (let move in beat.moves) {
            if (move.tokens < 6 || move.tokens > 16) {
                problems.push(
                    `beat "${beat.name}", ${move.pose}: tokens must be 6 to 16, not ${move.tokens}`,
                );
            }
            if (move.early_frames < 0 || move.early_frames > 20) {
                problems.push(
                    `beat "${beat.name}", ${move.pose}: early_frames must be 0 to 20, not ${move.early_frames}`,
                );
            }
            if (move.speed_mps < 0.0) {
                problems.push(`beat "${beat.name}", ${move.pose}: speed_mps cannot be negative`);
            }
        }
    }
    for (let pair in steps_back(moves)) {
        problems.push(pair);
    }
    problems
}

/// Moves that are placed behind the one before them.
function steps_back(moves: Move[]) -> string[] {
    let out: string[] = [];
    let last = 0.0;
    for (let move in moves) {
        if (move.at_m < last - 0.001) {
            out.push(`${move.pose} at ${move.at_m} m is behind the move before it (${last} m)`);
        }
        last = move.at_m;
    }
    out
}

/// Asks Opus for the shot list; if it comes back unsound, shows Opus what is
/// wrong and asks once more.
function choreograph(brief: ShotBrief) -> ShotList {
    let first = Choreograph(brief.brief, brief.beats);
    let problems = shot_problems(first);
    if (!problems) {
        return first;
    }
    log.info(`choreograph: asking again, ${problems.length()} problems: ${problems.join("; ")}`);
    let again = Choreograph(
        `${brief.brief}\n\nYour last shot list had these problems. Fix every one:\n- ${problems.join("\n- ")}`,
        brief.beats,
    );
    let left = shot_problems(again);
    if (left) {
        throw ShotFailed { step: "choreograph", reason: left.join("; ") }
    }
    again
}

/// Runs one of scripts/motion/*.py and logs the lines it marks for us.
function motion_script(step: string, script: string, args: string[], mark: string) -> void {
    let out = baml.sys.run(
        "python3",
        args = [`${MOTION_SCRIPTS}/${script}`].concat(args),
        capture_output = true,
    ) catch (e) {
        baml.errors.Io => {
            throw ShotFailed { step: step, reason: "python3 not found" }
        },
    };
    let lines = string.from_utf8(out.stdout).lines();
    for (
        let line in lines.filter((l) -> {
            l.starts_with(mark)
        })
    ) {
        log.info(`${step}: ${line.slice(mark.length() + 1, line.length())}`);
    }
    if (!out.ok()) {
        throw ShotFailed { step: step, reason: string.from_utf8(out.stderr) }
    }
}

/// Films the shot folder's motion.glb in a background Blender.
function film(run: Run) -> void {
    let blender = baml.env.get("BLENDER") ?? BLENDER_APP;
    let out = baml.sys.run(
        blender,
        args = ["-b", "--factory-startup", "-P", `${MOTION_SCRIPTS}/render_shot.py`, "--", run.dir],
        timeout = baml.time.Duration.from_minutes(RENDER_TIMEOUT_MINUTES),
        capture_output = true,
    ) catch (e) {
        baml.errors.Io => {
            throw ShotFailed { step: "film", reason: `Blender not found at ${blender} (set BLENDER)` }
        },
        baml.errors.Timeout => {
            throw ShotFailed { step: "film", reason: `still rendering after ${RENDER_TIMEOUT_MINUTES} minutes` }
        },
    };
    let lines = string.from_utf8(out.stdout).lines();
    for (
        let line in lines.filter((l) -> {
            l.starts_with("RENDER ")
        })
    ) {
        log.info(`film: ${line.slice(7, line.length())}`);
    }
    if (!out.ok() || !run.has("motion.mp4")) {
        let tail = lines.slice(baml.Int.max(0, lines.length() - 15), lines.length()).join("\n");
        throw ShotFailed { step: "film", reason: `Blender exited ${out.exit_code}:\n${tail}` }
    }
}

/// Makes one shot from its plan in motion/shots/<shot>.json; returns its folder.
function shoot(shot: string) -> string {
    let plan_file = `${SHOT_PLANS}/${shot}.json`;
    let brief = baml.json.decode<ShotBrief>(baml.fs.read(plan_file));
    let run = Run { dir: `${SHOTS_DIR}/${shot}` };
    baml.fs.mkdir(run.dir, baml.fs.MkdirOptions { recursive: true });
    //# 1. Opus choreographs (or the shot list kept with the plan is used)
    if (!run.has("shotlist.json")) {
        let kept = `${SHOT_PLANS}/${shot}.shotlist.json`;
        if (baml.fs.exists(kept)) {
            log.info(`choreograph: using ${kept}`);
            baml.fs.write(run.path("shotlist.json"), baml.fs.read(kept));
        } else {
            log.info("choreograph: asking Opus for the shot list");
            run.save("shotlist.json", choreograph(brief));
        }
    }
    //# 2. Stand our poses along the path
    motion_script("plan", "plan_shot.py", [run.dir, "--brief", plan_file], "PLAN");
    //# 3. MotionBricks fills in the movement
    if (!run.has("motion.json")) {
        log.info("motion: sending the poses to MotionBricks on RunPod");
        let reply = MotionBricks.from_env().call("inbetween", baml.fs.read(run.path("request.json")));
        baml.fs.write(run.path("motion.json"), reply.text);
        run.save("motion-record.json", reply.record);
    }
    //# 4. Measure it, and put it on the box mannequin
    motion_script("checks", "checks.py", [run.dir], "CHECK");
    motion_script("mannequin", "to_gltf.py", [run.dir], "GLTF");
    //# 5. Film it
    if (!run.has("motion.mp4")) {
        log.info("film: a background Blender is rendering");
        film(run);
    }
    run.dir
}

/// Only step 1, to read what Opus would plan.
function choreograph_only(shot: string) -> ShotList {
    choreograph(baml.json.decode<ShotBrief>(baml.fs.read(`${SHOT_PLANS}/${shot}.json`)))
}

const TEST_BEATS: BeatPlan[] = [
    BeatPlan {
        time: "0-1 s",
        action: "crouched, looks left",
        driven_by: "crouch, crouch_look_left",
    },
    BeatPlan { time: "1-2.5 s", action: "sneaks forward", driven_by: "sneak steps" },
];

const TEST_REPLY = `
    {
      "title": "Two beats",
      "start_pose": "crouch",
      "path": [{ "x": 0, "z": 0 }, { "x": 0.0, "z": 1.0 }, { "x": 0.2, "z": 2.0 }],
      "beats": [
        {
          "name": "look left",
          "source": "poses",
          "seconds": 1.0,
          "moves": [
            { "pose": "crouch_look_left", "at_m": 0, "side_m": 0, "facing_deg": 0, "speed_mps": 0,
              "tokens": 9, "early_frames": 0, "pins": [], "hold_pins_frames": 0 }
          ]
        },
        {
          "name": "sneak forward",
          "source": "poses",
          "seconds": 1.5,
          "moves": [
            { "pose": "sneak_left", "at_m": 0.5, "side_m": 0, "facing_deg": 0, "speed_mps": 0.8,
              "tokens": 8, "early_frames": 4, "pins": [], "hold_pins_frames": 0 },
            { "pose": "sneak_right", "at_m": 1.0, "side_m": 0, "facing_deg": 0, "speed_mps": 0.8,
              "tokens": 8, "early_frames": 0, "pins": ["right_foot"], "hold_pins_frames": 0 }
          ]
        }
      ],
      "props": [{ "prop": "katana", "socket": "back", "from_seconds": 0 }],
      "camera": [{ "from_seconds": 0, "view": "three_quarter_tracking", "distance_m": 5.5 }]
    }
`;

test "Choreograph parses a shot list" {
    let shot = Choreograph@spec("a rooftop", TEST_BEATS).parse(TEST_REPLY);
    assert.equal(shot.start_pose, "crouch");
    assert.equal(shot.beats.length(), 2);
    assert.equal(shot.beats.at(1)?.moves.at(1)?.pins, ["right_foot"]);
    assert.equal(shot.props.at(0)?.socket, "back");
    assert.approx_equal(shot.path.at(2)?.x ?? 0.0, 0.2, 0.0001);
    // The reply above is sound: 29 frames, then 21 + 25.
    assert.equal(shot_problems(shot), [])
}

test "Choreograph is shown the pose library, the beats and how long a move lasts" {
    let asked = Choreograph@spec("a rooftop at night", TEST_BEATS).prompt().to_string();
    assert.contains(asked, "land_three_point");
    assert.contains(asked, "a rooftop at night");
    assert.contains(asked, "sneaks forward");
    assert.contains(asked, "4 * tokens - 7 - early_frames")
}

test "a move's length comes from its tokens; a beat's from its moves" {
    let shot = Choreograph@spec("a rooftop", TEST_BEATS).parse(TEST_REPLY);
    let sneak = shot.beats.at(1) ?? throw "no second beat";
    assert.equal(
        sneak.moves.map((m) -> {
            move_frames(m)
        }),
        [21, 25],
    );
    assert.approx_equal(beat_seconds(sneak), 46 / 30.0, 0.0001)
}

test "an unsound shot list is told what is wrong with it" {
    let shot = Choreograph@spec("a rooftop", TEST_BEATS).parse(TEST_REPLY);
    let look = shot.beats.at(0)?.moves.at(0) ?? throw "no first move";
    look.tokens = 17;
    let back = shot.beats.at(1)?.moves.at(1) ?? throw "no last move";
    back.at_m = 0.2;
    let problems = shot_problems(shot).join("\n");
    assert.contains(problems, "should last 1.0 s but its moves add up to");
    assert.contains(problems, "tokens must be 6 to 16, not 17");
    assert.contains(problems, "sneak_right at 0.2 m is behind the move before it (0.5 m)")
}

/// The names in motion/poses.json.
class PoseLibrary {
    poses: map<string, json>,
}

test "the pose names match the library" {
    let library = baml.json.decode<PoseLibrary>(baml.fs.read(POSE_LIBRARY));
    let names = library.poses.keys();
    // Every pose in the library is one Opus may name, and is on the card it reads...
    for (let name in names) {
        let _ = baml.json.decode<PoseName>(baml.json.stringify(name));
        assert.contains(POSE_CARD, name);
    }
    // ...and there are no names on offer that the library lacks.
    assert.equal(names.length(), 13)
}

test "the hero shot list kept with its plan is sound" {
    let shot = baml.json.decode<ShotList>(baml.fs.read(`${SHOT_PLANS}/hero-rooftop.shotlist.json`));
    assert.equal(shot_problems(shot), []);
    assert.equal(shot.beats.length(), 6);
    let frames = shot.beats
        .flat_map((b) -> {
            b.moves
        })
        .reduce(
            (total, m) -> {
                total + move_frames(m)
            },
            0,
        );
    // Twelve seconds at 30 frames a second.
    assert.equal(frames, 360)
}
