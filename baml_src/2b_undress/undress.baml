// Step 2b / 3b: a real body under clothes that hide it.
//
// A long skirt, a robe or a cloak hides the body, and image-to-3D can only
// guess at what is under it. So for a character whose brief says something
// hides the body (`hidden_by`), the body is made for real and the clothes
// are put back on it:
//
//   2b. Codex edits the clothed picture: same figure, same framing, the
//       hiding clothes off and plain skin-tight base clothing in their
//       place.                                        -> base/image.png
//   3b. TRELLIS.2 makes a mesh of that picture, the "base body"
//                                                      -> base/mesh.glb
//       garment.py checks the two line up, lays the base body on the
//       clothed mesh, and cuts each hiding garment out of the clothed mesh
//                          -> base/body.glb, base/cut/<garment>.glb, base/cut.json
//   4a. After the finish in Blender, follow.py moves the body and garments
//       to where the finished object stands (see follow.baml)
//                          -> base/final.glb, garments/<garment>.glb
//
// It all lives in base/ inside the run, not in a run of its own: the gallery
// and `resume` treat every folder under runs/ as one object, and the body is
// part of this one. base/ is itself shaped like a run (image.png, mesh.glb,
// mesh.json), so `sculpt` makes its mesh unchanged.
//
// The two pictures must show the figure in the same place at the same size,
// and the two meshes must agree where the clothes don't cover. Both are
// measured (garment.py); when either fails, the edit is tried once more with
// what went wrong in the request, and after that the step stops with the
// numbers.

const BASE_DIR = "base";
const CUT_FILE = "base/cut.json";
const UNDRESS_FAILED_FILE = "base/failed.json";
const GARMENT_TOOL = ".claude/skills/tidy-mesh/scripts/garment.py";
const HEADLESS = "scripts/tidy_headless.py";
const SHOTS_TOOL = "scripts/base_shots.py";
const UNDRESS_TIMEOUT_MINUTES = 10;
/// The edit is tried at most this many times in all.
const EDIT_TRIES = 2;

class UndressFailed {
    step: string,
    reason: string,

    implements baml.ToString {
        function to_string(self) -> string {
            `could not make the base body (${self.step}): ${self.reason}`
        }
    }
}

/// The base body doesn't line up with the clothed character, after every try.
class BaseBodyMisaligned {
    stage: "pictures" | "meshes",
    why: string[],
    numbers: string,

    implements baml.ToString {
        function to_string(self) -> string {
            `the base body doesn't line up with the clothed character (${self.stage}): ${self.why.join("; ")}\n${self.numbers}`
        }
    }
}

// ---- what garment.py reports (base/cut.json) -------------------------------

class PictureEdge {
    moved_pct: float,
    garment_reaches_it: bool,
}

class PictureCheck {
    ok: bool,
    why: string[],
    changed_pct: float,
    slivers_pct: float,
    edges: map<string, PictureEdge>,
}

class ViewCheck {
    overlap_pct: float,
    color_off: float,
    stretch: float,
    mirrored: bool,
}

class OffBy {
    median: float,
    p90: float,
    worst: float,
}

class FitCheck {
    ok: bool,
    why: string[],
    started_from: string,
    points: int,
    scale: float,
    shift_pct: float[],
    off_pct: OffBy,
    before_pct: float,
}

class VoteCount {
    faces: int,
    area_pct: float,
}

class Votes {
    faces: int,
    said_garment: map<string, VoteCount>,
    agreement: map<string, VoteCount>,
    two_or_more: VoteCount,
}

class Cleanup {
    edge_faces_evened: int,
    faces_grown_to_the_color_seam: int,
    crumbs_dropped: map<string, int>,
    holes_closed: map<string, int>,
}

class CutGarment {
    name: string,
    slot: string?,
    faces: int,
    file: string?,
    area_pct: float?,
    pieces: int?,
    top: float?,
    bottom: float?,
    closed_round_its_top_pct: float?,
    other_colors_pct: float?,
    points_lifted_onto_the_body: int?,
    lifted_at_most_pct: float?,
}

class CutReport {
    ok: bool,
    why: string[],
    pictures: PictureCheck,
    view: map<string, ViewCheck>?,
    fit: FitCheck?,
    votes: Votes?,
    cleanup: Cleanup?,
    garments: CutGarment[]?,
    garment_area_pct: float?,
    body: string?,
    overlay: string[]?,

    /// The numbers a person needs to judge a failed line-up, in one line each.
    function numbers(self) -> string {
        let edges = ["left", "right", "top", "bottom"]
            .filter_map((side) -> {
                let edge = self.pictures.edges.get(side);
                if (edge) {
                    `${side} ${edge.moved_pct}%`
                } else {
                    null
                }
            })
            .join(", ");
        let pictures = `pictures: ${self.pictures.changed_pct}% of the figure changed, ${self.pictures.slivers_pct}% in slivers, edges moved ${edges}`;
        let fit = self.fit;
        if (fit) {
            `${pictures}\nmeshes: uncovered parts ${fit.off_pct.median}% of the height apart typically, ${fit.off_pct.p90}% for nine in ten, ${fit.off_pct.worst}% at worst; the base body was scaled x${fit.scale} and shifted ${fit.shift_pct}% to fit (started from ${fit.started_from})`
        } else {
            pictures
        }
    }
}

// ---- which gear comes off ---------------------------------------------------

/// The gear that hides the body and so comes off for the base body.
/// `undress` is "auto" (what the brief's hidden_by names), "none", or gear
/// names separated by commas to force it for those.
function hidden_gear(
    brief: ObjectBrief,
    undress: string = "auto",
) -> GearItem[] throws UndressFailed {
    if (undress == "none" || !(brief.character ?? false)) {
        return [];
    }
    let gear = brief.gear ?? [];
    let forced = undress != "auto";
    let names = if (forced) {
        undress.split(",")
            .map((n) -> {
                n.trim()
            })
            .filter((n) -> {
                !n.is_empty()
            })
    } else {
        brief.hidden_by ?? []
    };
    names.filter_map((name) -> {
        let item = gear.find((g) -> {
            g.name.to_lower_case() == name.to_lower_case() && g.kind != "held"
        });
        if (item == null && forced) {
            throw UndressFailed {
                step: "choosing the gear",
                reason: `"${name}" is not worn or attached gear in the brief (it lists: ${gear.map((g) -> { g.name }).join(", ")})`,
            }
        }
        if (item == null) {
            log.warn(
                `base body: the brief says "${name}" hides the body, but lists no such gear; skipping it`,
            );
        }
        item
    })
}

// ---- 2b. the picture --------------------------------------------------------

/// What a garment in each slot hides, in the words the edit request uses.
const SLOT_HIDES: map<string, string> = {
    "head": "the head, hair and ears",
    "face": "the face",
    "neck": "the neck and collarbones",
    "torso": "the chest, waist and back",
    "arms": "the shoulders, arms and wrists",
    "hands": "the hands",
    "back": "the back",
    "hip": "the hips, thighs, knees and calves",
    "legs": "the hips, thighs, knees and calves",
    "feet": "the ankles and feet",
};

/// The edit request: keep everything, take these garments off, show what
/// they hid in plain skin-tight base clothing. `note` carries what was wrong
/// with a first try.
function base_request(brief: ObjectBrief, hidden: GearItem[], note: string = "") -> string {
    let off = hidden.map((g) -> {
        g.name
    });
    let kept = (brief.gear ?? [])
        .filter((g) -> {
            g.kind != "held" && !off.includes(g.name)
        })
        .map((g) -> {
            g.name
        });
    let parts: string[] = [];
    for (let g in hidden) {
        let part = SLOT_HIDES.get(g.slot) ?? "the body";
        if (!parts.includes(part)) {
            parts.push(part);
        }
    }
    `
        Use your built-in image_gen tool to edit the attached picture and
        generate exactly one square image, then reply with the single word:
        done. Do not run shell commands and do not edit files.

        The picture is a character model sheet: ${brief.name}, front-on in a
        T-pose.

        Keep everything identical: the same figure, face, hair, skin and
        build, the same front-on T-pose with arms straight out, the same
        camera, framing, scale, lighting and plain background. The head,
        hands and feet stay exactly where they are in the frame.
        ${if (kept) { `Keep every piece that stays on, unchanged: ${kept.join(", ")}.` } else { "" }}

        Change one thing: take off completely
        ${hidden.map((g) -> { `- the ${g.name} (${g.look})` }).join("\n")}

        In its place show the body it was hiding, ${parts.join(", ")}, and
        anything else it covered, wearing plain skin-tight matte black base
        clothing with no folds, seams or pattern, so the true shape of the
        body is clearly visible, standing exactly as it stands under the
        clothes now. If what comes off is itself black or very dark, make the
        base clothing plain matte teal instead, so the change shows. No
        fabric hanging anywhere, nothing in the hands.
        ${note}
    `
}

/// The base folder as a run of its own, so `sculpt` works on it unchanged.
function base_run(run: Run) -> Run {
    let base = Run { dir: run.path(BASE_DIR) };
    baml.fs.mkdir(base.dir, baml.fs.MkdirOptions { recursive: true });
    base
}

/// The folders earlier tries were set aside in: base/tried-1, ...
function tries_set_aside(run: Run) -> string[] {
    let entries: baml.fs.DirEntry[] = baml.fs.read_dir(run.path(BASE_DIR)) catch (e) {
        baml.errors.Io => []
    };
    entries
        .filter((f) -> {
            !f.is_file && f.name.starts_with("tried-")
        })
        .map((f) -> {
            f.name
        })
        .sort_by_key((n) -> {
            n
        })
}

/// What to tell Codex about the try before this one, if there was one.
function retry_note(run: Run) -> string {
    let tried = tries_set_aside(run);
    let last = tried.at(tried.length() - 1)
        ?? return "";
    let why: string[] = baml.json.decode<string[]>(baml.fs.read(run.path(`${BASE_DIR}/${last}/why.json`))) catch (e) {
        _ => []
    };
    `
        An earlier try was turned down: ${why.join("; ")}. This time change
        nothing but the clothes: the figure must stay in exactly the same
        place, at exactly the same size, pixel for pixel where it isn't
        covered by what comes off.
    `
}

/// Asks Codex for the base picture and saves it as base/image.png, with the
/// request beside it (base/edit.txt).
function draw_base(brief: ObjectBrief, run: Run, hidden: GearItem[]) -> string {
    let base = base_run(run);
    let request = base_request(brief, hidden, note = retry_note(run));
    baml.fs.write(base.path("edit.txt"), request);
    //# Codex edits the clothed picture
    codex_picture(run.dir, request, [run.absolute("image.png")], base.path("image.png"))
}

// ---- 3b. the body and the cut ----------------------------------------------

/// Runs one tidy-mesh script in a background Blender and returns its RESULT.
function headless_result(source: string, script: string, params: string, step: string) -> string {
    let blender = baml.env.get("BLENDER") ?? BLENDER_APP;
    let name = script.split("/").at(script.split("/").length() - 1) ?? script;
    let out = baml.sys.run(
        blender,
        args = [
            "-b",
            "--factory-startup",
            "--python-exit-code",
            "1",
            "-P",
            HEADLESS,
            "--",
            source,
            script,
            "--params",
            `{"${name}": ${params}}`,
        ],
        timeout = baml.time.Duration.from_minutes(UNDRESS_TIMEOUT_MINUTES),
        capture_output = true,
    ) catch (e) {
        baml.errors.Io => {
            throw UndressFailed { step: step, reason: `Blender not found at ${blender} (set BLENDER)` }
        },
        baml.errors.Timeout => {
            throw UndressFailed { step: step, reason: `still running after ${UNDRESS_TIMEOUT_MINUTES} minutes` }
        },
    };
    let lines = string.from_utf8(out.stdout).lines();
    let line = lines.find((l) -> {
        l.starts_with("RESULT ")
    });
    if (line) {
        return line.slice(7, line.length());
    }
    let tail = lines.slice(baml.Int.max(0, lines.length() - 12), lines.length()).join("\n");
    throw UndressFailed { step: step, reason: `Blender exited ${out.exit_code} without a result:\n${tail}` }
}

/// garment.py on the run: with `cut` it lays the base body on the clothed
/// mesh and cuts the garments; without, it only compares the two pictures.
function compare(run: Run, hidden: GearItem[], cut: bool) -> CutReport {
    let garments = hidden.map((g) -> {
        { "name": g.name, "slot": g.slot, "kind": g.kind }
    });
    let params = if (cut) {
        baml.fs.mkdir(run.path("base/cut"), baml.fs.MkdirOptions { recursive: true });
        baml.json.stringify(
            {
                "picture": run.absolute("image.png"),
                "base_picture": run.absolute("base/image.png"),
                "garments": garments,
                "clothed": run.absolute("mesh.glb"),
                "base": run.absolute("base/mesh.glb"),
                "out": run.absolute("base/cut"),
                "body_out": run.absolute("base/body.glb"),
                "overlay": run.absolute("base/votes"),
            },
        )
    } else {
        baml.json.stringify(
            {
                "picture": run.absolute("image.png"),
                "base_picture": run.absolute("base/image.png"),
                "garments": garments,
            },
        )
    };
    baml.json.decode<CutReport>(
        headless_result(
            "-",
            GARMENT_TOOL,
            params,
            if (cut) {
                "cutting the garments"
            } else {
                "comparing the pictures"
            },
        ),
    ) catch (e) {
        baml.json.DecodeError | baml.json.ParseError => {
            throw UndressFailed { step: "reading garment.py's result", reason: `${e}` }
        },
    }
}

/// Moves a failed try's picture and mesh into base/tried-N with why it
/// failed, so the next try starts clean and the failed one can be looked at.
function set_aside(run: Run, report: CutReport) -> void {
    let base = base_run(run);
    let aside = `tried-${tries_set_aside(run).length() + 1}`;
    baml.fs.mkdir(base.path(aside), baml.fs.MkdirOptions { recursive: true });
    for (let file in ["image.png", "edit.txt", "mesh.glb", "mesh.json"]) {
        if (base.has(file)) {
            baml.fs.rename(base.path(file), base.path(`${aside}/${file}`));
        }
    }
    baml.fs.write(base.path(`${aside}/why.json`), baml.json.stringify(report.why, indent = 2));
    baml.fs.write(base.path(`${aside}/report.json`), baml.json.stringify(report, indent = 2));
}

/// A failed line-up: try the edit again if a try is left, else stop with the numbers.
function retry_or_stop(
    brief: ObjectBrief,
    run: Run,
    hidden: GearItem[],
    stage: "pictures" | "meshes",
    report: CutReport,
) -> CutReport {
    if (tries_set_aside(run).length() + 1 >= EDIT_TRIES) {
        throw BaseBodyMisaligned { stage: stage, why: report.why, numbers: report.numbers() }
    }
    log.warn(
        `base body: the ${stage} don't line up (${report.why.join("; ")}); editing the picture once more`,
    );
    set_aside(run, report);
    undress(brief, run, hidden)
}

/// 2b alone: the base picture, drawn and compared with the clothed one
/// (one more try if the figure moved). Needs only image.png.
function base_picture(brief: ObjectBrief, run: Run, hidden: GearItem[]) -> void {
    let base = base_run(run);
    if (base.has("image.png")) {
        return;
    }
    log.info(`base body: codex is taking off ${hidden.map((g) -> { g.name }).join(", ")}`);
    draw_base(brief, run, hidden);
    let seen = compare(run, hidden, false);
    if (!seen.pictures.ok) {
        if (tries_set_aside(run).length() + 1 >= EDIT_TRIES) {
            throw BaseBodyMisaligned { stage: "pictures", why: seen.why, numbers: seen.numbers() }
        }
        log.warn(
            `base body: the pictures don't line up (${seen.why.join("; ")}); editing once more`,
        );
        set_aside(run, seen);
        base_picture(brief, run, hidden);
    }
}

/// The whole step: base picture, base mesh, line-up check, garments cut.
/// Skips what is already there; returns what garment.py measured (also
/// saved as base/cut.json). Needs the clothed image.png and mesh.glb.
function undress(brief: ObjectBrief, run: Run, hidden: GearItem[]) -> CutReport {
    if (run.has(CUT_FILE)) {
        return run.load<CutReport>(CUT_FILE);
    }
    let base = base_run(run);
    //# 2b. Codex edits the clothes off the picture
    base_picture(brief, run, hidden);
    //# 3b. TRELLIS.2 builds the base body
    if (!base.has("mesh.glb")) {
        log.info("base body: sending the edited picture to TRELLIS.2 on RunPod");
        sculpt(base);
    }
    //# Line the two up and cut the garments out of the clothed mesh
    log.info("base body: lining it up with the clothed mesh and cutting the garments");
    let report = compare(run, hidden, true);
    if (!report.pictures.ok) {
        return retry_or_stop(brief, run, hidden, "pictures", report);
    }
    if (!(report.fit?.ok ?? false)) {
        return retry_or_stop(brief, run, hidden, "meshes", report);
    }
    if (!report.ok) {
        throw UndressFailed { step: "cutting the garments", reason: report.why.join("; ") }
    }
    run.save(CUT_FILE, report);
    base_sheet(run, "base/body.glb", "base/cut", "base/sheet.png");
    report
}

/// A sheet of pictures to judge the cut by eye: body, clothes and both,
/// front and quarter, over garment.py's vote renders. Only a picture, so a
/// failure is a warning.
function base_sheet(run: Run, body: string, garments: string, sheet: string) -> void {
    let entries: baml.fs.DirEntry[] = baml.fs.read_dir(run.path(garments)) catch (e) {
        baml.errors.Io => []
    };
    let files = entries
        .filter((f) -> {
            f.is_file && f.name.ends_with(".glb")
        })
        .map((f) -> {
            run.path(`${garments}/${f.name}`)
        });
    let votes = if (run.has("base/votes-front.png")) {
        ["--votes", run.absolute("base/votes")]
    } else {
        []
    };
    let out = baml.sys.run(
        baml.env.get("BLENDER") ?? BLENDER_APP,
        args = ["-b", "--factory-startup", "--python-exit-code", "1", "-P", SHOTS_TOOL, "--", run.path(body), run.path(sheet)]
            .concat(files)
            .concat(votes),
        timeout = baml.time.Duration.from_minutes(UNDRESS_TIMEOUT_MINUTES),
        capture_output = true,
    ) catch (e) {
        _ => {
            log.warn("base body: could not render the sheet of pictures");
            return;
        },
    };
    if (!out.ok()) {
        log.warn(
            `base body: the sheet of pictures was not rendered (Blender exited ${out.exit_code})`,
        );
    }
}

/// A base body that can't be lined up: saved in base/failed.json. Forced
/// (`--undress "<gear>"`) it stops the run; otherwise the run goes on the
/// old way, and later resumes don't try again.
function give_up(run: Run, off: BaseBodyMisaligned, undress_mode: string) -> void {
    run.save(UNDRESS_FAILED_FILE, off);
    if (undress_mode != "auto") {
        throw off
    }
    log.error(`base body: ${off}`);
    log.error("base body: going on without it; the body under the clothes will be guessed");
}

/// The gear to take off now, or none: nothing hides the body, the base body
/// is already made, or it was given up on.
function still_hidden(brief: ObjectBrief, run: Run, undress_mode: string) -> GearItem[] {
    if (run.has(CUT_FILE) || (undress_mode == "auto" && run.has(UNDRESS_FAILED_FILE))) {
        return [];
    }
    hidden_gear(brief, undress = undress_mode)
}

/// What `finish` calls after the picture: the base picture, when gear hides the body.
function base_picture_if_hidden(
    brief: ObjectBrief,
    run: Run,
    undress_mode: string = "auto",
) -> void {
    let hidden = still_hidden(brief, run, undress_mode);
    if (!hidden) {
        return;
    }
    base_picture(brief, run, hidden) catch (e) {
        let off: BaseBodyMisaligned => give_up(run, off, undress_mode),
    };
}

/// What `finish` calls after the mesh: the base body and the cut garments,
/// when gear hides the body.
function undress_if_hidden(brief: ObjectBrief, run: Run, undress_mode: string = "auto") -> void {
    let hidden = still_hidden(brief, run, undress_mode);
    if (!hidden) {
        return;
    }
    let report = undress(brief, run, hidden) catch (e) {
        let off: BaseBodyMisaligned => {
            give_up(run, off, undress_mode);
            return;
        },
    };
    let fit = report.fit;
    if (fit) {
        log.info(
            `base body: uncovered parts ${fit.off_pct.median}% of the height apart; cut ${(report.garments ?? []).map((g) -> { `${g.name} (${g.faces} faces)` }).join(", ")}`,
        );
    }
}

/// Only this step, on an existing run: `just undress <run> "<gear, gear>"`.
function undress_run(dir: string, gear: string = "auto") -> string {
    let run = Run.open(dir);
    let brief = run.load<ObjectBrief>("brief.json");
    let hidden = hidden_gear(brief, undress = gear);
    if (!hidden) {
        throw UndressFailed {
            step: "choosing the gear",
            reason: "the brief names no gear that hides the body; name the gear to take off",
        }
    }
    let report = undress(brief, run, hidden);
    report.numbers()
}
