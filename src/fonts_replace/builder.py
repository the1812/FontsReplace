import hashlib
import platform
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import asdict, is_dataclass
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, TypedDict, cast

from fontTools.ttLib import TTCollection, TTFont

from .config import system_directory
from .metadata import CoverageReport, MetricsReport, apply_metadata, instantiate
from .models import Face, Plan, Task
from .validation import Snapshot, snapshot, validate


class AxisReport(TypedDict):
  minimum: float
  default: float
  maximum: float


class FaceReport(TypedDict):
  path: Path
  index: int
  collection: bool
  family: str
  subfamily: str
  postscript: str
  weight: int
  width: int
  style: str
  upem: int
  version: str
  axes: dict[str, AxisReport]
  outline: str
  sha256: str


class PreserveReport(TypedDict):
  index: int
  action: Literal["preserve"]
  original: FaceReport


class ReplaceReport(TypedDict):
  index: int
  action: Literal["patch", "replace"]
  family: str
  weight: int
  style: str
  template: FaceReport
  source: FaceReport
  source_axes: dict[str, float]
  target_axes: dict[str, float]
  static_replacement: bool
  variable_output: bool
  selection: str
  metrics: MetricsReport
  coverage: CoverageReport


MemberReport = PreserveReport | ReplaceReport


class OutputReport(TypedDict):
  file: str
  sha256: str
  members: list[MemberReport]


class BuildReport(TypedDict):
  schema: int
  tool: str
  version: str
  python: str
  fonttools: str
  system_dir: Path
  input_dir: Path
  skipped: list[str]
  outputs: list[OutputReport]


def json_value(value: object) -> str | dict[str, object]:
  if isinstance(value, Path):
    return value.as_posix()
  if is_dataclass(value) and not isinstance(value, type):
    return asdict(value)
  raise TypeError(f"Cannot serialize {type(value).__name__}")


def check_output(plan: Plan, output: Path) -> None:
  for source in (plan.system_dir, plan.input_dir, system_directory()):
    if output.is_relative_to(source) or source.is_relative_to(output):
      raise ValueError(f"Output must be separate from font sources: {source}")
  if not plan.outputs:
    raise ValueError("No matching system fonts to generate")


def build(
  plan: Plan, output: Path, progress: Callable[[str], None] = print
) -> BuildReport:
  output = output.resolve()
  check_output(plan, output)
  output.parent.mkdir(parents=True, exist_ok=True)
  hashes: dict[Path, str] = {}

  def digest(path: Path) -> str:
    if path not in hashes:
      with path.open("rb") as stream:
        hashes[path] = hashlib.file_digest(stream, "sha256").hexdigest()
    return hashes[path]

  def record(face: Face) -> FaceReport:
    return cast(FaceReport, asdict(face) | {"sha256": digest(face.path)})

  manifest: BuildReport = {
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
    instances: dict[tuple[Path, int, tuple[tuple[str, float], ...]], Path] = {}

    def extract(face: Face) -> Path:
      if face.key in originals:
        return originals[face.key]
      if not face.collection:
        originals[face.key] = face.path
        return face.path
      collection = TTCollection(
        face.path, lazy=True, recalcBBoxes=False, recalcTimestamp=False
      )
      try:
        for index, font in enumerate(collection.fonts):
          path = work / f"original-{len(originals)}-{index}.ttf"
          font.save(path)
          originals[face.path, index] = path
      finally:
        collection.close()
      return originals[face.key]

    def instance(face: Face, axes: dict[str, float]) -> Path:
      key = (face.path, face.index, tuple(sorted(axes.items())))
      if key not in instances:
        path = work / f"instance-{len(instances)}.ttf"
        with TTFont(
          extract(face), lazy=True, recalcBBoxes=bool(axes), recalcTimestamp=False
        ) as font:
          instantiate(font, axes)
          font.save(path)
        instances[key] = path
      return instances[key]

    for index, target in enumerate(plan.outputs):
      progress(f"[{index + 1}/{len(plan.outputs)}] {target.name}")
      members: list[Path] = []
      expected: list[Snapshot] = []
      reports: list[MemberReport] = []
      for member_index, member in enumerate(target.members):
        if isinstance(member, Face):
          path = extract(member)
          with TTFont(
            path, lazy=True, recalcBBoxes=False, recalcTimestamp=False
          ) as font:
            expected.append(snapshot(font))
          members.append(path)
          preserved: PreserveReport = {
            "index": member_index,
            "action": "preserve",
            "original": record(member),
          }
          reports.append(preserved)
          continue
        task = member
        path = work / f"result-{index}-{member_index}.ttf"
        with (
          TTFont(
            instance(task.source, task.source_axes),
            lazy=True,
            recalcBBoxes=False,
            recalcTimestamp=False,
          ) as font,
          TTFont(
            task.template.path,
            fontNumber=task.template.index,
            lazy=True,
            recalcBBoxes=False,
            recalcTimestamp=False,
          ) as template,
        ):
          metadata_report = apply_metadata(font, template, task)
          expected.append(snapshot(font))
          font.save(path)
        members.append(path)
        generated: ReplaceReport = {
          "index": member_index,
          "action": "patch" if task.patch else "replace",
          "family": task.family,
          "weight": task.weight,
          "style": task.style,
          "template": record(task.template),
          "source": record(task.source),
          "source_axes": task.source_axes,
          "target_axes": task.target_axes,
          "static_replacement": bool(task.template.axes or task.target.variable_family)
          and not task.variable,
          "variable_output": task.variable,
          "selection": task.reason,
          "metrics": metadata_report["metrics"],
          "coverage": metadata_report["coverage"],
        }
        reports.append(generated)
      destination = delivery / target.name
      if target.name.lower().endswith(".ttc"):
        with ExitStack() as stack:
          collection = TTCollection()
          collection.fonts = [
            stack.enter_context(
              TTFont(path, lazy=True, recalcBBoxes=False, recalcTimestamp=False)
            )
            for path in members
          ]
          collection.save(destination)
        result = TTCollection(destination, lazy=True, recalcBBoxes=False)
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
        with TTFont(destination, lazy=True, recalcBBoxes=False) as font:
          validate(font, expected[0], True)
      output_report: OutputReport = {
        "file": target.name,
        "sha256": digest(destination),
        "members": reports,
      }
      manifest["outputs"].append(output_report)
    output.mkdir(parents=True, exist_ok=True)
    for path in delivery.iterdir():
      path.replace(output / path.name)
  return manifest
