import hashlib
import json
import platform
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import asdict, is_dataclass
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

from fontTools.ttLib import TTCollection, TTFont

from .config import system_directory
from .metadata import apply_metadata, instantiate
from .models import Face, Plan, Task
from .validation import snapshot, validate


def json_value(value):
  if isinstance(value, Path):
    return value.as_posix()
  if is_dataclass(value):
    return asdict(value)
  raise TypeError(f"Cannot serialize {type(value).__name__}")


def write_json(path: Path, value) -> None:
  path.write_text(
    json.dumps(value, default=json_value, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
  )


def check_output(plan: Plan, output: Path) -> None:
  if output.exists():
    raise ValueError(f"Output already exists; choose a new directory: {output}")
  for source in (plan.system_dir, plan.input_dir, system_directory()):
    if output.is_relative_to(source) or source.is_relative_to(output):
      raise ValueError(f"Output must be separate from font sources: {source}")
  if not plan.outputs:
    raise ValueError("No matching system fonts to generate")


def build(plan: Plan, output: Path, progress: Callable[[str], None] = print) -> dict:
  output = output.resolve()
  check_output(plan, output)
  output.parent.mkdir(parents=True, exist_ok=True)
  hashes: dict[Path, str] = {}

  def digest(path: Path) -> str:
    if path not in hashes:
      with path.open("rb") as stream:
        hashes[path] = hashlib.file_digest(stream, "sha256").hexdigest()
    return hashes[path]

  def record(face: Face) -> dict:
    return asdict(face) | {"sha256": digest(face.path)}

  manifest = {
    "schema": 1,
    "tool": "fonts_replace",
    "version": version("fonts_replace"),
    "python": platform.python_version(),
    "fonttools": version("fonttools"),
    "system_dir": plan.system_dir,
    "input_dir": plan.input_dir,
    "skipped": plan.skipped,
    "outputs": [],
  }
  with TemporaryDirectory(prefix=".fonts_replace-", dir=output.parent) as temporary:
    work = Path(temporary)
    delivery = work / "output"
    delivery.mkdir()
    originals: dict[tuple[Path, int], Path] = {}
    instances: dict[tuple, Path] = {}

    def extract(face: Face) -> Path:
      if face.key in originals:
        return originals[face.key]
      if not face.collection:
        originals[face.key] = face.path
        return face.path
      collection = TTCollection(face.path, recalcTimestamp=False)
      try:
        for index, font in enumerate(collection.fonts):
          path = work / f"original-{len(originals)}-{index}.ttf"
          font.save(path)
          originals[face.path, index] = path
      finally:
        collection.close()
      return originals[face.key]

    def instance(face: Face, axes: dict[str, float]) -> Path:
      key = face.key + tuple(sorted(axes.items()))
      if key not in instances:
        path = work / f"instance-{len(instances)}.ttf"
        with TTFont(extract(face), recalcTimestamp=False) as font:
          instantiate(font, axes)
          font.save(path)
        instances[key] = path
      return instances[key]

    for index, target in enumerate(plan.outputs):
      progress(f"[{index + 1}/{len(plan.outputs)}] {target.name}")
      members: list[Path] = []
      expected: list[dict] = []
      reports: list[dict] = []
      for member_index, member in enumerate(target.members):
        if isinstance(member, Face):
          path = extract(member)
          with TTFont(path, recalcTimestamp=False) as font:
            expected.append(snapshot(font))
          members.append(path)
          reports.append(
            {"index": member_index, "action": "preserve", "original": record(member)}
          )
          continue
        task = member
        path = work / f"result-{index}-{member_index}.ttf"
        template_path = (
          instance(task.template, task.target_axes)
          if task.template.axes
          else extract(task.template)
        )
        with (
          TTFont(
            instance(task.source, task.source_axes), recalcTimestamp=False
          ) as font,
          TTFont(template_path, recalcTimestamp=False) as template,
        ):
          report = apply_metadata(font, template, task)
          expected.append(snapshot(font))
          font.save(path)
        members.append(path)
        reports.append(
          {
            "index": member_index,
            "action": "patch" if task.patch else "replace",
            "family": task.family,
            "weight": task.weight,
            "style": task.style,
            "template": record(task.template),
            "source": record(task.source),
            "source_axes": task.source_axes,
            "target_axes": task.target_axes,
            "static_replacement": bool(task.template.axes),
            "selection": task.reason,
            **report,
          }
        )
      destination = delivery / target.name
      if target.name.lower().endswith(".ttc"):
        with ExitStack() as stack:
          collection = TTCollection()
          collection.fonts = [
            stack.enter_context(TTFont(path, recalcTimestamp=False)) for path in members
          ]
          collection.save(destination)
        result = TTCollection(destination)
        try:
          if len(result.fonts) != len(target.members):
            raise ValueError(f"Collection member count changed: {target.name}")
          for font, expectation, member in zip(
            result.fonts, expected, target.members, strict=True
          ):
            validate(font, expectation, isinstance(member, Task))
        finally:
          result.close()
      else:
        members[0].rename(destination)
        with TTFont(destination) as font:
          validate(font, expected[0], True)
      manifest["outputs"].append(
        {"file": target.name, "sha256": digest(destination), "members": reports}
      )
    write_json(delivery / "manifest.json", manifest)
    delivery.rename(output)
  return manifest
