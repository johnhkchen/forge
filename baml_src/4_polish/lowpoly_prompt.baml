// Step 4c: Claude blocks out a low-poly version, the way artists built
// early real-time models (think Warcraft): simple shapes sized to each part,
// a few hundred triangles in total. No reduction algorithm gets there from a
// 300k-triangle scan-like mesh: below ~1k triangles they crumple or drop
// thin parts. The detail comes back as a baked texture (profile "lowpoly").
//
// Claude measures the detailed mesh (measure.py), describes the pieces as
// data, and build.py makes them; the scripts are passed in as `tools`
// (see tools.baml).
//
// A character also gets a face: left to itself Claude spends the triangles
// on the outline and builds the head as a plain loft (the first troll's was
// 54 triangles of 1,254, with no brow, eyes, nose or mouth). face.py finds
// the features on the detailed head and prints a "head" piece for build.py.
//
// And its gear comes off: a game has to show the character without the coat
// or swap the boots. So the body is built whole, each gear item from the
// brief is a piece of its own over it, and the points props attach to
// (sockets) are marked. export.py writes them as separate named meshes.
//
// And its clothes sit on it: Claude builds each piece where the picture shows
// it and says how it is worn ("fit": tight, loose or stiff); drape.py then
// lays the pieces on the body, so Claude doesn't have to chase a gap of a
// centimeter by hand, and loose cloth is left hanging to swing later.

// And when clothes hide the body, the body isn't guessed: such a character
// has a base body made from a second picture without them, and each hiding
// garment cut out of the clothed mesh (2b_undress). Body pieces are then
// measured on the base body and each hidden garment on its own cut.

/// A character's base body and cut garments, in finished space.
class BaseRefs {
    body: string,
    garments: GarmentRef[],
}

class GarmentRef {
    name: string,
    mesh: string,
}

/// The base-body part of a character's block-out: where to measure the body
/// and the clothes that hide it. Empty when the run has no base body.
function base_steps(base: BaseRefs?) -> string {
    if (base == null) {
        return "";
    }
    let names = base.garments
        .map((g) -> {
            g.name
        })
        .join(", ");
    `
        This character has a real body under its clothes. The reference was
        made with the clothes on, so under the ${names} it only guesses at
        the body. These meshes stand in exactly the same place and size as
        the reference; they were made from a second picture with those
        clothes off:
        - the base body, the true body: ${base.body}
        ${base.garments.map((g) -> { `- the ${g.name} alone, cut out of the reference: ${g.mesh}` }).join("\n")}
        Use them like this:
        - In step 1, after the reference, bring each in with open.py and
          "add": True (same "scene"; don't move or scale them): the base
          body as "Body", each garment as "Garment: <its name>".
        - In step 2, read the body off the base body: "object": "Body" in
          landmarks.py. Anything of the body you measure yourself, measure
          there too: "object": "Body" in measure.py. Don't take the body's
          shape from the reference
          where the ${names} cover it: what is there is cloth, not body.
          A body read off the base body needs no "under" for the ${names}.
        - Measure each of the ${names} on its own mesh ("object": "Garment:
          <its name>") and build that gear piece from those rows. The mesh
          is that garment and nothing else, so the rows are the cloth
          itself: its top edge (a waistband, a collar), its widest part,
          its hem. It keeps its "gear" and "fit" tags like any other piece.
        - Everything else (the head and face.py, gear that hides nothing) is
          measured on the reference as before: pass "object": "Reference"
          to measure.py and face.py for those, and "reference": "Reference"
          to build.py every time, now that it isn't the only mesh in the
          scene.
        - The base body can be the bigger mesh, so a tool left to pick "the
          largest visible mesh" may pick the wrong one. While these meshes
          are in the scene, always name the object a tool works on.
        - Hide "Body" and the "Garment: ..." meshes (hide_viewport = True)
          before you \`look\` at your model beside the reference. To check
          the body alone, show "Body" and hide the reference instead.
        - Say in your notes that the body was measured on the base body.
    `
}

/// What a character needs on top of a prop: a pose that can be rigged, and
/// a face that can be read.
const CHARACTER_STEPS = `
    It is a character in a T-pose, to be rigged later: keep the T-pose, and
    build what you build yourself symmetric (model the +X half and set
    "mirror": True, if the reference is centered on x = 0).

    Its body is a body, not a stack of tubes. Don't block out the trunk,
    neck, arms, hands, legs and feet by hand:
    - In step 2, once you have the head's box, run landmarks.py with it as
      "head". It finds the chin, neck, shoulders, armpits, chest, waist,
      hips, crotch, elbows, wrists, knees and ankles, reads the body's own
      shape all the way along, and prints a "body" piece. \`look\` at its
      marks (mode "angles", target ["Reference", "Look: landmarks"]).
    - In step 3 that "body" piece goes into build.py's "parts" as it is.
      build.py makes it a trunk with a ribcage, a waist and a pelvis, a
      neck, arms with a shoulder cap, hands with a thumb, legs with a knee
      and a calf, and feet with a heel and toes: about 900 triangles, with
      three rings at each elbow and knee so they bend. What you build
      yourself is the head, the hair, what the character grows (a tail,
      horns, spines) and what it wears.
    - Then check its anatomy against the picture, as you would a drawing:
      1. A landmark "found" by "usual proportion" is a guess. Put a wrong
         one right on the piece: "landmarks": {"knee": [x, y, z]}. On a
         body with its arms hanging, the elbow is level with the waist and
         the wrist with the crotch; the knee is halfway down the leg.
      2. Proportions: landmarks.py prints how many heads tall it is and
         how much of its height is leg and arm. Keep what the picture has
         (a cartoon's big head and short legs, a troll's long arms); don't
         pull it toward an average person.
      3. The trunk: shoulders against hips as in the picture, a waist
         between the ribcage and the pelvis, the chest in front, the
         shoulder blades and glutes behind.
      4. The limbs: a shoulder cap, an upper arm and a forearm that each
         swell and taper, a wrist; a thigh, a kneecap in front, a calf
         behind, an ankle.
      5. Hands end in one finger mass with a thumb forward of it; feet
         have a heel, an arch and toes, and lie flat on the floor. No
         separate fingers.
      6. The neck meets the head under the jaw and is no thinner or longer
         than the picture's, with a slope down to the shoulders.
    - Style goes on the piece, not into new shapes: "style": {"chunky":
      1.2} thickens the trunk and limbs (old RuneScape), "limbs": 0.9
      slims the limbs alone, "head": 1.15 grows the head and all that sits
      on it. "follow": 0.6 keeps cleaner, evener shapes (a mobile-clean or
      cartoon look); 1.0 follows every fold of the reference.
    - Where clothes cover the body, draw it in so it sits under them:
      "under": {"trunk": 0.012, "leg": 0.012, "foot": 0.03}, in meters
      ("arm" and "hand" too). Leave bare parts out.

    The face is what people look at, so the head is never a plain loft:
    - In step 2, measure a "head" box too, then run face.py with that box.
      It prints the head as one piece and draws a line at each feature;
      \`look\` (mode "angles", target ["Look: face"]) and correct any row
      whose line misses its brow, eyes, nose, mouth or chin.
    - In step 3, that "head" piece goes into build.py's "parts" with the
      rest. Add the ears, tusks, hair or beard the description names, and
      use its "color" as the skin color of the body pieces too. A hat,
      helmet or horns are pieces of their own.
    - Unless the style asks for flat colors, a texture is laid over this
      head afterwards, and the texture carries the eyes, brows and lips,
      painted from the character's picture. Then give the head piece
      "eyes": "flat", so no dark pocket is cut where the painted eye goes,
      and don't build eyes, eyebrows or lips as pieces of their own. What
      stands off the face (glasses, a mustache, an eye patch) is still a
      piece: keep it as thin and as small as on the reference, or it
      covers the face behind it.
    - In step 4, also \`look\` at the head alone (target ["Look: face"])
      front-on and from the side, next to the reference and without it. At
      the size the whole figure is seen, the brow, eyes, nose and mouth must
      still read; if they don't, raise "bold" or darken the colors. Say in
      your notes what reads on the face and what doesn't.
`;

/// The gear part of a character's block-out: a whole body, each gear item a
/// piece of its own over it, and sockets for the props. A character with no
/// gear list (a brief from before gear) still gets its sockets.
function gear_steps(brief: ObjectBrief) -> string {
    let gear = brief.gear ?? [];
    let built = gear.filter((g) -> {
        g.kind != "held"
    });
    let held = gear.filter((g) -> {
        g.kind == "held"
    });
    let sockets = `
        Mark where props attach: set "sockets": True in build.py. Its result
        gives five "sockets" (each palm, the top of the head, the upper back,
        the left hip). Check the hand ones sit in the palms and the head one
        on top of the head, not on a hat or a hump; move one that landed
        wrong with "sockets": {"head": [x, y, z]}.
    `;
    if (!built) {
        return sockets;
    }
    let tags = gear.map((g) -> {
        { "name": g.name, "kind": g.kind, "slot": g.slot }
    });
    `
        Its gear comes off: a game will show this character without its coat,
        or swap its boots. So build it in two layers:
        - The body first, whole: skin (or fur, or scales) everywhere, under
          the clothes too. Under a coat there is a chest and arms, under
          boots there are feet. The "body" piece from landmarks.py is that
          body; give it "under" where gear covers it. Hair, beards, horns,
          tails and tusks are body.
        - Then each gear item below as a piece or pieces of its own, built
          where the reference shows it, with "gear": "<the item's name>" on
          every piece of it. A piece with no "gear" is body.
        - Say how each gear piece is worn, with "fit" on the piece:
          "tight" for cloth that lies on the body (trousers, sleeves, a
          shirt, wraps, a mask), "loose" for cloth that hangs off it (a
          kilt, a skirt, a coat's skirts below the belt, a hood, a cape, a
          sash's ends), "stiff" for what keeps its own shape (boots, a hat,
          armor plates, a buckle, glasses). Build a coat as a tight piece
          down to the belt and a loose piece below it.
        - Leave loose pieces hanging the way they hang in the reference, at
          their full length and standing off the legs. Don't pull a kilt or
          a coat's skirts in to the thighs, and don't spend rounds closing
          small gaps between cloth and body: the next step does that.
        - The hidden body comes on top of the triangle budget, up to a
          quarter more; don't thin the pieces people see to pay for it.
        - Pass the list once as build.py's "gear" (below, ready to paste).
          The result then lists the "groups" it made (the body and one per
          gear item) and "gear_not_built", which should end up empty.
        Gear to build:
        ${built.map((g) -> { `- ${g.name} (${g.kind}, ${g.slot}): ${g.look}` }).join("\n")}
        build.py "gear": ${baml.json.stringify(tags)}
        - When the shape is right, and after your last build.py call, run
          drape.py once (it needs no settings). It lays every tight piece on
          the body, fits loose pieces where they rest and leaves them
          hanging below, and marks the skin the gear hides so it can't show
          through. Read its result: "pieces" says what each piece was taken
          for (a wrong one is put right with "fit" on the piece in build.py,
          then drape.py again), and "skin_showing_through" should be 0 or
          close to it. \`look\` once more, then export. build.py undoes
          drape.py, so it comes last.
        ${if (held) { `Held in the hand, made separately and not built here: ${held.map((g) -> { g.name }).join(", ")}. Leave the hands empty.` } else { "" }}

        ${sockets}
    `
}

class LowPolyPart {
    name: string @description("The part, like 'body' or 'spout'"),
    gear: string? @description(
        "For a piece of gear: the gear item it is, named exactly as in the gear list. Leave out for the body and for objects",
    ),
    fit: string? @description(
        "For a piece of gear: 'tight' (lies on the body), 'loose' (hangs off it) or 'stiff' (keeps its shape). Leave out for the body and for objects",
    ),
    shape: string @description("How it was built, like '8-sided loft, 5 rings, top ring narrowed'"),
    triangles: int,
}

class LowPolyReport {
    triangles: int @description("Total triangles of the finished low-poly object"),
    parts: LowPolyPart[],
    shape_typical: float @description("build.py's shape_lost p95_% from the last build"),
    shape_worst: float @description("build.py's shape_lost max_% from the last build"),
    notes: string @description("What reads well, and what was simplified away"),
}

function BlockOut(
    brief: ObjectBrief,
    mesh: string,
    out: string,
    parts: string,
    tools: string,
    budget: string,
    base: string = "",
) -> LowPolyReport {
    client: Finisher
    prompt: `
        ${role("system")}
        You are a low-poly 3D artist in the style of early real-time games
        (Warcraft III, early World of Warcraft), working in a live Blender
        session through the blender MCP tools. Every call freezes the
        person's screen until it returns, so keep calls light: \`look\` with
        shading "solid" or "material", max_size 512, never "rendered".

        ${tool_rules()}

        ${role("user")}
        Build a low-poly version of this object: ${brief.name}.
        ${brief.description}

        Parts already identified (boxes in world meters; the main body is
        whatever isn't in a box):
        ${parts}

        ${if (brief.character ?? false) { CHARACTER_STEPS } else { "" }}
        ${if (brief.character ?? false) { gear_steps(brief) } else { "" }}
        ${base}
        Style: ${brief.lowpoly_style ?? "early real-time game prop: clean simple shapes, smooth-shaded"}.

        1. Bring it in: open.py with "mesh": "${mesh}", "scene": "Low poly"
           and "name": "Reference". Do not move or scale it; build around it
           in place. Then \`look\` (mode "angles", shading "material").
        2. Measure before you build: one measure.py call with the parts
           above as "parts" and one "measure" entry per piece you plan
           ("part" for a listed part or "body", a "box" for anything else,
           like one arm or the head; "along" its long axis). The rows it
           prints are ready-made rings.
        3. Build every piece in one build.py call, the way an artist would
           block it out: lofts of 6-12 sides from the measured rows (a round
           body, lid or knob is a loft of round rings), tubes for bent bars,
           lumps for rocks. Give each piece a flat "color" from the
           reference. Budget: ${budget}. Spend them on the silhouette
           (outline, profile curves, things that stick out); flat or hidden
           areas get as few as possible. Parts may overlap where they join,
           as on any game prop; leave an end open ("caps") where it hides
           inside another piece.
        4. Check it two ways and improve, at most 4 rounds:
           - \`look\` (mode "angles", shading "material") with both objects
             in view, then with only yours (target ["Reference (light)"]);
             compare outline and proportions.
           - read build.py's result: "triangles" against the budget, and
             "shape_lost": aim for p95 under 2.5% and max under 8% of the
             object's size. "most_missing_at" says where the reference
             sticks out of your model, and each piece's "sticks_out_%" where
             yours sticks out of the reference.
           To change something, send build.py with only the pieces that
           change in "parts" (and "remove" for ones to drop); the rest stay.
        5. Export: export.py with "object": "Reference (light)" (or the
           name build.py printed, if it differs), "path": "${out}" and
           "materials": False. Its result must say
           "only_this_object": true (for a character with gear or sockets
           it writes one mesh per group and the sockets, and lists them).
           Leave the "Low poly" scene for the person to see.

        Tools:

        ${tools}

        ${ctx.output_format()}
    `
}
