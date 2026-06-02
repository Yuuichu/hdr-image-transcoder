# Feature Specification: PQ TIFF to Ultra HDR JPEG

**Feature Branch**: `001-pq-tiff-ultrahdr`

**Created**: 2026-06-02

**Status**: Implemented

**Input**: User description: "Study a focused PQ TIFF to Ultra HDR JPEG pipeline and optimize this project for known true PQ TIFF inputs, Apple compatibility, clear validation, and clean logs."

## User Scenarios & Testing

### User Story 1 - Convert known PQ TIFF to Apple-compatible Ultra HDR JPEG (Priority: P1)

A Windows user has a TIFF exported as BT.2020 PQ HDR and wants a compact Ultra
HDR JPEG that Apple and Android readers can recognize through gain map metadata.

**Why this priority**: This is the narrow compatibility path requested for real
PQ TIFF exports.

**Independent Test**: Convert a known BT.2020 PQ TIFF with `--bt2020-pq-tiff --format ultrahdr --uhdr-backend libultrahdr` and verify Ultra HDR metadata plus peak reconstruction.

**Acceptance Scenarios**:

1. **Given** a known uint16 RGB BT.2020 PQ TIFF and available `uhdr.dll`, **When** the user runs the dedicated Ultra HDR command, **Then** the output JPEG contains Ultra HDR gain map markers and passes project peak verification.
2. **Given** a TIFF source that is not intended to be PQ, **When** the user omits `--bt2020-pq-tiff`, **Then** the generic HDR pipeline remains available without silently assuming PQ TIFF semantics.

---

### User Story 2 - Select or diagnose the Ultra HDR backend (Priority: P2)

A user needs to understand whether the encoder used the real `libultrahdr`
pipeline or the legacy `imagecodecs` fallback.

**Why this priority**: Backend ambiguity caused previous compatibility debugging
to be slow and hard to reproduce.

**Independent Test**: Run with `--uhdr-backend libultrahdr` while `uhdr.dll` is
missing and confirm a clear error; run with `--uhdr-backend auto` and confirm a
warning before fallback.

**Acceptance Scenarios**:

1. **Given** `--uhdr-backend libultrahdr` and no loadable DLL, **When** conversion starts, **Then** the command fails with instructions for `HDR_TRANSCODER_UHDR_DLL` or `tools/libultrahdr/uhdr.dll`.
2. **Given** `--uhdr-backend auto` and no DLL, **When** conversion starts, **Then** the command warns that it is falling back to `imagecodecs`.

---

### User Story 3 - Inspect and validate Ultra HDR outputs (Priority: P3)

A maintainer needs logs that show whether an output has gain map metadata and
whether the reconstructed peak matches the source.

**Why this priority**: Without metadata and peak checks, platform display bugs
cannot be distinguished from container-generation bugs.

**Independent Test**: Run `--verify-fidelity --info-json` and inspect the JSON
or matrix summary for Ultra HDR gain map detection and display peak.

**Acceptance Scenarios**:

1. **Given** a generated Ultra HDR JPEG, **When** the inspector runs, **Then** it reports lightweight JPEG gain map clues such as MPF, XMP, ISO, or second-image markers.
2. **Given** a matrix validation run, **When** Ultra HDR output is tested, **Then** metadata and peak checks are included in the result.

### Edge Cases

- `uhdr.dll` is absent or incompatible.
- TIFF input is not uint16 RGB.
- The user requests the dedicated PQ TIFF path with an unsupported output format.
- Peak target is outside the accepted Ultra HDR range.
- The legacy backend is used and emits older `hdrgm:` metadata.

## Requirements

### Functional Requirements

- **FR-001**: The CLI MUST provide a `--bt2020-pq-tiff` flag that treats TIFF RGB samples as known BT.2020 PQ HDR input.
- **FR-002**: The CLI MUST provide Ultra HDR backend selection with `auto`, `imagecodecs`, and `libultrahdr` modes.
- **FR-003**: The dedicated PQ TIFF Ultra HDR path MUST use `libultrahdr` when requested and MUST fail clearly if the DLL is unavailable.
- **FR-004**: The dedicated path MUST convert BT.2020 PQ TIFF data to a Display P3 Ultra HDR profile for Apple-oriented compatibility.
- **FR-005**: Ultra HDR validation MUST detect gain map metadata and compare reconstructed peak behavior.
- **FR-006**: Tool checks MUST report optional `uhdr.dll` discovery paths without treating absence as a hard failure for non-Ultra-HDR workflows.
- **FR-007**: Unit tests MUST cover PQ TIFF loading constraints, packing behavior, backend rejection, and decoder white-point normalization.

### Key Entities

- **PQ TIFF Source**: A known uint16 RGB TIFF whose samples are interpreted as BT.2020 PQ.
- **Ultra HDR Backend**: The selected encoder implementation: `libultrahdr`, `imagecodecs`, or `auto`.
- **Ultra HDR Output**: A JPEG with SDR base data and HDR gain map metadata.

## Success Criteria

### Measurable Outcomes

- **SC-001**: A known PQ TIFF source can be converted through the `libultrahdr` backend and pass project metadata and peak verification.
- **SC-002**: The default test suite and fidelity suite pass after the change.
- **SC-003**: Format matrix validation passes for both a synthetic standard HDR source and a synthetic PQ TIFF source at fidelity-oriented quality settings.
- **SC-004**: The CLI and runtime check logs identify the selected Ultra HDR backend and whether `uhdr.dll` was discovered.

## Assumptions

- The dedicated TIFF path is intentionally narrow and only supports known true
  BT.2020 PQ TIFF exports.
- Full OCIO or ACES Reference Gamut Compression is outside this first feature.
- `libultrahdr` binaries are optional local dependencies and are not committed
  unless their redistribution status is explicitly resolved.
