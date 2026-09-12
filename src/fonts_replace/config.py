import os
import tomllib
from importlib.resources import files
from pathlib import Path

from .models import Download, Family, Mapping, Patch, Preset, Source


def system_directory() -> Path:
  return Path(os.environ.get("WINDIR", "C:/Windows"), "Fonts").resolve()


def read_targets(path: Path | None) -> tuple[Family, ...]:
  resource = (
    path if path is not None else files("fonts_replace").joinpath("data/windows.toml")
  )
  data = tomllib.loads(resource.read_text(encoding="utf-8-sig"))
  families = tuple(
    Family(
      id=item["id"],
      names=tuple(item["names"]),
      files=tuple(item.get("files", [])),
      group=item["group"],
      regular_weights=tuple(item.get("regular_weights", [])),
      patches=tuple(Patch(**patch) for patch in item.get("patches", [])),
      enabled=item.get("enabled", True),
      static_family=item.get("static_family"),
    )
    for item in data["families"]
  )
  ids = [family.id for family in families]
  if len(ids) != len(set(ids)):
    raise ValueError("Duplicate target family id")
  for family in families:
    for patch in family.patches:
      if not 1 <= patch.weight <= 1000 or patch.style not in (
        "regular",
        "italic",
        "oblique",
      ):
        raise ValueError(f"Invalid patch style: {family.id}")
      if patch.naming not in ("compatible", "extended"):
        raise ValueError(f"Unknown naming mode: {patch.naming}")
      if (
        Path(patch.output).name != patch.output
        or ":" in patch.output
        or "\\" in patch.output
      ):
        raise ValueError(f"Patch output must be a filename: {patch.output}")
      if Path(patch.output).suffix.lower() not in (".ttf", ".ttc"):
        raise ValueError(f"Unsupported patch output: {patch.output}")
  return families


def read_preset(path: Path, input_dir: Path | None = None) -> Preset:
  if path.suffix == "" and path.parent == Path("."):
    path = Path("presets") / f"{path.name}.toml"
  path = path.resolve()
  data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
  directory = (
    input_dir.resolve() if input_dir else (path.parent / data["input_dir"]).resolve()
  )
  sources = tuple(
    Source(
      groups=tuple(item["groups"]),
      files=tuple(item.get("files", ["*.ttf", "*.ttc"])),
      exclude=tuple(item.get("exclude", [])),
      families=tuple(item.get("families", [])),
      fallback_style=item.get("fallback_style"),
    )
    for item in data["sources"]
  )
  mappings = tuple(Mapping(**item) for item in data.get("mappings", []))
  download = data.get("download")
  return Preset(
    path,
    directory,
    sources,
    mappings,
    Download(download["url"], download["sha256"], tuple(download["directories"]))
    if download
    else None,
  )
