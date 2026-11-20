"""Check that Blender scripts will get past the MCP add-on's safe mode.

    python3 scripts/check_safe.py                      (every tidy-mesh skill script)
    python3 scripts/check_safe.py FILE.py [FILE.py ...]
    python3 scripts/check_safe.py --upstream safe_mode.py [FILE.py ...]

The pipeline runs Blender MCP with BLENDER_MCP_SAFE_MODE=1, which reads every
script before it reaches Blender and refuses anything outside a short list.
A refused script costs Claude a round trip, so this finds the problem first.

It follows the rules in github.com/ahujasid/mcp-for-blender
(src/blender_mcp/safe_mode.py, read Nov 2026). The ones that bite in practice:

  - no lambda, class, global, nonlocal, yield, walrus, decorators
  - imports: bpy, bmesh, mathutils and a few pure-Python modules (math, json,
    random, colorsys, itertools, collections...). No numpy, os, sys. No
    `import x as y`, no `from bpy import ...`
  - no open/eval/exec/compile/__import__/dir/vars/globals/super/object
  - getattr/setattr/hasattr only with a literal name: getattr(o, "name")
  - a variable can't reuse a builtin's or a module's name (min, max, type, id,
    format, filter, math...)
  - a bare call must be to a `def` in the script, a builtin, or a
    `from x import name`: no calling a function that was passed in
  - no bpy.app.handlers/timers, bpy.data.texts/libraries, bpy.ops.script/
    text/preferences/extensions/console, wm.append/link

`--upstream` also runs the add-on's own validator from a copy of its file:
  gh api repos/ahujasid/mcp-for-blender/contents/src/blender_mcp/safe_mode.py \\
     -H "Accept: application/vnd.github.raw" > safe_mode.py
"""
import ast
import glob
import importlib.util
import os
import sys

MODULES = {
    "bpy", "bmesh", "mathutils", "math", "cmath", "random", "colorsys", "json", "itertools",
    "functools", "collections", "statistics", "string", "re", "enum", "dataclasses", "typing",
    "decimal", "fractions", "textwrap", "unicodedata", "uuid", "copy", "heapq", "bisect", "array",
}
BAD_IMPORT_NAMES = {
    "system", "popen", "SystemRandom", "previews", "path", "environ", "exit", "argv", "modules",
    "builtins", "reload", "import_module", "find_spec", "util",
}
BUILTINS = {
    "bool", "int", "float", "complex", "str", "bytes", "bytearray", "list", "tuple", "set",
    "frozenset", "dict", "slice", "abs", "round", "min", "max", "sum", "pow", "divmod", "hex",
    "oct", "bin", "ord", "chr", "len", "range", "enumerate", "zip", "map", "filter", "reversed",
    "sorted", "all", "any", "iter", "next", "isinstance", "issubclass", "callable", "repr",
    "format", "hash", "id", "print", "type", "Exception", "ValueError", "TypeError", "KeyError",
    "IndexError", "RuntimeError", "AttributeError", "ZeroDivisionError", "StopIteration",
    "NotImplementedError", "ArithmeticError", "OverflowError", "LookupError", "AssertionError",
    "FloatingPointError", "True", "False", "None", "NotImplemented", "Ellipsis",
}
BAD_CALLS = {
    "eval", "exec", "compile", "__import__", "open", "input", "breakpoint", "exit", "quit",
    "globals", "locals", "vars", "dir", "help", "memoryview", "super", "object", "staticmethod",
    "classmethod", "property", "copyright", "credits", "license",
}
LITERAL_ATTR_CALLS = {"getattr", "setattr", "delattr", "hasattr"}
BAD_ATTRS = {
    "mro", "func_globals", "func_code", "func_closure", "gi_frame", "cr_frame", "f_globals",
    "f_locals", "f_builtins", "f_back", "tb_frame",
    "driver_namespace", "register_class", "unregister_class", "execfile", "load_scripts",
    "save_homefile", "quit_blender", "url_open", "path_open", "console_toggle", "as_pointer",
    "driver_add", "driver_remove", "texts", "scripts", "libraries", "handlers", "timers",
    "app_handlers", "binary_path", "user_resource", "script_paths", "script_directories",
    "modules_from_path", "python_file_run", "run_script", "addon_install", "addon_enable",
}
BAD_ASSIGN_ATTRS = {"expression", "script", "use_self", "script_directory", "use_scripts_auto_execute"}
BAD_PATHS = (
    "bpy.app.driver_namespace", "bpy.app.handlers", "bpy.app.timers", "bpy.app.binary_path",
    "bpy.utils.register_class", "bpy.utils.unregister_class", "bpy.utils.register_classes_factory",
    "bpy.utils.execfile", "bpy.utils.load_scripts", "bpy.utils.script_paths", "bpy.utils.user_resource",
    "bpy.utils.modules_from_path", "bpy.utils.refresh_script_paths", "bpy.utils.previews",
    "bpy.data.texts", "bpy.data.scripts", "bpy.data.libraries", "bpy.props", "bpy.types.Operator",
    "bpy.types.Panel", "bpy.types.AddonPreferences", "bpy.types.Macro", "bpy.ops.wm.append",
    "bpy.ops.wm.link", "bpy.ops.wm.lib_relocate", "bpy.ops.wm.lib_reload", "bpy.ops.wm.save_homefile",
    "bpy.ops.wm.url_open", "bpy.ops.wm.path_open", "bpy.ops.wm.console_toggle",
    "bpy.ops.wm.quit_blender", "bpy.ops.render.play_rendered_anim",
    "bpy.context.preferences.filepaths.script_directories",
    "bpy.ops.script", "bpy.ops.text", "bpy.ops.preferences", "bpy.ops.extensions", "bpy.ops.console",
)
NAVIGATION = {"ops", "utils", "app", "props", "types", "wm", "script", "preferences", "extensions"}
BAD_NODES = {
    "Lambda": "lambda is refused: write a def",
    "ClassDef": "class definitions are refused: use functions",
    "Global": "global is refused",
    "Nonlocal": "nonlocal is refused",
    "NamedExpr": "the walrus := is refused",
    "Yield": "generators (yield) are refused",
    "YieldFrom": "generators (yield from) are refused",
    "Match": "match statements are refused",
    "AsyncFunctionDef": "async is refused", "AsyncFor": "async is refused",
    "AsyncWith": "async is refused", "Await": "async is refused",
}
MAX_BYTES, MAX_NODES, MAX_DEPTH = 200000, 20000, 24


def chain(node):
    """`a.b.c` for a dotted name, or None when it doesn't start at a plain name."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    return ".".join(reversed(parts + [node.id]))


def dunder(name):
    return name.startswith("__") and name.endswith("__")


def problems(code):
    """Every reason safe mode would refuse this script, as (line, message)."""
    found = []

    def flag(node, message):
        found.append((getattr(node, "lineno", 0), message))

    if len(code.encode("utf-8")) > MAX_BYTES:
        found.append((0, "longer than %d bytes" % MAX_BYTES))
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [(e.lineno or 0, "syntax error: %s" % e.msg)]
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_NODES:
        found.append((0, "too big: %d syntax nodes, the limit is %d" % (len(nodes), MAX_NODES)))
    stack = [(tree, 0)]
    while stack:
        node, depth = stack.pop()
        if depth > MAX_DEPTH:
            flag(node, "nested deeper than %d levels" % MAX_DEPTH)
            break
        stack.extend((child, depth + 1) for child in ast.iter_child_nodes(node))

    parent = {child: node for node in nodes for child in ast.iter_child_nodes(node)}
    modules = {a.name.split(".")[0] for n in nodes if isinstance(n, ast.Import) for a in n.names}
    from_names = {a.asname or a.name for n in nodes if isinstance(n, ast.ImportFrom) for a in n.names}
    functions = {n.name for n in nodes if isinstance(n, ast.FunctionDef)}
    bound = set(from_names) | functions
    for n in nodes:
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            bound.add(n.id)
        elif isinstance(n, ast.arg):
            bound.add(n.arg)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            bound.add(n.name)

    def binding(node, name):
        if name in modules:
            flag(node, "%r is an imported module; a variable can't reuse its name" % name)
        elif name in BAD_CALLS or name in LITERAL_ATTR_CALLS or name in BUILTINS:
            flag(node, "%r is a builtin; a variable or function can't reuse its name" % name)
        elif dunder(name):
            flag(node, "can't bind the dunder name %r" % name)

    for n in nodes:
        kind = type(n).__name__
        if kind in BAD_NODES:
            flag(n, BAD_NODES[kind])
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split(".")[0] not in MODULES or a.name in ("bpy.utils.previews", "collections.abc"):
                    flag(n, "import of %r is not allowed" % a.name)
                if a.asname:
                    flag(n, "`import %s as %s` is refused: import it under its own name" % (a.name, a.asname))
        elif isinstance(n, ast.ImportFrom):
            module = n.module or ""
            root = module.split(".")[0]
            if n.level or root not in MODULES or module in ("bpy.utils.previews", "collections.abc"):
                flag(n, "import from %r is not allowed" % module)
            elif root == "bpy":
                flag(n, "`from bpy import ...` is refused: use `import bpy` and full dotted paths")
            for a in n.names:
                if a.name == "*" or a.name in BAD_IMPORT_NAMES or a.name.startswith("_"):
                    flag(n, "importing %r from %r is not allowed" % (a.name, module))
                else:
                    binding(n, a.asname or a.name)
        elif isinstance(n, ast.FunctionDef):
            if n.decorator_list:
                flag(n, "decorators are refused")
            binding(n, n.name)
        elif isinstance(n, ast.arg):
            binding(n, n.arg)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            binding(n, n.name)
        elif isinstance(n, ast.Name):
            name = n.id
            if isinstance(n.ctx, (ast.Store, ast.Del)):
                binding(n, name)
            elif name in BAD_CALLS:
                flag(n, "%s is forbidden" % name)
            elif dunder(name):
                flag(n, "the dunder name %r is not accessible" % name)
            elif name in modules:
                up = parent.get(n)
                if not (isinstance(up, ast.Attribute) and up.value is n):
                    flag(n, "module %r can only start a dotted path, not be passed around" % name)
            elif name not in bound and name not in BUILTINS and name not in LITERAL_ATTR_CALLS:
                flag(n, "unknown name %r (not an allowed builtin, an import, or defined here)" % name)
        elif isinstance(n, ast.Attribute):
            attr = n.attr
            if dunder(attr) or attr in BAD_ATTRS:
                flag(n, "the attribute %r is refused" % attr)
            if isinstance(n.ctx, (ast.Store, ast.Del)) and attr in BAD_ASSIGN_ATTRS:
                flag(n, "assigning to %r is refused" % attr)
            path = chain(n)
            if path is None:
                if attr in NAVIGATION:
                    flag(n, "%r must be reached from a plain name like bpy.%s" % (attr, attr))
                continue
            for bad in BAD_PATHS:
                if path == bad or path.startswith(bad + "."):
                    flag(n, "%s is forbidden" % path)
            if isinstance(n.ctx, (ast.Store, ast.Del)) and path.startswith("bpy.types."):
                flag(n, "assigning to %s is refused" % path)
            up = parent.get(n)
            outermost = not (isinstance(up, ast.Attribute) and up.value is n)
            parts = path.split(".")
            if (outermost and isinstance(n.ctx, ast.Load) and parts[0] in modules
                    and all(p in NAVIGATION for p in parts[1:])):
                flag(n, "%s is a module namespace and can't be used as a value" % path)
        elif isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                name = f.id
                if name in LITERAL_ATTR_CALLS:
                    target = n.args[1] if len(n.args) > 1 else None
                    if not (isinstance(target, ast.Constant) and isinstance(target.value, str)):
                        flag(n, "%s() needs a literal attribute name, like %s(o, \"name\")" % (name, name))
                    elif (dunder(target.value) or target.value in BAD_ATTRS or target.value in NAVIGATION
                          or (name in ("setattr", "delattr") and target.value in BAD_ASSIGN_ATTRS)):
                        flag(n, "%s() on %r is refused" % (name, target.value))
                elif name == "type" and len(n.args) != 1:
                    flag(n, "type() with three arguments is refused")
                elif name not in BAD_CALLS and name not in functions | modules | from_names | BUILTINS:
                    flag(n, "%r is called but isn't a def, a builtin or a from-import "
                            "(a function passed in as a value can't be called)" % name)
            elif not isinstance(f, ast.Attribute):
                flag(n, "the thing being called must be a name or an attribute")
    return sorted(set(found))


def load_upstream(path):
    spec = importlib.util.spec_from_file_location("upstream_safe_mode", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["upstream_safe_mode"] = module
    spec.loader.exec_module(module)
    return module


def main(argv):
    upstream = None
    if "--upstream" in argv:
        i = argv.index("--upstream")
        upstream = load_upstream(argv[i + 1])
        del argv[i:i + 2]
    here = os.path.dirname(os.path.abspath(__file__))
    files = argv or sorted(glob.glob(os.path.join(here, "..", ".claude", "skills", "*", "scripts", "*.py")))
    bad = 0
    for path in files:
        with open(path) as f:
            code = f.read()
        found = problems(code)
        if upstream:
            ok, reason = upstream.is_safe(code)
            if ok and found:
                found.append((0, "check_safe is stricter than the add-on here (the add-on accepts this file)"))
            if not ok and not found:
                found.append((0, "the add-on refuses this, check_safe missed it: %s" % reason))
        name = os.path.relpath(path)
        if found:
            bad += 1
            for line, message in found:
                print("%s:%d: %s" % (name, line, message))
        else:
            print("ok  %s" % name)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
