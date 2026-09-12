import hashlib

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._n_a_m_e import NameRecordVisitor

from .metadata import VARIABLE_TABLES, vertical_metrics


def names(font: TTFont) -> list[tuple]:
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


def snapshot(font: TTFont) -> dict:
  font.ensureDecompiled()
  return {
    "names": names(font),
    "weight": font["OS/2"].usWeightClass,
    "width": font["OS/2"].usWidthClass,
    "selection": font["OS/2"].fsSelection,
    "mac_style": font["head"].macStyle,
    "upem": font["head"].unitsPerEm,
    "metrics": vertical_metrics(font),
    "tables": table_hashes(font, ("glyf", "hmtx", "cmap", "GSUB", "GPOS", "GDEF")),
  }


def validate(font: TTFont, expected: dict, replaced: bool) -> None:
  actual = snapshot(font)
  for field, value in expected.items():
    if actual[field] != value:
      detail = (
        [tag for tag, digest in value.items() if actual[field].get(tag) != digest]
        if field == "tables"
        else field
      )
      raise ValueError(f"Output validation failed: {detail}")
  if not replaced:
    return
  if any(tag in font for tag in VARIABLE_TABLES) or "STAT" in font or "DSIG" in font:
    raise ValueError("Static output contains variable tables or an invalid signature")
  glyphs = set(font.getGlyphOrder())
  if not set((font.getBestCmap() or {}).values()) <= glyphs:
    raise ValueError("Output character map references missing glyphs")
  if set(font["hmtx"].metrics) != glyphs:
    raise ValueError("Output horizontal metrics do not cover all glyphs")
  for glyph in font["glyf"].glyphs.values():
    if glyph.isComposite() and any(
      component.glyphName not in glyphs for component in glyph.components
    ):
      raise ValueError("Output composite references a missing glyph")
  visitor = NameRecordVisitor()
  visitor.visit(font)
  missing = visitor.seen - {record.nameID for record in font["name"].names} - {0, 65535}
  if missing:
    raise ValueError(f"Output contains unresolved name references: {sorted(missing)}")
