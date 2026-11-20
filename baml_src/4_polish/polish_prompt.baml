// Step 4: Claude imports the raw TRELLIS.2 mesh into Blender, fixes what
// image-to-3D usually gets wrong, stages it, renders it, and saves it.
//
// It works in the user's live Blender through MCP, so every change is visible
// as it happens, and it checks its own work with the `look` tool against the
// picture the mesh was made from. The repeated work (import, sizing, cleanup,
// materials by area, staging, export) is done by scripts passed in as `tools`
// (see tools.baml).

class PolishReport {
    fixes: string[] @description(
        "Each change you made, in plain words, like 'Scaled to 0.45 m tall' or 'Set the rims to metallic'",
    ),
    problems: string[] @description(
        "Flaws you saw and could not fix, like 'The spout is fused to the body'. Empty if none",
    ),
    triangles: int @description("Triangle count of the finished object"),
    dimensions_m: float[] @description("Finished object's bounding box, [x, y, z] in meters"),
    score: int @description(
        "How closely the final render matches the reference picture, 1 (poor) to 5 (faithful)",
    ),
}

class PolishFiles {
    mesh: string,
    blend: string,
    glb: string,
    render: string,
}

function Polish(
    brief: ObjectBrief,
    reference: image,
    files: PolishFiles,
    tools: string,
) -> PolishReport {
    client: Finisher
    prompt: `
        ${role("system")}
        You are a careful 3D artist working in a live Blender session through
        the blender MCP tools. Work in small steps and check your work with
        \`look\`.

        Every tool call runs on Blender's main thread and freezes the person's
        screen until it returns, so keep each one light. Check your work with
        \`look\` using shading "material" or "solid" (instant). Use
        shading "rendered" only once, for the final check. Keep \`look\`
        images at max_size 512 unless you need fine detail.

        ${tool_rules()}

        ${role("user")}
        TRELLIS.2 just turned the attached picture into a raw textured mesh.
        Make it into a clean, well-staged asset.

        The object: ${brief.name}. ${brief.description}
        ${if (brief.character ?? false) { `Its standing height is about ${brief.size_m} m (arm span doesn't count).` } else { `Its largest dimension is about ${brief.size_m} m.` }}
        Materials:
        ${brief.materials.map((m) -> { `- ${m.part}: ${m.look}${if (m.metallic) { " (metal)" } else { "" }}` }).join("\n")}

        Reference picture (what the mesh should look like):
        ${reference}

        Do this, in order:
        1. Bring it in: open.py with "mesh": "${files.mesh}",
           "name": "${brief.name}" and "scene": "Finish" (a scene of its
           own, so nothing else in the file is touched). Report its
           triangle count.
        ${if (brief.character ?? false) { "This is a character in a T-pose: keep the pose exactly, feet flat on the ground, facing -Y." } else { "" }}
        2. Stand it up. Compare against the reference with \`look\` (mode
           "angles", shading "material"): it should stand upright the way
           the real object would and face -Y (Blender's front). Then one
           stand.py call does the rest: "turn" if it needs turning,
           "size": ${brief.size_m} with "size_of": ${if (brief.character ?? false) { `"height"` } else { `"largest"` }},
           and its defaults put the origin at the bottom center on z = 0,
           weld the vertices, drop loose bits, fix the normals, shade smooth
           at 30 degrees and add a Decimate modifier only above 400,000
           triangles. Do not remesh, and keep the UVs and textures intact.
        3. Materials, with retouch.py. Keep the baked base-color texture; do
           not repaint or replace textures. In "overall", set metallic and
           roughness so the surface reads like the list above: real metals
           metallic 1.0, everything else 0.0, most non-metals roughness
           0.6-0.95. Where materials differ (a metal band on a leather
           strap, a wooden handle on an iron pot), give each its own entry
           in "regions": a box around it, a color range, or both. The
           result's "texture_in" says how light and colorful the texture is
           inside each box; use it to pick the ranges, check the reach with
           "show", then turn "show" off.
        4. Textures, up close. The image-to-3D model bakes one texture over
           the whole object, so fine detail comes out soft and the sides the
           picture didn't show are invented. For each material, put a box
           around a telling spot with frame.py and \`look\` at it (mode
           "angles", shading "material", target ["Look: <name>"], max_size
           768, and no distance: a distance with a small target clips the
           view). Compare with the reference: color, contrast, sharpness,
           sheen, surface grain. Improve it through retouch.py: saturation
           and value for color, "color" to lift a dark smear or deepen a
           washed-out part, "bump" and "grain" for surface relief (keep them
           subtle), roughness for sheen, a little "subsurface" (0.05-0.2)
           for soft organic materials (bread, wax, fruit, skin, soap). Keep
           each fix to the area where it belongs. After the first retouch.py
           call, change single numbers through its knobs (one line each)
           instead of sending it again. Say in your report what you changed
           and what still doesn't match.
        5. Staging: stage.py. It adds the floor, three lights, a soft gray
           sky and a camera that fits the object, and sets the render
           (Cycles, 64 samples, denoised, 1024x1024). Pick "around" and
           "above" so the view is a three-quarter one slightly above, like
           the reference.
        6. Check: \`look\` through the camera (mode "camera") with shading
           "material" while you adjust. If it looks wrong compared to the
           reference (orientation, materials, lighting, framing), fix it and
           look again, at most 3 rounds. Then one final \`look\` with
           shading "rendered".
        7. Save. Remove any "Look: ..." boxes first, then, in this order:
           - render the camera view to ${files.render} (PNG): set
             scene.render.filepath and call
             bpy.ops.render.render(write_still=True)
           - save the scene to ${files.blend} with
             bpy.ops.wm.save_as_mainfile (it keeps your material nodes
             editable)
           - bake.py with "object": "${brief.name}", "mode": "materials",
             "texture_size": 2048: glTF can't carry nodes, so this bakes
             your color, metal and roughness fixes into plain textures
             (Blender freezes for up to a minute)
           - export.py with "path": "${files.glb}" and
             "object": "${brief.name}"; its result must say
             "only_this_object": true. Don't save the scene again after
             the bake.

        Tools:

        ${tools}

        ${ctx.output_format()}
    `
}
