const LOWPOLY_TOOLS = ["open", "measure", "build", "export"];
const CHARACTER_TOOLS = ["open", "measure", "face", "build", "export"];

/// The triangle budget as the prompt states it. A character's head and face
/// get a stated share: without one they get about 5%.
function lowpoly_budget(brief: ObjectBrief) -> string {
    let target = brief.lowpoly_triangles ?? 550;
    let total = `about ${target} triangles in total (${target * 3 / 4} to ${target * 5 / 4})`;
    if (brief.character ?? false) {
        `${total}, ${target * 15 / 100} to ${target / 4} of them for the head and face`
    } else {
        total
    }
}

/// Asks Claude to block out a low-poly version in the live Blender and save
/// it as lowpoly.glb; the "lowpoly" profile bakes the detail onto it.
function block_out(brief: ObjectBrief, run: Run) -> LowPolyReport {
    let parts = if (run.has("parts.json")) {
        baml.fs.read(run.path("parts.json"))
    } else {
        "(none found: treat it as one piece)"
    };
    //# Claude builds it from simple shapes and checks it against the detail
    let names = if (brief.character ?? false) {
        CHARACTER_TOOLS
    } else {
        LOWPOLY_TOOLS
    };
    let report = BlockOut(
        brief,
        run.absolute("final.glb"),
        run.absolute("lowpoly.glb"),
        parts,
        tools(names),
        lowpoly_budget(brief),
    );
    keep_transcript(run, "lowpoly");
    run.save("lowpoly.json", report);
    //# Save the recipe it was built from, for the mid-poly version
    keep_recipe(run);
    report
}

const RECIPE_TOOL = "scripts/blockout_recipe.py";

/// Saves what build.py was given as lowpoly_build.json, and names the .glb's
/// meshes for their tags (body, gear: ..., socket: ...).
///
/// Claude's tools run in Blender's safe mode and can't write files of their
/// own, so the recipe and the tags ride inside lowpoly.glb; this reads them
/// back out (scripts/blockout_recipe.py). The run is still good without it,
/// so a failure here is a warning: only the `midpoly` profile needs the recipe.
function keep_recipe(run: Run) -> void {
    if (!run.has("lowpoly.glb")) {
        return;
    }
    let out = baml.sys.run("python3", args = [RECIPE_TOOL, run.path("lowpoly.glb")], capture_output = true) catch (e) {
        baml.errors.Io => {
            log.warn("lowpoly: python3 not found, so the block-out's recipe was not saved");
            return;
        },
    };
    if (out.ok()) {
        log.info(`lowpoly: ${string.from_utf8(out.stdout).trim()}`);
    } else {
        log.warn(
            `lowpoly: could not read the recipe out of lowpoly.glb: ${string.from_utf8(out.stderr)}`,
        );
    }
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
        name: "Iron Kettle",
        description: "A kettle.",
        subject: "A kettle.",
        materials: [],
        size_m: 0.24,
        character: null,
        lowpoly_triangles: null,
        lowpoly_style: null,
    };
    let report = BlockOut@spec(brief, "final.glb", "lowpoly.glb", "{}", tools(LOWPOLY_TOOLS), "about 500 triangles")
        .parse(reply);
    assert.equal(report.triangles, 512)
}

/// A brief with only what the low-poly step reads filled in.
function lowpoly_test_brief(character: bool, triangles: int?) -> ObjectBrief {
    ObjectBrief {
        name: "Cave Troll",
        description: "A troll.",
        subject: "A troll.",
        materials: [],
        size_m: 2.6,
        character: character,
        lowpoly_triangles: triangles,
        lowpoly_style: null,
    }
}

test "a character with gear is asked for a whole body, gear as its own pieces, and sockets" {
    let wrestler = ObjectBrief {
        ...lowpoly_test_brief(true, 1400),
        gear: [
            GearItem {
                name: "wool singlet",
                kind: "worn",
                slot: "torso",
                look: "navy knitted wool",
            },
            GearItem {
                name: "round spectacles",
                kind: "attached",
                slot: "face",
                look: "gunmetal rims",
            },
            GearItem { name: "umbrella", kind: "held", slot: "hand_right", look: "black, furled" },
        ],
    };
    let asked = BlockOut@spec(wrestler, "final.glb", "lowpoly.glb", "{}", tools(CHARACTER_TOOLS), lowpoly_budget(wrestler))
        .prompt()
        .to_string();
    assert.contains(asked, "The body first, whole");
    assert.contains(asked, "- wool singlet (worn, torso): navy knitted wool");
    assert.contains(asked, `{"name":"round spectacles","kind":"attached","slot":"face"}`);
    assert.contains(asked, "made separately and not built here: umbrella");
    assert.is_true(!asked.includes("- umbrella"));
    assert.contains(asked, `set "sockets": True`);
    // A character from before gear lists still gets its sockets, and no gear talk.
    let troll = lowpoly_test_brief(true, 1200);
    let plain = BlockOut@spec(troll, "final.glb", "lowpoly.glb", "{}", tools(CHARACTER_TOOLS), lowpoly_budget(troll))
        .prompt()
        .to_string();
    assert.contains(plain, `set "sockets": True`);
    assert.is_true(!plain.includes("Its gear comes off"));
    // An object gets neither.
    let kettle = lowpoly_test_brief(false, null);
    let prop = BlockOut@spec(kettle, "final.glb", "lowpoly.glb", "{}", tools(LOWPOLY_TOOLS), lowpoly_budget(kettle))
        .prompt()
        .to_string();
    assert.is_true(!prop.includes(`"sockets": True in build.py`))
}

test "a low-poly report can say which gear a piece is" {
    let reply = `
        {
          "triangles": 900,
          "parts": [
            { "name": "torso", "shape": "8-sided loft", "triangles": 100 },
            { "name": "coat", "gear": "navy coat", "shape": "8-sided loft", "triangles": 120 }
          ],
          "shape_typical": 2.1,
          "shape_worst": 5.0,
          "notes": "none"
        }
    `;
    let troll = lowpoly_test_brief(true, 1200);
    let report = BlockOut@spec(troll, "final.glb", "lowpoly.glb", "{}", tools(CHARACTER_TOOLS), lowpoly_budget(troll))
        .parse(reply);
    assert.equal(report.parts.at(0)?.gear, null);
    assert.equal(report.parts.at(1)?.gear, "navy coat")
}

test "a character's budget sets aside the head's share" {
    assert.equal(
        lowpoly_budget(lowpoly_test_brief(true, 1200)),
        "about 1200 triangles in total (900 to 1500), 180 to 300 of them for the head and face",
    );
    assert.equal(
        lowpoly_budget(lowpoly_test_brief(false, null)),
        "about 550 triangles in total (412 to 687)",
    )
}

test "a character's prompt asks for a measured face; a prop's doesn't mention one" {
    let troll = lowpoly_test_brief(true, 1200);
    let asked = BlockOut@spec(troll, "final.glb", "lowpoly.glb", "{}", tools(CHARACTER_TOOLS), lowpoly_budget(troll))
        .prompt()
        .to_string();
    assert.contains(asked, "run face.py with that box");
    assert.contains(asked, "===== face");
    assert.contains(asked, "for the head and face");
    let kettle = lowpoly_test_brief(false, null);
    let plain = BlockOut@spec(kettle, "final.glb", "lowpoly.glb", "{}", tools(LOWPOLY_TOOLS), lowpoly_budget(kettle))
        .prompt()
        .to_string();
    assert.is_true(!plain.includes("face.py with that box"));
    assert.is_true(!plain.includes("===== face"))
}
