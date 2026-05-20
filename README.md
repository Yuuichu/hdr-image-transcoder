# HDR Image Transcoder

Convert HDR images between modern HDR still-image formats.

The default workflow is optimized for strict HDR preservation: decode the source
to linear float32 scRGB-like data and write lossless linear JPEG XL as the master
output. The tool can also write display/delivery formats such as Rec.2020 PQ
JPEG XL, gain map AVIF, Ultra HDR JPEG, standard 10-bit PQ AVIF, and HEIF HDR.

## Features

- Convert HDR images to lossless linear JPEG XL (`.jxl`) by default
- Export Rec.2020 PQ JPEG XL HDR (`.jxl`)
- Export Ultra HDR JPEG (`.jpg` / `.jpeg`)
- Export standard 10-bit PQ HDR AVIF (`.avif` with `--format avif`)
- Export HEIF HDR (`.heic` / `.heif`)
- Batch convert a whole directory
- Decode through `imagecodecs`, with bundled Windows `libavif` tools for gain map AVIF
- Inspect images with `python -m hdr_transcoder.inspector`
- Optional debug overlay and `output.info.json` conversion sidecars
- Backward-compatible `jxr2avif.py` entry point

## Supported Formats

### Input

| Format | Extensions |
| --- | --- |
| JPEG XR | `.jxr`, `.wdp`, `.hdp` |
| JPEG XL | `.jxl` |
| OpenEXR | `.exr` |
| AVIF | `.avif` |
| HEIF/HEIC | `.heic`, `.heif` |
| Radiance HDR | `.hdr` |
| Ultra HDR JPEG | `.jpg`, `.jpeg` |
| PNG | `.png` |
| TIFF | `.tif`, `.tiff` |

### Output

| Format | Extension | Command |
| --- | --- | --- |
| JPEG XL Master | `.jxl` | default, `--fidelity master` |
| JPEG XL Display HDR | `.jxl` | `--format jxl --fidelity display --jxl-mode rec2020-pq` |
| Gain map AVIF | `.avif` | `--format gainmap --fidelity compat` |
| Ultra HDR JPEG | `.jpg`, `.jpeg` | output path ending in `.jpg` / `.jpeg` with `--fidelity compat`, or `--format ultrahdr --fidelity compat` |
| Standard PQ HDR AVIF | `.avif` | `--format avif --fidelity display` |
| HEIF HDR | `.heic`, `.heif` | output path ending in `.heic` / `.heif` with `--fidelity display`, or `--format heif --fidelity display` |

## Installation

Python 3.12 is used during development. Install the Python dependencies:

```powershell
pip install -r requirements.txt
```

For the optional Electron GUI, install the Node dependencies:

```powershell
npm install
```

If the Electron binary download is slow or stalls, use a mirror for the install
step:

```powershell
$env:ELECTRON_MIRROR = "https://npmmirror.com/mirrors/electron/"
npm install
```

The repository includes Windows `libavif` binaries under `tools/libavif/` and
Windows `libjxl` command-line tools under `tools/libjxl/`.
`avifgainmaputil_hdr.exe` is required for gain map AVIF output because it can
write explicit base/alternate headroom metadata. The official
`avifgainmaputil.exe` remains bundled for `printmetadata` and `tonemap`
validation paths. `cjxl.exe`, `jxlinfo.exe`, and `avifdec.exe` are required for
encoding and verification. Run a local self-check with:

```powershell
python -m hdr_transcoder.tools_check --pretty
```

## Usage

### Local GUI

Start the Electron desktop GUI:

```powershell
npm start
```

The GUI runs the same local Python conversion pipeline as the CLI. It supports
multi-file conversion by default, directory conversion, output format selection,
batch output naming, quality, speed, gain map headroom mode, JXL mode, JXL
lossless mode, live logs, image metadata inspection, runtime self-check, and
cancellation.

Development mode uses the system Python on `PATH`. Portable packaged mode uses
the bundled runtime at `resources/python/python.exe`; `npm run prepack` prepares
that runtime, installs Python dependencies into it, copies project source and
bundled tools, then runs `python -m hdr_transcoder.tools_check`.

### CLI

Convert a single file to strict master JPEG XL:

```powershell
python hdr2avif.py input.jxr
```

Choose the output format by extension:

```powershell
python hdr2avif.py input.jxr output.jxl
python hdr2avif.py input.jxr output.jpg --fidelity compat
python hdr2avif.py input.jxr output.heic --fidelity display
```

Strict master mode only accepts lossless linear JPEG XL. Use `--fidelity display`
or `--fidelity compat` for delivery formats, or `--allow-non-master` when you
intentionally want a non-master format while keeping the master policy enabled.

Write standard 10-bit PQ HDR AVIF instead of gain map AVIF:

```powershell
python hdr2avif.py input.jxr output.avif --format avif --fidelity display
```

Write 10-bit PQ HDR HEIF:

```powershell
python hdr2avif.py input.jxr output.heic --fidelity display
python hdr2avif.py input.jxr output.heif --format heif --fidelity display
```

Batch convert a directory:

```powershell
python hdr2avif.py "C:\Path\To\HDR Screenshots" --output-dir .\output
```

Batch convert to JPEG XL:

```powershell
python hdr2avif.py "C:\Path\To\HDR Screenshots" --output-dir .\jxl_output --format jxl
```

Tune quality, encoder speed, and gain map headroom mode:

```powershell
python hdr2avif.py input.jxr output.avif --format gainmap --fidelity compat -q 90 -s 4 --gainmap-headroom-mode source-peak
```

Defaults are quality `100` and speed `0`, which prioritize fidelity and
compression efficiency over conversion time. `speed` is the encoder effort
setting: `0` is the slowest/best-compression setting, and `10` is the fastest.
It does not replace the `quality` setting; gain map AVIF still uses quality
`100` by default for both the base color image and the gain map. The default
gain map headroom mode is `source-peak`, which writes `Alternate headroom` from
the source HDR peak (`log2(max(source_rgb_peak, 1.0))`). Use
`--gainmap-headroom-mode auto` only when you intentionally want libavif's
computed metadata. `--max-headroom` remains available as a legacy libavif cap
for debugging but is not the default fidelity path.

Batch rename outputs:

```powershell
python hdr2avif.py input1.jxr input2.jxr --output-dir .\output --name-prefix HDR_ --name-suffix _pq
python hdr2avif.py "C:\Path\To\HDR Screenshots" --output-dir .\output --name-find Screenshot --name-replace HDR
python hdr2avif.py input1.jxr input2.jxr --output-dir .\output --name-pattern "Forza_HDR_{n}" --name-start 1 --name-padding 3
```

Batch naming supports `{name}` for the original filename stem and `{n}` for the
number. Single-file commands with an explicit output path keep that exact path.

Create lossless JPEG XL:

```powershell
python hdr2avif.py input.jxr output.jxl --lossless
```

In master mode, lossless linear scRGB JPEG XL is selected automatically. In the
Rec.2020 PQ JXL mode, `--lossless` is only lossless after the 16-bit PQ
conversion step, so it is a display format rather than a strict master format.

Create archive-oriented linear scRGB JPEG XL:

```powershell
python hdr2avif.py input.jxr output.jxl --jxl-mode linear-srgb
```

Verify the written file after conversion:

```powershell
python hdr2avif.py input.jxr output.jxl --verify-fidelity
```

Write a conversion metadata sidecar:

```powershell
python hdr2avif.py input.jxr output.jxl --verify-fidelity --info-json
```

The sidecar is written next to the output, for example `output.info.json`, and
contains the output format, CICP metadata, gain map headroom, decoded peak,
verify result, and the full inspector payload.

List supported formats:

```powershell
python hdr2avif.py --list-formats
python hdr2avif.py --list-output-formats
```

Inspect existing output metadata:

```powershell
python -m hdr_transcoder.inspector output.avif --pretty
```

Backward-compatible JXR entry point:

```powershell
python jxr2avif.py input.jxr
```

## Gain Map AVIF Notes

Gain map AVIF is a multi-layer compatibility/delivery output, not the strict
master archive format. The encoded file contains:

- SDR base image for normal SDR viewers
- HDR alternate image converted from scRGB to Rec.2020 and encoded with PQ transfer
- AVIF gain map metadata generated by libavif, with headroom metadata overridden
  by `avifgainmaputil_hdr.exe` when `--gainmap-headroom-mode source-peak` is used

Use this command to inspect the resulting metadata:

```powershell
& .\tools\libavif\avifgainmaputil.exe printmetadata output.avif
```

The official libavif CLI can compute headroom but cannot force `Alternate
headroom` to match the source HDR peak. This project therefore uses
`avifgainmaputil_hdr.exe` for encoding. It keeps libavif's AVIF container, AV1
encoding, and gain map generation, then writes the requested headroom metadata
and verifies it with the official `printmetadata` command. Use
`--verify-fidelity` to fail the command if the alternate headroom falls below
the source image peak headroom by more than `0.02` stops, if decoded gainmap
peak differs by more than `0.05` stops, or if alternate image CICP is not
Rec.2020/PQ/Rec.2020 NCL (`9/16/9`).

## Standard HDR AVIF Notes

Use `--format avif` when you want a normal 10-bit PQ AVIF instead of a gain map
AVIF:

```powershell
python hdr2avif.py input.jxr output.avif --format avif
```

This path converts the internal linear scRGB pixels to Rec.2020 before PQ
encoding, then writes Rec.2020 primaries, PQ transfer, and Rec.2020 non-constant
luminance matrix CICP metadata (`9/16/9`). This avoids constraining HDR output
to the BT.709/sRGB gamut while keeping the earlier red-preview fix by avoiding
identity matrix signaling.

## JPEG XL Notes

JPEG XL output uses the bundled official `cjxl.exe` tool, not the
`imagecodecs.jpegxl_encode` fallback path. The default mode converts internal
linear scRGB pixels to Rec.2020, encodes PQ, forces a JPEG XL container, and
writes Rec.2100 PQ color metadata (`RGB_D65_202_Rel_PeQ`) with a 10000-nit
intensity target.

Use `--jxl-mode linear-srgb` only for archive or reprocessing workflows. That
mode writes linear sRGB/scRGB float data (`RGB_D65_SRG_Rel_Lin`) and stays
closer to the original Windows HDR screenshot math, but many viewers may not
trigger HDR display from it.

## HEIF HDR Notes

HEIF output uses `pillow-heif` and writes 10-bit HEVC with nclx metadata:
Rec.2020 primaries, PQ transfer, Rec.2020 non-constant luminance matrix, full
range (`9/16/9`). The encoder requests 4:4:4 chroma for better color fidelity;
viewer support may still vary by platform.

## Project Structure

```text
hdr2avif.py          Thin CLI entry point
jxr2avif.py          Backward-compatible wrapper
electron/            Local Electron GUI
hdr_transcoder/       Root import shim for python -m module execution
src/hdr_transcoder/   Main Python package
  cli.py              CLI orchestration
  config.py           CICP, timeout, fidelity, and format constants
  tools.py            Bundled tool paths and runtime self-check
  validation.py       Fidelity verification rules
  inspector.py        JSON metadata inspection and debug overlay
  formats/decoder.py  Input format detection and decoding
  formats/jxl.py      JPEG XL encoder
  formats/avif.py     Standard AVIF encoder
  formats/gainmap.py  Gain map AVIF encoder using avifgainmaputil_hdr
  formats/heif.py     HEIF encoder
  formats/ultrahdr.py Ultra HDR JPEG encoder
tests/unit/           Fast unit and import compatibility tests
tests/integration/    GUI wiring tests
tests/fidelity/       Slower encode/decode fidelity tests
tests/fixtures/       Committed HDR fixture files
tools/libavif/       Bundled Windows libavif tools and headroom helper
tools/libjxl/        Bundled Windows libjxl tools
```

## Development

Run syntax and test checks:

```powershell
python -m compileall src hdr_transcoder hdr2avif.py jxr2avif.py tools\libavif\avifgainmaputil_hdr.py
node --check electron\main.js electron\preload.js electron\renderer\app.js scripts\prepare-package.js
python -m pytest
python -m pytest -m fidelity
npm run prepack
```

The tool is currently developed and tested on Windows. Viewer support for HDR,
gain maps, and metadata varies by application, so use `avifdec --info` or another
metadata-aware tool when validating output files.
