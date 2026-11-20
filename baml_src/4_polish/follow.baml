// Step 4a: the base body and its garments follow the finished object.
//
// Finishing turns, sizes and stands the clothed mesh (stand.py). The base
// body and the cut garments were made beside the raw mesh (2b_undress), so
// they make exactly the same move here, in a background Blender: the person
// sees no extra work in theirs. follow.py reads the move stand.py kept on
// the finished object in scene.blend, or fits it when it isn't there, and
// checks it by moving the raw mesh onto the finished one.
//
//   base/body.glb        -> base/final.glb
//   base/cut/<name>.glb  -> garments/<name>.glb

const FOLLOW_TOOL = ".claude/skills/tidy-mesh/scripts/follow.py";
const FOLLOW_FILE = "base/follow.json";
const BASE_FINAL = "base/final.glb";
const GARMENTS_DIR = "garments";

class FollowedFile {
    from: string,
    to: string,
}

class FollowCheck {
    typical_pct: float,
    nine_in_ten_within_pct: float,
}

class FollowReport {
    ok: bool,
    why: string[],
    move_from: string,
    placed: float[],
    scale: float,
    check: FollowCheck,
    written: FollowedFile[],
}

/// The cut garments of a run, as file names: ["ruffled-skirt.glb"].
function cut_files(run: Run) -> string[] {
    let entries: baml.fs.DirEntry[] = baml.fs.read_dir(run.path("base/cut")) catch (e) {
        baml.errors.Io => []
    };
    entries
        .filter((f) -> {
            f.is_file && f.name.ends_with(".glb")
        })
        .map((f) -> {
            f.name
        })
        .sort_by_key((n) -> {
            n
        })
}

/// Moves base/body.glb and base/cut/*.glb to where the finished object
/// stands, as base/final.glb and garments/*.glb.
function follow_base(run: Run) -> FollowReport {
    let source = if (run.has("scene.blend")) {
        run.path("scene.blend")
    } else {
        run.path("final.glb")
    };
    baml.fs.mkdir(run.path(GARMENTS_DIR), baml.fs.MkdirOptions { recursive: true });
    let jobs = [{ "from": run.absolute("base/body.glb"), "to": run.absolute(BASE_FINAL) }].concat(
        cut_files(run).map((name) -> {
            {
                "from": run.absolute(`base/cut/${name}`),
                "to": run.absolute(`${GARMENTS_DIR}/${name}`),
            }
        }),
    );
    let params = baml.json.stringify({ "raw": run.absolute("mesh.glb"), "follow": jobs });
    //# A background Blender moves them the way the finish moved the mesh
    let report = baml.json.decode<FollowReport>(
        headless_result(source, FOLLOW_TOOL, params, "following the finished object"),
    ) catch (e) {
        baml.json.DecodeError | baml.json.ParseError => {
            throw UndressFailed { step: "reading follow.py's result", reason: `${e}` }
        },
    };
    if (!report.ok) {
        throw UndressFailed { step: "following the finished object", reason: report.why.join("; ") }
    }
    run.save(FOLLOW_FILE, report);
    base_sheet(run, BASE_FINAL, GARMENTS_DIR, "base/sheet-finished.png");
    report
}

/// What `finish` calls after the Blender finish: only when there is a base
/// body to move and it hasn't been moved yet.
function follow_if_base(run: Run) -> void {
    if (!run.has(CUT_FILE) || !run.has("final.glb") || run.has(BASE_FINAL)) {
        return;
    }
    log.info("base body: moving it and its garments to where the finished object stands");
    let report = follow_base(run);
    log.info(
        `base body: ${report.written.length()} files moved (${report.move_from}); the raw mesh lands ${report.check.typical_pct}% of the height from the finished one`,
    );
}

test "follow.py's result decodes" {
    let report = baml.json.decode<FollowReport>(
        `
            {"ok": true, "why": [], "object": "Dancer", "move_from": "kept by stand.py",
             "placed": [1.65, 0, 0, 0, 0, 1.65, 0, 0, 0, 0, 1.65, 0.82, 0, 0, 0, 1], "scale": 1.65,
             "check": {"typical_pct": 0.0, "nine_in_ten_within_pct": 0.01}, "height": 1.65,
             "written": [{"from": "/r/base/body.glb", "to": "/r/base/final.glb", "min": [0, 0, 0], "max": [1, 1, 1]}]}
        `,
    );
    assert.equal(report.move_from, "kept by stand.py");
    assert.equal(report.written.at(0)?.to, "/r/base/final.glb")
}
