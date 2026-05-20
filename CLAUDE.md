# CLAUDE.md

This file gives local guidance for working in this repository.

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

```text
src/
  cli.py          -> CLI orchestration (convert_single, main)
  decoder.py      -> Multi-format decoder (decode_to_scrgb)
  encoder.py      -> Multi-format encoder (encode_output)
  gainmap.py      -> Gainmap AVIF encoder (avifgainmaputil_hdr)
  processor.py    -> HDR processing (prepare_base_sdr, prepare_alternate_hdr)
hdr2avif.py       -> thin CLI entry: from src.cli import main
jxr2avif.py       -> backward-compatible wrapper for hdr2avif.main()
```

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
