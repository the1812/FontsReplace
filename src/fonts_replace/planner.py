from collections import defaultdict
from math import isfinite
from pathlib import Path

from .inventory import font_paths, matches, require_truetype, scan_file
from .models import Face, Family, Mapping, Output, Patch, Plan, Preset, Source, Task


def scan_system(directory: Path) -> list[Face]:
  return [face for path in font_paths(directory) for face in scan_file(path)]


def scan_sources(preset: Preset) -> list[Face]:
  explicit = tuple(mapping.file for mapping in preset.mappings if mapping.file)
  paths = [
    path
    for path in font_paths(preset.input_dir)
    if matches(path, preset.input_dir, explicit)
    or any(
      matches(path, preset.input_dir, source.files)
      and not matches(path, preset.input_dir, source.exclude)
      for source in preset.sources
    )
  ]
  return [face for path in paths for face in scan_file(path)]


def source_matches(face: Face, source: Source, root: Path) -> bool:
  return (
    matches(face.path, root, source.files)
    and not matches(face.path, root, source.exclude)
    and (
      not source.families
      or face.family.casefold() in {f.casefold() for f in source.families}
    )
  )


def coordinates(
  face: Face, weight: int, style: str, overrides: dict[str, float]
) -> dict[str, float]:
  unknown = overrides.keys() - face.axes.keys()
  if unknown:
    raise ValueError(f"Unknown axes {sorted(unknown)} in {face.label}")
  result = {tag: axis.default for tag, axis in face.axes.items()}
  if "wght" in result:
    result["wght"] = weight
  if "ital" in result:
    result["ital"] = 1 if style == "italic" else 0
  for tag, value in overrides.items():
    if not isfinite(value):
      raise ValueError(f"Invalid coordinate {tag}={value}: {face.label}")
    result[tag] = value
  return {
    tag: min(face.axes[tag].maximum, max(face.axes[tag].minimum, value))
    for tag, value in result.items()
  }


def supports_style(face: Face, style: str) -> bool:
  if "ital" in face.axes and style in ("regular", "italic"):
    axis = face.axes["ital"]
    return axis.minimum <= (1 if style == "italic" else 0) <= axis.maximum
  return face.style == style


def select_source(
  preset: Preset,
  sources: list[Face],
  target: Family,
  template: Face,
  family: str,
  weight: int,
  style: str,
  prefer_variable: bool,
) -> tuple[Face, dict[str, float], str]:
  applicable = [
    mapping
    for mapping in preset.mappings
    if mapping.target in (target.id, family)
    and (mapping.face is None or mapping.face == template.postscript)
    and (mapping.weight is None or mapping.weight == weight)
    and (mapping.style is None or mapping.style == style)
  ]
  mapping = None
  if applicable:

    def specificity(item: Mapping) -> tuple[bool, int]:
      return item.face is not None, sum(
        value is not None for value in (item.weight, item.style)
      )

    best = max(map(specificity, applicable))
    applicable = [item for item in applicable if specificity(item) == best]
    if len(applicable) != 1:
      raise ValueError(f"Ambiguous mappings: {family} {weight} {style}")
    mapping = applicable[0]
  visual_weight = 400 if weight in target.regular_weights else weight
  source_style = mapping.source_style if mapping and mapping.source_style else style
  if mapping and mapping.source_weight is not None:
    visual_weight = mapping.source_weight
  group = mapping.group if mapping and mapping.group else target.group
  if mapping and mapping.file:
    candidates = [
      face
      for face in sources
      if matches(face.path, preset.input_dir, (mapping.file,))
      and (mapping.index is None or face.index == mapping.index)
    ]
  else:
    definitions = [source for source in preset.sources if group in source.groups]
    candidates = [
      face
      for face in sources
      if any(source_matches(face, source, preset.input_dir) for source in definitions)
      and supports_style(face, source_style)
    ]
    if not candidates:
      fallbacks = {
        source.fallback_style for source in definitions if source.fallback_style
      }
      if len(fallbacks) > 1:
        raise ValueError(f"Conflicting fallback styles in group {group}")
      if fallbacks:
        source_style = fallbacks.pop()
        candidates = [
          face
          for face in sources
          if supports_style(face, source_style)
          and any(
            source_matches(face, source, preset.input_dir) for source in definitions
          )
        ]
  if not candidates:
    raise ValueError(f"No input face for {family} {weight} {style} (group {group})")

  def score(face: Face) -> tuple[bool, float, float, int]:
    value = visual_weight
    if "wght" in face.axes:
      axis = face.axes["wght"]
      value = min(axis.maximum, max(axis.minimum, value))
    else:
      value = face.weight
    return (
      prefer_variable and not face.axes,
      abs(value - visual_weight),
      value,
      abs(face.width - template.width),
    )

  best = min(map(score, candidates))
  candidates = [face for face in candidates if score(face) == best]
  if len(candidates) != 1:
    raise ValueError(
      f"Ambiguous input for {family} {weight} {style}: "
      + ", ".join(face.label for face in candidates)
    )
  face = candidates[0]
  require_truetype(face)
  axes = coordinates(face, visual_weight, source_style, mapping.axes if mapping else {})
  if prefer_variable and face.axes:
    axes = {tag: axes[tag] for tag in mapping.axes} if mapping else {}
  reason = "mapping" if mapping else f"group:{group}"
  if weight in target.regular_weights:
    reason += "; readability:Regular"
  reason += f"; requested:{visual_weight}/{source_style}; selected:{axes.get('wght', face.weight)}"
  return face, axes, reason


def make_plan(
  system_dir: Path,
  preset: Preset,
  targets: tuple[Family, ...],
  selected: list[str] | None = None,
) -> Plan:
  if selected:
    unknown = set(selected) - {family.id for family in targets}
    if unknown:
      raise ValueError(f"Unknown targets: {sorted(unknown)}")
  targets = (
    tuple(family for family in targets if family.id in selected)
    if selected
    else tuple(family for family in targets if family.enabled)
  )
  filenames = {name.casefold() for target in targets for name in target.files}
  system = [
    face
    for path in font_paths(system_dir)
    if path.name.casefold() in filenames
    for face in scan_file(path)
  ]
  sources = scan_sources(preset)
  by_file: dict[Path, list[Face]] = defaultdict(list)
  for face in system:
    by_file[face.path].append(face)
  outputs: dict[str, Output] = {}
  assigned: dict[tuple[Path, int], Task] = {}
  identities: dict[tuple[str, int, int, str], Task] = {}
  skipped: list[str] = []

  def task_for(
    target: Family,
    face: Face,
    family: str,
    weight: int,
    style: str,
    patch: Patch | None = None,
  ) -> Task:
    require_truetype(face)
    source, axes, reason = select_source(
      preset,
      sources,
      target,
      face,
      family,
      weight,
      style,
      patch is None
      and (
        bool(face.axes)
        or face.path.name.casefold()
        in {name.casefold() for name in target.variable_files}
      ),
    )
    if source.axes.keys() - axes.keys():
      weight = round(axes["wght"]) if "wght" in axes else source.weight
    task = Task(
      target,
      face,
      source,
      family,
      weight,
      face.width,
      style,
      axes,
      coordinates(face, weight, style, {}),
      reason,
      patch,
    )
    if task.identity in identities:
      other = identities[task.identity]
      raise ValueError(
        f"Duplicate output identity {task.identity}: "
        f"{other.template.label} and {face.label}; use a clean system snapshot"
      )
    identities[task.identity] = task
    return task

  for target in targets:
    names = {name.casefold() for name in target.names}
    candidates = {name.casefold() for name in target.files}
    members = [
      face
      for face in system
      if face.path.name.casefold() in candidates and face.family.casefold() in names
    ]
    for path, faces in by_file.items():
      if path.name.casefold() in candidates and not any(
        face in members for face in faces
      ):
        skipped.append(
          f"{target.id}: {path.name} has other identities: "
          + ", ".join(face.family for face in faces)
        )
    if not members:
      skipped.append(f"{target.id}: family not installed; patches skipped")
      continue
    for face in members:
      if face.key in assigned:
        raise ValueError(f"Face selected by multiple targets: {face.label}")
      family = target.variable_family or face.family
      weight = 400 if face.axes else face.weight
      assigned[face.key] = task_for(target, face, family, weight, face.style)

    for family in dict.fromkeys(
      target.variable_family or face.family for face in members
    ):
      family_faces = [
        face for face in members if (target.variable_family or face.family) == family
      ]
      for patch in target.patches:
        if any(
          not face.axes and face.weight == patch.weight and face.style == patch.style
          for face in family_faces
        ):
          skipped.append(
            f"{family} {patch.weight} {patch.style}: existing static face replaces patch"
          )
          continue
        templates = [face for face in family_faces if supports_style(face, patch.style)]
        if not templates:
          raise ValueError(f"No {patch.style} metadata template for patch {family}")
        templates.sort(
          key=lambda face: (
            face.weight != 400,
            abs(face.weight - patch.weight),
            face.path.as_posix().casefold(),
            face.index,
          )
        )
        face = templates[0]
        task = task_for(target, face, family, patch.weight, patch.style, patch)
        key = patch.output.casefold()
        output = outputs.setdefault(key, Output(patch.output, None, []))
        output.members.append(task)

  for path, members in by_file.items():
    if not any(face.key in assigned for face in members):
      continue
    key = path.name.casefold()
    if key in outputs:
      raise ValueError(f"Output filename conflict: {path.name}")
    if path.suffix.casefold() != (".ttc" if members[0].collection else ".ttf"):
      raise ValueError(f"Container/extension mismatch: {path}")
    outputs[key] = Output(
      path.name, path, [assigned.get(face.key, face) for face in members]
    )
  for output in outputs.values():
    if not output.name.lower().endswith(".ttc") and len(output.members) != 1:
      raise ValueError(f"Multiple faces need a TTC output: {output.name}")
  return Plan(
    system_dir,
    preset.input_dir,
    sorted(outputs.values(), key=lambda out: out.name.casefold()),
    skipped,
  )
