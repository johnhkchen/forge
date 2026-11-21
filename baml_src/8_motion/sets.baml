// Standing sets: a place of our own, built once and shot many times, the way
// a TV studio keeps its talk-show stage up all season.
//
// A set is a folder, sets/<name>/, with a set.json (scripts/sets/standing.py
// says what is in it): the floor, what is in the way, named marks to stand
// on and sit at, fixed cameras, fixed lights, a painted backdrop, dressing.
// A shot's plan names its set ("set": "studio"), and then:
//
//   - blocking names marks, never coordinates: a shot list's beats say `to`
//     or `at` a mark, and plan_shot.py asks the set for the path, facings,
//     seat heights and hand spots;
//   - the contact step keeps the cast out of the set's blocks;
//   - one take is filmed from every one of the set's cameras at once, and
//     the cut is chosen afterwards.
//
// A take is a shot with more than one person in it. It comes from a segment
// (motion/segments/<name>.json): the routine written once for roles and
// marks, so the only things a take adds are who plays whom:
//
//   baml run shoot -- --shot studio-guest-entrance
//   baml run cast -- --shot studio-guest-entrance --character runs --clip guest-entrance
//
// Everything a take makes goes into shots/<name>/: a folder per role (each
// one an ordinary shot: shotlist.json, plan.json, motion.json, checks.json),
// and the films, one .mp4 and one strip per camera.

const SETS_DIR = "sets";
const SET_SCRIPTS = "scripts/sets";
const SET_BACKDROP_WIDTH_PX = 1024;

/// A named spot on a set (the part of it that blocking needs to know).
class SetMark {
    kind: "stand" | "sit" | "touch" | "lean",
    about: string?,
    offstage: bool?,
}

/// Two marks people can walk between.
class SetPath {
    from: string,
    to: string,
}

class SetCamera {
    lens_mm: float,
    sees: string[]?,
    about: string?,
}

/// sets/<name>/set.json, as far as planning a shot needs it.
class StandingSet {
    name: string,
    title: string?,
    about: string?,
    marks: map<string, SetMark>,
    paths: SetPath[]?,
    cameras: map<string, SetCamera>,

    function load(name: string) -> StandingSet {
        let file = `${SETS_DIR}/${name}/set.json`;
        if (!baml.fs.exists(file)) {
            throw ShotFailed { step: "set", reason: `there is no set called "${name}" (no ${file})` }
        }
        baml.json.decode<StandingSet>(baml.fs.read(file))
    }

    /// The set in words, for whoever lays out a shot on it.
    function card(self) -> string {
        let marks = self.marks.keys()
            .map((name) -> {
                let mark = self.marks.get(name) ?? throw "a key without a value";
                let what = match (mark.kind) {
                    "stand" => "a spot to stand on",
                    "sit" => "a seat",
                    "touch" => "a spot to stand on, with a spot for a hand",
                    "lean" => "a spot to stand at, with something to lean a hand on",
                };
                `- ${name}: ${what}. ${mark.about ?? ""}`
            })
            .join("\n");
        let walks = (self.paths ?? [])
            .map((p) -> {
                `${p.from} to ${p.to}`
            })
            .join("; ");
        `
            A STANDING SET: ${self.title ?? self.name}. ${self.about ?? ""}
            Its marks (name them; never write a coordinate):
            ${marks}
            It has a path, walked either way, between: ${walks}.
        `
    }
}

/// The standing set a shot's plan names, if it names one.
function standing_set_of(brief: ShotBrief) -> StandingSet? {
    if let name: string = brief.set {
        StandingSet.load(name)
    } else {
        null
    }
}

/// What is wrong with how a shot list uses marks. Empty when it is sound.
function mark_problems(shot: ShotList, stage: StandingSet?) -> string[] {
    let named = shot.beats.flat_map((beat) -> {
        [beat.from, beat.to, beat.at].filter_map((mark) -> {
            mark
        })
    });
    let start: string[] = if let mark: string = shot.start_mark {
        [mark]
    } else {
        []
    };
    let all = start.concat(named);
    if (!all) {
        return [];
    }
    let on = stage
        ?? return ["the shot list names marks, but the shot has no standing set"];
    let problems: string[] = if (start) {
        []
    } else {
        ["a shot list that names marks says which one it starts on (start_mark)"]
    };
    let unknown = all
        .filter((mark) -> {
            on.marks.get(mark) == null
        })
        .map((mark) -> {
            `the set "${on.name}" has no mark called "${mark}"`
        });
    let seats = shot.beats.flat_map((beat) -> {
        let mark = beat.at ?? beat.to ?? "";
        let is_seat = on.marks.get(mark)?.kind == "sit";
        beat.moves
            .filter((move) -> {
                SEATED_POSES.includes(move.pose) && !is_seat
            })
            .map((move) -> {
                `beat "${beat.name}": ${move.pose} sits, and "${mark}" is not a seat`
            })
    });
    problems.concat(unknown).concat(seats)
}

/// One role of a take, in shots/<take>/take.json (written by scripts/motion/segment.py).
class TakeRole {
    character: string @description(
        "The end of the character's run folder name, like 'roosevelt-wrestler-1890s'",
    ),
    folder: string,
}

class TakeRecord {
    name: string,
    set: string,
    segment: string,
    roles: map<string, TakeRole>,
}

/// Films a shot or a take from every camera its set has: one .mp4 and one strip each.
function film_on_set(run: Run, more: string[] = []) -> void {
    motion_blender("film", "render_take.py", [run.dir].concat(more), "RENDER");
}

/// Makes a take from a segment: each role's motion, then one film per camera on box figures.
function shoot_take(run: Run, plan_file: string) -> string {
    //# 1. The segment's shot lists, one per role
    motion_script("segment", "segment.py", [plan_file, run.dir], "SEGMENT");
    let take = run.load<TakeRecord>("take.json");
    //# 2. Each role's motion, like any shot's
    for (let role in take.roles.keys()) {
        log.info(`take: the ${role}`);
        let part = Run { dir: `${run.dir}/${role}` };
        make_motion(part, plan_file);
    }
    //# 3. Film it from every camera
    if (!run.has("films.json")) {
        log.info("film: a background Blender is rendering every camera");
        film_on_set(run);
    }
    run.dir
}

/// The newest run folder in `runs` whose name ends with `character` (or `character` itself, if it is a folder).
function character_run(runs: string, character: string) -> string {
    if (baml.fs.exists(`${character}/lowpoly.glb`)) {
        return character;
    }
    let found = baml.fs.read_dir(runs)
        .map((entry) -> {
            entry.name
        })
        .filter((name) -> {
            name.ends_with(`-${character}`)
        })
        .sort_by_key((name) -> {
            name
        });
    let newest = found.at(found.length() - 1)
        ?? throw ShotFailed { step: "cast", reason: `no run in ${runs} is named for "${character}"` };
    `${runs}/${newest}`
}

/// Plays a finished take on its cast (each role's character, from `runs`), and films it from every camera.
function cast_take(run: Run, runs: string, clip: string) -> string {
    let take = run.load<TakeRecord>("take.json");
    for (let role in take.roles.keys()) {
        let part = take.roles.get(role) ?? throw "a key without a value";
        let folder = `${run.dir}/${part.folder}`;
        if (!baml.fs.exists(`${folder}/motion.json`)) {
            throw ShotFailed { step: "cast", reason: `no motion for the ${role} yet: run shoot first` }
        }
        //# The role's motion through its character's own skeleton, limits and feet
        motion_blender(
            `cast the ${role}`,
            "apply_shot.py",
            [folder, character_run(runs, part.character), "--name", clip],
            "APPLY",
        );
    }
    //# Film the low-poly cast on the set, from every camera
    film_on_set(run, more = ["--cast", clip]);
    run.dir
}

const SET_BACKDROP_RULES = `
    Use your built-in image_gen tool to generate exactly one landscape image
    (3:2, wide), then reply with the single word: done. Do not run shell
    commands and do not edit files.
`;

/// What Codex is asked for: the rules above, then the set's own words for its backdrop (sets/<name>/backdrop.txt).
function set_backdrop_request(words: string) -> string {
    if (words.includes("image_gen")) {
        return words;
    }
    `
        ${SET_BACKDROP_RULES}

        Image: a painted theatre backdrop, painted flat like a scenic artist's
        backcloth, filling the whole frame edge to edge with no border, no
        frame, no people in front of it, no text. Evenly lit.

        ${words}
    `
}

/// Has Codex paint a set's backdrop from sets/<name>/backdrop.txt. Keeps the
/// picture as it came (backdrop-full.png, not committed) and a smaller one
/// the films and the gallery use (backdrop.png).
function paint_set_backdrop(name: string) -> string {
    let dir = `${SETS_DIR}/${name}`;
    let words = baml.fs.read(`${dir}/backdrop.txt`);
    log.info("backdrop: codex is painting");
    let full = codex_picture(dir, set_backdrop_request(words), [], `${dir}/backdrop-full.png`);
    let small = `${dir}/backdrop.png`;
    let out = baml.sys.run(
        "sips",
        args = ["-Z", `${SET_BACKDROP_WIDTH_PX}`, full, "--out", small],
        capture_output = true,
    );
    if (!out.ok()) {
        throw ShotFailed { step: "backdrop", reason: string.from_utf8(out.stderr) }
    }
    small
}

test "a set says its marks and walks in words" {
    let studio = StandingSet.load("studio");
    let card = studio.card();
    assert.contains(card, "A STANDING SET: The studio");
    assert.contains(card, "- couch_1: a seat.");
    assert.contains(card, "- meet_left: a spot to stand on, with a spot for a hand.");
    assert.contains(card, "desk_chair to meet_right");
    assert.equal(studio.cameras.keys(), ["wide", "host", "guest"])
}

test "every set in the repo reads" {
    assert.equal(StandingSet.load("rooftop").cameras.keys().length(), 0);
    assert.equal(StandingSet.load("ring").marks.get("steps")?.kind, "stand");
    let missing = StandingSet.load("the moon") catch (e) {
        let failed: ShotFailed => failed.reason,
    };
    assert.contains(`${missing}`, `there is no set called "the moon"`)
}

test "the hero shots are filmed on the rooftop set" {
    for (let shot in ["hero-rooftop", "hero-rooftop-mixed"]) {
        let brief = baml.json.decode<ShotBrief>(baml.fs.read(`${SHOT_PLANS}/${shot}.json`));
        assert.equal(standing_set_of(brief)?.name, "rooftop");
    }
}

const MARKED_REPLY = `
    {
      "title": "On and sit",
      "start_pose": "stand",
      "start_mark": "wings",
      "path": [],
      "beats": [
        {
          "name": "walk on", "source": "text", "seconds": 4.0, "moves": [],
          "prompt": "A person walks forward at an easy pace.", "to": "centre",
          "keys": [{ "pose": "stand", "at_seconds": 0, "at_m": 0, "side_m": 0, "facing_deg": 0, "only": [], "where": "end" }]
        },
        {
          "name": "sit down", "source": "poses", "seconds": 1.9, "at": "centre",
          "moves": [
            { "pose": "sit", "at_m": 0, "side_m": 0, "facing_deg": 0, "speed_mps": 0,
              "tokens": 16, "early_frames": 0, "pins": [], "hold_pins_frames": 0 }
          ]
        }
      ],
      "props": [],
      "camera": []
    }
`;

test "a shot list can name marks, and is told when it names them wrongly" {
    let studio = StandingSet.load("studio");
    let shot = Choreograph@spec("a talk show", TEST_BEATS).parse(MARKED_REPLY);
    assert.equal(shot.start_mark, "wings");
    assert.equal(shot.beats.at(0)?.to, "centre");
    assert.equal(shot.beats.at(0)?.keys?.at(0)?.where, "end");
    // A text beat that names where it goes needs no from_m and to_m.
    let problems = shot_problems(shot, stage = studio).join("\n");
    assert.contains(problems, `sit sits, and "centre" is not a seat`);
    assert.equal(shot_problems(shot, stage = studio).length(), 1);
    let sit = shot.beats.at(1) ?? throw "no second beat";
    sit.at = "the green room";
    assert.contains(
        shot_problems(shot, stage = studio).join("\n"),
        `has no mark called "the green room"`,
    );
    assert.contains(shot_problems(shot).join("\n"), "the shot has no standing set")
}

test "Choreograph is told how marks work, and shown the set's marks" {
    let studio = StandingSet.load("studio");
    let asked = Choreograph@spec(brief_on_set("a guest walks on", studio), TEST_BEATS).prompt().to_string();
    assert.contains(asked, "HOW MARKS WORK");
    assert.contains(asked, "A STANDING SET: The studio");
    assert.contains(asked, "- wings: a spot to stand on.");
    assert.contains(asked, "sit_talk")
}

/// The roles' shot lists inside a segment (motion/segments/<name>.json).
class SegmentCard {
    name: string,
    roles: map<string, ShotList>,
    together: string[],
}

test "the guest-entrance segment is sound on the studio set" {
    let studio = StandingSet.load("studio");
    let segment = baml.json.decode<SegmentCard>(baml.fs.read("motion/segments/guest-entrance.json"));
    assert.equal(segment.roles.keys(), ["guest", "host"]);
    for (let role in segment.roles.keys()) {
        let shot = segment.roles.get(role) ?? throw "a key without a value";
        // (A template's prompts are filled in from its sentences when a take is made.)
        let problems = shot_problems(shot, stage = studio).filter((problem) -> {
            !problem.includes("the prompt should start")
        });
        assert.equal(problems, []);
        assert.equal(
            shot.beats.map((b) -> {
                b.source
            }),
            ["poses", "text", "poses", "text", "poses"],
        );
    }
    // The handshake is done together: both roles reach it on the same frame.
    let before = segment.roles.values().map((shot) -> {
        shot.beats.slice(0, 2).reduce(
            (total, b) -> {
                total + beat_frames(b)
            },
            0,
        )
    });
    assert.equal(before, [175, 175])
}

test "a take names its set, its segment and who plays whom" {
    let brief = baml.json.decode<ShotBrief>(baml.fs.read(`${SHOT_PLANS}/studio-guest-entrance.json`));
    assert.equal(brief.segment, "guest-entrance");
    assert.equal(brief.roles?.get("guest"), "roosevelt-wrestler-1890s");
    assert.equal(standing_set_of(brief)?.cameras.keys().length(), 3)
}

test "a backdrop is asked for as one wide painted picture" {
    let asked = set_backdrop_request("A city skyline at dusk in steel blue and cream.");
    assert.contains(asked, "exactly one landscape image");
    assert.contains(asked, "A city skyline at dusk");
    // A backdrop.txt that already holds the whole request is sent as it is.
    let whole = baml.fs.read("sets/studio/backdrop.txt");
    assert.equal(set_backdrop_request(whole), whole)
}
