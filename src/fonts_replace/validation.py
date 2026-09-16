import hashlib
from typing import Literal, TypedDict

from fontTools.ttLib import TTFont

from .metadata import VARIABLE_TABLES, name_references, vertical_metrics

NameSnapshot = tuple[int, int, int, int, str]


class Snapshot(TypedDict):
  names: list[NameSnapshot]
  weight: int
  width: int
  selection: int
  mac_style: int
  upem: int
  metrics: dict[str, dict[str, int]]
  tables: dict[str, str]


SnapshotField = Literal[
  "names", "weight", "width", "selection", "mac_style", "upem", "metrics"
]
SNAPSHOT_FIELDS: tuple[SnapshotField, ...] = (
  "names",
  "weight",
  "width",
  "selection",
  "mac_style",
  "upem",
  "metrics",
)


def names(font: TTFont) -> list[NameSnapshot]:
  return sorted(
    (
      record.nameID,
      record.platformID,
      record.platEncID,
      record.langID,
      record.toUnicode(),
    )
    for record in font["name"].names
  )


def table_hashes(font: TTFont, tags: tuple[str, ...]) -> dict[str, str]:
  return {
    tag: hashlib.sha256(font.getTableData(tag)).hexdigest()
    for tag in tags
    if tag in font
  }


def snapshot(font: TTFont) -> Snapshot:
  return {
    "names": names(font),
    "weight": font["OS/2"].usWeightClass,
    "width": font["OS/2"].usWidthClass,
    "selection": font["OS/2"].fsSelection,
    "mac_style": font["head"].macStyle,
    "upem": font["head"].unitsPerEm,
    "metrics": vertical_metrics(font),
    "tables": table_hashes(
      font,
      (
        "glyf",
        "loca",
        "hmtx",
        "cmap",
        "GSUB",
        "GPOS",
        "GDEF",
        "STAT",
        *VARIABLE_TABLES,
      ),
    ),
  }


def validate(font: TTFont, expected: Snapshot, replaced: bool) -> None:
  actual = snapshot(font)
  for field in SNAPSHOT_FIELDS:
    if actual[field] != expected[field]:
      raise ValueError(f"Output validation failed: {field}")
  if actual["tables"] != expected["tables"]:
    detail = [
      tag
      for tag, digest in expected["tables"].items()
      if actual["tables"].get(tag) != digest
    ]
    raise ValueError(f"Output validation failed: {detail}")
  if not replaced:
    return
  if (
    font["head"].yMax > font["OS/2"].usWinAscent
    or -font["head"].yMin > font["OS/2"].usWinDescent
  ):
    raise ValueError("Output clipping metrics do not contain glyph bounds")
  if "DSIG" in font:
    raise ValueError("Output contains an invalid signature")
  if "fvar" not in font and (
    any(tag in font for tag in VARIABLE_TABLES) or "STAT" in font
  ):
    raise ValueError("Static output contains variable tables")
  glyphs = set(font.getGlyphOrder())
  if not set((font.getBestCmap() or {}).values()) <= glyphs:
    raise ValueError("Output character map references missing glyphs")
  if set(font["hmtx"].metrics) != glyphs:
    raise ValueError("Output horizontal metrics do not cover all glyphs")
  glyf = font["glyf"]
  for glyph in glyf.glyphs.values():
    if any(component not in glyphs for component in glyph.getComponentNames(glyf)):
      raise ValueError("Output composite references a missing glyph")
  missing = (
    name_references(font)
    - {record.nameID for record in font["name"].names}
    - {0, 65535}
  )
  if missing:
    raise ValueError(f"Output contains unresolved name references: {sorted(missing)}")
