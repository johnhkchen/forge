// A character's expression sheet: Codex draws the same head eight times, in
// our comic style, each with a different face. A comic panel then swaps the
// face and keeps the body and pose (scripts/comic/face_fit.py cuts the sheet
// and measures where each face sits; face_swap.py in the tidy-mesh skill puts
// one on the head).
//
// Codex is shown two pictures: the character's head sheet (who this is), and
// the character's own 3D head drawn from the front in the comic style (how it
// should look, and the exact shape, size and place to keep, so the drawn face
// sits on the 3D head). One image per character.
//
//   baml run expression_sheet -- --who lincoln
//
// Before it: `face_fit.py head <who>` (makes comics/cast/<who>/head.png).
// After it:  `face_fit.py cut <who>`. `just expressions <who>` does all three.

const CAST_FILE = "comics/cast.json";
const CAST_DIR = "comics/cast";
// The order of the cells, left to right, top row first. scripts/comic/kit.py holds the same list.
const EXPRESSIONS: string[] = ["neutral", "happy", "angry", "surprised", "sad", "smug", "talking", "shouting"];
const SHEET_COLUMNS = 4;
const SHEET_ROWS = 2;

class FaceHow {
    kind: "whole" | "eyes",
    region: float[],
}

class CastMember {
    name: string,
    run: string,
    version: string,
    about: string,
    face: FaceHow?,
}

class CastFile {
    cast: map<string, CastMember>,
}

/// How each expression should read on a face, or on eyes alone.
function expression_notes(masked: bool) -> string {
    if (masked) {
        `
            The mouth is hidden, so every expression is told by the eyes, the
            eyelids and the eyebrows alone, pushed far enough to read at a
            glance:
              neutral: level brows, calm eyes.
              happy: eyes curved into smiling arcs, brows lifted.
              angry: brows slammed down in a V, eyes narrowed.
              surprised: eyes wide and round with small pupils, brows high.
              sad: inner brow ends tilted up, eyelids drooping.
              smug: one brow raised, eyes half-lidded, looking sideways.
              talking: like neutral, brows a little lifted, eyes on the camera.
              shouting: eyes wide, brows down hard.
        `
    } else {
        `
            Push each expression far enough to read at a glance:
              neutral: mouth closed and relaxed.
              happy: a big open smile, eyes crinkled.
              angry: brows down in a V, teeth clenched.
              surprised: eyes wide, brows high, mouth a small round O.
              sad: inner brow ends tilted up, mouth turned down.
              smug: one brow raised, eyes half-lidded, a one-sided smirk.
              talking: mouth half open mid-word, friendly.
              shouting: mouth wide open, brows down.
        `
    }
}

function expression_sheet_request(member: CastMember) -> string {
    let masked = (member.face?.kind ?? "whole") == "eyes";
    let rows = `Row 1, left to right: ${EXPRESSIONS.slice(0, SHEET_COLUMNS).join(", ")}. Row 2, left to right: ${EXPRESSIONS.slice(SHEET_COLUMNS, EXPRESSIONS.length()).join(", ")}.`;
    `
        Use your built-in image_gen tool to generate exactly one image, using
        the two attached pictures, then reply with the single word: done. Do
        not run shell commands and do not edit files.

        The attached pictures:
          1. A head sheet of the character: this is who it is. Use its front
             view for the likeness.
          2. The same character's head as our comic draws it, from a 3D
             model, seen from the front. This is the look to draw in (flat
             colors, a few flat tones, an even black ink line), the colors
             to use, and the exact shape, size and position of the head and
             of everything on it.

        Image: an expression sheet for a webcomic. One landscape image, a
        grid of ${SHEET_COLUMNS} columns and ${SHEET_ROWS} rows:
        ${SHEET_COLUMNS * SHEET_ROWS} equal cells. Every cell holds the SAME
        head as picture 2: seen exactly from the front, level, the same size
        and in the same place in its cell, filling about 75% of the cell's
        height, with clear empty background all around it. The head only:
        cut it off level just under the chin, with no neck and no shoulders.
        Only the expression changes from cell to cell. ${rows}

        ${expression_notes(masked)}

        Draw it like a clean webcomic: flat colors with at most three flat
        tones each, no gradients, no texture, no photographic detail; a
        bold, even, black ink outline around the head and every feature;
        simple shapes for the eyes, brows and mouth. Keep the hair,
        skin color, and everything worn on the head or face exactly as in
        picture 2, in the same place in every cell. The same plain, flat
        light-gray background in every cell. No cell borders, no lines
        between cells, no text, no labels, no numbers.

        The character: ${member.about}
    `
}

/// The run folder whose name ends with -<ending>, the newest if there are several.
function run_ending(runs: string, ending: string) -> string {
    let folders = baml.fs.read_dir(runs)
        .filter((f) -> {
            f.is_dir && f.name.ends_with(`-${ending}`)
        })
        .map((f) -> {
            f.name
        })
        .sort_by_key((n) -> {
            n
        });
    let newest = folders.at(folders.length() - 1)
        ?? throw ComicFailed {
        step: "expressions",
        reason: `no run ending in -${ending} under ${runs}`,
    };
    `${runs}/${newest}`
}

/// Has Codex draw one cast member's expression sheet; returns the file
/// (comics/cast/<who>/sheet.png). Costs one Codex image.
function expression_sheet(who: string, runs: string = RUNS_DIR) -> string {
    let file = baml.json.decode<CastFile>(baml.fs.read(CAST_FILE));
    let member = file.cast.get(who)
        ?? throw ComicFailed { step: "expressions", reason: `nobody called "${who}" in ${CAST_FILE}` };
    let here = baml.sys.current_dir();
    let ours = `${here}/${CAST_DIR}/${who}/head.png`;
    if (!baml.fs.exists(ours)) {
        throw ComicFailed { step: "expressions", reason: `no ${ours}: run face_fit.py head ${who} first` }
    }
    let run = run_ending(runs, member.run);
    let absolute_run = if (run.starts_with("/")) {
        run
    } else {
        `${here}/${run}`
    };
    let head_sheet = `${absolute_run}/${HEAD_SHEET}`;
    let likeness = if (baml.fs.exists(head_sheet)) {
        head_sheet
    } else {
        `${absolute_run}/image.png`
    };
    let drawn = codex_drawn(expression_sheet_request(member), `${CAST_DIR}/${who}`, [likeness, ours]);
    let target = `${CAST_DIR}/${who}/sheet.png`;
    baml.fs.write_bytes(target, baml.fs.open(drawn, "r").bytes());
    target
}

test "an expression sheet asks for eight cells of the same head, in order" {
    let lincoln = CastMember {
        name: "Lincoln",
        run: "young-lincoln-frontier-wrestler",
        version: "midpoly",
        about: "young Lincoln, a lanky wrestler",
        face: FaceHow { kind: "whole", region: [0.2, 0.4, 0.8, 0.95] },
    };
    let asked = expression_sheet_request(lincoln);
    assert.is_true(asked.includes("4 columns and 2 rows"));
    assert.is_true(asked.includes("8 equal cells"));
    assert.is_true(asked.includes("Row 1, left to right: neutral, happy, angry, surprised."));
    assert.is_true(asked.includes("Row 2, left to right: sad, smug, talking, shouting."));
    assert.is_true(asked.includes("two attached pictures"));
    assert.is_true(asked.includes("a big open smile"));
    assert.is_true(asked.includes("young Lincoln, a lanky wrestler"))
}

test "a masked face is asked for with eyes and brows only" {
    let ninja = CastMember {
        name: "Ninja",
        run: "shadow-ninja",
        version: "midpoly",
        about: "a ninja in a mask",
        face: FaceHow { kind: "eyes", region: [0.1, 0.46, 0.9, 0.7] },
    };
    let asked = expression_sheet_request(ninja);
    assert.is_true(asked.includes("The mouth is hidden"));
    assert.is_true(!asked.includes("a big open smile"))
}

test "the cast file reads, with the keys this step does not use left alone" {
    let file = baml.json.decode<CastFile>(
        `{"about": "who", "cast": {"ninja": {"name": "Ninja", "run": "shadow-ninja", "version": "midpoly", "about": "a ninja", "face": {"kind": "eyes", "region": [0.1, 0.4, 0.9, 0.7]}, "clips": {"hero": {"shot": "hero-rooftop"}}}, "troll": {"name": "Troll", "run": "cave-troll", "version": "lowpoly", "about": "a troll", "clips": {}}}}`,
    );
    assert.equal(file.cast.get("ninja")?.face?.kind, "eyes");
    assert.equal(file.cast.get("troll")?.face, null)
}
