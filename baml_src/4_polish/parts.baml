const SPLIT_SCRIPT = ".claude/skills/tidy-mesh/scripts/split.py";

/// Asks Claude to find the object's parts in the live Blender and saves the
/// plan as parts.json, which the profiles use to remesh part by part.
function find_parts(brief: ObjectBrief, run: Run) -> PartsPlan {
    //# Claude places and checks one box per part
    let plan = FindParts(brief, run.absolute("final.glb"), baml.fs.read(SPLIT_SCRIPT));
    run.save("parts.json", plan);
    plan
}

test "FindParts parses a plan" {
    let reply = `
        {
          "parts": [
            { "name": "knob", "why": "Round knob on the lid", "min": [-0.02, -0.02, 0.2], "max": [0.02, 0.02, 0.24] }
          ],
          "notes": "none"
        }
    `;
    let brief = ObjectBrief {
        name: "Iron Kettle", description: "A kettle.", subject: "A kettle.",
        materials: [], size_m: 0.24,
    };
    let plan = FindParts@spec(brief, "final.glb", "script").parse(reply);
    assert.equal(plan.parts.at(0)?.name, "knob")
}
