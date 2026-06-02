# Implementation Plan: PQ TIFF to Ultra HDR JPEG

**Branch**: `001-pq-tiff-ultrahdr` | **Date**: 2026-06-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-pq-tiff-ultrahdr/spec.md`

## Summary

Add a narrow, explicit path for known true BT.2020 PQ TIFF inputs to produce
Ultra HDR JPEG output through optional `libultrahdr`, while keeping the existing
generic `imagecodecs` Ultra HDR path as a fallback. The feature adds backend
selection, Display P3 Ultra HDR preparation, inspector metadata checks, runtime
tool reporting, and validation coverage.

## Technical Context

**Language/Version**: Python 3.12+ development target, tested under Windows
PowerShell.

**Primary Dependencies**: `numpy`, `tifffile`, `imagecodecs`, optional
`libultrahdr` loaded through `ctypes`.

**Storage**: Local input and output image files only.

**Testing**: `pytest`, fidelity-marked tests, and
`scripts/format_matrix_validation.py`.

**Target Platform**: Windows desktop CLI, with output compatibility aimed at
Apple and Android Ultra HDR readers.

**Project Type**: Python CLI/library with bundled native tools.

**Performance Goals**: Preserve high fidelity at quality-oriented settings;
avoid unnecessary output size growth from duplicate container structures.

**Constraints**: `uhdr.dll` is optional and must not be required for unrelated
formats. Generated images and logs must stay under ignored paths.

**Scale/Scope**: Single-image and batch CLI conversions.

## Constitution Check

- Fidelity First: Pass. The dedicated path keeps PQ TIFF semantics explicit and
  validates peak reconstruction.
- Explicit Color Metadata: Pass. The path names BT.2020 PQ input and Display P3
  Ultra HDR output assumptions.
- CLI And Inspectability: Pass. CLI options, warnings, runtime checks, and
  inspector metadata checks were added.
- Validation With Logs: Pass. Unit, fidelity, and matrix validation cover the
  new behavior.
- Clean Local Artifacts: Pass. `uhdr.dll`, generated files, and research
  checkouts remain in ignored local paths.

## Project Structure

### Documentation

```text
specs/001-pq-tiff-ultrahdr/
|-- spec.md
|-- plan.md
|-- tasks.md
`-- quickstart.md
```

### Source Code

```text
src/hdr_transcoder/
|-- cli.py
|-- color.py
|-- config.py
|-- inspector.py
|-- tools.py
|-- validation.py
`-- formats/
    |-- __init__.py
    |-- decoder.py
    |-- ultrahdr.py
    `-- ultrahdr_lib.py

tests/unit/
`-- test_ultrahdr_lib.py

scripts/
`-- format_matrix_validation.py
```

**Structure Decision**: Keep the feature inside the existing format encoder,
decoder, validation, and CLI modules. Add only one backend-specific helper
module because `libultrahdr` requires `ctypes` structs and DLL discovery that do
not belong in the generic encoder dispatch.

## Implementation Notes

- `--uhdr-backend auto` prefers `libultrahdr` only when a DLL is available.
- `--uhdr-backend libultrahdr` is strict and fails if no DLL is available.
- `--bt2020-pq-tiff` is a user assertion, not automatic TIFF metadata
  detection.
- The Display P3 conversion uses a direct NumPy matrix/PQ path for this feature;
  a future feature can replace it with OCIO/ACES RGC if needed.

## Validation Plan

1. Compile all changed Python entry points.
2. Run focused Ultra HDR unit tests.
3. Run the default unit suite.
4. Run fidelity-marked tests.
5. Run format matrix validation on a synthetic standard HDR source.
6. Run format matrix validation on a synthetic PQ TIFF source.
