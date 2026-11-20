// Step 5: sized versions of the finished object, made by the tidy-mesh skill's
// scripts in a background Blender (no model calls, never touches the open
// Blender). Each profile lands in profiles/<name>.glb with previews; see
// .claude/skills/tidy-mesh/SKILL.md for what each one is for.

const DEFAULT_PROFILES: string[] = ["web", "game"];
const BLENDER_APP = "/Applications/Blender.app/Contents/MacOS/Blender";
const PROFILE_TIMEOUT_MINUTES = 15;

class ProfilesFailed {
    reason: string,

    implements baml.ToString {
        function to_string(self) -> string {
            `could not make the profiles: ${self.reason}`
        }
    }
}

/// The profiles this run doesn't have yet.
function missing_profiles(run: Run, wanted: string[]) -> string[] {
    wanted.filter((p) -> {
        !run.has(`profiles/${p}.glb`)
    })
}

/// Makes the given profiles from the run's scene.blend (Claude's finished
/// scene), or from the raw mesh if Blender never finished.
function shape(run: Run, wanted: string[] = DEFAULT_PROFILES) -> void {
    let todo = missing_profiles(run, wanted);
    if (!todo) {
        return;
    }
    let source = if (run.has("scene.blend")) {
        run.path("scene.blend")
    } else {
        run.path("mesh.glb")
    };
    let blender = baml.env.get("BLENDER") ?? BLENDER_APP;
    //# Background Blender runs the tidy-mesh steps for each profile
    let out = baml.sys.run(
        blender,
        args = [
            "-b",
            "--factory-startup",
            "-P",
            "scripts/tidy_profile.py",
            "--",
            source,
            run.path("profiles"),
        ]
            .concat(todo),
        timeout = baml.time.Duration.from_minutes(PROFILE_TIMEOUT_MINUTES),
        capture_output = true,
    ) catch (e) {
        baml.errors.Io => {
            throw ProfilesFailed { reason: `Blender not found at ${blender} (set BLENDER)` }
        },
        baml.errors.Timeout => {
            throw ProfilesFailed { reason: `still running after ${PROFILE_TIMEOUT_MINUTES} minutes` }
        },
    };
    let lines = string.from_utf8(out.stdout).lines();
    for (
        let line in lines.filter((l) -> {
            l.starts_with("PROFILE ")
        })
    ) {
        log.info(`profiles: ${line.slice(8, line.length())}`);
    }
    if (!out.ok() || missing_profiles(run, todo)) {
        let tail = lines.slice(baml.Int.max(0, lines.length() - 15), lines.length()).join("\n");
        throw ProfilesFailed { reason: `Blender exited ${out.exit_code}:\n${tail}` }
    }
}
