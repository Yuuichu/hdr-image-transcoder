# Tasks: PQ TIFF to Ultra HDR JPEG

**Input**: Design documents from `/specs/001-pq-tiff-ultrahdr/`

**Prerequisites**: `plan.md`, `spec.md`

**Tests**: Unit tests, fidelity tests, and matrix validations are required
because this feature changes HDR encoding, metadata inspection, and peak
verification.

## Phase 1: Setup

- [x] T001 [P] Define Ultra HDR backend/profile constants in `src/hdr_transcoder/config.py`
- [x] T002 [P] Add Display P3 conversion helper in `src/hdr_transcoder/color.py`
- [x] T003 Document feature scope in `specs/001-pq-tiff-ultrahdr/spec.md`

---

## Phase 2: Foundational

- [x] T004 Implement optional `libultrahdr` discovery and ctypes bindings in `src/hdr_transcoder/formats/ultrahdr_lib.py`
- [x] T005 Implement BT.2020 PQ TIFF loading constraints in `src/hdr_transcoder/formats/ultrahdr_lib.py`
- [x] T006 Implement Display P3 PQ preparation and Ultra HDR raw image packing in `src/hdr_transcoder/formats/ultrahdr_lib.py`
- [x] T007 Report optional `uhdr.dll` discovery in `src/hdr_transcoder/tools.py`

---

## Phase 3: User Story 1 - Convert known PQ TIFF to Ultra HDR JPEG

**Goal**: Convert known BT.2020 PQ TIFF sources through `libultrahdr`.

**Independent Test**: Run the dedicated CLI command with `--bt2020-pq-tiff --format ultrahdr --uhdr-backend libultrahdr --verify-fidelity --info-json`.

- [x] T008 [US1] Add dedicated PQ TIFF Ultra HDR encode function in `src/hdr_transcoder/formats/ultrahdr.py`
- [x] T009 [US1] Route `--bt2020-pq-tiff --format ultrahdr` through the dedicated path in `src/hdr_transcoder/cli.py`
- [x] T010 [US1] Pass Ultra HDR backend parameters through `src/hdr_transcoder/formats/__init__.py`

---

## Phase 4: User Story 2 - Select or diagnose backend

**Goal**: Make backend selection and fallback behavior visible and reproducible.

**Independent Test**: Run with missing `uhdr.dll` under both `auto` and
`libultrahdr` modes.

- [x] T011 [US2] Add CLI options for `--uhdr-backend`, `--uhdr-profile`, `--gainmap-scale`, `--gainmap-gamma`, and `--target-peak-nits`
- [x] T012 [US2] Emit warnings for `auto` fallback and hard errors for explicit missing `libultrahdr`
- [x] T013 [US2] Preserve the legacy `imagecodecs` Ultra HDR path as fallback

---

## Phase 5: User Story 3 - Inspect and validate outputs

**Goal**: Detect Ultra HDR metadata and validate reconstructed peak behavior.

**Independent Test**: Run `--verify-fidelity --info-json` and matrix validation
against Ultra HDR output.

- [x] T014 [US3] Add lightweight Ultra HDR JPEG marker/XMP scan in `src/hdr_transcoder/inspector.py`
- [x] T015 [US3] Verify Ultra HDR metadata in `src/hdr_transcoder/validation.py`
- [x] T016 [US3] Normalize legacy `hdrgm:` decoder white point in `src/hdr_transcoder/formats/decoder.py`
- [x] T017 [US3] Update Ultra HDR expectations in `scripts/format_matrix_validation.py`

---

## Phase 6: Tests And Documentation

- [x] T018 [P] Add unit tests in `tests/unit/test_ultrahdr_lib.py`
- [x] T019 [P] Update README CLI/runtime documentation for PQ TIFF Ultra HDR usage
- [x] T020 [P] Update agent documentation for the new module layout
- [x] T021 Run compile, unit, fidelity, and matrix validation commands

---

## Validation Commands

```powershell
python -m compileall src hdr2avif.py jxr2avif.py scripts\format_matrix_validation.py
python -m pytest tests\unit\test_ultrahdr_lib.py -q
python -m pytest -q
python -m pytest -m fidelity -q
python scripts\format_matrix_validation.py --run-id codex-uhdr-lib-final-q100 --width 64 --height 40 --quality 100 --speed 8 --timeout 900
python scripts\format_matrix_validation.py --input output\format-matrix\codex-uhdr-lib-smoke-q100\sources\reference_bt2020_pq_untagged.tif --bt2020-pq-tiff --run-id codex-uhdr-lib-final-pqtiff-q100 --quality 100 --speed 8 --timeout 900
```
