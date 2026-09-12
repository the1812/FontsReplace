import hashlib
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from urllib.request import urlopen
from zipfile import ZipFile

from .models import Preset


def fetch(preset: Preset, progress: Callable[[str], None]) -> None:
  download = preset.download
  if download is None:
    raise ValueError(f"Preset has no download source: {preset.path}")
  cache = preset.input_dir / ".downloads"
  cache.mkdir(parents=True, exist_ok=True)
  archive = cache / f"{download.sha256}.zip"
  with TemporaryDirectory(dir=cache) as temporary:
    staging = Path(temporary)
    if not archive.exists():
      progress(f"Downloading {download.url}")
      pending = staging / "download.zip"
      with urlopen(download.url, timeout=60) as response, pending.open("wb") as output:
        while chunk := response.read(1024 * 1024):
          output.write(chunk)
      with pending.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
      if digest != download.sha256:
        raise ValueError(
          f"Download SHA-256 mismatch: expected {download.sha256}, got {digest}"
        )
      pending.replace(archive)
    else:
      with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != download.sha256:
          raise ValueError(
            f"Cached download SHA-256 mismatch; remove {archive} and retry"
          )
    files: dict[Path, bytes] = {}
    with ZipFile(archive) as zipped:
      for directory in download.directories:
        members = [
          item
          for item in zipped.infolist()
          if not item.is_dir() and str(PurePosixPath(item.filename).parent) == directory
        ]
        if not any(item.filename.lower().endswith(".ttf") for item in members):
          raise ValueError(f"Download contains no TTF fonts in {directory}")
        for member in members:
          name = PurePosixPath(member.filename).name
          if Path(name).suffix.lower() != ".ttf" and name != "LICENSE.txt":
            continue
          relative = (
            Path("licenses") / PurePosixPath(directory).name / name
            if name == "LICENSE.txt"
            else Path(name)
          )
          content = zipped.read(member)
          if relative in files and files[relative] != content:
            raise ValueError(f"Conflicting download filenames: {relative}")
          files[relative] = content
    for relative, content in files.items():
      destination = preset.input_dir / relative
      if destination.exists() and destination.read_bytes() != content:
        raise ValueError(f"Existing file differs from download: {destination}")
      staged = staging / relative
      staged.parent.mkdir(parents=True, exist_ok=True)
      staged.write_bytes(content)
    written = 0
    for relative in files:
      destination = preset.input_dir / relative
      if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        (staging / relative).replace(destination)
        written += 1
    progress(
      f"Fetched {written} files, reused {len(files) - written}: {preset.input_dir}"
    )
