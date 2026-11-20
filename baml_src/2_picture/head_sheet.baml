// Step 2b, characters only: Codex draws the head again, large, from three sides.
//
// The picture for TRELLIS.2 shows the whole figure, so the face is small in
// it: about a tenth of the picture's height. TRELLIS.2 gets the head's shape
// about right from that and its texture wrong: eyes come out as dark
// smudges, lips as a blur, glasses as black blobs. So Codex is shown the
// picture and asked for a turnaround sheet of the same head: front,
// three-quarter and side, side by side, each several times larger than the
// face was. It is saved as heads/sheet.png.
//
// The profile runner lays the sheet's front view over the front of the
// detailed head before it bakes any version (face_paint.py in the tidy-mesh
// skill), and Claude has all three views to look at when it blocks the head
// out. Nothing waits on it: without a sheet the runner uses image.png, and a
// sheet that doesn't sit on the mesh's head is passed over the same way.

const HEAD_SHEET = "heads/sheet.png";

const HEAD_SHEET_RULES = `
    A head turnaround sheet of the character in the attached picture, for a
    3D modeler. One landscape image holding THREE views of the SAME head,
    side by side, left to right, each in its own equal third of the image:

      1. FRONT: facing the camera exactly straight on, level, eyes open and
         looking at the camera, mouth relaxed and closed.
      2. THREE-QUARTER: the head turned 45 degrees to its left.
      3. SIDE: a true profile, the head turned 90 degrees, nose pointing to
         the left edge of the image.

    Each view shows the whole head and neck down to the collarbone, the same
    size in all three, eyes on the same horizontal line across the sheet,
    the head filling about 80% of the image's height. Keep exactly this
    character: the same face, proportions, skin, hair, and everything worn
    on the head or face in the attached picture, in the same colors and the
    same rendering style. Flat orthographic look with no perspective
    distortion. Soft, even lighting from the front with no cast shadows. The
    same plain, solid light-gray background as the attached picture, with
    clear empty background between the three views. No text, no labels, no
    lines, no borders, no hands, nothing else.
`;

/// What the head wears, from the brief's gear list: "tricorn hat, eye patch".
/// The picture shows it too; naming it keeps Codex from tidying it away.
function head_gear(brief: ObjectBrief) -> string {
    (brief.gear ?? [])
        .filter((g) -> {
            g.kind != "held" && (g.slot == "head" || g.slot == "face" || g.slot == "neck")
        })
        .map((g) -> {
            g.name
        })
        .join(", ")
}

function head_sheet_request(brief: ObjectBrief) -> string {
    let worn = head_gear(brief);
    let keep = if (worn.is_empty()) {
        ""
    } else {
        `On the head and face, keep: ${worn}.`
    };
    `
        Use your built-in image_gen tool to generate exactly one image, using
        the attached picture as the input image, then reply with the single
        word: done. Do not run shell commands and do not edit files.

        Image: ${HEAD_SHEET_RULES}

        The character: ${brief.subject}
        ${keep}
    `
}

/// Only a character has a face to draw again.
function wants_head_sheet(brief: ObjectBrief) -> bool {
    brief.character ?? false
}

/// Draws the character's head from three sides, working from image.png, and
/// saves it as heads/sheet.png in the run folder.
function head_sheet(brief: ObjectBrief, run: Run) -> string {
    let drawn = codex_draws(head_sheet_request(brief), run.dir, from = run.absolute("image.png"));
    baml.fs.mkdir(run.path("heads"), baml.fs.MkdirOptions { recursive: true });
    let target = run.path(HEAD_SHEET);
    baml.fs.write_bytes(target, baml.fs.open(drawn, "r").bytes());
    target
}

/// Only this step, for a run that has its picture: draws heads/sheet.png
/// (again, if it is there). The next `just tidy` paints the face from it.
///
///   baml run head_sheet_for -- --dir runs/<run>
function head_sheet_for(dir: string) -> string {
    let run = Run.open(dir);
    head_sheet(run.load<ObjectBrief>("brief.json"), run)
}

test "a head sheet asks for three views of the same head, and names what it wears" {
    let pirate = ObjectBrief {
        name: "Stocky Pirate Deckhand",
        description: "A stocky pirate.",
        subject: "A stocky pirate deckhand with a beard.",
        materials: [],
        size_m: 1.7,
        character: true,
        gear: [
            GearItem { name: "tricorn hat", kind: "attached", slot: "head", look: "black felt" },
            GearItem { name: "eye patch", kind: "worn", slot: "face", look: "black leather" },
            GearItem { name: "navy coat", kind: "worn", slot: "torso", look: "navy wool" },
            GearItem { name: "spyglass", kind: "held", slot: "hand_right", look: "brass" },
        ],
    };
    assert.equal(head_gear(pirate), "tricorn hat, eye patch");
    let asked = head_sheet_request(pirate);
    assert.is_true(asked.includes("FRONT"));
    assert.is_true(asked.includes("THREE-QUARTER"));
    assert.is_true(asked.includes("SIDE"));
    assert.is_true(asked.includes("attached picture"));
    assert.is_true(asked.includes("keep: tricorn hat, eye patch."));
    assert.is_true(asked.includes("A stocky pirate deckhand with a beard."));
    assert.is_true(!asked.includes("navy coat"));
    assert.is_true(!asked.includes("spyglass"))
}

test "a head sheet is for characters; a bare head is asked for nothing extra" {
    let troll = ObjectBrief {
        name: "Cave Troll",
        description: "A troll.",
        subject: "A hulking cave troll.",
        materials: [],
        size_m: 2.6,
        character: true,
    };
    let kettle = ObjectBrief {
        name: "Iron Kettle",
        description: "A kettle.",
        subject: "A cast-iron kettle.",
        materials: [],
        size_m: 0.3,
    };
    assert.is_true(wants_head_sheet(troll));
    assert.is_true(!wants_head_sheet(kettle));
    assert.equal(head_gear(troll), "");
    assert.is_true(!head_sheet_request(troll).includes("keep:"))
}
