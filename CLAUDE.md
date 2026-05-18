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

Supported output formats:

- Gainmap AVIF: default `.avif` output, using `avifgainmaputil.exe`
- JPEG XL HDR: `.jxl`
- Ultra HDR JPEG: `.jpg` / `.jpeg`
- Standard HDR AVIF: `.avif` with `--format avif`

## Common Commands

```powershell
# Convert one file to gainmap AVIF.
python hdr2avif.py "C:\Users\77126\Videos\Forza Horizon 6\screenshot.jxr"

# Convert one file and infer output format from extension.
python hdr2avif.py input.jxr output.jxl
python hdr2avif.py input.jxr output.jpg

# Write standard 10-bit PQ HDR AVIF instead of gainmap AVIF.
python hdr2avif.py input.jxr output.avif --format avif

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
hdr2avif.py
  -> format_decoder.decode_to_scrgb()
     -> imagecodecs decoders and WIC fallback
  -> hdr_processor.prepare_base_sdr()
  -> hdr_processor.prepare_alternate_hdr()
  -> avif_encoder.encode_gainmap_avif()
     -> tools/libavif/avifgainmaputil.exe
  -> format_encoder.encode_output()
     -> JPEG XL, Ultra HDR JPEG, or standard HDR AVIF

jxr2avif.py
  -> backward-compatible wrapper for hdr2avif.main()
```

## Notes

- `--max-headroom 0` means no maximum cap for `avifgainmaputil`.
- Default `.avif` output is gainmap AVIF for backward compatibility.
- Use `--format avif` when the intended output is standard 10-bit PQ HDR AVIF.
- The CLI avoids overwriting an input file when the default output extension is
  the same as the input extension.
