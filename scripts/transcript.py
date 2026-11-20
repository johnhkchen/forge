"""Print the Blender code Claude ran in one step of a run, in order.

    python3 scripts/transcript.py runs/<run> <step>      (step: polish, parts, lowpoly)
"""
import json
import sys

run, step = sys.argv[1], sys.argv[2]
n = 0
with open("%s/transcripts/%s.jsonl" % (run.rstrip("/"), step)) as f:
    for line in f:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") != "assistant":
            continue
        for block in event.get("message", {}).get("content", []):
            if block.get("type") != "tool_use":
                continue
            n += 1
            name = block.get("name", "").replace("mcp__blender__", "")
            args = block.get("input", {})
            print("\n# ---- %d. %s" % (n, name))
            if name == "execute_blender_code":
                print(args.get("code", ""))
            else:
                print(json.dumps({k: v for k, v in args.items() if k != "user_prompt"}))
print("\n# %d tool calls" % n)
