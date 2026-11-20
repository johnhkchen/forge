const PARTS_TOOLS = ["open", "measure", "frame", "split"];

/// Asks Claude to find the object's parts in the live Blender and saves the
/// plan as parts.json, which the profiles use to remesh part by part.
function find_parts(brief: ObjectBrief, run: Run) -> PartsPlan {
    //# Claude places and checks one box per part
    let plan = FindParts(brief, run.absolute("final.glb"), tools(PARTS_TOOLS));
    keep_transcript(run, "parts");
    run.save("parts.json", plan);
    plan
}

test "FindParts parses a plan" {
    let reply = `
        {
          "parts": [
            { "name": "knob", "why": "Round knob on the lid", "min": [-0.02, -0.02, 0.2], "max": [0.02, 0.02, 0.24] },
            { "name": "belt", "why": "Rope belt, lower in front", "min": [-0.7, -0.75, 1.12], "max": [0.7, 0.67, 1.34], "turn": [11, 0, 0], "wraps": true }
          ],
          "notes": "none"
        }
    `;
    let brief = ObjectBrief {
        name: "Iron Kettle",
        description: "A kettle.",
        subject: "A kettle.",
        materials: [],
        size_m: 0.24,
        character: null,
        lowpoly_triangles: null,
        lowpoly_style: null,
    };
    let plan = FindParts@spec(brief, "final.glb", tools(PARTS_TOOLS)).parse(reply);
    assert.equal(plan.parts.at(0)?.name, "knob");
    assert.equal(plan.parts.at(0)?.wraps, null);
    assert.equal(plan.parts.at(1)?.wraps, true)
}
