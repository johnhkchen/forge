// Step 2: Codex draws the object, using its built-in image tool (the ChatGPT
// login, no API key).
//
// The picture is input for TRELLIS.2, not a poster. Image-to-3D does best with
// one whole object, centered, on a plain background, lit evenly, seen from a
// three-quarter angle so its depth shows. Those rules are fixed here; only the
// subject comes from the brief.
//
// Codex keeps what it draws in ~/.codex/generated_images/<thread id>/. The
// thread id is the first event `codex exec --json` prints, so the file is
// found by id rather than by guessing which picture is newest.

const PICTURE_TIMEOUT_S = 300;

// Characters are drawn front-on in a T-pose: image-to-3D reads a symmetric,
// front-facing figure far better than a turned one, and a T-pose is what
// rigging starts from.
const CHARACTER_RULES = `
    Full-body character model sheet: ONE figure standing in a T-pose, arms
    straight out to the sides with palms down, legs slightly apart, facing
    the camera straight on, eye level, whole body in frame from head to feet
    with an empty margin on every side. Plain, solid light-gray background.
    Soft, even lighting with no cast shadows, no ground plane, nothing held,
    no other figures, no text. Sharp focus, clear readable shapes and
    colors.
`;

const PICTURE_RULES = `
    Studio product photo of ONE object, alone. The whole object is in frame,
    centered with an empty margin on every side, filling about 75% of a square image, seen from a three-quarter
    view slightly above so its depth reads clearly. Plain, solid light-gray
    background. Soft, even studio lighting with no hard cast shadows, no
    reflections of the room, no ground plane, no props, no text or labels.
    Sharp focus, realistic materials.
`;

class PictureFailed {
    reason: string,

    implements baml.ToString {
        function to_string(self) -> string {
            `codex did not draw the picture: ${self.reason}`
        }
    }
}

function picture_request(brief: ObjectBrief) -> string {
    let rules = if (brief.character ?? false) {
        CHARACTER_RULES
    } else {
        PICTURE_RULES
    };
    `
        Use your built-in image_gen tool to generate exactly one square image,
        then reply with the single word: done. Do not run shell commands and do
        not edit files.

        Image: ${rules}

        The subject: ${brief.subject}
    `
}

/// The thread id from `codex exec --json`'s first event:
/// {"type":"thread.started","thread_id":"01a1f6f7-..."}
function codex_thread(events: string) -> string throws PictureFailed {
    let first = events.lines().at(0) ?? throw PictureFailed { reason: "codex printed nothing" };
    let started = baml.json.parse(first) catch (e) {
        _ => throw PictureFailed { reason: `unreadable first event: ${first}` },
    };
    baml.json.path_or<string?>(started, ".thread_id", null)
        ?? throw PictureFailed { reason: `first event has no thread id: ${first}` }
}

/// Draws the brief's subject and saves it as image.png in the run folder.
function draw(brief: ObjectBrief, run: Run) -> string {
    codex_picture(run.dir, picture_request(brief), [], run.path("image.png"))
}

/// Asks codex for one picture and saves it as `target`. `attach` are
/// pictures it is shown (absolute paths), for an edit of one.
function codex_picture(dir: string, request: string, attach: string[], target: string) -> string {
    let drawn = codex_drawn(request, dir, attach);
    baml.fs.write_bytes(target, baml.fs.open(drawn, "r").bytes());
    target
}

/// Asks codex for one picture and returns the file it drew, in codex's own
/// thread folder. `from` is a picture to work from (the head sheet is drawn
/// from the character's picture); `dir` is where codex runs.
function codex_draws(request: string, dir: string, from: string? = null) -> string {
    let shown: string[] = if let picture: string = from {
        [picture]
    } else {
        []
    };
    codex_drawn(request, dir, shown)
}

/// The one codex call behind both: `attach` pictures are shown with -i.
function codex_drawn(request: string, dir: string, attach: string[]) -> string {
    //# Ask codex for one picture
    let shown = attach.flat_map((path) -> {
        ["-i", path]
    });
    let out = baml.sys.run(
        "codex",
        args = ["exec", "--json", "--skip-git-repo-check", "--sandbox", "read-only", "-C", dir]
            .concat(shown)
            .concat(["-"]),
        input = request,
        timeout = baml.time.Duration.from_seconds(PICTURE_TIMEOUT_S),
        capture_output = true,
    ) catch (e) {
        baml.errors.Io => throw PictureFailed { reason: "codex is not installed or not on PATH" },
        baml.errors.Timeout => {
            throw PictureFailed { reason: `no answer within ${PICTURE_TIMEOUT_S}s` }
        },
    };
    let events = string.from_utf8(out.stdout);
    if (!out.ok()) {
        throw PictureFailed { reason: `codex exited ${out.exit_code}: ${string.from_utf8(out.stderr)}` }
    }

    //# Find the picture in codex's thread folder
    let home = baml.sys.home_dir() ?? throw PictureFailed { reason: "no home directory" };
    let folder = `${home}/.codex/generated_images/${codex_thread(events)}`;
    let drawn = (
        baml.fs.read_dir(folder) catch (e) {
            baml.errors.Io => throw PictureFailed { reason: `no pictures in ${folder}` },
        }
    )
        .filter((f) -> {
            f.is_file && f.name.ends_with(".png")
        })
        .at(0)
        ?? throw PictureFailed { reason: `no .png in ${folder}` };
    `${folder}/${drawn.name}`
}

test "codex_thread reads the id from the first event" {
    let events = `
        {"type":"thread.started","thread_id":"01a1f6f7-aaa1"}
        {"type":"turn.started"}
    `;
    assert.equal(codex_thread(events), "01a1f6f7-aaa1")
}
