// Offline tests for BUY HOUSE: a kept design parses as a reply would, and the
// checks catch a plan that cannot be built. No model is called.

const KEPT_HOUSE = "sets/casa-de-la-rosa/design.json";

/// The dancer's house as Opus drew it, read back the way a reply is.
function kept_house() -> HouseDesign {
    DesignHouse@spec("Flamenco Dancer", "a brief", "who she is", "").parse(baml.fs.read(KEPT_HOUSE))
}

test "the dancer's kept design parses as a reply and is sound" {
    let house = kept_house();
    assert.equal(house.name, "Casa de la Rosa");
    assert.equal(house_problems(house), []);
    assert.equal(count_of(house, AreaKind.Stage), 1);
    assert.equal(count_of(house, AreaKind.PracticeFloor), 1);
    // Her microphone stands on her stage, and the house says which way it looks.
    let stage = house.areas.find((a) -> {
        a.kind == AreaKind.Stage
    });
    assert.equal(house.microphone_area, stage?.name);
    assert.equal(house.faces, "the spawn spot");
    assert.is_true(is_hex(house.walls.hex))
}

test "a plan that cannot be built is told why" {
    let house = kept_house();
    let stage = house.areas.find((a) -> {
        a.kind == AreaKind.Stage
    })
        ?? throw "no stage";
    let floor = house.areas.find((a) -> {
        a.kind == AreaKind.PracticeFloor
    })
        ?? throw "no practice floor";
    // The stage slid over the practice floor, and grown past what a stage is.
    stage.x_m = floor.x_m + 1.0;
    stage.wide_m = 6.5;
    let overlapping = house_problems(house).join("\n");
    assert.contains(overlapping, "overlap on the plan");
    assert.contains(overlapping, "a stage is 2.5 to 5.0 m wide");
    // An area hanging off the edge, a colour that is not one, a sign too long to letter.
    let second = kept_house();
    let last = second.areas.at(second.areas.length() - 1) ?? throw "no areas";
    last.z_m = second.deep_m - 1.0;
    second.roof.hex = "terracotta";
    second.sign = "Welcome, every one of you, to my house";
    let off = house_problems(second).join("\n");
    assert.contains(off, "runs outside the house");
    assert.contains(off, `the roof colour "terracotta" is not #rrggbb`);
    assert.contains(off, "should be 1 to 22 letters")
}

test "a house needs its stage, its practice floor and a microphone on one of them" {
    let house = kept_house();
    house.areas
        = house.areas.filter((a) -> {
            a.kind != AreaKind.Stage
        });
    let problems = house_problems(house).join("\n");
    assert.contains(problems, "exactly one Stage, not 0");
    assert.contains(
        problems,
        `the microphone stands in "the tablao", which is not one of the areas`,
    );
    assert.contains(problems, `the arches belong to "the tablao", which is not one of the areas`);
    let quiet = kept_house();
    quiet.microphone_area = "the quiet room";
    assert.contains(
        house_problems(quiet).join("\n"),
        "it belongs on the stage or the practice floor",
    );
    let tiny = kept_house();
    tiny.wide_m = 30.0;
    tiny.areas = tiny.areas.slice(0, 2);
    let small = house_problems(tiny).join("\n");
    assert.contains(small, "it is 8.0 to 14.0 m wide");
    assert.contains(small, "a house has 3 to 6 areas, not 2")
}

test "DesignHouse is told who the toon is, the rules of the plan, and what they asked for" {
    let canon = baml.fs.read(CANON_FILE);
    let who = who_is("Flamenco Dancer", canon);
    assert.contains(who, "A star, about to premiere");
    assert.equal(
        who_is("Somebody New", canon),
        "A toon of this world. Nothing more is written about them yet.",
    );
    let asked = DesignHouse@spec(
        "Flamenco Dancer",
        "a long red ruffled skirt",
        who,
        "WHAT THEY ASKED FOR, IN THEIR OWN WORDS\na balcony",
    )
        .prompt()
        .to_string();
    assert.contains(asked, "THE TOON: Flamenco Dancer");
    assert.contains(asked, "a long red ruffled skirt");
    assert.contains(asked, "A star, about to premiere");
    assert.contains(asked, "Exactly one Stage");
    assert.contains(asked, "the front is at z = deep_m");
    assert.contains(asked, "a balcony");
    // The schema the reply must fit is in the prompt: the kinds of area, and how it faces.
    assert.contains(asked, "PracticeFloor");
    assert.contains(asked, "the spawn spot")
}

test "a house's failures say what happened, and a new house never takes an old one's folder" {
    let rejected = HouseRejected { toon: "Flamenco Dancer", problems: ["a house has 3 to 6 areas, not 9"] };
    assert.contains(`${rejected}`, "cannot be built as designed: a house has 3 to 6 areas, not 9");
    let unknown = buy_house("nobody-at-all", runs = "sets") catch (e) {
        let missing: ToonUnknown => `${missing}`,
    };
    assert.contains(unknown, `no run in sets is named for "nobody-at-all"`);
    assert.equal(free_house_folder("Casa de la Rosa"), "casa-de-la-rosa-2");
    assert.equal(free_house_folder("A House Nobody Has"), "a-house-nobody-has")
}
