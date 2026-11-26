// Casting: the paid steps of finding a new member of the cast (scripts/casting
// has the free ones, the files and the page).
//
//   casting_headshots   Codex pictures for each look in casting/<role>/role.json
//                       that has none: `variations` of each, each a different
//                       design of the same brief (optionally Opus writes more
//                       looks first)
//   casting_mesh_screen the few headshots the screen test ranks highest, each
//                       built by TRELLIS.2 alone (no Claude, no rig, no motion),
//                       so their 3D can be looked at before a take is paid for;
//                       a take of one of them starts from that mesh
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
const SCREEN_SCRIPT = "scripts/casting/screen.py";
const HEADSHOT_PX = 1024;

// How many Codex pictures are drawn at once. Each is its own codex thread.
const DRAWING_AT_ONCE = 3;

/// List prices, US dollars a million tokens: what an answer would cost on the
/// API. The calls here go through the logged-in Claude Code CLI (clients.baml),
/// so they spend plan time, not a bill; this says what they come to all the same.
class TokenPrices {
    model: string,
    fresh: float,
    cached: float,
    written: float,
    out: float,
}

const OPUS_PRICES = TokenPrices { model: "Opus", fresh: 4.0, cached: 0.2, written: 5.0, out: 20.0 };
const HAIKU_PRICES = TokenPrices { model: "Haiku", fresh: 0.1, cached: 0.01, written: 0.125, out: 0.5 };

/// The tokens of one answer, and what they come to at list price.
class TokenBill {
    prices: TokenPrices,
    fresh: int,
    cached: int,
    written: int,
    out: int,

    function of(usage: ai.events.ModelUsage[], prices: TokenPrices) -> TokenBill {
        usage.reduce(
            (sum, u) -> {
                TokenBill {
                    prices: prices,
                    fresh: sum.fresh + (u.usage.input_tokens ?? 0),
                    cached: sum.cached + (u.usage.cached_input_tokens ?? 0),
                    written: sum.written + (u.usage.cache_write_input_tokens ?? 0),
                    out: sum.out + (u.usage.output_tokens ?? 0),
                }
            },
            TokenBill { prices: prices, fresh: 0, cached: 0, written: 0, out: 0 },
        )
    }

    function usd(self) -> float {
        let p = self.prices;
        (self.fresh * p.fresh + self.cached * p.cached + self.written * p.written + self.out * p.out) / 1000000.0
    }

    implements baml.ToString {
        function to_string(self) -> string {
            let cents = (self.usd() * 1000.0 + 0.5).floor() / 10.0;
            `${self.fresh} tokens in, ${self.cached} read from cache, ${self.written} written to it, ${self.out} out: about ${cents} cents at ${self.prices.model} list price`
        }
    }
}

// What makes each picture of a look a different design. The first is the brief
// as written; the others ask for another design within the same rules.
const VARIATIONS: string[] = [
    "",
    "This is a second, different design for the same brief: change the shape of the head and the proportions of the body and limbs, and keep every colour, part and rule above.",
    "This is a third, different design for the same brief: chunkier and simpler, fewer and bigger shapes, fewer small details, and keep every colour, part and rule above.",
];

class CastingLook {
    id: string,
    name: string,
    suits: string?,
    brief: ObjectBrief,
    colourways: Colourway[]?,
}

/// One colour of a colourway: a name, its hex, and where it goes.
class Swatch {
    name: string,
    hex: string,
    where: string,
}

/// A headshot drawn again in other colours, nothing else changed. `of` is the
/// headshot it is drawn from ("clerk.2"), `headshot` its own ("clerk.2-lilac").
class Colourway {
    id: string,
    name: string,
    why: string,
    of: string,
    headshot: string,
    swatches: Swatch[],
}

class CanonOption {
    id: string,
    name: string,
    pitch: string,
}

class CastingRole {
    id: string,
    breakdown: map<string, json>,
    canon_options: CanonOption[],
    looks: CastingLook[],

    function load(role: string) -> CastingRole {
        baml.json.decode<CastingRole>(baml.fs.read(`${CASTING_DIR}/${role}/role.json`))
    }

    /// Picture `n` of a look as git keeps it: tin-toy.jpg is the first,
    /// tin-toy.2.jpg the second (a 1024-pixel JPEG; screen.py keep makes it).
    function headshot(self, look: string, n: int = 1) -> string {
        self.kept(shot_name(look, n))
    }

    /// A headshot by name ("clerk.2", "clerk.2-lilac") as git keeps it.
    function kept(self, shot: string) -> string {
        `${CASTING_DIR}/${self.id}/headshots/${shot}.jpg`
    }

    /// Codex's own full-size picture of a headshot, kept out of git.
    function full(self, shot: string) -> string {
        `${CASTING_DIR}/${self.id}/headshots/full/${shot}.png`
    }

    /// The best picture there is of a headshot, for TRELLIS or Codex to work
    /// from: Codex's own if it is on this Mac, else the kept JPEG.
    function picture(self, shot: string) -> string {
        if (baml.fs.exists(self.full(shot))) { self.full(shot) } else { self.kept(shot) }
    }

    /// A headshot's look, and its colourway when it is one ("clerk.2-lilac").
    function shot(self, shot: string) -> (CastingLook, Colourway?) throws CastingFailed {
        let look_id = shot.split(".").at(0) ?? shot;
        let look = self.looks.find((l) -> { l.id == look_id })
            ?? throw CastingFailed { step: "headshot", reason: `no look ${look_id} in the role` };
        let way = (look.colourways ?? []).find((w) -> { w.headshot == shot });
        (look, way)
    }

    function drawn(self, shot: string) -> bool {
        baml.fs.exists(self.full(shot)) || baml.fs.exists(self.kept(shot))
    }

    /// The breakdown as the model reads it: its fields as JSON.
    function words(self) -> string {
        baml.json.stringify(self.breakdown, indent = 2)
    }

    /// The ways the part could arrive, as the model reads them.
    function arrivals(self) -> string {
        self.canon_options.map((o) -> { `- ${o.id}: ${o.name}. ${o.pitch}` }).join("\n")
    }

    /// The ways it could arrive that no look written so far suits.
    function unsuited(self) -> string[] {
        self.canon_options
            .filter((o) -> { !self.looks.some((l) -> { l.suits == o.id }) })
            .map((o) -> { o.id })
    }
}

/// A headshot's name: the look's id for its first picture, "<look>.<n>" after.
function shot_name(look: string, n: int) -> string {
    if (n > 1) { `${look}.${n}` } else { look }
}

/// Codex's PNGs into headshots/full/, a JPEG of each beside them for git.
function keep_headshots(role: string) -> void {
    let out = baml.sys.run(
        "uv",
        args = ["run", "--no-project", "--python", "3.12", "--with", "pillow", "--with", "numpy", "--with", "scipy", "python", SCREEN_SCRIPT, "keep", role],
        capture_output = true,
    );
    if (!out.ok()) {
        throw CastingFailed { step: "keep", reason: string.from_utf8(out.stderr) }
    }
}

/// The picture request for picture `n` of a look.
function variation_request(brief: ObjectBrief, n: int) -> string {
    let nudge = VARIATIONS.at(n - 1)
        ?? "This is another, different design for the same brief: keep every colour, part and rule above.";
    if (!nudge) {
        return picture_request(brief);
    }
    `
        ${picture_request(brief)}

        ${nudge}
    `
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
    variation: int?,
    colourway: string?,
    screen_run: string?,
    takes: CastingTake[],
    notes: CastingNote[],

    function load(role: string, candidate: string) -> CastingCandidate {
        baml.json.decode<CastingCandidate>(
            baml.fs.read(`${CASTING_DIR}/${role}/candidates/${candidate}/candidate.json`),
        )
    }

    /// The headshot it was shortlisted from: "clerk", "clerk.2", "clerk.2-lilac".
    function shot(self, look: string) -> string {
        let base = shot_name(look, self.variation ?? 1);
        if let w: string = self.colourway {
            let numbered = if (base == look) { `${look}.1` } else { base };
            return `${numbered}-${w}`;
        }
        base
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

/// One headshot to draw: picture `n` of a look (0 for a colourway), the file Codex
/// writes, what it is asked, and the pictures it is shown.
class Sitting {
    look: CastingLook,
    n: int,
    file: string,
    request: string,
    shown: string[],
}

/// Opus writes `count` more looks and they are kept in role.json; logs what it cost.
function more_looks(part: CastingRole, count: int) -> void {
    let have = part.looks.map((l) -> { l.name });
    let result = ai.Agent.new(client = CastingWriter).run(
        CastingLooks@spec(part.words(), have, part.arrivals(), part.unsuited(), count),
    );
    let bill = TokenBill.of(result.usage, OPUS_PRICES);
    log.info(`looks: Opus wrote ${result.value.looks.length()} looks; ${bill} (as the CLI passed them on: its own cost_usd line above is the figure to go by)`);
    for (let idea in result.value.looks) {
        casting_record(["add-look", role_id(part), baml.json.stringify(idea)]);
    }
}

function role_id(part: CastingRole) -> string {
    part.id
}

/// Codex pictures for every look that has fewer than `variations`; returns the
/// headshots drawn. `more` asks Opus for that many more looks first, and keeps
/// them in role.json. Up to DRAWING_AT_ONCE pictures are drawn at a time; one
/// Codex refusal does not stop the others (it is logged, and drawn next time).
function casting_headshots(role: string, more: int = 0, variations: int = 1) -> string[] {
    let part = CastingRole.load(role);
    if (more > 0) {
        //# Opus writes more looks (one short answer)
        more_looks(part, more);
        part = CastingRole.load(role);
    }
    baml.fs.mkdir(`${CASTING_DIR}/${role}/headshots/full`, baml.fs.MkdirOptions { recursive: true });
    //# Codex draws each picture of each look that is not there yet, a few at a time
    let wanted = part.looks
        .flat_map((l) -> {
            baml.Array.generate(variations, (i) -> {
                Sitting { look: l, n: i + 1, file: part.full(shot_name(l.id, i + 1)), request: variation_request(l.brief, i + 1), shown: [] }
            })
        })
        .filter((s) -> { !part.drawn(shot_name(s.look.id, s.n)) });
    log.info(`headshots: ${wanted.length()} to draw`);
    draw_all(role, wanted)
}

/// Every sitting drawn by Codex, DRAWING_AT_ONCE at a time; one refusal does not
/// stop the others (it is logged, and drawn next time). Then each is kept as
/// git keeps headshots. Returns the pictures drawn.
function draw_all(role: string, wanted: Sitting[]) -> string[] {
    let gate = baml.sync.Semaphore.new(DRAWING_AT_ONCE);
    let drawing = wanted.map((s) -> {
        spawn with gate {
            log.info(`headshots: codex is drawing ${s.look.name}, ${s.file}`);
            codex_picture(`${CASTING_DIR}/${role}`, s.request, s.shown, s.file) catch (e) {
                PictureFailed => {
                    log.warn(`headshots: ${s.file}: ${e}`);
                    ""
                },
            }
        }
    });
    let drawn = (await baml.future.all(drawing)).filter((f) -> { f != "" });
    keep_headshots(role);
    drawn
}

/// The request for a headshot drawn again in a colourway: the headshot is
/// attached, and only its colours change.
function colourway_request(way: Colourway) -> string {
    let colours = way.swatches.map((s) -> { `- ${s.name} (${s.hex}): ${s.where}` }).join("\n");
    `
        Use your built-in image_gen tool to make exactly one new square image from
        the attached picture, then reply with the single word: done. Do not run
        shell commands and do not edit files.

        The attached picture is a character model sheet. Draw the same picture
        again: the same character with the same shapes, parts and proportions, the
        same T-pose, the same camera, framing and size in the frame, the same plain
        light-grey background and soft even light. Change only its colours, to
        these matte painted enamels:
        ${colours}

        Keep the face plate dark and the two round lamp eyes light. Matte paint
        everywhere: no chrome, no glass, nothing that glows, no shine, no text or
        numbers, nothing held, no shadow on the ground.
    `
}

/// Every colourway written in role.json that has no picture yet, drawn by Codex
/// from the headshot it belongs to (attached), its colours changed and nothing
/// else. Returns the pictures drawn.
function casting_colourways(role: string) -> string[] {
    let part = CastingRole.load(role);
    baml.fs.mkdir(`${CASTING_DIR}/${role}/headshots/full`, baml.fs.MkdirOptions { recursive: true });
    //# Each colourway not drawn yet, from its headshot
    let wanted = part.looks.flat_map((l) -> {
        (l.colourways ?? [])
            .filter((w) -> { !part.drawn(w.headshot) && part.drawn(w.of) })
            .map((w) -> {
                Sitting {
                    look: l,
                    n: 0,
                    file: part.full(w.headshot),
                    request: colourway_request(w),
                    shown: [`${baml.sys.current_dir()}/${part.picture(w.of)}`],
                }
            })
    });
    log.info(`colourways: ${wanted.length()} to draw`);
    draw_all(role, wanted)
}

/// The headshots named (`tin-toy`, `clerk.2`) each built by TRELLIS.2 alone, as
/// the first step of a take would build them: a run with its brief and picture
/// and mesh.glb, and nothing more. The free half (`casting.py screen-3d`) stands
/// each up and pictures it from all round. Returns the run folders.
function casting_mesh_screen(role: string, shots: string) -> string[] {
    let part = CastingRole.load(role);
    shots.split(",").map((s) -> { s.trim() }).filter((s) -> { s != "" }).map((shot) -> {
        let (let look, let way) = part.shot(shot);
        if (!part.drawn(shot)) {
            throw CastingFailed { step: "mesh screen", reason: `no headshot ${shot}` }
        }
        //# The headshot is the picture of a new run, as a take's would be
        let brief = brief_in(look.brief, way);
        let run = Run.start(brief.name);
        run.save("brief.json", brief);
        as_png(part.picture(shot), run.path("image.png"));
        //# TRELLIS.2 builds the mesh, and nothing else is paid for
        log.info(`mesh screen: TRELLIS.2 is building ${shot} in ${run.dir}`);
        sculpt(run);
        casting_record(["add-mesh", role, shot, run.dir]);
        run.dir
    })
}

/// A look's brief, in a colourway when there is one: its colours said in the
/// subject and the description, so Claude finishing it in Blender matches the
/// picture and not the colours the look was first written in.
function brief_in(brief: ObjectBrief, way: Colourway?) -> ObjectBrief {
    if let w: Colourway = way {
        let colours = w.swatches.map((s) -> { `${s.name} (${s.hex}) on the ${s.where}` }).join("; ");
        return ObjectBrief {
            ...brief,
            name: `${brief.name} ${w.name}`,
            description: `${brief.description} In the ${w.name} colourway: ${colours}.`,
            subject: `${brief.subject} Its colours, which replace any named above, all matte painted enamel: ${colours}.`,
        };
    }
    brief
}

/// A picture copied as a PNG: Codex's own as it is, a kept JPEG converted.
function as_png(source: string, target: string) -> void {
    if (source.ends_with(".png")) {
        baml.fs.write_bytes(target, baml.fs.open(source, "r").bytes());
        return;
    }
    let out = baml.sys.run(
        "uv",
        args = ["run", "--no-project", "--python", "3.12", "--with", "pillow", "--with", "numpy", "--with", "scipy", "python", SCREEN_SCRIPT, "png", source, target],
        capture_output = true,
    );
    if (!out.ok()) {
        throw CastingFailed { step: "png", reason: string.from_utf8(out.stderr) }
    }
}

/// One headshot as the screen test lists it (casting/<role>/screen.json).
class ScreenedShot {
    id: string,
    look_small: string?,
}

class ScreenFile {
    shots: ScreenedShot[],
}

/// What Haiku saw, kept for screen.py to fold into the scores.
class VisionRecord {
    made: string,
    model: string,
    shown: int,
    tokens: string,
    usd: float,
    shots: map<string, SeenShot>,
}

/// The breakdown's must-nots checked by eye, cheaply: Haiku is shown every
/// headshot the screen test listed, small (its look_small picture, 384 pixels),
/// in one ask, and says which rules each breaks. Writes
/// casting/<role>/screen-vision.json, with the tokens and what they come to.
function casting_vision(role: string) -> string {
    let part = CastingRole.load(role);
    let screened = baml.json.decode<ScreenFile>(baml.fs.read(`${CASTING_DIR}/${role}/screen.json`));
    let shown = screened.shots.filter((s) -> { s.look_small != null });
    let pictures = shown.map((s) -> { baml.media.Image.from_file(s.look_small ?? "", "image/jpeg") });
    let rules = (key: string) -> string[] {
        baml.json.to<string[]>(part.breakdown.get(key) ?? baml.json.from([]))
    };
    //# Haiku looks at every headshot at once
    let result = ai.Agent.new(client = Looker).run(
        ScreenMustNots@spec(rules("must_not"), rules("must_have"), shown.map((s) -> { s.id }), pictures),
    );
    let bill = TokenBill.of(result.usage, HAIKU_PRICES);
    log.info(`vision: Haiku looked at ${shown.length()} headshots; ${bill} (as the CLI passed them on: its own cost_usd line above is the figure to go by)`);
    let seen: map<string, SeenShot> = {};
    for (let s in result.value.shots) {
        seen.set(s.id, s);
    }
    let path = `${CASTING_DIR}/${role}/screen-vision.json`;
    baml.fs.write(
        path,
        baml.json.stringify(
            VisionRecord {
                made: `${baml.time.Instant.now().to_string().slice(0, 16).replace("T", " ")} UTC`,
                model: "Haiku, through the Claude Code CLI",
                shown: shown.length(),
                tokens: bill.to_string(),
                usd: bill.usd(),
                shots: seen,
            },
            indent = 2,
        ),
    );
    path
}

/// A shortlisted headshot built into a character; returns the run folder. When
/// the mesh screen already built its mesh, the take carries on from that run.
function casting_take(role: string, candidate: string) -> string {
    let part = CastingRole.load(role);
    let who = CastingCandidate.load(role, candidate);
    let look_id = who.look ?? throw CastingFailed { step: "take", reason: "a stand-in has no look to build" };
    let look = part.looks.find((l) -> { l.id == look_id })
        ?? throw CastingFailed { step: "take", reason: `no look ${look_id} in the role` };
    let shot = who.shot(look_id);
    let (let _, let way) = part.shot(shot);
    if (!part.drawn(shot)) {
        throw CastingFailed { step: "take", reason: "draw its headshot first" }
    }
    let brief = brief_in(look.brief, way);
    //# The headshot is the picture: a run starts from its brief and picture (or the mesh screen's run)
    let screened = who.screen_run;
    let run = if (screened && baml.fs.exists(`${RUNS_DIR}/${screened}/mesh.glb`)) {
        Run.open(`${RUNS_DIR}/${screened}`)
    } else {
        let fresh = Run.start(brief.name);
        fresh.save("brief.json", brief);
        as_png(part.picture(shot), fresh.path("image.png"));
        fresh
    };
    log.info(`casting: building ${look.name} in ${run.dir}`);
    //# The make pipeline from step 2 on: mesh, Claude in Blender, profiles, walk, run
    finish(run, brief);
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
    assert.equal(part.headshot("tin-toy"), "casting/robot/headshots/tin-toy.jpg");
    assert.equal(part.full("tin-toy"), "casting/robot/headshots/full/tin-toy.png");
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

test "a look's second and third pictures have files of their own, and ask for another design" {
    let part = CastingRole.load("robot");
    assert.equal(part.headshot("clerk", n = 2), "casting/robot/headshots/clerk.2.jpg");
    let brief = part.looks.at(0)?.brief ?? throw "no look";
    assert.equal(variation_request(brief, 1), picture_request(brief));
    assert.contains(variation_request(brief, 2), "second, different design");
    assert.contains(variation_request(brief, 3), "chunkier and simpler");
    assert.contains(variation_request(brief, 5), "another, different design")
}

test "the ways it could arrive that no look suits are the ones asked for" {
    let part = CastingRole.load("robot");
    assert.is_true(part.canon_options.some((o) -> { o.id == "crew" }));
    let suited = part.looks.some((l) -> { l.suits == "crew" });
    assert.equal(part.unsuited().includes("crew"), !suited);
    assert.contains(part.arrivals(), "- crew: The ninja's crew.")
}

test "CastingLooks parses looks with why and what they suit" {
    let part = CastingRole.load("robot");
    let reply = `
        {"looks": [{"brief": {"name": "Stagehand Robot", "description": "A small stagehand robot.", "subject": "A robot in a T-pose.",
          "materials": [{"part": "body", "look": "matte mustard enamel", "metallic": false}], "size_m": 1.45, "character": true},
          "why": "For the crew option: a stagehand.", "suits": "crew"}]}
    `;
    let spec = CastingLooks@spec(part.words(), ["Tin toy"], part.arrivals(), ["crew"], 1);
    assert.equal(spec.parse(reply).looks.at(0)?.suits, "crew");
    assert.contains(spec.prompt().to_string(), "crew")
}

test "a colourway is found by its headshot, asks only for its colours, and its brief says them" {
    let part = CastingRole.load("robot");
    let (let look, let way) = part.shot("clerk.2-lilac");
    assert.equal(look.id, "clerk");
    let w = way ?? throw "no lilac colourway";
    assert.equal(w.of, "clerk.2");
    let request = colourway_request(w);
    assert.contains(request, "Change only its colours");
    assert.contains(request, "#A88BD1");
    assert.contains(brief_in(look.brief, w).subject, "lilac enamel (#A88BD1)");
    let (let plain, let none) = part.shot("clerk.2");
    assert.equal(brief_in(plain.brief, none).name, plain.brief.name);
    let who = CastingCandidate { look: "clerk", variation: 2, colourway: "lilac", takes: [], notes: [] };
    assert.equal(who.shot("clerk"), "clerk.2-lilac")
}
