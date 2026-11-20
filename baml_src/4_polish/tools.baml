// The tools Claude gets for the three Blender steps: ready-made scripts from
// .claude/skills/tidy-mesh/scripts, pasted into the prompt.
//
// Why pasted: the Blender add-on runs every execute_blender_code call in a
// brand-new Python namespace (addon.py: `exec(code, {"bpy": bpy})`), so a
// function defined in one call is gone in the next, and safe mode leaves no
// place to keep code between calls. A tool is therefore a whole script that
// Claude sends each time, with its PARAMS edited. Each step gets only the
// scripts it uses, to keep its prompt short.

const TOOLS_DIR = ".claude/skills/tidy-mesh/scripts";

/// How to use the scripts; goes in the system part of each Blender prompt.
const TOOL_RULES = `
    You have ready-made tools: the scripts under "Tools" at the end. Use one
    wherever it fits; write your own code only for what no tool covers.
    - Nothing carries over between execute_blender_code calls (no functions,
      no variables), so to use a tool, send its code every time: everything
      from the line "PARAMS = {" to the end, unchanged except for the values
      in PARAMS. The comment block above PARAMS is the tool's instructions;
      read it, and leave it out of what you send.
    - Each tool prints one line, RESULT {json}. Read it before the next step.
    - The tools work on the open scene and, unless told otherwise, on its
      largest visible mesh, so you rarely need object names.
    - Code you write yourself must pass the add-on's safe mode: import only
      bpy, bmesh, mathutils, math, json, random, colorsys (no numpy, no
      \`import x as y\`); no lambda (write a def), no class, no open/eval/
      exec/__import__/dir/vars; getattr only with a literal name; don't
      reuse a builtin's name (min, max, type, id) for a variable; call only
      your own defs and builtins by bare name (not a function handed in as
      an argument); no bpy.data.texts and no Blender preferences.
`;

/// The named scripts as prompt text, each under its file name.
function tools(names: string[]) -> string {
    names
        .map((name) -> {
            `===== ${name}.py =====\n${baml.fs.read(`${TOOLS_DIR}/${name}.py`)}`
        })
        .join("\n\n")
}

test "tools pastes each script under its name" {
    let text = tools(["frame", "open"]);
    assert.is_true(text.starts_with("===== frame.py ====="));
    assert.contains(text, "===== open.py =====");
    assert.contains(text, "PARAMS = {")
}
