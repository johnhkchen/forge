test "Describe parses a well-formed brief" {
    let reply = `
        {
          "name": "Brass Diving Helmet",
          "description": "A round copper-and-brass diving helmet.",
          "subject": "A round brass diving helmet with three circular viewports.",
          "materials": [
            { "part": "shell", "look": "polished brass", "metallic": true }
          ],
          "size_m": 0.45
        }
    `;
    let brief = Describe@spec("deep sea").parse(reply);
    assert.equal(brief.name, "Brass Diving Helmet");
    assert.approx_equal(brief.size_m, 0.45, 0.001)
}
