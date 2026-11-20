// One idea in, one finished 3D object out.
//
//   1. Opus writes a short brief                     (1_describe)
//   2. Codex draws the object                        (2_picture)
//   3. TRELLIS.2 on RunPod lifts it into a mesh      (3_mesh)
//   4. Claude finishes it in Blender over MCP        (4_polish)
//
// Each step writes its result into the run folder, and a step whose result is
// already there is skipped, so `resume` picks a stopped run up where it left off.
//
//   baml run make -- --idea "a brass diving helmet"
//   baml run resume -- --dir runs/2026-11-20T03-22-22-brass-diving-helmet

/// Makes one object from a loose idea; returns the run folder.
function make(idea: string) -> string {
    //# 1. Opus writes the brief
    log.info(`brief: asking Opus about "${idea}"`);
    let brief = Describe(idea);
    let run = Run.start(brief.name);
    run.save("brief.json", brief);
    log.info(`brief: ${brief.name} -> ${run.dir}`);
    finish(run, brief)
}

/// Picks up a stopped run at its first missing result.
function resume(dir: string) -> string {
    let run = Run.open(dir);
    finish(run, run.load<ObjectBrief>("brief.json"))
}

function finish(run: Run, brief: ObjectBrief) -> string {
    //# 2. Codex draws it
    if (!run.has("image.png")) {
        log.info("picture: codex is drawing");
        draw(brief.subject, run);
    }
    //# 3. TRELLIS.2 builds the mesh
    if (!run.has("mesh.glb")) {
        log.info("mesh: sending the picture to TRELLIS.2 on RunPod");
        sculpt(run);
    }
    //# 4. Claude finishes it in Blender
    if (!run.has("polish.json")) {
        log.info("blender: Claude is finishing the mesh");
        let report = polish(brief, run);
        log.info(`blender: done, ${report.fixes.length()} fixes, match ${report.score}/5`);
    }
    run.dir
}
