// Motion, start to finish, for one shot:
//
//   1. Opus choreographs: the plan in words becomes a shot list   (Choreograph)
//   2. Code stands our own poses along the path                   (scripts/motion/plan_shot.py)
//   3. MotionBricks fills in the movement between them, on RunPod  (motionbricks.baml)
//   4. Code measures the result and puts it on a box mannequin    (checks.py, to_gltf.py)
//   5. A background Blender films it                              (render_shot.py)
//
// A shot with a beat made from a sentence ("source": "text") is made in
// pieces at step 3: each beat on its own (Kimodo for a sentence, MotionBricks
// between our poses), then a MotionBricks tween across every seam, then the
// join (scripts/motion/timeline.py). Each request to a worker is kept under
// the hash of its content, so only what changed is ever made again.
//
// A shot's plan lives in motion/shots/<name>.json (the brief, the beats, and
// the standing set it is filmed on: see sets.baml). A plan with a `segment`
// is a take, with more than one person in it; sets.baml makes those.
// Everything a shot makes goes into shots/<name>/, and a step whose
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
// What Kimodo, the text-to-motion model, does well: prompts that start this
// way, up to ten seconds each, with only a few moments pinned to a pose.
const TEXT_PROMPT_START = "A person ";
const TEXT_BEAT_MAX_SECONDS = 10.0;
const TEXT_BEAT_MAX_KEYS = 4;
// Pieces, then seams, then the join; one more in case a pass only planned.
const TIMELINE_PASSES = 4;

// The library poses that sit: only a seat mark takes them.
const SEATED_POSES: PoseName[] = ["sit", "sit_talk"];

/// motion/shots/<name>.json.
class ShotBrief {
    name: string,
    brief: string,
    beats: BeatPlan[],
    // The standing set it is filmed on, by name (sets/<name>). The older way,
    // a ledge, roof and wall described here, is still read by plan_shot.py.
    set: (string | map<string, json>)?,
    // A take: the segment it plays (motion/segments/<name>.json) and who
    // plays each role (the end of a run folder's name).
    segment: string?,
    roles: map<string, string>?,
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

/// How many frames a beat plays for: its moves', or a text beat's own length.
function beat_frames(beat: ShotBeat) -> int {
    if (beat.source == "text") {
        return beat.frames ?? (beat.seconds * MOTION_FPS).iround();
    }
    beat.moves.reduce(
        (total, m) -> {
            total + move_frames(m)
        },
        0,
    )
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

/// What is wrong with a shot list, in words Opus can act on. Empty when it is
/// sound. `stage` is the standing set the shot is on, if it is on one.
function shot_problems(shot: ShotList, stage: StandingSet? = null) -> string[] {
    let problems: string[] = mark_problems(shot, stage);
    // On a standing set the marks give the route; anywhere else the shot list draws it.
    if (shot.path.length() < 2 && !shot.start_mark) {
        problems.push("the path needs at least 2 points");
    }
    let moves = shot.beats.flat_map((b) -> {
        b.moves
    });
    if (!shot.beats) {
        problems.push("there are no beats");
    }
    let in_beats = shot.beats.flat_map((beat) -> {
        match (beat.source) {
            "poses" => poses_beat_problems(beat),
            "text" => text_beat_problems(beat),
            "walk" => {
                [`beat "${beat.name}": a "walk" beat cannot be made yet; use "poses" or "text"`]
            },
        }
    });
    problems.concat(in_beats).concat(steps_back(moves))
}

/// What is wrong with a beat made from our poses.
function poses_beat_problems(beat: ShotBeat) -> string[] {
    let problems: string[] = [];
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
    problems
}

/// What is wrong with a beat made from a sentence.
function text_beat_problems(beat: ShotBeat) -> string[] {
    let problems: string[] = [];
    let prompt = beat.prompt ?? "";
    if (!prompt.trim()) {
        problems.push(`beat "${beat.name}": a text beat needs a prompt`);
    } else if (!prompt.trim().starts_with(TEXT_PROMPT_START)) {
        problems.push(`beat "${beat.name}": the prompt should start "${TEXT_PROMPT_START}..."`);
    }
    if (beat.moves) {
        problems.push(
            `beat "${beat.name}": a text beat has no moves; put poses it must pass through in keys`,
        );
    }
    let from = beat.from_m;
    let to = beat.to_m;
    if (beat.to) {
        // It walks to a mark: the set says where that is along the path.
    } else if (from == null || to == null) {
        problems.push(
            `beat "${beat.name}": a text beat says where it starts and ends on the path (from_m, to_m)`,
        );
    } else if (to < from - 0.001) {
        problems.push(`beat "${beat.name}": it ends (${to} m) behind where it starts (${from} m)`);
    }
    if (beat.seconds <= 0.0 || beat.seconds > TEXT_BEAT_MAX_SECONDS) {
        problems.push(
            `beat "${beat.name}": a text beat lasts up to ${TEXT_BEAT_MAX_SECONDS} s, not ${beat.seconds} s`,
        );
    }
    let keys = beat.keys ?? [];
    if (keys.length() > TEXT_BEAT_MAX_KEYS) {
        problems.push(
            `beat "${beat.name}": at most ${TEXT_BEAT_MAX_KEYS} keys, not ${keys.length()}`,
        );
    }
    for (let key in keys) {
        if (key.at_seconds < 0.0 || key.at_seconds > beat.seconds + BEAT_SLACK_SECONDS) {
            problems.push(
                `beat "${beat.name}", key ${key.pose}: at ${key.at_seconds} s is outside the beat (0 to ${beat.seconds} s)`,
            );
        }
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

/// The shot in words, with the standing set it is on (its marks and walks) for Opus to block it by.
function brief_on_set(brief: string, stage: StandingSet?) -> string {
    if let on: StandingSet = stage {
        `${brief}\n\n${on.card()}`
    } else {
        brief
    }
}

/// Asks Opus for the shot list; if it comes back unsound, shows Opus what is
/// wrong and asks once more.
function choreograph(brief: ShotBrief) -> ShotList {
    let stage = standing_set_of(brief);
    let words = brief_on_set(brief.brief, stage);
    let first = Choreograph(words, brief.beats);
    let problems = shot_problems(first, stage = stage);
    if (!problems) {
        return first;
    }
    log.info(`choreograph: asking again, ${problems.length()} problems: ${problems.join("; ")}`);
    let again = Choreograph(
        `${words}\n\nYour last shot list had these problems. Fix every one:\n- ${problems.join("\n- ")}`,
        brief.beats,
    );
    let left = shot_problems(again, stage = stage);
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
        args = ["-b", "--factory-startup", "--python-exit-code", "1", "-P", `${MOTION_SCRIPTS}/render_shot.py`, "--", run.dir],
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

/// The part of plan.json that says whether the shot is made in pieces, and which standing set it is on.
class ShotPlan {
    pieces: json[]?,
    standing_set: string?,

    /// Does its set have cameras of its own? Then it is filmed from those, not by a camera that follows.
    function has_set_cameras(self) -> bool {
        if let name: string = self.standing_set {
            StandingSet.load(name).cameras.keys().length() > 0
        } else {
            false
        }
    }
}

/// One request timeline.py still needs an answer to (todo.json).
class PieceToMake {
    request: string @description("The request's name in the shot's cache: the hash of its content"),
    kind: "inbetween" | "text",
    what: string,
}

/// Sends what timeline.py asks for until it has joined the shot: the pieces,
/// then the seams. An answer already in the cache is never asked for again.
function join_pieces(run: Run) -> void {
    let passes = 0;
    while (passes < TIMELINE_PASSES) {
        passes += 1;
        motion_script("join", "timeline.py", [run.dir], "TIMELINE");
        let todo = baml.json.decode<PieceToMake[]>(baml.fs.read(run.path("todo.json")));
        if (!todo) {
            return;
        }
        for (let piece in todo) {
            log.info(`motion: making ${piece.what} (${piece.kind}) on RunPod`);
            let reply = MotionBricks.from_env().call(
                piece.kind,
                baml.fs.read(run.path(`cache/${piece.request}.request.json`)),
            );
            baml.fs.write(run.path(`cache/${piece.request}.json`), reply.text);
            run.save(`cache/${piece.request}.record.json`, reply.record);
        }
    }
    throw ShotFailed { step: "join", reason: `still not joined after ${TIMELINE_PASSES} passes` }
}

/// Steps 2 to 4 for a folder that has its shotlist.json: the poses stood on the
/// path (or on the set's marks), the motion made, measured, and put on the box figure.
function make_motion(run: Run, plan_file: string) -> void {
    //# 2. Stand our poses along the path
    motion_script("plan", "plan_shot.py", [run.dir, "--brief", plan_file], "PLAN");
    //# 3. MotionBricks fills in the movement
    if (run.load<ShotPlan>("plan.json").pieces) {
        //# 3. Made in pieces: each beat, then a tween across every seam, then the join
        join_pieces(run);
    } else if (!run.has("motion.json")) {
        log.info("motion: sending the poses to MotionBricks on RunPod");
        let reply = MotionBricks.from_env().call("inbetween", baml.fs.read(run.path("request.json")));
        baml.fs.write(run.path("motion.json"), reply.text);
        run.save("motion-record.json", reply.record);
    }
    //# 4. Measure it, and put it on the box mannequin
    motion_script("checks", "checks.py", [run.dir], "CHECK");
    motion_script("mannequin", "to_gltf.py", [run.dir], "GLTF");
}

/// Makes one shot from its plan in motion/shots/<shot>.json; returns its folder.
function shoot(shot: string) -> string {
    let plan_file = `${SHOT_PLANS}/${shot}.json`;
    let brief = baml.json.decode<ShotBrief>(baml.fs.read(plan_file));
    let run = Run { dir: `${SHOTS_DIR}/${shot}` };
    baml.fs.mkdir(run.dir, baml.fs.MkdirOptions { recursive: true });
    if (brief.segment) {
        // A take: more than one person, each with a shot list from the segment.
        return shoot_take(run, plan_file);
    }
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
    make_motion(run, plan_file);
    //# 5. Film it: from the set's own cameras if it has them, else with the camera that follows
    if (run.load<ShotPlan>("plan.json").has_set_cameras()) {
        if (!run.has("films.json")) {
            log.info("film: a background Blender is rendering every camera");
            film_on_set(run);
        }
    } else if (!run.has("motion.mp4")) {
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

const TEXT_BEAT_REPLY = `
    {
      "name": "sneak forward", "source": "text", "seconds": 3.0, "moves": [],
      "prompt": "A person sneaks forward in a low crouch.",
      "from_m": 0.0, "to_m": 2.2, "speed_in_mps": 0.0, "speed_out_mps": 0.8,
      "keys": [{ "pose": "crouch", "at_seconds": 0, "at_m": 0, "side_m": 0, "facing_deg": 0, "only": [] }]
    }
`;

test "a beat can be made from a sentence" {
    let shot = Choreograph@spec("a rooftop", TEST_BEATS).parse(TEST_REPLY);
    shot.beats
        = [shot.beats.at(0) ?? throw "no first beat", baml.json.decode<ShotBeat>(TEXT_BEAT_REPLY)];
    assert.equal(shot_problems(shot), []);
    let sneak = shot.beats.at(1) ?? throw "no text beat";
    assert.equal(sneak.keys?.at(0)?.pose, "crouch");
    assert.equal(sneak.lead_frames, null)
}

test "an unsound text beat is told what is wrong with it" {
    let beat = baml.json.decode<ShotBeat>(TEXT_BEAT_REPLY);
    beat.prompt = "sneaks forward";
    beat.to_m = -1.0;
    beat.seconds = 12.0;
    let problems = text_beat_problems(beat).join("\n");
    assert.contains(problems, `the prompt should start "A person ..."`);
    assert.contains(problems, "behind where it starts");
    assert.contains(problems, "lasts up to 10.0 s");
    let walk = ShotBeat { ...beat, source: "walk" };
    let shot = Choreograph@spec("a rooftop", TEST_BEATS).parse(TEST_REPLY);
    shot.beats = [walk];
    assert.contains(shot_problems(shot).join("\n"), `a "walk" beat cannot be made yet`)
}

test "Choreograph is told how a text beat works" {
    let asked = Choreograph@spec("a rooftop at night", TEST_BEATS).prompt().to_string();
    assert.contains(asked, "HOW A TEXT BEAT WORKS");
    assert.contains(asked, "A person sneaks forward")
}

test "the mixed hero shot list kept with its plan is sound" {
    let shot = baml.json.decode<ShotList>(baml.fs.read(`${SHOT_PLANS}/hero-rooftop-mixed.shotlist.json`));
    assert.equal(shot_problems(shot), []);
    assert.equal(
        shot.beats.map((b) -> {
            b.source
        }),
        ["poses", "text", "text", "text", "poses", "poses"],
    );
    // The same beats as the in-house cut, frame for frame: 62 + 89 + 58 + 46 + 46 + 59.
    let frames = shot.beats.map((b) -> {
        b.frames
            ?? b.moves.reduce(
                (total, m) -> {
                    total + move_frames(m)
                },
                0,
            )
    });
    assert.equal(frames, [62, 89, 58, 46, 46, 59]);
    let vault = shot.beats.at(3) ?? throw "no vault";
    assert.equal(vault.keys?.at(0)?.only, ["right_hand"]);
    assert.equal(vault.join_out_frames, 0)
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
    assert.equal(names.length(), 18);
    // The poses the library marks as seated are the ones only a seat mark takes.
    let seated = names.filter((name) -> {
        baml.json.path_or<bool?>(library.poses.get(name) ?? throw "no pose", ".seated", null)
            ?? false
    });
    assert.equal(seated, ["sit", "sit_talk"]);
    assert.equal(
        seated,
        SEATED_POSES.map((pose) -> {
            `${pose}`
        }),
    )
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
