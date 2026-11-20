// One idea in, one finished 3D object out.
//
//   1. Opus writes a short brief                     (1_describe)
//   2. Codex draws the object                        (2_picture)
//      a character whose clothes hide its body is drawn again without
//      them, for a real body under the clothes       (2b_undress)
//   3. TRELLIS.2 on RunPod lifts it into a mesh      (3_mesh)
//      and the second picture into the base body; the hiding clothes are
//      cut out of the clothed mesh                   (2b_undress)
//   4. Claude finishes it in Blender over MCP        (4_polish)
//      the base body and its clothes follow          (4_polish/follow)
//      finds its parts (lid, knob, spout...) and blocks out a low-poly version
//   5. Sized versions: web, game, ...               (5_profiles)
//      a character also gets a skeleton and a walk   (7_walk)
//      and a run, when Kimodo can be reached         (9_run)
//   6. Only when asked: a character's props, each a small run of its own (6_props)
//
// Each step writes its result into the run folder, and a step whose result is
// already there is skipped, so `resume` picks a stopped run up where it left off.
//
//   baml run make -- --idea "a brass diving helmet"
//   baml run resume -- --dir runs/2026-11-20T03-22-22-brass-diving-helmet
//
// Props are off unless asked for: add `--props held` (things carried in a
// hand) or `--props all` (hats, backpacks and the like too) to either.
//
// The base body is made when the brief says clothes hide the body
// (`--undress auto`, the default). `--undress none` skips it; `--undress
// "ruffled skirt, cloak"` makes it for those gear items whatever the brief
// says.

/// Makes one object from a loose idea; returns the run folder.
function make(idea: string, props: string = "none", undress: string = "auto") -> string {
    //# 1. Opus writes the brief
    log.info(`brief: asking Opus about "${idea}"`);
    let brief = Describe(idea);
    let run = Run.start(brief.name);
    run.save("brief.json", brief);
    log.info(`brief: ${brief.name} -> ${run.dir}`);
    finish(run, brief, props = props, undress = undress)
}

/// Steps 1-3 only (brief, picture, mesh): nothing touches Blender, so it's
/// safe while Blender is busy. Finish later with `resume`.
function make_mesh(idea: string, undress: string = "auto") -> string {
    log.info(`brief: asking Opus about "${idea}"`);
    let brief = Describe(idea);
    let run = Run.start(brief.name);
    run.save("brief.json", brief);
    log.info(`brief: ${brief.name} -> ${run.dir}`);
    log.info("picture: codex is drawing");
    draw(brief, run);
    log.info("mesh: sending the picture to TRELLIS.2 on RunPod");
    sculpt(run);
    undress_if_hidden(brief, run, undress_mode = undress);
    run.dir
}

/// Picks up a stopped run at its first missing result.
function resume(dir: string, props: string = "none", undress: string = "auto") -> string {
    let run = Run.open(dir);
    finish(run, run.load<ObjectBrief>("brief.json"), props = props, undress = undress)
}

function finish(
    run: Run,
    brief: ObjectBrief,
    props: string = "none",
    undress: string = "auto",
) -> string {
    let wanted = props_wanted(props);
    //# 2. Codex draws it
    if (!run.has("image.png")) {
        log.info("picture: codex is drawing");
        draw(brief, run);
    }
    //# 2b. Clothes that hide the body: Codex draws the character again without them
    base_picture_if_hidden(brief, run, undress_mode = undress);
    //# 3. TRELLIS.2 builds the mesh
    if (!run.has("mesh.glb")) {
        log.info("mesh: sending the picture to TRELLIS.2 on RunPod");
        sculpt(run);
    }
    //# 3b. ...and the base body; the hiding clothes are cut out of the clothed mesh
    undress_if_hidden(brief, run, undress_mode = undress);
    //# 4. Claude finishes it in Blender
    if (!run.has("polish.json")) {
        log.info("blender: Claude is finishing the mesh");
        let report = polish(brief, run);
        log.info(`blender: done, ${report.fixes.length()} fixes, match ${report.score}/5`);
    }
    //# 4a. The base body and its clothes follow the finished object
    follow_if_base(run);
    //# 4b. Claude finds the parts, for part-by-part remeshing
    if (run.has("final.glb") && !run.has("parts.json")) {
        log.info("parts: Claude is finding the parts");
        let plan = find_parts(brief, run);
        log.info(`parts: ${plan.parts.map((p) -> { p.name }).join(", ")}`);
    }
    //# 4c. Claude blocks out a low-poly version from simple shapes
    if (run.has("final.glb") && !run.has("lowpoly.glb")) {
        log.info("lowpoly: Claude is blocking out a low-poly version");
        let low = block_out(brief, run);
        log.info(`lowpoly: ${low.triangles} triangles, ${low.shape_typical}% off typically`);
    }
    //# 5. Sized versions for the web, games, ...; a character also gets a walk
    let versions = profiles_for(brief, run);
    if (versions.includes(WALK) && !run.has(GAIT_FILE)) {
        let traits = gait(brief, run);
        log.info(`walk: ${traits.why}`);
    }
    shape(run, wanted = versions);
    //# 5c. A run beside the walk, when the sentence-to-motion model can be reached (never stops the run)
    if (versions.includes(WALK)) {
        run_for(run);
    }
    //# 6. Props: each held thing as a small run of its own (off unless asked)
    if (wanted != "none") {
        make_props(brief, run, wanted);
    }
    run.dir
}
