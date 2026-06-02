# AGENTS.md

Compact guidance for Zap and Codex agents working in this repository.

## Language

Use Chinese for user-facing explanations unless asked otherwise.

## Project

Windows-first HDR still-image transcoder. Core package: `src/hdr_transcoder`.
Entry points: `hdr2avif.py` (CLI), `jxr2avif.py` (backward-compat wrapper).
Electron GUI in `electron/`. README and CLAUDE.md have detailed usage docs.

## Architecture Gotchas

- **Flat `src/` modules are thin shims.** `src/cli.py`, `src/decoder.py`, etc.
  re-export from `hdr_transcoder.*`. Add new code to `src/hdr_transcoder/` only.
- **JXL encoding MUST go through bundled `cjxl.exe`.** Never add an
  `imagecodecs.jpegxl_encode` fallback — it produces misleading HDR metadata.
- **Default `.avif` output is gainmap AVIF, not standard AVIF.** Use
  `--format avif` for standard 10-bit PQ HDR AVIF.
- **Master fidelity requires `--jxl-mode linear-srgb`** (lossless linear JXL).
  Non-JXL outputs under master need `--allow-non-master`.
- **HEIF/AVIF HDR outputs must use Rec.2020 non-constant luminance matrix
  (`9/16/9`).** Identity matrix produces a red-tinted image on WIC and some
  viewers. Do NOT switch back to RGB identity matrix.
- **Validation must stay consistent across all layers** (HTML `min` attributes,
  renderer `validateOptions`, main process `validateOptions`, Python CLI
  `_validate_args`). After changing a rule, grep for the old value everywhere.
- **Do not overwrite input files.** CLI avoids it when default output extension
  matches input extension; `_converted_name` appends `_converted`.

## Commands

```powershell
# Install
pip install -r requirements.txt
npm install

# Syntax check
python -m compileall src hdr_transcoder hdr2avif.py jxr2avif.py
node --check electron\main.js electron\preload.js electron\renderer\app.js

# Tests (fidelity tests are skipped by default)
python -m pytest -q                    # quick tests only
python -m pytest -m "" -q              # ALL tests
python -m pytest -m fidelity -q        # fidelity-only

# Runtime self-check (also run after npm run prepack)
python -m hdr_transcoder.tools_check --pretty
python -m hdr_transcoder.tools_check --invoke   # also test tool --help outputs

# GUI checks
npm start
npm run prepack

# Format matrix smoke test (use small dimensions for speed)
python scripts\format_matrix_validation.py --run-id local-smoke --width 64 --height 40 --quality 100 --speed 8
```

## Testing Quirks

- `pytest` default markers skip fidelity and GUI tests. Use `-m ""` to run
  everything, `-m fidelity` for slow encode/decode round-trips.
- Tools tests (`-m tools`) require bundled `.exe` files under `tools/`.
- GUI tests (`-m gui`) use Playwright against the Electron renderer.
  `page.evaluate()` state is lost on `location.reload()` or navigation —
  re-inject mocks after every navigation. Forms with `<button type="submit">`
  need `event.preventDefault()` or they trigger a GET navigation.
  `browser_select_option` requires the `values` parameter (array of strings).

## PowerShell Warning

`Stop-Process -Name "powershell"` kills ALL PowerShell sessions. Target
specific PIDs or filter on the command line.

## Spec Kit

For feature work:
1. Create branch `NNN-feature-name` with matching `specs/<branch>/`.
2. Maintain `spec.md`, `plan.md`, `tasks.md` before implementation.
3. Update `.specify/memory/constitution.md` when engineering rules change.

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan.
<!-- SPECKIT END -->
