// Every model call goes through a logged-in CLI, so a run costs subscription
// time rather than metered API tokens.

// Opus writes the brief: one short structured reply, no tools.
client Writer = claude_code.ClaudeCodeClient.new(model = "opus", timeout_ms = 180000);

// Opus finishes the mesh in Blender, through MCP for Blender
// (github.com/ahujasid/mcp-for-blender). The add-on must be running inside an
// open Blender; this client only starts the MCP server that talks to it.
//
// No Claude Code tools are attached, only Blender's. Safe mode limits the
// Python it runs to bpy, bmesh and mathutils, with no file or network access
// outside Blender's own import, export, render and save operators. That is
// enough for this job and keeps an unattended session inside Blender.
// It runs through scripts/claude-logged, which keeps the full event log
// (every script Claude sends to Blender); see keep_transcript in run.baml.
client Finisher = claude_code.ClaudeCodeClient.new(
    model = "opus",
    executable = "scripts/claude-logged",
    timeout_ms = 1800000,
    mcp_servers = {
        "blender": {
            "command": "uvx",
            "args": ["--python", "3.11", "mcp-for-blender"],
            "env": { "BLENDER_MCP_SAFE_MODE": "1", "UV_PYTHON_PREFERENCE": "only-managed" },
        },
    },
);
