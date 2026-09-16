from collections.abc import Sequence

from fontTools.ttLib import FvarAxis

class VarStoreInstancer:
  def __init__(
    self,
    varstore: object,
    fvar_axes: Sequence[FvarAxis],
    location: dict[str, float] = ...,
  ) -> None: ...
  def __getitem__(self, varidx: int) -> float: ...
