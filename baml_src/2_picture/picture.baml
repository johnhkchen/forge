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

function picture_request(subject: string) -> string {
    `
        Use your built-in image_gen tool to generate exactly one square image,
        then reply with the single word: done. Do not run shell commands and do
        not edit files.

        Image: ${PICTURE_RULES}

        The object: ${subject}
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

/// Draws `subject` and saves it as image.png in the run folder.
function draw(subject: string, run: Run) -> string {
    //# Ask codex for one picture
    let out = baml.sys.run(
        "codex",
        args = ["exec", "--json", "--skip-git-repo-check", "--sandbox", "read-only", "-C", run.dir, "-"],
        input = picture_request(subject),
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

    //# Copy the picture out of codex's thread folder
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
    let target = run.path("image.png");
    baml.fs.write_bytes(target, baml.fs.open(`${folder}/${drawn.name}`, "r").bytes());
    target
}

test "codex_thread reads the id from the first event" {
    let events = `
        {"type":"thread.started","thread_id":"01a1f6f7-aaa1"}
        {"type":"turn.started"}
    `;
    assert.equal(codex_thread(events), "01a1f6f7-aaa1")
}
