// Step 4c: Claude blocks out a low-poly version, the way artists built
// early real-time models (think Warcraft): simple shapes sized to each part,
// a few hundred triangles in total. No reduction algorithm gets there from a
// 300k-triangle scan-like mesh: below ~1k triangles they crumple or drop
// thin parts. The detail comes back as a baked texture (profile "lowpoly").
//
// Claude measures the detailed mesh (measure.py), describes the pieces as
// data, and build.py makes them; the scripts are passed in as `tools`
// (see tools.baml).

class LowPolyPart {
    name: string @description("The part, like 'body' or 'spout'"),
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
) -> LowPolyReport {
    client: Finisher
    prompt: `
        ${role("system")}
        You are a low-poly 3D artist in the style of early real-time games
        (Warcraft III, early World of Warcraft), working in a live Blender
        session through the blender MCP tools. Every call freezes the
        person's screen until it returns, so keep calls light: \`look\` with
        shading "solid" or "material", max_size 512, never "rendered".

        ${TOOL_RULES}

        ${role("user")}
        Build a low-poly version of this object: ${brief.name}.
        ${brief.description}

        Parts already identified (boxes in world meters; the main body is
        whatever isn't in a box):
        ${parts}

        ${if (brief.character ?? false) { "It is a character in a T-pose, to be rigged later: keep the T-pose, build it symmetric (model the +X half and set \"mirror\": True, if the reference is centered on x = 0), and give elbows, knees, shoulders, hips and the neck an extra ring so they can bend. Keep hands and feet as simple blocks; no separate fingers." } else { "" }}
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
           "only_this_object": true. Leave the "Low poly" scene for the
           person to see.

        Tools:

        ${tools}

        ${ctx.output_format()}
    `
}
