// Step 5b: a character's walk. Opus says how it carries itself (four numbers,
// gait.json); the `walk` profile then gives the low-poly and mid-poly versions
// a skeleton and a walk worked out from the model's own build (rig.py, walk.py
// and animate.py in the tidy-mesh skill), in the same background Blender run
// as the other profiles.

const GAIT_FILE = "gait.json";

/// Asks once how this character walks and saves the answer in the run.
function gait(brief: ObjectBrief, run: Run) -> GaitTraits {
    if (run.has(GAIT_FILE)) {
        return run.load<GaitTraits>(GAIT_FILE);
    }
    let traits = within_range(HowItWalks(brief.name, brief.description, brief.subject));
    run.save(GAIT_FILE, traits);
    traits
}

/// Every trait held to 0-1, whatever the model wrote.
function within_range(traits: GaitTraits) -> GaitTraits {
    GaitTraits {
        ...traits,
        weight: unit(traits.weight),
        stealth: unit(traits.stealth),
        swagger: unit(traits.swagger),
        stiffness: unit(traits.stiffness),
    }
}

function unit(value: float) -> float {
    baml.Float.max(0.0, baml.Float.min(1.0, value))
}

test "HowItWalks parses a reply and is held to 0-1" {
    let reply = `
        {
          "weight": 1.4,
          "stealth": 0.05,
          "swagger": 0.5,
          "stiffness": -0.2,
          "why": "It lumbers, each step a thud."
        }
    `;
    let traits = within_range(HowItWalks@spec("Cave Troll", "A huge troll.", "A troll in a T-pose.").parse(reply));
    assert.approx_equal(traits.weight, 1.0, 0.001);
    assert.approx_equal(traits.stiffness, 0.0, 0.001);
    assert.approx_equal(traits.swagger, 0.5, 0.001)
}

/// Only the question: how would this run's character walk? Saves nothing.
///
///   baml run how_it_walks -- --dir runs/<run>
function how_it_walks(dir: string) -> GaitTraits {
    let brief = Run.open(dir).load<ObjectBrief>("brief.json");
    within_range(HowItWalks(brief.name, brief.description, brief.subject))
}
