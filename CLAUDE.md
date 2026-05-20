# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a multi-format HDR image conversion tool. It decodes HDR-oriented
inputs to float32 linear scRGB-like data, then writes one of several HDR output
formats.

Supported input formats:

- JPEG XR: `.jxr`, `.wdp`, `.hdp`
- JPEG XL: `.jxl`
- OpenEXR: `.exr`
- AVIF: `.avif`
- HEIF/HEIC: `.heic`, `.heif`
- Ultra HDR JPEG: `.jpg`, `.jpeg`
- Radiance HDR: `.hdr`
- PNG: `.png`
- TIFF: `.tif`, `.tiff`

Supported output formats:

- Gainmap AVIF: default `.avif` output, using `avifgainmaputil_hdr.exe`
- JPEG XL HDR: `.jxl`
- Ultra HDR JPEG: `.jpg` / `.jpeg`
- Standard HDR AVIF: `.avif` with `--format avif`
- HEIF HDR: `.heic` / `.heif`

## Common Commands

```powershell
# Convert one file to gainmap AVIF.
python hdr2avif.py "C:\Users\77126\Videos\Forza Horizon 6\screenshot.jxr"

# Convert one file and infer output format from extension.
python hdr2avif.py input.jxr output.jxl
python hdr2avif.py input.jxr output.jpg
python hdr2avif.py input.jxr output.heic

# Write standard 10-bit PQ HDR AVIF instead of gainmap AVIF.
python hdr2avif.py input.jxr output.avif --format avif

# Write standard 10-bit PQ HDR HEIF.
python hdr2avif.py input.jxr output.heic --format heif

# Batch convert a directory.
python hdr2avif.py "C:\Users\77126\Videos\Forza Horizon 6" --output-dir .\output

# Batch convert to JPEG XL.
python hdr2avif.py "dir\" --output-dir .\jxl_out --format jxl

# Gainmap AVIF quality and headroom metadata mode.
python hdr2avif.py input.jxr -q 90 -s 4 --gainmap-headroom-mode source-peak

# Batch output naming.
python hdr2avif.py input1.jxr input2.jxr --output-dir .\output --name-pattern "HDR_{n}"

# JPEG XL lossless output.
python hdr2avif.py input.jxr output.jxl --lossless

# List supported formats.
python hdr2avif.py --list-formats
python hdr2avif.py --list-output-formats

# Inspect gain map metadata.
& .\tools\libavif\avifgainmaputil.exe printmetadata output.avif

# Install dependencies.
pip install -r requirements.txt
```

## Architecture

The core logic lives in the `src/hdr_transcoder` package. The old flat `src/`
modules (`cli.py`, `decoder.py`, `encoder.py`, `gainmap.py`, `processor.py`) are
now thin compatibility wrappers that re-export from `hdr_transcoder.*`.

```text
src/hdr_transcoder/
  config.py         -> Central constants, CICP codes, paths, timeouts
  color.py          -> Color-space matrices (sRGB↔BT.2020, gamma helpers)
  processor.py      -> SDR tone-mapping (prepare_base_sdr), PQ encoding (prepare_alternate_hdr)
  validation.py     -> Fidelity verification (peak/headroom checks, metadata validation)
  inspector.py      -> Image inspection, debug overlay generation, info JSON
  tools.py          -> Bundled tool paths, runtime environment checks
  tools_check.py    -> CLI entry for `python -m hdr_transcoder.tools_check`
  cli.py            -> CLI orchestration (convert_single, main, arg parsing)
  formats/
    __init__.py     -> Encoder dispatch (encode_output), format registry
    decoder.py      -> Multi-format decoder (decode_to_scrgb, probe_format)
    gainmap.py      -> Gainmap AVIF (avifgainmaputil_hdr.exe)
    jxl.py          -> JPEG XL (cjxl.exe), JXL_MODE_* constants
    avif.py         -> Standard AVIF HDR (imagecodecs)
    ultrahdr.py     -> Ultra HDR JPEG (imagecodecs)
    heif.py         -> HEIF HDR (pillow-heif)
hdr2avif.py         -> CLI entry: from hdr_transcoder.cli import main
jxr2avif.py         -> backward-compatible wrapper for hdr2avif.main()
```

### Data flow

```
Input → decoder.decode_to_scrgb() → float32 scRGB (H×W×3)
  ├─ Tier-1 formats (jxl/avif/heif/ultrahdr) → encoder.encode_output()
  └─ Gainmap AVIF → processor.prepare_base_sdr() + prepare_alternate_hdr()
                    → gainmap.encode_gainmap_avif()
```

### Fidelity model

| Mode | Default format | Description |
|------|---------------|-------------|
| `master` | lossless linear JXL | Archive/reprocessing (requires `--jxl-mode linear-srgb`) |
| `display` | Rec.2020 PQ JXL | Viewable HDR delivery |
| `compat` | Gainmap AVIF | Web-compatible with SDR fallback |

`--fidelity master` is the default. Non-JXL outputs under master require
`--allow-non-master`. Tier-1 formats (jxl, avif, heif, ultrahdr) are encoded
directly from scRGB; gainmap AVIF goes through the two-pass SDR+HDR pipeline.

### Bundled tools

Encode/decode relies on prebuilt executables in `tools/`:

- `tools/libjxl/` — cjxl.exe, djxl.exe, jxlinfo.exe (JPEG XL)
- `tools/libavif/` — avifgainmaputil.exe, avifgainmaputil_hdr.exe, avifdec.exe,
  avifenc.exe (AVIF)

These are required at runtime. `python -m hdr_transcoder.tools_check` reports
missing tools and dependency errors. `hdr_transcoder.tools` maps tool names to
absolute paths.

## Testing

```powershell
# Run quick tests (default — skips fidelity tests).
pytest

# Run all tests including slower end-to-end fidelity tests.
pytest -m ""

# Run only fidelity tests.
pytest -m fidelity

# Run a specific test file.
pytest tests/unit/test_tools_check.py

# Run tool invocation checks.
python -m hdr_transcoder.tools_check --invoke
```

Test markers (defined in pytest.ini):

| Marker | Description |
|--------|-------------|
| `quick` (default) | Fast tests, no full encode/decode round-trips |
| `fidelity` | Slower end-to-end tests that encode and decode output images |
| `tools` | Tests that require bundled command-line tools |
| `gui` | Electron renderer/main-process wiring checks |

Test fixtures live in `tests/fixtures/` (test JXL files, HEIF reference).

## Notes

- `--gainmap-headroom-mode source-peak` is the default for Gainmap AVIF and
  writes `Alternate headroom` from the decoded source peak.
- `--max-headroom` is a legacy libavif cap for debugging, not the default
  fidelity path.
- `--headroom` controls SDR base tonemap headroom in stops (default 2.0).
- Defaults are quality 100 and speed 0 to prioritize fidelity and compression.
- Batch naming applies to multi-file and directory mode; explicit single output
  paths are kept unchanged.
- Default `.avif` output is gainmap AVIF for backward compatibility.
- Use `--format avif` when the intended output is standard 10-bit PQ HDR AVIF.
- Standard AVIF HDR output converts scRGB to Rec.2020, then writes PQ with
  Rec.2020 non-constant luminance matrix (`9/16/9`). Avoid RGB identity matrix
  for viewable AVIF/HEIF outputs.
- HEIF HDR output converts scRGB to Rec.2020, then writes PQ with Rec.2020
  non-constant luminance matrix (`9/16/9`) and 4:2:0 chroma. Do not switch it
  back to RGB identity matrix; WIC and some viewers display that path as a
  red-tinted image.
- JPEG XL output uses bundled `tools/libjxl/cjxl.exe`. Default JXL mode converts
  scRGB to Rec.2020 PQ and writes `RGB_D65_202_Rel_PeQ` metadata with a
  10000-nit intensity target. `--jxl-mode linear-srgb` writes linear scRGB-like
  float data for archive/reprocessing only.
- Do not add an `imagecodecs` fallback for JXL encoding. If `cjxl.exe` is
  missing, fail directly with a clear error.
- As of 2026-05, Safari is the only browser with JXL enabled by default;
  Chrome 145+ and Firefox 152+ require a flag. macOS 14+, Windows 11 24H2,
  and Linux (GNOME 45+) have native OS-level JXL decoding.
- The CLI avoids overwriting an input file when the default output extension is
  the same as the input extension.

## Common Pitfalls (lessons learned from past mistakes)

### Keep JXL on the cjxl path

- JXL encoding is intentionally routed through `cjxl.exe` so color metadata can
  be explicit and inspectable with `jxlinfo.exe`.
- `imagecodecs.jpegxl_encode` may preserve pixels, but do not use it as a silent
  fallback because it can produce misleading HDR metadata.

### Validation consistency across layers

- The same constraint must be enforced at HTML (`min`), renderer JS
  (`validateOptions`), main process (`validateOptions`), and Python CLI
  (`_validate_args`). Inconsistency causes confusing late-stage failures where
  the UI says OK but the spawned process crashes.
- After changing a validation rule, grep for the old value across all layers.

### Playwright testing of Electron renderer

- `page.evaluate()` state is lost on `location.reload()` or page navigation.
  Mock injection must be re-applied after every navigation.
- A `<form>` with a `<button type="submit">` will trigger a GET navigation
  (appending `?` to URL) if `event.preventDefault()` isn't called. When the
  mock API isn't properly wired, the form falls through to native submission.
- `browser_select_option` requires the `values` parameter (an array of strings);
  omitting it causes a silent error.
- Prefer WebFetch over WebSearch when the target URL is known (e.g. caniuse.com,
  wikipedia.org). WebSearch can fail silently while WebFetch gives direct results.

### Code review agent output needs verification

- Agent-flagged issues (typos, dead code, "unused imports") should be verified
  by reading the target file before including them in a report. In one instance,
  `from textwrap import indent` was flagged as a typo, but the file already had
  the correct spelling.

### PowerShell: avoid broad process termination

- `Stop-Process -Name "powershell"` kills ALL PowerShell processes including the
  current session. Target specific PIDs or use `Get-Process` with a filter on
  the command line.
