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

// With the Forge add-on installed (`just forge-addon`, then restart Blender),
// the same scripts are bundled inside Blender as bpy.ops.forge.run, so a
// prompt carries only each tool's instructions and settings, not its code.
const FORGE_STARTUP = "Library/Application Support/Blender/5.2/scripts/startup/forge_tools.py";

function forge_installed() -> bool {
    let home = baml.sys.home_dir() ?? "";
    home != "" && baml.fs.exists(`${home}/${FORGE_STARTUP}`)
}

/// How to call the tools through the Forge add-on.
const FORGE_RULES = `
    You have ready-made tools, installed in Blender as one operator. Use one
    wherever it fits; write your own code only for what no tool covers.
    - Call a tool with one line, then read its result:
          bpy.ops.forge.run(tool="measure", params=json.dumps({...}))
          print(bpy.context.scene["forge_result"])
      Put only the PARAMS you change in params; the rest keep their
      defaults. Under "Tools" at the end, each tool has its instructions
      and its PARAMS with defaults; there is no need to send its code.
    - Several tool calls can go in one execute_blender_code call.
    - If bpy.ops.forge.run is missing, Blender wasn't restarted after the
      add-on was installed: say so in your report and do the work by hand.
    - The tools work on the open scene and, unless told otherwise, on its
      largest visible mesh, so you rarely need object names.
    - Code you write yourself must pass the add-on's safe mode: import only
      bpy, bmesh, mathutils, math, json, random, colorsys (no numpy, no
      \`import x as y\`); no lambda (write a def), no class, no open/eval/
      exec/__import__/dir/vars; getattr only with a literal name; don't
      reuse a builtin's name (min, max, type, id) for a variable; no
      bpy.data.texts and no Blender preferences.
`;

/// The rules for whichever way the tools are delivered.
function tool_rules() -> string {
    if (forge_installed()) { FORGE_RULES } else { TOOL_RULES }
}

/// A tool's instructions and PARAMS block: everything before its imports.
function tool_card(source: string) -> string {
    let cut = source.index_of("\nimport ") ?? source.length();
    source.slice(0, cut).trim_end()
}

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

/// The named tools as prompt text, each under its name: the whole script
/// to paste, or with the Forge add-on just its instructions and PARAMS.
function tools(names: string[]) -> string {
    let cards = forge_installed();
    names
        .map((name) -> {
            let source = baml.fs.read(`${TOOLS_DIR}/${name}.py`);
            if (cards) {
                `===== ${name} (bpy.ops.forge.run(tool="${name}", ...)) =====\n${tool_card(source)}`
            } else {
                `===== ${name}.py =====\n${source}`
            }
        })
        .join("\n\n")
}

test "a tool card stops before the imports" {
    let card = tool_card("# what it does\nPARAMS = {\"a\": 1}\n\nimport bpy\nprint(1)");
    assert.equal(card, "# what it does\nPARAMS = {\"a\": 1}")
}

test "tools pastes each script under its name" {
    let text = tools(["frame", "open"]);
    assert.is_true(text.starts_with("===== frame"));
    assert.contains(text, "===== open");
    assert.contains(text, "PARAMS = {")
}
