"""Apply the two Windows compatibility fixes required by robosuite 1.4.0."""

import argparse
import ast
import importlib.metadata
import platform
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Apply a required fix; otherwise inspect without changes.")
    args = parser.parse_args()
    if platform.system() != "Windows":
        parser.error("This helper is for the Windows LIBERO environment.")
    suite = importlib.metadata.distribution("robosuite")
    if suite.version != "1.4.0":
        parser.error("This helper expects robosuite 1.4.0, got " + suite.version)
    binding = Path(suite.locate_file("robosuite/utils/binding_utils.py"))
    source = binding.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    replacement = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = ast.get_source_segment(source, node.test)
        if test not in ('_SYSTEM == "Darwin"', "_SYSTEM == 'Darwin'"):
            continue
        block = ast.get_source_segment(source, node)
        # Match the upstream GPU-rendering branch, never arbitrary EGL imports.
        if 'os.environ["MUJOCO_GL"] = "egl"' not in block:
            continue
        if len(node.body) != 1 or len(node.orelse) != 1 or isinstance(node.orelse[0], ast.If):
            raise RuntimeError("Unexpected rendering branch; inspect " + str(binding))
        indent = " " * node.col_offset
        replacement = (node.lineno - 1, node.end_lineno,
                       indent + 'if _SYSTEM == "Darwin":\n'
                       + indent + '    os.environ["MUJOCO_GL"] = "cgl"\n'
                       + indent + 'elif _SYSTEM == "Windows":\n'
                       + indent + '    os.environ["MUJOCO_GL"] = "wgl"\n'
                       + indent + 'else:\n'
                       + indent + '    os.environ["MUJOCO_GL"] = "egl"\n')
        break
    if replacement is not None:
        print("Windows WGL branch required:", binding)
        if args.apply:
            start, end, block = replacement
            fixed = "".join(lines[:start]) + block + "".join(lines[end:])
            ast.parse(fixed)
            binding.write_text(fixed, encoding="utf-8")
    else:
        print("Rendering branch already configured:", binding)
    mujoco = importlib.metadata.distribution("mujoco")
    source_dll = Path(mujoco.locate_file("mujoco/mujoco.dll"))
    target_dll = binding.parent / "mujoco.dll"
    if not source_dll.is_file():
        raise FileNotFoundError("MuJoCo Windows DLL missing: " + str(source_dll))
    dll_fix = not target_dll.is_file() or source_dll.read_bytes() != target_dll.read_bytes()
    if dll_fix:
        print("Matching MuJoCo DLL required:", target_dll)
        if args.apply:
            shutil.copy2(str(source_dll), str(target_dll))
    else:
        print("MuJoCo DLL already matches:", target_dll)
    if (replacement is not None or dll_fix) and not args.apply:
        raise SystemExit("Run this helper again with --apply to configure Windows.")
    print("Windows compatibility OK")


if __name__ == "__main__":
    main()
