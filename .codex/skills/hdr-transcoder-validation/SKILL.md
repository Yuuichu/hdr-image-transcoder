---
name: hdr-transcoder-validation
description: Use when validating this JXR_Trans HDR Image Transcoder project, especially after changes to Gainmap AVIF, source-peak headroom, AVIF/JXL/HEIF color metadata, debug overlay, inspector output, CLI conversion, or Electron GUI parameter wiring.
---

# HDR Transcoder Validation

## Workflow

- Start by checking the worktree and changed files; do not revert unrelated changes.
- If pytest is unavailable, run `python -m pip install -r requirements.txt`.
- For quick validation, run:
  - `python -m compileall src hdr2avif.py jxr2avif.py tools\libavif\avifgainmaputil_hdr.py`
  - `node --check electron\main.js electron\preload.js electron\renderer\app.js scripts\prepare-package.js`
  - `python -m pytest -m "quick or gui"`
- For fidelity validation, run `python -m pytest -m fidelity`.

## Fidelity Expectations

- Gainmap AVIF source-peak mode must write Base headroom `0` and Alternate headroom no more than `0.02` stops below the source peak headroom.
- Gainmap decoded peak stop delta against `tests\fixtures\test_hdr_fix.jxl` must be `<= 0.05`.
- Gainmap alternate color must be Rec.2020/PQ/Rec.2020 NCL CICP `9/16/9`.
- Standard AVIF HDR must signal Rec.2020/PQ/Rec.2020 NCL CICP `9/16/9`.
- JXL master must remain linear and decoded peak delta must be `<= 0.02` scRGB.
- Debug overlay must create a sidecar `_debug.png` without modifying the converted output.

## Failure Triage

- If gainmap headroom fails, inspect with `tools\libavif\avifgainmaputil.exe printmetadata <file>`.
- If AVIF color metadata fails, inspect with `tools\libavif\avifdec.exe --info <file>`.
- If JXL metadata fails, inspect with `tools\libjxl\jxlinfo.exe <file>`.
- Keep generated outputs in pytest `tmp_path` or temporary directories.
