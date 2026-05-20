# libavif Tools

This directory carries the Windows x64 libavif command-line tools used by the
Python pipeline.

- `avifgainmaputil.exe` is the official libavif 1.4.1 tool. The app uses it for
  `printmetadata` and `tonemap` validation paths.
- `avifgainmaputil_hdr.exe` is the headroom-aware helper used for gain map AVIF
  encoding. It accepts the official `avifgainmaputil combine` arguments plus:
  - `--base-headroom <stops>`
  - `--alternate-headroom <stops>`

The helper preserves libavif's official `combine` implementation for AVIF
container writing, AV1 encoding, and gain map generation. When a headroom
override is supplied, it patches the ISO gain map metadata fractions in the
written AVIF and verifies the result with `avifgainmaputil printmetadata`.

## Rebuilding `avifgainmaputil_hdr.exe`

The checked-in helper is built from `avifgainmaputil_hdr.py` with PyInstaller:

```powershell
pyinstaller --onefile --clean `
  --name avifgainmaputil_hdr `
  --distpath tools\libavif `
  --workpath tmp_pyinstaller_hdr `
  --specpath tmp_pyinstaller_hdr `
  tools\libavif\avifgainmaputil_hdr.py
```

`avifgainmaputil_hdr.exe` must remain next to `avifgainmaputil.exe` because the
current wrapper delegates the actual encode and metadata inspection work to that
sibling binary. This wrapper is a compatibility/debug path; the product target is
a native patched libavif helper with the same executable name and command-line
flags.

## Native Patched Helper Target

Use libavif `v1.4.1` as the fixed source baseline. The target binary is still
named `avifgainmaputil_hdr.exe` so the Python pipeline and Electron portable
package do not need a different path.

Recommended native build flow:

```powershell
git clone https://github.com/AOMediaCodec/libavif.git tmp_libavif_src\libavif
cd tmp_libavif_src\libavif
git checkout v1.4.1
# Apply the headroom override patch described below.
cmake -S . -B build -DAVIF_BUILD_APPS=ON -DAVIF_ENABLE_WERROR=OFF
cmake --build build --config Release --target avifgainmaputil
copy build\apps\Release\avifgainmaputil.exe ..\..\tools\libavif\avifgainmaputil_hdr.exe
```

After replacing the helper, validate:

```powershell
tools\libavif\avifgainmaputil_hdr.exe combine --help
python -m pytest -m fidelity
```

## Equivalent libavif Source Patch

For a native libavif build, apply the same behavior to libavif 1.4.1 in
`apps/avifgainmaputil/combine_command.cc`:

1. Add `arg_base_headroom_` and `arg_alternate_headroom_` as optional float
   arguments in `combine_command.h`.
2. Register `--base-headroom` and `--alternate-headroom` in
   `CombineCommand::CombineCommand()`.
3. After `avifImageComputeGainMap(...)` and the existing `--max-headroom` cap,
   assign the requested values with `avifDoubleToUnsignedFraction(...)`:

```cpp
if (arg_base_headroom_.provenance() == argparse::Provenance::SPECIFIED) {
  if (!avifDoubleToUnsignedFraction(arg_base_headroom_.value(),
                                    &base_image->gainMap->baseHdrHeadroom)) {
    std::cout << "Unable to express base headroom as a fraction";
    return AVIF_RESULT_INVALID_ARGUMENT;
  }
}
if (arg_alternate_headroom_.provenance() == argparse::Provenance::SPECIFIED) {
  if (!avifDoubleToUnsignedFraction(arg_alternate_headroom_.value(),
                                    &base_image->gainMap->alternateHdrHeadroom)) {
    std::cout << "Unable to express alternate headroom as a fraction";
    return AVIF_RESULT_INVALID_ARGUMENT;
  }
}
```

Keep all other `combine` behavior unchanged.
