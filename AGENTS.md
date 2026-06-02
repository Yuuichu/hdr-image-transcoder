# AGENTS.md

Project guidance for Codex and Spec Kit agents working in this repository.

## Language And Style

- Use Chinese for normal user-facing explanations unless the user asks otherwise.
- Keep development updates concise and practical.
- For debugging, root-cause analysis, or tradeoff discussions, state assumptions and evidence explicitly.
- In review mode, lead with concrete findings, regressions, risks, and missing validation.

## Project Overview

This repository is a Windows-first HDR still-image transcoder. The core package
is `src/hdr_transcoder`, with compatibility entry points at `hdr2avif.py` and
`jxr2avif.py`.

Generated images, logs, local binaries, and research checkouts belong under
`output/` or `local-scratch/`; both are intentionally ignored by git.

## Development Rules

- Prefer existing helpers in `src/hdr_transcoder` over adding parallel paths.
- Keep color-space assumptions explicit in code, CLI help, metadata, and tests.
- Use `--bt2020-pq-tiff` only for known true BT.2020 PQ TIFF exports.
- Do not commit generated outputs, temporary matrices, local DLLs, screenshots, or downloaded tool trees.
- After changes that touch encoding, decoding, metadata, or validation, run targeted tests plus the relevant format matrix smoke test.

## Common Commands

```powershell
python -m compileall src hdr2avif.py jxr2avif.py scripts\format_matrix_validation.py
python -m pytest -q
python -m pytest -m fidelity -q
python scripts\format_matrix_validation.py --run-id local-smoke --width 64 --height 40 --quality 100 --speed 8
```

## Spec Kit

Use Spec Kit for larger feature work:

1. Create or select a feature branch named like `001-feature-name`.
2. Keep feature artifacts in `specs/<branch-name>/`.
3. Maintain `spec.md`, `plan.md`, and `tasks.md` before implementation changes.
4. Update `.specify/memory/constitution.md` when project-wide engineering rules change.

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan.
<!-- SPECKIT END -->
