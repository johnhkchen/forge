// Step 4b: Claude finds the object's parts, so each can be remeshed on its
// own. TRELLIS.2 fuses touching parts into one surface (a kettle's lid, knob
// and spout are one piece with the body), and nothing in the mesh says where
// one ends; Claude knows what the object is and can look at it.
//
// Claude only places boxes and checks them; the cutting is done later by
// .claude/skills/tidy-mesh/scripts/split.py, from the saved plan.

class PartBox {
    name: string @description("Short plain name, like 'lid', 'knob', 'spout'")
    why: string @description("One line: what this part is and why it's separate")
    min: float[] @description("Box corner [x, y, z] in meters, world coordinates")
    max: float[] @description("Opposite box corner [x, y, z] in meters")
}

class PartsPlan {
    parts: PartBox[] @description("Parts to cut out of the body, smallest/innermost first. Empty if the object is one piece")
    notes: string @description("Anything that didn't separate cleanly, or 'none'")
}

function FindParts(brief: ObjectBrief, mesh: string, split_script: string) -> PartsPlan {
    client: Finisher
    prompt: `
        ${role("system")}
        You are a careful 3D artist working in a live Blender session through
        the blender MCP tools. Every call freezes the person's screen until it
        returns, so keep calls light: use \`look\` with shading "material"
        and max_size 512, never "rendered".

        ${role("user")}
        We're about to rebuild this object's mesh with clean quads. The mesh
        came from an image-to-3D model that fused touching parts into one
        surface. Remeshing works much better part by part, so find the parts.

        The object: ${brief.name}. ${brief.description}
        Its materials, by part:
        ${brief.materials.map((m) -> { `- ${m.part}: ${m.look}` }).join("\n")}

        1. Make a new scene named "Parts" (bpy.data.scenes.new, then set it
           as the window's scene) so nothing else is touched, and import
           ${mesh} into it with bpy.ops.import_scene.gltf. Print its
           dimensions and bounding box.
        2. Decide which parts a modeler would build as separate pieces: things
           that sit on, stick out of, or attach to the main body (a lid, a
           knob, a spout, a handle, legs, a strap). The main body itself
           needs no box. Pieces that are already separate in the mesh still
           get a box if they are a distinct part.
        3. For each part, choose one axis-aligned box (world coordinates,
           meters) that contains that part and as little of anything else as
           possible. Faces go to the FIRST box that contains their center, so
           list small parts that sit inside bigger ones first (a knob before
           the lid it sits on).
        4. Check your boxes with this script: send it whole through
           execute_blender_code, with PARAMS set to your parts and
           mode "color". It paints each part a color (the body stays gray)
           and prints each part's share of the surface. Then \`look\` (mode
           "angles", shading "material") and adjust the boxes until every part
           is one clean color with no stray patches, and nothing bleeds into
           its neighbor. At most 4 rounds.

        ${split_script}

        5. Leave the "Parts" scene as it is (the person may want to see it).

        ${ctx.output_format()}
    `
}
