// Step 4c: Claude blocks out a low-poly version, the way artists built
// early real-time models (think Warcraft): simple shapes sized to each part,
// a few hundred triangles in total. No reduction algorithm gets there from a
// 300k-triangle scan-like mesh: below ~1k triangles they crumple or drop
// thin parts. The detail comes back as a baked texture (profile "lowpoly").

class LowPolyPart {
    name: string @description("The part, like 'body' or 'spout'")
    shape: string @description("How it was built, like '8-sided cylinder, top ring narrowed'")
    triangles: int
}

class LowPolyReport {
    triangles: int @description("Total triangles of the finished low-poly object")
    parts: LowPolyPart[]
    shape_typical: float @description("match.py shape_lost p95_%")
    shape_worst: float @description("match.py shape_lost max_%")
    notes: string @description("What reads well, and what was simplified away")
}

function BlockOut(brief: ObjectBrief, mesh: string, out: string, parts: string, match_script: string, budget: string) -> LowPolyReport {
    client: Finisher
    prompt: `
        ${role("system")}
        You are a low-poly 3D artist in the style of early real-time games
        (Warcraft III, early World of Warcraft), working in a live Blender
        session through the blender MCP tools. Every call freezes the
        person's screen until it returns, so keep calls light: \`look\` with
        shading "solid" or "material", max_size 512, never "rendered".

        ${role("user")}
        Build a low-poly version of this object: ${brief.name}.
        ${brief.description}

        Parts already identified (boxes in world meters; the main body is
        whatever isn't in a box):
        ${parts}

        ${if (brief.character ?? false) { "It is a character in a T-pose, to be rigged later: keep the T-pose, build it symmetric (model one half and mirror it across x = 0 if the reference is centered there), and give elbows, knees, shoulders, hips and the neck an extra edge loop so they can bend. Keep hands and feet as simple blocks; no separate fingers." } else { "" }}
        Style: ${brief.lowpoly_style ?? "early real-time game prop: clean simple shapes, smooth-shaded"}.

        1. Make a new scene "Low poly" (bpy.data.scenes.new, set it as the
           window's scene). Import ${mesh} with bpy.ops.import_scene.gltf,
           join its meshes into one object named "Reference", and print its
           bounding box. Do not move or scale it; build around it in place.
        2. Build each part from simple shapes, the way an artist would block
           it out: bpy.ops.mesh.primitive_cylinder_add / cone / cube /
           uv_sphere with few segments (6-12 around), then shape them with
           bmesh (scale rings to taper, move rings to bulge, bend a handle
           as a short chain of segments). Measure the reference's vertices
           inside each part's box to size and place the shapes.
           Budget: ${budget}. Spend them on the silhouette
           (outline, profile curves, things that stick out); flat or hidden
           areas get as few as possible. Parts may overlap where they join,
           as on any game prop. No floating or inside-out faces.
        3. Join all parts into one object named "Reference (light)", apply
           its transforms, recalculate normals outward, and print the
           triangle count.
        4. Check it two ways and improve, at most 4 rounds:
           - \`look\` (mode "angles", shading "solid") with both objects in
             view, then with only yours; compare outline and proportions.
           - run this script through execute_blender_code unchanged (it
             finds both objects by name) and read shape_lost: aim for p95
             under 2.5% and max under 8% of the object's size.

        ${match_script}

        5. Export only "Reference (light)" to ${out}:
           bpy.ops.export_scene.gltf(filepath=..., export_format="GLB",
           use_selection=True, export_apply=True, export_materials="NONE").
           Leave the "Low poly" scene for the person to see.

        ${ctx.output_format()}
    `
}
