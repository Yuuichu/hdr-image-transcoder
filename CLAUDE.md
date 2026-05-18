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

- Gainmap AVIF: default `.avif` output, using `avifgainmaputil.exe`
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

# Gainmap AVIF quality and headroom options.
python hdr2avif.py input.jxr -q 90 -s 4 --max-headroom 4.0

# JPEG XL lossless output.
python hdr2avif.py input.jxr output.jxl --lossless

# List supported formats.
python hdr2avif.py --list-formats
python hdr2avif.py --list-output-formats

# Inspect gain map metadata.
& .\tools\libavif\avifdec.exe --info output.avif 2>&1

# Install dependencies.
pip install -r requirements.txt
```

## Architecture

```text
src/
  cli.py          -> CLI orchestration (convert_single, main)
  decoder.py      -> Multi-format decoder (decode_to_scrgb)
  encoder.py      -> Multi-format encoder (encode_output)
  gainmap.py      -> Gainmap AVIF encoder (avifgainmaputil)
  processor.py    -> HDR processing (prepare_base_sdr, prepare_alternate_hdr)
hdr2avif.py       -> thin CLI entry: from src.cli import main
jxr2avif.py       -> backward-compatible wrapper for hdr2avif.main()
```

## Notes

- `--max-headroom 0` means no maximum cap for `avifgainmaputil`.
- `--headroom` controls SDR base tonemap headroom in stops (default 2.0).
- Default `.avif` output is gainmap AVIF for backward compatibility.
- Use `--format avif` when the intended output is standard 10-bit PQ HDR AVIF.
- Standard AVIF HDR output uses PQ with BT.709 matrix (`1/16/1`) for OS viewer
  compatibility. Avoid RGB identity matrix for viewable AVIF/HEIF outputs.
- HEIF HDR output uses PQ with BT.709 matrix (`1/16/1`) and 4:2:0 chroma for
  OS viewer compatibility. Do not switch it back to RGB identity matrix; WIC
  and some viewers display that path as a red-tinted image.
- JPEG XL output writes a container with full CICP metadata
  (primaries=1 BT.709/sRGB, transfer=8 Linear, bitspersample=32).
  As of 2026-05, Safari is the only browser with JXL enabled by default;
  Chrome 145+ and Firefox 152+ require a flag. macOS 14+, Windows 11 24H2,
  and Linux (GNOME 45+) have native OS-level JXL decoding.
- The CLI avoids overwriting an input file when the default output extension is
  the same as the input extension.

## Common Pitfalls (lessons learned from past mistakes)

### Verify library API before claiming limitations

- `imagecodecs` is actively developed (`pip show imagecodecs` for version). The
  `jpegxl_encode` function now exposes `primaries`, `transfer`, `bitspersample`,
  `matrix` as keyword arguments. Before concluding a parameter is unsupported,
  run `help(imagecodecs.jpegxl_encode)` to check the current signature.
- In 2026.5.10, it supports `primaries` — a one-line fix (`primaries=1`) solved
  what was previously documented as an unresolvable limitation.

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
- `browser_select_option` requires the `values` parameter (an array of strings)
  — omitting it causes a silent error.
- Prefer WebFetch over WebSearch when the target URL is known (e.g. caniuse.com,
  wikipedia.org). WebSearch can fail silently while WebFetch gives direct results.

### Code review agent output needs verification

- Agent-flagged issues (typos, dead code, "unused imports") should be verified
  by reading the target file before including them in a report. In one instance,
  `from textwrap import indent` was flagged as a typo — but the file already had
  the correct spelling.

### PowerShell: avoid broad process termination

- `Stop-Process -Name "powershell"` kills ALL PowerShell processes including the
  current session. Target specific PIDs or use `Get-Process` with a filter on
  the command line.
