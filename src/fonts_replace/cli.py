import argparse
import json
import sys
from pathlib import Path

from fontTools.ttLib import TTLibError

from .builder import build, json_value
from .config import read_preset, read_targets, system_directory
from .inventory import font_paths, scan_file
from .planner import make_plan


def main() -> int:
  sys.stdout.reconfigure(encoding="utf-8")
  sys.stderr.reconfigure(encoding="utf-8")
  parser = argparse.ArgumentParser(
    description="Generate system-identity fonts from replacement TrueType faces"
  )
  subparsers = parser.add_subparsers(dest="command", required=True)
  inspect = subparsers.add_parser(
    "inspect", help="Read font identities and variable axes without writing fonts"
  )
  inspect.add_argument("--system-dir", type=Path, default=system_directory())
  inspect.add_argument("--input-dir", type=Path)
  for command in ("plan", "build"):
    command_parser = subparsers.add_parser(command)
    command_parser.add_argument("--preset", type=Path, required=True)
    command_parser.add_argument("--system-dir", type=Path, default=system_directory())
    command_parser.add_argument("--input-dir", type=Path)
    command_parser.add_argument(
      "--targets", type=Path, help="Custom system target TOML"
    )
    command_parser.add_argument(
      "--family",
      action="append",
      help="Select a target id; repeat for multiple targets",
    )
    if command == "build":
      command_parser.add_argument("--output", type=Path, required=True)
  args = parser.parse_args()
  try:
    if args.command == "inspect":
      roots = {"system": args.system_dir.resolve()}
      if args.input_dir:
        roots["input"] = args.input_dir.resolve()
      result = {
        name: [face for path in font_paths(root) for face in scan_file(path)]
        for name, root in roots.items()
      }
      print(json.dumps(result, default=json_value, ensure_ascii=False, indent=2))
      return 0
    preset = read_preset(args.preset, args.input_dir)
    plan = make_plan(
      args.system_dir.resolve(), preset, read_targets(args.targets), args.family
    )
    if args.command == "plan":
      print(json.dumps(plan, default=json_value, ensure_ascii=False, indent=2))
    else:
      build(
        plan,
        args.output,
        progress=lambda message: print(message, file=sys.stderr, flush=True),
      )
      print(f"Generated {len(plan.outputs)} font files: {args.output.resolve()}")
    return 0
  except (ValueError, OSError, TTLibError) as error:
    print(f"fonts_replace: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
  raise SystemExit(main())
