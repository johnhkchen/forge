// Casting: the paid steps of finding a new member of the cast (scripts/casting
// has the free ones, the files and the page).
//
//   casting_headshots   a Codex picture for each look in casting/<role>/role.json
//                       that has none (optionally Opus writes more looks first)
//   casting_take        a shortlisted headshot becomes a run: its brief and its
//                       picture go into a new runs/ folder and `finish` builds it,
//                       as `just resume` would (mesh, Claude in Blender, profiles,
//                       walk, run)
//   casting_revise      the open notes about the look rewrite the brief (Opus),
//                       Codex draws it again from the last take's picture, and it
//                       is built as a new take
//
// Each records what it made through scripts/casting/casting.py, which owns the
// casting files. None of them is run by the gallery; `just casting-*` runs one
// only when told `go` (and prints what it would cost first).

const CASTING_DIR = "casting";
const CASTING_SCRIPT = "scripts/casting/casting.py";
const HEADSHOT_PX = 1024;

class CastingLook {
    id: string,
    name: string,
    brief: ObjectBrief,
}

class CastingRole {
    id: string,
    breakdown: map<string, json>,
    looks: CastingLook[],

    function load(role: string) -> CastingRole {
        baml.json.decode<CastingRole>(baml.fs.read(`${CASTING_DIR}/${role}/role.json`))
    }

    function headshot(self, look: string) -> string {
        `${CASTING_DIR}/${self.id}/headshots/${look}.png`
    }

    /// The breakdown as the model reads it: its fields as JSON.
    function words(self) -> string {
        baml.json.stringify(self.breakdown, indent = 2)
    }
}

class CastingNote {
    id: int,
    about: string,
    text: string,
    answered_by: int?,
}

class CastingTake {
    n: int,
    run: string,
}

class CastingCandidate {
    look: string?,
    takes: CastingTake[],
    notes: CastingNote[],

    function load(role: string, candidate: string) -> CastingCandidate {
        baml.json.decode<CastingCandidate>(
            baml.fs.read(`${CASTING_DIR}/${role}/candidates/${candidate}/candidate.json`),
        )
    }

    /// Notes no take has answered yet that are about how it looks (the paid kind).
    function open_look_notes(self) -> CastingNote[] {
        self.notes.filter((n) -> {
            n.about == "look" && n.answered_by == null
        })
    }
}

class CastingFailed {
    step: string,
    reason: string,

    implements baml.ToString {
        function to_string(self) -> string {
            `casting ${self.step}: ${self.reason}`
        }
    }
}

/// Hands what a step made to scripts/casting/casting.py (which writes the casting files).
function casting_record(args: string[]) -> void {
    let out = baml.sys.run("python3", args = [CASTING_SCRIPT].concat(args), capture_output = true);
    if (!out.ok()) {
        throw CastingFailed { step: args.at(0) ?? "record", reason: string.from_utf8(out.stderr) }
    }
}

/// A Codex picture for every look that has none; returns the headshots drawn.
/// `more` asks Opus for that many more looks first, and keeps them in role.json.
function casting_headshots(role: string, more: int = 0) -> string[] {
    let part = CastingRole.load(role);
    if (more > 0) {
        //# Opus writes more looks (one short answer)
        let have = part.looks.map((l) -> { l.name });
        let briefs = CastingLooks(part.words(), have, more);
        for (let brief in briefs) {
            casting_record(["add-look", role, baml.json.stringify(brief)]);
        }
        part = CastingRole.load(role);
    }
    baml.fs.mkdir(`${CASTING_DIR}/${role}/headshots`, baml.fs.MkdirOptions { recursive: true });
    //# Codex draws each look that has no picture yet
    part.looks
        .filter((l) -> { !baml.fs.exists(part.headshot(l.id)) })
        .map((l) -> {
            log.info(`headshots: codex is drawing ${l.name}`);
            codex_picture(`${CASTING_DIR}/${role}`, picture_request(l.brief), [], part.headshot(l.id))
        })
}

/// A shortlisted headshot built into a character; returns the run folder.
function casting_take(role: string, candidate: string) -> string {
    let part = CastingRole.load(role);
    let who = CastingCandidate.load(role, candidate);
    let look_id = who.look ?? throw CastingFailed { step: "take", reason: "a stand-in has no look to build" };
    let look = part.looks.find((l) -> { l.id == look_id })
        ?? throw CastingFailed { step: "take", reason: `no look ${look_id} in the role` };
    if (!baml.fs.exists(part.headshot(look_id))) {
        throw CastingFailed { step: "take", reason: "draw its headshot first" }
    }
    //# The headshot is the picture: a run starts from its brief and picture
    let run = Run.start(look.brief.name);
    run.save("brief.json", look.brief);
    baml.fs.write_bytes(run.path("image.png"), baml.fs.open(part.headshot(look_id), "r").bytes());
    log.info(`casting: building ${look.name} in ${run.dir}`);
    //# The make pipeline from step 2 on: mesh, Claude in Blender, profiles, walk, run
    finish(run, look.brief);
    casting_record(["add-take", role, candidate, run.dir]);
    run.dir
}

/// The picture request for a revised take: the last take's picture is shown,
/// and only what the notes ask changes.
function revision_picture_request(brief: ObjectBrief, notes: CastingNote[]) -> string {
    let changes = notes.map((n) -> { `- ${n.text}` }).join("\n");
    `
        ${picture_request(brief)}

        The attached picture is this same character as it was last time. Keep
        everything about it except what these notes ask to change:
        ${changes}
    `
}

/// The open notes about the look answered by a new take; returns its run folder.
function casting_revise(role: string, candidate: string) -> string {
    let part = CastingRole.load(role);
    let who = CastingCandidate.load(role, candidate);
    if (who.look == null) {
        throw CastingFailed { step: "revise", reason: "a stand-in is already in the cast and is not rebuilt" }
    }
    let notes = who.open_look_notes();
    if (!notes) {
        throw CastingFailed { step: "revise", reason: "no open notes about the look: notes on moves or cards are free (just casting-tape)" }
    }
    let last = who.takes.at(who.takes.length() - 1) ?? throw CastingFailed { step: "revise", reason: "no take to revise yet" };
    let before = Run.open(`${RUNS_DIR}/${last.run}`);
    //# Opus rewrites the brief to answer the notes
    let brief = Revise(
        before.load<ObjectBrief>("brief.json"),
        part.words(),
        notes.map((n) -> { n.text }),
    );
    let run = Run.start(brief.name);
    run.save("brief.json", brief);
    //# Codex draws it again from the last take's picture
    codex_picture(run.dir, revision_picture_request(brief, notes), [before.absolute("image.png")], run.path("image.png"));
    //# Built as any run is
    finish(run, brief);
    let answered = notes.map((n) -> { `${n.id}` }).join(",");
    casting_record(["add-take", role, candidate, run.dir, "--answers", answered]);
    run.dir
}

test "a role's looks and a candidate's open notes read from their files" {
    let part = CastingRole.load("robot");
    assert.equal(part.looks.at(0)?.id, "tin-toy");
    assert.equal(part.headshot("tin-toy"), "casting/robot/headshots/tin-toy.png");
    assert.is_true(part.looks.every((l) -> { l.brief.character ?? false }));
    let who = CastingCandidate {
        look: "tin-toy",
        takes: [CastingTake { n: 1, run: "2026-01-01T00-00-00-tin-toy-robot" }],
        notes: [
            CastingNote { id: 1, about: "look", text: "Try it bigger.", answered_by: null },
            CastingNote { id: 2, about: "cards", text: "The knees blot.", answered_by: null },
            CastingNote { id: 3, about: "look", text: "Warmer eyes.", answered_by: 2 },
        ],
    };
    assert.equal(who.open_look_notes().map((n) -> { n.id }), [1])
}

test "a revised picture keeps the character and names only the notes" {
    let part = CastingRole.load("robot");
    let notes = [CastingNote { id: 1, about: "look", text: "Make the head a little smaller.", answered_by: null }];
    let request = revision_picture_request(part.looks.at(0)?.brief ?? throw "no look", notes);
    assert.contains(request, "T-pose");
    assert.contains(request, "- Make the head a little smaller.")
}

test "Revise parses a revised brief" {
    let reply = `
        {"name": "Tin Toy Robot", "description": "A smaller-headed toy robot.", "subject": "A toy robot in a T-pose.",
         "materials": [{"part": "body", "look": "matte mustard enamel", "metallic": false}], "size_m": 1.45, "character": true}
    `;
    let part = CastingRole.load("robot");
    let brief = Revise@spec(part.looks.at(0)?.brief ?? throw "no look", part.words(), ["Smaller head."]).parse(reply);
    assert.equal(brief.name, "Tin Toy Robot");
    assert.approx_equal(brief.size_m, 1.45, 0.001)
}
