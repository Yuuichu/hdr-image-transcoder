# HDR Image Transcoder Constitution

## Core Principles

### I. Fidelity First

Every format path must preserve HDR intent before convenience. Encoding changes
must define the source transfer function, primaries, peak/headroom policy, and
fallback behavior. Lossy delivery paths are allowed only when their validation
thresholds and expected metadata are explicit.

### II. Explicit Color Metadata

Pixel conversion and container metadata must agree. Do not tag images as
BT.2020, Display P3, PQ, HLG, sRGB, or Rec.709 unless the actual encoded pixels
match that interpretation. Any compatibility workaround must document which
reader family it targets.

### III. CLI And Inspectability

User-facing conversions must be reachable through `hdr2avif.py` or the package
CLI. New paths must expose enough flags, warnings, `--info-json` data, and
inspector output for a Windows user to understand which backend and metadata
were used.

### IV. Validation With Logs

Changes to decoders, encoders, gain maps, tone mapping, metadata, or CICP tags
must include focused unit tests and at least one representative matrix or
fidelity validation. Test commands and log paths must be reported with the
change.

### V. Clean Local Artifacts

Source, specs, scripts, tests, and committed tools stay in the repository tree.
Generated images, temporary matrices, downloaded research projects, local DLLs,
and screenshots stay under ignored paths such as `output/` or `local-scratch/`.

## Project Constraints

- Primary runtime: Python on Windows PowerShell.
- Source package: `src/hdr_transcoder`.
- CLI entry points: `hdr2avif.py` and `jxr2avif.py`.
- Tests: `tests/` with `pytest`; fidelity and tool-dependent tests use markers
  from `pytest.ini`.
- Bundled command-line tools live under `tools/`. Optional local binaries that
  cannot be redistributed must not be committed.
- Spec Kit feature artifacts live under `specs/<NNN-feature-name>/`.

## Development Workflow

1. For feature work, create a numbered feature branch and matching `specs/`
   directory before implementation.
2. Keep `spec.md`, `plan.md`, and `tasks.md` aligned with the implemented
   behavior.
3. Prefer small, reviewable changes that follow the existing encoder/decoder
   module boundaries.
4. Run targeted tests before broad matrix tests; keep matrix logs in `output/`.
5. Commit only source, specs, tests, scripts, docs, and redistributable tools.

## Governance

This constitution overrides ad hoc workflow preferences for repository work.
Amendments require updating this file, checking affected templates or specs,
and documenting any changed validation expectations in the same commit.

**Version**: 1.0.0 | **Ratified**: 2026-06-02 | **Last Amended**: 2026-06-02
