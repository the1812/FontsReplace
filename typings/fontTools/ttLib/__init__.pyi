from collections.abc import Sequence
from os import PathLike
from typing import BinaryIO, Literal, Protocol, Self, overload

class TTLibError(Exception): ...

class NameRecord(Protocol):
  nameID: int
  platformID: int
  platEncID: int
  langID: int
  offset: int
  length: int

  def toUnicode(self) -> str: ...

class NameTable(Protocol):
  names: list[NameRecord]

  def getDebugName(self, nameID: int) -> str | None: ...
  def getName(
    self, nameID: int, platformID: int, platEncID: int, langID: int | None = None
  ) -> NameRecord | None: ...
  def setName(
    self,
    string: str,
    nameID: int,
    platformID: int,
    platEncID: int,
    langID: int,
  ) -> None: ...
  def removeNames(
    self,
    nameID: int | None = None,
    platformID: int | None = None,
    platEncID: int | None = None,
    langID: int | None = None,
  ) -> None: ...

class LtagTable(Protocol):
  tags: list[str]

  def addTag(self, tag: str) -> int: ...

class OS2Table(Protocol):
  usWeightClass: int
  usWidthClass: int
  fsSelection: int
  version: int
  sTypoAscender: int
  sTypoDescender: int
  sTypoLineGap: int
  usWinAscent: int
  usWinDescent: int
  usFirstCharIndex: int
  usLastCharIndex: int
  usDefaultChar: int
  usBreakChar: int

  def recalcUnicodeRanges(
    self, ttFont: TTFont, pruneOnly: bool = False
  ) -> set[int]: ...
  def recalcCodePageRanges(
    self, ttFont: TTFont, pruneOnly: bool = False
  ) -> set[int]: ...
  def recalcAvgCharWidth(self, ttFont: TTFont) -> int: ...

class HeadTable(Protocol):
  unitsPerEm: int
  macStyle: int
  xMin: int
  yMin: int
  xMax: int
  yMax: int

class HheaTable(Protocol):
  ascent: int
  descent: int
  lineGap: int
  caretSlopeRise: int
  caretSlopeRun: int
  caretOffset: int

class PostTable(Protocol):
  italicAngle: float

class FvarAxis(Protocol):
  axisTag: str
  minValue: float
  defaultValue: float
  maxValue: float

class FvarInstance(Protocol):
  postscriptNameID: int

class FvarTable(Protocol):
  axes: list[FvarAxis]
  instances: list[FvarInstance]

class MvarValueRecord(Protocol):
  ValueTag: str
  VarIdx: int

class MvarData(Protocol):
  VarStore: object
  ValueRecord: list[MvarValueRecord]
  ValueRecordCount: int

class MvarTable(Protocol):
  table: MvarData

class GlyphCoordinates(Protocol):
  def translate(self, delta: tuple[int, int]) -> None: ...

class GlyphComponent(Protocol):
  x: int

class Glyph(Protocol):
  numberOfContours: int
  xMin: int
  xMax: int
  components: list[object]
  coordinates: GlyphCoordinates

  def isComposite(self) -> bool: ...
  def recalcBounds(self, glyfTable: GlyfTable) -> None: ...
  def getComponentNames(self, glyfTable: GlyfTable) -> list[str]: ...

class GlyfTable(Protocol):
  glyphs: dict[str, Glyph]

  def __getitem__(self, glyphName: str) -> Glyph: ...

class HmtxTable(Protocol):
  metrics: dict[str, tuple[int, int]]

  def __getitem__(self, glyphName: str) -> tuple[int, int]: ...
  def __setitem__(self, glyphName: str, metrics: tuple[int, int]) -> None: ...

class LocaTable(Protocol):
  locations: Sequence[int]

class MaxpTable(Protocol):
  def recalc(self, ttFont: TTFont) -> None: ...

class TTFont:
  recalcBBoxes: bool
  flavor: str | None

  def __init__(
    self,
    file: str | PathLike[str] | BinaryIO | None = None,
    *,
    recalcBBoxes: bool = ...,
    recalcTimestamp: bool = ...,
    fontNumber: int = ...,
    lazy: bool | None = ...,
  ) -> None: ...
  def __enter__(self) -> Self: ...
  def __exit__(
    self,
    exc_type: type[BaseException] | None,
    exc_value: BaseException | None,
    traceback: object,
  ) -> None: ...
  def close(self) -> None: ...
  def save(
    self, file: str | PathLike[str] | BinaryIO, reorderTables: bool | None = True
  ) -> None: ...
  @overload
  def __getitem__(self, tag: Literal["name"]) -> NameTable: ...
  @overload
  def __getitem__(self, tag: Literal["OS/2"]) -> OS2Table: ...
  @overload
  def __getitem__(self, tag: Literal["head"]) -> HeadTable: ...
  @overload
  def __getitem__(self, tag: Literal["hhea"]) -> HheaTable: ...
  @overload
  def __getitem__(self, tag: Literal["post"]) -> PostTable: ...
  @overload
  def __getitem__(self, tag: Literal["fvar"]) -> FvarTable: ...
  @overload
  def __getitem__(self, tag: Literal["MVAR"]) -> MvarTable: ...
  @overload
  def __getitem__(self, tag: Literal["glyf"]) -> GlyfTable: ...
  @overload
  def __getitem__(self, tag: Literal["hmtx"]) -> HmtxTable: ...
  @overload
  def __getitem__(self, tag: Literal["loca"]) -> LocaTable: ...
  @overload
  def __getitem__(self, tag: Literal["maxp"]) -> MaxpTable: ...
  @overload
  def __getitem__(self, tag: Literal["ltag"]) -> LtagTable: ...
  @overload
  def __getitem__(self, tag: str) -> object: ...
  def __setitem__(self, tag: str, table: object) -> None: ...
  def __delitem__(self, tag: str) -> None: ...
  def __contains__(self, tag: str) -> bool: ...
  def getTableData(self, tag: str) -> bytes: ...
  def getBestCmap(self) -> dict[int, str] | None: ...
  def getGlyphOrder(self) -> list[str]: ...
  def normalizeLocation(self, location: dict[str, float]) -> dict[str, float]: ...

class TTCollection:
  fonts: list[TTFont]

  def __init__(
    self,
    file: str | PathLike[str] | BinaryIO | None = None,
    shareTables: bool = False,
    **kwargs: object,
  ) -> None: ...
  def __enter__(self) -> Self: ...
  def __exit__(
    self,
    exc_type: type[BaseException] | None,
    exc_value: BaseException | None,
    traceback: object,
  ) -> None: ...
  def close(self) -> None: ...
  def save(
    self, file: str | PathLike[str] | BinaryIO, shareTables: bool = True
  ) -> None: ...

@overload
def newTable(tag: Literal["ltag"]) -> LtagTable: ...
@overload
def newTable(tag: str) -> object: ...
