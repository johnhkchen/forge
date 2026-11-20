// Step 4: Claude imports the raw TRELLIS.2 mesh into Blender, fixes what
// image-to-3D usually gets wrong, stages it, renders it, and saves it.
//
// It works in the user's live Blender through MCP, so every change is visible
// as it happens, and it checks its own work with the `look` tool against the
// picture the mesh was made from.

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

function Polish(brief: ObjectBrief, reference: image, files: PolishFiles) -> PolishReport {
    client: Finisher
    prompt: `
        ${role("system")}
        You are a careful 3D artist working in a live Blender session through
        the blender MCP tools. Work in small steps, print what you need to
        know from each script, and check your work with \`look\`.

        Every tool call runs on Blender's main thread and freezes the person's
        screen until it returns, so keep each one light. Check your work with
        \`look\` using shading "material" or "solid" (instant). Use
        shading "rendered" only once, for the final check. Keep \`look\`
        images at max_size 512 unless you need fine detail.

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
        1. Start from an empty scene: remove every object, then import
           ${files.mesh} with bpy.ops.import_scene.gltf. Join its meshes into
           one object named "${brief.name}". Report its triangle count.
        ${if (brief.character ?? false) { "This is a character in a T-pose: keep the pose exactly, feet flat on the ground, facing -Y, and scale it so its standing height (z) is the size above." } else { "" }}
        2. Orientation and size. Compare against the reference with
           \`look\` (mode "angles", shading "material"). Make sure it stands upright the way the
           real object would and faces -Y (Blender's front). Scale it to the size
           above (${brief.size_m} m), then apply rotation and scale.
        3. Origin and placement: put the origin at the bottom center of the
           bounding box and the object at the world origin, resting on z = 0.
        4. Mesh cleanup: merge vertices by distance (0.0001 m), delete loose
           geometry, recalculate normals outward, and shade smooth with a
           Smooth by Angle modifier (30 degrees). If it has more than 400,000
           triangles, add a Decimate (collapse) modifier down to about 300,000.
           Do not remesh, and keep the UVs and textures intact.
        5. Materials: keep the baked base-color texture. Set metallic and
           roughness so each material reads like the list above: real metals
           metallic 1.0, everything else 0.0. Fix anything the picture
           contradicts. Do not repaint or replace textures.
        5b. Textures, up close. The image-to-3D model bakes one texture over
           the whole object, so fine detail comes out soft and the sides the
           picture didn't show are invented. For each material, \`look\`
           closely (mode "angles", shading "material", a short distance,
           max_size 768) and compare it with the reference: color, contrast,
           sharpness, sheen, surface grain. Improve it with nodes only:
           - color and contrast: Hue/Saturation/Value, RGB Curves or
             Brightness/Contrast on the base-color texture;
           - surface grain: a Bump node driven by the texture's own value or
             by a fine Noise/Voronoi texture, kept subtle;
           - sheen: roughness (most non-metals are 0.6-0.95);
           - soft organic materials (bread, wax, fruit, skin, soap): a
             little subsurface (weight 0.05-0.2, warm radius).
           Keep each fix to the material where it belongs (use the texture's
           color to separate materials if they share one texture). Say in
           your report what you changed and what still doesn't match.
        6. Staging: a large ground plane with a neutral matte warm-gray
           material, a soft key light from the upper left, a fill and a rim
           light, and a soft light-gray world. A camera at a three-quarter
           view slightly above, like the reference, framing the object with a
           margin. Render engine Cycles with the Metal GPU if available,
           64 samples with denoising, 1024x1024.
        7. Check: \`look\` through the camera with shading "material" while
           you adjust. If it looks wrong compared to the reference
           (orientation, materials, lighting, framing), fix it and look
           again, at most 3 rounds. Then one final \`look\` with shading
           "rendered".
        8. Save:
           - render the camera view to ${files.render} (PNG)
           - export only the object, with modifiers applied, to ${files.glb}
           - save the scene to ${files.blend}

        ${ctx.output_format()}
    `
}
