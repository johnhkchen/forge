const MATCH_SCRIPT = ".claude/skills/tidy-mesh/scripts/match.py";

/// Asks Claude to block out a low-poly version in the live Blender and save
/// it as lowpoly.glb; the "lowpoly" profile bakes the detail onto it.
function block_out(brief: ObjectBrief, run: Run) -> LowPolyReport {
    let parts = if (run.has("parts.json")) { baml.fs.read(run.path("parts.json")) } else { "(none found: treat it as one piece)" };
    //# Claude builds it from simple shapes and checks it against the detail
    let report = BlockOut(brief, run.absolute("final.glb"), run.absolute("lowpoly.glb"), parts, baml.fs.read(MATCH_SCRIPT));
    keep_transcript(run, "lowpoly");
    run.save("lowpoly.json", report);
    report
}

test "BlockOut parses a report" {
    let reply = `
        {
          "triangles": 512,
          "parts": [{ "name": "body", "shape": "8-sided cylinder", "triangles": 160 }],
          "shape_typical": 1.8,
          "shape_worst": 6.2,
          "notes": "none"
        }
    `;
    let brief = ObjectBrief {
        name: "Iron Kettle", description: "A kettle.", subject: "A kettle.",
        materials: [], size_m: 0.24,
    };
    let report = BlockOut@spec(brief, "final.glb", "lowpoly.glb", "{}", "script").parse(reply);
    assert.equal(report.triangles, 512)
}
