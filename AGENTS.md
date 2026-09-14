# Agent guide

Read [CONCEPTS.md](CONCEPTS.md) before changing configuration, source selection, metadata, or variable-font handling. It defines the terminology, configuration fields, and generation behavior.

## Development

- Use PowerShell and uv. Python >= 3.12; fontTools handles fonts. Keep Ruff's 2-space indentation.
- Keep README focused on user workflows, conceptual details in CONCEPTS.md, and agent instructions here.
- Keep system targets independent of source-specific presets.

## Code map

- `src/fonts_replace/cli.py`: `inspect`, `fetch`, and `build`; `build --dry-run` prints the plan.
- `config.py` / `models.py`: TOML parsing and data models.
- `inventory.py` / `planner.py`: font scanning, source selection, and output planning.
- `metadata.py` / `builder.py` / `validation.py`: metadata handling, generation, and read-back validation.
- `fetch.py`: downloads, SHA-256 verification, and extraction.
- `src/fonts_replace/data/windows.toml`: system targets and extra styles.
- `presets/*.toml`: source fonts and mappings.

## Constraints

- Generate files only. Do not install fonts, edit the registry, or overwrite system fonts, input fonts, or backups.
- Scan configured system filenames and verify internal identities. Skip absent families; generate configured extra styles when the family exists.
- Preserve TTC member order and unselected members. Prefer variable sources for variable targets; instantiate ordinary static targets and patches.
- Preserve system identity and layout semantics while using source glyphs and variation data. Handle UPM differences and clipping bounds. Report ambiguous selection, missing sources, and identity conflicts as errors.
- Allow existing output directories without emptiness checks. Validate all generated fonts before replacing same-name output files; preserve unrelated files.
- Keep JSON on stdout and progress on stderr. Do not place reports in the font output directory.

## Verification

```powershell
uv run ruff check .
uv run ruff format --check .
uv run fonts_replace build --dry-run --preset harmonyos
```

For download or generation changes, verify `fetch harmonyos` followed by `build --preset harmonyos` using isolated input and output directories. Use `--input-dir`, `--system-dir`, and `--output` to select verification paths. Check repeated builds overwrite same-name files.

For variable-font changes, verify both variable output and static fallback, including axis/name references and actual glyph variation. Distinguish file or fixture validation from installed Windows rendering; do not claim the latter without checking it.
