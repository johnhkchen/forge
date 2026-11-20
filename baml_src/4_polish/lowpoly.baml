const MATCH_SCRIPT = ".claude/skills/tidy-mesh/scripts/match.py";

/// Asks Claude to block out a low-poly version in the live Blender and save
/// it as lowpoly.glb; the "lowpoly" profile bakes the detail onto it.
function block_out(brief: ObjectBrief, run: Run) -> LowPolyReport {
    let parts = if (run.has("parts.json")) { baml.fs.read(run.path("parts.json")) } else { "(none found: treat it as one piece)" };
    //# Claude builds it from simple shapes and checks it against the detail
    let target = brief.lowpoly_triangles ?? 550;
    let budget = `about ${target} triangles in total (${target * 3 / 4} to ${target * 5 / 4})`;
    let report = BlockOut(brief, run.absolute("final.glb"), run.absolute("lowpoly.glb"), parts, baml.fs.read(MATCH_SCRIPT), budget);
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
        materials: [], size_m: 0.24, character: null, lowpoly_triangles: null, lowpoly_style: null,
    };
    let report = BlockOut@spec(brief, "final.glb", "lowpoly.glb", "{}", "script", "about 500 triangles").parse(reply);
    assert.equal(report.triangles, 512)
}
