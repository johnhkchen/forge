// Offline tests for the comic script step: a saved reply parses into panels,
// and the checks catch what cannot be drawn or lettered. No model is called.

function test_kit() -> ComicKit {
    baml.json.decode<ComicKit>(
        `
            {
              "cast": [
                {"id": "lincoln", "name": "Lincoln", "about": "tall and patient",
                 "poses": [{"name": "stand", "about": "standing easy"}, {"name": "point", "about": "pointing"}],
                 "moments": [], "clips": ["run", "walk"], "expressions": ["neutral", "happy", "smug", "talking"], "shot_clips": [], "silent": false},
                {"id": "roosevelt", "name": "Roosevelt", "about": "stocky and loud",
                 "poses": [{"name": "stand", "about": "standing easy"}, {"name": "flex", "about": "a flex"}],
                 "moments": [], "clips": ["walk"], "expressions": ["neutral", "happy", "shouting"], "shot_clips": [], "silent": false},
                {"id": "ninja", "name": "Ninja", "about": "serious",
                 "poses": [{"name": "stand", "about": "standing easy"}],
                 "moments": [{"name": "hero:draw", "about": "hand at the sword grip", "second": 11.3}], "silent": true,
                 "shot_clips": [{"clip": "hero", "seconds": 12.0, "beats": ["0.0 to 2.1 s: crouch and look", "7.0 to 8.5 s: vault the wall"], "places": ["rooftop", "rooftop-dawn"]}],
                 "clips": ["hero", "walk"], "expressions": []}
              ],
              "places": [
                {"name": "ring", "about": "a wrestling ring", "marks": [], "cameras": []},
                {"name": "rooftop", "about": "a roof at night", "marks": [], "cameras": []},
                {"name": "rooftop-dawn", "about": "the same roof at sunrise", "marks": [], "cameras": []},
                {"name": "studio", "about": "a talk-show set", "marks": ["host", "guest"], "cameras": ["desk"]}
              ],
              "framings": [{"name": "wide", "about": "everyone head to toe"}, {"name": "close-up", "about": "a face"}]
            }
        `,
    )
}

const STRIP_REPLY = `
    {
      "title": "Long Reach",
      "panels": [
        {"framing": "wide", "place": "ring", "camera": null, "shape": "square",
         "cast": [{"who": "roosevelt", "at": "left", "facing": "right", "pose": "flex", "expression": "shouting"},
                  {"who": "lincoln", "at": "right", "facing": "left", "pose": "stand", "expression": "neutral"}],
         "lines": [{"who": "roosevelt", "says": "A bully morning for a bout!", "how": "shout"}],
         "caption": null, "sfx": null},
        {"framing": "two-shot", "place": "ring", "camera": null, "shape": "square",
         "cast": [{"who": "roosevelt", "at": "left", "facing": "right", "pose": "stand", "expression": "happy"},
                  {"who": "lincoln", "at": "right", "facing": "left", "pose": "stand", "expression": "talking"}],
         "lines": [{"who": "lincoln", "says": "I'll try my best to stand here.", "how": "say"}],
         "caption": null, "sfx": null},
        {"framing": "two-shot", "place": "ring", "camera": null, "shape": "square",
         "cast": [{"who": "roosevelt", "at": "left", "facing": "right", "pose": "stand", "expression": "shouting"},
                  {"who": "lincoln", "at": "right", "facing": "left", "pose": "point", "expression": "neutral"}],
         "lines": [], "caption": null, "sfx": "SHOVE"},
        {"framing": "close-up", "place": "ring", "camera": null, "shape": "square",
         "cast": [{"who": "lincoln", "at": "center", "facing": "camera", "pose": "run@0.4", "expression": "smug"}],
         "lines": [{"who": "lincoln", "says": "Same spot tomorrow.", "how": "say"}],
         "caption": "Forty minutes later.", "sfx": null}
      ]
    }
`;

function strip_script() -> ComicScript {
    WriteComic@spec("a premise", format_rules("strip"), test_kit().to_prompt()).parse(STRIP_REPLY)
}

test "WriteComic parses a saved script into panels, and it passes every check" {
    let script = strip_script();
    assert.equal(script.title, "Long Reach");
    assert.equal(script.panels.length(), 4);
    assert.equal(script.panels.at(0)?.cast.at(0)?.pose, "flex");
    assert.equal(script.panels.at(2)?.sfx, "SHOVE");
    assert.equal(script.panels.at(3)?.lines.at(0)?.how, "say");
    assert.equal(script_problems(script, test_kit(), "strip"), [])
}

test "the kit is shown to Opus by name: poses, faces, clips, places, marks and cameras" {
    let shown = test_kit().to_prompt();
    assert.is_true(shown.includes("- lincoln (Lincoln): tall and patient"));
    assert.is_true(shown.includes("expressions: neutral, happy, smug, talking"));
    assert.is_true(shown.includes("flex: a flex"));
    assert.is_true(
        shown.includes("hero:draw: hand at the sword grip (11.3 s into its clip)")
            && shown.includes(
                "the clip \"hero\" is one continuous 12.0 s action that belongs to rooftop or rooftop-dawn",
            )
            && shown.includes("7.0 to 8.5 s: vault the wall")
            && shown.includes("NEVER SPEAKS ALOUD"),
    );
    assert.is_true(shown.includes("clips, as clip@seconds: run, walk"));
    assert.is_true(shown.includes("expressions: neutral only"));
    assert.is_true(shown.includes("- studio: a talk-show set; marks: host, guest; cameras: desk"));
    let narrowed = test_kit().only(["lincoln"], ["ring"]);
    assert.equal(narrowed.cast.length(), 1);
    assert.equal(narrowed.places.length(), 1)
}

test "a pose is a name, a moment, or clip@seconds for a clip the character has" {
    let ninja = test_kit().cast.at(2) ?? throw "no ninja";
    assert.is_true(ninja.can_pose("stand"));
    assert.is_true(ninja.can_pose("hero:draw"));
    assert.is_true(ninja.can_pose("hero@7.25"));
    assert.is_true(ninja.can_pose("walk@0.3s"));
    assert.is_true(!ninja.can_pose("run@0.3"));
    assert.is_true(!ninja.can_pose("hero@soon"));
    assert.is_true(!ninja.can_pose("moonwalk"));
    assert.is_true(ninja.at_home("hero:draw", "rooftop"));
    assert.is_true(ninja.at_home("hero@4.2", "rooftop-dawn"));
    assert.is_true(!ninja.at_home("hero:draw", "ring"));
    assert.is_true(!ninja.at_home("walk@0.3", "rooftop"));
    assert.is_true(!ninja.at_home("stand", "rooftop"))
}

test "a script that names what the kit does not have is told so, panel by panel" {
    let script = strip_script();
    let first = script.panels.at(0) ?? throw "no panel";
    first.place = "moon";
    first.cast.at(0)?.pose = "backflip";
    first.cast.at(1)?.expression = "furious";
    first.lines.push(ComicLine { who: "ninja", says: "Hello.", how: "say" });
    let problems = script_problems(script, test_kit(), "strip");
    assert.is_true(
        problems.includes(
            `panel 1: no place "moon" (there is: ring, rooftop, rooftop-dawn, studio)`,
        ),
    );
    assert.is_true(problems.includes(`panel 1: roosevelt has no pose "backflip"`));
    assert.is_true(
        problems.includes(
            `panel 1: lincoln has no expression "furious" (it has: neutral, happy, smug, talking)`,
        ),
    );
    assert.is_true(problems.includes("panel 1: ninja has a line but is not in the panel"))
}

test "dialogue has to fit the balloon space its framing leaves" {
    let script = strip_script();
    let close = script.panels.at(3) ?? throw "no panel";
    close.lines
        = [
            ComicLine {
                who: "lincoln",
                says: "I have been standing in this very spot since breakfast, Theodore.",
                how: "say",
            },
            ComicLine { who: "lincoln", says: "And I mean to stand here until supper.", how: "say" },
        ];
    let problems = script_problems(script, test_kit(), "strip");
    assert.equal(problems.length(), 1);
    assert.is_true((problems.at(0) ?? "").includes("a close-up panel has room for about 70"));
    close.lines = [ComicLine { who: "lincoln", says: "word ".repeat(30), how: "say" }];
    let long = script_problems(script, test_kit(), "strip");
    assert.is_true(
        long.some((p) -> {
            p.includes("at most 90 fit")
        }),
    )
}

test "a strip is four square panels; a scroll episode is six to ten" {
    let script = strip_script();
    assert.equal(
        script_problems(script, test_kit(), "scroll"),
        ["a scroll episode has 6 to 10 panels, not 4"],
    );
    script.panels.at(1)?.shape = "tall";
    assert.is_true(
        script_problems(script, test_kit(), "strip").includes(
            "panel 2: a strip's panels are all square",
        ),
    );
    assert.is_true(format_rules("strip").includes("exactly 4 panels"));
    assert.is_true(format_rules("scroll").includes("6 to 10 panels"));
    assert.equal(as_layout("scroll"), "scroll")
}

test "a set's marks and cameras are accepted, and 'there' needs a moment that belongs to the place" {
    let script = strip_script();
    let panel = script.panels.at(0) ?? throw "no panel";
    panel.place = "studio";
    panel.camera = "desk";
    panel.cast.at(0)?.at = "host";
    panel.cast.at(1)?.at = "guest";
    assert.equal(script_problems(script, test_kit(), "strip"), []);
    panel.camera = "crane";
    panel.cast.at(1)?.at = "there";
    let problems = script_problems(script, test_kit(), "strip");
    assert.is_true(problems.includes(`panel 1: studio has no camera "crane"; leave camera null`));
    assert.is_true(
        problems.includes(
            `panel 1: lincoln stands at "there", which needs a moment of a clip that belongs to studio`,
        ),
    )
}

test "the comic file keeps the script and the premise, and reads back" {
    let file = ComicFile {
        canon: false,
        title: "Long Reach",
        premise: "a bout",
        layout: "strip",
        panels: strip_script().panels,
    };
    let back = baml.json.decode<ComicFile>(baml.json.stringify(file));
    assert.equal(back.panels.length(), 4);
    assert.equal(back.layout, "strip");
    assert.equal(listed(" lincoln, roosevelt ,"), ["lincoln", "roosevelt"]);
    assert.equal(listed(""), [])
}

const POV_REPLY = `
    {
      "title": "First Light",
      "panels": [
        {"framing": "pov", "look": "hands", "place": "rooftop", "camera": null, "shape": "wide",
         "cast": [{"who": "ninja", "at": "there", "facing": "camera", "pose": "hero@7.9", "expression": "neutral"}],
         "lines": [{"who": "ninja", "says": "Every good film has one wall.", "how": "think"}],
         "caption": "Take one.", "sfx": null},
        {"framing": "wide", "look": null, "place": "rooftop-dawn", "camera": null, "shape": "tall",
         "cast": [{"who": "ninja", "at": "there", "facing": "camera", "pose": "hero:draw", "expression": "neutral"}],
         "lines": [], "caption": null, "sfx": null}
      ]
    }
`;

test "a pov panel parses with its look, and a silent character may only think" {
    let script = WriteComic@spec("a premise", format_rules("scroll"), test_kit().to_prompt()).parse(POV_REPLY);
    let first = script.panels.at(0) ?? throw "no panel";
    assert.equal(first.framing, "pov");
    assert.equal(first.look, "hands");
    assert.equal(script.panels.at(1)?.look, null);
    let sound = script_problems(script, test_kit(), "scroll").filter((p) -> {
        !p.includes("6 to 10 panels")
    });
    assert.equal(sound, []);
    first.lines = [ComicLine { who: "ninja", says: "Action!", how: "shout" }];
    let problems = script_problems(script, test_kit(), "scroll");
    assert.is_true(
        problems.includes(
            `panel 1: ninja never speaks aloud; make the line a thought ("think") or a caption`,
        ),
    );
    assert.equal(panel_room("pov"), 110)
}
