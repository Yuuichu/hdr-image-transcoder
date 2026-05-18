"""
HDR to multi-format converter.

Converts JXR, JXL, EXR, AVIF, HEIC, Ultra HDR, Radiance HDR, and other
HDR images to:
  - Gainmap AVIF (ISO 21496-1): default for .avif
  - JPEG XL HDR: .jxl
  - Ultra HDR JPEG: .jpg/.jpeg
  - Standard AVIF HDR: .avif with -f avif
  - HEIF HDR: .heic/.heif

Usage:
    python hdr2avif.py <input> [output]
    python hdr2avif.py <directory> --output-dir <dir> --format jxl
"""
from src.cli import main

if __name__ == "__main__":
    main()
