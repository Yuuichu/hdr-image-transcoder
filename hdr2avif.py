"""
HDR to multi-format converter.

Converts JXR, JXL, EXR, AVIF, HEIC, Ultra HDR, Radiance HDR, and other
HDR images to:
  - JPEG XL linear scRGB lossless: default strict master output
  - Gainmap AVIF (ISO 21496-1): compatibility output
  - Ultra HDR JPEG: .jpg/.jpeg
  - Standard AVIF HDR: .avif with -f avif
  - HEIF HDR: .heic/.heif

Usage:
    python hdr2avif.py <input> [output]
    python hdr2avif.py <directory> --output-dir <dir> --format jxl
"""
from hdr_transcoder.cli import main

if __name__ == "__main__":
    main()
