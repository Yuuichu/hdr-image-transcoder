# Quickstart: PQ TIFF to Ultra HDR JPEG

## Prerequisites

- Known true BT.2020 PQ TIFF input.
- Python dependencies installed from `requirements.txt`.
- Optional `libultrahdr` DLL available through one of:
  - `HDR_TRANSCODER_UHDR_DLL`
  - `UHDR_DLL`
  - `tools/libultrahdr/uhdr.dll`

## Dedicated Apple-oriented Ultra HDR Path

```powershell
$env:HDR_TRANSCODER_UHDR_DLL = "C:\Path\To\uhdr.dll"

python hdr2avif.py input_bt2020_pq.tif output_uhdr.jpg `
  --format ultrahdr `
  --fidelity compat `
  --bt2020-pq-tiff `
  --uhdr-backend libultrahdr `
  --gainmap-scale 2 `
  --target-peak-nits 1000 `
  --verify-fidelity `
  --info-json
```

## Auto Fallback Mode

```powershell
python hdr2avif.py input_bt2020_pq.tif output_uhdr.jpg `
  --format ultrahdr `
  --fidelity compat `
  --bt2020-pq-tiff `
  --uhdr-backend auto `
  --verify-fidelity `
  --info-json
```

If `libultrahdr` is unavailable, `auto` falls back to the legacy `imagecodecs`
Ultra HDR path and prints a warning.

## Inspect Runtime Tools

```powershell
python -m hdr_transcoder.tools_check
```

The report includes optional `uhdr.dll` discovery status.

## Matrix Validation

```powershell
python scripts\format_matrix_validation.py `
  --input output\format-matrix\codex-uhdr-lib-smoke-q100\sources\reference_bt2020_pq_untagged.tif `
  --bt2020-pq-tiff `
  --run-id local-pqtiff-uhdr `
  --quality 100 `
  --speed 8 `
  --timeout 900
```
