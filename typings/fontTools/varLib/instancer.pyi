from contextlib import AbstractContextManager

from fontTools.ttLib import TTFont

def instantiateVariableFont(
  varfont: TTFont,
  axisLimits: dict[str, float],
  inplace: bool = False,
  optimize: bool = True,
  overlap: object = ...,
  updateFontNames: bool = False,
  *,
  downgradeCFF2: bool = False,
  static: bool = False,
) -> TTFont: ...
def verticalMetricsKeptInSync(varfont: TTFont) -> AbstractContextManager[bool]: ...
