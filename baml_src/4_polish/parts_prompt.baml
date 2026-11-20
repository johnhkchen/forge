// Step 4b: Claude finds the object's parts, so each can be remeshed on its
// own. TRELLIS.2 fuses touching parts into one surface (a kettle's lid, knob
// and spout are one piece with the body), and nothing in the mesh says where
// one ends; Claude knows what the object is and can look at it.
//
// Claude only places boxes and checks them; the cutting is done later by
// .claude/skills/tidy-mesh/scripts/split.py, from the saved plan. The
// scripts it works with are passed in as `tools` (see tools.baml).

class PartBox {
    name: string @description(
        "Short plain name, like 'lid', 'knob', 'spout'. Boxes with the same name make one part",
    ),
    why: string @description("One line: what this part is and why it's separate"),
    min: float[] @description("Box corner [x, y, z] in meters, world coordinates"),
    max: float[] @description("Opposite box corner [x, y, z] in meters"),
    // Optional so plans from earlier runs still load.
    turn: float[]? @description(
        "Only for a tilted box: degrees to turn it about its own center, [x, y, z]. Leave out for a straight box",
    ),
    wraps: bool? @description("true only if the part goes all the way around the body (a belt, a wrist band)"),
}

class PartsPlan {
    parts: PartBox[] @description(
        "Parts to cut out of the body, smallest/innermost first. Empty if the object is one piece",
    ),
    notes: string @description("Anything that didn't separate cleanly, or 'none'"),
}

function FindParts(brief: ObjectBrief, mesh: string, tools: string) -> PartsPlan {
    client: Finisher
    prompt: `
        ${role("system")}
        You are a careful 3D artist working in a live Blender session through
        the blender MCP tools. Every call freezes the person's screen until it
        returns, so keep calls light: use \`look\` with shading "material"
        and max_size 512, never "rendered".

        ${tool_rules()}

        ${role("user")}
        We're about to rebuild this object's mesh with clean quads. The mesh
        came from an image-to-3D model that fused touching parts into one
        surface. Remeshing works much better part by part, so find the parts.

        The object: ${brief.name}. ${brief.description}
        Its materials, by part:
        ${brief.materials.map((m) -> { `- ${m.part}: ${m.look}` }).join("\n")}

        1. Bring it in: open.py with "mesh": "${mesh}", "scene": "Parts" and
           "name": "Parts mesh", so nothing else in the file is touched. It
           prints the bounding box. Then \`look\` (mode "angles", shading
           "material").
        2. Decide which parts a modeler would build as separate pieces: things
           that sit on, stick out of, or attach to the main body (a lid, a
           knob, a spout, a handle, legs, a strap). The main body itself
           needs no box. Pieces that are already separate in the mesh still
           get a box if they are a distinct part.
        3. Find where each part starts and stops. measure.py does this in
           one call: give it a rough box per part and "along" to get the
           part's middle and width slice by slice (a wrist band shows as a
           step in width along the arm; a lid as a step along z). To see a
           small part up close, frame.py puts a box around it for \`look\`
           (target ["Look: <name>"], no distance).
        4. For each part, choose a box (world coordinates, meters) that
           contains that part and as little of anything else as possible.
           Faces go to the FIRST box that contains their center, so list
           small parts that sit inside bigger ones first (a knob before the
           lid it sits on). Where one straight box can't follow a part:
           give two or three boxes the same name (they become one part),
           tilt a box with "turn" (a belt that sits lower in front), and
           mark a part that goes all the way around the body with
           "wraps": True, so the body beyond it stays body.
        5. Check your boxes with split.py, mode "color", with "parts" set to
           your list (the same fields you will report: name, min, max, and
           turn or wraps where used). It paints each part a color (the body
           stays gray) and prints each part's share of the surface. Then
           \`look\` (mode "angles", shading "material") and adjust the boxes
           until every part is one clean color with no stray patches, and
           nothing bleeds into its neighbor. At most 4 rounds.
        6. Leave the "Parts" scene as it is (the person may want to see it).

        Tools:

        ${tools}

        ${ctx.output_format()}
    `
}
