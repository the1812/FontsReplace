# Project concepts

FontsReplace combines the glyphs of a **source font** with the identity and selected layout metadata of a **system font**. It generates replacement TTF/TTC files; it does not install fonts or modify the registry.

A **face** is one font inside a file. A TTF contains one face; a TTC contains multiple faces. Replacement operates on faces, then rebuilds each TTC in its original member order, preserving unselected members.

Two configurations have separate responsibilities:

- A **preset** describes the source fonts and how to choose them. See [presets/harmonyos.toml](presets/harmonyos.toml).
- A **target configuration** describes the system fonts to replace and extra styles to generate. See [src/fonts_replace/data/windows.toml](src/fonts_replace/data/windows.toml). Keep source-specific filenames out of this configuration.

## Presets

`--preset harmonyos` resolves to `presets/harmonyos.toml` relative to the working directory. A full TOML path is also accepted. The same resolution applies to `fetch harmonyos`.

### Root fields

| Field | Meaning |
| --- | --- |
| `input_dir` | Required source font directory, relative to the preset file. `--input-dir` overrides it with a path relative to the working directory. |
| `[[sources]]` | Required list of source-selection rules. Multiple rules can contribute candidates to the same group. |
| `[[mappings]]` | Optional exceptions for individual targets, faces, weights, or styles. |
| `[download]` | Optional ZIP download configuration used by `fetch`. Omit it for manually supplied fonts. |

### Source rules: `[[sources]]`

| Field | Default | Meaning |
| --- | --- | --- |
| `groups` | Required | Routing labels such as `en`, `zh-Hans`, `zh-Hant`, or `ja`. A target's `group` selects matching source rules. These labels do not check character coverage. |
| `files` | `["*.ttf", "*.ttc"]` | Filename patterns relative to `input_dir`. Matching is case-insensitive and uses `/` separators. |
| `exclude` | `[]` | Patterns excluded from this rule. Another rule or an explicit mapping can still select those files. |
| `families` | `[]` | Allowed internal font family names, matched case-insensitively. Empty means no family filter. |
| `fallback_style` | Unset | Source style to use if the group has no candidate for the requested style: `regular`, `italic`, or `oblique`. It does not synthesize slanted glyphs. |

Source directories are scanned recursively. Patterns are matched against the entire relative path using `fnmatchcase`; `*` can also match `/` in that path. Only TrueType outlines in TTF/TTC containers are supported for generation.

For example, this manually supplied preset uses one font collection for all language groups:

```toml
input_dir = "../fonts/MiSans"

[[sources]]
groups = ["en", "zh-Hans", "zh-Hant", "ja"]
files = ["*.ttf"]
fallback_style = "regular"
```

### Mapping rules: `[[mappings]]`

A mapping selects a target with `target`, optionally narrows it with `face`, `weight`, and `style`, then changes source selection with the remaining fields.

| Field | Default | Meaning |
| --- | --- | --- |
| `target` | Required | Target configuration ID, such as `yahei`, or the output family name. Matched exactly, including case. |
| `face` | Unset | System template's PostScript name, matched exactly. This is not a source face name. |
| `weight` | Unset | Target weight to match, before source-weight adjustments. |
| `style` | Unset | Target style to match: `regular`, `italic`, or `oblique`. |
| `group` | Target's group | Select a different source group. |
| `file` | Unset | Source file pattern relative to `input_dir`. Bypasses source-rule family, group, exclusion, and style filters. |
| `index` | Unset | Zero-based source face index, used only with `file`; useful for TTC files. |
| `source_weight` | Requested weight | Override the weight used to select or instantiate the source. Takes precedence over `regular_weights`. |
| `source_style` | Target style | Override the requested source style without changing the target's style identity. |
| `axes` | `{}` | Source axis coordinates, for example `{ wght = 500, opsz = 14 }`. Unknown axes or non-finite values are errors; coordinates are clamped to the source range. |

Only one mapping is applied. A `face` selector has priority over mappings without one; next, the mapping with more `weight`/`style` selectors wins. Equal specificity is an error. Mappings are not merged or applied in file order.

For example, use a 500-weight source for a static 600-weight YaHei target:

```toml
[[mappings]]
target = "yahei"
weight = 600
source_weight = 500
```

### Download configuration: `[download]`

| Field | Meaning |
| --- | --- |
| `url` | Required ZIP archive URL. |
| `sha256` | Required expected archive SHA-256, including for cached downloads. |
| `directories` | Required list of exact directories inside the ZIP. Only their direct `.ttf` files and `LICENSE.txt` are extracted. |

`fetch` caches the archive under `input_dir/.downloads/`, places font files directly in `input_dir`, and saves licenses under `input_dir/licenses/<directory-name>/`. Identical existing files are reused; conflicting contents are an error. `build` does not download missing fonts automatically.

## System targets: `windows.toml`

The bundled configuration uses Windows 11 fonts as its baseline. `--targets path/to/windows.toml` replaces the whole target configuration, rather than merging with it.

By default, system templates come from `%WINDIR%/Fonts`. `--system-dir` selects another directory, such as a clean font backup. Only filenames listed in selected targets are scanned, and their internal family names must also match. A missing family is skipped, including its extra styles.

### Family rules: `[[families]]`

| Field | Default | Meaning |
| --- | --- | --- |
| `id` | Required | Unique target ID, used by `--family` and preset mappings. |
| `names` | Required | Accepted internal system family names, matched case-insensitively. One target may include multiple related families. |
| `files` | `[]` | Exact candidate filenames, matched case-insensitively. These are not glob patterns. No files means no system faces can be selected. |
| `group` | Required | Default source-group label. |
| `regular_weights` | `[]` | Target weights that request a 400-weight source for readability. Static output retains the target's original weight identity. |
| `enabled` | `true` | Include this target by default. Explicit `--family` selection can include a disabled target. |
| `variable_family` | Unset | Common output family name for this target, used for both variable output and static fallback, and for grouping extra styles. Otherwise use each system face's family. |
| `variable_files` | `[]` | Filenames to treat as variable targets even if the installed file is an earlier static replacement. Include these filenames in `files` too. Actual variable system faces are recognized without this field. |
| `[[families.patches]]` | None | Additional static styles to generate for each matched output family. |

### Extra styles: `[[families.patches]]`

A patch generates a missing style, such as Medium or Semibold, using an installed family member as its metadata template. It does not require the patch's output file to already exist. If a static face with that weight and style exists, it is replaced normally and the patch is skipped.

| Field | Default | Meaning |
| --- | --- | --- |
| `weight` | Required | Output weight, from 1 to 1000. |
| `style` | Required | `regular`, `italic`, or `oblique`. A compatible system template must exist. |
| `output` | Required | Output filename ending in `.ttf` or `.ttc`, without directory components. Use TTC when multiple output families share this patch file. |
| `naming` | `"compatible"` | `compatible` retains the family grouping and uses Regular/Italic-style legacy names. `extended` separates non-400/700 weights into legacy families and uses Bold style linking for weight 700. Both modes set typographic family and style names. |

For example, Segoe UI Variable declares `SegUIVar.ttf` as a variable target and `SegUIVarSemibold.ttf` as a separate static Semibold patch. Declaring the main file variable does not make every file in the family variable.

## Selection and variable output

After applying a mapping and filtering candidates by source group and style, selection prefers variable sources for variable targets. It then chooses the closest available weight, the lighter weight on equal distance, and finally the closest width class. Remaining ties are errors, not arbitrary choices based on directory order.

| Target | Source | Output |
| --- | --- | --- |
| Static face or patch | Static | Static replacement using the selected source face. |
| Static face or patch | Variable | Static instance at the requested coordinates. |
| Variable face or declared variable file | Static | Static fallback. |
| Variable face or declared variable file | Variable | Variable replacement retaining source axes, except axes explicitly pinned by a mapping. |

For static instances, `wght` uses the requested source weight, `ital` uses the requested style, and other axes use their defaults unless overridden. For variable output, only explicit `axes` entries pin axes; `source_weight` and `source_style` do not by themselves freeze variable axes. Pinning every axis produces static output.

Axes, ranges, and variation data come from the source, never from unrelated system outlines. A source without `opsz`, for example, cannot reproduce the system font's optical-size axis. Variable output uses the source's default weight metadata unless `wght` is explicitly pinned.

## Metadata and delivery

The system template supplies identity, target style, and selected vertical layout metrics. The source supplies outlines, character coverage, layout tables, and retained variation data. Metrics account for differences in units per em; clipping bounds are expanded for the source glyphs. Variation adjustments to transplanted vertical/caret metrics are removed so they cannot override those metrics.

Missing source characters are not filled from system fonts. Reduced coverage and static fallback are supported results. Invalid source selection, duplicate output identities, and filename conflicts stop the build.

`build --dry-run` prints the plan without writing fonts. A build generates and validates files in a temporary directory, then replaces same-name files in the output directory. Other existing files remain. The output directory must be separate from the system and source directories. Delivery replaces files individually; it is not an atomic swap of an existing directory.

JSON results go to stdout; progress goes to stderr. Reports are not written into the font output directory. File validation does not establish that fonts render correctly after installation in Windows.
