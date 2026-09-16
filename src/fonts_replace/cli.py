import argparse
import json
import sys
from io import TextIOWrapper
from pathlib import Path
from typing import cast
from zipfile import BadZipFile

from fontTools.ttLib import TTLibError

from .builder import build, json_value
from .config import read_preset, read_targets, system_directory
from .fetch import fetch
from .inventory import font_paths, scan_file
from .planner import make_plan


def main() -> int:
  cast(TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8")
  cast(TextIOWrapper, sys.stderr).reconfigure(encoding="utf-8")
  parser = argparse.ArgumentParser(
    description="Generate system-identity fonts from replacement TrueType faces"
  )
  subparsers = parser.add_subparsers(dest="command", required=True)
  inspect = subparsers.add_parser(
    "inspect", help="Read font identities and variable axes without writing fonts"
  )
  inspect.add_argument("--system-dir", type=Path, default=system_directory())
  inspect.add_argument("--input-dir", type=Path)
  fetch_parser = subparsers.add_parser("fetch", help="Download a preset's fonts")
  fetch_parser.add_argument("preset", type=Path)
  fetch_parser.add_argument("--input-dir", type=Path)
  build_parser = subparsers.add_parser("build", help="Generate replacement fonts")
  build_parser.add_argument("--preset", type=Path, required=True)
  build_parser.add_argument("--system-dir", type=Path, default=system_directory())
  build_parser.add_argument("--input-dir", type=Path)
  build_parser.add_argument("--targets", type=Path, help="Custom system target TOML")
  build_parser.add_argument(
    "--family",
    action="append",
    help="Select a target id; repeat for multiple targets",
  )
  build_parser.add_argument("--output", type=Path, default=Path("replacements"))
  build_parser.add_argument(
    "--dry-run", action="store_true", help="Print the build plan without writing fonts"
  )
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
    if args.command == "fetch":
      fetch(
        preset, progress=lambda message: print(message, file=sys.stderr, flush=True)
      )
      return 0
    plan = make_plan(
      args.system_dir.resolve(), preset, read_targets(args.targets), args.family
    )
    if args.dry_run:
      print(json.dumps(plan, default=json_value, ensure_ascii=False, indent=2))
    else:
      result = build(
        plan,
        args.output,
        progress=lambda message: print(message, file=sys.stderr, flush=True),
      )
      print(json.dumps(result, default=json_value, ensure_ascii=False, indent=2))
    return 0
  except (ValueError, OSError, TTLibError, BadZipFile) as error:
    print(f"fonts_replace: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
  raise SystemExit(main())
