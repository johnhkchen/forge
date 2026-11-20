// Motion, last step: put one of our own characters in a finished shot.
//
// The shot's motion is on NVIDIA's SOMA skeleton. scripts/motion/apply_shot.py
// renames it bone for bone (tidy-mesh's bones.json) and hands it to the same
// rig.py and animate.py the walk goes through, so the character's own limits,
// leg lengths and planted feet apply. A prop the shot list mentions rides the
// character's sockets (the katana: on the back, then in the right hand).
//
//   baml run cast -- --shot hero-rooftop --character runs/<character> --prop runs/<prop>
//
// Writes into shots/<shot>/: lowpoly-hero.glb, midpoly-hero.glb, what each
// step measured (.json), and a film and strip of the low-poly one. A second
// cut of a shot is cast under a name of its own (--clip hero-mixed), so a
// character can carry both. A take on a standing set casts every role and
// films from every one of the set's cameras (sets.baml). The
// character's own folder is only read; `just clip-to-gallery` copies the
// clips into it when you want them in the gallery.

const CLIP_NAME = "hero";
const CAST_TIMEOUT_MINUTES = 30;

/// The part of <version>-hero.json the film needs.
class CastRecord {
    size_against_soma: float,
}

/// Runs one of scripts/motion's Blender scripts in a background Blender and logs the lines it marks.
function motion_blender(step: string, script: string, args: string[], mark: string) -> void {
    let blender = baml.env.get("BLENDER") ?? BLENDER_APP;
    let out = baml.sys.run(
        blender,
        args = ["-b", "--factory-startup", "-P", `${MOTION_SCRIPTS}/${script}`, "--"].concat(args),
        timeout = baml.time.Duration.from_minutes(CAST_TIMEOUT_MINUTES),
        capture_output = true,
    ) catch (e) {
        baml.errors.Io => {
            throw ShotFailed { step: step, reason: `Blender not found at ${blender} (set BLENDER)` }
        },
        baml.errors.Timeout => {
            throw ShotFailed { step: step, reason: `still running after ${CAST_TIMEOUT_MINUTES} minutes` }
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
        let tail = lines.slice(baml.Int.max(0, lines.length() - 15), lines.length()).join("\n");
        throw ShotFailed { step: step, reason: `Blender exited ${out.exit_code}:\n${tail}` }
    }
}

/// Plays a finished shot on a character (a run folder with a low-poly block-out); returns the shot folder.
/// For a take (a shot with several people in it) the cast comes from the take itself, and `character` is
/// the folder their runs are in.
function cast(
    shot: string,
    character: string = "runs",
    prop: string = "",
    clip: string = CLIP_NAME,
) -> string {
    let run = Run { dir: `${SHOTS_DIR}/${shot}` };
    if (run.has("take.json")) {
        return cast_take(run, character, clip);
    }
    if (!run.has("motion.json")) {
        throw ShotFailed { step: "cast", reason: `no motion in ${run.dir} yet: run shoot first` }
    }
    //# 1. The shot's motion, through the character's own skeleton, limits and feet
    let with_prop = if (prop) {
        ["--prop", prop]
    } else {
        []
    };
    motion_blender("cast", "apply_shot.py", [run.dir, character, "--name", clip].concat(with_prop), "APPLY");
    let filmed = `lowpoly-${clip}`;
    if (!run.has(`${filmed}.glb`)) {
        throw ShotFailed { step: "cast", reason: `${filmed}.glb was not written` }
    }
    //# 2. Film the low-poly one in the set: from the set's own cameras if it has them...
    if (run.load<ShotPlan>("plan.json").has_set_cameras()) {
        film_on_set(run, more = ["--cast", clip]);
        return run.dir;
    }
    //# ...else with the camera that follows, the set brought to the character's size
    let size = run.load<CastRecord>(`${filmed}.json`).size_against_soma;
    motion_blender(
        "film",
        "render_shot.py",
        [run.dir, "--character", `${filmed}.glb`, "--scale", `${size}`, "--out", filmed],
        "RENDER",
    );
    run.dir
}

test "a cast record reads the character's size" {
    let record = baml.json.decode<CastRecord>(`{"version": "lowpoly", "size_against_soma": 0.9921, "bytes": 5}`);
    assert.approx_equal(record.size_against_soma, 0.9921, 0.00001)
}
