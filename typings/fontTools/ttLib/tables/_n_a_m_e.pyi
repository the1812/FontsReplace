from fontTools.ttLib.ttVisitor import TTVisitor

class NameRecordVisitor(TTVisitor):
  TABLES: tuple[str, ...]
  seen: set[int]
