// Offline tests for the base-body step: which gear comes off, what Codex is
// asked, how garment.py's result is read, and what the block-out is told.

/// The flamenco dancer's brief, cut down to what this step reads.
function dancer_brief() -> ObjectBrief {
    ObjectBrief {
        name: "Flamenco Dancer",
        description: "A flamenco dancer in a T-pose.",
        subject: "A dancer.",
        materials: [],
        size_m: 1.65,
        character: true,
        lowpoly_triangles: 1400,
        gear: [
            GearItem {
                name: "sleeveless top",
                kind: "worn",
                slot: "torso",
                look: "close-fitting black stretch top",
            },
            GearItem {
                name: "ruffled skirt",
                kind: "worn",
                slot: "hip",
                look: "long red skirt with white polka dots",
            },
            GearItem {
                name: "heeled dance shoes",
                kind: "worn",
                slot: "feet",
                look: "black leather shoes",
            },
            GearItem { name: "fan", kind: "held", slot: "hand_right", look: "a folded fan" },
        ],
        hidden_by: ["ruffled skirt"],
        lowpoly_style: null,
    }
}

test "Describe's reply can name the gear that hides the body" {
    let reply = `
        {
          "name": "Flamenco Dancer",
          "description": "A dancer.",
          "subject": "A dancer in a long skirt.",
          "materials": [],
          "size_m": 1.65,
          "character": true,
          "gear": [
            { "name": "ruffled skirt", "kind": "worn", "slot": "hip", "look": "long red skirt" },
            { "name": "sleeveless top", "kind": "worn", "slot": "torso", "look": "black top" }
          ],
          "hidden_by": ["ruffled skirt"]
        }
    `;
    let brief = Describe@spec("a flamenco dancer").parse(reply);
    assert.equal(brief.hidden_by, ["ruffled skirt"]);
    assert.equal(
        hidden_gear(brief).map((g) -> {
            g.slot
        }),
        ["hip"],
    );
    // the prompt tells Opus when to fill it, and when not to
    let asked = Describe@spec("a flamenco dancer").prompt().to_string();
    assert.contains(asked, "name it in hidden_by");
    assert.contains(asked, "Tight tops and trousers hide nothing");
    // a brief from before the field still loads, and nothing comes off
    let old = Describe@spec("x").parse(
        `{"name": "Troll", "description": "d", "subject": "s", "materials": [], "size_m": 2.6, "character": true}`,
    );
    assert.equal(old.hidden_by, null);
    assert.equal(hidden_gear(old).length(), 0)
}

test "hidden gear: from the brief, forced by name, or none" {
    let dancer = dancer_brief();
    let names = (items: GearItem[]) -> {
        items
            .map((g) -> {
                g.name
            })
            .join("|")
    };
    assert.equal(names(hidden_gear(dancer)), "ruffled skirt");
    assert.equal(names(hidden_gear(dancer, undress = "none")), "");
    // forced: any worn gear by name, whatever the brief says; spaces and case don't matter
    assert.equal(
        names(hidden_gear(dancer, undress = " Sleeveless Top , ruffled skirt")),
        "sleeveless top|ruffled skirt",
    );
    // a forced name the brief doesn't list, or something only held, is an error
    let missing = hidden_gear(dancer, undress = "cloak") catch (e) {
        let f: UndressFailed => [GearItem { name: f.step, kind: "worn", slot: "", look: "" }],
    };
    assert.equal(names(missing), "choosing the gear");
    let none: GearItem[] = [];
    let held = hidden_gear(dancer, undress = "fan") catch (e) {
        UndressFailed => none,
    };
    assert.equal(held.length(), 0);
    // a name the brief's own hidden_by gets wrong is skipped, not fatal
    let slip = ObjectBrief { ...dancer, hidden_by: ["ballgown", "ruffled skirt"] };
    assert.equal(names(hidden_gear(slip)), "ruffled skirt");
    // an object never has a base body
    let prop = ObjectBrief { ...dancer, character: false };
    assert.equal(hidden_gear(prop).length(), 0)
}

test "the edit request keeps everything, takes off the hiding gear and shows what it hid" {
    let dancer = dancer_brief();
    let asked = base_request(dancer, hidden_gear(dancer));
    assert.contains(asked, "edit the attached picture");
    assert.contains(asked, "The head,\nhands and feet stay exactly where they are in the frame.");
    assert.contains(asked, "- the ruffled skirt (long red skirt with white polka dots)");
    assert.contains(asked, "the hips, thighs, knees and calves");
    assert.contains(asked, "skin-tight matte black base");
    // what stays on is named; what is only held isn't in the picture at all
    assert.contains(asked, "unchanged: sleeveless top, heeled dance shoes.");
    assert.is_true(!asked.includes("fan"));
    assert.is_true(!asked.includes("An earlier try"));
    // two garments: both listed, each body part once
    let robed = ObjectBrief {
        ...dancer,
        gear: [
            GearItem {
                name: "wool robe",
                kind: "worn",
                slot: "torso",
                look: "floor-length gray robe",
            },
            GearItem { name: "deep hood", kind: "worn", slot: "head", look: "a gray hood" },
            GearItem { name: "leggings", kind: "worn", slot: "legs", look: "gray" },
        ],
        hidden_by: ["wool robe", "deep hood"],
    };
    let both = base_request(robed, hidden_gear(robed), note = "An earlier try was turned down: it moved.");
    assert.contains(both, "- the wool robe (floor-length gray robe)\n- the deep hood (a gray hood)");
    assert.contains(both, "the chest, waist and back, the head, hair and ears");
    assert.contains(both, "unchanged: leggings.");
    assert.contains(both, "An earlier try was turned down: it moved.")
}

/// garment.py's RESULT on the flamenco dancer (20 Nov 2026), trimmed.
const DANCER_CUT = `
    {"ok": true, "why": [],
     "pictures": {"ok": true, "why": [], "compared_at": [384, 384], "changed_pct": 66.9, "slivers_pct": 0.16,
       "edges": {"left": {"moved_pct": 0.0, "garment_reaches_it": false}, "right": {"moved_pct": 0.0, "garment_reaches_it": false},
                 "top": {"moved_pct": 0.0, "garment_reaches_it": false}, "bottom": {"moved_pct": 0.0, "garment_reaches_it": false}}},
     "view": {"clothed": {"overlap_pct": 91.1, "color_off": 0.166, "stretch": 1.0, "mirrored": false},
              "base": {"overlap_pct": 87.7, "color_off": 0.087, "stretch": 0.9862, "mirrored": false}},
     "fit": {"ok": true, "why": [], "started_from": "as the meshes came", "points": 4202, "scale": 0.9979,
             "shift_pct": [0.15, -0.09, 0.16], "off_pct": {"median": 0.14, "p90": 0.61, "worst": 2.57},
             "off_pct_by_tenth_from_top": [0.1, 0.11, 0.16, 0.19, null, 0.06, null, null, null, 0.25], "before_pct": 0.16},
     "body": "/runs/dancer/base/body.glb",
     "votes": {"faces": 297106,
       "said_garment": {"picture": {"faces": 213688, "area_pct": 73.38}, "color": {"faces": 167029, "area_pct": 63.2},
                        "distance": {"faces": 168927, "area_pct": 64.69}},
       "agreement": {"picture + color + distance": {"faces": 131102, "area_pct": 55.07}, "picture + color": {"faces": 29366, "area_pct": 6.96},
                     "picture + distance": {"faces": 34745, "area_pct": 8.52}, "color + distance": {"faces": 814, "area_pct": 0.45},
                     "picture only": {"faces": 18475, "area_pct": 2.82}, "color only": {"faces": 5747, "area_pct": 0.72},
                     "distance only": {"faces": 2266, "area_pct": 0.64}, "none": {"faces": 74591, "area_pct": 24.8}},
       "two_or_more": {"faces": 196027, "area_pct": 71.01}},
     "cleanup": {"edge_faces_evened": 1854, "crumbs_dropped": {"pieces": 79, "faces": 9857},
                 "holes_closed": {"holes": 93, "faces": 1064}, "faces_grown_to_the_color_seam": 6762},
     "garments": [{"name": "ruffled skirt", "slot": "hip", "faces": 194512, "file": "/runs/dancer/base/cut/ruffled-skirt.glb",
                   "area_pct": 71.63, "pieces": 2, "top": 0.612, "bottom": 0.108,
                   "points_lifted_onto_the_body": 7884, "lifted_at_most_pct": 1.16}],
     "garment_area_pct": 71.63,
     "overlay": ["/runs/dancer/base/votes-front.png"]}
`;

test "garment.py's result decodes, with every vote and the fit" {
    let report = baml.json.decode<CutReport>(DANCER_CUT);
    assert.is_true(report.ok);
    assert.approx_equal(report.fit?.off_pct.median ?? 9.0, 0.14, 0.001);
    assert.equal(report.votes?.said_garment.get("color")?.faces, 167029);
    assert.equal(report.votes?.agreement.get("picture + color")?.faces, 29366);
    assert.equal(report.cleanup?.crumbs_dropped.get("pieces"), 79);
    assert.equal(report.garments?.at(0)?.name, "ruffled skirt");
    assert.approx_equal(report.garments?.at(0)?.top ?? 0.0, 0.612, 0.0001);
    assert.contains(report.numbers(), "uncovered parts 0.14% of the height apart typically");
    assert.contains(report.numbers(), "edges moved left 0.0%, right 0.0%, top 0.0%, bottom 0.0%")
}

test "a picture-only check decodes, and a failed one says why with its numbers" {
    let report = baml.json.decode<CutReport>(
        `
            {"ok": false, "why": ["the figure's bottom edge moved 4.2% of its height between the pictures (limit 2.0)"],
             "pictures": {"ok": false, "why": ["the figure's bottom edge moved 4.2% of its height between the pictures (limit 2.0)"],
               "compared_at": [384, 384], "changed_pct": 71.0, "slivers_pct": 9.5,
               "edges": {"bottom": {"moved_pct": 4.2, "garment_reaches_it": false}}}}
        `,
    );
    assert.is_true(!report.pictures.ok);
    assert.equal(report.fit, null);
    let off = BaseBodyMisaligned { stage: "pictures", why: report.why, numbers: report.numbers() };
    assert.contains(off.to_string(), "doesn't line up with the clothed character (pictures)");
    assert.contains(off.to_string(), "bottom edge moved 4.2%");
    assert.contains(off.to_string(), "9.5% in slivers")
}

test "with a base body, the block-out measures the body on it and each hidden garment on its cut" {
    let dancer = dancer_brief();
    let refs = BaseRefs {
        body: "/runs/dancer/base/final.glb",
        garments: [GarmentRef { name: "ruffled skirt", mesh: "/runs/dancer/garments/ruffled-skirt.glb" }],
    };
    let asked = BlockOut@spec(
        dancer,
        "final.glb",
        "lowpoly.glb",
        "{}",
        tools(lowpoly_tools(dancer)),
        lowpoly_budget(dancer),
        base = base_steps(refs),
    )
        .prompt()
        .to_string();
    assert.contains(asked, "This character has a real body under its clothes");
    assert.contains(asked, "the true body: /runs/dancer/base/final.glb");
    assert.contains(
        asked,
        "- the ruffled skirt alone, cut out of the reference: /runs/dancer/garments/ruffled-skirt.glb",
    );
    assert.contains(asked, `"object": "Body" in measure.py`);
    assert.contains(asked, `"add": True`);
    assert.contains(asked, `"reference": "Reference"`);
    // the gear and fit tags from the clothing work are still asked for
    assert.contains(asked, `"gear": "<the item's name>"`);
    assert.contains(asked, `"loose" for cloth that hangs off it`);
    assert.contains(asked, "drape.py once");
    // and open.py's card says how to add a mesh beside another
    assert.contains(asked, `"add": False`);
    // without a base body the prompt is as it was
    let plain = BlockOut@spec(dancer, "final.glb", "lowpoly.glb", "{}", tools(lowpoly_tools(dancer)), lowpoly_budget(dancer))
        .prompt()
        .to_string();
    assert.is_true(!plain.includes("real body under its clothes"));
    assert.equal(base_steps(null), "")
}
