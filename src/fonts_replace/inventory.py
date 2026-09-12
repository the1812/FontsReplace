from fnmatch import fnmatchcase
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont

from .models import Axis, Face


def matches(path: Path, root: Path, patterns: tuple[str, ...]) -> bool:
  relative = path.relative_to(root).as_posix().casefold()
  return any(fnmatchcase(relative, pattern.casefold()) for pattern in patterns)


def font_paths(root: Path) -> list[Path]:
  if not root.is_dir():
    raise ValueError(f"Font directory does not exist: {root}")
  return sorted(
    (
      path
      for path in root.rglob("*")
      if path.is_file()
      and path.suffix.casefold() in (".ttf", ".ttc", ".otf", ".otc", ".woff", ".woff2")
    ),
    key=lambda path: path.as_posix().casefold(),
  )


def is_collection(path: Path) -> bool:
  with path.open("rb") as stream:
    return stream.read(4) == b"ttcf"


def describe(font: TTFont, path: Path, index: int, collection: bool) -> Face:
  name = font["name"]
  os2 = font["OS/2"]
  style = (
    "oblique"
    if os2.fsSelection & 512
    else "italic"
    if os2.fsSelection & 1
    else "regular"
  )
  axes = (
    {
      axis.axisTag: Axis(axis.minValue, axis.defaultValue, axis.maxValue)
      for axis in font["fvar"].axes
    }
    if "fvar" in font
    else {}
  )
  return Face(
    path=path,
    index=index,
    collection=collection,
    family=name.getDebugName(16) or name.getDebugName(1) or "",
    subfamily=name.getDebugName(17) or name.getDebugName(2) or "",
    postscript=name.getDebugName(6) or "",
    weight=os2.usWeightClass,
    width=os2.usWidthClass,
    style=style,
    upem=font["head"].unitsPerEm,
    version=name.getDebugName(5) or "",
    axes=axes,
    outline="TrueType" if "glyf" in font and font.flavor is None else "unsupported",
  )


def scan_file(path: Path) -> list[Face]:
  if is_collection(path):
    collection = TTCollection(path, lazy=True)
    try:
      return [
        describe(font, path, index, True) for index, font in enumerate(collection.fonts)
      ]
    finally:
      collection.close()
  with TTFont(path, lazy=True) as font:
    return [describe(font, path, 0, False)]


def require_truetype(face: Face) -> None:
  if face.outline != "TrueType":
    raise ValueError(f"Only TrueType outlines in TTF/TTC are supported: {face.label}")
