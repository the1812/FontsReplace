from copy import deepcopy

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._n_a_m_e import NameRecordVisitor
from fontTools.ttLib.ttVisitor import TTVisitor
from fontTools.varLib.instancer import instantiateVariableFont

from .models import Task

VERTICAL_FIELDS = {
  "hhea": ("ascent", "descent", "lineGap"),
  "OS/2": (
    "sTypoAscender",
    "sTypoDescender",
    "sTypoLineGap",
    "usWinAscent",
    "usWinDescent",
  ),
}
VARIABLE_TABLES = ("fvar", "avar", "gvar", "cvar", "HVAR", "VVAR", "MVAR", "VARC")
WEIGHTS = {
  100: "Thin",
  200: "ExtraLight",
  300: "Light",
  350: "Semilight",
  400: "Regular",
  500: "Medium",
  600: "Semibold",
  700: "Bold",
  800: "ExtraBold",
  900: "Black",
}


def instantiate(font: TTFont, axes: dict[str, float]) -> TTFont:
  if "fvar" in font:
    instantiateVariableFont(font, axes, inplace=True, updateFontNames=False)
  for tag in ("STAT", "DSIG"):
    if tag in font:
      del font[tag]
  font["name"].removeNames(nameID=25)
  return font


class NameRemapper(TTVisitor):
  def __init__(self, offset: int):
    self.offset = offset

  def visitAttr(self, obj, attr, value, *args, **kwargs):
    if attr.endswith("NameID") and 256 <= value < 65535:
      setattr(obj, attr, value + self.offset)
    elif attr in ("paletteLabels", "paletteEntryLabels"):
      setattr(
        obj,
        attr,
        [item + self.offset if 256 <= item < 65535 else item for item in value],
      )
    else:
      super().visitAttr(obj, attr, value, *args, **kwargs)


def transplant_names(font: TTFont, template: TTFont) -> None:
  visitor = NameRecordVisitor()
  visitor.visit(font)
  references = visitor.seen - {0, 65535}
  donor_names = deepcopy(font["name"])
  donor_ltag = deepcopy(font["ltag"]) if "ltag" in font else None
  font["name"] = deepcopy(template["name"])
  if "ltag" in template:
    font["ltag"] = deepcopy(template["ltag"])
  elif "ltag" in font:
    del font["ltag"]
  offset = max(255, max(record.nameID for record in font["name"].names)) + 1
  if references and max(references) + offset > 32767:
    raise ValueError("Not enough custom name IDs for replacement layout features")
  for tag in ("GSUB", "GPOS", "CPAL"):
    if tag in font:
      NameRemapper(offset).visit(font[tag])
  for name_id in references:
    records = [record for record in donor_names.names if record.nameID == name_id]
    if not records:
      raise ValueError(f"Input layout references missing name ID {name_id}")
    if name_id < 256:
      if donor_names.getDebugName(name_id) != font["name"].getDebugName(name_id):
        raise ValueError(f"Layout name conflicts with system identity: {name_id}")
      continue
    for record in records:
      record.nameID += offset
      if record.platformID == 0 and record.langID != 65535 and donor_ltag:
        if "ltag" not in font:
          from fontTools.ttLib import newTable

          font["ltag"] = newTable("ltag")
        record.langID = font["ltag"].addTag(donor_ltag.tags[record.langID])
      font["name"].names.append(record)


def set_identity(font: TTFont, task: Task) -> None:
  name = font["name"]
  weight_name = WEIGHTS.get(task.weight, str(task.weight))
  slope = {"regular": "", "italic": "Italic", "oblique": "Oblique"}[task.style]
  style = (
    " ".join(
      part for part in (weight_name if task.weight != 400 else "", slope) if part
    )
    or "Regular"
  )
  extended = task.patch is not None and task.patch.naming == "extended"
  locales = {
    (record.platformID, record.platEncID, record.langID)
    for record in name.names
    if record.nameID == 1
  }
  locales.add((3, 1, 1033))
  ps_family = "".join(char for char in task.family if char.isascii() and char.isalnum())
  postscript = ps_family + ("-" + style.replace(" ", "") if style != "Regular" else "")
  if not postscript or len(postscript) > 63:
    raise ValueError(f"Invalid generated PostScript name: {postscript}")
  for platform, encoding, language in locales:
    local = name.getName(16, platform, encoding, language) or name.getName(
      1, platform, encoding, language
    )
    family = local.toUnicode() if local else task.family
    if task.target.static_family:
      family = task.family
    elif not name.getName(16, platform, encoding, language):
      for suffix in (
        " Regular",
        " Light",
        " Semilight",
        " Semibold",
        " Bold",
        " Italic",
        " Medium",
      ):
        family = family.removesuffix(suffix)
    legacy_family = family + (
      f" {weight_name}" if extended and task.weight not in (400, 700) else ""
    )
    legacy_style = slope or "Regular"
    if extended and task.weight == 700:
      legacy_style = "Bold" + (f" {slope}" if slope else "")
    values = {
      1: legacy_family,
      2: legacy_style,
      3: f"{family}-{style.replace(' ', '')}",
      4: family + (f" {style}" if style != "Regular" else ""),
      6: postscript,
      16: family,
      17: style,
    }
    for name_id in (21, 22):
      if name.getName(name_id, platform, encoding, language):
        values[name_id] = family if name_id == 21 else style
    for name_id, value in values.items():
      name.setName(value, name_id, platform, encoding, language)


def vertical_metrics(font: TTFont) -> dict[str, dict[str, int]]:
  return {
    tag: {field: getattr(font[tag], field) for field in fields}
    for tag, fields in VERTICAL_FIELDS.items()
  }


def apply_metadata(font: TTFont, template: TTFont, task: Task) -> dict:
  if task.family.casefold() == "segoe ui":
    cmap = font.getBestCmap() or {}
    ratio_name, colon_name = cmap.get(0x2236), cmap.get(0x003A)
    if ratio_name and colon_name and ratio_name != colon_name:
      glyph = font["glyf"][ratio_name]
      width = font["hmtx"][colon_name][0]
      if glyph.numberOfContours and font["hmtx"][ratio_name][0] > width:
        left = round((width - (glyph.xMax - glyph.xMin)) / 2)
        offset = left - glyph.xMin
        if glyph.isComposite():
          for component in glyph.components:
            if hasattr(component, "x"):
              component.x += offset
        else:
          glyph.coordinates.translate((offset, 0))
        glyph.recalcBounds(font["glyf"])
        font["hmtx"][ratio_name] = (width, left)
  font.getTableData("glyf")
  font["maxp"].recalc(font)
  transplant_names(font, template)
  derived = task.patch is not None or bool(task.template.axes)
  if derived:
    set_identity(font, task)
    font["name"].removeUnusedNames(font)
  os2 = font["OS/2"]
  original = template["OS/2"]
  os2.usWeightClass = task.weight
  os2.usWidthClass = task.width
  os2.fsSelection = original.fsSelection
  font["head"].macStyle = template["head"].macStyle
  if derived:
    os2.fsSelection &= ~(1 | 32 | 64 | 512)
    font["head"].macStyle &= ~3
    if task.style != "regular":
      os2.fsSelection |= 1 if task.style == "italic" else 512
      font["head"].macStyle |= 2
    if task.patch and task.patch.naming == "extended" and task.weight == 700:
      os2.fsSelection |= 32
      font["head"].macStyle |= 1
    elif task.weight == 400 and task.style == "regular":
      os2.fsSelection |= 64
  if os2.fsSelection & (128 | 256 | 512):
    os2.version = max(4, os2.version)
  font["post"].italicAngle = template["post"].italicAngle
  for field in ("caretSlopeRise", "caretSlopeRun"):
    setattr(font["hhea"], field, getattr(template["hhea"], field))
  ratio = font["head"].unitsPerEm / template["head"].unitsPerEm
  font["hhea"].caretOffset = round(template["hhea"].caretOffset * ratio)
  before = vertical_metrics(template)
  for tag, fields in before.items():
    for field, value in fields.items():
      setattr(font[tag], field, round(value * ratio))
  clipping_expanded = (
    font["head"].yMax > os2.usWinAscent or -font["head"].yMin > os2.usWinDescent
  )
  os2.usWinAscent = max(os2.usWinAscent, font["head"].yMax)
  os2.usWinDescent = max(os2.usWinDescent, -font["head"].yMin)
  os2.recalcUnicodeRanges(font)
  if os2.version >= 1:
    os2.recalcCodePageRanges(font)
  os2.recalcAvgCharWidth(font)
  codepoints = set(font.getBestCmap() or {})
  original_codepoints = set(template.getBestCmap() or {})
  os2.usFirstCharIndex = min(min(codepoints, default=0), 65535)
  os2.usLastCharIndex = min(max(codepoints, default=0), 65535)
  if os2.version >= 2:
    os2.usDefaultChar = 0
    os2.usBreakChar = 32 if 32 in codepoints else 0
  return {
    "metrics": {
      "policy": "system-with-glyph-bounds",
      "scale": ratio,
      "original": before,
      "output": vertical_metrics(font),
      "use_typo_metrics": bool(os2.fsSelection & 128),
      "clipping_expanded": clipping_expanded,
    },
    "coverage": {
      "original": len(original_codepoints),
      "output": len(codepoints),
      "lost": len(original_codepoints - codepoints),
    },
  }
