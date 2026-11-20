/// Finishes the raw mesh in the live Blender session and saves the results
/// next to it in the run folder.
function polish(brief: ObjectBrief, run: Run) -> PolishReport {
    //# Claude works on the mesh in Blender over MCP
    let files = PolishFiles {
        mesh: run.absolute("mesh.glb"),
        blend: run.absolute("scene.blend"),
        glb: run.absolute("final.glb"),
        render: run.absolute("render.png"),
    };
    let reference = baml.media.Image.from_file(run.path("image.png"), "image/png");
    let report = Polish(brief, reference, files);
    run.save("polish.json", report);
    report
}

test "Polish parses a report" {
    let reply = `
        {
          "fixes": ["Scaled to 0.3 m"],
          "problems": [],
          "triangles": 280000,
          "dimensions_m": [0.3, 0.22, 0.3],
          "score": 4
        }
    `;
    let files = PolishFiles { mesh: "m.glb", blend: "s.blend", glb: "f.glb", render: "r.png" };
    let brief = ObjectBrief {
        name: "Iron Kettle",
        description: "A kettle.",
        subject: "A kettle.",
        materials: [],
        size_m: 0.3,
    };
    let report = Polish@spec(brief, baml.media.Image.from_base64("iVBORw0KGgo=", "image/png"), files).parse(
        reply,
    );
    assert.equal(report.score, 4)
}
