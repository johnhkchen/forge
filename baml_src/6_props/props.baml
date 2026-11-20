// Step 6 (only when asked): each prop in a character's gear list becomes a
// small run of its own, linked to the character.
//
//   runs/<character>/props.json        which prop goes on which socket, and its run
//   runs/<prop>/brief.json             the prop's own brief
//   runs/<prop>/prop_of.json           the way back: whose prop it is
//
// The prop's run is an ordinary run: picture, mesh, Blender, low poly,
// profiles. So once its brief is saved, `just resume runs/<prop>` makes it,
// and a stopped one picks up where it left off.

/// Which props to make: none, the things carried in a hand, or also the
/// rigid things fixed to one spot (a hat, a backpack). Worn clothing is
/// never a prop; it is built on the character as gear that comes off.
type PropsWanted = "none" | "held" | "all";

/// The points a block-out marks for props (build.py, "sockets").
type Socket = "hand_right" | "hand_left" | "head" | "back" | "hip";

/// The switch as typed on the command line (`--props held`), checked.
function props_wanted(text: string) -> PropsWanted throws baml.errors.InvalidArgument {
    match (text) {
        "none" => "none",
        "held" => "held",
        "all" => "all",
        _ => {
            throw baml.errors.InvalidArgument { message: `--props is none, held or all, not "${text}"` }
        },
    }
}

/// One prop of a character (an entry of props.json).
class PropLink {
    gear: string,
    kind: "worn" | "attached" | "held",
    socket: Socket,
    grip: string,
    name: string,
    run: string,
}

/// A character's props.json.
class PropsPlan {
    character: string,
    props: PropLink[],
}

/// A prop's prop_of.json.
class PropOf {
    character: string,
    gear: string,
    socket: Socket,
    grip: string,
}

/// The character's socket a gear item goes on: its slot if that is a
/// socket, otherwise the nearest one.
function socket_for(item: GearItem) -> Socket {
    match (item.slot) {
        "hand_left" => "hand_left",
        "hand_right" | "hands" | "arms" => "hand_right",
        "head" | "face" | "neck" => "head",
        "back" | "torso" => "back",
        _ => "hip",
    }
}

/// The gear items that become props.
function props_in(brief: ObjectBrief, wanted: PropsWanted) -> GearItem[] {
    (brief.gear ?? []).filter((g) -> {
        match (wanted) {
            "none" => false,
            "held" => g.kind == "held",
            "all" => g.kind != "worn",
        }
    })
}

function prop_link(item: GearItem, prop: PropBrief, dir: string) -> PropLink {
    PropLink {
        gear: item.name,
        kind: item.kind,
        socket: socket_for(item),
        grip: prop.grip,
        name: prop.brief.name,
        run: dir,
    }
}

/// Writes a brief for each prop, starts a run folder for it, and saves the
/// links as props.json in the character's run. Makes nothing yet.
function plan_props(brief: ObjectBrief, run: Run, wanted: PropsWanted) -> PropsPlan {
    let links = props_in(brief, wanted).map((item) -> {
        //# Opus writes the prop's brief
        log.info(`props: asking Opus about the ${item.name}`);
        let prop = DescribeProp(brief, item, socket_for(item));
        let prop_run = Run.start(prop.brief.name);
        let link = prop_link(item, prop, prop_run.dir);
        prop_run.save("brief.json", prop.brief);
        prop_run.save(
            "prop_of.json",
            PropOf { character: run.dir, gear: link.gear, socket: link.socket, grip: link.grip },
        );
        log.info(`props: ${item.name} -> ${prop_run.dir}, on ${link.socket}`);
        link
    });
    let plan = PropsPlan { character: run.dir, props: links };
    run.save("props.json", plan);
    plan
}

/// Plans the character's props if that hasn't been done, then makes each
/// one: the whole pipeline again, on the prop's own run folder.
function make_props(brief: ObjectBrief, run: Run, wanted: PropsWanted) -> PropsPlan {
    let plan = if (run.has("props.json")) {
        run.load<PropsPlan>("props.json")
    } else {
        plan_props(brief, run, wanted)
    };
    for (let link in plan.props) {
        //# Each prop is a run of its own
        log.info(`props: making the ${link.gear} (${link.run})`);
        let prop_run = Run.open(link.run);
        finish(prop_run, prop_run.load<ObjectBrief>("brief.json"));
    }
    plan
}

/// Only the briefs and the links, for a character that is already made:
/// `baml run props -- --dir runs/<character>`, then `just resume` each prop.
function props(dir: string, wanted: string = "held") -> PropsPlan {
    let run = Run.open(dir);
    plan_props(run.load<ObjectBrief>("brief.json"), run, props_wanted(wanted))
}

/// A character brief with only its gear filled in.
function props_test_brief() -> ObjectBrief {
    ObjectBrief {
        name: "Rainy Day Clerk",
        description: "A clerk.",
        subject: "A clerk.",
        materials: [],
        size_m: 1.7,
        character: true,
        lowpoly_triangles: 1000,
        gear: [
            GearItem { name: "tweed coat", kind: "worn", slot: "torso", look: "brown tweed" },
            GearItem { name: "bowler hat", kind: "attached", slot: "head", look: "black felt" },
            GearItem {
                name: "umbrella",
                kind: "held",
                slot: "hand_right",
                look: "black, furled, cane handle",
            },
        ],
        lowpoly_style: "faceted, flat colors",
    }
}

test "props are the held things; `all` adds what is fixed to one spot; worn clothing never" {
    let brief = props_test_brief();
    let names = (wanted: PropsWanted) -> {
        props_in(brief, wanted).map((g) -> {
            g.name
        })
    };
    assert.equal(props_wanted("held"), "held");
    assert.equal(names("none"), []);
    assert.equal(names("held"), ["umbrella"]);
    assert.equal(names("all"), ["bowler hat", "umbrella"])
}

test "a gear item's slot picks one of the five sockets" {
    let on = (slot: string) -> {
        socket_for(GearItem { name: "x", kind: "attached", slot: slot, look: "" })
    };
    assert.equal(on("hand_left"), "hand_left");
    assert.equal(on("face"), "head");
    assert.equal(on("torso"), "back");
    assert.equal(on("legs"), "hip")
}

test "DescribeProp parses a prop's brief, and the link records where it goes" {
    let reply = `
        {
          "brief": {
            "name": "Furled Black Umbrella",
            "description": "A furled umbrella with a cane handle.",
            "subject": "A tightly furled black umbrella with a curved wooden handle.",
            "materials": [{ "part": "canopy", "look": "black cloth", "metallic": false }],
            "size_m": 0.9,
            "character": false,
            "lowpoly_triangles": 120,
            "gear": [],
            "lowpoly_style": "faceted, flat colors"
          },
          "grip": "the curved handle, at its straight part"
        }
    `;
    let brief = props_test_brief();
    let umbrella = props_in(brief, "held").at(0) ?? throw baml.errors.InvalidArgument { message: "no held gear" };
    let spec = DescribeProp@spec(brief, umbrella, socket_for(umbrella));
    let asked = spec.prompt().to_string();
    assert.contains(
        asked,
        "The prop: umbrella (held, goes on the character's hand_right). black, furled, cane handle",
    );
    assert.contains(asked, "Rainy Day Clerk, 1.7 m tall");
    let prop = spec.parse(reply);
    assert.equal(prop.brief.character, false);
    let link = prop_link(umbrella, prop, "runs/2026-11-20T15-00-00-furled-black-umbrella");
    assert.equal(link.socket, "hand_right");
    assert.equal(link.name, "Furled Black Umbrella");
    assert.equal(link.grip, "the curved handle, at its straight part")
}
