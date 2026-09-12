from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Axis:
  minimum: float
  default: float
  maximum: float


@dataclass(frozen=True)
class Face:
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
  axes: dict[str, Axis]
  outline: str

  @property
  def key(self) -> tuple[Path, int]:
    return self.path, self.index

  @property
  def label(self) -> str:
    return f"{self.path.name}#{self.index} ({self.family}, {self.subfamily})"


@dataclass(frozen=True)
class Patch:
  weight: int
  style: str
  output: str
  naming: str = "compatible"


@dataclass(frozen=True)
class Family:
  id: str
  names: tuple[str, ...]
  files: tuple[str, ...]
  group: str
  regular_weights: tuple[int, ...]
  patches: tuple[Patch, ...]
  enabled: bool = True
  static_family: str | None = None


@dataclass(frozen=True)
class Source:
  groups: tuple[str, ...]
  files: tuple[str, ...]
  exclude: tuple[str, ...]
  families: tuple[str, ...]
  fallback_style: str | None = None


@dataclass(frozen=True)
class Mapping:
  target: str
  face: str | None = None
  weight: int | None = None
  style: str | None = None
  file: str | None = None
  index: int | None = None
  group: str | None = None
  source_weight: int | None = None
  source_style: str | None = None
  axes: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Download:
  url: str
  sha256: str
  directories: tuple[str, ...]


@dataclass(frozen=True)
class Preset:
  path: Path
  input_dir: Path
  sources: tuple[Source, ...]
  mappings: tuple[Mapping, ...]
  download: Download | None = None


@dataclass(frozen=True)
class Task:
  target: Family
  template: Face
  source: Face
  family: str
  weight: int
  width: int
  style: str
  source_axes: dict[str, float]
  target_axes: dict[str, float]
  reason: str
  patch: Patch | None = None

  @property
  def identity(self) -> tuple[str, int, int, str]:
    return self.family.casefold(), self.weight, self.width, self.style


@dataclass
class Output:
  name: str
  original: Path | None
  members: list[Task | Face]


@dataclass
class Plan:
  system_dir: Path
  input_dir: Path
  outputs: list[Output]
  skipped: list[str]
